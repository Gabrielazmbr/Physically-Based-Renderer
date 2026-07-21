#!/usr/bin/env -S uv run --script
'''
import mitsuba as mi
mi.set_variant("llvm_ad_rgb")
import numpy as np
from assets.scenes.environment_lighting import environment_lighting_scene

from bsdfs.principled import PrincipledBSDF
from integrators.path_tracer import PathTracer
from emitters.envmap import CustomEnvmap

mi.register_integrator("path_tracer", lambda props: PathTracer(props))
mi.register_bsdf("principled_bsdf", lambda props: PrincipledBSDF(props))
mi.register_bsdf("custom_envmap", lambda props: CustomEnvmap(props))

N_SEEDS = 24  # up from 8
SPP = 16
FLOOR_ROWS = slice(460, 512)
BG_ROWS = slice(0, 150)

def render_repeats(hdri_path, importance, seeds=range(N_SEEDS)):
    imgs = []
    for seed in seeds:
        scene_dict = environment_lighting_scene()
        scene_dict["emitter"] = {
            "type": "custom_envmap",
            "filename": hdri_path,
            "importance": importance,
        }
        scene_dict["sensor"]["sampler"]["sample_count"] = SPP
        scene_dict["sensor"]["sampler"]["seed"] = seed
        scene = mi.load_dict(scene_dict)
        imgs.append(np.array(mi.render(scene, seed=seed)))
    return np.stack(imgs)

def get_region_masks(hdri_path):
    scene_dict = environment_lighting_scene()
    scene_dict["emitter"] = {"type": "custom_envmap", "filename": hdri_path, "importance": True}
    scene = mi.load_dict(scene_dict)
    sensor = scene.sensors()[0]
    film_size = sensor.film().crop_size()

    xs, ys = np.meshgrid(np.arange(film_size.x), np.arange(film_size.y))
    pos = mi.Point2f((xs.flatten() + 0.5), (ys.flatten() + 0.5))
    rays, _ = sensor.sample_ray_differential(
        time=0, sample1=0.5,
        sample2=mi.Point2f(pos.x / film_size.x, pos.y / film_size.y),
        sample3=mi.Point2f(0.5, 0.5),
    )
    si = scene.ray_intersect(rays)
    hit = np.array(si.is_valid()).reshape(film_size.y, film_size.x)

    shapes = scene.shapes()
    shape_ptr = np.array(si.shape, dtype=object).reshape(film_size.y, film_size.x)
    sphere_mask_dr = (si.shape == shapes[0]) & si.is_valid()
    floor_mask_dr  = (si.shape == shapes[1]) & si.is_valid()
    bg_mask_dr     = ~si.is_valid()

    sphere_mask = np.array(sphere_mask_dr).reshape(film_size.y, film_size.x)
    floor_mask  = np.array(floor_mask_dr).reshape(film_size.y, film_size.x)
    bg_mask     = np.array(bg_mask_dr).reshape(film_size.y, film_size.x)
    return bg_mask, sphere_mask, floor_mask

def masked_std(imgs, mask):
    # imgs: (N_SEEDS, H, W, 3); mask: (H, W) bool
    return imgs[:, mask, :].std(axis=0).mean()

def run_comparison_masked(hdri_path, label):
    bg_mask, sphere_mask, floor_mask = get_region_masks(hdri_path)
    uniform_imgs    = render_repeats(hdri_path, importance=False)
    importance_imgs = render_repeats(hdri_path, importance=True)
    print(f"\n--- {label} ({hdri_path}) — exact masks ---")
    for name, mask in [("background", bg_mask), ("sphere", sphere_mask), ("floor", floor_mask)]:
        u = masked_std(uniform_imgs, mask)
        i = masked_std(importance_imgs, mask)
        print(f"{name:12s} n_px={mask.sum():6d}  uniform std={u:.6f}  importance std={i:.6f}  reduction={(1-i/u)*100:.1f}%")

#run_comparison_masked("assets/hdri/venice_sunset_1k.exr", "Venice Sunset (stability check)")
#run_comparison_masked("assets/hdri/sundowner_overlook_1k.exr", "Sundowner Overlook (pathological case)")

def strict_background_mask(bg_mask, erode_px=2):
    # "strict" background = pixels with no hit geometry AND no hit-adjacent
    # neighbor within erode_px, i.e. far enough from any silhouette that
    # AA jitter can't have picked up a sliver of reflection.
    hit_mask = ~bg_mask
    dilated = hit_mask.copy()
    for _ in range(erode_px):
        dilated = (
            dilated
            | np.roll(dilated, 1, axis=0) | np.roll(dilated, -1, axis=0)
            | np.roll(dilated, 1, axis=1) | np.roll(dilated, -1, axis=1)
        )
    return bg_mask & ~dilated

def check_background_independence_strict(hdri_path):
    bg_mask, _, _ = get_region_masks(hdri_path)  # after the drjit-comparison fix
    strict_bg = strict_background_mask(bg_mask, erode_px=2)
    print(f"{hdri_path}: raw bg pixels={bg_mask.sum()}, strict bg pixels={strict_bg.sum()}")

    scene_u = mi.load_dict({**environment_lighting_scene(),
        "emitter": {"type": "custom_envmap", "filename": hdri_path, "importance": False}})
    scene_i = mi.load_dict({**environment_lighting_scene(),
        "emitter": {"type": "custom_envmap", "filename": hdri_path, "importance": True}})
    img_u = np.array(mi.render(scene_u, seed=0))
    img_i = np.array(mi.render(scene_i, seed=0))

    diff = np.abs(img_u[strict_bg] - img_i[strict_bg])
    print(f"strict background: max abs diff = {diff.max():.6f}, mean = {diff.mean():.6f}")

check_background_independence_strict("assets/hdri/venice_sunset_1k.exr")
check_background_independence_strict("assets/hdri/sundowner_overlook_1k.exr")
'''

import os
import numpy as np
import mitsuba as mi

mi.set_variant("llvm_ad_rgb")

# ── Register plugins ────────────────────────────────────────────
from bsdfs.principled import PrincipledBSDF
from integrators.path_tracer import PathTracer
from emitters.envmap import CustomEnvmap

mi.register_integrator("path_tracer", lambda props: PathTracer(props))
mi.register_bsdf("principled_bsdf", lambda props: PrincipledBSDF(props))
mi.register_bsdf("custom_envmap", lambda props: CustomEnvmap(props))

# ── Load scene ────────────────────────────────────────────────
from assets.scenes.material_test import material_test_scene
from assets.scenes.white_furnace import white_furnace_scene
from assets.scenes.cornell_box import cornell_box_scene
from assets.scenes.environment_lighting import environment_lighting_scene


scene_dict = environment_lighting_scene()
scene_name = "environment_lighting_scene_HDRI_sundowner_overlook_MitsubaEnvmap"
test_name = "IBLValidation"
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
