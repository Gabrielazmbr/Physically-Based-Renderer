#!/usr/bin/env python3
"""Canonical evidence audit for thesis Section 5.6.

The historical defective renderer is not reconstructed. Instead, this cheap
runner verifies the six user-approved diagnostic images, records their hashes
and image statistics, checks the decisive black-frame control, and confirms
that the active CustomEnvmap uses the corrected safe shadow-ray radius.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
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


OUTPUT = ROOT / "outputs" / "evaluation" / "5_6_failure_case"
DATA = OUTPUT / "data"
KITCHEN = ROOT / "assets" / "production_scenes" / "kitchen_scene"
EMITTER_SOURCE = ROOT / "emitters" / "envmap.py"

STEPS = (
    (
        1,
        "1_light_not_coherent.png",
        "Initial symptom",
        "Interior illumination direction was inconsistent with light entering through the window.",
    ),
    (
        2,
        "2_light_source_isolation.png",
        "Environment isolation",
        "Practical emitters were removed so the HDR environment was the only light source.",
    ),
    (
        3,
        "3_direct_light_only.png",
        "Direct-only isolation",
        "Indirect bounces were removed; mutually inconsistent directly lit regions remained.",
    ),
    (
        4,
        "4_window_transmission_to_zero.png",
        "Opaque-window control before fix",
        "Illumination remained after setting window transmission to zero, proving that light bypassed the intended opening.",
    ),
    (
        5,
        "5_bug_fixed_black_image.png",
        "Opaque-window control after fix",
        "With the visibility defect corrected, the sealed direct-only scene became exactly black.",
    ),
    (
        6,
        "6_window_transmission_restored.png",
        "Transmission restored after fix",
        "Restoring the pane admitted environment illumination through the intended opening.",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        help="Directory containing the six externally delivered diagnostic PNGs.",
    )
    return parser.parse_args()


def find_evidence_dir(explicit: Path | None) -> Path | None:
    candidates = (
        [explicit.expanduser().resolve()]
        if explicit is not None
        else [
            ROOT / "assets" / "evaluation" / "scale_failure",
            OUTPUT / "renders",
        ]
    )
    for candidate in candidates:
        if all((candidate / filename).is_file() for _, filename, _, _ in STEPS):
            return candidate
    if explicit is not None:
        raise FileNotFoundError(
            f"The evidence directory does not contain all six required PNGs: {explicit}"
        )
    return None


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


def image_rows(evidence_dir: Path) -> tuple[list[dict], dict]:
    rows = []
    dimensions = set()
    for step, filename, role, interpretation in STEPS:
        path = evidence_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing approved evidence: {path}")
        image = np.asarray(mi.Bitmap(str(path)), dtype=np.float32)[..., :3]
        dimensions.add(image.shape[:2])
        luminance = (
            0.2126 * image[..., 0]
            + 0.7152 * image[..., 1]
            + 0.0722 * image[..., 2]
        )
        rows.append(
            {
                "step": step,
                "filename": filename,
                "evidence_role": role,
                "interpretation": interpretation,
                "width": image.shape[1],
                "height": image.shape[0],
                "mean_luminance": float(luminance.mean()),
                "max_channel": float(image.max()),
                "nonzero_pixel_fraction": float(np.any(image > 0.0, axis=-1).mean()),
                "sha256": sha256(path),
            }
        )

    black = rows[4]
    restored = rows[5]
    checks = {
        "evidence_count": len(rows),
        "common_dimensions": len(dimensions) == 1,
        "dimensions": list(next(iter(dimensions))) if len(dimensions) == 1 else None,
        "opaque_after_fix_exactly_black": black["max_channel"] == 0.0,
        "restored_transmission_nonzero": restored["mean_luminance"] > 0.0,
    }
    checks["status"] = (
        "PASS"
        if checks["evidence_count"] == 6
        and checks["common_dimensions"]
        and checks["opaque_after_fix_exactly_black"]
        and checks["restored_transmission_nonzero"]
        else "FAIL"
    )
    return rows, checks


def active_fix_check() -> dict:
    previous = Path.cwd()
    try:
        # CustomEnvmap resolves its texture filename against the process CWD.
        os.chdir(KITCHEN)
        scene = mi.load_file("scene.xml", resx=16, resy=9, spp=1)
        environment = scene.environment()
        radius = float(environment.bsphere_radius)
    finally:
        os.chdir(previous)

    source = EMITTER_SOURCE.read_text(encoding="utf-8")
    result = {
        "runtime_bsphere_radius": radius,
        "safe_default_at_least_1e6": radius >= 1e6,
        "sample_distance_uses_twice_radius": "ds.dist = 2.0 * self.bsphere_radius" in source,
        "set_scene_never_shortens_radius": "dr.maximum" in source,
    }
    result["status"] = (
        "PASS"
        if result["safe_default_at_least_1e6"]
        and result["sample_distance_uses_twice_radius"]
        and result["set_scene_never_shortens_radius"]
        else "FAIL"
    )
    return result


def main() -> None:
    args = parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    evidence_dir = find_evidence_dir(args.evidence_dir)
    if evidence_dir is not None:
        rows, evidence_checks = image_rows(evidence_dir)
        write_csv(DATA / "diagnostic_sequence.csv", rows)
    else:
        evidence_checks = {
            "status": "SKIP",
            "evidence_count": 0,
            "reason": "external diagnostic images were not supplied",
        }
    fix_checks = active_fix_check()
    write_csv(DATA / "verification.csv", [{**evidence_checks, **fix_checks}])

    metadata = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Scale-dependent environment visibility failure case for thesis Section 5.6",
        "evidence_policy": "Fixed historical diagnostic images; no defective-code reconstruction or rerender",
        "evidence_directory": str(evidence_dir) if evidence_dir else None,
        "evidence_checks": evidence_checks,
        "active_fix_checks": fix_checks,
        "mitsuba_version": mi.__version__,
        "variant": mi.variant(),
        "hardware": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "source_hashes": {
            "evaluation_script": sha256(SCRIPT_PATH),
            "custom_environment": sha256(EMITTER_SOURCE),
            "kitchen_scene": sha256(KITCHEN / "scene.xml"),
        },
        **git_metadata(),
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    if evidence_checks["status"] == "FAIL" or fix_checks["status"] != "PASS":
        raise RuntimeError(f"Section 5.6 verification failed: {metadata}")
    if evidence_checks["status"] == "PASS":
        print(f"PASS: six approved images and active fix verified in {OUTPUT}")
    else:
        print("PASS: active fix verified; external diagnostic image audit skipped")


if __name__ == "__main__":
    main()
