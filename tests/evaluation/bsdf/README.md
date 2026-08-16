# Principled BSDF evaluation — Thesis Section 5.2

`evaluate_bsdf.py` consolidates the existing BSDF validation into four focused
questions:

1. Does the opaque Principled mixture show the expected white-furnace energy
   behaviour in dielectric, metallic, and zero-specular control modes?
2. Are `sample()` and `pdf()` statistically consistent for representative
   diffuse, plastic, metallic, mixed, and clearcoat configurations?
3. Is the hand-written GTR1 distribution normalised, and does its sampler
   reproduce the analytic distribution?
4. Does smooth transmission reproduce Mitsuba's dielectric Fresnel split,
   radiance weights, total internal reflection, delta convention, furnace
   behaviour, and rendered appearance?

The sharp-lobe chi-squared failures are retained as measured numerical-harness
limits. The suite includes Mitsuba's own sharp Principled failure as a reference
and a gloss-0.95 grid refinement that changes the result without changing the
BSDF sampler.

Canonical results are written to `outputs/evaluation/5_2_bsdf/` with separate
`data/`, `renders/`, and `figures/` directories. Clearcoat/sheen appearance,
anisotropy, and Burley diffuse remain assigned to Thesis Section 5.4.

A reduced design check uses the separate quick-output tree:

```sh
uv run python tests/evaluation/bsdf/evaluate_bsdf.py --quick \
  --output outputs/quick/5_2_bsdf
```

## Figures

- `principled_furnace_roughness_comparison.png`: the top row is the default
  opaque dielectric mixture and the bottom row is metallic. Roughness is 0.0,
  0.5, and 1.0 from left to right.
- `glass_reference_custom_difference.png`: Mitsuba dielectric, custom smooth
  transmission, and absolute difference amplified by 50 from left to right.

The zero-specular Lambertian furnace control is retained in the CSV evidence
but omitted from the main comparison figure because its correct result is a
uniform white sphere at every roughness.

Superseded furnace, chi-squared, and glass scripts are preserved unchanged in
`tests/legacy/bsdf/`. Development-only PDF, albedo, brightness, and texture
probes are retained in `tests/legacy/bsdf/diagnostics/`.
