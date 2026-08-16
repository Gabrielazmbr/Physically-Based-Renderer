"""Export a read-only light and material inventory from the Kitchen .blend.

Run this file from Blender 4.3's Scripting workspace while the canonical
Country Kitchen file is open. It does not modify the scene. JSON and two CSV
files are written under the Chapter 6 Kitchen evaluation data directory.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import bpy


REPOSITORY_OVERRIDE = ""
OUTPUT_RELATIVE = Path("outputs/evaluation/6_blender_comparison/kitchen/data")


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
            if (root / "assets" / "production_scenes" / "kitchen_scene" / "scene.xml").is_file():
                return root
    raise FileNotFoundError(
        "Repository not found. Set REPOSITORY_OVERRIDE at the top of this script."
    )


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def serialise(value):
    if hasattr(value, "to_tuple"):
        return list(value.to_tuple())
    if isinstance(value, (list, tuple)):
        return [serialise(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        return list(value)
    except TypeError:
        return str(value)


def socket_record(socket):
    record = {"value": serialise(getattr(socket, "default_value", None))}
    if socket.is_linked:
        link = socket.links[0]
        record["linked_from"] = {
            "node": link.from_node.name,
            "node_type": link.from_node.bl_idname,
            "socket": link.from_socket.name,
        }
    return record


def socket_by_names(node, *names):
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None:
            return socket_record(socket)
    return None


def node_record(node):
    return {
        "name": node.name,
        "label": node.label,
        "type": node.bl_idname,
        "inputs": {socket.name: socket_record(socket) for socket in node.inputs},
    }


def matrix_values(obj):
    return [[float(value) for value in row] for row in obj.matrix_world]


def light_area(data):
    """Area from Blender's documented full-width size controls."""
    if data.type != "AREA":
        return None
    shape = data.shape
    if shape == "SQUARE":
        return float(data.size * data.size)
    if shape == "RECTANGLE":
        return float(data.size * data.size_y)
    if shape == "DISK":
        return float(math.pi * (data.size * 0.5) ** 2)
    if shape == "ELLIPSE":
        return float(math.pi * data.size * data.size_y * 0.25)
    return None


def mesh_slot_areas(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    areas = {}
    try:
        transform = evaluated.matrix_world
        for polygon in mesh.polygons:
            vertices = [transform @ mesh.vertices[index].co for index in polygon.vertices]
            if len(vertices) < 3:
                continue
            origin = vertices[0]
            area = 0.0
            for index in range(1, len(vertices) - 1):
                area += 0.5 * (vertices[index] - origin).cross(
                    vertices[index + 1] - origin
                ).length
            areas[polygon.material_index] = areas.get(polygon.material_index, 0.0) + area
    finally:
        evaluated.to_mesh_clear()
    return areas


def material_record(material, users):
    record = {
        "name": material.name,
        "users": sorted(users),
        "use_nodes": bool(material.use_nodes),
        "diffuse_color": serialise(material.diffuse_color),
        "principled_nodes": [],
        "emission_nodes": [],
        "image_textures": [],
        "shader_graph": [],
        "surface_output": None,
    }
    if not material.use_nodes or material.node_tree is None:
        return record
    for node in material.node_tree.nodes:
        record["shader_graph"].append(node_record(node))
        if node.bl_idname == "ShaderNodeOutputMaterial":
            surface = node.inputs.get("Surface")
            if surface is not None:
                record["surface_output"] = socket_record(surface)
        if node.bl_idname == "ShaderNodeBsdfPrincipled":
            record["principled_nodes"].append(
                {
                    "name": node.name,
                    "base_color": socket_by_names(node, "Base Color"),
                    "metallic": socket_by_names(node, "Metallic"),
                    "roughness": socket_by_names(node, "Roughness"),
                    "ior": socket_by_names(node, "IOR"),
                    "specular": socket_by_names(
                        node, "Specular IOR Level", "IOR Level", "Specular"
                    ),
                    "anisotropy": socket_by_names(
                        node, "Anisotropic IOR Level", "Anisotropic", "Anisotropy"
                    ),
                    "coat_weight": socket_by_names(node, "Coat Weight", "Clearcoat"),
                    "coat_roughness": socket_by_names(
                        node, "Coat Roughness", "Clearcoat Roughness"
                    ),
                    "sheen_weight": socket_by_names(node, "Sheen Weight", "Sheen"),
                    "transmission": socket_by_names(
                        node, "Transmission Weight", "Transmission"
                    ),
                    "emission_color": socket_by_names(
                        node, "Emission Color", "Emission"
                    ),
                    "emission_strength": socket_by_names(node, "Emission Strength"),
                }
            )
        elif node.bl_idname == "ShaderNodeEmission":
            record["emission_nodes"].append(
                {
                    "name": node.name,
                    "color": socket_by_names(node, "Color"),
                    "strength": socket_by_names(node, "Strength"),
                }
            )
        elif node.bl_idname == "ShaderNodeTexImage":
            image = node.image
            record["image_textures"].append(
                {
                    "node": node.name,
                    "image": image.name if image else None,
                    "filepath": bpy.path.abspath(image.filepath) if image else None,
                    "color_space": image.colorspace_settings.name if image else None,
                    "interpolation": node.interpolation,
                }
            )
    return record


def has_emission(material_record):
    if material_record["emission_nodes"]:
        return True
    for node in material_record["principled_nodes"]:
        strength = node.get("emission_strength")
        colour = node.get("emission_color")
        strength_value = strength.get("value") if strength else 0.0
        colour_value = colour.get("value") if colour else [0.0, 0.0, 0.0, 1.0]
        if strength and strength.get("linked_from"):
            return True
        if colour and colour.get("linked_from"):
            return True
        if isinstance(strength_value, (int, float)) and strength_value != 0.0:
            if isinstance(colour_value, list) and any(value != 0.0 for value in colour_value[:3]):
                return True
    return False


def flatten(value):
    return json.dumps(value, sort_keys=True) if value is not None else ""


def write_csv(path, rows, fieldnames):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    if not bpy.data.filepath:
        raise RuntimeError("Save/open the canonical Kitchen .blend before running this inventory.")
    root = repository_root()
    output = root / OUTPUT_RELATIVE
    output.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()

    material_users = {}
    for obj in scene.objects:
        for slot in obj.material_slots:
            if slot.material:
                material_users.setdefault(slot.material.name, set()).add(obj.name)
    materials = [
        material_record(material, material_users.get(material.name, set()))
        for material in sorted(
            (bpy.data.materials[name] for name in material_users), key=lambda item: item.name
        )
    ]
    material_lookup = {record["name"]: record for record in materials}

    lights = []
    for obj in sorted((item for item in scene.objects if item.type == "LIGHT"), key=lambda item: item.name):
        data = obj.data
        area = light_area(data)
        lights.append(
            {
                "kind": "light_object",
                "object": obj.name,
                "data": data.name,
                "type": data.type,
                "energy_watts": float(data.energy),
                "color": serialise(data.color),
                "shape": getattr(data, "shape", None),
                "size": float(getattr(data, "size", 0.0)),
                "size_y": float(getattr(data, "size_y", 0.0)),
                "computed_area_m2": area,
                "power_density_w_per_m2": (
                    float(data.energy / area) if area and area > 0 else None
                ),
                "matrix_world": matrix_values(obj),
                "use_nodes": bool(data.use_nodes),
                "hide_render": bool(obj.hide_render),
                "visible_camera": bool(obj.visible_camera),
                "visible_diffuse": bool(obj.visible_diffuse),
                "visible_glossy": bool(obj.visible_glossy),
                "visible_transmission": bool(obj.visible_transmission),
                "use_shadow": bool(data.use_shadow),
                "angle_radians": float(getattr(data, "angle", 0.0)),
                "spread_radians": float(getattr(data, "spread", 0.0)),
                "shadow_soft_size": float(getattr(data, "shadow_soft_size", 0.0)),
                "node_graph": (
                    [node_record(node) for node in data.node_tree.nodes]
                    if data.use_nodes and data.node_tree else []
                ),
            }
        )

    emissive_meshes = []
    for obj in sorted((item for item in scene.objects if item.type == "MESH"), key=lambda item: item.name):
        emitting_slots = []
        for index, slot in enumerate(obj.material_slots):
            material = slot.material
            if material and has_emission(material_lookup[material.name]):
                emitting_slots.append((index, material))
        if not emitting_slots:
            continue
        areas = mesh_slot_areas(obj, depsgraph)
        for index, material in emitting_slots:
            emissive_meshes.append(
                {
                    "kind": "emissive_mesh",
                    "object": obj.name,
                    "material": material.name,
                    "material_slot": index,
                    "computed_area_m2": float(areas.get(index, 0.0)),
                    "matrix_world": matrix_values(obj),
                    "material_emission": {
                        "principled_nodes": material_lookup[material.name]["principled_nodes"],
                        "emission_nodes": material_lookup[material.name]["emission_nodes"],
                    },
                    "hide_render": bool(obj.hide_render),
                    "visible_camera": bool(obj.visible_camera),
                    "visible_diffuse": bool(obj.visible_diffuse),
                    "visible_glossy": bool(obj.visible_glossy),
                    "visible_transmission": bool(obj.visible_transmission),
                }
            )

    blend_path = Path(bpy.data.filepath).resolve()
    world = scene.world
    world_record = None
    if world is not None:
        world_record = {
            "name": world.name,
            "color": serialise(world.color),
            "use_nodes": bool(world.use_nodes),
            "node_graph": (
                [node_record(node) for node in world.node_tree.nodes]
                if world.use_nodes and world.node_tree else []
            ),
        }
    inventory = {
        "purpose": "Read-only Blender reference inventory for Chapter 6 Kitchen translation audit",
        "blender_version": bpy.app.version_string,
        "blend_file": str(blend_path),
        "blend_sha256": sha256(blend_path),
        "scene": scene.name,
        "render": {
            "engine": scene.render.engine,
            "resolution": [scene.render.resolution_x, scene.render.resolution_y],
            "view_transform": scene.view_settings.view_transform,
            "look": scene.view_settings.look,
            "exposure": scene.view_settings.exposure,
            "gamma": scene.view_settings.gamma,
            "cycles_samples": scene.cycles.samples if hasattr(scene, "cycles") else None,
        },
        "world": world_record,
        "light_objects": lights,
        "emissive_meshes": emissive_meshes,
        "materials": materials,
    }
    (output / "blender_reference_inventory.json").write_text(
        json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
    )

    light_rows = []
    for item in lights:
        light_rows.append(
            {
                "kind": item["kind"], "object": item["object"],
                "material_or_data": item["data"], "type": item["type"],
                "energy_watts": item["energy_watts"], "color": flatten(item["color"]),
                "shape": item["shape"], "size": item["size"], "size_y": item["size_y"],
                "computed_area_m2": item["computed_area_m2"],
                "emission_parameters": flatten(item["node_graph"]),
                "hide_render": item["hide_render"],
                "visible_camera": item["visible_camera"],
                "visible_diffuse": item["visible_diffuse"],
                "visible_glossy": item["visible_glossy"],
                "visible_transmission": item["visible_transmission"],
            }
        )
    for item in emissive_meshes:
        light_rows.append(
            {
                "kind": item["kind"], "object": item["object"],
                "material_or_data": item["material"], "type": "MESH",
                "energy_watts": "", "color": "", "shape": "", "size": "", "size_y": "",
                "computed_area_m2": item["computed_area_m2"],
                "emission_parameters": flatten(item["material_emission"]),
                "hide_render": item["hide_render"],
                "visible_camera": item["visible_camera"],
                "visible_diffuse": item["visible_diffuse"],
                "visible_glossy": item["visible_glossy"],
                "visible_transmission": item["visible_transmission"],
            }
        )
    write_csv(
        output / "blender_light_inventory.csv", light_rows,
        ["kind", "object", "material_or_data", "type", "energy_watts", "color",
         "shape", "size", "size_y", "computed_area_m2", "emission_parameters",
         "hide_render", "visible_camera", "visible_diffuse", "visible_glossy",
         "visible_transmission"],
    )

    material_rows = []
    for item in materials:
        first = item["principled_nodes"][0] if item["principled_nodes"] else {}
        material_rows.append(
            {
                "material": item["name"], "object_count": len(item["users"]),
                "objects": flatten(item["users"]), "base_color": flatten(first.get("base_color")),
                "metallic": flatten(first.get("metallic")), "roughness": flatten(first.get("roughness")),
                "ior": flatten(first.get("ior")), "specular": flatten(first.get("specular")),
                "anisotropy": flatten(first.get("anisotropy")),
                "coat_weight": flatten(first.get("coat_weight")),
                "sheen_weight": flatten(first.get("sheen_weight")),
                "transmission": flatten(first.get("transmission")),
                "image_textures": flatten(item["image_textures"]),
                "shader_graph": flatten(item["shader_graph"]),
                "surface_output": flatten(item["surface_output"]),
                "emissive": has_emission(item),
            }
        )
    write_csv(
        output / "blender_material_inventory.csv", material_rows,
        ["material", "object_count", "objects", "base_color", "metallic", "roughness",
         "ior", "specular", "anisotropy", "coat_weight", "sheen_weight",
         "transmission", "image_textures", "shader_graph", "surface_output", "emissive"],
    )
    print(
        f"PASS: exported {len(lights)} light objects, {len(emissive_meshes)} emissive "
        f"mesh assignments and {len(materials)} used materials to {output}"
    )


if __name__ == "__main__":
    main()
