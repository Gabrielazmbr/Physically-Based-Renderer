#!/usr/bin/env -S uv run --script

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import mitsuba as mi
mi.set_variant("llvm_ad_rgb")

from integrators.path_tracer import PathTracer
from bsdfs.principled import PrincipledBSDF
mi.register_integrator("path_tracer", lambda props: PathTracer(props))
mi.register_bsdf("principled_bsdf", lambda props: PrincipledBSDF(props))

from assets.scenes.white_furnace import white_furnace_scene

roughness_values = [0.0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5]
spp, seed = 1024, 11

print(f"{'Roughness':>9} {'Mean':>8} {'Std':>8}")
for r in roughness_values:
    bsdf = {"type": "principled_bsdf", "base_colour": [1.0, 1.0, 1.0], "roughness": r, "metallic": 0.0}
    scene = mi.load_dict(white_furnace_scene(bsdf, integrator_type="path_tracer", spp=spp))
    img = mi.render(scene, spp=spp, seed=seed)
    arr = np.array(img)
    print(f"{r:>9.3f} {arr.mean():>8.4f} {arr.std():>8.4f}")
