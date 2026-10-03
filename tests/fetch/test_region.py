import pytest

from ghosttown_fetch import region
from ghosttown_fetch.frame import Frame
from ghosttown_fetch.net import SourceError
from fakes import FakeNet, form
from toronto_samples import LAT0, LON0, page, polygon

WEST = polygon([(-3000, -3000), (0, -3000), (0, 3000), (-3000, 3000)], AREA_NAME="West")
EAST = polygon([(0, -3000), (3000, -3000), (3000, 3000), (0, 3000)], AREA_NAME="East")
AWAY = polygon([(1000, 1000), (2000, 1000), (2000, 2000), (1000, 2000)], AREA_NAME="Away")
F = Frame(LAT0, LON0)


def _boundary(*features):
    return region.fetch_boundary(FakeNet({"toronto": page(*features)}))


def test_parts_are_unioned_into_one_city():
    assert region.classify(_boundary(WEST, EAST), F, 300) == ("toronto", False)


def test_a_circle_reaching_over_the_line_is_flagged():
    assert region.classify(_boundary(WEST, EAST), F, 3500) == ("toronto", True)


def test_a_centre_outside_is_the_world():
    boundary = _boundary(AWAY)
    assert region.classify(boundary, F, 300) == ("world", False)
    assert region.classify(boundary, F, 1500) == ("world", True)


def test_the_query_asks_for_the_simplified_city_outline():
    net = FakeNet({"toronto": page(WEST)})
    region.fetch_boundary(net)
    url, source, data = net.calls[0]
    assert url.endswith("/cot_geospatial27/FeatureServer/40/query") and source == "toronto"
    assert form(data)["maxAllowableOffset"] == "0.0002" and form(data)["outSR"] == "4326"


def test_an_empty_boundary_is_a_source_error():
    with pytest.raises(SourceError, match="boundary"):
        _boundary()


def test_near_toronto():
    assert region.near_toronto(43.649667, -79.380991)
    assert not region.near_toronto(51.50735, -0.12776)
    assert not region.near_toronto(45.5017, -73.5673)


def test_an_empty_boundary_answer_is_not_cached(tmp_path):
    from ghosttown_fetch.net import Net

    answers = [(200, page()), (200, page(WEST, EAST))]
    net = Net(str(tmp_path), transport=lambda url, data, headers, timeout: answers.pop(0))
    with pytest.raises(SourceError, match="boundary"):
        region.fetch_boundary(net)
    assert region.classify(region.fetch_boundary(net), F, 300) == ("toronto", False)
