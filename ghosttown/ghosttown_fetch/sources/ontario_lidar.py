"""Ontario's LiDAR: heights above ground around a site, from the province's surface and terrain models.

Geospatial Ontario publishes a Digital Surface Model (tops of buildings and trees) and a Digital Terrain
Model (bare earth), both lidar-derived at 0.5 m, as ArcGIS ImageServers under the Open Government
Licence – Ontario. `exportImage` answers a Web Mercator box with one uncompressed 32-bit float TIFF.
Both models come from the same surveys, so surface minus terrain is a height above ground with no datum
question. Outside the surveyed areas the TIFF leaves its tiles out, and the terrain model marks water
and gaps with float32's largest value. The mosaic joins surveys from 2009 to 2025 and the service
can't say which one a pixel came from, so no year is given.
"""
import math
import urllib.parse

import numpy as np

from .. import tiff
from ..frame import lonlat_to_merc
from ..net import SourceError
from ..terrain import bilinear

ROOT = "https://ws.geoservices.lrc.gov.on.ca/arcgis5/rest/services/Elevation"
SURFACE = "Ontario_DSM_LidarDerived"
TERRAIN = "Ontario_DTM_LidarDerived"
BOX = (41.6, 50.5, -94.8, -74.3)  # lat_min, lat_max, lon_min, lon_max: the services' extent
TIMEOUT_S = 240                   # the surface model can take a minute to answer its first request
NODATA_ABOVE = 1e30               # the terrain model's no-data value is float32's largest
NONE_HERE = "Ontario has no LiDAR here."


class NoLidar(SourceError):
    """The site is outside the province's LiDAR surveys."""


def covers(lat, lon):
    lat_min, lat_max, lon_min, lon_max = BOX
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def cell_for(radius_m):
    """The roof grid in metres: the LiDAR's own 0.5 m up to a 300 m radius, 1 m beyond."""
    return 0.5 if radius_m <= 300 else 1.0


def area(frame, bounds_m, cell_m):
    """(Web Mercator box, (width, height) in pixels) over local bounds [xmin, ymin, xmax, ymax], with
    pixels of about `cell_m` on the ground (a Mercator metre is cos(latitude) ground metres)."""
    xmin, ymin, xmax, ymax = bounds_m
    lon0, lat0 = frame.to_lonlat(xmin, ymin)
    lon1, lat1 = frame.to_lonlat(xmax, ymax)
    x0, y0 = lonlat_to_merc(lon0, lat0)
    x1, y1 = lonlat_to_merc(lon1, lat1)
    box = (round(float(x0), 3), round(float(y0), 3), round(float(x1), 3), round(float(y1), 3))
    step = cell_m / math.cos(math.radians(frame.lat0))
    size = (max(1, math.ceil((box[2] - box[0]) / step)), max(1, math.ceil((box[3] - box[1]) / step)))
    return box, size


def export_url(service, box, size):
    query = urllib.parse.urlencode({
        "bbox": ",".join(f"{v:.3f}" for v in box), "bboxSR": 3857, "imageSR": 3857,
        "size": f"{size[0]},{size[1]}", "format": "tiff", "pixelType": "F32", "compression": "None",
        "f": "image"})
    return f"{ROOT}/{service}/ImageServer/exportImage?{query}"


def check(body):
    """A TIFF the reader can read; ArcGIS sends its errors as JSON or HTML."""
    try:
        tiff.read(body)
    except tiff.TiffError as e:
        raise SourceError(f"Ontario's LiDAR service sent an image Ghost Town can't read ({e})") from None


class Heights:
    """Heights above ground (surface minus terrain) on the LiDAR grid, sampled at local points."""

    def __init__(self, surface, terrain, frame):
        """`surface` and `terrain` are tiff.read results for the same box and size."""
        top, x0, y0, dx, dy = surface
        bottom = terrain[0]
        if bottom.shape != top.shape:
            raise SourceError("Ontario's LiDAR surface and terrain images don't line up.")
        gaps = np.isnan(top) | np.isnan(bottom) | (top > NODATA_ABOVE) | (bottom > NODATA_ABOVE)
        self.grid = np.where(gaps, np.nan, top - bottom)
        self.x0, self.y0, self.dx, self.dy = x0, y0, dx, dy
        self.frame = frame

    def sample(self, xs, ys):
        """Bilinear heights at local points; NaN off the grid or where any of the four cells has none."""
        lon, lat = self.frame.to_lonlat(np.asarray(xs, dtype=float), np.asarray(ys, dtype=float))
        mx, my = lonlat_to_merc(lon, lat)
        return bilinear(self.grid, self.x0, self.y0, self.dx, self.dy, mx, my)


def fetch(net, frame, bounds_m, cell_m):
    """Heights over local bounds. Raises NoLidar outside the surveys and SourceError when the service
    fails. The terrain model is asked for only when the surface model has something there."""
    box, size = area(frame, bounds_m, cell_m)
    surface = tiff.read(net.get(export_url(SURFACE, box, size), source="ontario", check=check, timeout=TIMEOUT_S))
    if np.isnan(surface[0]).all():
        raise NoLidar(NONE_HERE)
    terrain = tiff.read(net.get(export_url(TERRAIN, box, size), source="ontario", check=check, timeout=TIMEOUT_S))
    return Heights(surface, terrain, frame)
