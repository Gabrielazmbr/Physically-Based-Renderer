#!/usr/bin/env -S uv run --script
"""
Section 3: Principled BSDF furnace test (energy conservation).
Custom path_tracer + custom principled_bsdf throughout, at
metallic=0.0 (diffuse+Fresnel) and metallic=1.0 (pure specular), across
a roughness sweep. Expected: mean - 1.0 everywhere if the BSDF is fully
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

def principled_burley(roughness, metallic):
    return {
        "type": "principled_bsdf",
        "diffuse_model": "burley",
        "base_colour": [1.0, 1.0, 1.0],
        "roughness": roughness,
        "metallic": metallic,
    }

def principled_zero_specular(roughness):
    """
    specular=0.0, metallic=0.0 — zero-specular Lambertian
    Expected:
    mean: 1.0 at every roughness, since there's no Fresnel attenuation left
    at all (unlike the metallic=0.0/specular=0.5 case above, which
    still carries a small F0=0.04 term).
    """
    return {
        "type": "principled_bsdf",
        "base_colour": [1.0, 1.0, 1.0],
        "roughness": roughness,
        "metallic": 0.0,
        "specular": 0.0,
    }

def principled_clearcoat(clearcoat, gloss):
    """
    Clearcoat on a zero-specular base, so the only thing above the Lambertian
    1.0 baseline is the coat itself. Disney's clearcoat is ADDITIVE — it does
    not remove energy from the layer beneath — so the mean is expected to sit
    ABOVE 1.0 by the coat's directional albedo. That overshoot is faithful to
    the 2012 model, not a bug.
    """
    return {
        "type": "principled_bsdf",
        "base_colour": [1.0, 1.0, 1.0],
        "roughness": 1.0,
        "metallic": 0.0,
        "specular": 0.0,
        "clearcoat": clearcoat,
        "clearcoat_gloss": gloss,
    }


def principled_sheen(sheen, sheen_tint):
    """
    Sheen on a zero-specular base, same reasoning: an additive grazing-angle
    term, so the mean is expected above 1.0. White base means sheen_tint
    should make no difference — that is itself the test.
    """
    return {
        "type": "principled_bsdf",
        "base_colour": [1.0, 1.0, 1.0],
        "roughness": 1.0,
        "metallic": 0.0,
        "specular": 0.0,
        "sheen": sheen,
        "sheen_tint": sheen_tint,
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
        arr = np.array(img)[..., :3]
        print(f"{r:>9.1f} {spp:>6} {seed:>6} {arr.mean():>8.4f} {arr.std():>8.4f}")

print(f"\nZero-specular (specular=0.0, metallic=0.0)")
print(f"{'Roughness':>9} {'SPP':>6} {'Seed':>6} {'Mean':>8} {'Std':>8}")
for r in roughness_values:
    scene = mi.load_dict(white_furnace_scene(principled_zero_specular(r), integrator_type="path_tracer", spp=spp))
    img = mi.render(scene, spp=spp, seed=17)
    arr = np.array(img)[..., :3]
    print(f"{r:>9.1f} {spp:>6} {17:>6} {arr.mean():>8.4f} {arr.std():>8.4f}")


print(f"\nBurley diffuse (metallic=0.0, diffuse_model=burley)")
print(f"{'Roughness':>9} {'SPP':>6} {'Seed':>6} {'Mean':>8} {'Std':>8}")
for r in roughness_values:
    scene = mi.load_dict(white_furnace_scene(principled_burley(r, 0.0), integrator_type="path_tracer", spp=spp))
    img = mi.render(scene, spp=spp, seed=23)
    arr = np.array(img)
    print(f"{r:>9.1f} {spp:>6} {23:>6} {arr.mean():>8.4f} {arr.std():>8.4f}")



# Clearcoat
print(f"\nClearcoat (zero-specular base, roughness=1.0)")
print(f"{'Clearcoat':>9} {'Gloss':>6} {'SPP':>6} {'Seed':>6} {'Mean':>8} {'Std':>8} {'Delta':>8}")
cc_base = None
for cc, gloss in [(0.0, 0.0), (0.5, 0.0), (1.0, 0.0), (1.0, 0.5), (1.0, 1.0)]:
    scene = mi.load_dict(white_furnace_scene(principled_clearcoat(cc, gloss), integrator_type="path_tracer", spp=spp))
    img = mi.render(scene, spp=spp, seed=31)
    arr = np.array(img)[..., :3]
    m = arr.mean()
    if cc_base is None:
        cc_base = m  # clearcoat=0 row: must match the zero-specular 1.0000 exactly
    print(f"{cc:>9.1f} {gloss:>6.1f} {spp:>6} {31:>6} {m:>8.4f} {arr.std():>8.4f} {m - cc_base:>+8.4f}")

print(f"\nSheen (zero-specular base, roughness=1.0, white base)")
print(f"{'Sheen':>9} {'Tint':>6} {'SPP':>6} {'Seed':>6} {'Mean':>8} {'Std':>8} {'Delta':>8}")
sh_base = None
for sh, tint in [(0.0, 0.5), (0.5, 0.5), (1.0, 0.0), (1.0, 0.5), (1.0, 1.0)]:
    scene = mi.load_dict(white_furnace_scene(principled_sheen(sh, tint), integrator_type="path_tracer", spp=spp))
    img = mi.render(scene, spp=spp, seed=37)
    arr = np.array(img)[..., :3]
    m = arr.mean()
    if sh_base is None:
        sh_base = m
    print(f"{sh:>9.1f} {tint:>6.1f} {spp:>6} {37:>6} {m:>8.4f} {arr.std():>8.4f} {m - sh_base:>+8.4f}")


"""
SPP Increase.
"""
bsdf = {"type": "principled_bsdf", "base_colour": [1.0, 1.0, 1.0], "roughness": 0.0, "metallic": 0.0}

print("SPP Increase: ")
for spp, seed in [(256, 11), (1024, 11), (1024, 22), (4096, 11)]:
    scene = mi.load_dict(white_furnace_scene(bsdf, integrator_type="path_tracer", spp=spp))
    img = mi.render(scene, spp=spp, seed=seed)
    arr = np.array(img)[..., :3]
    print(f"spp={spp:>5} seed={seed:>3}  mean={arr.mean():.4f}  std={arr.std():.4f}")
