#!/usr/bin/env python3
"""Controlled thin-sheet versus solid-glass figure for thesis section 5.4."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import mitsuba as mi
import numpy as np


SCRIPT_PATH = Path(__file__).resolve()
TESTS_DIR = SCRIPT_PATH.parents[2]
ROOT = SCRIPT_PATH.parents[3]
sys.path.insert(0, str(TESTS_DIR))

import _common  # noqa: E402,F401 -- variant and custom plugin registration


DEFAULT_OUTPUT = ROOT / "outputs" / "evaluation" / "5_4_features"
HDRI = ROOT / "assets" / "hdri" / "studio_kontrast_04_1k.exr"

CONFIGURATIONS = [
    {
        "id": "open_aperture",
        "title": "Open aperture",
        "caption": "No optical interface",
        "geometry": "none",
        "thin": None,
        "ior": None,
    },
    {
        "id": "thin_sheet",
        "title": "Thin-sheet glazing",
        "caption": "Straight-through transmission + Fresnel reflection",
        "geometry": "single rectangle",
        "thin": True,
        "ior": 1.5,
    },
    {
        "id": "solid_slab",
        "title": "Solid glass slab",
        "caption": "Refraction through modelled thickness",
        "geometry": "closed cube, thickness 0.24 scene units",
        "thin": False,
        "ior": 1.5,
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--spp", type=int)
    parser.add_argument("--seed", type=int, default=23)
    return parser.parse_args()


def rgb(value: list[float]) -> dict:
    return {"type": "rgb", "value": value}


def checker(a: list[float], b: list[float], scale: float) -> dict:
    return {
        "type": "checkerboard",
        "color0": rgb(a),
        "color1": rgb(b),
        "to_uv": mi.ScalarTransform4f().scale([scale, scale, 1]),
    }


def glass_bsdf(*, thin: bool) -> dict:
    return {
        "type": "principled_bsdf",
        "base_colour": [0.92, 0.98, 1.0],
        "transmission": 1.0,
        "ior": 1.5,
        "thin": thin,
    }


def window_transform() -> mi.ScalarTransform4f:
    return mi.ScalarTransform4f().rotate([0, 1, 0], -18)


def add_frame(scene: dict) -> None:
    transform = window_transform()
    wall_material = {
        "type": "diffuse",
        "reflectance": rgb([0.16, 0.17, 0.19]),
    }
    # Four rectangles form a wall with a 3.6 x 2.8 opening. This prevents the
    # oblique camera from seeing the comparison target around a freestanding
    # frame, so every background ray must genuinely pass through the aperture.
    wall_parts = {
        "wall_top": ([0, 3.20, 0.0], [10.0, 1.80, 1]),
        "wall_bottom": ([0, -3.20, 0.0], [10.0, 1.80, 1]),
        "wall_left": ([-6.00, 0, 0.0], [4.20, 1.40, 1]),
        "wall_right": ([6.00, 0, 0.0], [4.20, 1.40, 1]),
    }
    for name, (translation, scale) in wall_parts.items():
        scene[name] = {
            "type": "rectangle",
            "to_world": transform @ mi.ScalarTransform4f().translate(translation).scale(scale),
            "bsdf": wall_material,
        }

    frame_material = {
        "type": "roughplastic",
        "diffuse_reflectance": rgb([0.055, 0.065, 0.075]),
        "alpha": 0.22,
    }
    bars = {
        "frame_top": ([0, 1.55, 0.025], [2.10, 0.15, 1]),
        "frame_bottom": ([0, -1.55, 0.025], [2.10, 0.15, 1]),
        "frame_left": ([-1.95, 0, 0.025], [0.15, 1.55, 1]),
        "frame_right": ([1.95, 0, 0.025], [0.15, 1.55, 1]),
    }
    for name, (translation, scale) in bars.items():
        scene[name] = {
            "type": "rectangle",
            "to_world": transform @ mi.ScalarTransform4f().translate(translation).scale(scale),
            "bsdf": frame_material,
        }


def scene_dict(configuration: dict, width: int, height: int, spp: int) -> dict:
    scene = {
        "type": "scene",
        "integrator": {
            "type": "path_tracer",
            "max_depth": 16,
            "rr_depth": 4,
            "firefly_clamp": 0.0,
        },
        "sensor": {
            "type": "perspective",
            "fov": 44,
            "fov_axis": "x",
            "to_world": mi.ScalarTransform4f().look_at(
                origin=[3.2, 0.7, 6.5], target=[0, 0, -1.35], up=[0, 1, 0]
            ),
            "film": {
                "type": "hdrfilm",
                "width": width,
                "height": height,
                "pixel_format": "rgb",
                "component_format": "float32",
                "rfilter": {"type": "box"},
            },
            "sampler": {"type": "stratified", "sample_count": spp},
        },
        "environment": {
            "type": "envmap",
            "filename": str(HDRI),
            "scale": 0.55,
            "to_world": mi.ScalarTransform4f().rotate([0, 1, 0], 30),
        },
        "key": {
            "type": "rectangle",
            "to_world": mi.ScalarTransform4f().look_at(
                origin=[-2.8, 4.5, 3.2], target=[0, 0, -1.5], up=[0, 1, 0]
            ).scale([1.4, 0.8, 1]),
            "emitter": {"type": "area", "radiance": rgb([12.0, 11.5, 10.8])},
        },
        # The target is deliberately high-frequency: displacement and
        # distortion are much easier to see than against a flat background.
        "target": {
            "type": "rectangle",
            "to_world": window_transform()
            @ mi.ScalarTransform4f().translate([-1.5, 0, -3.1]).scale([4.0, 2.20, 1]),
            "bsdf": {
                "type": "diffuse",
                "reflectance": checker(
                    [0.035, 0.045, 0.065], [0.82, 0.86, 0.92], 18
                ),
            },
        },
        "red_marker": {
            "type": "sphere",
            "to_world": window_transform()
            @ mi.ScalarTransform4f().translate([-1.95, -0.42, -2.65]).scale(0.25),
            "bsdf": {
                "type": "diffuse",
                "reflectance": rgb([0.72, 0.025, 0.02]),
            },
        },
        "green_marker": {
            "type": "sphere",
            "to_world": window_transform()
            @ mi.ScalarTransform4f().translate([-1.20, 0.38, -2.58]).scale(0.22),
            "bsdf": {
                "type": "diffuse",
                "reflectance": rgb([0.025, 0.62, 0.12]),
            },
        },
        "blue_marker": {
            "type": "sphere",
            "to_world": window_transform()
            @ mi.ScalarTransform4f().translate([-0.42, -0.18, -2.55]).scale(0.28),
            "bsdf": {
                "type": "diffuse",
                "reflectance": rgb([0.025, 0.12, 0.75]),
            },
        },
    }
    add_frame(scene)

    if configuration["id"] == "thin_sheet":
        scene["glazing"] = {
            "type": "rectangle",
            "to_world": window_transform() @ mi.ScalarTransform4f().scale([1.80, 1.40, 1]),
            "bsdf": glass_bsdf(thin=True),
        }
    elif configuration["id"] == "solid_slab":
        scene["glazing"] = {
            "type": "cube",
            "to_world": window_transform() @ mi.ScalarTransform4f().scale([1.80, 1.40, 0.12]),
            "bsdf": glass_bsdf(thin=False),
        }
    return scene


def write_bitmap_outputs(exr: Path, png: Path, image: np.ndarray) -> None:
    bitmap = mi.Bitmap(np.ascontiguousarray(image, dtype=np.float32))
    bitmap.write(str(exr))
    bitmap.convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, True).write(str(png))


def write_comparison_svg(path: Path, pngs: list[Path], size: int) -> None:
    header = 70
    footer = 58
    gap = 12
    width = size * 3 + gap * 2
    height = header + size + footer
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#20242a"/>',
    ]
    for index, (configuration, png) in enumerate(zip(CONFIGURATIONS, pngs)):
        x = index * (size + gap)
        encoded = base64.b64encode(png.read_bytes()).decode("ascii")
        parts.extend(
            [
                f'<text x="{x + size / 2:.1f}" y="30" text-anchor="middle" '
                'font-family="Arial, Helvetica, sans-serif" font-size="24" '
                f'font-weight="600" fill="#ffffff">{html.escape(configuration["title"])}</text>',
                f'<image x="{x}" y="{header}" width="{size}" height="{size}" '
                f'href="data:image/png;base64,{encoded}"/>',
                f'<text x="{x + size / 2:.1f}" y="{header + size + 35}" text-anchor="middle" '
                'font-family="Arial, Helvetica, sans-serif" font-size="16" '
                f'fill="#d7dce4">{html.escape(configuration["caption"])}</text>',
            ]
        )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def write_configuration_csv(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CONFIGURATIONS[0]))
        writer.writeheader()
        writer.writerows(CONFIGURATIONS)


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


def main() -> None:
    args = parse_args()
    size = 320 if args.quick else 700
    spp = args.spp if args.spp is not None else (36 if args.quick else 256)
    output = args.output.resolve()
    renders = output / "renders"
    figures = output / "figures"
    data = output / "data"
    for directory in (renders, figures, data):
        directory.mkdir(parents=True, exist_ok=True)

    pngs = []
    for configuration in CONFIGURATIONS:
        print(f'Rendering glazing panel: {configuration["id"]}', flush=True)
        scene = mi.load_dict(scene_dict(configuration, size, size, spp))
        image = np.asarray(
            mi.render(scene, spp=spp, seed=args.seed), dtype=np.float32
        )[..., :3]
        exr = renders / f'glazing_{configuration["id"]}.exr'
        png = figures / f'glazing_{configuration["id"]}.png'
        write_bitmap_outputs(exr, png, image)
        pngs.append(png)

    figure = figures / "glazing_open_thin_solid_comparison.svg"
    write_comparison_svg(figure, pngs, size)
    write_configuration_csv(data / "glazing_configurations.csv")

    metadata = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Section 5.4 open aperture vs thin-sheet vs solid-glass comparison",
        "backend": "llvm_ad_rgb",
        "hardware": "Apple M4 Pro",
        "panel_resolution": [size, size],
        "spp": spp,
        "seed": args.seed,
        "sampler": "stratified",
        "reconstruction_filter": "box",
        "max_depth": 16,
        "rr_depth": 4,
        "firefly_clamp": 0.0,
        "integrator": "custom path_tracer",
        "emitter": "Mitsuba envmap plus one area light",
        "hdri": str(HDRI.relative_to(ROOT)),
        "view": "oblique camera; identical across panels",
        "script_sha256": file_sha256(SCRIPT_PATH),
        **git_metadata(),
    }
    (output / "glazing_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {figure}", flush=True)


if __name__ == "__main__":
    main()
