import os
import subprocess
import sys
from pathlib import Path

import pytest

from ghosttown_fetch import context as ctx
from ghosttown_fetch import request as rq

SQUARE = [[0, 0], [10, 0], [10, 10], [0, 10]]
TETRA = {"kind": "tree", "verts": [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
         "faces": [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]}
GHOSTTOWN_DIR = str(Path(__file__).resolve().parents[2] / "ghosttown")


def _doc():
    req = rq.build(centre={"lat": 43.65, "lon": -79.38}, radius_m=150,
                   cache_dir="c", out_dir="o", address="320 Bay St")
    return ctx.new(req, region="world", terrain_source="flat")


def _building(eid, kind="building"):
    return ctx.element(eid, kind, solids=[ctx.solid(kind, [SQUARE], -0.3, 10, "osm_height")])


def test_new_document_is_valid_and_empty():
    doc = ctx.finish(_doc())
    assert ctx.validate(doc) == []
    assert doc["address"] == "320 Bay St" and doc["counts"] == {} and doc["terrain"]["source"] == "flat"


def test_counts_by_kind():
    doc = _doc()
    doc["elements"] += [_building("a"), _building("b"), ctx.element("t", "tree", meshes=[TETRA])]
    assert ctx.finish(doc)["counts"] == {"building": 2, "tree": 1}


def test_solid_rounds_heights_to_millimetres():
    s = ctx.solid("building", [SQUARE], -0.30004, 12.34567, "osm_height")
    assert (s["z0"], s["z1"]) == (-0.3, 12.346)


def test_a_solid_records_the_ground_its_top_stands_on():
    s = ctx.solid("building", [SQUARE], -1.3, 12.0, "osm_height", ground=-1.00004)
    assert s["ground"] == -1.0
    assert "ground" not in ctx.solid("building", [SQUARE], 0, 1, "s")


def test_add_source_once_with_its_credit():
    doc = _doc()
    ctx.add_source(doc, "osm")
    ctx.add_source(doc, "osm")
    assert doc["sources"] == [{"key": "osm", "name": "OpenStreetMap", "credit": "© OpenStreetMap contributors"}]


@pytest.mark.parametrize("bad, words", [
    (ctx.element("x", "spaceship", solids=[ctx.solid("building", [SQUARE], 0, 1, "s")]), "unknown kind"),
    (ctx.element("x", "building", solids=[ctx.solid("building", [[[0, 0], [1, 0]]], 0, 1, "s")]), "rings"),
    (ctx.element("x", "building", solids=[ctx.solid("building", [SQUARE], 5, 5, "s")]), "z0 below z1"),
    (ctx.element("x", "road", meshes=[{"kind": "road", "verts": [[0, 0, 0]], "faces": [[0, 1, 2]]}]), "missing vertex"),
    (ctx.element("x", "parcel", lines=[{"kind": "parcel", "pts": [[0, 0, 0]]}]), "2 points"),
    (ctx.element("x", "building"), "no geometry"),
    (ctx.element("x", "building", solids=[dict(ctx.solid("building", [SQUARE], 0, 1, "s"), ground="low")]),
     "ground must be a number"),
])
def test_validate_catches_bad_elements(bad, words):
    doc = _doc()
    doc["elements"].append(bad)
    problems = ctx.validate(ctx.finish(doc))
    assert any(words in p for p in problems), problems


def test_validate_catches_missing_top_level_keys():
    assert "The context has no elements." in ctx.validate({"schema": 1})


def test_iter_elements_ground_then_buildings_then_trees_then_parcels():
    doc = _doc()
    for eid, kind in [("p", "parcel"), ("t", "tree"), ("b", "building"), ("r", "road"), ("w", "water")]:
        doc["elements"].append(ctx.element(eid, kind, lines=[{"kind": kind, "pts": [[0, 0, 0], [1, 0, 0]]}]))
    assert [el["kind"] for el in ctx.iter_elements(doc)] == ["water", "road", "building", "tree", "parcel"]


def test_schema_modules_are_stdlib_only():
    code = ("import sys; sys.modules['numpy'] = None; sys.modules['shapely'] = None; sys.modules['PIL'] = None; "
            "import ghosttown_fetch, ghosttown_fetch.request, ghosttown_fetch.context, ghosttown_fetch.look_schema; "
            "print('ok')")
    env = {**os.environ, "PYTHONPATH": GHOSTTOWN_DIR}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    assert out.stdout.strip() == "ok", out.stderr


def test_survey_is_optional_but_must_hold_numbers_when_present():
    doc = ctx.new(rq.build(centre={"lat": 43.65, "lon": -79.38}, radius_m=150, cache_dir="/c", out_dir="/o"),
                  region="toronto", terrain_source="flat")
    assert "survey" not in doc and ctx.validate(doc) == []
    doc["survey"] = {"epsg": "EPSG:2952", "name": "NAD83(CSRS) / MTM zone 10", "easting_m": 314400.285,
                     "northing_m": 4834420.675, "elevation_m": None, "grid_angle_deg": 0.082146}
    assert ctx.validate(doc) == []
    doc["survey"]["northing_m"] = "4834419"
    assert ctx.validate(doc) == ["The survey point needs a numeric easting, northing and grid angle."]


def test_survey_must_name_its_grid():
    doc = ctx.new(rq.build(centre={"lat": 43.65, "lon": -79.38}, radius_m=150, cache_dir="/c", out_dir="/o"),
                  region="toronto", terrain_source="flat")
    good = {"epsg": "EPSG:2952", "name": "NAD83(CSRS) / MTM zone 10", "easting_m": 314400.285,
            "northing_m": 4834420.675, "elevation_m": None, "grid_angle_deg": 0.082146}
    for key, bad in (("epsg", None), ("name", None), ("epsg", ""), ("name", "  "), ("epsg", 2952)):
        doc["survey"] = dict(good)
        if bad is None:
            del doc["survey"][key]
        else:
            doc["survey"][key] = bad
        assert ctx.validate(doc) == ["The survey point needs its grid's name and EPSG code."], (key, bad)


def test_photo_is_optional_but_must_be_well_formed():
    doc = ctx.new(rq.build(centre={"lat": 43.65, "lon": -79.38}, radius_m=150, cache_dir="/c", out_dir="/o"),
                  region="toronto", terrain_source="flat")
    good = {"file": "photo.jpg", "year": 2025, "width_px": 3750, "height_px": 3750,
            "bounds_m": [-150.0, -150.0, 150.0, 150.0], "source": "toronto"}
    for fine in (good, dict(good, year=None)):
        doc["photo"] = fine
        assert ctx.validate(doc) == []
    for bad in (dict(good, file="../photo.jpg"), dict(good, file="C:photo.jpg"), dict(good, file=""),
                dict(good, bounds_m=[1, 0, 0, 1]),
                dict(good, bounds_m=[0, 0, 1]), dict(good, width_px=0), dict(good, year="2025")):
        doc["photo"] = bad
        assert ctx.validate(doc) == [
            "The photo needs a file name beside context.json, a pixel size and bounds_m [xmin, ymin, xmax, ymax]."]


LIDAR = {"file": "lidar_roofs.npz", "cell_m": 0.5, "year": None, "source": "ontario", "buildings": 3,
         "triangles": 1200, "kinds": ["building", "building_on_site", "building_guessed"]}


@pytest.mark.parametrize("change", [
    {"file": "../lidar_roofs.npz"}, {"file": "C:lidar.npz"}, {"file": ""}, {"cell_m": 0}, {"buildings": -1},
    {"triangles": 1.5}, {"kinds": ["road"]}, {"kinds": []}, {"year": "2023"},
])
def test_lidar_roofs_are_optional_but_must_be_well_formed(change):
    doc = _doc()
    assert ctx.validate(doc) == []
    doc["lidar"] = dict(LIDAR)
    assert ctx.validate(doc) == []
    doc["lidar"].update(change)
    assert any("LiDAR roofs need" in p for p in ctx.validate(doc))


@pytest.mark.parametrize("roof, ok", [
    ({"shape": "gabled", "height": 2.5}, True), ({"shape": "flat"}, True), ({"height": 3}, True),
    ({"shape": ""}, False), ({"height": 0}, False), ({"height": "2"}, False), ({"pitch": 30}, False), ("gabled", False),
])
def test_a_solids_roof_tags_are_optional_but_must_be_well_formed(roof, ok):
    doc = _doc()
    s = ctx.solid("building", [SQUARE], -0.3, 10, "osm_height")
    s["roof"] = roof
    doc["elements"] = [ctx.element("osm:way:1", "building", solids=[s])]
    problems = ctx.validate(doc)
    assert problems == ([] if ok else ["osm:way:1: a solid's roof tags need a shape name and a positive height, each optional."])


@pytest.mark.parametrize("change", [
    {"file": "../fitted_roofs.npz"}, {"file": ""}, {"buildings": -1}, {"triangles": 1.5}, {"triangles": None},
])
def test_fitted_roofs_are_optional_but_must_be_well_formed(change):
    doc = _doc()
    doc["lidar"] = dict(LIDAR, fitted={"file": "fitted_roofs.npz", "buildings": 3, "triangles": 400})
    assert ctx.validate(doc) == []
    doc["lidar"]["fitted"].update(change)
    assert ctx.validate(doc) == ["The fitted roofs need a file name beside context.json and counts."]


def _apps_doc(sites, date="2026-10-09"):
    doc = ctx.finish(ctx.new({"centre": {"lat": 43.65, "lon": -79.38}, "radius_m": 150.0}, region="toronto",
                             terrain_source="flat"))
    doc["applications"] = sites
    if date is not None:
        doc["applications_date"] = date
    return doc


def _app_entry(number="A1", **over):
    entry = {"number": number, "type": "OZ", "status": "Under Review", "submitted": "2024-01-01",
             "address": "1 Main St", "description": "a 14-storey building", "source": "application",
             "floor_area_m2": 0.0, "url": "http://app.toronto.ca/AIC/index.do?folderRsn=abc"}
    entry.update(over)
    return entry


def _app_site(**over):
    site = {"id": "app:21 1 BLD", "group": "construction", "numbers": ["21 1 BLD", "A1"], "main": "21 1 BLD",
            "centre_m": [10.0, 5.0], "angle_deg": 12.5, "width_m": 30.0, "depth_m": 20.0, "height_m": 45.0,
            "base_m": -0.3, "height_from": "permit: 14 storeys",
            "applications": [_app_entry("21 1 BLD", type="Apartment Building", status="Inspection", source="permit",
                                        description="", floor_area_m2=1200.0, url=""),
                             _app_entry("A1")]}
    site.update(over)
    return site


def test_a_doc_with_application_sites_is_valid():
    other = _app_site(id="app:B", group="review", numbers=["B"], main="B", applications=[_app_entry("B")])
    assert ctx.validate(_apps_doc([_app_site(), other])) == []
    assert ctx.validate(_apps_doc([])) == []


@pytest.mark.parametrize("change, words", [
    ({"group": "rumoured"}, "unknown group"),
    ({"numbers": ["A1", "A1"]}, "distinct"),
    ({"main": "Z"}, "main application"),
    ({"centre_m": [1.0]}, "no centre"),
    ({"angle_deg": float("nan")}, "angle_deg"),
    ({"width_m": 0.0}, "width_m"),
    ({"height_from": ""}, "height is from"),
    ({"applications": []}, "do not match"),
    ({"id": "A1"}, "no id"),
])
def test_a_broken_application_site_is_named(change, words):
    problems = ctx.validate(_apps_doc([_app_site(**change)]))
    assert len(problems) == 1 and words in problems[0]


@pytest.mark.parametrize("change", [{"source": "rumour"}, {"url": "https://example.com/AIC"},
                                    {"floor_area_m2": -1.0}, {"description": None}, {"submitted": 20240101}])
def test_a_broken_application_entry_is_refused(change):
    site = _app_site()
    site["applications"][1].update(change)
    problems = ctx.validate(_apps_doc([site]))
    assert len(problems) == 1 and "do not match" in problems[0]


def test_two_sites_may_not_share_an_id_or_a_number():
    a = _app_site()
    b = _app_site(numbers=["A1", "B"], main="B", applications=[_app_entry("A1"), _app_entry("B")])
    problems = ctx.validate(_apps_doc([a, b]))
    assert "Application site id app:21 1 BLD is used twice." in problems
    assert "Application A1 is in two sites." in problems


def test_applications_need_their_day_and_must_be_a_list():
    day = "The applications need the day they were fetched, as YYYY-MM-DD."
    assert ctx.validate(_apps_doc([], date=None)) == [day]
    assert ctx.validate(_apps_doc([], date="9 Oct")) == [day]
    assert ctx.validate(_apps_doc({})) == ["The applications must be a list."]


def test_applications_problems_checks_a_list_and_its_day_without_a_document():
    assert ctx.applications_problems([], "2026-10-09") == []
    assert ctx.applications_problems([_app_site()], "2026-10-09") == []
    (problem,) = ctx.applications_problems([_app_site(group="rumoured")], "2026-10-09")
    assert "unknown group" in problem
    assert ctx.applications_problems([], None) == ["The applications need the day they were fetched, as YYYY-MM-DD."]


@pytest.mark.parametrize("url, want", [
    ("http://app.toronto.ca/AIC/index.do?folderRsn=abc", "http://app.toronto.ca/AIC/index.do?folderRsn=abc"),
    ("https://secure.toronto.ca/x", "https://secure.toronto.ca/x"), ("https://toronto.ca/", "https://toronto.ca/"),
    (" https://www.toronto.ca/a ", "https://www.toronto.ca/a"),
    ("https://toronto.ca.evil.com/x", ""), ("https://eviltoronto.ca/x", ""), ("ftp://app.toronto.ca/x", ""),
    ("javascript:alert(1)", ""), ("", ""), (None, ""), ("http://[::1", ""),
    ("https://evil.com\\@toronto.ca/x", ""), ("https://user@toronto.ca/x", ""), ("https://toronto.ca@evil.com/", ""),
    ("https://www.toronto.ca/a b", ""), ("https://www.toronto.ca/a\tb", ""),
    ("https://xn--toronto-9ya.ca/", ""), ("https://torontö.ca/", ""),
    ("HTTPS://WWW.TORONTO.CA/a", "HTTPS://WWW.TORONTO.CA/a"),
    ("https://toronto.ca:443/x", "https://toronto.ca:443/x"), ("https://toronto.ca./x", "")])
def test_only_links_on_toronto_ca_are_kept(url, want):
    assert ctx.city_link(url) == want


@pytest.mark.parametrize("url", ["https://toronto.ca:443.evil.com/x", "https://toronto.ca:abc/x",
                                 "https://toronto.ca:99999/x"])
def test_a_port_that_is_not_a_number_is_no_city_link(url):
    assert ctx.city_link(url) == ""
