"""Fitted roofs: building solids made of a few planar faces measured from Ontario's LiDAR, the light
choice for Revit beside the sampled LiDAR roofs.

House-sized solids (up to 400 m2 and 20 m tall) get the simplest of four roofs that explains the LiDAR:
flat, shed, gable or hip. Ridges are searched along and across the outline's main axes and every 15
degrees. Each candidate is fitted by least squares, then again without its worst fifth of samples
(chimneys, tree crowns, the ground at the edges), and its planes run out to the walls, so the eaves sit
where they meet them. OpenStreetMap's roof:shape, height and roof:height tags constrain the fit when
the survey agrees with them.

Larger solids become stepped tiers at their measured roof levels: heights the roof's smooth cells share,
at least a storey (3 m) apart and 25 m2 large. The tiers fill the footprint exactly and each is a closed
prism, like the City's own parts.

A solid the survey predates keeps its own height, as with LiDAR roofs. Any other solid that can't be
fitted keeps a flat top at its measured height.
"""
import math

import numpy as np
import shapely
from shapely.geometry import Polygon

from .lidar_roofs import (CITY_ABOVE_M, CITY_GROUND_M, MIN_WALL_M, OTHER_RANGE_M, RIDGE_M, _close, _outline,
                          _triangle_coords)

MODELS = ("flat", "shed", "gable", "hip")  # simplest first
SHAPES = {"flat": "flat", "skillion": "shed", "gabled": "gable", "hipped": "hip", "half-hipped": "hip"}
INSET_M = 1.0          # house samples stay this far inside the walls...
INSET_MIN_SHARE = 0.3  # ...unless that keeps less than this share of the footprint
MIN_SAMPLES = 12
KEEP = 0.8             # the robust refit keeps this share of the samples
SIMPLER_BY = 1.15      # a more complex roof must beat the simpler one's error by this factor
MAX_ERROR_M = 1.5      # a best fit worse than this is no fit
MIN_SLOPE = 0.05       # a gable or hip slopes at least this much (m per m)
SWEEP_DEG = 15.0       # ridge directions tried everywhere...
NUDGE_DEG = 3.0        # ...and along and across the outline's main axes, nudged by this
AXIS_EDGE_M = 3.0      # outline edges this long or longer set main axes
OFFSETS = 15           # ridge positions tried across the house
HIP_ENDS = (0.5, 0.75, 1.0)
LOWEST_ROOF_M = OTHER_RANGE_M[0]  # no roof point below this height above the ground


def _grid(poly, cell):
    """The LiDAR cells over the outline's bounds: (i0, j0, centre x, centre y, inside), the last three
    as (columns, rows) arrays."""
    minx, miny, maxx, maxy = poly.bounds
    i0, j0 = math.floor(minx / cell), math.floor(miny / cell)
    ni, nj = max(math.ceil(maxx / cell) - i0, 1), max(math.ceil(maxy / cell) - j0, 1)
    gx, gy = np.meshgrid((np.arange(ni) + i0 + 0.5) * cell, (np.arange(nj) + j0 + 0.5) * cell, indexing="ij")
    inside = shapely.contains_xy(poly, gx.ravel(), gy.ravel()).reshape(gx.shape)
    return i0, j0, gx, gy, inside


def _centres(poly, cell):
    _, _, gx, gy, inside = _grid(poly, cell)
    return gx[inside], gy[inside]


def _kept(above, own, city):
    """The samples the LiDAR rules keep: the City's outlines drop crane- and gap-like heights (over 8 m
    above their own, or under 2 m), other solids keep 2-400 m."""
    with np.errstate(invalid="ignore"):
        if city:
            return np.isfinite(above) & (above >= CITY_GROUND_M) & (above <= own + CITY_ABOVE_M)
        return np.isfinite(above) & (above >= OTHER_RANGE_M[0]) & (above <= OTHER_RANGE_M[1])


def house_samples(poly, own, heights, cell, city):
    """x, y and height above ground of the kept samples INSET_M inside the walls (the whole outline when
    the inset keeps too little), capped at their median plus 3 m like LiDAR roofs."""
    inner = poly.buffer(-INSET_M)
    if inner.is_empty or inner.area < INSET_MIN_SHARE * poly.area:
        inner = poly
    xs, ys = _centres(inner, cell)
    above = heights.sample(xs, ys)
    keep = _kept(above, own, city)
    xs, ys, above = xs[keep], ys[keep], above[keep]
    if above.size:
        above = np.minimum(above, float(np.median(above)) + RIDGE_M)
    return xs, ys, above


def _trimmed(r):
    """True for the residuals kept by the robust refit: all but the worst (1 - KEEP), row by row."""
    a = np.abs(r)
    return a <= np.quantile(a, KEEP, axis=-1, keepdims=True)


def _rms(r, keep):
    return np.sqrt((np.where(keep, r * r, 0.0)).sum(axis=-1) / np.maximum(keep.sum(axis=-1), 1))


def _pitched(D, z, top=None, slope=None):
    """Fit z = H - s * D for every row of D (candidates x samples): least squares, then again on the
    samples the first fit explains best. `top` fixes H; `slope` (one per row, with `top` only) fixes s.
    Returns H, s and the error, one per row."""
    keep = np.ones(D.shape, dtype=bool)
    for round_ in range(2):
        w = keep.astype(float)
        n = w.sum(axis=1)
        if top is None:
            dm = (w * D).sum(axis=1) / n
            zm = (w * z).sum(axis=1) / n
            sxx = (w * (D - dm[:, None]) ** 2).sum(axis=1)
            sxz = (w * (D - dm[:, None]) * (z - zm[:, None])).sum(axis=1)
            with np.errstate(invalid="ignore", divide="ignore"):
                s = -sxz / sxx
            H = zm + s * dm
        else:
            H = np.full(len(D), float(top))
            if slope is None:
                dd = (w * D * D).sum(axis=1)
                with np.errstate(invalid="ignore", divide="ignore"):
                    s = (w * D * (top - z)).sum(axis=1) / dd
            else:
                s = np.asarray(slope, dtype=float)
        r = H[:, None] - s[:, None] * D - z
        if round_ == 0:
            keep = _trimmed(np.where(np.isfinite(r), r, 0.0))
    return H, s, _rms(r, keep)


def _flat(z, top=None):
    h = float(top) if top is not None else float(z.mean())
    keep = _trimmed(h - z)
    if top is None:
        h = float(z[keep].mean())
    return {"kind": "flat", "h": h}, float(_rms(h - z, keep))


def _shed(x, y, z, outline, top=None, drop=None):
    """One plane. With the top known its highest outline point is the top, and with `drop` its lowest
    outline point sits that far below."""
    A = np.column_stack([x, y, np.ones_like(x)])
    keep = np.ones(len(z), dtype=bool)
    for round_ in range(2):
        c, *_ = np.linalg.lstsq(A[keep], z[keep], rcond=None)
        if top is not None:
            along = outline[:, 0] * c[0] + outline[:, 1] * c[1]
            span = float(along.max() - along.min())
            if drop is not None and span > 0:
                c[:2] *= drop / span
                along = outline[:, 0] * c[0] + outline[:, 1] * c[1]
            c[2] = top - float(along.max())
        r = A @ c - z
        if round_ == 0:
            keep = _trimmed(r)
    return {"kind": "shed", "c": [float(v) for v in c]}, float(_rms(r, keep))


def _apart(a, b):
    d = abs(a - b) % math.pi
    return min(d, math.pi - d)


def directions(poly):
    """Ridge directions to try, in radians from 0 to pi: along and across the outline's main axes (its
    minimum rotated rectangle and every edge of AXIS_EDGE_M or more), each nudged by NUDGE_DEG either way,
    and every SWEEP_DEG."""
    edges = []
    with np.errstate(divide="ignore", invalid="ignore"):  # GEOS divides by zero on axis-aligned outlines
        rect = shapely.minimum_rotated_rectangle(poly)
    if rect.geom_type == "Polygon":
        r = np.asarray(rect.exterior.coords)
        edges.append((r[0], r[1]))
    ring = np.asarray(poly.exterior.coords)
    edges += [(a, b) for a, b in zip(ring[:-1], ring[1:]) if math.dist(a, b) >= AXIS_EDGE_M]
    axes = []
    for a, b in edges:
        t = math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi
        for axis in (t, (t + math.pi / 2) % math.pi):
            if all(_apart(axis, o) > math.radians(0.5) for o in axes):
                axes.append(axis)
    nudges = np.radians([-NUDGE_DEG, 0.0, NUDGE_DEG])
    found = [(a + d) % math.pi for a in axes for d in nudges]
    return np.array(found + list(np.radians(np.arange(0.0, 180.0, SWEEP_DEG))))


def _frame(x, y, th):
    """(along, across) the ridge direction th."""
    c, s = math.cos(th), math.sin(th)
    return x * c + y * s, -x * s + y * c


def _best_pitched(x, y, z, outline, dirs, hip, top=None, drop=None):
    """The best gable (or hip) over every direction and ridge position: (model, error), or (None, inf)."""
    best, best_err = None, math.inf
    for th in dirs:
        v, u = _frame(x, y, th)
        ov, ou = _frame(outline[:, 0], outline[:, 1], th)
        lo, hi = np.percentile(u, [15, 85])
        u0 = np.linspace(lo, hi, OFFSETS)
        D = np.abs(u[None, :] - u0[:, None])
        OD = np.abs(ou[None, :] - u0[:, None])
        params = [(float(a), None) for a in u0]
        if hip:
            v0 = (v.min() + v.max()) / 2
            ends = np.maximum((v.max() - v.min()) / 2 - np.array(HIP_ENDS) * (u.max() - u.min()) / 2, 0.0)
            D = np.maximum(D[:, None, :], np.abs(v - v0)[None, None, :] - ends[None, :, None]).reshape(-1, len(z))
            OD = np.maximum(OD[:, None, :], np.abs(ov - v0)[None, None, :] - ends[None, :, None]).reshape(-1, len(ov))
            params = [(float(a), float(e)) for a in u0 for e in ends]
        slope = drop / np.maximum(OD.max(axis=1), 1e-9) if top is not None and drop is not None else None
        H, s, err = _pitched(D, z, top, slope)
        ok = np.isfinite(err) & np.isfinite(s) & (s > MIN_SLOPE)
        if not ok.any():
            continue
        k = int(np.argmin(np.where(ok, err, np.inf)))
        if err[k] < best_err:
            ridge, end = params[k]
            best = {"kind": "hip" if hip else "gable", "th": float(th), "u0": ridge, "H": float(H[k]), "s": float(s[k])}
            if hip:
                best.update(v0=float(v0), a=end)
            best_err = float(err[k])
    return best, best_err


def _choose(x, y, z, poly, kinds, top, drop):
    """The simplest of `kinds` that explains the samples, with its 'error'; None when none fits at all."""
    outline = shapely.get_coordinates(poly.boundary)
    dirs = None
    best = None
    for kind in MODELS:
        if kind not in kinds:
            continue
        if kind == "flat":
            m, err = _flat(z, top)
        elif kind == "shed":
            m, err = _shed(x, y, z, outline, top, drop)
        else:
            if dirs is None:
                dirs = directions(poly)
            m, err = _best_pitched(x, y, z, outline, dirs, kind == "hip", top, drop)
        if m is None or not np.isfinite(err):
            continue
        if best is None or err * SIMPLER_BY < best["error"]:
            best = dict(m, error=err)
    return best


def fit_house(x, y, z, poly, roof=None, top=None):
    """The house roof that best explains the samples (heights above ground) as a model dict with its
    'error', or None when there are fewer than MIN_SAMPLES or nothing fits within MAX_ERROR_M.
    `roof` holds OpenStreetMap's roof tags ({"shape", "height"}); `top` is a height tag's top above ground.
    A tag-constrained fit that is poor gives way to the free fit: the survey measures the roof as built."""
    if len(z) < MIN_SAMPLES:
        return None
    roof = roof or {}
    shape = SHAPES.get(roof.get("shape"))
    drop = roof.get("height") if top is not None else None
    if shape is not None or top is not None:
        m = _choose(x, y, z, poly, (shape,) if shape else MODELS, top, drop)
        if m is not None and m["error"] <= MAX_ERROR_M:
            return m
    m = _choose(x, y, z, poly, MODELS, None, None)
    return m if m is not None and m["error"] <= MAX_ERROR_M else None


def roof_z(m, x, y):
    """The model's roof height above ground at x, y."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if m["kind"] == "flat":
        return np.full(x.shape, m["h"])
    if m["kind"] == "shed":
        a, b, c = m["c"]
        return a * x + b * y + c
    v, u = _frame(x, y, m["th"])
    d = np.abs(u - m["u0"])
    if m["kind"] == "hip":
        d = np.maximum(d, np.abs(v - m["v0"]) - m["a"])
    return m["H"] - m["s"] * d


def _faces(poly, m):
    """The footprint cut where the roof bends: along the ridge (gable), plus the hip lines, 45 degrees in
    plan (hip). Each piece is one plane of the roof."""
    if m["kind"] in ("flat", "shed"):
        return [poly]
    c, s = math.cos(m["th"]), math.sin(m["th"])
    minx, miny, maxx, maxy = poly.bounds
    e = 10.0 * (max(abs(minx), abs(miny), abs(maxx), abs(maxy)) + abs(m["u0"]) + abs(m.get("v0", 0.0)) + 100.0)

    def xy(v, u):
        return (v * c - u * s, v * s + u * c)

    u0 = m["u0"]
    if m["kind"] == "gable":
        cuts = [Polygon([xy(-e, u0), xy(e, u0), xy(e, u0 + e), xy(-e, u0 + e)]),
                Polygon([xy(-e, u0), xy(-e, u0 - e), xy(e, u0 - e), xy(e, u0)])]
    else:
        p, q = (m["v0"] - m["a"], u0), (m["v0"] + m["a"], u0)
        cuts = [Polygon([xy(*p), xy(*q), xy(q[0] + e, u0 + e), xy(p[0] - e, u0 + e)]),
                Polygon([xy(*p), xy(p[0] - e, u0 - e), xy(q[0] + e, u0 - e), xy(*q)]),
                Polygon([xy(*q), xy(q[0] + e, u0 - e), xy(q[0] + e, u0 + e)]),
                Polygon([xy(*p), xy(p[0] - e, u0 + e), xy(p[0] - e, u0 - e)])]
    out = []
    for cut in cuts:
        out += [g for g in shapely.get_parts(shapely.intersection(poly, cut)) if g.geom_type == "Polygon" and g.area > 1e-4]
    return out


def house_solid(rings, z0, ground, m):
    """(verts, faces) of a closed solid whose roof is the model `m` (heights above `ground`), its planes
    running out to the walls; or None. Built like a LiDAR roof: walls and base follow the roof's own edge."""
    poly = Polygon(rings[0], rings[1:])
    if not poly.is_valid or poly.area <= 0:
        return None
    parts = _faces(poly, m)
    if not parts:
        return None
    corners = _triangle_coords(np.array(parts, dtype=object)).reshape(-1, 2)
    _, first, inverse = np.unique(np.round(corners * 1000.0).astype(np.int64), axis=0,
                                  return_index=True, return_inverse=True)
    xy = corners[first]
    surface = _outline(inverse.reshape(-1, 3), xy)
    if surface is None:
        return None
    top, loops, edge, base = surface
    z = np.maximum(ground + roof_z(m, xy[:, 0], xy[:, 1]), max(ground + LOWEST_ROOF_M, z0 + MIN_WALL_M))
    return _close(top, xy, z, z0, loops, edge, base)
