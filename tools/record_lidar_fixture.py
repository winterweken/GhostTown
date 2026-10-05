"""Record small Ontario LiDAR fixtures for the tests (needs the network).

    uv run python tools/record_lidar_fixture.py

Writes tests/fetch/fixtures/ontario/: the surface and terrain models over ±40 m around 320 Bay St, as
gzipped TIFFs, and the service's empty answer for a box out in Lake Ontario.
"""
import gzip
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ghosttown"))

from ghosttown_fetch.frame import Frame  # noqa: E402
from ghosttown_fetch.net import USER_AGENT  # noqa: E402
from ghosttown_fetch.sources import ontario_lidar as lidar  # noqa: E402

OUT = os.path.join(ROOT, "tests", "fetch", "fixtures", "ontario")
BAY = (43.649667, -79.380991)
LAKE = (43.45, -78.6)
HALF_M = 40.0


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=lidar.TIMEOUT_S) as resp:
        return resp.read()


def main():
    os.makedirs(OUT, exist_ok=True)
    square = (-HALF_M, -HALF_M, HALF_M, HALF_M)
    box, size = lidar.area(Frame(*BAY), square, 0.5)
    for name, service in (("bay_surface", lidar.SURFACE), ("bay_terrain", lidar.TERRAIN)):
        body = get(lidar.export_url(service, box, size))
        lidar.check(body)
        with open(os.path.join(OUT, name + ".tif.gz"), "wb") as f:
            f.write(gzip.compress(body, mtime=0))
        print(name, size, len(body), "bytes")
    box, size = lidar.area(Frame(*LAKE), square, 0.5)
    body = get(lidar.export_url(lidar.SURFACE, box, size))
    with open(os.path.join(OUT, "lake_none.tif"), "wb") as f:
        f.write(body)
    print("lake_none", size, len(body), "bytes")


if __name__ == "__main__":
    main()
