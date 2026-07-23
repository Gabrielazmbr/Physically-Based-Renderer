#!/usr/bin/env -S uv run --script
"""
tests/diag_texture_uv.py
Confirms PrincipledBSDF's texture-parameter helpers (_base_colour_at,
_roughness_at, _metallic_at) actually read si.uv and vary spatially,
rather than silently returning one constant everywhere.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import mitsuba as mi
mi.set_variant("llvm_ad_rgb")
import drjit as dr

from bsdfs.principled import PrincipledBSDF
mi.register_bsdf("principled_bsdf", lambda props: PrincipledBSDF(props))

checker = mi.load_dict({
    "type": "checkerboard",
    "color0": {"type": "rgb", "value": [0.05, 0.05, 0.05]},
    "color1": {"type": "rgb", "value": [1.0, 1.0, 1.0]},
    "to_uv": mi.ScalarTransform4f().scale([4, 4, 1]),
})
bsdf = mi.load_dict({
    "type": "principled_bsdf",
    "base_colour": [0.8, 0.8, 0.8],
    "roughness": checker,
    "metallic": 0.0,
})

def si_at_uv(u, v):
    si = dr.zeros(mi.SurfaceInteraction3f)
    si.uv = mi.Point2f(u, v)
    si.n = mi.Vector3f(0, 0, 1)
    si.sh_frame = mi.Frame3f(si.n)
    si.wi = mi.Vector3f(0, 0, 1)
    return si

# (u, v, expected) — expected computed directly from the verified tiling rule
test_points = [
    (0.05, 0.05, 1.00),
    (0.15, 0.05, 0.05),
    (0.05, 0.15, 0.05),
    (0.15, 0.15, 1.00),
    (0.30, 0.05, 1.00),
]

print(f"{'u':>5} {'v':>5} {'roughness':>10} {'expected':>10} {'result':>8}")
all_pass = True
for u, v, expected in test_points:
    si = si_at_uv(u, v)
    r = float(np.array(bsdf._roughness_at(si)).flatten()[0])
    ok = abs(r - expected) < 1e-3
    all_pass &= ok
    print(f"{u:>5.2f} {v:>5.2f} {r:>10.4f} {expected:>10.4f} {'PASS' if ok else 'FAIL':>8}")

print("\nUV texture lookup:", "PASS" if all_pass else "FAIL")

# --- render a small scene to see the effect visually ---
if os.environ.get("RENDER_DEMO") == "1":
    import _common  # registers path_tracer, principled_bsdf, etc.

    scene = mi.load_dict({
        "type": "scene",
        "integrator": {"type": "path_tracer", "max_depth": 8},
        "sensor": {
            "type": "perspective",
            "fov": 35,
            "to_world": mi.ScalarTransform4f().look_at(
                origin=[0, -6, 1.5], target=[0, 0, 0], up=[0, 0, 1]
            ),
            "film": {"type": "hdrfilm", "width": 600, "height": 450},
            "sampler": {"type": "independent", "sample_count": 256},
        },
        # Real spatial detail is what makes roughness variation visible —
        # a flat/constant environment can't show sharp-vs-blurred reflection.
        "env": {"type": "envmap", "filename": "assets/hdri/studio_kontrast_04_1k.exr"},
        "sphere": {
            "type": "sphere",
            "bsdf": {
                "type": "principled_bsdf",
                "base_colour": [0.6, 0.6, 0.6],
                "roughness": checker,
                "metallic": 0.0,
            },
        },
    })
    img = mi.render(scene, spp=256)
    os.makedirs("outputs/diagnostics", exist_ok=True)
    mi.util.write_bitmap("outputs/diagnostics/checker_roughness_demo.png", img)
    print("\nRendered to outputs/diagnostics/checker_roughness_demo.png")
