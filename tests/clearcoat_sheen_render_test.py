#!/usr/bin/env -S uv run --script
"""
Clearcoat and sheen visual validation.
The furnace test measures energy; this measures appearance. Two sphere
rows on a dark base colour, lit by area lights so both lobes produce a
visible highlight (a constant emitter alone would wash them out).

Row 1: clearcoat=1.0, sweeping clearcoat_gloss 0 to 1. The coat highlight
       should tighten from broad and soft to nearly mirror-sharp.
Row 2: sheen=1.0, sweeping sheen_tint 0 to 1 on a coloured base. Sheen
       should appear only at the silhouette edges, and shift from white
       (tint=0) toward the base hue (tint=1).

STAGE 1 NOTE: clearcoat is evaluated but not yet importance-sampled, so
high-gloss spheres will be visibly noisy. That is expected, not a bug.
Re-run this script unchanged after Stage 2 to get a direct noise
comparison at matched spp. All spheres are metallic=0 so that diffuse
sampling still covers the hemisphere.
"""
import _common
import numpy as np
import mitsuba as mi
import os

SPP = 256
SEED = 5
MAX_DEPTH = 8
FOV = 46
FILM_W, FILM_H = 1400, 340
GLOSS_SWEEP = [0.0, 0.25, 0.5, 0.75, 1.0]
TINT_SWEEP = [0.0, 0.25, 0.5, 0.75, 1.0]
BASE_RED = [0.30, 0.025, 0.025]
BASE_BLUE = [0.10, 0.12, 0.34]


def sphere(x, bsdf, radius=0.42):
    # transforms apply right-to-left: scale the unit sphere, then place it
    return {
        "type": "sphere",
        "to_world": mi.ScalarTransform4f().translate([x, 0.0, 0.0]).scale(radius),
        "bsdf": bsdf,
    }


def scene_dict(spheres):
    d = {
        "type": "scene",
        "integrator": {"type": "path_tracer", "max_depth": MAX_DEPTH},
        "sensor": {
            "type": "perspective",
            "fov": FOV,
            "fov_axis": "x",  # stated explicitly rather than relying on the default
            "to_world": mi.ScalarTransform4f().look_at(
                origin=[0, 0.5, 7.5], target=[0, 0, 0], up=[0, 1, 0]
            ),
            "film": {"type": "hdrfilm", "width": FILM_W, "height": FILM_H},
            "sampler": {"type": "independent", "sample_count": SPP},
        },
        # dim fill so the unlit sides are not pure black
        "fill": {"type": "constant", "radiance": {"type": "rgb", "value": [0.05, 0.05, 0.06]}},
        # KEY: small and bright, high above the frame. Small is the point — a
        # large source reflects as a large blob at every gloss value, which is
        # why the previous version showed no gloss variation. A small source
        # gives a compact highlight whose SIZE tracks clearcoat_gloss.
        # At y=2.6 it sits well outside the ~+/-0.8 visible height, so it does
        # not appear in frame.
        "key": {
            "type": "rectangle",
            "to_world": mi.ScalarTransform4f()
            .translate([1.6, 2.6, 2.4])
            .rotate([1, 0, 0], -125)
            .scale(0.32),
            "emitter": {"type": "area", "radiance": {"type": "rgb", "value": [420.0, 420.0, 420.0]}},
        },
        # RIM: behind and above, angled down to backlight the silhouettes.
        # Also lifted out of frame — this is what was filling the background white.
        "rim": {
            "type": "rectangle",
            "to_world": mi.ScalarTransform4f()
            .translate([-1.2, 2.3, -3.0])
            .rotate([1, 0, 0], 55)
            .scale(1.1),
            "emitter": {"type": "area", "radiance": {"type": "rgb", "value": [45.0, 45.0, 45.0]}},
        },
    }
    for i, s in enumerate(spheres):
        d[f"sphere_{i}"] = s
    return d


def render_row(name, spheres, note):
    scene = mi.load_dict(scene_dict(spheres))
    img = np.array(mi.render(scene, spp=SPP, seed=SEED))
    os.makedirs("outputs/ClearcoatSheen", exist_ok=True)
    path = f"outputs/ClearcoatSheen/{name}.png"
    mi.util.write_bitmap(path, img)
    print(f"Wrote {path}   mean={img.mean():.4f}  max={img.max():.3f}   {note}")
    return img


xs = np.linspace(-2.2, 2.2, len(GLOSS_SWEEP))

# Row 1 — clearcoat gloss sweep
render_row(
    "clearcoat_gloss_sweep",
    [sphere(float(x), {
        "type": "principled_bsdf",
        "base_colour": BASE_RED,
        "roughness": 0.9,
        "metallic": 0.0,
        "specular": 0.0,
        "clearcoat": 1.0,
        "clearcoat_gloss": g,
    }) for x, g in zip(xs, GLOSS_SWEEP)],
    "gloss 0 - 1, left to right",
)

# Control — identical spheres with the coat switched off.
# Must differ from the row above ONLY by the coat highlight.
render_row(
    "clearcoat_off_control",
    [sphere(float(x), {
        "type": "principled_bsdf",
        "base_colour": BASE_RED,
        "roughness": 0.9,
        "metallic": 0.0,
        "specular": 0.0,
        "clearcoat": 0.0,
    }) for x in xs],
    "control: no coat",
)

# Row 2 — sheen tint sweep
render_row(
    "sheen_tint_sweep",
    [sphere(float(x), {
        "type": "principled_bsdf",
        "base_colour": BASE_BLUE,
        "roughness": 0.8,
        "metallic": 0.0,
        "specular": 0.0,
        "sheen": 1.0,
        "sheen_tint": t,
    }) for x, t in zip(xs, TINT_SWEEP)],
    "tint 0 (white) - 1 (base hue), left to right",
)

# Control — sheen off. The difference against the row above is the sheen term.
render_row(
    "sheen_off_control",
    [sphere(float(x), {
        "type": "principled_bsdf",
        "base_colour": BASE_BLUE,
        "roughness": 0.8,
        "metallic": 0.0,
        "specular": 0.0,
        "sheen": 0.0,
    }) for x in xs],
    "control: no sheen",
)
