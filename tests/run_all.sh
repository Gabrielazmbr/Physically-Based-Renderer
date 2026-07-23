#!/usr/bin/env bash
set -e
echo "=== Furnace: diffuse (path tracer control) ==="
uv run tests/furnace_diffuse_pathtracer.py
echo
echo "=== Furnace: GGX reference (roughconductor) ==="
uv run tests/furnace_ggx_reference.py
echo
echo "=== Furnace: Principled BSDF ==="
uv run tests/furnace_principled.py
echo
echo "=== Chi-squared: BSDF sampling consistency ==="
uv run tests/chi_test_bsdf.py
