#!/usr/bin/env python3
"""Evaluator-friendly command line entry point for the renderer."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
KITCHEN_DIR = ROOT / "assets" / "production_scenes" / "kitchen_scene"
KITCHEN_XML = KITCHEN_DIR / "scene.xml"

SCENES = {
    "cornell": "Cornell box: global illumination and colour bleeding",
    "materials": "Eighteen-material Principled BSDF capability gallery",
    "glazing": "Thin-sheet and finite-thickness glass demonstration",
    "dof": "Physical-camera depth-of-field demonstration",
    "bokeh": "Physical-camera aperture-shape demonstration with bright points",
    "environment": "Metal sphere lit by a sampled HDR environment",
    "lego": "Blender-authored LEGO Bulldozer reconstructed with the custom plugins",
    "kitchen": "Country Kitchen production scene (six camera views)",
}

KITCHEN_VIEWS = {
    "hero": 0,
    "stove": 1,
    "table": 2,
    "radio": 3,
    "towel": 4,
    "island": 5,
}

SCENE_ASPECTS = {
    "cornell": 1.0,
    "materials": 16.0 / 9.0,
    "glazing": 1.0,
    "dof": 2.0,
    "bokeh": 1.0,
    "environment": 1.0,
    "lego": 1.0,
    "kitchen": 16.0 / 9.0,
}

# The default render is deliberately inexpensive. Individual settings remain
# overridable so a command is an exact record of a controlled render.
QUALITY_PRESETS = {
    "draft": {"width": 320, "height": 180, "spp": 4, "passes": 1},
    "preview": {"width": 640, "height": 360, "spp": 16, "passes": 1},
    "final": {"width": 1280, "height": 720, "spp": 256, "passes": 4},
}


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def nonnegative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        description="Render demonstration and production scenes with the custom plugins."
    )
    cli.add_argument(
        "--variant",
        default="llvm_ad_rgb",
        choices=("llvm_ad_rgb", "cuda_ad_rgb"),
        help="Mitsuba execution backend (default: CPU).",
    )
    commands = cli.add_subparsers(dest="command")

    commands.add_parser("list-scenes", help="Show the available render scenes.")
    commands.add_parser(
        "doctor", help="Check the environment and required evaluator assets."
    )

    render = commands.add_parser("render", help="Render one scene.")
    render.add_argument("scene", choices=SCENES)
    render.add_argument(
        "--quality", choices=QUALITY_PRESETS, default="draft",
        help="Base resolution, samples and pass count (default: draft).",
    )
    render.add_argument(
        "--view", choices=KITCHEN_VIEWS, default="hero",
        help="Named camera for the kitchen scene.",
    )
    render.add_argument(
        "--glazing-mode",
        choices=("open", "thin", "solid"),
        default="solid",
        help=(
            "Glazing configuration: no interface, thin sheet, or solid slab "
            "(default: solid)."
        ),
    )
    render.add_argument("--width", type=positive_int)
    render.add_argument("--height", type=positive_int)
    render.add_argument("--spp", type=positive_int, help="Samples per pixel per pass.")
    render.add_argument("--passes", type=positive_int)
    render.add_argument("--seed", type=nonnegative_int, default=0)
    render.add_argument("--max-depth", type=positive_int)
    render.add_argument("--rr-depth", type=positive_int)
    render.add_argument(
        "--sampler", choices=("independent", "stratified"),
        help="Override the scene sampler.",
    )
    render.add_argument(
        "--integrator",
        choices=("custom", "mitsuba-path", "mitsuba"),
        default="custom",
        help=(
            "Select the path integrator only: custom or Mitsuba path. The "
            "scene's BSDF, camera, emitter and sampler are otherwise unchanged. "
            "'mitsuba' is retained as an alias for 'mitsuba-path'."
        ),
    )
    render.add_argument("--firefly-clamp", type=nonnegative_float)
    render.add_argument("--transparent-shadows", action="store_true")
    render.add_argument("--envmap-scale", type=nonnegative_float)
    render.add_argument("--aperture-radius", type=nonnegative_float)
    render.add_argument("--focus-distance", type=positive_float)
    render.add_argument("--aperture-blades", type=nonnegative_int)
    output_mode = render.add_mutually_exclusive_group()
    output_mode.add_argument(
        "--aovs", action="store_true",
        help="Write beauty, albedo, normal and depth channels to an EXR.",
    )
    output_mode.add_argument(
        "--denoise", action="store_true",
        help=(
            "Denoise the custom integrator's beauty output with OIDN, using "
            "automatically rendered albedo and shading-normal AOVs."
        ),
    )
    render.add_argument(
        "--output", type=Path,
        help="Output image path (default: outputs/renders/<descriptive name>.png).",
    )
    render.add_argument(
        "--dry-run", action="store_true",
        help="Print the resolved settings without loading or rendering the scene.",
    )
    return cli


def resolved_settings(args: argparse.Namespace) -> dict:
    settings = dict(QUALITY_PRESETS[args.quality])
    for name in ("spp", "passes"):
        value = getattr(args, name)
        if value is not None:
            settings[name] = value
    aspect = SCENE_ASPECTS[args.scene]
    if args.width is None and args.height is None:
        settings["width"] = round(settings["height"] * aspect)
    elif args.width is None:
        settings["height"] = args.height
        settings["width"] = round(args.height * aspect)
    elif args.height is None:
        settings["width"] = args.width
        settings["height"] = round(args.width / aspect)
    else:
        settings["width"] = args.width
        settings["height"] = args.height
    settings.update(
        {
            "scene": args.scene,
            "view": args.view if args.scene == "kitchen" else None,
            "glazing_mode": args.glazing_mode if args.scene == "glazing" else None,
            "sensor": KITCHEN_VIEWS[args.view] if args.scene == "kitchen" else 0,
            "quality": args.quality,
            "seed": args.seed,
            "variant": args.variant,
            "integrator": (
                "mitsuba-path" if args.integrator == "mitsuba" else args.integrator
            ),
            "comparison_scope": (
                "path_integrator_only"
                if args.integrator in {"mitsuba", "mitsuba-path"}
                else None
            ),
            "max_depth": args.max_depth,
            "rr_depth": args.rr_depth,
            "sampler": args.sampler,
            "firefly_clamp": args.firefly_clamp,
            "transparent_shadows": args.transparent_shadows,
            "envmap_scale": args.envmap_scale,
            "aperture_radius": args.aperture_radius,
            "focus_distance": args.focus_distance,
            "aperture_blades": args.aperture_blades,
            "aovs": args.aovs,
            "denoise": args.denoise,
            "render_aovs": args.aovs or args.denoise,
        }
    )
    return settings


def output_path(args: argparse.Namespace, settings: dict) -> Path:
    if args.output:
        path = args.output.expanduser()
        if not path.is_absolute():
            path = ROOT / path
    else:
        view = f"_{settings['view']}" if settings["view"] else ""
        glazing = (
            f"_{settings['glazing_mode']}"
            if settings["glazing_mode"] is not None
            else ""
        )
        extension = ".exr" if settings["aovs"] else ".png"
        denoised = "_denoised" if settings["denoise"] else ""
        filename = (
            f"{settings['scene']}{view}{glazing}_{settings['quality']}"
            f"{denoised}{extension}"
        )
        path = ROOT / "outputs" / "renders" / filename
    if settings["aovs"] and path.suffix.lower() != ".exr":
        path = path.with_suffix(".exr")
    if not settings["aovs"] and path.suffix.lower() not in {".png", ".exr"}:
        raise ValueError("output must end in .png or .exr")
    return path.resolve()


def configure_mitsuba(variant: str):
    import mitsuba as mi

    mi.set_variant(variant)
    from bsdfs.principled import PrincipledBSDF
    from cameras.physical_camera import PhysicalCamera
    from emitters.envmap import CustomEnvmap
    from integrators.path_tracer import PathTracer

    mi.register_bsdf("principled_bsdf", lambda props: PrincipledBSDF(props))
    mi.register_sensor("physical_camera", lambda props: PhysicalCamera(props))
    mi.register_emitter("custom_envmap", lambda props: CustomEnvmap(props))
    mi.register_integrator("path_tracer", lambda props: PathTracer(props))
    return mi


def builtin_scene_dict(name: str, settings: dict) -> dict:
    if name == "cornell":
        from assets.scenes.cornell_box import cornell_box_scene

        return cornell_box_scene()
    if name == "materials":
        from assets.scenes.material_test import material_test_scene

        return material_test_scene()
    if name == "glazing":
        from assets.scenes.glazing import glazing_scene_for_mode

        return glazing_scene_for_mode(settings["glazing_mode"])
    if name == "dof":
        from assets.scenes.depth_of_field import depth_of_field_scene

        return depth_of_field_scene()
    if name == "bokeh":
        from assets.scenes.bokeh import bokeh_scene

        return bokeh_scene()
    if name == "environment":
        from assets.scenes.environment_lighting import environment_lighting_scene

        hdri = ROOT / "assets" / "hdri" / "sundowner_overlook_1k.exr"
        return environment_lighting_scene(str(hdri))
    if name == "lego":
        from assets.production_scenes.lego_bulldozer.scene import lego_scene_dict

        return lego_scene_dict()
    raise ValueError(f"{name!r} is not a built-in scene")


def apply_dict_settings(scene: dict, settings: dict) -> None:
    scene["integrator"]["type"] = (
        "path_tracer" if settings["integrator"] == "custom" else "path"
    )
    if settings["integrator"] == "mitsuba-path":
        for custom_property in (
            "with_aovs",
            "firefly_clamp",
            "transparent_shadows",
            "max_transparent_shadow_depth",
            "hide_from_camera",
            "opaque_shadow_shapes",
        ):
            scene["integrator"].pop(custom_property, None)
    for name in ("max_depth", "rr_depth"):
        if settings[name] is not None:
            scene["integrator"][name] = settings[name]
    if settings["firefly_clamp"] is not None and settings["integrator"] == "custom":
        scene["integrator"]["firefly_clamp"] = settings["firefly_clamp"]
    if settings["transparent_shadows"] and settings["integrator"] == "custom":
        scene["integrator"]["transparent_shadows"] = True
    if settings["render_aovs"] and settings["integrator"] == "custom":
        scene["integrator"]["with_aovs"] = True

    sensor = scene["sensor"]
    sensor["film"]["width"] = settings["width"]
    sensor["film"]["height"] = settings["height"]
    sensor.setdefault("sampler", {})["sample_count"] = settings["spp"]
    if settings["sampler"]:
        sensor["sampler"]["type"] = settings["sampler"]
    for name in ("aperture_radius", "focus_distance", "aperture_blades"):
        if settings[name] is not None:
            sensor[name] = settings[name]
    if settings["envmap_scale"] is not None:
        for value in scene.values():
            if isinstance(value, dict) and value.get("type") == "custom_envmap":
                value["scale"] = settings["envmap_scale"]


@contextmanager
def working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def load_scene(mi, settings: dict):
    if settings["scene"] != "kitchen":
        scene_dict = builtin_scene_dict(settings["scene"], settings)
        apply_dict_settings(scene_dict, settings)
        return mi.load_dict(scene_dict)

    substitutions = {
        "integrator": "path_tracer" if settings["integrator"] == "custom" else "path",
        "resx": str(settings["width"]),
        "resy": str(settings["height"]),
        "spp": str(settings["spp"]),
        "with_aovs": "true" if settings["render_aovs"] else "false",
        "transparent_shadows": "true" if settings["transparent_shadows"] else "false",
    }
    optional = {
        "max_depth": settings["max_depth"],
        "rr_depth": settings["rr_depth"],
        "sampler": settings["sampler"],
        "firefly_clamp": settings["firefly_clamp"],
        "envmap_scale": settings["envmap_scale"],
        "aperture_radius": settings["aperture_radius"],
        "focus_distance": settings["focus_distance"],
        "aperture_blades": settings["aperture_blades"],
    }
    substitutions.update(
        {name: str(value) for name, value in optional.items() if value is not None}
    )
    with working_directory(KITCHEN_DIR):
        if settings["integrator"] == "custom":
            return mi.load_file(str(KITCHEN_XML), **substitutions)

        # The production XML exposes custom-integrator properties. Mitsuba's
        # reference path tracer correctly rejects those unknown properties, so
        # retain only its two shared path-depth controls for this comparison.
        root = ET.parse(KITCHEN_XML).getroot()
        integrator = root.find("integrator")
        if integrator is None:
            raise RuntimeError("Kitchen scene has no integrator element")
        for child in list(integrator):
            if child.get("name") not in {"max_depth", "rr_depth"}:
                integrator.remove(child)
        xml = ET.tostring(root, encoding="unicode")
        substitutions.pop("with_aovs")
        substitutions.pop("transparent_shadows")
        return mi.load_string(xml, **substitutions)


def git_state() -> dict:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        )
        return {"commit": commit, "dirty_worktree": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty_worktree": None}


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def valid_stratified_count(spp: int) -> bool:
    root = int(spp**0.5)
    return root * root == spp and root > 0 and (root & (root - 1)) == 0


def render(args: argparse.Namespace) -> int:
    settings = resolved_settings(args)
    if settings["integrator"] == "mitsuba-path":
        print(
            "NOTE: integrator-only comparison. Mitsuba's path tracer is used "
            "with the same scene components. This does not compare the custom "
            "Principled BSDF with a Mitsuba equivalent.",
            file=sys.stderr,
        )
    if settings["aovs"] and settings["integrator"] != "custom":
        print("error: --aovs is available only with --integrator custom", file=sys.stderr)
        return 2
    if settings["denoise"] and settings["integrator"] != "custom":
        print(
            "error: --denoise is available only with --integrator custom",
            file=sys.stderr,
        )
        return 2
    sampler = settings["sampler"] or (
        "stratified"
        if settings["scene"] in {"materials", "glazing", "kitchen"}
        else "independent"
    )
    if sampler == "stratified" and not valid_stratified_count(settings["spp"]):
        print(
            "error: stratified sampling requires spp in 1, 4, 16, 64, 256, ...",
            file=sys.stderr,
        )
        return 2
    destination = output_path(args, settings)
    print(json.dumps({"output": str(destination), **settings}, indent=2))
    if args.dry_run:
        return 0

    mi = configure_mitsuba(settings["variant"])
    started = time.perf_counter()
    scene = load_scene(mi, settings)
    accumulation = None
    for index in range(settings["passes"]):
        seed = settings["seed"] + index
        image = mi.render(
            scene, spp=settings["spp"], sensor=settings["sensor"], seed=seed
        )
        import numpy as np

        array = np.asarray(image, dtype=np.float32)
        accumulation = array if accumulation is None else accumulation + array
        print(f"pass {index + 1}/{settings['passes']} complete (seed={seed})", flush=True)
    result = accumulation / settings["passes"]
    denoising = {"enabled": False}
    if settings["denoise"]:
        if result.shape[-1] < 9:
            raise RuntimeError(
                "denoising requires beauty, albedo and shading-normal AOVs; "
                f"the renderer returned {result.shape[-1]} channels"
            )
        from denoisers.oidn import denoise_composite_aov_render

        result = denoise_composite_aov_render(result, hdr=True)
        denoising = {
            "enabled": True,
            "denoiser": "Intel Open Image Denoise (OIDN)",
            "input_aovs": ["beauty", "albedo", "shading_normal"],
            "emitter_masking": True,
        }
    destination.parent.mkdir(parents=True, exist_ok=True)
    mi.util.write_bitmap(str(destination), result)

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "image": display_path(destination),
        "settings": settings,
        "effective_spp": settings["spp"] * settings["passes"],
        "denoising": denoising,
        "elapsed_seconds": time.perf_counter() - started,
        "software": {
            "python": platform.python_version(),
            "mitsuba": mi.__version__,
            "variant": mi.variant(),
        },
        "git": git_state(),
    }
    if settings["scene"] == "materials":
        from assets.scenes.material_test import material_catalogue

        metadata["material_catalogue"] = material_catalogue()
    if settings["scene"] == "glazing":
        from assets.scenes.glazing import glazing_configuration

        metadata["glazing_configuration"] = glazing_configuration(
            settings["glazing_mode"]
        )
    metadata_path = destination.with_suffix(destination.suffix + ".json")
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {destination}")
    print(f"wrote {metadata_path}")
    return 0


def doctor(variant: str) -> int:
    checks: list[tuple[str, bool, str]] = []
    kitchen_models = list((KITCHEN_DIR / "models").glob("*.obj"))
    kitchen_textures = [
        path for path in (KITCHEN_DIR / "textures").glob("*.*")
        if path.name != ".DS_Store"
    ]
    hdris = list((ROOT / "assets" / "hdri").glob("*.exr"))
    lego_dir = ROOT / "assets" / "production_scenes" / "lego_bulldozer"
    lego_meshes = list((lego_dir / "meshes").glob("*.ply"))
    lego_environments = list((lego_dir / "textures").glob("*.hdr"))
    checks.append(("Python 3.13+", sys.version_info >= (3, 13), platform.python_version()))
    checks.append(("Git LFS", shutil.which("git-lfs") is not None, "required for source assets"))
    checks.append(("Kitchen XML", KITCHEN_XML.is_file(), str(KITCHEN_XML.relative_to(ROOT))))
    checks.append(("Kitchen models", len(kitchen_models) == 295, f"{len(kitchen_models)}/295 OBJ files"))
    checks.append(("Kitchen textures", len(kitchen_textures) == 11, f"{len(kitchen_textures)}/11 image files"))
    checks.append(("Lego meshes", len(lego_meshes) == 439, f"{len(lego_meshes)}/439 PLY files"))
    checks.append(("Lego environment", len(lego_environments) == 1, f"{len(lego_environments)}/1 HDR file"))
    checks.append(("HDR environments", len(hdris) == 4, f"{len(hdris)}/4 EXR files"))

    lfs_assets = [
        *kitchen_models,
        *kitchen_textures,
        *hdris,
        *lego_meshes,
        *lego_environments,
        *list((ROOT / "assets" / "production_scenes").glob("**/*.blend")),
    ]
    pointers = []
    for path in lfs_assets:
        try:
            with path.open("rb") as handle:
                header = handle.read(80)
            if header.startswith(b"version https://git-lfs.github.com/spec"):
                pointers.append(path)
        except OSError:
            pointers.append(path)
    checks.append(
        (
            "LFS content",
            not pointers,
            "all source assets materialized" if not pointers else f"{len(pointers)} pointer files; run git lfs pull",
        )
    )
    try:
        mi = configure_mitsuba(variant)
        import numpy
        import pyoidn  # noqa: F401

        detail = f"Mitsuba {mi.__version__}, NumPy {numpy.__version__}, pyoidn available"
        checks.append(("Python dependencies", True, detail))
    except Exception as exc:
        checks.append(("Python dependencies", False, str(exc)))

    print("Repository preflight")
    for label, passed, detail in checks:
        print(f"  {'PASS' if passed else 'FAIL':4}  {label}: {detail}")
    passed = all(item[1] for item in checks)
    print("\nReady to render." if passed else "\nPreflight failed; see the checks above.")
    return 0 if passed else 1


def main() -> int:
    cli = parser()
    args = cli.parse_args()
    if args.command is None:
        cli.print_help()
        return 0
    if args.command == "list-scenes":
        for name, description in SCENES.items():
            suffix = f"; views: {', '.join(KITCHEN_VIEWS)}" if name == "kitchen" else ""
            print(f"{name:12} {description}{suffix}")
        return 0
    if args.command == "doctor":
        return doctor(args.variant)
    if args.command == "render":
        return render(args)
    cli.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
