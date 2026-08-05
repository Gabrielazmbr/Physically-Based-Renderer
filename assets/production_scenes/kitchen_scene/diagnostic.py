#!/usr/bin/env -S uv run --script
"""
DIAGNOSTIC: compare _shadow_ray_occluded against Mitsuba's built-in
visibility test on identical NEE samples. Any disagreement is light
this implementation is losing (or gaining) versus the reference.
"""
import os, sys
sys.path.insert(0, os.path.abspath('../../../'))
import numpy as np, mitsuba as mi, drjit as dr
mi.set_variant('llvm_ad_rgb')
from bsdfs.principled import PrincipledBSDF
from emitters.envmap import CustomEnvmap
from integrators.path_tracer import PathTracer
from cameras.physical_camera import PhysicalCamera
mi.register_bsdf('principled_bsdf', lambda p: PrincipledBSDF(p))
mi.register_emitter('custom_envmap', lambda p: CustomEnvmap(p))
mi.register_integrator('path_tracer', lambda p: PathTracer(p))
mi.register_sensor('physical_camera', lambda p: PhysicalCamera(p))

scene = mi.load_file('scene.xml', resx=320, resy=240)
sensor = scene.sensors()[0]
integrator = scene.integrator()

sampler = mi.load_dict({'type': 'independent'})
N = 200000
sampler.seed(0, N)

# primary hits across the frame
uv = mi.Point2f(sampler.next_1d(), sampler.next_1d())
ray, _ = sensor.sample_ray(0.0, 0.5, uv, mi.Point2f(0.5, 0.5), True)
si = scene.ray_intersect(ray)
active = si.is_valid()

# Mitsuba's own test (visibility ON) vs raw sample (visibility OFF)
ds_ref, w_ref = scene.sample_emitter_direction(si, sampler.next_2d(), True, active)
ds_raw, w_raw = scene.sample_emitter_direction(si, sampler.next_2d(), False, active)

mine = integrator._shadow_ray_occluded(scene, si, ds_raw, active)

ref_blocked = np.array(active & (dr.max(w_ref) <= 0)).flatten()
mine_blocked = np.array(mine).flatten()
act = np.array(active).flatten()

n = act.sum()
print(f'active shadow rays: {n}')
print(f'  Mitsuba says blocked: {(ref_blocked & act).sum()}  ({100*(ref_blocked&act).sum()/n:.2f}%)')
print(f'  mine says blocked:    {(mine_blocked & act).sum()}  ({100*(mine_blocked&act).sum()/n:.2f}%)')
over  = (mine_blocked & ~ref_blocked & act).sum()
under = (~mine_blocked & ref_blocked & act).sum()
print()
print(f'  I block but Mitsuba does NOT (light lost): {over}  ({100*over/n:.2f}%)')
print(f'  Mitsuba blocks but I do NOT (expected -- glass/null): {under}  ({100*under/n:.2f}%)')
