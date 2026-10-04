import gzip
from pathlib import Path

import pytest

from ghosttown_fetch import buildings
from ghosttown_fetch import context as ctx
from ghosttown_fetch import request as rq
from ghosttown_fetch.frame import Frame
from ghosttown_fetch.sources import osm
from ghosttown_fetch.terrain import FlatTerrain
from osm_samples import LAT0, LON0, body, relation, square, way
from terrains import Ramp

FRAME = Frame(LAT0, LON0)
FLAT = FlatTerrain()


def build(*elements):
    return buildings.from_osm(osm.parse(body(*elements)), FRAME, FLAT)


def valid(elements):
    req = rq.build(centre={"lat": LAT0, "lon": LON0}, radius_m=150, cache_dir="c", out_dir="o")
    doc = ctx.new(req, region="world", terrain_source="flat")
    doc["elements"] = elements
    return ctx.validate(ctx.finish(doc))


def _area(ring):
    return 0.5 * sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))


@pytest.mark.parametrize("text, metres", [
    ("12", 12.0), ("12 m", 12.0), ("12.5m", 12.5), ("12,5", 12.5), ("40'", 12.192),
    ("40 ft", 12.192), ("12'6\"", 3.81), ("tall", None), (None, None), ("", None),
])
def test_parse_length(text, metres):
    got = buildings.parse_length(text)
    if metres is None:
        assert got is None
    else:
        assert got == pytest.approx(metres, abs=1e-3)


def test_flat_terrain():
    assert FLAT.z([1.0, 2.0], [3.0, 4.0]).tolist() == [0.0, 0.0]
    assert FLAT.min_under(None) == 0.0


def test_height_tag_wins_over_levels():
    el, = build(way(1, square(0, 0, 10), {"building": "yes", "height": "30", "building:levels": "3"}))
    s, = el["solids"]
    assert (s["z0"], s["z1"], s["height_source"], el["kind"]) == (-0.3, 30.0, "osm_height", "building")


def test_each_solid_records_the_ground_under_it():
    el, = buildings.from_osm(osm.parse(body(way(1, square(20, 0, 10), {"building": "yes", "height": "12", "min_height": "3"}))),
                             FRAME, Ramp())
    s, = el["solids"]
    assert s["ground"] == pytest.approx(2.0, abs=0.01)
    assert (s["z0"], s["z1"]) == (pytest.approx(5.0, abs=0.01), pytest.approx(14.0, abs=0.01))


def test_levels_when_there_is_no_height():
    el, = build(way(1, square(0, 0, 10), {"building": "yes", "building:levels": "4"}))
    assert el["solids"][0]["z1"] == pytest.approx(12.8) and el["solids"][0]["height_source"] == "osm_levels"


def test_guessed_height_marks_the_kind():
    el, = build(way(1, square(0, 0, 10), {"building": "yes"}))
    assert el["kind"] == "building_guessed" and el["solids"][0]["kind"] == "building_guessed"
    assert el["solids"][0]["z1"] == 9.0


def test_rings_are_ccw_unclosed_local_metres():
    el, = build(way(1, square(0, 0, 10), {"building": "yes"}))
    ring = el["solids"][0]["rings"][0]
    assert len(ring) == 4 and _area(ring) == pytest.approx(100.0, abs=0.05)


def test_parts_replace_their_outline():
    els = build(
        way(1, square(0, 0, 20), {"building": "yes", "height": "10"}),
        way(2, square(0, 0, 10), {"building:part": "yes", "height": "30"}),
        way(3, square(10, 0, 10), {"building:part": "yes", "height": "5"}),
    )
    assert [el["id"] for el in els] == ["osm:way:1"]
    assert sorted(s["z1"] for s in els[0]["solids"]) == [5.0, 30.0]


def test_a_part_outside_every_outline_is_its_own_building():
    el, = build(way(2, square(0, 0, 10), {"building:part": "yes", "height": "7"}))
    assert el["id"] == "osm:way:2" and el["solids"][0]["z1"] == 7.0


def test_min_height_lifts_the_base():
    el, = build(way(1, square(0, 0, 10), {"building": "yes", "min_height": "6", "height": "12"}))
    assert (el["solids"][0]["z0"], el["solids"][0]["z1"]) == (6.0, 12.0)


def test_building_no_and_bare_roofs_are_skipped():
    assert build(way(1, square(0, 0, 10), {"building": "no"})) == []
    assert build(way(1, square(0, 0, 10), {"building": "roof"})) == []
    el, = build(way(1, square(0, 0, 10), {"building": "roof", "min_height": "3", "height": "4"}))
    assert el["solids"][0]["z0"] == 3.0


def test_a_self_intersecting_way_is_repaired_not_fatal():
    els = build(way(1, [(0, 0), (10, 10), (10, 0), (0, 10), (0, 0)], {"building": "yes", "height": "5"}))
    assert len(els) == 1 and len(els[0]["solids"]) == 2
    assert valid(els) == []


def test_a_courtyard_keeps_its_hole():
    el, = build(relation(7, [[(0, 0), (30, 0), (30, 30)], [(30, 30), (0, 30), (0, 0)]],
                         [square(10, 10, 10)], {"building": "yes", "height": "15"}))
    assert len(el["solids"][0]["rings"]) == 2


def test_names_come_from_name_or_address():
    a, = build(way(1, square(0, 0, 10), {"building": "yes", "name": "Old City Hall"}))
    b, = build(way(2, square(0, 0, 10), {"building": "yes", "addr:housenumber": "320", "addr:street": "Bay Street"}))
    assert (a["name"], b["name"]) == ("Old City Hall", "320 Bay Street")


def test_recorded_bay_street_buildings_are_valid():
    raw = gzip.decompress((Path(__file__).parent / "fixtures" / "bay" / "osm.json.gz").read_bytes())
    lat, lon = 43.649667, -79.380991
    els = buildings.from_osm(osm.parse(raw), Frame(lat, lon), FLAT)
    assert len(els) >= 30  # 36 outlines in the recording; their 92 parts fold into them
    assert valid(els) == []


def test_a_self_touching_way_gives_rings_that_do_not_touch():
    from shapely.geometry import LinearRing

    pts = [(0, 0), (20, 0), (20, 20), (0, 20), (0, 10), (5, 12), (5, 8), (0, 10), (0, 0)]
    els = build(way(1, pts, {"building": "yes", "height": "6"}))
    assert els and valid(els) == []
    for s in els[0]["solids"]:
        lrs = [LinearRing(r) for r in s["rings"]]
        assert all(lr.is_simple for lr in lrs)
        assert not any(a.intersects(b) for i, a in enumerate(lrs) for b in lrs[i + 1:])
