#!/usr/bin/env -S uv run --script
"""
Glass validation, reference-comparison style: custom principled_bsdf
with transmission vs Mitsuba's own smooth `dielectric`, matched IOR.
Checks the three things that define correct smooth transmission:
  1. Fresnel reflect/transmit split ratio
  2. Per-branch weights (reflect=1, transmit=1/eta^2 radiance scaling)
  3. Total internal reflection past the critical angle
Also confirms eval()/pdf() return zero, per the delta-lobe convention.
"""
import _common
import math
import numpy as np
import mitsuba as mi
import drjit as dr

IOR = 1.5
N = 200000
ctx = mi.BSDFContext()
sampler = mi.load_dict({"type": "independent"})

def make_si(theta_deg, from_inside=False):
    t = math.radians(theta_deg)
    z = -math.cos(t) if from_inside else math.cos(t)
    si = dr.zeros(mi.SurfaceInteraction3f)
    si.wi = mi.Vector3f(dr.full(mi.Float, math.sin(t), N),
                        dr.zeros(mi.Float, N),
                        dr.full(mi.Float, z, N))
    si.n = mi.Vector3f(0, 0, 1)
    si.sh_frame = mi.Frame3f(si.n)
    si.wavelengths = mi.Color0f()
    return si

def stats(bsdf, theta, from_inside=False, seed=0):
    si = make_si(theta, from_inside)
    sampler.seed(seed, N)
    bs, w = bsdf.sample(ctx, si, sampler.next_1d(), sampler.next_2d())
    cos_o = np.array(mi.Frame3f.cos_theta(bs.wo))
    weights = np.array(w.x)
    # Reflection keeps wo on the SAME side as wi. For rays arriving from inside
    # (cos_theta_i < 0) that means cos_o < 0 — the opposite of the outside case.
    cos_i = -math.cos(math.radians(theta)) if from_inside else math.cos(math.radians(theta))
    refl = (cos_o > 0) if cos_i > 0 else (cos_o < 0)
    return {
        "refl_frac": refl.mean(),
        "w_refl": weights[refl].mean() if refl.any() else float("nan"),
        "w_tran": weights[~refl].mean() if (~refl).any() else float("nan"),
    }

mine = mi.load_dict({"type": "principled_bsdf", "base_colour": [1.0,1.0,1.0], "roughness": 0.0, "metallic": 0.0, "transmission": 1.0, "ior": IOR})
ref = mi.load_dict({"type": "dielectric", "int_ior": IOR, "ext_ior": 1.0})

print("=== 1. Entering the surface (outside - inside) ===")
print(f"{'theta':>6} {'':>10} {'refl frac':>10} {'w_refl':>9} {'w_tran':>9}")
for theta in [10, 45, 70, 85]:
    F = float(mi.fresnel(mi.Float(math.cos(math.radians(theta))), mi.Float(IOR))[0][0])
    for label, b in [("mine", mine), ("dielectric", ref)]:
        s = stats(b, theta)
        print(f"{theta:>6} {label:>10} {s['refl_frac']:>10.4f} {s['w_refl']:>9.4f} {s['w_tran']:>9.4f}")
    print(f"{'':>6} {'(Fresnel F)':>10} {F:>10.4f}   expected w_tran = {1/IOR**2:.4f}")

print("\n=== 2. Total internal reflection (inside - outside) ===")
crit = math.degrees(math.asin(1.0/IOR))
print(f"  critical angle = {crit:.2f} deg; past it, refl frac must be 1.0")
print(f"{'theta':>6} {'':>10} {'refl frac':>10}")
for theta in [20, 40, crit - 2, crit + 2, 60]:
    for label, b in [("mine", mine), ("dielectric", ref)]:
        s = stats(b, theta, from_inside=True)
        print(f"{theta:>6.1f} {label:>10} {s['refl_frac']:>10.4f}")

print("\n=== 3. Delta-lobe convention: eval()/pdf() must be zero ===")
si1 = make_si(30)
wo = mi.Vector3f(0.2, 0.0, -0.9)
for label, b in [("mine", mine), ("dielectric", ref)]:
    e = float(np.array(b.eval(ctx, si1, wo)).flatten()[0])
    p = float(np.array(b.pdf(ctx, si1, wo)).flatten()[0])
    print(f"  {label:>10}: eval={e:.6f}  pdf={p:.6f}")
