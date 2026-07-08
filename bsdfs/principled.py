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

        # Set BSDF flags: All types of scattering
        # On the front face only
        self.m_flags = mi.BSDFFlags.All | mi.BSDFFlags.FrontSide
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

        value = self.base_colour

        return bs, dr.select(active & (cos_theta_i > 0), value, mi.Color3f(0))

    def eval(self, ctx, si, wo, active):
        cos_theta_i = mi.Frame3f.cos_theta(si.wi)
        cos_theta_o = mi.Frame3f.cos_theta(wo)
        return dr.select(
            active & (cos_theta_i > 0) & (cos_theta_o > 0),
            self.base_colour * dr.inv_pi * cos_theta_o,
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
