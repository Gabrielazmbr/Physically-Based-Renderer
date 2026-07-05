#!/usr/bin/env -S uv run --script

import drjit as dr
import mitsuba as mi

## Official documentation
"""
Mitsuba 3 Custom Python Plugin tutorial:
https://mitsuba.readthedocs.io/en/stable/src/others/custom_plugin.html

Mitsuba's own path tracer (`path.py`):
https://github.com/mitsuba-renderer/mitsuba3/blob/master/src/integrators/path.py
"""


mi.set_variant("llvm_ad_rgb")

# ───────────────────────────────────────────────────────────────────────────
# Custom Integrator
# Integrator that returns surface normals as colour using a plugin system.
# ───────────────────────────────────────────────────────────────────────────


class NormalIntegrator(mi.SamplingIntegrator):
    """
    Custom integrator written in Python.
    Visualises surface normals as RGB colour.
    mi.SamplingIntegrator is subclassable in Python.
    """

    def __init__(self, props):
        super().__init__(props)

    def sample(self, scene, sampler, ray, medium=None, active=True):
        # Intersect the ray with the scene
        si = scene.ray_intersect(ray, active)

        # Convert normal from [-1,1] to [0,1] range for display
        normal_colour = (si.n + 1.0) * 0.5

        # Return colour where ray hit something, black where it didn't
        result = dr.select(si.is_valid(), mi.Color3f(normal_colour), mi.Color3f(0))

        return result, si.is_valid(), []

    def aov_names(self):
        return []

    def to_string(self):
        return "NormalIntegrator[]"


mi.register_integrator("normal_integrator", lambda props: NormalIntegrator(props))
print("✓ Custom integrator registered (pure Python)")


# ─────────────────────────────────────────────
# Custom BSDF
# ─────────────────────────────────────────────


class TintedDiffuseBSDF(mi.BSDF):
    """
    Custom BSDF written in Python.
    A Lambertian diffuse material with a configurable tint colour.
    mi.BSDF is subclassable in Python.
    """

    def __init__(self, props):
        mi.BSDF.__init__(self, props)

        # Read tint colour from scene dict, default to orange
        self.tint = mi.Color3f(
            props.get("tint_r", 0.8), props.get("tint_g", 0.4), props.get("tint_b", 0.1)
        )

        # Set BSDF flags — this surface scatters light diffusely
        # on the front face only
        self.m_flags = mi.BSDFFlags.DiffuseReflection | mi.BSDFFlags.FrontSide
        self.m_components = [self.m_flags]

    def sample(self, ctx, si, sample1, sample2, active):
        # Sample a cosine-weighted direction on the hemisphere
        cos_theta_i = mi.Frame3f.cos_theta(si.wi)

        bs = mi.BSDFSample3f()
        bs.wo = mi.warp.square_to_cosine_hemisphere(sample2)
        bs.pdf = mi.warp.square_to_cosine_hemisphere_pdf(bs.wo)
        bs.eta = 1.0
        bs.sampled_type = +mi.BSDFFlags.DiffuseReflection
        bs.sampled_component = mi.UInt32(0)

        # BSDF value: tint colour divided by pi (energy conserving Lambertian)
        value = self.tint * dr.inv_pi * dr.maximum(cos_theta_i, 0)

        return bs, dr.select(active & (cos_theta_i > 0), value, mi.Color3f(0))

    def eval(self, ctx, si, wo, active):
        cos_theta_i = mi.Frame3f.cos_theta(si.wi)
        cos_theta_o = mi.Frame3f.cos_theta(wo)
        return dr.select(
            active & (cos_theta_i > 0) & (cos_theta_o > 0),
            self.tint * dr.inv_pi,
            mi.Color3f(0),
        )

    def pdf(self, ctx, si, wo, active):
        cos_theta_o = mi.Frame3f.cos_theta(wo)
        return dr.select(
            active & (cos_theta_o > 0),
            mi.warp.square_to_cosine_hemisphere_pdf(wo),
            mi.Float(0),
        )

    def eval_pdf(self, ctx, si, wo, active):
        return self.eval(ctx, si, wo, active), self.pdf(ctx, si, wo, active)

    def traverse(self, callback):
        pass

    def to_string(self):
        return f"TintedDiffuseBSDF[tint={self.tint}]"


mi.register_bsdf("tinted_diffuse", lambda props: TintedDiffuseBSDF(props))
print("✓ Custom BSDF registered (pure Python)")


# ─────────────────────────────────────────────
# Render using both custom plugins
# This scene uses the Python integrator and
# Python BSDF together.
# ─────────────────────────────────────────────

scene_dict = {
    "type": "scene",
    # Custom Python integrator
    "integrator": {"type": "normal_integrator"},
    # Camera
    "sensor": {
        "type": "perspective",
        "fov": 45,
        "to_world": mi.ScalarTransform4f().look_at(
            origin=[0, 0, 10], target=[0, 0, 0], up=[0, 1, 0]
        ),
        "film": {
            "type": "hdrfilm",
            "width": 512,
            "height": 512,
            "pixel_format": "rgb",
            "component_format": "float32",
            "rfilter": {"type": "gaussian"},
        },
        "sampler": {"type": "independent", "sample_count": 64},
    },
    # Light
    "light": {
        "type": "constant",
        "radiance": {"type": "rgb", "value": [1.0, 1.0, 1.0]},
    },
    # Sphere using custom BSDF
    "sphere": {
        "type": "sphere",
        "radius": 1.0,
        "bsdf": {"type": "tinted_diffuse", "tint_r": 0.8, "tint_g": 0.3, "tint_b": 0.1},
    },
    # Ground plane using BSDF with different tint
    "floor": {
        "type": "rectangle",
        "to_world": mi.ScalarTransform4f()
        .scale([3, 3, 1])
        .translate([0, -1, 0])
        .rotate([1, 0, 0], 90),
        "bsdf": {"type": "tinted_diffuse", "tint_r": 0.2, "tint_g": 0.4, "tint_b": 0.7},
    },
}


scene = mi.load_dict(scene_dict)
img = mi.render(scene)
mi.Bitmap(img).write("concept_test.exr")
print("Output saved to concept_test.exr")
