import json

import pytest

from ghosttown_fetch.net import SourceError
from ghosttown_fetch.sources import arcgis
from fakes import FakeNet, form
from toronto_samples import page, square


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
