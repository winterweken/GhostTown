"""Ground heights in local metres, with z = 0 at the site centre.

NRCan's bare-earth elevation (HRDEM DTM) covers Canada. Elsewhere, or where NRCan has nothing,
the ground is flat and the build says why. Lake-front grids are mostly water, which has no
ground: gaps are filled low (at about shoreline height) as long as most of the site has data."""
import numpy as np
import shapely

from .frame import lonlat_to_merc
from .net import SourceError
from .sources import nrcan

MARGIN_M = 30.0
CANADA = (41.5, 84.0, -141.1, -52.5)  # lat_min, lat_max, lon_min, lon_max
MAX_NODATA = 0.95  # islands and piers are mostly lake; keep whatever land there is
GAP_PERCENTILE = 5


def bilinear(grid, x0, y0, dx, dy, mx, my, *, edge="nan"):
    """Bilinear values of `grid` at Web Mercator points. The grid's top-left corner is (x0, y0) and a pixel
    is dx wide and dy tall; a pixel's value belongs to its centre, half a pixel in. Points off the grid
    get NaN (`edge="nan"`) or the nearest edge's value (`edge="clamp"`). A NaN cell among the four around
    a point makes its value NaN either way."""
    if edge not in ("nan", "clamp"):
        raise ValueError(f"edge is 'nan' or 'clamp', not {edge!r}")
    rows, cols = grid.shape
    col = (np.asarray(mx, dtype=float) - x0) / dx - 0.5
    row = (y0 - np.asarray(my, dtype=float)) / dy - 0.5
    if edge == "clamp":
        col, row = np.clip(col, 0, cols - 1), np.clip(row, 0, rows - 1)
    else:
        inside = (col >= 0) & (col <= cols - 1) & (row >= 0) & (row <= rows - 1)
        col, row = np.where(inside, col, 0.0), np.where(inside, row, 0.0)  # off-grid points are NaN below
    c0, r0 = np.floor(col).astype(int), np.floor(row).astype(int)
    c1, r1 = np.minimum(c0 + 1, cols - 1), np.minimum(r0 + 1, rows - 1)
    fc, fr = col - c0, row - r0
    top = grid[r0, c0] * (1 - fc) + grid[r0, c1] * fc
    bottom = grid[r1, c0] * (1 - fc) + grid[r1, c1] * fc
    value = top * (1 - fr) + bottom * fr
    return value if edge == "clamp" else np.where(inside, value, np.nan)


class FlatTerrain:
    source = "flat"
    ground_at_centre_m = None
    cell_m = None

    def z(self, xs, ys):
        return np.zeros(np.shape(xs), dtype=float)

    def min_under(self, polygon):
        return 0.0


class GridTerrain:
    source = "nrcan-dtm"

    def __init__(self, grid, x0, y0, dx, dy, frame, cell_m):
        self.grid = np.asarray(grid, dtype=float)
        self.x0, self.y0, self.dx, self.dy = x0, y0, dx, dy
        self.frame = frame
        self.cell_m = cell_m
        self._centre = float(self._raw(np.zeros(1), np.zeros(1))[0])
        self.ground_at_centre_m = round(self._centre, 3)

    def _raw(self, xs, ys):
        lon, lat = self.frame.to_lonlat(np.asarray(xs, dtype=float), np.asarray(ys, dtype=float))
        mx, my = lonlat_to_merc(lon, lat)
        return bilinear(self.grid, self.x0, self.y0, self.dx, self.dy, mx, my, edge="clamp")

    def z(self, xs, ys):
        return self._raw(xs, ys) - self._centre

    def min_under(self, polygon):
        """Lowest ground under a footprint: its outline points plus a grid of points inside it."""
        edge = shapely.get_coordinates(shapely.boundary(polygon))
        minx, miny, maxx, maxy = polygon.bounds
        gx, gy = np.meshgrid(np.arange(minx, maxx, self.cell_m), np.arange(miny, maxy, self.cell_m))
        gx, gy = gx.ravel(), gy.ravel()
        inside = shapely.contains_xy(polygon, gx, gy)
        xs = np.concatenate([edge[:, 0], gx[inside]])
        ys = np.concatenate([edge[:, 1], gy[inside]])
        return float(np.min(self.z(xs, ys)))


def cell_for(radius_m):
    return 2.0 if radius_m <= 500 else 4.0


def load(net, frame, radius_m):
    """(terrain, note): NRCan elevation where it exists, else flat ground and a note saying why."""
    lat_min, lat_max, lon_min, lon_max = CANADA
    if not (lat_min <= frame.lat0 <= lat_max and lon_min <= frame.lon0 <= lon_max):
        return FlatTerrain(), ("info", "terrain", "Elevation data covers Canada only for now, so the ground is flat.")
    cell = cell_for(radius_m)
    try:
        grid, x0, y0, dx, dy = nrcan.fetch(net, frame, radius_m + MARGIN_M, cell)
    except SourceError as e:
        return FlatTerrain(), ("warn", "terrain", f"{e} The ground is flat.")
    gaps = np.isnan(grid)
    if min(grid.shape) < 3 or gaps.mean() > MAX_NODATA:
        return FlatTerrain(), ("info", "terrain", "NRCan has no elevation data for this site, so the ground is flat.")
    if gaps.any():
        grid = np.where(gaps, np.nanpercentile(grid, GAP_PERCENTILE), grid)
    return GridTerrain(grid, x0, y0, dx, dy, frame, cell), None
