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
TIER_STEP_M = 3.0      # a storey: tiers stand at least this far apart...
MIN_TIER_M2 = 25.0     # ...and cover at least this much
MIN_SEED_M2 = 8.0      # a tier rests on at least this much smooth roof of its own, so a smooth spot in a crown isn't one
ROUGH_M = 0.5          # a cell whose 3 x 3 neighbourhood strays this far from a plane is a tree, wall or clutter
LEVEL_BIN_M = 0.5
LEVEL_SIGMA_M = 1.0
SMOOTH_PASSES = 2
SMOOTH_VOTES = 5       # of 9: a cell takes its neighbourhood's majority label
TIER_SIMPLIFY_M = 1.0


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


def _windows(a, fill=None):
    """The 9 shifted copies of `a` that line up each cell's 3 x 3 neighbourhood on the first axis; the
    border is padded with `fill`, or with the edge's own values."""
    ni, nj = a.shape
    p = np.pad(a, 1, mode="edge") if fill is None else np.pad(a, 1, constant_values=fill)
    return np.stack([p[r:r + ni, c:c + nj] for r in range(3) for c in range(3)])

def _rough(h):
    """True where a cell's 3 x 3 neighbourhood strays more than ROUGH_M (RMS) from its best plane; a
    neighbourhood with a NaN in it counts as rough."""
    win = _windows(h, np.nan)
    dr = np.repeat([-1.0, 0.0, 1.0], 3)[:, None, None]
    dc = np.tile([-1.0, 0.0, 1.0], 3)[:, None, None]
    plane = win.mean(axis=0) + dr * (dr * win).sum(axis=0) / 6.0 + dc * (dc * win).sum(axis=0) / 6.0
    with np.errstate(invalid="ignore"):
        return ~(np.sqrt(((win - plane) ** 2).mean(axis=0)) <= ROUGH_M)

def _levels(smooth_heights, valid_heights, cell):
    """The roof levels: peaks of the smooth cells' height histogram (LEVEL_BIN_M bins, smoothed by a
    LEVEL_SIGMA_M Gaussian), taken from the tallest peak down, each TIER_STEP_M from those taken and with
    MIN_TIER_M2 of valid cells within half a step of it. The median when no peak qualifies."""
    lo, hi = smooth_heights.min(), smooth_heights.max()
    edges = np.arange(lo - 3 * LEVEL_SIGMA_M, hi + 3 * LEVEL_SIGMA_M + LEVEL_BIN_M, LEVEL_BIN_M)
    counts, _ = np.histogram(smooth_heights, edges)
    reach = int(round(2 * LEVEL_SIGMA_M / LEVEL_BIN_M))
    kernel = np.exp(-0.5 * (np.arange(-reach, reach + 1) * LEVEL_BIN_M / LEVEL_SIGMA_M) ** 2)
    smooth = np.convolve(counts, kernel / kernel.sum(), mode="same")
    centres = (edges[:-1] + edges[1:]) / 2
    peaks = [i for i in range(1, len(smooth) - 1) if smooth[i] >= smooth[i - 1] and smooth[i] > smooth[i + 1]]
    taken = []
    for i in sorted(peaks, key=lambda i: -smooth[i]):
        level = float(centres[i])
        if (all(abs(level - t) >= TIER_STEP_M for t in taken)
                and np.count_nonzero(np.abs(valid_heights - level) < TIER_STEP_M / 2) * cell * cell >= MIN_TIER_M2):
            taken.append(level)
    return np.array(sorted(taken)) if taken else np.array([float(np.median(smooth_heights))])

def _label(mask):
    """The 4-connected pieces of `mask`: each cell's label is the smallest flat index in its piece, -1
    off the mask."""
    ni, nj = mask.shape
    index = np.arange(ni * nj).reshape(ni, nj)
    down, right = mask[:-1, :] & mask[1:, :], mask[:, :-1] & mask[:, 1:]
    a = np.concatenate([index[:-1, :][down], index[:, :-1][right]])
    b = np.concatenate([index[1:, :][down], index[:, 1:][right]])
    lab = np.where(mask, index, -1).ravel()
    while True:
        low = np.minimum(lab[a], lab[b])
        new = lab.copy()
        np.minimum.at(new, a, low)
        np.minimum.at(new, b, low)
        on = new >= 0
        new[on] = new[new[on]]
        if np.array_equal(new, lab):
            return lab.reshape(ni, nj)
        lab = new

def _fill(lab):
    """Every cell takes the label of its nearest labelled cell, growing outwards one cell per pass."""
    full = lab.copy()
    shifts = ((np.s_[:-1, :], np.s_[1:, :]), (np.s_[1:, :], np.s_[:-1, :]),
              (np.s_[:, :-1], np.s_[:, 1:]), (np.s_[:, 1:], np.s_[:, :-1]))
    while (full < 0).any():
        before = full.copy()
        for src, dst in shifts:
            grow = (full[dst] < 0) & (before[src] >= 0)
            full[dst][grow] = before[src][grow]
        if np.array_equal(full, before):
            break
    return full

def _borders(full):
    """{(a, b): shared cell sides} between neighbouring labels a < b."""
    pairs = []
    for x, y in ((full[:-1, :], full[1:, :]), (full[:, :-1], full[:, 1:])):
        d = x != y
        pairs.append(np.stack([np.minimum(x[d], y[d]), np.maximum(x[d], y[d])], axis=1))
    pairs = np.concatenate(pairs)
    if not len(pairs):
        return {}
    keys, counts = np.unique(pairs, axis=0, return_counts=True)
    return {(int(a), int(b)): int(n) for (a, b), n in zip(keys, counts)}

def _by_label(values, labels, count):
    """`values` split into one array per label 0..count-1."""
    order = np.argsort(labels, kind="stable")
    bounds = np.searchsorted(labels[order], np.arange(count + 1))
    values = values[order]
    return [values[bounds[k]:bounds[k + 1]] for k in range(count)]


def _merge(full, inside, smooth, h, min_cells, min_seed_cells):
    """(labels, {label: height}): tiers covering under MIN_TIER_M2 inside the outline, or resting on
    under MIN_SEED_M2 of smooth roof, join the neighbour they share the longest border with, smallest
    first; then neighbours whose medians are under TIER_STEP_M apart merge, closest first. Each merge
    updates sizes, borders and heights in place, so a cluttered roof costs one pass per merge over its
    labels, not over its cells. A tier's height is the median of its smooth cells."""
    keys, flat = np.unique(full, return_inverse=True)
    full = flat.reshape(full.shape)
    count = len(keys)
    size = np.bincount(full[inside], minlength=count)
    heights = _by_label(h[smooth], full[smooth], count)
    near = [{} for _ in range(count)]
    for (a, b), n in _borders(full).items():
        near[a][b] = near[b][a] = n
    into = np.arange(count)
    alive = set(range(count))

    def join(k, j):
        """Tier k becomes part of tier j."""
        into[into == k] = j
        size[j] += size[k]
        heights[j] = np.concatenate([heights[j], heights[k]])
        for other, n in near[k].items():
            if other != j:
                near[j][other] = near[other][j] = near[j].get(other, 0) + n
            del near[other][k]
        near[k] = {}
        alive.discard(k)

    while len(alive) > 1:
        small = [k for k in alive if size[k] < min_cells or len(heights[k]) < min_seed_cells]
        if not small:
            break
        k = min(small, key=lambda k: (size[k], k))
        join(k, max(near[k], key=lambda j: (near[k][j], -j)))
    level = {k: float(np.median(heights[k])) for k in alive}
    while len(alive) > 1:
        close = [(abs(level[a] - level[b]), a, b) for a in alive for b in near[a]
                 if a < b and abs(level[a] - level[b]) < TIER_STEP_M]
        if not close:
            break
        _, a, b = min(close)
        join(b, a)
        level[a] = float(np.median(heights[a]))
        del level[b]
    return into[full], level

def _smooth(full):
    """SMOOTH_PASSES passes in which each cell takes the label held by SMOOTH_VOTES of its 3 x 3 cells."""
    for _ in range(SMOOTH_PASSES):
        win = _windows(full)
        most, pick = np.zeros(full.shape, dtype=np.int64), full.copy()
        for k in np.unique(full):  # one label at a time, keeping the best so far: memory stays one grid's worth
            votes = (win == k).sum(axis=0)
            better = votes > most
            most, pick = np.where(better, votes, most), np.where(better, k, pick)
        full = np.where(most >= SMOOTH_VOTES, pick, full)
    return full

def _absorb(parts):
    """Polygons under MIN_TIER_M2 join the neighbour they share the longest edge with, keeping its height;
    one that shares no edge, or wouldn't make one polygon with it, stays as it is."""
    todo = sorted(parts, key=lambda ph: ph[0].area)
    done = []
    while todo:
        p, height = todo.pop(0)
        others = todo + done
        if p.area >= MIN_TIER_M2 or not others:
            done.append((p, height))
            continue
        lengths = [p.boundary.intersection(q.boundary).length for q, _ in others]
        j = int(np.argmax(lengths))
        merged = shapely.union(others[j][0], p) if lengths[j] > 0 else None
        if merged is None or merged.geom_type != "Polygon":
            done.append((p, height))
            continue
        if j < len(todo):
            todo[j] = (merged, todo[j][1])
            todo.sort(key=lambda ph: ph[0].area)
        else:
            done[j - len(todo)] = (merged, done[j - len(todo)][1])
    return done

def _cells(mask, i0, j0, cell):
    """The union of the mask's cells, built from its runs of cells along y (far fewer shapes than cells)."""
    steps = np.diff(np.pad(mask, ((0, 0), (1, 1))).astype(np.int8), axis=1)
    si, sj = np.nonzero(steps == 1)   # a run starts at sj...
    _, ej = np.nonzero(steps == -1)   # ...and stops before ej, in the same order
    return shapely.union_all(shapely.box((si + i0) * cell, (sj + j0) * cell, (si + i0 + 1) * cell, (ej + j0) * cell))

def _outlines(full, i0, j0, cell, poly, level):
    """[(Polygon, height)]: each tier's cells unioned, their shared edges simplified by TIER_SIMPLIFY_M
    with the outer edge fixed, cut to the outline, and the small pieces absorbed."""
    keys = [int(k) for k in np.unique(full)]
    regions = [_cells(full == k, i0, j0, cell) for k in keys]
    try:
        regions = list(shapely.coverage_simplify(np.array(regions, dtype=object), TIER_SIMPLIFY_M,
                                                 simplify_boundary=False))
    except shapely.errors.GEOSException:
        pass  # the cells' own edges, unsimplified
    parts = []
    for k, region in zip(keys, regions):
        parts += [(p, level[k]) for p in shapely.get_parts(shapely.intersection(region, poly))
                  if p.geom_type == "Polygon" and p.area > 0]
    return _absorb(parts)

def tiers(poly, own, heights, cell, city, taller=None):
    """[(Polygon, height above ground)] filling `poly` at its measured roof levels, or None when less
    than MIN_TIER_M2 of its roof is smooth LiDAR. Cells under `taller` (other solids standing higher)
    are left out: the LiDAR there sees those solids."""
    i0, j0, gx, gy, inside = _grid(poly, cell)
    h = heights.sample(gx.ravel(), gy.ravel()).reshape(gx.shape)
    valid = inside & _kept(h, own, city)
    if taller is not None and not taller.is_empty:
        valid &= ~shapely.contains_xy(taller, gx.ravel(), gy.ravel()).reshape(gx.shape)
    smooth = valid & ~_rough(np.where(valid, h, np.nan))
    min_cells = MIN_TIER_M2 / (cell * cell)
    if np.count_nonzero(smooth) < min_cells:
        return None
    levels = _levels(h[smooth], h[valid], cell)
    known = np.where(np.isfinite(h), h, 0.0)
    nearest = np.abs(known[..., None] - levels).argmin(axis=-1)
    seed = smooth & (np.abs(known - levels[nearest]) < TIER_STEP_M / 2)  # smooth cells off every level seed nothing
    if not seed.any():
        return None
    lab = np.full(h.shape, -1)
    for q in range(len(levels)):
        pieces = _label(seed & (nearest == q))
        lab = np.where(pieces >= 0, pieces, lab)
    full, level = _merge(_fill(lab), inside, smooth, h, min_cells, MIN_SEED_M2 / (cell * cell))
    return _outlines(_smooth(full), i0, j0, cell, poly, level)
