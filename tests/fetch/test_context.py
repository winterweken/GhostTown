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
    code = ("import sys; sys.modules['numpy'] = None; sys.modules['shapely'] = None; "
            "import ghosttown_fetch, ghosttown_fetch.request, ghosttown_fetch.context; print('ok')")
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
