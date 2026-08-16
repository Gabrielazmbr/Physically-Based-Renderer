# Thesis evaluations

Each subdirectory groups experiments by the renderer responsibility being
evaluated. Results are stored separately under `outputs/evaluation/`, organised
by thesis section.

A completed evaluation should normally provide:

1. A concise statement of the question being tested.
2. Explicit resolution, spp, depth, sampler, seed, backend, and comparison
   settings where applicable.
3. Per-render CSV data for repeated-seed experiments.
4. A summary CSV containing only thesis-facing measurements.
5. Raw linear EXRs when images are quantitative evidence.
6. Labelled PNG figures when visual interpretation is required.
7. Machine-readable metadata identifying the source state used for the run.

Not every experiment requires every artifact. For example, a chi-squared test
needs a clear result table but does not require a gallery of renders.

Reduced `--quick` runs write to `outputs/quick/<section>/`, supplied through
the evaluator's `--output` option. Canonical full-resolution evidence remains
exclusively under `outputs/evaluation/<section>/`. This convention applies to
every canonical section.
