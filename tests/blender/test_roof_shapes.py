import json
import os
import tempfile

import bpy

import ghosttown
from ghosttown import scene_build, site_use
from helpers import lidar_doc, load_fixture
from test_site_lidar import buildings, lidar_site

FLAT, LIDAR = site_use.FLAT_KEY, site_use.LIDAR_KEY


def _names(me):
    return [m.name for m in me.materials]


def test_the_switch_swaps_every_building_both_ways():
    root, _ = lidar_site()
    site_use.apply_roof_shapes(root, "flat")
    assert all(ob.data == ob[FLAT] for ob in buildings(root)) and root["use_roof_shapes"] == "flat"
    site_use.apply_roof_shapes(root, "lidar")
    assert all(ob.data == ob[LIDAR] for ob in buildings(root)) and root["use_roof_shapes"] == "lidar"


def test_the_roof_photo_moves_to_the_mesh_shown_and_leaves_the_other_plain():
    root, _ = lidar_site(photo=True)
    photo = root["ctx_photo_material"]
    site_use.apply_roofs(root, "photo", 100.0)
    tower = buildings(root)[0]
    assert _names(tower[LIDAR])[-1] == photo
    site_use.apply_roof_shapes(root, "flat")
    assert _names(tower[FLAT])[-1] == photo
    assert photo not in _names(tower[LIDAR]) and site_use.INDEX_ATTR not in tower[LIDAR].attributes
    site_use.apply_roofs(root, "plain")
    assert photo not in _names(tower[FLAT])


def test_roof_detail_simplifies_only_the_roof_interior():
    root, _ = lidar_site(dense=True)
    shed = buildings(root)[1]
    site_use.apply_roof_detail(root, 0.5)
    mod = shed.modifiers[site_use.DETAIL_MODIFIER]
    assert (mod.decimate_type, mod.vertex_group, round(mod.ratio, 6)) == ("COLLAPSE", site_use.ROOF_GROUP, 0.5)
    assert root["roof_detail"] == 0.5
    group = shed.vertex_groups[site_use.ROOF_GROUP].index
    edge = {tuple(round(c, 4) for c in v.co) for v in shed.data.vertices if all(g.group != group for g in v.groups)}
    evaluated = shed.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    kept = {tuple(round(c, 4) for c in v.co) for v in evaluated.vertices}
    assert edge <= kept and len(evaluated.polygons) < len(shed.data.polygons)
    site_use.apply_roof_detail(root, 1.0)
    assert site_use.DETAIL_MODIFIER not in shed.modifiers


def test_flat_roofs_carry_no_detail_modifier_and_lidar_gets_it_back():
    root, _ = lidar_site(dense=True)
    site_use.apply_roof_detail(root, 0.4)
    site_use.apply_roof_shapes(root, "flat")
    assert all(site_use.DETAIL_MODIFIER not in ob.modifiers for ob in buildings(root))
    site_use.apply_roof_shapes(root, "lidar")
    assert abs(buildings(root)[1].modifiers[site_use.DETAIL_MODIFIER].ratio - 0.4) < 1e-6


def test_the_triangle_count_is_what_the_site_exports():
    root, _ = lidar_site(dense=True)
    graph = bpy.context.evaluated_depsgraph_get()
    full = site_use.count_triangles(root, graph)
    by_hand = sum(len(p.vertices) - 2 for ob in root.all_objects if ob.type == "MESH"
                  for p in ob.evaluated_get(graph).data.polygons)
    assert full == by_hand == root["ctx_triangles"]
    site_use.apply_roof_detail(root, 0.3)
    fewer = site_use.count_triangles(root, bpy.context.evaluated_depsgraph_get())
    site_use.apply_roof_shapes(root, "flat")
    flat = site_use.count_triangles(root, bpy.context.evaluated_depsgraph_get())
    assert flat < fewer < full


def test_switching_skips_a_building_in_edit_mode():
    root, _ = lidar_site()
    tower, shed = buildings(root)
    bpy.context.view_layer.objects.active = tower
    tower.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        site_use.apply_roof_shapes(root, "flat")
        assert tower.data == tower[LIDAR] and shed.data == shed[FLAT]
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


def test_the_switch_acts_on_the_picked_site_and_counts():
    ghosttown.register()
    try:
        root, _ = lidar_site()
        bpy.context.scene.ghosttown.site = root
        assert bpy.ops.ghosttown.use_roof_shapes(use="flat") == {"FINISHED"}
        assert root["use_roof_shapes"] == "flat" and root["ctx_triangles"] > 0
    finally:
        ghosttown.unregister()


def test_the_switch_waits_for_a_site_with_lidar():
    ghosttown.register()
    try:
        root = scene_build.build(bpy.context.scene, load_fixture("mini_context.json"))
        bpy.context.scene.ghosttown.site = root
        assert not bpy.ops.ghosttown.use_roof_shapes.poll()
    finally:
        ghosttown.unregister()


def _import(doc, folder):
    path = os.path.join(folder, "context.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    assert bpy.ops.ghosttown.import_context(filepath=path) == {"FINISHED"}
    return bpy.context.scene.ghosttown


def test_importing_lidar_roofs_counts_the_triangles_and_says_so():
    ghosttown.register()
    try:
        folder = tempfile.mkdtemp()
        settings = _import(lidar_doc(folder), folder)
        assert settings.summary.endswith(", LiDAR roofs") and settings.site["ctx_triangles"] > 0
    finally:
        ghosttown.unregister()


def test_a_missing_roofs_file_builds_flat_roofs():
    ghosttown.register()
    try:
        folder = tempfile.mkdtemp()
        doc = lidar_doc(folder)
        os.remove(os.path.join(folder, "lidar_roofs.npz"))
        settings = _import(doc, folder)
        assert "LiDAR" not in settings.summary and not site_use.has_lidar(settings.site)
    finally:
        ghosttown.unregister()


FITTED = site_use.FITTED_KEY

def test_the_switch_goes_every_way_between_all_three():
    from test_site_lidar import fitted_site
    root, _ = fitted_site()
    for use, key in (("flat", FLAT), ("lidar", LIDAR), ("fitted", FITTED), ("flat", FLAT), ("fitted", FITTED),
                     ("lidar", LIDAR)):
        site_use.apply_roof_shapes(root, use)
        assert all(ob.data == ob[key] for ob in buildings(root)) and root["use_roof_shapes"] == use

def test_the_roof_photo_follows_onto_the_fitted_roofs():
    from test_site_lidar import fitted_site
    root, _ = fitted_site(photo=True)
    photo = root["ctx_photo_material"]
    site_use.apply_roofs(root, "photo", 100.0)
    tower = buildings(root)[0]
    assert _names(tower[FITTED])[-1] == photo
    site_use.apply_roof_shapes(root, "lidar")
    assert _names(tower[LIDAR])[-1] == photo and photo not in _names(tower[FITTED])

def test_roof_detail_touches_only_lidar_roofs():
    from test_site_lidar import fitted_site
    root, _ = fitted_site(dense=True)
    site_use.apply_roof_detail(root, 0.4)
    assert all(site_use.DETAIL_MODIFIER not in ob.modifiers for ob in buildings(root))  # fitted shows
    site_use.apply_roof_shapes(root, "lidar")
    assert abs(buildings(root)[1].modifiers[site_use.DETAIL_MODIFIER].ratio - 0.4) < 1e-6
    site_use.apply_roof_shapes(root, "fitted")
    assert all(site_use.DETAIL_MODIFIER not in ob.modifiers for ob in buildings(root))

def test_the_triangle_count_follows_the_choice():
    from test_site_lidar import fitted_site
    root, _ = fitted_site(dense=True)
    counts = {}
    for use in ("lidar", "fitted", "flat"):
        site_use.apply_roof_shapes(root, use)
        counts[use] = site_use.count_triangles(root, bpy.context.evaluated_depsgraph_get())
    others = sum(len(p.vertices) - 2 for ob in root.all_objects if ob.type == "MESH" and ob not in buildings(root)
                 for p in ob.data.polygons)
    for use, key in (("flat", FLAT), ("fitted", FITTED), ("lidar", LIDAR)):
        assert counts[use] == others + sum(len(p.vertices) - 2 for ob in buildings(root) for p in ob[key].polygons)
    assert counts["fitted"] < counts["lidar"]

def test_the_operator_refuses_fitted_on_a_site_without_them():
    ghosttown.register()
    try:
        root, _ = lidar_site()
        bpy.context.scene.ghosttown.site = root
        assert bpy.ops.ghosttown.use_roof_shapes(use="fitted") == {"CANCELLED"}
        assert root["use_roof_shapes"] == "lidar"
    finally:
        ghosttown.unregister()

def test_importing_fitted_roofs_says_so_and_shows_them():
    from helpers import fitted_doc
    ghosttown.register()
    try:
        folder = tempfile.mkdtemp()
        settings = _import(fitted_doc(folder), folder)
        assert settings.summary.endswith(", fitted and LiDAR roofs") and settings.site["use_roof_shapes"] == "fitted"
    finally:
        ghosttown.unregister()

def test_a_missing_fitted_file_leaves_the_lidar_roofs():
    from helpers import fitted_doc
    ghosttown.register()
    try:
        folder = tempfile.mkdtemp()
        doc = fitted_doc(folder)
        os.remove(os.path.join(folder, "fitted_roofs.npz"))
        settings = _import(doc, folder)
        assert settings.summary.endswith(", LiDAR roofs") and settings.site["use_roof_shapes"] == "lidar"
    finally:
        ghosttown.unregister()


def test_the_operator_refuses_lidar_on_a_site_with_only_fitted_roofs():
    from helpers import fitted_doc
    ghosttown.register()
    try:
        folder = tempfile.mkdtemp()
        doc = fitted_doc(folder)
        os.remove(os.path.join(folder, "lidar_roofs.npz"))
        root = scene_build.build(bpy.context.scene, doc, folder=folder)
        bpy.context.scene.ghosttown.site = root
        assert bpy.ops.ghosttown.use_roof_shapes(use="lidar") == {"CANCELLED"} and root["use_roof_shapes"] == "fitted"
        assert bpy.ops.ghosttown.use_roof_shapes(use="flat") == {"FINISHED"}
        assert bpy.ops.ghosttown.use_roof_shapes(use="fitted") == {"FINISHED"} and root["use_roof_shapes"] == "fitted"
    finally:
        ghosttown.unregister()


def test_importing_says_which_roofs_files_are_missing():
    from ghosttown import ops
    from helpers import fitted_doc
    ghosttown.register()
    try:
        for missing, ending, warned in (
                ((), ", fitted and LiDAR roofs", []),
                (("fitted_roofs.npz",), ", LiDAR roofs", ["no fitted roofs."]),
                (("lidar_roofs.npz",), ", fitted roofs", ["no LiDAR roofs."]),
                (("lidar_roofs.npz", "fitted_roofs.npz"), None, ["flat roofs.", "no fitted roofs."])):
            folder = tempfile.mkdtemp()
            doc = fitted_doc(folder)
            for name in missing:
                os.remove(os.path.join(folder, name))
            path = os.path.join(folder, "context.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(doc, f)
            reports = []
            ops.import_into_scene(bpy.context, path, lambda level, text: reports.append(text))
            summary = bpy.context.scene.ghosttown.summary
            assert summary.endswith(ending) if ending else "roofs" not in summary, (missing, summary)
            said = [t.split("so the buildings have ")[1] for t in reports if "file is missing or unreadable" in t]
            assert said == warned, (missing, reports)
    finally:
        ghosttown.unregister()
