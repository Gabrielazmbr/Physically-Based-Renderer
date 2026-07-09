import drjit as dr
import mitsuba as mi


class PathTracer(mi.SamplingIntegrator):
    def __init__(self, props):
        super().__init__(props)
        self.max_depth = props.get("max_depth", 10)

    @dr.syntax
    def sample(
        self,
        scene: mi.Scene,
        sampler: mi.Sampler,
        ray: mi.RayDifferential3f,
        medium: mi.Medium = None,
        active: mi.Bool = True,
    ) -> tuple[mi.Color3f, mi.Bool, list]:

        ray = mi.Ray3f(ray)
        depth = mi.UInt32(0)
        throughput = mi.Color3f(1.0)
        result = mi.Color3f(0.0)
        active = mi.Bool(active)
        si = dr.zeros(mi.SurfaceInteraction3f)
        bsdf_ctx = mi.BSDFContext()

        prev_bsdf_pdf = mi.Float(1.0)
        prev_delta = mi.Bool(False)

        while active:
            # Step 1: Intersect rays into the scene
            si = scene.ray_intersect(ray, active)
            active = active & si.is_valid()

            # Step 2: Calculates direct illumination NEE
            ds, emitter_radiance = scene.sample_emitter_direction(
                si, sampler.next_2d(), True, active
            )  # ds.pdf : The emitter pdf when a BSDF ray hits a light

            bsdf = si.bsdf(ray)
            wo = si.to_local(ds.d)
            bsdf_val = bsdf.eval(bsdf_ctx, si, wo, active)

            # MIS : For the NEE contribution, gets the BSDF pdf for that direction and applies the weight
            bsdf_pdf = bsdf.pdf(bsdf_ctx, si, wo, active)

            # MIS computation, handles delta light case (point light, directional light) - 1.0.
            mis_em = dr.select(ds.delta, mi.Float(1), self.mis_weight(ds.pdf, bsdf_pdf))

            # Adds emission from directly visible emitters (lights) and weighted byt MIS.
            ds_prev = dr.zeros(mi.DirectionSample3f)
            em_pdf = scene.pdf_emitter_direction(si, ds_prev, active)
            mis_bsdf = dr.select(
                prev_delta, mi.Float(1), self.mis_weight(prev_bsdf_pdf, em_pdf)
            )
            result += throughput * si.emitter(scene).eval(si, active) * mis_bsdf

            result += throughput * bsdf_val * emitter_radiance * mis_em

            # Step 3: Sample new direction for next bounce (Indirect Ilumination) BSDF Sampling
            bsdf_sample, bsdf_weight = bsdf.sample(
                bsdf_ctx, si, sampler.next_1d(), sampler.next_2d(), active
            )
            throughput *= bsdf_weight
            ray = si.spawn_ray(si.to_world(bsdf_sample.wo))

            # Step 4: Russian roulette after depth 3
            active = active & (depth < self.max_depth)
            rr_active = depth >= 3
            rr_prob = dr.minimum(dr.max(throughput), 0.95)
            rr_continue = sampler.next_1d() < rr_prob
            throughput[rr_active] *= dr.rcp(rr_prob)
            active = active & (~rr_active | rr_continue)

            prev_bsdf_pdf = bsdf_sample.pdf
            prev_delta = mi.Bool(
                bsdf_sample.sampled_type & mi.UInt32(mi.BSDFFlags.Delta) != 0
            )

            depth += 1

        return dr.select(si.is_valid(), result, mi.Color3f(0)), si.is_valid(), []

    def mis_weight(self, pdf_a, pdf_b):
        """
        Balance heuristic function. Computes the MIS (Multiple Importance Sampling) weight for a given pair of pdfs.
        """
        pdf_a *= pdf_a
        pdf_b *= pdf_b
        return dr.select(pdf_a > 0, pdf_a / (pdf_a + pdf_b), mi.Float(0))

    def aov_names(self) -> list[str]:
        return []

    def to_string(self) -> str:
        return "_"


mi.register_integrator("PathTracer", lambda props: PathTracer(props))
