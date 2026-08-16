#!/usr/bin/env -S uv run --script
"""
Consolidated evaluation for thesis Section 5.1.

This script keeps Mitsuba BSDFs fixed and changes only the integrator. It
produces repeated-seed statistics for:

1. A diffuse white-furnace convergence test.
2. A GGX roughconductor reference comparison.
3. A matched-seed versus independent-seed identity control.
4. A stock Cornell-box integration comparison.
5. Primary-hit albedo, shading-normal, and depth AOV output.

Furnace statistics are measured only over primary rays that hit the sphere.
The mask is eroded by two pixels to remove stochastic silhouette/filter mixing.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import drjit as dr
import mitsuba as mi
import numpy as np

SCRIPT_PATH = Path(__file__).resolve()
TESTS_DIR = SCRIPT_PATH.parents[2]
ROOT = SCRIPT_PATH.parents[3]
sys.path.insert(0, str(TESTS_DIR))

import _common  # noqa: F401 -- selects the variant and registers custom plugins
from assets.scenes.white_furnace import white_furnace_scene


DEFAULT_OUTPUT = ROOT / "outputs" / "evaluation" / "5_1_path_tracer"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument("--furnace-resolution", type=int, default=128)
    parser.add_argument("--cornell-resolution", type=int, default=256)
    parser.add_argument(
        "--only",
        choices=("all", "aov"),
        default="all",
        help="Run the complete evaluation or only the inexpensive AOV check.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run a low-cost smoke test of masks, rendering, and file output.",
    )
    return parser.parse_args()


def set_common_film(scene_dict: dict, resolution: int, spp: int) -> None:
    sensor = scene_dict["sensor"]
    sensor["film"] = {
        "type": "hdrfilm",
        "width": resolution,
        "height": resolution,
        "pixel_format": "rgb",
        "component_format": "float32",
        "rfilter": {"type": "box"},
    }
    sensor["sampler"] = {"type": "independent", "sample_count": spp}


def render_rgb(scene: mi.Scene, spp: int, seed: int) -> np.ndarray:
    return np.array(mi.render(scene, spp=spp, seed=seed), dtype=np.float32)[..., :3]


def erode_mask(mask: np.ndarray, iterations: int = 2) -> np.ndarray:
    """Eight-neighbour binary erosion implemented without extra dependencies."""
    result = np.asarray(mask, dtype=bool).copy()
    for _ in range(iterations):
        padded = np.pad(result, 1, mode="constant", constant_values=False)
        neighbours = [
            padded[dy : dy + result.shape[0], dx : dx + result.shape[1]]
            for dy in range(3)
            for dx in range(3)
        ]
        result = np.logical_and.reduce(neighbours)
    return result


def primary_hit_mask(scene: mi.Scene, erosion: int = 2) -> np.ndarray:
    """Return an eroded pixel-centre mask of primary rays hitting geometry."""
    sensor = scene.sensors()[0]
    size = sensor.film().crop_size()
    width, height = int(size.x), int(size.y)
    index = dr.arange(mi.UInt32, width * height)
    film_sample = mi.Point2f(
        (mi.Float(index % width) + 0.5) / width,
        (mi.Float(index // width) + 0.5) / height,
    )
    ray, _ = sensor.sample_ray(
        mi.Float(0), mi.Float(0.5), film_sample, mi.Point2f(0.5), True
    )
    mask = np.array(scene.ray_test(ray), dtype=bool).reshape(height, width)
    return erode_mask(mask, erosion)


def masked_stats(image: np.ndarray, mask: np.ndarray) -> tuple[float, float]:
    values = image[mask]
    return float(values.mean()), float(values.std())


def aggregate_scalar_rows(rows: list[dict]) -> dict:
    render_means = np.array([r["masked_mean"] for r in rows], dtype=np.float64)
    spatial_sds = np.array([r["masked_spatial_sd"] for r in rows], dtype=np.float64)
    return {
        "mean": float(render_means.mean()),
        "between_seed_sd": float(render_means.std(ddof=1)) if len(rows) > 1 else 0.0,
        "mean_spatial_sd": float(spatial_sds.mean()),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_bitmap(path: Path, image: np.ndarray) -> None:
    tensor = mi.TensorXf(np.ascontiguousarray(image, dtype=np.float32))
    mi.util.write_bitmap(str(path), tensor)


def run_aov_sanity(
    data: Path,
    figures: Path,
    resolution: int,
    spp: int,
) -> tuple[list[dict], dict]:
    """Check the opt-in primary-hit AOV layout and basic channel semantics."""
    print("\n[5/5] Primary-hit AOV sanity check", flush=True)
    scene = mi.load_dict(
        {
            "type": "scene",
            "integrator": {
                "type": "path_tracer",
                "max_depth": 8,
                "with_aovs": True,
            },
            "sensor": {
                "type": "physical_camera",
                "fov": 35,
                "aperture_radius": 0.0,
                "focus_distance": 5.0,
                "to_world": mi.ScalarTransform4f().look_at(
                    origin=[0, -5, 5.5], target=[0, 0, 0.5], up=[0, 0, 1]
                ),
                "film": {
                    "type": "hdrfilm",
                    "width": resolution,
                    "height": resolution,
                    "pixel_format": "rgb",
                    "component_format": "float32",
                    "rfilter": {"type": "box"},
                },
                "sampler": {"type": "independent", "sample_count": spp},
            },
            "light": {
                "type": "constant",
                "radiance": {"type": "rgb", "value": [0.6, 0.6, 0.6]},
            },
            "sphere": {
                "type": "sphere",
                "to_world": mi.ScalarTransform4f().translate([0, 0, 0.8]),
                "bsdf": {
                    "type": "principled_bsdf",
                    "base_colour": [0.8, 0.1, 0.1],
                    "roughness": 0.3,
                    "metallic": 0.0,
                },
            },
            "floor": {
                "type": "rectangle",
                "to_world": mi.ScalarTransform4f().scale(4),
                "bsdf": {
                    "type": "principled_bsdf",
                    "base_colour": [0.4, 0.4, 0.4],
                    "roughness": 0.6,
                    "metallic": 0.0,
                },
            },
        }
    )

    image = np.array(mi.render(scene, spp=spp, seed=0), dtype=np.float32)
    names = [str(name) for name in scene.integrator().aov_names()]
    expected_names = [
        "albedo.R",
        "albedo.G",
        "albedo.B",
        "normal.X",
        "normal.Y",
        "normal.Z",
        "depth.Y",
    ]
    channel_count = int(image.shape[-1])
    if channel_count < 10:
        raise RuntimeError(f"Expected 10 RGB+AOV channels, received {channel_count}")

    rgb = image[..., :3]
    albedo = image[..., 3:6]
    normal = image[..., 6:9]
    depth = image[..., 9]
    hit = depth > 0.0
    miss = ~hit

    expected_albedos = np.array([[0.8, 0.1, 0.1], [0.4, 0.4, 0.4]])
    albedo_distances = np.linalg.norm(
        albedo[hit, None, :] - expected_albedos[None, :, :], axis=-1
    )
    nearest_albedo_error = np.min(albedo_distances, axis=1)
    normal_length_error = np.abs(np.linalg.norm(normal[hit], axis=-1) - 1.0)
    miss_max = float(
        max(
            np.max(np.abs(albedo[miss])) if np.any(miss) else 0.0,
            np.max(np.abs(normal[miss])) if np.any(miss) else 0.0,
            np.max(np.abs(depth[miss])) if np.any(miss) else 0.0,
        )
    )

    checks = [
        {
            "check": "channel_layout",
            "measured": f"{channel_count} channels; {','.join(names)}",
            "expected": f"10 channels; {','.join(expected_names)}",
            "status": "PASS" if channel_count == 10 and names == expected_names else "FAIL",
        },
        {
            "check": "finite_values",
            "measured": str(bool(np.isfinite(image).all())),
            "expected": "True",
            "status": "PASS" if np.isfinite(image).all() else "FAIL",
        },
        {
            "check": "miss_aovs_zero",
            "measured": f"{miss_max:.8g}",
            "expected": "<= 1e-6",
            "status": "PASS" if np.any(miss) and miss_max <= 1e-6 else "FAIL",
        },
        {
            "check": "material_albedo",
            "measured": f"median nearest-colour error {np.median(nearest_albedo_error):.8g}",
            "expected": "< 1e-3",
            "status": "PASS"
            if np.any(hit) and np.median(nearest_albedo_error) < 1e-3
            else "FAIL",
        },
        {
            "check": "unit_shading_normals",
            "measured": f"median length error {np.median(normal_length_error):.8g}",
            "expected": "< 1e-3",
            "status": "PASS"
            if np.any(hit) and np.median(normal_length_error) < 1e-3
            else "FAIL",
        },
        {
            "check": "positive_hit_depth",
            "measured": f"range {depth[hit].min():.6g} to {depth[hit].max():.6g}",
            "expected": "positive, non-constant range",
            "status": "PASS"
            if np.any(hit) and depth[hit].min() > 0 and depth[hit].max() > depth[hit].min()
            else "FAIL",
        },
    ]
    write_csv(data / "aov_sanity.csv", checks)

    depth_display = np.zeros_like(depth)
    if np.any(hit):
        depth_display[hit] = depth[hit] / depth[hit].max()
    write_bitmap(figures / "aov_beauty.png", rgb)
    write_bitmap(figures / "aov_albedo.png", albedo)
    write_bitmap(figures / "aov_normal.png", normal * 0.5 + 0.5)
    write_bitmap(
        figures / "aov_depth.png", np.repeat(depth_display[..., None], 3, axis=-1)
    )

    summary = {
        "resolution": [resolution, resolution],
        "spp": spp,
        "channel_count": channel_count,
        "aov_names": names,
        "hit_pixels": int(hit.sum()),
        "miss_pixels": int(miss.sum()),
        "all_checks_pass": all(row["status"] == "PASS" for row in checks),
    }
    return checks, summary


def render_cornell_aovs(
    renders: Path,
    figures: Path,
    resolution: int,
    spp: int,
) -> dict:
    """Render a simple Cornell-box demonstration of the validated AOV output."""
    print("  Rendering Cornell-box AOV demonstration", flush=True)
    scene_dict = mi.cornell_box()
    scene_dict["integrator"] = {
        "type": "path_tracer",
        "max_depth": 8,
        "rr_depth": 3,
        "with_aovs": True,
    }
    set_common_film(scene_dict, resolution, spp)
    scene = mi.load_dict(scene_dict)
    image = np.array(mi.render(scene, spp=spp, seed=0), dtype=np.float32)
    if image.shape[-1] < 10:
        raise RuntimeError(
            f"Expected 10 RGB+AOV channels for Cornell box, received {image.shape[-1]}"
        )

    beauty = image[..., :3]
    albedo = image[..., 3:6]
    normal_display = image[..., 6:9] * 0.5 + 0.5
    depth = image[..., 9]
    hit = depth > 0.0
    depth_display = np.zeros_like(depth)
    if np.any(hit):
        low, high = np.percentile(depth[hit], [1.0, 99.0])
        depth_display[hit] = np.clip((depth[hit] - low) / max(high - low, 1e-6), 0, 1)
    depth_rgb = np.repeat(depth_display[..., None], 3, axis=-1)

    write_bitmap(renders / "cornell_aov_beauty.exr", beauty)
    write_bitmap(renders / "cornell_aov_albedo.exr", albedo)
    write_bitmap(renders / "cornell_aov_normal.exr", image[..., 6:9])
    write_bitmap(renders / "cornell_aov_depth.exr", depth[..., None])
    write_bitmap(figures / "cornell_aov_beauty.png", beauty)
    write_bitmap(figures / "cornell_aov_albedo.png", albedo)
    write_bitmap(figures / "cornell_aov_depth.png", depth_rgb)
    write_bitmap(figures / "cornell_aov_normals.png", normal_display)

    top = np.concatenate([beauty, albedo], axis=1)
    bottom = np.concatenate([depth_rgb, normal_display], axis=1)
    write_bitmap(figures / "cornell_aov_outputs.png", np.concatenate([top, bottom], axis=0))
    return {
        "resolution": [resolution, resolution],
        "spp": spp,
        "layout": ["beauty", "albedo", "depth", "normals"],
        "composite": "figures/cornell_aov_outputs.png",
    }


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_metadata() -> dict:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True
            ).strip()
        )
        return {"commit": commit, "dirty_worktree": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty_worktree": None}


def furnace_scene(
    bsdf: dict,
    integrator: str,
    spp: int,
    resolution: int,
) -> mi.Scene:
    scene_dict = white_furnace_scene(
        bsdf, integrator_type=integrator, spp=spp, max_depth=16
    )
    # Mitsuba's path integrator defaults to rr_depth=5 while the custom
    # integrator defaults to 3. Hold this fixed so only the implementation
    # changes between comparison renders.
    scene_dict["integrator"]["rr_depth"] = 3
    set_common_film(scene_dict, resolution, spp)
    return mi.load_dict(scene_dict)


def run_diffuse_furnace(
    renders: Path,
    figures: Path,
    seeds: list[int],
    resolution: int,
    spp_values: list[int],
) -> tuple[list[dict], list[dict]]:
    print("\n[1/5] Diffuse white-furnace convergence", flush=True)
    bsdf = {
        "type": "diffuse",
        "reflectance": {"type": "rgb", "value": [1.0, 1.0, 1.0]},
    }
    per_render: list[dict] = []
    summary: list[dict] = []

    for spp in spp_values:
        for integrator in ("path", "path_tracer"):
            scene = furnace_scene(bsdf, integrator, spp, resolution)
            mask = primary_hit_mask(scene)
            rows = []
            images = []
            for seed in seeds:
                print(
                    f"  diffuse integrator={integrator:<11} spp={spp:<4} seed={seed}",
                    flush=True,
                )
                image = render_rgb(scene, spp, seed)
                mean, spatial_sd = masked_stats(image, mask)
                row = {
                    "test": "diffuse_furnace",
                    "integrator": integrator,
                    "roughness": "",
                    "spp": spp,
                    "seed": seed,
                    "masked_mean": mean,
                    "masked_spatial_sd": spatial_sd,
                }
                rows.append(row)
                per_render.append(row)
                images.append(image)

            stats = aggregate_scalar_rows(rows)
            summary.append(
                {
                    "test": "diffuse_furnace",
                    "integrator": integrator,
                    "roughness": "",
                    "spp": spp,
                    "seed_count": len(seeds),
                    **stats,
                }
            )
            mean_image = np.stack(images).mean(axis=0)
            stem = f"diffuse_{integrator}_spp{spp}_mean"
            write_bitmap(renders / f"{stem}.exr", mean_image)
            if spp == max(spp_values):
                write_bitmap(figures / f"{stem}.png", mean_image)

    mask_rgb = np.repeat(mask[..., None].astype(np.float32), 3, axis=-1)
    write_bitmap(figures / "furnace_measurement_mask.png", mask_rgb)
    return per_render, summary


def run_roughconductor(
    renders: Path,
    figures: Path,
    seeds: list[int],
    resolution: int,
    spp: int,
) -> tuple[list[dict], list[dict]]:
    print("\n[2/5] Mitsuba GGX roughconductor reference comparison", flush=True)
    per_render: list[dict] = []
    summary: list[dict] = []
    mean_images: dict[tuple[str, float], np.ndarray] = {}

    for roughness in (0.0, 0.5, 1.0):
        alpha = max(roughness * roughness, 1e-4)
        bsdf = {"type": "roughconductor", "distribution": "ggx", "alpha": alpha}
        for integrator in ("path", "path_tracer"):
            scene = furnace_scene(bsdf, integrator, spp, resolution)
            mask = primary_hit_mask(scene)
            rows = []
            images = []
            for seed in seeds:
                print(
                    f"  GGX r={roughness:.1f} integrator={integrator:<11} "
                    f"spp={spp:<4} seed={seed}",
                    flush=True,
                )
                image = render_rgb(scene, spp, seed)
                mean, spatial_sd = masked_stats(image, mask)
                row = {
                    "test": "roughconductor_furnace",
                    "integrator": integrator,
                    "roughness": roughness,
                    "spp": spp,
                    "seed": seed,
                    "masked_mean": mean,
                    "masked_spatial_sd": spatial_sd,
                }
                rows.append(row)
                per_render.append(row)
                images.append(image)

            stats = aggregate_scalar_rows(rows)
            summary.append(
                {
                    "test": "roughconductor_furnace",
                    "integrator": integrator,
                    "roughness": roughness,
                    "spp": spp,
                    "seed_count": len(seeds),
                    **stats,
                }
            )

            mean_image = np.stack(images).mean(axis=0)
            mean_images[(integrator, roughness)] = mean_image
            write_bitmap(
                renders / f"ggx_{integrator}_roughness_{roughness:.1f}_mean.exr",
                mean_image,
            )

    # Two rows (Mitsuba reference, custom integrator), three columns
    # (roughness 0.0, 0.5, 1.0). Labels are supplied by the thesis caption.
    gap_vertical = np.full((resolution, 4, 3), 0.18, dtype=np.float32)
    gap_horizontal = np.full(
        (4, resolution * 3 + gap_vertical.shape[1] * 2, 3),
        0.18,
        dtype=np.float32,
    )
    rows = []
    for integrator in ("path", "path_tracer"):
        rows.append(
            np.concatenate(
                [
                    mean_images[(integrator, 0.0)],
                    gap_vertical,
                    mean_images[(integrator, 0.5)],
                    gap_vertical,
                    mean_images[(integrator, 1.0)],
                ],
                axis=1,
            )
        )
    comparison = np.concatenate([rows[0], gap_horizontal, rows[1]], axis=0)
    write_bitmap(figures / "ggx_roughness_comparison.png", comparison)

    return per_render, summary


def integrator_identity(scene: mi.Scene) -> tuple[str, str]:
    integrator = scene.integrator()
    return type(integrator).__name__, str(integrator).splitlines()[0]


def run_seed_identity_control(
    data: Path,
    figures: Path,
    resolution: int,
    quick: bool,
) -> list[dict]:
    """Show why matched seeds agree and that distinct plugins/seeds differ."""
    print("\n[3/5] Matched-seed and independent-seed identity control", flush=True)
    diffuse = {
        "type": "diffuse",
        "reflectance": {"type": "rgb", "value": [1.0, 1.0, 1.0]},
    }
    configs = [
        ("diffuse", "", diffuse, 64 if quick else 256, 0, 1000),
    ]
    if not quick:
        configs.append(("diffuse", "", diffuse, 1024, 0, 1000))
    for roughness in ((0.5,) if quick else (0.0, 0.5, 1.0)):
        alpha = max(roughness * roughness, 1e-4)
        configs.append(
            (
                "roughconductor",
                roughness,
                {"type": "roughconductor", "distribution": "ggx", "alpha": alpha},
                64 if quick else 256,
                56,
                43,
            )
        )

    rows: list[dict] = []
    visual_pair: tuple[np.ndarray, np.ndarray] | None = None
    for material, roughness, bsdf, spp, custom_independent_seed, reference_independent_seed in configs:
        scenes = {
            "reference": furnace_scene(bsdf, "path", spp, resolution),
            "custom": furnace_scene(bsdf, "path_tracer", spp, resolution),
        }
        reference_python_type, reference_description = integrator_identity(
            scenes["reference"]
        )
        custom_python_type, custom_description = integrator_identity(scenes["custom"])
        mask = primary_hit_mask(scenes["reference"])
        cache: dict[tuple[str, int], np.ndarray] = {}

        for mode, reference_seed, custom_seed in (
            ("matched_seed", 0, 0),
            (
                "independent_seeds",
                reference_independent_seed,
                custom_independent_seed,
            ),
        ):
            for label, seed in (("reference", reference_seed), ("custom", custom_seed)):
                key = (label, seed)
                if key not in cache:
                    print(
                        f"  {material:<14} r={str(roughness):<3} spp={spp:<4} "
                        f"{mode:<17} {label:<9} seed={seed}",
                        flush=True,
                    )
                    cache[key] = render_rgb(scenes[label], spp, seed)

            reference = cache[("reference", reference_seed)]
            custom = cache[("custom", custom_seed)]
            reference_mean, reference_sd = masked_stats(reference, mask)
            custom_mean, custom_sd = masked_stats(custom, mask)
            difference = custom[mask] - reference[mask]
            rows.append(
                {
                    "material": material,
                    "roughness": roughness,
                    "spp": spp,
                    "comparison": mode,
                    "reference_plugin": "path",
                    "reference_python_type": reference_python_type,
                    "reference_description": reference_description,
                    "reference_seed": reference_seed,
                    "custom_plugin": "path_tracer",
                    "custom_python_type": custom_python_type,
                    "custom_description": custom_description,
                    "custom_seed": custom_seed,
                    "reference_mean": reference_mean,
                    "custom_mean": custom_mean,
                    "absolute_mean_difference": abs(custom_mean - reference_mean),
                    "reference_spatial_sd": reference_sd,
                    "custom_spatial_sd": custom_sd,
                    "masked_mae": float(np.abs(difference).mean()),
                    "masked_rmse": float(np.sqrt(np.mean(difference * difference))),
                    "masked_max_absolute_difference": float(np.abs(difference).max()),
                }
            )
            if material == "roughconductor" and roughness == 0.5 and mode == "independent_seeds":
                visual_pair = (reference, custom)

    if visual_pair is not None:
        reference, custom = visual_pair
        difference = np.abs(custom - reference)
        gap = np.full((resolution, 4, 3), 0.18, dtype=np.float32)
        write_bitmap(
            figures / "independent_seed_control_ggx_r05.png",
            np.concatenate(
                [reference, gap, custom, gap, np.clip(difference * 10.0, 0.0, 1.0)],
                axis=1,
            ),
        )

    write_csv(data / "seed_identity_control.csv", rows)
    return rows


def cornell_scene(
    integrator: str,
    max_depth: int,
    spp: int,
    resolution: int,
) -> mi.Scene:
    scene_dict = mi.cornell_box()
    scene_dict["integrator"] = {
        "type": integrator,
        "max_depth": max_depth,
        "rr_depth": 3,
    }
    set_common_film(scene_dict, resolution, spp)
    return mi.load_dict(scene_dict)


def image_metrics(a: np.ndarray, b: np.ndarray) -> dict:
    difference = a - b
    return {
        "signed_mean_difference": float(difference.mean()),
        "mae": float(np.abs(difference).mean()),
        "rmse": float(np.sqrt(np.mean(difference * difference))),
        "max_absolute_difference": float(np.abs(difference).max()),
    }


def run_cornell(
    renders: Path,
    figures: Path,
    seeds: list[int],
    resolution: int,
    spp: int,
) -> tuple[list[dict], list[dict], dict]:
    print("\n[4/5] Stock Cornell-box integration comparison", flush=True)
    per_render: list[dict] = []
    summary: list[dict] = []
    stacks: dict[str, np.ndarray] = {}

    configurations = (("path", "path", 8), ("path_tracer", "path_tracer", 8))
    for configuration, integrator, max_depth in configurations:
        scene = cornell_scene(integrator, max_depth, spp, resolution)
        images = []
        for seed in seeds:
            print(
                f"  Cornell configuration={configuration:<18} "
                f"max_depth={max_depth} spp={spp:<4} seed={seed}",
                flush=True,
            )
            image = render_rgb(scene, spp, seed)
            images.append(image)
            per_render.append(
                {
                    "test": "cornell_box",
                    "configuration": configuration,
                    "plugin": integrator,
                    "max_depth": max_depth,
                    "spp": spp,
                    "seed": seed,
                    "image_mean": float(image.mean()),
                    "image_spatial_sd": float(image.std()),
                }
            )

        stack = np.stack(images)
        stacks[configuration] = stack
        render_means = stack.mean(axis=(1, 2, 3))
        summary.append(
            {
                "test": "cornell_box",
                "configuration": configuration,
                "plugin": integrator,
                "max_depth": max_depth,
                "spp_per_seed": spp,
                "seed_count": len(seeds),
                "effective_spp": spp * len(seeds),
                "mean": float(render_means.mean()),
                "between_seed_sd": float(render_means.std(ddof=1))
                if len(seeds) > 1
                else 0.0,
                "mean_per_pixel_sd": float(stack.std(axis=0, ddof=1).mean())
                if len(seeds) > 1
                else 0.0,
            }
        )

    reference = stacks["path"].mean(axis=0)
    custom = stacks["path_tracer"].mean(axis=0)
    difference = np.abs(custom - reference)
    metrics = image_metrics(custom, reference)

    write_bitmap(renders / "cornell_reference_mean.exr", reference)
    write_bitmap(renders / "cornell_custom_mean.exr", custom)
    write_bitmap(figures / "cornell_reference_mean.png", reference)
    write_bitmap(figures / "cornell_custom_mean.png", custom)
    write_bitmap(
        figures / "cornell_absolute_difference_x20.png",
        np.clip(difference * 20.0, 0.0, 1.0),
    )
    comparison = np.concatenate(
        [reference, custom, np.clip(difference * 20.0, 0.0, 1.0)], axis=1
    )
    write_bitmap(
        figures / "cornell_comparison_reference_custom_diff.png", comparison
    )
    return per_render, summary, metrics


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    data = output / "data"
    renders = output / "renders"
    figures = output / "figures"
    for directory in (data, renders, figures):
        directory.mkdir(parents=True, exist_ok=True)

    if args.quick:
        seeds = [0]
        diffuse_spp = [16, 64]
        rough_spp = 32
        cornell_spp = 16
        furnace_resolution = min(args.furnace_resolution, 64)
        cornell_resolution = min(args.cornell_resolution, 96)
    else:
        seeds = list(range(args.seeds))
        diffuse_spp = [256, 1024]
        rough_spp = 256
        cornell_spp = 128
        furnace_resolution = args.furnace_resolution
        cornell_resolution = args.cornell_resolution

    print("Section 5.1 path-tracer evaluation", flush=True)
    print(f"  output: {output}", flush=True)
    print(f"  seeds: {seeds}", flush=True)

    aov_resolution = 96 if args.quick else 192
    aov_spp = 8 if args.quick else 32
    cornell_aov_resolution = 128 if args.quick else 256
    cornell_aov_spp = 16 if args.quick else 256
    if args.only == "aov":
        _, aov_summary = run_aov_sanity(data, figures, aov_resolution, aov_spp)
        cornell_aov_summary = render_cornell_aovs(
            renders, figures, cornell_aov_resolution, cornell_aov_spp
        )
        metadata = {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "mitsuba_version": mi.__version__,
            "variant": mi.variant(),
            "git": git_metadata(),
            "settings": {"quick": args.quick, "only": "aov"},
            "source_hashes": {
                "evaluation_script": file_sha256(Path(__file__)),
                "path_tracer": file_sha256(ROOT / "integrators" / "path_tracer.py"),
            },
            "aov_sanity": aov_summary,
            "cornell_aov_demonstration": cornell_aov_summary,
        }
        (output / "metadata_aov.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )
        print("\nCompleted AOV-only evaluation.", flush=True)
        print(f"  AOV results: {data / 'aov_sanity.csv'}", flush=True)
        return

    diffuse_rows, diffuse_summary = run_diffuse_furnace(
        renders, figures, seeds, furnace_resolution, diffuse_spp
    )
    rough_rows, rough_summary = run_roughconductor(
        renders, figures, seeds, furnace_resolution, rough_spp
    )
    seed_control_rows = run_seed_identity_control(
        data, figures, furnace_resolution, args.quick
    )
    cornell_rows, cornell_summary, cornell_metrics = run_cornell(
        renders, figures, seeds, cornell_resolution, cornell_spp
    )
    _, aov_summary = run_aov_sanity(data, figures, aov_resolution, aov_spp)
    cornell_aov_summary = render_cornell_aovs(
        renders, figures, cornell_aov_resolution, cornell_aov_spp
    )

    per_render_rows = diffuse_rows + rough_rows
    write_csv(data / "furnace_per_render.csv", per_render_rows)
    write_csv(data / "furnace_summary.csv", diffuse_summary + rough_summary)
    write_csv(data / "cornell_per_render.csv", cornell_rows)
    write_csv(data / "cornell_summary.csv", cornell_summary)

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "mitsuba_version": mi.__version__,
        "variant": mi.variant(),
        "git": git_metadata(),
        "settings": {
            "quick": args.quick,
            "seeds": seeds,
            "sampler": "independent",
            "reconstruction_filter": "box",
            "furnace_resolution": furnace_resolution,
            "diffuse_spp": diffuse_spp,
            "roughconductor_spp": rough_spp,
            "furnace_max_depth": 16,
            "rr_depth": 3,
            "furnace_mask_erosion_pixels": 2,
            "cornell_resolution": cornell_resolution,
            "cornell_spp_per_seed": cornell_spp,
            "cornell_effective_spp": cornell_spp * len(seeds),
            "cornell_max_depth": 8,
            "aov_resolution": aov_resolution,
            "aov_spp": aov_spp,
            "cornell_aov_resolution": cornell_aov_resolution,
            "cornell_aov_spp": cornell_aov_spp,
        },
        "source_hashes": {
            "evaluation_script": file_sha256(Path(__file__)),
            "path_tracer": file_sha256(ROOT / "integrators" / "path_tracer.py"),
            "white_furnace_scene": file_sha256(
                ROOT / "assets" / "scenes" / "white_furnace.py"
            ),
        },
        "cornell_comparison": cornell_metrics,
        "seed_identity_control_rows": len(seed_control_rows),
        "aov_sanity": aov_summary,
        "cornell_aov_demonstration": cornell_aov_summary,
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    print("\nCompleted.", flush=True)
    print(f"  Furnace summary: {data / 'furnace_summary.csv'}", flush=True)
    print(f"  Cornell summary: {data / 'cornell_summary.csv'}", flush=True)
    print(f"  Metadata:        {output / 'metadata.json'}", flush=True)


if __name__ == "__main__":
    main()
