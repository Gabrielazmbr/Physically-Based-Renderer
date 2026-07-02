#!/usr/bin/env -S uv run --script

import drjit as dr
import mitsuba as mi

mi.set_variant("llvm_ad_rgb")

# Simulate 5 rays hitting a scene
# Some hit a surface, some miss
hit_distance = mi.Float(0.5, 1e38, 0.3, 1e38, 2.1)  # 1e38 = infinity

# A ray "hit something" if distance is less than infinity
active = hit_distance < 1e37

print("Hit distances:", hit_distance)
print("Did hit:", active)

# If hit : colour the pixel based on distance (closer = brighter)
# If miss : return black (background)
brightness = 1.0 / hit_distance  # closer hits are brighter
pixel_colour = dr.select(active, brightness, mi.Float(0))

print("Pixel colours:", pixel_colour)

# fire rays, check what they hit, return black for misses
