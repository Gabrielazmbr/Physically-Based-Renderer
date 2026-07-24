#!/usr/bin/env -S uv run --script
"""
Section 1: Path tracer energy-transport validation (control test).
Uses Mitsuba's built-in `diffuse` BSDF, isolating whether the path
tracer itself handles energy correctly, independent of custom BSDF.
Expected: mean -> 1.0, std -> 0 as spp increases, matching Mitsuba's
own `path` integrator at every spp.
"""
import _common  # noqa: F401
import numpy as np
import mitsuba as mi
from assets.scenes.white_furnace import white_furnace_scene

diffuse_bsdf = {"type": "diffuse", "reflectance": {"type": "rgb", "value": [1.0, 1.0, 1.0]}}

configs = [
    ("path_tracer", 256,  0),
    ("path_tracer", 1024, 0),
    ("path",        256,  1000),
    ("path",        1024, 1000),
]

print(f"{'Integrator':<12} {'SPP':>6} {'Seed':>6} {'Mean':>8} {'Std':>8}")
for integrator_type, spp, seed in configs:
    scene = mi.load_dict(white_furnace_scene(diffuse_bsdf, integrator_type=integrator_type, spp=spp))
    img = mi.render(scene, spp=spp, seed=seed)
    arr = np.array(img)[..., :3]
    print(f"{integrator_type:<12} {spp:>6} {seed:>6} {arr.mean():>8.4f} {arr.std():>8.4f}")
