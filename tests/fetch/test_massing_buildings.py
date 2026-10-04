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


def test_the_taller_part_wins_where_parts_overlap():
    slab, low = P(1, box(0, 0, 40, 40), 40.0), P(2, box(0, 0, 40, 37), 10.0)
    el, = buildings.from_massing([slab, low], FlatTerrain(), 150, 2025)
    assert tops(el) == [(40.0, 1600)]


def test_a_low_part_inside_a_tall_one_is_hidden():
    tower, low = P(1, box(0, 0, 50, 60), 240.0), P(2, box(10, 10, 30, 40), 11.0)
    el, = buildings.from_massing([tower, low], FlatTerrain(), 150, 2025)
    assert tops(el) == [(240.0, 3000)]


def test_equal_tops_go_to_the_lower_record():
    a, b = P(7, box(0, 0, 20, 10), 15.0), P(3, box(10, 0, 30, 10), 15.0)  # overlap 10 x 10
    el, = buildings.from_massing([a, b], FlatTerrain(), 150, 2025)
    assert el["id"] == "toronto:massing:2025:3"
    assert tops(el) == [(15.0, 100), (15.0, 200)]
    by_bounds = {Polygon(s["rings"][0]).bounds for s in el["solids"]}
    assert by_bounds == {(10.0, 0.0, 30.0, 10.0), (0.0, 0.0, 10.0, 10.0)}


def test_parts_sharing_a_wall_are_one_building():
    els = buildings.from_massing([P(1, box(0, 0, 10, 10), 9.0), P(2, box(10, 0, 20, 10), 15.0)], FlatTerrain(), 150, 2025)
    el, = els
    assert el["id"] == "toronto:massing:2025:1"
    assert tops(el) == [(9.0, 100), (15.0, 100)]


def test_parts_touching_at_a_corner_stay_apart():
    els = buildings.from_massing([P(1, box(0, 0, 10, 10), 9.0), P(2, box(10, 10, 20, 20), 15.0)], FlatTerrain(), 150, 2025)
    assert sorted(e["id"] for e in els) == ["toronto:massing:2025:1", "toronto:massing:2025:2"]


def test_parts_sharing_less_than_half_a_metre_of_wall_stay_apart():
    els = buildings.from_massing([P(1, box(0, 0, 10, 10), 9.0), P(2, box(10, 9.8, 20, 20), 15.0)], FlatTerrain(), 150, 2025)
    assert len(els) == 2


def test_parts_a_few_centimetres_apart_along_a_wall_are_one_building():
    els = buildings.from_massing([P(1, box(0, 0, 10, 10), 9.0), P(2, box(10.03, 0, 20, 10), 15.0)], FlatTerrain(), 150, 2025)
    assert len(els) == 1


class Slope:
    """Ground rising 0.1 m per metre east."""
    source = "test"

    def min_under(self, poly):
        return poly.bounds[0] * 0.1


def test_each_part_stands_on_its_own_ground_with_one_buried_base():
    parts = [P(1, box(0, 0, 10, 10), 9.0), P(2, box(10, 0, 20, 10), 9.0)]
    el, = buildings.from_massing(parts, Slope(), 150, 2025)
    assert sorted(s["z1"] for s in el["solids"]) == [9.0, 10.0]
    assert [s["z0"] for s in el["solids"]] == [-buildings.SINK_M] * 2


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
    assert len(els) >= 10 and len({e["id"] for e in els}) == len(els)
    assert max(s["z1"] for e in els for s in e["solids"]) > 150  # the towers at Bay and Adelaide
    doc = ctx.new({"centre": {"lat": 43.649667, "lon": -79.380991}, "radius_m": 150}, region="toronto", terrain_source="flat")
    doc["elements"] = els
    assert ctx.validate(ctx.finish(doc)) == []
