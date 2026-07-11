import mitsuba as mi


def white_furnace_scene(roughness=0.5):
    """
    Validates: BSDF energy conservation
    Expected: sphere completely invisible against white background
    """
    return {
        "type": "scene",
        "integrator": {"type": "path", "max_depth": 16},
        "sensor": {
            "type": "perspective",
            "fov": 45,
            "to_world": mi.ScalarTransform4f().look_at(
                origin=[0, 0, 3], target=[0, 0, 0], up=[0, 1, 0]
            ),
            "film": {
                "type": "hdrfilm",
                "width": 512,
                "height": 512,
                "pixel_format": "rgb",
                "component_format": "float32",
                "rfilter": {"type": "gaussian"},
            },
            "sampler": {"type": "independent", "sample_count": 256},
        },
        "emitter": {
            "type": "constant",
            "radiance": {"type": "rgb", "value": [1.0, 1.0, 1.0]},
        },
        "sphere": {
            "type": "sphere",
            "radius": 1.0,
            "bsdf": {
                "type": "principled_bsdf",
                "base_colour": [1.0, 1.0, 1.0],
                "roughness": roughness,
                "metallic": 0.0,
            },
        },
    }
