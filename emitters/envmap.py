#!/usr/bin/env -S uv run --script
import math
import numpy as np
import drjit as dr
import mitsuba as mi

"""
This class implements an infinite environment emitter that maps a HDR image onto a sphere
surrounding the scene. Performs luminance-based importance sampling to preferentially
sample brighter regions of the environment.
"""
class CustomEnvmap(mi.Emitter):
    def __init__(self, props):
        mi.Emitter.__init__(self, props)
        self.texture = mi.load_dict({
            "type": "bitmap",
            "filename": props["filename"],
            "raw": True,
            "filter_type": "bilinear",
            "wrap_mode": "repeat",
        })
        self.scale = props.get("scale", 1.0)
        self.importance = props.get("importance", True)  # switch: True=importance, False=uniform

        self.m_flags = mi.EmitterFlags.Infinite
        self.bsphere_radius = 1.0

        self.to_world = self.world_transform()
        self.to_world_inv = self.to_world.inverse()

        # Build the luminance CDF for importance sampling
        self.res_x, self.res_y = 256, 128
        bitmap = mi.Bitmap(props["filename"])
        img = np.array(bitmap, dtype=np.float32)
        H, W = img.shape[0], img.shape[1]
        by, bx = H // self.res_y, W // self.res_x
        small = img[:by*self.res_y, :bx*self.res_x].reshape(
            self.res_y, by, self.res_x, bx, -1).mean(axis=(1, 3))

        luminance = 0.2126*small[..., 0] + 0.7152*small[..., 1] + 0.0722*small[..., 2]
        theta = (np.arange(self.res_y) + 0.5) / self.res_y * math.pi
        sin_theta = np.sin(theta)[:, None]
        weighted = np.maximum(luminance * sin_theta, 1e-8).astype(np.float32)

        self.distribution = mi.DiscreteDistribution2D(weighted)

    def set_scene(self, scene):
        bbox = scene.bbox()
        self.bsphere_radius = dr.norm(bbox.max - bbox.min) * 0.5

    def _dir_to_uv(self, d):
        d_local = dr.normalize(mi.Vector3f(self.to_world_inv @ mi.Vector3f(d)))
        u = dr.atan2(d_local.x, -d_local.z) * (1.0 / (2.0 * math.pi))
        u = u - dr.floor(u)
        cos_v = dr.clamp(d_local.y, -1.0, 1.0)
        v = dr.acos(cos_v) * (1.0 / math.pi)
        return mi.Point2f(u, v)

    def _uv_to_dir(self, u, v):
        theta = v * math.pi
        phi = u * 2.0 * math.pi
        sin_theta, cos_theta = dr.sin(theta), dr.cos(theta)
        d_local = mi.Vector3f(sin_theta * dr.sin(phi), cos_theta, -sin_theta * dr.cos(phi))
        return dr.normalize(mi.Vector3f(self.to_world @ d_local))

    def _radiance(self, d, active):
        si_tex = dr.zeros(mi.SurfaceInteraction3f)
        si_tex.uv = self._dir_to_uv(d)
        return self.texture.eval(si_tex, active) * self.scale

    def eval(self, si, active=True):
        return self._radiance(dr.normalize(-si.wi), active)

    def sample_direction(self, it, sample, active=True):
        if not self.importance:
            # uniform baseline, unchanged from stage 3
            d = mi.warp.square_to_uniform_sphere(sample)
            pdf = mi.warp.square_to_uniform_sphere_pdf(d)
        else:
            # luminance importance sampling
            pos, pdf_pmf, remainder = self.distribution.sample(mi.Point2f(sample), active)
            u = (mi.Float(pos.x) + remainder.x) / self.res_x
            v = (mi.Float(pos.y) + remainder.y) / self.res_y
            d = self._uv_to_dir(u, v)

            sin_theta = dr.sin(v * math.pi)
            pdf = pdf_pmf * (self.res_x * self.res_y) / \
                  (2.0 * math.pi**2 * dr.maximum(sin_theta, 1e-4))

        ds = dr.zeros(mi.DirectionSample3f)
        ds.d = d
        ds.pdf = pdf
        ds.dist = 2.0 * self.bsphere_radius
        ds.p = it.p + d * ds.dist
        ds.n = -d
        ds.uv = self._dir_to_uv(d)
        ds.time = it.time
        ds.delta = mi.Bool(False)
        ds.emitter = mi.EmitterPtr(self)

        radiance = self._radiance(d, active)
        weight = dr.select(pdf > 0, radiance / dr.maximum(pdf, 1e-8), mi.Color3f(0))
        return ds, weight & active

    def pdf_direction(self, it, ds, active=True):
        d = dr.normalize(ds.d)
        if not self.importance:
            return dr.select(active, mi.warp.square_to_uniform_sphere_pdf(d), 0.0)

        uv = self._dir_to_uv(d)
        px = dr.minimum(mi.UInt32(uv.x * self.res_x), self.res_x - 1)
        py = dr.minimum(mi.UInt32(uv.y * self.res_y), self.res_y - 1)
        pdf_pmf = self.distribution.pdf(mi.Point2u(px, py), active)

        sin_theta = dr.sin(uv.y * math.pi)
        pdf = pdf_pmf * (self.res_x * self.res_y) / \
              (2.0 * math.pi**2 * dr.maximum(sin_theta, 1e-4))
        return dr.select(active, pdf, 0.0)

    def eval_direction(self, it, ds, active=True):
        return self._radiance(dr.normalize(ds.d), active)

    def to_string(self):
        return f"CustomEnvmap[importance={self.importance}, radius={self.bsphere_radius}]"
