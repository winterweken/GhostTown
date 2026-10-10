"""Development application boxes in Blender (design/development-applications.md §5): made, refreshed, kept,
greyed, removed, remembered when deleted and carried across a rebuild."""
import json
import math

import bpy

from ghosttown import scene_build, site_apps, site_use
from ghosttown.ghosttown_fetch import BUILDING_KINDS
from ghosttown.ghosttown_fetch.frame import Frame
from helpers import closed_and_outward, load_fixture, mesh_arrays

SITE = "320 Bay St"
LINK = "http://app.toronto.ca/AIC/index.do?folderRsn=abc"


def _site(number, *more, group="review", centre=(40.0, 10.0), w=30.0, d=20.0, h=45.0, angle=0.0,
          address="25 KING ST W", source="application"):
    numbers = sorted((number,) + more)
    return {"id": "app:" + numbers[0], "group": group, "numbers": numbers, "main": number,
            "centre_m": list(centre), "angle_deg": angle, "width_m": w, "depth_m": d, "height_m": h, "base_m": -0.3,
            "height_from": "description: 14 storeys",
            "applications": [{"number": n, "type": "OZ", "status": "Under Review", "submitted": "2024-01-01",
                              "address": address, "description": "a 14-storey building with retail at grade",
                              "source": source, "floor_area_m2": 0.0, "url": LINK} for n in numbers]}


def _doc(sites, centre=None, radius=None, date="2026-10-09"):
    doc = load_fixture("mini_context.json")
    if sites is not None:
        doc["applications"] = sites
        doc["applications_date"] = date
    if centre is not None:
        doc["centre"] = centre
    if radius is not None:
        doc["radius_m"] = radius
    return doc


def _build(sites, lines=None, centre=None, radius=None, levels=None, date="2026-10-09"):
    """Build the mini site; `lines` collects the text reported, `levels` (level, text) pairs."""
    def report(level, text):
        if lines is not None:
            lines.append(text)
        if levels is not None:
            levels.append((next(iter(level)), text))
    return scene_build.build(bpy.context.scene, _doc(sites, centre, radius, date),
                             report=report if lines is not None or levels is not None else None)


def _remembered():
    """The centres the Applications collection remembers for the boxes in the scene."""
    coll = site_apps.find(bpy.context.scene, SITE)
    return [e["centre_m"] for e in json.loads(coll["ctx_app_boxes"])]


def _boxes():
    return site_apps.boxes(bpy.context.scene, SITE)


def _height(ob):
    zs = [v.co.z for v in ob.data.vertices]
    return max(zs) - min(zs)


def _close(a, b, tol=1e-4):
    return all(math.isclose(x, y, abs_tol=tol) for x, y in zip(a, b))


def test_a_build_with_applications_makes_one_see_through_box_per_site():
    root = _build([_site("A", angle=30.0)])
    coll = root.children[f"Applications · {SITE}"]
    (box,) = coll.objects
    assert box.name == "Under review · 25 King St W" and box["ctx_app_group"] == "review"
    assert len(box.data.vertices) == 8 and closed_and_outward(*mesh_arrays(box))
    assert _close(box.location, (40.0, 10.0, -0.3)) and math.isclose(box.rotation_euler.z, math.radians(30.0),
                                                                     abs_tol=1e-6)
    assert math.isclose(_height(box), 45.0, abs_tol=1e-4)
    mat = box.data.materials[0]
    assert mat.name == "Context - Application (Under review)" and math.isclose(mat.diffuse_color[3], 0.7,
                                                                               abs_tol=1e-6)
    assert json.loads(box["ctx_app_numbers"]) == ["A"] and box["ctx_app_height_from"] == "description: 14 storeys"
    assert site_apps.applications_of(box)[0]["url"] == LINK
    assert box not in site_use.made_objects(root, BUILDING_KINDS)    # Street Look and the roof switches pass it by


def test_a_build_without_applications_makes_no_collection():
    root = _build(None)
    assert not any(c.get(site_apps.SITE_PROP) for c in root.children_recursive)


def test_a_rebuild_refreshes_the_status_and_resizes_an_untouched_box():
    _build([_site("A")])
    (box,) = _boxes()
    lines = []
    _build([_site("A", group="approved", h=60.0)], lines)
    assert _boxes() == [box] and box.name == "Approved · 25 King St W"
    assert site_apps.find(bpy.context.scene, SITE).name not in bpy.context.scene.collection.children   # only in the site
    assert math.isclose(_height(box), 60.0, abs_tol=1e-4)
    assert box.data.materials[0].name == "Context - Application (Approved)"
    assert lines[0] == "Development applications (City of Toronto, 2026-10-09): 1 site from 1 application: 1 approved."


def test_a_box_the_user_scaled_keeps_its_shape_and_takes_the_new_status():
    _build([_site("A")])
    (box,) = _boxes()
    box.scale.x = 2.0
    lines = []
    _build([_site("A", group="approved", h=60.0)], lines)
    assert box.scale.x == 2.0 and math.isclose(_height(box), 45.0, abs_tol=1e-4)
    assert box.data.materials[0].name == "Context - Application (Approved)"
    assert "1 box kept at the size you gave it." in lines[0]


def test_a_closed_box_is_removed_untouched_and_turns_grey_when_changed():
    _build([_site("A"), _site("B", centre=(-40.0, 10.0), address="1 BAY ST")])
    edited = next(ob for ob in _boxes() if ob["ctx_app_main"] == "B")
    edited.location.x += 5.0
    _build([])
    assert _boxes() == [edited] and edited.name == "Closed · 1 Bay St" and edited["ctx_app_group"] == "closed"
    assert edited.data.materials[0].name == "Context - Application (Closed)"


def test_a_deleted_box_stays_deleted_until_brought_back():
    _build([_site("A")])
    (box,) = _boxes()
    bpy.data.objects.remove(box)
    _build([_site("A")])
    assert _boxes() == []
    coll = site_apps.find(bpy.context.scene, SITE)
    assert site_apps.deleted_count(bpy.context.scene, coll) == 1
    assert site_apps.bring_back(bpy.context.scene, coll) == 1
    assert site_apps.deleted_count(bpy.context.scene, coll) == 0
    _build([_site("A")])
    assert len(_boxes()) == 1


def test_a_build_that_did_not_look_leaves_every_box_and_carries_it():
    _build([_site("A")])
    (box,) = _boxes()
    box.location.y += 3.0
    root = _build(None)
    assert _boxes() == [box] and list(root.children[f"Applications · {SITE}"].objects) == [box]
    assert math.isclose(box.location.y, 13.0, abs_tol=1e-4)


def test_a_box_renamed_and_moved_into_the_users_collection_is_updated_there():
    _build([_site("A")])
    (box,) = _boxes()
    mine = bpy.data.collections.new("My boxes")
    bpy.context.scene.collection.children.link(mine)
    mine.objects.link(box)
    for coll in list(box.users_collection):
        if coll != mine:
            coll.objects.unlink(box)
    box.name = "my tower"
    _build([_site("A", group="appealed")])
    assert _boxes() == [box] and [c.name for c in box.users_collection] == ["My boxes"]
    assert box.name == "my tower" and box["ctx_app_group"] == "appealed"


def test_a_duplicated_box_is_left_as_it_is_and_named():
    _build([_site("A")])
    (box,) = _boxes()
    copy = box.copy()
    copy.data = box.data.copy()
    box.users_collection[0].objects.link(copy)
    lines = []
    _build([_site("A", group="approved")], lines)
    assert sorted(ob["ctx_app_group"] for ob in _boxes()) == ["approved", "review"]
    assert box["ctx_app_group"] == "approved"
    assert any(copy.name in line and "left as it is" in line for line in lines)


def test_a_restyled_status_material_keeps_its_colour():
    _build([_site("A")])
    mat = bpy.data.materials["Context - Application (Under review)"]
    mat.diffuse_color = (1.0, 0.0, 0.0, 0.5)
    _build([_site("A")])
    assert _close(mat.diffuse_color, (1.0, 0.0, 0.0, 0.5))


def test_a_site_built_again_around_another_centre_carries_its_boxes():
    _build([_site("A")])
    (box,) = _boxes()
    doc = load_fixture("mini_context.json")
    lon, lat = Frame(doc["centre"]["lat"], doc["centre"]["lon"]).to_lonlat(10.0, 0.0)
    _build(None, centre={"lat": lat, "lon": lon})
    assert _close(box.location[:2], (30.0, 10.0), tol=1e-3)
    _build([_site("A", group="approved", centre=(30.0, 10.0), h=60.0)], centre={"lat": lat, "lon": lon})
    assert box["ctx_app_group"] == "approved" and math.isclose(_height(box), 60.0, abs_tol=1e-4)   # still untouched


def test_a_fresh_box_is_remembered_where_it_stands():
    _build([_site("A")])
    (centre,) = _remembered()
    assert _close(centre, (40.0, 10.0), tol=1e-3)


def test_a_deleted_box_keeps_a_permit_site_on_its_spot_away():
    _build([_site("A")])
    (box,) = _boxes()
    bpy.data.objects.remove(box)
    _build([_site("21 1 BLD", group="built", centre=(41.0, 10.0), source="permit")])
    assert _boxes() == []


def test_a_carried_box_is_remembered_in_the_new_frame():
    _build([_site("A")])
    doc = load_fixture("mini_context.json")
    lon, lat = Frame(doc["centre"]["lat"], doc["centre"]["lon"]).to_lonlat(10.0, 0.0)
    _build(None, centre={"lat": lat, "lon": lon})
    (centre,) = _remembered()
    assert _close(centre, (30.0, 10.0), tol=1e-3)


def _ten_metres_east():
    doc = load_fixture("mini_context.json")
    lon, lat = Frame(doc["centre"]["lat"], doc["centre"]["lon"]).to_lonlat(10.0, 0.0)
    return {"lat": lat, "lon": lon}


def _hang(child, parent):
    """Parent `child` to `parent` where it stands, with no parent inverse, so its own transform is in the
    parent's turned and scaled space."""
    bpy.context.view_layer.update()
    world = child.matrix_world.copy()
    child.parent = parent
    child.matrix_parent_inverse.identity()
    child.matrix_world = world


def _world_xy(ob):
    bpy.context.view_layer.update()
    return ob.matrix_world.translation[:2]


def test_a_box_hung_from_a_turned_and_scaled_empty_is_carried_in_world_space():
    _build([_site("A")])
    (box,) = _boxes()
    empty = bpy.data.objects.new("Rig", None)
    bpy.context.scene.collection.objects.link(empty)
    empty.location = (5.0, -3.0, 0.0)
    empty.rotation_euler = (0.0, 0.0, math.radians(90.0))
    empty.scale = (2.0, 2.0, 2.0)
    _hang(box, empty)
    _build(None, centre=_ten_metres_east())
    assert _close(_world_xy(box), (30.0, 10.0), tol=1e-3)
    assert _close(_world_xy(empty), (5.0, -3.0), tol=1e-6)      # the user's empty is theirs: left where it was
    (centre,) = _remembered()
    assert _close(centre, (30.0, 10.0), tol=1e-3)


def test_a_box_hung_from_another_box_moves_with_it_once():
    _build([_site("A"), _site("B", centre=(-40.0, 10.0))])
    a, b = sorted(_boxes(), key=lambda ob: ob["ctx_app_main"])
    _hang(b, a)
    _build(None, centre=_ten_metres_east())
    assert _close(_world_xy(a), (30.0, 10.0), tol=1e-3)
    assert _close(_world_xy(b), (-50.0, 10.0), tol=1e-3)
    assert _close(sorted(_remembered())[0], (-50.0, 10.0), tol=1e-3)
    assert _close(sorted(_remembered())[1], (30.0, 10.0), tol=1e-3)


def test_an_untouched_box_outside_a_smaller_circle_is_left_alone():
    _build([_site("A", centre=(140.0, 0.0), w=10.0, d=10.0)])
    (box,) = _boxes()
    _build([], radius=100.0)
    assert _boxes() == [box]


def test_a_box_with_a_damaged_record_counts_as_changed():
    _build([_site("A")])
    (box,) = _boxes()
    box["ctx_app_placed"] = json.dumps({"location": list(box.location)})   # the right place, but no rotation, scale or mesh
    _build([_site("A", group="approved", h=60.0)])
    assert _boxes() == [box] and math.isclose(_height(box), 45.0, abs_tol=1e-4)
    assert box.data.materials[0].name == "Context - Application (Approved)"


def test_find_needs_a_real_label():
    _build([_site("A")])
    scene = bpy.context.scene
    scene.collection.children.link(bpy.data.collections.new("Some other collection"))   # without the Applications mark
    for label in (None, "", 5, ["Context"]):
        assert site_apps.find(scene, label) is None and site_apps.boxes(scene, label) == []
    assert site_apps.find(scene, SITE) is not None and site_apps.find(scene, "No such site") is None


def _principled(mat, depsgraph=None):
    mat = mat if depsgraph is None else mat.evaluated_get(depsgraph)
    return next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")


def test_the_swatch_colour_drives_the_rendered_base_colour_without_scripts():
    _build([_site("A")])
    (box,) = _boxes()
    mat = box.data.materials[0]
    base_colour = f'nodes["{_principled(mat).name}"].inputs[0].default_value'   # Base Color is the first input
    drivers = [f for f in mat.node_tree.animation_data.drivers if f.data_path == base_colour]
    assert sorted(f.array_index for f in drivers) == [0, 1, 2]
    for f in drivers:
        (variable,) = f.driver.variables
        target = variable.targets[0]
        assert f.driver.type == "AVERAGE" and variable.type == "SINGLE_PROP"   # plain drivers: no script, no auto-run
        assert target.id_type == "MATERIAL" and target.id == mat
        assert target.data_path == f"diffuse_color[{f.array_index}]"
    mat.diffuse_color = (1.0, 0.0, 0.0, 0.7)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    assert _close(_principled(mat, depsgraph).inputs["Base Color"].default_value[:3], (1.0, 0.0, 0.0))


def test_a_status_material_that_exists_is_left_as_it_is():
    _build([_site("A")])
    (box,) = _boxes()
    mat = box.data.materials[0]
    mat.diffuse_color = (0.2, 0.3, 0.4, 0.7)
    before = len(mat.node_tree.animation_data.drivers)
    _build([_site("A")])
    assert box.data.materials[0] is mat and len(mat.node_tree.animation_data.drivers) == before
    assert _close(mat.diffuse_color[:3], (0.2, 0.3, 0.4))



def test_a_build_that_fails_after_detach_keeps_the_boxes_in_the_scene():
    _build([_site("A")])
    (box,) = _boxes()
    coll = site_apps.find(bpy.context.scene, SITE)
    real = scene_build._building_object

    def broken(el):
        raise RuntimeError("the build stopped halfway")
    scene_build._building_object = broken
    try:
        try:
            _build([_site("A")])
        except RuntimeError:
            pass
        else:
            raise AssertionError("the patched build should have failed")
    finally:
        scene_build._building_object = real
    scene = bpy.context.scene
    assert box.name in scene.objects and coll.users > 0
    assert coll in scene.collection.children_recursive and _boxes() == [box]


def test_a_box_record_too_damaged_to_read_still_finishes_the_build():
    _build([_site("A")])
    (box,) = _boxes()
    damaged = json.loads(box["ctx_app_placed"])
    damaged["scale"] = ["a", "b", "c"]
    box["ctx_app_placed"] = json.dumps(damaged)
    levels = []
    root = _build([_site("A", group="approved", h=60.0)], levels=levels)
    assert root is not None and _boxes() == [box]
    assert box["ctx_app_group"] == "approved" or any(level == "WARNING" for level, _ in levels)


def test_apply_reports_a_failure_as_a_warning():
    _build([_site("A")])
    (box,) = _boxes()
    real = site_apps.app_boxes.plan

    def broken(*args, **kwargs):
        raise ValueError("no plan today")
    site_apps.app_boxes.plan = broken
    levels = []
    try:
        root = _build([_site("A", group="approved")], levels=levels)
    finally:
        site_apps.app_boxes.plan = real
    assert root is not None and _boxes() == [box] and box["ctx_app_group"] == "review"
    assert any(level == "WARNING" and "couldn't be updated" in text and "ValueError" in text
               for level, text in levels)
    assert site_apps.find(bpy.context.scene, SITE) in root.children_recursive     # linked into the new site


def test_a_box_is_named_for_its_address_in_street_capitals():
    _build([_site("A", address="33RD ST; 2 MCCAUL ST")])
    (box,) = _boxes()
    assert box.name == "Under review · 33rd St" and box["ctx_app_place"] == "33rd St"
    for address, name in (("2 MCCAUL ST", "2 McCaul St"), ("1 QUEEN'S PARK W", "1 Queen's Park W"),
                          ("10 ST. CLAIR AVE E", "10 St. Clair Ave E"), ("25-27 MC ST", "25-27 Mc St"),
                          ("MCKENZIE AVE", "McKenzie Ave")):
        assert site_apps._place_name(_site("B", address=address)) == name


def test_a_context_older_than_the_boxes_leaves_them_as_they_are():
    _build([_site("A")])
    (box,) = _boxes()
    levels = []
    _build([_site("A", group="approved")], levels=levels, date="2026-10-01")
    assert _boxes() == [box] and box["ctx_app_group"] == "review"
    assert ("INFO", "This context's development applications (2026-10-01) are older than the boxes' (2026-10-09), "
                    "so the boxes were left as they are.") in levels
    assert site_apps.find(bpy.context.scene, SITE)["ctx_app_date"] == "2026-10-09"
    levels = []
    _build([_site("A", group="approved")], levels=levels, date="2026-10-09")        # the same day is not older
    assert box["ctx_app_group"] == "approved" and not any("older" in text for _, text in levels)


def test_a_build_without_applications_says_so_when_it_leaves_boxes():
    _build([_site("A")])
    (box,) = _boxes()
    levels = []
    _build(None, levels=levels)
    assert _boxes() == [box]
    assert levels == [("INFO", "Development applications weren't fetched this time (the tick was off), so the "
                               "boxes were left as they are.")]
    levels = []
    doc = _doc(None)
    doc["notes"].append({"level": "warn", "code": "applications", "text": "The applications failed."})
    scene_build.build(bpy.context.scene, doc, report=lambda level, text: levels.append((next(iter(level)), text)))
    assert levels == []                                  # the context's own note says why


def test_a_site_that_never_had_boxes_has_nothing_to_say_about_them():
    levels = []
    _build(None, levels=levels)
    _build(None, levels=levels)
    assert levels == []
