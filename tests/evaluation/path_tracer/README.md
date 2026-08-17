# Path-tracer evaluation — Thesis Section 5.1

The active consolidated evaluator is `evaluate_path_tracer.py`. It evaluates:

- diffuse white-furnace convergence using Mitsuba's diffuse BSDF;
- Mitsuba GGX roughconductor under custom and reference integrators;
- a stock Cornell box with only the integrator changed;
- repeated-seed means and variance;
- a same-setting Cornell comparison with matched `max_depth` and `rr_depth`.

Canonical results are written to `outputs/evaluation/5_1_path_tracer/`, separating
CSV data, linear EXR renders, and PNG/JPEG images for display.

The final run uses eight independent seeds. Furnace comparisons use Mitsuba
BSDFs to isolate the integrator, while the Cornell comparison holds geometry,
materials, sensor, sampler, reconstruction filter, `max_depth`, and `rr_depth`
constant and changes only the integrator plugin.

Historical single-seed furnace scripts are preserved under
`tests/legacy/path_tracer/`. Their old renders are preserved under
`outputs/legacy/pre_thesis_reorganisation/PathTracerValidation/`.
