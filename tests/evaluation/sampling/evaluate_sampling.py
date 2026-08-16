#!/usr/bin/env -S uv run --script
"""Canonical evaluation for thesis Section 5.3: sampling and noise."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
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
from assets.scenes.cornell_box import cornell_box_scene  # noqa: E402
from assets.scenes.environment_lighting import environment_lighting_scene  # noqa: E402
from denoisers.oidn import denoise_composite  # noqa: E402


DEFAULT_OUTPUT = ROOT / "outputs" / "evaluation" / "5_3_sampling"
HDRIS = {
    "studio": ROOT / "assets/hdri/studio_kontrast_04_1k.exr",
    "venice": ROOT / "assets/hdri/venice_sunset_1k.exr",
    "sundowner": ROOT / "assets/hdri/sundowner_overlook_1k.exr",
    "rogland": ROOT / "assets/hdri/rogland_clear_night_1k.exr",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
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


def erode_mask(mask: np.ndarray, iterations: int = 3) -> np.ndarray:
    result = np.asarray(mask, dtype=bool).copy()
    for _ in range(iterations):
        padded = np.pad(result, 1, mode="constant", constant_values=False)
        result = np.logical_and.reduce(
            [
                padded[dy : dy + result.shape[0], dx : dx + result.shape[1]]
                for dy in range(3)
                for dx in range(3)
            ]
        )
    return result


def environment_scene(
    hdri: Path,
    spp: int,
    resolution: int,
    *,
    importance: bool = True,
    compensation: bool = False,
    cdf_x: int = 512,
    cdf_y: int = 256,
    pooling: str = "max",
    sampler: str = "independent",
    firefly_clamp: float = 0.0,
) -> mi.Scene:
    scene = environment_lighting_scene(str(hdri))
    scene["integrator"]["firefly_clamp"] = firefly_clamp
    scene["sensor"]["film"] = {
        "type": "hdrfilm",
        "width": resolution,
        "height": resolution,
        "pixel_format": "rgb",
        "component_format": "float32",
        "rfilter": {"type": "box"},
    }
    scene["sensor"]["sampler"] = {
        "type": sampler,
        "sample_count": spp,
    }
    scene["emitter"] = {
        "type": "custom_envmap",
        "filename": str(hdri),
        "importance": importance,
        "mis_compensation": compensation,
        "cdf_res_x": cdf_x,
        "cdf_res_y": cdf_y,
        "cdf_pooling": pooling,
    }
    return mi.load_dict(scene)


def render_rgb(scene: mi.Scene, spp: int, seed: int) -> np.ndarray:
    return np.asarray(mi.render(scene, spp=spp, seed=seed), dtype=np.float32)[..., :3]


def primary_shape_masks(scene: mi.Scene) -> dict[str, np.ndarray]:
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
    si = scene.ray_intersect(ray)
    masks = {}
    for shape in scene.shapes():
        masks[shape.id()] = erode_mask(
            np.asarray(si.shape == mi.ShapePtr(shape), dtype=bool).reshape(
                height, width
            )
        )
    masks["background"] = erode_mask(
        ~np.asarray(si.is_valid(), dtype=bool).reshape(height, width)
    )
    masks["full_image"] = np.ones((height, width), dtype=bool)
    return masks


def mean_pixel_std(stack: np.ndarray, mask: np.ndarray | None = None) -> float:
    noise = stack.std(axis=0, ddof=1).mean(axis=-1)
    return float(noise[mask].mean() if mask is not None else noise.mean())


def jackknife_noise_interval(
    stack: np.ndarray, mask: np.ndarray | None
) -> tuple[float, float]:
    if stack.shape[0] < 3:
        value = mean_pixel_std(stack, mask)
        return value, value
    estimates = np.asarray(
        [
            mean_pixel_std(np.delete(stack, index, axis=0), mask)
            for index in range(stack.shape[0])
        ],
        dtype=np.float64,
    )
    centre = mean_pixel_std(stack, mask)
    jackknife_mean = estimates.mean()
    standard_error = np.sqrt(
        (stack.shape[0] - 1)
        / stack.shape[0]
        * np.sum((estimates - jackknife_mean) ** 2)
    )
    return max(0.0, centre - 1.96 * standard_error), centre + 1.96 * standard_error


class EnvironmentRenderCache:
    def __init__(self, spp: int, resolution: int, seeds: list[int]):
        self.spp = spp
        self.resolution = resolution
        self.seeds = seeds
        self._cache: dict[tuple, np.ndarray] = {}
        self._scenes: dict[tuple, mi.Scene] = {}

    def get(
        self,
        hdri_name: str,
        *,
        importance: bool = True,
        compensation: bool = False,
        cdf_x: int = 512,
        cdf_y: int = 256,
        pooling: str = "max",
        sampler: str = "independent",
    ) -> np.ndarray:
        key = (
            hdri_name,
            importance,
            compensation,
            cdf_x,
            cdf_y,
            pooling,
            sampler,
        )
        if key not in self._cache:
            print(
                "  render "
                f"{hdri_name}: importance={importance}, comp={compensation}, "
                f"cdf={cdf_x}x{cdf_y}/{pooling}, sampler={sampler}",
                flush=True,
            )
            scene = environment_scene(
                HDRIS[hdri_name],
                self.spp,
                self.resolution,
                importance=importance,
                compensation=compensation,
                cdf_x=cdf_x,
                cdf_y=cdf_y,
                pooling=pooling,
                sampler=sampler,
            )
            images = [
                render_rgb(scene, self.spp, seed) for seed in self.seeds
            ]
            self._cache[key] = np.stack(images)
            self._scenes[key] = scene
        return self._cache[key]

    def scene(self, hdri_name: str, **kwargs) -> mi.Scene:
        self.get(hdri_name, **kwargs)
        key = (
            hdri_name,
            kwargs.get("importance", True),
            kwargs.get("compensation", False),
            kwargs.get("cdf_x", 512),
            kwargs.get("cdf_y", 256),
            kwargs.get("pooling", "max"),
            kwargs.get("sampler", "independent"),
        )
        return self._scenes[key]

    def clear(self) -> None:
        self._cache.clear()
        self._scenes.clear()


def false_colour(values: np.ndarray, maximum: float) -> np.ndarray:
    t = np.clip(values / max(maximum, 1e-8), 0.0, 1.0)
    stops = np.asarray(
        [
            [0.02, 0.02, 0.08],
            [0.10, 0.15, 0.45],
            [0.65, 0.10, 0.55],
            [0.98, 0.45, 0.10],
            [1.00, 0.95, 0.50],
        ],
        dtype=np.float32,
    )
    scaled = t * (len(stops) - 1)
    lower = np.floor(scaled).astype(np.int32)
    upper = np.minimum(lower + 1, len(stops) - 1)
    fraction = (scaled - lower)[..., None]
    return stops[lower] * (1.0 - fraction) + stops[upper] * fraction


def comparison_grid(
    left: np.ndarray,
    right: np.ndarray,
    left_noise: np.ndarray,
    right_noise: np.ndarray,
) -> np.ndarray:
    maximum = float(np.percentile(np.concatenate([left_noise.ravel(), right_noise.ravel()]), 99.5))
    gap_v = np.full((left.shape[0], 5, 3), 0.18, dtype=np.float32)
    gap_h = np.full((5, left.shape[1] * 2 + 5, 3), 0.18, dtype=np.float32)
    top = np.concatenate([left, gap_v, right], axis=1)
    bottom = np.concatenate(
        [false_colour(left_noise, maximum), gap_v, false_colour(right_noise, maximum)],
        axis=1,
    )
    return np.concatenate([top, gap_h, bottom], axis=0)


def hdri_concentration() -> list[dict]:
    rows = []
    for name, path in HDRIS.items():
        image = np.asarray(mi.Bitmap(str(path)), dtype=np.float64)[..., :3]
        luminance = (
            0.2126 * image[..., 0]
            + 0.7152 * image[..., 1]
            + 0.0722 * image[..., 2]
        )
        flat = np.sort(luminance.ravel())
        top_count = max(1, int(np.ceil(flat.size * 0.01)))
        rows.append(
            {
                "hdri": name,
                "top_1_percent_energy_share": float(flat[-top_count:].sum() / flat.sum()),
                "max_to_mean_luminance": float(luminance.max() / luminance.mean()),
            }
        )
    return rows


def run_environment_sampling(
    data: Path,
    renders: Path,
    figures: Path,
    cache: EnvironmentRenderCache,
) -> tuple[list[dict], list[dict]]:
    print("\n[1/5] Uniform versus importance-sampled environment lighting", flush=True)
    rows = []
    unbiasedness = []
    for name in ("venice", "sundowner"):
        uniform = cache.get(name, importance=False)
        importance = cache.get(name, importance=True)
        masks = primary_shape_masks(cache.scene(name, importance=True))
        for region in ("sphere", "floor", "background", "full_image"):
            mask = masks[region]
            uniform_noise = mean_pixel_std(uniform, mask)
            importance_noise = mean_pixel_std(importance, mask)
            for mode, stack, noise in (
                ("uniform", uniform, uniform_noise),
                ("importance", importance, importance_noise),
            ):
                low, high = jackknife_noise_interval(stack, mask)
                rows.append(
                    {
                        "hdri": name,
                        "region": region,
                        "sampling": mode,
                        "mean_per_pixel_sd": noise,
                        "jackknife_95_low": low,
                        "jackknife_95_high": high,
                        "reduction_vs_uniform_percent": 0.0
                        if mode == "uniform"
                        else 100.0 * (1.0 - importance_noise / uniform_noise)
                        if uniform_noise > 0
                        else 0.0,
                    }
                )

        mean_uniform = uniform.mean(axis=0)
        mean_importance = importance.mean(axis=0)
        difference = mean_importance - mean_uniform
        per_seed_difference = (
            importance.mean(axis=(1, 2, 3)) - uniform.mean(axis=(1, 2, 3))
        )
        difference_mean = float(per_seed_difference.mean())
        difference_sd = float(per_seed_difference.std(ddof=1))
        difference_half_interval = 1.96 * difference_sd / np.sqrt(
            len(per_seed_difference)
        )
        unbiasedness.append(
            {
                "hdri": name,
                "uniform_mean": float(mean_uniform.mean()),
                "importance_mean": float(mean_importance.mean()),
                "signed_mean_difference": difference_mean,
                "between_seed_sd_of_difference": difference_sd,
                "difference_95_low": difference_mean - difference_half_interval,
                "difference_95_high": difference_mean + difference_half_interval,
                "relative_signed_difference_percent": float(
                    100.0 * difference.mean() / mean_uniform.mean()
                ),
                "mean_absolute_difference": float(np.abs(difference).mean()),
            }
        )
        write_bitmap(renders / f"{name}_uniform_seed0.exr", uniform[0])
        write_bitmap(renders / f"{name}_importance_seed0.exr", importance[0])
        write_bitmap(renders / f"{name}_uniform_seed_mean.exr", mean_uniform)
        write_bitmap(renders / f"{name}_importance_seed_mean.exr", mean_importance)
        uniform_noise_map = uniform.std(axis=0, ddof=1).mean(axis=-1)
        importance_noise_map = importance.std(axis=0, ddof=1).mean(axis=-1)
        write_bitmap(
            figures / f"environment_importance_{name}.png",
            comparison_grid(
                uniform[0], importance[0], uniform_noise_map, importance_noise_map
            ),
        )
        gap = np.full((uniform.shape[1], 5, 3), 0.18, dtype=np.float32)
        write_bitmap(
            figures / f"environment_importance_{name}_convergence.png",
            np.concatenate(
                [uniform[0], gap, importance[0], gap, mean_importance], axis=1
            ),
        )
        write_bitmap(
            figures / f"environment_importance_{name}_convergence_exposed_down.png",
            np.concatenate(
                [
                    np.clip(uniform[0] / 8.0, 0.0, 1.0),
                    gap,
                    np.clip(importance[0] / 8.0, 0.0, 1.0),
                    gap,
                    np.clip(mean_importance / 8.0, 0.0, 1.0),
                ],
                axis=1,
            ),
        )
    write_csv(data / "environment_importance_noise.csv", rows)
    write_csv(data / "environment_importance_unbiasedness.csv", unbiasedness)
    return rows, unbiasedness


def run_sampler_and_cdf(
    data: Path, cache: EnvironmentRenderCache
) -> tuple[list[dict], list[dict]]:
    print("\n[2/5] Sampler and CDF construction", flush=True)
    sampler_rows = []
    for sampler in ("independent", "stratified"):
        stack = cache.get("sundowner", sampler=sampler)
        low, high = jackknife_noise_interval(stack, None)
        sampler_rows.append(
            {
                "sampler": sampler,
                "mean_per_pixel_sd": mean_pixel_std(stack),
                "jackknife_95_low": low,
                "jackknife_95_high": high,
            }
        )
    baseline = sampler_rows[0]["mean_per_pixel_sd"]
    for row in sampler_rows:
        row["reduction_vs_independent_percent"] = 100.0 * (
            1.0 - row["mean_per_pixel_sd"] / baseline
        )

    configurations = [
        ("256x128 mean", 256, 128, "mean"),
        ("256x128 max", 256, 128, "max"),
        ("512x256 mean", 512, 256, "mean"),
        ("512x256 max", 512, 256, "max"),
    ]
    cdf_rows = []
    for label, cdf_x, cdf_y, pooling in configurations:
        stack = cache.get(
            "sundowner", cdf_x=cdf_x, cdf_y=cdf_y, pooling=pooling
        )
        low, high = jackknife_noise_interval(stack, None)
        cdf_rows.append(
            {
                "configuration": label,
                "cdf_res_x": cdf_x,
                "cdf_res_y": cdf_y,
                "pooling": pooling,
                "mean_per_pixel_sd": mean_pixel_std(stack),
                "jackknife_95_low": low,
                "jackknife_95_high": high,
            }
        )
    baseline = cdf_rows[0]["mean_per_pixel_sd"]
    for row in cdf_rows:
        row["reduction_vs_256x128_mean_percent"] = 100.0 * (
            1.0 - row["mean_per_pixel_sd"] / baseline
        )
    write_csv(data / "sampler_comparison.csv", sampler_rows)
    write_csv(data / "cdf_comparison.csv", cdf_rows)
    return sampler_rows, cdf_rows


def run_mis_compensation(
    data: Path,
    renders: Path,
    figures: Path,
    cache: EnvironmentRenderCache,
) -> list[dict]:
    print("\n[3/5] Mean-subtraction MIS compensation", flush=True)
    rows = []
    for name in HDRIS:
        off = cache.get(name, compensation=False)
        on = cache.get(name, compensation=True)
        off_noise = mean_pixel_std(off)
        on_noise = mean_pixel_std(on)
        for enabled, stack, noise in (
            (False, off, off_noise),
            (True, on, on_noise),
        ):
            low, high = jackknife_noise_interval(stack, None)
            rows.append(
                {
                    "hdri": name,
                    "mis_compensation": enabled,
                    "mean_per_pixel_sd": noise,
                    "jackknife_95_low": low,
                    "jackknife_95_high": high,
                    "change_vs_off_percent": 0.0
                    if not enabled
                    else 100.0 * (on_noise / off_noise - 1.0),
                }
            )
        write_bitmap(renders / f"mis_compensation_{name}_off_seed0.exr", off[0])
        write_bitmap(renders / f"mis_compensation_{name}_on_seed0.exr", on[0])
        off_noise_map = off.std(axis=0, ddof=1).mean(axis=-1)
        on_noise_map = on.std(axis=0, ddof=1).mean(axis=-1)
        write_bitmap(
            figures / f"mis_compensation_{name}.png",
            comparison_grid(off[0], on[0], off_noise_map, on_noise_map),
        )
    write_csv(data / "mis_compensation.csv", rows)
    return rows


def svg_panel_chart(
    path: Path,
    importance_rows: list[dict],
    sampler_rows: list[dict],
    cdf_rows: list[dict],
    compensation_rows: list[dict],
) -> None:
    width, height = 1600, 1040
    panels = [
        (40, 70, 740, 410),
        (820, 70, 740, 410),
        (40, 550, 740, 410),
        (820, 550, 740, 410),
    ]
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#1c2530}.title{font-size:24px;font-weight:700}.label{font-size:17px}.small{font-size:14px}.axis{stroke:#65717e;stroke-width:1}.grid{stroke:#dce2e8;stroke-width:1}</style>',
    ]

    def bars(panel, title, labels, values, unit, colour="#3c78a8"):
        x, y, w, h = panel
        plot_x, plot_y = x + 205, y + 55
        plot_w, plot_h = w - 240, h - 100
        maximum = max(max(values) * 1.15, 1e-8)
        elements.append(f'<text x="{x}" y="{y + 25}" class="title">{html.escape(title)}</text>')
        for tick in range(5):
            tx = plot_x + plot_w * tick / 4
            value = maximum * tick / 4
            elements.append(f'<line x1="{tx}" y1="{plot_y}" x2="{tx}" y2="{plot_y + plot_h}" class="grid"/>')
            elements.append(f'<text x="{tx}" y="{plot_y + plot_h + 25}" text-anchor="middle" class="small">{value:.2f}</text>')
        bar_h = min(42, plot_h / max(len(values), 1) * 0.65)
        spacing = plot_h / max(len(values), 1)
        for index, (label, value) in enumerate(zip(labels, values)):
            cy = plot_y + spacing * (index + 0.5)
            bw = plot_w * value / maximum
            elements.append(f'<text x="{plot_x - 12}" y="{cy + 6}" text-anchor="end" class="label">{html.escape(label)}</text>')
            elements.append(f'<rect x="{plot_x}" y="{cy - bar_h / 2}" width="{bw}" height="{bar_h}" rx="3" fill="{colour}"/>')
            elements.append(f'<text x="{plot_x + bw + 8}" y="{cy + 6}" class="small">{value:.3f}</text>')
        elements.append(f'<text x="{plot_x + plot_w / 2}" y="{plot_y + plot_h + 50}" text-anchor="middle" class="small">{html.escape(unit)}</text>')

    regional = [
        row
        for row in importance_rows
        if row["sampling"] == "importance" and row["region"] in ("sphere", "floor")
    ]
    bars(
        panels[0],
        "A. Importance-sampling reduction",
        [f'{row["hdri"]} {row["region"]}' for row in regional],
        [row["reduction_vs_uniform_percent"] for row in regional],
        "variance proxy reduction (%)",
        "#2c8c74",
    )
    bars(
        panels[1],
        "B. Sampler choice",
        [row["sampler"] for row in sampler_rows],
        [row["mean_per_pixel_sd"] for row in sampler_rows],
        "mean per-pixel standard deviation",
        "#5470b3",
    )
    bars(
        panels[2],
        "C. Environment CDF construction",
        [row["configuration"] for row in cdf_rows],
        [row["mean_per_pixel_sd"] for row in cdf_rows],
        "mean per-pixel standard deviation",
        "#9b6eb8",
    )
    enabled = [row for row in compensation_rows if row["mis_compensation"]]
    bars(
        panels[3],
        "D. Mean-subtraction compensation",
        [row["hdri"] for row in enabled],
        [max(0.0, -row["change_vs_off_percent"]) for row in enabled],
        "noise reduction relative to disabled (%)",
        "#c4793f",
    )
    elements.append("</svg>")
    path.write_text("\n".join(elements), encoding="utf-8")


def run_firefly(
    data: Path,
    renders: Path,
    figures: Path,
    resolution: int,
    spp: int,
    seeds: list[int],
) -> list[dict]:
    print("\n[4/5] Firefly clamping", flush=True)
    images: dict[float, list[np.ndarray]] = {}
    per_seed = []
    mask_scene = environment_scene(
        HDRIS["sundowner"],
        spp,
        resolution,
        importance=True,
        compensation=True,
        sampler="independent",
        firefly_clamp=0.0,
    )
    masks = primary_shape_masks(mask_scene)
    geometry_mask = masks["sphere"] | masks["floor"]
    background_mask = masks["background"]
    for clamp in (0.0, 3.0, 50.0):
        scene = environment_scene(
            HDRIS["sundowner"],
            spp,
            resolution,
            importance=True,
            compensation=True,
            sampler="independent",
            firefly_clamp=clamp,
        )
        images[clamp] = []
        for seed in seeds:
            print(f"  clamp={clamp:<4} seed={seed}", flush=True)
            image = render_rgb(scene, spp, seed)
            images[clamp].append(image)
            per_seed.append(
                {
                    "clamp": clamp,
                    "spp": spp,
                    "seed": seed,
                    "mean": float(image.mean()),
                    "maximum": float(image.max()),
                    "p99_99": float(np.percentile(image, 99.99)),
                    "geometry_mean": float(image[geometry_mask].mean()),
                    "geometry_maximum": float(image[geometry_mask].max()),
                    "background_mean": float(image[background_mask].mean()),
                    "background_maximum": float(image[background_mask].max()),
                }
            )
    summary = []
    control_mean = np.mean([row["mean"] for row in per_seed if row["clamp"] == 0.0])
    for clamp in (0.0, 3.0, 50.0):
        selected = [row for row in per_seed if row["clamp"] == clamp]
        means = np.asarray([row["mean"] for row in selected])
        maxima = np.asarray([row["maximum"] for row in selected])
        percentiles = np.asarray([row["p99_99"] for row in selected])
        geometry_means = np.asarray([row["geometry_mean"] for row in selected])
        geometry_maxima = np.asarray([row["geometry_maximum"] for row in selected])
        background_means = np.asarray([row["background_mean"] for row in selected])
        background_maxima = np.asarray([row["background_maximum"] for row in selected])
        control_geometry_mean = np.mean(
            [row["geometry_mean"] for row in per_seed if row["clamp"] == 0.0]
        )
        control_background_mean = np.mean(
            [row["background_mean"] for row in per_seed if row["clamp"] == 0.0]
        )
        summary.append(
            {
                "clamp": clamp,
                "spp": spp,
                "seed_count": len(seeds),
                "mean": float(means.mean()),
                "between_seed_sd_mean": float(means.std(ddof=1)),
                "mean_shift_vs_unclamped_percent": float(100.0 * (means.mean() / control_mean - 1.0)),
                "mean_of_maximum": float(maxima.mean()),
                "maximum_across_seeds": float(maxima.max()),
                "mean_p99_99": float(percentiles.mean()),
                "geometry_mean": float(geometry_means.mean()),
                "geometry_mean_shift_percent": float(
                    100.0 * (geometry_means.mean() / control_geometry_mean - 1.0)
                ),
                "geometry_maximum_across_seeds": float(geometry_maxima.max()),
                "background_mean": float(background_means.mean()),
                "background_mean_shift_percent": float(
                    100.0 * (background_means.mean() / control_background_mean - 1.0)
                ),
                "background_maximum_across_seeds": float(background_maxima.max()),
            }
        )

    control_maxima = [row for row in per_seed if row["clamp"] == 0.0]
    visual_seed = int(max(control_maxima, key=lambda row: row["maximum"])["seed"])
    seed_index = seeds.index(visual_seed)
    panels = []
    gap = np.full((resolution, 5, 3), 0.18, dtype=np.float32)
    for clamp in (0.0, 3.0, 50.0):
        image = images[clamp][seed_index]
        write_bitmap(renders / f"firefly_clamp_{clamp:g}_seed_{visual_seed}.exr", image)
        panels.append(np.clip(image / 8.0, 0.0, 1.0))
    write_bitmap(
        figures / "firefly_clamp_comparison.png",
        np.concatenate([panels[0], gap, panels[1], gap, panels[2]], axis=1),
    )
    write_csv(data / "firefly_per_seed.csv", per_seed)
    write_csv(data / "firefly_summary.csv", summary)
    return summary


def cornell_scene(
    spp: int, resolution: int, reconstruction_filter: str, with_aovs: bool
) -> mi.Scene:
    scene = cornell_box_scene()
    scene["integrator"] = {
        "type": "path_tracer",
        "max_depth": 8,
        "with_aovs": with_aovs,
    }
    scene["sensor"]["film"] = {
        "type": "hdrfilm",
        "width": resolution,
        "height": resolution,
        "component_format": "float32",
        "rfilter": {"type": reconstruction_filter},
    }
    scene["sensor"]["sampler"] = {
        "type": "independent",
        "sample_count": spp,
    }
    return mi.load_dict(scene)


def render_cornell(
    spp: int,
    seed: int,
    resolution: int,
    reconstruction_filter: str,
    with_aovs: bool,
) -> np.ndarray:
    return np.asarray(
        mi.render(
            cornell_scene(spp, resolution, reconstruction_filter, with_aovs),
            spp=spp,
            seed=seed,
        ),
        dtype=np.float32,
    )


def rmse(a: np.ndarray, b: np.ndarray, mask: np.ndarray | None = None) -> float:
    squared = (a - b) ** 2
    return float(np.sqrt(squared[mask].mean() if mask is not None else squared.mean()))


def lag_one_correlation(residual: np.ndarray) -> tuple[float, float]:
    scalar = residual.mean(axis=-1)

    def corr(a, b):
        a = a.ravel() - a.mean()
        b = b.ravel() - b.mean()
        denominator = np.sqrt(np.dot(a, a) * np.dot(b, b))
        return float(np.dot(a, b) / denominator) if denominator > 0 else 0.0

    return corr(scalar[:, :-1], scalar[:, 1:]), corr(scalar[:-1, :], scalar[1:, :])


def run_oidn(
    data: Path,
    renders: Path,
    figures: Path,
    resolution: int,
    reference_spp: int,
    reference_seeds: list[int],
    test_seeds: list[int],
    sweep_spp: list[int],
) -> tuple[list[dict], list[dict]]:
    print("\n[5/5] OIDN error and reconstruction-filter validation", flush=True)
    references = {}
    for rfilter in ("box", "gaussian"):
        print(f"  {rfilter} high-spp reference", flush=True)
        images = [
            render_cornell(reference_spp, seed, resolution, rfilter, False)[..., :3]
            for seed in reference_seeds
        ]
        references[rfilter] = np.mean(images, axis=0)
        write_bitmap(renders / f"oidn_reference_{rfilter}.exr", references[rfilter])

    reference = references["box"]
    non_emitter = np.repeat((reference.mean(axis=-1) <= 2.0)[..., None], 3, axis=-1)
    rows = []
    visual_noisy = visual_denoised = None
    for spp in sweep_spp:
        noisy_images, denoised_images = [], []
        for seed in test_seeds:
            print(f"  box spp={spp:<3} seed={seed}", flush=True)
            full = render_cornell(spp, seed, resolution, "box", True)
            noisy = np.ascontiguousarray(full[..., :3])
            albedo = np.ascontiguousarray(full[..., 3:6])
            normal = np.ascontiguousarray(full[..., 6:9])
            denoised = denoise_composite(
                noisy, albedo, normal, emitter_threshold=2.0
            )
            noisy_images.append(noisy)
            denoised_images.append(denoised)
            rows.append(
                {
                    "spp": spp,
                    "seed": seed,
                    "noisy_rmse": rmse(noisy, reference),
                    "denoised_rmse": rmse(denoised, reference),
                    "noisy_rmse_excluding_emitter": rmse(noisy, reference, non_emitter),
                    "denoised_rmse_excluding_emitter": rmse(denoised, reference, non_emitter),
                }
            )
        if spp == sweep_spp[0]:
            visual_noisy = noisy_images[0]
            visual_denoised = denoised_images[0]
        write_bitmap(renders / f"oidn_noisy_{spp}spp_mean.exr", np.mean(noisy_images, axis=0))
        write_bitmap(renders / f"oidn_denoised_{spp}spp_mean.exr", np.mean(denoised_images, axis=0))

    summary = []
    for spp in sweep_spp:
        selected = [row for row in rows if row["spp"] == spp]
        summary_row = {"spp": spp, "seed_count": len(selected)}
        for metric in (
            "noisy_rmse",
            "denoised_rmse",
            "noisy_rmse_excluding_emitter",
            "denoised_rmse_excluding_emitter",
        ):
            values = np.asarray([row[metric] for row in selected])
            summary_row[f"{metric}_mean"] = float(values.mean())
            summary_row[f"{metric}_sd"] = float(values.std(ddof=1))
        summary_row["improvement_percent"] = 100.0 * (
            1.0
            - summary_row["denoised_rmse_mean"] / summary_row["noisy_rmse_mean"]
        )
        summary_row["improvement_excluding_emitter_percent"] = 100.0 * (
            1.0
            - summary_row["denoised_rmse_excluding_emitter_mean"]
            / summary_row["noisy_rmse_excluding_emitter_mean"]
        )
        summary.append(summary_row)

    filter_rows = []
    for rfilter in ("box", "gaussian"):
        for seed in test_seeds:
            print(f"  filter diagnostic {rfilter} seed={seed}", flush=True)
            full = render_cornell(sweep_spp[0], seed, resolution, rfilter, True)
            noisy = np.ascontiguousarray(full[..., :3])
            denoised = denoise_composite(
                noisy,
                np.ascontiguousarray(full[..., 3:6]),
                np.ascontiguousarray(full[..., 6:9]),
                emitter_threshold=2.0,
            )
            horizontal, vertical = lag_one_correlation(noisy - references[rfilter])
            noisy_error = rmse(noisy, references[rfilter])
            denoised_error = rmse(denoised, references[rfilter])
            filter_rows.append(
                {
                    "filter": rfilter,
                    "spp": sweep_spp[0],
                    "seed": seed,
                    "horizontal_lag1": horizontal,
                    "vertical_lag1": vertical,
                    "noisy_rmse": noisy_error,
                    "denoised_rmse": denoised_error,
                    "improvement_percent": 100.0 * (1.0 - denoised_error / noisy_error),
                }
            )

    gap = np.full((resolution, 5, 3), 0.18, dtype=np.float32)
    write_bitmap(
        figures / "oidn_low_spp_comparison.png",
        np.concatenate([visual_noisy, gap, visual_denoised, gap, reference], axis=1),
    )
    write_csv(data / "oidn_per_seed.csv", rows)
    write_csv(data / "oidn_summary.csv", summary)
    write_csv(data / "oidn_filter_diagnostic.csv", filter_rows)
    return summary, filter_rows


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    data = output / "data"
    renders = output / "renders"
    figures = output / "figures"
    for directory in (output, data, renders, figures):
        directory.mkdir(parents=True, exist_ok=True)

    if args.quick:
        environment_resolution = 128
        environment_seeds = list(range(8))
        firefly_resolution, firefly_spp, firefly_seeds = 128, 32, list(range(2))
        oidn_resolution = 128
        oidn_reference_spp, oidn_reference_seeds = 128, [0, 1]
        oidn_test_seeds, oidn_sweep = [10, 11], [16, 64]
    else:
        environment_resolution = 256
        environment_seeds = list(range(24))
        firefly_resolution, firefly_spp, firefly_seeds = 256, 256, list(range(4))
        oidn_resolution = 256
        oidn_reference_spp, oidn_reference_seeds = 512, [0, 1, 2, 3]
        oidn_test_seeds, oidn_sweep = [10, 11, 12, 13], [16, 32, 64, 128, 256]

    environment_spp = 16
    concentration = hdri_concentration()
    write_csv(data / "hdri_concentration.csv", concentration)
    cache = EnvironmentRenderCache(
        environment_spp, environment_resolution, environment_seeds
    )
    importance_rows, unbiasedness = run_environment_sampling(
        data, renders, figures, cache
    )
    sampler_rows, cdf_rows = run_sampler_and_cdf(data, cache)
    compensation_rows = run_mis_compensation(data, renders, figures, cache)
    svg_panel_chart(
        figures / "sampling_variance_summary.svg",
        importance_rows,
        sampler_rows,
        cdf_rows,
        compensation_rows,
    )
    cache.clear()

    firefly_rows = run_firefly(
        data,
        renders,
        figures,
        firefly_resolution,
        firefly_spp,
        firefly_seeds,
    )
    oidn_rows, filter_rows = run_oidn(
        data,
        renders,
        figures,
        oidn_resolution,
        oidn_reference_spp,
        oidn_reference_seeds,
        oidn_test_seeds,
        oidn_sweep,
    )

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "mitsuba_version": mi.__version__,
        "variant": mi.variant(),
        "git": git_metadata(),
        "settings": {
            "quick": args.quick,
            "environment": {
                "resolution": environment_resolution,
                "spp": environment_spp,
                "seeds": environment_seeds,
                "reconstruction_filter": "box",
            },
            "firefly": {
                "resolution": firefly_resolution,
                "spp": firefly_spp,
                "seeds": firefly_seeds,
            },
            "oidn": {
                "resolution": oidn_resolution,
                "reference_spp_per_seed": oidn_reference_spp,
                "reference_seeds": oidn_reference_seeds,
                "test_seeds": oidn_test_seeds,
                "spp_sweep": oidn_sweep,
            },
        },
        "source_hashes": {
            "evaluation_script": file_sha256(SCRIPT_PATH),
            "environment_emitter": file_sha256(ROOT / "emitters/envmap.py"),
            "path_tracer": file_sha256(ROOT / "integrators/path_tracer.py"),
            "denoiser": file_sha256(ROOT / "denoisers/oidn.py"),
            "environment_scene": file_sha256(
                ROOT / "assets/scenes/environment_lighting.py"
            ),
            "cornell_scene": file_sha256(ROOT / "assets/scenes/cornell_box.py"),
        },
        "result_counts": {
            "importance_rows": len(importance_rows),
            "unbiasedness_rows": len(unbiasedness),
            "sampler_rows": len(sampler_rows),
            "cdf_rows": len(cdf_rows),
            "compensation_rows": len(compensation_rows),
            "firefly_rows": len(firefly_rows),
            "oidn_rows": len(oidn_rows),
            "oidn_filter_rows": len(filter_rows),
        },
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(f"\nComplete: {output}", flush=True)


if __name__ == "__main__":
    main()
