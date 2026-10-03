import shapely

from ghosttown_fetch.frame import Frame
from ghosttown_fetch.sources import toronto
from fakes import FakeNet, form, router
from toronto_samples import LAT0, LON0, line, page, polygon, square

F = Frame(LAT0, LON0)
TABLE = {
    "cot_geospatial3/FeatureServer/3/": page(polygon([(-100, -4), (100, -4), (100, 4), (-100, 4)], OBJECTID=1)),
    "cot_geospatial3/FeatureServer/6/": page(square(20, 10, 5, OBJECTID=2)),
    "cot_geospatial3/FeatureServer/13/": page(),
    "cot_geospatial3/FeatureServer/14/": page(line([(0, 50), (100, 50)], OBJECTID=3)),
    "cot_geospatial3/FeatureServer/16/": page(),
    "cot_geospatial27/FeatureServer/3/": page(square(-50, -50, 10, OBJECTID=4)),
    "cot_geospatial3/FeatureServer/9/": page(square(-80, -50, 10, OBJECTID=5)),
}


def test_city_layers_map_to_kinds_and_rail_becomes_a_surface():
    pieces = toronto.fetch_ground(FakeNet({"toronto": router(TABLE)}), LAT0, LON0, 200, F)
    assert set(pieces) == {"road", "sidewalk", "rail", "green"}
    assert shapely.union_all(pieces["rail"]).area == __import__("pytest").approx(100 * 3.5, rel=0.01)
    assert len(pieces["green"]) == 2
    assert shapely.union_all(pieces["road"]).area == __import__("pytest").approx(200 * 8, rel=0.01)


def test_streetcar_tracks_are_left_out():
    net = FakeNet({"toronto": router(TABLE)})
    toronto.fetch_ground(net, LAT0, LON0, 200, F)
    rail = [form(d) for url, _, d in net.calls if "/cot_geospatial3/FeatureServer/14/" in url]
    assert rail and rail[0]["where"] == "SUBTYPE_DESC = 'Rail Track'"


def test_only_the_requested_kinds_are_fetched():
    net = FakeNet({"toronto": router(TABLE)})
    pieces = toronto.fetch_ground(net, LAT0, LON0, 200, F, kinds=["road"])
    assert set(pieces) == {"road"} and len(net.calls) == 1


def test_one_unreadable_ground_shape_is_left_out_not_fatal(monkeypatch):
    real = toronto.polygons

    def fussy(geom):
        if abs(geom.area - 25.0) < 0.5:  # the sidewalk square
            raise shapely.errors.GEOSException("TopologyException: test")
        return real(geom)

    monkeypatch.setattr(toronto, "polygons", fussy)
    skipped = []
    pieces = toronto.fetch_ground(FakeNet({"toronto": router(TABLE)}), LAT0, LON0, 200, F, skipped=skipped)
    assert "sidewalk" not in pieces and {"road", "rail", "green"} <= set(pieces)
    assert skipped == [("sidewalk", 2)]
