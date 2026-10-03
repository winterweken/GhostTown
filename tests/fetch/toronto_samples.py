"""GeoJSON answers shaped like the City of Toronto's ArcGIS layers, written in local metres around (LAT0, LON0)."""
import json

from ghosttown_fetch.frame import Frame

LAT0, LON0 = 43.65, -79.38
_F = Frame(LAT0, LON0)


def _ll(x, y):
    lon, lat = _F.to_lonlat(x, y)
    return [lon, lat]


def _feature(geometry, props):
    return {"type": "Feature", "geometry": geometry, "properties": props}


def polygon(pts, **props):
    ring = [_ll(x, y) for x, y in pts]
    ring.append(ring[0])
    return _feature({"type": "Polygon", "coordinates": [ring]}, props)


def square(x0, y0, size, **props):
    return polygon([(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size)], **props)


def line(pts, **props):
    return _feature({"type": "LineString", "coordinates": [_ll(x, y) for x, y in pts]}, props)


def point(x, y, **props):
    return _feature({"type": "Point", "coordinates": _ll(x, y)}, props)


def page(*features, more=False):
    doc = {"type": "FeatureCollection", "features": list(features)}
    if more:
        doc["properties"] = {"exceededTransferLimit": True}
    return json.dumps(doc).encode("utf-8")
