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
LABELS = "Labels from Mapillary · https://www.mapillary.com"


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


def _look_props(root):
    return [key for key in (look_build.LOOK_PROP, look_build.SUMMARY_PROP, look_build.CREDITS_PROP) if key in root]


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
    assert root[look_build.SUMMARY_PROP].startswith("Look from photos")
    assert root[look_build.CREDITS_PROP] == CREDIT + "\n" + LABELS   # the panel's two credit lines
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
        assert block["credits"].splitlines() == ["© OpenStreetMap contributors", CREDIT, LABELS]
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


def test_detail_sits_on_the_buildings_base():
    root = _build()
    _apply(root)
    detail, = _details()
    zs = [v.co.z for v in detail.data.vertices]
    # base_z is -0.3: the lowest detail is the storefront band (3.0 - 0.15 above it), the highest a fin's top (60.3)
    assert abs(min(zs) - (-0.3 + 2.85)) < 1e-6 and abs(max(zs) - (-0.3 + 60.3)) < 1e-6


def test_a_moved_building_is_read_and_dressed_in_world_space():
    root = _build()
    tower = _building("osm:way:1")
    tower.location = (100.0, 50.0, 7.0)
    bpy.context.view_layer.update()
    low = min(look_build.mesh_solids(tower), key=lambda s: s["z1"])
    assert sorted(map(tuple, low["rings"][0])) == [(100.0, 60.0), (100.0, 80.0), (120.0, 60.0), (120.0, 80.0)]
    assert (low["z0"], low["z1"]) == (6.7, 19.0)
    _apply(root)
    assert abs(tower["gt_look_base_z"] - 6.7) < 1e-6


def test_summary_counts_and_wording():
    answer = load_fixture("mini_look.json")
    answer["buildings"]["osm:way:3"] = dict(answer["buildings"]["osm:way:1"])   # a second one from photos
    assert look_build.summary(answer, {"osm:way:1", "osm:way:2", "osm:way:3"}) == \
        "Look from photos: 2 buildings · guessed: 1 · 3 photos (2019–2025)"
    answer["photos_used"], answer["years"] = 1, [2019, 2019]
    assert look_build.summary(answer, {"osm:way:1", "osm:way:2"}) == \
        "Look from photos: 1 building · guessed: 1 · 1 photo (2019)"
    answer["photos_used"], answer["years"] = 0, None
    assert look_build.summary(answer, {"osm:way:2"}) == "Look from photos: 0 buildings · guessed: 1"


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


def _look_with_two_detail_buildings():
    """mini_look.json with detail on the courtyard building too, along its south wall."""
    answer = load_fixture("mini_look.json")
    answer["buildings"]["osm:way:2"]["detail_walls"] = [{"a": [30, 10], "b": [50, 10], "n": [0, -1],
                                                         "z0": 0.0, "z1": 9.3}]
    return answer


def _context_with_the_tower_moved(dx):
    """mini_context.json fetched around a nudged centre: the same site and label, the tower dx metres east."""
    doc = load_fixture("mini_context.json")
    tower = next(el for el in doc["elements"] if el["id"] == "osm:way:1")
    for solid in tower["solids"]:
        solid["rings"] = [[[x + dx, y] for x, y in ring] for ring in solid["rings"]]
    return doc


def test_a_rebuild_drops_the_detail_of_a_building_whose_walls_moved():
    look_build.apply(bpy.context.scene, _build(), _look_with_two_detail_buildings(), Settings())
    both = ["detail:osm:way:1", "detail:osm:way:2"]
    assert sorted(d["ctx_id"] for d in _details()) == both
    _build(_context_with_the_tower_moved(0.3))   # within half a metre the stored walls still lie on the tower
    assert sorted(d["ctx_id"] for d in _details()) == both
    root = _build(_context_with_the_tower_moved(2.0))
    courtyard, = _details()   # the tower's bands would float 2 m off its facade
    assert courtyard["ctx_id"] == "detail:osm:way:2" and courtyard.name in json.loads(root["ctx_objects"])
    entry = _look_with_two_detail_buildings()["buildings"]["osm:way:2"]
    assert len(courtyard.data.polygons) == len(look_detail.boxes(entry, base_z=-0.3)[1]) > 0
    tower = _building("osm:way:1")
    assert tower["gt_look_on"] == 1.0 and tower["gt_look_z3_kind"] == 3.0   # its shader look stays
    assert all(me.users > 0 for me in bpy.data.meshes)


def test_a_rebuild_without_keep_drops_the_look():
    _apply(_build())
    root = _build(keep_look=False)
    assert look_build.LOOK_PROP not in root and "gt_look_on" not in _building("osm:way:1")
    assert _details() == [] and all(me.users > 0 for me in bpy.data.meshes) and CREDIT not in root["credits"]


def test_applying_twice_replaces_the_detail_and_keeps_one_of_everything():
    root = _build()
    _apply(root)
    _apply(root)
    assert len(_details()) == 1
    assert len([c for c in root.children if c.get("ctx_group") == "Detail"]) == 1
    assert sum(1 for name in json.loads(root["ctx_objects"]) if name.startswith("Detail")) == 1
    assert all(me.users > 0 for me in bpy.data.meshes)   # the first detail mesh went with its object
    assert root["credits"].splitlines() == ["© OpenStreetMap contributors", CREDIT, LABELS]


def test_reapply_drops_a_damaged_look_but_a_bug_stays_loud():
    # Only the errors a damaged or hand-edited look raises drop it; anything else is a bug, and the look stays.
    root = _build()
    _apply(root)

    def broken(root, sources):
        raise RuntimeError("a bug")

    real = look_build._credit
    look_build._credit = broken
    try:
        look_build.reapply(bpy.context.scene, root)
    except RuntimeError:
        pass
    else:
        raise AssertionError("reapply should have raised the bug")
    finally:
        look_build._credit = real
    assert look_build.LOOK_PROP in root


def test_reapply_skips_buildings_that_are_gone():
    root = _build()
    _apply(root)
    bpy.data.objects.remove(_building("osm:way:1"))
    assert look_build.reapply(bpy.context.scene, root) is False   # the look stays for the buildings still there
    assert _details() == [] and not [c for c in root.children if c.get("ctx_group") == "Detail"]
    assert not any(name.startswith("Detail") for name in json.loads(root["ctx_objects"]))
    assert _building("osm:way:2")["gt_look_on"] == 1.0


def test_a_corrupt_stored_look_is_dropped():
    def damaged(change):
        answer = load_fixture("mini_look.json")
        change(answer)
        return answer

    unappliable = {   # all but the last pass the validation; applying them raises these
        KeyError: damaged(lambda a: a["sources"][0].pop("credit")),
        TypeError: damaged(lambda a: a.update(sources=["Mapillary"])),
        ValueError: damaged(lambda a: a["buildings"]["osm:way:1"].update(confidence="high")),
        IndexError: damaged(lambda a: a.update(years=[2019])),
        AttributeError: damaged(lambda a: a.update(buildings=[])),   # validating this raises too
    }
    for error, answer in unappliable.items():
        root = _build()
        try:
            look_build.apply(bpy.context.scene, root, answer, Settings())
        except error:
            pass
        else:
            raise AssertionError(f"apply should have raised {error.__name__}")
        assert look_build.LOOK_PROP not in root   # so a rebuild has nothing broken to carry over
    stored = ["", "not json", "[]", "null", '{"schema": 9}'] + [json.dumps(a) for a in unappliable.values()]
    for text in stored:
        root = _build()
        root[look_build.LOOK_PROP] = text
        root[look_build.SUMMARY_PROP] = root[look_build.CREDITS_PROP] = "old"
        assert look_build.reapply(bpy.context.scene, root) is True   # nothing raises; the caller hears it was dropped
        assert _look_props(root) == [], text
        root[look_build.LOOK_PROP] = text
        assert _look_props(_build()) == [], text   # nor does a rebuild that carries it over


def test_a_dropped_look_leaves_the_plain_look_and_no_detail():
    no_credit = load_fixture("mini_look.json")   # dresses the buildings, then fails on the source
    del no_credit["sources"][0]["credit"]
    one_year = load_fixture("mini_look.json")   # dresses them and makes the detail, then fails on the years
    one_year["years"] = [2019]
    for answer in (no_credit, one_year):
        root = _build()
        root[look_build.LOOK_PROP] = json.dumps(answer)
        root = _build()   # the rebuild carries the look over, can't apply it, and drops it
        buildings = look_build.made_buildings(root)
        assert len(buildings) == 2 and all(ob.get("gt_look_on") == 0.0 for ob in buildings)
        assert not [c for c in root.children if c.get("ctx_group") == "Detail"] and _details() == []
        assert not any(name.startswith("Detail") for name in json.loads(root["ctx_objects"]))
        assert _look_props(root) == []


def test_the_renderer_sees_a_dropped_look_on_buildings_already_on_screen():
    root = _build()
    _apply(root)
    tower = _building("osm:way:1")
    assert tower.evaluated_get(bpy.context.evaluated_depsgraph_get())["gt_look_on"] == 1.0   # evaluated, as when shown
    root[look_build.LOOK_PROP] = "not json"
    look_build.reapply(bpy.context.scene, root)
    assert tower.evaluated_get(bpy.context.evaluated_depsgraph_get())["gt_look_on"] == 0.0


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
    for world in [w for w in bpy.data.worlds if w.name == "World"]:
        bpy.data.worlds.remove(world)
    scene.world = bpy.data.worlds.new("World")   # Blender's name, but the user gave it an environment image
    scene.world.node_tree.nodes.new("ShaderNodeTexEnvironment")
    assert scene.world.name == "World" and not look_build.can_add_sky(scene)


def _sky_brightness(direction):
    """Mean rendered brightness of the world seen through a narrow camera pointing along direction, read from a
    32-bit EXR: scene-linear, so the bright side never clips at 1 as an 8-bit picture does."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 4
    scene.cycles.device = "CPU"
    scene.render.image_settings.file_format, scene.render.image_settings.color_depth = "OPEN_EXR", "32"
    scene.render.resolution_x = scene.render.resolution_y = 16
    cam = scene.camera or bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    if scene.camera is None:
        scene.collection.objects.link(cam)
        scene.camera = cam
    cam.data.angle = math.radians(4)
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    path = os.path.join(tempfile.mkdtemp(), "sky.exr")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    image = bpy.data.images.load(path)
    px = image.pixels[:]
    bpy.data.images.remove(image)
    return sum(px[0::4]) / (len(px) / 4)


def test_the_sky_glows_where_the_sun_lamp_shines_from():
    # The check mirrors the lamp east to west: within about 6 degrees of due north or south the mirror image is too
    # near the sun to tell apart (measured: 5.4 times as bright at 200 degrees, 2.7 at 190, 1.6 at 186, 1.3 at 184).
    assert abs(math.sin(math.radians(look_build.SUN_AZIMUTH_DEG))) > 0.1, "the sun is too near due north or south"
    look_build.add_sky(bpy.context.scene)
    sun = bpy.data.objects[look_build.SKY_SUN]
    sun.hide_render = True
    bpy.context.view_layer.update()
    to_sun = (sun.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
    mirrored = Vector((-to_sun.x, to_sun.y, to_sun.z))   # where the glow would be with east and west swapped
    bright, other = _sky_brightness(to_sun), _sky_brightness(mirrored)
    assert bright > 1.5 * other, (bright, other)


def test_the_sky_glows_at_the_sun_lamps_height():
    # 20 degrees above and below the lamp's direction the sky is dimmer (measured: 3.4 against 0.7 and 1.8), so a
    # lamp set higher or lower than the sky's sun fails here
    look_build.add_sky(bpy.context.scene)
    sun = bpy.data.objects[look_build.SKY_SUN]
    sun.hide_render = True
    bpy.context.view_layer.update()
    to_sun = (sun.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
    level = Vector((to_sun.x, to_sun.y, 0)).normalized()
    elevation = math.asin(to_sun.z)
    above, below = (level * math.cos(elevation + d) + Vector((0, 0, math.sin(elevation + d)))
                    for d in (math.radians(20), math.radians(-20)))
    bright, above, below = _sky_brightness(to_sun), _sky_brightness(above), _sky_brightness(below)
    assert bright > 1.5 * above and bright > 1.5 * below, (bright, above, below)
