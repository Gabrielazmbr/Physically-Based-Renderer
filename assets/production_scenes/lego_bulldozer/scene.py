"""Reusable reconstruction of the Blender-authored LEGO production scene.

The exported XML remains the source of geometry, material colours, camera, and
environment transforms. This module maps that description to the custom plugin
pipeline used by both ``main.py`` and the Section 5.5 integration evaluator.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import mitsuba as mi
import numpy as np


ASSET_DIR = Path(__file__).resolve().parent
XML_PATH = ASSET_DIR / "scene_export.xml"
DEFAULT_ROUGHNESS = 0.4


def rgb_from_element(element: ET.Element) -> np.ndarray:
    rgb = element.find("rgb")
    if rgb is None:
        raise ValueError(f"No RGB value found in material element {element.attrib}")
    return np.array([float(value) for value in rgb.get("value").split()])


def collapse_material_colour(element: ET.Element) -> tuple[np.ndarray, str]:
    """Reduce the exported diffuse/blended material to one linear RGB value."""
    material_type = element.get("type")
    if material_type == "twosided":
        child = element.find("bsdf")
        if child is None:
            raise ValueError("twosided material has no nested BSDF")
        colour, nested_type = collapse_material_colour(child)
        return colour, f"twosided/{nested_type}"
    if material_type == "diffuse":
        return rgb_from_element(element), "diffuse"
    if material_type == "blendbsdf":
        weight_element = element.find("float[@name='weight']")
        first = element.find("bsdf[@name='bsdf1']")
        second = element.find("bsdf[@name='bsdf2']")
        if weight_element is None or first is None or second is None:
            raise ValueError("blendbsdf is missing its weight or child BSDFs")
        weight = float(weight_element.get("value"))
        colour_a, type_a = collapse_material_colour(first)
        colour_b, type_b = collapse_material_colour(second)
        colour = weight * colour_a + (1.0 - weight) * colour_b
        return colour, f"blendbsdf({type_a},{type_b})"
    raise ValueError(f"Unsupported exported material type: {material_type}")


def load_description() -> tuple[
    list[ET.Element], list[ET.Element], dict[str, np.ndarray]
]:
    root = ET.parse(XML_PATH).getroot()
    material_elements = root.findall("bsdf")
    shape_elements = root.findall("shape")
    colours = {
        element.get("id"): collapse_material_colour(element)[0]
        for element in material_elements
    }
    return material_elements, shape_elements, colours


def scalar_matrix(transform: mi.Transform4f) -> list[list[float]]:
    matrix = transform.matrix
    return [[float(matrix[i][j][0]) for j in range(4)] for i in range(4)]


def load_exported_scene(resolution: int, spp: int) -> mi.Scene:
    """Load the source export to resolve its authored transforms exactly."""
    return mi.load_file(
        str(XML_PATH), spp=spp, resx=resolution, resy=resolution
    )


def reconstructed_scene_dict(
    colours: dict[str, np.ndarray],
    shape_elements: list[ET.Element],
    camera_matrix: list[list[float]],
    environment_matrix: list[list[float]],
    material_mode: str,
    width: int,
    height: int,
    spp: int,
) -> dict:
    """Build the matched custom-plugin scene dictionary."""
    if material_mode not in {"principled", "diffuse"}:
        raise ValueError(f"Unknown material mode: {material_mode}")

    materials = {}
    for material_id, colour in colours.items():
        values = [float(value) for value in colour]
        if material_mode == "principled":
            inner = {
                "type": "principled_bsdf",
                "base_colour": values,
                "roughness": DEFAULT_ROUGHNESS,
                "metallic": 0.0,
                "specular": 0.0,
            }
        else:
            inner = {
                "type": "diffuse",
                "reflectance": {"type": "rgb", "value": values},
            }
        materials[material_id] = {"type": "twosided", "bsdf": inner}

    shapes = {}
    for index, element in enumerate(shape_elements):
        filename = element.find("string[@name='filename']").get("value")
        material_id = element.find("ref").get("id")
        shapes[f"shape_{index:04d}"] = {
            "type": "ply",
            "filename": str(ASSET_DIR / filename),
            "bsdf": materials[material_id],
        }

    return {
        "type": "scene",
        "integrator": {
            "type": "path_tracer",
            "max_depth": 8,
            "rr_depth": 3,
            "firefly_clamp": 0.0,
        },
        "sensor": {
            "type": "physical_camera",
            "fov": 39.000001,
            "aperture_radius": 0.0,
            "focus_distance": 1.0,
            "to_world": mi.ScalarTransform4f(camera_matrix),
            "film": {
                "type": "hdrfilm",
                "width": width,
                "height": height,
                "pixel_format": "rgb",
                "component_format": "float32",
                "rfilter": {"type": "gaussian", "stddev": 0.5},
            },
            "sampler": {"type": "independent", "sample_count": spp},
        },
        "environment": {
            "type": "custom_envmap",
            "filename": str(ASSET_DIR / "textures" / "_unnamed_6.hdr"),
            "importance": True,
            "scale": 0.5,
            "to_world": mi.ScalarTransform4f(environment_matrix),
        },
        **shapes,
    }


def reconstructed_scene(
    colours: dict[str, np.ndarray],
    shape_elements: list[ET.Element],
    camera_matrix: list[list[float]],
    environment_matrix: list[list[float]],
    material_mode: str,
    resolution: int,
    spp: int,
) -> mi.Scene:
    """Compatibility wrapper used by the canonical integration evaluator."""
    return mi.load_dict(
        reconstructed_scene_dict(
            colours,
            shape_elements,
            camera_matrix,
            environment_matrix,
            material_mode,
            resolution,
            resolution,
            spp,
        )
    )


def lego_scene_dict(width: int = 512, height: int = 512, spp: int = 64) -> dict:
    """Construct the custom LEGO scene directly from the canonical export."""
    _, shape_elements, colours = load_description()
    exported = load_exported_scene(16, 1)
    camera_matrix = scalar_matrix(exported.sensors()[0].world_transform())
    environment_matrix = scalar_matrix(exported.environment().world_transform())
    return reconstructed_scene_dict(
        colours,
        shape_elements,
        camera_matrix,
        environment_matrix,
        "principled",
        width,
        height,
        spp,
    )
