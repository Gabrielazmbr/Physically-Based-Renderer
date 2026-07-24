#!/usr/bin/env -S uv run --script
"""
Compares per-pixel noise with and without MIS envmap compensation
(Karlik et al. 2019). 24 seeds, per-pixel std across repeats.
CDF resolution/pooling held at validated defaults so only
mis_compensation changes.
"""
import _common
import numpy as np
import mitsuba as mi
from assets.scenes.environment_lighting import environment_lighting_scene

HDRI = "assets/hdri/studio_kontrast_04_1k.exr"
SPP = 16
N_SEEDS = 24

def build_scene(mis_compensation):
    scene_dict = environment_lighting_scene(HDRI)
    scene_dict["sensor"]["sampler"] = {"type": "independent", "sample_count": SPP}
    scene_dict["emitter"] = {
        "type": "custom_envmap", "filename": HDRI, "importance": True,
        "mis_compensation": mis_compensation,
    }
    return mi.load_dict(scene_dict)

def measure_noise(mis_compensation):
    scene = build_scene(mis_compensation)
    imgs = [np.array(mi.render(scene, spp=SPP, seed=seed)) for seed in range(N_SEEDS)]
    return np.stack(imgs, axis=0).std(axis=0).mean()

print(HDRI)
print(f"{'Config':>24} {'Mean per-pixel std':>20}")
for label, comp in [("compensation off", False), ("compensation on", True)]:
    print(f"{label:>24} {measure_noise(comp):>20.5f}")
