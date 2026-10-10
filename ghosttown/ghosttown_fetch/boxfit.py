"""An application's starting box (design/development-applications.md §4.3): the largest rectangle inside its site,
turned to the site's main direction (the long side of its minimum rotated rectangle).

The site is turned flat, laid on a grid (CELL_M, coarser when the grid would pass MAX_CELLS) and shrunk by half a
cell, and the largest block of cells whose centres are inside is the rectangle: it stays inside the site to a
fraction of a cell. A site that has no such block at least MIN_SIDE_M a side (a strip, a sliver) gets its minimum
rotated rectangle instead. Ported from BHPlus bh_context/boxfit.py (60d801e)."""
import math

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import box

CELL_M = 1.0
MAX_CELLS = 250000
MIN_SIDE_M = 2.0


def _fold(angle):
    """Degrees folded into (-90, 90]: a box turned half round is the same box."""
    while angle <= -90.0:
        angle += 180.0
    while angle > 90.0:
        angle -= 180.0
    return angle


def main_angle(g):
    """Degrees in (-90, 90], counter-clockwise from east, of the long side of `g`'s minimum rotated rectangle
    (0 for a shape with no area)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        rect = shapely.oriented_envelope(g)
    if rect.geom_type != "Polygon":
        return 0.0
    xy = np.asarray(rect.exterior.coords)
    a, b = xy[1] - xy[0], xy[2] - xy[1]
    edge = a if math.hypot(*a) >= math.hypot(*b) else b
    return round(_fold(math.degrees(math.atan2(edge[1], edge[0]))), 6)


def footprint(cx, cy, angle_deg, width_m, depth_m):
    """The box's outline: width along angle_deg, turned about its centre."""
    flat = box(cx - width_m / 2.0, cy - depth_m / 2.0, cx + width_m / 2.0, cy + depth_m / 2.0)
    return affinity.rotate(flat, angle_deg, origin=(cx, cy))


def _largest(mask):
    """(row0, col0, rows, cols) of the largest all-True block of a 2D bool array, or None: row by row, the tallest
    run of True above each cell is a histogram, and its largest rectangle is found with a stack."""
    h, w = mask.shape
    heights = np.zeros(w, dtype=np.int64)
    best_area, best = 0, None
    for r in range(h):
        heights = np.where(mask[r], heights + 1, 0)
        stack = []
        for c in range(w + 1):
            cur = int(heights[c]) if c < w else 0
            start = c
            while stack and stack[-1][1] >= cur:
                s, tall = stack.pop()
                if tall * (c - s) > best_area:
                    best_area, best = tall * (c - s), (r - tall + 1, s, tall, c - s)
                start = s
            stack.append((start, cur))
    return best


def _envelope(g, angle, about):
    with np.errstate(divide="ignore", invalid="ignore"):
        rect = shapely.oriented_envelope(g)
    flat = affinity.rotate(rect, -angle, origin=about)
    x0, y0, x1, y1 = flat.bounds
    p = affinity.rotate(shapely.Point((x0 + x1) / 2.0, (y0 + y1) / 2.0), angle, origin=about)
    return p.x, p.y, angle, x1 - x0, y1 - y0


def rectangle(g):
    """(cx, cy, angle_deg, width_m, depth_m): the largest rectangle inside `g` (a Polygon or MultiPolygon in local
    metres, with area) whose sides run along and across its main direction; width runs along angle_deg."""
    angle = main_angle(g)
    about = g.centroid
    flat = affinity.rotate(g, -angle, origin=about)
    x0, y0, x1, y1 = flat.bounds
    cell = max(CELL_M, math.sqrt((x1 - x0) * (y1 - y0) / MAX_CELLS))
    inner = flat.buffer(-cell / 2.0 + 1e-6)
    nx, ny = max(1, int(math.ceil((x1 - x0) / cell))), max(1, int(math.ceil((y1 - y0) / cell)))
    gx, gy = np.meshgrid(x0 + cell * (np.arange(nx) + 0.5), y0 + cell * (np.arange(ny) + 0.5))
    mask = shapely.contains_xy(inner, gx, gy) if not inner.is_empty else np.zeros(gx.shape, dtype=bool)
    found = _largest(mask)
    if found is not None:
        r0, c0, rows, cols = found
        w, d = cols * cell, rows * cell
        if min(w, d) >= MIN_SIDE_M:
            p = affinity.rotate(shapely.Point(x0 + cell * (c0 + cols / 2.0), y0 + cell * (r0 + rows / 2.0)),
                                angle, origin=about)
            return p.x, p.y, angle, w, d
    return _envelope(g, angle, about)
