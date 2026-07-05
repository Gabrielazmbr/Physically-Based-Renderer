#!/usr/bin/env -S uv run --script

import os

import drjit as dr
import mitsuba as mi

mi.set_variant("llvm_ad_rgb")

# Import and register integrator
from integrators.path_tracer import PathTracer

mi.register_integrator("path_tracer", lambda props: PathTracer(props))

# Load Cornell Box but swap in PathTracer integrator
scene_dict = mi.cornell_box()
scene_dict["integrator"] = {"type": "path_tracer"}


def next_render_index(folder, prefix):
    os.makedirs(folder, exist_ok=True)
    existing = [f for f in os.listdir(folder) if f.startswith(prefix)]
    return len(existing) + 1


scene = mi.load_dict(scene_dict)
folder = "outputs/path_tracer"
prefix = "cornell_box"
index = next_render_index(folder, prefix)

img = mi.render(scene, spp=512)
mi.Bitmap(img).write(f"{folder}/{prefix}_{index:02d}.exr")
print(f"Saved render {index:02d}")
