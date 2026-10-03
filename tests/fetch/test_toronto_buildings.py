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
from toronto_samples import LAT0, LON0, page, polygon, square

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


def test_fetch_asks_once_for_every_outline_around_the_site():
    net = FakeNet({"toronto": page(square(0, 0, 10, BUILDINGID=7, OBJECTID=1, DERIVED_HEIGHT=5.0, SUBTYPE_DESC=OUTLINE))})
    feats = toronto.fetch_buildings(net, LAT0, LON0, 100)
    assert len(feats) == 1 and len(net.calls) == 1
    sent = urllib.parse.unquote_plus(net.calls[0][2].decode())
    assert "distance=350" in sent and "SUBTYPE_DESC = 'Building Outline'" in sent and "BUILDINGID IN" not in sent
    assert net.calls[0][0].endswith("/cot_geospatial3/FeatureServer/2/query")


def test_buildings_touching_the_circle_come_in_whole_and_the_rest_stay_out():
    els = buildings.from_toronto(_features(
        square(0, 0, 10, BUILDINGID=7, DERIVED_HEIGHT=20.0, SUBTYPE_DESC=OUTLINE, OBJECTID=1),
        square(200, 0, 10, BUILDINGID=7, DERIVED_HEIGHT=9.0, SUBTYPE_DESC=OUTLINE, OBJECTID=2),
        square(180, 50, 10, BUILDINGID=8, DERIVED_HEIGHT=30.0, SUBTYPE_DESC=OUTLINE, OBJECTID=3),
    ), F, FlatTerrain(), 100)
    assert [e["id"] for e in els] == ["toronto:building:7"] and len(els[0]["solids"]) == 2


def test_a_container_outline_at_the_circle_edge_does_not_bring_the_monolith_back():
    # The container (id 9) touches the circle; the roofs under its far end belong to a building that doesn't.
    els = buildings.from_toronto(_features(
        polygon([(-10, 0), (200, 0), (200, 40), (-10, 40)], BUILDINGID=9, DERIVED_HEIGHT=200.0, SUBTYPE_DESC=OUTLINE, OBJECTID=1),
        polygon([(-10, 0), (60, 0), (60, 40), (-10, 40)], BUILDINGID=7, DERIVED_HEIGHT=20.0, SUBTYPE_DESC=OUTLINE, OBJECTID=2),
        polygon([(60, 0), (200, 0), (200, 40), (60, 40)], BUILDINGID=8, DERIVED_HEIGHT=30.0, SUBTYPE_DESC=OUTLINE, OBJECTID=3),
    ), F, FlatTerrain(), 50)
    assert [e["id"] for e in els] == ["toronto:building:7"]
    assert max(s["z1"] for e in els for s in e["solids"]) == 20.0


def test_a_gap_left_in_a_container_outline_takes_its_neighbours_height():
    # Roof levels cover 96 % of the whole-building outline; the 15 x 10 m gap is not a 200 m tower.
    el, = buildings.from_toronto(_features(
        polygon([(0, 0), (100, 0), (100, 40), (0, 40)], BUILDINGID=7, DERIVED_HEIGHT=200.0, SUBTYPE_DESC=OUTLINE, OBJECTID=1),
        polygon([(0, 0), (45, 0), (45, 40), (0, 40)], BUILDINGID=7, DERIVED_HEIGHT=48.0, SUBTYPE_DESC=OUTLINE, OBJECTID=2),
        polygon([(60, 0), (100, 0), (100, 40), (60, 40)], BUILDINGID=7, DERIVED_HEIGHT=200.0, SUBTYPE_DESC=OUTLINE, OBJECTID=3),
        polygon([(45, 0), (60, 0), (60, 30), (45, 30)], BUILDINGID=7, DERIVED_HEIGHT=50.0, SUBTYPE_DESC=OUTLINE, OBJECTID=4),
    ), F, FlatTerrain())
    gap, = [s for s in el["solids"] if abs(_area(s) - 150) < 1]
    assert gap["z1"] == 50.0 and gap["height_source"] == "toronto_inferred"
    assert sorted(s["z1"] for s in el["solids"]) == [48.0, 50.0, 50.0, 200.0]


def test_a_mostly_uncovered_outline_keeps_its_own_height():
    el, = buildings.from_toronto(_features(
        square(0, 0, 40, BUILDINGID=7, DERIVED_HEIGHT=100.0, SUBTYPE_DESC=OUTLINE, OBJECTID=1),
        square(0, 0, 10, BUILDINGID=7, DERIVED_HEIGHT=12.0, SUBTYPE_DESC=OUTLINE, OBJECTID=2),
    ), F, FlatTerrain())
    big, = [s for s in el["solids"] if _area(s) > 1000]
    assert big["z1"] == 100.0 and big["height_source"] == "toronto_derived"


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


def _recorded_solids():
    from shapely.geometry import Polygon

    feats = json.loads(gzip.decompress((FIX / "bay" / "toronto_buildings.json.gz").read_bytes()))["features"]
    solids = [s for e in buildings.from_toronto(feats, Frame(43.649667, -79.380991), FlatTerrain()) for s in e["solids"]]
    return solids, [Polygon(s["rings"][0], s["rings"][1:]) for s in solids]


def test_recorded_bay_street_solids_do_not_overlap():
    import shapely

    solids, polys = _recorded_solids()
    tree = shapely.STRtree(polys)
    worst = 0.0
    for i, j in zip(*tree.query(polys, predicate="intersects")):
        if i < j:
            worst = max(worst, polys[i].intersection(polys[j]).area)
    assert worst < 0.05
    assert max(p.area for p, s in zip(polys, solids) if s["z1"] > 250) < 6000  # towers, not whole blocks


def test_recorded_bay_street_gaps_never_rise_above_their_neighbours():
    import shapely

    solids, polys = _recorded_solids()
    inferred = [i for i, s in enumerate(solids) if s["height_source"] == "toronto_inferred"]
    assert inferred
    tree = shapely.STRtree(polys)
    for i in inferred:
        near = [j for j in tree.query(polys[i].buffer(0.1), predicate="intersects") if j != i]
        assert near and solids[i]["z1"] <= max(solids[j]["z1"] for j in near) + 1e-6


def test_real_outlines_that_once_broke_the_overlay_resolve_cleanly():
    # OBJECTID 306525 and its two neighbours (south of King St): opening the cut-back outline with
    # mitre joins gave GEOS an invalid polygon, and the whole 1000 m build failed.
    from shapely.geometry import Polygon

    raw = gzip.decompress((FIX / "bay" / "toronto_buildings_overlay_trouble.json.gz").read_bytes())
    els = buildings.from_toronto(json.loads(raw)["features"], Frame(43.649667039, -79.380991173), FlatTerrain())
    assert els and _valid(els) == []
    polys = [Polygon(s["rings"][0], s["rings"][1:]) for e in els for s in e["solids"]]
    assert all(p.is_valid for p in polys)
    assert max((a.intersection(b).area for i, a in enumerate(polys) for b in polys[i + 1:]), default=0.0) < 0.05


def test_an_overlay_failure_on_one_outline_does_not_fail_the_build(monkeypatch):
    import shapely

    def broken(*args, **kwargs):
        raise shapely.errors.GEOSException("TopologyException: test")

    monkeypatch.setattr(buildings, "_cut_back", broken)
    els = buildings.from_toronto(_features(
        square(0, 0, 40, BUILDINGID=7, DERIVED_HEIGHT=100.0, SUBTYPE_DESC=OUTLINE, OBJECTID=1),
        square(0, 0, 10, BUILDINGID=7, DERIVED_HEIGHT=12.0, SUBTYPE_DESC=OUTLINE, OBJECTID=2),
    ), F, FlatTerrain())
    assert len(els) == 1 and len(els[0]["solids"]) == 2  # the outline is kept uncut rather than lost


def test_a_courtyard_a_hair_from_the_wall_still_gives_valid_footprints():
    # BUILDINGID 458241 (1000 m from Bay St): a ring less than 1 mm from the outer wall crossed it once
    # the coordinates were rounded to millimetres.
    from shapely.geometry import Polygon

    raw = gzip.decompress((FIX / "bay" / "toronto_buildings_near_touching_rings.json.gz").read_bytes())
    els = buildings.from_toronto(json.loads(raw)["features"], Frame(43.649667039, -79.380991173), FlatTerrain())
    polys = [Polygon(s["rings"][0], s["rings"][1:]) for e in els for s in e["solids"]]
    assert polys and all(p.is_valid for p in polys)
