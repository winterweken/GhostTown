"""Line of sight against Ghost Town's buildings. They are vertical prisms, so a ray can only be stopped by
a wall: each test is a 2D segment crossing plus a height check at the crossing. Rays that would come down
onto a roof are not stopped; street cameras rarely look down."""
import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

EPS = 1e-9
SEGMENT_M = 50.0   # rays are tested in pieces this long, nearest first


def _polygon(rings):
    """A solid's footprint: the ring with the largest area is the outline, rings inside it are courtyards.
    Exterior counter-clockwise, courtyards clockwise."""
    polys = sorted((Polygon(r) for r in rings if len(r) >= 3), key=lambda p: -abs(p.area))
    if not polys or abs(polys[0].area) <= 0:
        return None
    outer = Polygon(polys[0].exterior.coords)
    holes = [p.exterior.coords for p in polys[1:] if outer.contains(p)]
    poly = Polygon(outer.exterior.coords, holes)
    if not poly.is_valid:
        fixed = [g for g in shapely.get_parts(shapely.make_valid(poly)) if g.geom_type == "Polygon"]
        if not fixed:
            return None
        poly = max(fixed, key=lambda g: g.area)
    return orient(poly, sign=1.0)


class Scene:
    def __init__(self, buildings):
        self.ids = [b["id"] for b in buildings]
        polys, owners, z0s, z1s = [], [], [], []
        A, B, N, wz0, wz1, wown = [], [], [], [], [], []
        for bi, b in enumerate(buildings):
            for s in b["solids"]:
                poly = _polygon(s["rings"])
                if poly is None:
                    continue
                z0, z1 = float(s["z0"]), float(s["z1"])
                polys.append(poly)
                owners.append(bi)
                z0s.append(z0)
                z1s.append(z1)
                for ring in (poly.exterior, *poly.interiors):
                    pts = np.asarray(ring.coords)[:, :2]
                    for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
                        length = float(np.hypot(bx - ax, by - ay))
                        if length < 1e-6:
                            continue
                        A.append((ax, ay))
                        B.append((bx, by))
                        N.append(((by - ay) / length, -(bx - ax) / length))   # right of travel = outside
                        wz0.append(z0)
                        wz1.append(z1)
                        wown.append(bi)
        self.solids = polys
        self.solid_owner = np.asarray(owners, dtype=int)
        self.solid_z0 = np.asarray(z0s, dtype=float)
        self.solid_z1 = np.asarray(z1s, dtype=float)
        self.A = np.asarray(A, dtype=float).reshape(-1, 2)
        self.B = np.asarray(B, dtype=float).reshape(-1, 2)
        self.N = np.asarray(N, dtype=float).reshape(-1, 2)
        self.wall_z0 = np.asarray(wz0, dtype=float)
        self.wall_z1 = np.asarray(wz1, dtype=float)
        self.wall_owner = np.asarray(wown, dtype=int)
        self._walls = shapely.STRtree(shapely.linestrings(np.stack([self.A, self.B], 1))) if len(self.A) else None
        self._solids = shapely.STRtree(polys) if polys else None
        self.base_z = np.full(len(self.ids), np.inf)
        for bi, z0 in zip(self.solid_owner, self.solid_z0):
            self.base_z[bi] = min(self.base_z[bi], z0)

    def first_hit(self, origins, dirs, max_dist):
        """(owner, dist) per ray: the building index of the first wall each ray meets within max_dist
        metres (-1 for none) and the distance along the ray (inf for none). dirs are unit 3D vectors;
        one origin may serve every ray; max_dist is one number or one per ray."""
        D = np.asarray(dirs, dtype=float).reshape(-1, 3)
        n = len(D)
        O = np.asarray(origins, dtype=float).reshape(-1, 3)
        if len(O) == 1 and n > 1:
            O = np.repeat(O, n, axis=0)
        T = np.broadcast_to(np.asarray(max_dist, dtype=float), (n,))
        owner = np.full(n, -1, dtype=int)
        dist = np.full(n, np.inf)
        if self._walls is None or n == 0:
            return owner, dist
        live = np.nonzero(np.hypot(D[:, 0], D[:, 1]) > EPS)[0]   # vertical rays never meet a wall
        top = float(self.wall_z1.max())
        t0 = 0.0
        while len(live):
            # The rays go out in SEGMENT_M pieces, nearest first: a short piece's box meets only the walls
            # near it, so this costs far less than one query with the whole ray, and the first hit is the same.
            t1 = t0 + SEGMENT_M
            start = O[live, :2] + D[live, :2] * t0
            end = O[live, :2] + D[live, :2] * np.minimum(t1, T[live])[:, None]
            rays_i, walls_i = self._walls.query(shapely.linestrings(np.stack([start, end], 1)))   # boxes only
            r = live[rays_i]
            p0, d2 = O[r, :2], D[r, :2]
            a = self.A[walls_i]
            e = self.B[walls_i] - a
            denom = d2[:, 0] * e[:, 1] - d2[:, 1] * e[:, 0]
            ap = a - p0
            safe = np.where(np.abs(denom) > EPS, denom, 1.0)
            t = (ap[:, 0] * e[:, 1] - ap[:, 1] * e[:, 0]) / safe
            s = (ap[:, 0] * d2[:, 1] - ap[:, 1] * d2[:, 0]) / safe
            z = O[r, 2] + t * D[r, 2]
            good = ((np.abs(denom) > EPS) & (t > max(t0, 1e-6)) & (t <= np.minimum(t1, T[r]))
                    & (s >= -1e-9) & (s <= 1 + 1e-9)
                    & (z >= self.wall_z0[walls_i] - 1e-6) & (z <= self.wall_z1[walls_i] + 1e-6))
            r, t, w = r[good], t[good], walls_i[good]
            order = np.lexsort((t, r))
            r, t, w = r[order], t[order], w[order]
            first = np.ones(len(r), dtype=bool)
            first[1:] = r[1:] != r[:-1]
            owner[r[first]] = self.wall_owner[w[first]]
            dist[r[first]] = t[first]
            live = live[(owner[live] < 0) & (T[live] > t1)]
            live = live[~((D[live, 2] > 0) & (O[live, 2] + D[live, 2] * t1 > top))]   # above every roof, still rising
            t0 = t1
        return owner, dist

    def covered(self, points):
        """Whether each point is inside or under a solid: in its footprint and below its top."""
        P = np.asarray(points, dtype=float).reshape(-1, 3)
        out = np.zeros(len(P), dtype=bool)
        if self._solids is None or not len(P):
            return out
        pi, si = self._solids.query(shapely.points(P[:, :2]), predicate="intersects")
        hit = P[pi, 2] < self.solid_z1[si]
        out[pi[hit]] = True
        return out
