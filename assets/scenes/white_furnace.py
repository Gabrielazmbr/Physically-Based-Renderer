import mitsuba as mi

def white_furnace_scene(bsdf, integrator_type="path_tracer", spp=256, max_depth=16):
    """
    Validates: energy conservation for a given BSDF + integrator pair.
    Expected: sphere completely invisible against white background (mean -> 1.0).
    """
    return {
        "type": "scene",
        "integrator": {"type": integrator_type, "max_depth": max_depth},
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
            "sampler": {"type": "independent", "sample_count": spp},
        },
        "emitter": {
            "type": "constant",
            "radiance": {"type": "rgb", "value": [1.0, 1.0, 1.0]},
        },
        "sphere": {
            "type": "sphere",
            "radius": 1.0,
            "bsdf": bsdf,
        },
    }
