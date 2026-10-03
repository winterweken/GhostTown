"""NRCan HRDEM bare-earth elevation (DTM) from the datacube WCS, as one GeoTIFF over the site."""
import math
import urllib.parse

import numpy as np

from .. import tiff
from ..frame import lonlat_to_merc
from ..net import SourceError

ENDPOINT = "https://datacube.services.geo.ca/wrapper/ogc/elevation-hrdem-mosaic"
CRS = "urn:ogc:def:crs:EPSG::3857"


def build_url(frame, half_m, cell_m):
    lons, lats = frame.to_lonlat(np.array([-half_m, half_m]), np.array([-half_m, half_m]))
    xs, ys = lonlat_to_merc(lons, lats)
    step = cell_m / math.cos(math.radians(frame.lat0))  # Web Mercator metres per ground metre at this latitude
    params = {
        "SERVICE": "WCS", "VERSION": "1.1.1", "REQUEST": "GetCoverage", "FORMAT": "image/geotiff",
        "IDENTIFIER": "dtm",
        "BOUNDINGBOX": f"{xs[0]:.0f},{ys[0]:.0f},{xs[1]:.0f},{ys[1]:.0f},{CRS}",
        "GRIDBASECRS": CRS,
        "GRIDOFFSETS": f"{step:.3f},{-step:.3f}",
    }
    return ENDPOINT + "?" + urllib.parse.urlencode(params, safe=":,")


def check(body):
    try:
        tiff.read(body)
    except tiff.TiffError as e:
        raise SourceError(f"Natural Resources Canada sent elevation data that couldn't be read ({e})") from None


def fetch(net, frame, half_m, cell_m):
    return tiff.read(net.get(build_url(frame, half_m, cell_m), source="nrcan", check=check))
