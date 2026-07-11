import mitsuba as mi


def cornell_box_scene():
    """
    Validates: global illumination, colour bleeding, shadow behaviour
    Expected: red wall bleeds onto ceiling and floor,
    soft shadows under boxes, indirect light on ceiling
    """
    scene = mi.cornell_box()
    scene["integrator"] = {"type": "path_tracer", "max_depth": 8}

    scene['white'] = {
            'type': 'principled_bsdf',
            'base_colour': [0.885, 0.698, 0.666],
            'roughness': 1.0,
            'metallic': 0.0
        }
    scene['red'] = {
        'type': 'principled_bsdf',
        'base_colour': [0.570, 0.043, 0.044],
        'roughness': 1.0,
        'metallic': 0.0
    }
    scene['green'] = {
        'type': 'principled_bsdf',
        'base_colour': [0.105, 0.377, 0.076],
        'roughness': 1.0,
        'metallic': 0.0
    }
    return scene
