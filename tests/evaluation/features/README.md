# Section 5.4 — isolated feature evaluation

`evaluate_features.py` is the single canonical runner for section 5.4. It
consolidates the original camera, bokeh, anisotropy, Burley, clearcoat, sheen,
transparent-shadow, glazing, and material-showcase experiments without making
the historical scripts the source of final thesis measurements.

The evaluation is deliberately split into five controlled groups:

1. an 18-material Principled BSDF showcase under a shared HDRI/light setup;
2. open-aperture, thin-sheet, and solid-slab glazing at matched settings;
3. aperture-zero equivalence, depth of field, and circular/polygonal bokeh;
4. anisotropy orientation, a Burley/Lambert angle sweep, and same-position
   clearcoat/sheen controls;
5. transparent direct-light visibility with no pane, the feature disabled,
   and the opt-in straight-through approximation enabled.

The gallery uses Mitsuba's standard environment emitter so that it concentrates
on the custom BSDF. The numerical correctness evidence remains the furnace,
chi-squared, and reference comparisons in section 5.2; this suite asks whether
the exposed controls produce their intended visible behaviour.

Run a low-resolution design check:

```sh
uv run python tests/evaluation/features/evaluate_features.py --quick \
  --output outputs/quick/5_4_features
```

Generate all canonical section 5.4 evidence:

```sh
uv run python tests/evaluation/features/evaluate_features.py
```

Run one group while developing a figure:

```sh
uv run python tests/evaluation/features/evaluate_features.py --only camera
uv run python tests/evaluation/features/evaluate_features.py --only glazing
uv run python tests/evaluation/features/evaluate_features.py --only materials
uv run python tests/evaluation/features/evaluate_features.py --only shadows
```

The canonical run writes to `outputs/evaluation/5_4_features/`:

- raw linear EXR renders in `renders/`;
- display PNGs and labelled/composite SVGs in `figures/`;
- camera, glazing, material, Burley, lobe, and transparent-shadow CSV data in
  `data/`;
- `metadata.json`, containing all settings, seeds, backend, hardware, commit,
  script hash, and principal measurements.

Quick checks use `outputs/quick/5_4_features/` so that reduced settings cannot
overwrite the canonical evidence.

The final material gallery is 1600 × 900 at 1024 spp. Glazing panels are 700 ×
700 at 1024 spp; the increased sample count resolves refractive slab-edge paths
without using the biased firefly clamp. The remaining rendered controls use 256
spp. Historical clamp diagnostics are retained under
`outputs/legacy/5_4_features/` and are not part of the section 5.4 evidence.

Superseded scripts are preserved unchanged in `tests/legacy/features/`.
