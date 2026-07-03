#!/usr/bin/env -S uv run --script

import drjit as dr
import mitsuba as mi

mi.set_variant("llvm_ad_rgb")

# Import and register integrator
from integrators.path_tracer import PathTracer

mi.register_integrator("path_tracer", lambda props: PathTracer(props))

# Load Cornell Box but swap in PathTracer integrator
scene_dict = mi.cornell_box()
scene_dict["integrator"] = {"type": "path_tracer"}

scene = mi.load_dict(scene_dict)
img = mi.render(scene, spp=256)
mi.Bitmap(img).write("outputs/stage1_black.exr")
print("Render complete")
