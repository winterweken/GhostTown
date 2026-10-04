import bpy

from ghosttown import scene_build
from helpers import closed_and_outward, load_fixture, mesh_arrays

SITE = "320 Bay St"


def _build(doc=None):
    return scene_build.build(bpy.context.scene, doc or load_fixture("mini_context.json"))


def _ctx_objects():
    return [ob for ob in bpy.data.objects if "ctx_id" in ob]


def test_collections_and_buildings():
    root = _build()
    assert root.name == f"Context · {SITE}"
    assert [c.name for c in root.children] == [f"{g} · {SITE}" for g in ("Buildings", "Ground", "Trees", "Parcels")]
    buildings = root.children[f"Buildings · {SITE}"].objects
    assert sorted(ob["ctx_id"] for ob in buildings) == ["osm:way:1", "osm:way:2"]
    tower = next(ob for ob in buildings if ob["ctx_id"] == "osm:way:1")
    assert tower.name == "Tower" and tower["ctx_source"] == "osm"
    assert tower["ctx_height_source"] == "osm_height, osm_levels"


def test_every_building_is_closed_and_outward():
    root = _build()
    for ob in root.children[f"Buildings · {SITE}"].objects:
        assert closed_and_outward(*mesh_arrays(ob)), ob.name


def test_merged_ground_trees_and_parcels():
    root = _build()
    road, = root.children[f"Ground · {SITE}"].objects
    trees, = root.children[f"Trees · {SITE}"].objects
    parcels, = root.children[f"Parcels · {SITE}"].objects
    assert (road.name, road["ctx_id"], len(road.data.polygons)) == (f"Road · {SITE}", "merged:road", 2)
    assert len(trees.data.polygons) == 8 and closed_and_outward(*mesh_arrays(trees))
    assert len(parcels.data.edges) == 4 and len(parcels.data.polygons) == 0


def test_materials_by_kind_without_duplicates_on_rerun():
    _build()
    _build()
    names = sorted(m.name for m in bpy.data.materials if m.name.startswith("Context - "))
    assert names == sorted(["Context - Building", "Context - Building (height guessed)", "Context - Road",
                            "Context - Tree", "Context - Parcel"])
    guessed = next(ob for ob in bpy.data.objects if ob.get("ctx_id") == "osm:way:2")
    assert guessed.data.materials[0].name == "Context - Building (height guessed)"


def test_rerun_replaces_objects_and_leaves_no_orphan_meshes():
    _build()
    _build()
    assert len(_ctx_objects()) == 2 + 3 + 1
    assert all(me.users > 0 for me in bpy.data.meshes)
    assert len([c for c in bpy.data.collections if c.name.startswith("Context · ")]) == 1


def test_rerun_keeps_the_users_own_objects():
    root = _build()
    mine = bpy.data.objects.new("My massing", bpy.data.meshes.new("My massing"))
    root.objects.link(mine)
    _build()
    assert bpy.data.objects.get("My massing") is mine
    assert mine.name in bpy.context.scene.collection.objects


def test_georef_on_collection_and_origin_empty():
    root = _build()
    origin, = [ob for ob in root.objects if ob.get("ctx_id") == "origin"]
    assert origin.type == "EMPTY"
    for block in (root, origin):
        assert abs(block["lat"] - 43.649667) < 1e-9 and abs(block["lon"] + 79.380991) < 1e-9
        assert block["ground_at_centre_m"] == 84.7 and block["radius_m"] == 150.0
        assert block["credits"] == "© OpenStreetMap contributors"
        assert block["true_north_deg"] == 0.0 and "A test warning." in block["notes_json"]


def test_metric_units_and_identity_transforms():
    _build()
    units = bpy.context.scene.unit_settings
    assert (units.system, units.scale_length, units.length_unit) == ("METRIC", 1.0, "METERS")
    for ob in _ctx_objects():
        assert ob.matrix_world.is_identity, ob.name


def test_a_long_unicode_address_still_builds():
    doc = load_fixture("mini_context.json")
    doc["address"] = "Rue Saint-Denis / Café " + "x" * 80
    root = _build(doc)
    assert root.name.startswith("Context · Rue Saint-Denis / Café") and len(scene_build.site_label(doc)) <= 60


def test_a_site_without_an_address_is_named_by_coordinates():
    doc = load_fixture("mini_context.json")
    doc["address"] = ""
    assert _build(doc).name == "Context · 43.64967, -79.38099"


def test_rerun_keeps_the_users_sub_collections():
    scene = bpy.context.scene
    root = _build()
    mine = bpy.data.collections.new("Proposed massing")
    root.children.link(mine)
    elsewhere = bpy.data.collections.new("Elsewhere")
    scene.collection.children.link(elsewhere)
    elsewhere.children.link(mine)
    massing = bpy.data.objects.new("Massing A", bpy.data.meshes.new("Massing A"))
    mine.objects.link(massing)
    sketches = bpy.data.collections.new("Sketches")
    root.children[f"Buildings · {SITE}"].children.link(sketches)
    _build()
    assert bpy.data.collections.get("Proposed massing") is not None and "Proposed massing" in elsewhere.children
    assert "Massing A" in bpy.data.collections["Proposed massing"].objects
    assert bpy.data.collections.get("Sketches") is not None and "Sketches" in scene.collection.children


def test_rerun_keeps_duplicates_of_context_buildings():
    root = _build()
    tower = next(ob for ob in bpy.data.objects if ob.get("ctx_id") == "osm:way:1")
    copy = tower.copy()
    copy.data = tower.data.copy()
    root.children[f"Buildings · {SITE}"].objects.link(copy)
    name = copy.name
    _build()
    assert bpy.data.objects.get(name) is not None
    assert len([ob for ob in bpy.data.objects if ob.get("ctx_id") == "osm:way:1"]) == 2


def test_user_objects_linked_elsewhere_stay_out_of_the_scene_collection():
    scene = bpy.context.scene
    root = _build()
    elsewhere = bpy.data.collections.new("Elsewhere")
    scene.collection.children.link(elsewhere)
    mine = bpy.data.objects.new("Mine", bpy.data.meshes.new("Mine"))
    root.objects.link(mine)
    elsewhere.objects.link(mine)
    _build()
    assert "Mine" in elsewhere.objects and "Mine" not in scene.collection.objects


def test_the_same_site_in_another_scene_is_left_alone():
    first = bpy.context.scene
    root_a = _build()
    name_a = root_a.name
    other = bpy.data.scenes.new("Other")
    scene_build.build(other, load_fixture("mini_context.json"))
    scene_build.build(other, load_fixture("mini_context.json"))
    assert name_a in first.collection.children
    assert len([c for c in other.collection.children if c.name.startswith("Context · ")]) == 1
    assert len([c for c in bpy.data.collections if c.get("ctx_root")]) == 2


def test_a_courtyard_touching_the_facade_is_still_a_closed_solid():
    doc = load_fixture("mini_context.json")
    doc["elements"] = [{"id": "osm:way:9", "kind": "building", "name": "Pinched", "meshes": [], "lines": [],
                        "solids": [{"kind": "building", "height_source": "osm_height", "z0": -0.3, "z1": 10.0,
                                    "rings": [[[0, 0], [30, 0], [30, 30], [0, 30], [0, 10]],
                                              [[0, 10], [10, 12], [10, 8]]]}]}]
    root = _build(doc)
    ob, = root.children[f"Buildings · {SITE}"].objects
    assert closed_and_outward(*mesh_arrays(ob))


def test_survey_point_on_collection_and_origin_empty():
    root = _build()
    origin, = [ob for ob in root.objects if ob.get("ctx_id") == "origin"]
    for block in (root, origin):
        assert block["survey_epsg"] == "EPSG:32617" and block["survey_name"] == "WGS 84 / UTM zone 17N"
        assert block["survey_easting_m"] == 630564.787 and block["survey_northing_m"] == 4834236.788
        assert block["survey_elevation_m"] == 84.7 and block["survey_grid_angle_deg"] == 1.117674
        assert block["true_north_deg"] == 0.0


def test_an_older_context_without_a_survey_point_still_builds():
    doc = load_fixture("mini_context.json")
    del doc["survey"]
    root = _build(doc)
    origin, = [ob for ob in root.objects if ob.get("ctx_id") == "origin"]
    assert not [k for k in origin.keys() if k.startswith("survey_")] and origin["lat"] == 43.649667
