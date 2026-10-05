"""How a site uses its fetched data: which material its ground and its roofs show.
Only Blender data changes; nothing is fetched again."""
import json

import bpy
import numpy as np

from .ghosttown_fetch import BUILDING_KINDS, GROUND_KINDS

ROOF_NORMAL_Z = 0.5             # faces pointing up at least this much count as roof (pitched ones too)
INDEX_ATTR = "ctx_material_index"
FLAT_KEY, FITTED_KEY, LIDAR_KEY = "ctx_mesh_flat", "ctx_mesh_fitted", "ctx_mesh_lidar"  # a building's meshes
SHAPE_KEYS = {"flat": FLAT_KEY, "fitted": FITTED_KEY, "lidar": LIDAR_KEY}  # roof shape -> the mesh's ID property
ROOF_GROUP = "roof interior"    # LiDAR roof vertices off the outline: the only ones Roof detail may move
DETAIL_MODIFIER = "Ghost Town roof detail"
SITE_KINDS = BUILDING_KINDS + GROUND_KINDS + ("tree", "parcel", "parcel_on_site")


def made_objects(root, kinds):
    """The site's own objects of these kinds: ones Ghost Town made, not the user's duplicates."""
    names = set(json.loads(root.get("ctx_objects", "[]")))
    return [ob for ob in root.all_objects if ob.name in names and ob.get("ctx_kind") in kinds]


def _photo_block(root, id_key, name_key, blocks):
    if id_key in root:
        return root[id_key]  # the pointer; None once the datablock has been deleted
    return blocks.get(root.get(name_key, ""))  # files made before the pointers existed


def photo_material(root):
    """The site's photo material, or None when it is gone."""
    return _photo_block(root, "ctx_photo_material_id", "ctx_photo_material", bpy.data.materials)


def photo_image(root):
    """The site's photo image, or None when it is gone."""
    return _photo_block(root, "ctx_photo_image_id", "ctx_photo_image", bpy.data.images)


def has_photo(root):
    """True while the site's photo material exists, which is what the photo switches need."""
    return photo_material(root) is not None


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


def meshes_of(ob):
    """The meshes a building can show: the one in use, and its other roof shapes when it has them."""
    out = [ob.data]
    for key in SHAPE_KEYS.values():
        me = ob.get(key)
        if me is not None and me not in out:
            out.append(me)
    return out


def roof_choices(root):
    """The roof shapes the site's buildings can show, in the panel's order: flat always, fitted and LiDAR
    when any building has them."""
    obs = made_objects(root, BUILDING_KINDS)
    return [use for use in SHAPE_KEYS if use == "flat" or any(ob.get(SHAPE_KEYS[use]) is not None for ob in obs)]


def has_lidar(root):
    """True while the site's buildings have roof shapes from the LiDAR (fitted or sampled) to switch to."""
    return root.get("use_roof_shapes") in SHAPE_KEYS and len(roof_choices(root)) > 1


def has_fitted(root):
    """True while the site's buildings have fitted roofs."""
    return root.get("use_roof_shapes") in SHAPE_KEYS and "fitted" in roof_choices(root)


def _detail(ob, ratio):
    """Roof detail on one building: a Decimate (Collapse) modifier limited to the roof interior, so walls
    and eaves stay put; only while the building shows its LiDAR roof, and none at 100 %."""
    mod = ob.modifiers.get(DETAIL_MODIFIER)
    lidar = ob.get(LIDAR_KEY)
    if ratio >= 1.0 or lidar is None or ob.data != lidar:
        if mod is not None:
            ob.modifiers.remove(mod)
        return
    if mod is None:
        mod = ob.modifiers.new(DETAIL_MODIFIER, "DECIMATE")
        mod.decimate_type = "COLLAPSE"
        mod.vertex_group = ROOF_GROUP
        mod.use_collapse_triangulate = True
    mod.ratio = ratio


def apply_roof_shapes(root, use):
    """`use` is "flat", "fitted" or "lidar": each building shows that mesh. The roof photo choice moves to the mesh
    now shown (the other is left plain), and Roof detail follows. Buildings in Edit Mode are skipped.
    Returns how many buildings were reset rather than restored exactly."""
    material = photo_material(root)
    photo = root.get("use_roofs") == "photo" and material is not None
    limit = float(root.get("roof_photo_max_m", 20.0))
    ratio = float(root.get("roof_detail", 1.0))
    reset = 0
    for ob in made_objects(root, BUILDING_KINDS):
        target = ob.get(SHAPE_KEYS[use]) if use in SHAPE_KEYS else None
        if target is None or ob.data.is_editmode:
            continue
        if ob.data != target:
            if photo and not _restore_roofs(ob, material):
                reset += 1
            ob.data = target
            if photo and float(ob.get("ctx_height_m", 0.0)) <= limit:
                _photo_roofs(ob, material)
        _detail(ob, ratio)
    root["use_roof_shapes"] = use
    return reset


def apply_roof_detail(root, ratio):
    """Roof detail from 5 % to 100 % on every building showing its LiDAR roof."""
    ratio = min(1.0, max(0.05, float(ratio)))
    root["roof_detail"] = ratio
    for ob in made_objects(root, BUILDING_KINDS):
        _detail(ob, ratio)


def count_triangles(root, depsgraph):
    """The triangles the site exports with modifiers applied (buildings, ground, trees; parcels are
    lines), stored on the root as ctx_triangles. Never call this while a panel draws."""
    total = 0
    for ob in made_objects(root, SITE_KINDS):
        me = ob.evaluated_get(depsgraph).data
        sizes = np.empty(len(me.polygons), dtype=np.int32)
        me.polygons.foreach_get("loop_total", sizes)
        total += int(np.clip(sizes - 2, 0, None).sum())
    root["ctx_triangles"] = total
    return total


_scheduled = {}  # site name -> the function its timer will run


def count_later(root, delay=0.3):
    """Count the site's triangles shortly after a change: a dragged slider changes many times, and an
    update callback is no place to evaluate the scene. Returns the scheduled function (tests call it).
    A site counts as pending only while its timer is registered: loading a file drops timers."""
    name = root.name

    def run():
        if _scheduled.get(name) is run:
            del _scheduled[name]
        site = bpy.data.collections.get(name)
        if site is not None and site.get("ctx_root"):
            count_triangles(site, bpy.context.evaluated_depsgraph_get())
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == "VIEW_3D":
                        area.tag_redraw()
        return None

    pending = _scheduled.get(name)
    if pending is not None and bpy.app.timers.is_registered(pending):
        return pending
    _scheduled[name] = run
    bpy.app.timers.register(run, first_interval=delay)
    return run
