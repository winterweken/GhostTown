import itertools
import json
import math
import os
import tempfile

import bpy
import numpy as np

import ghosttown
from ghosttown import look_build, materials, realistic, scene_build, site_realistic, site_use
from ghosttown.ghosttown_fetch import CIRCLE_QUAD_SEGS, GROUND_KINDS
from helpers import drum_doc, fetch_tree_meshes, load_fixture, mesh_arrays, open_only_at_the_top


def drum_site(**kw):
    folder = tempfile.mkdtemp()
    return scene_build.build(bpy.context.scene, drum_doc(**kw), folder=folder)


def test_the_drum_is_closed_and_meets_the_ground_at_the_rim():
    root = drum_site()
    earth = site_realistic.make_earth(root)
    verts, faces = mesh_arrays(earth)
    assert open_only_at_the_top(verts, faces)                    # wall + base; the ground pieces cover the top
    r = root["radius_m"]
    for a in np.linspace(0, 2 * np.pi, 37)[:-1]:
        near = [z for x, y, z in verts
                if abs((math.atan2(y, x) - a + math.pi) % (2 * math.pi) - math.pi) < 0.004]
        top = max(near)
        assert abs(top - 0.02 * r * math.cos(a)) < 0.05          # the plane z = 0.02 x at the rim


def test_the_base_is_flat_fifteen_metres_below_the_lowest_rim_point():
    root = drum_site()
    verts, _ = mesh_arrays(site_realistic.make_earth(root))
    bottom = min(z for *_, z in verts)
    assert abs(bottom - (-0.02 * root["radius_m"] - 15.0)) < 0.05
    assert max(z for *_, z in verts if z < bottom + 1.0) - bottom < 1e-4          # the base ring is flat


def test_the_wall_and_the_cutter_stand_on_the_grounds_inscribed_circle():
    root = drum_site()
    inscribed = root["radius_m"] * math.cos(math.pi / (4 * CIRCLE_QUAD_SEGS))    # the ground's rim polygon
    for ob in (site_realistic.make_earth(root), site_realistic.make_cutter(root)):
        verts, _ = mesh_arrays(ob)
        assert np.allclose([math.hypot(x, y) for x, y, _ in verts], inscribed)


def test_one_earth_per_site_recorded_for_removal():
    root = drum_site()
    site_realistic.make_earth(root); earth = site_realistic.make_earth(root)
    assert [o for o in root.all_objects if o.get("ctx_kind") == "earth"] == [earth]
    name = earth.name
    assert name in json.loads(root["ctx_objects"]) and earth.material_slots[0].material.name.endswith("Earth")
    site_realistic.remove_earth(root)
    assert site_realistic.find(root, "earth") is None and name not in json.loads(root["ctx_objects"])
    assert not [m for m in bpy.data.meshes if m.name.startswith("Earth")]


def test_a_gap_in_the_ground_is_bridged_and_no_ground_is_flat():
    root = drum_site()
    bpy.data.objects.remove(next(o for o in root.all_objects if o.get("ctx_kind") == "green"))
    assert open_only_at_the_top(*mesh_arrays(site_realistic.make_earth(root)))
    for ob in [o for o in root.all_objects if o.get("ctx_kind") in GROUND_KINDS]:
        bpy.data.objects.remove(ob)
    verts, _ = mesh_arrays(site_realistic.make_earth(root))
    assert abs(max(z for *_, z in verts) - root["ground_at_centre_m"]) < 1e-4


def test_the_earth_carries_depth_below_the_rim_and_is_named_for_the_site():
    root = drum_site()
    earth = site_realistic.make_earth(root)
    assert earth.name == "Earth · " + root["ctx_label"] and earth["ctx_id"] == "earth"
    attribute = earth.data.attributes["gt_depth"]
    assert attribute.domain == "POINT" and attribute.data_type == "FLOAT"
    depth = np.array([d.value for d in attribute.data])
    z = np.array([v.co.z for v in earth.data.vertices])
    n = len(z) // 2
    assert np.allclose(depth[:n], 0.0) and np.allclose(depth[n:], z[:n] - z[n:])
    assert np.allclose(z[n:], z[n:].min())


def test_the_wall_faces_outward_and_the_base_faces_down():
    earth = site_realistic.make_earth(drum_site())
    assert min(p.normal.z for p in earth.data.polygons) < -0.99
    assert all(p.normal.to_2d().dot(p.center.to_2d()) > 0 for p in earth.data.polygons if abs(p.normal.z) < 0.5)


def test_the_ring_helper_gives_about_a_vertex_a_metre_and_at_least_sixty_four():
    root = drum_site()
    angles = site_realistic.ring_angles(root)
    assert len(angles) == max(64, math.ceil(2 * math.pi * root["radius_m"])) and angles[0] == 0.0
    assert len(site_realistic.make_earth(root).data.vertices) == 2 * len(angles)
    small = drum_site(radius=5.0)
    assert len(site_realistic.ring_angles(small)) == 64
    assert len(site_realistic.make_earth(small).data.vertices) == 128


def test_removing_the_site_removes_its_earth():
    root = drum_site()
    site_realistic.make_earth(root)
    scene_build.remove(root, bpy.context.scene)
    assert not [o for o in bpy.data.objects if o.get("ctx_kind") == "earth"]
    assert not [m for m in bpy.data.meshes if m.name.startswith("Earth")]


def test_only_what_crosses_the_edge_is_trimmed_to_the_circle():
    root = drum_site(); r = root["radius_m"]
    assert site_realistic.add_trim(root) == 2                     # osm:way:9 and the merged trees
    cutter = site_realistic.find(root, "earth_cutter")
    assert cutter.hide_viewport and cutter.hide_render
    dg = bpy.context.evaluated_depsgraph_get()
    for ob in root.all_objects:
        mods = [m for m in ob.modifiers if m.name == site_realistic.TRIM]
        crosses = ob.get("ctx_id") == "osm:way:9" or ob.get("ctx_kind") == "tree"
        assert len(mods) == (1 if crosses else 0)
        if mods:
            assert mods[0].object == cutter and mods[0].operation == "INTERSECT"
            me = ob.evaluated_get(dg).data
            assert len(me.vertices) > 0
            assert max(math.hypot(*(ob.matrix_world @ v.co).xy) for v in me.vertices) < r + 0.05


def two_solid_site():
    """drum_site plus osm:way:7: a podium and a taller tower inside it, both across the rim (overlapping shells)."""
    doc = drum_doc(); r = doc["radius_m"]
    ring = lambda x0, x1, y0, y1: [[r + x0, y0], [r + x1, y0], [r + x1, y1], [r + x0, y1]]
    doc["elements"].append({"id": "osm:way:7", "kind": "building", "name": "", "meshes": [], "lines": [], "solids": [
        {"kind": "building", "rings": [ring(-10, 30, 20, 30)], "z0": -0.3, "z1": 10.0, "height_source": "osm_levels"},
        {"kind": "building", "rings": [ring(-5, 20, 22, 28)], "z0": -0.3, "z1": 40.0, "height_source": "osm_levels"}]})
    return scene_build.build(bpy.context.scene, doc, folder=tempfile.mkdtemp())


def test_a_building_of_overlapping_solids_survives_the_trim():
    root = two_solid_site()
    site_realistic.add_trim(root)
    dg = bpy.context.evaluated_depsgraph_get()
    tower = next(o for o in root.all_objects if o.get("ctx_id") == "osm:way:7")
    box = next(o for o in root.all_objects if o.get("ctx_id") == "osm:way:9")
    me = tower.evaluated_get(dg).data
    assert len(me.polygons) > 0                                            # not emptied by the overlap
    assert len(me.polygons) > len(box.evaluated_get(dg).data.polygons)      # more than one trimmed box
    assert furthest(tower, me) < root["radius_m"] + 0.05


def triangles(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


def furthest(ob, me):
    return max(math.hypot(*(ob.matrix_world @ v.co).xy) for v in me.vertices)


def test_a_dense_grove_across_the_edge_keeps_its_trees():
    doc = drum_doc(); r = doc["radius_m"]
    grid = itertools.product(np.arange(r - 12, r + 6, 4.0), np.arange(-10, 10, 4.0))
    for i, (x, y) in enumerate(grid):                             # 10 m trees 4 m apart: the crowns overlap
        doc["elements"].append({"id": f"tree:grove:{i}", "kind": "tree", "name": "", "solids": [], "lines": [],
                                "meshes": fetch_tree_meshes(x, y, 0.02 * x, 10.0)})
    root = scene_build.build(bpy.context.scene, doc, folder=tempfile.mkdtemp())
    trees, = site_use.made_objects(root, ("tree",))
    before = triangles(trees.data)
    site_realistic.add_trim(root)
    me = trees.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    assert triangles(me) > before / 2
    assert furthest(trees, me) < r + 0.05


def look_across(r):
    """mini_look.json with detail on osm:way:9, the building across the rim, along its south wall."""
    answer = load_fixture("mini_look.json")
    entry = json.loads(json.dumps(answer["buildings"]["osm:way:2"]))
    entry["detail_walls"] = [{"a": [r - 10, -5], "b": [r + 30, -5], "n": [0, -1], "z0": 0.0, "z1": 20.3}]
    answer["buildings"]["osm:way:9"] = entry
    return answer


def detail_of(root, building_id):
    return next(o for o in site_use.made_objects(root, ("facade_detail",)) if o["ctx_id"] == "detail:" + building_id)


def assert_trimmed(root, ob):
    assert any(m.name == site_realistic.TRIM for m in ob.modifiers)
    me = ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    assert triangles(me) > 0 and furthest(ob, me) < root["radius_m"] + 0.05


def test_facade_detail_across_the_edge_is_trimmed():
    root = drum_site()
    look_build.apply(bpy.context.scene, root, look_across(root["radius_m"]))
    site_use.apply_ground(root, "realistic")
    assert_trimmed(root, detail_of(root, "osm:way:9"))
    assert not detail_of(root, "osm:way:1").modifiers                # the tower's detail is inside


def test_street_look_on_realistic_trims_its_new_detail():
    root = drum_site()
    site_use.apply_ground(root, "realistic")
    for _ in range(2):                                            # applying again replaces the detail
        look_build.apply(bpy.context.scene, root, look_across(root["radius_m"]))
        assert_trimmed(root, detail_of(root, "osm:way:9"))
    assert len(site_use.made_objects(root, ("earth_cutter",))) == 1


def test_switching_roof_shape_keeps_the_trim():
    root = drum_site(); site_realistic.add_trim(root)
    ob = next(o for o in root.all_objects if o.get("ctx_id") == "osm:way:9")
    ob.data = ob.data.copy()                                      # stands in for a roof-shape swap
    me = ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    assert max(math.hypot(*(ob.matrix_world @ v.co).xy) for v in me.vertices) < root["radius_m"] + 0.05


def test_a_building_whose_other_roof_mesh_crosses_is_trimmed():
    root = drum_site()
    ob = next(o for o in root.all_objects if o.get("ctx_id") == "osm:way:1")
    far = bpy.data.meshes.new("far"); far.from_pydata([(0, 0, 0), (400, 0, 0), (0, 1, 1)], [], [(0, 1, 2)])
    ob[site_use.LIDAR_KEY] = far
    site_realistic.add_trim(root)
    assert any(m.name == site_realistic.TRIM for m in ob.modifiers)


def test_removing_the_trim_leaves_nothing_and_the_revit_count_ignores_it():
    root = drum_site(); dg = bpy.context.evaluated_depsgraph_get()
    before = site_use.count_triangles(root, dg)
    site_realistic.make_earth(root); site_realistic.add_trim(root)
    assert site_use.count_triangles(root, bpy.context.evaluated_depsgraph_get()) == before
    site_realistic.remove_trim(root)
    assert site_realistic.find(root, "earth_cutter") is None
    assert not any(m.name == site_realistic.TRIM for o in root.all_objects for m in o.modifiers)


def test_a_later_roof_detail_goes_before_the_trim():
    root = drum_site(); site_realistic.add_trim(root)
    ob = next(o for o in root.all_objects if o.get("ctx_id") == "osm:way:9")
    ob[site_use.LIDAR_KEY] = ob.data                              # shows its LiDAR roof, so detail applies
    site_use.apply_roof_detail(root, 0.5)
    names = [m.name for m in ob.modifiers]
    assert names == [site_use.DETAIL_MODIFIER, site_realistic.TRIM]


def test_trimming_twice_leaves_one_trim_per_object_and_one_cutter():
    root = drum_site()
    assert site_realistic.add_trim(root) == 2 and site_realistic.add_trim(root) == 2
    assert len([o for o in root.all_objects if o.get("ctx_kind") == "earth_cutter"]) == 1
    for ob in root.all_objects:
        assert len([m for m in ob.modifiers if m.name == site_realistic.TRIM]) <= 1
    assert sum(1 for o in root.all_objects for m in o.modifiers if m.name == site_realistic.TRIM) == 2


def test_adding_the_trim_again_repairs_stale_settings():
    root = drum_site(); site_realistic.add_trim(root)
    building = next(o for o in root.all_objects if o.get("ctx_id") == "osm:way:9").modifiers[site_realistic.TRIM]
    trees = next(o for o in site_use.made_objects(root, ("tree",))).modifiers[site_realistic.TRIM]
    building.solver, building.use_self, building.use_hole_tolerant = "MANIFOLD", False, False
    trees.solver = "EXACT"
    site_realistic.add_trim(root)
    assert (building.solver, building.use_self, building.use_hole_tolerant) == ("EXACT", True, True)
    assert trees.solver == "MANIFOLD"


def slots(root):
    return {o["ctx_kind"]: (o.material_slots[0].link, o.material_slots[0].material.name, o.data.materials[0].name)
            for o in site_use.made_objects(root, GROUND_KINDS)}


def test_realistic_puts_each_surface_on_the_object_and_keeps_the_context_material():
    root = drum_site()
    site_use.apply_ground(root, "realistic")
    for kind, (link, shown, data) in slots(root).items():
        assert link == "OBJECT" and shown == "Ghost Town Realistic · " + realistic.SURFACES[kind]
        assert data == materials.material_name(kind)
    assert root["use_ground"] == "realistic" and site_realistic.find(root, "earth") is not None


def test_every_switching_order_ends_clean():
    folder = tempfile.mkdtemp()
    root = scene_build.build(bpy.context.scene, drum_doc(photo_folder=folder), folder=folder)
    for path in itertools.permutations(("colours", "photo", "realistic")):
        for use in path + path[:1]:
            site_use.apply_ground(root, use)
        last = path[0]
        assert sum(o.get("ctx_kind") == "earth" for o in root.all_objects) == (last == "realistic")
        assert any(m.name == site_realistic.TRIM for o in root.all_objects for m in o.modifiers) == (last == "realistic")
        links = {link for link, *_ in slots(root).values()}
        assert links == ({"DATA"} if last == "colours" else {"OBJECT"})


def test_hand_deleted_pieces_never_break_a_switch():
    root = drum_site()
    site_use.apply_ground(root, "realistic")
    bpy.data.objects.remove(site_realistic.find(root, "earth"))
    bpy.data.objects.remove(site_realistic.find(root, "earth_cutter"))
    site_use.apply_ground(root, "colours")
    site_use.apply_ground(root, "realistic")
    assert site_realistic.find(root, "earth") and site_realistic.find(root, "earth_cutter")


def test_two_sites_keep_their_own_choice_and_share_materials():
    a, b = drum_site(address="1 First St"), drum_site(address="2 Second St")
    site_use.apply_ground(a, "realistic")
    assert {link for link, *_ in slots(b).values()} == {"DATA"} and site_realistic.find(b, "earth") is None
    site_use.apply_ground(b, "realistic")
    assert sum(m.name == "Ghost Town Realistic · Grass" for m in bpy.data.materials) == 1


def test_removing_a_realistic_site_leaves_nothing_behind():
    root = drum_site()
    site_use.apply_ground(root, "realistic")
    scene_build.remove(root, bpy.context.scene)
    assert not any(o.get("ctx_kind") in ("earth", "earth_cutter") for o in bpy.data.objects)
    assert not any(m.name == site_realistic.TRIM for o in bpy.data.objects for m in o.modifiers)


def test_realistic_survives_save_and_reload():
    root = drum_site()
    site_use.apply_ground(root, "realistic")
    path = os.path.join(tempfile.mkdtemp(), "r.blend")
    name = root.name
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    root = bpy.data.collections[name]
    assert root["use_ground"] == "realistic" and site_realistic.find(root, "earth") is not None


def test_the_operator_refuses_photo_without_a_photo_and_allows_realistic():
    ghosttown.register()
    try:
        root = drum_site()
        bpy.context.scene.ghosttown.site = root
        assert bpy.ops.ghosttown.use_ground(use="photo") == {"CANCELLED"}
        assert bpy.ops.ghosttown.use_ground(use="realistic") == {"FINISHED"}
        assert root["use_ground"] == "realistic"
    finally:
        ghosttown.unregister()
