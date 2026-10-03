"""One crack-free ground surface over the site circle.

Per-kind polygons are laid out without overlaps in priority order (water > road > sidewalk >
parking > rail > green; whatever is left is plain ground). Every outline, the circle edge and a
regular grid are noded together and polygonised, so neighbouring faces share their edges exactly
and the grid lets the terrain show through. Faces are triangulated into one vertex table, welded
within 3 mm, and draped on the terrain. Each water body is flattened to its own shoreline level."""
import math

import numpy as np
import shapely
from shapely.geometry import LineString, Point

from . import context as ctx

PRIORITY = ("water", "road", "sidewalk", "parking", "rail", "green")
ORDER = PRIORITY + ("ground",)
WELD_M = 0.003
WATER_DROP_M = 0.1
WATER_PERCENTILE = 10
QUAD_SEGS = 64
MIN_FACE_M2 = 1e-6


def cell_size(radius_m):
    return min(12.0, max(2.0, radius_m / 80.0))


def disc(radius_m):
    return Point(0.0, 0.0).buffer(radius_m, quad_segs=QUAD_SEGS)


def _polygonal(geom):
    """Polygon parts of any geometry (overlays can leave stray lines and points)."""
    out = []
    for part in shapely.get_parts(geom):
        if part.geom_type == "Polygon":
            if part.area > MIN_FACE_M2:
                out.append(part)
        elif part.geom_type in ("MultiPolygon", "GeometryCollection"):
            out += _polygonal(part)
    return out


def layout(pieces, radius_m, *, include_ground=True):
    """{kind: [Polygon]} in local metres -> [(kind, Polygon)] faces covering the disc exactly once."""
    site = disc(radius_m)
    remaining = site
    claimed = []
    for kind in PRIORITY:
        geoms = [g for g in pieces.get(kind, ()) if g is not None and not g.is_empty]
        if not geoms or remaining.is_empty:
            continue
        area = shapely.union_all(_polygonal(shapely.intersection(shapely.union_all(geoms), remaining)))
        if area.is_empty:
            continue
        claimed.append((kind, area))
        remaining = shapely.union_all(_polygonal(shapely.difference(remaining, area)))
    claimed.append(("ground", remaining))

    cell = cell_size(radius_m)
    n = math.ceil(radius_m / cell) + 1
    reach = n * cell
    ticks = [i * cell for i in range(-n, n + 1)]
    lines = [LineString([(t, -reach), (t, reach)]) for t in ticks]
    lines += [LineString([(-reach, t), (reach, t)]) for t in ticks]
    edges = [area.boundary for _, area in claimed if not area.is_empty] + [site.boundary] + lines
    noded = shapely.union_all(edges, grid_size=0.001)
    faces = [f for f in shapely.get_parts(shapely.polygonize(shapely.get_parts(noded))) if f.area > MIN_FACE_M2]
    if not faces:
        return []
    probes = shapely.point_on_surface(np.array(faces, dtype=object))
    labels = [None] * len(faces)
    for kind, area in claimed:
        if area.is_empty:
            continue
        shapely.prepare(area)
        for i in np.flatnonzero(shapely.contains(area, probes)):
            if labels[i] is None:
                labels[i] = kind
    inside = shapely.contains(site, probes)
    out = []
    for i, face in enumerate(faces):
        kind = labels[i] or ("ground" if inside[i] else None)  # mm slivers on a seam count as plain ground
        if kind is not None and (include_ground or kind != "ground"):
            out.append((kind, face))
    return out


class _Welder:
    """One vertex table: points closer than `dist` share an index (greedy, hashed on a `dist` grid)."""

    def __init__(self, dist):
        self.dist = dist
        self.xs, self.ys = [], []
        self._cells = {}

    def index(self, x, y):
        x, y = round(float(x), 3), round(float(y), 3)
        cx, cy = math.floor(x / self.dist), math.floor(y / self.dist)
        d2 = self.dist * self.dist
        for i in (cx - 1, cx, cx + 1):
            for j in (cy - 1, cy, cy + 1):
                for k in self._cells.get((i, j), ()):
                    if (self.xs[k] - x) ** 2 + (self.ys[k] - y) ** 2 < d2:
                        return k
        k = len(self.xs)
        self.xs.append(x)
        self.ys.append(y)
        self._cells.setdefault((cx, cy), []).append(k)
        return k

    def twice_area(self, a, b, c):
        xs, ys = self.xs, self.ys
        return (xs[b] - xs[a]) * (ys[c] - ys[a]) - (xs[c] - xs[a]) * (ys[b] - ys[a])


def _triangulate(geoms):
    try:
        return list(shapely.constrained_delaunay_triangles(np.array(geoms, dtype=object)))
    except shapely.errors.GEOSException:
        out = []
        for g in geoms:
            try:
                out.append(shapely.constrained_delaunay_triangles(g))
            except shapely.errors.GEOSException:
                out.append(None)
        return out


def mesh(faces, terrain):
    """[(kind, Polygon)] -> {kind: {"verts", "faces"}}, counter-clockwise from above, one welded vertex table."""
    if not faces:
        return {}
    welder = _Welder(WELD_M)
    tris = {}
    for (kind, _), collection in zip(faces, _triangulate([f for _, f in faces])):
        if collection is None:
            continue
        for tri in shapely.get_parts(collection):
            idx = [welder.index(x, y) for x, y in shapely.get_coordinates(tri)[:3]]
            if len(set(idx)) < 3:
                continue
            area2 = welder.twice_area(*idx)
            if abs(area2) < 2 * MIN_FACE_M2:
                continue
            tris.setdefault(kind, []).append(tuple(idx) if area2 > 0 else (idx[0], idx[2], idx[1]))
    xs, ys = np.array(welder.xs), np.array(welder.ys)
    zs = np.asarray(terrain.z(xs, ys), dtype=float).copy()
    if "water" in tris:
        _flatten_water(tris, zs)
    return {kind: _compact(t, xs, ys, zs) for kind, t in tris.items()}


def _flatten_water(tris, zs):
    """Each connected water body lies flat just below its own shoreline: the 10th percentile of the
    terrain at the vertices it shares with the land. Shore vertices keep the terrain height."""
    water = tris["water"]
    shore = {i for kind, t in tris.items() if kind != "water" for tri in t for i in tri}
    parent = {}

    def find(i):
        parent.setdefault(i, i)
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b, c in water:
        parent[find(a)] = find(b)
        parent[find(b)] = find(c)
    bodies = {}
    for tri in water:
        bodies.setdefault(find(tri[0]), set()).update(tri)
    for verts in bodies.values():
        on_shore = [zs[i] for i in verts if i in shore]
        level = float(np.percentile(on_shore or [zs[i] for i in verts], WATER_PERCENTILE)) - WATER_DROP_M
        for i in verts:
            if i not in shore:
                zs[i] = level


def _compact(tris, xs, ys, zs):
    used = sorted({i for tri in tris for i in tri})
    remap = {old: new for new, old in enumerate(used)}
    verts = [[round(float(xs[i]), 3), round(float(ys[i]), 3), round(float(zs[i]), 3)] for i in used]
    return {"verts": verts, "faces": [[remap[a], remap[b], remap[c]] for a, b, c in tris]}


def elements(faces, terrain):
    meshes = mesh(faces, terrain)
    return [ctx.element(f"ground:{kind}", kind, meshes=[{"kind": kind, **meshes[kind]}])
            for kind in ORDER if kind in meshes]
