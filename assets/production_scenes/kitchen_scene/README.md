# Country Kitchen production scene

This directory contains the active production-scene input for thesis Section
5.5.2. `scene_original.xml` is the untouched downloaded Mitsuba scene and
`build_scene.py` deterministically rebuilds the active `scene.xml`. Run the
builder from this directory so its relative paths resolve correctly.

The active asset consists of the two XML files, builder and render entry point,
`models/`, `meshes/`, and `textures/`. Fixed external reference images belong
under `reference/`. Generated evaluation results belong under
`outputs/evaluation/5_5_integration/kitchen/`, not in this asset directory.

Historical development renders and one-off diagnostics are preserved under
`outputs/legacy/5_5_integration/kitchen_development/` and
`tests/legacy/integration/kitchen/` respectively.

The original scene is the Country Kitchen scene by Benedikt Bitterli. See
`LICENSE.txt` for its licensing information.
