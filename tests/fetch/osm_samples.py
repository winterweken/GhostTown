"""Tiny hand-made Overpass answers. Coordinates are written in local metres around (LAT0, LON0)."""
import json

from ghosttown_fetch.frame import Frame

LAT0, LON0 = 43.65, -79.38
_F = Frame(LAT0, LON0)


def _ll(x, y):
    lon, lat = _F.to_lonlat(x, y)
    return {"lat": lat, "lon": lon}


def square(x0, y0, size):
    return [(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size), (x0, y0)]


def way(wid, pts, tags):
    return {"type": "way", "id": wid, "geometry": [_ll(x, y) for x, y in pts], "tags": dict(tags)}


def node(nid, x, y, tags):
    return {"type": "node", "id": nid, **_ll(x, y), "tags": dict(tags)}


def relation(rid, outers, inners, tags):
    members = [{"type": "way", "ref": 1000 + i, "role": "outer", "geometry": [_ll(x, y) for x, y in pts]}
               for i, pts in enumerate(outers)]
    members += [{"type": "way", "ref": 2000 + i, "role": "inner", "geometry": [_ll(x, y) for x, y in pts]}
                for i, pts in enumerate(inners)]
    return {"type": "relation", "id": rid, "members": members, "tags": {"type": "multipolygon", **tags}}


def body(*elements, remark=None):
    doc = {"version": 0.6, "elements": list(elements)}
    if remark:
        doc["remark"] = remark
    return json.dumps(doc).encode("utf-8")
