import json

import pytest

from ghosttown_fetch.net import SourceError
from ghosttown_fetch.sources import arcgis
from fakes import FakeNet, form
from toronto_samples import page, point, square


def city_feature(n):
    """A point as the City's server sends one: its OBJECTID is the feature's id as well as a property."""
    return {**point(n, 0, OBJECTID=n), "id": n}


def pages_before_it_filters(rows, size):
    """A FakeNet answer that pages the way the City of Toronto's server does (seen 2026-11-05): `resultOffset` and the
    page size count rows the distance test hasn't run on yet, so a page holds only its rows in the circle and may be
    short, and the answer says there is more while rows remain past it. `rows` are (feature, in the circle) in
    OBJECTID order."""
    def answer(url, data):
        start = int(form(data)["resultOffset"])
        return page(*[feature for feature, inside in rows[start:start + size] if inside], more=start + size < len(rows))
    return answer


def test_radius_params_ask_for_geojson_in_wgs84_around_the_centre():
    p = arcgis.radius_params(43.649667, -79.380991, 300, out_fields="OBJECTID", where="FEATURE_TYPE = 'COMMON'")
    assert p["geometry"] == "-79.3809910,43.6496670" and p["distance"] == "300" and p["inSR"] == "4326"
    assert p["outSR"] == "4326" and p["f"] == "geojson" and p["orderByFields"] == "OBJECTID"
    assert p["where"] == "FEATURE_TYPE = 'COMMON'" and p["outFields"] == "OBJECTID"
    assert p["units"] == "esriSRUnit_Meter" and p["spatialRel"] == "esriSpatialRelIntersects"


def test_query_follows_pages_until_the_server_says_done():
    pages = [page(square(0, 0, 5, OBJECTID=1), square(10, 0, 5, OBJECTID=2), more=True), page(square(20, 0, 5, OBJECTID=3))]
    net = FakeNet({"toronto": lambda url, data: pages.pop(0)})
    feats = arcgis.query(net, "cot_geospatial3", 2, arcgis.radius_params(43.65, -79.38, 300))
    assert [f["properties"]["OBJECTID"] for f in feats] == [1, 2, 3]
    assert [form(d)["resultOffset"] for _, _, d in net.calls] == ["0", "2"]
    assert net.calls[0][0] == arcgis.BASE + "/cot_geospatial3/FeatureServer/2/query"
    assert net.calls[0][1] == "toronto"


def test_a_server_that_pages_before_it_filters_gives_each_feature_once():
    # Rows 1 to 8, with 3 and 6 outside the circle, in pages of 4 rows. The first page is 1, 2, 4 and says there is
    # more; asked from offset 3 the server starts again at row 4, so 4 comes back, and later 7.
    rows = [(city_feature(n), n not in (3, 6)) for n in range(1, 9)]
    net = FakeNet({"toronto": pages_before_it_filters(rows, 4)})
    params = arcgis.radius_params(43.65, -79.38, 1000, out_fields="OBJECTID")
    feats = arcgis.query(net, "cot_geospatial27", 36, params)
    assert [f["id"] for f in feats] == [1, 2, 4, 5, 7, 8]
    # asked for as ever, the offset moving on by the features received: the answers an earlier version stored still serve
    assert [form(d) for _, _, d in net.calls] == [{**params, "resultOffset": offset} for offset in ("0", "3", "6")]


def test_a_page_of_nothing_but_repeats_does_not_end_paging():
    # Rows 1 to 8 with 3, 5, 6 and 7 outside, in pages of 4 rows: 1, 2, 4, then from offset 3 only 4 again, then 8.
    rows = [(city_feature(n), n not in (3, 5, 6, 7)) for n in range(1, 9)]
    net = FakeNet({"toronto": pages_before_it_filters(rows, 4)})
    feats = arcgis.query(net, "cot_geospatial27", 36, arcgis.radius_params(43.65, -79.38, 1000, out_fields="OBJECTID"))
    assert [f["id"] for f in feats] == [1, 2, 4, 8]
    assert [form(d)["resultOffset"] for _, _, d in net.calls] == ["0", "3", "4"]


def test_repeats_without_an_id_are_told_by_everything_else_they_say():
    rows = [(point(n, 0, OBJECTID=n), n not in (3, 6)) for n in range(1, 9)]   # GeoJSON features need not carry an "id"
    net = FakeNet({"toronto": pages_before_it_filters(rows, 4)})
    feats = arcgis.query(net, "cot_geospatial27", 36, arcgis.radius_params(43.65, -79.38, 1000, out_fields="OBJECTID"))
    assert [f["properties"]["OBJECTID"] for f in feats] == [1, 2, 4, 5, 7, 8]


def test_an_empty_page_ends_paging_even_if_more_is_flagged():
    net = FakeNet({"toronto": lambda url, data: page(more=True)})
    assert arcgis.query(net, "cot_geospatial3", 2, {}) == [] and len(net.calls) == 1


def test_an_error_answer_is_a_source_error():
    net = FakeNet({"toronto": json.dumps({"error": {"code": 400, "message": "Invalid query"}}).encode()})
    with pytest.raises(SourceError, match="refused"):
        arcgis.query(net, "cot_geospatial3", 2, {})


def test_non_json_is_a_source_error():
    with pytest.raises(SourceError, match="isn't JSON"):
        arcgis.query(FakeNet({"toronto": b"<html>busy</html>"}), "cot_geospatial3", 2, {})


def test_runaway_paging_stops():
    net = FakeNet({"toronto": lambda url, data: page(square(0, 0, 5, OBJECTID=1), more=True)})
    with pytest.raises(SourceError, match="too many"):
        arcgis.query(net, "cot_geospatial3", 2, {})
    assert len(net.calls) == arcgis.MAX_PAGES


def test_query_hands_its_age_to_the_cache():
    net = FakeNet({"toronto": lambda url, data: page(square(0, 0, 5, OBJECTID=1))})
    arcgis.query(net, "cot_geospatial11", 60, arcgis.radius_params(43.65, -79.38, 150), max_age_days=1)
    arcgis.query(net, "cot_geospatial3", 2, arcgis.radius_params(43.65, -79.38, 150))
    assert net.ages == [1, None]
