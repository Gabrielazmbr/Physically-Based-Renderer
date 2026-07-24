#!/usr/bin/env -S uv run --script
"""
Renders a simple multi-material scene and splits the output into
separate RGB / albedo / normal / depth images, to visually confirm the
new AOV channels contain sensible data.
"""
import _common
import numpy as np
import mitsuba as mi

scene = mi.load_dict({
    "type": "scene",
    "integrator": {"type": "path_tracer", "max_depth": 8, "with_aovs": True},
    "sensor": {
        "type": "physical_camera",
        "fov": 35,
        "aperture_radius": 0.0,
        "focus_distance": 5.0,
        "to_world": mi.ScalarTransform4f().look_at(
            origin=[0, -5, 5.5], target=[0, 0, 0.5], up=[0, 0, 1]
        ),
        "film": {"type": "hdrfilm", "width": 400, "height": 300},
        "sampler": {"type": "independent", "sample_count": 64},
    },
    "light": {"type": "constant", "radiance": {"type": "rgb", "value": [0.6, 0.6, 0.6]}},
    "sphere": {
        "type": "sphere",
        "to_world": mi.ScalarTransform4f().translate([0, 0, 0.8]),
        "bsdf": {"type": "principled_bsdf", "base_colour": [0.8, 0.1, 0.1], "roughness": 0.3, "metallic": 0.0},
    },
    "floor": {
        "type": "rectangle",
        "to_world": mi.ScalarTransform4f().scale(4),
        "bsdf": {"type": "principled_bsdf", "base_colour": [0.4, 0.4, 0.4], "roughness": 0.6, "metallic": 0.0},
    },
})

img = mi.render(scene, spp=64)
arr = np.array(img)
print("Rendered image shape:", arr.shape)

rgb = arr[..., 0:3]
mi.util.write_bitmap("outputs/aov_rgb.png", rgb)

if arr.shape[-1] >= 10:
    # assumes layout: [R,G,B, albedo.R,G,B, normal.X,Y,Z, depth.Y]
    # against the printed shape above; adjust indices here if it doesn't match
    albedo = arr[..., 3:6]
    normal = arr[..., 6:9] * 0.5 + 0.5  # remap [-1,1] -> [0,1] for display only
    depth = arr[..., 9]
    depth_norm = depth / max(depth.max(), 1e-6)  # normalize for display only

    mi.util.write_bitmap("outputs/AOVs_Validation/aov_albedo.png", albedo)
    mi.util.write_bitmap("outputs/AOVs_Validation/aov_normal.png", normal)
    mi.util.write_bitmap("outputs/AOVs_Validation/aov_depth.png", np.stack([depth_norm]*3, axis=-1))
    print("Wrote outputs/AOVs_Validation/aov_{rgb,albedo,normal,depth}.png")
else:
    print(f"Only {arr.shape[-1]} channels found — AOVs may not be included as expected. Check aov_names() and the sample() return.")
