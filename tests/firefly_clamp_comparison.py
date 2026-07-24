#!/usr/bin/env -S uv run --script
"""
Renders control (no clamp) and clamped, same seed/scene, saves both as
PNG and EXR, and reloads the saved EXR from disk to confirm the clamp
is genuinely present in the saved file, not just in the in-memory
array before writing. Also writes an exposure-reduced PNG, since the
sun/highlight region is bright enough that a normal PNG conversion
clips both control and clamped to the same white regardless of the
clamp, pulling exposure down is the only way to actually see the
difference.
"""
import _common
import numpy as np
import mitsuba as mi
from assets.scenes.environment_lighting import environment_lighting_scene

HDRI = "assets/hdri/sundowner_overlook_1k.exr"
SPP = 256
SEED = 7
CLAMP_VALUE = 50.0

def render(clamp_value):
    scene_dict = environment_lighting_scene(HDRI)
    scene_dict["sensor"]["sampler"] = {"type": "independent", "sample_count": SPP}
    scene_dict["integrator"]["firefly_clamp"] = clamp_value
    scene = mi.load_dict(scene_dict)
    return mi.render(scene, spp=SPP, seed=SEED)

img_control = render(0.0)
img_clamped = render(CLAMP_VALUE)

print(f"{'':>10} {'max':>10} {'mean':>10}")
for label, img in [("control", img_control), ("clamped", img_clamped)]:
    arr = np.array(img)
    print(f"{label:>10} {arr.max():>10.3f} {arr.mean():>10.4f}")

    mi.util.write_bitmap(f"outputs/FireflyHandlingValidation/firefly_{label}_256spp.png", img)          # standard 8-bit, clips ~1.0
    mi.Bitmap(img).write(f"outputs/FireflyHandlingValidation/firefly_{label}_256spp.exr")               # raw HDR, no clipping

    exposed_down = arr / 8.0  # ~3 stops down, pulls the sun back into a visible range
    mi.util.write_bitmap(f"outputs/FireflyHandlingValidation/firefly_{label}_exposed_down_256spp.png", exposed_down)

print("\nReloaded from saved .exr (ground truth — no viewer, no render, just the file on disk):")
for label in ["control", "clamped"]:
    arr = np.array(mi.Bitmap(f"outputs/FireflyHandlingValidation/firefly_{label}_256spp.exr"))
    print(f"{label:>10} {arr.max():>10.3f} {arr.mean():>10.4f}")
