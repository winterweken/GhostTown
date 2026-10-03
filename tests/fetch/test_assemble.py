import pytest

from ghosttown_fetch import context as ctx
from ghosttown_fetch import request as rq
from ghosttown_fetch.assemble import NothingFetched, assemble
from ghosttown_fetch.net import SourceError
from fakes import FakeNet
from osm_samples import LAT0, LON0, body, square, way

ONE = body(way(1, square(0, 0, 10), {"building": "yes", "height": "20"}))


def _req(tmp_path, **kw):
    return rq.build(centre={"lat": LAT0, "lon": LON0}, radius_m=150, cache_dir=str(tmp_path / "c"),
                    out_dir=str(tmp_path / "o"), address="Test site", **kw)


def test_buildings_from_osm(tmp_path):
    doc = assemble(_req(tmp_path), FakeNet({"osm": ONE}))
    assert doc["counts"] == {"building": 1}
    assert [s["key"] for s in doc["sources"]] == ["osm"]
    assert doc["terrain"]["source"] == "flat" and doc["address"] == "Test site"
    assert ctx.validate(doc) == []


def test_layers_not_built_yet_get_an_info_note(tmp_path):
    doc = assemble(_req(tmp_path), FakeNet({"osm": ONE}))
    later = [n for n in doc["notes"] if n["code"] == "later"]
    assert later and later[0]["level"] == "info" and "terrain" in later[0]["text"]


def test_when_the_only_source_fails_nothing_is_fetched(tmp_path):
    net = FakeNet({"osm": SourceError("OpenStreetMap answered HTTP 504; try again in a minute.")})
    with pytest.raises(NothingFetched, match="504"):
        assemble(_req(tmp_path), net)


def test_progress_is_reported_in_order(tmp_path):
    seen = []
    assemble(_req(tmp_path), FakeNet({"osm": ONE}), progress=lambda stage, pct: seen.append((stage, pct)))
    assert seen[0][0] == "OpenStreetMap"
    assert [pct for _, pct in seen] == sorted(pct for _, pct in seen)


def test_custom_overpass_endpoint_is_used(tmp_path):
    net = FakeNet({"osm": ONE})
    assemble(_req(tmp_path, overpass_url="https://example.org/api/interpreter"), net)
    assert net.calls[0][0] == "https://example.org/api/interpreter"
