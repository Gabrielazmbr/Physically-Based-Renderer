#!/usr/bin/env -S uv run --script
"""
Test: max_transparent_shadow_depth boundary.

Fires NEE shadow rays through a stack of N thin glass panes at a diffuse
receiver, sweeping N past the cap (default 8). Confirms the cap engages and
fails CONSERVATIVELY (treats over-budget as blocked) rather than leaking.

Expected: receiver lit for N <= cap, dark for N > cap. The transition IS
the test. Also reports the per-pane Fresnel falloff below the cap.
"""
import os
import sys
import _common
sys.path.insert(0, os.path.abspath('..'))

import numpy as np
import mitsuba as mi
mi.set_variant('llvm_ad_rgb')

from bsdfs.principled import PrincipledBSDF
from integrators.path_tracer import PathTracer
mi.register_bsdf('principled_bsdf', lambda p: PrincipledBSDF(p))
mi.register_integrator('path_tracer', lambda p: PathTracer(p))

CAP = 8
SPP = 1024


def build(n_panes, transparent_shadows):
    """
    Receiver at z=0 facing +z. Panes stacked between receiver and light.
    Zero-specular diffuse receiver so brightness reads only the transmitted
    light, with no specular lobe confusing the measurement.
    """
    scene = {
        'type': 'scene',
        'integrator': {
            'type': 'path_tracer',
            'max_depth': 4,
            'transparent_shadows': transparent_shadows,
            'max_transparent_shadow_depth': CAP,
        },
        'sensor': {
            'type': 'perspective',
            'fov': 30,
            # Camera on the +z side: the rectangle's normal is +z, and
            # principled_bsdf is front-side only, so viewing from -z hits the
            # unlit back face and returns exactly zero (measured: dot(d,n)=+1).
            'to_world': mi.ScalarTransform4f().look_at(
                origin=[2.5, 2.5, 4.0], target=[0, 0, 0], up=[0, 1, 0]),
            'sampler': {'type': 'independent', 'sample_count': SPP},
            'film': {'type': 'hdrfilm', 'width': 64, 'height': 64,
                     'pixel_format': 'rgb', 'rfilter': {'type': 'box'}},
        },
        'receiver': {
            'type': 'rectangle',
            'to_world': mi.ScalarTransform4f().scale([1, 1, 1]),
            'bsdf': {
                'type': 'principled_bsdf',
                'base_colour': [1.0, 1.0, 1.0],
                'roughness': 1.0,
                'metallic': 0.0,
                'specular': 0.0,   # true Lambertian -- no specular lobe
            },
        },
        'light': {
            'type': 'rectangle',
            # z=8 (was 5) to leave a camera gap past the pane stack
            'to_world': (mi.ScalarTransform4f().translate([0, 0, 8])
                         @ mi.ScalarTransform4f().rotate(axis=[0, 1, 0], angle=180)
                         @ mi.ScalarTransform4f().scale([2, 2, 1])),
            'emitter': {'type': 'area', 'radiance': {'type': 'rgb', 'value': 10.0}},
        },
    }
    # Panes evenly spaced between receiver (z=0) and light (z=5)
    for i in range(n_panes):
        z = 1.0 + i * 0.15
        scene[f'pane_{i}'] = {
            'type': 'rectangle',
            'to_world': (mi.ScalarTransform4f().translate([0, 0, z])
                         @ mi.ScalarTransform4f().scale([2, 2, 1])),
            'bsdf': {
                'type': 'principled_bsdf',
                'base_colour': [1.0, 1.0, 1.0],
                'roughness': 0.0,
                'metallic': 0.0,
                'specular': 0.5,
                'transmission': 1.0,
                'ior': 1.5,
                'thin': True,
            },
        }
    return mi.load_dict(scene)


def mean_brightness(n_panes, transparent_shadows):
    scene = build(n_panes, transparent_shadows)
    img = mi.render(scene, spp=SPP, seed=0)
    arr = np.array(img, dtype=np.float32)
    h, w = arr.shape[:2]
    # Central crop: receiver only, avoiding edges/background
    c = arr[h//4:3*h//4, w//4:3*w//4, :3]
    return float(c.mean())


print(f'max_transparent_shadow_depth = {CAP}, spp = {SPP}\n')
print(f'{"panes":>6} {"OFF":>10} {"ON":>10} {"ON/OFF":>9}  expected')
print('-' * 52)

# --- Diagnostic: is the n=0 scene even lit? -----------------------------
sc = build(0, False)
img = mi.render(sc, spp=SPP, seed=0)
arr = np.array(img, dtype=np.float32)
print(f'DIAG n=0: img min={arr.min():.6f} max={arr.max():.6f} mean={arr.mean():.6f}')
print(f'DIAG n=0: nonzero pixels = {(arr > 1e-6).sum()} / {arr.size}')
si_test = sc.ray_intersect(mi.Ray3f(o=mi.Point3f(0, 0, -3), d=mi.Vector3f(0, 0, 1)))
print(f'DIAG center ray hit: {bool(si_test.is_valid()[0])}')
if bool(si_test.is_valid()[0]):
    print(f'  hit point: {np.array(si_test.p).flatten()[:3]}')
    print(f'  hit normal: {np.array(si_test.n).flatten()[:3]}')
    print(f'  dot(ray_dir, n): {float(np.dot([0,0,1], np.array(si_test.n).flatten()[:3])):.4f}')

baseline_on = None
for n in [0, 1, 2, 4, 6, 7, 8, 9, 10, 12]:
    off = mean_brightness(n, False)
    on = mean_brightness(n, True)
    ratio = on / off if off > 1e-9 else float('nan')
    if n == 0:
        baseline_on = on
    exp = 'lit (<= cap)' if n <= CAP else 'DARK (> cap)'
    print(f'{n:>6} {off:>10.5f} {on:>10.5f} {ratio:>9.2f}  {exp}')

print()
print('Reading the result:')
print(f'  n=0 gives the unobstructed reference ({baseline_on:.5f}).')
print(f'  For 1 <= n <= {CAP}: ON should stay lit, decreasing slightly per pane')
print('    (Fresnel reflection at each interface -- NOT modelled in the shadow')
print('     ray itself, so any falloff here comes from CAMERA-ray paths).')
print(f'  For n > {CAP}: ON should collapse to ~OFF (both dark) -- the cap engaging.')
print('  OFF should be dark for every n >= 1 (glass blocks NEE entirely).')
