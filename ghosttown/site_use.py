"""How a site uses its fetched data: which material its ground and its roofs show.
Only Blender data changes; nothing is fetched again."""
import json

import bpy
import numpy as np

from .ghosttown_fetch import BUILDING_KINDS, GROUND_KINDS

ROOF_NORMAL_Z = 0.5             # faces pointing up at least this much count as roof (pitched ones too)
INDEX_ATTR = "ctx_material_index"


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


def picked(context):
    """The site the Site panel shows, if it is a context collection in this scene."""
    root = context.scene.ghosttown.site
    if root is None or not root.get("ctx_root") or root not in context.scene.collection.children_recursive:
        return None
    return root


def _restore_roofs(ob, material):
    """Undo photo roofs on one building. False when the saved indices no longer fit the mesh and
    were reset instead."""
    me = ob.data
    exact = True
    saved = me.attributes.get(INDEX_ATTR)
    if saved is not None:
        if saved.domain == "FACE" and len(saved.data) == len(me.polygons):
            values = np.empty(len(saved.data), dtype=np.int32)
            saved.data.foreach_get("value", values)
            me.polygons.foreach_set("material_index", values)
        else:
            exact = False
        me.attributes.remove(saved)
    for i in reversed(range(len(me.materials))):
        if material is not None and me.materials[i] == material:
            me.materials.pop(index=i)
    count = max(len(me.materials), 1)
    indices = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("material_index", indices)
    if (indices >= count).any():
        exact = False
        indices[indices >= count] = 0
        me.polygons.foreach_set("material_index", indices)
    me.update()
    return exact


def _photo_roofs(ob, material):
    me = ob.data
    n = len(me.polygons)
    indices = np.empty(n, dtype=np.int32)
    me.polygons.foreach_get("material_index", indices)
    saved = me.attributes.new(INDEX_ATTR, "INT", "FACE")
    saved.data.foreach_set("value", indices)
    normals = np.empty(n * 3, dtype=np.float32)
    me.polygons.foreach_get("normal", normals)
    me.materials.append(material)
    indices[normals.reshape(-1, 3)[:, 2] > ROOF_NORMAL_Z] = len(me.materials) - 1
    me.polygons.foreach_set("material_index", indices)
    me.update()


def apply_roofs(root, use, max_m=None):
    """`use` is "photo" or "plain". Photo roofs go on buildings up to the limit (taller ones lean in
    the photo, so their roof texture would be offset). Buildings in Edit Mode are skipped. Returns how
    many buildings were reset rather than restored exactly."""
    if max_m is not None:
        root["roof_photo_max_m"] = float(max_m)
    limit = float(root.get("roof_photo_max_m", 20.0))
    material = photo_material(root)
    reset = 0
    for ob in made_objects(root, BUILDING_KINDS):
        if ob.data.is_editmode:
            continue  # its mesh data is out of date until the user leaves Edit Mode; leave it as it is
        if not _restore_roofs(ob, material):
            reset += 1
        if use == "photo" and material is not None and float(ob.get("ctx_height_m", 0.0)) <= limit:
            _photo_roofs(ob, material)
    root["use_roofs"] = use
    return reset
