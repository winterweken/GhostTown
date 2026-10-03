"""Parcel (lot) boundaries as lines draped just above the ground, clipped to the site circle."""
import numpy as np
import shapely
from shapely.geometry import MultiLineString, Point

from . import context as ctx
from .geom import feature_geometry, polygons, to_local

DRAPE_M = 0.15
STEP_M = 2.0
MIN_PIECE_M = 0.003


def _name(props):
    number, street = props.get("ADDRESS_NUMBER"), props.get("LINEAR_NAME_FULL")
    return f"{number} {street}" if number and street else ""


def from_toronto(features, frame, terrain, radius_m):
    site = Point(0.0, 0.0).buffer(radius_m, quad_segs=64)
    out = []
    for feature in features:
        props = feature.get("properties") or {}
        geom = feature_geometry(feature)
        if geom is None:
            continue
        lines = []
        for poly in polygons(to_local(geom, frame)):
            clipped = poly.boundary.intersection(site)
            parts = [p for p in shapely.get_parts(clipped) if p.geom_type == "LineString"]
            if not parts:
                continue
            merged = shapely.line_merge(MultiLineString(parts))
            for part in shapely.get_parts(merged):
                if part.length < MIN_PIECE_M:
                    continue
                xy = shapely.get_coordinates(shapely.segmentize(part, STEP_M))
                zs = np.asarray(terrain.z(xy[:, 0], xy[:, 1]), dtype=float) + DRAPE_M
                lines.append({"kind": "parcel",
                              "pts": [[round(float(x), 3), round(float(y), 3), round(float(z), 3)]
                                      for (x, y), z in zip(xy, zs)]})
        if lines:
            pid = props.get("PARCELID") or props.get("OBJECTID")
            out.append(ctx.element(f"toronto:parcel:{pid}", "parcel", name=_name(props), lines=lines))
    return out
