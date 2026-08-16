import drjit as dr
import mitsuba as mi

"""
This class implements a Principled BSDF model.
It can be seen as a material router with validated results.
The class inherits from Mitsuba’s BSDF interface.
eval():   How much light would scatter in this specified direction?
pdf():    How likely is this BSDF to generate that direction?
sample(): Generate a direction and return its transport weight.
"""

class PrincipledBSDF(mi.BSDF):
    def __init__(self, props):
        mi.BSDF.__init__(self, props)

        # Base Colour
        self.base_colour = props.get("base_colour", mi.Color3f(1.0)) # Gets base colour from scene, if not falls back to white
        if not isinstance(self.base_colour, mi.Texture):
            self.base_colour = mi.Color3f(self.base_colour) # Mitsuba's parser instantiates intp mi.Texture object

        # Roughness
        self.roughness = props.get("roughness", 0.0) # Gets roughness, if not falls to smooth 0.0
        if not isinstance(self.roughness, mi.Texture):
            self.roughness = mi.Float(self.roughness)

        # Metallic
        self.metallic = props.get("metallic", 0.0) # Gets metallic, if not falls to dielectric 0.0
        if not isinstance(self.metallic, mi.Texture):
            self.metallic = mi.Float(self.metallic)

        # Specular
        self.specular = props.get("specular", 0.5) # Gets specular, default 0.5 matches Disney/Blender convention
        if not isinstance(self.specular, mi.Texture):
            self.specular = mi.Float(self.specular)

        # Anisotropic
        self.anisotropic = props.get("anisotropic", 0.0) # Gets anisotropic, 0.0 = isotropic
        if not isinstance(self.anisotropic, mi.Texture):
            self.anisotropic = mi.Float(self.anisotropic)

        # Clearcoat - second specular lobe (GTR1)
        self.clearcoat = props.get("clearcoat", 0.0) # 0.0 = no coat (default, unchanged behaviour)
        if not isinstance(self.clearcoat, mi.Texture):
            self.clearcoat = mi.Float(self.clearcoat)

        # Clearcoat gloss - 0 = soft coat (alpha 0.1), 1 = near-mirror coat (alpha 0.001)
        self.clearcoat_gloss = props.get("clearcoat_gloss", 1.0)
        if not isinstance(self.clearcoat_gloss, mi.Texture):
            self.clearcoat_gloss = mi.Float(self.clearcoat_gloss)

        # Sheen - grazing-angle fabric term. Evaluated only, never separately
        # sampled (Disney's own reference). Documented approximation.
        self.sheen = props.get("sheen", 0.0)
        if not isinstance(self.sheen, mi.Texture):
            self.sheen = mi.Float(self.sheen)

        # Sheen tint - 0 = white sheen, 1 = tinted toward base_colour's hue
        self.sheen_tint = props.get("sheen_tint", 0.5)
        if not isinstance(self.sheen_tint, mi.Texture):
            self.sheen_tint = mi.Float(self.sheen_tint)

        # Diffuse model
        self.diffuse_model = props.get("diffuse_model", "lambert") # "lambert" (default, unchanged) or "burley" — see eval()

        # Transmission (smooth dielectric)
        self.transmission = props.get("transmission", 0.0) # 0.0 = fully opaque (default, unchanged behaviour)
        if not isinstance(self.transmission, mi.Texture):
            self.transmission = mi.Float(self.transmission)
        self.ior = float(props.get("ior", 1.5)) # relative index of refraction, outside to inside. Only used when transmission > 0.

        # Thin-sheet mode: a pane of glass, a dial cover, a window.
        self.thin = bool(props.get("thin", False))

        # Whether to advertise transmission-related flags. Decided once at
        # construction: textures can vary per-point, so assume transmissive.
        has_transmission = isinstance(self.transmission, mi.Texture) or float(self.transmission[0]) > 0


        # Flags: Bitmask describing what the BSDF is able to do.
        self.m_flags = (
            mi.BSDFFlags.DiffuseReflection  # Diffuse reflection
            | mi.BSDFFlags.GlossyReflection  # GGX Specular lobe
            | mi.BSDFFlags.FrontSide # just front side
        )
        # Component flags: registers a list of lobes required for plugin
        self.m_components = [
            mi.BSDFFlags.DiffuseReflection | mi.BSDFFlags.FrontSide,
            mi.BSDFFlags.GlossyReflection | mi.BSDFFlags.FrontSide,
        ]
        if has_transmission:
            # Transmission needs back-side hits (rays exiting the medium) and
            # advertises delta lobes. NonSymmetric because the eta^2 radiance
            # scaling makes the BSDF direction-dependent.
            self.m_flags = (self.m_flags
                | mi.BSDFFlags.DeltaReflection
                | mi.BSDFFlags.DeltaTransmission
                | mi.BSDFFlags.BackSide
                | mi.BSDFFlags.NonSymmetric)
            self.m_components.append(
                mi.BSDFFlags.DeltaReflection | mi.BSDFFlags.DeltaTransmission
                | mi.BSDFFlags.FrontSide | mi.BSDFFlags.BackSide)

        # Clearcoat advertises a second glossy lobe. The index is computed, not
        # hardcoded, because the transmission component above may or may not
        # have been appended.
        has_clearcoat = isinstance(self.clearcoat, mi.Texture) or float(self.clearcoat[0]) > 0
        self.cc_component = 0
        if has_clearcoat:
            self.cc_component = len(self.m_components)
            self.m_components.append(
                mi.BSDFFlags.GlossyReflection | mi.BSDFFlags.FrontSide)


    def _clearcoat_at(self, si, active=True):
        """
        Outputs clearcoat at the current surface point,
        regardless of whether the clearcoat is a constant value or a texture
        """
        if isinstance(self.clearcoat, mi.Texture):
            return self.clearcoat.eval_1(si, active)
        return self.clearcoat

    def _clearcoat_gloss_at(self, si, active=True):
        """
        Outputs clearcoat gloss at the current surface point,
        regardless of whether the clearcoat gloss is a constant value or a texture
        """

        if isinstance(self.clearcoat_gloss, mi.Texture):
            return self.clearcoat_gloss.eval_1(si, active)
        return self.clearcoat_gloss

    def _sheen_at(self, si, active=True):
        """
        Outputs sheen at the current surface point,
        regardless of whether the sheen is a constant value or a texture
        """

        if isinstance(self.sheen, mi.Texture):
            return self.sheen.eval_1(si, active)
        return self.sheen

    def _sheen_tint_at(self, si, active=True):
        """
        Outputs sheen tint at the current surface point,
        regardless of whether the sheen tint is a constant value or a texture
        """
        if isinstance(self.sheen_tint, mi.Texture):
            return self.sheen_tint.eval_1(si, active)
        return self.sheen_tint


    def _base_colour_at(self, si, active=True):
        """
        Outputs base color at the current surface point,
        regardless of whether the base color is a constant value or a texture
        """
        if isinstance(self.base_colour, mi.Texture):
            return self.base_colour.eval(si, active)
        return self.base_colour

    def _roughness_at(self, si, active=True):
        """
        Outputs roughness at the current surface point,
        regardless of whether the roughness is a constant value or a texture
        """
        if isinstance(self.roughness, mi.Texture):
            return self.roughness.eval_1(si, active)
        return self.roughness

    def _metallic_at(self, si, active=True):
        """
        Outputs metallic value at the current surface point,
        regardless of whether the metallic value is a constant value or a texture
        """
        if isinstance(self.metallic, mi.Texture):
            return self.metallic.eval_1(si, active)
        return self.metallic

    def _specular_at(self, si, active=True):
        """
        Outputs specular value at the current surface point,
        regardless of whether the specular value is a constant value or a texture
        """
        if isinstance(self.specular, mi.Texture):
            return self.specular.eval_1(si, active)
        return self.specular

    def _anisotropic_at(self, si, active=True):
            """
            Outputs anisotropic value at the current surface point,
            regardless of whether the anisotropic value is a constant value or a texture
            """
            if isinstance(self.anisotropic, mi.Texture):
                return self.anisotropic.eval_1(si, active)
            return self.anisotropic

    def _alphas(self, roughness, anisotropic):
        """
        Splits a single roughness into two directional roughnesses (tangent and
        bitangent) using Disney's aspect-ratio convention.
        anisotropic=0 gives aspect=1, so alpha_u == alpha_v == the original
        isotropic alpha (previous behaviour exactly).
        """
        alpha = dr.maximum(roughness * roughness, 1e-4) # Squaring roughness for better control, also avoids 0
        aspect = dr.sqrt(1.0 - 0.9 * anisotropic) # 0.9 caps the stretch so alpha never collapses to zero
        alpha_u = dr.maximum(alpha / aspect, 1e-4) # roughness along the tangent
        alpha_v = dr.maximum(alpha * aspect, 1e-4) # roughness along the bitangent
        return alpha_u, alpha_v

    def _clearcoat_alpha(self, clearcoat_gloss):
        """
        Disney's clearcoat has its own fixed roughness range, and unlike the
        main specular lobe this alpha is used DIRECTLY, not squared.
        gloss=0 to alpha=0.1 (soft coat); gloss=1 to alpha=0.001 (near-mirror).
        """
        return dr.maximum(0.1 * (1.0 - clearcoat_gloss) + 0.001 * clearcoat_gloss, 1e-4)

    def _gtr1_D(self, cos_theta_h, alpha):
        """
        GTR1 (Berry) normal distribution — Disney's clearcoat NDF.
        Hand-written because Mitsuba's MicrofacetDistribution only ships
        Beckmann and GGX. Both (a2 - 1) and log(a2) are negative for alpha
        < 1, so D > 0. Verified numerically: integral of D*cos over the
        hemisphere = 1.000000 for alpha in [0.001, 0.1].
        NOTE: cos_theta_h here is n.h, NOT wi.h.
        """
        a2 = dr.sqr(alpha)
        denom = dr.log(a2) * (1.0 + (a2 - 1.0) * dr.sqr(cos_theta_h))
        return dr.select(cos_theta_h > 0, (a2 - 1.0) * dr.inv_pi / denom, mi.Float(0.0))


    def _clearcoat_prob(self, clearcoat, clearcoat_gloss):
        """
        Probability of selecting the clearcoat lobe, scaled by gloss.
        A broad coat (gloss=0, alpha=0.1) falls inside the region cosine
        sampling already covers, so giving it a large share of samples
        starves the base layers — measured: fixed 0.25 made the furnace std
        WORSE at gloss=0 (0.0107 to 0.0135) while improving gloss=1 by 4.3x.
        A sharp coat is a spike no other lobe finds, so it needs the samples.
        Floored at 0.05 rather than 0, because a metallic base has p_diff=0
        and a low-roughness GGX lobe may not cover the coat's directions
        either — dropping to zero there would reintroduce fireflies.
        """
        return clearcoat * dr.clamp(0.05 + 0.20 * clearcoat_gloss, 0.05, 0.25)

    def _sample_gtr1(self, sample2, alpha):
        """
        Importance-samples a microfacet normal from GTR1 by inverting its CDF
        in cos(theta). Isotropic, so phi is uniform and no tangent-frame
        rotation is needed — unlike the anisotropic GGX lobe.
        The inversion was validated against the analytic density before use:
        KS test over 20 seeds gave 0/20 failures, while a deliberately
        mis-scaled control failed 20/20.
        Returns the half-vector in the shading frame.
        """
        a2 = dr.sqr(alpha)
        cos_sq = (1.0 - dr.power(a2, 1.0 - sample2.x)) / dr.maximum(1.0 - a2, 1e-8)
        cos_theta = dr.sqrt(dr.clamp(cos_sq, 0.0, 1.0))
        sin_theta = dr.sqrt(dr.maximum(1.0 - dr.sqr(cos_theta), 0.0))
        sin_phi, cos_phi = dr.sincos(dr.two_pi * sample2.y) # returns (sin, cos)
        return mi.Vector3f(sin_theta * cos_phi, sin_theta * sin_phi, cos_theta)

    def _clearcoat_pdf(self, si, wo, alpha):
        """
        Clearcoat lobe PDF in the same solid-angle measure as the other lobes.
        Half-vector density D*cos(theta_h), converted by the reflection
        Jacobian 1/(4*dot(wi,h)). Verified: mi.reflect(wi,h) satisfies
        normalize(wi+wo)==h and dot(wi,h)==dot(wo,h).
        """
        h = dr.normalize(si.wi + wo)
        cos_h = mi.Frame3f.cos_theta(h)
        dot_wi_h = dr.dot(si.wi, h)
        pdf = self._gtr1_D(cos_h, alpha) * cos_h / (4.0 * dr.maximum(dr.abs(dot_wi_h), 1e-7))
        return dr.maximum(dr.select(dot_wi_h > 0, pdf, mi.Float(0.0)), 0.0)

    def _sheen_colour(self, base_colour, sheen_tint):
        """
        Disney's sheen tint: base_colour's hue with its brightness divided out,
        blended toward white by sheen_tint. Luminance weights are Disney's.
        """
        lum = 0.3 * base_colour.x + 0.6 * base_colour.y + 0.1 * base_colour.z
        tint = dr.select(lum > 0, base_colour / dr.maximum(lum, 1e-8), mi.Color3f(1.0))
        return mi.Color3f(1.0) * (1.0 - sheen_tint) + tint * sheen_tint

    def _tangent_local(self, si):
            """
            Surface tangent direction, expressed inside the shading frame.
            dp_du is the tangent from the UV parameterisation and is perpendicular
            to the normal, so in shading-frame coordinates it lies in the XY plane.
            Aligning to it is therefore only a rotation about the local Z axis.
            Falls back to the frame's own X axis (an identity rotation) when
            dp_du is degenerate or unset — e.g. a hand-built SurfaceInteraction
            with no real UV data, as used by the chi-squared test harness.
            """
            t = si.sh_frame.to_local(si.dp_du)
            t2 = mi.Vector2f(t.x, t.y)
            len_t2 = dr.norm(t2)
            degenerate = len_t2 < 1e-6
            return dr.select(degenerate, mi.Vector2f(1.0, 0.0), t2 / dr.maximum(len_t2, 1e-8))

    def _to_tangent(self, v, t):
        """Rotates a shading-frame direction into the tangent-aligned frame (Z unchanged)."""
        return mi.Vector3f(v.x * t.x + v.y * t.y, -v.x * t.y + v.y * t.x, v.z)

    def _from_tangent(self, v, t):
        """Inverse of _to_tangent: tangent-aligned frame back to shading frame."""
        return mi.Vector3f(v.x * t.x - v.y * t.y, v.x * t.y + v.y * t.x, v.z)

    def _transmission_at(self, si, active=True):
        """
        Outputs transmission value at the current surface point,
        regardless of whether the transmission value is a constant value or a texture
        """
        if isinstance(self.transmission, mi.Texture):
            return self.transmission.eval_1(si, active)
        return self.transmission


    def eval_diffuse_reflectance(self, si, active=True):
        """
        Overrides the generic base-class default (which folds in Fresnel and
        view-angle dependence) to return the traditional flat albedo AOV:
        material base color only, no lighting or view dependence. Albedo pass.
        """
        return self._base_colour_at(si, active)

    def _spec_prob(self, metallic, specular):
        """
        Computes the probability (0.0 - 1.0) of sampling specular lobe vs diffuse lobe based on metallic.
        Floors at 0.1 to avoid a nonzero specular lobe being invisible to the
        sampler except when there is truly no specular reflectance at all
        (specular=0 and metallic=0), in which case this returns exactly 0,
        matching a full Lambertian.
        """
        base_prob = dr.select(metallic > 0.99, mi.Float(1.0),
            mi.Float(dr.clamp(metallic * 0.8 + 0.1, 0.1, 0.9)))
        has_specular = (specular > 0) | (metallic > 0)
        return dr.select(has_specular, base_prob, mi.Float(0.0))

    def sample(self, ctx, si, sample1, sample2, active=True): # BSDF Context, Surface interaction data, random numbers, ray mask
        """
        Randomly chooses an outgoing light direction according to the BSDF,
        computes the energy carried by that direction, and returns all the
        information the path tracer needs to continue tracing the path.
        """

        cos_theta_i = mi.Frame3f.cos_theta(si.wi) #incoming ray direction
        transmission = self._transmission_at(si, active) # Calls _transmission_at for transmission value

        # Back-side hits are only meaningful through the transmissive lobe;
        # the opaque BSDF below remains front-side only.
        active = active & ((cos_theta_i > 0) | (transmission > 0))

        # Outer blend: transmissive (smooth dielectric) vs opaque (existing mixture).
        # Rays arriving from inside must take the dielectric branch, since the
        # opaque lobes are undefined there.
        take_diel = (sample1 < transmission) | (cos_theta_i <= 0)
        # Rescale sample1 so each branch still receives a uniform [0,1) value
        sample1 = dr.select(
            take_diel,
            sample1 / dr.maximum(transmission, 1e-8),
            (sample1 - transmission) / dr.maximum(1.0 - transmission, 1e-8),
        )
        sample1 = dr.clamp(sample1, 0.0, 0.999999)

        roughness = self._roughness_at(si, active) # Calls _roughness_at for roughness value
        metallic = self._metallic_at(si, active) # Calls _metallic_at for metallic value

        specular = self._specular_at(si, active) # Calls _specular_at for specular value
        anisotropic = self._anisotropic_at(si, active) # Calls _anisotropic_at for anisotropic value
        spec_prob = self._spec_prob(metallic, specular) # Calls _spec_prob for computing probability

        # Clearcoat takes its share off the top, then the existing two-lobe
        # split divides what remains. p_clear + p_spec + p_diff == 1 exactly.
        # At clearcoat=0 this reduces to the original split unchanged.
        clearcoat = self._clearcoat_at(si, active)
        cc_gloss = self._clearcoat_gloss_at(si, active)
        cc_alpha = self._clearcoat_alpha(cc_gloss)
        cc_prob = self._clearcoat_prob(clearcoat, cc_gloss)
        p_clear = cc_prob
        p_spec = spec_prob * (1.0 - cc_prob)
        p_diff = (1.0 - spec_prob) * (1.0 - cc_prob)

        alpha_u, alpha_v = self._alphas(roughness, anisotropic) # Two directional roughnesses (equal when anisotropic=0)
        distr = mi.MicrofacetDistribution(mi.MicrofacetType.GGX, alpha_u, alpha_v, True)
        # MicrofacetDistribution : GGX Model object from Mitsuba

        tangent = self._tangent_local(si) # Surface tangent direction, inside the shading frame
        wi_t = self._to_tangent(si.wi, tangent) # Incoming direction, rotated tangent-aligned

        bs = mi.BSDFSample3f() # stores sampling result (wo, pdf, eta, s type, s component)
        # Three-way lobe choice from one uniform: [0,p_clear) clearcoat,
        # [p_clear, p_clear+p_spec) specular, remainder diffuse.
        take_clear = sample1 < p_clear
        sample_specular = (~take_clear) & (sample1 < p_clear + p_spec)

        # Specular sampling (performed in the tangent-aligned frame)
        wi_hat_t = dr.mulsign(wi_t, cos_theta_i) # Stores incoming direction
        m_t, m_pdf = distr.sample(wi_hat_t, sample2) # Samples microfacet normal , probability of choosing that microfacet PDF
        wo_spec_t = mi.reflect(wi_t, m_t) # reflected direction, still tangent-aligned
        wo_spec = self._from_tangent(wo_spec_t, tangent) # rotated back to the shading frame

        valid_spec = (mi.Frame3f.cos_theta(wo_spec) > 0) & active # Checks direction is valid (not underneath surface)


        # Clearcoat sampling (isotropic — shading frame directly, no tangent rotation)
        h_cc = self._sample_gtr1(sample2, cc_alpha) # GTR1 microfacet normal
        wo_cc = mi.reflect(si.wi, h_cc) # reflected direction
        valid_cc = (mi.Frame3f.cos_theta(wo_cc) > 0) & active # not below the surface

        # Diffuse sampling
        wo_diff = mi.warp.square_to_cosine_hemisphere(sample2) # Chosen diffuse reflection direction

        # Select lobe (Diffuse or Specular)
        use_spec = sample_specular & valid_spec # Checks if specular lobe was chosen and is valid, both need to be true
        use_clear = take_clear & valid_cc # same rule for the coat
        # Failed clearcoat samples fall through to wo_diff and get a zero
        # weight below — identical handling to failed specular samples.
        bs.wo = dr.select(use_clear, wo_cc, dr.select(use_spec, wo_spec, wo_diff))
        bs.eta = 1.0 # index of refraction (no refraction in this case)
        bs.sampled_component = dr.select(
            use_clear,
            mi.UInt32(self.cc_component),
            dr.select(use_spec, mi.UInt32(1), mi.UInt32(0))
        ) # Component index based un result
        bs.sampled_type = dr.select(
            use_clear | use_spec,
            mi.UInt32(+mi.BSDFFlags.GlossyReflection),
            mi.UInt32(+mi.BSDFFlags.DiffuseReflection)
        ) # Flags index based on result

        # PDF for MIS
        cos_theta_o = mi.Frame3f.cos_theta(bs.wo) # how much outgoing ray points away from surface: n⋅ωo
        wo_t = self._to_tangent(bs.wo, tangent) # outgoing direction, tangent-aligned
        h_t = dr.normalize(wi_t + wo_t) # microfacet normal halfway vector, tangent-aligned
        cos_theta_i_val = dr.maximum(cos_theta_i, 1e-7) # Clamp to avoid division by zero in the PDF computation

        spec_pdf = dr.maximum(
            distr.eval(h_t) * distr.smith_g1(wi_hat_t, h_t) / (4 * cos_theta_i_val), 0
        )
        diff_pdf = mi.warp.square_to_cosine_hemisphere_pdf(bs.wo) # Probability of chosen direction
        cc_pdf = self._clearcoat_pdf(si, bs.wo, cc_alpha) # coat lobe density at the chosen direction
        # Every lobe's density is evaluated at the SAME chosen direction,
        # whichever lobe produced it — that is what makes this a valid mixture.
        bs.pdf = (p_clear * cc_pdf + p_spec * spec_pdf + p_diff * diff_pdf) * (1.0 - transmission) # includes the probability of taking the opaque branch

        # Smooth dielectric branch (delta reflection / delta refraction)
        base_colour_d = self._base_colour_at(si, active)

        if self.thin:
            """
            Thin-sheet dielectric. A thin pane has no interior for a ray to be
            inside of, so a back-side hit is still air->glass->air: dr.abs()
            on the cosine prevents mi.fresnel from firing spurious total
            internal reflection (without it, back-side hits reflected 100% at
            cos_i=-0.5 where the correct answer is 16%).
            Light bouncing between the two close interfaces raises the effective
            reflectance from R to 2R/(1+R). The transmitted ray continues
            straight through, so there is no refraction offset and no eta^2
            radiance scaling.
            """
            F_d, _, _, _ = mi.fresnel(dr.abs(cos_theta_i), mi.Float(self.ior))
            F_thin = 2.0 * F_d / (1.0 + F_d)
            take_reflect = sample1 < F_thin
            wo_diel = dr.select(take_reflect, mi.reflect(si.wi), -si.wi) # straight through
            weight_diel = dr.select(take_reflect, mi.Color3f(1.0), base_colour_d)
            pdf_diel = dr.select(take_reflect, F_thin, 1.0 - F_thin) * transmission
            eta_diel = mi.Float(1.0) # enters and exits: no net medium change
        else:
            # Smooth dielectric branch (delta reflection / delta refraction)
            F_d, cos_theta_t, eta_it, eta_ti = mi.fresnel(cos_theta_i, mi.Float(self.ior))
            # mi.fresnel handles both sides automatically from the sign of cos_theta_i,
            # and returns F = 1 under total internal reflection, so TIR needs no special case.
            take_reflect = sample1 < F_d
            wo_diel = dr.select(take_reflect, mi.reflect(si.wi), mi.refract(si.wi, cos_theta_t, eta_ti))
            base_colour_d = self._base_colour_at(si, active)
            # Transmitted radiance is scaled by eta_ti^2 - radiance compresses entering
            # a denser medium (flux is conserved, radiance is not). Verified against
            # Mitsuba's own `dielectric`: 1/1.5^2 = 0.4444 at ior=1.5.
            weight_diel = dr.select(take_reflect, mi.Color3f(1.0), base_colour_d * dr.sqr(eta_ti))
            pdf_diel = dr.select(take_reflect, F_d, 1.0 - F_d) * transmission # includes the probability of taking the dielectric branch
            type_diel = dr.select(take_reflect, mi.UInt32(+mi.BSDFFlags.DeltaReflection), mi.UInt32(+mi.BSDFFlags.DeltaTransmission))
            eta_diel = dr.select(take_reflect, mi.Float(1.0), eta_it)

        type_diel = dr.select(take_reflect, mi.UInt32(+mi.BSDFFlags.DeltaReflection), mi.UInt32(+mi.BSDFFlags.DeltaTransmission))


        #Specular weight (opaque branch)
        full_brdf = self.eval(ctx, si, bs.wo, active)
        weight = dr.select(bs.pdf > 0, full_brdf / bs.pdf, mi.Color3f(0))
        weight = dr.select(sample_specular & ~valid_spec, mi.Color3f(0), weight)
        weight = dr.select(take_clear & ~valid_cc, mi.Color3f(0), weight) # same rule for the coat
        weight = dr.select(active & (cos_theta_o > 0), weight, mi.Color3f(0))

        # Choose between the two top-level branches. The blend factor cancels in
        # each branch's weight (value and selection probability carry the same
        # factor), so no extra scaling is needed here.
        bs.wo = dr.select(take_diel, wo_diel, bs.wo)
        bs.pdf = dr.select(take_diel, pdf_diel, bs.pdf)
        bs.eta = dr.select(take_diel, eta_diel, mi.Float(1.0))
        bs.sampled_type = dr.select(take_diel, type_diel, bs.sampled_type)
        bs.sampled_component = dr.select(take_diel, mi.UInt32(2), bs.sampled_component)
        weight = dr.select(take_diel, weight_diel, weight)

        return bs, dr.select(active, weight, mi.Color3f(0))


    def fresnel_schlick(self, cos_theta, base_colour, metallic, specular):
        """
        Applies Fresnel Schlick approximation equation.
            F=F0​+(1−F0​)(1−cosθ)5
        """
        # F0 blended by metallic parameter
        f0_dielectric = mi.Color3f(0.08 * specular) # Reflectance at normal incidence; 0.08 * specular is the Disney/Blender convention.
        f0 = f0_dielectric * (1 - metallic) + base_colour * metallic
        # Case 1: Dialectric = Metallic 0, uses 0.08 * specular reflectance
        # Case 2: Metals = Metallic 1, uses base_colour
        return f0 + (1 - f0) * dr.power(dr.maximum(1 - cos_theta, 0), 5) # Schlick's approximation result

    def eval(self, ctx, si, wo, active=True):
        """
        Evaluates the BSDF value for a given incoming and outgoing direction
        without generating a new sample. It returns how much light is reflected
        from the incoming direction si.wi towards the outgoing direction wo.
        """

        cos_theta_i = mi.Frame3f.cos_theta(si.wi)  #incoming ray direction n⋅ωi
        cos_theta_o = mi.Frame3f.cos_theta(wo) # outgoing ray direction n⋅ωo
        h = dr.normalize(si.wi + wo) #reconstructs halfway vector microfacet normal
        cos_theta_h = dr.dot(si.wi, h) # angle between incoming ray and microfacet normal ωi​⋅h

        base_colour = self._base_colour_at(si, active)
        roughness = self._roughness_at(si, active)
        metallic = self._metallic_at(si, active)
        specular = self._specular_at(si, active)
        anisotropic = self._anisotropic_at(si, active)
        transmission = self._transmission_at(si, active) # opaque lobes only carry (1 - transmission) of the energy
        has_specular = (specular > 0) | (metallic > 0)

        F = dr.select(has_specular, self.fresnel_schlick(cos_theta_h, base_colour, metallic, specular), mi.Color3f(0)) # specular: Fresnel at the half-vector
        F_diffuse_gate = dr.select(has_specular, self.fresnel_schlick(cos_theta_i, base_colour, metallic, specular), mi.Color3f(0))
        # diffuse: gate by what actually reflected at the surface, not the half-vector

        if self.diffuse_model == "burley":
            """
            Burley (2012) diffuse retro-reflection term, multiplied on top of
            the existing Fresnel energy-conservation gate above (a deliberate
            combination of two separate ideas, not something either source
            specifies together). At exact normal incidence FD_i=FD_o=1
            always, recovering plain Lambertian regardless of roughness.
            Away from normal incidence: FD90<1 (low roughness) gives mild
            grazing darkening; FD90>1 (high roughness) gives the
            characteristic grazing brightening this term is known for.
            Reuses cos_theta_h already computed above for the specular
            Fresnel term, since cos_theta_d = dot(wi,h) = dot(wo,h) by
            definition of the half-vector.
            """
            fd90 = 0.5 + 2.0 * roughness * cos_theta_h * cos_theta_h
            fd_i = 1.0 + (fd90 - 1.0) * dr.power(dr.maximum(1.0 - cos_theta_i, 0.0), 5)
            fd_o = 1.0 + (fd90 - 1.0) * dr.power(dr.maximum(1.0 - cos_theta_o, 0.0), 5)
        else:
            fd_i = mi.Float(1.0)
            fd_o = mi.Float(1.0)

        diffuse = (
            base_colour * dr.inv_pi * cos_theta_o * (1 - F_diffuse_gate) * (1 - metallic) * fd_i * fd_o
        )


        specular_term = dr.select(has_specular, self.eval_specular(si, wo, roughness, anisotropic, active) * F, mi.Color3f(0))
        # renamed from `specular` to avoid clashing with the specular *parameter* above

        # Sheen — added alongside diffuse (Disney 2012). Deliberately NOT behind
        # the F_diffuse_gate above: that gate is this renderer's own addition,
        # Disney applies no such gate to sheen.
        sheen = self._sheen_at(si, active)
        sheen_tint = self._sheen_tint_at(si, active)
        fh = dr.power(dr.maximum(1.0 - cos_theta_h, 0.0), 5) # Schlick weight at wi.h
        sheen_term = (self._sheen_colour(base_colour, sheen_tint)
                        * sheen * fh * (1 - metallic) * cos_theta_o)

        # Clearcoat — narrower second specular lobe: GTR1 instead of GGX,
        # fixed IOR 1.5 (F0 = 0.04), fixed G roughness 0.25. The 0.25 scale is
        # Disney's own fixed coefficient for this lobe.
        clearcoat = self._clearcoat_at(si, active)
        cc_alpha = self._clearcoat_alpha(self._clearcoat_gloss_at(si, active))
        cos_theta_h_n = mi.Frame3f.cos_theta(h) # n.h — NOT cos_theta_h, which is wi.h
        d_cc = self._gtr1_D(cos_theta_h_n, cc_alpha)
        g_cc = mi.MicrofacetDistribution(
            mi.MicrofacetType.GGX, mi.Float(0.25), mi.Float(0.25), True).G(si.wi, wo, h)
        f_cc = 0.04 + 0.96 * fh # Schlick, F0 = 0.04 for a 1.5-IOR coat
        clearcoat_term = mi.Color3f(
            0.25 * clearcoat * d_cc * g_cc * f_cc
            / (4.0 * dr.maximum(cos_theta_i * cos_theta_o, 1e-7)) * cos_theta_o
        )

        return dr.select(active & (cos_theta_i > 0) & (cos_theta_o > 0),
            (diffuse + specular_term + sheen_term + clearcoat_term) * (1.0 - transmission),
            mi.Color3f(0)
        )

    def eval_specular(self, si, wo, roughness, anisotropic, active=True):
        """
        Evaluates the GGX microfacet specular BRDF (without Fresnel)
        for a given incoming and outgoing direction. Evaluated in the
        tangent-aligned frame so the two directional roughnesses line up
        with the surface's UV parameterisation.
        """

        cos_theta_i = mi.Frame3f.cos_theta(si.wi)  #incoming ray direction n⋅ωi
        cos_theta_o = mi.Frame3f.cos_theta(wo)  #outgoing ray direction n⋅ωo
        # Z is unchanged by the tangent rotation, so both cosines stay valid

        tangent = self._tangent_local(si)
        wi_t = self._to_tangent(si.wi, tangent)
        wo_t = self._to_tangent(wo, tangent)
        h = dr.normalize(wi_t + wo_t) # Halfway vector microfacet normal, tangent-aligned

        # GGX microfacet distribution
        alpha_u, alpha_v = self._alphas(roughness, anisotropic)
        distr = mi.MicrofacetDistribution(
            mi.MicrofacetType.GGX, alpha_u, alpha_v, True
        ) # MicrofacetDistribution : GGX Model object from Mitsuba

        D = distr.eval(h) # D : microfacet distribution (high bright, low dimmed)
        G = distr.G(wi_t, wo_t, h) # G : Visibility of microfacets (masking, shadowing)

        # Specular value
        specular = D * G / (4.0 * dr.maximum(cos_theta_i * cos_theta_o, 1e-7)) * cos_theta_o # GGX BRDF equation without F, dr.maximum avoids div zero

        return dr.select(
            active & (cos_theta_i > 0) & (cos_theta_o > 0),
            mi.Color3f(specular),
            mi.Color3f(0),
        ) # Checks alive rays and above the surface as valid, returns specular BRDF

    def pdf(self, ctx, si, wo, active=True):
        """
        Returns the probability density that the BSDF's sample() function
        would generate the outgoing direction wo.
        """
        cos_theta_i = mi.Frame3f.cos_theta(si.wi) #incoming ray direction n⋅ωi
        cos_theta_o = mi.Frame3f.cos_theta(wo) #outgoing ray direction n⋅ωo

        roughness = self._roughness_at(si, active)
        metallic = self._metallic_at(si, active)

        specular = self._specular_at(si, active)
        anisotropic = self._anisotropic_at(si, active)
        transmission = self._transmission_at(si, active)
        spec_prob = self._spec_prob(metallic, specular)
        clearcoat = self._clearcoat_at(si, active)
        cc_gloss = self._clearcoat_gloss_at(si, active)
        cc_alpha = self._clearcoat_alpha(cc_gloss)
        cc_prob = self._clearcoat_prob(clearcoat, cc_gloss)
        p_clear = cc_prob
        p_spec = spec_prob * (1.0 - cc_prob)
        p_diff = (1.0 - spec_prob) * (1.0 - cc_prob)

        alpha_u, alpha_v = self._alphas(roughness, anisotropic)
        distr = mi.MicrofacetDistribution(
            mi.MicrofacetType.GGX, alpha_u, alpha_v, True
        ) # MicrofacetDistribution : GGX Model object from Mitsuba

        tangent = self._tangent_local(si)
        wi_t = self._to_tangent(si.wi, tangent)
        wo_t = self._to_tangent(wo, tangent)
        wi_hat_t = dr.mulsign(wi_t, cos_theta_i) # Stores incoming direction
        h = dr.normalize(wi_t + wo_t) # Halfway vector microfacet normal, tangent-aligned
        cos_theta_i_val = dr.maximum(cos_theta_i, 1e-7) # Clamp to avoid division by zero
        spec_pdf = dr.maximum(
            distr.eval(h) * distr.smith_g1(wi_hat_t, h) / (4 * cos_theta_i_val), 0
        )

        diff_pdf = mi.warp.square_to_cosine_hemisphere_pdf(wo) # Probability of chosen direction
        cc_pdf = self._clearcoat_pdf(si, wo, cc_alpha) # coat lobe density
        # Must mirror sample() exactly — any divergence here is a silent MIS bug.
        pdf_val = (p_clear * cc_pdf + p_spec * spec_pdf + p_diff * diff_pdf) * (1.0 - transmission) # probability of even taking the opaque branch


        return dr.select(
            active & (cos_theta_i > 0) & (cos_theta_o > 0),
            pdf_val,
            mi.Float(0)
        ) # If the directions are physically valid return the PDF

    def eval_pdf(self, ctx, si, wo, active=True):
        """
        Evaluates both the BSDF value and the PDF for the same
        outgoing direction in a single function call.
        """
        return self.eval(ctx, si, wo, active), self.pdf(ctx, si, wo, active)

    def traverse(self, callback):
        pass

    def to_string(self):
        return f"PrincipledBSDF[base_colour={self.base_colour}, roughness={self.roughness}, metallic={self.metallic}, specular={self.specular}, anisotropic={self.anisotropic}, diffuse_model={self.diffuse_model}]"


mi.register_bsdf("principled_bsdf", lambda props: PrincipledBSDF(props)) # Register PrincipledBSDF class (creates instance)
print("Principled BSDF registered")
