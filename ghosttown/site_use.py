"""How a site uses its fetched data: which material its ground shows (and, in Task 5, its roofs).
Only Blender data changes; nothing is fetched again."""
import json

import bpy

from .ghosttown_fetch import GROUND_KINDS


def made_objects(root, kinds):
    """The site's own objects of these kinds: ones Ghost Town made, not the user's duplicates."""
    names = set(json.loads(root.get("ctx_objects", "[]")))
    return [ob for ob in root.all_objects if ob.name in names and ob.get("ctx_kind") in kinds]


def photo_material(root):
    return bpy.data.materials.get(root.get("ctx_photo_material", ""))


def apply_ground(root, use):
    """`use` is "photo" or "colours". The photo goes in an object-level slot, so each mesh keeps its
    Context - <Kind> material underneath and switching back costs nothing."""
    material = photo_material(root)
    for ob in made_objects(root, GROUND_KINDS):
        if not ob.material_slots:
            continue
        slot = ob.material_slots[0]
        if use == "photo" and material is not None:
            slot.link = "OBJECT"
            slot.material = material
        else:
            slot.link = "DATA"
    root["use_ground"] = use
