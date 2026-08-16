# Path-tracer evaluation — Thesis Section 5.1

The active consolidated evaluator is `evaluate_path_tracer.py`. It evaluates:

- diffuse white-furnace convergence using Mitsuba's diffuse BSDF;
- Mitsuba GGX roughconductor under custom and reference integrators;
- a stock Cornell box with only the integrator changed;
- repeated-seed means and variance;
- matched-seed and deliberately independent-seed controls, including the
  loaded `PathIntegrator` and `PathTracer` class identities;
- a same-setting Cornell comparison with matched `max_depth` and `rr_depth`.
- opt-in primary-hit albedo, shading-normal, and depth AOV channels.

Validation exposed and corrected an off-by-one path-depth convention: the custom
integrator previously allowed one more scattering segment than Mitsuba for the
same numeric `max_depth`. A depth sweep after the correction matched Mitsuba
exactly at depths 1--3 and within Monte Carlo noise at depth 8.

Canonical results are written to `outputs/evaluation/5_1_path_tracer/`, separating
CSV data, linear EXR renders, and display figures.

A reduced design check uses the separate quick-output tree:

```sh
uv run python tests/evaluation/path_tracer/evaluate_path_tracer.py --quick \
  --output outputs/quick/5_1_path_tracer
```

The final run uses eight independent seeds. Furnace comparisons use Mitsuba
BSDFs to isolate the integrator, while the Cornell comparison holds geometry,
materials, sensor, sampler, reconstruction filter, `max_depth`, and `rr_depth`
constant and changes only the integrator plugin.

`figures/ggx_roughness_comparison.png` arranges Mitsuba `path` on the top row
and the custom `path_tracer` on the bottom row. Columns show roughness 0.0, 0.5,
and 1.0 from left to right.

`data/seed_identity_control.csv` explains the exact matched-seed results and
checks that they are not caused by loading the same plugin twice. It compares
the two distinct integrator classes first with a shared seed and then with the
independent seeds used by the original validation. The accompanying
`independent_seed_control_ggx_r05.png` shows the nonzero stochastic image
difference while retaining matching aggregate statistics.

`data/aov_sanity.csv` records the AOV channel layout and checks that material
albedo, unit shading normals, positive hit depth, and zero-valued miss channels
are sensible. The corresponding beauty, albedo, normal, and depth images are
kept as separate files in `figures/`. To rerun only this inexpensive check
without replacing the established Section 5.1 metadata, use:

```sh
uv run python tests/evaluation/path_tracer/evaluate_path_tracer.py \
  --only aov --output outputs/evaluation/5_1_path_tracer
```

The Cornell-box demonstration is exported as four individual passes and as the
plain 2-by-2 figure `figures/cornell_aov_outputs.png`. Its layout is beauty and
albedo on the top row, followed by depth and world-space shading normals.

Historical single-seed furnace scripts are preserved under
`tests/legacy/path_tracer/`. Their old renders are preserved under
`outputs/legacy/pre_thesis_reorganisation/PathTracerValidation/`.
The original standalone AOV script is preserved in the same legacy test folder,
with its former renders under
`outputs/legacy/pre_thesis_reorganisation/AOVs_Validation/`.
