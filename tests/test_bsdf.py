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


print(f"\n{'All tests passed.' if all_passed else 'Some tests failed.'}")
