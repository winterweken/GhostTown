import json
import math
import os
import re
import tempfile

import bmesh
import bpy
from mathutils import Vector

from ghosttown import look_build, look_detail, materials, scene_build, site_use
from ghosttown.ghosttown_fetch import look_schema as ls
from helpers import closed_and_outward, fitted_doc, load_fixture, mesh_arrays

CREDIT = "Street photos © Mapillary contributors, CC BY-SA 4.0"


class Settings:
    look_detail, look_budget, look_not_before = True, 150, 0
    show_look, show_detail, look_brightness = True, True, 1.15

    def __init__(self, **changes):
        self.__dict__.update(changes)


def _build(doc=None, **options):
    return scene_build.build(bpy.context.scene, doc or load_fixture("mini_context.json"), **options)


def _apply(root, settings=None):
    return look_build.apply(bpy.context.scene, root, load_fixture("mini_look.json"), settings or Settings())


def _building(bid):
    return next(ob for ob in bpy.data.objects if ob.get("ctx_id") == bid)


def _details():
    return [ob for ob in bpy.data.objects if ob.get("ctx_kind") == "facade_detail"]


def _area(ring):
    return 0.5 * sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))


def _points(ring):
    return {tuple(p) for p in ring}


def test_mesh_solids_read_back_the_tiers_and_courtyards():
    _build()
    low, high = sorted(look_build.mesh_solids(_building("osm:way:1")), key=lambda s: s["z1"])
    assert (low["z0"], low["z1"], high["z0"], high["z1"]) == (-0.3, 12.0, -0.3, 60.0)
    assert _points(low["rings"][0]) == {(0, 10), (20, 10), (20, 30), (0, 30)} and _area(low["rings"][0]) == 400
    assert _points(high["rings"][0]) == {(5, 15), (15, 15), (15, 25), (5, 25)}
    solid, = look_build.mesh_solids(_building("osm:way:2"))
    outer, hole = solid["rings"]
    assert _area(outer) == 400 and _area(hole) == -100 and _points(hole) == {(35, 15), (35, 25), (45, 25), (45, 15)}


def test_the_request_lists_the_buildings_and_marks_selected_detail():
    root = _build()
    tower = _building("osm:way:1")
    req = look_build.make_request(root, Settings(), "/tmp/gt-cache", selected=[tower], now=0)
    assert ls.validate_request(req) == []
    assert {b["id"]: b["detail"] for b in req["buildings"]} == {"osm:way:1": True, "osm:way:2": False}
    assert req["centre"] == {"lat": 43.649667, "lon": -79.380991} and req["radius_m"] == 150.0
    assert req["ground_at_centre_m"] == 84.7 and req["budget_photos"] == 150 and req["not_before_year"] is None
    assert req["out_dir"].startswith(os.path.join("/tmp/gt-cache", "runs", "look-"))
    off = look_build.make_request(root, Settings(look_detail=False, look_not_before=2019), "/tmp/gt-cache",
                                  selected=[tower], now=0)
    assert not any(b["detail"] for b in off["buildings"]) and off["not_before_year"] == 2019


def test_a_building_without_bottom_faces_is_left_out():
    root = _build()
    tower = _building("osm:way:1")
    bm = bmesh.new()
    bm.from_mesh(tower.data)
    bm.normal_update()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.normal.z < -0.99], context="FACES")
    bm.to_mesh(tower.data)
    bm.free()
    assert look_build.mesh_solids(tower) == []
    req = look_build.make_request(root, Settings(), "/tmp/gt-cache", selected=[tower], now=0)
    assert [b["id"] for b in req["buildings"]] == ["osm:way:2"] and ls.validate_request(req) == []


def test_apply_sets_properties_materials_credits_and_detail():
    root = _build()
    before = site_use.count_triangles(root, bpy.context.evaluated_depsgraph_get())
    assert _apply(root) == "Look from photos: 1 building · guessed: 1 · 3 photos (2019–2025)"
    assert root[look_build.SUMMARY_PROP].startswith("Look from photos") and root[look_build.CREDITS_PROP] == CREDIT
    tower = _building("osm:way:1")
    assert tower["gt_look_on"] == 1.0 and abs(tower["gt_look_base_z"] + 0.3) < 1e-6 and tower["gt_look_floor_h"] == 3.5
    assert [tower[f"gt_look_z{n}_kind"] for n in range(1, 5)] == [1.0, 2.0, 3.0, 0.0]
    assert [tower[f"gt_look_z{n}_top"] for n in range(1, 5)] == [3.0, 12.0, look_build.TOP, look_build.TOP]
    assert [round(c, 6) for c in tower["gt_look_z2_colour"]] == [0.3, 0.12, 0.08]
    guessed = _building("osm:way:2")
    assert guessed["gt_look_source"] == "guessed" and guessed["gt_look_z2_top"] == look_build.TOP
    names = sorted(m.name for m in bpy.data.materials if m.name.startswith("Context - "))
    assert names == sorted(["Context - Building", "Context - Building (height guessed)", "Context - Road",
                            "Context - Tree", "Context - Parcel", "Context - Facade detail"])
    for name in ("Context - Building", "Context - Building (height guessed)"):
        assert bpy.data.materials[name].node_tree.nodes.get(materials.LOOK_NODE) is not None
    assert bpy.data.materials["Context - Road"].node_tree.nodes.get(materials.LOOK_NODE) is None
    origin, = [ob for ob in root.objects if ob.get("ctx_id") == "origin"]
    for block in (root, origin):
        assert block["credits"].splitlines() == ["© OpenStreetMap contributors", CREDIT]
    detail, = _details()
    coll = detail.users_collection[0]
    assert detail.name == "Detail · Tower" and detail["ctx_id"] == "detail:osm:way:1"
    assert coll.get("ctx_group") == "Detail" and coll.name in root.children
    assert detail.name in json.loads(root["ctx_objects"]) and detail.data.materials[0].name == "Context - Facade detail"
    entry = load_fixture("mini_look.json")["buildings"]["osm:way:1"]
    assert len(detail.data.polygons) == len(look_detail.boxes(entry, base_z=-0.3)[1])
    assert closed_and_outward(*mesh_arrays(detail))
    triangles = sum(len(p.vertices) - 2 for p in detail.data.polygons)   # the detail counts for Revit
    assert site_use.count_triangles(root, bpy.context.evaluated_depsgraph_get()) == before + triangles


def test_the_renderer_sees_the_values_of_buildings_already_on_screen():
    root = _build()
    tower = _building("osm:way:1")
    assert "gt_look_on" not in tower.evaluated_get(bpy.context.evaluated_depsgraph_get())   # evaluated, as when shown
    _apply(root)
    assert tower.evaluated_get(bpy.context.evaluated_depsgraph_get())["gt_look_on"] == 1.0


def test_switches():
    root = _build()
    _apply(root, Settings(show_look=False, show_detail=False, look_brightness=0.8))
    node = bpy.data.materials["Context - Building"].node_tree.nodes[materials.LOOK_NODE]
    assert node.inputs["Look"].default_value == 0.0 and abs(node.inputs["Brightness"].default_value - 0.8) < 1e-6
    coll = _details()[0].users_collection[0]
    assert coll.hide_viewport and coll.hide_render
    look_build.set_show_detail(bpy.context.scene, True)
    assert not coll.hide_viewport and not coll.hide_render


def test_a_rebuild_keeps_the_look_and_regenerates_detail():
    _apply(_build())
    root = _build()
    assert json.loads(root[look_build.LOOK_PROP])["photos_used"] == 3 and CREDIT in root["credits"]
    assert root[look_build.SUMMARY_PROP] == "Look from photos: 1 building · guessed: 1 · 3 photos (2019–2025)"
    tower = _building("osm:way:1")
    assert tower["gt_look_on"] == 1.0 and tower["gt_look_z3_kind"] == 3.0
    detail, = _details()
    assert detail.name == "Detail · Tower" and detail.name in json.loads(root["ctx_objects"])
    assert all(me.users > 0 for me in bpy.data.meshes)


def test_a_rebuild_without_keep_drops_the_look():
    _apply(_build())
    root = _build(keep_look=False)
    assert look_build.LOOK_PROP not in root and "gt_look_on" not in _building("osm:way:1")
    assert _details() == [] and all(me.users > 0 for me in bpy.data.meshes) and CREDIT not in root["credits"]


def test_reapply_skips_buildings_that_are_gone():
    root = _build()
    _apply(root)
    bpy.data.objects.remove(_building("osm:way:1"))
    look_build.reapply(bpy.context.scene, root)
    assert _details() == [] and not [c for c in root.children if c.get("ctx_group") == "Detail"]
    assert not any(name.startswith("Detail") for name in json.loads(root["ctx_objects"]))
    assert _building("osm:way:2")["gt_look_on"] == 1.0


def _exported_material_names():
    folder = tempfile.mkdtemp()
    bpy.ops.wm.obj_export(filepath=os.path.join(folder, "site.obj"), export_materials=True)
    with open(os.path.join(folder, "site.mtl"), encoding="utf-8") as f:   # OBJ writes spaces as underscores
        from_obj = {line[len("newmtl "):].strip().replace("_", " ") for line in f if line.startswith("newmtl ")}
    bpy.ops.export_scene.fbx(filepath=os.path.join(folder, "site.fbx"))
    with open(os.path.join(folder, "site.fbx"), "rb") as f:   # binary FBX names objects "<name>\x00\x01<class>"
        from_fbx = {m.decode("utf-8") for m in re.findall(rb"(Context - [^\x00]+)\x00\x01Material", f.read())}
    return from_obj, from_fbx


def test_export_keeps_todays_material_names():
    root = _build()
    before_obj, before_fbx = _exported_material_names()
    _apply(root)
    after_obj, after_fbx = _exported_material_names()
    assert "Context - Building" in before_obj and "Context - Building" in before_fbx
    assert after_obj == before_obj | {"Context - Facade detail"}
    assert after_fbx == before_fbx | {"Context - Facade detail"}


def test_roof_shapes_share_the_look_and_the_request_reads_the_flat_mesh():
    folder = tempfile.mkdtemp()
    root = _build(fitted_doc(folder), folder=folder)
    tower = _building("osm:way:1")
    assert tower.data != tower[site_use.FLAT_KEY]   # a fitted roof shows after the build
    low, high = sorted(look_build.mesh_solids(tower), key=lambda s: s["z1"])
    assert (low["z1"], high["z1"]) == (12.0, 60.0)
    _apply(root)
    for use in ("lidar", "flat", "fitted"):
        site_use.apply_roof_shapes(root, use)
        assert tower["gt_look_on"] == 1.0 and abs(tower["gt_look_base_z"] + 0.3) < 1e-6
        assert any(m.node_tree.nodes.get(materials.LOOK_NODE) for m in tower.data.materials if m is not None)


def test_the_users_duplicates_are_neither_asked_about_nor_dressed():
    root = _build()
    tower = _building("osm:way:1")
    copy = tower.copy()
    copy.data = tower.data.copy()
    root.children["Buildings · 320 Bay St"].objects.link(copy)
    req = look_build.make_request(root, Settings(), "/tmp/gt-cache", now=0)
    assert sorted(b["id"] for b in req["buildings"]) == ["osm:way:1", "osm:way:2"]
    _apply(root)
    assert "gt_look_on" not in copy and tower["gt_look_on"] == 1.0


def test_add_sky_only_over_blenders_default_world():
    scene = bpy.context.scene
    assert scene.world is None and look_build.can_add_sky(scene)
    scene.world = bpy.data.worlds.new("World")
    assert scene.world.name == "World" and look_build.can_add_sky(scene)
    world = look_build.add_sky(scene)
    assert scene.world == world and world.name == look_build.SKY_WORLD and not look_build.can_add_sky(scene)
    sky = next(n for n in world.node_tree.nodes if n.bl_idname == "ShaderNodeTexSky")
    assert sky.sky_type == "MULTIPLE_SCATTERING" and not sky.sun_disc
    sun = bpy.data.objects[look_build.SKY_SUN]
    assert sun.data.type == "SUN" and sun.name in scene.collection.objects
    scene.world = bpy.data.worlds.new("Studio")
    assert not look_build.can_add_sky(scene)


def _sky_brightness(direction):
    """Mean rendered brightness of the world seen through a narrow camera pointing along direction."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 4
    scene.cycles.device = "CPU"
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x = scene.render.resolution_y = 16
    cam = scene.camera or bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    if scene.camera is None:
        scene.collection.objects.link(cam)
        scene.camera = cam
    cam.data.angle = math.radians(4)
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    path = os.path.join(tempfile.mkdtemp(), "sky.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    px = bpy.data.images.load(path).pixels[:]
    return sum(px[0::4]) / (len(px) / 4)


def test_the_sky_glows_where_the_sun_lamp_shines_from():
    look_build.add_sky(bpy.context.scene)
    sun = bpy.data.objects[look_build.SKY_SUN]
    sun.hide_render = True
    bpy.context.view_layer.update()
    to_sun = (sun.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
    mirrored = Vector((-to_sun.x, to_sun.y, to_sun.z))   # where the glow would be with east and west swapped
    bright, other = _sky_brightness(to_sun), _sky_brightness(mirrored)
    assert bright > 1.1 * other
