#!/usr/bin/env python3
"""Canonical isolated-feature evaluation for thesis section 5.4.

The suite covers the material gallery, thin and solid glazing, the physical
camera, isolated BSDF controls, and the transparent-shadow approximation.
Comparisons hold unrelated parameters constant wherever possible.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import json
import math
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
from assets.scenes.material_test import (  # noqa: E402
    MATERIALS,
    material_test_scene,
)
from assets.scenes.glazing import (  # noqa: E402
    GLAZING_CONFIGURATIONS,
    glazing_scene,
)


DEFAULT_OUTPUT = ROOT / "outputs" / "evaluation" / "5_4_features"
HDRI = ROOT / "assets" / "hdri" / "studio_kontrast_04_1k.exr"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--spp", type=int)
    parser.add_argument("--seed", type=int, default=19)
    parser.add_argument(
        "--only",
        choices=["all", "gallery", "glazing", "camera", "materials", "shadows"],
        default="all",
        help="Run one evaluation group or the complete section 5.4 suite.",
    )
    parser.add_argument(
        "--clamp", type=float, default=0.0,
        help="Per-contribution firefly clamp; use 0 for an unbiased render.",
    )
    return parser.parse_args()


def rgb(value: list[float]) -> dict:
    return {"type": "rgb", "value": value}


def checker(a: list[float], b: list[float], scale: float = 5.0) -> dict:
    return {
        "type": "checkerboard",
        "color0": rgb(a),
        "color1": rgb(b),
        "to_uv": mi.ScalarTransform4f().scale([scale, scale, 1]),
    }


def principled(**parameters) -> dict:
    material = {"type": "principled_bsdf"}
    material.update(parameters)
    return material


def write_catalogue(path: Path) -> None:
    rows = []
    for index, item in enumerate(MATERIALS):
        row, column = divmod(index, 6)
        rows.append(
            {
                "id": item["id"],
                "group": item["group"],
                "row": row + 1,
                "column": column + 1,
                "title": item["title"],
                "subtitle": item["subtitle"],
                "geometry": item.get("geometry", "sphere"),
                "bsdf_parameters": json.dumps(item["bsdf"], default=str),
            }
        )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_labelled_svg(path: Path, png_path: Path, width: int, height: int) -> None:
    encoded = base64.b64encode(png_path.read_bytes()).decode("ascii")
    cell_width = width / 6.0
    # Approximate projected row centres for the fixed camera above.
    row_centres = [height * 0.205, height * 0.500, height * 0.795]
    label_offset = height * 0.105
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<image width="{width}" height="{height}" href="data:image/png;base64,{encoded}"/>',
    ]
    for index, item in enumerate(MATERIALS):
        row, column = divmod(index, 6)
        x = (column + 0.5) * cell_width
        y = row_centres[row] + label_offset
        box_width = cell_width * 0.86
        box_height = height * 0.060
        parts.extend(
            [
                f'<rect x="{x - box_width / 2:.1f}" y="{y - box_height * 0.54:.1f}" '
                f'width="{box_width:.1f}" height="{box_height:.1f}" rx="5" '
                'fill="#07090c" fill-opacity="0.74"/>',
                f'<text x="{x:.1f}" y="{y - height * 0.004:.1f}" text-anchor="middle" '
                f'font-family="Arial, Helvetica, sans-serif" font-size="{height * 0.017:.1f}" '
                f'font-weight="600" fill="#ffffff">{html.escape(item["title"])}</text>',
                f'<text x="{x:.1f}" y="{y + height * 0.018:.1f}" text-anchor="middle" '
                f'font-family="Arial, Helvetica, sans-serif" font-size="{height * 0.013:.1f}" '
                f'fill="#cdd2da">{html.escape(item["subtitle"])}</text>',
            ]
        )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


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


def write_bitmap_outputs(exr: Path, png: Path, image: np.ndarray) -> None:
    bitmap = mi.Bitmap(np.ascontiguousarray(image, dtype=np.float32))
    bitmap.write(str(exr))
    bitmap.convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, True).write(str(png))


def write_panel_svg(
    path: Path,
    panels: list[dict],
    panel_width: int,
    panel_height: int,
    columns: int,
) -> None:
    """Creates a labelled, self-contained SVG from already-written PNGs."""
    header, footer, gap = 58, 48, 12
    rows = math.ceil(len(panels) / columns)
    width = columns * panel_width + (columns - 1) * gap
    height = rows * (header + panel_height + footer) + (rows - 1) * gap
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#20242a"/>',
    ]
    for index, panel in enumerate(panels):
        row, column = divmod(index, columns)
        x = column * (panel_width + gap)
        y = row * (header + panel_height + footer + gap)
        encoded = base64.b64encode(Path(panel["png"]).read_bytes()).decode("ascii")
        parts.extend(
            [
                f'<text x="{x + panel_width / 2:.1f}" y="{y + 31}" text-anchor="middle" '
                'font-family="Arial, Helvetica, sans-serif" font-size="22" '
                f'font-weight="600" fill="#ffffff">{html.escape(panel["title"])}</text>',
                f'<image x="{x}" y="{y + header}" width="{panel_width}" height="{panel_height}" '
                f'href="data:image/png;base64,{encoded}"/>',
                f'<text x="{x + panel_width / 2:.1f}" y="{y + header + panel_height + 30}" '
                'text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="15" '
                f'fill="#d7dce4">{html.escape(panel["caption"])}</text>',
            ]
        )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")



def run_glazing(data: Path, renders: Path, figures: Path, quick: bool, seed: int) -> dict:
    size = 320 if quick else 700
    spp = 36 if quick else 1024
    panels = []
    for configuration in GLAZING_CONFIGURATIONS:
        print(f'  glazing: {configuration["id"]}', flush=True)
        scene = mi.load_dict(glazing_scene(configuration, size, spp))
        image = np.asarray(mi.render(scene, spp=spp, seed=seed), dtype=np.float32)[..., :3]
        exr = renders / f'glazing_{configuration["id"]}.exr'
        png = figures / f'glazing_{configuration["id"]}.png'
        write_bitmap_outputs(exr, png, image)
        panels.append({"png": png, "title": configuration["title"], "caption": configuration["caption"]})
    write_panel_svg(
        figures / "glazing_open_thin_solid_comparison.svg", panels, size, size, 3
    )
    with (data / "glazing_configurations.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(GLAZING_CONFIGURATIONS[0]))
        writer.writeheader()
        writer.writerows(GLAZING_CONFIGURATIONS)
    return {"panel_resolution": [size, size], "spp": spp, "seed": seed}


def camera_scene(
    sensor_type: str,
    width: int,
    height: int,
    spp: int,
    *,
    aperture_radius: float = 0.0,
    focus_distance: float = 5.0,
) -> dict:
    sensor = {
        "type": sensor_type,
        "fov": 40,
        "to_world": mi.ScalarTransform4f().look_at(
            origin=[0, 0, 0], target=[0, 0, -1], up=[0, 1, 0]
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
    }
    if sensor_type == "perspective":
        sensor["fov_axis"] = "x"
    if sensor_type == "physical_camera":
        sensor.update(
            {"aperture_radius": aperture_radius, "focus_distance": focus_distance}
        )
    scene = {
        "type": "scene",
        "integrator": {"type": "path_tracer", "max_depth": 4},
        "sensor": sensor,
        "light": {"type": "constant", "radiance": rgb([1.0, 1.0, 1.0])},
    }
    for name, position, colour in [
        ("near", [-0.65, 0, -3], [0.9, 0.05, 0.04]),
        ("focus", [0, 0, -5], [0.05, 0.8, 0.08]),
        ("far", [1.0, 0, -9], [0.04, 0.08, 0.9]),
    ]:
        scene[name] = {
            "type": "sphere",
            "to_world": mi.ScalarTransform4f().translate(position).scale(0.42),
            "bsdf": principled(
                base_colour=colour, roughness=0.5, metallic=0.0, specular=0.0
            ),
        }
    return scene


def bokeh_scene(blades: int, size: int, spp: int) -> dict:
    scene = {
        "type": "scene",
        "integrator": {"type": "path_tracer", "max_depth": 2},
        "sensor": {
            "type": "physical_camera",
            "fov": 50,
            "aperture_radius": 0.35,
            "focus_distance": 6.0,
            "aperture_blades": blades,
            "to_world": mi.ScalarTransform4f().look_at(
                origin=[0, 0, 0], target=[0, 0, -1], up=[0, 1, 0]
            ),
            "film": {
                "type": "hdrfilm",
                "width": size,
                "height": size,
                "pixel_format": "rgb",
                "component_format": "float32",
                "rfilter": {"type": "box"},
            },
            "sampler": {"type": "stratified", "sample_count": spp},
        },
        "background": {"type": "constant", "radiance": rgb([0.01, 0.01, 0.012])},
    }
    for index, (position, colour) in enumerate(
        [
            ([-0.8, 0.3, -2.0], [34, 34, 34]),
            ([0.7, -0.2, -2.2], [34, 26, 18]),
            ([0.0, 0.65, -2.5], [18, 22, 34]),
        ]
    ):
        scene[f"light_{index}"] = {
            "type": "sphere",
            "to_world": mi.ScalarTransform4f().translate(position).scale(0.045),
            "emitter": {"type": "area", "radiance": rgb(colour)},
        }
    return scene


def run_camera(data: Path, renders: Path, figures: Path, quick: bool, seed: int) -> dict:
    width, height = ((240, 180) if quick else (480, 360))
    spp = 64 if quick else 256
    images = {}
    panels = []
    camera_configs = [
        ("perspective", "perspective", 0.0, "Mitsuba perspective", "Reference pinhole"),
        ("physical_pinhole", "physical_camera", 0.0, "Custom aperture 0", "Pinhole-equivalent mode"),
        ("physical_dof", "physical_camera", 0.15, "Custom finite aperture", "Mid sphere focused; near/far blurred"),
    ]
    for key, sensor, aperture, title, caption in camera_configs:
        scene = mi.load_dict(
            camera_scene(
                sensor, width, height, spp,
                aperture_radius=aperture, focus_distance=5.0,
            )
        )
        image = np.asarray(mi.render(scene, spp=spp, seed=seed), dtype=np.float32)[..., :3]
        images[key] = image
        exr, png = renders / f"camera_{key}.exr", figures / f"camera_{key}.png"
        write_bitmap_outputs(exr, png, image)
        panels.append({"png": png, "title": title, "caption": caption})
    write_panel_svg(
        figures / "camera_pinhole_dof_comparison.svg", panels, width, height, 3
    )
    difference = images["physical_pinhole"] - images["perspective"]
    camera_rows = [
        {
            "comparison": "physical_camera aperture=0 vs Mitsuba perspective",
            "resolution": f"{width}x{height}",
            "spp": spp,
            "seed": seed,
            "mae": float(np.abs(difference).mean()),
            "rmse": float(np.sqrt(np.mean(difference * difference))),
            "max_absolute_difference": float(np.abs(difference).max()),
        }
    ]
    with (data / "camera_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(camera_rows[0]))
        writer.writeheader()
        writer.writerows(camera_rows)

    bokeh_size = 280 if quick else 500
    bokeh_spp = 64 if quick else 256
    bokeh_panels = []
    for key, blades, title, caption in [
        ("circular", 0, "Circular aperture", "Circular out-of-focus highlights"),
        ("hexagonal", 6, "Six-blade aperture", "Hexagonal out-of-focus highlights"),
    ]:
        scene = mi.load_dict(bokeh_scene(blades, bokeh_size, bokeh_spp))
        image = np.asarray(mi.render(scene, spp=bokeh_spp, seed=seed), dtype=np.float32)[..., :3]
        exr, png = renders / f"bokeh_{key}.exr", figures / f"bokeh_{key}.png"
        write_bitmap_outputs(exr, png, image)
        bokeh_panels.append({"png": png, "title": title, "caption": caption})
    write_panel_svg(
        figures / "camera_bokeh_comparison.svg",
        bokeh_panels,
        bokeh_size,
        bokeh_size,
        2,
    )
    return {
        "resolution": [width, height],
        "spp": spp,
        "bokeh_resolution": [bokeh_size, bokeh_size],
        "bokeh_spp": bokeh_spp,
        "seed": seed,
        "pinhole_mae": camera_rows[0]["mae"],
        "pinhole_rmse": camera_rows[0]["rmse"],
        "pinhole_max_absolute_difference": camera_rows[0]["max_absolute_difference"],
    }


def anisotropy_scene(anisotropic: float, size: int, spp: int) -> dict:
    return {
        "type": "scene",
        "integrator": {"type": "path_tracer", "max_depth": 4},
        "sensor": {
            "type": "physical_camera",
            "fov": 35,
            "aperture_radius": 0.0,
            "focus_distance": 5.0,
            "to_world": mi.ScalarTransform4f().look_at(
                origin=[0, 2.5, 4], target=[0, 0, 0], up=[0, 1, 0]
            ),
            "film": {
                "type": "hdrfilm",
                "width": size,
                "height": size,
                "pixel_format": "rgb",
                "component_format": "float32",
                "rfilter": {"type": "box"},
            },
            "sampler": {"type": "stratified", "sample_count": spp},
        },
        "light": {
            "type": "point",
            "position": [2, 4, 3],
            "intensity": rgb([40, 40, 40]),
        },
        "fill": {"type": "constant", "radiance": rgb([0.05, 0.05, 0.05])},
        "disc": {
            "type": "disk",
            "to_world": mi.ScalarTransform4f().scale(1.5).rotate([1, 0, 0], -90),
            "bsdf": principled(
                base_colour=[0.9, 0.9, 0.9], roughness=0.25,
                metallic=1.0, anisotropic=anisotropic,
            ),
        },
    }


def make_surface_interaction(theta_i_deg: int) -> mi.SurfaceInteraction3f:
    si = dr.zeros(mi.SurfaceInteraction3f)
    theta = math.radians(theta_i_deg)
    si.wi = mi.Vector3f(math.sin(theta), 0.0, math.cos(theta))
    si.n = mi.Vector3f(0, 0, 1)
    si.sh_frame = mi.Frame3f(si.n)
    return si


def write_burley_heatmap(path: Path, rows: list[dict]) -> None:
    angles = [0, 30, 60, 80]
    roughnesses = [0.1, 0.5, 0.9]
    cell, margin_x, margin_y, panel_gap = 74, 80, 82, 52
    panel_w, panel_h = margin_x + cell * 4, margin_y + cell * 4
    width = panel_w * 3 + panel_gap * 2
    height = panel_h + 58
    lookup = {(r["roughness"], r["theta_i"], r["theta_o"]): r["ratio"] for r in rows}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#20242a"/>',
    ]
    for panel, roughness in enumerate(roughnesses):
        ox = panel * (panel_w + panel_gap)
        parts.append(
            f'<text x="{ox + panel_w / 2:.1f}" y="31" text-anchor="middle" '
            f'font-family="Arial" font-size="22" font-weight="600" fill="white">roughness {roughness}</text>'
        )
        for i, ti in enumerate(angles):
            parts.append(
                f'<text x="{ox + margin_x - 10}" y="{margin_y + i * cell + 44}" '
                f'text-anchor="end" font-family="Arial" font-size="15" fill="#d7dce4">{ti}°</text>'
            )
            for j, to in enumerate(angles):
                ratio = lookup[(roughness, ti, to)]
                if ratio < 1.0:
                    strength = min((1.0 - ratio) / 0.3, 1.0)
                    colour = f"rgb({55 + int(55 * strength)},{105 + int(40 * strength)},{165 + int(55 * strength)})"
                else:
                    strength = min((ratio - 1.0) / 1.3, 1.0)
                    colour = f"rgb({92 + int(145 * strength)},{91 - int(35 * strength)},{79 - int(35 * strength)})"
                x, y = ox + margin_x + j * cell, margin_y + i * cell
                parts.extend(
                    [
                        f'<rect x="{x}" y="{y}" width="{cell - 2}" height="{cell - 2}" fill="{colour}"/>',
                        f'<text x="{x + (cell - 2)/2:.1f}" y="{y + 43}" text-anchor="middle" '
                        f'font-family="Arial" font-size="16" fill="white">{ratio:.3f}</text>',
                    ]
                )
        for j, to in enumerate(angles):
            parts.append(
                f'<text x="{ox + margin_x + j * cell + (cell - 2)/2:.1f}" y="{margin_y - 12}" '
                f'text-anchor="middle" font-family="Arial" font-size="15" fill="#d7dce4">{to}°</text>'
            )
        label_x = ox + 18
        label_y = margin_y + 2 * cell
        parts.append(
            f'<text x="{label_x}" y="{label_y}" text-anchor="middle" '
            f'transform="rotate(-90 {label_x} {label_y})" '
            'font-family="Arial" font-size="15" fill="#d7dce4">incidence</text>'
        )
    parts.append(
        f'<text x="{width/2:.1f}" y="{height - 15}" text-anchor="middle" '
        'font-family="Arial" font-size="16" fill="#d7dce4">Exit angle increases left to right; values are Burley / Lambert</text>'
    )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def lobe_scene(bsdf: dict, size: int, spp: int) -> dict:
    return {
        "type": "scene",
        "integrator": {"type": "path_tracer", "max_depth": 8},
        "sensor": {
            "type": "perspective",
            "fov": 32,
            "fov_axis": "x",
            "to_world": mi.ScalarTransform4f().look_at(
                origin=[0, 0.25, 5.2], target=[0, 0, 0], up=[0, 1, 0]
            ),
            "film": {
                "type": "hdrfilm", "width": size, "height": size,
                "pixel_format": "rgb", "component_format": "float32",
                "rfilter": {"type": "box"},
            },
            "sampler": {"type": "stratified", "sample_count": spp},
        },
        "fill": {"type": "constant", "radiance": rgb([0.04, 0.04, 0.05])},
        "key": {
            "type": "point",
            "position": [3.0, 2.5, 3.0],
            "intensity": rgb([150, 150, 150]),
        },
        "rim": {
            "type": "point",
            "position": [-3.0, 1.8, -2.4],
            "intensity": rgb([90, 90, 90]),
        },
        "sphere": {"type": "sphere", "radius": 1.0, "bsdf": bsdf},
    }


def run_material_features(
    data: Path, renders: Path, figures: Path, quick: bool, seed: int
) -> dict:
    # Dedicated anisotropy orientation comparison.
    aniso_size, aniso_spp = ((280, 64) if quick else (500, 256))
    aniso_panels = []
    for key, value, title, caption in [
        ("isotropic", 0.0, "Isotropic GGX", "Circular response; anisotropic 0"),
        ("anisotropic", 0.8, "Anisotropic GGX", "Tangent-oriented elongated response"),
    ]:
        scene = mi.load_dict(anisotropy_scene(value, aniso_size, aniso_spp))
        image = np.asarray(mi.render(scene, spp=aniso_spp, seed=seed), dtype=np.float32)[..., :3]
        exr, png = renders / f"anisotropy_{key}.exr", figures / f"anisotropy_{key}.png"
        write_bitmap_outputs(exr, png, image)
        aniso_panels.append({"png": png, "title": title, "caption": caption})
    write_panel_svg(
        figures / "anisotropy_orientation_comparison.svg",
        aniso_panels, aniso_size, aniso_size, 2,
    )

    # Burley direct-evaluation sweep, with specular disabled to isolate diffuse.
    angles = [0, 30, 60, 80]
    burley_rows = []
    ctx = mi.BSDFContext()
    for roughness in [0.1, 0.5, 0.9]:
        lambert = mi.load_dict(
            principled(
                diffuse_model="lambert", base_colour=[1, 1, 1], roughness=roughness,
                metallic=0.0, specular=0.0,
            )
        )
        burley = mi.load_dict(
            principled(
                diffuse_model="burley", base_colour=[1, 1, 1], roughness=roughness,
                metallic=0.0, specular=0.0,
            )
        )
        for ti in angles:
            si = make_surface_interaction(ti)
            for to in angles:
                theta_o = math.radians(to)
                wo = mi.Vector3f(math.sin(theta_o), 0.0, math.cos(theta_o))
                value_l = float(np.asarray(lambert.eval(ctx, si, wo)).reshape(-1)[0])
                value_b = float(np.asarray(burley.eval(ctx, si, wo)).reshape(-1)[0])
                burley_rows.append(
                    {
                        "roughness": roughness,
                        "theta_i": ti,
                        "theta_o": to,
                        "lambert": value_l,
                        "burley": value_b,
                        "ratio": value_b / max(value_l, 1e-12),
                    }
                )
    with (data / "burley_angle_sweep.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(burley_rows[0]))
        writer.writeheader()
        writer.writerows(burley_rows)
    write_burley_heatmap(figures / "burley_angle_sweep.svg", burley_rows)

    # Same-position controls remove the confound in the original five-sphere rows.
    lobe_size, lobe_spp = ((260, 64) if quick else (420, 256))
    lobe_configs = [
        (
            "clearcoat_off", "Clearcoat off", "Matched base control",
            principled(base_colour=[0.30, 0.025, 0.025], roughness=0.9,
                       metallic=0.0, specular=0.0, clearcoat=0.0),
        ),
        (
            "clearcoat_soft", "Soft clearcoat", "clearcoat gloss 0",
            principled(base_colour=[0.30, 0.025, 0.025], roughness=0.9,
                       metallic=0.0, specular=0.0, clearcoat=1.0, clearcoat_gloss=0.0),
        ),
        (
            "clearcoat_sharp", "Sharp clearcoat", "clearcoat gloss 1",
            principled(base_colour=[0.30, 0.025, 0.025], roughness=0.9,
                       metallic=0.0, specular=0.0, clearcoat=1.0, clearcoat_gloss=1.0),
        ),
        (
            "sheen_off", "Sheen off", "Matched base control",
            principled(base_colour=[0.10, 0.12, 0.34], roughness=0.8,
                       metallic=0.0, specular=0.0, sheen=0.0),
        ),
        (
            "sheen_white", "White sheen", "sheen tint 0",
            principled(base_colour=[0.10, 0.12, 0.34], roughness=0.8,
                       metallic=0.0, specular=0.0, sheen=1.0, sheen_tint=0.0),
        ),
        (
            "sheen_tinted", "Tinted sheen", "sheen tint 1",
            principled(base_colour=[0.10, 0.12, 0.34], roughness=0.8,
                       metallic=0.0, specular=0.0, sheen=1.0, sheen_tint=1.0),
        ),
    ]
    lobe_panels = []
    lobe_images = {}
    for key, title, caption, bsdf in lobe_configs:
        scene = mi.load_dict(lobe_scene(bsdf, lobe_size, lobe_spp))
        image = np.asarray(mi.render(scene, spp=lobe_spp, seed=seed), dtype=np.float32)[..., :3]
        lobe_images[key] = image
        exr, png = renders / f"lobe_{key}.exr", figures / f"lobe_{key}.png"
        write_bitmap_outputs(exr, png, image)
        lobe_panels.append({"png": png, "title": title, "caption": caption})
    write_panel_svg(
        figures / "clearcoat_sheen_same_position.svg",
        lobe_panels, lobe_size, lobe_size, 3,
    )
    lobe_rows = []
    for feature, control, variants in [
        ("clearcoat", "clearcoat_off", ["clearcoat_soft", "clearcoat_sharp"]),
        ("sheen", "sheen_off", ["sheen_white", "sheen_tinted"]),
    ]:
        for variant in variants:
            delta = np.abs(lobe_images[variant] - lobe_images[control])
            lobe_rows.append(
                {
                    "feature": feature,
                    "variant": variant,
                    "mae_against_control": float(delta.mean()),
                    "max_difference": float(delta.max()),
                    "changed_pixel_fraction_gt_0_01": float(
                        (delta.mean(axis=-1) > 0.01).mean()
                    ),
                }
            )
    with (data / "lobe_visual_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(lobe_rows[0]))
        writer.writeheader()
        writer.writerows(lobe_rows)
    return {
        "anisotropy_resolution": [aniso_size, aniso_size],
        "anisotropy_spp": aniso_spp,
        "lobe_resolution": [lobe_size, lobe_size],
        "lobe_spp": lobe_spp,
        "seed": seed,
        "burley_normal_ratios": [
            row["ratio"] for row in burley_rows
            if row["theta_i"] == 0 and row["theta_o"] == 0
        ],
        "burley_grazing_ratios": [
            row["ratio"] for row in burley_rows
            if row["theta_i"] == 80 and row["theta_o"] == 80
        ],
    }


def transparent_shadow_scene(
    mode: str, width: int, height: int, spp: int
) -> dict:
    has_pane = mode != "reference"
    enabled = mode == "transparent_on"
    scene = {
        "type": "scene",
        "integrator": {
            "type": "path_tracer",
            "max_depth": 2,
            "rr_depth": 3,
            "transparent_shadows": enabled,
            "max_transparent_shadow_depth": 8,
        },
        "sensor": {
            "type": "perspective",
            "fov": 34,
            "fov_axis": "x",
            # The camera ray stays below the pane; only the NEE shadow ray
            # crosses it, isolating the feature from ordinary camera refraction.
            "to_world": mi.ScalarTransform4f().look_at(
                origin=[3.2, 2.2, 1.15], target=[0, 0, 0], up=[0, 0, 1]
            ),
            "film": {
                "type": "hdrfilm", "width": width, "height": height,
                "pixel_format": "rgb", "component_format": "float32",
                "rfilter": {"type": "box"},
            },
            "sampler": {"type": "stratified", "sample_count": spp},
        },
        "receiver": {
            "type": "rectangle",
            "to_world": mi.ScalarTransform4f().scale([1.0, 1.0, 1]),
            "bsdf": principled(
                base_colour=[0.72, 0.72, 0.72], roughness=1.0,
                metallic=0.0, specular=0.0,
            ),
        },
        "light": {
            "type": "rectangle",
            "to_world": mi.ScalarTransform4f().translate([0, 0, 4.0])
            @ mi.ScalarTransform4f().rotate([0, 1, 0], 180)
            @ mi.ScalarTransform4f().scale([1.6, 1.6, 1]),
            "emitter": {"type": "area", "radiance": rgb([8.0, 8.0, 8.0])},
        },
    }
    if has_pane:
        scene["pane"] = {
            "type": "rectangle",
            "to_world": mi.ScalarTransform4f().translate([0, 0, 2.0]).scale([1.6, 1.6, 1]),
            "bsdf": principled(
                base_colour=[1, 1, 1], transmission=1.0, ior=1.5, thin=True
            ),
        }
    return scene


def primary_shape_mask(scene: mi.Scene, shape_id: str) -> np.ndarray:
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
    target = next(shape for shape in scene.shapes() if shape.id() == shape_id)
    return np.asarray(si.shape == mi.ShapePtr(target), dtype=bool).reshape(height, width)


def run_transparent_shadows(
    data: Path, renders: Path, figures: Path, quick: bool, seed: int
) -> dict:
    width, height = ((240, 180) if quick else (480, 360))
    spp = 64 if quick else 256
    panels, rows = [], []
    for mode, title, caption in [
        ("reference", "No pane", "Unobstructed direct-light reference"),
        ("transparent_off", "Pane; feature off", "Binary visibility blocks NEE"),
        ("transparent_on", "Pane; feature on", "Straight-through NEE approximation"),
    ]:
        scene = mi.load_dict(transparent_shadow_scene(mode, width, height, spp))
        image = np.asarray(mi.render(scene, spp=spp, seed=seed), dtype=np.float32)[..., :3]
        mask = primary_shape_mask(scene, "receiver")
        luminance = image @ np.asarray([0.2126, 0.7152, 0.0722], dtype=np.float32)
        rows.append(
            {
                "mode": mode,
                "resolution": f"{width}x{height}",
                "spp": spp,
                "seed": seed,
                "receiver_mean_luminance": float(luminance[mask].mean()),
                "receiver_pixel_count": int(mask.sum()),
            }
        )
        exr, png = renders / f"transparent_shadows_{mode}.exr", figures / f"transparent_shadows_{mode}.png"
        write_bitmap_outputs(exr, png, image)
        panels.append({"png": png, "title": title, "caption": caption})
    reference = rows[0]["receiver_mean_luminance"]
    off = rows[1]["receiver_mean_luminance"]
    on = rows[2]["receiver_mean_luminance"]
    for row in rows:
        row["fraction_of_unobstructed"] = row["receiver_mean_luminance"] / max(reference, 1e-12)
    with (data / "transparent_shadows.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    write_panel_svg(
        figures / "transparent_shadows_comparison.svg",
        panels, width, height, 3,
    )
    return {
        "resolution": [width, height], "spp": spp, "seed": seed,
        "reference_mean": reference, "off_mean": off, "on_mean": on,
        "on_fraction_of_reference": on / max(reference, 1e-12),
        "off_fraction_of_reference": off / max(reference, 1e-12),
    }


def run_gallery(
    data: Path,
    renders: Path,
    figures: Path,
    *,
    quick: bool,
    requested_spp: int | None,
    seed: int,
    firefly_clamp: float,
) -> dict:
    width, height = ((960, 540) if quick else (1600, 900))
    spp = requested_spp if requested_spp is not None else (16 if quick else 1024)

    print(f"Rendering Principled gallery: {width}x{height}, {spp} spp", flush=True)
    scene = mi.load_dict(material_test_scene(width, height, spp, firefly_clamp))
    image = np.asarray(mi.render(scene, spp=spp, seed=seed), dtype=np.float32)[..., :3]

    clamp_suffix = "" if firefly_clamp <= 0 else f"_clamp{firefly_clamp:g}"
    exr_path = renders / f"principled_material_showcase{clamp_suffix}.exr"
    png_path = figures / f"principled_material_showcase{clamp_suffix}.png"
    svg_path = figures / f"principled_material_showcase{clamp_suffix}_labelled.svg"
    # Bitmap.write() is synchronous. This matters because the labelled SVG
    # immediately reads the PNG back for embedding; mi.util.write_bitmap()
    # may still be flushing the file when it returns.
    bitmap = mi.Bitmap(np.ascontiguousarray(image))
    bitmap.write(str(exr_path))
    display_bitmap = bitmap.convert(
        mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, True
    )
    display_bitmap.write(str(png_path))
    write_labelled_svg(svg_path, png_path, width, height)
    write_catalogue(data / "material_catalogue.csv")
    print(f"Wrote {png_path}", flush=True)
    print(f"Wrote {svg_path}", flush=True)
    return {
        "resolution": [width, height],
        "spp": spp,
        "seed": seed,
        "sampler": "stratified",
        "reconstruction_filter": "box",
        "max_depth": 12,
        "rr_depth": 3,
        "firefly_clamp": firefly_clamp,
        "clamp_note": (
            "Disabled; unbiased qualitative render."
            if firefly_clamp <= 0 else
            "Biased per-contribution clamp used only for qualitative display."
        ),
        "integrator": "custom path_tracer",
        "emitter": "Mitsuba envmap plus two area lights",
        "hdri": str(HDRI.relative_to(ROOT)),
        "material_count": len(MATERIALS),
    }


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    renders = output / "renders"
    figures = output / "figures"
    data = output / "data"
    for directory in (renders, figures, data):
        directory.mkdir(parents=True, exist_ok=True)

    results = {}
    if args.only in ("all", "gallery"):
        print("\n[1/5] Principled material showcase", flush=True)
        results["gallery"] = run_gallery(
            data, renders, figures,
            quick=args.quick,
            requested_spp=args.spp,
            seed=args.seed,
            firefly_clamp=args.clamp,
        )
    if args.only in ("all", "glazing"):
        print("\n[2/5] Thin-sheet and solid glazing", flush=True)
        results["glazing"] = run_glazing(
            data, renders, figures, args.quick, args.seed + 4
        )
    if args.only in ("all", "camera"):
        print("\n[3/5] Physical camera", flush=True)
        results["camera"] = run_camera(
            data, renders, figures, args.quick, args.seed + 8
        )
    if args.only in ("all", "materials"):
        print("\n[4/5] Anisotropy, Burley, clearcoat, and sheen", flush=True)
        results["material_features"] = run_material_features(
            data, renders, figures, args.quick, args.seed + 12
        )
    if args.only in ("all", "shadows"):
        print("\n[5/5] Transparent shadows", flush=True)
        results["transparent_shadows"] = run_transparent_shadows(
            data, renders, figures, args.quick, args.seed + 16
        )

    metadata = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Canonical evaluation for thesis section 5.4: isolated feature behaviour",
        "backend": "llvm_ad_rgb",
        "hardware": "Apple M4 Pro",
        "selected_group": args.only,
        "quick": args.quick,
        "results": results,
        "script_sha256": file_sha256(SCRIPT_PATH),
        **git_metadata(),
    }
    metadata_name = "metadata.json" if args.only == "all" else f"metadata_{args.only}.json"
    (output / metadata_name).write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nWrote {output / metadata_name}", flush=True)


if __name__ == "__main__":
    main()
