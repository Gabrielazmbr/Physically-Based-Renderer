#!/usr/bin/env -S uv run --script
"""
Why does scene.shapes() return fewer shapes than scene.xml defines?

Standalone: does NOT touch path_tracer.py or any validated plugin code.
Run from the kitchen_scene directory:  uv run diag_shapes.py
"""
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.abspath('../../../'))

import mitsuba as mi
mi.set_variant('llvm_ad_rgb')

from bsdfs.principled import PrincipledBSDF
from emitters.envmap import CustomEnvmap
from integrators.path_tracer import PathTracer
from cameras.physical_camera import PhysicalCamera

mi.register_bsdf('principled_bsdf', lambda props: PrincipledBSDF(props))
mi.register_emitter('custom_envmap', lambda props: CustomEnvmap(props))
mi.register_integrator('path_tracer', lambda props: PathTracer(props))
mi.register_sensor('physical_camera', lambda props: PhysicalCamera(props))

SCENE = 'scene.xml'

print(f'Mitsuba {mi.__version__}, variant {mi.variant()}')
print()

# ---- 1. Ground truth from the XML itself -------------------------------
raw = open(SCENE).read()
xml_shape_tags = re.findall(r'<shape\s[^>]*>', raw)
xml_ids = re.findall(r'<shape\s+type="[^"]*"\s+id="([^"]+)"', raw)
xml_types = Counter(re.findall(r'<shape\s+type="([^"]+)"', raw))

print('--- scene.xml (text) ---')
print(f'  <shape> tags:        {len(xml_shape_tags)}')
print(f'  with an id=:         {len(xml_ids)}')
print(f'  by type:             {dict(xml_types)}')
print(f'  duplicate ids:       {[i for i, n in Counter(xml_ids).items() if n > 1]}')
print()

# ---- 2. What Mitsuba reports after loading -----------------------------
scene = mi.load_file(SCENE)
shapes = scene.shapes()
loaded_ids = [s.id() for s in shapes]

print('--- scene.shapes() ---')
print(f'  count:               {len(shapes)}')
print(f'  non-empty ids:       {len([i for i in loaded_ids if i])}')
print(f'  emitters():          {len(scene.emitters())}')
print()

missing = sorted(set(xml_ids) - set(loaded_ids))
print(f'  in XML but NOT in scene.shapes():  {len(missing)}')
print(f'    first 15: {missing[:15]}')
print()

# ---- 3. Are the "missing" shapes actually in the scene? ----------------
# If they render, they must be intersectable. Check the total triangle count
# against what the reported shapes alone would account for.
total_faces = 0
for s in shapes:
    try:
        total_faces += s.face_count()
    except Exception:
        pass
print(f'  faces across reported shapes: {total_faces}')
print()

# ---- 4. Does traverse() see more than shapes() does? ------------------
# traverse walks the whole scene graph, so if the missing shapes appear here
# but not in shapes(), the omission is specific to the shapes() accessor.
params = mi.traverse(scene)
keys = list(params.keys())
traverse_shape_ids = sorted({k.split('.')[0] for k in keys})
print('--- mi.traverse(scene) ---')
print(f'  total parameter keys:      {len(keys)}')
print(f'  distinct top-level names:  {len(traverse_shape_ids)}')
for probe in ('WineGlasses_0001', 'WineGlasses_0002', 'WineGlassesBSDF'):
    hits = [k for k in keys if k.startswith(probe)]
    print(f'  {probe:<20} {len(hits)} key(s)  {hits[:2]}')
print()

# ---- 5. Is 85 == the material count, or a real shape count? -----------
bsdf_ids = re.findall(r'<bsdf[^>]*\sid="([^"]+)"', raw)
print('--- coincidence check ---')
print(f'  <bsdf> definitions in XML: {len(bsdf_ids)}')
print(f'  scene.shapes() count:      {len(shapes)}')
print(f'  equal? {len(bsdf_ids) == len(shapes)}')
print()

# ---- 6. Do the reported shapes map 1:1 onto distinct BSDFs? -----------
# If shapes() is somehow collapsing by material, each reported shape would
# carry a different BSDF.
bsdf_of_shape = []
for s in shapes:
    try:
        b = s.bsdf()
        bsdf_of_shape.append(b.id() if b is not None else None)
    except Exception:
        bsdf_of_shape.append('<error>')
distinct = len(set(bsdf_of_shape))
print('--- shape -> bsdf mapping ---')
print(f'  distinct BSDFs across reported shapes: {distinct} (of {len(shapes)} shapes)')
dupes = [b for b, n in Counter(bsdf_of_shape).items() if n > 1]
print(f'  BSDFs used by >1 reported shape: {len(dupes)}  {dupes[:5]}')

# add to the end of diag_shapes.py
print()
print('--- can we find the wine glasses via their BSDF? ---')
for i, s in enumerate(shapes):
    b = s.bsdf()
    bid = b.id() if b is not None else None
    if bid == 'WineGlassesBSDF':
        print(f'  shape[{i}] id={s.id()!r}  bsdf={bid}  faces={s.face_count()}')
print()
print('--- do empty-id shapes look like merged aggregates? ---')
named = [s.face_count() for s in shapes if s.id()]
anon  = [s.face_count() for s in shapes if not s.id()]
print(f'  named shapes: n={len(named)} total_faces={sum(named)}')
print(f'  empty-id:     n={len(anon)} total_faces={sum(anon)}')
