import pytest
from shapely.geometry import Polygon, box

from ghosttown_fetch import buildings
from ghosttown_fetch import context as ctx
from ghosttown_fetch.frame import Frame
from ghosttown_fetch.sources import toronto_massing as massing
from ghosttown_fetch.terrain import FlatTerrain
from fakes import FakeNet, router
from test_toronto_massing import SUBSET, package


def P(record, geom, height, base=0.0, source="toronto_massing_lidar"):
    return massing.Part(record, [geom], height, base, source)


def tops(element):
    return sorted((s["z1"], round(Polygon(s["rings"][0], s["rings"][1:]).area)) for s in element["solids"])


def test_a_tower_on_its_podium_is_one_building_with_both_heights():
    el, = buildings.from_massing([P(4, box(0, 0, 40, 40), 12.0), P(9, box(10, 10, 20, 20), 80.0)], FlatTerrain(), 150, 2025)
    assert el["id"] == "toronto:massing:2025:4" and el["kind"] == "building"
    assert tops(el) == [(12.0, 1500), (80.0, 100)]
    assert {s["height_source"] for s in el["solids"]} == {"toronto_massing_lidar"}


def test_a_mostly_covered_part_keeps_its_own_height():
    slab, low = P(1, box(0, 0, 40, 40), 40.0), P(2, box(0, 0, 40, 37), 10.0)  # 92.5 % covered by a lower part
    el, = buildings.from_massing([slab, low], FlatTerrain(), 150, 2025)
    assert tops(el) == [(10.0, 1480), (40.0, 120)]


def test_neighbours_that_only_touch_stay_separate():
    els = buildings.from_massing([P(1, box(0, 0, 10, 10), 9.0), P(2, box(10, 0, 20, 10), 15.0)], FlatTerrain(), 150, 2025)
    assert sorted(e["id"] for e in els) == ["toronto:massing:2025:1", "toronto:massing:2025:2"]


def test_only_buildings_touching_the_circle_come_in_whole():
    near, far = P(1, box(140, -5, 170, 5), 9.0), P(2, box(300, 0, 310, 10), 9.0)
    el, = buildings.from_massing([near, far], FlatTerrain(), 150, 2025)
    assert el["id"] == "toronto:massing:2025:1"
    assert Polygon(el["solids"][0]["rings"][0]).bounds == (140.0, -5.0, 170.0, 5.0)


def test_a_raised_part_starts_at_its_base():
    el, = buildings.from_massing([P(1, box(0, 0, 10, 10), 20.0, base=5.0)], FlatTerrain(), 150, 2025)
    assert (el["solids"][0]["z0"], el["solids"][0]["z1"]) == (5.0, 20.0)


def test_no_parts_no_buildings():
    assert buildings.from_massing([], FlatTerrain(), 150, 2025) == []


def test_the_recorded_slice_builds_valid_buildings(tmp_path):
    net = FakeNet({"toronto": router({"package_show?id=3d-massing": package(2025), "3DMassingShapefile_": SUBSET})})
    frame = Frame(43.649667, -79.380991)
    parts, year = massing.fetch(net, str(tmp_path), frame, 150)
    els = buildings.from_massing(parts, FlatTerrain(), 150, year)
    assert len(els) >= 30 and len({e["id"] for e in els}) == len(els)
    assert max(s["z1"] for e in els for s in e["solids"]) > 150  # the towers at Bay and Adelaide
    doc = ctx.new({"centre": {"lat": 43.649667, "lon": -79.380991}, "radius_m": 150}, region="toronto", terrain_source="flat")
    doc["elements"] = els
    assert ctx.validate(ctx.finish(doc)) == []
