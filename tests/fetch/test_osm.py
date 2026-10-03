import gzip
from pathlib import Path

import pytest

from ghosttown_fetch.net import SourceError
from ghosttown_fetch.sources import osm
from fakes import FakeNet
from osm_samples import LAT0, LON0, body, node, relation, square, way

FIXTURES = Path(__file__).parent / "fixtures"


def test_query_asks_for_buildings_and_parts_around_the_centre():
    q = osm.build_query(43.649667, -79.380991, 150, ["buildings"])
    assert q.startswith("[out:json][timeout:90];")
    assert '(around:150,43.6496670,-79.3809910)' in q
    assert 'way["building"]' in q and 'relation["building:part"]["type"="multipolygon"]' in q
    assert q.endswith("out tags geom qt;")


def test_parse_way_polygon_open_line_and_node_point():
    feats = osm.parse(body(
        way(1, square(0, 0, 10), {"building": "yes"}),
        way(2, [(0, 0), (5, 0)], {"highway": "service"}),
        node(3, 1, 1, {"natural": "tree"}),
    ))
    assert [f.id for f in feats] == ["osm:way:1", "osm:way:2", "osm:node:3"]
    assert [f.geom.geom_type for f in feats] == ["Polygon", "LineString", "Point"]
    assert feats[0].tags == {"building": "yes"}


def test_parse_multipolygon_with_split_outer_and_a_courtyard():
    outer_a = [(0, 0), (30, 0), (30, 30)]
    outer_b = [(30, 30), (0, 30), (0, 0)]
    inner = square(10, 10, 10)
    f, = osm.parse(body(relation(7, [outer_a, outer_b], [inner], {"building": "yes"})))
    assert f.id == "osm:relation:7" and f.geom.geom_type == "Polygon" and len(f.geom.interiors) == 1


def test_a_remark_means_the_server_gave_up():
    with pytest.raises(SourceError, match="Overpass"):
        osm.parse(body(remark='runtime error: Query timed out in "query" at line 3 after 91 seconds.'))


def test_non_json_means_failure():
    with pytest.raises(SourceError, match="isn't JSON"):
        osm.parse(b"<html>Too busy</html>")


def test_fetch_posts_the_query_and_rejects_partial_answers():
    net = FakeNet({"osm": body(way(1, square(0, 0, 10), {"building": "yes"}))})
    feats = osm.fetch(net, LAT0, LON0, 150, ["buildings"])
    url, source, data = net.calls[0]
    assert url == osm.ENDPOINT and source == "osm" and data.startswith(b"data=")
    assert len(feats) == 1
    with pytest.raises(SourceError):
        osm.fetch(FakeNet({"osm": body(remark="runtime error: out of memory")}), LAT0, LON0, 150, ["buildings"])


def test_fetch_uses_a_custom_endpoint():
    net = FakeNet({"osm": body()})
    osm.fetch(net, LAT0, LON0, 150, ["buildings"], endpoint="https://example.org/api/interpreter")
    assert net.calls[0][0] == "https://example.org/api/interpreter"


def test_recorded_bay_street_answer_parses():
    feats = osm.parse(gzip.decompress((FIXTURES / "bay" / "osm.json.gz").read_bytes()))
    polygonal = [f for f in feats if f.geom.geom_type in ("Polygon", "MultiPolygon")]
    outlines = [f for f in polygonal if "building" in f.tags]
    parts = [f for f in polygonal if "building:part" in f.tags]
    assert len(outlines) >= 30 and len(parts) >= 50  # downtown towers are mapped as parts
