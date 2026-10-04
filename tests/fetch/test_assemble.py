import pytest

from ghosttown_fetch import context as ctx
from ghosttown_fetch import request as rq
from ghosttown_fetch.assemble import NothingFetched, assemble
from ghosttown_fetch.frame import Frame
from ghosttown_fetch.net import SourceError
from fakes import FakeNet, router
from osm_samples import body, way
from osm_samples import square as osm_square
from tiff_samples import east_slope_tiff
from toronto_samples import LAT0, LON0, page, point, polygon, square
import photo_samples

OUTLINE = "Building Outline"
CITY = polygon([(-3000, -3000), (3000, -3000), (3000, 3000), (-3000, 3000)], AREA_NAME="Toronto")
SMALL_CITY = polygon([(-500, -500), (500, -500), (500, 500), (-500, 500)], AREA_NAME="Toronto")
FAR = polygon([(5000, 5000), (6000, 5000), (6000, 6000), (5000, 6000)], AREA_NAME="Elsewhere")
TIER = square(0, 0, 10, BUILDINGID=7, OBJECTID=1, DERIVED_HEIGHT=20.0, SUBTYPE_DESC=OUTLINE)
OSM = body(way(1, osm_square(0, 0, 10), {"building": "yes", "height": "20"}))
DOWN = SourceError("City of Toronto answered HTTP 503; try again in a minute.")


def _req(tmp_path, radius=150, **kw):
    return rq.build(centre={"lat": LAT0, "lon": LON0}, radius_m=radius, cache_dir=str(tmp_path / "c"),
                    out_dir=str(tmp_path / "o"), address="Test site", **kw)


def _city(**overrides):
    table = {
        "FeatureServer/40/": page(CITY),
        "BUILDINGID IN": page(TIER),
        "cot_geospatial3/FeatureServer/2/": page(TIER),
        "cot_geospatial3/FeatureServer/3/": page(polygon([(-200, -4), (200, -4), (200, 4), (-200, 4)], OBJECTID=2)),
        "cot_geospatial3/FeatureServer/10/": page(point(5, 30, OBJECTID=9, DERIVED_HEIGHT=10.0)),
        "cot_geospatial27/FeatureServer/36/": page(square(-20, -20, 40, OBJECTID=3, PARCELID=55)),
        "package_show?id=3d-massing": DOWN,  # the massing model is unavailable: these tests cover the fallback
        "FeatureServer/": page(),
    }
    table.update(photo_samples.ANSWERS)
    table.update(overrides)
    return router(table)


def _net(toronto=None, nrcan=None, osm=OSM):
    f = Frame(LAT0, LON0)
    return FakeNet({"toronto": toronto or _city(), "nrcan": nrcan or east_slope_tiff(f, half=200.0), "osm": osm})


def test_a_toronto_site_uses_city_data_on_nrcan_terrain(tmp_path):
    doc = assemble(_req(tmp_path), _net())
    ids = {e["id"] for e in doc["elements"]}
    assert {"toronto:building:7", "tree:toronto:9", "toronto:parcel:55", "ground:road", "ground:ground"} <= ids
    assert doc["region"] == "toronto" and doc["terrain"]["source"] == "nrcan-dtm"
    assert doc["ground_at_centre_m"] is not None and {s["key"] for s in doc["sources"]} == {"toronto", "nrcan"}
    assert ctx.validate(doc) == []


def test_a_site_outside_toronto_uses_osm_and_plain_ground(tmp_path):
    net = _net(toronto=_city(**{"FeatureServer/40/": page(FAR)}))
    doc = assemble(_req(tmp_path), net)
    assert doc["region"] == "world"
    assert {e["id"] for e in doc["elements"]} == {"osm:way:1", "ground:ground"}
    assert [url for url, source, _ in net.calls if source == "toronto"] == [net.calls[0][0]]


def test_far_from_toronto_the_city_is_not_even_asked(tmp_path):
    req = rq.build(centre={"lat": 51.50735, "lon": -0.12776}, radius_m=150, cache_dir=str(tmp_path / "c"),
                   out_dir=str(tmp_path / "o"))
    net = FakeNet({"osm": OSM})
    doc = assemble(req, net)
    assert doc["region"] == "world" and doc["terrain"]["source"] == "flat"
    assert [source for _, source, _ in net.calls] == ["osm"]


def test_a_circle_crossing_the_city_line_gets_a_warning(tmp_path):
    doc = assemble(_req(tmp_path, radius=600), _net(toronto=_city(**{"FeatureServer/40/": page(SMALL_CITY)})))
    assert any(n["code"] == "boundary" and n["level"] == "warn" for n in doc["notes"])


def test_boundary_failure_means_the_world_with_a_warning(tmp_path):
    doc = assemble(_req(tmp_path), _net(toronto=_city(**{"FeatureServer/40/": DOWN})))
    assert doc["region"] == "world" and any(n["code"] == "region" for n in doc["notes"])
    assert "osm:way:1" in {e["id"] for e in doc["elements"]}


def test_terrain_failure_still_builds_on_flat_ground(tmp_path):
    doc = assemble(_req(tmp_path), _net(nrcan=SourceError("Natural Resources Canada answered HTTP 500; try again in a minute.")))
    assert doc["terrain"]["source"] == "flat" and doc["ground_at_centre_m"] is None
    assert any(n["code"] == "terrain" and n["level"] == "warn" for n in doc["notes"])
    assert "toronto:building:7" in {e["id"] for e in doc["elements"]}


def test_one_city_layer_failing_is_a_warning_not_a_failure(tmp_path):
    doc = assemble(_req(tmp_path), _net(toronto=_city(**{"cot_geospatial3/FeatureServer/10/": DOWN})))
    assert any(n["code"] == "city_trees" and n["level"] == "warn" for n in doc["notes"])
    assert "toronto:building:7" in {e["id"] for e in doc["elements"]}


def test_when_every_data_source_fails_nothing_is_fetched(tmp_path):
    everything_down = router({"FeatureServer/40/": page(CITY), "package_show?id=3d-massing": DOWN, "FeatureServer/": DOWN})
    with pytest.raises(NothingFetched, match="503"):
        assemble(_req(tmp_path), _net(toronto=everything_down))


def test_layers_not_asked_for_are_not_fetched(tmp_path):
    net = _net()
    doc = assemble(_req(tmp_path, layers=["buildings"]), net)
    assert {e["kind"] for e in doc["elements"]} == {"building"}
    city_urls = [url for url, source, _ in net.calls if source == "toronto"]
    assert not any("/10/" in u or "/36/" in u or "/FeatureServer/3/" in u for u in city_urls)
    assert all(source != "nrcan" for _, source, _ in net.calls)


def test_progress_is_reported_in_order(tmp_path):
    seen = []
    assemble(_req(tmp_path), _net(), progress=lambda stage, pct: seen.append((stage, pct)))
    assert [p for _, p in seen] == sorted(p for _, p in seen) and seen[-1][0] == "Writing"


def test_custom_overpass_endpoint_is_used_outside_toronto(tmp_path):
    net = _net(toronto=_city(**{"FeatureServer/40/": page(FAR)}))
    assemble(_req(tmp_path, overpass_url="https://example.org/api/interpreter"), net)
    assert any(url == "https://example.org/api/interpreter" for url, source, _ in net.calls if source == "osm")


def _geos_error(*args, **kwargs):
    import shapely

    raise shapely.errors.GEOSException("TopologyException: found non-noded intersection")


def test_a_geometry_error_in_one_layer_is_a_warning_not_a_failed_build(tmp_path, monkeypatch):
    monkeypatch.setattr("ghosttown_fetch.buildings.from_toronto", _geos_error)
    doc = assemble(_req(tmp_path), _net())
    assert any(n["code"] == "city_buildings" and n["level"] == "warn" and "couldn't be built" in n["text"] for n in doc["notes"])
    ids = {e["id"] for e in doc["elements"]}
    assert "tree:toronto:9" in ids and "ground:road" in ids and not any(i.startswith("toronto:building") for i in ids)
    assert ctx.validate(doc) == []


def test_if_the_ground_pieces_cannot_be_laid_out_the_ground_is_plain(tmp_path, monkeypatch):
    from ghosttown_fetch import ground

    real = ground.layout

    def fussy(pieces, radius_m, **kw):
        if pieces:
            _geos_error()
        return real(pieces, radius_m, **kw)

    monkeypatch.setattr("ghosttown_fetch.ground.layout", fussy)
    doc = assemble(_req(tmp_path), _net())
    assert any(n["code"] == "ground" and n["level"] == "warn" for n in doc["notes"])
    ground_ids = {e["id"] for e in doc["elements"] if e["id"].startswith("ground:")}
    assert ground_ids == {"ground:ground"} and "toronto:building:7" in {e["id"] for e in doc["elements"]}


def test_a_geometry_error_while_reading_city_ground_gives_plain_ground(tmp_path, monkeypatch):
    monkeypatch.setattr("ghosttown_fetch.sources.toronto.fetch_ground", _geos_error)
    doc = assemble(_req(tmp_path), _net())
    assert any(n["code"] == "city_ground" and n["level"] == "warn" for n in doc["notes"])
    ids = {e["id"] for e in doc["elements"]}
    assert "toronto:building:7" in ids and {i for i in ids if i.startswith("ground:")} == {"ground:ground"}
    assert ctx.validate(doc) == []


def test_ground_shapes_that_cannot_be_read_are_reported(tmp_path, monkeypatch):
    from ghosttown_fetch.sources import toronto as city

    real = city.fetch_ground

    def lossy(*args, skipped=None, **kw):
        pieces = real(*args, skipped=skipped, **kw)
        skipped.append(("road", 99))
        return pieces

    monkeypatch.setattr("ghosttown_fetch.sources.toronto.fetch_ground", lossy)
    doc = assemble(_req(tmp_path), _net())
    assert any(n["code"] == "city_ground" and n["level"] == "warn" and "1 City ground shape" in n["text"]
               for n in doc["notes"])
    assert "ground:road" in {e["id"] for e in doc["elements"]}


def test_a_geometry_error_reading_the_city_boundary_means_the_world(tmp_path, monkeypatch):
    monkeypatch.setattr("ghosttown_fetch.region.fetch_boundary", _geos_error)
    doc = assemble(_req(tmp_path), _net())
    assert doc["region"] == "world" and any(n["code"] == "region" and n["level"] == "warn" for n in doc["notes"])
    assert "osm:way:1" in {e["id"] for e in doc["elements"]}


def test_the_survey_point_of_the_origin_is_recorded(tmp_path):
    doc = assemble(_req(tmp_path), _net())
    s = doc["survey"]
    assert s["epsg"] == "EPSG:2952" and s["elevation_m"] == round(doc["ground_at_centre_m"], 3)
    assert 300000 < s["easting_m"] < 330000 and 4.82e6 < s["northing_m"] < 4.85e6
    world = assemble(_req(tmp_path), _net(toronto=_city(**{"FeatureServer/40/": page(FAR)})))
    assert world["survey"]["epsg"] == "EPSG:32617" and ctx.validate(world) == []
