# Path Tracer Concepts

A reference document covering the core concepts behind the custom path tracing
integrator implemented in this project.

---

# How the Path Tracer Works

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

---

# Dr.Jit Vectorisation

Dr.Jit is a JIT (Just-In-Time) compiler that transforms Python rendering code
into native CPU or GPU kernels. In path tracing we deal with millions of rays
per render, processing them one at a time in a Python loop would be unusably
slow because Python has significant overhead per operation and cannot leverage
the parallel processing capabilities of modern hardware.

Instead of looping, Dr.Jit represents all rays simultaneously as arrays and
compiles the operations on those arrays into a single native kernel that runs
on all rays in parallel. The Python code executes once to describe the
computation, and the compiled kernel does the actual work at native speed.

## Example

In a 512×512 render with 128 samples per pixel, we have 33 million rays.
Instead of:

```python
for ray in rays:  # 33 million Python iterations
    if hit:
        colour = brightness
    else:
        colour = 0
```

We write:

```python
colour = dr.select(active, brightness, mi.Float(0))  # runs once, processes all 33M rays
```

Dr.Jit compiles the `dr.select` call into a kernel that evaluates all rays
simultaneously.

---

# Active Mask

Because all rays live in the same array, rays cannot be removed when they die,
that would change the array size and break vectorisation. Instead, Dr.Jit
uses a boolean array called `active` that tracks which rays are still alive.
Operations check this mask and only apply to rays where `active` is True. Dead
rays stay in the array but are effectively ignored.

## Example

```python
active = mi.Bool(True, False, True, False, True)
si = scene.ray_intersect(ray, active)  # only intersects rays 1, 3, 5
```

---

# dr.select()

`dr.select()` is Dr.Jit's replacement for Python `if` statements. It takes a
boolean condition array, a value to use where the condition is True, and a
value to use where it is False, and returns an array with the appropriate
value selected per element. Both outcomes are computed for all elements; the
condition picks between them.

## Example

```python
# Mirror surfaces keep full energy, diffuse surfaces absorb half
throughput = dr.select(is_mirror, mi.Float(1.0), mi.Float(0.5))
# Result: [1.0, 0.5, 1.0, 0.5, 1.0] for rays hitting [mirror, diffuse, mirror, diffuse, mirror]
```

---

# Throughput Accumulation

Throughput represents how much of a ray's original energy survives after each
bounce. It starts at 1.0 (full energy) and gets multiplied by the surface
reflectance at every bounce. When a ray reaches a light source, the accumulated
light contribution is `throughput × light radiance`, meaning bright paths
through reflective surfaces contribute more to the final pixel than dark paths
through absorbing surfaces.

## Example from experiment

```
Ray 4: throughput starts at 1.0
       → hits surface (×0.3) → throughput 0.3
       → hits light (×5.0)   → contributes 1.5 to pixel
```

After many bounces through dark surfaces, throughput approaches zero and the
ray contributes almost nothing.

---

# Russian Roulette

Russian roulette is a technique for terminating low-throughput rays
probabilistically without biasing the result. Once a ray's throughput drops
below a threshold, instead of always terminating it or always continuing it, a
random coin flip decides. The survival probability is proportional to the
throughput. Bright rays are likely to survive, dim rays are likely to die.
Crucially, surviving rays have their throughput divided by the survival
probability, which compensates mathematically and keeps the final image
unbiased.

## Example

A ray with throughput 0.1 has a 10% chance of surviving. If it survives:

```
throughput = 0.1 / 0.1 = 1.0
```

It carries the full weight of what it would have contributed, compensating for
all the rays that didn't make it. This saves significant computation, as rays
that would contribute almost nothing to the image are terminated early, and
their computational budget is effectively redistributed to rays that matter.

---

# Next Event Estimation (NEE)

NEE is a technique that explicitly connects every surface hit to the light
source, rather than hoping a randomly bounced ray eventually finds it. At every
surface intersection, a shadow ray is fired directly towards a sampled point on
the light. If nothing blocks it, the light contribution is accumulated. This
dramatically reduces noise because the direct lighting component is solved
deterministically at every bounce rather than by chance.

In code this is handled by `scene.sample_emitter_direction()`, which samples a
point on the light, checks visibility, and returns the incoming radiance and
direction. The BSDF is then evaluated in that direction to determine how much
of that light the surface actually reflects towards the camera.

Without NEE, a ray would need to randomly bounce its way to the light by
chance. In a small scene like the Cornell Box this might happen reasonably
often. In a large scene with a small light source, most rays would never find
it and the image would be almost entirely noise.

---

# Monte Carlo Integration

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

---

# PDF — Probability Density Function
When you randomly sample a direction, not all directions are equally likely to
be chosen. The PDF tells you how likely a particular direction was to be sampled.

If you're sampling directions towards a light source, directions pointing straight 
at the light have a high probability of being chosen. The PDF value for that direction 
is high. A direction pointing away from the light has a low probability — low PDF.

Why does this matter? Because in Monte Carlo integration, if you preferentially sample
certain directions more often, you need to divide by how often you sampled them to avoid
over-counting their contribution. That division by PDF is what keeps the result unbiased.

```
ds.pdf — how likely NEE was to pick that direction to the light
bsdf_sample.pdf — how likely the BSDF was to pick its bounce direction
```

---

# Multiple Importance Sampling (MIS)
MIS solves a sampling efficiency problem that arises when two valid strategies exist for 
finding light at a surface. Next Event Estimation (NEE) samples ray directions by explicitly
targeting the light source. BSDF sampling samples directions based on the probability 
distribution of how the surface material scatters light. Both strategies are mathematically
correct but each performs better in different situations. NEE works well for large diffuse
lights, BSDF sampling works better for small bright lights on glossy surfaces.

Rather than choosing one strategy over the other, MIS combines both simultaneously, weighting
each contribution by how well-suited that strategy was to sample that particular direction. 
A strategy that was highly likely to sample a given direction gets more weight; one that was
unlikely gets less. Both still contribute to the final result, just in different proportions 
depending on the situation.

The power heuristic implements this weighting by squaring each strategy's PDF before dividing:

```
weight_a = pdf_a² / (pdf_a² + pdf_b²)
```

Squaring makes the weights more decisive. If one strategy is clearly better suited for a direction,
it receives a proportionally larger share of the contribution. This reduces noise more effectively
than the basic balance heuristic which uses unsquared PDFs.

## The emitter hit problem
Without MIS on emitter hits, a render can show firefly artefacts which are isolated very bright 
pixels on glossy surfaces near small lights. This happens because NEE already accounts for the light
contribution with correct weighting, but when a BSDF-sampled ray accidentally hits the same light 
directly, that contribution gets added again without any weight. The fix tracks the previous bounce's
BSDF pdf across loop iterations and uses it to weight the emitter hit contribution, eliminating the 
double counting.

---

# Implementation Notes

- `@dr.syntax` decorator : required above `sample()` to compile the `while`
  loop into a Dr.Jit kernel. Without it, the loop runs as just Python.
- `ray = mi.Ray3f(ray)` : convert `RayDifferential3f` to `Ray3f` before the
  loop. Dr.Jit requires loop state variables to keep the same type across
  iterations.
- `si = dr.zeros(mi.SurfaceInteraction3f)` : initialise `si` before the loop
  so it exists in scope for the return statement.
- `bsdf_ctx = mi.BSDFContext()` : must be declared outside the loop. Dr.Jit
  treats variables created inside the loop as changing state, which causes
  errors.
- `si.emitter(scene).eval(si, active)` : adds contribution from directly
  visible emitters (the ceiling light). Without this line, the light source
  itself is invisible in the render.
