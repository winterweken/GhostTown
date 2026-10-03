"""Prism meshes for building solids. Pure functions over Blender's mathutils."""
import math

from mathutils import Vector
from mathutils.geometry import tessellate_polygon

MIN_EDGE_M = 0.003   # shorter edges are merged: Revit and most CAD importers refuse them
COLLINEAR_M = 0.002  # points this close to the line through their neighbours are dropped (no sliver caps)
MIN_AREA_M2 = 1e-6


def _area(ring):
    return 0.5 * sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))


def _off_line(p, a, b):
    """Distance from p to the line through a and b."""
    length = math.dist(a, b)
    if length == 0.0:
        return math.dist(p, a)
    return abs((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) / length


def _clean_ring(ring):
    pts = []
    for x, y in ring:
        p = (float(x), float(y))
        if not pts or math.dist(pts[-1], p) >= MIN_EDGE_M:
            pts.append(p)
    while len(pts) > 1 and math.dist(pts[0], pts[-1]) < MIN_EDGE_M:
        pts.pop()
    changed = True
    while changed and len(pts) > 3:
        changed = False
        for i in range(len(pts)):
            if _off_line(pts[i], pts[i - 1], pts[(i + 1) % len(pts)]) < COLLINEAR_M:
                del pts[i]
                changed = True
                break
    return pts if len(pts) >= 3 and abs(_area(pts)) > MIN_AREA_M2 else []


def is_closed(faces):
    """True when every edge is used exactly once in each direction: a closed, consistently wound mesh."""
    directed = set()
    for f in faces:
        for i in range(len(f)):
            edge = (f[i], f[(i + 1) % len(f)])
            if edge in directed:
                return False
            directed.add(edge)
    return all((b, a) in directed for a, b in directed)


def clean_rings(rings):
    """[outer CCW, *holes CW] with sub-3 mm edges merged; [] when the outer ring collapses."""
    if not rings:
        return []
    outer = _clean_ring(rings[0])
    if not outer:
        return []
    if _area(outer) < 0:
        outer.reverse()
    out = [outer]
    for ring in rings[1:]:
        hole = _clean_ring(ring)
        if hole:
            if _area(hole) > 0:
                hole.reverse()
            out.append(hole)
    return out


def prism(rings, z0, z1):
    """A closed vertical prism. Caps are triangles (bottom reversed), walls are one quad per edge;
    a CCW outer ring and CW holes both give outward-facing walls."""
    flat = [p for ring in rings for p in ring]
    n = len(flat)
    verts = [(x, y, z0) for x, y in flat] + [(x, y, z1) for x, y in flat]
    tris = tessellate_polygon([[Vector((x, y, 0.0)) for x, y in ring] for ring in rings])
    faces = [(a, c, b) for a, b, c in tris]
    faces += [(a + n, b + n, c + n) for a, b, c in tris]
    start = 0
    for ring in rings:
        m = len(ring)
        for k in range(m):
            a, b = start + k, start + (k + 1) % m
            faces.append((a, b, b + n, a + n))
        start += m
    return verts, faces
