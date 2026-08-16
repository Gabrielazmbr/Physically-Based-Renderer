"""Build the three controlled Blender Cycles scenes for thesis Chapter 6.

Run from Blender 4.3's Scripting workspace in a new, empty Blender file. The
script creates or replaces three scenes named ``CH6_Materials``,
``CH6_HDR_Environment`` and ``CH6_Camera_DOF``. It does not render or save the
file. The layouts and numerical inputs reproduce the canonical custom-renderer
tests from Sections 5.3 and 5.4 as closely as Cycles' available models allow.
"""

from __future__ import annotations

import math
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


REPOSITORY_OVERRIDE = ""
SCENE_NAMES = ("CH6_Materials", "CH6_HDR_Environment", "CH6_Camera_DOF")

MATERIALS = (
    ("matte_diffuse", (0.78, 0.20, 0.055), 0.80, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 1.5, None),
    ("dielectric_plastic", (0.045, 0.20, 0.72), 0.22, 0.0, 0.5, 0.0, 0.0, 1.0, 0.0, 1.5, None),
    ("high_specular", (0.045, 0.20, 0.72), 0.22, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 1.5, None),
    ("metallic_blend", (0.95, 0.58, 0.12), 0.25, 0.5, 0.5, 0.0, 0.0, 1.0, 0.0, 1.5, None),
    ("rough_metal", (0.95, 0.58, 0.12), 0.55, 1.0, 0.5, 0.0, 0.0, 1.0, 0.0, 1.5, None),
    ("polished_metal", (0.95, 0.58, 0.12), 0.08, 1.0, 0.5, 0.0, 0.0, 1.0, 0.0, 1.5, None),
    ("isotropic_control", (0.72, 0.76, 0.82), 0.25, 1.0, 0.5, 0.0, 0.0, 1.0, 0.0, 1.5, None),
    ("anisotropic_05", (0.72, 0.76, 0.82), 0.25, 1.0, 0.5, 0.5, 0.0, 1.0, 0.0, 1.5, None),
    ("anisotropic_09", (0.72, 0.76, 0.82), 0.25, 1.0, 0.5, 0.9, 0.0, 1.0, 0.0, 1.5, None),
    ("clearcoat_off", (0.32, 0.018, 0.025), 0.75, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 1.5, None),
    ("soft_clearcoat", (0.32, 0.018, 0.025), 0.75, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.5, None),
    ("sharp_clearcoat", (0.32, 0.018, 0.025), 0.75, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 1.5, None),
    ("opaque_control", (0.045, 0.52, 0.28), 0.28, 0.0, 0.5, 0.0, 0.0, 1.0, 0.0, 1.5, None),
    ("partial_transmission", (0.045, 0.52, 0.28), 0.28, 0.0, 0.5, 0.0, 0.0, 1.0, 0.5, 1.5, None),
    ("colour_texture", (0.025, 0.12, 0.52), 0.35, 0.0, 0.5, 0.0, 0.0, 1.0, 0.0, 1.5, "colour"),
    ("roughness_texture", (0.68, 0.72, 0.78), 0.08, 1.0, 0.5, 0.0, 0.0, 1.0, 0.0, 1.5, "roughness"),
    ("glass_ior_15", (0.92, 0.98, 1.0), 0.0, 0.0, 0.5, 0.0, 0.0, 1.0, 1.0, 1.5, None),
    ("glass_ior_24", (0.90, 0.97, 1.0), 0.0, 0.0, 0.5, 0.0, 0.0, 1.0, 1.0, 2.4, None),
)


def repository_root() -> Path:
    if REPOSITORY_OVERRIDE:
        root = Path(bpy.path.abspath(REPOSITORY_OVERRIDE)).expanduser().resolve()
        if root.is_dir():
            return root
    candidates = []
    script_name = globals().get("__file__")
    if script_name and not str(script_name).startswith("<"):
        candidates.append(Path(bpy.path.abspath(str(script_name))).resolve().parent)
    if bpy.data.filepath:
        candidates.append(Path(bpy.path.abspath("//")).resolve())
    candidates.append(Path.cwd().resolve())
    for candidate in candidates:
        for root in (candidate, *candidate.parents):
            if (root / "assets" / "hdri" / "studio_kontrast_04_1k.exr").is_file():
                return root
    raise FileNotFoundError(
        "Repository not found. Set REPOSITORY_OVERRIDE at the top of this script."
    )


def input_socket(node, *names):
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None:
            return socket
    raise KeyError(f"None of {names!r} exists on {node.bl_idname}")


def set_input(node, value, *names):
    input_socket(node, *names).default_value = value


def clear_scene(scene):
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(scene.collection.children):
        scene.collection.children.unlink(collection)
        if collection.users == 0:
            bpy.data.collections.remove(collection)
    scene.world = None


def fresh_scene(name):
    scene = bpy.data.scenes.get(name) or bpy.data.scenes.new(name)
    clear_scene(scene)
    return scene


def link_object(scene, obj):
    scene.collection.objects.link(obj)
    return obj


def configure_cycles(scene, root, *, width, height, samples, max_bounces, seed, filename):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.use_denoising = False
    if hasattr(scene.cycles, "use_preview_denoising"):
        scene.cycles.use_preview_denoising = False
    scene.cycles.seed = seed
    scene.cycles.max_bounces = max_bounces
    scene.cycles.diffuse_bounces = max_bounces
    scene.cycles.glossy_bounces = max_bounces
    scene.cycles.transmission_bounces = max_bounces
    scene.cycles.transparent_max_bounces = max_bounces
    scene.cycles.sample_clamp_direct = 0.0
    scene.cycles.sample_clamp_indirect = 0.0
    scene.cycles.use_light_tree = False
    scene.cycles.caustics_reflective = True
    scene.cycles.caustics_refractive = True
    if hasattr(scene.cycles, "pixel_filter_type"):
        scene.cycles.pixel_filter_type = "BOX"
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "OPEN_EXR"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "32"
    scene.render.image_settings.exr_codec = "NONE"
    scene.render.film_transparent = False
    scene.render.filepath = str(root / "outputs" / "evaluation" / "6_blender_comparison" / filename)
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    if hasattr(scene.render.image_settings, "color_management"):
        scene.render.image_settings.color_management = "OVERRIDE"
    if hasattr(scene.render.image_settings, "linear_colorspace_settings"):
        try:
            scene.render.image_settings.linear_colorspace_settings.name = "Linear Rec.709"
        except TypeError:
            pass
    scene["chapter_6_protocol"] = (
        f"Cycles CPU; {samples} spp; max bounces {max_bounces}; denoising off; "
        "clamping off; Box filter; Standard view; full-float linear RGB EXR"
    )


def make_world(scene, name, strength=1.0, hdri=None, rotation_degrees=0.0):
    world = bpy.data.worlds.new(name)
    world.use_nodes = True
    nodes = world.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputWorld")
    background = nodes.new("ShaderNodeBackground")
    background.inputs["Strength"].default_value = strength
    world.node_tree.links.new(background.outputs["Background"], output.inputs["Surface"])
    if hdri is None:
        background.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    else:
        texcoord = nodes.new("ShaderNodeTexCoord")
        mapping = nodes.new("ShaderNodeMapping")
        environment = nodes.new("ShaderNodeTexEnvironment")
        environment.image = bpy.data.images.load(str(hdri), check_existing=True)
        try:
            environment.image.colorspace_settings.name = "Linear Rec.709"
        except TypeError:
            environment.image.colorspace_settings.name = "Non-Color"
        mapping.inputs["Rotation"].default_value[2] = math.radians(rotation_degrees)
        world.node_tree.links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])
        world.node_tree.links.new(mapping.outputs["Vector"], environment.inputs["Vector"])
        world.node_tree.links.new(environment.outputs["Color"], background.inputs["Color"])
    scene.world = world


def make_principled(name, base, roughness, metallic, specular=0.5, anisotropic=0.0,
                    coat=0.0, coat_gloss=1.0, transmission=0.0, ior=1.5,
                    checker=None):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    set_input(shader, (*base, 1.0), "Base Color")
    set_input(shader, roughness, "Roughness")
    set_input(shader, metallic, "Metallic")
    set_input(shader, specular, "Specular IOR Level", "IOR Level", "Specular")
    set_input(shader, anisotropic, "Anisotropic IOR Level", "Anisotropic", "Anisotropy")
    set_input(shader, coat, "Coat Weight", "Clearcoat")
    alpha = 0.1 * (1.0 - coat_gloss) + 0.001 * coat_gloss
    set_input(shader, math.sqrt(alpha), "Coat Roughness", "Clearcoat Roughness")
    set_input(shader, transmission, "Transmission Weight", "Transmission")
    set_input(shader, ior, "IOR")
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    if checker:
        coordinates = nodes.new("ShaderNodeTexCoord")
        texture = nodes.new("ShaderNodeTexChecker")
        texture.inputs["Scale"].default_value = 6.0
        links.new(coordinates.outputs["UV"], texture.inputs["Vector"])
        if checker == "colour":
            texture.inputs["Color1"].default_value = (0.025, 0.12, 0.52, 1.0)
            texture.inputs["Color2"].default_value = (0.95, 0.32, 0.035, 1.0)
            links.new(texture.outputs["Color"], input_socket(shader, "Base Color"))
        else:
            texture.inputs["Color1"].default_value = (0.08, 0.08, 0.08, 1.0)
            texture.inputs["Color2"].default_value = (0.75, 0.75, 0.75, 1.0)
            links.new(texture.outputs["Color"], input_socket(shader, "Roughness"))
    material["custom_parameter_note"] = (
        "Numerical match where exposed. Cycles diffuse/transmission/coat models "
        "are not identical to the custom BSDF."
    )
    return material


def make_diffuse(name, colour):
    material = bpy.data.materials.new(name)
    material.diffuse_color = (*colour, 1.0)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    set_input(shader, (*colour, 1.0), "Base Color")
    set_input(shader, 1.0, "Roughness")
    set_input(shader, 0.0, "Specular IOR Level", "IOR Level", "Specular")
    return material


def add_uv_sphere(scene, name, location, radius, material):
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    geometry = bmesh.new()
    bmesh.ops.create_uvsphere(
        geometry, u_segments=64, v_segments=32, radius=radius
    )
    geometry.to_mesh(mesh)
    geometry.free()
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            direction = mesh.vertices[mesh.loops[loop_index].vertex_index].co.normalized()
            u = (math.atan2(direction.y, direction.x) / (2.0 * math.pi)) % 1.0
            v = math.acos(max(-1.0, min(1.0, direction.z))) / math.pi
            uv_layer.data[loop_index].uv = (u, v)
    obj = bpy.data.objects.new(name, mesh)
    link_object(scene, obj)
    obj.location = location
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


def add_plane(scene, name, location, dimensions, material, vertical=False):
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(((-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)), (), ((0, 1, 2, 3),))
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for loop_index, uv in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))):
        uv_layer.data[loop_index].uv = uv
    obj = bpy.data.objects.new(name, mesh)
    link_object(scene, obj)
    obj.location = location
    obj.dimensions = dimensions
    if vertical:
        obj.rotation_euler[0] = math.radians(90.0)
    obj.data.materials.append(material)
    return obj


def add_camera(scene, name, origin, target, fov_x, *, focus=None, aperture_radius=0.0):
    data = bpy.data.cameras.new(f"{name}_Data")
    camera = bpy.data.objects.new(name, data)
    link_object(scene, camera)
    camera.location = origin
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
    data.sensor_fit = "HORIZONTAL"
    data.sensor_width = 36.0
    data.lens = 36.0 / (2.0 * math.tan(math.radians(fov_x) / 2.0))
    if focus is not None and aperture_radius > 0.0:
        data.dof.use_dof = True
        data.dof.focus_distance = focus
        data.dof.aperture_fstop = (data.lens / 1000.0) / (2.0 * aperture_radius)
        data.dof.aperture_blades = 0
    scene.camera = camera
    return camera


def add_area(scene, name, origin, target, dimensions, radiance):
    data = bpy.data.lights.new(f"{name}_Data", "AREA")
    obj = bpy.data.objects.new(name, data)
    link_object(scene, obj)
    obj.location = origin
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    data.shape = "RECTANGLE"
    data.size, data.size_y = dimensions
    area = dimensions[0] * dimensions[1]
    peak = max(radiance)
    data.color = tuple(value / peak for value in radiance)
    data.energy = peak * area * math.pi
    data["mitsuba_radiance"] = str(tuple(radiance))
    return obj


def build_materials(root):
    scene = fresh_scene("CH6_Materials")
    configure_cycles(scene, root, width=1600, height=900, samples=1024,
                     max_bounces=12, seed=19,
                     filename="materials/renders/cycles_material_showcase.exr")
    make_world(scene, "CH6_Materials_World", 0.55,
               root / "assets" / "hdri" / "studio_kontrast_04_1k.exr", 28.0)
    backdrop = make_diffuse("CH6_Backdrop", (0.105, 0.11, 0.12))
    add_plane(scene, "Backdrop", (0, 1.30, 0), (12.6, 7.5, 0), backdrop, True)
    checker = make_principled("CH6_Checker_Card", (0.025, 0.035, 0.055), 1.0,
                              0.0, 0.0, checker="colour")
    texture = checker.node_tree.nodes.get("Checker Texture")
    texture.inputs["Color1"].default_value = (0.025, 0.035, 0.055, 1.0)
    texture.inputs["Color2"].default_value = (0.78, 0.82, 0.88, 1.0)
    texture.inputs["Scale"].default_value = 5.0
    for index, x in enumerate((-4.5, -2.7, 2.7, 4.5)):
        add_plane(scene, f"Glass_Target_{index}", (x, 1.22, -2.25),
                  (1.64, 1.64, 0), checker, True)
    xs, zs = (-4.5, -2.7, -0.9, 0.9, 2.7, 4.5), (2.25, 0.0, -2.25)
    for index, spec in enumerate(MATERIALS):
        name, base, rough, metal, specular, aniso, coat, gloss, transmission, ior, checker_kind = spec
        material = make_principled(
            f"MAT_{name}", base, rough, metal, specular, aniso,
            coat, gloss, transmission, ior, checker_kind,
        )
        row, column = divmod(index, 6)
        add_uv_sphere(scene, name, (xs[column], 0, zs[row]), 0.68, material)
    add_area(scene, "Key", (-3.8, -5.0, 5.8), (0, 0, 0), (4.2, 2.0), (15.0, 14.5, 13.5))
    add_area(scene, "Strip", (5.5, -4.0, 1.3), (0, 0, 0), (0.9, 4.4), (10.0, 11.0, 13.0))
    add_camera(scene, "CH6_Materials_Camera", (0, -13.0, 0.15), (0, 0, 0), 54.0)
    scene["comparison_source"] = "Section 5.4 principled_material_showcase"


def build_environment(root):
    scene = fresh_scene("CH6_HDR_Environment")
    configure_cycles(scene, root, width=1024, height=1024, samples=1024,
                     max_bounces=8, seed=10,
                     filename="environment/renders/cycles_sundowner.exr")
    make_world(scene, "CH6_HDR_World", 1.0,
               root / "assets" / "hdri" / "sundowner_overlook_1k.exr", 90.0)
    metal = make_principled("CH6_HDR_Metal", (0.95, 0.95, 0.95), 0.1, 1.0)
    add_uv_sphere(scene, "HDR_Sphere", (0, 0, 0), 1.0, metal)
    floor = make_diffuse("CH6_HDR_Floor", (0.8, 0.8, 0.8))
    # Exact Mitsuba transform converted from Y-up to Blender Z-up. The source
    # rectangle is a shallow strip behind the sphere, not a full ground plane.
    add_plane(scene, "Floor", (0, 1.1, -2.5), (10, 2, 0), floor)
    add_camera(scene, "CH6_HDR_Camera", (0, -5, 0.5), (0, 0, 0), 40.0)
    scene["comparison_source"] = "assets/scenes/environment_lighting.py"


def build_camera(root):
    scene = fresh_scene("CH6_Camera_DOF")
    configure_cycles(scene, root, width=960, height=720, samples=256,
                     max_bounces=4, seed=27,
                     filename="camera/renders/cycles_camera_dof.exr")
    make_world(scene, "CH6_Camera_World", 1.0)
    for name, location, colour in (
        ("Near", (-0.65, 0, -3), (0.9, 0.05, 0.04)),
        ("Focus", (0, 0, -5), (0.05, 0.8, 0.08)),
        ("Far", (1.0, 0, -9), (0.04, 0.08, 0.9)),
    ):
        material = make_principled(f"CH6_Camera_{name}", colour, 0.5, 0.0, 0.0)
        add_uv_sphere(scene, name, location, 0.42, material)
    add_camera(scene, "CH6_DOF_Camera", (0, 0, 0), (0, 0, -1), 40.0,
               focus=5.0, aperture_radius=0.15)
    scene["comparison_source"] = "Section 5.4 camera_physical_dof"


def main():
    root = repository_root()
    for relative in ("materials/renders", "environment/renders", "camera/renders"):
        (root / "outputs" / "evaluation" / "6_blender_comparison" / relative).mkdir(
            parents=True, exist_ok=True
        )
    build_materials(root)
    build_environment(root)
    build_camera(root)
    bpy.context.window.scene = bpy.data.scenes["CH6_Materials"]
    print("Chapter 6 controlled scenes created:", ", ".join(SCENE_NAMES))
    print("Inspect the three camera views, then save the .blend before rendering.")


if __name__ == "__main__":
    main()
