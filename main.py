#!/usr/bin/env -S uv run --script

import os
import numpy as np
import mitsuba as mi

mi.set_variant("llvm_ad_rgb")

# ── Register plugins ────────────────────────────────────────────
from bsdfs.principled import PrincipledBSDF
from integrators.path_tracer import PathTracer

mi.register_integrator("path_tracer", lambda props: PathTracer(props))
mi.register_bsdf("principled_bsdf", lambda props: PrincipledBSDF(props))

# ── Load scene ────────────────────────────────────────────────
from assets.scenes.material_test import material_test_scene
from assets.scenes.white_furnace import white_furnace_scene
from assets.scenes.cornell_box import cornell_box_scene


scene_dict = material_test_scene()
scene_name = "material_test"
test_name = "PathTracerValidation"
spp = 256

# ───────────────────────────────────────────────────────────────


def save_render(img, scene_name, test_name):
    os.makedirs(f"outputs/{test_name}", exist_ok=True)
    existing = [
        f for f in os.listdir(f"outputs/{test_name}") if f.startswith(scene_name)
    ]
    index = len(existing) + 1
    path = f"outputs/{test_name}/{scene_name}_{index:02d}.exr"
    mi.Bitmap(img).write(path)
    print(f"Saved: {path}")
    return path


scene = mi.load_dict(scene_dict)
img = mi.render(scene, spp=spp)
save_render(img, scene_name, test_name)

'''

img_np = np.array(mi.Bitmap(img))
print(f"Min: {img_np.min():.4f}")
print(f"Max: {img_np.max():.4f}")
print(f"Mean: {img_np.mean():.4f}")
print(f"Std: {img_np.std():.4f}")

'''
