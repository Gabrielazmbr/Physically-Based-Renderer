#!/usr/bin/env -S uv run --script
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mitsuba as mi
import drjit as dr

mi.set_variant('llvm_ad_rgb')

from bsdfs.principled import PrincipledBSDF
mi.register_bsdf("principled_bsdf", lambda props: PrincipledBSDF(props))

from mitsuba.chi2 import BSDFAdapter, ChiSquareTest, SphericalDomain

configs = [
    ("Diffuse (r=1.0, m=0.0)",  [1.0, 1.0, 1.0], 1.0, 0.0),
    ("Plastic (r=0.3, m=0.0)",  [0.2, 0.3, 0.8], 0.3, 0.0),
    ("Metal (r=0.3, m=1.0)", [0.95, 0.77, 0.33], 0.3, 1.0),
    ("Mixed (r=0.4, m=0.5)", [0.5, 0.5, 0.5], 0.4, 0.5),
]

all_passed = True

sample_func, pdf_func = BSDFAdapter("principled", """
    <rgb name="base_color" value="1.0, 1.0, 1.0"/>
    <float name="roughness" value="1.0"/>
    <float name="metallic" value="0.0"/>
""")
test3 = ChiSquareTest(
    domain=SphericalDomain(),
    sample_func=sample_func,
    pdf_func=pdf_func,
    sample_dim=3,
    res=201,
    ires=32
)
result3 = test3.run(0.01)
print(f"Mitsuba principled r=1.0 m=0.0: {'PASS' if result3 else 'FAIL'}")

sample_func, pdf_func = BSDFAdapter("principled", """
    <rgb name="base_color" value="0.95, 0.77, 0.33"/>
    <float name="roughness" value="0.1"/>
    <float name="metallic" value="1.0"/>
""")
test4 = ChiSquareTest(
    domain=SphericalDomain(),
    sample_func=sample_func,
    pdf_func=pdf_func,
    sample_dim=3,
    res=201,
    ires=32
)
result4 = test4.run(0.01)
print(f"Mitsuba principled r=0.1 m=1.0: {'PASS' if result4 else 'FAIL'}")



for name, colour, roughness, metallic in configs:
    print(f"\nTesting: {name}")

    adapter = BSDFAdapter("principled_bsdf", f"""
        <rgb name="base_colour" value="{colour[0]}, {colour[1]}, {colour[2]}"/>
        <float name="roughness" value="{roughness}"/>
        <float name="metallic" value="{metallic}"/>
    """)

    test = ChiSquareTest(
        domain=SphericalDomain(),
        sample_func=adapter[0],
        pdf_func=adapter[1],
        sample_dim=3,
        res=201,
        ires=32
    )

    result = test.run(0.01)
    status = "PASS" if result else "FAIL"
    print(f"  Chi-squared test: {status}")
    all_passed = all_passed and result


def run_chi2(name, xml, note=""):
    """Builds and runs one chi-squared test from a raw parameter XML block."""
    print(f"\nTesting: {name}")
    if note:
        print(f"  ({note})")
    adapter = BSDFAdapter("principled_bsdf", xml)
    test = ChiSquareTest(
        domain=SphericalDomain(),
        sample_func=adapter[0],
        pdf_func=adapter[1],
        sample_dim=3,
        res=201,
        ires=32
    )
    result = test.run(0.01)
    print(f"  Chi-squared test: {'PASS' if result else 'FAIL'}")
    return result


# Clearcoat / sheen sampling consistency.
# These matter because clearcoat introduced a THREE-way lobe partition
# (coat / specular / diffuse) into sample() and pdf(). A mismatch between
# those two is exactly what chi-squared detects and what the furnace test
# cannot see once the means agree.
extra_configs = [
    ("Clearcoat broad (cc=1.0, gloss=0.0)", """
        <rgb name="base_colour" value="0.8, 0.8, 0.8"/>
        <float name="roughness" value="1.0"/>
        <float name="metallic" value="0.0"/>
        <float name="specular" value="0.0"/>
        <float name="clearcoat" value="1.0"/>
        <float name="clearcoat_gloss" value="0.0"/>
     """, "coat + diffuse only; alpha=0.1 is well within grid resolution, expect PASS"),

    ("Clearcoat partial (cc=0.5, gloss=0.0)", """
        <rgb name="base_colour" value="0.8, 0.8, 0.8"/>
        <float name="roughness" value="1.0"/>
        <float name="metallic" value="0.0"/>
        <float name="specular" value="0.0"/>
        <float name="clearcoat" value="0.5"/>
        <float name="clearcoat_gloss" value="0.0"/>
     """, "partial coat probability: p_clear=0.125, tests the partition scales correctly"),

    ("Clearcoat + specular (cc=1.0, gloss=0.3, r=0.3)", """
        <rgb name="base_colour" value="0.2, 0.3, 0.8"/>
        <float name="roughness" value="0.3"/>
        <float name="metallic" value="0.0"/>
        <float name="specular" value="0.5"/>
        <float name="clearcoat" value="1.0"/>
        <float name="clearcoat_gloss" value="0.3"/>
     """, "ALL THREE lobes active — the config most likely to expose a partition bug"),

    ("Clearcoat + metal (cc=1.0, gloss=0.3, r=0.3, m=1.0)", """
        <rgb name="base_colour" value="0.95, 0.77, 0.33"/>
        <float name="roughness" value="0.3"/>
        <float name="metallic" value="1.0"/>
        <float name="clearcoat" value="1.0"/>
        <float name="clearcoat_gloss" value="0.3"/>
     """, "no diffuse lobe: p_diff=0, so the partition is coat 0.25 / specular 0.75"),

    ("Clearcoat sharp (cc=1.0, gloss=1.0)", """
        <rgb name="base_colour" value="0.8, 0.8, 0.8"/>
        <float name="roughness" value="1.0"/>
        <float name="metallic" value="0.0"/>
        <float name="specular" value="0.0"/>
        <float name="clearcoat" value="1.0"/>
        <float name="clearcoat_gloss" value="1.0"/>
     """, "alpha=0.001 is far narrower than the 201x201 grid — a FAIL here is a harness "
          "resolution limit, same class as Mitsuba's own r=0.1 m=1.0 failure above"),

    ("Sheen (null test)", """
        <rgb name="base_colour" value="0.2, 0.3, 0.8"/>
        <float name="roughness" value="1.0"/>
        <float name="metallic" value="0.0"/>
        <float name="specular" value="0.0"/>
        <float name="sheen" value="1.0"/>
        <float name="sheen_tint" value="1.0"/>
     """, "sheen lives only in eval(), which chi-squared never touches — this cannot "
          "detect a sheen error, it only guards against sheen leaking into sample()/pdf()"),
]

for name, xml, note in extra_configs:
    all_passed = run_chi2(name, xml, note) and all_passed

sharp_xml = """
    <rgb name="base_colour" value="0.8, 0.8, 0.8"/>
    <float name="roughness" value="1.0"/>
    <float name="metallic" value="0.0"/>
    <float name="specular" value="0.0"/>
    <float name="clearcoat" value="1.0"/>
    <float name="clearcoat_gloss" value="1.0"/>
"""
print("\n=== Resolution sweep: clearcoat gloss=1.0 (alpha=0.001) ===")
for res, ires in [(201, 32), (401, 32), (801, 32), (1601, 32)]:
    print(f"\n  res={res}, ires={ires}")
    adapter = BSDFAdapter("principled_bsdf", sharp_xml)
    t = ChiSquareTest(domain=SphericalDomain(), sample_func=adapter[0],
                      pdf_func=adapter[1], sample_dim=3, res=res, ires=ires)
    print(f"   {'PASS' if t.run(0.01) else 'FAIL'}")

# gloss=0.95 fails differently from gloss=1.0: its PDF sum is only 2% high,
# so the test runs and rejects rather than bailing early. If that failure is
# also quadrature, refining the grid should flip it to PASS. If it stays
# rejected at high resolution, something real is going on at narrow alpha.
print("\n=== Resolution sweep: clearcoat gloss=0.95 (alpha=0.006) ===")
gloss95_xml = """
    <rgb name="base_colour" value="0.8, 0.8, 0.8"/>
    <float name="roughness" value="1.0"/>
    <float name="metallic" value="0.0"/>
    <float name="specular" value="0.0"/>
    <float name="clearcoat" value="1.0"/>
    <float name="clearcoat_gloss" value="0.95"/>
"""
for res, ires in [(201, 32), (401, 32), (801, 32)]:
    print(f"\n  res={res}, ires={ires}")
    adapter = BSDFAdapter("principled_bsdf", gloss95_xml)
    t = ChiSquareTest(domain=SphericalDomain(), sample_func=adapter[0],
                      pdf_func=adapter[1], sample_dim=3, res=res, ires=ires)
    print(f"   {'PASS' if t.run(0.01) else 'FAIL'}")

# Where does the harness actually break down? Sweep gloss at fixed resolution.
print("\n=== Gloss sweep at res=201: locating the harness limit ===")
for gloss in [0.0, 0.5, 0.8, 0.95, 1.0]:
    alpha = 0.1 * (1 - gloss) + 0.001 * gloss
    print(f"\n  gloss={gloss} (alpha={alpha:.4f})")
    adapter = BSDFAdapter("principled_bsdf", f"""
        <rgb name="base_colour" value="0.8, 0.8, 0.8"/>
        <float name="roughness" value="1.0"/>
        <float name="metallic" value="0.0"/>
        <float name="specular" value="0.0"/>
        <float name="clearcoat" value="1.0"/>
        <float name="clearcoat_gloss" value="{gloss}"/>
    """)
    t = ChiSquareTest(domain=SphericalDomain(), sample_func=adapter[0],
                      pdf_func=adapter[1], sample_dim=3, res=201, ires=32)
    print(f"   {'PASS' if t.run(0.01) else 'FAIL'}")
