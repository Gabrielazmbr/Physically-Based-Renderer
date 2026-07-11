
# GGX Specular
At a microscopic level, no surface is perfectly flat. Even a surface 
that looks smooth to the eye is covered in tiny facets, microscopic 
bumps and grooves pointing in slightly different directions.

A mirror has facets that are all perfectly aligned as they all point
the same direction, so all light reflects in exactly one direction. 
A rough surface has facets pointing in many different directions, 
so light scatters broadly. A glossy surface is somewhere between. Most 
facets are roughly aligned but with some variation.

GGX (also called Trowbridge-Reitz) is a mathematical distribution that
describes how these microfacets are oriented. It takes a roughness 
parameter: at roughness 0 all facets are perfectly aligned (mirror), 
at roughness 1 they point in random directions (diffuse-like). The 
distribution is bell-shaped around the surface normal, but GGX has longer
tails than older distributions like Beckmann, meaning there are more 
facets at extreme angles, which produces the characteristic bright 
elongated highlights you see on metals and plastics in production renders.


D : the distribution function — GGX itself. How many facets are oriented 
towards the halfway vector between incoming and outgoing light.

G : the geometric term — accounts for facets shadowing and masking each 
other at grazing angles.

F : Fresnel term — how much light reflects versus refracts at each facet,
based on the viewing angle.

The full specular BSDF is:
```
f_specular = (D * G * F) / (4 * cos_theta_i * cos_theta_o)
```

## The halfway vector

The halfway vector (also called the half vector) sits exactly between
the incoming and outgoing directions. It points in the direction a 
microfacet would need to be oriented to reflect light from the incoming 
direction towards the outgoing direction.

GGX uses it because instead of asking "how much light goes from direction 
A to direction B", it asks "how many microfacets are oriented towards the
halfway vector between A and B", because those are the only facets that 
contribute to that specific reflection. The distribution D(h) answers that
question.

```
h = dr.normalize(si.wi + wo)  # halfway vector
```

## Fresnel blending

Fresnel blending is used to blend the specular reflection term with the diffuse
term, so that the specular reflection is only visible at grazing angles 
(i.e. when the viewing angle is close to the surface normal).

- Controls the specular/diffuse split — at grazing angles more light reflects
 as specular, less as diffuse. At normal incidence less reflects as specular, 
 more as diffuse.
- Ensures energy conservation — the energy that goes into specular comes out
 of diffuse. They must sum to 1.0 or less.

The Schlick approximation for Fresnel is:

```
F(cos_theta) = F0 + (1 - F0) * (1 - cos_theta)^5
```

Where F0 is the reflectance at normal incidence (straight on). For dielectrics
(plastic, wood, skin) F0 is around 0.04. For metals F0 is the base colour itself
which is why metals look coloured in their reflections.

This is where metallic comes in. It blends between two behaviours:
- metallic = 0 → dielectric, F0 = 0.04
- metallic = 1 → conductor, F0 = base_colour

---
