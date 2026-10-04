"""context.json: what the fetcher hands back. Standard library only.

Coordinates are local metres (x east, y north, z up) from the request centre.
Solids: rings[0] is the outer ring, counter-clockwise; holes are clockwise;
rings are not closed. Meshes: triangles, counter-clockwise seen from above.
"""
import math

from . import BUILDING_KINDS, CREDITS, GROUND_KINDS, KINDS, SCHEMA, SOURCE_NAMES, TOOL

_ORDER = {kind: i for i, kind in enumerate(
    GROUND_KINDS + BUILDING_KINDS + ("tree", "parcel", "parcel_on_site"))}
_MAX_PROBLEMS = 20


def new(request, *, region, terrain_source, ground_at_centre_m=None, cell_m=None):
    return {
        "schema": SCHEMA,
        "tool": TOOL,
        "centre": {"lat": request["centre"]["lat"], "lon": request["centre"]["lon"]},
        "address": request.get("address", ""),
        "radius_m": request["radius_m"],
        "region": region,
        "ground_at_centre_m": ground_at_centre_m,
        "terrain": {"source": terrain_source, "cell_m": cell_m},
        "site_rings_m": [],
        "elements": [],
        "sources": [],
        "notes": [],
        "counts": {},
    }


def element(element_id, kind, *, name="", solids=(), meshes=(), lines=()):
    return {"id": element_id, "kind": kind, "name": name,
            "solids": list(solids), "meshes": list(meshes), "lines": list(lines)}


def solid(kind, rings, z0, z1, height_source, ground=None):
    """A prism. `ground` is the ground level its top stands on (z1 - ground is its height), which LiDAR
    roofs measure up from; the base z0 can sit lower, buried under a whole building."""
    out = {"kind": kind, "rings": rings, "z0": round(float(z0), 3), "z1": round(float(z1), 3),
           "height_source": height_source}
    if ground is not None:
        out["ground"] = round(float(ground), 3)
    return out


def note(doc, level, code, text):
    doc["notes"].append({"level": level, "code": code, "text": text})


def add_source(doc, key):
    if all(s["key"] != key for s in doc["sources"]):
        doc["sources"].append({"key": key, "name": SOURCE_NAMES[key], "credit": CREDITS[key]})


def finish(doc):
    counts = {}
    for el in doc["elements"]:
        counts[el["kind"]] = counts.get(el["kind"], 0) + 1
    doc["counts"] = counts
    return doc


def iter_elements(doc):
    """Elements in build order: ground kinds, then buildings, trees, parcels (stable within a kind)."""
    return iter(sorted(doc["elements"], key=lambda el: _ORDER.get(el["kind"], len(_ORDER))))


def validate(doc):
    """Plain-sentence problems with a context document (at most 20); empty means fine."""
    if not isinstance(doc, dict):
        return ["The context is not a JSON object."]
    problems = []
    if doc.get("schema") != SCHEMA:
        problems.append(f"Unknown context schema {doc.get('schema')!r}; Ghost Town reads schema {SCHEMA}.")
    for key in ("centre", "radius_m", "terrain", "elements", "sources", "notes", "counts"):
        if key not in doc:
            problems.append(f"The context has no {key}.")
    if problems:
        return problems
    if doc.get("survey") is not None:
        problems += _survey_problems(doc["survey"])
    if doc.get("photo") is not None:
        problems += _photo_problems(doc["photo"])
    for el in doc["elements"]:
        problems += _element_problems(el)
        if len(problems) >= _MAX_PROBLEMS:
            break
    return problems[:_MAX_PROBLEMS]


def _survey_problems(point):
    """The survey point is optional (older files have none) but must hold numbers when present."""
    if not (isinstance(point, dict) and all(_num(point.get(k)) for k in ("easting_m", "northing_m", "grid_angle_deg"))
            and (point.get("elevation_m") is None or _num(point["elevation_m"]))):
        return ["The survey point needs a numeric easting, northing and grid angle."]
    return []


def _photo_problems(photo):
    """The photo is optional (older files have none) but must say where it is and what it covers.
    The file must sit beside context.json: no folders in its name, and no ':' (on Windows 'C:x.jpg'
    is relative to a drive's current folder)."""
    bounds = photo.get("bounds_m") if isinstance(photo, dict) else None
    ok = (isinstance(photo, dict) and isinstance(photo.get("file"), str) and photo["file"].strip()
          and not any(c in photo["file"] for c in "/\\:") and photo["file"] not in (".", "..")
          and isinstance(bounds, list) and len(bounds) == 4 and all(_num(v) for v in bounds)
          and bounds[0] < bounds[2] and bounds[1] < bounds[3]
          and all(isinstance(photo.get(k), int) and not isinstance(photo.get(k), bool) and photo[k] > 0
                  for k in ("width_px", "height_px"))
          and (photo.get("year") is None or (isinstance(photo["year"], int) and not isinstance(photo["year"], bool))))
    if not ok:
        return ["The photo needs a file name beside context.json, a pixel size and bounds_m [xmin, ymin, xmax, ymax]."]
    return []


def _element_problems(el):
    if not (isinstance(el, dict) and isinstance(el.get("id"), str) and el["id"]):
        return ["An element has no id."]
    eid, p = el["id"], []
    if el.get("kind") not in KINDS:
        p.append(f"{eid}: unknown kind {el.get('kind')!r}.")
    for s in el.get("solids", []):
        rings = s.get("rings")
        if not (isinstance(rings, list) and rings and all(isinstance(r, list) and len(r) >= 3 for r in rings)):
            p.append(f"{eid}: a solid needs rings of at least 3 points.")
        elif not (_num(s.get("z0")) and _num(s.get("z1")) and s["z0"] < s["z1"]):
            p.append(f"{eid}: a solid needs z0 below z1.")
        elif "ground" in s and not _num(s["ground"]):
            p.append(f"{eid}: a solid's ground must be a number.")
    for m in el.get("meshes", []):
        n = len(m.get("verts", []))
        if not all(len(f) == 3 and all(isinstance(i, int) and 0 <= i < n for i in f) for f in m.get("faces", [])):
            p.append(f"{eid}: a mesh face points at a missing vertex.")
    for line in el.get("lines", []):
        if len(line.get("pts", [])) < 2:
            p.append(f"{eid}: a line needs at least 2 points.")
    if not (el.get("solids") or el.get("meshes") or el.get("lines")):
        p.append(f"{eid}: the element has no geometry.")
    return p


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
