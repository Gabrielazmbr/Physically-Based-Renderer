#!/usr/bin/env -S uv run --script
import os
import numpy as np
import mitsuba as mi

mi.set_variant("llvm_ad_rgb")

# ── Register plugins ────────────────────────────────────────────
from bsdfs.principled import PrincipledBSDF
from integrators.path_tracer import PathTracer
from emitters.envmap import CustomEnvmap
from cameras.thin_lens_camera import ThinLensCamera

mi.register_integrator("path_tracer", lambda props: PathTracer(props))
mi.register_bsdf("principled_bsdf", lambda props: PrincipledBSDF(props))
mi.register_bsdf("custom_envmap", lambda props: CustomEnvmap(props))
mi.register_sensor("thinlens_probe", lambda props: ThinLensCamera(props))

# ── Load scene ────────────────────────────────────────────────
from assets.scenes.material_test import material_test_scene
from assets.scenes.white_furnace import white_furnace_scene
from assets.scenes.cornell_box import cornell_box_scene
from assets.scenes.environment_lighting import environment_lighting_scene
from assets.scenes.depth_of_field import depth_of_field_scene

# ───────────────────────────────────────────────────────────────

scene_dict = depth_of_field_scene()
scene_dict["sensor"]["type"] = "thinlens_probe"
scene = mi.load_dict(scene_dict)
sensor = scene.sensors()[0]


ray, w = sensor.sample_ray(time=0, sample1=0.5, sample2=mi.Point2f(0.5, 0.5), sample3=mi.Point2f(0.5, 0.5))
print("direction:", ray.d)



scene_name = "depth_of_field_scene_ISVALID_MitsubaPerspective"
test_name = "DOPValidation"
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
