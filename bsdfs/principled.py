import drjit as dr
import mitsuba as mi


class PrincipledBSDF(mi.BSDF):
    def __init__(self, props):
        mi.BSDF.__init__(self, props)

        self.base_colour = mi.Color3f(
            props.get(
                "base_colour",
                mi.Color3f(
                    1.0,
                ),
            )
        )
        self.roughness = props.get("roughness", 0.0)
        self.metallic = props.get("metallic", 0.0)

        # Flags: Diffuse reflection, glossy reflection, front side only
        self.m_flags = (
            mi.BSDFFlags.DiffuseReflection
            | mi.BSDFFlags.GlossyReflection
            | mi.BSDFFlags.FrontSide
        )
        # Component flags: Diffuse reflection on front side, glossy reflection on front side
        self.m_components = [
            mi.BSDFFlags.DiffuseReflection | mi.BSDFFlags.FrontSide,
            mi.BSDFFlags.GlossyReflection | mi.BSDFFlags.FrontSide,
        ]

    def sample(self, ctx, si, sample1, sample2, active):
        # Sample a cosine-weighted direction on the hemisphere
        cos_theta_i = mi.Frame3f.cos_theta(si.wi)

        bs = mi.BSDFSample3f()
        bs.wo = mi.warp.square_to_cosine_hemisphere(sample2)
        bs.pdf = mi.warp.square_to_cosine_hemisphere_pdf(bs.wo)
        bs.eta = 1.0
        bs.sampled_type = +mi.BSDFFlags.DiffuseReflection
        bs.sampled_component = mi.UInt32(0)

        value = self.base_colour

        return bs, dr.select(active & (cos_theta_i > 0), value, mi.Color3f(0))

    def fresnel_schlick(self, cos_theta):
        # F0 blended by metallic parameter
        f0_dielectric = mi.Color3f(0.04)
        f0 = f0_dielectric * (1 - self.metallic) + self.base_colour * self.metallic
        return f0 + (1 - f0) * dr.power(dr.maximum(1 - cos_theta, 0), 5)

    def eval(self, ctx, si, wo, active):
        cos_theta_i = mi.Frame3f.cos_theta(si.wi)
        cos_theta_o = mi.Frame3f.cos_theta(wo)
        h = dr.normalize(si.wi + wo)
        cos_theta_h = dr.dot(si.wi, h)

        # Fresnel term
        F = self.fresnel_schlick(cos_theta_h)

        # Diffuse lobe
        diffuse = (
            self.base_colour * dr.inv_pi * cos_theta_o * (1 - F) * (1 - self.metallic)
        )

        # Specular lobe
        specular = self.eval_specular(si, wo, active) * F

        return dr.select(
            active & (cos_theta_i > 0) & (cos_theta_o > 0),
            diffuse + specular,
            mi.Color3f(0),
        )

    def eval_specular(self, si, wo, active):
        # Halfway vector
        h = dr.normalize(si.wi + wo)

        cos_theta_i = mi.Frame3f.cos_theta(si.wi)
        cos_theta_o = mi.Frame3f.cos_theta(wo)

        # GGX microfacet distribution
        alpha = dr.maximum(self.roughness * self.roughness, 1e-4)
        distr = mi.MicrofacetDistribution(
            mi.MicrofacetType.GGX, alpha, sample_visible=True
        )

        # D — microfacet distribution
        D = distr.eval(h)

        # G — shadowing masking term
        G = distr.G(si.wi, wo, h)

        # Specular value
        specular = D * G / (4.0 * cos_theta_i)

        return dr.select(
            active & (cos_theta_i > 0) & (cos_theta_o > 0),
            mi.Color3f(specular),
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
        return f"PrincipledBSDF[base_colour={self.base_colour}, roughness={self.roughness}, metallic={self.metallic}]"


mi.register_bsdf("PrincipledBSDF", lambda props: PrincipledBSDF(props))
print("Principled BSDF registered")
