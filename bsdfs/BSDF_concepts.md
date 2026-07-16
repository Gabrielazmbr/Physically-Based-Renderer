# Principled BSDF Concepts

A reference document covering the core concepts behind the custom
Principled BSDF, organised to follow the order the code itself is read:
class definition, lobe-selection probability, `sample()` step by step,
`fresnel_schlick()`, `eval()`, `eval_specular()`, then `pdf()`.

---

## 1. Overview

```text
              Principled BSDF
                      |
          -------------------------
          |            |            |
        sample()      eval()       pdf()
          |             |            |
  Choose a direction    |     How probable the
  for the next bounce   |     direction is.
          |             |
          |             |
          ------------eval------------
                        |
              How much light gets
            reflected in a direction.
```

Three functions, three jobs. `sample()` is called by the path tracer's
BSDF-sampling step (see `path_tracer_concepts.md`, section 8) to pick a
new direction to bounce towards. `eval()` is called by NEE (section 7) to
ask "if I already know I want to go towards this specific direction —
say, towards a light — how much of the surface's light actually travels
that way?" `pdf()` answers "if `sample()` were run again, how likely is
it that it would have picked this particular direction?" — needed for
MIS, so NEE's light-sampling strategy and this BSDF's own sampling
strategy can be compared and weighted fairly against each other.

### Material building

```text
          Principled BSDF
                  |
            Metallic parameter
                  |
        --------- + -------------
    (Metallic mixes between the two)
        |                       |
    Diffuse                  Specular
      lobe                    GGX lobe
        |                       |
  Lambertian-ish          Microfacet GGX
        |                       |
  plastic/paint/etc.        glossy metals
```

Every real-world reflectance this BSDF can represent is a mix of exactly
two building blocks — a soft, matte diffuse lobe and a glossy, mirror-like
specular lobe — with `metallic` controlling how much of each.

---

## 2. Class Definition — `__init__`

```python
self.base_colour = mi.Color3f(props.get("base_colour", mi.Color3f(1.0)))
self.roughness = props.get("roughness", 0.0)
self.metallic = props.get("metallic", 0.0)
```

Three parameters read from the scene dictionary, with sensible defaults:
white, perfectly smooth, fully dielectric.

### Metallic Parameter

`metallic` is the single control that decides which of two very
different physical behaviours a surface has:

- **Dielectrics** (`metallic = 0`) — plastic, wood, skin, paint. Light
  hitting the surface partially reflects (a small amount, governed by
  Fresnel) and partially refracts *into* the material, where it scatters
  around between internal particles and re-emerges in a essentially
  random direction — this re-emergence is what the diffuse lobe models.
  Because the light has bounced around inside the material before
  re-emerging, it picks up the material's tint — hence "base colour"
  drives the diffuse term.
- **Conductors** (`metallic = 1`) — metals. Free electrons in the metal
  immediately re-radiate any light that enters, within a fraction of a
  wavelength of the surface. There is no meaningful subsurface
  scattering, so there is no diffuse term at all — all reflected light
  is specular, and critically, the metal's own colour tints *that*
  reflection directly (which is why `fresnel_schlick`, in section 5,
  uses `base_colour` as `F0` when `metallic = 1`, rather than the fixed
  `0.04` used for dielectrics).

`metallic` is therefore not just a blend slider for artistic convenience
— it's standing in for a genuine physical difference in how light
interacts with the surface at all. Values between 0 and 1 don't
correspond to a single real material; they're a practical compromise
that lets one parameter approximate things like rusted or part-oxidised
metal.

```python
self.m_flags = (
    mi.BSDFFlags.DiffuseReflection
    | mi.BSDFFlags.GlossyReflection
    | mi.BSDFFlags.FrontSide
)
self.m_components = [
    mi.BSDFFlags.DiffuseReflection | mi.BSDFFlags.FrontSide,
    mi.BSDFFlags.GlossyReflection | mi.BSDFFlags.FrontSide,
]
```

`m_flags` is a single bitmask (built with bitwise OR) describing
*everything this BSDF can do overall*: it can reflect diffusely, it can
reflect glossily (the GGX lobe), and it only has a front side — no
transmission, matching a fully opaque material.

`m_components` is different — a **list**, one entry per distinct lobe,
rather than one combined mask. This is what lets an integrator or AOV
pass address "the diffuse part" and "the glossy part" of this BSDF
separately, rather than treating it as one opaque blob. `sample()`'s
`bs.sampled_component` (section 6) reports an index into *this exact
list* — `0` for diffuse, `1` for glossy — so anything downstream can tell
which lobe actually produced a given sample.

---

## 3. `_spec_prob()` — Lobe Selection Probability

```python
def _spec_prob(self):
    return dr.select(self.metallic > 0.99, mi.Float(1.0),
        mi.Float(dr.clamp(self.metallic * 0.8 + 0.1, 0.1, 0.9)))
```

This is a single number between 0 and 1 — the odds of a **weighted coin
flip** used to decide which lobe to sample from, before any direction is
even chosen. "Weighted" doesn't mean 50/50; it means *unequal* odds,
whatever `metallic` dictates. At `metallic = 0.2`, for instance, this
returns `0.26` — meaning roughly 26% of calls to `sample()` will attempt
the specular lobe, and 74% the diffuse lobe.

**This is not a PDF.** A PDF (probability density function) describes,
over a whole continuous space — every possible direction on the
hemisphere — how likely each individual direction is. `_spec_prob()`
isn't over directions at all; it's over exactly two discrete choices:
"use the specular sampler" or "use the diffuse sampler." Each individual
call to `sample()` is still all-or-nothing — a single call never returns
"26% specular blended with 74% diffuse"; it returns one direction, fully
from one lobe or the other. The blending only happens statistically,
across many calls.

This is a standard Monte Carlo technique for sampling from a **mixture**
of two distributions: rather than constructing one direct sampler for "a
weighted blend of two different shapes" (mathematically awkward), you
pick which distribution to draw from *proportionally to its weight*,
then sample cleanly from just that one. Over enough samples, the
aggregate result is statistically identical to true mixture sampling.

The specific numbers: at `metallic > 0.99` (a pure conductor), the result
is `1.0` — always sample specular, since a fully metallic material has no
diffuse lobe anyway (`weight_diff` gets multiplied by `(1 - metallic)`
later, so it's zero regardless of what this function returns). Otherwise
it's `clamp(metallic * 0.8 + 0.1, 0.1, 0.9)` — ranging from `0.1` (mostly
diffuse sampling, at `metallic = 0`) up to `0.9` as `metallic` approaches
`1`. The floor and ceiling mean the algorithm never fully commits to one
lobe below full metallic — even a fully dielectric material still sends
10% of samples towards specular, because glossy highlights can still be
important to resolve even when most of the reflected energy is diffuse.

This same value reappears twice more: as the actual coin flip in
`sample()` (`sample1 < spec_prob`, section 4), and as the mixing weight
in the combined PDF formula (`pdf_val = spec_prob * spec_pdf + (1 -
spec_prob) * diff_pdf`, sections 6 and 9) — where it turns two separate
per-lobe densities into one combined mixture density.

---

## 4. `sample()` — Setup

```python
def sample(self, ctx, si, sample1, sample2, active=True):
    cos_theta_i = mi.Frame3f.cos_theta(si.wi)
    active = active & (cos_theta_i > 0)
    spec_prob = self._spec_prob()
    alpha = dr.maximum(self.roughness * self.roughness, 1e-4)
    distr = mi.MicrofacetDistribution(mi.MicrofacetType.GGX, alpha, sample_visible=True)
    bs = mi.BSDFSample3f()
    sample_specular = sample1 < spec_prob
```

`si.wi` is the incoming direction (towards the camera / previous bounce),
expressed in the surface's **local shading frame**, where the z-axis
*is* the surface normal by construction — so `cos_theta_i`, the cosine of
the angle between the incoming direction and the normal, is just the
z-component of `si.wi`. `sample1` is a fresh 1D random number (used for
the lobe coin-flip); `sample2` is a fresh 2D random number (used to pick
a direction *within* whichever lobe gets chosen) — Mitsuba conventionally
splits these because picking "which lobe" only needs one number, while
picking "which direction on a hemisphere" needs two.

**`alpha = roughness²`** — squaring `roughness` before it's used is the
standard Disney/Burley convention: it makes the *perceptual* roughness
slider feel more linear to an artist, even though GGX's underlying math
wants the squared value. The floor of `1e-4` exists because at
`roughness = 0` exactly, `alpha = 0` would make the GGX distribution
mathematically degenerate.

**`sample_visible=True`** selects **VNDF sampling** (Visible Normal
Distribution Function — the Heitz 2018 paper in your references), rather
than naive GGX sampling. This is *why* the specular weight formula
(section 5) collapses to the clean `F * G2/G1` — that simplification only
holds because microfacet normals are sampled from the visible-normal
distribution specifically.

---

## 5. Specular Sampling

```python
wi_hat = dr.mulsign(si.wi, cos_theta_i)
m, m_pdf = distr.sample(wi_hat, sample2)
wo_spec = mi.reflect(si.wi, m)
valid_spec = (mi.Frame3f.cos_theta(wo_spec) > 0) & active

cos_mi = dr.dot(si.wi, m)
F = self.fresnel_schlick(cos_mi)
G1 = distr.smith_g1(si.wi, m)
G2 = distr.G(si.wi, wo_spec, m)
weight_spec = dr.select(G1 > 0, F * G2 / G1, mi.Color3f(0))
```

### GGX Specular

At a microscopic level, no surface is perfectly flat. Even a surface
that looks smooth to the eye is covered in tiny facets — microscopic
bumps and grooves pointing in slightly different directions. A mirror
has facets all perfectly aligned, so all light reflects in exactly one
direction. A rough surface has facets pointing in many different
directions, so light scatters broadly. A glossy surface sits somewhere
between — most facets roughly aligned, with some variation.

GGX (also called Trowbridge-Reitz) is a mathematical distribution
describing how these microfacets are oriented. At `roughness = 0`, all
facets are perfectly aligned (mirror); at `roughness = 1`, they point in
random directions (diffuse-like). The distribution is bell-shaped around
the surface normal, but GGX has longer tails than older distributions
like Beckmann — more facets at extreme angles — which produces the
characteristic bright, elongated highlights seen on metals and plastics
in production renders.

- **D** — the distribution function, GGX itself: how many facets are
  oriented towards the halfway vector between incoming and outgoing
  light.
- **G** — the geometric term: accounts for facets shadowing and masking
  each other at grazing angles.
- **F** — the Fresnel term: how much light reflects versus refracts at
  each facet, based on viewing angle (section 8).

The full specular BSDF is:
```
f_specular = (D * G * F) / (4 * cos_theta_i * cos_theta_o)
```
(implemented for real in `eval_specular()`, section 10 — this line is the
*evaluation* form; `sample()` needs a different, sampling-specific
formula, below.)

### The halfway vector

The halfway vector (or half vector) sits exactly between the incoming
and outgoing directions. It's the orientation a microfacet would need to
have in order to reflect light from the incoming direction towards the
outgoing direction.

GGX uses it because, instead of asking "how much light goes from
direction A to direction B", it asks "how many microfacets are oriented
towards the halfway vector between A and B" — because those are the
*only* facets that contribute to that specific reflection. The
distribution `D(h)` answers exactly that question.

```python
h = dr.normalize(si.wi + wo)  # halfway vector
```

### `wi_hat` and two-sided handling

`dr.mulsign(si.wi, cos_theta_i)` flips `si.wi` to the same side as the
shading normal if it isn't already. Since `sample()` already gates
`active` on `cos_theta_i > 0` (section 4), `si.wi` is already
front-facing by the time this runs — so `wi_hat == si.wi` in practice
here. It's a defensive step matching Mitsuba convention for BSDFs that
might be queried from either side.

### VNDF sampling and specular failure

`distr.sample(wi_hat, sample2)` draws a microfacet normal `m` from the
*visible* normal distribution (Heitz 2018) — importance-sampling only the
microfacets that could actually be seen from the incoming direction,
rather than all of them. `wo_spec = mi.reflect(si.wi, m)` reflects the
real incoming direction about that microfacet normal.

`valid_spec` checks whether the resulting reflection direction is still
above the hemisphere. It sometimes isn't — for rough, grazing-angle
configurations, a sampled microfacet normal can produce a reflection that
points *below* the surface, which is non-physical. When this happens,
the specular attempt is discarded (see `weight`, section 7) rather than
patched or redirected — which means the renderer genuinely loses a small
amount of energy at high roughness. **This is the actual mechanism behind
the documented "GGX single-scattering energy loss" limitation** — it
isn't a separate approximation bolted on afterwards, it's a direct
consequence of some VNDF samples failing to produce a valid direction at
all. Production renderers (Arnold, RenderMan) compensate for this with
*energy compensation* (Kulla & Conty 2017) — modelling the lost
multi-bounce microfacet energy analytically and adding it back in,
rather than tracing it.

### Specular weight — Heitz 2018

`weight_spec = F * G2/G1` looks deceptively simple for what's actually
being computed. This is the closed-form importance-sampling weight
specifically derived for VNDF sampling (Heitz 2018): because the sampled
microfacet normal `m` was already drawn *proportionally* to the visible
normal distribution, most of the terms in the full Cook-Torrance
specular BRDF (`D`, and one `cos` term) cancel out algebraically against
the sampling PDF, leaving only this compact ratio. `G1` is the
*incoming*-direction masking term (how much of the incoming direction is
blocked by neighbouring facets); `G2` is the *joint* incoming-and-outgoing
masking term. Their ratio, `G2/G1`, captures how much *additional*
shadowing/masking applies specifically to the chosen outgoing direction
— multiplied by Fresnel `F` for how much of that light actually reflects
rather than refracts. This formula is exactly why VNDF sampling
(`sample_visible=True`) was worth using in the first place — the
alternative (naive GGX sampling) doesn't collapse this cleanly and
carries noticeably higher variance.

---

## 6. Diffuse Sampling

```python
wo_diff = mi.warp.square_to_cosine_hemisphere(sample2)
cos_mi_diff = dr.dot(si.wi, dr.normalize(si.wi + wo_diff))
F_diff = self.fresnel_schlick(dr.maximum(cos_mi_diff, 0))
weight_diff = self.base_colour * (1 - F_diff) * (1 - self.metallic)
```

### Diffuse Lambertian Lobe

The diffuse lobe models light that has entered the material, scattered
around internally, and re-emerged in a direction essentially unrelated
to where it came from — the defining behaviour of non-metals (section
2). Because the outgoing direction carries no memory of the incoming
one, a Lambertian surface reflects light *equally in all directions*
(before accounting for the angle it left at) — this is what makes it
"diffuse" rather than glossy.

### Lambert's cosine law (why we need `cos_theta`)

A flat beam of light hitting a surface at a steep angle spreads its
energy over a *larger* patch of surface than the same beam hitting
straight-on — the energy per unit area drops off proportionally to the
cosine of the angle of incidence. This is Lambert's cosine law, and it's
why a diffuse BRDF's contribution to the rendering equation always
carries an explicit `cos_theta_o` factor (visible in `eval()`, section
9) — it's not a property of the material, it's basic geometry of how
light spreads over a surface at an angle.

`mi.warp.square_to_cosine_hemisphere` samples directions so that this
`cos_theta_o` factor is already baked into *how often* a direction gets
picked (steep, grazing directions are sampled less often) — which is
why, in the weight formula, the `cos_theta_o` term and the sampling PDF's
own `cos_theta_o` term cancel out algebraically, leaving
`weight_diff` as simply `base_colour * (1 - F) * (1 - metallic)` with no
explicit cosine term visible in the code at all. This is what the "cos
terms cancel with pdf" comment is referring to.

Every diffuse sample also loses a little energy to Fresnel — even a
matte, non-metallic surface reflects *some* light specularly at grazing
angles (`F_diff`), so what's left over for the diffuse lobe is
`(1 - F_diff)`. And, matching section 2, diffuse only exists at all for
non-metals, hence the `(1 - metallic)` factor.

---

## 7. Lobe Selection

```python
use_spec = sample_specular & valid_spec
bs.wo = dr.select(use_spec, wo_spec, wo_diff)
bs.eta = 1.0
bs.sampled_component = dr.select(use_spec, mi.UInt32(1), mi.UInt32(0))
bs.sampled_type = dr.select(use_spec,
    mi.UInt32(+mi.BSDFFlags.GlossyReflection),
    mi.UInt32(+mi.BSDFFlags.DiffuseReflection))
```

`use_spec` requires **both** that specular was the coin-flip choice
*and* that the VNDF sample actually produced a valid direction — either
condition failing sends the sample down the diffuse-shaped output
instead (though see `weight`, section 8, for why that doesn't mean it
contributes as a diffuse sample).

`bs.sampled_component` reports which entry of `m_components` (section 2)
this sample came from — `1` for the glossy/specular lobe, `0` for
diffuse. This is metadata for anything downstream that wants to query
per-lobe contributions (e.g. AOVs); this integrator doesn't currently
read it itself.

---

## 8. Weight — Combining the Two Lobes

```python
weight = dr.select(use_spec, weight_spec,
         dr.select(~sample_specular, weight_diff, mi.Color3f(0)))
```

Three distinct outcomes collapse into one line:

- **Specular attempted and valid** → `weight_spec`.
- **Diffuse was the coin-flip choice from the start** → `weight_diff`.
- **Specular was attempted but produced an invalid direction** → `0`,
  explicitly — *not* a fallback to `weight_diff`. This was a deliberate
  fix: falling back to a diffuse-shaped weight here would make the
  sampling statistically inconsistent with what the PDF (section 9)
  actually reports for that outcome. Returning zero instead means a
  failed specular attempt simply contributes nothing to that path — the
  energy is genuinely lost (tying back to section 5's explanation of
  where the documented GGX energy loss actually comes from).

---

## 9. PDF for MIS — `bs.pdf`

```python
cos_theta_o = mi.Frame3f.cos_theta(bs.wo)
h = dr.normalize(si.wi + bs.wo)
cos_theta_i_val = dr.maximum(cos_theta_i, 1e-7)
spec_pdf = dr.maximum(distr.eval(h) * distr.smith_g1(wi_hat, h) / (4 * cos_theta_i_val), 0)
diff_pdf = mi.warp.square_to_cosine_hemisphere_pdf(bs.wo)
bs.pdf = spec_prob * spec_pdf + (1 - spec_prob) * diff_pdf
```

This reports how likely `sample()` was to produce the direction it just
returned (`bs.wo`) — used by the path tracer as `prev_bsdf_pdf` for MIS
weighting on the *next* bounce (`path_tracer_concepts.md`, section 6).

Because two techniques (specular VNDF sampling, diffuse cosine-hemisphere
sampling) can both potentially produce the *same* direction, the correct
combined density is the full **mixture**: `spec_prob * spec_pdf(wo) + (1
- spec_prob) * diff_pdf(wo)` — regardless of which technique actually
produced this particular `bs.wo`. This holds for a genuine mixture
distribution: the density function doesn't depend on which internal
mechanism generated a given sample.

> **Debugging note — a real bug found and fixed.** Earlier versions of
> this code computed `spec_pdf` using `m` — the microfacet normal from
> the *specular attempt* — and only added the `spec_prob * spec_pdf` term
> when `use_spec` was true, via a branch. That's fine when specular
> succeeds (`m` and `h` are provably identical there, by the mirror-
> reflection identity), but wrong whenever the diffuse lobe was actually
> chosen: `m` then refers to an unrelated, discarded direction, and the
> branch meant the specular contribution was silently dropped from the
> reported PDF entirely for those samples. Verified by cross-checking
> `sample()`'s reported `bs.pdf` against an independent call to `pdf()`
> for the same direction — about 20% of samples disagreed by more than
> 5% before the fix, zero after. The fix: always use `h` (the half-vector
> of whatever direction was actually returned, computed fresh right
> above), and always apply the full mixture formula unconditionally, no
> branch.

---

## 10. `fresnel_schlick()`

### Fresnel blending

Fresnel blending blends the specular and diffuse terms so that specular
reflection becomes more dominant at grazing angles, and less dominant
at normal incidence:

- **Controls the specular/diffuse split** — at grazing angles, more
  light reflects as specular; at normal incidence, more goes to diffuse.
- **Ensures energy conservation** — energy that goes into specular comes
  out of diffuse; together they must sum to `1.0` or less.

The Schlick approximation:
```
F(cos_theta) = F0 + (1 - F0) * (1 - cos_theta)^5
```

`F0` is the reflectance at normal incidence (straight-on). For
dielectrics (plastic, wood, skin), `F0` is around `0.04`. For metals,
`F0` is the base colour itself — which is why metals look coloured in
their reflections, and why `metallic` blends between the two:

```python
f0 = f0_dielectric * (1 - self.metallic) + self.base_colour * self.metallic
```

- `metallic = 0` → dielectric, `F0 = 0.04`
- `metallic = 1` → conductor, `F0 = base_colour`

---

## 11. `eval()`

```python
h = dr.normalize(si.wi + wo)
cos_theta_h = dr.dot(si.wi, h)
F = self.fresnel_schlick(cos_theta_h)

diffuse = self.base_colour * dr.inv_pi * cos_theta_o * (1 - F) * (1 - self.metallic)
specular = self.eval_specular(si, wo, active) * F
```

Where `sample()` *picks* a direction, `eval()` is asked "given this
specific `wo` I already have in mind (usually from NEE, section 7 of
`path_tracer_concepts.md`), how much light actually reflects that way?"

The diffuse term is Lambert's law (section 6) — `base_colour * inv_pi *
cos_theta_o` — reduced by however much Fresnel routes into specular
instead (`1 - F`), and zeroed for metals (`1 - metallic`). The specular
term reuses `eval_specular()` (section 12) for the shape of the GGX lobe,
scaled by Fresnel. The two lobes are simply added — this is why they
each need to individually respect energy conservation, so their sum
still can't exceed the incoming light.

---

## 12. `eval_specular()`

```python
D = distr.eval(h)
G = distr.G(si.wi, wo, h)
specular = D * G / (4.0 * dr.maximum(cos_theta_i * cos_theta_o, 1e-7))
```

The Cook-Torrance microfacet BRDF, without the Fresnel term (added
separately in `eval()`, since Fresnel depends on the specific direction
being evaluated, not just the material):
```
f_specular = (D * G) / (4 * cos_theta_i * cos_theta_o)
```
`D` (how many microfacets point towards the halfway vector, section 5)
and `G` (how much they shadow/mask each other, using the *joint*
incoming-and-outgoing term this time, not the single-direction `G1` used
during sampling) combine with the `4 * cos_i * cos_o` normalisation
factor that comes from the change of variables between microfacet-normal
space and outgoing-direction space.

---

## 13. `pdf()` — Standalone

```python
wi_hat = dr.mulsign(si.wi, cos_theta_i)
h = dr.normalize(si.wi + wo)
spec_pdf = dr.maximum(distr.eval(h) * distr.smith_g1(wi_hat, h) / (4 * cos_theta_i_val), 0)
diff_pdf = mi.warp.square_to_cosine_hemisphere_pdf(wo)
pdf_val = spec_prob * spec_pdf + (1 - spec_prob) * diff_pdf
```

The same mixture-density formula as `bs.pdf` (section 9), but for an
*arbitrary* queried `wo` rather than one `sample()` just produced —
called directly by NEE (`path_tracer_concepts.md`, section 7) to weight
the light-sampling contribution against this BSDF's own sampling
strategy.

> **Debugging note — a second bug, found and fixed.** This function
> previously multiplied `diff_pdf` by an extra `(1 - self.metallic)`
> factor that `sample()`'s version never had. A PDF has to be purely a
> property of the *sampling technique's geometry* — cosine-hemisphere
> sampling is always `cos_theta_o / π`, regardless of what material it's
> attached to. "How much weight the diffuse lobe gets overall" is a
> separate question, already answered by `spec_prob` (section 3), which
> is itself already `metallic`-dependent — so this extra factor was
> applying the same scaling a second time. It was inert at `metallic = 0`
> and `metallic = 1` (multiplying by exactly `1` or `0`), which is why it
> survived unnoticed through every existing validation config — all of
> which happened to sit at one of those two endpoints. Verified with a
> new intermediate test case (`roughness=0.4, metallic=0.5`): removing
> the factor took `bs.pdf` vs. independently-computed `pdf(wo)` from a
> 14% average mismatch to exact agreement.

---

## 14. `eval_pdf()`, `traverse()`, `to_string()`

```python
def eval_pdf(self, ctx, si, wo, active=True):
    return self.eval(ctx, si, wo, active), self.pdf(ctx, si, wo, active)
```

A convenience function bundling `eval()` and `pdf()` together — some
integrators call both at once and this saves recomputing shared setup
work internally (Mitsuba may optimise this pairing at the C++ level even
though this Python implementation just calls both in sequence).

`traverse()` is required by the `mi.BSDF` interface for exposing
differentiable parameters to Mitsuba's optimisation/differentiation
system — left empty here since this project doesn't use inverse
rendering or parameter optimisation.

`to_string()` is just a human-readable debug representation, shown when
printing a scene or BSDF object.
