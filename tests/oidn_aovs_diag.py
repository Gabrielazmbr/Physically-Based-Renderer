#!/usr/bin/env -S uv run --script
"""
Is OIDN broken, or are our AOVs feeding it something degenerate?
"""
import _common
import numpy as np
import mitsuba as mi
import pyoidn
from assets.scenes.environment_lighting import environment_lighting_scene

HDRI = "assets/hdri/sundowner_overlook_1k.exr"

d = environment_lighting_scene(HDRI)
d["integrator"] = {"type": "path_tracer", "max_depth": 8, "with_aovs": True}
d["sensor"]["film"] = {"type": "hdrfilm", "width": 400, "height": 400}
d["sensor"]["sampler"] = {"type": "independent", "sample_count": 16}
full = np.array(mi.render(mi.load_dict(d), spp=16, seed=5))
color, albedo, normal = full[..., 0:3], full[..., 3:6], full[..., 6:9]

def run(color_in, albedo_in=None, normal_in=None, hdr=True, label=""):
    c = np.ascontiguousarray(color_in, dtype=np.float32)
    out = np.zeros_like(c)
    dev = pyoidn.Device(pyoidn.OIDN_DEVICE_TYPE_CPU); dev.commit()
    flt = pyoidn.Filter(dev, "RT")
    flt.set_image(pyoidn.OIDN_IMAGE_COLOR, c, pyoidn.OIDN_FORMAT_FLOAT3)
    if albedo_in is not None:
        flt.set_image(pyoidn.OIDN_IMAGE_ALBEDO,
                      np.ascontiguousarray(albedo_in, dtype=np.float32),
                      pyoidn.OIDN_FORMAT_FLOAT3)
    if normal_in is not None:
        flt.set_image(pyoidn.OIDN_IMAGE_NORMAL,
                      np.ascontiguousarray(normal_in, dtype=np.float32),
                      pyoidn.OIDN_FORMAT_FLOAT3)
    flt.set_image(pyoidn.OIDN_IMAGE_OUTPUT, out, pyoidn.OIDN_FORMAT_FLOAT3)
    flt.set_bool("hdr", hdr)
    flt.commit(); flt.execute()
    err = dev.get_error(); flt.release(); dev.release()
    if err:
        print(f"  {label}: ERROR {err}"); return None
    print(f"  {label:<40} mean|out-in| = {np.abs(out - c).mean():.5f}")
    return out

print("A. Does the choice of auxiliary buffers matter?")
run(color, albedo, normal, label="1. colour + albedo + normal")
run(color, albedo, None,   label="2. colour + albedo only")
run(color, None,   normal, label="3. colour + normal only")
den_c = run(color, None,   None,   label="4. colour ONLY (no aux buffers)")

print("\nB. Control: does OIDN denoise obviously-noisy input?")
gt = np.array(mi.render(mi.load_dict({**d, "integrator": {"type": "path_tracer", "max_depth": 8}}), spp=512, seed=5))[..., :3]
rng = np.random.default_rng(0)
synthetic = np.clip(gt + rng.normal(0, 0.15, gt.shape), 0, None).astype(np.float32)
den_s = run(synthetic, None, None, label="5. GT + gaussian noise, colour only")
if den_s is not None:
    r = lambda a, b: float(np.sqrt(np.mean((a - b) ** 2)))
    print(f"     RMSE vs GT: noisy {r(synthetic, gt):.5f} - denoised {r(den_s, gt):.5f}")

if den_c is not None:
    mi.util.write_bitmap("outputs/Denoise/diag_colour_only.png", den_c)
