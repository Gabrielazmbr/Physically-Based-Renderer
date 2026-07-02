#!/usr/bin/env -S uv run --script

import drjit as dr
import mitsuba as mi

mi.set_variant("llvm_ad_rgb")

# Two types of surfaces — diffuse and mirror
# Each ray hits a different surface type
is_mirror = mi.Bool(True, False, True, False, True)

# Mirror reflects full energy, diffuse absorbs half
mirror_reflectance = mi.Float(1.0, 1.0, 1.0, 1.0, 1.0)
diffuse_reflectance = mi.Float(0.5, 0.5, 0.5, 0.5, 0.5)

throughput = dr.select(is_mirror, mirror_reflectance, diffuse_reflectance)

print("Is mirror:", is_mirror)
print("Throughput:", throughput)
