import gzip
import json
import urllib.parse
from pathlib import Path

from ghosttown_fetch import buildings
from ghosttown_fetch import context as ctx
from ghosttown_fetch import request as rq
from ghosttown_fetch.frame import Frame
from ghosttown_fetch.sources import toronto
from ghosttown_fetch.terrain import FlatTerrain
from fakes import FakeNet, router
from terrains import Ramp
from toronto_samples import LAT0, LON0, page, square

F = Frame(LAT0, LON0)
FIX = Path(__file__).parent / "fixtures"
OUTLINE = "Building Outline"


def _features(*features):
    return json.loads(page(*features))["features"]


def _valid(elements):
    req = rq.build(centre={"lat": LAT0, "lon": LON0}, radius_m=150, cache_dir="c", out_dir="o")
    doc = ctx.new(req, region="toronto", terrain_source="flat")
    doc["elements"] = elements
    return ctx.validate(ctx.finish(doc))


def test_tiers_with_one_building_id_become_one_building():
    el, = buildings.from_toronto(_features(
        square(0, 0, 20, BUILDINGID=7, DERIVED_HEIGHT=12.0, SUBTYPE_DESC=OUTLINE, OBJECTID=1),
        square(5, 5, 10, BUILDINGID=7, DERIVED_HEIGHT=60.0, SUBTYPE_DESC=OUTLINE, OBJECTID=2),
    ), F, FlatTerrain())
    assert el["id"] == "toronto:building:7" and el["kind"] == "building"
    assert sorted(s["z1"] for s in el["solids"]) == [12.0, 60.0]
    assert {s["z0"] for s in el["solids"]} == {-0.3}
    assert {s["height_source"] for s in el["solids"]} == {"toronto_derived"}


def test_tiers_share_the_lowest_ground_under_the_whole_building():
    el, = buildings.from_toronto(_features(
        square(20, 0, 10, BUILDINGID=7, DERIVED_HEIGHT=10.0, SUBTYPE_DESC=OUTLINE, OBJECTID=1),
        square(40, 0, 10, BUILDINGID=7, DERIVED_HEIGHT=30.0, SUBTYPE_DESC=OUTLINE, OBJECTID=2),
    ), F, Ramp())
    assert {s["z0"] for s in el["solids"]} == {1.7}
    assert sorted(s["z1"] for s in el["solids"]) == [12.0, 32.0]


def test_a_missing_height_is_guessed():
    el, = buildings.from_toronto(_features(
        square(0, 0, 10, BUILDINGID=7, DERIVED_HEIGHT=None, SUBTYPE_DESC=OUTLINE, OBJECTID=1)), F, FlatTerrain())
    assert el["kind"] == "building_guessed" and el["solids"][0]["z1"] == 9.0
    assert el["solids"][0]["height_source"] == "guessed"


def test_miscellaneous_structures_are_skipped():
    assert buildings.from_toronto(_features(
        square(0, 0, 10, BUILDINGID=7, DERIVED_HEIGHT=5.0, SUBTYPE_DESC="Miscellaneous Structure", OBJECTID=1)),
        F, FlatTerrain()) == []


def test_buildings_without_an_id_stand_alone():
    els = buildings.from_toronto(_features(
        square(0, 0, 10, BUILDINGID=None, DERIVED_HEIGHT=5.0, SUBTYPE_DESC=OUTLINE, OBJECTID=5),
        square(20, 0, 10, BUILDINGID=None, DERIVED_HEIGHT=6.0, SUBTYPE_DESC=OUTLINE, OBJECTID=6)), F, FlatTerrain())
    assert sorted(e["id"] for e in els) == ["toronto:building:obj5", "toronto:building:obj6"]
    assert _valid(els) == []


def test_fetch_asks_again_for_tiers_outside_the_circle():
    near = page(square(0, 0, 10, BUILDINGID=7, OBJECTID=1, DERIVED_HEIGHT=5.0, SUBTYPE_DESC=OUTLINE),
                square(50, 0, 10, BUILDINGID=8, OBJECTID=2, DERIVED_HEIGHT=5.0, SUBTYPE_DESC=OUTLINE))
    whole = page(square(0, 0, 10, BUILDINGID=7, OBJECTID=1, DERIVED_HEIGHT=5.0, SUBTYPE_DESC=OUTLINE),
                 square(200, 0, 10, BUILDINGID=7, OBJECTID=3, DERIVED_HEIGHT=9.0, SUBTYPE_DESC=OUTLINE))
    net = FakeNet({"toronto": router({"BUILDINGID IN": whole, "geometry=": near})})
    feats = toronto.fetch_buildings(net, LAT0, LON0, 100)
    assert sorted(f["properties"]["OBJECTID"] for f in feats) == [1, 2, 3]
    forms = [urllib.parse.unquote_plus(d.decode()) for _, _, d in net.calls]
    assert "SUBTYPE_DESC = 'Building Outline'" in forms[0] and "geometry=" in forms[0]
    assert "BUILDINGID IN (7,8) AND SUBTYPE_DESC = 'Building Outline'" in forms[1]
    assert "distance=350" in forms[1]  # the same ids far away (the City reuses some) stay out
    assert all("/cot_geospatial3/FeatureServer/2/query" in url for url, _, _ in net.calls)


def test_recorded_bay_street_city_buildings_are_valid():
    feats = json.loads(gzip.decompress((FIX / "bay" / "toronto_buildings.json.gz").read_bytes()))["features"]
    els = buildings.from_toronto(feats, Frame(43.649667, -79.380991), FlatTerrain())
    assert len(els) >= 10 and sum(len(e["solids"]) for e in els) >= 100 and _valid(els) == []  # complexes share one id
    assert sum(1 for e in els if e["kind"] == "building") > 0.9 * len(els)


def _area(solid):
    from shapely.geometry import Polygon

    return Polygon(solid["rings"][0], solid["rings"][1:]).area


def test_an_outline_drawn_around_its_own_roof_levels_does_not_become_a_monolith():
    # The City draws the whole building at its tallest height *and* each roof level inside it.
    el, = buildings.from_toronto(_features(
        square(-0.2, -0.2, 40.4, BUILDINGID=7, DERIVED_HEIGHT=200.0, SUBTYPE_DESC=OUTLINE, OBJECTID=1),
        square(0, 0, 40, BUILDINGID=7, DERIVED_HEIGHT=20.0, SUBTYPE_DESC=OUTLINE, OBJECTID=2),
        square(15, 15, 10, BUILDINGID=7, DERIVED_HEIGHT=200.0, SUBTYPE_DESC=OUTLINE, OBJECTID=3),
    ), F, FlatTerrain())
    tall = [s for s in el["solids"] if s["z1"] > 100]
    low = [s for s in el["solids"] if s["z1"] < 100]
    assert len(tall) == 1 and abs(_area(tall[0]) - 100) < 1
    assert abs(sum(_area(s) for s in low) - 1500) < 2 and {s["z1"] for s in low} == {20.0}


def test_a_complex_outline_over_other_buildings_gives_way_to_them():
    els = buildings.from_toronto(_features(
        square(-0.3, -0.3, 20.6, BUILDINGID=9, DERIVED_HEIGHT=300.0, SUBTYPE_DESC=OUTLINE, OBJECTID=1),
        square(0, 0, 20, BUILDINGID=7, DERIVED_HEIGHT=30.0, SUBTYPE_DESC=OUTLINE, OBJECTID=2),
    ), F, FlatTerrain())
    assert [e["id"] for e in els] == ["toronto:building:7"] and els[0]["solids"][0]["z1"] == 30.0


def test_duplicate_outlines_become_one_solid():
    el, = buildings.from_toronto(_features(
        square(0, 0, 20, BUILDINGID=7, DERIVED_HEIGHT=30.0, SUBTYPE_DESC=OUTLINE, OBJECTID=1),
        square(0, 0, 20, BUILDINGID=7, DERIVED_HEIGHT=30.0, SUBTYPE_DESC=OUTLINE, OBJECTID=2),
    ), F, FlatTerrain())
    assert len(el["solids"]) == 1


def test_neighbours_that_only_touch_keep_their_exact_shapes():
    el, = buildings.from_toronto(_features(
        square(0, 0, 10, BUILDINGID=7, DERIVED_HEIGHT=30.0, SUBTYPE_DESC=OUTLINE, OBJECTID=1),
        square(10, 0, 5, BUILDINGID=7, DERIVED_HEIGHT=12.0, SUBTYPE_DESC=OUTLINE, OBJECTID=2),
    ), F, FlatTerrain())
    assert sorted(round(_area(s)) for s in el["solids"]) == [25, 100]


def test_recorded_bay_street_has_no_overlapping_tiers():
    import shapely
    from shapely.geometry import Polygon

    feats = json.loads(gzip.decompress((FIX / "bay" / "toronto_buildings.json.gz").read_bytes()))["features"]
    solids = [s for e in buildings.from_toronto(feats, Frame(43.649667, -79.380991), FlatTerrain()) for s in e["solids"]]
    polys = [Polygon(s["rings"][0], s["rings"][1:]) for s in solids]
    assert sum(p.area for p in polys) == __import__("pytest").approx(shapely.union_all(polys).area, rel=0.01)
    assert max(p.area for p, s in zip(polys, solids) if s["z1"] > 250) < 6000  # towers, not whole blocks
