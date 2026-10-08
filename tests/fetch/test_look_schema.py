import json

from ghosttown_fetch import LOOK_SCHEMA, TOOL
from ghosttown_fetch import look_schema as ls

BOX = {"id": "t:1", "solids": [{"rings": [[[0, 0], [10, 0], [10, 10], [0, 10]]], "z0": 0, "z1": 20}]}


def _req(**changes):
    req = ls.build_request(centre={"lat": 43.65, "lon": -79.38}, radius_m=300, buildings=[BOX],
                           cache_dir="/c", out_dir="/c/runs/look-1")
    req.update(changes)
    return req


def test_a_built_request_is_valid_and_carries_no_token():
    req = _req()
    assert ls.validate_request(req) == []
    assert req["schema"] == LOOK_SCHEMA and req["tool"] == TOOL
    assert req["budget_photos"] == 150 and req["search_margin_m"] == 200.0 and req["not_before_year"] is None
    assert req["buildings"][0]["detail"] is False
    assert "token" not in json.dumps(req).lower()
    assert ls.TOKEN_ENV == "GHOSTTOWN_MAPILLARY_TOKEN"


def test_request_problems_are_plain_sentences():
    assert "radius_m" in ls.validate_request(_req(radius_m=5))[0]
    assert "budget_photos" in ls.validate_request(_req(budget_photos=5))[0]
    assert "not_before_year" in ls.validate_request(_req(not_before_year=1990))[0]
    assert "search_margin_m" in ls.validate_request(_req(search_margin_m=900))[0]
    flat = {"id": "x", "solids": [{"rings": BOX["solids"][0]["rings"], "z0": 5, "z1": 5}]}
    assert "z0 below z1" in ls.validate_request(_req(buildings=[flat]))[0]
    line = {"id": "x", "solids": [{"rings": [[[0, 0], [1, 1]]], "z0": 0, "z1": 5}]}
    assert "rings of at least 3" in ls.validate_request(_req(buildings=[line]))[0]


def test_at_most_twenty_buildings_have_detail():
    many = [dict(BOX, id=f"t:{i}", detail=True) for i in range(21)]
    assert any("At most 20" in p for p in ls.validate_request(_req(buildings=many)))


def test_not_before_zero_means_every_year():
    req = ls.build_request(centre={"lat": 1, "lon": 2}, radius_m=300, buildings=[], cache_dir="c", out_dir="o",
                           not_before_year=0)
    assert req["not_before_year"] is None


def test_read_request_reports_unreadable_files(tmp_path):
    doc, problems = ls.read_request(str(tmp_path / "missing.json"))
    assert doc is None and "Couldn't read" in problems[0]


ENTRY = {"source": "photos", "photos": 3, "confidence": 0.8, "floor_h": 3.5,
         "zones": [{"h0": 0, "h1": 3, "kind": "storefront", "colour": [0.05, 0.05, 0.05]},
                   {"h0": 3, "h1": None, "kind": "glass", "colour": [0.2, 0.4, 0.5]}]}


def _answer():
    doc = ls.new_answer()
    doc["buildings"]["t:1"] = json.loads(json.dumps(ENTRY))
    return doc


def test_answer_validation():
    assert ls.validate_answer(_answer()) == []
    gap = _answer()
    gap["buildings"]["t:1"]["zones"][1]["h0"] = 4
    assert "without gaps" in ls.validate_answer(gap)[0]
    closed = _answer()
    closed["buildings"]["t:1"]["zones"][1]["h1"] = 30
    assert "zone 2" in ls.validate_answer(closed)[0]
    brick = _answer()
    brick["buildings"]["t:1"]["zones"][0]["kind"] = "brick"
    assert "zone 1" in ls.validate_answer(brick)[0]
    assert "schema" in ls.validate_answer({"schema": 9})[0]
