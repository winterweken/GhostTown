"""OpenStreetMap via the Overpass API: one query per build, geometry inline (out geom)."""
import json
import urllib.parse
from collections import namedtuple

import shapely
from shapely.geometry import LineString, Point, Polygon

from ..net import SourceError

ENDPOINT = "https://overpass-api.de/api/interpreter"

Feature = namedtuple("Feature", "id tags geom")  # geom in lon/lat degrees


def build_query(lat, lon, radius_m, layers):
    around = f"(around:{radius_m:.0f},{lat:.7f},{lon:.7f})"
    lines = []
    if "buildings" in layers:
        for key in ("building", "building:part"):
            lines.append(f'way["{key}"]{around};')
            lines.append(f'relation["{key}"]["type"="multipolygon"]{around};')
    union = "\n".join("  " + line for line in lines)
    return f"[out:json][timeout:90];\n(\n{union}\n);\nout tags geom qt;"


def fetch(net, lat, lon, radius_m, layers, endpoint=ENDPOINT):
    data = urllib.parse.urlencode({"data": build_query(lat, lon, radius_m, layers)}).encode("ascii")
    return parse(net.get(endpoint or ENDPOINT, source="osm", data=data, check=check))


def check(body):
    _load(body)


def parse(body):
    doc = _load(body)
    out = []
    for el in doc.get("elements", []):
        try:
            geom = _geometry(el)
        except shapely.errors.GEOSException:
            continue  # one element the geometry library can't assemble must not cost the rest
        if geom is not None and not geom.is_empty:
            out.append(Feature(f"osm:{el['type']}:{el['id']}", el.get("tags", {}), geom))
    return out


def _load(body):
    try:
        doc = json.loads(body)
    except ValueError:
        raise SourceError("OpenStreetMap's Overpass server sent an answer that isn't JSON; try again in a minute.") from None
    remark = str(doc.get("remark") or "").strip()
    if remark:
        raise SourceError(f"OpenStreetMap's Overpass server didn't finish ({remark[:120]}); try again in a minute.")
    return doc


def _coords(points):
    return [(p["lon"], p["lat"]) for p in points if p]


def _geometry(el):
    kind = el.get("type")
    if kind == "node":
        return Point(el["lon"], el["lat"])
    if kind == "way":
        pts = _coords(el.get("geometry", []))
        if len(pts) >= 4 and pts[0] == pts[-1]:
            return Polygon(pts)
        return LineString(pts) if len(pts) >= 2 else None
    if kind == "relation" and el.get("tags", {}).get("type") == "multipolygon":
        outer, inner = [], []
        for m in el.get("members", []):
            pts = _coords(m.get("geometry") or []) if m.get("type") == "way" else []
            if len(pts) >= 2:
                (inner if m.get("role") == "inner" else outer).append(LineString(pts))
        if not outer:
            return None
        shell = shapely.union_all(shapely.get_parts(shapely.polygonize(outer)))
        if inner and not shell.is_empty:
            shell = shell.difference(shapely.union_all(shapely.get_parts(shapely.polygonize(inner))))
        return shell
    return None
