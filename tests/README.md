# Evaluation catalogue

This directory separates thesis-facing evaluations from development diagnostics
and preserved historical scripts.

## Categories

- `evaluation/`: controlled experiments used as evidence in Chapter 5.
- `legacy/`: superseded experiments retained as a development record.
- `_common.py`: shared Mitsuba variant and custom-plugin registration for the
  evaluation programs.

Most files in this project are experimental render evaluations rather than unit
tests. A final evaluation should state its question, comparison conditions,
settings, expected interpretation, and output location. Repeated-seed claims
should save both individual measurements and aggregate statistics.

## Common launcher

From the repository root, first run the low-cost smoke workflow:

```sh
uv run python tests/run_evaluations.py --smoke
```

List all targets or run selected reduced evaluations:

```sh
uv run python tests/run_evaluations.py --list
uv run python tests/run_evaluations.py path-tracer bsdf
```

Reduced settings are the default and write under `outputs/quick/`. Use `--full`
only when intentionally regenerating canonical evidence. `--dry-run` prints the
exact child commands, while `--keep-going` completes a batch before reporting
all failures.

## Chapter 5 map

| Thesis section | Evaluation question | Code area | Status |
| --- | --- | --- | --- |
| 5.1 Path tracer | Does light transport agree with Mitsuba when the BSDF and path budget are controlled? | `evaluation/path_tracer/` | Complete |
| 5.2 BSDF | Are energy, sampling, and smooth transmission internally consistent or reference-equivalent? | `evaluation/bsdf/` | Complete |
| 5.3 Sampling | How do environment sampling, sampler choice, clamping, and denoising affect variance or error? | `evaluation/sampling/` | Complete |
| 5.4 Features | Do camera, material, glazing, and visibility controls produce the intended isolated behaviour? | `evaluation/features/` | Complete |
| 5.5 Integration | Do the plugins operate on imported and production-style assets? | `evaluation/integration/` | Lego and Kitchen complete |
| 5.6 Scale case study | Does the environment visibility regression remain fixed at production scale? | `evaluation/scale_failure/` | Active fix checked; historical evidence optional |

Historical scripts are kept under `legacy/` only when their purpose is covered
by a retained canonical evaluation. The chronological validation and debugging
record is preserved separately in
[`docs/development/validation-journal.md`](../docs/development/validation-journal.md).
