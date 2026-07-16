# Path Tracer Concepts

A reference document covering the core concepts behind the custom path
tracing integrator, organised to follow the order the code itself is read:
class definition first, then the `sample()` signature, then straight down
the loop, step by step.

---

## 1. Overview

### How the path tracer works

Rays are shot from the camera into the scene, each carrying a throughput value
of 1.0 representing full energy. On the first bounce, rays that hit a surface
trigger two things simultaneously. First, Next Event Estimation (NEE) fires a
shadow ray from that surface point directly towards the light source,
accumulating direct light contribution weighted by the surface's BSDF (Bidirectional
Scattering Distribution Function) which meanshow much the material reflects light 
in that direction. Second, the BSDF samples a new direction for the ray to continue 
travelling, spawning a secondary ray for the next bounce.

On each subsequent bounce, the same process repeats from the new surface
intersection point. The ray arrives carrying whatever throughput survived from
previous bounces, NEE fires another shadow ray to the light, and the BSDF
spawns another ray in a new direction. Each bounce multiplies the throughput by
the BSDF weight, which represents how much energy the surface reflects. Dark
or absorbing surfaces reduce throughput significantly, while highly reflective
surfaces preserve it.

After the third bounce, Russian roulette probabilistic termination activates.
Rather than always continuing or always terminating low-energy rays, a random
test decides. The survival probability is proportional to the ray's remaining
throughput as weaker rays are more likely to be terminated. Rays that survive
are compensated by dividing their throughput by the survival probability, which
mathematically offsets the terminated rays and keeps the final result unbiased.
A ray that had a 10% chance of surviving but did survive effectively carries
ten times the weight, accounting for the nine equivalent rays that didn't make
it.

Pixel colour is determined by Monte Carlo integration, firing multiple rays
per pixel and averaging their contributions. Monte Carlo works by randomly
sampling directions rather than exhaustively evaluating every possible light
path, which would be computationally infinite. As sample count increases, the
estimate converges towards the correct solution. Noise decreases at a rate 
proportional to 1/√n, where n is the number of samples. Quadrupling the sample
count halves the noise.


### Monte Carlo Integration

Rendering equation:

```
Lo = Le + ∫ fr * Li cosθdω
```

Monte Carlo integration is the mathematical foundation of path tracing. The
rendering equation which describes how light distributes in a scene is an
integral over all possible incoming directions at every surface point. This
integral has no closed form solution for complex scenes.

Monte Carlo solves it by randomly sampling directions and averaging the
results. The key property is convergence — as sample count n increases, the
estimate approaches the correct solution. Noise decreases at a rate of 1/√n:

```
64 spp   → baseline noise
256 spp  → half the noise  (4× samples)
1024 spp → quarter noise   (16× samples)
```


### Dr.Jit vectorisation — how the loop actually runs

Dr.Jit is a JIT (Just-In-Time) compiler that transforms Python rendering
code into native CPU or GPU kernels. In path tracing we deal with millions
of rays per render; processing them one at a time in a Python loop would be
unusably slow, because Python has significant per-operation overhead and
cannot leverage the parallel processing capabilities of modern hardware.

Instead of looping, Dr.Jit represents all rays simultaneously as arrays and
compiles the operations on those arrays into a single native kernel that
runs on all rays in parallel. The Python code executes once to *describe*
the computation, and the compiled kernel does the actual work at native
speed.

```python
for ray in rays:              # 33 million Python iterations — slow
    colour = brightness if hit else 0
```
```python
colour = dr.select(active, brightness, mi.Float(0))  # runs once, all 33M rays
```

**The active mask.** Because all rays live in the same array, rays can't be
removed when they die — that would change the array size and break
vectorisation. Instead, a boolean array called `active` tracks which rays
are still alive; operations only apply where `active` is `True`, and dead
rays simply sit in the array being ignored.

**`dr.select()`** is Dr.Jit's replacement for Python `if` statements. It
takes a condition array plus a true-value and false-value, and returns the
appropriate value per element. Both outcomes are actually computed for
every element — the condition just picks between them afterward.

**`@dr.syntax`** is the decorator that makes a plain-looking Python
`while active:` loop compile into a vectorised Dr.Jit kernel. Without it,
the loop would just execute as ordinary, slow, non-vectorised Python.


### The loop:

```text
Camera Ray
    │
    ▼
Intersect Scene
    │
    ▼
If emitter hit → Add emitted radiance (MIS weighted)
    │
    ▼
Next Event Estimation (sample light)
    │
    ▼
Evaluate BSDF toward sampled light
    │
    ▼
Apply MIS
    │
    ▼
Sample BSDF
    │
    ▼
Update Throughput
    │
    ▼
Spawn Next Ray
    │
    ▼
Russian Roulette
    │
    ▼
Repeat until terminated
```


---

## 2. Class Definition — `__init__`

`PathTracer` subclasses `mi.SamplingIntegrator`, Mitsuba's base class for
any integrator that estimates radiance via Monte Carlo sampling. `props`
is Mitsuba's property container: whatever key/value pairs a scene
dictionary passes in under `"integrator": {"type": "path_tracer", ...}`
arrive here.

**Parameters read from `props`:**

- **`max_depth`** — the maximum number of bounces allowed for a ray before
  forced termination.
- **`rr_depth`** — the bounce number at which Russian roulette begins being
  considered (section 9). Set to 3 here: Russian roulette starts after
  bounce 3, not before, since early bounces usually still carry meaningful
  energy and terminating them early would just add noise for no speed
  benefit.

**SPP, max_depth, and the cost of a render** for a 1920 × 1080 image at
SPP = 64, max_depth = 8:

```
Resolution: 2.07 million pixels
SPP = 64
Max depth = 8

Approximately:
2.07 million pixels × 64 camera paths per pixel = 132 million paths

Each of those paths can bounce up to 8 times.

132 million paths × 8 bounces ≈ 1.06 billion ray-surface interactions
```

Many paths terminate earlier due to misses or Russian roulette, so the
final number is usually lower. This is the practical reason SPP and
max_depth are exposed as configurable parameters rather than hardcoded,
they're the two biggest levers on render time.


## 3. The `sample()` function

Every argument is handed in by Mitsuba's rendering pipeline, not
constructed by us:

- **`scene: mi.Scene`**:  the object graph holding all geometry, emitters,
  and their spatial acceleration structures.
- **`sampler: mi.Sampler`**: the random number generator. Every call to
  `sampler.next_1d()` / `next_2d()` draws a fresh random number, used to
  pick which light to sample, which direction to bounce, or whether a ray
  survives Russian roulette.
- **`ray: mi.RayDifferential3f`**: the camera ray(s) for this sample,
  batched across however many pixels/samples are being processed at once.
- **`medium: mi.Medium`**: Mitsuba's representation of participating
  media (smoke, fog, water) that scatter or absorb light as a ray passes
  through them. Defaults to `None` as this integrator doesn't currently
  handle volumetric media.
- **`active: mi.Bool`**: the mask (section 1) distinguishing rays still
  worth tracing from ones already known to be dead, ranging over the whole
  batch.

The return type, `tuple[mi.Color3f, mi.Bool, list]` (explained in section 10).

---

## 4. Initialisation — inside `sample()`, before the loop

``` python
ray = mi.Ray3f(ray)         throughput = mi.Color3f(1.0)
result = mi.Color3f(0.0)    depth = mi.UInt32(0)
active = mi.Bool(active)
```

- **`ray = mi.Ray3f(ray)`** — converts the incoming `RayDifferential3f` to
  a plain `Ray3f` before the loop starts. Dr.Jit requires loop state
  variables to keep the *same type* across every iteration, and the ray
  changes type as it gets re-spawned each bounce, so it's normalised here.
- **`throughput`** — rays' energy starts at 100%, multiplied down at every
  bounce (section 8).
- **`result`** — accumulated radiance. Starts at zero; every contribution
  throughout the loop adds to it.
- **`depth`** — counts bounces so far.

**Tracking the previous bounce, for MIS:**
``` python
prev_si = dr.zeros(mi.Interaction3f)
prev_bsdf_pdf = mi.Float(1.0)
prev_delta = mi.Bool(True)
```

`prev_si` stores the previous surface interaction, `prev_bsdf_pdf` stores
the probability of the previous BSDF sample, and `prev_delta` is a boolean
that tracks whether the previous bounce was a perfect specular event.

**Delta distributions :**  a delta distribution has zero probability
everywhere except at one (or a finite number of) exact direction. Perfect
mirrors and glass are delta events: there's no "roughly towards the
mirror", light either goes in the *one* reflected direction or it
doesn't. You can't meaningfully sample "towards" a delta event the normal
probabilistic way, which is why MIS treats delta events as a special case
later on (weight = 1, no blending — section 6) rather than running the
usual power heuristic.

**Environment light validity:**
``` python
valid_ray = mi.Bool(scene.environment() is not None)
```

If the scene has an environment light (an HDRI), rays that miss all
geometry are still valid as they pick up environment radiance instead of
returning black. This flag is initialised once here and updated as the
loop runs (section 5).

**Setting up before the loop starts:**
``` python
si = dr.zeros(mi.SurfaceInteraction3f)
bsdf_ctx = mi.BSDFContext()
```

`si` is initialised as a zeroed `SurfaceInteraction3f` *before* the loop so
it exists in scope even for the return statement, in case the loop never
runs. `bsdf_ctx` must be declared outside the loop. Dr.Jit treats
variables created *inside* the loop as changing per-iteration state.

**`mi.BSDFContext()`** carries the transport mode used when evaluating a
BSDF. Two transport modes exist: *radiance transport* (light → camera)
physically how light actually travels. And *importance transport* (camera
→ light) the direction path tracing actually simulates, tracing
backwards from the eye. The context also distinguishes reflection versus
transmission components. This integrator uses the default mode throughout.

---

## 5. Step 1 — Intersect Scene
``` python
si = scene.ray_intersect(ray, active)
```

Tests for an intersection and returns detailed information about where a
ray hits first. Internally, this queries a **BVH** (Bounding Volume
Hierarchy). A spatial acceleration structure that narrows down which
triangles/primitives are even worth testing, rather than checking the
ray against every primitive in the scene one by one.

The result, `si` (a `SurfaceInteraction3f`), retains everything needed
about that hit point: position, normal, UV coordinates, which BSDF is
attached, which emitter (if any) is attached, etc.

---

## 6. Step 2 — Emitter Hit (direct visibility of a light)
``` python
ds_emitter = mi.DirectionSample3f(scene, si, prev_si)
em_pdf = dr.select(~prev_delta, scene.pdf_emitter_direction(prev_si, ds_emitter, ~prev_delta), mi.Float(0))
mis_bsdf = dr.select(prev_delta, mi.Float(1), self.mis_weight(prev_bsdf_pdf, em_pdf))
result += throughput * si.emitter(scene).eval(si, active) * mis_bsdf
```

**`DirectionSample3f`** stores data describing the path from point A
(`prev_si`) to point B (`si`): the direction, the distance, the PDF, and
which emitter (if any) is involved.

`em_pdf` computes the emitter PDF for this direction, unless the previous
bounce was a delta event (in which case it's set to zero). This measures 
the probability ofhaving reached this point via *light sampling*, so it 
can be compared against the probability of having reached it via 
*BSDF sampling*.

`mis_bsdf` compares the BSDF-sampling PDF against the emitter PDF and
assigns the appropriate weight via the power heuristic (below) — unless the
previous bounce was delta, in which case the weight is simply 1 (no
blending needed).

Finally, `si.emitter(scene).eval(si, active)` adds the contribution of a
directly-visible emitter: energy lost along the path so far, times the
radiance of the emitter as seen from this surface, times the MIS weight.
Without this line, light sources would be invisible in the render; you'd
see their illumination on other objects but never the light itself.


### Multiple Importance Sampling (MIS)

MIS solves a sampling efficiency problem that arises when two valid
strategies exist for finding light at a surface. NEE (section 7) samples
directions by explicitly targeting the light. BSDF sampling (section 8)
samples directions based on how the surface material scatters light. Both
strategies are mathematically correct, but each performs better in
different situations — NEE works well for large diffuse lights, BSDF
sampling works better for small bright lights seen through glossy
surfaces.

Rather than choosing one strategy over the other, MIS combines both
simultaneously, weighting each contribution by how well-suited that
strategy was for sampling that particular direction. The power heuristic
implements this by squaring each strategy's PDF before dividing:

```
weight_a = pdf_a² / (pdf_a² + pdf_b²)
```

Squaring makes the weights more decisive: if one strategy was clearly
better suited for a direction, it receives a proportionally larger share
of the contribution. This reduces noise more effectively than the basic
balance heuristic, which uses unsquared PDFs.

**The emitter-hit problem.** Without MIS on emitter hits specifically, a
render can show firefly artefacts which consists of isolated, very bright
pixels on glossy surfaces near small lights. This happens because NEE 
already accounts for the light's contribution with correct weighting, 
but when a BSDF-sampled ray *also* happens to hit the same light directly,
that contribution gets added a second time with no weighting to compensate.
The fix tracks the previous bounce's BSDF PDF across loop iterations 
(`prev_bsdf_pdf`) and uses it to weight the emitter-hit contribution, 
eliminating the double-count.

---

## 7. Step 3 — Next Event Estimation (NEE)
``` python
bsdf = si.bsdf(ray)
active_em = active & (depth < self.max_depth)
ds, emitter_radiance = scene.sample_emitter_direction(si, sampler.next_2d(), True, active_em)
active_em &= ds.pdf > 0
wo = si.to_local(ds.d)
bsdf_val = bsdf.eval(bsdf_ctx, si, wo, active_em)
bsdf_pdf = bsdf.pdf(bsdf_ctx, si, wo, active_em)
mis_em = dr.select(ds.delta, mi.Float(1), self.mis_weight(ds.pdf, bsdf_pdf))
result += dr.select(active_em, throughput * bsdf_val * emitter_radiance * mis_em, mi.Color3f(0))
```

NEE is a technique that explicitly connects every surface hit to the light
source, rather than hoping a randomly bounced ray eventually finds it. At
every surface intersection, a shadow ray is fired directly towards a
sampled point on the light. If nothing blocks it, the light's contribution
is accumulated. This dramatically reduces noise, because the direct
lighting component is solved deterministically at every bounce rather than
left to chance.

`bsdf = si.bsdf(ray)` finds the material attached to the surface.
`scene.sample_emitter_direction()` samples a point on a light, checks
visibility, and returns the incoming radiance and direction (`ds`,
`emitter_radiance`). `active_em &= ds.pdf > 0` disables the NEE
contribution for any ray where no light could actually be reached.

`wo = si.to_local(ds.d)` transforms the sampled direction from world space
into the surface's local shading frame, since the BSDF needs to be
evaluated locally. `bsdf.eval()` then evaluates how much of that light the
surface reflects back towards the camera, and `bsdf.pdf()` computes the
probability that *BSDF sampling* would have picked this same direction,
needed for the MIS comparison below.

`mis_em` compares the emitter PDF against the BSDF PDF and weights
accordingly, unless the light itself is a delta light (weight = 1). The
final contribution is masked so that only rays which could actually reach
a light (`active_em`) add anything.

### PDF — Probability Density Function

When you randomly sample a direction, not all directions are equally
likely to be chosen. The PDF tells you how likely a particular direction
was to be sampled. Directions pointing straight at a light have a high
PDF; directions pointing away have a low one.

Why does this matter? In Monte Carlo integration, if you preferentially
sample certain directions more often, you need to divide by how often you
sampled them, to avoid over-counting their contribution. That division by
PDF is what keeps the result unbiased.

```
ds.pdf          — how likely NEE was to pick this direction to the light
bsdf_sample.pdf — how likely the BSDF was to pick its bounce direction
```

Without NEE, a ray would need to randomly bounce its way to the light by
chance. In a small scene like the Cornell Box this might happen reasonably
often; in a large scene with a small light source, most rays would never
find it and the image would be almost entirely noise.

---

## 8. Step 4 — BSDF Sampling (choosing the next direction)

BSDF sampling is the second of the two light-finding strategies mentioned
back in section 6's MIS explanation. Where NEE samples a direction by
looking at *where the lights are*, BSDF sampling does the opposite: it
samples a new direction based on the probability distribution defined by
the surface's own BSDF — how that material tends to scatter light. A
mirror-like surface will sample directions tightly clustered around the
perfect reflection; a rough diffuse surface will sample broadly across the
whole hemisphere.

This is also the mechanism that actually **extends the path** — every
bounce after the first only exists because BSDF sampling chose a direction
to continue into. NEE (section 7) only ever *looks toward* a light from
the current point; it never moves the path itself. BSDF sampling is what
decides where the ray goes next, bounce after bounce, until Russian
roulette or `max_depth` ends it.

The two strategies are complementary precisely because they're good at
different things: BSDF sampling is what lets the path ever reach small or
distant lights it wasn't deliberately aimed at (via the emitter-hit logic
in section 6), and it's the *only* way delta surfaces — mirrors, glass —
can ever find light at all, since a delta BSDF has exactly one valid
outgoing direction and NEE's shadow ray toward an arbitrary light almost
never lands on it.

``` python
bsdf_sample, bsdf_weight = bsdf.sample(bsdf_ctx, si, sampler.next_1d(), sampler.next_2d(), active)
throughput *= bsdf_weight
ray = si.spawn_ray(si.to_world(bsdf_sample.wo))
```

`bsdf.sample()` chooses an outgoing direction according to the surface's
properties, given a random number to choose *which* lobe/possibility and a
2D random number to choose the direction itself. It returns
`bsdf_sample` — retaining the outgoing direction `wo`, its PDF, and flags
describing what kind of event was sampled — and `bsdf_weight`, the
scattering event's contribution.

### Throughput accumulation

Throughput represents how much of a ray's original energy survives after
each bounce. It starts at 1.0 and gets multiplied by the surface
reflectance at every bounce. When a ray reaches a light source, the
accumulated light contribution is `throughput × light radiance` — bright
paths through reflective surfaces contribute more to the final pixel than
dark paths through absorbing surfaces.

**Example:**
Ray: throughput starts at 1.0
→ hits surface (×0.3) → throughput 0.3
→ hits light (×5.0)   → contributes 1.5 to pixel

After many bounces through dark surfaces, throughput approaches zero and
the ray contributes almost nothing.

### Spawning the next ray

`si.spawn_ray()` converts the sampled local-space direction back into
world space (`si.to_world`) and creates the next ray, offset slightly away
from the surface. This offset avoids **self-intersection**: without it,
floating-point rounding could cause the new ray to immediately re-hit the
same surface it just left, at distance ≈ 0, producing shadow-acne-like
artefacts or infinite loops.


---

## 9. Step 5 — Russian Roulette
``` python
rr_active = depth >= self.rr_depth
rr_prob = dr.minimum(dr.max(throughput), 0.95)
rr_continue = sampler.next_1d() < rr_prob
throughput[rr_active] *= dr.rcp(rr_prob)
active &= ~rr_active | rr_continue
active &= dr.max(throughput) > 0
```

Russian roulette is a technique for terminating low-throughput rays
probabilistically without biasing the result. Once a ray has bounced past
`rr_depth`, instead of always terminating it or always continuing it, a
random coin flip decides. The survival probability is proportional to the
remaining throughput (capped at 0.95) — bright rays are likely to survive,
dim rays are likely to die.

Crucially, surviving rays have their throughput divided by the survival
probability (`dr.rcp(rr_prob)`), which compensates mathematically and
keeps the final image unbiased.

**Example:** a ray with throughput 0.1 has a 10% chance of surviving. If it
survives:

```
throughput = 0.1 / 0.1 = 1.0
```

It carries the full weight of what it would have contributed, accounting
for the nine equivalent rays that didn't make it. This saves significant
computation, since rays that would contribute almost nothing to the image
are terminated early, and their computational budget is effectively
redistributed to rays that matter. The final line, `active &= dr.max(throughput) > 0`,
removes any ray whose energy has actually reached zero, roulette aside.

---

## 10. End of Bounce, Loop, and Return
``` python
prev_si = mi.Interaction3f(si)
prev_bsdf_pdf = bsdf_sample.pdf
prev_delta = mi.Bool(bsdf_sample.sampled_type & mi.UInt32(mi.BSDFFlags.Delta) != 0)
depth += 1
```

The current bounce's interaction, PDF, and delta status get carried
forward to be the *previous* bounce's data next iteration (used back in
section 6). Depth increments, and the loop repeats until every ray in the
batch is inactive.
return (dr.select(valid_ray, result, mi.Color3f(0)), valid_ray, [])

The return signature is `(radiance, valid_ray, aovs)`:

- **radiance** — the accumulated `result`, or black if the path never
  validly hit anything.
- **valid_ray** — whether the path contributed at all, used by the film
  for alpha/coverage.
- **AOVs (Arbitrary Output Variables)** — additional per-pixel data
  channels a renderer can output besides colour (e.g. depth, normals,
  albedo). This integrator returns none (`[]`).
