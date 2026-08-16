# Legacy integration experiments

These scripts document the exploratory Blender-to-Mitsuba import work that
preceded the canonical Section 5.5 evaluator.

- `test_import_blender.py` is the non-square single-cube proof of concept that
  exposed the physical-camera aspect-ratio error.
- `test_import_lego.py` is the first full Lego reconstruction and contains the
  material parsing logic later consolidated into the integration evaluator.

They intentionally retain their original absolute paths and output names as a
historical record. Use `tests/evaluation/integration/evaluate_integration.py`
for reproducible thesis evidence.
