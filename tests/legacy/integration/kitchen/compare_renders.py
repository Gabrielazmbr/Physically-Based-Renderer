#!/usr/bin/env -S uv run --script
"""
Compares two linear EXR renders. Used to verify --passes:
  - regression check: two renders that should be bit-identical
  - equivalence check: does accumulation behave like an ordinary render
    at the same total spp (compare its diff-from-reference against the
    diff between two independent ordinary renders)

Usage: uv run compare_renders.py a.exr b.exr
"""
import sys
import numpy as np
import mitsuba as mi

mi.set_variant('llvm_ad_rgb')

a_path, b_path = sys.argv[1], sys.argv[2]
a = np.array(mi.Bitmap(a_path), dtype=np.float32)
b = np.array(mi.Bitmap(b_path), dtype=np.float32)

if a.shape != b.shape:
    print(f'SHAPE MISMATCH: {a.shape} vs {b.shape}')
    sys.exit(1)

diff = np.abs(a - b)
identical = np.array_equal(a, b)

print(f'{a_path}  vs  {b_path}')
print(f'  bit-identical: {identical}')
print(f'  mean |diff|:   {diff.mean():.6f}')
print(f'  max  |diff|:   {diff.max():.6f}')
print(f'  RMSE:          {np.sqrt((diff ** 2).mean()):.6f}')
print(f'  a mean:        {a.mean():.6f}')
print(f'  b mean:        {b.mean():.6f}')
