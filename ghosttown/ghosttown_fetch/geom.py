"""Small shapely helpers shared by the builders."""
import numpy as np
import shapely
import shapely.geometry
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

MIN_AREA_M2 = 1e-6
SEPARATE_M = 0.005  # rings that touch at a point are pulled this far apart
GRID_M = 0.001      # everything written out is on a 1 mm grid


def _snap(geom):
    """The geometry on the 1 mm grid, still valid. Coordinates are written out in millimetres, so the
    checks below must see what will be written: rounding afterwards can make near-touching rings cross."""
    try:
        return shapely.set_precision(geom, GRID_M)
    except shapely.errors.GEOSException:
        return geom


def polygons(geom):
    """Valid, non-empty polygonal parts of any geometry. Invalid input is repaired, and rings that
    touch at a point (a courtyard on the facade, two courtyards sharing a node) are separated,
    because a prism built from touching rings is not a closed solid."""
    if geom is None or geom.is_empty:
        return []
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    out = []
    for poly in _polygon_parts(_snap(geom)):
        out += _separate(poly)
    return out


def _polygon_parts(geom):
    out = []
    for part in shapely.get_parts(geom):
        if isinstance(part, Polygon):
            if not part.is_empty and part.area > MIN_AREA_M2:
                out.append(part)
        elif part.geom_type in ("MultiPolygon", "GeometryCollection"):
            out += _polygon_parts(part)
    return out


def _touching(poly):
    ring_list = [poly.exterior, *poly.interiors]
    if not all(r.is_simple for r in ring_list):
        return True
    return any(a.intersects(b) for i, a in enumerate(ring_list) for b in ring_list[i + 1:])


def _separate(poly):
    if not _touching(poly):
        return [poly]
    # Shrink each courtyard a few millimetres: it pulls back from the facade and from its neighbours.
    holes = [shapely.buffer(Polygon(r), -SEPARATE_M, join_style="mitre") for r in poly.interiors]
    fixed = Polygon(poly.exterior).difference(shapely.union_all(holes)) if holes else Polygon(poly.exterior)
    out = []
    for part in _polygon_parts(_snap(fixed)):
        if not _touching(part):
            out.append(part)
        elif Polygon(part.exterior).is_valid and part.exterior.is_simple:
            out.append(Polygon(part.exterior))  # last resort: keep the footprint, drop the courtyards
    return out


def rings(poly):
    """[outer CCW, *holes CW] as unclosed [x, y] lists rounded to 1 mm; None if the outer collapses."""
    poly = orient(poly, sign=1.0)
    outer = _ring(poly.exterior.coords)
    if outer is None:
        return None
    out = [outer]
    for interior in poly.interiors:
        hole = _ring(interior.coords)
        if hole is not None:
            out.append(hole)
    return out


def _ring(coords):
    pts = []
    for x, y in list(coords)[:-1]:
        p = [round(x, 3), round(y, 3)]
        if not pts or p != pts[-1]:
            pts.append(p)
    while len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    return pts if len(pts) >= 3 else None


def to_local(geom, frame):
    """A lon/lat geometry in the site's local metres."""
    return shapely.transform(geom, lambda c: np.column_stack(frame.to_local(c[:, 0], c[:, 1])))


def feature_geometry(feature):
    """The shapely geometry of a GeoJSON feature, or None when it has none or it can't be read."""
    g = (feature or {}).get("geometry")
    if not g:
        return None
    try:
        geom = shapely.geometry.shape(g)
    except (ValueError, TypeError, AttributeError, KeyError, IndexError, shapely.errors.GEOSException):
        return None
    return None if geom.is_empty else geom
