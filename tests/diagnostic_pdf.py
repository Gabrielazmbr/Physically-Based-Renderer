#!/usr/bin/env -S uv run --script
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mitsuba as mi
import drjit as dr
import numpy as np

mi.set_variant('llvm_ad_rgb')

print("=== Diagnostic: Does distr.pdf integrate to 1.0? ===\n")

for roughness, alpha in [(0.1, 0.01), (0.3, 0.09), (1.0, 1.0)]:
    alpha_val = max(roughness * roughness, 1e-4)
    distr = mi.MicrofacetDistribution(mi.MicrofacetType.GGX, alpha_val, sample_visible=True)

    n = 100000
    sampler = mi.load_dict({'type': 'independent'})
    sampler.seed(0, n)

    wi = mi.Vector3f(0, 0, 1)
    sample2 = sampler.next_2d()

    m, m_pdf = distr.sample(wi, sample2)
    wo = mi.reflect(wi, m)
    cos_h = dr.maximum(dr.dot(wi, m), 1e-7)

    h = dr.normalize(wi + wo)
    pdf_distr = distr.pdf(wi, h)

    # Method A: m_pdf / (4 * dot(wi,m))
    pdfA = m_pdf / (4 * cos_h)

    # Method B: distr.pdf / (4 * dot(wi,h))
    pdfB = pdf_distr / (4 * dr.maximum(dr.dot(wi, h), 1e-7))

    # Method C: distr.pdf / (4 * cos_theta_i)
    pdfC = pdf_distr / (4 * mi.Frame3f.cos_theta(wi))

    # Method D: just m_pdf directly
    pdfD = m_pdf

    print(f"Roughness {roughness} (alpha={alpha_val:.4f}):")
    print(f"  m_pdf mean:          {np.array(m_pdf).mean():.4f}")
    print(f"  A: m_pdf/4cos_h:     {np.array(pdfA).mean():.4f}")
    print(f"  B: distr.pdf/4cos_h: {np.array(pdfB).mean():.4f}")
    print(f"  C: distr.pdf/4cos_i: {np.array(pdfC).mean():.4f}")
    print(f"  D: m_pdf directly:   {np.array(pdfD).mean():.4f}")
    print()


from mitsuba.chi2 import BSDFAdapter, ChiSquareTest, SphericalDomain

sample_func, pdf_func = BSDFAdapter("roughconductor", """
    <string name="material" value="none"/>
    <float name="alpha" value="0.1"/>
    <string name="distribution" value="ggx"/>
""")

test = ChiSquareTest(
    domain=SphericalDomain(),
    sample_func=sample_func,
    pdf_func=pdf_func,
    sample_dim=3,
    res=201,
    ires=32
)

result = test.run(0.01)
print(f"roughconductor chi2: {'PASS' if result else 'FAIL'}")
print(f"PDF sum: {np.array(test.pdf).sum():.4f}")


# In diagnostic_pdf.py add:
from bsdfs.principled import PrincipledBSDF
mi.register_bsdf("principled_bsdf", lambda props: PrincipledBSDF(props))

sample_func, pdf_func = BSDFAdapter("principled_bsdf", """
    <rgb name="base_colour" value="1.0, 1.0, 1.0"/>
    <float name="roughness" value="0.1"/>
    <float name="metallic" value="1.0"/>
""")

test = ChiSquareTest(
    domain=SphericalDomain(),
    sample_func=sample_func,
    pdf_func=pdf_func,
    sample_dim=3,
    res=101,
    ires=8
)
test.tabulate_pdf()
print(f"principled metal PDF integral: {np.array(test.pdf).sum():.4f}")




sample_func, pdf_func = BSDFAdapter("roughconductor", """
    <string name="material" value="none"/>
    <float name="alpha" value="0.01"/>
    <string name="distribution" value="ggx"/>
""")
test = ChiSquareTest(
    domain=SphericalDomain(),
    sample_func=sample_func,
    pdf_func=pdf_func,
    sample_dim=3,
    res=201,
    ires=32
)
result = test.run(0.01)
print(f"roughconductor alpha=0.01: {'PASS' if result else 'FAIL'}, PDF sum={np.array(test.pdf).sum():.0f}")
