"""look_request.json and look.json: what Street Look asks the fetcher for and what it answers.
Standard library only, so the Blender add-on can import it.

In look.json, heights are metres above the building's lowest point and colours are linear RGB."""
import json
import math

from . import LOOK_SCHEMA, TOOL

TOKEN_ENV = "GHOSTTOWN_MAPILLARY_TOKEN"
ZONE_KINDS = ("storefront", "opaque", "glass", "cap")
BUDGET_RANGE = (10, 500)
MAX_DETAIL = 20
_MAX_PROBLEMS = 20


def build_request(*, centre, radius_m, buildings, cache_dir, out_dir, ground_at_centre_m=None,
                  budget_photos=150, not_before_year=None, search_margin_m=200.0, fetch_fresh=False):
    return {
        "schema": LOOK_SCHEMA,
        "tool": TOOL,
        "centre": {"lat": float(centre["lat"]), "lon": float(centre["lon"])},
        "radius_m": float(radius_m),
        "ground_at_centre_m": None if ground_at_centre_m is None else float(ground_at_centre_m),
        "buildings": [{"id": str(b["id"]), "detail": bool(b.get("detail", False)),
                       "solids": [{"rings": [[[float(x), float(y)] for x, y in ring] for ring in s["rings"]],
                                   "z0": float(s["z0"]), "z1": float(s["z1"])} for s in b["solids"]]}
                      for b in buildings],
        "budget_photos": int(budget_photos),
        "not_before_year": int(not_before_year) if not_before_year else None,
        "search_margin_m": float(search_margin_m),
        "fetch_fresh": bool(fetch_fresh),
        "cache_dir": str(cache_dir),
        "out_dir": str(out_dir),
    }


def validate_request(doc):
    """Plain-sentence problems with a look request (at most 20); empty means fine."""
    if not isinstance(doc, dict):
        return ["The street look request is not a JSON object."]
    problems = []
    if doc.get("schema") != LOOK_SCHEMA:
        problems.append(f"Unknown street look schema {doc.get('schema')!r}; this fetcher reads schema {LOOK_SCHEMA}.")
    c = doc.get("centre")
    if not (isinstance(c, dict) and _num(c.get("lat")) and _num(c.get("lon"))
            and -85 <= c["lat"] <= 85 and -180 <= c["lon"] <= 180):
        problems.append("centre must be {lat, lon} in degrees, with latitude within ±85.")
    if not (_num(doc.get("radius_m")) and 50 <= doc["radius_m"] <= 1000):
        problems.append("radius_m must be between 50 and 1000 m.")
    lo, hi = BUDGET_RANGE
    if not (_int(doc.get("budget_photos")) and lo <= doc["budget_photos"] <= hi):
        problems.append(f"budget_photos must be a whole number from {lo} to {hi}.")
    year = doc.get("not_before_year")
    if year is not None and not (_int(year) and 2000 <= year <= 2100):
        problems.append("not_before_year must be blank or a year from 2000 to 2100.")
    if not (_num(doc.get("search_margin_m")) and 0 <= doc["search_margin_m"] <= 500):
        problems.append("search_margin_m must be between 0 and 500 m.")
    buildings = doc.get("buildings")
    if not isinstance(buildings, list):
        problems.append("buildings must be a list.")
    else:
        if sum(1 for b in buildings if isinstance(b, dict) and b.get("detail")) > MAX_DETAIL:
            problems.append(f"At most {MAX_DETAIL} buildings can have detail.")
        for b in buildings:
            problems += _building_problems(b)
            if len(problems) >= _MAX_PROBLEMS:
                break
    for key in ("cache_dir", "out_dir"):
        if not (isinstance(doc.get(key), str) and doc[key].strip()):
            problems.append(f"{key} must be a folder path.")
    return problems[:_MAX_PROBLEMS]


def _building_problems(b):
    if not (isinstance(b, dict) and isinstance(b.get("id"), str) and b["id"]):
        return ["A building has no id."]
    solids = b.get("solids")
    if not (isinstance(solids, list) and solids):
        return [f"{b['id']}: a building needs at least one solid."]
    problems = []
    for s in solids:
        rings = s.get("rings") if isinstance(s, dict) else None
        if not (isinstance(rings, list) and rings and all(_ring(r) for r in rings)):
            problems.append(f"{b['id']}: a solid needs rings of at least 3 points.")
        elif not (_num(s.get("z0")) and _num(s.get("z1")) and s["z0"] < s["z1"]):
            problems.append(f"{b['id']}: a solid needs z0 below z1.")
    return problems


def _ring(ring):
    return (isinstance(ring, list) and len(ring) >= 3
            and all(isinstance(p, list) and len(p) == 2 and _num(p[0]) and _num(p[1]) for p in ring))


def read_request(path):
    """(doc, problems). doc is None when the file can't be read as JSON."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        return None, [f"Couldn't read the street look request ({e})."]
    return doc, validate_request(doc)


def new_answer():
    return {"schema": LOOK_SCHEMA, "tool": TOOL, "photos_used": 0, "years": None, "buildings": {},
            "sources": [], "notes": []}


def validate_answer(doc):
    """Plain-sentence problems with a look.json (at most 20); empty means fine."""
    if not isinstance(doc, dict):
        return ["The street look answer is not a JSON object."]
    if doc.get("schema") != LOOK_SCHEMA:
        return [f"Unknown street look schema {doc.get('schema')!r}; Ghost Town reads schema {LOOK_SCHEMA}."]
    problems = [f"The street look answer has no {key}." for key in ("buildings", "sources", "notes") if key not in doc]
    if problems:
        return problems
    for bid, entry in doc["buildings"].items():
        problems += _entry_problems(bid, entry)
        if len(problems) >= _MAX_PROBLEMS:
            break
    return problems[:_MAX_PROBLEMS]


def _entry_problems(bid, e):
    if not isinstance(e, dict):
        return [f"{bid}: not an object."]
    problems = []
    if e.get("source") not in ("photos", "guessed"):
        problems.append(f"{bid}: source must be photos or guessed.")
    if not (_num(e.get("floor_h")) and e["floor_h"] > 0):
        problems.append(f"{bid}: floor_h must be positive.")
    zones = e.get("zones")
    if not (isinstance(zones, list) and 1 <= len(zones) <= 4):
        return problems + [f"{bid}: zones must be a list of 1 to 4 zones."]
    last = None
    for i, z in enumerate(zones):
        final = i == len(zones) - 1
        if not (isinstance(z, dict) and z.get("kind") in ZONE_KINDS and _num(z.get("h0"))
                and (z.get("h1") is None if final else _num(z.get("h1")))
                and isinstance(z.get("colour"), list) and len(z["colour"]) == 3
                and all(_num(c) and c >= 0 for c in z["colour"])):
            problems.append(f"{bid}: zone {i + 1} is malformed.")
            continue
        if last is not None and abs(z["h0"] - last) > 1e-6:
            problems.append(f"{bid}: zones must follow each other without gaps.")
        last = z["h1"]
    return problems


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)
