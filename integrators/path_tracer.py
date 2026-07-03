import drjit as dr
import mitsuba as mi

mi.set_variant("llvm_ad_rgb")


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

        while active:
            # Step 1: Intersect rays into the scene
            si = scene.ray_intersect(ray, active)
            active = active & si.is_valid()

            # Adds emission from directly visible emitters (lights)
            result += throughput * si.emitter(scene).eval(si, active)

            # Step 2: Calculates direct illumination
            ds, emitter_radiance = scene.sample_emitter_direction(
                si, sampler.next_2d(), True, active
            )
            bsdf = si.bsdf(ray)
            wo = si.to_local(ds.d)
            bsdf_val = bsdf.eval(bsdf_ctx, si, wo, active)
            result += throughput * bsdf_val * emitter_radiance

            # Step 3: Sample new direction for next bounce (Indirect Ilumination)
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

            depth += 1

        return dr.select(si.is_valid(), result, mi.Color3f(0)), si.is_valid(), []

    def aov_names(self) -> list[str]:
        return []

    def to_string(self) -> str:
        return "_"


mi.register_integrator("PathTracer", lambda props: PathTracer(props))
