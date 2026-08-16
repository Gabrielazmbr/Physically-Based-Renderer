#!/usr/bin/env -S uv run --script
"""
Parses the Blender-exported lego XML into a scene dict using
plugins. Camera transform is extracted from Mitsuba's own resolved
sensor (same technique validated on the cube test) rather than
hand-deriving the rotate/translate composition.
"""
import _common
import xml.etree.ElementTree as ET
import os
import mitsuba as mi

XML_PATH = "/Users/gabrielazambrano/Desktop/MSC_CAVE/MASTER PROJECT/MISC/BLENDER_SCENES/LEGO_TEST/lego_test.xml"
BASE_DIR = os.path.dirname(XML_PATH)

DEFAULT_ROUGHNESS = 0.4


tree = ET.parse(XML_PATH)
root = tree.getroot()

def parse_rgb(bsdf_el):
    return [float(x) for x in bsdf_el.find("rgb").get("value").split()]

materials = {}
for bsdf_el in root.findall("bsdf"):
    mat_id, mat_type = bsdf_el.get("id"), bsdf_el.get("type")
    if mat_type == "twosided":
        color = parse_rgb(bsdf_el.find("bsdf"))
    elif mat_type == "diffuse":
        color = parse_rgb(bsdf_el)
    elif mat_type == "blendbsdf":
        weight = float(bsdf_el.find("float[@name='weight']").get("value"))
        b1 = bsdf_el.find("bsdf[@name='bsdf1']").find("bsdf")
        b2 = bsdf_el.find("bsdf[@name='bsdf2']").find("bsdf")
        c1, c2 = parse_rgb(b1), parse_rgb(b2)
        color = [weight * a + (1 - weight) * b for a, b in zip(c1, c2)]
    else:
        print(f"Unhandled material type '{mat_type}' ({mat_id}), skipping")
        continue

    materials[mat_id] = {
        "type": "twosided",
        "bsdf": {"type": "principled_bsdf", "base_colour": color,
                "roughness": DEFAULT_ROUGHNESS, "metallic": 0.0,
                "specular": 0.0},
    }
    """
    materials[mat_id] = {
        "type": "twosided",
        "bsdf": {"type": "diffuse", "reflectance": {"type": "rgb", "value": color}},
    }
    """
print(f"Parsed {len(materials)} materials: {list(materials.keys())}")

shapes = {}
for i, shape_el in enumerate(root.findall("shape")):
    filename = shape_el.find("string[@name='filename']").get("value")
    ref_id = shape_el.find("ref").get("id")
    shapes[f"shape_{i}"] = {"type": "ply", "filename": os.path.join(BASE_DIR, filename), "bsdf": materials[ref_id]}
print(f"Parsed {len(shapes)} shapes")

ref_scene = mi.load_file(XML_PATH)
cam_matrix = ref_scene.sensors()[0].world_transform().matrix
cam_matrix = [[float(cam_matrix[i][j][0]) for j in range(4)] for i in range(4)]

ref_env = ref_scene.environment()
env_matrix = ref_env.world_transform().matrix
env_matrix = [[float(env_matrix[i][j][0]) for j in range(4)] for i in range(4)]

scene_dict = {
    "type": "scene",
    "integrator": {"type": "path_tracer", "max_depth": 8},
    "sensor": {
        "type": "physical_camera",
        "fov": 39.000001,
        "aperture_radius": 0.0,
        "focus_distance": 1.0,
        "to_world": mi.ScalarTransform4f(cam_matrix),
        "film": {"type": "hdrfilm", "width": 1080, "height": 1080},
        "sampler": {"type": "independent", "sample_count": 1024},
    },
    "envlight": {
        "type": "custom_envmap",
        "filename": os.path.join(BASE_DIR, "textures/_unnamed_6.hdr"),
        "importance": True,
        "scale": 0.5,
        "to_world": mi.ScalarTransform4f(env_matrix),
    },
    **materials,
    **shapes,
}

own_scene = mi.load_dict(scene_dict)
img = mi.render(own_scene, spp=1024)
mi.util.write_bitmap("outputs/BlenderValidation/lego_test_custom_04.exr", img)
print("Wrote outputs/BlenderValidation/lego_test_custom_04.exr")
