import mitsuba as mi
import drjit as dr
import os
import numpy as np
import math

class PhysicalCamera(mi.ProjectiveCamera):
    def __init__(self, props):
        mi.Sensor.__init__(self, props)
        self.aperture_radius = props.get("aperture_radius", 0.0)
        self.focus_distance_val = props.get("focus_distance", 1.0)
        self.fov = props.get("fov", 60.0)
        self.aperture_blades = int(props.get("aperture_blades", 0))
        # 0 = circular (default, unchanged behaviour). >=3 = polygonal bladed bokeh with this many sides.
        self.aperture_rotation = dr.deg2rad(props.get("aperture_rotation", 0.0)) # optional rotation of the polygon, degrees

        film_size = self.film().size()
        aspect = film_size.x / film_size.y
        # tan(half-fov) gives the film-plane half-extent at z=1 in camera space —
        # standard perspective setup
        # sensor already uses internally.
        self.tan_fov = dr.tan(dr.deg2rad(self.fov) / 2.0)
        self.aspect = aspect

    def needs_aperture_sample(self):
        return True

    def sample_ray(self, time, sample1, sample2, sample3, active=True):
        x = -(2.0 * sample2.x - 1.0) * self.tan_fov
        y = -(2.0 * sample2.y - 1.0) * self.tan_fov / self.aspect
        d_cam = dr.normalize(mi.Vector3f(x, y, 1.0))



        t_focus = self.focus_distance_val / d_cam.z
        focus_point_cam = d_cam * t_focus

        lens_point_cam = self._sample_aperture(sample3) * self.aperture_radius
        lens_origin_cam = mi.Point3f(lens_point_cam.x, lens_point_cam.y, 0.0)

        new_dir_cam = dr.normalize(focus_point_cam - lens_origin_cam)


        trafo = self.world_transform()
        origin_world = trafo @ mi.Point3f(lens_origin_cam)      # force Point3f: translation applied
        dir_cam_vec  = mi.Vector3f(new_dir_cam)                 # force Vector3f explicitly
        dir_world = dr.normalize(trafo @ dir_cam_vec)           # now @ sees a true Vector3f


        ray = mi.Ray3f(o=origin_world, d=dir_world, time=time, wavelengths=mi.Color0f())

        return ray, mi.Color3f(1.0)

    def _sample_aperture(self, sample3):
        """
        Samples a point in the unit aperture (before scaling by
        aperture_radius). Circular when aperture_blades < 3 - identical to
        the original disc sampling. Polygonal ("bladed bokeh") otherwise:
        splits the polygon into N triangular wedges, picks one via the
        same stratified-remainder technique used in envmap.py's
        sample_direction, then samples uniformly within it.
        """
        if self.aperture_blades < 3:
            return mi.warp.square_to_uniform_disk_concentric(mi.Point2f(sample3))

        n = self.aperture_blades
        s = sample3.x * n
        k = dr.floor(s)
        f = s - k  # fractional part, reused as one barycentric coordinate

        theta0 = (2.0 * math.pi / n) * k + self.aperture_rotation
        theta1 = theta0 + (2.0 * math.pi / n)
        v1 = mi.Point2f(dr.cos(theta0), dr.sin(theta0))
        v2 = mi.Point2f(dr.cos(theta1), dr.sin(theta1))

        sqrt_f = dr.sqrt(f)
        v = sample3.y
        return v1 * (sqrt_f * (1.0 - v)) + v2 * (sqrt_f * v)

    def sample_ray_differential(self, time, sample1, sample2, sample3, active=True):
        ray, weight = self.sample_ray(time, sample1, sample2, sample3, active)
        ray_diff = mi.RayDifferential3f(ray)
        ray_diff.has_differentials = False
        return ray_diff, weight

mi.register_sensor("physical_camera", lambda props: PhysicalCamera(props))
print("Physical Camera Registered")
