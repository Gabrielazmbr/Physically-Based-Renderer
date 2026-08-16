"""Shared 18-material Principled BSDF capability gallery."""

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


MATERIALS = [
    {
        "id": "matte_diffuse",
        "group": "Base mixture",
        "title": "Matte diffuse",
        "subtitle": "specular 0",
        "bsdf": principled(
            base_colour=[0.78, 0.20, 0.055], roughness=0.8,
            metallic=0.0, specular=0.0,
        ),
    },
    {
        "id": "dielectric_plastic",
        "group": "Base mixture",
        "title": "Dielectric plastic",
        "subtitle": "specular 0.5",
        "bsdf": principled(
            base_colour=[0.045, 0.20, 0.72], roughness=0.22,
            metallic=0.0, specular=0.5,
        ),
    },
    {
        "id": "high_specular",
        "group": "Base mixture",
        "title": "High specular",
        "subtitle": "specular 1.0",
        "bsdf": principled(
            base_colour=[0.045, 0.20, 0.72], roughness=0.22,
            metallic=0.0, specular=1.0,
        ),
    },
    {
        "id": "metallic_blend",
        "group": "Base mixture",
        "title": "Metallic blend",
        "subtitle": "metallic 0.5",
        "bsdf": principled(
            base_colour=[0.95, 0.58, 0.12], roughness=0.25,
            metallic=0.5, specular=0.5,
        ),
    },
    {
        "id": "rough_metal",
        "group": "Base mixture",
        "title": "Rough metal",
        "subtitle": "roughness 0.55",
        "bsdf": principled(
            base_colour=[0.95, 0.58, 0.12], roughness=0.55,
            metallic=1.0,
        ),
    },
    {
        "id": "polished_metal",
        "group": "Base mixture",
        "title": "Polished metal",
        "subtitle": "roughness 0.08",
        "bsdf": principled(
            base_colour=[0.95, 0.58, 0.12], roughness=0.08,
            metallic=1.0,
        ),
    },
    {
        "id": "isotropic_control",
        "group": "Additional lobes",
        "title": "Isotropic control",
        "subtitle": "anisotropic 0",
        "bsdf": principled(
            base_colour=[0.72, 0.76, 0.82], roughness=0.25,
            metallic=1.0, anisotropic=0.0,
        ),
    },
    {
        "id": "anisotropic_05",
        "group": "Additional lobes",
        "title": "Medium anisotropy",
        "subtitle": "anisotropic 0.5",
        "bsdf": principled(
            base_colour=[0.72, 0.76, 0.82], roughness=0.25,
            metallic=1.0, anisotropic=0.5,
        ),
    },
    {
        "id": "anisotropic_09",
        "group": "Additional lobes",
        "title": "Strong anisotropy",
        "subtitle": "anisotropic 0.9",
        "bsdf": principled(
            base_colour=[0.72, 0.76, 0.82], roughness=0.25,
            metallic=1.0, anisotropic=0.9,
        ),
    },
    {
        "id": "clearcoat_off",
        "group": "Additional lobes",
        "title": "Clearcoat control",
        "subtitle": "clearcoat 0",
        "bsdf": principled(
            base_colour=[0.32, 0.018, 0.025], roughness=0.75,
            metallic=0.0, specular=0.0, clearcoat=0.0,
        ),
    },
    {
        "id": "soft_clearcoat",
        "group": "Additional lobes",
        "title": "Soft clearcoat",
        "subtitle": "coat gloss 0",
        "bsdf": principled(
            base_colour=[0.32, 0.018, 0.025], roughness=0.75,
            metallic=0.0, specular=0.0, clearcoat=1.0,
            clearcoat_gloss=0.0,
        ),
    },
    {
        "id": "sharp_clearcoat",
        "group": "Additional lobes",
        "title": "Sharp clearcoat",
        "subtitle": "coat gloss 1",
        "bsdf": principled(
            base_colour=[0.32, 0.018, 0.025], roughness=0.75,
            metallic=0.0, specular=0.0, clearcoat=1.0,
            clearcoat_gloss=1.0,
        ),
    },
    {
        "id": "opaque_control",
        "group": "Models and interfaces",
        "title": "Opaque control",
        "subtitle": "transmission 0",
        "bsdf": principled(
            base_colour=[0.045, 0.52, 0.28], roughness=0.28,
            metallic=0.0, specular=0.5, transmission=0.0,
        ),
    },
    {
        "id": "partial_transmission",
        "group": "Models and interfaces",
        "title": "Partial transmission",
        "subtitle": "transmission 0.5",
        "bsdf": principled(
            base_colour=[0.045, 0.52, 0.28], roughness=0.28,
            metallic=0.0, specular=0.5, transmission=0.5,
            ior=1.5,
        ),
    },
    {
        "id": "colour_texture",
        "group": "Models and interfaces",
        "title": "Colour texture",
        "subtitle": "UV checker",
        "bsdf": principled(
            base_colour=checker([0.025, 0.12, 0.52], [0.95, 0.32, 0.035], 6),
            roughness=0.35, metallic=0.0, specular=0.5,
        ),
    },
    {
        "id": "roughness_texture",
        "group": "Models and interfaces",
        "title": "Roughness texture",
        "subtitle": "0.08 / 0.75",
        "bsdf": principled(
            base_colour=[0.68, 0.72, 0.78],
            roughness=checker([0.08, 0.08, 0.08], [0.75, 0.75, 0.75], 6),
            metallic=1.0,
        ),
    },
    {
        "id": "glass_ior_15",
        "group": "Models and interfaces",
        "title": "Solid glass",
        "subtitle": "IOR 1.5",
        "bsdf": principled(
            base_colour=[0.92, 0.98, 1.0], transmission=1.0,
            ior=1.5,
        ),
    },
    {
        "id": "glass_ior_24",
        "group": "Models and interfaces",
        "title": "High-IOR glass",
        "subtitle": "IOR 2.4",
        "bsdf": principled(
            base_colour=[0.90, 0.97, 1.0], transmission=1.0,
            ior=2.4,
        ),
    },
]


X_POSITIONS = [-4.5, -2.7, -0.9, 0.9, 2.7, 4.5]
Y_POSITIONS = [2.25, 0.0, -2.25]


def material_test_scene(
    width: int = 1600,
    height: int = 900,
    spp: int = 1024,
    firefly_clamp: float = 0.0,
) -> dict:
    scene = {
        "type": "scene",
        "integrator": {
            "type": "path_tracer",
            "max_depth": 12,
            "rr_depth": 3,
            "firefly_clamp": firefly_clamp,
        },
        "sensor": {
            "type": "perspective",
            "fov": 54,
            "fov_axis": "x",
            "to_world": mi.ScalarTransform4f().look_at(
                origin=[0, 0.15, 13.0], target=[0, 0, 0], up=[0, 1, 0]
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
        # Standard emitter by design: this test isolates the custom BSDF.
        "environment": {
            "type": "envmap",
            "filename": str(HDRI),
            "scale": 0.55,
            "to_world": mi.ScalarTransform4f().rotate([0, 1, 0], 28),
        },
        "backdrop": {
            "type": "rectangle",
            "to_world": mi.ScalarTransform4f()
            .translate([0, 0, -1.30])
            .scale([6.3, 3.75, 1]),
            "bsdf": {
                "type": "diffuse",
                "reflectance": rgb([0.105, 0.11, 0.12]),
            },
        },
        # Large and narrow sources create readable broad and strip highlights.
        "key": {
            "type": "rectangle",
            "to_world": mi.ScalarTransform4f().look_at(
                origin=[-3.8, 5.8, 5.0], target=[0, 0, 0], up=[0, 1, 0]
            ).scale([2.1, 1.0, 1]),
            "emitter": {"type": "area", "radiance": rgb([15.0, 14.5, 13.5])},
        },
        "strip": {
            "type": "rectangle",
            "to_world": mi.ScalarTransform4f().look_at(
                origin=[5.5, 1.3, 4.0], target=[0, 0, 0], up=[0, 1, 0]
            ).scale([0.45, 2.2, 1]),
            "emitter": {"type": "area", "radiance": rgb([10.0, 11.0, 13.0])},
        },
    }

    # Matched checker cards make partial transmission and IOR-dependent
    # refraction legible without changing the material parameters themselves.
    for index, x in enumerate((-4.5, -2.7, 2.7, 4.5)):
        scene[f"glass_target_{index}"] = {
            "type": "rectangle",
            "to_world": mi.ScalarTransform4f()
            .translate([x, Y_POSITIONS[2], -1.22])
            .scale([0.82, 0.82, 1]),
            "bsdf": {
                "type": "diffuse",
                "reflectance": checker(
                    [0.025, 0.035, 0.055], [0.78, 0.82, 0.88], 5
                ),
            },
        }

    for index, material in enumerate(MATERIALS):
        row, column = divmod(index, 6)
        x, y = X_POSITIONS[column], Y_POSITIONS[row]
        scene[material["id"]] = {
            "type": "sphere",
            "center": [x, y, 0],
            "radius": 0.68,
            "bsdf": material["bsdf"],
        }
    return scene


def material_catalogue() -> list[dict]:
    """Return JSON-safe names and parameters for render metadata."""
    return [
        {
            "id": item["id"],
            "group": item["group"],
            "title": item["title"],
            "subtitle": item["subtitle"],
            "bsdf_parameters": json_safe(item["bsdf"]),
        }
        for item in MATERIALS
    ]


def json_safe(value):
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
