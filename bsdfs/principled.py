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

    def _spec_prob(self):
        # Metals should be specular
        return mi.Float(dr.clamp(self.metallic * 0.8 + 0.1, 0.1, 0.9))

    def sample(self, ctx, si, sample1, sample2, active=True):
        cos_theta_i = mi.Frame3f.cos_theta(si.wi)
        active = active & (cos_theta_i > 0)

        # Fresnel at normal incidence
        spec_prob = self._spec_prob()

        alpha = dr.maximum(self.roughness * self.roughness, 1e-4)
        distr = mi.MicrofacetDistribution(mi.MicrofacetType.GGX, alpha, sample_visible=True)

        bs = mi.BSDFSample3f()
        sample_specular = sample1 < spec_prob

        # ── Specular sampling ──
        wi_hat = dr.mulsign(si.wi, cos_theta_i)
        m, _ = distr.sample(wi_hat, sample2)
        wo_spec = mi.reflect(si.wi, m)
        valid_spec = (mi.Frame3f.cos_theta(wo_spec) > 0) & active

        # Specular weight
        cos_mi = dr.dot(si.wi, m)
        F = self.fresnel_schlick(cos_mi)
        G1 = distr.smith_g1(si.wi, m)
        G2 = distr.G(si.wi, wo_spec, m)
        weight_spec = dr.select(G1 > 0, F * G2 / G1, mi.Color3f(0))

        # ── Diffuse sampling ──
        wo_diff = mi.warp.square_to_cosine_hemisphere(sample2)
        # cos terms cancel with pdf
        cos_mi_diff = dr.dot(si.wi, dr.normalize(si.wi + wo_diff))
        F_diff = self.fresnel_schlick(dr.maximum(cos_mi_diff, 0))
        weight_diff = self.base_colour * (1 - F_diff) * (1 - self.metallic)

        # ── Select lobe ──
        use_spec = sample_specular & valid_spec
        bs.wo = dr.select(use_spec, wo_spec, wo_diff)
        bs.eta = 1.0
        bs.sampled_component = mi.UInt32(0)
        bs.sampled_type = dr.select(
            use_spec,
            mi.UInt32(+mi.BSDFFlags.GlossyReflection),
            mi.UInt32(+mi.BSDFFlags.DiffuseReflection)
        )

        # PDF for MIS
        cos_theta_o = mi.Frame3f.cos_theta(bs.wo)
        h = dr.normalize(si.wi + bs.wo)
        cos_h = dr.maximum(dr.dot(wi_hat, h), 1e-7)
        spec_pdf = dr.maximum(distr.pdf(wi_hat, h) / (4 * cos_h), 0)
        diff_pdf = mi.warp.square_to_cosine_hemisphere_pdf(bs.wo)
        bs.pdf = spec_prob * spec_pdf + (1 - spec_prob) * diff_pdf

        weight = dr.select(use_spec, weight_spec, weight_diff)

        return bs, dr.select(active & (cos_theta_o > 0), weight, mi.Color3f(0))

    def fresnel_schlick(self, cos_theta):
        # F0 blended by metallic parameter
        f0_dielectric = mi.Color3f(0.04)
        f0 = f0_dielectric * (1 - self.metallic) + self.base_colour * self.metallic
        return f0 + (1 - f0) * dr.power(dr.maximum(1 - cos_theta, 0), 5)

    def eval(self, ctx, si, wo, active=True):
        cos_theta_i = mi.Frame3f.cos_theta(si.wi)
        cos_theta_o = mi.Frame3f.cos_theta(wo)
        h = dr.normalize(si.wi + wo)
        cos_theta_h = dr.dot(si.wi, h)

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

    def eval_specular(self, si, wo, active=True):
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
        specular = D * G / (4.0 * dr.maximum(cos_theta_i * cos_theta_o, 1e-7))

        return dr.select(
            active & (cos_theta_i > 0) & (cos_theta_o > 0),
            mi.Color3f(specular),
            mi.Color3f(0),
        )

    def pdf(self, ctx, si, wo, active=True):
        cos_theta_i = mi.Frame3f.cos_theta(si.wi)
        cos_theta_o = mi.Frame3f.cos_theta(wo)

        spec_prob = self._spec_prob()

        alpha = dr.maximum(self.roughness * self.roughness, 1e-4)
        distr = mi.MicrofacetDistribution(
            mi.MicrofacetType.GGX, alpha, sample_visible=True
        )

        h = dr.normalize(si.wi + wo)
        cos_h = dr.maximum(dr.abs(dr.dot(si.wi, h)), 1e-7)

        wi_hat = dr.mulsign(si.wi, cos_theta_i)
        spec_pdf = dr.maximum(distr.pdf(wi_hat, h) / (4 * cos_h), 0)

        diff_pdf = mi.warp.square_to_cosine_hemisphere_pdf(wo) * (1 - self.metallic)
        pdf_val = spec_prob * spec_pdf + (1 - spec_prob) * diff_pdf

        return dr.select(
            active & (cos_theta_i > 0) & (cos_theta_o > 0),
            pdf_val,
            mi.Float(0)
        )

    def eval_pdf(self, ctx, si, wo, active=True):
        return self.eval(ctx, si, wo, active), self.pdf(ctx, si, wo, active)

    def traverse(self, callback):
        pass

    def to_string(self):
        return f"PrincipledBSDF[base_colour={self.base_colour}, roughness={self.roughness}, metallic={self.metallic}]"


mi.register_bsdf("principled_bsdf", lambda props: PrincipledBSDF(props))
print("Principled BSDF registered")
