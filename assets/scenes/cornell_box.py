"""
Scene 01 Cornell Box
Validates: global illumination, colour bleeding, shadow behaviour
Outcome: red wall bleeds onto ceiling and floor,
soft shadows under boxes, indirect light on ceiling
"""

import mitsuba as mi

mi.set_variant("llvm_ad_rgb")

scene_dict = {
    "type": "scene",
    # To be replaced: 'path' with 'path_tracer'
    "integrator": {"type": "path", "max_depth": 8},
    **mi.cornell_box(),
}

if __name__ == "__main__":
    scene = mi.load_dict(mi.cornell_box())
    img = mi.render(scene, spp=64)
    mi.Bitmap(img).write("outputs/01_cornell_box.exr")
    print("Cornell Box rendered — check outputs/01_cornell_box.exr")
