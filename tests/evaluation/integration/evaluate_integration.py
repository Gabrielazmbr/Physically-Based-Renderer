#!/usr/bin/env python3
"""Canonical imported-scene evaluation for thesis Section 5.5.

The current target is the Blender-authored Lego 856 Bulldozer used in Section
5.5.1. The evaluator checks asset integrity, reconstructs the exported scene
with the custom plugins, runs a low-cost silhouette control, and compares the
full custom result with a fixed Blender Cycles reference. The Country Kitchen
target covers Section 5.5.2 through a reproducible conversion manifest and six
production-scene views.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import Counter
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
from assets.production_scenes.lego_bulldozer.scene import (  # noqa: E402
    collapse_material_colour,
    load_description,
    load_exported_scene,
    reconstructed_scene,
    scalar_matrix,
)


ASSET_DIR = ROOT / "assets" / "production_scenes" / "lego_bulldozer"
XML_PATH = ASSET_DIR / "scene_export.xml"
BLEND_PATH = ASSET_DIR / "BLENDER_LEGO_CYCLES.blend"
REFERENCE_DIR = ASSET_DIR / "reference"
REFERENCE_EXR = REFERENCE_DIR / "cycles_reference_1024spp.exr"
REFERENCE_METADATA = REFERENCE_DIR / "reference_metadata.json"

DEFAULT_OUTPUT = ROOT / "outputs" / "evaluation" / "5_5_integration"
DEFAULT_QUICK_OUTPUT = ROOT / "outputs" / "quick" / "5_5_integration"

EXPECTED_SHAPES = 439
EXPECTED_MATERIALS = 9

KITCHEN_DIR = ROOT / "assets" / "production_scenes" / "kitchen_scene"
KITCHEN_XML = KITCHEN_DIR / "scene.xml"
KITCHEN_SOURCE_XML = KITCHEN_DIR / "scene_original.xml"
KITCHEN_BUILD = KITCHEN_DIR / "build_scene.py"
KITCHEN_VIEWS = (
    (0, "hero", "full-room integration"),
    (1, "stove", "metal, practical lighting, and depth of field"),
    (2, "table", "glass, transmission, and contact shadows"),
    (3, "radio", "textures and small geometric detail"),
    (4, "towel", "textured diffuse response"),
    (5, "island", "varied materials and close occlusion"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scene",
        choices=["lego", "kitchen"],
        default="lego",
        help="Production-scene target for Section 5.5.1 or 5.5.2.",
    )
    parser.add_argument(
        "--only",
        choices=["all", "manifest", "silhouette", "renders", "views"],
        default="all",
        help="Run one evidence group or the complete Lego evaluation.",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--resolution", type=int)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--spp", type=int)
    parser.add_argument(
        "--passes",
        type=int,
        default=None,
        help="Kitchen only: independently seeded passes to average.",
    )
    parser.add_argument(
        "--no-denoise",
        action="store_true",
        help="Kitchen only: omit OIDN display output.",
    )
    parser.add_argument("--seed", type=int, default=10)
    parser.add_argument(
        "--cycles-reference",
        type=Path,
        help="LEGO only: external Cycles EXR (for example from the evidence transfer).",
    )
    parser.add_argument(
        "--no-cycles-reference",
        action="store_true",
        help="LEGO only: render and validate without auto-detecting a local Cycles EXR.",
    )
    parser.add_argument(
        "--reference-metadata",
        type=Path,
        help="LEGO only: optional JSON metadata accompanying --cycles-reference.",
    )
    return parser.parse_args()


def file_sha256(path: Path) -> str:
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
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_exr(path: Path, image: np.ndarray) -> None:
    mi.Bitmap(np.ascontiguousarray(image, dtype=np.float32)).write(str(path))


def write_png(path: Path, image: np.ndarray) -> None:
    bitmap = mi.Bitmap(np.ascontiguousarray(image, dtype=np.float32))
    bitmap.convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, True).write(
        str(path)
    )


def inspect_kitchen_asset() -> tuple[dict, list[dict]]:
    """Rebuild and inventory the canonical Country Kitchen scene."""
    root = ET.parse(KITCHEN_XML).getroot()
    defaults = {item.get("name"): item.get("value") for item in root.findall("default")}
    materials = root.findall("bsdf")
    shapes = root.findall("shape")
    sensors = root.findall("sensor")
    filename_values = [
        item.get("value")
        for item in root.iter("string")
        if item.get("name") == "filename"
    ]
    missing_files = [
        value for value in filename_values if not (KITCHEN_DIR / value).resolve().exists()
    ]

    local_window_panes = []
    for shape in shapes:
        local = shape.find("bsdf[@type='principled_bsdf']")
        if local is None:
            continue
        thin = local.find("boolean[@name='thin']")
        transmission = local.find("float[@name='transmission']")
        if (
            thin is not None
            and thin.get("value") == "true"
            and transmission is not None
            and float(transmission.get("value")) == 1.0
        ):
            local_window_panes.append(shape)

    converted_principled = 0
    material_rows = []
    for material in materials:
        inner = (
            material
            if material.get("type") == "principled_bsdf"
            else material.find("bsdf[@type='principled_bsdf']")
        )
        if inner is not None:
            converted_principled += 1
        material_rows.append(
            {
                "material_id": material.get("id", "<anonymous>"),
                "outer_type": material.get("type"),
                "principled": inner is not None,
                "diffuse_model": (
                    inner.find("string[@name='diffuse_model']").get("value")
                    if inner is not None
                    and inner.find("string[@name='diffuse_model']") is not None
                    else ""
                ),
            }
        )

    with tempfile.TemporaryDirectory(prefix="pbr_kitchen_build_") as temp_name:
        temp = Path(temp_name)
        shutil.copy2(KITCHEN_BUILD, temp / "build_scene.py")
        shutil.copy2(KITCHEN_SOURCE_XML, temp / "scene_original.xml")
        completed = subprocess.run(
            [sys.executable, "build_scene.py"],
            cwd=temp,
            check=True,
            capture_output=True,
            text=True,
        )
        rebuilt = temp / "scene.xml"
        rebuild_matches = rebuilt.read_bytes() == KITCHEN_XML.read_bytes()
        conversion_match = re.search(
            r"Converted (\d+) materials to principled_bsdf", completed.stdout
        )
        source_materials_converted = (
            int(conversion_match.group(1)) if conversion_match else None
        )

    manifest = {
        "scene": "Country Kitchen",
        "source_materials_converted": source_materials_converted,
        "top_level_material_definitions": len(materials),
        "principled_material_definitions": converted_principled,
        "shape_count": len(shapes),
        "sensor_count": len(sensors),
        "physical_camera_count": sum(
            sensor.get("type") == "physical_camera" for sensor in sensors
        ),
        "custom_path_tracer": defaults.get("integrator") == "path_tracer",
        "custom_environment_count": len(root.findall("emitter[@type='custom_envmap']")),
        "thin_transmissive_window_pane_count": len(local_window_panes),
        "filename_reference_count": len(filename_values),
        "unique_filename_reference_count": len(set(filename_values)),
        "missing_filename_reference_count": len(missing_files),
        "canonical_rebuild_byte_identical": rebuild_matches,
    }
    manifest["status"] = (
        "PASS"
        if source_materials_converted == 85
        and len(materials) == 87
        and converted_principled == 86
        and len(shapes) == 301
        and len(sensors) == 6
        and manifest["physical_camera_count"] == 6
        and manifest["custom_path_tracer"]
        and manifest["custom_environment_count"] == 1
        and len(local_window_panes) == 1
        and not missing_files
        and rebuild_matches
        else "FAIL"
    )
    return manifest, material_rows


def render_kitchen_views(
    output: Path,
    width: int,
    height: int,
    spp: int,
    passes: int,
    seed: int,
    denoise: bool,
) -> list[dict]:
    """Render the hero view and five authored close-up sensors."""
    from denoisers.oidn import denoise_composite_aov_render

    renders = output / "renders"
    figures = output / "figures"
    rows = []
    for sensor_index, name, evidence in KITCHEN_VIEWS:
        print(f"  sensor={sensor_index} {name}", flush=True)
        started = time.perf_counter()
        previous_cwd = Path.cwd()
        try:
            # CustomEnvmap receives the XML filename verbatim and resolves it
            # against the process directory. Match render_scene.py's documented
            # launch context while keeping the evaluator callable from ROOT.
            os.chdir(KITCHEN_DIR)
            scene = mi.load_file(
                "scene.xml",
                spp=spp,
                resx=width,
                resy=height,
                sampler="stratified",
                with_aovs="true",
                max_depth="17",
                rr_depth="3",
                transparent_shadows="true",
                firefly_clamp="50",
                envmap_scale="2.0",
            )
            accumulation = None
            for pass_index in range(passes):
                rendered = np.asarray(
                    mi.render(
                        scene,
                        spp=spp,
                        sensor=sensor_index,
                        seed=seed + pass_index,
                    ),
                    dtype=np.float32,
                )
                accumulation = (
                    rendered.astype(np.float64)
                    if accumulation is None
                    else accumulation + rendered
                )
        finally:
            os.chdir(previous_cwd)
        image = np.asarray(accumulation / passes, dtype=np.float32)
        beauty = image[..., :3]
        write_exr(renders / f"{sensor_index}_{name}_aovs.exr", image)
        write_png(figures / f"{sensor_index}_{name}_beauty.png", beauty)
        if denoise:
            denoised = denoise_composite_aov_render(image)
            write_exr(renders / f"{sensor_index}_{name}_denoised.exr", denoised)
            write_png(figures / f"{sensor_index}_{name}_denoised.png", denoised)
        rows.append(
            {
                "sensor": sensor_index,
                "view": name,
                "evidence": evidence,
                "width": width,
                "height": height,
                "spp_per_pass": spp,
                "passes": passes,
                "effective_spp": spp * passes,
                "seed_start": seed,
                "sampler": "stratified",
                "max_depth": 17,
                "rr_depth": 3,
                "transparent_shadows": True,
                "firefly_clamp": 50.0,
                "aov_channel_count": int(image.shape[-1]),
                "finite": bool(np.isfinite(image).all()),
                "mean_luminance": float(luminance(beauty).mean()),
                "elapsed_seconds": float(time.perf_counter() - started),
                "status": (
                    "PASS"
                    if image.shape[-1] == 10 and np.isfinite(image).all()
                    else "FAIL"
                ),
            }
        )
    return rows


def run_kitchen(args: argparse.Namespace) -> None:
    output_root = args.output
    if output_root is None:
        output_root = DEFAULT_QUICK_OUTPUT if args.quick else DEFAULT_OUTPUT
    output = output_root / "kitchen"
    for directory in (output / "data", output / "renders", output / "figures"):
        directory.mkdir(parents=True, exist_ok=True)

    print("[1/2] Country Kitchen conversion and asset manifest", flush=True)
    manifest, materials = inspect_kitchen_asset()
    write_csv(output / "data" / "scene_manifest.csv", [manifest])
    write_csv(output / "data" / "material_inventory.csv", materials)
    if manifest["status"] != "PASS":
        raise RuntimeError(f"Kitchen manifest failed: {manifest}")

    width = args.width or (320 if args.quick else 1280)
    height = args.height or (180 if args.quick else 720)
    # Mitsuba's stratified sampler requires a power-of-two square count. Using
    # 16 avoids its silent 8 -> 9 rounding and keeps metadata exact.
    spp = args.spp or (16 if args.quick else 256)
    passes = args.passes or (1 if args.quick else 4)
    view_rows = []
    if args.only in {"all", "views", "renders"}:
        print("[2/2] Hero and five close-up views", flush=True)
        view_rows = render_kitchen_views(
            output,
            width,
            height,
            spp,
            passes,
            args.seed,
            not args.no_denoise,
        )
        write_csv(output / "data" / "views.csv", view_rows)

    metadata = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Country Kitchen production-scene integration for thesis Section 5.5.2",
        "scene": "kitchen",
        "selected_group": args.only,
        "quick": args.quick,
        "settings": {
            "width": width,
            "height": height,
            "spp_per_pass": spp,
            "passes": passes,
            "effective_spp": spp * passes,
            "seed_start": args.seed,
            "sampler": "stratified",
            "max_depth": 17,
            "rr_depth": 3,
            "transparent_shadows": True,
            "firefly_clamp": 50.0,
            "with_aovs": True,
            "denoised_figures": not args.no_denoise,
        },
        "asset": {
            "directory": str(KITCHEN_DIR.relative_to(ROOT)),
            "scene_xml_sha256": file_sha256(KITCHEN_XML),
            "source_xml_sha256": file_sha256(KITCHEN_SOURCE_XML),
            "build_script_sha256": file_sha256(KITCHEN_BUILD),
        },
        "component_hashes": {
            "path_tracer": file_sha256(ROOT / "integrators" / "path_tracer.py"),
            "principled_bsdf": file_sha256(ROOT / "bsdfs" / "principled.py"),
            "physical_camera": file_sha256(ROOT / "cameras" / "physical_camera.py"),
            "custom_environment": file_sha256(ROOT / "emitters" / "envmap.py"),
            "oidn_wrapper": file_sha256(ROOT / "denoisers" / "oidn.py"),
        },
        "results": {"manifest": manifest, "views": view_rows},
        "script_sha256": file_sha256(SCRIPT_PATH),
        **git_metadata(),
    }
    metadata_name = (
        "metadata.json" if args.only == "all" else f"metadata_{args.only}.json"
    )
    (output / metadata_name).write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {output / metadata_name}", flush=True)


def inspect_asset(
    reference_exr: Path | None,
    reference_metadata: Path | None,
) -> tuple[dict, list[dict], dict[str, np.ndarray], list[ET.Element]]:
    root = ET.parse(XML_PATH).getroot()
    material_elements, shape_elements, colours = load_description()
    material_ids = {element.get("id") for element in material_elements}
    shape_refs = [element.find("ref").get("id") for element in shape_elements]
    shape_counts = Counter(shape_refs)

    mesh_paths = [
        ASSET_DIR / element.find("string[@name='filename']").get("value")
        for element in shape_elements
    ]
    missing_meshes = [path for path in mesh_paths if not path.exists()]
    invalid_refs = [material for material in shape_refs if material not in material_ids]

    emitter = root.find("emitter[@type='envmap']")
    env_path = None
    if emitter is not None:
        filename = emitter.find("string[@name='filename']")
        if filename is not None:
            env_path = ASSET_DIR / filename.get("value")

    material_rows = []
    for element in material_elements:
        material_id = element.get("id")
        colour, source_structure = collapse_material_colour(element)
        source_type = element.get("type")
        if source_type == "blendbsdf":
            mapping = "weighted flat-colour approximation"
            limitation = "source blend is not preserved as a layered BSDF"
        else:
            mapping = "diffuse colour to zero-specular Principled"
            limitation = "none for the exported diffuse response"
        if material_id in {"mat-mat-transparent", "mat-mat-Red_Glass"}:
            limitation = "name implies transmission, but Blender export is diffuse"
        material_rows.append(
            {
                "material_id": material_id,
                "source_structure": source_structure,
                "shape_count": shape_counts[material_id],
                "mapped_base_r": float(colour[0]),
                "mapped_base_g": float(colour[1]),
                "mapped_base_b": float(colour[2]),
                "mapping": mapping,
                "limitation": limitation,
            }
        )

    reference_hash = file_sha256(reference_exr) if reference_exr else None
    reference_json = (
        json.loads(reference_metadata.read_text(encoding="utf-8"))
        if reference_metadata
        else None
    )
    recorded_hash = (
        reference_json.get("reference", {}).get("exr_sha256")
        if reference_json
        else None
    )
    reference_hash_matches = (
        reference_hash == recorded_hash
        if reference_hash is not None and recorded_hash is not None
        else None
    )

    manifest = {
        "scene": "Lego 856 Bulldozer",
        "shape_count": len(shape_elements),
        "unique_mesh_count": len(set(mesh_paths)),
        "missing_mesh_count": len(missing_meshes),
        "material_count": len(material_elements),
        "invalid_material_reference_count": len(invalid_refs),
        "environment_count": int(emitter is not None),
        "missing_environment_count": int(env_path is None or not env_path.exists()),
        "cycles_reference_present": reference_exr is not None,
        "cycles_reference_metadata_present": reference_metadata is not None,
        "cycles_reference_hash_matches_metadata": reference_hash_matches,
        "expected_shape_count": EXPECTED_SHAPES,
        "expected_material_count": EXPECTED_MATERIALS,
    }
    manifest["status"] = (
        "PASS"
        if manifest["shape_count"] == EXPECTED_SHAPES
        and manifest["material_count"] == EXPECTED_MATERIALS
        and manifest["missing_mesh_count"] == 0
        and manifest["invalid_material_reference_count"] == 0
        and manifest["missing_environment_count"] == 0
        else "FAIL"
    )
    return manifest, material_rows, colours, shape_elements


def primary_hit_mask(scene: mi.Scene) -> np.ndarray:
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
    return np.asarray(scene.ray_test(ray), dtype=bool).reshape(height, width)


def silhouette_metrics(reference: np.ndarray, reconstructed: np.ndarray) -> dict:
    intersection = np.logical_and(reference, reconstructed).sum()
    union = np.logical_or(reference, reconstructed).sum()
    differing = np.logical_xor(reference, reconstructed).sum()
    total = reference.size
    return {
        "reference_hit_pixels": int(reference.sum()),
        "reconstructed_hit_pixels": int(reconstructed.sum()),
        "intersection_pixels": int(intersection),
        "union_pixels": int(union),
        "iou": float(intersection / union) if union else 1.0,
        "pixel_agreement": float(1.0 - differing / total),
        "differing_pixels": int(differing),
    }


def resize_bilinear(image: np.ndarray, size: int) -> np.ndarray:
    height, width = image.shape[:2]
    if height == size and width == size:
        return image
    ys = np.linspace(0.0, height - 1.0, size)
    xs = np.linspace(0.0, width - 1.0, size)
    y0 = np.floor(ys).astype(np.int32)
    x0 = np.floor(xs).astype(np.int32)
    y1 = np.minimum(y0 + 1, height - 1)
    x1 = np.minimum(x0 + 1, width - 1)
    wy = (ys - y0)[:, None, None]
    wx = (xs - x0)[None, :, None]
    top = image[y0][:, x0] * (1.0 - wx) + image[y0][:, x1] * wx
    bottom = image[y1][:, x0] * (1.0 - wx) + image[y1][:, x1] * wx
    return (top * (1.0 - wy) + bottom * wy).astype(np.float32)


def render_rgb(scene: mi.Scene, spp: int, seed: int) -> np.ndarray:
    return np.asarray(mi.render(scene, spp=spp, seed=seed), dtype=np.float32)[..., :3]


def luminance(image: np.ndarray) -> np.ndarray:
    return (
        0.2126 * image[..., 0]
        + 0.7152 * image[..., 1]
        + 0.0722 * image[..., 2]
    )


def comparison_rows(
    comparison: str,
    reference: np.ndarray,
    candidate: np.ndarray,
    geometry_mask: np.ndarray,
) -> list[dict]:
    rows = []
    for region, mask in (
        ("full_frame", np.ones(reference.shape[:2], dtype=bool)),
        ("geometry", geometry_mask),
    ):
        difference = candidate[mask] - reference[mask]
        reference_luminance = luminance(reference)[mask]
        candidate_luminance = luminance(candidate)[mask]
        mean_reference = float(reference_luminance.mean())
        mean_candidate = float(candidate_luminance.mean())
        rows.append(
            {
                "comparison": comparison,
                "region": region,
                "pixel_count": int(mask.sum()),
                "mae": float(np.mean(np.abs(difference))),
                "rmse": float(np.sqrt(np.mean(difference * difference))),
                "max_abs_error": float(np.max(np.abs(difference))),
                "reference_mean_luminance": mean_reference,
                "candidate_mean_luminance": mean_candidate,
                "candidate_reference_luminance_ratio": (
                    float(mean_candidate / mean_reference)
                    if mean_reference != 0.0
                    else None
                ),
            }
        )
    return rows


def main() -> None:
    args = parse_args()
    if args.scene == "kitchen":
        run_kitchen(args)
        return
    reference_exr = args.cycles_reference
    if (
        reference_exr is None
        and not args.no_cycles_reference
        and REFERENCE_EXR.exists()
    ):
        reference_exr = REFERENCE_EXR
    if reference_exr is not None:
        reference_exr = reference_exr.expanduser().resolve()
        if not reference_exr.is_file():
            raise FileNotFoundError(f"Cycles reference not found: {reference_exr}")
    reference_metadata_path = args.reference_metadata
    if reference_metadata_path is None and REFERENCE_METADATA.exists():
        reference_metadata_path = REFERENCE_METADATA
    if reference_metadata_path is not None:
        reference_metadata_path = reference_metadata_path.expanduser().resolve()
        if not reference_metadata_path.is_file():
            raise FileNotFoundError(
                f"Reference metadata not found: {reference_metadata_path}"
            )
    output_root = args.output
    if output_root is None:
        output_root = DEFAULT_QUICK_OUTPUT if args.quick else DEFAULT_OUTPUT
    output = output_root / args.scene
    renders = output / "renders"
    figures = output / "figures"
    data = output / "data"
    for directory in (renders, figures, data):
        directory.mkdir(parents=True, exist_ok=True)

    resolution = args.resolution or (256 if args.quick else 1080)
    spp = args.spp or (16 if args.quick else 1024)
    silhouette_resolution = 128 if args.quick else 256

    print("[1/3] Asset and material manifest", flush=True)
    manifest, material_rows, colours, shape_elements = inspect_asset(
        reference_exr, reference_metadata_path
    )
    write_csv(data / "import_manifest.csv", [manifest])
    write_csv(data / "material_mapping.csv", material_rows)
    if manifest["status"] != "PASS":
        raise RuntimeError(f"Asset integrity failed: {manifest}")

    results: dict[str, object] = {"manifest": manifest}

    if args.only in {"all", "silhouette"}:
        print("[2/3] Geometry and camera silhouette control", flush=True)
        exported = load_exported_scene(silhouette_resolution, 1)
        camera_matrix = scalar_matrix(exported.sensors()[0].world_transform())
        environment_matrix = scalar_matrix(exported.environment().world_transform())
        reconstructed = reconstructed_scene(
            colours,
            shape_elements,
            camera_matrix,
            environment_matrix,
            "principled",
            silhouette_resolution,
            1,
        )
        silhouette = silhouette_metrics(
            primary_hit_mask(exported), primary_hit_mask(reconstructed)
        )
        silhouette["resolution"] = silhouette_resolution
        write_csv(data / "silhouette_reconstruction.csv", [silhouette])
        results["silhouette"] = silhouette

    if args.only in {"all", "renders"}:
        print("[3/3] Cycles, custom Principled, and diffuse control", flush=True)
        exported = load_exported_scene(resolution, spp)
        camera_matrix = scalar_matrix(exported.sensors()[0].world_transform())
        environment_matrix = scalar_matrix(exported.environment().world_transform())

        custom_scene = reconstructed_scene(
            colours,
            shape_elements,
            camera_matrix,
            environment_matrix,
            "principled",
            resolution,
            spp,
        )
        diffuse_scene = reconstructed_scene(
            colours,
            shape_elements,
            camera_matrix,
            environment_matrix,
            "diffuse",
            resolution,
            spp,
        )

        custom = render_rgb(custom_scene, spp, args.seed)
        diffuse = render_rgb(diffuse_scene, spp, args.seed)
        geometry_mask = primary_hit_mask(custom_scene)

        write_exr(renders / "custom_principled.exr", custom)
        write_exr(renders / "mitsuba_diffuse_control.exr", diffuse)
        write_png(figures / "custom_principled.png", custom)
        write_png(figures / "mitsuba_diffuse_control.png", diffuse)
        metric_rows = comparison_rows(
            "mitsuba_diffuse_vs_custom_principled",
            diffuse,
            custom,
            geometry_mask,
        )
        if reference_exr is not None:
            cycles_full = np.asarray(
                mi.Bitmap(str(reference_exr)), dtype=np.float32
            )[..., :3]
            cycles = resize_bilinear(cycles_full, resolution)
            write_png(figures / "cycles_reference.png", cycles)
            write_png(
                figures / "cycles_vs_custom.png",
                np.concatenate([cycles, custom], axis=1),
            )
            metric_rows = comparison_rows(
                "cycles_reference_vs_custom_principled",
                cycles,
                custom,
                geometry_mask,
            ) + metric_rows
            results["reference_resampled"] = cycles_full.shape[0] != resolution
        else:
            print(
                "  Cycles comparison skipped: no external reference EXR supplied.",
                flush=True,
            )
        write_csv(data / "image_metrics.csv", metric_rows)
        results["image_metrics"] = metric_rows
        results["cycles_comparison"] = (
            "completed" if reference_exr is not None else "skipped_missing_reference"
        )

    reference_json = (
        json.loads(reference_metadata_path.read_text(encoding="utf-8"))
        if reference_metadata_path
        else None
    )
    metadata = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Canonical imported-scene evaluation for thesis Section 5.5.1",
        "scene": args.scene,
        "selected_group": args.only,
        "quick": args.quick,
        "settings": {
            "resolution": resolution,
            "spp": spp,
            "seed": args.seed,
            "max_depth": 8,
            "rr_depth": 3,
            "sampler": "independent",
            "reconstruction_filter": "Gaussian stddev 0.5",
            "firefly_clamp": 0.0,
        },
        "backend": "llvm_ad_rgb",
        "hardware": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "asset": {
            "directory": str(ASSET_DIR.relative_to(ROOT)),
            "xml_sha256": file_sha256(XML_PATH),
            "blend_sha256": file_sha256(BLEND_PATH),
            "environment_sha256": file_sha256(
                ASSET_DIR / "textures" / "_unnamed_6.hdr"
            ),
            "cycles_reference_path": str(reference_exr) if reference_exr else None,
            "cycles_reference_sha256": (
                file_sha256(reference_exr) if reference_exr else None
            ),
            "cycles_reference_metadata": reference_json,
        },
        "results": results,
        "script_sha256": file_sha256(SCRIPT_PATH),
        **git_metadata(),
    }
    metadata_name = (
        "metadata.json" if args.only == "all" else f"metadata_{args.only}.json"
    )
    (output / metadata_name).write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {output / metadata_name}", flush=True)


if __name__ == "__main__":
    main()
