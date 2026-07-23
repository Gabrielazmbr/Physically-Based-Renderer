#!/usr/bin/env -S uv run --script
"""
Section 3: Principled BSDF furnace test (energy conservation).
Custom path_tracer + custom principled_bsdf throughout, at
metallic=0.0 (diffuse+Fresnel) and metallic=1.0 (pure specular), across
a roughness sweep. Expected: mean -> 1.0 everywhere if the BSDF is fully
energy-conserving; remaining loss at high roughness is the known GGX
single-scattering effect (see furnace_ggx_reference.py).
"""

import _common  # noqa: F401
import numpy as np
import mitsuba as mi
from assets.scenes.white_furnace import white_furnace_scene

def principled(roughness, metallic):
    return {
        "type": "principled_bsdf",
        "base_colour": [1.0, 1.0, 1.0],
        "roughness": roughness,
        "metallic": metallic,
    }

roughness_values = [0.0, 0.5, 1.0]
spp = 256

for metallic, seed in [(0.0, 11), (1.0, 7)]:
    label = "Diffuse (metallic=0.0)" if metallic == 0.0 else "Metal (metallic=1.0)"
    print(f"\n{label}")
    print(f"{'Roughness':>9} {'SPP':>6} {'Seed':>6} {'Mean':>8} {'Std':>8}")
    for r in roughness_values:
        scene = mi.load_dict(white_furnace_scene(principled(r, metallic), integrator_type="path_tracer", spp=spp))
        img = mi.render(scene, spp=spp, seed=seed)
        arr = np.array(img)
        print(f"{r:>9.1f} {spp:>6} {seed:>6} {arr.mean():>8.4f} {arr.std():>8.4f}")


"""
SPP Increase.
"""
bsdf = {"type": "principled_bsdf", "base_colour": [1.0, 1.0, 1.0], "roughness": 0.0, "metallic": 0.0}

print("SPP Increase: ")
for spp, seed in [(256, 11), (1024, 11), (1024, 22), (4096, 11)]:
    scene = mi.load_dict(white_furnace_scene(bsdf, integrator_type="path_tracer", spp=spp))
    img = mi.render(scene, spp=spp, seed=seed)
    arr = np.array(img)
    print(f"spp={spp:>5} seed={seed:>3}  mean={arr.mean():.4f}  std={arr.std():.4f}")
