#!/usr/bin/env -S uv run --script
"""
Rendering scene.xml with all four custom plugins registered.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath('../../../'))

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

parser = argparse.ArgumentParser()

parser.add_argument('--scene', default='scene.xml')
parser.add_argument('--sensor', type=int, default=0, help='0=main, 1=stove closeup, 2=table closeup')
parser.add_argument('--fov', type=float, default=None,
                     help='Override FOV in degrees -- MAIN SENSOR (0) ONLY. '
                          'Will error on close-up sensors (1-5), which have no $fov placeholder.')
parser.add_argument('--resy', type=int, default=None)
parser.add_argument('--resx', type=int, default=None)

parser.add_argument('--spp', type=int, default=256)
parser.add_argument('--seed', type=int, default=0,
                     help='RNG seed. Vary across runs for multi-seed variance measurement.')

parser.add_argument('--out', default='render.png')

parser.add_argument('--max-depth', type=int, default=None,
                     help='Override max_depth. 1 = direct lighting only, no bounces.')
parser.add_argument('--rr-depth', type=int, default=None,
                     help='Override rr_depth (requires the $rr_depth placeholder)')

parser.add_argument('--sampler', default=None, choices=['independent', 'stratified',
                                                          'multijitter', 'ldsampler'],
                     help='Override sampler type; stratified is the scene default')
parser.add_argument('--aovs', action='store_true',
                     help='Enable albedo/normal/depth AOVs. Forces .exr output.')



parser.add_argument('--firefly-clamp', type=float, default=None,
                     help='Cap per-sample contribution. 0 = disabled.')
parser.add_argument('--transparent-shadows', action='store_true',
                     help='Let NEE shadow rays pass through smooth glass (approximate)')


parser.add_argument('--envmap-scale', type=float, default=None,
                     help='Override envmap brightness for this render only')
parser.add_argument('--aperture-radius', type=float, default=None)
parser.add_argument('--focus-distance', type=float, default=None)
parser.add_argument('--aperture-blades', type=int, default=None,
                     help='0=circular. >=3 for bladed bokeh (e.g. 6 for hexagonal)')

args = parser.parse_args()
load_kwargs = {'spp': args.spp}

if args.max_depth is not None:
    load_kwargs['max_depth'] = str(args.max_depth)
if args.rr_depth is not None:
    load_kwargs['rr_depth'] = args.rr_depth
if args.sampler is not None:
    load_kwargs['sampler'] = args.sampler

if args.firefly_clamp is not None:
    load_kwargs['firefly_clamp'] = str(args.firefly_clamp)
if args.transparent_shadows:
    load_kwargs['transparent_shadows'] = 'true'

if args.envmap_scale is not None:
    load_kwargs['envmap_scale'] = str(args.envmap_scale)
if args.aperture_radius is not None:
    load_kwargs['aperture_radius'] = str(args.aperture_radius)
if args.focus_distance is not None:
    load_kwargs['focus_distance'] = str(args.focus_distance)
if args.aperture_blades is not None:
    load_kwargs['aperture_blades'] = str(args.aperture_blades)

if args.fov is not None:
    load_kwargs['fov'] = str(args.fov)
if args.resy is not None:
    load_kwargs['resy'] = str(args.resy)
if args.resx is not None:
    load_kwargs['resx'] = str(args.resx)
if args.aovs:
    load_kwargs['with_aovs'] = 'true'



scene = mi.load_file(args.scene, **load_kwargs)
img = mi.render(scene, spp=args.spp, sensor=args.sensor, seed=args.seed)

out = args.out
if args.aovs and not out.lower().endswith('.exr'):
    # AOV renders carry 10 channels; PNG can only hold 3. Force .exr so the
    # albedo/normal/depth passes actually survive to disk
    out = out.rsplit('.', 1)[0] + '.exr'
    print(f'AOVs enabled, writing {out} instead (PNG cannot hold 10 channels)')


mi.util.write_bitmap(out, img)
print(f'Wrote {out}  (shape {img.shape})')
