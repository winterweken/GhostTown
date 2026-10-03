import json

import pytest

from ghosttown_fetch import LAYERS
from ghosttown_fetch import request as rq


def good(**kw):
    return rq.build(centre={"lat": 43.65, "lon": -79.38}, radius_m=300,
                    cache_dir="/tmp/c", out_dir="/tmp/o", **kw)


def test_build_fills_defaults_and_is_valid():
    d = good()
    assert rq.validate(d) == []
    assert d["schema"] == 1 and d["tool"].startswith("ghosttown ")
    assert d["layers"] == list(LAYERS)
    assert d["site_polys_m"] == [] and d["fetch_fresh"] is False and d["overpass_url"] == ""


@pytest.mark.parametrize("change, words", [
    ({"radius_m": 20}, "radius_m"),
    ({"radius_m": 5000}, "radius_m"),
    ({"radius_m": True}, "radius_m"),
    ({"layers": []}, "layers"),
    ({"layers": ["roofs"]}, "layers"),
    ({"centre": {"lat": 91, "lon": 0}}, "centre"),
    ({"centre": {"lat": "43", "lon": 0}}, "centre"),
    ({"out_dir": " "}, "out_dir"),
    ({"site_polys_m": [[[0, 0], [1, 0]]]}, "site_polys_m"),
    ({"site_polys_m": [[[0, 0], [1, 0], [0, 9999]]]}, "site_polys_m"),
    ({"fetch_fresh": "yes"}, "fetch_fresh"),
    ({"overpass_url": "ftp://example.org"}, "overpass_url"),
    ({"schema": 2}, "schema"),
])
def test_validate_names_the_problem(change, words):
    d = good()
    d.update(change)
    problems = rq.validate(d)
    assert any(words in p for p in problems), problems


def test_validate_rejects_non_objects():
    assert rq.validate([]) == ["The request is not a JSON object."]


def test_read_reports_missing_and_bad_json(tmp_path):
    doc, problems = rq.read(str(tmp_path / "none.json"))
    assert doc is None and problems[0].startswith("Couldn't read the request")
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    doc, problems = rq.read(str(bad))
    assert doc is None and problems[0].startswith("Couldn't read the request")


def test_read_round_trip(tmp_path):
    path = tmp_path / "request.json"
    path.write_text(json.dumps(good()), encoding="utf-8")
    doc, problems = rq.read(str(path))
    assert problems == [] and doc == good()
