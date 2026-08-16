#!/usr/bin/env -S uv run --script
"""
Directional albedo, importance-sampled via the BSDF's own sample()
(valid at any roughness)

  albedo_sample = E[ weight returned by sample() ]
  albedo_eval   = E[ eval(wo) / pdf(wo) ],  wo ~ sample()

Both estimate the same integral. Divergence => sample() and eval()/pdf()
disagree. Either exceeding 1.0 => energy gain in the model.
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
N = 1 << 22
sampler = mi.load_dict({"type": "independent"})

def albedo_pair(bsdf, theta_i_deg, seed=0):
    sampler.seed(seed, N)
    ti = math.radians(theta_i_deg)
    si = dr.zeros(mi.SurfaceInteraction3f)
    si.wi = mi.Vector3f(dr.full(mi.Float, math.sin(ti), N),
                        dr.zeros(mi.Float, N),
                        dr.full(mi.Float, math.cos(ti), N))
    si.n = mi.Vector3f(0, 0, 1)
    si.sh_frame = mi.Frame3f(si.n)

    bs, weight = bsdf.sample(ctx, si, sampler.next_1d(), sampler.next_2d())
    a_sample = float(np.array(weight.x).mean())

    val = bsdf.eval(ctx, si, bs.wo)
    ratio = dr.select(bs.pdf > 0, val.x / dr.maximum(bs.pdf, 1e-12), mi.Float(0))
    a_eval = float(np.array(ratio).mean())
    return a_sample, a_eval

print(f"{'metallic':>8} {'rough':>6} {'theta_i':>8} {'a_sample':>9} {'a_eval':>9}")
for metallic in [0.0, 1.0]:
    for roughness in [0.0, 0.1, 0.5, 1.0]:
        b = mi.load_dict({"type": "principled_bsdf",
                          "base_colour": [1.0, 1.0, 1.0],
                          "roughness": roughness,
                          "metallic": metallic})
        for t in (10, 30, 50, 70, 85):
            a_s, a_e = albedo_pair(b, t)
            print(f"{metallic:>8.1f} {roughness:>6.1f} {t:>8} {a_s:>9.4f} {a_e:>9.4f}")

print("\n--- control: Mitsuba roughconductor (same harness) ---")
print(f"{'alpha':>6} {'theta_i':>8} {'a_sample':>9}")
for alpha in [0.25, 1.0]:          # = roughness 0.5 and 1.0, since alpha = roughness^2
    rc = mi.load_dict({"type": "roughconductor", "distribution": "ggx",
                       "alpha": alpha, "material": "none"})
    for t in (10, 50, 85):
        a_s, _ = albedo_pair(rc, t)
        print(f"{alpha:>6.2f} {t:>8} {a_s:>9.4f}")
