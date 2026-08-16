#!/usr/bin/env -S uv run --script
"""
Test 4: glass in a real render. Exercises what the analytic tests
cannot — back-side hits on real geometry, multi-bounce paths entering
and exiting the medium, and the path tracer's prev_delta MIS handling
firing on DeltaTransmission events.

Renders an identical scene twice, changing ONLY the sphere's BSDF:
custom principled_bsdf (transmission=1.0) vs Mitsuba's own dielectric.
The checkered floor makes refraction unambiguous — correct refraction
inverts and magnifies the pattern seen through the sphere.
"""
import _common
import numpy as np
import mitsuba as mi
import os

IOR = 1.5
SPP = 256
SEED = 3
MAX_DEPTH = 16  # glass needs depth: 2+ events just to see through, plus internal reflections

def scene_dict(sphere_bsdf):
    return {
        "type": "scene",
        "integrator": {"type": "path_tracer", "max_depth": MAX_DEPTH},
        "sensor": {
            "type": "perspective",
            "fov": 40,
            "to_world": mi.ScalarTransform4f().look_at(
                origin=[0, 1.2, 5.5], target=[0, 0, 0], up=[0, 1, 0]
            ),
            "film": {"type": "hdrfilm", "width": 500, "height": 400},
            "sampler": {"type": "independent", "sample_count": SPP},
        },
        "light": {"type": "constant", "radiance": {"type": "rgb", "value": [1.0, 1.0, 1.0]}},
        "sphere": {"type": "sphere", "radius": 1.0, "bsdf": sphere_bsdf},
        # floor transform copied from environment_lighting_scene (known-good pattern)
        "floor": {
            "type": "rectangle",
            # transforms apply right-to-left: scale, then rotate flat, then drop to y=-1
            "to_world": mi.ScalarTransform4f()
            .translate([0, -1.0, 0])
            .rotate([1, 0, 0], -90)
            .scale(10),
            "bsdf": {
                "type": "diffuse",
                "reflectance": {
                    "type": "checkerboard",
                    "color0": {"type": "rgb", "value": [0.05, 0.05, 0.05]},
                    "color1": {"type": "rgb", "value": [0.9, 0.9, 0.9]},
                    "to_uv": mi.ScalarTransform4f().scale([12, 12, 1]),
                },
            },
        },
    }

mine_bsdf = {"type": "principled_bsdf", "base_colour": [1.0, 1.0, 1.0],
             "roughness": 0.0, "metallic": 0.0,
             "transmission": 1.0, "ior": IOR}
ref_bsdf = {"type": "dielectric", "int_ior": IOR, "ext_ior": 1.0}

imgs = {}
for label, bsdf in [("mine", mine_bsdf), ("dielectric", ref_bsdf)]:
    scene = mi.load_dict(scene_dict(bsdf))
    img = np.array(mi.render(scene, spp=SPP, seed=SEED))
    imgs[label] = img
    os.makedirs(f"outputs/GlassValidation", exist_ok=True)
    mi.util.write_bitmap(f"outputs/GlassValidation/glass_{label}.png", img)
    print(f"Wrote outputs/GlassValidation/glass_{label}.png   mean={img.mean():.4f}  max={img.max():.3f}")

diff = np.abs(imgs["mine"] - imgs["dielectric"]).mean()
print(f"\nMean abs diff vs dielectric: {diff:.5f} (expect near 0 — both are delta BSDFs, so")
print("identical sampling decisions from the same seed should give near-identical images)")
