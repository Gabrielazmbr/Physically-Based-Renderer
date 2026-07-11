import drjit as dr
import mitsuba as mi


class PathTracer(mi.SamplingIntegrator):
    def __init__(self, props):
        super().__init__(props)
        self.max_depth = props.get("max_depth", 8)
        self.rr_depth = props.get("rr_depth", 3)

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
        throughput = mi.Color3f(1.0)
        result = mi.Color3f(0.0)
        depth = mi.UInt32(0)
        active = mi.Bool(active)

        # Track previous interaction for MIS
        prev_si = dr.zeros(mi.Interaction3f)
        prev_bsdf_pdf = mi.Float(1.0)
        prev_delta = mi.Bool(True)

        # Is the path valid (did it hit something or start from environment)
        valid_ray = mi.Bool(scene.environment() is not None)

        si = dr.zeros(mi.SurfaceInteraction3f)
        bsdf_ctx = mi.BSDFContext()

        while active:
            # Step 1: Intersect
            si = scene.ray_intersect(ray, active)

            # Step 2: Direct emission: evaluate emitter hit via BSDF sample
            # Uses MIS weight from previous bounce
            ds_emitter = mi.DirectionSample3f(scene, si, prev_si)
            em_pdf = dr.select(
                ~prev_delta,
                scene.pdf_emitter_direction(prev_si, ds_emitter, ~prev_delta),
                mi.Float(0),
            )
            mis_bsdf = dr.select(
                prev_delta, mi.Float(1), self.mis_weight(prev_bsdf_pdf, em_pdf)
            )
            result += throughput * si.emitter(scene).eval(si, active) * mis_bsdf

            # Update valid_ray
            valid_ray |= active & si.is_valid()

            # Continue only if we hit something and depth allows
            active = active & si.is_valid() & (depth < self.max_depth)

            # Step 3: NEE: sample emitter direction
            bsdf = si.bsdf(ray)
            active_em = active & (depth < self.max_depth)

            ds, emitter_radiance = scene.sample_emitter_direction(
                si, sampler.next_2d(), True, active_em
            )
            active_em &= ds.pdf > 0

            wo = si.to_local(ds.d)
            bsdf_val = bsdf.eval(bsdf_ctx, si, wo, active_em)
            bsdf_pdf = bsdf.pdf(bsdf_ctx, si, wo, active_em)
            mis_em = dr.select(ds.delta, mi.Float(1), self.mis_weight(ds.pdf, bsdf_pdf))
            result += dr.select(
                active_em,
                throughput * bsdf_val * emitter_radiance * mis_em,
                mi.Color3f(0),
            )

            # Step 4: BSDF sampling, choose next direction
            bsdf_sample, bsdf_weight = bsdf.sample(
                bsdf_ctx, si, sampler.next_1d(), sampler.next_2d(), active
            )
            throughput *= bsdf_weight
            ray = si.spawn_ray(si.to_world(bsdf_sample.wo))

            # Step 5: Russian roulette
            rr_active = depth >= self.rr_depth
            rr_prob = dr.minimum(dr.max(throughput), 0.95)
            rr_continue = sampler.next_1d() < rr_prob
            throughput[rr_active] *= dr.rcp(rr_prob)
            active &= ~rr_active | rr_continue
            active &= dr.max(throughput) > 0

            # Update previous bounce info for next iteration
            prev_si = mi.Interaction3f(si)
            prev_bsdf_pdf = bsdf_sample.pdf
            prev_delta = mi.Bool(
                bsdf_sample.sampled_type & mi.UInt32(mi.BSDFFlags.Delta) != 0
            )

            depth += 1

        return (dr.select(valid_ray, result, mi.Color3f(0)), valid_ray, [])

    def mis_weight(self, pdf_a, pdf_b):
        pdf_a *= pdf_a
        pdf_b *= pdf_b
        return dr.select(pdf_a > 0, pdf_a / (pdf_a + pdf_b), mi.Float(0))

    def aov_names(self):
        return []

    def to_string(self):
        return f"PathTracer[max_depth={self.max_depth}, rr_depth={self.rr_depth}]"


mi.register_integrator("path_tracer", lambda props: PathTracer(props))
