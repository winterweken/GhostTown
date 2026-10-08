"""Record a small Mapillary street for the offline Street Look test.

    GHOSTTOWN_MAPILLARY_TOKEN=... uv run python tools/record_look_fixture.py [cache folder]

Builds the City's massing around 351 King St E, keeps the buildings that have a corner within 60 m (whole buildings,
so some reach farther), runs Street Look on them with a budget of 6 photos on flat ground, and writes
tests/fetch/fixtures/kingst/: look_request.json, and mapillary.json.gz with the listings cut down to the photos
downloaded, those photos at 512 px and their labels. The saved request carries the smallest valid budget, because
the validator rejects less, while the recording downloads only BUDGET photos; the replay can only choose among the
recorded ones.
Pass a cache folder to reuse one that already holds the massing model (an 81 MB download).
Street photos © Mapillary contributors, CC BY-SA 4.0.
"""
import base64
import gzip
import io
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ghosttown"))

from PIL import Image  # noqa: E402

from ghosttown_fetch import cli, look, terrain  # noqa: E402
from ghosttown_fetch import look_schema as ls  # noqa: E402
from ghosttown_fetch import request as rq  # noqa: E402
from ghosttown_fetch.net import Net  # noqa: E402

CENTRE = {"lat": 43.651769, "lon": -79.365065}   # 351 King St E
KEEP_M = 60.0
BUDGET = 6
OUT = os.path.join(ROOT, "tests", "fetch", "fixtures", "kingst")


class Recorder:
    """A Net that keeps every answer Street Look got, by cache key or URL."""

    def __init__(self, net):
        self.net, self.answers, self.sleep = net, {}, net.sleep

    def get(self, url, *, key=None, **kwargs):
        body = self.net.get(url, key=key, **kwargs)
        self.answers[key or url] = body
        return body

    def cached(self, source, key, check=None):
        return None   # everything passes through get, so everything is recorded


def _near(el):
    return any(x * x + y * y <= KEEP_M ** 2 for s in el["solids"] for ring in s["rings"] for x, y in ring)


def _small(jpeg):
    im = Image.open(io.BytesIO(jpeg)).convert("RGB")
    im.thumbnail((512, 512))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85)
    return out.getvalue()


def main():
    token = os.environ.get(ls.TOKEN_ENV, "").strip()
    if not token:
        sys.exit(f"Set {ls.TOKEN_ENV} first.")
    work = tempfile.mkdtemp(prefix="ghosttown-look-fixture-")
    cache = sys.argv[1] if len(sys.argv) > 1 else os.path.join(work, "cache")
    req = rq.build(centre=CENTRE, radius_m=150, layers=["buildings"], cache_dir=cache,
                   out_dir=os.path.join(work, "run"))
    os.makedirs(req["out_dir"])
    path = os.path.join(req["out_dir"], "request.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(req, f)
    result = cli.fetch(path, None)
    if not result["ok"]:
        sys.exit(result["error"])
    with open(result["context"], encoding="utf-8") as f:
        doc = json.load(f)
    buildings = [{"id": el["id"], "solids": [{k: s[k] for k in ("rings", "z0", "z1")} for s in el["solids"]]}
                 for el in doc["elements"] if el["solids"] and _near(el)]
    look_req = ls.build_request(centre=CENTRE, radius_m=KEEP_M, buildings=buildings, cache_dir="unused",
                                out_dir="unused", budget_photos=max(BUDGET, ls.BUDGET_RANGE[0]))
    terrain.load = lambda net, frame, radius_m: (terrain.FlatTerrain(), None)   # as in the test
    net = Recorder(Net(cache))
    answer = look.run(dict(look_req, budget_photos=BUDGET), net, token)

    photos = {key.split(":")[1]: body for key, body in net.answers.items() if key.startswith("photo:")}
    labels = {url.split("/")[-2]: json.loads(body)["data"] for url, body in net.answers.items() if "/detections" in url}
    listings = {url: [im for im in json.loads(body)["data"] if str(im.get("id")) in photos]
                for url, body in net.answers.items() if "/images?" in url}
    data = {"listings": {url: ims for url, ims in listings.items() if ims},
            "photos": {i: base64.b64encode(_small(b)).decode("ascii") for i, b in photos.items()},
            "labels": {i: labels[i] for i in photos if i in labels}}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "look_request.json"), "w", encoding="utf-8") as f:
        json.dump(look_req, f, separators=(",", ":"))
    with gzip.open(os.path.join(OUT, "mapillary.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    size = sum(os.path.getsize(os.path.join(OUT, n)) for n in os.listdir(OUT))
    print(f"{len(buildings)} buildings; {len(photos)} photos recorded, {answer['photos_used']} used; {size / 1024:.0f} KB in {OUT}")


if __name__ == "__main__":
    main()
