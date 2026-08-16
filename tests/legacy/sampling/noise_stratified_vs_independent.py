#!/usr/bin/env -S uv run --script
"""
Compares per-pixel noise between the independent and stratified
samplers, at equal spp. Holding scene, HDRI, and the already-validated
importance-sampled CustomEnvmap remain fixed, so the sampler type is the only
variable.
"""
import _common
import numpy as np
import mitsuba as mi
from assets.scenes.environment_lighting import environment_lighting_scene

HDRI = "assets/hdri/sundowner_overlook_1k.exr"  # highest energy-concentration HDRI, the case most likely to expose a sampler-quality difference
SPP = 16  # must be a perfect square for the stratified sampler (16 = 4x4), also matches Week 6's own spp choice
N_SEEDS = 24  # matches Week 6 methodology

def build_scene(sampler_type):
    scene_dict = environment_lighting_scene(HDRI)
    scene_dict["sensor"]["sampler"] = {"type": sampler_type, "sample_count": SPP}
    scene_dict["emitter"] = {"type": "custom_envmap", "filename": HDRI, "importance": True, "mis_compensation": False}
    return mi.load_dict(scene_dict)

def measure_noise(sampler_type):
    scene = build_scene(sampler_type)
    imgs = [np.array(mi.render(scene, spp=SPP, seed=seed)) for seed in range(N_SEEDS)]
    stack = np.stack(imgs, axis=0)  # (N_SEEDS, H, W, 3)
    per_pixel_std = stack.std(axis=0)
    return per_pixel_std.mean()

print(f"{'Sampler':>12} {'Mean per-pixel std':>20}")
for sampler_type in ["independent", "stratified"]:
    noise = measure_noise(sampler_type)
    print(f"{sampler_type:>12} {noise:>20.5f}")
