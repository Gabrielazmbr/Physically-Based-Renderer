# Dr.Jit Vectorisation
- Dr.Jit is a JIT (Just-In-Time) compiler that transforms Python rendering code into native CPU or GPU kernels. In path tracing we deal with millions of rays per render — processing them one at a time in a Python loop would be unusably slow because Python has significant overhead per operation and cannot leverage the parallel processing capabilities of modern hardware.

- Instead of looping, Dr.Jit represents all rays simultaneously as arrays and compiles the operations on those arrays into a single native kernel that runs on all rays in parallel. The Python code executes once to describe the computation — the compiled kernel does the actual work at native speed.
## Example: 
In a 512×512 render with 128 samples per pixel, we have 33 million rays. Instead of:
```python
for ray in rays:  # 33 million Python iterations
    if hit:
        colour = brightness
    else:
        colour = 0
```
We write:
```python
pythoncolour = dr.select(active, brightness, mi.Float(0))  # runs once, processes all 33M rays
```
Dr.Jit compiles the dr.select call into a kernel that evaluates all rays simultaneously.


# Active Mask
- Because all rays live in the same array, rays cannot be removed when they die — that would change the array size and break vectorisation. Instead, Dr.Jit uses a boolean array called active that tracks which rays are still alive. Operations check this mask and only apply to rays where active is True. Dead rays stay in the array but are effectively ignored.
## Example:
```python
active = mi.Bool(True, False, True, False, True)
si = scene.ray_intersect(ray, active)  # only intersects rays 1, 3, 5
```

# dr.select()
- `dr.select()` is Dr.Jit's replacement for Python if statements. It takes a boolean condition array, a value to use where the condition is True, and a value to use where it is False — and returns an array with the appropriate value selected per element. Both outcomes are computed for all elements; the condition picks between them.
```python
# Mirror surfaces keep full energy, diffuse surfaces absorb half
throughput = dr.select(is_mirror, mi.Float(1.0), mi.Float(0.5))
# Result: [1.0, 0.5, 1.0, 0.5, 1.0] for rays hitting [mirror, diffuse, mirror, diffuse, mirror]
```

# Throughput Accumulation
- Throughput represents how much of a ray's original energy survives after each bounce. It starts at 1.0 (full energy) and gets multiplied by the surface reflectance at every bounce. When a ray reaches a light source, the accumulated light contribution is throughput × light radiance, meaning bright paths through reflective surfaces contribute more to the final pixel than dark paths through absorbing surfaces.
## Example from experiment:
Ray 4: throughput starts at 1.0 → hits surface (×0.3) → throughput 0.3 → hits light (×5.0) → contributes 1.5 to pixel
After many bounces through dark surfaces, throughput approaches zero and the ray contributes almost nothing.

# Russian Roulette
- Russian roulette is a technique for terminating low-throughput rays probabilistically without biasing the result. Once a ray's throughput drops below a threshold, instead of always terminating it or always continuing it, a random coin flip decides. The survival probability is proportional to the throughput — bright rays are likely to survive, dim rays are likely to die. Crucially, surviving rays have their throughput divided by the survival probability, which compensates mathematically and keeps the final image unbiased.

## Example: 
A ray with throughput 0.1 has a 10% chance of surviving. If it survives, its throughput becomes 0.1 / 0.1 = 1.0 .
It carries the full weight of what it would have contributed, compensating for all the rays that didn't make it.

This saves significant computation — rays that would contribute almost nothing to the image are terminated early, and their computational budget is effectively redistributed to rays that matter.
