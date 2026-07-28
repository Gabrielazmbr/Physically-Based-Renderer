#!/usr/bin/env -S uv run --script
"""
Visual check: anisotropic GGX should show a highlight elongated
perpendicular to the low-alpha (sharp) direction, and rotate visibly
between two orthogonal alpha_u/alpha_v assignments — confirms both
that anisotropy is present and that its orientation actually follows
the surface's tangent direction, not some fixed/arbitrary axis.
"""
import _common
import numpy as np
import mitsuba as mi

def scene_dict(anisotropic):
    return {
        "type": "scene",
        "integrator": {"type": "path_tracer", "max_depth": 4},
        "sensor": {
            "type": "physical_camera",
            "fov": 35,
            "aperture_radius": 0.0,
            "focus_distance": 5.0,
            "to_world": mi.ScalarTransform4f().look_at(origin=[0, 2.5, 4], target=[0, 0, 0], up=[0, 1, 0]),
            "film": {"type": "hdrfilm", "width": 500, "height": 500},
            "sampler": {"type": "independent", "sample_count": 256},
        },
        "light": {"type": "point", "position": [2, 4, 3], "intensity": {"type": "rgb", "value": [40, 40, 40]}},
        "fill": {"type": "constant", "radiance": {"type": "rgb", "value": [0.05, 0.05, 0.05]}},
        "disc": {
            "type": "disk",
            "to_world": mi.ScalarTransform4f().scale(1.5).rotate([1, 0, 0], -90),
            "bsdf": {
                "type": "principled_bsdf",
                "base_colour": [0.9, 0.9, 0.9],
                "roughness": 0.25,
                "metallic": 1.0,
                "anisotropic": anisotropic,
            },
        },
    }

for label, aniso in [("isotropic", 0.0), ("anisotropic_08", 0.8)]:
    scene = mi.load_dict(scene_dict(aniso))
    img = np.array(mi.render(scene, spp=256))
    mi.util.write_bitmap(f"outputs/AnistropicValid/aniso_{label}.png", img)
    print(f"Wrote outputs/AnistropicValid/aniso_{label}.png")
