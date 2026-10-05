"""The City of Toronto's newest aerial photo of a site, as one JPEG. Standard library and numpy only.

The City publishes one orthophoto service per year in the `basemap` folder on gis.toronto.ca, named
cot_ortho_<year>_color_<n>cm, under the Open Government Licence – Toronto. `export` answers a Web
Mercator box with one image of up to 4,096 px a side, and honours a square box exactly. It is a
standard orthophoto: tall buildings lean.
"""
import json
import math
import os
import re
import urllib.parse

from ..cache import atomic_write
from ..frame import lonlat_to_merc, merc_to_lonlat
from ..net import SourceError

ROOT = "https://gis.toronto.ca/arcgis/rest/services"
LISTING = ROOT + "/basemap?f=json"
CURRENT = "basemap/cot_ortho"        # the City's "current year" service, used when the listing can't say
_YEARLY = re.compile(r"basemap/cot_ortho_(\d{4})_color_(\d+)cm")
MAX_PX = 4096
NATIVE_M = 0.08                      # the newest photos' pixel size; finer requests add nothing
FILE = "photo.jpg"


def _check_listing(body):
    try:
        doc = json.loads(body)
    except ValueError:
        raise SourceError("The City's list of map services isn't JSON.") from None
    if not (isinstance(doc, dict) and isinstance(doc.get("services"), list)):
        raise SourceError("The City's list of map services has no services in it.")


def newest(net):
    """(service name, year or None): the newest yearly photo, else the current-year service."""
    try:
        listing = json.loads(net.get(LISTING, source="toronto", check=_check_listing))
    except SourceError:
        return CURRENT, None
    years = []
    for service in listing["services"]:
        m = _YEARLY.fullmatch(str(service.get("name", "")))
        if m and service.get("type") == "MapServer":
            years.append((int(m.group(1)), service["name"]))
    if not years:
        return CURRENT, None
    year, name = max(years)
    return name, year


def area(frame, radius_m):
    """(Web Mercator box, bounds in local metres) of the site square, x and y from -r to +r.

    x maps exactly between the two. Along y, Mercator stretches with latitude, which the straight
    mapping from the box to local metres ignores: under 10 cm at a 1000 m radius, well under a pixel."""
    lon0, lat0 = frame.to_lonlat(-radius_m, -radius_m)
    lon1, lat1 = frame.to_lonlat(radius_m, radius_m)
    x0, y0 = lonlat_to_merc(lon0, lat0)
    x1, y1 = lonlat_to_merc(lon1, lat1)
    box = (round(float(x0), 3), round(float(y0), 3), round(float(x1), 3), round(float(y1), 3))
    lons, lats = merc_to_lonlat([box[0], box[2]], [box[1], box[3]])
    bx0, by0 = frame.to_local(float(lons[0]), float(lats[0]))
    bx1, by1 = frame.to_local(float(lons[1]), float(lats[1]))
    return box, [round(bx0, 3), round(by0, 3), round(bx1, 3), round(by1, 3)]


def size_px(radius_m):
    return min(MAX_PX, math.ceil(2 * radius_m / NATIVE_M))


def export_url(service, box, size):
    query = urllib.parse.urlencode({
        "bbox": ",".join(f"{v:.3f}" for v in box), "bboxSR": 3857, "imageSR": 3857,
        "size": f"{size},{size}", "format": "jpg", "f": "image"})
    return f"{ROOT}/{service}/MapServer/export?{query}"


def check(body):
    """A whole JPEG, judged by its start and end markers; ArcGIS sends errors as JSON or HTML."""
    if len(body) <= 1024 or body[:2] != b"\xff\xd8" or body.rstrip(b"\x00")[-2:] != b"\xff\xd9":
        raise SourceError("The City's aerial photo service didn't send a whole JPEG image.")


def fetch(net, frame, radius_m, out_dir):
    """The site's photo, written to <out_dir>/photo.jpg; returns the context's `photo` block."""
    service, year = newest(net)
    box, bounds = area(frame, radius_m)
    size = size_px(radius_m)
    body = net.get(export_url(service, box, size), source="toronto", check=check)
    atomic_write(os.path.join(out_dir, FILE), body)
    return {"file": FILE, "year": year, "width_px": size, "height_px": size, "bounds_m": bounds,
            "source": "toronto"}
