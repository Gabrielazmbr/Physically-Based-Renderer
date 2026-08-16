"""Import the canonical Country Kitchen sensors into the open Blender file.

Run this file from Blender's Scripting workspace.  It reads the six physical
camera sensors from ``assets/production_scenes/kitchen_scene/scene.xml`` and
creates or updates a dedicated ``Chapter_6_Cameras`` collection.  Geometry,
materials, lights, world settings, and render settings are not modified.

The XML hero sensor was exported from the Blender scene's existing main camera.
The script therefore uses that camera as a spatial reference and derives the
full XML-to-Blender world alignment from the known hero pair. This includes the
Mitsuba Y-up to Blender Z-up conversion and the different local camera axes.
"""

from __future__ import annotations

import math
from pathlib import Path
import xml.etree.ElementTree as ET

import bpy
from mathutils import Matrix, Vector


COLLECTION_NAME = "Chapter_6_Cameras"
CAMERA_NAMES = ("Hero", "Stove", "Table", "Radio", "Towel", "Island")
XML_RELATIVE_PATH = Path("assets/production_scenes/kitchen_scene/scene.xml")

# Set this only if the script cannot locate the repository automatically.
XML_PATH_OVERRIDE = ""

# Leave empty to use the scene's current active camera. If that is not the
# original main camera, enter its Blender object name here (for example Camera).
REFERENCE_CAMERA_NAME = ""

# Mitsuba's camera looks along local +Z with image-right along -X. Blender's
# camera looks along local -Z with image-right along +X.
CAMERA_BASIS_CONVERSION = Matrix.Diagonal((-1.0, 1.0, -1.0, 1.0))


def _candidate_roots() -> list[Path]:
    """Return plausible repository roots without assuming the .blend location."""
    candidates: list[Path] = []

    if XML_PATH_OVERRIDE:
        override = Path(bpy.path.abspath(XML_PATH_OVERRIDE)).expanduser()
        candidates.append(override if override.is_dir() else override.parent)

    script_name = globals().get("__file__")
    if script_name and not str(script_name).startswith("<"):
        candidates.append(Path(bpy.path.abspath(str(script_name))).resolve().parent)

    if bpy.data.filepath:
        candidates.append(Path(bpy.path.abspath("//")).resolve())

    candidates.append(Path.cwd().resolve())

    roots: list[Path] = []
    for candidate in candidates:
        roots.extend((candidate, *candidate.parents))
    return list(dict.fromkeys(roots))


def locate_scene_xml() -> Path:
    """Locate the canonical XML, or explain how to provide its path."""
    if XML_PATH_OVERRIDE:
        override = Path(bpy.path.abspath(XML_PATH_OVERRIDE)).expanduser().resolve()
        if override.is_file():
            return override

    for root in _candidate_roots():
        path = root / XML_RELATIVE_PATH
        if path.is_file():
            return path

    raise FileNotFoundError(
        "Could not locate the canonical Country Kitchen scene.xml. "
        "Set XML_PATH_OVERRIDE near the top of this script to its absolute path."
    )


def _resolved_number(
    element: ET.Element | None,
    defaults: dict[str, str],
    fallback: float,
) -> float:
    if element is None:
        return fallback
    value = element.get("value", str(fallback))
    if value.startswith("$"):
        value = defaults[value[1:]]
    return float(value)


def _vector(value: str, length: int) -> list[float]:
    values = [float(item) for item in value.replace(",", " ").split()]
    if len(values) != length:
        raise ValueError(f"Expected {length} values, received {len(values)}: {value!r}")
    return values


def _operation_matrix(operation: ET.Element) -> Matrix:
    """Convert one Mitsuba XML transform operation to a 4x4 matrix."""
    if operation.tag == "matrix":
        values = _vector(operation.get("value", ""), 16)
        return Matrix(
            tuple(
                tuple(values[row * 4 + col] for col in range(4))
                for row in range(4)
            )
        )

    if operation.tag == "translate":
        if "value" in operation.attrib:
            xyz = _vector(operation.attrib["value"], 3)
        else:
            xyz = [float(operation.get(axis, "0")) for axis in "xyz"]
        return Matrix.Translation(Vector(xyz))

    if operation.tag == "scale":
        if "value" in operation.attrib:
            raw = operation.attrib["value"].replace(",", " ").split()
            xyz = (
                [float(raw[0])] * 3
                if len(raw) == 1
                else _vector(operation.attrib["value"], 3)
            )
        else:
            xyz = [float(operation.get(axis, "1")) for axis in "xyz"]
        return Matrix.Diagonal((*xyz, 1.0))

    if operation.tag == "rotate":
        axis = Vector(tuple(float(operation.get(component, "0")) for component in "xyz"))
        if axis.length == 0:
            raise ValueError("A rotate operation has a zero-length axis")
        return Matrix.Rotation(
            math.radians(float(operation.get("angle", "0"))),
            4,
            axis.normalized(),
        )

    raise ValueError(f"Unsupported sensor transform operation: <{operation.tag}>")


def sensor_world_matrix(sensor: ET.Element) -> Matrix:
    transform = sensor.find("transform[@name='to_world']")
    if transform is None:
        return Matrix.Identity(4)

    # Mitsuba composes XML operations in listed order by pre-multiplication.
    result = Matrix.Identity(4)
    for operation in transform:
        result = _operation_matrix(operation) @ result
    return result


def read_sensors(xml_path: Path) -> tuple[list[dict], tuple[int, int]]:
    root = ET.parse(xml_path).getroot()
    defaults = {
        item.get("name", ""): item.get("value", "")
        for item in root.findall("default")
    }
    width = int(float(defaults.get("resx", "1280")))
    height = int(float(defaults.get("resy", "720")))

    sensors = root.findall("sensor")
    if len(sensors) != len(CAMERA_NAMES):
        raise ValueError(
            f"Expected {len(CAMERA_NAMES)} canonical sensors, found {len(sensors)} in {xml_path}"
        )

    records = []
    for index, (sensor, label) in enumerate(zip(sensors, CAMERA_NAMES)):
        if sensor.get("type") != "physical_camera":
            raise ValueError(f"Sensor {index} is {sensor.get('type')!r}, not 'physical_camera'")

        records.append(
            {
                "index": index,
                "label": label,
                "name": f"CH6_{index:02d}_{label}",
                "fov_degrees": _resolved_number(
                    sensor.find("float[@name='fov']"), defaults, 60.0
                ),
                "focus_distance": _resolved_number(
                    sensor.find("float[@name='focus_distance']"), defaults, 1.0
                ),
                "aperture_radius": _resolved_number(
                    sensor.find("float[@name='aperture_radius']"), defaults, 0.0
                ),
                "aperture_blades": int(
                    _resolved_number(
                        sensor.find("integer[@name='aperture_blades']"),
                        defaults,
                        0,
                    )
                ),
                "xml_matrix": sensor_world_matrix(sensor),
            }
        )
    return records, (width, height)


def comparison_collection() -> bpy.types.Collection:
    collection = bpy.data.collections.get(COLLECTION_NAME)
    if collection is None:
        collection = bpy.data.collections.new(COLLECTION_NAME)
        bpy.context.scene.collection.children.link(collection)
    elif collection.name not in bpy.context.scene.collection.children:
        # Usually already linked; this covers a collection imported from another scene.
        try:
            bpy.context.scene.collection.children.link(collection)
        except RuntimeError:
            pass
    return collection


def reference_camera() -> bpy.types.Object:
    """Return the original Blender camera corresponding to XML sensor zero."""
    if REFERENCE_CAMERA_NAME:
        camera = bpy.data.objects.get(REFERENCE_CAMERA_NAME)
        if camera is None or camera.type != "CAMERA":
            raise ValueError(
                f"REFERENCE_CAMERA_NAME={REFERENCE_CAMERA_NAME!r} does not name "
                "a Blender camera object"
            )
        return camera

    active = bpy.context.scene.camera
    if (
        active is not None
        and active.type == "CAMERA"
        and not active.name.startswith("CH6_")
    ):
        return active

    candidates = [
        item
        for item in bpy.data.objects
        if item.type == "CAMERA" and not item.name.startswith("CH6_")
    ]
    if len(candidates) == 1:
        return candidates[0]

    names = ", ".join(item.name for item in candidates) or "none"
    raise ValueError(
        "Could not identify one original Blender main camera automatically. "
        f"Non-CH6 cameras found: {names}. Set REFERENCE_CAMERA_NAME near the "
        "top of this script to the correct camera object name."
    )


def align_to_blender_scene(records: list[dict], reference: bpy.types.Object) -> None:
    """Recover the complete XML-world to Blender-world alignment."""
    xml_hero = records[0]["xml_matrix"]
    predicted_hero = xml_hero @ CAMERA_BASIS_CONVERSION
    world_alignment = reference.matrix_world.copy() @ predicted_hero.inverted()
    for record in records:
        predicted = record["xml_matrix"] @ CAMERA_BASIS_CONVERSION
        record["matrix_world"] = world_alignment @ predicted

    # Avoid tiny floating-point drift: sensor zero is the reference by design.
    records[0]["matrix_world"] = reference.matrix_world.copy()


def create_or_update_camera(record: dict, collection: bpy.types.Collection) -> bpy.types.Object:
    name = record["name"]
    camera_object = bpy.data.objects.get(name)
    if camera_object is not None and camera_object.type != "CAMERA":
        raise TypeError(f"An existing non-camera object is named {name!r}")

    if camera_object is None:
        camera_data = bpy.data.cameras.new(name)
        camera_object = bpy.data.objects.new(name, camera_data)
        collection.objects.link(camera_object)
    else:
        camera_data = camera_object.data
        if camera_object.name not in collection.objects:
            collection.objects.link(camera_object)

    camera_object.matrix_world = record["matrix_world"]
    camera_object.show_name = True
    camera_object.show_in_front = True
    camera_data.display_size = 0.20

    # The custom physical camera interprets fov as horizontal FOV.  A fixed
    # horizontal sensor fit prevents Blender from changing framing with aspect.
    camera_data.type = "PERSP"
    camera_data.sensor_fit = "HORIZONTAL"
    camera_data.sensor_width = 36.0
    fov_radians = math.radians(record["fov_degrees"])
    camera_data.lens = camera_data.sensor_width / (2.0 * math.tan(fov_radians / 2.0))

    radius = record["aperture_radius"]
    camera_data.dof.focus_distance = record["focus_distance"]
    camera_data.dof.use_dof = radius > 0.0
    if radius > 0.0:
        # The custom radius is expressed in scene metres. Blender expects an
        # f-number N = focal_length / aperture_diameter, so convert the lens
        # from millimetres to metres before dividing by 2 * radius.
        focal_length_metres = camera_data.lens / 1000.0
        camera_data.dof.aperture_fstop = focal_length_metres / (2.0 * radius)
        camera_data.dof.aperture_blades = record["aperture_blades"]

    camera_object["source"] = "Country Kitchen canonical scene.xml"
    camera_object["sensor_index"] = record["index"]
    camera_object["horizontal_fov_degrees"] = record["fov_degrees"]
    camera_object["custom_aperture_radius"] = radius
    camera_object["focus_distance"] = record["focus_distance"]
    return camera_object


def main() -> None:
    xml_path = locate_scene_xml()
    sensors, canonical_resolution = read_sensors(xml_path)
    reference = reference_camera()
    align_to_blender_scene(sensors, reference)
    collection = comparison_collection()
    cameras = [create_or_update_camera(record, collection) for record in sensors]

    current_resolution = (
        bpy.context.scene.render.resolution_x,
        bpy.context.scene.render.resolution_y,
    )
    print("\nCountry Kitchen Chapter 6 camera import")
    print(f"  Source: {xml_path}")
    print(f"  Blender reference camera: {reference.name}")
    for record, camera in zip(sensors, cameras):
        dof = (
            "pinhole"
            if record["aperture_radius"] == 0
            else f"f/{camera.data.dof.aperture_fstop:.2f}"
        )
        print(
            f"  {record['index']}: {camera.name:<18} "
            f"FOVx={record['fov_degrees']:.3f} deg, "
            f"focus={record['focus_distance']:.3f}, {dof}"
        )
    print(f"  Canonical resolution: {canonical_resolution[0]} x {canonical_resolution[1]}")
    if current_resolution != canonical_resolution:
        print(
            f"  WARNING: current Blender resolution is {current_resolution[0]} x "
            f"{current_resolution[1]}; this script intentionally did not change it."
        )
    print("  Materials, lights, world, render settings, and active camera were unchanged.\n")


if __name__ == "__main__":
    main()
