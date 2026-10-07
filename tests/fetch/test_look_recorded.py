"""Street Look on a recorded street: 351 King St E, its buildings within 60 m and six Mapillary photos with
their labels (tools/record_look_fixture.py). Real photos catch what the synthetic street can't."""
import base64
import gzip
import json
import os

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
    def answer(url, _data):
        if "/images?" in url:
            return json.dumps({"data": data["listings"].get(url, [])}).encode()
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
    monkeypatch.setattr(terrain, "load", lambda net, frame, radius_m: (terrain.FlatTerrain(), None))
    answer = look.run(dict(req, cache_dir=str(tmp_path), out_dir=str(tmp_path / "run")), _net(data), "MLY|test")
    assert ls.validate_answer(answer) == []
    assert 3 <= answer["photos_used"] <= req["budget_photos"] and answer["sources"][0]["key"] == "mapillary"
    tower = answer["buildings"][TOWER]
    assert tower["source"] == "photos" and len(tower["zones"]) >= 2
    shop, above = tower["zones"][:2]
    assert shop["kind"] == "storefront" and _lum(shop) < _lum(above)
    assert set(answer["buildings"]) == {b["id"] for b in req["buildings"]}
