"""NRCan HRDEM bare-earth elevation (DTM) from the datacube WCS, as GeoTIFFs over the site.

The service answers a coverage that fits in one 256-pixel GeoTIFF tile, but a bigger one comes back as
`null` or as a file cut off partway (every time, for a 300 m site, on 2026-10-04). So a wide site is asked
for in pieces of at most PIECE_STEPS pixels on one pixel grid. A coverage's corners are pixel centres, so
neighbouring pieces share a row or column of the same heights and join without a seam."""
import math
import urllib.parse

import numpy as np

from .. import tiff
from ..frame import lonlat_to_merc
from ..net import SourceError

ENDPOINT = "https://datacube.services.geo.ca/wrapper/ogc/elevation-hrdem-mosaic"
CRS = "urn:ogc:def:crs:EPSG::3857"
PIECE_STEPS = 250  # pixels a side per request, inside one 256-pixel tile
PAD_M = 0.001      # NRCan counts int(width / offset) + 1 pixels; past a whole number, rounding can't lose one


def build_url(box, step):
    params = {
        "SERVICE": "WCS", "VERSION": "1.1.1", "REQUEST": "GetCoverage", "FORMAT": "image/geotiff",
        "IDENTIFIER": "dtm",
        "BOUNDINGBOX": ",".join(f"{v:.3f}" for v in box) + "," + CRS,
        "GRIDBASECRS": CRS,
        "GRIDOFFSETS": f"{step:.3f},{-step:.3f}",
    }
    return ENDPOINT + "?" + urllib.parse.urlencode(params, safe=":,")


def _split(steps):
    count = -(-steps // PIECE_STEPS)
    edges = [round(k * steps / count) for k in range(count + 1)]
    return list(zip(edges[:-1], edges[1:]))


def pieces(frame, half_m, cell_m):
    """(step, cols, rows, [(col, row, url)]): the site's pixel grid in Web Mercator, `cols` × `rows` steps
    with a pixel every `step` metres, and the requests that cover it. Each request's top-left pixel sits
    at (col, row) in the whole grid, counted from the north-west corner."""
    lons, lats = frame.to_lonlat(np.array([-half_m, half_m]), np.array([-half_m, half_m]))
    xs, ys = lonlat_to_merc(lons, lats)
    west, north = round(float(xs[0]), 3), round(float(ys[1]), 3)
    step = round(cell_m / math.cos(math.radians(frame.lat0)), 3)  # one cell in Web Mercator metres here
    cols, rows = math.ceil((xs[1] - west) / step), math.ceil((north - ys[0]) / step)
    out = []
    for c0, c1 in _split(cols):
        for r0, r1 in _split(rows):
            box = (west + c0 * step, north - r1 * step - PAD_M, west + c1 * step + PAD_M, north - r0 * step)
            out.append((c0, r0, build_url(box, step)))
    return step, cols, rows, out


def _read(body):
    try:
        return tiff.read(body)
    except tiff.TiffError as e:
        raise SourceError(f"Natural Resources Canada sent elevation data that couldn't be read ({e})") from None


def check(body):
    _read(body)


def _join(answers, step, cols, rows):
    """One grid from the pieces' answers, each placed by its own georeferencing. A piece in NRCan's 1×1
    "no data" form has the wrong pixel size and leaves a gap."""
    fits = [(c, r, a) for c, r, a in answers
            if math.isclose(a[3], step, rel_tol=0.01) and math.isclose(a[4], step, rel_tol=0.01)]
    if not fits:
        return answers[0][2]
    c, r, (_, x0, y0, dx, dy) = fits[0]
    x0, y0 = x0 - c * dx, y0 + r * dy
    canvas = np.full((rows + 1, cols + 1), np.nan)
    for c, r, (grid, gx, gy, _, _) in fits:
        col, row = round((gx - x0) / dx), round((y0 - gy) / dy)
        if (col, row) != (c, r):
            raise SourceError("Natural Resources Canada sent elevation pieces that don't line up.")
        under = canvas[row:row + grid.shape[0], col:col + grid.shape[1]]
        part = grid[:under.shape[0], :under.shape[1]]
        under[...] = np.where(np.isnan(part), under, part)
    return canvas, x0, y0, dx, dy


def fetch(net, frame, half_m, cell_m):
    """The elevation grid. An unreadable file is a SourceError wherever it came from, a stored answer
    included, so the build carries on with flat ground."""
    step, cols, rows, requests = pieces(frame, half_m, cell_m)
    answers = [(c, r, _read(net.get(url, source="nrcan", check=check))) for c, r, url in requests]
    if len(answers) == 1:
        return answers[0][2]
    return _join(answers, step, cols, rows)
