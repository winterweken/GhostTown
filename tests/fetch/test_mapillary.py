import json
import math

import pytest

from ghosttown_fetch.frame import Frame
from ghosttown_fetch.net import Net, SourceError
from ghosttown_fetch.sources import mapillary as m
from fakes import FakeNet, router

F = Frame(43.65, -79.38)
TOKEN = "MLY|secret"


def test_tiles_cover_the_circle_and_stay_bounded():
    assert len(m.tiles(F, 100)) == 4
    assert len(m.tiles(F, 150)) == 9
    assert len(m.tiles(F, 1000)) <= 400


def test_tiles_coverage_and_coordinates():
    """Tiles cover points in the circle, boxes have correct coordinate order, and clipping reduces count."""
    radius_m = 120  # Not a multiple of 50m to exercise the clip
    tiles_list = m.tiles(F, radius_m)

    # Every box has lon0 < lon1 and lat0 < lat1
    for lon0, lat0, lon1, lat1 in tiles_list:
        assert lon0 < lon1, f"Box {(lon0, lat0, lon1, lat1)} has lon0 >= lon1"
        assert lat0 < lat1, f"Box {(lon0, lat0, lon1, lat1)} has lat0 >= lat1"

    # Site center is in some box
    center_lon, center_lat = F.to_lonlat(0, 0)
    center_in_box = any(lon0 <= center_lon <= lon1 and lat0 <= center_lat <= lat1
                        for lon0, lat0, lon1, lat1 in tiles_list)
    assert center_in_box, f"Center {(center_lon, center_lat)} not in any tile"

    # Points on the circle edge and inside fall in some box
    for angle_deg in [0, 45, 90, 135, 180, 225, 270, 315]:
        angle_rad = math.radians(angle_deg)
        for r in [0, radius_m * 0.5, radius_m * 0.99]:  # Center, halfway, near edge
            x = r * math.cos(angle_rad)
            y = r * math.sin(angle_rad)
            p_lon, p_lat = F.to_lonlat(x, y)
            point_in_box = any(lon0 <= p_lon <= lon1 and lat0 <= p_lat <= lat1
                               for lon0, lat0, lon1, lat1 in tiles_list)
            assert point_in_box, f"Point {(p_lon, p_lat)} at radius {r}m angle {angle_deg}° not in any tile"

    # Clipping reduces count from unclipped square
    assert len(m.tiles(F, 1000)) < 400, "1000m radius should have <400 tiles due to circle clip"
    assert len(m.tiles(F, 1000)) == 352, "1000m radius should clip to exactly 352 tiles"


def test_list_url_has_the_box_and_fields_but_no_token():
    url = m.list_url((-79.381, 43.649, -79.379, 43.651))
    assert url.startswith("https://graph.mapillary.com/images?") and "bbox=-79.3810000,43.6490000" in url
    assert "computed_rotation" in url and "MLY" not in url


def test_list_images_deduplicates_and_sends_the_token_in_a_header():
    body = json.dumps({"data": [{"id": "1"}, {"id": "2"}]}).encode()
    net = FakeNet({"mapillary": router({"/images?": body})})
    images, failed = m.list_images(net, F, 100, TOKEN)
    assert sorted(im["id"] for im in images) == ["1", "2"] and failed == 0
    assert net.headers and all(h["Authorization"] == "OAuth " + TOKEN for h in net.headers)
    assert all(TOKEN not in url for url, _source, _data in net.calls)


def test_a_failed_tile_is_counted_not_fatal():
    calls = []

    def answer(url, data):
        calls.append(url)
        if len(calls) == 1:
            return SourceError("Mapillary answered HTTP 500; try again in a minute.", status=500)
        return json.dumps({"data": [{"id": "1"}]}).encode()

    images, failed = m.list_images(FakeNet({"mapillary": answer}), F, 100, TOKEN, workers=1)
    assert failed == 1 and [im["id"] for im in images] == ["1"]


def test_a_rejected_token_stops_everything():
    net = FakeNet({"mapillary": SourceError("Mapillary answered HTTP 401; try again in a minute.", status=401)})
    with pytest.raises(m.TokenRejected, match="refused the token"):
        m.list_images(net, F, 100, TOKEN)


def test_a_403_status_is_token_rejected():
    """403 Forbidden also indicates a rejected token."""
    net = FakeNet({"mapillary": SourceError("Mapillary answered HTTP 403; try again in a minute.", status=403)})
    with pytest.raises(m.TokenRejected, match="refused the token"):
        m.list_images(net, F, 100, TOKEN)


def test_an_unreadable_listing_is_a_source_error():
    net = FakeNet({"mapillary": b"<html>busy</html>"})
    images, failed = m.list_images(net, F, 100, TOKEN, workers=1)
    assert images == [] and failed == 4


class Transport:
    """Answers by URL substring, for a real Net."""

    def __init__(self, table):
        self.table, self.calls = table, []

    def __call__(self, url, data, headers, timeout):
        self.calls.append((url, headers))
        for key, body in self.table.items():
            if key in url:
                return 200, body
        return 404, b""


JPEG = b"\xff\xd8\xff" + b"x" * 200


def test_photos_are_cached_by_image_id_and_signed_links_are_not_stored(tmp_path):
    link = json.dumps({"id": "77", "thumb_2048_url": "https://cdn.example/77.jpg?sig=a"}).encode()
    t = Transport({"/77?fields=thumb_2048_url": link, "cdn.example/77.jpg": JPEG})
    net = Net(str(tmp_path), transport=t)
    assert m.photo(net, "77", TOKEN) == JPEG
    assert m.photo(net, "77", TOKEN) == JPEG
    assert len(t.calls) == 2                       # one link lookup, one download, then the cache
    assert not any(b"sig=a" in p.read_bytes() for p in (tmp_path / "mapillary").iterdir())
    assert "Authorization" not in t.calls[1][1]    # the image server never sees the token
    assert net.cached("mapillary", "photo:77:2048") == JPEG  # cache key does not include token


def test_detections_keep_only_usable_entries():
    body = json.dumps({"data": [{"value": "nature--sky", "geometry": "AAAA"}, {"value": "x"}]}).encode()
    net = FakeNet({"mapillary": router({"/detections": body})})
    assert m.detections(net, "77", TOKEN) == [{"value": "nature--sky", "geometry": "AAAA"}]


def test_fetch_many_collects_failures_per_id():
    def fn(i):
        if i == "b":
            raise SourceError("nope")
        return i.upper()

    out = m.fetch_many(fn, ["a", "b"])
    assert out["a"] == "A" and isinstance(out["b"], SourceError)


def test_fetch_many_raises_token_rejected_immediately():
    """A TokenRejected from any id propagates immediately, not collected per-id."""
    def fn(i):
        if i == "b":
            raise m.TokenRejected("token bad")
        return i.upper()

    with pytest.raises(m.TokenRejected, match="token bad"):
        m.fetch_many(fn, ["a", "b"])


THROTTLE_BODY = json.dumps({"error": {"message": "(#4) Application request limit reached", "type": "OAuthException",
                                      "code": 4, "error_subcode": 1349210}}).encode()
REFUSED_BODY = json.dumps({"error": {"message": "Invalid OAuth access token.", "type": "OAuthException",
                                     "code": 190}}).encode()
AWAY = SourceError("Mapillary couldn't be reached (timed out); try again in a minute.")   # no HTTP status


def _forbidden(body):
    return SourceError("Mapillary answered HTTP 403; try again in a minute.", status=403, body=body)


def test_a_request_turned_away_for_the_request_limit_is_asked_once_more_after_a_pause():
    answers = iter([_forbidden(THROTTLE_BODY), json.dumps({"data": []}).encode()])
    net = FakeNet({"mapillary": lambda url, data: next(answers)})
    assert m.detections(net, "77", TOKEN) == [] and net.slept == [30] and len(net.calls) == 2


def test_a_request_turned_away_twice_says_so_in_plain_words():
    net = FakeNet({"mapillary": _forbidden(THROTTLE_BODY)})
    with pytest.raises(m.Throttled) as e:
        m.detections(net, "77", TOKEN)
    assert str(e.value) == "Mapillary's request limit was reached; try again in a minute."
    assert not isinstance(e.value, m.TokenRejected) and "Application" not in str(e.value) and len(net.calls) == 2


def test_a_throttled_tile_is_a_failed_tile_not_a_refused_token():
    calls = []

    def answer(url, data):
        calls.append(url)
        return _forbidden(THROTTLE_BODY) if len(calls) <= 2 else json.dumps({"data": [{"id": "1"}]}).encode()

    images, failed = m.list_images(FakeNet({"mapillary": answer}), F, 100, TOKEN, workers=1)
    assert failed == 1 and [im["id"] for im in images] == ["1"]


def test_a_403_without_the_request_limit_is_still_a_refused_token():
    net = FakeNet({"mapillary": _forbidden(REFUSED_BODY)})
    with pytest.raises(m.TokenRejected, match="refused the token"):
        m.list_images(net, F, 100, TOKEN)
    assert net.slept == []


def _always(error):
    calls = []

    def fn(i):
        calls.append(i)
        raise error

    return fn, calls


@pytest.mark.parametrize("error, sentence", [
    (AWAY, "Mapillary couldn't be reached; try again in a minute."),
    (SourceError("Mapillary answered HTTP 502; try again in a minute.", status=502),
     "Mapillary couldn't be reached; try again in a minute."),
    (m.Throttled(m.THROTTLED, status=403), "Mapillary's request limit was reached; try again in a minute."),
], ids=["unreachable", "down", "throttled"])
def test_downloads_stop_asking_after_eight_failures_in_a_row(error, sentence):
    fn, calls = _always(error)
    got = m.fetch_many(fn, [str(i) for i in range(40)])
    assert len(calls) <= 2 * m.WORKERS and m.OUTAGE_FAILURES == 8
    assert len(got) == 40 and all(isinstance(v, SourceError) for v in got.values())
    assert {str(v) for v in got.values() if isinstance(v, m.NotSent)} == {sentence}


def test_listing_stops_asking_after_eight_tiles_in_a_row_find_nobody_there():
    net = FakeNet({"mapillary": AWAY})
    assert len(m.tiles(F, 250)) == 25
    images, failed = m.list_images(net, F, 250, TOKEN)
    assert images == [] and failed == 25 and len(net.calls) <= 2 * m.WORKERS


def test_failures_that_are_answers_or_are_broken_up_by_one_do_not_stop_downloads():
    gone = SourceError("Mapillary answered HTTP 404; try again in a minute.", status=404)
    fn, calls = _always(gone)
    assert len(m.fetch_many(fn, [str(i) for i in range(20)], workers=1)) == 20 and len(calls) == 20

    def flaky(i):   # seven unreachable, one answer, seven unreachable
        if i == "7":
            return b"ok"
        raise AWAY

    got = m.fetch_many(flaky, [str(i) for i in range(15)], workers=1)
    assert got["7"] == b"ok" and not any(isinstance(v, m.NotSent) for v in got.values())


def test_a_refused_token_stops_the_requests_still_waiting():
    fn, calls = _always(m.TokenRejected(m.REFUSED, status=401))
    with pytest.raises(m.TokenRejected):
        m.fetch_many(fn, [str(i) for i in range(40)], workers=1)
    assert len(calls) == 1
