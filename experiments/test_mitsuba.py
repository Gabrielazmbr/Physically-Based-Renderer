import mitsuba as mi

mi.set_variant('llvm_ad_rgb')

# Render the built-in Cornell Box
img = mi.render(mi.load_dict(mi.cornell_box()))

# Save it
mi.Bitmap(img).write('cornell_box.exr')
print("Success — Cornell Box rendered to cornell_box.exr")



'''
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import mitsuba as mi
mi.set_variant('llvm_ad_rgb')

from integrators.path_tracer import PathTracer
from bsdfs.principled import PrincipledBSDF
from assets.scenes.cornell_box import cornell_box_scene

os.makedirs("outputs/PathTracerValidation/cornell", exist_ok=True)

spp = 512
configs = [("path_tracer", 55), ("path", 1000)]
images = {}

for integrator_type, seed in configs:
    scene_dict = cornell_box_scene()
    scene_dict["integrator"] = {"type": integrator_type, "max_depth": 8}
    scene = mi.load_dict(scene_dict)
    img = mi.render(scene, spp=spp, seed=seed)
    mi.util.write_bitmap(f"outputs/PathTracerValidation/cornell/{integrator_type}.exr", img)
    images[integrator_type] = np.array(img)
    print(f"Saved {integrator_type} (seed={seed})")

diff = np.abs(images["path_tracer"] - images["path"])
print(f"\nMean absolute difference: {diff.mean():.5f}")
print(f"Max absolute difference:  {diff.max():.5f}")

import numpy as np
import mitsuba as mi
mi.set_variant('llvm_ad_rgb')

a = np.array(mi.Bitmap("outputs/PathTracerValidation/cornell/path_tracer.exr"))
b = np.array(mi.Bitmap("outputs/PathTracerValidation/cornell/path.exr"))
diff = np.abs(a - b)
y, x, c = np.unravel_index(np.argmax(diff), diff.shape)
print(f"Max diff at pixel ({x},{y}), channel {c}: path_tracer={a[y,x,c]:.4f}  path={b[y,x,c]:.4f}")
'''


'''
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import mitsuba as mi
mi.set_variant('llvm_ad_rgb')

from integrators.path_tracer import PathTracer   # registers "path_tracer"
from bsdfs.principled import PrincipledBSDF      # registers "principled_bsdf"
from assets.scenes.white_furnace import white_furnace_scene

principled_metal = lambda roughness: {
    "type": "principled_bsdf",
    "base_colour": [1.0, 1.0, 1.0],
    "roughness": roughness,
    "metallic": 1.0,
}

roughness_values = [0.0, 0.5, 1.0]
spp, seed = 256, 7

os.makedirs("outputs/PathTracerValidation/section3_metal", exist_ok=True)

print(f"{'Roughness':>9} {'SPP':>6} {'Seed':>6} {'Mean':>8} {'Std':>8}")
for r in roughness_values:
    scene = mi.load_dict(white_furnace_scene(principled_metal(r), integrator_type="path_tracer", spp=spp))
    img = mi.render(scene, spp=spp, seed=seed)
    arr = np.array(img)
    print(f"{r:>9.1f} {spp:>6} {seed:>6} {arr.mean():>8.4f} {arr.std():>8.4f}")

    tag = f"r{r}_metallic1_seed{seed}"
    mi.util.write_bitmap(f"outputs/PathTracerValidation/section3_metal/{tag}.exr", img)

print("\nSaved to outputs/PathTracerValidation/section3_metal/")
'''
'''

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import mitsuba as mi
mi.set_variant('llvm_ad_rgb')

from integrators.path_tracer import PathTracer   # registers "path_tracer"
from assets.scenes.white_furnace import white_furnace_scene

roughconductor = lambda alpha: {
    "type": "roughconductor",
    "distribution": "ggx",
    "alpha": alpha,
}

roughness_values = [0.0, 0.5, 1.0]

configs = []
for r in roughness_values:
    alpha = max(r * r, 1e-4)  # match principled_bsdf's own alpha = roughness^2 convention
    configs.append((r, alpha, "path_tracer", 256))
    configs.append((r, alpha, "path",        1000))

os.makedirs("outputs/PathTracerValidation/section2", exist_ok=True)

print(f"{'Roughness':>9} {'Integrator':<12} {'SPP':>6} {'Seed':>6} {'Mean':>8} {'Std':>8}")
for roughness, alpha, integrator_type, seed in configs:
    scene = mi.load_dict(white_furnace_scene(roughconductor(alpha), integrator_type=integrator_type, spp=256))
    img = mi.render(scene, spp=256, seed=seed)
    arr = np.array(img)
    print(f"{roughness:>9.1f} {integrator_type:<12} {256:>6} {seed:>6} {arr.mean():>8.4f} {arr.std():>8.4f}")

    tag = f"r{roughness}_{integrator_type}_seed{seed}"
    mi.util.write_bitmap(f"outputs/PathTracerValidation/section2/{tag}.exr", img)

    # Deviation heatmap - note: x2 gain here, NOT x10 like section 1.
    # Section 1's deviations are noise-scale (~0.01); this section's real
    # energy loss can be ~35%, so a x10 gain would just clip to solid white
    # at every roughness and hide the 0.0 -> 0.5 -> 1.0 progression.
    deviation = np.abs(arr[:, :, 0] - 1.0)
    heatmap = np.clip(deviation * 2, 0, 1)
    mi.util.write_bitmap(f"outputs/PathTracerValidation/section2/{tag}_deviation.png", mi.Bitmap(heatmap))

print("\nSaved to outputs/PathTracerValidation/section2/")
'''
'''
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import mitsuba as mi
mi.set_variant('llvm_ad_rgb')

from integrators.path_tracer import PathTracer   # registers "path_tracer"
from assets.scenes.white_furnace import white_furnace_scene

diffuse_bsdf = {"type": "diffuse", "reflectance": {"type": "rgb", "value": [1.0, 1.0, 1.0]}}

configs = [
    ("path_tracer", 256,  0),
    ("path_tracer", 1024, 0),
    ("path",        256,  1000),
    ("path",        1024, 1000),
]

os.makedirs("outputs/PathTracerValidation/section1", exist_ok=True)

print(f"{'Integrator':<12} {'SPP':>6} {'Seed':>6} {'Mean':>8} {'Std':>8}")
for integrator_type, spp, seed in configs:
    scene = mi.load_dict(white_furnace_scene(diffuse_bsdf, integrator_type=integrator_type, spp=spp))
    img = mi.render(scene, spp=spp, seed=seed)
    arr = np.array(img)
    print(f"{integrator_type:<12} {spp:>6} {seed:>6} {arr.mean():>8.4f} {arr.std():>8.4f}")

    tag = f"{integrator_type}_spp{spp}_seed{seed}"

    # Plain render, matching your existing main.py convention
    mi.util.write_bitmap(f"outputs/PathTracerValidation/section1/{tag}.exr", img)

    # Deviation-from-ideal heatmap: 0 = perfect (black), brighter = more energy loss/gain
    deviation = np.abs(arr[:, :, 0] - 1.0)  # single channel is enough, image is greyscale-ish anyway
    heatmap = np.clip(deviation * 10, 0, 1)  # x10 so small deviations are actually visible
    mi.util.write_bitmap(f"outputs/PathTracerValidation/section1/{tag}_deviation.png", mi.Bitmap(heatmap))

print("\nSaved plain renders + deviation heatmaps to outputs/PathTracerValidation/section1/")

'''
