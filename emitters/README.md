# HDR environment emitter

`envmap.py` implements the `custom_envmap` Mitsuba emitter used for image-based
lighting (IBL). An HDR panorama supplies radiance from every direction around
the scene. The implementation supports direct lookup, emitter-direction
sampling, the matching PDF required by MIS, environment rotation, and a
uniform-sphere control used by the evaluation suite.

## Direction and texture mapping

World-space directions are transformed into the environment's local frame and
mapped to longitude/latitude UV coordinates. Texture lookup uses the full HDR
image in linear RGB. The inverse mapping converts sampled UV cells back into
world-space directions, including the configured `to_world` rotation.

For latitude-longitude maps, equal UV areas do not represent equal solid
angles. The spherical surface element contributes `sin(theta)`, so the
importance table is constructed from

```text
weight(u, v) = luminance(u, v) sin(theta)
```

and the discrete cell probability is converted to a density per steradian:

```text
pdf_omega = pdf_cell * width * height / (2 pi^2 sin(theta)).
```

The same conversion appears in both `sample_direction()` and
`pdf_direction()`; agreement between those functions is required for correct
multiple importance sampling.

## Sampling controls

| Property | Default | Purpose |
| --- | ---: | --- |
| `filename` | required | Linear HDR panorama |
| `scale` | `1.0` | Radiance multiplier |
| `importance` | `true` | Luminance importance sampling; `false` is the uniform control |
| `mis_compensation` | `true` | Mean-subtracted sampling weights for above-average regions |
| `cdf_res_x` | `512` | Importance-table width |
| `cdf_res_y` | `256` | Importance-table height |
| `cdf_pooling` | `max` | `max` or `mean` downsampling of HDR blocks |
| `to_world` | identity | Environment orientation |

The full-resolution texture is always used for radiance evaluation. CDF
resolution changes only the proposal distribution.

## Scene scale

The emitter represents a source at infinity but Mitsuba direction samples still
need a finite endpoint for visibility rays. The implementation begins with a
large safe radius and `set_scene()` may only increase it. This prevents the
historical production-scale shadow-ray truncation documented in Section 5.6.

## Validation and limitations

The canonical sampling evaluation compares uniform and importance sampling
over repeated seeds, checks matched means, measures regional variance, sweeps
CDF construction, and evaluates the implemented MIS-compensation heuristic:

- [`tests/evaluation/sampling`](../tests/evaluation/sampling/README.md)
- [`tests/evaluation/scale_failure`](../tests/evaluation/scale_failure/README.md)

The mean-subtraction option is an implemented heuristic rather than the full
analytic MIS-compensation method from the literature. Its measured behaviour is
reported explicitly instead of being presented as a general optimum.
