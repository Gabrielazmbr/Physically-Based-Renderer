"""Shared thin-sheet and solid-glass glazing demonstration scene."""

from pathlib import Path

import mitsuba as mi


HDRI = Path(__file__).resolve().parents[1] / "hdri" / "studio_kontrast_04_1k.exr"


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


GLAZING_CONFIGURATIONS = [
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


def glazing_window_transform() -> mi.ScalarTransform4f:
    return mi.ScalarTransform4f().rotate([0, 1, 0], -18)


def add_glazing_frame(scene: dict) -> None:
    transform = glazing_window_transform()
    wall_material = {"type": "diffuse", "reflectance": rgb([0.16, 0.17, 0.19])}
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


def glazing_scene(configuration: dict, size: int, spp: int) -> dict:
    scene = {
        "type": "scene",
        "integrator": {"type": "path_tracer", "max_depth": 16, "rr_depth": 4},
        "sensor": {
            "type": "perspective",
            "fov": 44,
            "fov_axis": "x",
            "to_world": mi.ScalarTransform4f().look_at(
                origin=[3.2, 0.7, 6.5], target=[0, 0, -1.35], up=[0, 1, 0]
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
        "target": {
            "type": "rectangle",
            "to_world": glazing_window_transform()
            @ mi.ScalarTransform4f().translate([-1.5, 0, -3.1]).scale([4.0, 2.20, 1]),
            "bsdf": {
                "type": "diffuse",
                "reflectance": checker(
                    [0.035, 0.045, 0.065], [0.82, 0.86, 0.92], 18
                ),
            },
        },
    }
    for name, position, radius, colour in [
        ("red_marker", [-1.95, -0.42, -2.65], 0.25, [0.72, 0.025, 0.02]),
        ("green_marker", [-1.20, 0.38, -2.58], 0.22, [0.025, 0.62, 0.12]),
        ("blue_marker", [-0.42, -0.18, -2.55], 0.28, [0.025, 0.12, 0.75]),
    ]:
        scene[name] = {
            "type": "sphere",
            "to_world": glazing_window_transform()
            @ mi.ScalarTransform4f().translate(position).scale(radius),
            "bsdf": {"type": "diffuse", "reflectance": rgb(colour)},
        }
    add_glazing_frame(scene)
    if configuration["id"] == "thin_sheet":
        scene["glazing"] = {
            "type": "rectangle",
            "to_world": glazing_window_transform()
            @ mi.ScalarTransform4f().scale([1.80, 1.40, 1]),
            "bsdf": principled(
                base_colour=[0.92, 0.98, 1.0], transmission=1.0, ior=1.5, thin=True
            ),
        }
    elif configuration["id"] == "solid_slab":
        scene["glazing"] = {
            "type": "cube",
            "to_world": glazing_window_transform()
            @ mi.ScalarTransform4f().scale([1.80, 1.40, 0.12]),
            "bsdf": principled(
                base_colour=[0.92, 0.98, 1.0], transmission=1.0, ior=1.5, thin=False
            ),
        }
    return scene


GLAZING_MODES = {
    "open": "open_aperture",
    "thin": "thin_sheet",
    "solid": "solid_slab",
}


def glazing_configuration(mode: str) -> dict:
    """Resolve a short CLI mode to its documented glazing configuration."""
    configuration_id = GLAZING_MODES[mode]
    return next(item for item in GLAZING_CONFIGURATIONS if item["id"] == configuration_id)


def glazing_scene_for_mode(
    mode: str = "solid",
    size: int = 700,
    spp: int = 1024,
) -> dict:
    return glazing_scene(glazing_configuration(mode), size, spp)

