# Physical thin-lens camera

`physical_camera.py` implements the `physical_camera` Mitsuba sensor. It begins
with a perspective camera ray, intersects that ray with a chosen focal plane,
samples a point on a finite aperture, and redirects the ray from the aperture
sample toward the focal point.

## Projection and focus

The field of view defines the film-plane extent at unit distance. Horizontal
coordinates use the requested FOV directly and vertical coordinates are divided
by the film aspect ratio. This convention was validated against Mitsuba's
`perspective` sensor at zero aperture, including non-square images.

For a camera-space direction `d`, the focal-plane intersection is

```text
t_focus = focus_distance / d.z
focus_point = d * t_focus.
```

The final direction is the normalized vector from a sampled lens point to that
focus point. When the aperture radius is zero, every ray begins at the camera
origin and the model becomes pinhole-equivalent.

## Aperture sampling

Circular apertures use concentric disk sampling. With three or more aperture
blades, the regular polygon is divided into triangular wedges; one wedge and a
uniform point within it are sampled from the aperture sample. Polygon rotation
is expressed in degrees.

Small out-of-focus emitters reproduce the aperture outline, which is why the
dedicated `bokeh` scene is a better aperture-shape demonstration than ordinary
diffuse spheres.

## Controls

| Property | Default | Purpose |
| --- | ---: | --- |
| `fov` | `60` | Horizontal field of view in degrees |
| `aperture_radius` | `0` | Lens radius; zero selects pinhole-equivalent projection |
| `focus_distance` | `1` | Camera-space focal-plane distance |
| `aperture_blades` | `0` | Circular below 3; otherwise a regular polygon |
| `aperture_rotation` | `0` | Polygon rotation in degrees |

## Validation and limitations

Section 5.4 checks aperture-zero projection equivalence, focal-plane behaviour,
and circular versus six-blade bokeh:

- [`tests/evaluation/features`](../tests/evaluation/features/README.md)

The implementation does not currently generate ray differentials, simulate
lens aberrations, model cat-eye vignetting, or expose a physical focal-length
and sensor-size pair. It is a controlled thin-lens model rather than a full
optical system.
