"""Street Look on a recorded street: 351 King St E, the buildings with a corner within 60 m of it and six Mapillary
photos with their labels (tools/record_look_fixture.py). Real photos catch what the synthetic street can't.
The tower has no measured floor height (its floor_h is the 3.5 m fallback) and no glass zone, so a re-recording that
gains them is not a regression. Its dark base is read up to 9 m, but read only where each photo shows the wall itself
(not a nearer part of the tower in front of it), the brightness step there is about 1.56 times: just short of the
storefront rule's 1.6, so the zone is opaque, not a storefront, and the test asks only for the dark base."""
import base64
import gzip
import json
import os
import urllib.parse

import pytest

from fakes import FakeNet
from ghosttown_fetch import look, terrain
from ghosttown_fetch import look_schema as ls

HERE = os.path.join(os.path.dirname(__file__), "fixtures", "kingst")
TOWER = "toronto:massing:2025:361309"   # 351 King St E: dark shopfronts under lighter floors


def _lum(zone):
    r, g, b = zone["colour"]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _net(data):
    # Listings are answered by position, not by tile URL, so retuning the search margin or the tile size still finds
    # the recorded photos.
    images = list({str(im["id"]): im for listing in data["listings"].values() for im in listing}.values())

    def answer(url, _data):
        if "/images?" in url:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            west, south, east, north = (float(v) for v in query["bbox"][0].split(","))
            fields = query["fields"][0].split(",")   # Mapillary answers only the fields asked for
            inside = [{k: im[k] for k in fields if k in im} for im in images
                      if west <= im["computed_geometry"]["coordinates"][0] <= east
                      and south <= im["computed_geometry"]["coordinates"][1] <= north]
            return json.dumps({"data": inside}).encode()
        if "?fields=thumb_2048_url" in url:
            image_id = url.split("/")[-1].split("?")[0]
            return json.dumps({"id": image_id, "thumb_2048_url": f"https://photos.test/{image_id}.jpg"}).encode()
        if url.startswith("https://photos.test/"):
            return base64.b64decode(data["photos"][url.rsplit("/", 1)[1][:-len(".jpg")]])
        if "/detections" in url:
            return json.dumps({"data": data["labels"][url.split("/")[-2]]}).encode()
        raise AssertionError(f"unexpected request {url}")

    return FakeNet({"mapillary": answer})


@pytest.fixture(scope="module")
def recorded():
    with open(os.path.join(HERE, "look_request.json"), encoding="utf-8") as f:
        req = json.load(f)
    with gzip.open(os.path.join(HERE, "mapillary.json.gz"), "rt", encoding="utf-8") as f:
        return req, json.load(f)


def test_the_recorded_street_gives_the_tower_its_dark_shopfronts(recorded, monkeypatch, tmp_path):
    req, data = recorded
    assert ls.validate_request(req) == []
    monkeypatch.setattr(terrain, "load", lambda net, frame, radius_m: (terrain.FlatTerrain(), None))
    answer = look.run(dict(req, cache_dir=str(tmp_path), out_dir=str(tmp_path / "run")), _net(data), "MLY|test")
    assert ls.validate_answer(answer) == []
    found = (answer["notes"], {bid: (e["source"], e["photos"]) for bid, e in answer["buildings"].items()})
    assert answer["photos_used"] >= 3 and answer["sources"][0]["key"] == "mapillary", found
    tower = answer["buildings"][TOWER]
    assert tower["source"] == "photos" and len(tower["zones"]) >= 2, found
    shop, above = tower["zones"][:2]
    assert shop["h1"] <= 9.0 and _lum(shop) < _lum(above), tower["zones"]   # the dark shopfronts
    assert set(answer["buildings"]) == {b["id"] for b in req["buildings"]}
