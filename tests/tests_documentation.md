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
Rendered a simple two-material scene (sphere + floor, distinct base
colors and roughness values) with `with_aovs=True` and inspected each
pass independently:

- **Albedo:** flat, uniform color per object, no lighting falloff or
  highlight — confirms the override is taking effect and the pass
  reflects material color only, independent of the lit beauty render.
- **Normal:** smooth per-pixel variation across the curved sphere;
  the flat floor plane's known geometric orientation matches its
  expected constant remapped color exactly, confirming world-space
  orientation is captured correctly.
- **Depth:** continuous gradient across visible geometry, consistent
  with relative camera distance.

**Result: PASS.** Regression suite (`run_all.sh`) re-confirmed
unaffected with the default `with_aovs=False`.

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
