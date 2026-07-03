#!/usr/bin/env -S uv run --script

import drjit as dr
import mitsuba as mi

mi.set_variant("llvm_ad_rgb")

# Simulate rays bouncing through a scene
# Each bounce, some rays die (hit a light or get absorbed)
# Others survive and keep bouncing

# Start: all 5 rays alive, full energy
active = mi.Bool(True, True, True, True, True)
throughput = mi.Float(1.0, 1.0, 1.0, 1.0, 1.0)
accumulated_light = mi.Float(0.0, 0.0, 0.0, 0.0, 0.0)

print(" Simulating 3 bounces... ")

# Simulate surface absorption at each bounce
# Each surface absorbs some energy (like a dark or bright material)
absorption_per_bounce = [
    mi.Float(0.8, 0.5, 0.9, 0.3, 0.7),  # bounce 1 - material reflectance
    mi.Float(0.6, 0.8, 0.5, 0.9, 0.4),  # bounce 2
    mi.Float(0.7, 0.3, 0.8, 0.6, 0.9),  # bounce 3
]

# Light hit at each bounce (0 = no light, >0 = hit a light)
light_hit = [
    mi.Float(0.0, 0.0, 0.0, 5.0, 0.0),  # ray 4 hits light on bounce 1
    mi.Float(0.0, 3.0, 0.0, 0.0, 0.0),  # ray 2 hits light on bounce 2
    mi.Float(2.0, 0.0, 0.0, 0.0, 4.0),  # rays 1 and 5 hit light on bounce 3
]

for bounce in range(3):
    # Accumulate light where active rays hit a light source
    accumulated_light += dr.select(active, throughput * light_hit[bounce], mi.Float(0))

    # Multiply throughput by surface reflectance
    throughput *= dr.select(active, absorption_per_bounce[bounce], mi.Float(1))

    # Kill rays with very low throughput (Russian roulette simplified)
    active &= throughput > 0.1

    print(f"After bounce {bounce + 1}:")
    print(f"  Active rays: {active}")
    print(f"  Throughput:  {throughput}")
    print(f"  Light so far: {accumulated_light}")

print("\nFinal pixel colours:", accumulated_light)
