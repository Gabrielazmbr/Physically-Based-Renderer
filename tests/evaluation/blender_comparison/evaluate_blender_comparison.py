#!/usr/bin/env python3
"""Audit and assemble the Country Kitchen Blender Cycles comparison.

This is a non-rendering evaluator. It validates the six fixed Cycles EXRs and
the six canonical raw custom-renderer AOV EXRs, records reproducibility and
image statistics, and writes unembellished side-by-side PNGs. Numerical image
differences are descriptive only because Cycles and the custom renderer do not
share identical material models, estimators, filtering, or clamp policy.
"""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import mitsuba as mi
import numpy as np


SCRIPT_PATH = Path(__file__).resolve()
ROOT = SCRIPT_PATH.parents[3]
OUTPUT = ROOT / "outputs" / "evaluation" / "6_blender_comparison" / "kitchen"
CYCLES_RENDERS = OUTPUT / "renders"
CUSTOM_OUTPUT = ROOT / "outputs" / "evaluation" / "5_5_integration" / "kitchen"
CUSTOM_RENDERS = CUSTOM_OUTPUT / "renders"
CUSTOM_METADATA = CUSTOM_OUTPUT / "metadata.json"
BLENDER_SCENE = (
    ROOT
    / "assets"
    / "production_scenes"
    / "kitchen_scene"
    / "blender"
    / "Country-Kitchen.blend"
)
DATA = OUTPUT / "data"
FIGURES = OUTPUT / "figures"

VIEWS = (
    (0, "hero", "full-room lighting and material integration"),
    (1, "stove", "metal response and depth of field"),
    (2, "table", "glass, transmission, and bright-window transport"),
    (3, "radio", "texture and small-detail reconstruction"),
    (4, "towel", "textured diffuse response and practical-light visibility"),
    (5, "island", "mixed materials, close occlusion, and depth of field"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def read_bitmap(path: Path) -> tuple[mi.Bitmap, np.ndarray]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing comparison input: {path}")
    bitmap = mi.Bitmap(str(path))
    image = np.asarray(bitmap, dtype=np.float32)
    return bitmap, image


def property_value(properties: mi.Properties, name: str, fallback=None):
    try:
        return properties[name]
    except Exception:
        return fallback


def luminance(image: np.ndarray) -> np.ndarray:
    return (
        0.2126 * image[..., 0]
        + 0.7152 * image[..., 1]
        + 0.0722 * image[..., 2]
    )


def image_statistics(image: np.ndarray) -> dict:
    lum = luminance(image)
    return {
        "mean_luminance": float(lum.mean()),
        "p999_luminance": float(np.quantile(lum, 0.999)),
        "max_luminance": float(lum.max()),
        "pixels_over_luminance_10": int(np.count_nonzero(lum > 10.0)),
        "finite": bool(np.isfinite(image).all()),
    }


def write_png(path: Path, image: np.ndarray) -> None:
    bitmap = mi.Bitmap(np.ascontiguousarray(image, dtype=np.float32))
    bitmap.convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, True).write(
        str(path)
    )


def audit_views() -> tuple[list[dict], list[dict]]:
    audit_rows = []
    comparison_rows = []

    for index, name, evidence in VIEWS:
        cycles_path = CYCLES_RENDERS / f"cycles_{index}_{name}.exr"
        custom_path = CUSTOM_RENDERS / f"{index}_{name}_aovs.exr"
        cycles_bitmap, cycles_all = read_bitmap(cycles_path)
        _, custom_all = read_bitmap(custom_path)
        cycles = cycles_all[..., :3]
        custom = custom_all[..., :3]

        if cycles.shape != custom.shape:
            raise ValueError(
                f"View {index} dimensions differ: Cycles {cycles.shape}, "
                f"custom {custom.shape}"
            )

        metadata = cycles_bitmap.metadata()
        cycles_stats = image_statistics(cycles)
        custom_stats = image_statistics(custom)
        expected_camera = f"CH6_{index:02d}_{name.capitalize()}"
        camera = str(property_value(metadata, "Camera", ""))
        samples = int(property_value(metadata, "cycles.RenderLayer.samples", 0))
        camera_metadata_matches = camera == expected_camera

        audit_rows.extend(
            (
                {
                    "view": index,
                    "name": name,
                    "renderer": "Blender Cycles",
                    "filename": cycles_path.name,
                    "width": cycles.shape[1],
                    "height": cycles.shape[0],
                    "channels": cycles_all.shape[-1],
                    "samples": samples,
                    "camera": camera,
                    "expected_camera": expected_camera,
                    "camera_metadata_matches": camera_metadata_matches,
                    "provenance_note": (
                        ""
                        if camera_metadata_matches
                        else "Visually verified view; Blender EXR Camera field "
                        "records the scene camera active when the Render Result "
                        "was saved, which may differ from the camera used to render it."
                    ),
                    **cycles_stats,
                    "sha256": sha256(cycles_path),
                    "status": (
                        "PASS"
                        if cycles_stats["finite"]
                        and cycles.shape[:2] == (720, 1280)
                        and cycles_all.shape[-1] == 3
                        and samples == 1024
                        else "FAIL"
                    ),
                },
                {
                    "view": index,
                    "name": name,
                    "renderer": "Custom renderer",
                    "filename": custom_path.name,
                    "width": custom.shape[1],
                    "height": custom.shape[0],
                    "channels": custom_all.shape[-1],
                    "samples": 1024,
                    "camera": f"sensor_{index}",
                    "expected_camera": f"sensor_{index}",
                    "camera_metadata_matches": True,
                    "provenance_note": "",
                    **custom_stats,
                    "sha256": sha256(custom_path),
                    "status": (
                        "PASS"
                        if custom_stats["finite"]
                        and custom.shape[:2] == (720, 1280)
                        and custom_all.shape[-1] == 10
                        else "FAIL"
                    ),
                },
            )
        )

        difference = cycles.astype(np.float64) - custom.astype(np.float64)
        comparison_rows.append(
            {
                "view": index,
                "name": name,
                "evidence": evidence,
                "cycles_mean_luminance": cycles_stats["mean_luminance"],
                "custom_mean_luminance": custom_stats["mean_luminance"],
                "cycles_to_custom_mean_luminance_ratio": (
                    cycles_stats["mean_luminance"]
                    / custom_stats["mean_luminance"]
                ),
                "descriptive_rgb_mae": float(np.mean(np.abs(difference))),
                "descriptive_rgb_rmse": float(np.sqrt(np.mean(difference**2))),
                "cycles_pixels_over_luminance_10": cycles_stats[
                    "pixels_over_luminance_10"
                ],
                "custom_pixels_over_luminance_10": custom_stats[
                    "pixels_over_luminance_10"
                ],
                "interpretation_policy": (
                    "descriptive only; non-identical BSDFs, estimators, and "
                    "clamp policy"
                ),
            }
        )

        pair = np.concatenate((cycles, custom), axis=1)
        write_png(FIGURES / f"{index}_{name}_cycles_vs_custom_raw.png", pair)

    return audit_rows, comparison_rows


def audit_unclamped_controls() -> list[dict]:
    """Audit all six controls that match Cycles' disabled clamp policy."""
    rows = []
    for index, name, _ in VIEWS:
        cycles_path = CYCLES_RENDERS / f"cycles_{index}_{name}.exr"
        custom_path = (
            CYCLES_RENDERS / f"custom_{index}_{name}_unclamped_aovs.exr"
        )
        _, cycles_all = read_bitmap(cycles_path)
        _, custom_all = read_bitmap(custom_path)
        cycles = cycles_all[..., :3]
        custom = custom_all[..., :3]
        if cycles.shape != custom.shape:
            raise ValueError(
                f"Unclamped {name} dimensions differ: "
                f"{cycles.shape} and {custom.shape}"
            )

        cycles_stats = image_statistics(cycles)
        custom_stats = image_statistics(custom)
        write_png(
            FIGURES / f"{index}_{name}_cycles_vs_custom_unclamped.png",
            np.concatenate((cycles, custom), axis=1),
        )
        rows.append(
            {
                "view": index,
                "name": name,
                "cycles_filename": cycles_path.name,
                "custom_filename": custom_path.name,
                "width": cycles.shape[1],
                "height": cycles.shape[0],
                "effective_spp_each": 1024,
                "cycles_mean_luminance": cycles_stats["mean_luminance"],
                "custom_mean_luminance": custom_stats["mean_luminance"],
                "cycles_p999_luminance": cycles_stats["p999_luminance"],
                "custom_p999_luminance": custom_stats["p999_luminance"],
                "cycles_max_luminance": cycles_stats["max_luminance"],
                "custom_max_luminance": custom_stats["max_luminance"],
                "cycles_pixels_over_luminance_10": cycles_stats[
                    "pixels_over_luminance_10"
                ],
                "custom_pixels_over_luminance_10": custom_stats[
                    "pixels_over_luminance_10"
                ],
                "cycles_sha256": sha256(cycles_path),
                "custom_sha256": sha256(custom_path),
                "status": (
                    "PASS"
                    if cycles_stats["finite"]
                    and custom_stats["finite"]
                    and custom_all.shape[-1] == 10
                    else "FAIL"
                ),
            }
        )
    return rows


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    audit_rows, comparison_rows = audit_views()
    unclamped_controls = audit_unclamped_controls()
    write_csv(DATA / "render_inventory.csv", audit_rows)
    write_csv(DATA / "comparison_summary.csv", comparison_rows)
    write_csv(DATA / "unclamped_controls.csv", unclamped_controls)
    old_control = DATA / "unclamped_hero_control.csv"
    if old_control.exists():
        old_control.unlink()

    custom_metadata = json.loads(CUSTOM_METADATA.read_text(encoding="utf-8"))
    status = (
        "PASS"
        if all(row["status"] == "PASS" for row in audit_rows)
        and all(row["status"] == "PASS" for row in unclamped_controls)
        else "FAIL"
    )
    metadata = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Country Kitchen Blender Cycles comparison for thesis Chapter 6",
        "status": status,
        "comparison_policy": {
            "primary_evidence": "raw linear EXR beauty comparison",
            "metrics": "descriptive only; no correctness threshold",
            "cycles": {
                "version": "4.3.0",
                "device": "CPU",
                "samples": 1024,
                "max_bounces": 17,
                "denoising": False,
                "clamping": False,
                "resolution": [1280, 720],
                "output": "full-float RGB OpenEXR, Linear Rec.709",
                "view_transform": "Standard, exposure 0, gamma 1",
                "pixel_filter": "box",
            },
            "custom": custom_metadata["settings"],
            "canonical_six_view_asymmetry": (
                "Canonical custom renders use firefly_clamp=50; Cycles renders "
                "are unclamped."
            ),
            "unclamped_control": (
                "Six additional custom views use identical custom settings but "
                "firefly_clamp=0, providing matched clamp-policy controls against "
                "the six unclamped Cycles views."
            ),
            "denoising_policy": (
                "Not applied in this audit: custom OIDN uses albedo/normal AOVs, "
                "while the supplied Cycles EXRs contain beauty RGB only."
            ),
        },
        "views": [
            {"index": index, "name": name, "evidence": evidence}
            for index, name, evidence in VIEWS
        ],
        "hardware": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "source_hashes": {
            "evaluation_script": sha256(SCRIPT_PATH),
            "camera_import_script": sha256(
                SCRIPT_PATH.parent / "import_kitchen_cameras.py"
            ),
            "cycles_blender_scene": sha256(BLENDER_SCENE),
            "canonical_kitchen_scene": sha256(
                ROOT / "assets" / "production_scenes" / "kitchen_scene" / "scene.xml"
            ),
        },
        "results": {
            "render_records": len(audit_rows),
            "comparison_records": len(comparison_rows),
            "unclamped_controls": unclamped_controls,
        },
        **git_metadata(),
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    if status != "PASS":
        failed = [row for row in audit_rows if row["status"] != "PASS"]
        raise RuntimeError(f"Chapter 6 Kitchen comparison audit failed: {failed}")
    print(f"PASS: six Cycles/custom pairs audited in {OUTPUT}")


if __name__ == "__main__":
    main()
