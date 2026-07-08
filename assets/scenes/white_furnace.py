"""
Scene 02 White Furnace Test
Validates: BSDF energy conservation
Expected outcome: sphere is completely invisible against
the white background at ALL roughness values.
If visible, the BSDF is not energy conserving.
"""

import mitsuba as mi

mi.set_variant("llvm_ad_rgb")


def white_furnace_scene(roughness=0.5):
    return {
        "type": "scene",
        "integrator": {
            "type": "path",
            "max_depth": 16,  # high depth needed for furnace test
        },
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
        # Uniform white environment, emits equal light from all directions
        "emitter": {
            "type": "constant",
            "radiance": {"type": "rgb", "value": [1.0, 1.0, 1.0]},
        },
        # Using PrincipledBSDF
        "sphere": {
            "type": "sphere",
            "radius": 1.0,
            "bsdf": {
                "type": "PrincipledBSDF",
                "base_colour": [1.0, 1.0, 1.0],
                "roughness": 1.0,
                "metallic": 0.0,
            },
        },
    }


if __name__ == "__main__":
    for roughness in [0.0, 0.5, 1.0]:
        scene = mi.load_dict(white_furnace_scene(roughness))
        img = mi.render(scene, spp=256)
        mi.Bitmap(img).write(f"outputs/02_white_furnace_r{roughness}.exr")
        print(f"White furnace rendered at roughness {roughness}")
