import mitsuba as mi


def depth_of_field_scene():
    """
    Validates: thin-lens camera model
    Expected: middle sphere in focus, near and far spheres blurred
    """
    return {
        "type": "scene",
        "integrator": {"type": "path_tracer", "max_depth": 8},
        "sensor": {
            "type": "physical_camera",
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
        "sphere_near": {
            "type": "sphere",
            "center": [-3, 0, 4],
            "radius": 0.6,
            "bsdf": {
                "type": "diffuse",
                "reflectance": {"type": "rgb", "value": [0.8, 0.2, 0.2]},
            },
        },
        "sphere_mid": {
            "type": "sphere",
            "center": [0, 0, 0],
            "radius": 0.6,
            "bsdf": {
                "type": "diffuse",
                "reflectance": {"type": "rgb", "value": [0.2, 0.8, 0.2]},
            },
        },
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
