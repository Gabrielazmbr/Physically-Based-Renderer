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
        ) # Gets base colour from scene, if not falls back to white
        self.roughness = props.get("roughness", 0.0) # Gets roughness, if not falls to smooth 0.0
        self.metallic = props.get("metallic", 0.0) # Gets metallic, if not falls to dielectric 0.0

        # Flags: Bitmask describing what the BSDF is able to do.
        self.m_flags = (
            mi.BSDFFlags.DiffuseReflection
            | mi.BSDFFlags.GlossyReflection #GGX Specular lobe
            | mi.BSDFFlags.FrontSide # just front side
        )
        # Component flags: registers a list of lobes required for plugin
        self.m_components = [
            mi.BSDFFlags.DiffuseReflection | mi.BSDFFlags.FrontSide,
            mi.BSDFFlags.GlossyReflection | mi.BSDFFlags.FrontSide,
        ]

    def _spec_prob(self):
        '''
        Computes the probability (0.1 - 1.0) of sampling specular lobe vs diffuse lobe based on metallic.
        Avoids 0 that completely ignores specular GGX lobe. Allows 1 for 100% specular.
        '''
        return dr.select(self.metallic > 0.99, mi.Float(1.0),
            mi.Float(dr.clamp(self.metallic * 0.8 + 0.1, 0.1, 0.9)))

    def sample(self, ctx, si, sample1, sample2, active=True): # BSDF Context, Surface interaction data, random numbers, ray mask
        '''
        Randomly chooses an outgoing light direction according to the BSDF,
        computes the energy carried by that direction, and returns all the
        information the path tracer needs to continue tracing the path.
        '''

        cos_theta_i = mi.Frame3f.cos_theta(si.wi) #incoming ray direction
        active = active & (cos_theta_i > 0) # For rays comming from the front side only

        spec_prob = self._spec_prob() # Calls _spec_prob for computing probability

        alpha = dr.maximum(self.roughness * self.roughness, 1e-4) # Squaring roughness for better control, also avoids 0
        distr = mi.MicrofacetDistribution(mi.MicrofacetType.GGX, alpha, sample_visible=True)
        # MicrofacetDistribution : GGX Model object from Mitsuba

        bs = mi.BSDFSample3f() # stores sampling result (wo, pdf, eta, s type, s component)
        sample_specular = sample1 < spec_prob # Decides which lobe

        # Specular sampling
        wi_hat = dr.mulsign(si.wi, cos_theta_i) # Stores incoming direction
        m, m_pdf = distr.sample(wi_hat, sample2) # Samples microfacet normal , probability of choosing that microfacet PDF
        wo_spec = mi.reflect(si.wi, m) # stores reflected outgoing ray direction
        valid_spec = (mi.Frame3f.cos_theta(wo_spec) > 0) & active # Checks direction is valid (not underneath surface)

        # Specular weight - Calculates amount of reflected light
        cos_mi = dr.dot(si.wi, m) # Dot product of incoming ray and microfacet normal
        F = self.fresnel_schlick(cos_mi) # Reflectance: dielectic materials is 0.04, for metals grabs base colour.
        G1 = distr.smith_g1(si.wi, m) # Incoming visibility (How much of the incoming direction is blocked)
        G2 = distr.G(si.wi, wo_spec, m) # Incoming shadowing and outgoing masking
        weight_spec = dr.select(G1 > 0, F * G2 / G1, mi.Color3f(0)) # Contribution: Cook-Torrance equation
        # D (probability) is implied in sample_specular
        # PDF is handled later

        # Diffuse sampling
        wo_diff = mi.warp.square_to_cosine_hemisphere(sample2) # Chosen diffuse reflection direction
        # cos terms cancel with pdf
        cos_mi_diff = dr.dot(si.wi, dr.normalize(si.wi + wo_diff)) # finds halfway vector
        F_diff = self.fresnel_schlick(dr.maximum(cos_mi_diff, 0)) # Amount of interaction behaving as reflection
        weight_diff = self.base_colour * (1 - F_diff) * (1 - self.metallic) # Contribution of energy aosciated with wo_diff

        # Select lobe (Diffuse or Specular)
        use_spec = sample_specular & valid_spec # Checks if specular lobe was chosen and is valid, both need to be true
        bs.wo = dr.select(use_spec, wo_spec, wo_diff) # If use_spec true the use wo_spec, else wo_diff
        bs.eta = 1.0 # index of refraction (no refraction in this case)
        bs.sampled_component = dr.select(
            use_spec,
            mi.UInt32(1),
            mi.UInt32(0)
        ) # Component index based un result
        bs.sampled_type = dr.select(
            use_spec,
            mi.UInt32(+mi.BSDFFlags.GlossyReflection),
            mi.UInt32(+mi.BSDFFlags.DiffuseReflection)
        ) # Flags index based on result

        # PDF for MIS
        cos_theta_o = mi.Frame3f.cos_theta(bs.wo) # how much outgoing ray points away from surface: n⋅ωo
        h = dr.normalize(si.wi + bs.wo) # microfacet normal halfway vector
        cos_theta_i_val = dr.maximum(cos_theta_i, 1e-7) # Clamp to avoid division by zero in the PDF computation

        spec_pdf = dr.maximum(
            distr.eval(h) * distr.smith_g1(wi_hat, h) / (4 * cos_theta_i_val), 0
        ) # microfacet probable orientation * visibility / 4 * cos_theta_i_val = PDF outgoing direction, clamps to positive
        diff_pdf = mi.warp.square_to_cosine_hemisphere_pdf(bs.wo) # Probability of chosen direction
        bs.pdf = spec_prob * spec_pdf + (1 - spec_prob) * diff_pdf # Monte Carlo approach - Final PDF

        weight = dr.select(use_spec, weight_spec,
                 dr.select(~sample_specular, weight_diff, mi.Color3f(0))) # the energy carried by bs.wo
        # If the specular lobe was chosen and the reflection is valid, use weight_spec.
        # If diffuse was chosen, use weight_diff.
        # If specular was chosen but produces an invalid direction, return zero, avoid falling back to diffuse.

        return bs, dr.select(active & (cos_theta_o > 0), weight, mi.Color3f(0))
        # Sampling result (BSDFSample3f) + sample weight (energy transported) checks ray being active and valid direction


    def fresnel_schlick(self, cos_theta):
        '''
        Applies Fresnel Schlick approximation equation.
            F=F0​+(1−F0​)(1−cosθ)5
        '''
        # F0 blended by metallic parameter
        f0_dielectric = mi.Color3f(0.04) # Reflectance at normal incidence given
        f0 = f0_dielectric * (1 - self.metallic) + self.base_colour * self.metallic
        # Case 1: Dialectric = Metallic 0, uses 0.04 reflectance
        # Case 2: Metals = Metallic 1, uses base_colour
        return f0 + (1 - f0) * dr.power(dr.maximum(1 - cos_theta, 0), 5) # Schlick's approximation result

    def eval(self, ctx, si, wo, active=True):
        '''
        Evaluates the BSDF value for a given incoming and outgoing direction
        without generating a new sample. It returns how much light is reflected
        from the incoming direction si.wi towards the outgoing direction wo.
        '''

        cos_theta_i = mi.Frame3f.cos_theta(si.wi)  #incoming ray direction n⋅ωi
        cos_theta_o = mi.Frame3f.cos_theta(wo) # outgoing ray direction n⋅ωo
        h = dr.normalize(si.wi + wo) #reconstructs halfway vector microfacet normal
        cos_theta_h = dr.dot(si.wi, h) # angle between incoming ray and microfacet normal ωi​⋅h

        F = self.fresnel_schlick(cos_theta_h) # Schlick returns the fraction of light reflected by microfacet

        # Diffuse lobe
        diffuse = (
            self.base_colour * dr.inv_pi * cos_theta_o * (1 - F) * (1 - self.metallic)
        ) # material colour * Lambert Reflection (1/π * cosine law) * available energy after fresnel * non-metal factor

        # Specular lobe
        specular = self.eval_specular(si, wo, active) * F # computes the shape of the GGX specular lobe according to Fresnel Effect

        return dr.select(
            active & (cos_theta_i > 0) & (cos_theta_o > 0),
            diffuse + specular,
            mi.Color3f(0),
        ) # Checks alive rays and above the surface as valid, returns complete BRDF

    def eval_specular(self, si, wo, active=True):
        '''
        Evaluates the GGX microfacet specular BRDF (without Fresnel)
        for a given incoming and outgoing direction.
        '''

        h = dr.normalize(si.wi + wo) # Halfway vector microfacet normal
        cos_theta_i = mi.Frame3f.cos_theta(si.wi)  #incoming ray direction n⋅ωi
        cos_theta_o = mi.Frame3f.cos_theta(wo)  #outgoing ray direction n⋅ωo

        # GGX microfacet distribution
        alpha = dr.maximum(self.roughness * self.roughness, 1e-4) # Squaring roughness for better control, also avoids 0
        distr = mi.MicrofacetDistribution(
            mi.MicrofacetType.GGX, alpha, sample_visible=True
        ) # MicrofacetDistribution : GGX Model object from Mitsuba

        D = distr.eval(h) # D : microfacet distribution (high bright, low dimmed)
        G = distr.G(si.wi, wo, h) # G : Visibility of microfacets (masking, shadowing)

        # Specular value
        specular = D * G / (4.0 * dr.maximum(cos_theta_i * cos_theta_o, 1e-7)) # GGX BRDF equation without F, dr.maximum avoids div zero

        return dr.select(
            active & (cos_theta_i > 0) & (cos_theta_o > 0),
            mi.Color3f(specular),
            mi.Color3f(0),
        ) # Checks alive rays and above the surface as valid, returns specular BRDF

    def pdf(self, ctx, si, wo, active=True):
        '''
        Returns the probability density that the BSDF's sample() function
        would generate the outgoing direction wo.
        '''
        cos_theta_i = mi.Frame3f.cos_theta(si.wi) #incoming ray direction n⋅ωi
        cos_theta_o = mi.Frame3f.cos_theta(wo) #outgoing ray direction n⋅ωo

        spec_prob = self._spec_prob() # Calls _spec_prob for computing probability

        alpha = dr.maximum(self.roughness * self.roughness, 1e-4) # Squaring roughness for better control, also avoids 0
        distr = mi.MicrofacetDistribution(
            mi.MicrofacetType.GGX, alpha, sample_visible=True
        ) # MicrofacetDistribution : GGX Model object from Mitsuba

        wi_hat = dr.mulsign(si.wi, cos_theta_i) # Stores incoming direction
        h = dr.normalize(si.wi + wo) # Halfway vector microfacet normal
        cos_theta_i_val = dr.maximum(cos_theta_i, 1e-7) # Clamp to avoid division by zero
        spec_pdf = dr.maximum(
            distr.eval(h) * distr.smith_g1(wi_hat, h) / (4 * cos_theta_i_val), 0
        ) # microfacet probable orientation * visibility / 4 * cos_theta_i_val = PDF outgoing direction, clamps to positive

        diff_pdf = mi.warp.square_to_cosine_hemisphere_pdf(wo) # Probability of chosen direction
        pdf_val = spec_prob * spec_pdf + (1 - spec_prob) * diff_pdf # Monte Carlo approach - Final PDF


        return dr.select(
            active & (cos_theta_i > 0) & (cos_theta_o > 0),
            pdf_val,
            mi.Float(0)
        ) # If the directions are physically valid return the PDF

    def eval_pdf(self, ctx, si, wo, active=True):
        '''
        Evaluates both the BSDF value and the PDF for the same
        outgoing direction in a single function call.
        '''
        return self.eval(ctx, si, wo, active), self.pdf(ctx, si, wo, active)

    def traverse(self, callback):
        pass

    def to_string(self):
        return f"PrincipledBSDF[base_colour={self.base_colour}, roughness={self.roughness}, metallic={self.metallic}]"


mi.register_bsdf("principled_bsdf", lambda props: PrincipledBSDF(props)) # Register PrincipledBSDF class (creates instance)
print("Principled BSDF registered")
