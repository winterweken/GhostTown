"""Is the site in the City of Toronto? The centre decides; the City's own boundary layer answers."""
import json

import numpy as np
import shapely
from shapely.geometry import Point

from .geom import feature_geometry
from .net import SourceError
from .sources import arcgis

BOUNDARY = ("cot_geospatial27", 40)            # "Toronto Land And Water Area": 14 parts (land, water, islands)
TORONTO_BOX = (43.55, 43.89, -79.67, -79.08)  # lat_min, lat_max, lon_min, lon_max, with a margin


def near_toronto(lat, lon):
    lat_min, lat_max, lon_min, lon_max = TORONTO_BOX
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def boundary_params():
    return {"where": "1=1", "outFields": "AREA_NAME", "returnGeometry": "true", "outSR": "4326",
            "f": "geojson", "maxAllowableOffset": "0.0002", "geometryPrecision": "6", "orderByFields": "OBJECTID"}


EMPTY = "The City of Toronto boundary came back empty; try again in a minute."


def _has_features(body):
    """An empty answer must not be cached: every Toronto site would look like it is outside the city."""
    arcgis.check(body)
    if not json.loads(body).get("features"):
        raise SourceError(EMPTY)


def fetch_boundary(net):
    parts = []
    for feature in arcgis.query(net, *BOUNDARY, boundary_params(), accept=_has_features):
        geom = feature_geometry(feature)
        if geom is not None:
            geom = shapely.make_valid(geom)
            parts += [p for p in shapely.get_parts(geom) if p.geom_type in ("Polygon", "MultiPolygon")]
    if not parts:
        raise SourceError(EMPTY)
    return shapely.union_all(parts)


def classify(boundary, frame, radius_m):
    """("toronto" | "world", crosses): crosses is True when the site circle reaches over the city line."""
    centre = Point(frame.lon0, frame.lat0)
    circle = shapely.transform(Point(0.0, 0.0).buffer(radius_m, quad_segs=16),
                               lambda c: np.column_stack(frame.to_lonlat(c[:, 0], c[:, 1])))
    if boundary.contains(centre):
        return "toronto", not boundary.contains(circle)
    return "world", bool(boundary.intersects(circle))
