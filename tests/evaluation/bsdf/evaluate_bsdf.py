#!/usr/bin/env -S uv run --script
"""Canonical evaluation for thesis Section 5.2: Principled BSDF."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
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

import _common  # noqa: E402,F401 -- variant and custom plugin registration
from assets.scenes.white_furnace import white_furnace_scene  # noqa: E402
from mitsuba.chi2 import BSDFAdapter, ChiSquareTest, SphericalDomain  # noqa: E402


DEFAULT_OUTPUT = ROOT / "outputs" / "evaluation" / "5_2_bsdf"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument("--quick", action="store_true")
    return parser.parse_args()


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_bitmap(path: Path, image: np.ndarray) -> None:
    mi.util.write_bitmap(
        str(path), mi.TensorXf(np.ascontiguousarray(image, dtype=np.float32))
    )


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


def erode_mask(mask: np.ndarray, iterations: int = 2) -> np.ndarray:
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


def furnace_scene(bsdf: dict, spp: int, resolution: int) -> mi.Scene:
    scene = white_furnace_scene(
        bsdf, integrator_type="path_tracer", spp=spp, max_depth=16
    )
    scene["integrator"]["rr_depth"] = 3
    scene["sensor"]["film"] = {
        "type": "hdrfilm",
        "width": resolution,
        "height": resolution,
        "pixel_format": "rgb",
        "component_format": "float32",
        "rfilter": {"type": "box"},
    }
    scene["sensor"]["sampler"] = {
        "type": "independent",
        "sample_count": spp,
    }
    return mi.load_dict(scene)


def render_rgb(scene: mi.Scene, spp: int, seed: int) -> np.ndarray:
    return np.array(mi.render(scene, spp=spp, seed=seed), dtype=np.float32)[..., :3]


def aggregate_masked(images: list[np.ndarray], mask: np.ndarray) -> dict:
    means = np.array([image[mask].mean() for image in images], dtype=np.float64)
    spatial = np.array([image[mask].std() for image in images], dtype=np.float64)
    return {
        "mean": float(means.mean()),
        "between_seed_sd": float(means.std(ddof=1)) if len(means) > 1 else 0.0,
        "mean_spatial_sd": float(spatial.mean()),
    }


def principled_config(mode: str, roughness: float) -> dict:
    result = {
        "type": "principled_bsdf",
        "base_colour": [1.0, 1.0, 1.0],
        "roughness": roughness,
        "metallic": 0.0,
    }
    if mode == "metallic":
        result["metallic"] = 1.0
    elif mode == "lambert_control":
        result["specular"] = 0.0
    return result


def run_opaque_furnace(
    data: Path,
    renders: Path,
    figures: Path,
    seeds: list[int],
    spp: int,
    resolution: int,
) -> list[dict]:
    print("\n[1/5] Principled opaque white-furnace sweep", flush=True)
    summary: list[dict] = []
    per_render: list[dict] = []
    means: dict[tuple[str, float], np.ndarray] = {}
    roughnesses = (0.0, 0.5, 1.0)

    for mode in ("opaque_default", "metallic", "lambert_control"):
        for roughness in roughnesses:
            scene = furnace_scene(
                principled_config(mode, roughness), spp, resolution
            )
            mask = primary_hit_mask(scene)
            images = []
            for seed in seeds:
                print(
                    f"  mode={mode:<16} roughness={roughness:.1f} seed={seed}",
                    flush=True,
                )
                image = render_rgb(scene, spp, seed)
                images.append(image)
                per_render.append(
                    {
                        "mode": mode,
                        "roughness": roughness,
                        "spp": spp,
                        "seed": seed,
                        "masked_mean": float(image[mask].mean()),
                        "masked_spatial_sd": float(image[mask].std()),
                    }
                )

            stats = aggregate_masked(images, mask)
            summary.append(
                {
                    "mode": mode,
                    "roughness": roughness,
                    "spp": spp,
                    "seed_count": len(seeds),
                    **stats,
                }
            )
            mean_image = np.stack(images).mean(axis=0)
            means[(mode, roughness)] = mean_image
            write_bitmap(
                renders / f"furnace_{mode}_roughness_{roughness:.1f}_mean.exr",
                mean_image,
            )

    gap_v = np.full((resolution, 4, 3), 0.18, dtype=np.float32)
    gap_h = np.full((4, resolution * 3 + 8, 3), 0.18, dtype=np.float32)
    rows = []
    for mode in ("opaque_default", "metallic"):
        rows.append(
            np.concatenate(
                [
                    means[(mode, 0.0)],
                    gap_v,
                    means[(mode, 0.5)],
                    gap_v,
                    means[(mode, 1.0)],
                ],
                axis=1,
            )
        )
    write_bitmap(
        figures / "principled_furnace_roughness_comparison.png",
        np.concatenate([rows[0], gap_h, rows[1]], axis=0),
    )
    write_csv(data / "furnace_per_render.csv", per_render)
    write_csv(data / "furnace_summary.csv", summary)
    return summary


def chi_xml(**values: float | list[float]) -> str:
    lines = []
    for name, value in values.items():
        if isinstance(value, list):
            text = ", ".join(str(v) for v in value)
            lines.append(f'<rgb name="{name}" value="{text}"/>')
        else:
            lines.append(f'<float name="{name}" value="{value}"/>')
    return "\n".join(lines)


def run_one_chi(
    name: str,
    plugin: str,
    xml: str,
    res: int,
    ires: int,
    expectation: str,
    diagnostic_directory: Path,
) -> dict:
    print(f"  {name} (res={res})", flush=True)
    adapter = BSDFAdapter(plugin, xml)
    test = ChiSquareTest(
        domain=SphericalDomain(),
        sample_func=adapter[0],
        pdf_func=adapter[1],
        sample_dim=3,
        res=res,
        ires=ires,
    )
    previous_directory = Path.cwd()
    try:
        os.chdir(diagnostic_directory)
        passed = bool(test.run(0.01))
    finally:
        os.chdir(previous_directory)
    histogram_sum = float(np.asarray(test.histogram_sum).reshape(-1)[0])
    pdf_sum = float(np.asarray(test.pdf_sum).reshape(-1)[0])
    return {
        "configuration": name,
        "plugin": plugin,
        "res": res,
        "ires": ires,
        "passed": passed,
        "p_value": float(test.p_value),
        "histogram_sum": histogram_sum,
        "pdf_sum": pdf_sum,
        "expectation": expectation,
        "expected_outcome": (
            passed if expectation == "pass" else not passed
        ),
    }


def run_chi_squared(data: Path, quick: bool) -> list[dict]:
    print("\n[2/5] BSDF sample/PDF chi-squared consistency", flush=True)
    broad_reference = chi_xml(
        base_color=[1.0, 1.0, 1.0], roughness=1.0, metallic=0.0
    )
    sharp_reference = chi_xml(
        base_color=[0.95, 0.77, 0.33], roughness=0.1, metallic=1.0
    )
    configs = [
        ("Mitsuba broad reference", "principled", broad_reference, "pass"),
        ("Mitsuba sharp reference", "principled", sharp_reference, "harness_fail"),
        (
            "Diffuse",
            "principled_bsdf",
            chi_xml(base_colour=[1, 1, 1], roughness=1.0, metallic=0.0),
            "pass",
        ),
        (
            "Plastic",
            "principled_bsdf",
            chi_xml(base_colour=[0.2, 0.3, 0.8], roughness=0.3, metallic=0.0),
            "pass",
        ),
        (
            "Metal",
            "principled_bsdf",
            chi_xml(base_colour=[0.95, 0.77, 0.33], roughness=0.3, metallic=1.0),
            "pass",
        ),
        (
            "Mixed",
            "principled_bsdf",
            chi_xml(base_colour=[0.5, 0.5, 0.5], roughness=0.4, metallic=0.5),
            "pass",
        ),
        (
            "Clearcoat broad",
            "principled_bsdf",
            chi_xml(
                base_colour=[0.8, 0.8, 0.8],
                roughness=1.0,
                metallic=0.0,
                specular=0.0,
                clearcoat=1.0,
                clearcoat_gloss=0.0,
            ),
            "pass",
        ),
        (
            "Clearcoat all three lobes",
            "principled_bsdf",
            chi_xml(
                base_colour=[0.2, 0.3, 0.8],
                roughness=0.3,
                metallic=0.0,
                specular=0.5,
                clearcoat=1.0,
                clearcoat_gloss=0.3,
            ),
            "pass",
        ),
        (
            "Clearcoat metallic base",
            "principled_bsdf",
            chi_xml(
                base_colour=[0.95, 0.77, 0.33],
                roughness=0.3,
                metallic=1.0,
                clearcoat=1.0,
                clearcoat_gloss=0.3,
            ),
            "pass",
        ),
        (
            "Clearcoat sharp gloss 1.0",
            "principled_bsdf",
            chi_xml(
                base_colour=[0.8, 0.8, 0.8],
                roughness=1.0,
                metallic=0.0,
                specular=0.0,
                clearcoat=1.0,
                clearcoat_gloss=1.0,
            ),
            "harness_fail",
        ),
    ]

    if quick:
        configs = [configs[0], configs[2], configs[5], configs[6]]
        res, ires = 51, 8
    else:
        res, ires = 201, 32

    rows = [
        run_one_chi(name, plugin, xml, res, ires, expected, data)
        for name, plugin, xml, expected in configs
    ]

    if not quick:
        gloss95 = chi_xml(
            base_colour=[0.8, 0.8, 0.8],
            roughness=1.0,
            metallic=0.0,
            specular=0.0,
            clearcoat=1.0,
            clearcoat_gloss=0.95,
        )
        rows.append(
            run_one_chi(
                "Clearcoat gloss 0.95 coarse grid",
                "principled_bsdf",
                gloss95,
                201,
                32,
                "harness_fail",
                data,
            )
        )
        rows.append(
            run_one_chi(
                "Clearcoat gloss 0.95 refined grid",
                "principled_bsdf",
                gloss95,
                401,
                32,
                "pass",
                data,
            )
        )

    write_csv(data / "chi_squared.csv", rows)
    return rows


def gtr1_d_scalar(cos_theta: float, alpha: float) -> float:
    if cos_theta <= 0.0:
        return 0.0
    a2 = alpha * alpha
    return (a2 - 1.0) / (
        math.pi * math.log(a2) * (1.0 + (a2 - 1.0) * cos_theta * cos_theta)
    )


def adaptive_simpson(
    function,
    left: float,
    right: float,
    tolerance: float = 1e-10,
    max_depth: int = 30,
) -> float:
    def simpson(a, b, fa, fm, fb):
        return (b - a) * (fa + 4.0 * fm + fb) / 6.0

    fa = function(left)
    fb = function(right)
    middle = 0.5 * (left + right)
    fm = function(middle)
    whole = simpson(left, right, fa, fm, fb)

    def recurse(a, b, fa_, fm_, fb_, estimate, tol, depth):
        m = 0.5 * (a + b)
        lm = 0.5 * (a + m)
        rm = 0.5 * (m + b)
        flm = function(lm)
        frm = function(rm)
        left_est = simpson(a, m, fa_, flm, fm_)
        right_est = simpson(m, b, fm_, frm, fb_)
        error = left_est + right_est - estimate
        if depth <= 0 or abs(error) <= 15.0 * tol:
            return left_est + right_est + error / 15.0
        return recurse(a, m, fa_, flm, fm_, left_est, tol / 2, depth - 1) + recurse(
            m, b, fm_, frm, fb_, right_est, tol / 2, depth - 1
        )

    return recurse(left, right, fa, fm, fb, whole, tolerance, max_depth)


def gtr1_theta_cdf(theta: np.ndarray, alpha: float) -> np.ndarray:
    a2 = alpha * alpha
    inside = np.maximum(1.0 - (1.0 - a2) * np.cos(theta) ** 2, a2)
    return 1.0 - np.log(inside) / math.log(a2)


def run_gtr1(data: Path, quick: bool) -> tuple[list[dict], list[dict]]:
    print("\n[3/5] Standalone GTR1 normalisation and sampling", flush=True)
    alphas = (0.1, 0.05, 0.01, 0.001)
    normalization = []
    for alpha in alphas:
        integral = adaptive_simpson(
            lambda y: math.pi * gtr1_d_scalar(math.sqrt(y), alpha),
            0.0,
            1.0,
        )
        normalization.append(
            {
                "alpha": alpha,
                "integral_D_cos": integral,
                "absolute_error": abs(integral - 1.0),
                "passed": abs(integral - 1.0) < 1e-6,
            }
        )
        print(f"  alpha={alpha:<6} integral={integral:.9f}", flush=True)

    bsdf = mi.load_dict({"type": "principled_bsdf"})
    sample_count = 50_000 if quick else 200_000
    seeds = [0] if quick else list(range(8))
    edges = np.linspace(0.0, 0.5 * math.pi, 60)
    sampling_rows = []

    for alpha in (0.1, 0.01, 0.001):
        expected = sample_count * np.diff(gtr1_theta_cdf(edges, alpha))
        valid = expected > 5.0
        for seed in seeds:
            sampler = mi.load_dict({"type": "independent"})
            sampler.seed(seed, sample_count)
            half_vectors = bsdf._sample_gtr1(sampler.next_2d(), mi.Float(alpha))
            theta = np.arccos(
                np.clip(np.array(half_vectors.z, dtype=np.float64), 0.0, 1.0)
            )
            observed = np.histogram(theta, bins=edges)[0]
            z_score = (observed[valid] - expected[valid]) / np.sqrt(expected[valid])
            mean_abs_z = float(np.mean(np.abs(z_score)))
            max_abs_z = float(np.max(np.abs(z_score)))
            sampling_rows.append(
                {
                    "configuration": "correct_sampler",
                    "alpha": alpha,
                    "seed": seed,
                    "sample_count": sample_count,
                    "mean_abs_z": mean_abs_z,
                    "max_abs_z": max_abs_z,
                    "passed": mean_abs_z < 1.5 and max_abs_z < 5.0,
                }
            )

    # Sensitivity control: sample with alpha displaced by 5%, but compare
    # against the undisplaced analytic distribution.
    alpha = 0.01
    sampler = mi.load_dict({"type": "independent"})
    sampler.seed(0, sample_count)
    half_vectors = bsdf._sample_gtr1(
        sampler.next_2d(), mi.Float(alpha * 1.05)
    )
    theta = np.arccos(
        np.clip(np.array(half_vectors.z, dtype=np.float64), 0.0, 1.0)
    )
    expected = sample_count * np.diff(gtr1_theta_cdf(edges, alpha))
    valid = expected > 5.0
    observed = np.histogram(theta, bins=edges)[0]
    z_score = (observed[valid] - expected[valid]) / np.sqrt(expected[valid])
    control_mean_abs_z = float(np.mean(np.abs(z_score)))
    control_max_abs_z = float(np.max(np.abs(z_score)))
    sampling_rows.append(
        {
            "configuration": "mis_scaled_5_percent_control",
            "alpha": alpha,
            "seed": 0,
            "sample_count": sample_count,
            "mean_abs_z": control_mean_abs_z,
            "max_abs_z": control_max_abs_z,
            "passed": control_mean_abs_z < 1.5 and control_max_abs_z < 5.0,
        }
    )

    summary = []
    for alpha in (0.1, 0.01, 0.001):
        rows = [
            row
            for row in sampling_rows
            if row["configuration"] == "correct_sampler" and row["alpha"] == alpha
        ]
        summary.append(
            {
                "alpha": alpha,
                "seed_count": len(rows),
                "mean_abs_z": float(np.mean([row["mean_abs_z"] for row in rows])),
                "max_abs_z": float(np.max([row["max_abs_z"] for row in rows])),
                "all_passed": all(row["passed"] for row in rows),
            }
        )

    write_csv(data / "gtr1_normalization.csv", normalization)
    write_csv(data / "gtr1_sampling_per_seed.csv", sampling_rows)
    write_csv(data / "gtr1_sampling_summary.csv", summary)
    return normalization, summary


def make_surface_interaction(
    theta_degrees: float, count: int, from_inside: bool = False
) -> mi.SurfaceInteraction3f:
    theta = math.radians(theta_degrees)
    z = -math.cos(theta) if from_inside else math.cos(theta)
    si = dr.zeros(mi.SurfaceInteraction3f)
    si.wi = mi.Vector3f(
        dr.full(mi.Float, math.sin(theta), count),
        dr.zeros(mi.Float, count),
        dr.full(mi.Float, z, count),
    )
    si.n = mi.Vector3f(0.0, 0.0, 1.0)
    si.sh_frame = mi.Frame3f(si.n)
    si.wavelengths = mi.Color0f()
    return si


def glass_sample_stats(
    bsdf: mi.BSDF,
    theta: float,
    count: int,
    seed: int,
    from_inside: bool = False,
) -> dict:
    context = mi.BSDFContext()
    si = make_surface_interaction(theta, count, from_inside)
    sampler = mi.load_dict({"type": "independent"})
    sampler.seed(seed, count)
    sample, weight = bsdf.sample(
        context, si, sampler.next_1d(), sampler.next_2d()
    )
    cos_o = np.array(mi.Frame3f.cos_theta(sample.wo))
    weights = np.array(weight.x)
    cos_i = -math.cos(math.radians(theta)) if from_inside else math.cos(
        math.radians(theta)
    )
    reflected = cos_o > 0 if cos_i > 0 else cos_o < 0
    return {
        "reflection_fraction": float(reflected.mean()),
        "reflection_weight": float(weights[reflected].mean())
        if reflected.any()
        else float("nan"),
        "transmission_weight": float(weights[~reflected].mean())
        if (~reflected).any()
        else float("nan"),
    }


def theoretical_dielectric_fresnel(
    theta_degrees: float, ior: float, from_inside: bool
) -> float:
    eta_i, eta_t = (ior, 1.0) if from_inside else (1.0, ior)
    cos_i = math.cos(math.radians(theta_degrees))
    sin_t_squared = (eta_i / eta_t) ** 2 * (1.0 - cos_i * cos_i)
    if sin_t_squared >= 1.0:
        return 1.0
    cos_t = math.sqrt(max(1.0 - sin_t_squared, 0.0))
    r_s = (eta_i * cos_i - eta_t * cos_t) / (
        eta_i * cos_i + eta_t * cos_t
    )
    r_p = (eta_t * cos_i - eta_i * cos_t) / (
        eta_t * cos_i + eta_i * cos_t
    )
    return 0.5 * (r_s * r_s + r_p * r_p)


def glass_scene(sphere_bsdf: dict, spp: int, width: int, height: int) -> mi.Scene:
    scene = {
        "type": "scene",
        "integrator": {"type": "path_tracer", "max_depth": 16, "rr_depth": 3},
        "sensor": {
            "type": "perspective",
            "fov": 40,
            "to_world": mi.ScalarTransform4f().look_at(
                origin=[0, 1.2, 5.5], target=[0, 0, 0], up=[0, 1, 0]
            ),
            "film": {
                "type": "hdrfilm",
                "width": width,
                "height": height,
                "pixel_format": "rgb",
                "component_format": "float32",
                "rfilter": {"type": "box"},
            },
            "sampler": {"type": "independent", "sample_count": spp},
        },
        "light": {
            "type": "constant",
            "radiance": {"type": "rgb", "value": [1.0, 1.0, 1.0]},
        },
        "sphere": {"type": "sphere", "radius": 1.0, "bsdf": sphere_bsdf},
        "floor": {
            "type": "rectangle",
            "to_world": mi.ScalarTransform4f()
            .translate([0, -1.0, 0])
            .rotate([1, 0, 0], -90)
            .scale(10),
            "bsdf": {
                "type": "diffuse",
                "reflectance": {
                    "type": "checkerboard",
                    "color0": {"type": "rgb", "value": [0.05] * 3},
                    "color1": {"type": "rgb", "value": [0.9] * 3},
                    "to_uv": mi.ScalarTransform4f().scale([12, 12, 1]),
                },
            },
        },
    }
    return mi.load_dict(scene)


def image_metrics(custom: np.ndarray, reference: np.ndarray) -> dict:
    difference = custom - reference
    return {
        "signed_mean_difference": float(difference.mean()),
        "mae": float(np.abs(difference).mean()),
        "rmse": float(np.sqrt(np.mean(difference * difference))),
        "max_absolute_difference": float(np.abs(difference).max()),
    }


def run_glass(
    data: Path,
    renders: Path,
    figures: Path,
    quick: bool,
) -> dict:
    print("\n[4/5] Smooth dielectric reference comparison", flush=True)
    ior = 1.5
    sample_count = 20_000 if quick else 200_000
    analytic_seeds = [0] if quick else [0, 1, 2, 3]
    mine_dict = {
        "type": "principled_bsdf",
        "base_colour": [1.0, 1.0, 1.0],
        "roughness": 0.0,
        "metallic": 0.0,
        "transmission": 1.0,
        "ior": ior,
    }
    reference_dict = {"type": "dielectric", "int_ior": ior, "ext_ior": 1.0}
    mine = mi.load_dict(mine_dict)
    reference = mi.load_dict(reference_dict)

    fresnel_rows = []
    critical = math.degrees(math.asin(1.0 / ior))
    configurations = [
        (False, angle) for angle in (10.0, 45.0, 70.0, 85.0)
    ] + [(True, angle) for angle in (20.0, 39.8, 40.0, critical + 2.0, 60.0)]

    for from_inside, angle in configurations:
        for seed in analytic_seeds:
            for label, bsdf in (("custom", mine), ("dielectric", reference)):
                stats = glass_sample_stats(
                    bsdf, angle, sample_count, seed, from_inside
                )
                fresnel_rows.append(
                    {
                        "direction": "inside_to_outside"
                        if from_inside
                        else "outside_to_inside",
                        "angle_degrees": angle,
                        "critical_angle_degrees": critical,
                        "implementation": label,
                        "seed": seed,
                        "sample_count": sample_count,
                        **stats,
                    }
                )
    write_csv(data / "glass_fresnel_per_seed.csv", fresnel_rows)
    fresnel_summary = []
    for from_inside, angle in configurations:
        direction = "inside_to_outside" if from_inside else "outside_to_inside"
        for label in ("custom", "dielectric"):
            rows = [
                row
                for row in fresnel_rows
                if row["direction"] == direction
                and row["angle_degrees"] == angle
                and row["implementation"] == label
            ]
            fractions = np.array(
                [row["reflection_fraction"] for row in rows], dtype=np.float64
            )
            fresnel_summary.append(
                {
                    "direction": direction,
                    "angle_degrees": angle,
                    "critical_angle_degrees": critical,
                    "implementation": label,
                    "seed_count": len(rows),
                    "samples_per_seed": sample_count,
                    "reflection_fraction_mean": float(fractions.mean()),
                    "reflection_fraction_sd": float(fractions.std(ddof=1))
                    if len(rows) > 1
                    else 0.0,
                    "theoretical_fresnel": theoretical_dielectric_fresnel(
                        angle, ior, from_inside
                    ),
                    "reflection_weight_mean": float(
                        np.mean([row["reflection_weight"] for row in rows])
                    ),
                    "transmission_weight_mean": float(
                        np.mean([row["transmission_weight"] for row in rows])
                    ),
                }
            )
    write_csv(data / "glass_fresnel_summary.csv", fresnel_summary)

    context = mi.BSDFContext()
    si = make_surface_interaction(30.0, 1)
    wo = mi.Vector3f(0.2, 0.0, -0.9)
    delta_rows = []
    for label, bsdf in (("custom", mine), ("dielectric", reference)):
        delta_rows.append(
            {
                "implementation": label,
                "eval": float(np.asarray(bsdf.eval(context, si, wo)).reshape(-1)[0]),
                "pdf": float(np.asarray(bsdf.pdf(context, si, wo)).reshape(-1)[0]),
            }
        )
    write_csv(data / "glass_delta_convention.csv", delta_rows)

    spp = 32 if quick else 256
    width, height = ((160, 128) if quick else (500, 400))
    images = {}
    for label, bsdf in (("custom", mine_dict), ("dielectric", reference_dict)):
        print(f"  render {label}", flush=True)
        images[label] = render_rgb(glass_scene(bsdf, spp, width, height), spp, 3)
        write_bitmap(renders / f"glass_{label}.exr", images[label])
        write_bitmap(figures / f"glass_{label}.png", images[label])

    metrics = image_metrics(images["custom"], images["dielectric"])
    difference = np.abs(images["custom"] - images["dielectric"])
    gap = np.full((height, 4, 3), 0.18, dtype=np.float32)
    comparison = np.concatenate(
        [
            images["dielectric"],
            gap,
            images["custom"],
            gap,
            np.clip(difference * 50.0, 0.0, 1.0),
        ],
        axis=1,
    )
    write_bitmap(figures / "glass_reference_custom_difference.png", comparison)
    write_csv(data / "glass_render_metrics.csv", [metrics])
    return metrics


def run_glass_furnace(
    data: Path,
    seeds: list[int],
    spp: int,
    resolution: int,
) -> list[dict]:
    print("\n[5/5] Smooth dielectric white-furnace control", flush=True)
    configs = {
        "custom": {
            "type": "principled_bsdf",
            "base_colour": [1.0, 1.0, 1.0],
            "roughness": 0.0,
            "metallic": 0.0,
            "transmission": 1.0,
            "ior": 1.5,
        },
        "dielectric": {"type": "dielectric", "int_ior": 1.5, "ext_ior": 1.0},
    }
    rows = []
    for label, bsdf in configs.items():
        scene = furnace_scene(bsdf, spp, resolution)
        mask = primary_hit_mask(scene)
        images = [render_rgb(scene, spp, seed) for seed in seeds]
        rows.append(
            {
                "implementation": label,
                "spp": spp,
                "seed_count": len(seeds),
                **aggregate_masked(images, mask),
            }
        )
    write_csv(data / "glass_furnace_summary.csv", rows)
    return rows


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    data = output / "data"
    renders = output / "renders"
    figures = output / "figures"
    for directory in (data, renders, figures):
        directory.mkdir(parents=True, exist_ok=True)

    seeds = [0] if args.quick else list(range(args.seeds))
    furnace_spp = 32 if args.quick else 256
    furnace_resolution = 64 if args.quick else 128

    furnace_summary = run_opaque_furnace(
        data, renders, figures, seeds, furnace_spp, furnace_resolution
    )
    chi_rows = run_chi_squared(data, args.quick)
    gtr1_normalization, gtr1_sampling = run_gtr1(data, args.quick)
    glass_metrics = run_glass(data, renders, figures, args.quick)
    glass_furnace = run_glass_furnace(
        data, seeds, furnace_spp, furnace_resolution
    )

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
            "furnace_spp": furnace_spp,
            "furnace_resolution": furnace_resolution,
            "furnace_max_depth": 16,
            "rr_depth": 3,
        },
        "source_hashes": {
            "evaluation_script": file_sha256(Path(__file__)),
            "principled_bsdf": file_sha256(ROOT / "bsdfs" / "principled.py"),
            "path_tracer": file_sha256(ROOT / "integrators" / "path_tracer.py"),
            "white_furnace_scene": file_sha256(
                ROOT / "assets" / "scenes" / "white_furnace.py"
            ),
        },
        "result_counts": {
            "furnace_configurations": len(furnace_summary),
            "chi_squared_configurations": len(chi_rows),
            "gtr1_normalization_configurations": len(gtr1_normalization),
            "gtr1_sampling_configurations": len(gtr1_sampling),
            "glass_furnace_configurations": len(glass_furnace),
        },
        "glass_render_comparison": glass_metrics,
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(f"\nCompleted: {output}", flush=True)


if __name__ == "__main__":
    main()
