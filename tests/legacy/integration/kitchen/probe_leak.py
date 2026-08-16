#!/usr/bin/env -S uv run --script
"""
DIAGNOSTIC: does the ceiling actually block the envmap?

Fires rays into the UPPER hemisphere from a point inside the room:
  - what fraction escape to the environment (should be 0 if sealed)
  - for those that hit, what BSDF flags the hit surface advertises
    (a ceiling that advertises Transmission/Null would pass light through
     while still registering as a valid intersection)
  - whether a continuation ray past the hit escapes (single thin surface
    vs. real enclosure)
"""
import argparse, os, sys
sys.path.insert(0, os.path.abspath('../../../'))
import numpy as np
import mitsuba as mi
mi.set_variant('llvm_ad_rgb')

from bsdfs.principled import PrincipledBSDF
from emitters.envmap import CustomEnvmap
from integrators.path_tracer import PathTracer
from cameras.physical_camera import PhysicalCamera
mi.register_bsdf('principled_bsdf', lambda props: PrincipledBSDF(props))
mi.register_emitter('custom_envmap', lambda props: CustomEnvmap(props))
mi.register_integrator('path_tracer', lambda props: PathTracer(props))
mi.register_sensor('physical_camera', lambda props: PhysicalCamera(props))

p = argparse.ArgumentParser()
p.add_argument('--scene', default='scene.xml')
p.add_argument('--point', type=float, nargs=3, default=[0.34, 0.5, -0.66],
               help='World-space point inside the room to probe from')
p.add_argument('--n', type=int, default=20000)
args = p.parse_args()

scene = mi.load_file(args.scene, resx=640, resy=480)
origin = mi.Point3f(args.point[0], args.point[1], args.point[2])
print(f'Probing upward from: {args.point}\n')

# --- Upper hemisphere only -------------------------------------------
sampler = mi.load_dict({'type': 'independent'})
sampler.seed(0, args.n)
d = mi.warp.square_to_uniform_hemisphere(sampler.next_2d())   # +z hemisphere
d = mi.Vector3f(d.x, d.z, d.y)                                 # remap so +y (up) is the hemisphere axis

ray = mi.Ray3f(o=origin, d=d)
si = scene.ray_intersect(ray)

valid = np.array(si.is_valid()).flatten()
escaped = ~valid
print(f'Rays into the UPPER hemisphere: {args.n}')
print(f'  escaped (see envmap directly): {escaped.sum()}  ({100*escaped.mean():.2f}%)')
print(f'  hit geometry:                  {valid.sum()}  ({100*valid.mean():.2f}%)')

if escaped.sum() > 0:
    dirs = np.array(d).reshape(3, -1).T
    e = dirs[escaped]
    print(f'  mean escape direction: {e.mean(axis=0)}')
    print('  --> UPWARD LEAK: there is a genuine opening above this point.')

# --- What did the upward rays hit, and is it transmissive? ------------
if valid.sum() > 0:
    t = np.array(si.t).flatten()[valid]
    print(f'\n  hit distances: min={t.min():.3f}  max={t.max():.3f}  mean={t.mean():.3f}')
    try:
        flags = np.array(si.bsdf().flags()).flatten()[valid]
        uniq = np.unique(flags)
        print(f'\n  distinct BSDF flag values on hit surfaces: {uniq}')
        T  = int(mi.BSDFFlags.Transmission)
        DT = int(mi.BSDFFlags.DeltaTransmission)
        N  = int(mi.BSDFFlags.Null)
        for f in uniq:
            bits = []
            if f & T:  bits.append('Transmission')
            if f & DT: bits.append('DeltaTransmission')
            if f & N:  bits.append('Null')
            count = int((flags == f).sum())
            tag = ('  <-- PASSES LIGHT: ' + '|'.join(bits)) if bits else '  (opaque)'
            print(f'    flags={f:<12} count={count:<8}{tag}')
    except Exception as ex:
        print(f'  (BSDF flag introspection unavailable: {ex})')

# --- Continuation: is it a real enclosure or one thin surface? --------
si2 = scene.ray_intersect(si.spawn_ray(d))
beyond_escaped = np.array(~si2.is_valid()).flatten() & valid
print(f'\n  of the rays that hit, {beyond_escaped.sum()} '
      f'({100*beyond_escaped.mean():.2f}% of all) escape immediately past that first surface')
print('  (high = ceiling is a single thin surface with open sky directly beyond)')
