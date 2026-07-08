"""
Scene 03 Material Test Scene
Validates: Principled BSDF parameter behaviour
Expected outcome: three spheres showing distinct
material responses.
"""

import mitsuba as mi

mi.set_variant("llvm_ad_rgb")

scene_dict = {
    "type": "scene",
    "integrator": {"type": "path", "max_depth": 8},
    "sensor": {
        "type": "perspective",
        "fov": 45,
        "to_world": mi.ScalarTransform4f().look_at(
            origin=[0, 1.5, 10], target=[0, 0, 0], up=[0, 1, 0]
        ),
        "film_id": {
            "type": "hdrfilm",
            "width": 768,
            "height": 384,
            "pixel_format": "rgb",
            "component_format": "float32",
            "rfilter": {"type": "gaussian"},
        },
        "sampler_id": {"type": "independent", "sample_count": 128},
    },
    "light": {
        "type": "constant",
        "radiance": {"type": "rgb", "value": [1.0, 1.0, 1.0]},
    },
    # Metal sphere: high metallic, low roughness
    # To be replaced: swap bsdf type for my_principled_bsdf
    "sphere_metal": {
        "type": "sphere",
        "center": [-2.5, 0, 0],
        "radius": 0.8,
        "bsdf": {
            "type": "conductor",
            "material": "Au",  # gold
            "alpha": 0.1,  # low roughness
        },
    },
    # Plastic sphere: low metallic, low roughness
    "sphere_plastic": {
        "type": "sphere",
        "center": [0, 0, 0],
        "radius": 0.8,
        "bsdf": {
            "type": "plastic",
            "diffuse_reflectance": {"type": "rgb", "value": [0.1, 0.27, 0.36]},
            "int_ior": 1.9,
        },
    },
    # Organic/diffuse sphere: low metallic, high roughness
    "sphere_organic": {
        "type": "sphere",
        "center": [2.5, 0, 0],
        "radius": 0.8,
        "bsdf": {
            "type": "diffuse",
            "reflectance": {"type": "rgb", "value": [0.6, 0.3, 0.2]},
        },
    },
    # Ground plane
    "floor": {
        "type": "rectangle",
        "to_world": mi.ScalarTransform4f()
        .scale([5, 5, 4])
        .rotate([1, 0, 0], 90)
        .translate([0, -0.8, 0.5]),
        "bsdf": {
            "type": "twosided",
            "bsdf": {
                "type": "diffuse",
                "reflectance": {"type": "rgb", "value": [0.8, 0.8, 0.8]},
            },
        },
    },
}

if __name__ == "__main__":
    scene = mi.load_dict(scene_dict)
    img = mi.render(scene, spp=128)
    mi.Bitmap(img).write("outputs/03_material_test.exr")
    print("Material test rendered — check outputs/03_material_test.exr")
