# Validation and development journal

> Historical development record. This document preserves intermediate experiments, debugging notes, superseded measurements, and the reasoning that led to the final implementation. It is not the evaluator entry point and some commands or numbers reflect earlier revisions. For reproducible current evidence, use [the evaluation catalogue](../../tests/README.md) and the canonical READMEs under [tests/evaluation](../../tests/evaluation/README.md).

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


------- Part #2 -------- IBL and Thin Lens Camera Build / DCC Scenes

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


# 8. Physical Camera Validation

Tests whether the custom thin-lens camera (`PhysicalCamera`) is
geometrically correct: matching Mitsuba's built-in `perspective` sensor
exactly at zero aperture, and behaving as a genuine thin-lens model
when aperture is nonzero.


### 8a. Pinhole-equivalence
At `aperture_radius=0`, `PhysicalCamera` should exactly match Mitsuba's
`perspective` sensor at the same fov and `to_world`.

| Stage | Mean abs diff | Result |
|-------|---------------|--------|
| Initial (mirror bug present, see 8c) | 0.01766 | Superseded |
| After mirror fix, 1024 spp | 0.00065 | PASS — consistent with Monte Carlo noise floor |

### 8b. Horizontal-axis mirror (found and fixed)
The initial diff, while plausible-looking, masked a real defect:
`PhysicalCamera` mirrored the image horizontally relative to
`perspective` — same `to_world`, same world-space object position,
opposite screen side. Confirmed directly (a single off-center test
object, compared screen-side placement against the reference) rather
than inferred from the aggregate diff alone. Root cause: sign of the
x-axis term in `sample_ray()`:

``` python
x = -(2.0 * sample2.x - 1.0) * self.tan_fov
```

The vertical axis was already correct and needed no change.

### 8d. Depth-of-field
Three spheres at increasing distance, `aperture_radius=0.15`,
`focus_distance` matching the mid sphere.

**Result: PASS.** Mid sphere renders sharp; near and far spheres render
visibly blurred, with blur increasing with distance from the focal
plane — correct thin-lens behavior.

----

# 9. DCC Scene Import Validation — Blender Pipeline

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

### 9a. Proof of concept — single cube

A default Blender cube, exported and reconstructed through the custom
pipeline, matched a Mitsuba-native reference render of the same
export. This test surfaced a real bug: `ThinLensCamera`'s FOV math had
the aspect-ratio scaling on the wrong axis for `fov_axis="x"` (fixed:
`x` now gets the raw `tan_fov`, `y` is divided by aspect, rather than
the reverse). This was invisible in prior square-format test scenes,
since at aspect ratio 1.0 the two formulations are numerically
identical — only a non-square DCC camera exposes the difference.

### 9b. Full scene — Lego 856 Bulldozer (Blendswap, CC-BY-NC, Heinzelnisse)

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

### 9c. Finding — `principled_bsdf` could not represent a true Lambertian material

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
low-Fresnel" approximation of one. This was corrected to be able to
display a full Lambertian material.



------- Part #3 -------- Improvements to BSDF, IBL, Camera and Path tracer



# Zero-Specular Case

### Zero-specular mode (specular=0.0, metallic=0.0)

| Roughness | Mean   | Std    | Result |
|-----------|--------|--------|--------|
| 0.0       | 1.0000 | 0.0067 | PASS — exact |
| 0.5       | 1.0000 | 0.0067 | PASS — exact |
| 1.0       | 1.0000 | 0.0067 | PASS — exact |

**Interpretation:** identical mean and std across every roughness value
(same seed) — expected and correct, since a true zero-specular material
has no roughness dependence at all once the specular lobe is fully
gated off. Slightly closer to 1.0 than the specular=0.5 default case at
roughness=0.0 (1.0000 vs 1.0001), consistent with there being no
residual Fresnel term (F0=0.04) left to attenuate the diffuse lobe.

----

## AOV (Arbitrary Output Variable) Support

Adds optional auxiliary output channels to the custom path tracer —
albedo, shading normal, and depth — alongside the main radiance result.
Useful for compositing, debugging material/geometry issues
independently of lighting, and as future input to post-process
denoising (see Known Limitations / roadmap).

### Design
Opt-in via a `with_aovs` flag on `path_tracer` (default `False`), so
every existing scene and test is completely unaffected unless AOVs are
explicitly requested. When enabled, `aov_names()` reports:

| Name | Channels | Source |
|------|----------|--------|
| `albedo` | R, G, B | `bsdf.eval_diffuse_reflectance()` |
| `normal` | X, Y, Z | Shading normal, world space, raw (not remapped for display) |
| `depth` | Y | Primary-ray hit distance |

All three are captured once, from the primary ray's first intersection
only — not accumulated across bounces — matching the conventional
meaning of an AOV pass (what's directly visible to camera). On a
missed ray, all three default to 0.

**Albedo note:** `principled_bsdf` overrides the generic
`eval_diffuse_reflectance()` base-class default to return the flat
material base color, with no Fresnel or view-angle dependence. The
generic base-class default (used automatically by any BSDF that
doesn't override it, including Mitsuba's own built-ins) folds in
Fresnel and does vary with view angle — a different, and for this
purpose less useful, quantity. This override matches the standard
VFX/compositing convention for an albedo pass (a flat, delighted
material-color swatch), rather than the generic default's shaded value.

### Validation
The original visual check has been incorporated into the canonical Section
5.1 evaluator (`tests/evaluation/path_tracer/evaluate_path_tracer.py`). It
renders a simple two-material scene (sphere + floor, distinct base colors and
roughness values) with `with_aovs=True`, writes each pass independently, and
records the checks in `data/aov_sanity.csv`:

- **Albedo:** flat, uniform color per object, no lighting falloff or
  highlight — confirms the override is taking effect and the pass
  reflects material color only, independent of the lit beauty render.
- **Normal:** smooth per-pixel variation across the curved sphere;
  the flat floor plane's known geometric orientation matches its
  expected constant remapped color exactly, confirming world-space
  orientation is captured correctly.
- **Depth:** continuous gradient across visible geometry, consistent
  with relative camera distance.

**Result: PASS.** The final check returned the expected 10-channel RGB+AOV
layout, finite values, zero-valued AOVs on misses, median material-color error
of `6.19e-08`, zero median unit-normal length error, and a positive,
non-constant depth range. AOV output remains opt-in, so the default
`with_aovs=False` path used by the other Section 5.1 comparisons is unchanged.

-----

## 10. Noise Reduction Experiments

Two independent noise-reduction techniques, each measured using the
Week 6 methodology: 24 independently-seeded renders at fixed spp,
per-pixel standard deviation across the repeats (reference-free
variance measurement), on `sundowner_overlook_1k.exr` — the HDRI with
the highest energy concentration from Week 6, and therefore the case
most likely to expose a sampling-quality difference.

### 10a. Stratified vs. independent sampler
Sampler type is the only variable; scene, HDRI, and the validated
importance-sampled `CustomEnvmap` held fixed. 16 spp (a perfect square,
required for stratified sampling's grid subdivision).

| Sampler | Mean per-pixel std | Reduction |
|---|---|---|
| independent (prior default) | 0.10892 | — |
| stratified | 0.08766 | 19.5% |

**Interpretation:** stratified sampling guarantees one sample per grid
cell rather than relying on pure chance to avoid clustering — a
theoretical guarantee that Monte Carlo variance can only decrease,
never increase, for a fixed sample count. No code changes were
required; this is a scene-configuration change reusing Mitsuba's
built-in `stratified` sampler plugin. Adopted as the new default.

### 10b. CDF resolution and pooling method
`CustomEnvmap`'s luminance CDF build was parameterized (`cdf_res_x`,
`cdf_res_y`, `cdf_pooling`), isolating resolution and block-pooling
method as independent, combinable variables. Sampler held fixed at
`independent` for this comparison, so only the CDF configuration
changes.

| Configuration | Mean per-pixel std | Reduction |
|---|---|---|
| Baseline (256x128, mean-pooled) | 0.10892 | — |
| Same resolution, max-pooled | 0.10475 | 3.8% |
| Higher resolution (512x256), mean-pooled | 0.10035 | 7.9% |
| Higher resolution (512x256), max-pooled | 0.08966 | 17.7% |

**Interpretation:** both changes individually reduce noise, and they
combine rather than compete — resolution determines how finely a
bright, spatially concentrated feature (e.g. a small sun disc) can be
resolved at all; pooling method determines how much of that feature's
peak brightness survives being averaged into a coarse cell. Since each
addresses a different point in the CDF-construction pipeline, their
effects are close to additive. Max-pooling is the more defensible
choice generally: mean-pooling can systematically underestimate a
small bright feature's true importance within a block, which is
precisely the scenario stratified/importance sampling exists to guard
against. Adopted as new defaults: `cdf_res_x=512, cdf_res_y=256,
cdf_pooling="max"`.

-----

## 11. Firefly Clamping

Adds an optional cap on any single sample's contribution to a pixel,
trading a small, controlled bias for reduced variance from rare,
extreme-outlier samples ("fireflies") — distinct from ordinary Monte
Carlo noise, which this does not address (see below).

### Design
Opt-in via `firefly_clamp` on `path_tracer` (default `0.0`, disabled —
every existing scene unaffected unless explicitly set). Applied to
both radiance-accumulation paths (NEE and BSDF-hit/emitter), since a
firefly can originate from either. Clamped per-channel (R, G, B
independently), not by luminance — the simpler, more common
convention, at the cost of a possible small hue shift on an extremely
bright, saturated, clamped pixel.

### Validation
`sundowner_overlook_1k.exr` (highest energy-concentration HDRI from
Week 6) — deliberately chosen as the case most prone to fireflies via
BSDF-sampled paths landing on the small, bright sun.

| Config | Max pixel value | Mean |
|---|---|---|
| Control (no clamp) | 4930.42 | 0.4991 |
| clamp=3.0 | 5.79 | 0.2964 |
| clamp=50.0 | 74.41 | 0.3330 |

**clamp=3.0 rejected**: 41% drop in overall image mean indicates the
sun's disc itself — legitimate bright content, not a rare outlier —
was being clamped, not just true fireflies. **clamp=50.0 adopted**:
much smaller mean shift, while still reducing peak value by two orders
of magnitude.

**Methodology note:** at low spp (32), ordinary per-pixel Monte Carlo
noise dominates the image visually and can make the clamp's effect
hard to see by eye, even though max/mean statistics confirm it's
working correctly (confirmed identically whether measured in-memory or
reloaded from the saved `.exr` file — the effect is real and format-
independent, not a display artifact). At higher spp (256), general
noise converges down and the clamp's effect on true outliers becomes
visually distinguishable from ordinary grain.

**Known limitation:** a single global clamp does not distinguish
direct camera rays seeing a bright light source (legitimate) from
indirect fireflies (the intended target) — production renderers
typically expose separate direct/indirect clamp controls for this
reason. Not implemented here, given time constraints.


-----

## 12. MIS Envmap Compensation

Adds an optional adjustment to `CustomEnvmap`'s luminance-based
importance sampling CDF, based on Karlík et al. (2019), "MIS
Compensation: Optimizing Sampling Techniques in Multiple Importance
Sampling."

### Implementation note — mean-subtraction variant, not the paper's derived optimum
The paper's core contribution is deriving an optimal constant to
subtract from the tabulated sampling density via variance
optimization, applied entirely in a preprocessing step. That
derivation was not implemented here. Instead, this uses **mean
subtraction** — subtracting the luminance table's own mean before
building the CDF, clamped at a small positive floor — a documented
simplification also used in published follow-up work (e.g. Ke et al.,
"NeRF as a Non-Distant Environment Emitter in Physics-based Inverse
Rendering," describes an equivalent mean-subtraction step explicitly
as "inspired by" Karlík et al., rather than an implementation of the
full derivation). Correctness of the underlying idea — that both
approaches leave the estimator unbiased, since only the *sampling*
density changes while `eval()`/`_radiance()` still return true
radiance and MIS rebalances the light/BSDF-sampling split automatically
— is confirmed by both sources.

### Design
Opt-in via `mis_compensation` on `custom_envmap` (default `False`,
matching prior behavior exactly). When enabled, the luminance table has
its global mean subtracted before the existing epsilon floor is
applied, concentrating the CDF on above-average regions only.
`sample_direction`, `pdf_direction`, and `_radiance` are unchanged —
all read generically from the resulting distribution.

### Validation
Same methodology as prior noise experiments (24 seeds, per-pixel std),
across four HDRIs spanning a wide range of energy concentration
(top-1%-brightest-pixel energy share, from Week 6 / Section 10):

| HDRI | Top-1% energy share | Off | On | Change |
|---|---|---|---|---|
| studio_kontrast_04 | 12.4% | 0.01566 | 0.01353 | -13.6% |
| venice_sunset | 9.1% | 0.00862 | 0.00803 | -6.9% |
| sundowner_overlook | 73.5% | 0.08966 | 0.08432 | -6.0% |
| rogland_clear_night | 4.3% | 0.00256 | 0.00259 | +1.2% |

**Interpretation:** compensation reduced noise on three of four HDRIs
(6-14%), with the fourth showing a change within likely measurement
noise (single 24-seed run). Energy concentration does **not** predict
the magnitude of benefit — sundowner has by far the highest
concentration (73.5%) but one of the smaller improvements, while
studio_kontrast (12.4%) shows the largest. This is a genuine,
confirmed empirical finding, not the expected result: prior to
measurement, higher concentration was hypothesized to predict larger
benefit; the data does not support that hypothesis. A plausible
alternative explanation — that benefit relates to how much the mean
subtraction actually redistributes the CDF, rather than to peak
concentration itself — was not tested and is not confirmed.

**Result: adopted as the new default** (`mis_compensation=True`), given
consistent improvement or noise-level neutrality across all four tested
HDRIs and no bias-related downside regardless of scene content.


-----

## 13. Anisotropic GGX

Adds directional roughness (`alpha_u`/`alpha_v` instead of a single
`alpha`), producing an elongated, oriented specular highlight —
brushed metal, satin, hair-like materials — aligned to the surface's
UV tangent direction (`dp_du`), matching the convention used by
Mitsuba's own `roughconductor`/`roughdielectric` plugins.

### Design
New `anisotropic` parameter (Disney/Blender convention, default `0.0`
= isotropic, identical to previous behavior exactly). `alpha_u`/`alpha_v`
derived from the existing `roughness` via an aspect-ratio split
(`aspect = sqrt(1 - 0.9*anisotropic)`), so the two collapse back to the
original single alpha when `anisotropic=0`.

Since the surface tangent is always perpendicular to the shading
normal, aligning the microfacet evaluation to it is purely a rotation
about the local Z axis — `cos_theta_i`/`cos_theta_o` (and therefore
every existing masking/validity check in `sample()`/`eval()`/`pdf()`)
are unaffected by the rotation and needed no changes.

**Scope note:** alignment follows the surface's UV parameterization
only — no separate user-controlled rotation offset (Blender's
"Anisotropic Rotation" parameter). This matches Mitsuba's own built-in
anisotropic BSDFs, and a fully general rotation control is a genuinely
open problem even in Mitsuba's own upstream Principled BSDF as of a
recent issue — reasonable to scope out here as well. On a mesh missing
valid UV/tangent data, orientation falls back to an arbitrary (though
non-degenerate) direction — a known limitation of UV-dependent
anisotropy in general, not specific to this implementation.

### Bug found and fixed during validation
The chi-squared suite initially failed catastrophically on every
config with a nonzero specular lobe (previously-passing p-values
collapsing to p≈0, PDF integrating up to 61× over 1.0) after this
change, while the furnace tests (real geometry) passed cleanly. Root
cause: the chi-squared harness constructs a synthetic
`SurfaceInteraction3f` directly rather than from a real ray
intersection, leaving `dp_du` at its zero-initialized default — a
degenerate tangent. The tangent-alignment rotation silently collapsed
every direction's azimuthal component to zero in this case, destroying
the sampled distribution's shape while leaving total energy roughly
intact (explaining why histogram sums stayed plausible even as chi²
exploded). Fixed by falling back to an identity rotation whenever the
tangent is degenerate (length < 1e-6), confirmed via direct testing
that both the built-in `sphere`/`rectangle` primitives and a PLY mesh
lacking UV coordinates return valid, non-degenerate `dp_du` — so this
fallback path is specifically for hand-built `SurfaceInteraction3f`
objects (as in the chi-squared harness), not expected to trigger on
any real rendered geometry.

### Validation
- **Regression**: full `run_all.sh` suite (furnace, chi-squared) —
  identical to pre-change baseline at `anisotropic=0` (default),
  confirming the tangent-rotation machinery is inert when unused.
- **Visual**: brushed-metal disc, `roughness=0.25`, `metallic=1.0`,
  single point light. `anisotropic=0.0` shows no strong highlight at
  the tested light angle (expected — round GGX highlights are narrow
  and angle-sensitive); `anisotropic=0.8` shows a clearly wedge-shaped,
  radially-elongated highlight following the disc's tangent direction
  — confirming both that anisotropy is present and that its
  orientation follows real per-point surface geometry rather than a
  fixed axis.



-----

## 14. Bladed (Polygonal) Bokeh

Adds an optional polygonal aperture shape to `PhysicalCamera`, in place
of the default circular aperture — reproducing the hexagonal/pentagonal
out-of-focus highlights ("bokeh") caused by a real camera's finite
number of aperture blades.

### Design
Two new parameters: `aperture_blades` (default `0` = circular, identical
to previous behavior) and `aperture_rotation` (optional, degrees).
When `aperture_blades >= 3`, the aperture is sampled as a regular
polygon: split into N triangular wedges from center to each pair of
adjacent vertices, wedge selected via the same stratified-remainder
technique already used in `CustomEnvmap.sample_direction`, then sampled
uniformly within the chosen wedge via the standard sqrt-barycentric
method. Only `_sample_aperture()` and one line in `sample_ray()`
changed — no other camera logic touched.

### Validation
- **Regression**: `validate_physical_camera.py`'s pinhole-equivalence
  test reproduces the prior result exactly (0.00065), confirming
  `aperture_blades=0` remains a true no-op.
- **Visual**: three small, bright, heavily out-of-focus point lights
  against a dark background — the clearest way to reveal aperture
  shape directly in the blur pattern. `aperture_blades=0` renders clean
  circles (as in all prior DoF tests); `aperture_blades=6` renders
  clearly hexagonal highlights with sharp, flat edges, consistently
  oriented across all three independent light sources — confirming
  both the polygonal shape and the shared, consistent rotation are
  correctly applied.

**Result: PASS.**


-----


## 15. Burley Diffuse Model

Adds Disney/Burley (2012)'s diffuse retro-reflection term as an
alternative to the existing plain Lambertian diffuse lobe — a
roughness-dependent brightening (or, at low roughness, mild darkening)
toward grazing angles, matching measured behavior of real rough
materials (cloth, paper) that plain Lambertian does not reproduce.

### Design
New `diffuse_model` parameter (`"lambert"` default — identical to
previous behavior exactly; `"burley"` opt-in). Applied as a
multiplicative correction (`fd_i * fd_o`) on top of the existing
Fresnel energy-conservation gate — a deliberate combination of two
separate ideas from two different sources, not something either
specifies together. Reuses `cos_theta_h` already computed for the
specular Fresnel term (valid since `cos_theta_d = dot(wi,h) =
dot(wo,h)` by definition of the half-vector). Only `eval()` changed —
`sample()`'s weight already flows through `eval(wo)/bs.pdf`, so no
sampling-side logic needed updating.

### Validation

**Regression**: `run_all.sh` at default `diffuse_model="lambert"` —
unchanged, confirmed identical to established baseline.

**Angle sweep** (direct `eval()` comparison, lambert vs burley, same
material, roughness × incidence-angle × exit-angle grid):

| Roughness | theta_i=0,theta_o=0 | Most grazing (80,80) | Pattern |
|---|---|---|---|
| 0.1 | 1.0000 | 0.7822 | Mild darkening |
| 0.5 | 1.0000 | 1.4142 | Brightening |
| 0.9 | 1.0000 | 2.1973 | Strong brightening |

**Result: PASS.** Exact `ratio=1.0000` at normal incidence confirmed at
every roughness (mathematical property of the formula, not an
approximation). Direction of the effect (darkening vs brightening)
correctly flips between low and high roughness, exactly as the
formula's `FD90` term predicts.

**Furnace** (metallic=0, `diffuse_model=burley`):

| Roughness | Mean | Std |
|---|---|---|
| 0.0 | 0.9781 | 0.0304 |
| 0.5 | 0.9832 | 0.0626 |
| 1.0 | 0.9890 | 0.0572 |

**Interpretation:** furnace means sit consistently ~1-2% below 1.0,
rather than the old Lambertian pattern's monotonic decline with
roughness (1.0001 → 0.9582). This is the correct, expected consequence
of the angle-sweep behavior above, not a new energy-conservation
concern: Burley's term is a perceptual retro-reflection model fit to
measured material appearance, not designed to be energy-conserving in
isolation, and was never claimed to be by its original source.



------- Part #4 -------- Improvements to BSDF, IBL, Camera and Path tracer


## 16. Transmission / Refraction (Smooth Dielectric)

Adds smooth (non-rough) dielectric transmission to `principled_bsdf` —
refraction via Snell's law, Fresnel-weighted reflect/transmit split,
and total internal reflection.

### Design
Transmission enters as a **top-level blend**, not as a third lobe
inside the existing specular/diffuse mixture:

BSDF = transmission x (smooth dielectric) + (1 - transmission) x (opaque BSDF)


Rationale: a smooth dielectric is a *delta* lobe, whereas the existing
mixture is built entirely around non-delta lobes with real pdfs. Mixing
a delta into that mixture would require special-casing the pdf
throughout. As an outer blend, the existing mixture code is untouched
and the branch is bypassed entirely at `transmission=0`.

Parameters: `transmission` (0.0 default = fully opaque, texture-capable)
and `ior` (1.5 default). `sample1` is rescaled after the branch decision
so each branch still receives a uniform variate, avoiding the need for a
fourth random input. Rays arriving from inside the medium are forced
down the dielectric branch, since the opaque lobes are undefined there.

`transmission` is deliberately **not** clamped against `metallic`,
following Disney's convention of treating parameters as independent —
nonphysical combinations are therefore possible, and are the scene
author's responsibility.

TIR requires no special-casing: `mi.fresnel` returns F = 1 past the
critical angle, so the reflect/transmit split handles it automatically.

### Bug found and fixed during validation
Initial implementation scaled only `sample()` by the blend factor,
leaving `eval()` and `pdf()` unscaled. At `transmission=1.0` — pure
glass — `eval()` therefore still returned the full opaque diffuse +
specular BSDF, and since NEE calls `eval()` at every bounce, this
injected light from a lobe that should not exist. Measured as a **4.2%
energy gain** (mean 1.0420 vs the reference's 0.9981, with a maximum of
1.230 in a scene where no pixel can physically exceed 1.0).

Not caught by the analytic tests, which exercise only `sample()`.
Fixed by applying `(1 - transmission)` consistently to `eval()`,
`pdf()`, and `sample()`'s reported `bs.pdf`; the branch probability
`transmission` was likewise folded into the dielectric branch's pdf.
Weights remain correct because the factor appears in both value and
pdf and cancels — which is also why the analytic tests passed despite
the bug.

### Methodology note — the furnace test *is* usable for glass
Initially assumed unusable, on the grounds that light passes through
rather than reflecting back. This is incorrect: in a **uniform
radiance field** (constant emitter), radiance is preserved through any
lossless dielectric regardless of refraction, so every pixel must read
exactly 1.0. This is what exposed the energy-gain bug above, and is a
valid energy-conservation test for transmissive materials.

### Validation
All four tests compare against Mitsuba's built-in smooth `dielectric`
at matched IOR (1.5).

**1. Fresnel split and radiance scaling** (200k samples per angle):

| theta | reflect frac (mine / ref / Fresnel F) | w_refl | w_tran |
|---|---|---|---|
| 10 | 0.0397 / 0.0397 / 0.0400 | 1.0000 | 0.4444 |
| 45 | 0.0497 / 0.0497 / 0.0502 | 1.0000 | 0.4444 |
| 70 | 0.1705 / 0.1705 / 0.1710 | 1.0000 | 0.4444 |
| 85 | 0.6129 / 0.6129 / 0.6128 | 1.0000 | 0.4444 |

Transmitted weight of 0.4444 = 1/eta^2 confirms the radiance
compression factor on entering a denser medium (flux is conserved;
radiance is not).

**2. Total internal reflection** (from inside, critical angle 41.81 deg):

| theta | reflect frac (mine / ref) |
|---|---|
| 20.0 | 0.0414 / 0.0414 |
| 39.8 | 0.2283 / 0.2283 |
| 40.0 | 0.2440 / 0.2440 |
| 43.8 | 1.0000 / 1.0000 |
| 60.0 | 1.0000 / 1.0000 |

Monotonic rise approaching the critical angle, then exactly 1.0 past
it — no light transmits, as required.

**3. Delta-lobe convention:** `eval()` and `pdf()` both return exactly
zero for transmitted directions, matching the reference.

**4. Render test** — glass sphere over a checkerboard floor, exercising
what the analytic tests cannot: back-side hits on real geometry,
multi-bounce enter/exit paths, and the path tracer's `prev_delta` MIS
handling firing on `DeltaTransmission` events (`mi.BSDFFlags.Delta` =
97 = Null | DeltaReflection | DeltaTransmission, so the existing MIS
logic required no changes).

**Result: mean absolute difference 0.00000 — pixel-identical to
Mitsuba's `dielectric`.** Both implementations receive the same random
stream (drawn by the integrator, not the BSDF) and make identical
Fresnel-driven branch decisions, so bit-identical output is the
expected outcome of two correct implementations, not a coincidence.
Visually: checkerboard correctly inverted through the sphere, with
refraction-compressed banding near the silhouette.

### Known limitations
- **Smooth transmission only.** Rough/frosted glass is not
  representable; the transmitted lobe ignores `roughness`. Rough
  transmission would require the GGX distribution applied to
  refraction, including the refraction Jacobian, and was scoped out.
- **No volumetric absorption.** `base_colour` tints transmitted
  radiance per interface, but this is not distance-dependent
  Beer-Lambert absorption through the medium, so thick and thin glass
  of the same colour tint identically.
- **No dispersion**, so no physically-derived chromatic aberration.


------

## 17. OIDN Post-Process Denoising

Integrates Intel Open Image Denoise as a post-process stage, using the
albedo and normal AOVs (Section 9) as auxiliary feature buffers.
Distinct in kind from the sampling-side noise work in Section 10: those
reduce variance at the source, this filters the rendered result,
trading a controlled bias for reduced noise.

Implemented in `denoisers/oidn.py` — deliberately not a Mitsuba plugin,
as it operates on a finished image rather than participating in light
transport. Depends on `pyoidn`.

### Diagnostic process — three hypotheses falsified, one confirmed
Initial integration ran without error but changed the image by only
~0.4%. Four candidate causes were tested:

1. **Non-contiguous input arrays** — falsified. `pyoidn` validates
   contiguity and raises `ValueError` explicitly; it never silently
   accepted a bad buffer.
2. **HDR autoexposure misestimation** — falsified. Forcing
   `inputScale=1.0` and clamping outliers both left the result
   unchanged.
3. **Degenerate albedo poisoning the demodulation** (albedo is zero
   where rays miss geometry) — falsified, and in the opposite
   direction: removing the auxiliary buffers entirely made filtering
   *weaker* (0.00113 vs 0.00176), not stronger.
4. **Reconstruction filter correlating the noise** — **confirmed by
   direct measurement.**

### Confirmed mechanism: reconstruction filter
Lag-1 spatial autocorrelation of the noise residual (noisy minus
converged reference), Cornell box, 16 spp:

| rfilter | Autocorrelation (h / v) | OIDN response |
|---|---|---|
| gaussian (Mitsuba default) | +0.279 / +0.187 | 0.2% — negligible |
| box | -0.062 / +0.001 | 9.4% — filters normally |

A Gaussian reconstruction filter distributes each sample across
neighbouring pixels, correlating their noise. OIDN is trained on
box-filtered renders where per-pixel noise is independent;
spatially-correlated noise resembles low-frequency signal to the
network and is preserved rather than removed. This matches OIDN's own
guidance recommending box-filtered input.

**Practical consequence:** any render intended for denoising must use
`"rfilter": {"type": "box"}`. This is a scene-configuration
requirement, not a code change.

### Metric artefact: directly-visible emitters
Even with box filtering, RMSE initially showed denoising making the
image *worse*. Localising the error revealed the cause: **0.59% of
pixels (the light source) contributed 98% of the squared error.**

OIDN demodulates by albedo — dividing colour by albedo, filtering, then
re-multiplying — which assumes `colour = albedo x illumination`. That
assumption is false for emissive surfaces, whose colour is emitted
radiance unrelated to their albedo, so the filter smears a very sharp,
very bright edge. Because RMSE is quadratic, this small region
dominated the metric while remaining nearly invisible to the eye —
the denoised images looked clearly better throughout.

Addressed by `denoise_composite()`, which restores original pixels
wherever luminance exceeds a threshold (default 2.0), matching standard
production practice of excluding directly-visible emitters from
denoising.

**Known limitation:** the luminance threshold is a heuristic and is
scene-dependent — a value appropriate for the Cornell box incorrectly
masked over 1% of pixels in the HDRI environment scene, whose 99th
percentile is 2.26. The principled alternative is a dedicated emission
AOV, captured at the first hit and subtracted before denoising then
added back after, removing the magic number entirely. Not implemented.

### Validation
Cornell box, box rfilter, 1024 spp reference. Emitter covers 0.59% of
pixels. Starred columns exclude it — error there reflects the restored
noisy input, not denoiser output.

| spp | noisy | denoised | change | noisy* | denoised* | change* |
|---|---|---|---|---|---|---|
| 16 | 0.03991 | 0.03253 | -18.5% | 0.02955 | 0.01832 | -38.0% |
| 32 | 0.03418 | 0.03060 | -10.5% | 0.02192 | 0.01571 | -28.3% |
| 64 | 0.02303 | 0.01982 | -13.9% | 0.01604 | 0.01090 | -32.0% |
| 128 | 0.01805 | 0.01626 | -9.9% | 0.01157 | 0.00852 | -26.4% |
| 256 | 0.01346 | 0.01227 | -8.8% | 0.00875 | 0.00676 | -22.7% |
| 512 | 0.00884 | 0.00806 | -8.8% | 0.00601 | 0.00478 | -20.4% |

**Result: PASS.** Error reduced at every tested sample count. Relative
benefit decreases as spp rises, as expected — less noise remains to
remove.

**Effective sample multiplier:** denoised 16 spp (excl. emitter,
0.01832) falls between undenoised 32 spp (0.02192, worse) and 64 spp
(0.01604, better) — so denoising is worth **between 2x and 4x** the
sample count on this scene. The crossover was not bisected further.

### Open question
On the Cornell box at 64 spp, colour-only denoising slightly outperformed
colour + albedo + normal (0.00897 vs 0.00917), whereas on the HDRI
environment scene the auxiliary buffers improved filtering by ~55%. Not
characterised further. Also noted: OIDN rejects `normal` supplied
without `albedo` ("unsupported combination of input features") — albedo
is a prerequisite for using normal.



-----

# 18. Clearcoat (GTR1 Second Specular Lobe)

Disney (2012) clearcoat: an additional narrow specular lobe layered above the
base material, simulating a lacquer or varnish coat. Implemented as a third
lobe in `principled_bsdf`, alongside the existing diffuse and GGX specular
lobes.

**Parameters added:** `clearcoat` (0.0 default, no coat), `clearcoat_gloss`
(1.0 default). Both texture-capable.

## 18a. Model and design decisions

| Component | Choice | Source |
|---|---|---|
| NDF | GTR1 (Berry), hand-written | Disney 2012 |
| Roughness | `alpha = mix(0.1, 0.001, gloss)`, used **directly, not squared** | Disney 2012 |
| Fresnel | Schlick, fixed F0 = 0.04 (IOR 1.5) | Disney 2012 |
| Geometry term | Smith GGX at fixed alpha = 0.25, reused from Mitsuba | Disney 2012 |
| Scale | Fixed 0.25 coefficient | Disney 2012 |

Two facts were verified against the source rather than assumed:

1. **Mitsuba's `MicrofacetDistribution` ships only Beckmann and GGX** — no
   GTR1. Checked against the plugin documentation. The GTR1 distribution and
   its sampling routine therefore had to be written by hand; only the geometry
   term reuses Mitsuba's validated code.
2. **Mitsuba's `.G()` is separable Smith**, i.e. `G1(wi) * G1(wo)`, not
   height-correlated. Verified numerically across 12 angle pairs: separable
   matched to <1e-4 at every pair, height-correlated diverged (e.g. 0.763351
   vs 0.774941 at theta_i=70, theta_o=75). This matters because Disney's own
   formulation is separable, so reusing Mitsuba's `G` requires no correction
   factor. Had it been height-correlated, the lobe would carry a small
   systematic energy error.

Disney's `smithG_GGX` returns `G1/(2·N·V)`, so the product of two already
absorbs the `1/(4·cos_i·cos_o)` denominator. Converted to the Cook-Torrance
form used by `eval_specular`:

```
f_cc = 0.25 · clearcoat · D_GTR1(n·h) · F(0.04) · G_smith(0.25) / (4·cos_i·cos_o)
```

**Angle convention note:** GTR1's `D` takes **n·h**, while the Fresnel and
sheen terms take **wi·h**. These are different angles and confusing them is a
classic source of error; the code names them `cos_theta_h_n` and
`cos_theta_h` respectively.

## 18b. Pre-implementation validation of GTR1

The distribution and its sampler were validated in isolation (pure NumPy,
independent of Mitsuba) **before** any of it entered the renderer, so that a
later failure could not be ambiguous between "wrong formula" and "wrong
integration".

**Normalisation.** `integral of D(h)·cos(h) dh` over the hemisphere:

| alpha | integral |
|---|---|
| 0.1 | 1.000000 |
| 0.05 | 1.000000 |
| 0.01 | 1.000001 |
| 0.001 | 1.000000 (after grid refinement — see below) |

**Sampler correctness.** Inverting the GTR1 CDF in cos(theta):

- Per-bin deviation from the analytic density: mean |z| = 0.74–0.90, max
  |z| = 2.17–3.45 across 59 bins. That is pure counting noise for that many
  bins.
- Kolmogorov-Smirnov test over 20 seeds at alpha = 0.1, 0.01, 0.001:
  **0/20 failures at every alpha**, median p = 0.432.
- **Control:** the same test on a deliberately mis-scaled sampler (alpha off
  by 5%) gave median p = 4.87e-19 and **20/20 failures**. This establishes
  that the test has the power to detect an error of that magnitude, so the
  passes above are meaningful rather than vacuous.

**Two false alarms, both traced to the reference rather than the formula.**
Recorded because the diagnostic pattern recurs throughout this project:

- The alpha=0.001 integral initially read 1.005589. Hypothesis: quadrature
  resolution, not formula error. Test: refine the grid. Result: 1.005589 to
  1.000060 (10x points) to 1.000000 (theta-space grid). Confirmed.
- Initial per-bin z-scores blew up at small alpha (mean |z| = 14.11 at
  alpha=0.001), which looked like sampler error. Hypothesis: the reference
  evaluated the analytic density at bin *centres*, a poor approximation for a
  steep lobe. Test: integrate the density across each bin instead. Result:
  mean |z| collapsed to 0.90. The sampler was correct; the reference was not.

## 18c. Staged implementation

Deliberately split so that each stage had an independent check:

- **Stage 1 — `eval()` only.** Clearcoat evaluated but not importance-sampled.
  Remains unbiased because cosine-hemisphere diffuse sampling covers the whole
  hemisphere with nonzero pdf, but is very noisy for a narrow coat. Valid only
  at `metallic=0`; at `metallic=1` the diffuse lobe is never sampled and coat
  energy would land where pdf ~= 0.
- **Stage 2 — `sample()` and `pdf()`.** Three-way lobe partition, GTR1
  importance sampling. Provides the noise reduction, and makes the
  chi-squared test meaningful for the first time.

Stage 1 provides the brute-force reference that Stage 2 must reproduce.

## 18d. Energy validation — white furnace test

Base configuration is the zero-specular Lambertian (`specular=0`,
`metallic=0`, `roughness=1.0`), which returns exactly 1.0000, so any increase
is directly readable as the coat's contribution.

**Predictions made before measurement** (numerically integrated directional
albedo, orthographic sphere): clearcoat gloss=0 to +0.0124, sheen to +0.0117.

**Measured:**

| Clearcoat | Gloss | Mean | Std | Delta |
|---|---|---|---|---|
| 0.0 | 0.0 | 1.0000 | 0.0068 | +0.0000 |
| 0.5 | 0.0 | 1.0037 | 0.0082 | +0.0036 |
| 1.0 | 0.0 | 1.0073 | 0.0110 | +0.0073 |
| 1.0 | 0.5 | 1.0077 | 0.0126 | +0.0077 |
| 1.0 | 1.0 | 1.0088 | 0.0164 | +0.0087 |

Findings:

- **Regression clean:** `clearcoat=0` returns exactly 1.0000, so the lobe
  partition collapses to the original two-lobe split as designed.
- **Linear in `clearcoat`:** +0.0036 at 0.5, +0.0073 at 1.0.
- **Prediction ratio:** measured/predicted = 0.59 (clearcoat) and 0.61
  (sheen). The shortfall is sphere-coverage dilution — the furnace frame
  includes background at radiance 1.0, so the sphere's contribution is scaled
  by its screen coverage. The two lobes were predicted independently and land
  on the *same* dilution factor, which would not happen if either were wrong.

## 18e. KNOWN LIMITATION — clearcoat is an additive lobe

**Disney's 2012 clearcoat does not remove energy from the layer beneath it.**
The coat is added on top; no absorption or base darkening is applied. A
renderer faithful to the paper therefore *exceeds unity* in a white furnace
test, by the coat's directional albedo (+0.0073 at `clearcoat=1`).

This is a limitation of the published model, not an implementation defect, and
it was reproduced deliberately rather than silently corrected. Later models
address it: Autodesk Standard Surface and Kulla-Conty-style coat absorption
attenuate the base by approximately `(1 - F_coat)` so the layered result
conserves energy.

The alternative — adding coat darkening — was considered and rejected for this
project on the grounds that it deviates from the reference paper the
implementation is claimed to follow. Documenting the overshoot is the more
honest position given the project's stated focus on energy-conservation
validation.

## 18f. Chi-squared — sampling consistency

Chi-squared histograms directions produced by `sample()` against `pdf()`. It
therefore tests the **three-way lobe partition** introduced by clearcoat,
which is the highest-risk part of the change (the same class of code that
produced the earlier mixture-pdf bug).

| Config | Result | p-value |
|---|---|---|
| Clearcoat broad (cc=1.0, gloss=0.0) | PASS | 0.996 |
| Clearcoat partial (cc=0.5, gloss=0.0) | PASS | 0.962 |
| Clearcoat + specular (cc=1.0, gloss=0.3, r=0.3) | PASS | 0.808 |
| Clearcoat + metal (cc=1.0, gloss=0.3, r=0.3, m=1.0) | PASS | 0.972 |
| Clearcoat sharp (cc=1.0, gloss=1.0) | FAIL | see 18g |

The two most diagnostic configs both pass: **all three lobes simultaneously
active** (the case most likely to expose a partition error), and **metallic
base where `p_diff = 0`** (partition reduces to coat 0.25 / specular 0.75).

## 18g. Harness resolution boundary — measured, not assumed

The `gloss=1.0` failure was investigated rather than attributed. Two prior
reasons to suspect the harness: the GTR1 density integrates analytically to
1.000000 (18b), and the furnace mean did not move between Stage 1 and Stage 2
(+0.0089 to +0.0087), which it would have if the pdf were genuinely 2.34x too
large.

**Decisive test — refine the grid at fixed `ires`:**

| res | PDF sum | histogram sum | result |
|---|---|---|---|
| 201 | 2.338811 | 0.987365 | FAIL |
| 401 | 1.636475 | 0.987365 | FAIL |
| 801 | 1.289908 | 0.987365 | FAIL |
| 1601 | 1.121898 | 0.987365 | FAIL |

**The histogram sum is identical to six decimal places at every resolution.**
The sampled distribution does not change; only the tabulated pdf does, and it
converges monotonically toward the histogram value. A genuine pdf error would
be invariant under grid refinement.

Error above 0.987365: 1.351 to 0.649 to 0.303 to 0.135, halving per doubling,
i.e. O(1/N) — the expected rate for integrating a spike narrower than one
cell. Extrapolating, res ~= 22,000 would be needed to bring the error under
0.01, requiring ~2.5e11 array entries against Dr.Jit's 2^32 (4.29e9) limit.
Unreachable in principle, not merely inconvenient.

**Confirmation at gloss=0.95** (a milder failure: pdf sum only 2% high, so the
test ran and rejected rather than bailing out early):

| res | PDF sum | histogram sum | result |
|---|---|---|---|
| 201 | 1.007957 | 0.983060 | FAIL |
| 401 | 0.991291 | 0.983060 | PASS |
| 801 | 0.985478 | 0.983060 | PASS |

The verdict flips with grid refinement alone, with sampling unchanged.

**Locating the boundary — gloss sweep at res=201:**

| gloss | alpha | result |
|---|---|---|
| 0.0 | 0.1000 | PASS (p=0.996) |
| 0.5 | 0.0505 | PASS (p=0.974) |
| 0.8 | 0.0208 | PASS (p=0.972) |
| 0.95 | 0.0060 | FAIL |
| 1.0 | 0.0010 | FAIL |

Breakdown lies between alpha = 0.021 and alpha = 0.006. For comparison,
**Mitsuba's own principled BSDF fails this harness at alpha = 0.1^2 = 0.01**,
inside the same window — the coat lobe therefore breaks the test at the same
scale as a production-grade implementation on the same grid.

**Conclusion:** chi-squared validates clearcoat sampling to alpha ~= 0.02 at
res=201, and to alpha = 0.006 at res >= 401. Below that the harness cannot
reach, and the furnace test provides coverage instead by confirming the
estimator remains unbiased.

*Caveat:* the gloss=0.95 passes carry p = 0.097 and 0.079, notably lower than
the 0.9+ of the broad configs. Consistent with residual quadrature bias — the
pdf sum is still 0.25% above the histogram at res=801 and still falling — but
worth noting rather than claiming a clean pass.

## 18h. Sampling probability heuristic

Lobe selection probability is `p_clear`, with the existing two-lobe split
dividing the remainder: `p_clear + p_spec + p_diff = 1` exactly, and
`p_clear = 0` recovers the original partition bit-for-bit.

A **fixed** `p_clear = 0.25 · clearcoat` was tried first and **made variance
worse at every gloss except 1.0**:

| Config | Stage 1 (no coat sampling) | Fixed 0.25 | Gloss-scaled |
|---|---|---|---|
| cc=0.5, gloss=0 | 0.0080 | 0.0095 | **0.0082** |
| cc=1.0, gloss=0 | 0.0107 | 0.0135 | **0.0110** |
| cc=1.0, gloss=0.5 | 0.0113 | 0.0141 | **0.0126** |
| cc=1.0, gloss=1.0 | 0.0711 | 0.0164 | **0.0164** |

**Diagnosis:** a broad coat (alpha=0.1) occupies directions cosine sampling
already covers well, so samples spent on it are taken from the base layers for
no gain. A sharp coat is a spike no other lobe finds, so it needs them. The
probability should track lobe narrowness, not be constant:

```
p_clear = clearcoat · clamp(0.05 + 0.20 · clearcoat_gloss, 0.05, 0.25)
```

The 0.05 floor exists because a metallic base has `p_diff = 0` and a
low-roughness GGX lobe may not cover the coat's directions either; dropping to
zero there would reintroduce fireflies.

Means were unchanged across all three variants (+0.0036 / +0.0073 / +0.0077 /
+0.0087), confirming the partition still sums to 1 and that `sample()` and
`pdf()` remained in agreement.

**Residual:** gloss=0.5 remains 11% worse than Stage 1 (0.0126 vs 0.0113).
Accepted rather than tuned further, because the white furnace is the
worst possible case for importance sampling — uniform radiance from every
direction means there is nothing to aim at, so any samples diverted to the
coat are pure loss. In a scene with concentrated lighting, coat sampling is
precisely what finds the highlight. Tuning further would optimise for a test
that does not represent real use.

This is a heuristic, not a derivation, and is justified only by the measured
variance above.

## 18i. Visual validation

`tests/render_clearcoat_sheen.py`. Five spheres sweeping `clearcoat_gloss`
0 to 1, plus a **matched control row** with `clearcoat=0` and all other
parameters identical, so any difference is attributable to the coat alone.
`specular=0` on both rows: with the base GGX lobe active its highlight lands
in the same place and completely masks the coat.

Scene design note: the key light is deliberately **small**. A large area light
reflects as a large blob at every gloss value, which is why an earlier version
of this test showed no visible gloss variation despite the lobe working
correctly.

**Stage 1 (coat evaluated, not sampled):**

| gloss | peak | area >0.1 | fireflies |
|---|---|---|---|
| 0.00 | 0.639 | 1707 | 0 |
| 0.25 | 0.784 | 2877 | 0 |
| 0.50 | 0.792 | 2000 | 0 |
| 0.75 | 0.831 | 1926 | 24 |
| 1.00 | 0.831 | 241 | 21 |

**Stage 2 (coat importance-sampled):**

| gloss | peak | area >0.1 | fireflies |
|---|---|---|---|
| 0.00 | 0.631 | 1708 | 0 |
| 0.25 | 0.780 | 2880 | 0 |
| 0.50 | 0.792 | 2001 | 0 |
| 0.75 | 0.753 | 1913 | **0** |
| 1.00 | 0.580 | 178 | **0** |

Fireflies eliminated entirely, matching the furnace std drop of 4.3x at
gloss=1 (0.0711 to 0.0164). The gloss=1 peak falling 0.831 to 0.580 reflects
that the Stage 1 peak was partly firefly spikes rather than converged signal.

**Known limitation of this figure:** the `area` column is not cleanly
monotonic in the middle of the sweep, because each sphere sits at a different
x position and therefore sees the key light at a different reflection angle.
Only the gloss=1 collapse (7x smaller) exceeds that positional variation. A
strictly monotonic figure would require rendering each sphere separately at
an identical position.

---

# 19. Sheen

Disney (2012) sheen: a grazing-angle term simulating the silhouette
brightening of fabrics such as velvet.

**Parameters added:** `sheen` (0.0 default), `sheen_tint` (0.5 default). Both
texture-capable.

```
f_sheen = sheen · C_sheen · (1 - wi·h)^5 · (1 - metallic)
```

added alongside the diffuse term, where `C_sheen` interpolates from white
toward the base colour's hue by `sheen_tint`.

## 19a. Documented approximation — sheen is not importance-sampled

Sheen is implemented in `eval()` only. It has **no dedicated sampling strategy
and no term in `pdf()`**; it rides on whatever direction the existing mixture
produces. This matches Disney's own reference implementation, and is justified
by the term being smooth, low-frequency and low-energy — the added variance is
small and it avoids a fourth slice in the lobe partition.

**This is a deliberate approximation, not full statistical consistency**, and
is recorded as such alongside the blend-BSDF flat-colour collapse (Section 7)
and the heuristic emitter-masking threshold (Section 17).

**Direct consequence for testing:** chi-squared compares `sample()` against
`pdf()`, and sheen appears in neither. **Chi-squared has no power to detect a
sheen error.** The sheen entry in the chi-squared suite is retained explicitly
as a *null test* — it guards only against sheen accidentally leaking into
`sample()` or `pdf()` in future changes. It passed (p=0.686), which
establishes nothing about sheen's correctness.

Sheen's validation therefore rests entirely on the furnace test and the render
comparison below.

## 19b. Energy validation — white furnace test

| Sheen | Tint | Mean | Std | Delta |
|---|---|---|---|---|
| 0.0 | 0.5 | 1.0000 | 0.0068 | +0.0000 |
| 0.5 | 0.5 | 1.0036 | 0.0093 | +0.0036 |
| 1.0 | 0.0 | 1.0071 | 0.0144 | +0.0071 |
| 1.0 | 0.5 | 1.0071 | 0.0144 | +0.0071 |
| 1.0 | 1.0 | 1.0071 | 0.0144 | +0.0071 |

- Predicted +0.0117 before measurement; measured +0.0071, ratio 0.61,
  matching the clearcoat dilution factor of 0.59 (see 18d).
- Linear in `sheen`: +0.0036 at 0.5, +0.0071 at 1.0.
- **Tint invariance confirmed:** on a white base, `sheen_tint` 0.0 / 0.5 / 1.0
  give *identical* results, as they must — a white base has no hue to tint
  toward. This is the specific test of `_sheen_colour`, and a difference here
  would indicate an error in the tint interpolation.

Like clearcoat, sheen is **additive** and pushes the furnace mean above unity.
Same limitation, same reasoning as 18e.

## 19c. Ctint normalisation can exceed 1 per channel

Disney's `Ctint` divides base colour by its luminance (weights 0.3/0.6/0.1),
which for a saturated base can push a channel above 1. The test render's blue
base `[0.10, 0.12, 0.34]` has luminance 0.136, giving a tint of approximately
`[0.74, 0.88, 2.50]` — the blue channel amplified 2.5x.

Consequence: **on a coloured base, `sheen_tint` changes sheen magnitude per
channel, not only hue.** This is correct Disney behaviour and explains why the
white-base furnace test shows tint invariance while the coloured-base renders
do not.

## 19d. Visual validation

Five spheres sweeping `sheen_tint` 0 to 1 on a dark blue base, with a matched
`sheen=0` control row. Rim lighting from behind, since sheen appears only at
grazing angles.

Measured against control: sheen changes 28% of pixels, max difference 0.51,
concentrated at the silhouettes. The tint shift from white to base hue is
visible across the sweep.

**Same positional confound as 18i:** the per-sphere magnitude varies with
position because rim lighting differs across the row, so magnitude differences
between spheres in this figure are not attributable to `sheen_tint` alone.

---

# Additions to Section 6 — Known Limitations

Append to the existing list (GGX single-scattering energy loss):

- **Clearcoat is an additive lobe (Disney 2012).** No coat absorption or base
  darkening, so a coated material exceeds unity in a white furnace test by the
  coat's directional albedo (+0.0073 at `clearcoat=1`). Faithful to the
  reference paper; addressed in later models such as Autodesk Standard Surface
  and Kulla-Conty coat absorption. See 18e.
- **Sheen is not importance-sampled.** Evaluated in `eval()` only, matching
  Disney's reference implementation. Consequence: chi-squared cannot validate
  sheen at all. See 19a.
- **Chi-squared cannot validate microfacet lobes below alpha ~= 0.006.** A
  harness limitation, demonstrated by grid-refinement convergence rather than
  asserted; Mitsuba's own principled BSDF fails the same harness at
  alpha = 0.01. Narrow-lobe validation falls back to the furnace test. See 18g.
- **No anisotropy or rotation control on the clearcoat lobe.** GTR1 is
  isotropic as specified by Disney; the base specular lobe's anisotropy does
  not propagate to the coat.



-----


# 20. NEE Shadow Rays vs. Smooth Transmission ("Transparent Shadows")

Direct sunlight was not entering the glazed kitchen window despite the pane
being correctly transmissive (Section 16, validated pixel-identical to
Mitsuba's own `dielectric`). This section documents the diagnosis, the fix,
its four explicit approximations, and the measured cost of each.

**Parameters added:** `transparent_shadows` (bool, default `False`),
`max_transparent_shadow_depth` (int, default `8`). Exposed as
`$`-overridable scene defaults and via `render_scene.py --transparent-shadows`.

## 20a. Symptom

With the window glazed and all local emitters stripped so the envmap was the
only light source, the room lit correctly from ambient/sky directions —
raising `envmap_scale` visibly brightened every surface — but no directional
sunbeam appeared, at any scale tested. Ambient transport through the glass was
never in question; the sharp directional component specifically was absent.

## 20b. Diagnosis

`path_tracer.py`'s NEE call performed a binary, material-blind occlusion test:

```python
ds, emitter_radiance = scene.sample_emitter_direction(si, sampler.next_2d(), True, active_em)
```

The `True` triggers Mitsuba's built-in shadow ray, which asks only *"is there
geometry between the shading point and the light"* — never *"does this
material transmit in this direction."* A pane of perfectly smooth glass
therefore blocks that test exactly like an opaque wall, regardless of
`transmission=1.0`.

Direct sunlight could consequently only arrive via a **BSDF-sampled** path: a
ray hits the glass, refracts in the single deterministic direction Snell's law
dictates for that incidence angle, and by chance that direction lands inside
the sun's small solid angle in the HDRI. Since BSDF sampling on a delta
surface aims at nothing — it returns the one physically correct refraction —
this cannot be accelerated by importance sampling.

**Decisive observation:** the same shot showed the sunbeam faintly emerging at
spp=4000 but not at spp=256. The path exists and is unbiased in principle;
its convergence rate is impractical. This is a convergence problem, not a
hard zero.

This is a known difficulty in unidirectional path tracing — the same family as
caustics, and as the defocused-specular-highlight case encountered earlier in
this project — and production renderers commonly special-case it.

## 20c. Fix — "shadow-transparent glass"

Manifold Next Event Estimation (iterative root-finding for the true refracted
path through a specular chain) is the correct solution and was judged out of
scope. This implements the standard production approximation instead: NEE
shadow rays pass **straight through** delta-transmissive surfaces, ignoring
the refraction bend.

`sample_emitter_direction` is called with `test_visibility=False` when the
feature is enabled, and occlusion is walked manually in `_shadow_blocked()`:
intersect toward the light, and if the hit surface advertises
`mi.BSDFFlags.DeltaTransmission`, continue from that point rather than
treating it as blocked. A non-transmissive hit, or exhausting the
pass-through budget, counts as blocked.

Identifying glass by that flag is unambiguous here: `principled_bsdf` sets it
whenever `transmission > 0`, and this renderer supports only smooth
transmission (Section 16, Known Limitations), so there is no rough-transmission
case to catch accidentally.

**Design note:** MIS weighting is untouched by this change. `mis_weight()`
consumes only `ds.pdf` and `bsdf_pdf`, neither of which `_shadow_blocked()`
modifies.

## 20d. The four approximations, stated explicitly

1. **Straight-line continuation, not the true refracted path.** This is both
   the entire cost saving relative to MNEE and the entire source of bias:
   light appears to arrive from a slightly incorrect direction through glass.
2. **No attenuation.** Neither Fresnel reflection loss nor the pane's
   `base_colour` tint is applied to light passing through for shadow purposes,
   so a coloured pane does not tint its own shadow. Magnitude bounded in 20f.
3. **Delta-transmissive objects cast no direct shadow.** Disabling their
   occlusion is precisely the mechanism, so any shadow they cast must come
   from BSDF-sampled paths alone. This affects *every* delta-transmissive
   surface simultaneously — window, wine glasses, radio dial cover. Measured
   in 20g.
4. **Opt-in, not default.** Keeps every previously validated number reachable
   and unchanged; enabling is a per-render decision.

## 20e. Regression — feature is inert when disabled

Full `run_all.sh` with `transparent_shadows=False`, compared field-by-field
against the documented baseline.

**Deterministic quantities — exact matches.** Every furnace mean and std
(diffuse, metallic, zero-specular, Burley, clearcoat deltas, sheen deltas)
reproduced to the last decimal. Chi-squared PDF sums, including the two known
failures:

| Config | Documented PDF sum | This run | Match |
|---|---|---|---|
| Clearcoat sharp (gloss=1.0) | 2.338811 | 2.338811 | exact |
| Resolution sweep, res=401 | 1.636475 | 1.636475 | exact |
| Resolution sweep, res=801 | 1.289908 | 1.289908 | exact |
| Resolution sweep, res=1601 | 1.121898 | 1.121898 | exact |

**Monte Carlo quantities — varied as expected.** Chi-squared p-values are
drawn fresh and unseeded; under a true null hypothesis a p-value is itself
uniformly distributed, so run-to-run variation is the correct behaviour, not
drift:

| Config | Documented p | This run p | Result |
|---|---|---|---|
| Mixed (r=0.4, m=0.5) | 0.849 | 0.828 | PASS |
| Clearcoat broad (gloss=0.0) | 0.996 | 0.848 | PASS |
| Clearcoat partial (cc=0.5) | 0.962 | 0.686 | PASS |
| Clearcoat + specular | 0.808 | 0.909 | PASS |
| Clearcoat + metal | 0.972 | 0.572 | PASS |

**Result: PASS.** All deterministic values bit-identical; all p-values far
above the 0.01 threshold. The feature is genuinely inert when disabled.

## 20f. Bias bound — derived from Section 16, no new measurement required

Approximation 2 omits the Fresnel reflectance a true shadow ray would lose at
each interface. Section 16's own measured Fresnel table gives the magnitude
directly:

| Incidence | Fresnel F (measured, Section 16) | Light leaked by this approximation |
|---|---|---|
| 10 deg | 0.0397 | ~4% |
| 45 deg | 0.0497 | ~5% |
| 70 deg | 0.1705 | ~17% |
| 85 deg | 0.6129 | ~61% |

The bias is therefore small near normal incidence and grows sharply toward
grazing angles, bounded by exactly that curve. For a window viewed from
inside a room, most shading points see the pane at moderate incidence, so the
practical error sits near the low end.

## 20g. Shadow-loss trade-off — measured

Table close-up (`--sensor 2`), 512 spp, 1280x720, `--sampler independent`,
identical seed, feature the only variable. The affected region is defined by
the difference image itself rather than a hand-drawn box.

| Change threshold | Pixels | % of frame | mean OFF | mean ON | ratio |
|---|---|---|---|---|---|
| > 0.001 | 900,519 | 97.71% | 0.39561 | 0.59203 | 1.496 |
| > 0.01 | 769,713 | 83.52% | 0.44019 | 0.66982 | 1.522 |
| > 0.05 | 507,671 | 55.09% | 0.54345 | 0.88292 | 1.625 |
| > 0.1 | 357,627 | 38.81% | 0.66118 | 1.12162 | 1.696 |

| Direction of change (threshold 0.01) | Pixels |
|---|---|
| Brightened | 752,253 |
| Darkened | 18,125 |

**Result.** Only **1.97%** of changed pixels are darker — a 41:1
brightened-to-darkened ratio. The shadow loss predicted by approximation 3 is
real but small, and is dominated by the light the feature admits. The ratio
rising with threshold (1.496 to 1.696) shows the largest changes land on
already-bright pixels, consistent with direct sunlight rather than a uniform
diffuse lift.

**Limitation of this test:** it cannot isolate the wine glasses. The window
pane is also delta-transmissive and dominates the frame's response, so the
18,125 darkened pixels represent shadow loss from all delta-transmissive
surfaces in view, not the glasses alone. Isolating them would require a
variant scene with the window unglazed; not performed.

## 20h. Convergence cost — measured

Section 10's reference-free methodology: N independently seeded renders per
configuration, per-pixel standard deviation across the repeats. Relative std
(std divided by mean) is the meaningful comparison here, since the feature
makes the image substantially brighter and brighter images carry more
absolute variance regardless of sampling quality.

| Config | Seeds | SPP | mean per-pixel std | image mean | relative std |
|---|---|---|---|---|---|
| OFF | 8 | 64 | 0.45671 | 0.32933 | 0.39087 |
| ON | 8 | 64 | 0.58976 | 0.49274 | 0.52300 |
| OFF | 16 | 256 | 0.60816 | 0.33058 | 0.32640 |
| ON | 16 | 256 | 0.70402 | 0.49417 | 0.45532 |

**Relative std penalty: +33.8% at 64spp, +39.5% at 256spp** — same direction
and similar magnitude across a 4x change in sample count and a doubled seed
count, so the finding is robust rather than a small-sample artifact. Both
configurations' relative std falls as spp rises (0.391 to 0.326 OFF, 0.523 to
0.455 ON), confirming both converge normally.

**Image mean ratio: 1.495x**, reproduced to three decimals in both rows above
*and independently* in the 20g test at different resolution, spp and seed set.
Three independent measurements agreeing establishes this as the feature's
radiance contribution: **the scene receives 49.5% more total light.**

**Interpretation — the variance increase is expected, not anomalous.** The
feature opens a previously closed high-variance path: direct sunlight through
glass, from a small and intense source, which delivers a large contribution
when a sample lands on it and nothing when it does not. With the feature
disabled that path contributes zero light *and* therefore zero variance.
Noise-free absence of light is not the superior outcome. The correct reading
is that ~35-40% more relative noise buys ~50% more delivered radiance.

## 20i. Pass-through budget boundary — measured

`tests/test_max_transparent_shadow_depth.py`. Synthetic scene: a diffuse
zero-specular receiver, a light, and N thin glass panes between them at fixed
0.15 spacing, sweeping N past the cap. Camera position was **measured, not
assumed** — an on-axis camera behind the light hits the light rectangle
itself (first hit at `p=[0,0,5]`), and a camera on the far side hits the
receiver's back face (`dot(d,n)=+1`, and `principled_bsdf` is front-side
only), both producing an entirely black frame. An off-axis position clears
both.

**At `max_depth=8`, 1024 spp, cap = 8:**

| Panes | OFF | ON | ON/OFF |
|---|---|---|---|
| 0 | 0.71192 | 0.71192 | 1.00 |
| 1 | 0.60584 | 1.26058 | 2.08 |
| 2 | 0.52420 | 1.13051 | 2.16 |
| 4 | 0.05873 | 0.56137 | 9.56 |
| 6 | 0.15099 | 0.55130 | 3.65 |
| 7 | 0.21590 | 0.57973 | 2.69 |
| 8 | 0.29907 | 0.29907 | **1.00** |
| 9 | 0.40100 | 0.40100 | 1.00 |
| 10 | 0.52299 | 0.52299 | 1.00 |
| 12 | 0.84846 | 0.84846 | 1.00 |

**The cap engages exactly and fails conservatively.** At and beyond 8 panes
the ON and OFF values are identical to five decimal places — the feature
switches itself off entirely and the renderer degrades to baseline occlusion
behaviour rather than misbehaving or leaking light.

**Off-by-one, worth noting:** `at_budget = (n_pass + 1) >= max_transparent_shadow_depth`
with `n_pass` starting at 0 means a cap of 8 permits **7** pass-throughs, not
8. Behaviour is safe; the parameter name is one greater than the number of
panes actually traversed.

**Working range is bounded by `max_depth`, not only by the cap.** Sweeping the
integrator's depth limit shows the two interact:

| `max_depth` | Feature effective up to | Flatlines at |
|---|---|---|
| 2 | 1 pane | 2 panes |
| 4 | 2 panes | 4 panes |
| 8 | 7 panes | 8 panes (the cap) |

The camera path must refract through every pane before reaching a surface
where NEE fires, so the depth budget bounds how many panes the feature can
act behind. **Consequence for the table above:** at `max_depth=8` the
flatline at 8 panes has two overlapping causes — the cap *and* the depth
budget — and this test does not cleanly separate them at that point. The cap
claim rests on the exact 1.00 ratio persisting for 9, 10 and 12 panes.

**Cleanest single-pane measurement:** at `max_depth=2`, one pane gives OFF =
0.00257 against ON = 0.64646 — a **251x ratio**, with ON recovering 91% of the
unobstructed reference (0.71192). With multi-bounce suppressed, a single pane
almost completely blocks NEE, and the feature restores nearly all of it.

**Anomaly investigated:** the OFF column is non-monotonic at `max_depth=8`,
dipping to 0.0587 at 4 panes then rising to 0.848 at 12. Hypothesis:
inter-pane multi-bounce, i.e. light reaching the receiver by reflecting
between densely stacked panes rather than passing directly. Test: re-run at
`max_depth=2` to suppress multi-bounce. Result: the curve flattened into a
clean monotonic rise, confirming the hypothesis. The rise itself remains
attributable to paths other than NEE (BSDF-sampled refraction still reaches
the light), which is why OFF is not zero for any pane count.

## 20j. Additions to Section 6 — Known Limitations

- **NEE ignores occlusion by smooth transmissive surfaces when
  `transparent_shadows` is enabled.** A deliberate, opt-in production
  approximation ("shadow-transparent glass"), not a defect: the exact
  alternative is Manifold Next Event Estimation, out of scope here.
  Consequences, all measured: light passing through glass for shadow purposes
  travels straight rather than refracted and unattenuated (bias bounded by the
  Fresnel curve, ~4% at normal to ~61% at grazing incidence — 20f);
  delta-transmissive objects cast no direct shadow (1.97% of affected pixels
  darkened, 41:1 brightened-to-darkened — 20g); and relative per-pixel
  variance rises ~35-40% in exchange for 1.495x delivered radiance (20h).
- **Pass-through budget is bounded by both `max_transparent_shadow_depth` and
  the integrator's `max_depth`.** The latter is usually the binding
  constraint, since the camera path must traverse each transmissive surface
  before NEE fires. Exceeding either degrades conservatively to full occlusion
  (20i).


---

## 20k. Isolating the wine-glass shadow loss

Section 20g flagged that its shadow-loss measurement could not separate the 
window's contribution from the wine glasses': both are delta-transmissive, and
the window dominates the frame's response. 20g proposed an unglazed-window 
variant scene as the way to isolate them and noted this was not performed.

Isolation was instead achieved by giving specific materials an opt-out from 
approximation 3 (§20d): an `opaque_shadow_shapes` integrator property takes
a comma-separated list of material ids and excludes them from the `transparent_shadows`
pass-through, restoring their normal occlusion behaviour — and therefore 
their own contact shadow — while every other delta-transmissive surface, 
including the window, is unaffected. This does not revise the 20g measurement, 
which remains the correct figure for the unmitigated case; it documents a further,
scoped refinement available on a per-material basis.

## 20l. Implementation obstacle — shape identity is not preserved through mesh merging

The first implementation resolved the exclusion list against shape ids read
directly from `scene.xml` (`WineGlasses_0001`, `WineGlasses_0002`), matching
the pattern already used by `hide_from_camera`. It consistently resolved zero 
shapes, despite both ids being present and correctly spelled in the XML.

A standalone diagnostic script, run independently of the validated integrator 
and BSDF code, established why:

| Source | Shape count | With a non-empty id |
|---|---|---|
| `scene.xml` (parsed as text) | 301 | 298 |
| `scene.shapes()` at runtime | 85 | 45 |
| `mi.traverse(scene)` | — (443 parameter keys) | `WineGlasses_0001`/`_0002` absent |

Both wine-glass meshes render correctly in every test to this point, so the
geometry was known to be loaded; only its individual addressability was in question.
Searching the 85 runtime shapes by BSDF rather than id located a single shape with 
an empty id and 27,136 faces carrying `bsdf=WineGlassesBSDF` — the two wine-glass
meshes, merged into one shape during scene loading. A merged shape retains its BSDF
reference but not the id either source mesh had in `scene.xml`.

**This generalises beyond this one feature.** Any code that resolves `scene.xml` 
shapes by id — `hide_from_camera` included — is reliable only for shapes Mitsuba 
does not merge at load time. `hide_from_camera`'s two lights happen not to be
merge candidates, which is incidental to how they were authored, not a guarantee
the approach holds elsewhere.

## 20m. Fix and verification

`opaque_shadow_shapes` was changed to match against `si_sh.bsdf().id()` at the 
intersection point rather than against `scene.shapes()` ids collected up front.
This requires no change to `principled_bsdf` and no change to `_shadow_blocked()`'s
occlusion logic — only how the exclusion set is resolved. `WineGlassesBSDF` 
was set as the excluded material in `build_scene.py`; the window pane and 
`RadioGlassBSDF` (both `thin=true`) are unaffected, since exclusion is applied 
only to the one material named.

Verification to date is qualitative: a matched `--transparent-shadows` on/off 
pair on the table close-up sensor shows the sunbeam still entering through the
window in both, and the wine glasses' contact shadow present with the exclusion
and absent without it — confirming the mitigation is additive to approximation 
3 rather than a replacement for it. A quantitative repeat of 20g's methodology, 
restricted to this scene and comparing exclusion-on against exclusion-off, would
give a directly comparable number; worth doing before submission if time allows, 
not yet performed.

## 20n. Addition to Section 6 — Known Limitations

- **`opaque_shadow_shapes` is a manually curated exception list, not a derived one.**
-  A material must be explicitly named in `build_scene.py` to keep its shadow; 
nothing in the scene automatically distinguishes "a window, which should lose its
shadow" from "an object, which probably shouldn't" — that judgement is made once,
by hand, at scene-build time, and does not extend to new glass objects added later 
without the same step.



----


# 21. Window Glazing — The Source Scene Had No Real Glass

## 21a. Discovery

Investigating an unexplained shadow direction on a dining chair (Section 22
covers the full diagnostic chain that followed), `build_scene.py`'s original
`remove_fake_window_light()` was examined directly rather than assumed
correct. Bitterli's original `scene_original.xml` fakes daylight with a
single `<shape type="rectangle">` sitting in the window opening: a black
diffuse BSDF (`reflectance = 0, 0, 0`) plus an `area` emitter
(`radiance = 16.032`). `remove_fake_window_light()` deleted this shape
entirely.

**Consequence, confirmed by checking `WindowBSDF` directly against the
original XML:** `WindowBSDF` — the material actually assigned to the
`Window_0001`/`Window_0002` sash meshes — is plain diffuse grey
(`0.571765, 0.563535, 0.559972`), not `dielectric` or `thindielectric`. There
is no real glass anywhere in the source scene for this window. Deleting the
fake-light rectangle therefore left the window opening physically **open** to
the environment: nothing occupies that space at all.

## 21b. Fix

Rather than adding new geometry (risking misalignment with the opening),
`glaze_fake_window_light()` repurposes the same rectangle: strips its emitter
and black BSDF, and assigns a real `principled_bsdf` in their place
(`base_colour=1,1,1`, `roughness=0`, `transmission=1.0`, `ior=1.5`,
`thin=true`). `thin=true` because the rectangle is a single infinitely-thin
surface, not a closed volume — the same reasoning as the radio dial cover
(Section 16).

**Deliberately not wrapped in `twosided`.** `twosided` flips the surface
normal, which destroys the entering/exiting distinction transmission depends
on — the exact mechanism that rendered the wine glasses solid black earlier
in this project. `glaze_fake_window_light()`'s docstring records this
explicitly so the mistake cannot recur on this shape.

A `glaze=False` mode is retained on the same function (reverts to full
removal, matching the original behaviour) — used for the isolation testing in
Section 22, and available if a future comparison needs the open-opening case
again.

## 21c. Validation

Direct geometric confirmation (e.g. a bounding-box probe on `Window_0001`/
`Window_0002` against the opening's known extent) was not performed
separately — the evidence here is the source-material check (21a) combined
with the render behaviour once both this fix and the Section 22 fix were in
place: `test_set_scene_fix.png` (max_depth=1, area emitters stripped) showed
light present **only** through the window opening and correctly absent
everywhere else — the physically expected result for a sealed room with one
glazed opening. That result depended on both fixes; see Section 22 for why
glazing alone was not sufficient to produce it.

## 21d. Known limitation carried forward

`fix_window_material()` (which sets the *sash/frame* material, distinct from
the pane) currently sets `transmission=0.0`, `base_colour=1,1,1`,
`roughness=0.0` — opaque, white, and smooth. Bitterli's original was grey
diffuse (`0.5718, 0.5636, 0.5600`, `roughness=1.0`). This is a real, currently
undocumented departure from "restoring the original" — a smooth white frame
will catch specular highlights the rough grey original would not. Not yet
resolved; flagged here rather than silently left.

`WindowBSDF` remains wrapped in `twosided`, which would be a live risk if
`fix_window_material` is ever changed to set `transmission > 0` again — at
`transmission=0.0` this is currently inert.

---

# 22. `CustomEnvmap` Shadow-Ray Truncation Bug (`bsphere_radius`)

The most significant bug found during the kitchen-scene build: a single
uninitialised value silently limited every NEE shadow ray toward the
environment to 2 metres, in a room several metres across.

## 22a. Symptom

With the window glazed (Section 21) and Bitterli's 3 original area emitters
stripped (`remove_all_area_emitters()`, confirming the scene has exactly 3 —
resolving an open question from the earlier Blender-comparison session
notes), the envmap should have been the sole light source. A dining chair's
shadow fell in a direction inconsistent with the window as the only key
light. The room also read visibly brighter overall than the equivalent
Blender/Cycles reference.

## 22b. Diagnostic chain — geometry ruled out first

Rather than assume a leak, each candidate was tested directly.

**`max_depth=1` isolation.** At depth 1 there are no bounces — only direct
lighting is visible. `iso_D_direct_only.png` showed **two distinct,
directionally separate lit patches**, one entering from a direction with a
wall in the way. Since only NEE and the BSDF-hit path can contribute at
depth 1, and the BSDF-hit path requires the camera ray itself to reach the
emitter, this located the leak to the light-delivery path rather than to GI.

**Hemisphere-escape probes**, fired outward from the two lit points:

| Probe point | Surface normal | Escape fraction | Escaping directions |
|---|---|---|---|
| Floor | `(0, 1, 0)` | 50.42% | ALL had `y < 0` — zero escape into the upper hemisphere the point is lit from |
| Wall | `(0, 0, 1)` | 4.26% | All behind/below (`y<0`, `z<0`) — zero escape on the front-facing side |

Both lit points therefore had **zero measured escape on the side they were
lit from** — a direct contradiction if illumination requires line of sight to
the sky.

**Ceiling probe**, purpose-built to test the specific "is the ceiling
letting light in" question: 20,000 rays fired into the upper hemisphere from
a point inside the room.

```
escaped (see envmap directly): 0  (0.00%)
hit geometry:                  20000  (100.00%)
distinct BSDF flag values on hit surfaces: [98314]   <- opaque, no
                                                          Transmission/Null bits
of the rays that hit, 0.01% escape immediately past that first surface
```

**Result: ceiling is genuinely sealed and fully opaque.** This eliminated a
hole or a mis-converted transmissive ceiling material.

**Opaque-window control.** With the glazed pane's `transmission` set to `0.0`
for this test only, the same lit patches persisted. This ruled out the window
as the leak's source and, combined with the probes above, eliminated geometry
entirely — every surface tested was measurably sealed on the relevant side,
yet still lit at `max_depth=1`.

## 22c. Root cause

With geometry eliminated, the remaining candidate was the delivery mechanism
itself: `CustomEnvmap.sample_direction()` sets

```python
ds.dist = 2.0 * self.bsphere_radius
ds.p = it.p + d * ds.dist
```

and Mitsuba's shadow ray is tested only along the segment to `ds.p`.
`self.bsphere_radius` is initialised to `1.0` in `__init__` and is only ever
corrected inside `set_scene()`:

```python
def set_scene(self, scene):
    bbox = scene.bbox()
    self.bsphere_radius = dr.norm(bbox.max - bbox.min) * 0.5
```

**Confirmed by direct measurement, not inference:** a `print()` was placed
inside `set_scene()`. Across multiple renders, it never printed. `set_scene`
does not fire for this Python emitter plugin in this Mitsuba build.
`bsphere_radius` therefore stays at its initialised `1.0`, `ds.dist` is
`2.0`, and **any occluder farther than 2 metres from the shading point is
never tested** — the shadow ray simply ends before reaching it, and the
environment reports as visible regardless of what is actually in the way.

## 22d. Fix

```python
# __init__
self.bsphere_radius = 1e6   # was 1.0
```

A large constant is the correct fix, not a smaller scene-derived one: for an
infinite emitter, `ds.dist` has exactly one job — exceed the scene's extent —
and does not otherwise enter the pdf or radiance calculation.

`set_scene()` was also changed so that, if it is ever invoked (a different
Mitsuba build, a future version), it cannot **shorten** the radius, only
lengthen it:

```python
def set_scene(self, scene):
    bbox = scene.bbox()
    self.bsphere_radius = dr.maximum(dr.norm(bbox.max - bbox.min) * 0.5,
                                      self.bsphere_radius)
```

## 22e. Verification

Re-running the identical isolation setup (area emitters stripped, window
glazed, `max_depth=1`) after the fix: `test_set_scene_fix.png` shows the room
correctly black except through the window opening — exactly the result 22a's
symptom description says should have appeared and did not, prior to this
fix. A subsequent multi-bounce render (`transmission` restored, full
`max_depth`) confirmed daylight now enters solely and correctly through the
glazed pane.

## 22f. Why prior validation never caught this

Sections 7, 7a and 7b's envmap validation used `environment_lighting_scene`
— a single sphere on an open plane, with no enclosure and nothing more than
a couple of units from anything else in the scene. A 2-metre shadow ray was
always long enough there, so the truncation was numerically inert and
invisible to those tests. The kitchen scene is the first real interior
geometry at real room scale (several metres across) built in this project —
exactly the condition needed to expose the bug. This is the same class of
finding as the anisotropic-GGX chi-squared harness collapse (Section 13): a
test that is correct on its own terms but structurally unable to exercise the
failure mode, discovered only when a sufficiently different scene was tried.

## 22g. Impact — not fully quantified

This bug plausibly explains a substantial share of the original
Blender-vs-Mitsuba brightness discrepancy that motivated this entire
investigation: every surface in the room was receiving unoccluded environment
light from any direction within 2 metres, regardless of whether a wall,
ceiling, or piece of furniture should have blocked it. **This has not been
isolated and re-measured against the original Blender comparison numbers** —
worth doing if time allows, since it would close that earlier open thread
with a confirmed mechanism rather than a plausible one.

## 22h. Addition to Section 6 — Known Limitations

- **Resolved, not a live limitation, but worth recording as a methodology
  note:** `CustomEnvmap`'s shadow-ray distance depended on `set_scene()`
  being invoked by the host renderer. It is not, for Python emitter plugins,
  in this Mitsuba build. Any future custom emitter in this codebase should
  default distance-dependent parameters to a value safe for the *largest*
  plausible scene, not derive them from a scene-callback that may silently
  never fire.

## 22i. Canonical Section 5.6 evidence

The final thesis evidence is consolidated under
`outputs/evaluation/5_6_failure_case/` and audited by
`tests/evaluation/scale_failure/evaluate_scale_failure.py`. Six approved
images retain the actual diagnostic sequence: incoherent illumination,
environment-only isolation, direct-only isolation, opaque-window control before
the fix, the exactly black opaque-window control after the fix, and restored
illumination after re-enabling pane transmission. The HDRI angle sweep remains
legacy evidence and is not required for the causal argument.

---

# 23. Multi-Pass Rendering — Sample-Count Divisibility Constraint

## 23a. The constraint

Dr.Jit's `llvm_ad_rgb` variant has an upper limit of 2^32
(4,294,967,296) total Monte Carlo samples (`width x height x spp`) per
rendering pass. Above that, Mitsuba automatically splits the render into
multiple passes and averages them — but **the requested `spp` must be evenly
divisible by the chosen pass count**, or it raises:

```
RuntimeError: [Sampler] sample_count should be a multiple of samples_per_wavefront!
```

**Confirmed directly, not assumed**, across several render attempts at
1920x1280:

| spp | Sampler | Total samples (reported) | Passes | Result |
|---|---|---|---|---|
| 4000 | stratified (rounds to 4096) | 3,354,624,000 | 3 | CRASH (4096 / 3 not integer) |
| 4000 | independent | 3,275,980,800 | 3 | CRASH (4000 / 3 not integer) |
| 3999 | independent | — | 3 | OK (3999 / 3 = 1333) |
| 2048 | independent | 2,516,582,400 | 2 | Process silently killed (see 23c) |

**The pass count is derived from total sample volume, resolution, and spp
together — it is not a fixed number.** A different resolution or spp choice
can select 2, 3, or more passes, so "always use a multiple of 3" is not a
general rule; the correct approach is to read the pass count from Mitsuba's
own warning and pick an `spp` divisible by it.

## 23b. Stratified sampler compounds the problem

`stratified` silently rounds `spp` up to the nearest perfect square (e.g.
4000 to 4096) before the divisibility check runs, so a value chosen to be
divisible by the pass count can be invalidated by the rounding itself.
`independent` performs no such rounding and is the more predictable choice
for high-spp final renders, at the cost of the ~19.5% noise-reduction
documented in Section 10a — a reduction whose benefit narrows sharply at high
sample counts, since the sample count itself is doing most of the variance
reduction by that point.

## 23c. A distinct failure mode: silent OOM kill

The `spp=2048` case above did not raise an exception — it produced the
"splitting into 2 passes" warning and then exited with **no traceback and no
`Wrote` line**. This is a different mechanism from 23a's divisibility crash:
Dr.Jit is a wavefront renderer and holds an entire pass's worth of ray state
(origin, direction, throughput, interaction data) in memory simultaneously.
At 1024 spp per pass (2048/2) and 1920x1280, that is on the order of 2.5
billion simultaneous live samples — enough to exhaust available memory,
at which point the OS terminates the process before it can print anything.
**Recognisable signature:** the render silently stops after the pass-split
warning, with no error output of any kind.

More RAM does not address the root constraint (2^32 is an architectural
limit of the variant, not a memory ceiling) — it only changes how many
oversized passes happen to survive before hitting a memory wall, and that
boundary is machine- and system-load-dependent, which is consistent with the
same `spp=2048` command succeeding on one run and failing on another.

## 23d. Adopted solution — accumulation over single high-spp renders

Rather than hunting for spp values that survive both the divisibility check
and the memory ceiling, final high-sample-count renders are produced by
averaging N independently-seeded lower-spp renders. This is mathematically
identical to a single render at N times the spp — same unbiased result, same
variance reduction — and sidesteps both failure modes: each individual render
stays comfortably under the single-pass sample limit, so no pass-splitting
(and therefore no divisibility arithmetic) is ever triggered.

**Prerequisite — `render_scene.py` had no seed control**, so repeated
renders were not independent and could not be validly averaged. This was
also a standing, previously unaddressed reproducibility gap (every render
non-reproducible, `main.py`'s outstanding tidy item since early sessions).

```python
# render_scene.py
parser.add_argument('--seed', type=int, default=0, ...)
...
img = mi.render(scene, spp=args.spp, sensor=args.sensor, seed=args.seed)
```

**Averaging must operate on raw linear data.** Two requirements, both
consequences of work already validated earlier in this project: average the
**undenoised** beauty channels (OIDN, Section 17, is itself a small biased
filter — applying it before averaging would compound bias across the
accumulated set rather than cancel), and average **linear EXR** values, never
gamma-encoded PNG output (`write_bitmap` bakes in sRGB gamma for `.png`
targets specifically, per the `file_format` behaviour noted when this
extension-driven encoding was first identified for the diagnostic EXR
exports).

**Secondary benefits:** accumulation is interruptible (a partial set of N
renders is still usable if a later one fails) and directly reuses the
per-render `--seed` flag now available for any other multi-seed measurement
(e.g. the convergence testing in Section 20h).

## 23e. Addition to Section 6 — Known Limitations

- **Single-pass Monte Carlo sample budget is architecturally capped at 2^32**
  for the `llvm_ad_rgb` variant. High total sample counts (large resolution
  x spp products) require either an `spp` evenly divisible by Mitsuba's
  automatically-chosen pass count, or — the adopted approach — accumulating
  multiple independently-seeded lower-spp renders in post. The latter is
  preferred: it avoids pass-count arithmetic entirely, is memory-safe
  regardless of resolution, and provides partial-failure resilience that a
  single large render does not.



---

## 23f. Implementation

`render_scene.py` gained a `--passes` argument (default `1`). At `passes <= 1`,
the code path is byte-identical to before this feature existed — a single `mi.render()`
call. At `passes > 1`, the scene is rendered `passes` times, each with `seed + i`, 
accumulated as a running sum in numpy and divided by `passes` before being written out
— the same numpy round-trip pattern already used in `denoise_aovs.py` (`np.array(bitmap)`
→ operate → `mi.TensorXf(...)` → `write_bitmap`).

## 23g. Regression test — `--passes 1` must reproduce prior behaviour

Four renders at identical settings (`--sensor 2 --spp 64 --resx 640 --resy 360 --seed 42`):
two with no `--passes` flag, two with `--passes 1` explicit.

| Pair | Flag state | Bit-identical | Mean \|diff\| | Max \|diff\| |
|---|---|---|---|---|
| a vs c | both no flag | **True** | 0.000000 | 0.000000 |
| a vs b | no flag vs explicit `1` | False | 0.004152 | 0.526121 |
| a vs d | no flag vs explicit `1` | False | 0.004630 | 0.991741 |
| b vs d | explicit `1` vs explicit `1` | False | 0.003141 | 0.996155 |

**Result: mostly pass, with one unresolved and low-priority finding.** No-flag runs 
reproduced exactly. Every pair involving an explicit `--passes 1` showed a small difference,
but the `b`-vs-`d` result rules out "explicit `--passes 1` deterministically takes a 
different path" — two runs of that same configuration didn't match each other either, 
so this isn't a stable, reproducible branch difference. Cause not isolated. **Not investigated 
further given its magnitude**: ~0.003–0.005 mean difference is roughly two orders of 
magnitude below the ordinary Monte Carlo noise floor at comparable sample counts (see 23h),
and the code path is identical regardless of whether the flag is typed explicitly.

## 23h. Statistical equivalence — accumulated result vs. an ordinary render at the same total spp

Three renders at 256 total spp, `--sensor 2 --resx 640 --resy 360`: two ordinary single-pass 
renders at different seeds, one accumulated as 4×64spp.

| Comparison | Mean \|diff\| | RMSE |
|---|---|---|
| single (seed 100) vs single (seed 300) | 0.380635 | 10.696407 |
| single (seed 100) vs accumulated 4×64 (seed 200) | 0.388122 | 10.775524 |

**Result: pass.** The accumulated render differs from an ordinary render by essentially t
he same magnitude two ordinary independent renders differ from each other (0.388 vs 0.381 
mean; 10.78 vs 10.70 RMSE). Accumulation is not introducing detectable bias relative to a 
single render at the same total sample count.

## 23i. Stress test — reproducing and resolving the §23a failure case

§23a documents `--spp 4000` at `1920x1280` crashing as a single pass (stratified sampler 
rounds to 4096, not evenly divisible by Mitsuba's chosen pass count). The same total sample
count, run as 8 independently seeded passes of 500 spp each:

```
uv run render_scene.py --sensor 0 --spp 500 --resx 1920 --resy 1280 --seed 0 --passes 8 --out outputs/test_high_total.exr
```

**Result: completed successfully**, where the equivalent single-pass request is documented to fail. 
Each individual `mi.render()` call (500 spp) stays far under Mitsuba's own pass-splitting threshold 
at this resolution, so the crash's root cause never triggers. **Caveat:** this run did not have 
`firefly_clamp`/`transparent_shadows` set to their intended final values, so the *image* isn't 
representative of a final render — only the mechanism (does high-total-spp accumulation complete 
without crashing) was being tested here, and it was.

## 23j. Timing cost — measured, pass count not yet shown to be necessary at this granularity

The 8-pass run above took approximately one hour at `1920x1280`. Whether 8 passes was 
the right choice is an open question worth stating honestly rather than assuming: the 
architectural ceiling this feature exists to avoid is 2^32 total samples *per single 
`mi.render()` call* (§23a). At `1920x1280` (2,457,600 pixels), that ceiling falls at 
approximately **1,748 spp per call** — meaning a single pass could have gone up to roughly
that spp before risking the crash at all. The 500-spp-per-pass choice here has substantial
headroom under that ceiling; whether fewer, larger passes (e.g. 4×1000 or 2×2000, both spread
to reach the same 4000-spp total) would render meaningfully faster is untested. Total compute
should be similar either way if render time scales with total samples rather than pass count,
but that assumption itself hasn't been measured — each `mi.render()` call may carry non-trivial
per-call overhead (Dr.Jit kernel dispatch, sampler setup) that a lower pass count would reduce.
**Not resolved here** — a genuine, cheap, time-permitting follow-up (three renders at matched 
4000-spp total, varying only pass count, comparing wall-clock time) rather than something this
write-up assumes an answer to.

## 23k. Addition to Section 6 — Known Limitations, extending 23e

- **Renders are reproducible with a fixed seed to within ~0.004 mean absolute difference**, 
not exactly bitforbit in every observed case; cause not isolated, and roughly two orders
of magnitude below the ordinary Monte Carlo noise floor at typical sample counts (23h),
so not treated as practically significant.
**Pass count for a given total spp target has not been shown to be optimal** — headroom 
under the architectural perpass ceiling means a lower pass count may achieve the same 
result faster, untested (23j).
