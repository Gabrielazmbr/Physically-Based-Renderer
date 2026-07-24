#!/usr/bin/env -S uv run --script
"""
Compares per-pixel noise across three CDF configurations for
CustomEnvmap's importance sampling, isolating resolution and pooling
method as separate variables. Sampler type held fixed at independent
(the validated default), same HDRI and methodology as the stratified
sampler comparison, so only the CDF configuration changes.
"""
import _common
import numpy as np
import mitsuba as mi
from assets.scenes.environment_lighting import environment_lighting_scene

HDRI = "assets/hdri/sundowner_overlook_1k.exr"
SPP = 16
N_SEEDS = 24

CONFIGS = [
    ("baseline (256x128, mean)",   {"cdf_res_x": 256, "cdf_res_y": 128, "cdf_pooling": "mean"}),
    ("same res, max-pooled",       {"cdf_res_x": 256, "cdf_res_y": 128, "cdf_pooling": "max"}),
    ("higher res (512x256), mean", {"cdf_res_x": 512, "cdf_res_y": 256, "cdf_pooling": "mean"}),
    ("baseline (256x128, mean)",   {"cdf_res_x": 256, "cdf_res_y": 128, "cdf_pooling": "mean"}),
    ("same res, max-pooled",       {"cdf_res_x": 256, "cdf_res_y": 128, "cdf_pooling": "max"}),
    ("higher res (512x256), mean", {"cdf_res_x": 512, "cdf_res_y": 256, "cdf_pooling": "mean"}),
    ("higher res (512x256), max",  {"cdf_res_x": 512, "cdf_res_y": 256, "cdf_pooling": "max"}),

]


def build_scene(envmap_overrides):
    scene_dict = environment_lighting_scene(HDRI)
    scene_dict["sensor"]["sampler"] = {"type": "independent", "sample_count": SPP}
    scene_dict["emitter"] = {"type": "custom_envmap", "filename": HDRI, "importance": True, **envmap_overrides}
    return mi.load_dict(scene_dict)

def measure_noise(envmap_overrides):
    scene = build_scene(envmap_overrides)
    imgs = [np.array(mi.render(scene, spp=SPP, seed=seed)) for seed in range(N_SEEDS)]
    stack = np.stack(imgs, axis=0)
    return stack.std(axis=0).mean()

print(f"{'Config':>28} {'Mean per-pixel std':>20}")
for label, overrides in CONFIGS:
    noise = measure_noise(overrides)
    print(f"{label:>28} {noise:>20.5f}")
