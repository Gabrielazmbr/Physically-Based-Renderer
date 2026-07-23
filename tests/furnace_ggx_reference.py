#!/usr/bin/env -S uv run --script
"""
Section 2: GGX energy-loss reference comparison.
Uses Mitsuba's own `roughconductor` (GGX) BSDF paired with
custom path tracer, vs. Mitsuba's own reference path tracer using
the identical BSDF. alpha = roughness^2 throughout, matching
principled_bsdf's own convention, so "roughness" here is the same
physical surface as in furnace_principled.py.
"""
import _common  # noqa: F401
import numpy as np
import mitsuba as mi
from assets.scenes.white_furnace import white_furnace_scene

roughconductor = lambda alpha: {"type": "roughconductor", "distribution": "ggx", "alpha": alpha}
roughness_values = [0.0, 0.5, 1.0]

configs = []
for r in roughness_values:
    alpha = max(r * r, 1e-4)
    configs.append((r, alpha, "path_tracer", 56))
    configs.append((r, alpha, "path",        43))

print(f"{'Roughness':>9} {'Integrator':<12} {'SPP':>6} {'Seed':>6} {'Mean':>8} {'Std':>8}")
for roughness, alpha, integrator_type, seed in configs:
    scene = mi.load_dict(white_furnace_scene(roughconductor(alpha), integrator_type=integrator_type, spp=256))
    img = mi.render(scene, spp=256, seed=seed)
    arr = np.array(img)
    print(f"{roughness:>9.1f} {integrator_type:<12} {256:>6} {seed:>6} {arr.mean():>8.4f} {arr.std():>8.4f}")
