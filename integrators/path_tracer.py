import drjit as dr
import mitsuba as mi

"""
The class inherits from Mitsuba’s SamplingIntegrator.
Mitsuba expects: radiance, valid-ray mask, AOV values.
It creates a new integrator (algorithm that computes incoming radiance).
It implements a Monte Carlo Path Tracer.
"""

class PathTracer(mi.SamplingIntegrator):
    def __init__(self, props): #props ships max_depth and rr_depth values
        super().__init__(props)
        #Path-control
        self.max_depth = props.get("max_depth", 8) # The maximum number of bounces allowed for a ray.
        self.rr_depth = props.get("rr_depth", 3) # Russian Roulette starts after bounce 3.

        #Output
        self.with_aovs = props.get("with_aovs", False) # Handles AOVs if asked
        self.firefly_clamp = props.get("firefly_clamp", 0.0) # Caps any single sample contribution to a pixel. 0.0 = disabled (default).

        #Visibility
        self.transparent_shadows = bool(props.get("transparent_shadows", False)) # Manage objects shadow visibility.
        self.max_transparent_shadow_depth = int(props.get("max_transparent_shadow_depth", 8)) # Cap on pass-throughs per shadow ray.
        self.hide_from_camera = props.get("hide_from_camera", "") # Hide objects from the camera's view.
        self.opaque_shadow_shapes = props.get("opaque_shadow_shapes", "") # Define shapes that are opaque for shadow purposes.

    @dr.syntax
    # transforms the Python control flow into vectorised Dr.Jit operations (kernels)
    def sample(
        self,
        scene: mi.Scene, # Object scene
        sampler: mi.Sampler, # Random number generator for every bounce
        ray: mi.RayDifferential3f, # Rays
        medium: mi.Medium = None, # Mitsuba representation for volumes (like smoke or water) that interact with light
        active: mi.Bool = True, # Parameter for masking active rays vs dead ones (False)
    ) -> tuple[mi.Color3f, mi.Bool, list]:
        # RGB values / Validator for rays that hit a surface (contributes) / AOVs

        """
        Performs Monte Carlo path tracing for a camera ray and returns its
        radiance contribution. The function evaluates light transport through
        multiple surface interactions using BSDF sampling, Next Event Estimation
        (NEE), Multiple Importance Sampling (MIS), and Russian Roulette path
        termination.
        It uses dr.select() and mask operations instead of ordinary Python if
        statements.
        """
        # Initialization
        ray = mi.Ray3f(ray) # Converts to standard mitsuba ray

        #Main Path State
        throughput = mi.Color3f(1.0) # Weight carried by the path. Energy starts at 100%
        result = mi.Color3f(0.0) # Accumulated radiance. Starts in 0 and every contribution adds to it.
        depth = mi.UInt32(0) # Counts bounces. Starts at 0 and increments for each bounce.
        active = mi.Bool(active) # Boolean mask that traces alive rays

        # Tracking of previous interaction for MIS
        prev_si = dr.zeros(mi.Interaction3f) # Stores previous surface interaction
        prev_bsdf_pdf = mi.Float(1.0) # Stores probability of previous BSDF sample
        prev_delta = mi.Bool(True) # Boolean that searches for perfect specular bounces on previous interaction.
        # Delta has zero probability everywhere except one (or a finite number of) exact direction.

        valid_ray = mi.Bool(scene.environment() is not None) # If environment light (HDRI) True then rays that miss geo are valid too.

        si = dr.zeros(mi.SurfaceInteraction3f) # Uses dr.jit zero-initialized array to store intersection data (position, normal, uv, bsdf, emitter, etc)
        bsdf_ctx = mi.BSDFContext() # Provides context of the model being used to sample the BSDF
        # Types of transport: radiance transport (light to camera), importance transport (camera to light - the one used)
        # Types of scattering: reflection, transmission

        # AOV accumulators, captured once from the primary ray's first hit only,
        # Default to 0, which is also the correct value on a miss.
        aov_albedo = mi.Color3f(0.0)
        aov_normal = mi.Vector3f(0.0)
        aov_depth = mi.Float(0.0)

        hidden_shapes = [] # Uses shape IDs to identify which shapes are hidden from the camera's view.
        if len(self.hide_from_camera) > 0:
            ids = {s.strip() for s in self.hide_from_camera.split(',') if s.strip()}
            hidden_shapes = [s for s in scene.shapes() if s.id() in ids]

        opaque_shadow_shapes = [] # Uses uses BSDF IDs to identify which shapes are opaque for shadow purposes.
        if self.transparent_shadows and len(self.opaque_shadow_shapes) > 0:
            # Matched by BSDF id becauseMitsuba merges compatible meshes at
            # load time, anda merged shape loses its own id while keeping its BSDF reference.
            ids = {s.strip() for s in self.opaque_shadow_shapes.split(',') if s.strip()}
            opaque_shadow_shapes = [s for s in scene.shapes()
                                    if s.bsdf() is not None and s.bsdf().id() in ids]


        while active:
            # Step 1: Intersect current ray
            si = scene.ray_intersect(ray, active) # Test for an intersection and return detailed information
            # It finds where a ray hits first. BVH (Bounding Volume Hierarchy) happens here (narrows down triangle candidates)
            # It uses SurfaceInteraction3f (si) to retain necessary data.


            # Step 2: BSDF Sampling, evaluate emitter hit via BSDF sample
            # Uses MIS weight from previous bounce.
            # Calculates the probability of reaching the light by BSDF sampling and Direct sampling.
            ds_emitter = mi.DirectionSample3f(scene, si, prev_si) # Stores data from path A (pre_si) to B (si): direction, distance, pdf, which emitter

            em_pdf = dr.select(
                ~prev_delta,
                scene.pdf_emitter_direction(prev_si, ds_emitter, ~prev_delta),
                mi.Float(0),
            ) # Computes Emitter PDF if not delta case. Measures probability on tracing a path using light sampling over BSDF sampling.

            mis_bsdf = dr.select(
                prev_delta, mi.Float(1), self.mis_weight(prev_bsdf_pdf, em_pdf)
            ) # Compares BSDF PDF against Emitter PDF. Adds appropiate weight to each method using mis_weight() power heuristic.

            bsdf_hit_contrib = throughput * si.emitter(scene).eval(si, active) * mis_bsdf
            # This line works for several cases:
            # a ray hits an area-light surface;
            # a ray misses geometry and reaches the environment;
            # a ray hits an ordinary non-emissive surface, whose emitter evaluation returns zero.

            bsdf_hit_contrib = dr.select(
                self.firefly_clamp > 0,
                dr.minimum(bsdf_hit_contrib, self.firefly_clamp),
                bsdf_hit_contrib,
            )
            if len(hidden_shapes) > 0:
                # If a hit shape is listed in hide_from_camera, the code suppresses emission only when depth == 0
                on_hidden = mi.Bool(False)
                for shp in hidden_shapes:
                    on_hidden |= (si.shape == shp)
                bsdf_hit_contrib = dr.select((depth == 0) & on_hidden,
                                                mi.Color3f(0.0), bsdf_hit_contrib)

            result += bsdf_hit_contrib
            # On new path: energy lost along the path so far * radiance of emitter (from surface) * MIS weight

            # Update valid_ray
            valid_ray |= active & si.is_valid()

            # Continue scattering only when another segment fits within the
            # configured path-depth budget. Mitsuba defines max_depth=1 as
            # directly visible emitters only, max_depth=2 as one-bounce direct
            # illumination, and so on.
            active = active & si.is_valid() & ((depth + 1) < self.max_depth)


            # Step 3: NEE: sample emitter direction
            bsdf = si.bsdf(ray) # Finds material attached to the surface

            # AOV capture : depth == 0 is true for every lane on the loop's
            # first pass, whether that ray hit or missed. Missed rays simply
            # keep the 0.0 default from initialization.
            first_hit = active & (depth == 0)
            aov_albedo = dr.select(first_hit, bsdf.eval_diffuse_reflectance(si, first_hit), aov_albedo)
            aov_normal = dr.select(first_hit, si.sh_frame.n, aov_normal)
            aov_depth = dr.select(first_hit, si.t, aov_depth)

            active_em = active & (depth < self.max_depth) # Masks rays that are still alive


            ds, emitter_radiance = scene.sample_emitter_direction(
                si, sampler.next_2d(), not self.transparent_shadows, active_em
            ) # NEE Sampling: Chooses a direct path (ds) to a light from surface. Stores radiance arriving from light (emitter_radiance).
            # transparent_shadows = False : Mitsuba samples the emitter and tests visibility.
            # transparent_shadows = True: Mitsuba samples the emitter without testing visibility. The custom integrator performs its own visibility walk.

            active_em &= ds.pdf > 0 # Checks if lights can be reached, if not it disables NEE contribution for the ray.

            if self.transparent_shadows:
                # If transparent shadows are enabled,
                # the sampled world-space direction is converted into the material’s local shading frame
                active_em &= ~self._shadow_blocked(scene, si, ds, active_em, opaque_shadow_shapes)




            wo = si.to_local(ds.d) # Transform coordinates from world (light sampling) to local (to then evaluate BSDF locally)
            bsdf_val = bsdf.eval(bsdf_ctx, si, wo, active_em) # Evaluates BSDF , reflection towards camera
            bsdf_pdf = bsdf.pdf(bsdf_ctx, si, wo, active_em) # Computes BSDF PDF. Measures probability on tracing a path using BSDF sampling over light sampling.
            mis_em = dr.select(ds.delta, mi.Float(1), self.mis_weight(ds.pdf, bsdf_pdf)) # Compares Emitter PDF against BSDF PDF. Adds appropiate weight to each method using mis_weight() power heuristic.


            nee_contrib = throughput * bsdf_val * emitter_radiance * mis_em #Now the direct-light contribution
            nee_contrib = dr.select(
                self.firefly_clamp > 0,
                dr.minimum(nee_contrib, self.firefly_clamp),
                nee_contrib,
            ) # firefly_clamp caps the per-sample contribution before it's masked/added, when enabled
            result += dr.select(active_em, nee_contrib, mi.Color3f(0))
            # On new path: energy lost along the path so far * radiance of emitter (from surface) * MIS weight, explicitly masks NEE contribution


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
            bsdf_sample.sampled_type & mi.UInt32(mi.BSDFFlags.Delta) != 0) # Stores Delta event if that is the case

            depth += 1 # Bounce count

        aovs = [aov_albedo.x, aov_albedo.y, aov_albedo.z, aov_normal.x, aov_normal.y, aov_normal.z, aov_depth] if self.with_aovs else []
        # AOVs are flattened into the channel order expected by Mitsuba

        return (
            dr.select(valid_ray, result, mi.Color3f(0)),
            valid_ray,
            aovs,
        )
        # Final color, if valid ray = result (color), Invalid Ray = black
        # valid_ray = if path contributed or not
        # # AOVs: albedo (R,G,B), shading normal (X,Y,Z), depth (primary-ray hit distance)


    def mis_weight(self, pdf_a, pdf_b):
        """
        Implements power heuristic:
        w = pdf_a² / (pdf_a² + pdf_b²)
        """
        pdf_a *= pdf_a
        pdf_b *= pdf_b
        return dr.select(pdf_a > 0, pdf_a / (pdf_a + pdf_b), mi.Float(0))

    @dr.syntax
    def _shadow_blocked(self, scene, si, ds, active, opaque_shapes):
        """
        Did an opaque surface intersect this segment, after allowing selected
        delta-transmissive surfaces to be crossed?

        Mitsuba's built-in visibility test is binary and
        material blind. A pane of perfectly smooth glass blocks a shadow ray
        exactly like a wall, regardless of transmission=1.0. So NEE can never
        deliver direct sunlight into a glazed room: the only route is a BSDF
        sample that happens to refract into the sun's tiny solid angle by
        chance. Testing: the sunbeam only emerges at ~4000spp on Kitchen Scene.

        This function lets the shadow ray continue straight through glass,
        ignoring the refraction bend.

        Identifying glass: principled_bsdf advertises DeltaTransmission
        whenever transmission > 0 (set once at construction). Since this
        renderer only supports smooth transmission, that flag is unambiguous.

        Returns a mask: True where the light is genuinely occluded.
        """
        # spawn_ray_to() sets maxt just short of the target, so "no hit"
        # means the ray reached the light -- no manual distance bookkeeping.
        ray = si.spawn_ray_to(ds.p) # ray aimed at the emitter sample.
        blocked = mi.Bool(False)
        walking = mi.Bool(active)
        n_pass = mi.UInt32(0)

        while walking:
            si_sh = scene.ray_intersect(ray, walking)
            hit = si_sh.is_valid()

            flags = si_sh.bsdf().flags()
            transparent = (flags & mi.UInt32(+mi.BSDFFlags.DeltaTransmission)) != 0 # Each hit is classified from its BSDF flags.
            if len(opaque_shapes) > 0:
                forced_opaque = mi.Bool(False)
                for shp in opaque_shapes:
                    forced_opaque |= (si_sh.shape == shp)
                transparent = transparent & ~forced_opaque

            at_budget = (n_pass + 1) >= mi.UInt32(self.max_transparent_shadow_depth)

            # No hit: The sampled emitter is visible.
            # Opaque hit: The emitter is blocked.
            # Transparent hit below budget: Spawn another ray toward the same emitter point.
            # Transparent hit at budget: Treat as blocked.
            blocked |= walking & hit & ~transparent
            blocked |= walking & hit & transparent & at_budget

            walking &= hit & transparent & ~at_budget
            ray = si_sh.spawn_ray_to(ds.p)
            n_pass += 1

        return blocked



    def aov_names(self):
        if not self.with_aovs:
            return []
        return ["albedo.R", "albedo.G", "albedo.B", "normal.X", "normal.Y", "normal.Z", "depth.Y"]

    def to_string(self):
        return f"PathTracer[max_depth={self.max_depth}, rr_depth={self.rr_depth}]"


mi.register_integrator("path_tracer", lambda props: PathTracer(props)) # Register PathTracer class
print("Path Tracer registered")
