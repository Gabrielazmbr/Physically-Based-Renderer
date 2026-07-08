"""
Scene 04 Environment Lighting Scene
Validates: IBL importance sampling vs uniform sampling
Expected outcome: importance sampled version shows
measurably less noise at same sample count.
"""

import mitsuba as mi

mi.set_variant("llvm_ad_rgb")


HDRI_PATH = "assets/hdri/studio_kontrast_04_1k.exr"

scene_dict = {
    "type": "scene",
    "integrator": {"type": "path", "max_depth": 8},
    "sensor": {
        "type": "perspective",
        "fov": 40,
        "to_world": mi.ScalarTransform4f().look_at(
            origin=[0, 0.5, 5], target=[0, 0, 0], up=[0, 1, 0]
        ),
        "film": {
            "type": "hdrfilm",
            "width": 512,
            "height": 512,
            "pixel_format": "rgb",
            "component_format": "float32",
            "rfilter": {"type": "gaussian"},
        },
        "sampler": {"type": "independent", "sample_count": 128},
    },
    # To be replaced: custom importance-sampled IBL emitter
    "emitter": {"type": "envmap", "filename": HDRI_PATH},
    "sphere": {"type": "sphere", "radius": 1.0, "bsdf": {"type": "conductor"}},
    "floor": {
        "type": "rectangle",
        "to_world": mi.ScalarTransform4f()
        .scale([5, 5, 1])
        .rotate([1, 0, 0], 90)
        .translate([0, -1.1, 0.5]),
        "bsdf": {
            "type": "twosided",
            "bsdf": {
                "type": "diffuse",
                "reflectance": {"type": "rgb", "value": [0.8, 0.8, 0.8]},
            },
        },
    },
}

if __name__ == "__main__":
    scene = mi.load_dict(scene_dict)
    img = mi.render(scene, spp=64)
    mi.Bitmap(img).write("outputs/04_environment_lighting.exr")
    print("Environment lighting rendered — check outputs/04_environment_lighting.exr")
