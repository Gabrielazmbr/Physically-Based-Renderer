import drjit as dr
import mitsuba as mi

'''
This class creates a new integrator (algorithm that computes incoming radiance).
It implements a Monte Carlo Path Tracer.
'''

class PathTracer(mi.SamplingIntegrator):
    def __init__(self, props): #props ships max_depth and rr_depth values
        super().__init__(props)
        self.max_depth = props.get("max_depth", 8) # The maximum number of bounces allowed for a ray.
        self.rr_depth = props.get("rr_depth", 3) # Russian Roulette starts after bounce 3.

    @dr.syntax
    # Decorator for handling Python loops (while statement) into vectorized kernels.
    def sample(
        self,
        scene: mi.Scene, # Object scene
        sampler: mi.Sampler, # Random number generator for every bounce
        ray: mi.RayDifferential3f, # Rays
        medium: mi.Medium = None, # Mitsuba representation for volumes (like smoke or water) that interact with light
        active: mi.Bool = True, # Parameter for masking active rays vs dead ones (False)
    ) -> tuple[mi.Color3f, mi.Bool, list]:
        # RGB values / Validator for rays that hit a surface (contributes) / AOVs

        # Initialization
        ray = mi.Ray3f(ray) # Standard mitsuba ray
        throughput = mi.Color3f(1.0) # Rays energy starts at 100%
        result = mi.Color3f(0.0) # Accumulated radiance. Starts in 0 and every contribution adds to it.
        depth = mi.UInt32(0) # Counts bounces
        active = mi.Bool(active) # Boolean mask that traces alive rays

        # Track previous interaction for MIS
        prev_si = dr.zeros(mi.Interaction3f) # Stores previous surface interaction
        prev_bsdf_pdf = mi.Float(1.0) # Stores probability of previous BSDF sample
        prev_delta = mi.Bool(True) # Boolean that search for perfect specular bounces.
        # Delta has zero probability everywhere except one (or a finite number of) exact direction.

        valid_ray = mi.Bool(scene.environment() is not None) # If environment light (HDRI) True then rays that miss geo are valid too.

        si = dr.zeros(mi.SurfaceInteraction3f) # Uses dr.jit zero-initialized array to store intersection data (position, normal, uv, bsdf, emitter, etc)
        bsdf_ctx = mi.BSDFContext() # Provides context of the model being used to sample the BSDF (Default mode for now)
        # Types of transport: radiance transport (light to camera), importance transport (camera to light - the one used)
        # Types of scattering: reflection, transmission

        while active:
            # Step 1: Intersect
            si = scene.ray_intersect(ray, active) # Test for an intersection and return detailed information
            # It finds where a ray hits first. BVH (Bounding Volume Hierarchy) happens here (narrows down triangle candidates)
            # It uses SurfaceInteraction3f (si) to retain necessary data.


            # Step 2: BSDF Sampling, evaluate emitter hit via BSDF sample
            # Uses MIS weight from previous bounce. Calculates the probability of reaching the light by BSDF sampling and Direct sampling.
            ds_emitter = mi.DirectionSample3f(scene, si, prev_si) # Stores data from path A (pre_si) to B (si): direction, distance, pdf, which emitter

            em_pdf = dr.select(
                ~prev_delta,
                scene.pdf_emitter_direction(prev_si, ds_emitter, ~prev_delta),
                mi.Float(0),
            ) # Computes Emitter PDF if not delta case. Measures probability on tracing a path using light sampling over BSDF sampling.

            mis_bsdf = dr.select(
                prev_delta, mi.Float(1), self.mis_weight(prev_bsdf_pdf, em_pdf)
            ) # Compares BSDF PDF against Emitter PDF. Adds appropiate weight to each method using mis_weight() power heuristic.

            result += throughput * si.emitter(scene).eval(si, active) * mis_bsdf
            # On new path: energy lost along the path so far * radiance of emitter (from surface) * MIS weight

            # Update valid_ray
            valid_ray |= active & si.is_valid()

            # Continue only if we hit something and depth allows
            active = active & si.is_valid() & (depth < self.max_depth)


            # Step 3: NEE: sample emitter direction
            bsdf = si.bsdf(ray) # Finds material attached to the surface
            active_em = active & (depth < self.max_depth) # Masks rays that are still alive

            ds, emitter_radiance = scene.sample_emitter_direction(
                si, sampler.next_2d(), True, active_em
            ) # NEE Sampling: Chooses a direct path (ds) to a light from surface. Stores radiance arriving from light (emitter_radiance).
            active_em &= ds.pdf > 0 # Checks if lights can be reached, if not it disables NEE contribution for the ray

            wo = si.to_local(ds.d) # Transform coordinates from world (light sampling) to local (to then evaluate BSDF locally)
            bsdf_val = bsdf.eval(bsdf_ctx, si, wo, active_em) # Evaluates BSDF , reflection towards camera
            bsdf_pdf = bsdf.pdf(bsdf_ctx, si, wo, active_em) # Computes BSDF PDF. Measures probability on tracing a path using BSDF sampling over light sampling.
            mis_em = dr.select(ds.delta, mi.Float(1), self.mis_weight(ds.pdf, bsdf_pdf)) # Compares Emitter PDF against BSDF PDF. Adds appropiate weight to each method using mis_weight() power heuristic.

            result += dr.select(
                active_em,
                throughput * bsdf_val * emitter_radiance * mis_em,
                mi.Color3f(0),
            ) # On new path: energy lost along the path so far * radiance of emitter (from surface) * MIS weight, explicitly masks NEE contribution

            # Step 4: BSDF sampling, choose next direction
            bsdf_sample, bsdf_weight = bsdf.sample(
                bsdf_ctx, si, sampler.next_1d(), sampler.next_2d(), active
            ) # BSDF Sample: Chooses and outgoing direction according to surface properties. Retains wo, pdf, flags, type etc.
            # BSDF weight: Scattering event contribution
            # Args: Context of the BSDF model, intersection data, random number to choose over possibilities, random number 2d to sample a direction, active flag for alive rays.

            throughput *= bsdf_weight # updates throughput energy
            ray = si.spawn_ray(si.to_world(bsdf_sample.wo)) # Creates new ray: Converts from local to world, then spawns a new ray and offsets it to avoid loops.



            # Step 5: Russian roulette
            rr_active = depth >= self.rr_depth # Mask rays with depth equal or bigger than rr_depth
            rr_prob = dr.minimum(dr.max(throughput), 0.95) # survival probability (min and max)
            rr_continue = sampler.next_1d() < rr_prob # random choice
            throughput[rr_active] *= dr.rcp(rr_prob) # Compensate surviving rays taking into account survival rate
            active &= ~rr_active | rr_continue # update active rays
            active &= dr.max(throughput) > 0 # Removes rays with no energy

            # Update previous bounce info for next iteration
            prev_si = mi.Interaction3f(si) # Current itration becomes prev
            prev_bsdf_pdf = bsdf_sample.pdf # PDF of the sampled BSDF direction
            prev_delta = mi.Bool(
                bsdf_sample.sampled_type & mi.UInt32(mi.BSDFFlags.Delta) != 0
            ) # Stores Delta event if that is the case

            depth += 1 # Bounce count

        return (dr.select(valid_ray, result, mi.Color3f(0)), valid_ray, [])
        # Final color, if valid ray = result (color), Invalid Ray = black
        # valid_ray = if path contributed or not
        # AOVS [] (empty)


    def mis_weight(self, pdf_a, pdf_b):
        '''
        Implements power heuristic:
        w = pdf_a² / (pdf_a² + pdf_b²)
        '''
        pdf_a *= pdf_a
        pdf_b *= pdf_b
        return dr.select(pdf_a > 0, pdf_a / (pdf_a + pdf_b), mi.Float(0))

    def aov_names(self):
        return []

    def to_string(self):
        return f"PathTracer[max_depth={self.max_depth}, rr_depth={self.rr_depth}]"


mi.register_integrator("path_tracer", lambda props: PathTracer(props)) # Register PathTracer class
