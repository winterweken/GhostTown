"""Street Look on five Toronto sites, to catch changes for the worse in choosing photos or reading facades.
Not part of CI: it needs the network and a Mapillary token, and takes a few minutes a site. Run it with
GHOSTTOWN_MAPILLARY_TOKEN set in the environment (never typed on the command line, where the shell's history keeps it):

    uv run python tools/look_accuracy.py [cache folder] [site name ...]

For each site it prints how many buildings got their look from photos, what the building at the address got,
and how long each stage took. Compare with the numbers in design/street-look.md (sections 3 and 10)."""
import json
import math
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ghosttown"))

from ghosttown_fetch import cli, look  # noqa: E402
from ghosttown_fetch import look_schema as ls  # noqa: E402
from ghosttown_fetch import request as rq  # noqa: E402
from ghosttown_fetch.net import Net  # noqa: E402

SITES = {
    "351 King St E": (43.651768898, -79.365064762),
    "320 Bay St": (43.649667039, -79.380991173),
    "235 Queens Quay W": (43.63923186, -79.383105327),
    "2300 Yonge St": (43.707157575, -79.399083527),
    "300 Borough Dr": (43.7762918562, -79.2580219048),
}
RADIUS_M = 300.0


def _buildings(lat, lon, cache, work):
    # With terrain, as the add-on fetches it: the buildings then stand on the same ground as the cameras in look.run.
    req = rq.build(centre={"lat": lat, "lon": lon}, radius_m=RADIUS_M, layers=["buildings", "terrain"], cache_dir=cache,
                   out_dir=os.path.join(work, "run"))
    os.makedirs(req["out_dir"])
    path = os.path.join(req["out_dir"], "request.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(req, f)
    result = cli.fetch(path, None)
    if not result["ok"]:
        raise SystemExit(result["error"])
    with open(result["context"], encoding="utf-8") as f:
        doc = json.load(f)
    if doc.get("ground_at_centre_m") is None:   # flat buildings would be measured, not the add-on's on their ground
        raise SystemExit("NRCan's ground heights couldn't be fetched, so the buildings are flat; run it again.")
    return [{"id": el["id"], "solids": [{k: s[k] for k in ("rings", "z0", "z1")} for s in el["solids"]]}
            for el in doc["elements"] if el["solids"]], doc.get("ground_at_centre_m")


def _at_address(buildings):
    """The building with a footprint corner nearest the address."""
    return min(buildings, key=lambda b: min(math.hypot(x, y) for s in b["solids"] for ring in s["rings"]
                                            for x, y in ring))["id"]


def _zones(entry):
    return " · ".join(f"{z['kind']} {z['h0']:g}–{'' if z['h1'] is None else format(z['h1'], 'g')}"
                      for z in entry["zones"])


def run_site(name, lat, lon, cache, token):
    work = tempfile.mkdtemp(prefix="ghosttown-accuracy-")
    buildings, ground = _buildings(lat, lon, cache, work)
    req = ls.build_request(centre={"lat": lat, "lon": lon}, radius_m=RADIUS_M, buildings=buildings,
                           ground_at_centre_m=ground, cache_dir=cache, out_dir=os.path.join(work, "look"))
    stages, start = {}, time.monotonic()
    answer = look.run(req, Net(cache), token, progress=lambda stage, pct: stages.setdefault(stage, time.monotonic() - start))
    total = time.monotonic() - start
    times = sorted(stages.items(), key=lambda kv: kv[1]) + [("End", total)]
    took = {a: round(t1 - t0) for (a, t0), (_b, t1) in zip(times, times[1:])}
    target = answer["buildings"][_at_address(buildings)]
    photos = sum(1 for e in answer["buildings"].values() if e["source"] == "photos")
    return (f"| {name} | {len(buildings)} | {photos} | {answer['photos_used']} | {target['source']}, "
            f"{target['confidence']:.2f}: {_zones(target)} | {took.get('Choosing photos', 0)} | "
            f"{took.get('Reading facades', 0)} | {round(total)} |")


def main():
    token = os.environ.get(ls.TOKEN_ENV, "").strip()
    if not token:
        sys.exit(f"Set {ls.TOKEN_ENV} first.")
    if not (token.isascii() and token.isprintable() and not any(c.isspace() for c in token)):
        # As in cli.py: a newline or control character in the header makes http.client raise a ValueError that quotes
        # the whole header, and the traceback would print the token.
        sys.exit(f"{ls.TOKEN_ENV} has characters a token can't have; check it.")
    cache = sys.argv[1] if len(sys.argv) > 1 else os.path.join(tempfile.mkdtemp(prefix="ghosttown-accuracy-"), "cache")
    names = sys.argv[2:] or list(SITES)
    print("| Site | Buildings | From photos | Photos | Building at the address | Choosing s | Reading s | Total s |")
    print("|---|---|---|---|---|---|---|---|")
    for name in names:
        print(run_site(name, *SITES[name], cache, token), flush=True)


if __name__ == "__main__":
    main()
