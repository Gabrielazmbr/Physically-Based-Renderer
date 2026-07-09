#!/usr/bin/env -S uv run --script

import os
import sys

import drjit as dr
import mitsuba as mi

mi.set_variant("llvm_ad_rgb")

# Import and register plugins
from bsdfs.principled import PrincipledBSDF
from integrators.path_tracer import PathTracer

# Register the Principled BSDF
mi.register_bsdf("principled_bsdf", lambda props: PrincipledBSDF(props))
# Register the Path Tracer integrator
mi.register_integrator("path_tracer", lambda props: PathTracer(props))


# Scene loading
from assets.scenes.white_furnace import white_furnace_scene

scene_name = "white_furnace"
test_name = "BSDF"

scene_dict = white_furnace_scene(roughness=1.0)
scene = mi.load_dict(scene_dict)


os.makedirs(f"outputs/{test_name}", exist_ok=True)
existing = [f for f in os.listdir(f"outputs/{test_name}") if f.startswith(scene_name)]
index = len(existing) + 1

img = mi.render(scene, spp=256)
mi.Bitmap(img).write(f"outputs/{test_name}/{scene_name}_{index:02d}.exr")
print(f"Rendered outputs/{test_name}/{scene_name}_{index:02d}.exr")
