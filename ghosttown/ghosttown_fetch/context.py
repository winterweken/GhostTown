"""context.json: what the fetcher hands back. Standard library only.

Coordinates are local metres (x east, y north, z up) from the request centre.
Solids: rings[0] is the outer ring, counter-clockwise; holes are clockwise;
rings are not closed. Meshes: triangles, counter-clockwise seen from above.
Development application sites (design/development-applications.md §4.4) come in an optional top-level "applications"
list, with the day they were fetched as "applications_date".
"""
import math
import re
import urllib.parse

from . import APPLICATION_GROUPS, BUILDING_KINDS, CREDITS, GROUND_KINDS, KINDS, SCHEMA, SOURCE_NAMES, TOOL

_ORDER = {kind: i for i, kind in enumerate(
    GROUND_KINDS + BUILDING_KINDS + ("tree", "parcel", "parcel_on_site"))}
_MAX_PROBLEMS = 20
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
APPLICATION_KEYS = ("number", "type", "status", "submitted", "address", "description", "source", "url")
APPLICATION_SOURCES = ("application", "permit")


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


def solid(kind, rings, z0, z1, height_source, ground=None, roof=None):
    """A prism. `ground` is the ground level its top stands on (z1 - ground is its height), which LiDAR
    roofs measure up from; the base z0 can sit lower, buried under a whole building. `roof` holds
    OpenStreetMap's roof tags for fitted roofs: {"shape": "gabled", "height": 2.5}, each key optional."""
    out = {"kind": kind, "rings": rings, "z0": round(float(z0), 3), "z1": round(float(z1), 3),
           "height_source": height_source}
    if ground is not None:
        out["ground"] = round(float(ground), 3)
    if roof:
        out["roof"] = dict(roof)
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
    if doc.get("lidar") is not None:
        problems += _lidar_problems(doc["lidar"])
    if "applications" in doc:
        problems += applications_problems(doc["applications"], doc.get("applications_date"))
    for el in doc["elements"]:
        problems += _element_problems(el)
        if len(problems) >= _MAX_PROBLEMS:
            break
    return problems[:_MAX_PROBLEMS]


def _survey_problems(point):
    """The survey point is optional (older files have none) but must hold numbers and name its grid when
    present."""
    if not (isinstance(point, dict) and all(_num(point.get(k)) for k in ("easting_m", "northing_m", "grid_angle_deg"))
            and (point.get("elevation_m") is None or _num(point["elevation_m"]))):
        return ["The survey point needs a numeric easting, northing and grid angle."]
    if not all(isinstance(point.get(k), str) and point[k].strip() for k in ("epsg", "name")):
        return ["The survey point needs its grid's name and EPSG code."]
    return []


def _beside(name):
    """A file name beside context.json: no folders in it, and no ':' (on Windows 'C:x.jpg' is relative
    to a drive's current folder)."""
    return (isinstance(name, str) and bool(name.strip()) and not any(c in name for c in "/\\:")
            and name not in (".", ".."))


def _count(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _photo_problems(photo):
    """The photo is optional (older files have none) but must say where it is and what it covers."""
    bounds = photo.get("bounds_m") if isinstance(photo, dict) else None
    ok = (isinstance(photo, dict) and _beside(photo.get("file"))
          and isinstance(bounds, list) and len(bounds) == 4 and all(_num(v) for v in bounds)
          and bounds[0] < bounds[2] and bounds[1] < bounds[3]
          and all(isinstance(photo.get(k), int) and not isinstance(photo.get(k), bool) and photo[k] > 0
                  for k in ("width_px", "height_px"))
          and (photo.get("year") is None or (isinstance(photo["year"], int) and not isinstance(photo["year"], bool))))
    if not ok:
        return ["The photo needs a file name beside context.json, a pixel size and bounds_m [xmin, ymin, xmax, ymax]."]
    return []


def _lidar_problems(lidar):
    """LiDAR roofs are optional but must name their file, grid, counts and building kinds."""
    kinds = lidar.get("kinds") if isinstance(lidar, dict) else None
    ok = (isinstance(lidar, dict) and _beside(lidar.get("file")) and _num(lidar.get("cell_m")) and lidar["cell_m"] > 0
          and _count(lidar.get("buildings")) and _count(lidar.get("triangles"))
          and isinstance(kinds, list) and kinds and all(k in BUILDING_KINDS for k in kinds)
          and (lidar.get("year") is None or _count(lidar["year"])))
    if not ok:
        return ["The LiDAR roofs need a file name beside context.json, a cell size, counts and building kinds."]
    fitted = lidar.get("fitted")
    if fitted is not None and not (isinstance(fitted, dict) and _beside(fitted.get("file"))
                                   and _count(fitted.get("buildings")) and _count(fitted.get("triangles"))):
        return ["The fitted roofs need a file name beside context.json and counts."]
    return []


def _roof_ok(roof):
    return (isinstance(roof, dict) and set(roof) <= {"shape", "height"}
            and ("shape" not in roof or (isinstance(roof["shape"], str) and roof["shape"].strip() != ""))
            and ("height" not in roof or (_num(roof["height"]) and roof["height"] > 0)))


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
        elif "roof" in s and not _roof_ok(s["roof"]):
            p.append(f"{eid}: a solid's roof tags need a shape name and a positive height, each optional.")
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


def city_link(url):
    """`url`, trimmed, when it is an http(s) address on toronto.ca or one of its subdomains, else "": the only
    links the Site panel opens. A backslash, a space or other control character, a user name or a host that is not
    ASCII is refused, since a browser may read such a URL as going somewhere else."""
    if not isinstance(url, str):
        return ""
    url = url.strip()
    if any(c == "\\" or ord(c) <= 0x20 or ord(c) == 0x7F for c in url):
        return ""
    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
        parts.port  # raises ValueError for a port that is not a number: then it is no City address
    except ValueError:
        return ""
    if "@" in parts.netloc or not parts.netloc.isascii():  # no user name, and the host as written is ASCII
        return ""
    if parts.scheme in ("http", "https") and (host == "toronto.ca" or host.endswith(".toronto.ca")):
        return url
    return ""


def _text(v):
    return isinstance(v, str) and v.strip() != ""


def _xy(v):
    return isinstance(v, list) and len(v) == 2 and all(_num(c) for c in v)


def _entry_ok(a):
    return (isinstance(a, dict) and all(isinstance(a.get(k), str) for k in APPLICATION_KEYS)
            and _text(a["number"]) and a["source"] in APPLICATION_SOURCES
            and _num(a.get("floor_area_m2")) and a["floor_area_m2"] >= 0
            and (a["url"] == "" or city_link(a["url"]) == a["url"]))


def _application_problem(site):
    """What is wrong with one application site, as a phrase, or None."""
    if not isinstance(site, dict):
        return "an application site is not an object"
    sid = site.get("id")
    if not (_text(sid) and sid.startswith("app:") and len(sid) > 4):
        return "an application site has no id"
    if site.get("group") not in APPLICATION_GROUPS:
        return f"application site {sid} has an unknown group"
    numbers = site.get("numbers")
    if not (isinstance(numbers, list) and numbers and all(_text(n) for n in numbers)
            and len(set(numbers)) == len(numbers)):
        return f"application site {sid} has no list of distinct application numbers"
    if site.get("main") not in numbers:
        return f"application site {sid}'s main application is not one of its numbers"
    if not _xy(site.get("centre_m")):
        return f"application site {sid} has no centre"
    for key in ("angle_deg", "base_m"):
        if not _num(site.get(key)):
            return f"application site {sid}'s {key} is not a finite number"
    for key in ("width_m", "depth_m", "height_m"):
        if not (_num(site.get(key)) and site[key] > 0):
            return f"application site {sid}'s {key} is not a positive number"
    if not _text(site.get("height_from")):
        return f"application site {sid} doesn't say where its height is from"
    apps = site.get("applications")
    if not (isinstance(apps, list) and apps and all(_entry_ok(a) for a in apps)
            and sorted(a["number"] for a in apps) == sorted(numbers)):
        return f"application site {sid}'s applications do not match its numbers"
    return None


def applications_problems(sites, date):
    """Plain-sentence problems with an "applications" list and the day it was fetched; empty means fine."""
    if not isinstance(sites, list):
        return ["The applications must be a list."]
    problems, ids, owner = [], set(), {}
    for i, site in enumerate(sites):
        problem = _application_problem(site)
        if problem:
            problems.append(problem[0].upper() + problem[1:] + ".")
            continue
        if site["id"] in ids:
            problems.append(f"Application site id {site['id']} is used twice.")
        ids.add(site["id"])
        for number in site["numbers"]:
            if owner.setdefault(number, i) != i:
                problems.append(f"Application {number} is in two sites.")
    if not (isinstance(date, str) and _DAY.fullmatch(date)):
        problems.append("The applications need the day they were fetched, as YYYY-MM-DD.")
    return problems


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
