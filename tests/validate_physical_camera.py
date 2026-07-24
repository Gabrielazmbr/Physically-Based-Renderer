#!/usr/bin/env -S uv run --script
"""
1. Pinhole-equivalence: at aperture_radius=0, physical_Camera should
   match Mitsuba's own built-in `perspective` sensor exactly (same fov,
   same to_world).
2. Depth-of-field: three spheres at different distances: mid one at
   focus_distance should be sharp, near/far should visibly blur.
"""
import _common
import numpy as np
import mitsuba as mi

def three_sphere_scene(sensor_type, aperture_radius=0.0, focus_distance=5.0):
    return {
        "type": "scene",
        "integrator": {"type": "path_tracer", "max_depth": 4},
        "sensor": {
            "type": sensor_type,
            "fov": 40,
            **({"aperture_radius": aperture_radius, "focus_distance": focus_distance}
               if sensor_type == "physical_camera" else {}),
            "to_world": mi.ScalarTransform4f().look_at(
                origin=[0, 0, 0], target=[0, 0, -1], up=[0, 1, 0]
            ),
            "film": {"type": "hdrfilm", "width": 400, "height": 300},
            "sampler": {"type": "independent", "sample_count": 64},
        },
        "light": {"type": "constant", "radiance": {"type": "rgb", "value": [1.0, 1.0, 1.0]}},
        "near":  {"type": "sphere", "to_world": mi.ScalarTransform4f().translate([-0.6, 0, -3]).scale(0.4),
                  "bsdf": {"type": "principled_bsdf", "base_colour": [0.9, 0.2, 0.2], "roughness": 0.5, "metallic": 0.0}},
        "mid":   {"type": "sphere", "to_world": mi.ScalarTransform4f().translate([0, 0, -5]).scale(0.4),
                  "bsdf": {"type": "principled_bsdf", "base_colour": [0.2, 0.9, 0.2], "roughness": 0.5, "metallic": 0.0}},
        "far":   {"type": "sphere", "to_world": mi.ScalarTransform4f().translate([0.9, 0, -9]).scale(0.4),
                  "bsdf": {"type": "principled_bsdf", "base_colour": [0.2, 0.2, 0.9], "roughness": 0.5, "metallic": 0.0}},
    }

# --- Test 1: pinhole equivalence ---
scene_physical_camera = mi.load_dict(three_sphere_scene("physical_camera", aperture_radius=0.0))
scene_perspective = mi.load_dict(three_sphere_scene("perspective"))

img_physical_camera = np.array(mi.render(scene_physical_camera, spp=1024))
img_perspective = np.array(mi.render(scene_perspective, spp=1024))

img_physical_camera = img_physical_camera
img_perspective = img_perspective

diff = np.abs(img_physical_camera - img_perspective).mean()
print(f"Pinhole-equivalence mean abs diff: {diff:.5f} (expect near 0)")
mi.util.write_bitmap("outputs/CameraValidation/pinhole_physical_camera.png", img_physical_camera)
mi.util.write_bitmap("outputs/CameraValidation/pinhole_perspective.png", img_perspective)

# --- Test 2: depth of field ---
scene_dof = mi.load_dict(three_sphere_scene("physical_camera", aperture_radius=0.15, focus_distance=5.0))
img_dof = np.array(mi.render(scene_dof, spp=256))
img_dof = np.array(mi.render(scene_dof, spp=256))
mi.util.write_bitmap("outputs/CameraValidation/dof_test.png", img_dof)
print("Wrote pinhole_physical_camera.png, pinhole_perspective.png, dof_test.png")
