# Section 5.5 — imported and production-scene integration

`evaluate_integration.py` is the single canonical runner for Section 5.5. The
`lego` target covers Section 5.5.1 and the `kitchen` target covers Section
5.5.2.

The Lego evaluation performs three groups of checks:

1. asset integrity and material-mapping inventory for the Blender export;
2. a low-cost primary-silhouette comparison between the exported Mitsuba scene
   and its custom-camera reconstruction;
3. a matched reconstruction using the custom path tracer, physical camera,
   environment emitter, and zero-specular Principled BSDF, compared with the
   fixed 1024-spp Blender Cycles reference.

A Mitsuba diffuse control changes only the reconstructed BSDF. It checks that
the custom zero-specular mode preserves the diffuse material response in the
imported scene. The Cycles comparison is reported descriptively rather than
given a pass threshold because the renderers do not share an estimator or
random-number sequence.

Run a low-cost design check without touching canonical evidence:

```sh
uv run python tests/evaluation/integration/evaluate_integration.py --quick
```

The custom LEGO render and asset checks work without a Cycles file. To recreate
the cross-renderer comparison using the separately delivered evidence, supply
its location explicitly:

```sh
uv run python tests/evaluation/integration/evaluate_integration.py --quick \
  --cycles-reference /path/to/cycles_reference_1024spp.exr
```

If the matching JSON is not already under the scene's `reference/` directory,
also pass `--reference-metadata /path/to/reference_metadata.json`. Without the
EXR, the evaluator writes the custom and Mitsuba-diffuse controls and records
the Cycles comparison as skipped.

Generate the canonical Lego evidence:

```sh
uv run python tests/evaluation/integration/evaluate_integration.py
```

Run one non-rendering group:

```sh
uv run python tests/evaluation/integration/evaluate_integration.py --only manifest
uv run python tests/evaluation/integration/evaluate_integration.py --only silhouette
```

Canonical outputs are written to
`outputs/evaluation/5_5_integration/lego/`. Quick outputs are written to
`outputs/quick/5_5_integration/lego/` automatically.

The output always contains ordinary CSV tables, custom and diffuse-control
linear EXRs, display PNGs, and machine-readable metadata. When the external
Cycles EXR is supplied, it additionally contains an unembellished horizontal
Cycles/custom PNG and descriptive comparison metrics.

## Country Kitchen

The kitchen manifest rebuilds `scene.xml` from the untouched source XML in a
temporary directory and requires the result to be byte-identical to the
canonical scene. It also inventories the converted materials, 301 shapes, six
physical-camera sensors, custom path tracer and environment emitter, thin
transmissive window pane, and every referenced asset.

The view group renders the hero sensor plus the five authored close-ups using
the same integration settings: stratified sampling, the validated clamp of 50,
transparent shadows, and multi-pass accumulation. It retains the linear
10-channel beauty/AOV EXR, an ordinary beauty PNG, and an AOV-guided OIDN
display PNG for each view. Quick previews use their own output route:

```sh
uv run python tests/evaluation/integration/evaluate_integration.py \
  --scene kitchen --quick
```

The non-rendering manifest can be checked independently:

```sh
uv run python tests/evaluation/integration/evaluate_integration.py \
  --scene kitchen --only manifest
```

Canonical kitchen results are written to
`outputs/evaluation/5_5_integration/kitchen/`; previews go to
`outputs/quick/5_5_integration/kitchen/`.
