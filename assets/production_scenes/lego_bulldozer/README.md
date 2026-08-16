# Lego 856 Bulldozer production scene

This directory contains the Blender-authored scene used for thesis Section
5.5.1 and its Mitsuba export. The integration evaluator can optionally consume
the fixed Cycles reference delivered with the separate thesis evidence.

## Contents

- `BLENDER_LEGO_CYCLES.blend`: Blender 4.3 scene used for the final reference.
- `scene_export.xml`: Mitsuba-Blender export reconstructed by the evaluator.
- `meshes/`: 439 PLY files referenced by the exported XML.
- `textures/`: exported HDR environment map.
- `reference/reference_metadata.json`: reference settings and EXR hash.

The corresponding linear 1080 x 1080 Cycles EXR is part of the separately
delivered thesis evidence rather than the Git repository. It can be passed to
the evaluator with `--cycles-reference` when regenerating the comparison.

The metadata was generated in Blender after the final render. During repository
organisation, its absolute source paths were made relative and its frame was
normalised from the timeline value 0 to the rendered frame recorded in the EXR
header (frame 1). The original Blender-generated JSON is preserved under
`outputs/legacy/5_5_integration/lego/reference_metadata_original.json`.

## Intended claim

This scene tests end-to-end reconstruction of a Blender-authored asset through
the Mitsuba export and the custom path tracer, camera, environment emitter, and
Principled BSDF. It is primarily a diffuse-material integration test. It does
not establish general compatibility with arbitrary Blender node graphs.

The exported `RubberBand` blend is reduced to a weighted flat colour. Materials
named `transparent` and `Red_Glass` were exported as diffuse BSDFs and are
therefore treated as diffuse rather than optically transmissive surfaces.

Render only the reconstructed scene through the custom pipeline:

```sh
uv run python main.py render lego --quality draft
```

## Attribution

The model is *Lego 856 Bulldozer* by Heinzelnisse, published on BlendSwap in
2014 under CC-BY-NC:

https://www.blendswap.com/blend/11490

See `LICENSE.txt` for the attribution record. LEGO is a trademark of the LEGO
Group, which does not sponsor or endorse this research project.
