# Validation Numbers


## 1. Path Tracer Validation — White Furnace Test

Tests that the path tracer correctly handles energy against
BSDF (Mitsuba's built-in `diffuse`), isolating integrator correctness. A passing furnace test means mean (average f every pixel) ≈ 1.0, 
std (standard deviation) → 0 as spp increases.

Each integrator run with a different seed, to confirm convergence is
genuine rather than an artifact of shared randomness.

| Integrator | SPP | Seed | Mean | Std | Result |
|---|---|---|---|---|---|
| Custom `path_tracer` | 256 | 0 | 1.0000 | 0.0068 | PASS |
| Custom `path_tracer` | 1024 | 0 | 1.0000 | 0.0034 | PASS |
| Mitsuba `path` (reference) | 256 | 1000 | 1.0000 | 0.0068 | PASS |
| Mitsuba `path` (reference) | 1024 | 1000 | 1.0000 | 0.0034 | PASS |

**Interpretation:** the custom path tracer and Mitsuba's own reference
integrator, run independently, converge to
equal results at every tested spp, both mean
*and* std. Noise also halves as spp quadruples (256→1024), consistent
with the expected `1/√n` Monte Carlo convergence rate. This confirms the
custom path tracer correctly handles energy transport. 

---

## 2. GGX Energy Loss — Reference Comparison

This test uses Mitsuba's own `roughconductor` (GGX) BSDF,  paired with
my custom path tracer, compared against Mitsuba's own reference path
tracer using the same BSDF. A directional, energy-lossy BSDF helps testing
whether the path tracer's NEE/MIS logic is correct.

`alpha = roughness²` is used throughout, matching `principled_bsdf`'s own
internal convention, so "roughness" here means the same physical surface
as it does in section 3 and in the summary chart.

### 2a. Mitsuba roughconductor (GGX) + Mitsuba path tracer (reference)

| Roughness | SPP | Seed | Mean | Std |
|-----------|-----|------|--------|--------|
| 0.0 | 256 | 43 | 1.0000 | 0.0003 |
| 0.5 | 256 | 43 | 0.9300 | 0.0647 |
| 1.0 | 256 | 43 | 0.6455 | 0.3097 |

### 2b. Mitsuba roughconductor (GGX) + custom path tracer

| Roughness | SPP | Seed | Mean | Std |
|-----------|-----|------|--------|--------|
| 0.0 | 256 | 56 | 1.0000 | 0.0002 |
| 0.5 | 256 | 56 | 0.9299 | 0.0647 |
| 1.0 | 256 | 56 | 0.6455 | 0.3097 |

**Interpretation:** two independently-seeded runs, custom vs. Mitsuba
reference, converge to matching results at every roughness — confirming
the custom path tracer is correct. The energy loss shown here (up to ~35%
at roughness=1.0) is a known property of GGX itself, not the implementation.

---

## 3. Principled BSDF Validation — White Furnace Test

Tests that the custom Principled BSDF is energy conserving. Uses the
custom path tracer (validated above). Results below are the final,
corrected numbers, after two rounds of bug fixes (see section 6).

### Diffuse mode (metallic=0, base_colour=[1,1,1])

| Roughness | Mean   | Std    | Result |
|-----------|--------|--------|--------|
| 0.0       | 1.0001 | 0.0123 | PASS — exact |
| 0.5       | 0.9792 | 0.0648 | Acceptable |
| 1.0       | 0.9582 | 0.0857 | Acceptable |

**Interpretation:** exact energy conservation at roughness 0.0, with a
monotonically increasing, physically expected loss as roughness grows —
matching the GGX single-scattering signature documented in section 2.
No energy gain at any tested roughness.

### Metallic mode (metallic=1, base_colour=[1,1,1])

| Roughness | Mean   | Std    | Result |
|-----------|--------|--------|--------|
| 0.0       | 1.0000 | 0.0003 | PASS — exact |
| 0.5       | 0.9300 | 0.0647 | Matches `roughconductor`  |
| 1.0       | 0.6455 | 0.3097 | Matches `roughconductor`  |


---

## 4. Chi-Squared Statistical Test — BSDF Sampling Consistency

Tests that `sample()` and `pdf()` are statistically consistent. Uses
Mitsuba's built-in chi2 module. Reference: Jakob (2010).

### 4a. Reference sanity check — Mitsuba's own `principled` plugin

| Config | Result | Notes |
|--------|--------|-------|
| r=1.0, m=0.0 | PASS | |
| r=0.1, m=1.0 | FAIL | alpha=0.01 too sharp for the numerical grid resolution |

### 4b. Custom `principled_bsdf`

| Material Config | Result | p-value | Histogram Sum | PDF Sum |
|----------------|--------|---------|----------------|---------|
| Diffuse (r=1.0, m=0.0) | PASS | 0.934 | 0.950 | 0.950 |
| Plastic (r=0.3, m=0.0) | PASS | 0.893 | 0.999 | 0.999 |
| Metal (r=0.3, m=1.0)   | PASS | 0.171 | 0.992 | 0.992 |
| Mixed (r=0.4, m=0.5)   | PASS | 0.849 | 0.988 | 0.988 |

**Interpretation:** all four configs pass — sampled directions are
statistically consistent with the reported PDF at every tested
metallic/roughness combination.


---

## 5. Summary

| Component | Status | Notes |
|-----------|--------|-------|
| Path tracer energy transport | Correct | Matches Mitsuba reference exactly (sections 1, 2) |
| BSDF energy conservation — diffuse mode | Acceptable | 0% loss at roughness 0.0, rising to ~4% at roughness 1.0, consistent with GGX single-scattering (section 3) |
| BSDF energy conservation — metallic mode | Acceptable | 0% loss at roughness 0.0, rising to ~35% at roughness 1.0, matches Mitsuba's `roughconductor` exactly (section 3) |
| BSDF sampling consistency — diffuse | PASS | p=0.934 |
| BSDF sampling consistency — plastic | PASS | p=0.893 |
| BSDF sampling consistency — metal | PASS | p=0.171 |
| BSDF sampling consistency — mixed metallic | PASS | p=0.849 |

---

## 6. Known Limitations

1. **GGX single-scattering energy loss** — the Cook-Torrance microfacet
   model doesn't account for multiple scattering between microfacets.
   Energy is lost at high roughness: section 2 shows up to ~35% loss at
   roughness=1.0 for Mitsuba's own `roughconductor`, matched exactly by
   the custom BSDF in metallic mode (section 3), confirming this is a
   property of GGX itself, not the implementation. The same effect
   appears at much smaller magnitude in diffuse mode (up to ~4% at
   roughness=1.0), since diffuse reflection recovers energy at high
   roughness in a way pure specular reflection cannot. Production fix:
   Kulla & Conty (2017) energy compensation, used in Arnold and
   RenderMan.


------- Part #2 --------

# Importance Sampling

### 7. Custom Environment Emitter — Unbiasedness Check (Uniform vs. Importance Sampling)

**Purpose:** Verify that `CustomEnvmap`'s uniform sphere sampling (`sample_direction`,
`pdf_direction`) is statistically correct — i.e. converges to the same result as
Mitsuba's importance-sampled `envmap`, just with more noise. This isolates the
custom emitter as the only variable: same scene, same `path_tracer`, same BSDF,
same spp — only the emitter differs (`custom_envmap` uniform vs. built-in `envmap`
importance-sampled).

**Method:** Rendered `environment_lighting_scene` (studio_kontrast_04, metallic
sphere + diffuse floor) through `path_tracer` twice, changing only the emitter.
Compared pixel-wise.

| Metric | Value | Interpretation |
|---|---|---|
| Mean signed diff | +0.001008 | ~0 → no systematic bias between samplers |
| Mean abs diff | 0.006656 | Consistent with per-pixel MC noise at this spp |
| Max abs diff | 0.877397 | Single-pixel outlier on bright softbox reflection — expected uniform-sampling firefly, not a bug (see note below) |

**Result: PASS.** Mean signed difference is negligible relative to image brightness,
confirming the uniform emitter is unbiased — it agrees with the importance-sampled
reference in expectation. The nonzero mean-abs and large max-abs are the expected
signature of uniform HDR sampling: rays that happen to land on the bright softbox
carry weight `radiance / (1/4π)`, producing occasional high-variance speckles
concentrated on specular/bright regions. This is precisely the noise importance
sampling (next stage) is intended to remove — it is the "before" measurement for
that comparison, not a defect.

**Note:** This confirms `CustomEnvmap`'s `sample_direction`/`pdf_direction`,
`set_scene` bounding-sphere handling, and its integration with the existing
NEE/MIS machinery in `path_tracer.py` are all correct. It does not yet test
importance sampling — that comparison is the deliverable of Week 6's next stage.


### 7a. Custom Environment Emitter — Importance Sampling Unbiasedness Check

**Purpose:** Verify `CustomEnvmap`'s luminance-importance-sampled `sample_direction`/
`pdf_direction` (via `mi.DiscreteDistribution2D` + manual solid-angle Jacobian
`pdf_pmf * (W*H) / (2*pi^2*sin(theta))`) converges to the same result as
Mitsuba's built-in `envmap`, confirming the CDF inversion and Jacobian are correct.

| Metric | Value |
|---|---|
| Mean signed diff | -0.001859 |
| Mean abs diff | 0.003894 |
| Max abs diff | 0.733282 |

**Result: PASS.** Mean signed diff negligible → unbiased. Mean abs diff lower
than the uniform-sampling unbiasedness check (0.006656) against the same
reference, an early indicator of reduced variance even before the controlled
equal-spp noise comparison (see below).


### 7b. Custom Environment Emitter — Importance Sampling Noise Reduction

**Purpose:** Quantify the variance reduction from luminance importance sampling
(`DiscreteDistribution2D`-based `CustomEnvmap`) vs. uniform sphere sampling, at
equal spp, across two HDRIs of differing luminance concentration.

**Method:** For each HDRI, rendered `environment_lighting_scene` 24 times per
sampling mode (16 spp, seeds 0-23) through `path_tracer`. Computed per-pixel
std across the 24 repeats — a direct, reference-free variance measurement.
Regions were split using an exact per-pixel hit mask from `scene.ray_intersect`
compared against `scene.shapes()` at the Dr.Jit level (a NumPy-level `==`
comparison after array conversion silently fails to match shape pointers and
was corrected during this test).

**HDRI concentration** (top-1%-brightest-pixel energy share, computed
independently as a predictor of expected effect size):
| HDRI | Top-1% energy share | Max/mean luminance |
|---|---|---|
| venice_sunset | 9.1% | 4,882 |
| sundowner_overlook | 73.5% | 172,473 |

**Results (24 seeds, 16 spp):**
| Region | Venice reduction | Sundowner reduction |
|---|---|---|
| Background (strict, silhouette-eroded) | ~0% (noise floor) | ~0% (noise floor) |
| Sphere (near-mirror, roughness=0.1, metallic=1.0) | 18.7% | 78.0% |
| Floor (diffuse) | 34.9% | 86.8% |

**Result: PASS — effect scales with light concentration, as predicted.**
Background shows no reduction, consistent with those pixels' radiance coming
from `eval()` (identical code path regardless of sampling mode) rather than
`sample_direction`. Floor and sphere show substantial, concentration-dependent
reduction, with the near-delta sundowner sun producing dramatic improvement on
both diffuse and specular-adjacent regions.

**False lead investigated and resolved:** an initial naive background mask
(pixel-center-ray hit test) showed a spurious 23-65% "reduction" in supposed
background pixels. Traced to AA-jittered sub-samples near the sphere's
silhouette picking up reflection contribution that the center-ray mask
misclassified as pure background. Confirmed via a silhouette-eroded strict
mask, which collapsed the diff to floating-point noise (~0.0001) for both
HDRIs. Underscores the importance of exact, per-sample geometric masks
(rather than brightness- or single-ray-based proxies) when isolating regions
for noise analysis.

---

# 8. DCC Scene Import Validation — Blender Pipeline

Tests whether a scene authored in a real DCC tool (Blender) can be
converted into a scene dict using this project's own plugins
(`principled_bsdf`, `thinlens`, `custom_envmap`, `path_tracer`) and
rendered to a result consistent with Blender's own reference renderer
(Cycles), rather than relying on hand-built test scenes.

**Method:** Scene exported from Blender via the `mitsuba-blender`
add-on. Camera and environment-emitter transforms are extracted
directly from Mitsuba's own resolved sensor/emitter matrices
(`sensor.world_transform()`) rather than hand-derived from the
exported XML's `<rotate>`/`<translate>` tags — this avoids needing to
know Mitsuba's rotation-composition convention, since the matrix is
already fully resolved by Mitsuba's own parser.

### 8a. Proof of concept — single cube

A default Blender cube, exported and reconstructed through the custom
pipeline, matched a Mitsuba-native reference render of the same
export. This test surfaced a real bug: `ThinLensCamera`'s FOV math had
the aspect-ratio scaling on the wrong axis for `fov_axis="x"` (fixed:
`x` now gets the raw `tan_fov`, `y` is divided by aspect, rather than
the reverse). This was invisible in prior square-format test scenes,
since at aspect ratio 1.0 the two formulations are numerically
identical — only a non-square DCC camera exposes the difference.

### 8b. Full scene — Lego 856 Bulldozer (Blendswap, CC-BY-NC, Heinzelnisse)

A ~439-shape, 9-material scene with an HDRI environment light —
substantially more complex than any hand-built validation scene,
chosen specifically to stress-test the pipeline beyond what a
synthetic test could.

**Material mapping:** each Mitsuba `diffuse`/`twosided` material
mapped to `principled_bsdf` (`base_color`→`base_colour`, flat
`roughness=0.4`, `metallic=0.0`). One material (`RubberBand`) was
exported as a `blendbsdf` mixing two diffuse materials; since
`principled_bsdf` has no blend-BSDF equivalent, this was collapsed to
a single flat color (weighted average of the two blended colors) —
a deliberate simplification, not an oversight.

**Environment lighting:** `CustomEnvmap` was extended to support a
`to_world` transform (previously assumed identity orientation), needed
because Blender's Z-up→Y-up axis convention rotates the HDRI relative
to Mitsuba's default mapping. The same "extract Mitsuba's own resolved
matrix" technique used for the camera was applied here.

**Result:** custom render closely matches Blender's Cycles reference —
correct geometry, correct HDRI orientation, correct per-material
colors, correct camera framing.

### 8c. Finding — `principled_bsdf` cannot represent a true Lambertian material

The custom render showed visibly more specular reflection across every
brick than the Cycles reference. Isolated via a controlled swap: with
every other variable held fixed (same scene, camera, HDRI, geometry),
replacing `principled_bsdf` with Mitsuba's built-in `diffuse` BSDF for
all nine materials reproduced the Cycles reference closely, confirming
the specular lobe as the cause.

**Root cause:** `_spec_prob()` has a hardcoded floor of 0.1 (10%
minimum probability of sampling the specular lobe, regardless of
input parameters), and the dielectric Fresnel term defaults to
`F0=0.04`. Together these mean `principled_bsdf` cannot represent a
true zero-specular Lambertian surface — only a "very rough,
low-Fresnel" approximation of one.

**Scope note for thesis:** this is a genuine, documented limitation,
not a bug — the model was designed around Disney's principled
parameterization, which assumes some baseline specular response is
always physically present. Materials that are genuinely
specular-free (chalk, unfinished matte cardboard) are not exactly
representable; glossy/plastic-like materials (the actual Lego bricks
being approximated here) arguably suit this model better than a pure
Lambertian would have anyway.
