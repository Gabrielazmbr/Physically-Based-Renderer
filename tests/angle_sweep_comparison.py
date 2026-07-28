#!/usr/bin/env -S uv run --script
"""
Direct eval() comparison: diffuse_model="lambert" vs "burley", same
BSDF, same material parameters, across a roughness x angle sweep.
Confirms the predicted pattern: ratio == 1.0 always at normal
incidence (theta_i=theta_o=0, FD_i=FD_o=1 regardless of roughness);
away from normal incidence, low roughness gives mild darkening
(ratio<1), higher roughness gives the characteristic grazing
brightening (ratio>1).
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

for roughness in [0.1, 0.5, 0.9]:
    lambert = mi.load_dict({"type": "principled_bsdf", "diffuse_model": "lambert",
                             "base_colour": [1.0,1.0,1.0], "roughness": roughness, "metallic": 0.0})
    burley  = mi.load_dict({"type": "principled_bsdf", "diffuse_model": "burley",
                             "base_colour": [1.0,1.0,1.0], "roughness": roughness, "metallic": 0.0})
    print(f"\nroughness={roughness}")
    for ti_deg in [0, 30, 60, 80]:
        si = make_si(ti_deg)
        for to_deg in [0, 30, 60, 80]:
            to = math.radians(to_deg)
            wo = mi.Vector3f(math.sin(to), 0.0, math.cos(to))
            v_lambert = float(np.array(lambert.eval(ctx, si, wo)).flatten()[0])
            v_burley  = float(np.array(burley.eval(ctx, si, wo)).flatten()[0])
            ratio = v_burley / max(v_lambert, 1e-9)
            print(f"  theta_i={ti_deg:>3} theta_o={to_deg:>3}  lambert={v_lambert:.4f}  burley={v_burley:.4f}  ratio={ratio:.4f}")
