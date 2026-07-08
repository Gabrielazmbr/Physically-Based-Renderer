"""
Scene 05 Depth of Field Scene
Validates: thin-lens camera model
Expected outcome: middle sphere in focus,
near and far spheres correctly blurred.
Bokeh sweep shows circle of confusion growing with aperture.
"""

import mitsuba as mi

mi.set_variant("llvm_ad_rgb")

scene_dict = {
    "type": "scene",
    "integrator": {"type": "path", "max_depth": 8},
    # To be replaced: 'perspective' with 'my_thin_lens'
    "sensor": {
        "type": "thinlens",
        "fov": 60,
        "aperture_radius": 0.5,
        "focus_distance": 12.0,
        "to_world": mi.ScalarTransform4f().look_at(
            origin=[0, 1, 12], target=[0, 0, 0], up=[0, 1, 0]
        ),
        "film": {
            "type": "hdrfilm",
            "width": 768,
            "height": 384,
            "pixel_format": "rgb",
            "component_format": "float32",
            "rfilter": {"type": "gaussian"},
        },
        "sampler": {"type": "independent", "sample_count": 128},
    },
    "light": {
        "type": "constant",
        "radiance": {"type": "rgb", "value": [1.5, 1.5, 1.5]},
    },
    # Near sphere — should be blurred
    "sphere_near": {
        "type": "sphere",
        "center": [-3, 0, 4],
        "radius": 0.6,
        "bsdf": {
            "type": "diffuse",
            "reflectance": {"type": "rgb", "value": [0.8, 0.2, 0.2]},
        },
    },
    # Middle sphere — should be in focus
    "sphere_mid": {
        "type": "sphere",
        "center": [0, 0, 0],
        "radius": 0.6,
        "bsdf": {
            "type": "diffuse",
            "reflectance": {"type": "rgb", "value": [0.2, 0.8, 0.2]},
        },
    },
    # Far sphere — should be blurred
    "sphere_far": {
        "type": "sphere",
        "center": [3, 0, -5],
        "radius": 0.6,
        "bsdf": {
            "type": "diffuse",
            "reflectance": {"type": "rgb", "value": [0.2, 0.2, 0.8]},
        },
    },
    "floor": {
        "type": "rectangle",
        "to_world": mi.ScalarTransform4f()
        .scale([10, 10, 1])
        .rotate([1, 0, 0], 90)
        .translate([0, -0.6, 0.3]),
        "bsdf": {
            "type": "twosided",
            "bsdf": {
                "type": "diffuse",
                "reflectance": {"type": "rgb", "value": [0.7, 0.7, 0.7]},
            },
        },
    },
}

if __name__ == "__main__":
    scene = mi.load_dict(scene_dict)
    img = mi.render(scene, spp=128)
    mi.Bitmap(img).write("outputs/05_depth_of_field.exr")
    print("Depth of field rendered — check outputs/05_depth_of_field.exr")
