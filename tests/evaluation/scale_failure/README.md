# Scale-dependent failure case — Thesis Section 5.6

`evaluate_scale_failure.py` audits the six approved diagnostic images and the
active environment-emitter correction. It deliberately does not restore or run
the defective implementation. The historical images are fixed evidence; the
runner records their hashes, dimensions and luminance statistics, verifies the
decisive exactly-black opaque-window control, and checks that the active emitter
uses a safe radius that cannot be shortened by `set_scene()`.

The six immutable diagnostic images are delivered with the thesis evidence and
are not stored in Git. Supply their directory when auditing them:

```sh
uv run python tests/evaluation/scale_failure/evaluate_scale_failure.py \
  --evidence-dir /path/to/scale_failure_images
```

Without the external images, the evaluator still checks the active correction
and reports the historical image audit as skipped.

Run from the repository root:

```sh
uv run python tests/evaluation/scale_failure/evaluate_scale_failure.py
```

CSV verification and metadata are written to
`outputs/evaluation/5_6_failure_case/`. The six source images remain separate so
they can be used as ordinary thesis subfigures. The HDRI angle sweep is
preserved in legacy storage but is not part of the canonical Section 5.6
evidence.
