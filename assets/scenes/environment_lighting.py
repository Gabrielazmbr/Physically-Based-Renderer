import mitsuba as mi


def environment_lighting_scene(hdri_path="assets/hdri/studio_kontrast_04_1k.exr"):
    """
    Validates: IBL importance sampling vs uniform sampling
    Expected: importance sampled version shows less noise at same sample count
    """
    return {
        "type": "scene",
        "integrator": {"type": "path_tracer", "max_depth": 8},
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
            "sampler": {"type": "independent", "sample_count": 64},
        },
        "emitter": {"type": "envmap", "filename": hdri_path},
        "sphere": {
            "type": "sphere",
            "radius": 1.0,
            "bsdf": {
                "type": "principled_bsdf",
                "base_colour": [0.95, 0.95, 0.95],
                "roughness": 0.1,
                "metallic": 1.0,
            },
        },
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
