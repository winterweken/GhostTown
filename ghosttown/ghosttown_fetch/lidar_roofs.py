"""Building solids whose tops follow Ontario's LiDAR, as closed meshes in one numpy file.

Buildings from the City of Toronto's 3D Massing model keep its massing: the City publishes the same
flat-topped block massing as SketchUp, AutoCAD and Multipatch files, which architects work against, so
LiDAR roofs are for every other building (OpenStreetMap elsewhere in Ontario, and the City's older
outlines when the model can't be had).

Each solid's outline is cut by a grid at the LiDAR cell and triangulated: whole cells are two triangles,
cut cells are triangulated where the outline crosses them (the ground layout's method). Points on the
outline sample the LiDAR half a cell inside, so eaves don't pick up the ground or trees beside the
building. Walls run from the solid's base up to the roof along the roof's own edge, courtyards
included, and a flat bottom closes the mesh, so every solid is closed by construction. A solid that
can't be made that way keeps its flat top. Heights are the solid's own ground plus the LiDAR's height
above ground, so the roofs sit on Ghost Town's terrain.
"""
import io
import math

import numpy as np
import shapely
from shapely.geometry import Polygon

from . import BUILDING_KINDS
from .buildings import SINK_M
from .cache import atomic_write

FILE = "lidar_roofs.npz"
CITY_MODEL = "toronto:massing:"  # element ids of buildings from the City's 3D Massing model
WELD_M = 0.003         # points closer than this are one point
EXACT_M = 1e-6         # a point this close to a grid node is that node
CITY_ABOVE_M = 8.0     # City buildings: LiDAR this far above the City's height is a crane or a tree...
CITY_GROUND_M = 2.0    # ...and this close to the ground is a gap; both take the City's height
OTHER_RANGE_M = (2.0, 400.0)  # other buildings keep LiDAR heights within this range above the ground
MIN_WALL_M = 0.05      # a roof point never comes closer than this to the solid's base
COVERAGE_STEP_M = 2.0
MIN_COVERAGE = 0.05    # less LiDAR than this under the footprints counts as none


def _snap(v, cell):
    k = round(v / cell)
    return k * cell if abs(v - k * cell) < WELD_M else v


def _densify(ring, cell):
    """The ring with points within 3 mm of a grid line moved onto it, and a point wherever it crosses a
    grid line, so neighbouring cells cut it at the same points. None when it collapses."""
    pts = [(_snap(float(x), cell), _snap(float(y), cell)) for x, y in ring]
    out = []
    for k in range(len(pts)):
        (x0, y0), (x1, y1) = pts[k], pts[(k + 1) % len(pts)]
        if not out or math.dist(out[-1], (x0, y0)) >= WELD_M:
            out.append((x0, y0))
        length = math.hypot(x1 - x0, y1 - y0)
        cuts = []
        for axis, (a0, a1) in enumerate(((x0, x1), (y0, y1))):
            if a0 == a1:
                continue
            lo, hi = sorted((a0, a1))
            for m in range(math.floor(lo / cell) + 1, math.ceil(hi / cell)):
                t = (m * cell - a0) / (a1 - a0)
                if axis == 0:
                    cuts.append((t, (m * cell, _snap(y0 + t * (y1 - y0), cell))))
                else:
                    cuts.append((t, (_snap(x0 + t * (x1 - x0), cell), m * cell)))
        for t, p in sorted(cuts):
            if WELD_M <= t * length <= length - WELD_M and math.dist(out[-1], p) >= WELD_M:
                out.append(p)
    while len(out) > 1 and math.dist(out[0], out[-1]) < WELD_M:
        out.pop()
    return out if len(out) >= 3 else None


class _Table:
    """The roof's vertex table: grid nodes by (i, j), other points welded within WELD_M."""

    def __init__(self, i0, j0, ni, nj, cell):
        self.i0, self.j0, self.cell = i0, j0, cell
        self.node = np.full((ni + 1, nj + 1), -1, dtype=np.int64)
        self.parts = []
        self.count = 0
        self.other_xy = np.empty((0, 2))
        self.other_ids = np.empty(0, dtype=np.int64)

    def _add(self, xy):
        ids = np.arange(self.count, self.count + len(xy))
        self.parts.append(xy)
        self.count += len(xy)
        return ids

    def nodes(self, i, j):
        ids = self.node[i - self.i0, j - self.j0]
        fresh = ids < 0
        if fresh.any():
            keys = np.unique(np.stack([i[fresh], j[fresh]], axis=1), axis=0)
            self.node[keys[:, 0] - self.i0, keys[:, 1] - self.j0] = self._add(keys * self.cell)
            ids = self.node[i - self.i0, j - self.j0]
        return ids

    def points(self, xy):
        xy = np.asarray(xy, dtype=float).reshape(-1, 2)
        f = xy / self.cell
        on_node = (np.abs(f - np.round(f)) * self.cell < EXACT_M).all(axis=1)
        ids = np.full(len(xy), -1, dtype=np.int64)
        if on_node.any():
            ij = np.round(f[on_node]).astype(np.int64)
            ids[on_node] = self.nodes(ij[:, 0], ij[:, 1])
        rest = np.flatnonzero(~on_node)
        if rest.size and self.other_ids.size:
            tree = shapely.STRtree(shapely.points(self.other_xy))
            found, hit = tree.query_nearest(shapely.points(xy[rest]), max_distance=WELD_M, all_matches=False)
            ids[rest[found]] = self.other_ids[hit]
        new = np.flatnonzero(ids < 0)
        if new.size:
            _, first, inverse = np.unique(np.round(xy[new] * 1e4).astype(np.int64), axis=0,
                                          return_index=True, return_inverse=True)
            fresh = self._add(xy[new][first])
            self.other_xy = np.concatenate([self.other_xy, xy[new][first]])
            self.other_ids = np.concatenate([self.other_ids, fresh])
            ids[new] = fresh[inverse.ravel()]
        return ids

    def coords(self):
        return np.concatenate(self.parts) if self.parts else np.empty((0, 2))


def _triangle_coords(geoms):
    """(K, 3, 2): the corners of every triangle in the constrained Delaunay triangulations of `geoms`."""
    tris = shapely.get_parts(shapely.get_parts(shapely.constrained_delaunay_triangles(geoms)))
    tris = tris[shapely.get_type_id(tris) == 3]
    return shapely.get_coordinates(tris).reshape(-1, 4, 2)[:, :3, :]


def _wind(tris, xy, up=True):
    """Triangles counter-clockwise seen from above (up) or from below."""
    a, b, c = xy[tris[:, 0]], xy[tris[:, 1]], xy[tris[:, 2]]
    cross = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1])
    flip = cross < 0 if up else cross > 0
    return np.where(flip[:, None], tris[:, [0, 2, 1]], tris)


def _loops(tris, n):
    """The surface's edge as closed loops of vertex ids (the outline counter-clockwise, courtyards
    clockwise), or None when it isn't a clean surface (an edge used twice, or two loops meeting)."""
    a = tris.ravel()
    b = np.roll(tris, -1, axis=1).ravel()
    key = a * n + b
    if np.unique(key).size != key.size:
        return None
    lone = ~np.isin(b * n + a, key)
    start, end = a[lone], b[lone]
    if np.unique(start).size != start.size:
        return None
    following = dict(zip(start.tolist(), end.tolist()))
    loops, seen = [], set()
    for s in start.tolist():
        if s in seen:
            continue
        loop, v = [], s
        while v not in seen:
            seen.add(v)
            loop.append(v)
            v = following.get(v)
            if v is None:
                return None
        if v != s:
            return None
        loops.append(loop)
    return loops


def _area(xy):
    x, y = xy[:, 0], xy[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def closed(faces):
    """True when every edge is used once in each direction: a closed, consistently wound mesh."""
    if len(faces) == 0:
        return False
    n = int(faces.max()) + 1
    a = faces.ravel().astype(np.int64)
    b = np.roll(faces, -1, axis=1).ravel().astype(np.int64)
    key = a * n + b
    return np.unique(key).size == key.size and bool(np.isin(b * n + a, key).all())


def _heights(xy, edge, poly, z0, z1, ground, heights, cell, city):
    """Roof z at every top vertex: edge points sample half a cell inside, then the outlier rules."""
    sample = xy.copy()
    shrunk = poly.buffer(-cell / 2)
    if shrunk.is_empty:
        p = poly.point_on_surface()
        sample[edge] = (p.x, p.y)
    else:
        sample[edge] = shapely.get_coordinates(shapely.shortest_line(shapely.points(xy[edge]), shrunk))[1::2]
    above = heights.sample(sample[:, 0], sample[:, 1])
    own = z1 - ground
    if city:
        keep = np.isfinite(above) & (above <= own + CITY_ABOVE_M) & (above >= CITY_GROUND_M)
        above = np.where(keep, above, own)
    else:
        above = np.where(np.isfinite(above), np.clip(above, *OTHER_RANGE_M), own)
    return np.maximum(ground + above, z0 + MIN_WALL_M)


def roof_solid(rings, z0, z1, ground, heights, cell, city):
    """(verts N×3, faces M×3, interior N) of a closed solid whose top follows `heights` (anything with
    sample(xs, ys) -> heights above ground, NaN where unknown), or None. `interior` marks roof
    vertices off the outline. `city` picks the City's outlier rule over the general one."""
    dense = [_densify(r, cell) for r in rings]
    if dense[0] is None:
        return None
    poly = Polygon(dense[0], [r for r in dense[1:] if r is not None])
    if not poly.is_valid or poly.area <= 0:
        return None

    minx, miny, maxx, maxy = poly.bounds
    i0, j0 = math.floor(minx / cell), math.floor(miny / cell)
    i1, j1 = math.ceil(maxx / cell), math.ceil(maxy / cell)
    ii, jj = np.meshgrid(np.arange(i0, i1), np.arange(j0, j1), indexing="ij")
    ii, jj = ii.ravel(), jj.ravel()
    boxes = shapely.box(ii * cell, jj * cell, (ii + 1) * cell, (jj + 1) * cell)
    shapely.prepare(poly)
    whole = shapely.contains_properly(poly, boxes)
    cut = ~whole & shapely.intersects(poly, boxes)

    table = _Table(i0, j0, i1 - i0, j1 - j0, cell)
    for ring in dense:
        if ring is not None:
            table.points(ring)
    parts = []
    i, j = ii[whole], jj[whole]
    if i.size:
        a, b, c, d = table.nodes(i, j), table.nodes(i + 1, j), table.nodes(i + 1, j + 1), table.nodes(i, j + 1)
        parts += [np.stack([a, b, c], axis=1), np.stack([a, c, d], axis=1)]
    if cut.any():
        corners = _triangle_coords(shapely.intersection(boxes[cut], poly))
        parts.append(table.points(corners.reshape(-1, 2)).reshape(-1, 3))
    if not parts:
        return None
    top = np.concatenate(parts)
    top = top[(top[:, 0] != top[:, 1]) & (top[:, 1] != top[:, 2]) & (top[:, 0] != top[:, 2])]
    xy = table.coords()
    n = len(xy)
    top = _wind(top, xy)

    loops = _loops(top, n)
    if not loops:
        return None
    edge = np.concatenate([np.asarray(loop) for loop in loops])
    outer = [loop for loop in loops if _area(xy[loop]) > 0]
    holes = [loop for loop in loops if _area(xy[loop]) < 0]
    if len(outer) != 1:
        return None
    base = Polygon(xy[outer[0]], [xy[h] for h in holes])
    if not base.is_valid:
        return None

    z = _heights(xy, edge, poly, z0, z1, ground, heights, cell, city)
    bottom_of = np.full(n, -1, dtype=np.int64)
    bottom_of[edge] = n + np.arange(len(edge))
    verts = np.concatenate([np.column_stack([xy, z]), np.column_stack([xy[edge], np.full(len(edge), float(z0))])])
    faces = [top]
    for loop in loops:
        a = np.asarray(loop)
        b = np.roll(a, -1)
        faces += [np.stack([bottom_of[a], bottom_of[b], b], axis=1), np.stack([bottom_of[a], b, a], axis=1)]
    corners = _triangle_coords(base).reshape(-1, 2)
    tree = shapely.STRtree(shapely.points(xy[edge]))
    found, hit = tree.query_nearest(shapely.points(corners), max_distance=EXACT_M, all_matches=False)
    if len(found) != len(corners):
        return None
    ids = np.empty(len(corners), dtype=np.int64)
    ids[found] = n + hit
    faces.append(_wind(ids.reshape(-1, 3), verts[:, :2], up=False))
    faces = np.concatenate(faces)
    if not closed(faces):
        return None
    interior = np.zeros(len(verts), dtype=bool)
    interior[:n] = True
    interior[edge] = False
    return verts, faces, interior


def prism(rings, z0, z1):
    """(verts, faces, interior) of the flat-topped solid, for when the roof can't be built; or None."""
    for use in (rings, rings[:1]):
        poly = Polygon(use[0], use[1:])
        if not poly.is_valid:
            continue
        xy = np.array([p for ring in use for p in ring], dtype=float)
        n = len(xy)
        corners = _triangle_coords(poly).reshape(-1, 2)
        tree = shapely.STRtree(shapely.points(xy))
        found, hit = tree.query_nearest(shapely.points(corners), max_distance=EXACT_M, all_matches=False)
        if len(found) != len(corners):
            continue
        tri = np.empty(len(corners), dtype=np.int64)
        tri[found] = hit
        tri = tri.reshape(-1, 3)
        faces = [_wind(tri, xy, up=False), _wind(tri, xy) + n]
        start = 0
        for ring in use:
            a = start + np.arange(len(ring))
            b = start + (np.arange(len(ring)) + 1) % len(ring)
            faces += [np.stack([a, b, b + n], axis=1), np.stack([a, b + n, a + n], axis=1)]
            start += len(ring)
        faces = np.concatenate(faces)
        verts = np.concatenate([np.column_stack([xy, np.full(n, float(z0))]), np.column_stack([xy, np.full(n, float(z1))])])
        if closed(faces):
            return verts, faces, np.zeros(2 * n, dtype=bool)
    return None


def wanted(element):
    """True for a building that gets a LiDAR roof: any building not from the City's 3D Massing model."""
    return element["kind"] in BUILDING_KINDS and not element["id"].startswith(CITY_MODEL)


def coverage(heights, elements, step_m=COVERAGE_STEP_M):
    """The share of points every `step_m` inside the wanted buildings' footprints where the LiDAR has a
    height."""
    outlines = [Polygon(s["rings"][0]) for el in elements if wanted(el) for s in el["solids"]]
    outlines = [p for p in outlines if p.is_valid and p.area > 0]
    if not outlines:
        return 0.0
    shape = shapely.union_all(outlines)
    minx, miny, maxx, maxy = shape.bounds
    gx, gy = np.meshgrid(np.arange(minx, maxx, step_m), np.arange(miny, maxy, step_m))
    gx, gy = gx.ravel(), gy.ravel()
    inside = shapely.contains_xy(shape, gx, gy)
    xs, ys = gx[inside], gy[inside]
    if xs.size == 0:
        xs, ys = shapely.get_coordinates(shapely.point_on_surface(outlines)).T
    return float(np.isfinite(heights.sample(xs, ys)).mean())


def build(elements, heights, cell):
    """(arrays, counts) for every wanted building, or (None, counts) when there is none. Arrays follow
    the npz layout: verts, faces (indices within each building), face_kind (index into kinds), interior,
    building_ids, vert_start and face_start (each building's slice), kinds. counts: buildings, triangles
    and flat (solids that kept their flat top)."""
    verts, faces, face_kind, interior, ids = [], [], [], [], []
    vert_start, face_start = [0], [0]
    flat = 0
    for el in elements:
        if not wanted(el):
            continue
        nv = nf = 0
        for s in el["solids"]:
            ground = s.get("ground", s["z0"] + SINK_M)
            city = s["height_source"].startswith("toronto")
            made = roof_solid(s["rings"], s["z0"], s["z1"], ground, heights, cell, city)
            if made is None:
                flat += 1
                made = prism(s["rings"], s["z0"], s["z1"])
                if made is None:
                    continue
            v, f, inner = made
            verts.append(v.astype(np.float32))
            faces.append((f + nv).astype(np.int32))
            face_kind.append(np.full(len(f), BUILDING_KINDS.index(s["kind"]), dtype=np.uint8))
            interior.append(inner.astype(np.uint8))
            nv += len(v)
            nf += len(f)
        if nf:
            ids.append(el["id"])
            vert_start.append(vert_start[-1] + nv)
            face_start.append(face_start[-1] + nf)
    counts = {"buildings": len(ids), "triangles": face_start[-1], "flat": flat}
    if not ids:
        return None, counts
    arrays = {
        "verts": np.concatenate(verts), "faces": np.concatenate(faces), "face_kind": np.concatenate(face_kind),
        "interior": np.concatenate(interior), "building_ids": np.array(ids, dtype=str),
        "vert_start": np.array(vert_start, dtype=np.int64), "face_start": np.array(face_start, dtype=np.int64),
        "kinds": np.array(BUILDING_KINDS, dtype=str),
    }
    return arrays, counts


def write(path, arrays):
    """Save the arrays as one compressed npz, so a half-written file is never read."""
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **arrays)
    atomic_write(path, buffer.getvalue())
