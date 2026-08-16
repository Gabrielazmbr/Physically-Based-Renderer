# Sampling and noise evaluation — Thesis Section 5.3

`evaluate_sampling.py` consolidates the existing sampling and post-process
experiments into five connected questions:

1. Does luminance importance sampling preserve the expected image mean while
   reducing repeated-seed variance relative to uniform sphere sampling?
2. How do Mitsuba's independent/stratified samplers and the environment CDF's
   resolution/pooling method affect variance at matched sample counts?
3. Does the implemented mean-subtraction compensation improve sampling across
   HDRIs with different luminance distributions?
4. What bias/outlier trade-off is introduced by firefly clamping?
5. How much does OIDN reduce error, and why is box-filtered input required?

The environment experiments use 24 matched seeds at 16 spp. They report mean
per-pixel standard deviation and a leave-one-seed-out jackknife 95% interval. The importance
comparison also uses conservative, geometry-derived and eroded masks for the
sphere, floor, and directly visible background.

The firefly experiment uses four matched seeds at 256 spp. OIDN is evaluated
against independently seeded accumulated references, with error reported both
overall and outside the directly visible emitter region.

Canonical results are written to `outputs/evaluation/5_3_sampling/` with
separate `data/`, `renders/`, and `figures/` directories.

A reduced design check uses the separate quick-output tree:

```sh
uv run python tests/evaluation/sampling/evaluate_sampling.py --quick \
  --output outputs/quick/5_3_sampling
```

## Figures

- `sampling_variance_summary.svg`: four-panel numerical summary of importance
  sampling, sampler choice, CDF construction, and compensation.
- `environment_importance_venice.png` and
  `environment_importance_sundowner.png`: top row shows matched-seed uniform
  and importance-sampled renders; bottom row shows repeated-seed standard
  deviation using one shared colour scale.
- `environment_importance_*_convergence.png`: uniform 16 spp, importance 16
  spp, and the 24-seed importance mean from left to right. The third panel
  distinguishes material appearance from a particularly noisy single render.
- `environment_importance_*_convergence_exposed_down.png`: the same comparison
  divided by eight (three stops down), matching the display exposure used for
  the firefly figure and preventing HDR samples from clipping blue/white.
- `mis_compensation_*.png`: compensation disabled/enabled on each of the four
  HDRIs. As above, the top row is a matched render and the bottom row is the
  repeated-seed standard-deviation map on one shared within-HDRI scale.
- `firefly_clamp_comparison.png`: unclamped, clamp 3, and clamp 50 from left to
  right, shown three stops down to retain bright outliers.
- `oidn_low_spp_comparison.png`: noisy, OIDN-denoised, and accumulated
  reference from left to right.

Superseded scripts are preserved unchanged in `tests/legacy/sampling/`.
Feature-appearance experiments remain assigned to Thesis Section 5.4.
