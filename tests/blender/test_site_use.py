import os
import tempfile

import bmesh
import bpy

import ghosttown
from ghosttown import site_use
from test_site_photo import buildings, ground, photo_site


def _names(ob):
    return [m.name for m in ob.data.materials]


def test_ground_switches_between_photo_and_colours():
    root, _ = photo_site()
    road, = ground(root)
    site_use.apply_ground(root, "colours")
    assert road.material_slots[0].link == "DATA" and root["use_ground"] == "colours"
    site_use.apply_ground(root, "photo")
    assert road.material_slots[0].link == "OBJECT" and root["use_ground"] == "photo"


def test_roof_photo_covers_upward_faces_of_buildings_under_the_limit():
    root, _ = photo_site()
    tower, shed = buildings(root)
    before = [p.material_index for p in shed.data.polygons]
    assert site_use.apply_roofs(root, "photo", 20.0) == 0
    photo = root["ctx_photo_material"]
    assert photo not in _names(tower)  # 60.3 m tall: over the limit
    assert _names(shed)[-1] == photo
    slot = len(shed.data.materials) - 1
    for polygon, old in zip(shed.data.polygons, before):
        assert polygon.material_index == (slot if polygon.normal.z > 0.5 else old)
    assert root["use_roofs"] == "photo" and root["roof_photo_max_m"] == 20.0


def test_plain_roofs_restore_every_index_and_leave_no_trace():
    root, _ = photo_site()
    shed = buildings(root)[1]
    before, names = [p.material_index for p in shed.data.polygons], _names(shed)
    site_use.apply_roofs(root, "photo", 20.0)
    site_use.apply_roofs(root, "photo", 20.0)  # applying twice must not stack slots
    assert len(shed.data.materials) == len(names) + 1
    site_use.apply_roofs(root, "plain")
    assert [p.material_index for p in shed.data.polygons] == before and _names(shed) == names
    assert site_use.INDEX_ATTR not in shed.data.attributes and root["use_roofs"] == "plain"


def test_raising_the_limit_takes_in_taller_buildings():
    root, _ = photo_site()
    tower, _shed = buildings(root)
    site_use.apply_roofs(root, "photo", 100.0)
    assert _names(tower)[-1] == root["ctx_photo_material"]
    site_use.apply_roofs(root, "photo", 20.0)
    assert root["ctx_photo_material"] not in _names(tower)


def test_an_edited_building_switches_back_safely():
    root, _ = photo_site()
    shed = buildings(root)[1]
    site_use.apply_roofs(root, "photo", 20.0)
    bm = bmesh.new()
    bm.from_mesh(shed.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])  # the user remeshed the building
    bm.to_mesh(shed.data)
    bm.free()
    site_use.apply_roofs(root, "plain")
    count = len(shed.data.materials)
    assert root["ctx_photo_material"] not in _names(shed)
    assert all(p.material_index < count for p in shed.data.polygons)
    assert site_use.INDEX_ATTR not in shed.data.attributes


def test_a_mesh_whose_saved_indices_no_longer_fit_is_reset_and_counted():
    root, _ = photo_site()
    shed = buildings(root)[1]
    site_use.apply_roofs(root, "photo", 20.0)
    shed.data.attributes.remove(shed.data.attributes[site_use.INDEX_ATTR])
    shed.data.attributes.new(site_use.INDEX_ATTR, "INT", "POINT")  # wrong length: it can't be trusted
    assert site_use.apply_roofs(root, "plain") == 1
    assert all(p.material_index < len(shed.data.materials) for p in shed.data.polygons)


def test_two_sites_keep_their_own_choices():
    first, _ = photo_site()
    second, _ = photo_site(address="Second site")
    site_use.apply_ground(first, "colours")
    assert ground(first)[0].material_slots[0].link == "DATA"
    assert ground(second)[0].material_slots[0].link == "OBJECT"
    assert ground(second)[0].material_slots[0].material.name == "Site photo · Second site"


def test_the_switches_act_on_the_picked_site():
    ghosttown.register()
    try:
        root, _ = photo_site()
        settings = bpy.context.scene.ghosttown
        settings.site = root
        assert bpy.ops.ghosttown.use_ground(use="colours") == {"FINISHED"} and root["use_ground"] == "colours"
        assert bpy.ops.ghosttown.use_roofs(use="photo") == {"FINISHED"} and root["use_roofs"] == "photo"
        tower = buildings(root)[0]
        assert root["ctx_photo_material"] not in _names(tower)
        settings.roof_photo_max_m = 100.0  # the field re-applies photo roofs
        assert _names(tower)[-1] == root["ctx_photo_material"] and root["roof_photo_max_m"] == 100.0
    finally:
        ghosttown.unregister()


def test_the_switches_wait_for_a_site_with_a_photo():
    ghosttown.register()
    try:
        assert not bpy.ops.ghosttown.use_ground.poll() and not bpy.ops.ghosttown.use_roofs.poll()
    finally:
        ghosttown.unregister()


def test_without_its_material_a_site_has_no_photo_and_the_switches_wait():
    ghosttown.register()
    try:
        root, _ = photo_site()
        bpy.context.scene.ghosttown.site = root
        assert site_use.has_photo(root) and bpy.ops.ghosttown.use_ground.poll() and bpy.ops.ghosttown.use_roofs.poll()
        bpy.data.materials.remove(site_use.photo_material(root))
        assert not site_use.has_photo(root) and site_use.photo_material(root) is None
        assert not bpy.ops.ghosttown.use_ground.poll() and not bpy.ops.ghosttown.use_roofs.poll()
        assert site_use.photo_image(root) is not None and bpy.ops.ghosttown.save_photo.poll()
        bpy.data.images.remove(site_use.photo_image(root))
        assert not bpy.ops.ghosttown.save_photo.poll()
    finally:
        ghosttown.unregister()


def test_an_older_file_finds_the_photo_by_name():
    root, _ = photo_site()
    del root["ctx_photo_material_id"], root["ctx_photo_image_id"]
    assert site_use.photo_material(root).name == root["ctx_photo_material"]
    assert site_use.photo_image(root).name == root["ctx_photo_image"]


def _enter_edit_mode(ob):
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")


def _state(ob):
    # Hidden attributes (".uv_select_face" and the like) come and go when Blender enters and leaves Edit Mode.
    attributes = {a.name for a in ob.data.attributes if not a.name.startswith(".")}
    return _names(ob), [p.material_index for p in ob.data.polygons], attributes


def test_changing_the_limit_in_edit_mode_leaves_buildings_intact():
    ghosttown.register()
    try:
        root, _ = photo_site()
        settings = bpy.context.scene.ghosttown
        settings.site = root
        tower, shed = buildings(root)
        site_use.apply_roofs(root, "photo", 20.0)
        before = _state(shed)
        _enter_edit_mode(shed)
        try:
            settings.roof_photo_max_m = 100.0  # the update must not touch the mesh being edited
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")
        assert _state(shed) == before
        assert all(p.material_index < len(shed.data.materials) for p in shed.data.polygons)
        assert root["roof_photo_max_m"] == 100.0 and root["use_roofs"] == "photo"
        assert root["ctx_photo_material"] not in _names(tower)
        site_use.apply_roofs(root, "photo", 100.0)
        assert _names(tower)[-1] == root["ctx_photo_material"]
    finally:
        ghosttown.unregister()


def test_apply_roofs_skips_a_building_in_edit_mode():
    root, _ = photo_site()
    tower, shed = buildings(root)
    site_use.apply_roofs(root, "photo", 20.0)
    before = _state(shed)
    _enter_edit_mode(shed)
    try:
        site_use.apply_roofs(root, "photo", 100.0)  # the limit now takes in the tower; the shed is being edited
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    assert _state(shed) == before
    assert _names(tower)[-1] == root["ctx_photo_material"]
    site_use.apply_roofs(root, "plain")
    assert root["ctx_photo_material"] not in _names(shed) and site_use.INDEX_ATTR not in shed.data.attributes
