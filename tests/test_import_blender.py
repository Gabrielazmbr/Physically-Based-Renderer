#!/usr/bin/env -S uv run --script
"""
Loads the raw Blender export with Mitsuba's own built-ins (geometry +
camera transform ground truth), then builds an equivalent scene with
plugins, reusing the sensor's *resolved* to_world matrix rather than
hand-deriving the rotate/translate composition. Scoped to this single
mesh/material test scene — a multi-object scene will need the
shape/material list generalized into a loop.
"""
import _common
import mitsuba as mi
import os

SCENE_DIR = "/Users/gabrielazambrano/Desktop/MSC_CAVE/MASTER PROJECT/MISC/BLENDER_SCENES/IMPORT_TEST"
XML_PATH = os.path.join(SCENE_DIR, "import_test.xml")

ref_scene = mi.load_file(XML_PATH)


cam_matrix = ref_scene.sensors()[0].world_transform().matrix
cam_matrix = [[float(cam_matrix[i][j][0]) for j in range(4)] for i in range(4)]

own_scene = mi.load_dict({
    "type": "scene",
    "integrator": {"type": "path_tracer", "max_depth": 12},
    "sensor": {
        "type": "thinlens",
        "fov": 39.597752,
        "aperture_radius": 0.0,
        "focus_distance": 1.0,
        "to_world": mi.ScalarTransform4f(cam_matrix),
        "film": {"type": "hdrfilm", "width": 480, "height": 270},
        "sampler": {"type": "independent", "sample_count": 128},
    },
    "light": {
        "type": "point",
        "position": [4.076245307922363, 5.903861999511719, -1.0054539442062378],
        "intensity": {"type": "rgb", "value": [79.577469, 79.577469, 79.577469]},
    },
    "cube": {
        "type": "ply",
        "filename": os.path.join(SCENE_DIR, "meshes/Cube.ply"),
        "face_normals": True,
        "bsdf": {
            "type": "twosided",
            "bsdf": {
                "type": "principled_bsdf",
                "base_colour": [0.8, 0.8, 0.8],
                "roughness": 0.25,
                "metallic": 0.0,
            },
        },
    },
})

ref_img = mi.render(ref_scene, spp=128)
own_img = mi.render(own_scene, spp=128)

mi.util.write_bitmap("outputs/SceneImportTest/import_test_reference_01.png", ref_img)
mi.util.write_bitmap("outputs/SceneImportTest/import_test_custom_01.png", own_img)
print("Wrote import_test_reference.png (Mitsuba built-ins) and import_test_custom.png (your stack)")
