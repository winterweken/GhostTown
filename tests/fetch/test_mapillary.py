import json

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
