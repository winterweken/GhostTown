"""Record live source answers for the offline tests.

    uv run python tools/record_fixtures.py [site ...]

Writes tests/fetch/fixtures/<site>/<source>.json.gz. The tests themselves never touch the network.
OpenStreetMap data © OpenStreetMap contributors, ODbL 1.0.
"""
import gzip
import json
import os
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ghosttown"))

from ghosttown_fetch.net import Net  # noqa: E402
from ghosttown_fetch.sources import osm  # noqa: E402
from ghosttown_fetch.sources import address, arcgis, toronto  # noqa: E402

FIXTURES = os.path.join(ROOT, "tests", "fetch", "fixtures")
SITES = {  # name: (lat, lon, radius_m)
    "bay": (43.649667, -79.380991, 150),       # 320 Bay St, downtown Toronto
    "steeles": (43.798060, -79.418890, 150),   # Yonge & Steeles, on the Toronto boundary
    "london": (51.507350, -0.127760, 150),     # Trafalgar Square, outside Canada
}


def record(name):
    lat, lon, radius = SITES[name]
    net = Net(os.path.join(ROOT, ".cache-record"), fresh=True)
    data = urllib.parse.urlencode({"data": osm.build_query(lat, lon, radius, ["buildings"])}).encode("ascii")
    body = net.get(osm.ENDPOINT, source="osm", data=data, check=osm.check)
    folder = os.path.join(FIXTURES, name)
    os.makedirs(folder, exist_ok=True)
    with gzip.open(os.path.join(folder, "osm.json.gz"), "wb") as f:
        f.write(body)
    print(f"{name}: {len(body):,} bytes")


def record_toronto(name):
    lat, lon, radius = SITES[name]
    net = Net(os.path.join(ROOT, ".cache-record"), fresh=True)
    folder = os.path.join(FIXTURES, name)
    os.makedirs(folder, exist_ok=True)
    feats = toronto.fetch_buildings(net, lat, lon, radius)
    with gzip.open(os.path.join(folder, "toronto_buildings.json.gz"), "wb") as f:
        f.write(json.dumps({"type": "FeatureCollection", "features": feats}).encode("utf-8"))
    print(f"{name}: {len(feats)} City building tiers")
    if hasattr(address, "build_params"):
        params = address.build_params(address.normalise("320 Bay St"), 5)
        body = net.get(arcgis.layer_url(*address.LAYER), source="toronto",
                       data=urllib.parse.urlencode(params).encode("ascii"), check=arcgis.check)
        with gzip.open(os.path.join(folder, "toronto_address.json.gz"), "wb") as f:
            f.write(body)
        print(f"{name}: address answer {len(body):,} bytes")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["toronto"]:
        record_toronto("bay")
    else:
        for site in args or list(SITES):
            record(site)
