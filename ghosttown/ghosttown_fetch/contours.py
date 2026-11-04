"""Contour lines of the terrain: the layer to make a Revit toposolid from (Toposolid › Create from Import on
the contour layer places the toposolid's points along the lines), and the ground read at a glance.

Levels are round heights above sea level, every 0.5 m, so a line is at 85.0 m, not at 0.3 m over the site
centre; each line's z is that height in local metres, exact and constant along it. Lines are drawn by
marching squares on the terrain's own grid, merged into polylines, cut to the site circle and simplified in
plan. Revit thins an import past MAX_POINTS its own way, so a site that would pass it is thinned here first:
the finest of SIMPLIFY_M that fits, then, as a map does on a big or hilly site, the next round interval of
INTERVALS_M. Flat ground has no contours."""
import math

import numpy as np
import shapely

from . import context as ctx
from .ground import disc

INTERVALS_M = (0.5, 1.0, 2.0, 5.0)
SIMPLIFY_M = (0.2, 0.5, 1.0, 2.0)
MAX_POINTS = 10_000
MIN_RING_M = 10.0    # a ring shorter than this is a one-cell speck of the elevation data, not ground
MIN_OPEN_M = 1.0     # an open piece this short is a sliver where a line grazes the circle
NUDGE_M = 1e-9       # ground exactly on a level counts as a hair above it: no crossing lands on a grid vertex

# Marching squares. A cell's corners are bits 0..3 counter-clockwise from its lower-left corner, set where the
# ground is at or above the level; its edges are B(ottom), R(ight), T(op) and L(eft). Each pattern joins two
# edges; the two saddles join either pair, decided by the cell's centre.
_JOINS = {1: [("L", "B")], 2: [("B", "R")], 3: [("L", "R")], 4: [("R", "T")], 6: [("B", "T")], 7: [("L", "T")],
          8: [("T", "L")], 9: [("B", "T")], 11: [("R", "T")], 12: [("L", "R")], 13: [("B", "R")], 14: [("L", "B")]}
_SADDLES = {5: ([("B", "R"), ("T", "L")], [("L", "B"), ("R", "T")]),    # (centre above, centre below)
            10: ([("L", "B"), ("R", "T")], [("B", "R"), ("T", "L")])}


def grid(terrain, radius_m):
    """(xs, ys, z): the terrain on its own cell over the site square plus one cell, z[j, i] at (xs[i], ys[j])."""
    cell = float(terrain.cell_m)
    n = math.ceil(radius_m / cell) + 1
    xs = np.arange(-n, n + 1, dtype=float) * cell
    gx, gy = np.meshgrid(xs, xs)
    z = np.asarray(terrain.z(gx.ravel(), gy.ravel()), dtype=float).reshape(gx.shape)
    return xs, xs.copy(), z


def level_lines(xs, ys, z, level, clip):
    """[LineString] where the grid crosses `level`, cut to `clip`, not yet simplified. Crossings are computed
    once per grid edge, so segments from neighbouring cells share their ends exactly and merge into one line.
    A vertex exactly on the level is nudged above it: a crossing on a vertex would be emitted by every cell
    around it, doubling a crest's line and breaking lines at the junctions."""
    s = z - level
    s = np.where(s == 0, NUDGE_M, s)
    above = s >= 0
    with np.errstate(divide="ignore", invalid="ignore"):
        th = s[:, :-1] / (s[:, :-1] - s[:, 1:])      # how far along each horizontal edge the level is crossed
        tv = s[:-1, :] / (s[:-1, :] - s[1:, :])      # the same along each vertical edge
    hx = xs[None, :-1] + th * np.diff(xs)[None, :]
    hy = np.broadcast_to(ys[:, None], hx.shape)
    vx = np.broadcast_to(xs[None, :], tv.shape)
    vy = ys[:-1, None] + tv * np.diff(ys)[:, None]
    edges = {"B": (hx, hy, 0, 0), "T": (hx, hy, 1, 0), "L": (vx, vy, 0, 0), "R": (vx, vy, 0, 1)}
    b0, b1, b2, b3 = above[:-1, :-1], above[:-1, 1:], above[1:, 1:], above[1:, :-1]
    case = b0.astype(np.int8) + 2 * b1 + 4 * b2 + 8 * b3
    centre_above = (s[:-1, :-1] + s[:-1, 1:] + s[1:, 1:] + s[1:, :-1]) >= 0
    segments = []

    def join(j, i, a, b):
        ax, ay, dj, di = edges[a]
        bx, by, ej, ei = edges[b]
        p = np.stack([ax[j + dj, i + di], ay[j + dj, i + di]], axis=1)
        q = np.stack([bx[j + ej, i + ei], by[j + ej, i + ei]], axis=1)
        keep = (p != q).any(axis=1)                  # a level through a corner can give a zero-length piece
        if keep.any():
            segments.append(np.stack([p[keep], q[keep]], axis=1))

    for code, joins in _JOINS.items():
        j, i = np.nonzero(case == code)
        for a, b in joins:
            join(j, i, a, b)
    for code, (when_above, when_below) in _SADDLES.items():
        j, i = np.nonzero(case == code)
        up = centre_above[j, i]
        for a, b in when_above:
            join(j[up], i[up], a, b)
        for a, b in when_below:
            join(j[~up], i[~up], a, b)
    if not segments:
        return []
    merged = shapely.line_merge(shapely.multilinestrings(shapely.linestrings(np.concatenate(segments))))
    return [part for part in shapely.get_parts(shapely.intersection(merged, clip))
            if part.geom_type == "LineString" and part.length >= (MIN_RING_M if part.is_closed else MIN_OPEN_M)]


def _points(levels):
    return sum(shapely.get_num_coordinates(line) for lines in levels.values() for line in lines)


def thinned(levels):
    """(interval, tolerance, {height: [LineString]}): the 0.5 m levels simplified within the finest tolerance that
    keeps the site under MAX_POINTS; failing that, every second, fourth or tenth level; failing that, the coarsest
    of both."""
    for interval in INTERVALS_M:
        subset = {h: lines for h, lines in levels.items() if abs(h / interval - round(h / interval)) < 1e-9}
        for tolerance in SIMPLIFY_M:
            out = {h: [shapely.simplify(line, tolerance) for line in lines] for h, lines in subset.items()}
            if _points(out) <= MAX_POINTS:
                return interval, tolerance, out
    return interval, tolerance, out


def elements(terrain, radius_m):
    """One element per level with a line inside the circle, contour:<height above sea level>, lowest first;
    none for flat ground."""
    base = terrain.ground_at_centre_m
    if base is None or not terrain.cell_m:
        return []
    xs, ys, z = grid(terrain, radius_m)
    site = disc(radius_m)
    step = INTERVALS_M[0]
    first, last = math.ceil((z.min() + base) / step), math.floor((z.max() + base) / step)
    levels = {}
    for k in range(first, last + 1):
        lines = level_lines(xs, ys, z, k * step - base, site)
        if lines:
            levels[k * step] = lines
    out = []
    for height, lines in thinned(levels)[2].items():
        local = round(height - base, 3)
        pts = [[[round(float(x), 3), round(float(y), 3), local] for x, y in shapely.get_coordinates(line)]
               for line in lines]
        out.append(ctx.element(f"contour:{height:g}", "contour", lines=[{"kind": "contour", "pts": p} for p in pts]))
    return out
