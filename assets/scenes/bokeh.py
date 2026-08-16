import mitsuba as mi


def bokeh_scene():
    """Demonstrate aperture shape using bright out-of-focus point sources."""
    scene = {
        "type": "scene",
        "integrator": {"type": "path_tracer", "max_depth": 2},
        "sensor": {
            "type": "physical_camera",
            "fov": 50,
            "aperture_radius": 0.35,
            "focus_distance": 6.0,
            "aperture_blades": 6,
            "to_world": mi.ScalarTransform4f().look_at(
                origin=[0, 0, 0], target=[0, 0, -1], up=[0, 1, 0]
            ),
            "film": {
                "type": "hdrfilm",
                "width": 500,
                "height": 500,
                "pixel_format": "rgb",
                "component_format": "float32",
                "rfilter": {"type": "box"},
            },
            "sampler": {"type": "independent", "sample_count": 256},
        },
        "background": {
            "type": "constant",
            "radiance": {"type": "rgb", "value": [0.01, 0.01, 0.012]},
        },
    }
    for index, (position, colour) in enumerate(
        [
            ([-0.8, 0.3, -2.0], [34, 34, 34]),
            ([0.7, -0.2, -2.2], [34, 26, 18]),
            ([0.0, 0.65, -2.5], [18, 22, 34]),
        ]
    ):
        scene[f"light_{index}"] = {
            "type": "sphere",
            "to_world": mi.ScalarTransform4f().translate(position).scale(0.045),
            "emitter": {
                "type": "area",
                "radiance": {"type": "rgb", "value": colour},
            },
        }
    return scene
