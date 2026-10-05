"""Record a small City of Toronto aerial photo for the offline tests.

    uv run python tools/record_photo_fixture.py

Writes tests/fetch/fixtures/bay/photo_128.jpg: 128 px of the newest photo, 200 m across, at 320 Bay St.
Contains information licensed under the Open Government Licence – Toronto.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ghosttown"))

from ghosttown_fetch.frame import Frame, lonlat_to_merc  # noqa: E402

SERVICES = "https://gis.toronto.ca/arcgis/rest/services"
HEADERS = {"User-Agent": "GhostTown-fixtures (+https://github.com/winterweken/GhostTown)"}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=120) as resp:
        return resp.read()


if __name__ == "__main__":
    names = [s["name"] for s in json.loads(get(SERVICES + "/basemap?f=json"))["services"]
             if re.fullmatch(r"basemap/cot_ortho_\d{4}_color_\d+cm", s["name"])]
    service = max(names, key=lambda name: int(name.split("_")[2]))
    frame = Frame(43.649667, -79.380991)
    x0, y0 = lonlat_to_merc(*frame.to_lonlat(-100.0, -100.0))
    x1, y1 = lonlat_to_merc(*frame.to_lonlat(100.0, 100.0))
    query = urllib.parse.urlencode({"bbox": f"{float(x0):.3f},{float(y0):.3f},{float(x1):.3f},{float(y1):.3f}",
                                    "bboxSR": 3857, "imageSR": 3857, "size": "128,128", "format": "jpg", "f": "image"})
    body = get(f"{SERVICES}/{service}/MapServer/export?{query}")
    assert body[:2] == b"\xff\xd8" and len(body) > 1024, body[:200]
    path = os.path.join(ROOT, "tests", "fetch", "fixtures", "bay", "photo_128.jpg")
    with open(path, "wb") as f:
        f.write(body)
    print(f"{service}: {len(body):,} bytes -> {path}")
