"""Ontario's LiDAR as the tests see it: synthetic surface and terrain images, and a recorded pair."""
import gzip
from pathlib import Path

import numpy as np

from ghosttown_fetch.frame import lonlat_to_merc, merc_to_lonlat
from tiff_samples import write_tiff

FIX = Path(__file__).parent / "fixtures" / "ontario"
BAY_SURFACE = gzip.decompress((FIX / "bay_surface.tif.gz").read_bytes())
BAY_TERRAIN = gzip.decompress((FIX / "bay_terrain.tif.gz").read_bytes())
LAKE_NONE = (FIX / "lake_none.tif").read_bytes()
FLOAT32_MAX = 3.4028234663852886e38


def rasters(frame, *, half=60.0, step=0.7, ground=80.0, tops=(), gaps=None):
    """(surface, terrain) TIFF bytes over ±`half` local metres, `step` Mercator metres a pixel: flat ground
    at `ground` m above sea level, each (xmin, ymin, xmax, ymax, height) in `tops` raised that far above
    it in the surface, and no data in either where `gaps(xs, ys)` is true (the terrain marks it with
    float32's largest value, as the real service does)."""
    lons, lats = frame.to_lonlat(np.array([-half, half]), np.array([-half, half]))
    mx, my = lonlat_to_merc(lons, lats)
    cols, rows = int((mx[1] - mx[0]) / step), int((my[1] - my[0]) / step)
    cx = mx[0] + (np.arange(cols) + 0.5) * step
    cy = my[1] - (np.arange(rows) + 0.5) * step
    lon, lat = merc_to_lonlat(*np.meshgrid(cx, cy))
    xs, ys = frame.to_local(lon, lat)
    terrain = np.full((rows, cols), float(ground))
    surface = terrain.copy()
    for x0, y0, x1, y1, height in tops:
        surface[(xs >= x0) & (xs <= x1) & (ys >= y0) & (ys <= y1)] = ground + height
    if gaps is not None:
        hole = gaps(xs, ys)
        surface[hole] = np.nan
        terrain[hole] = FLOAT32_MAX
    corner = (float(mx[0]), float(my[1]), step, step)
    return (write_tiff(surface, *corner, tile=64, nodata=None), write_tiff(terrain, *corner, tile=64, nodata=None))
