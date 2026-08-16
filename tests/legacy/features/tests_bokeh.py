#!/usr/bin/env -S uv run --script
"""
Visual check: bladed bokeh. Small, bright, heavily out-of-focus lights
against a dark background reveal the aperture's sampled shape directly
in the blur pattern - circular vs hexagonal.
"""
import _common
import numpy as np
import mitsuba as mi

def scene_dict(aperture_blades):
    return {
        "type": "scene",
        "integrator": {"type": "path_tracer", "max_depth": 2},
        "sensor": {
            "type": "physical_camera",
            "fov": 50,
            "aperture_radius": 0.35,
            "focus_distance": 6.0,
            "aperture_blades": aperture_blades,
            "to_world": mi.ScalarTransform4f().look_at(origin=[0,0,0], target=[0,0,-1], up=[0,1,0]),
            "film": {"type": "hdrfilm", "width": 500, "height": 500},
            "sampler": {"type": "independent", "sample_count": 256},
        },
        "bg": {"type": "constant", "radiance": {"type": "rgb", "value": [0.02, 0.02, 0.02]}},
        "light1": {"type": "sphere", "to_world": mi.ScalarTransform4f().translate([-0.8, 0.3, -2]).scale(0.05),
                   "emitter": {"type": "area", "radiance": {"type": "rgb", "value": [30, 30, 30]}}},
        "light2": {"type": "sphere", "to_world": mi.ScalarTransform4f().translate([0.7, -0.2, -2.2]).scale(0.05),
                   "emitter": {"type": "area", "radiance": {"type": "rgb", "value": [30, 25, 20]}}},
        "light3": {"type": "sphere", "to_world": mi.ScalarTransform4f().translate([0.0, 0.6, -2.5]).scale(0.05),
                   "emitter": {"type": "area", "radiance": {"type": "rgb", "value": [20, 20, 30]}}},
    }

for label, blades in [("circular", 0), ("hexagon", 6)]:
    scene = mi.load_dict(scene_dict(blades))
    img = np.array(mi.render(scene, spp=256))
    mi.util.write_bitmap(f"outputs/CamBokehValidation/bokeh_{label}.png", img)
    print(f"Wrote outputs/CamBokehValidation/bokeh_{label}.png")
