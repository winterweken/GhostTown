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
