# Chapter 6 — Blender Cycles comparison

The canonical Cycles source scene is
`assets/production_scenes/kitchen_scene/blender/Country-Kitchen.blend`. The
evaluator records its SHA-256 hash in the comparison metadata, linking the six
Cycles EXRs to the exact updated Blender scene used to produce them.

## Controlled comparison scenes

`setup_controlled_scenes.py` builds the remaining three Chapter 6 Cycles test
scenes. Run it in a **new empty Blender 4.3 file**, inspect the camera view of
each generated scene, and save the result as
`assets/production_scenes/blender_comparison/controlled_comparisons.blend`.
Set `REPOSITORY_OVERRIDE` at the top of the script only if it cannot locate the
repository automatically.

The generated scenes are:

- `CH6_Materials`: the complete 18-material Section 5.4 grid, 1600 x 900,
  1024 spp;
- `CH6_HDR_Environment`: the Section 5.3 Sundowner environment scene,
  1024 x 1024, 1024 spp; its Blender environment mapping uses a +90 degree Z
  correction to match the custom renderer's panorama convention;
- `CH6_Camera_DOF`: the finite-aperture three-sphere Section 5.4 scene,
  960 x 720, 256 spp.

All use Cycles CPU, fixed sampling, disabled denoising and clamping, a Box
filter, Standard view transform, and full-float linear RGB EXR output. The
script sets output paths under `outputs/evaluation/6_blender_comparison/` but
does not render or save automatically. `controlled_parameter_map.csv` records
the direct parameter transfers, necessary conversions, and non-equivalent
model details. The existing circular/hexagonal bokeh images remain Section 5.4
evidence; Chapter 6 uses the practical finite-aperture scene without repeating
that isolated test.

`import_kitchen_cameras.py` reconstructs the canonical Country Kitchen hero
camera and five close-up cameras inside the open Blender scene. It reads the
camera transforms and optical parameters directly from
`assets/production_scenes/kitchen_scene/scene.xml` and does not change scene
geometry, materials, lighting, world settings, render settings, resolution, or
the active camera.

The existing active Blender camera is treated as the source of XML sensor zero.
This reference pair lets the script correct both camera-axis conventions and
the Mitsuba Y-up/Blender Z-up world conversion. Consequently,
`CH6_00_Hero` exactly inherits the existing main camera transform, and the same
alignment is applied to the five XML close-ups.

To use it:

1. Open the Chapter 6 copy of `Country-Kitchen.blend`.
2. Confirm that the scene's active camera is the original main/hero camera.
3. Open Blender's **Scripting** workspace and load `import_kitchen_cameras.py`.
4. Press **Run Script** again; existing `CH6_` cameras will be corrected.
5. Inspect the new `Chapter_6_Cameras` collection. The cameras are named
   `CH6_00_Hero` through `CH6_05_Island`.
6. Save the Blender file only after checking the six camera views.

The script is safe to run repeatedly: existing cameras with those exact names
are updated rather than duplicated. If the repository cannot be located from
the script or `.blend` location, set `XML_PATH_OVERRIDE` at the top of the
script to the absolute path of the canonical `scene.xml`. If the active camera
is not the original hero camera, set `REFERENCE_CAMERA_NAME` to its exact object
name before running the script.

## Evidence audit

### Kitchen translation inventory

Before changing any Kitchen lights or materials, open the canonical
`Country-Kitchen.blend` and run `export_kitchen_reference_inventory.py` from
Blender's Scripting workspace. The script is read-only: it exports the source
light objects, emissive meshes, used materials, texture links, Principled
inputs and render colour-management settings to the Kitchen `data/` folder.
These records are then compared against `scene.xml`; no visual tuning is used
to decide equivalence.

After the six full-float Cycles EXRs have been saved under
`outputs/evaluation/6_blender_comparison/kitchen/renders/`, run:

```sh
uv run python tests/evaluation/blender_comparison/evaluate_blender_comparison.py
```

The evaluator does not render either scene. It verifies the six Cycles files
against their embedded camera, sample-count, dimension, channel and finite-data
metadata; checks the corresponding canonical custom AOV EXRs; writes ordinary
CSV/JSON records; and creates one plain horizontal raw comparison per view.

Image-error values are descriptive rather than pass criteria because the two
renderers do not use identical BSDFs, estimators, filtering or clamp policy.
The canonical custom renders use the validated clamp of 50 while the Cycles
renders are unclamped. Six additional custom views use the same 1024-spp
settings with `firefly_clamp=0`; the evaluator records them separately and
writes a plain Cycles/custom unclamped control pair for every view. Denoised
comparisons are not generated from the current files because custom OIDN is
albedo/normal-guided whereas these Cycles EXRs contain only beauty RGB.
