"""request.json: what the add-on asks the fetcher for. Standard library only."""
import json
import math

from . import LAYERS, RADIUS_RANGE_M, SCHEMA, SITE_LIMIT_M, TOOL


def build(*, centre, radius_m, cache_dir, out_dir, address="", layers=LAYERS,
          site_polys_m=(), fetch_fresh=False, overpass_url=""):
    return {
        "schema": SCHEMA,
        "tool": TOOL,
        "centre": {"lat": float(centre["lat"]), "lon": float(centre["lon"])},
        "address": str(address),
        "radius_m": float(radius_m),
        "layers": list(layers),
        "site_polys_m": [[[float(x), float(y)] for x, y in ring] for ring in site_polys_m],
        "fetch_fresh": bool(fetch_fresh),
        "overpass_url": str(overpass_url),
        "cache_dir": str(cache_dir),
        "out_dir": str(out_dir),
    }


def validate(doc):
    """Plain-sentence problems with a request; an empty list means it is fine."""
    if not isinstance(doc, dict):
        return ["The request is not a JSON object."]
    problems = []
    if doc.get("schema") != SCHEMA:
        problems.append(f"Unknown request schema {doc.get('schema')!r}; this fetcher reads schema {SCHEMA}.")
    c = doc.get("centre")
    if not (isinstance(c, dict) and _num(c.get("lat")) and _num(c.get("lon"))
            and -85 <= c["lat"] <= 85 and -180 <= c["lon"] <= 180):
        problems.append("centre must be {lat, lon} in degrees, with latitude within ±85.")
    lo, hi = RADIUS_RANGE_M
    r = doc.get("radius_m")
    if not (_num(r) and lo <= r <= hi):
        problems.append(f"radius_m must be between {lo:g} and {hi:g} m.")
    layers = doc.get("layers")
    if not (isinstance(layers, list) and layers and all(layer in LAYERS for layer in layers)):
        problems.append("layers must be a non-empty list drawn from: " + ", ".join(LAYERS) + ".")
    polys = doc.get("site_polys_m", [])
    if not (isinstance(polys, list) and all(_ring_ok(ring) for ring in polys)):
        problems.append(f"site_polys_m must be rings of at least 3 [x, y] points within {SITE_LIMIT_M:g} m of the centre.")
    if not isinstance(doc.get("fetch_fresh", False), bool):
        problems.append("fetch_fresh must be true or false.")
    url = doc.get("overpass_url", "")
    if not (isinstance(url, str) and (url == "" or url.startswith(("http://", "https://")))):
        problems.append("overpass_url must be blank or an http(s) address.")
    for key in ("cache_dir", "out_dir"):
        if not (isinstance(doc.get(key), str) and doc[key].strip()):
            problems.append(f"{key} must be a folder path.")
    return problems


def read(path):
    """(doc, problems). doc is None when the file can't be read as JSON."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        return None, [f"Couldn't read the request ({e})."]
    return doc, validate(doc)


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _ring_ok(ring):
    return (isinstance(ring, list) and len(ring) >= 3
            and all(isinstance(p, list) and len(p) == 2 and all(_num(c) and abs(c) <= SITE_LIMIT_M for c in p)
                    for p in ring))
