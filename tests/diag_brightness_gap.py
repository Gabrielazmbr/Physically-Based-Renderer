#!/usr/bin/env -S uv run --script
"""
Direct eval() comparison: principled_bsdf vs Mitsuba's built-in
principled, at the exact material parameters the Blender export used
(base_color=0.8 grey, metallic=0, specular=0.5 -> F0=0.04, matching
hardcoded dielectric F0 exactly), across a roughness sweep. If the ratio
grows with roughness, that's the multi-scatter compensation signature;
if it's flat, it's something else.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import math
import numpy as np
import mitsuba as mi
mi.set_variant("llvm_ad_rgb")
import drjit as dr

from bsdfs.principled import PrincipledBSDF
mi.register_bsdf("principled_bsdf", lambda props: PrincipledBSDF(props))

ctx = mi.BSDFContext()

def make_si(theta_i_deg):
    si = dr.zeros(mi.SurfaceInteraction3f)
    ti = math.radians(theta_i_deg)
    si.wi = mi.Vector3f(math.sin(ti), 0.0, math.cos(ti))
    si.n = mi.Vector3f(0, 0, 1)
    si.sh_frame = mi.Frame3f(si.n)
    return si

for roughness in [0.05, 0.25, 0.5, 0.8]:
    mine = mi.load_dict({"type": "principled_bsdf", "base_colour": [0.8, 0.8, 0.8],
                         "roughness": roughness, "metallic": 0.0})
    ref = mi.load_dict({
        "type": "principled",
        "base_color": {"type": "rgb", "value": [0.8, 0.8, 0.8]},
        "roughness": roughness, "metallic": 0.0, "specular": 0.5,
        "spec_tint": {"type": "rgb", "value": [1.0, 1.0, 1.0]},
        "spec_trans": 0.0, "anisotropic": 0.0, "sheen": 0.0,
        "sheen_tint": {"type": "rgb", "value": [1.0, 1.0, 1.0]},
        "clearcoat": 0.0, "clearcoat_gloss": 0.0009,
    })
    print(f"\nroughness={roughness}")
    for ti_deg in [10, 30, 50, 70]:
        si = make_si(ti_deg)
        for to_deg in [10, 30, 50, 70]:
            to = math.radians(to_deg)
            wo = mi.Vector3f(math.sin(to), 0.0, math.cos(to))
            v_mine = float(np.array(mine.eval(ctx, si, wo)).flatten()[0])
            v_ref = float(np.array(ref.eval(ctx, si, wo)).flatten()[0])
            ratio = v_ref / max(v_mine, 1e-9)
            print(f"  theta_i={ti_deg:>3} theta_o={to_deg:>3}  mine={v_mine:.4f}  ref={v_ref:.4f}  ratio={ratio:.4f}")
