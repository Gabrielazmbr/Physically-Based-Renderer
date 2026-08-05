#!/usr/bin/env -S uv run --script
"""
Reads a with_aovs=True render, verifies its channel layout, writes each AOV
out as a viewable image, and runs OIDN denoising.

The raw 10-channel EXR will not display correctly.

"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath('../../..'))

import numpy as np
import mitsuba as mi

mi.set_variant('llvm_ad_rgb')

from denoisers.oidn import denoise_composite_aov_render, denoise_aov_render

parser = argparse.ArgumentParser()
parser.add_argument('--input', default='kitchen_aovs.exr')
parser.add_argument('--outdir', default='aov_output')
parser.add_argument('--emitter-threshold', type=float, default=2.0,
                     help='Luminance above which a pixel is treated as a directly '
                          'visible emitter and left un-denoised (see Section 17)')
parser.add_argument('--no-composite', action='store_true',
                     help='Use plain denoise_aov_render instead of the emitter-masked '
                          'composite version, for an A/B of whether masking matters here')
args = parser.parse_args()

os.makedirs(args.outdir, exist_ok=True)

# ---- Read and verify ----------------------------------------------------
bmp = mi.Bitmap(args.input)
print(f'Read {args.input}')
print(f'  size:        {bmp.size()}')
print(f'  pixel fmt:   {bmp.pixel_format()}')
print(f'  channels:    {bmp.channel_count()}')
try:
    print(f'  channel names: {[bmp.struct_().operator_getitem(i).name for i in range(bmp.channel_count())]}')
except Exception:
    pass  # channel-name introspection differs across versions; not essential

arr = np.array(bmp, dtype=np.float32)
print(f'  array shape: {arr.shape}')

if arr.shape[-1] < 10:
    print()
    print(f'WARNING: expected 10 channels (3 colour + 7 AOVs), found {arr.shape[-1]}.')
    print('Was this rendered with --aovs? Falling back to colour-only denoising.')

# Per-channel sanity stats — these confirm the AOVs hold real data rather
# than being empty or misordered.
print()
print('Per-channel ranges (confirms the AOVs are populated and in the right slots):')
labels = ['color.R','color.G','color.B','albedo.R','albedo.G','albedo.B',
          'normal.X','normal.Y','normal.Z','depth']
for i in range(min(arr.shape[-1], len(labels))):
    ch = arr[..., i]
    print(f'  {labels[i]:<10} min={ch.min():>9.4f}  max={ch.max():>9.4f}  mean={ch.mean():>9.4f}')

# ---- Split AOVs into viewable images ------------------------------------
def save(name, data, normalize=False):
    d = np.asarray(data, dtype=np.float32)
    if normalize:
        lo, hi = float(d.min()), float(d.max())
        d = (d - lo) / (hi - lo) if hi > lo else np.zeros_like(d)
    if d.ndim == 2:
        d = np.stack([d]*3, axis=-1)
    path = os.path.join(args.outdir, name)
    mi.util.write_bitmap(path, mi.TensorXf(np.ascontiguousarray(d)))
    print(f'  wrote {path}')

print()
print('Writing viewable AOV images:')
save('00_beauty.png', arr[..., 0:3])
if arr.shape[-1] >= 9:
    save('01_albedo.png', arr[..., 3:6])
    # normals are -1..1; remap to 0..1 so they're viewable in the usual way
    save('02_normal.png', arr[..., 6:9] * 0.5 + 0.5)
if arr.shape[-1] >= 10:
    # depth is unbounded distance; normalize for display only
    save('03_depth.png', arr[..., 9], normalize=True)

# ---- Denoise ------------------------------------------------------------
print()
if args.no_composite:
    print('Denoising (plain, no emitter masking)...')
    denoised = denoise_aov_render(arr, hdr=True)
    out_name = '04_denoised_plain.png'
else:
    print(f'Denoising (emitter-masked composite, threshold={args.emitter_threshold})...')
    denoised = denoise_composite_aov_render(arr, emitter_threshold=args.emitter_threshold, hdr=True)
    out_name = '04_denoised_composite.png'

save(out_name, denoised)
save('05_denoised.exr', denoised)  # linear, for any further comparison work

# ---- Report ------------------------------------------------------------
color = arr[..., 0:3]
diff = np.abs(color - denoised)
print()
print('Denoise summary:')
print(f'  mean |change|: {diff.mean():.5f}')
print(f'  max  |change|: {diff.max():.5f}')
print(f'  pixels changed >1%: {(diff.max(axis=-1) > 0.01).mean()*100:.1f}%')
print()
print(f'Done. Compare {args.outdir}/00_beauty.png against {args.outdir}/{out_name}')
