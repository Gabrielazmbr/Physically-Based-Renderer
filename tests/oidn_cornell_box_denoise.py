#!/usr/bin/env -S uv run --script
"""
OIDN validation — Cornell box, box rfilter, emitter-composited.

Reports RMSE both overall and excluding directly-visible emitter pixels.
The emitter region is restored from the noisy input by denoise_composite
(OIDN's albedo demodulation is invalid for emissive surfaces), so error
there reflects the noisy render, not the denoiser. Because that region is
very bright, it still dominates a quadratic metric despite covering <1%
of pixels — hence reporting both.
"""
import _common
import numpy as np
import mitsuba as mi
from denoisers.oidn import denoise, denoise_composite
from assets.scenes.cornell_box import cornell_box_scene

GT_SPP = 1024
SWEEP_SPP = [16, 32, 64, 128, 256, 512]
SEED = 5

def render(spp, with_aovs=False):
    d = cornell_box_scene()
    d["integrator"] = {"type": "path_tracer", "max_depth": 8, "with_aovs": with_aovs}
    d["sensor"]["film"] = {"type": "hdrfilm", "width": 400, "height": 400,
                           "rfilter": {"type": "box"}}  # box: OIDN needs uncorrelated noise
    d["sensor"]["sampler"] = {"type": "independent", "sample_count": spp}
    return np.array(mi.render(mi.load_dict(d), spp=spp, seed=SEED))

def rmse(a, b, mask=None):
    d2 = (a - b) ** 2
    return float(np.sqrt(np.mean(d2[mask] if mask is not None else d2)))

print(f"Ground truth at {GT_SPP} spp...")
gt = np.ascontiguousarray(render(GT_SPP)[..., :3])
dark = (gt.mean(axis=-1) <= 2.0)[..., None].repeat(3, -1)   # everything but the emitter
print(f"Emitter covers {100*(1-dark[...,0].mean()):.2f}% of pixels\n")

print(f"{'spp':>5} | {'noisy':>9} {'denoised':>9} {'change':>8} | "
      f"{'noisy*':>9} {'denoised*':>9} {'change*':>8}   (* = excluding emitter)")
results = {}
for spp in SWEEP_SPP:
    full = render(spp, with_aovs=True)
    noisy  = np.ascontiguousarray(full[..., 0:3])
    albedo = np.ascontiguousarray(full[..., 3:6])
    normal = np.ascontiguousarray(full[..., 6:9])
    den = denoise_composite(noisy, albedo, normal, emitter_threshold=2.0)

    rn,  rd  = rmse(noisy, gt),       rmse(den, gt)
    rnd, rdd = rmse(noisy, gt, dark), rmse(den, gt, dark)
    results[spp] = (rn, rd, rnd, rdd)
    print(f"{spp:>5} | {rn:>9.5f} {rd:>9.5f} {100*(1-rd/rn):>7.1f}% | "
          f"{rnd:>9.5f} {rdd:>9.5f} {100*(1-rdd/rnd):>7.1f}%")

    if spp == 16:
        mi.util.write_bitmap("outputs/Denoise/final_16_noisy.png", noisy)
        mi.util.write_bitmap("outputs/Denoise/final_16_denoised.png", den)

# Effective sample multiplier, measured on the region the denoiser acts on
d16 = results[SWEEP_SPP[0]][3]
match = [s for s in SWEEP_SPP if results[s][2] <= d16]
print(f"\nDenoised 16 spp (excl. emitter) RMSE = {d16:.5f}")
print(f"  undenoised needs >= {match[0] if match else '>512'} spp to match "
      f"-> effective sample multiplier ~{(match[0]/16) if match else '>32'}x")
