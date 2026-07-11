import mitsuba as mi


def material_test_scene():
    """
    Validates: Principled BSDF parameter behaviour
    Expected: three spheres showing distinct material responses
    """
    return {
        "type": "scene",
        "integrator": {"type": "path_tracer", "max_depth": 8},
        "sensor": {
            "type": "perspective",
            "fov": 45,
            "to_world": mi.ScalarTransform4f().look_at(
                origin=[0, 1.5, 10], target=[0, 0, 0], up=[0, 1, 0]
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
            "radiance": {"type": "rgb", "value": [1.0, 1.0, 1.0]},
        },
        "sphere_metal": {
            "type": "sphere",
            "center": [-2.5, 0, 0],
            "radius": 0.8,
            "bsdf": {
                "type": "principled_bsdf",
                "base_colour": [0.95, 0.77, 0.33],
                "roughness": 0.1,
                "metallic": 1.0,
            },
        },
        "sphere_plastic": {
            "type": "sphere",
            "center": [0, 0, 0],
            "radius": 0.8,
            "bsdf": {
                "type": "principled_bsdf",
                "base_colour": [0.2, 0.3, 0.8],
                "roughness": 0.3,
                "metallic": 0.0,
            },
        },
        "sphere_organic": {
            "type": "sphere",
            "center": [2.5, 0, 0],
            "radius": 0.8,
            "bsdf": {
                "type": "principled_bsdf",
                "base_colour": [0.6, 0.3, 0.2],
                "roughness": 1.0,
                "metallic": 0.0,
            },
        },
        # Ground plane
        "floor": {
            "type": "rectangle",
            "to_world": mi.ScalarTransform4f()
            .scale([5, 5, 4])
            .rotate([1, 0, 0], 90)
            .translate([0, -0.8, 0.5]),
            "bsdf": {
                "type": "twosided",
                "bsdf": {
                    "type": "diffuse",
                    "reflectance": {"type": "rgb", "value": [0.8, 0.8, 0.8]},
                },
            },
        },
}
