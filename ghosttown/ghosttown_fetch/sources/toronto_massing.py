"""The City of Toronto's 3D Massing (the Context Massing Model), newest yearly edition.

City Planning publishes it on the open data portal under the Open Government Licence – Toronto, as one
city-wide shapefile per year (2025: 81 MB zipped, 428,184 parts), in Web Mercator despite its name.
Ghost Town downloads an edition once, keeps the unpacked files and an index of every part's box in the
cache folder, and reads only a site's parts from them. An older edition is deleted once a newer one is
ready; a copy that can't be read is deleted so the next build downloads it again.
"""
import io
import json
import mmap
import os
import re
import shutil
import tempfile
import zipfile
from collections import namedtuple

import numpy as np
import shapely

from .. import shapefile
from ..frame import lonlat_to_merc, merc_to_lonlat
from ..geom import polygons
from ..net import SourceError

PACKAGE = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_show?id=3d-massing"
_EDITION = re.compile(r"3DMassingShapefile_(\d{4})_WGS84\.zip")
FOLDER = "toronto_massing"
STEM = "massing"
MIN_HEIGHT_M = 0.5
SOURCES = {"Lidar-Derived": "toronto_massing_lidar", "3D Model": "toronto_massing_3d_model",
           "Site Plan": "toronto_massing_site_plan"}

Edition = namedtuple("Edition", "year url size")
Part = namedtuple("Part", "record polygons height base source")


def _check_package(body):
    try:
        doc = json.loads(body)
    except ValueError:
        raise SourceError("The City's open data portal didn't answer in JSON.") from None
    if not (isinstance(doc, dict) and doc.get("success") and isinstance((doc.get("result") or {}).get("resources"), list)):
        raise SourceError("The City's open data portal had no 3D Massing listing.")


def _size(value):
    """The listed size in bytes, or 0 (unknown) when the portal gives something else."""
    try:
        return max(int(value), 0)
    except (TypeError, ValueError, OverflowError):
        return 0


def newest_edition(net):
    doc = json.loads(net.get(PACKAGE, source="toronto", check=_check_package))
    found = []
    for resource in doc["result"]["resources"]:
        if not isinstance(resource, dict):
            continue
        m = _EDITION.fullmatch(str(resource.get("name", "")))
        if m and isinstance(resource.get("url"), str) and resource["url"]:
            found.append(Edition(int(m.group(1)), resource["url"], _size(resource.get("size"))))
    if not found:
        raise SourceError("The City's open data portal lists no 3D Massing shapefile.")
    return max(found)


def _check_zip(body):
    try:
        names = zipfile.ZipFile(io.BytesIO(body)).namelist()
    except zipfile.BadZipFile:
        raise SourceError("The City's 3D Massing download isn't a whole zip file.") from None
    if not all(any(n.lower().endswith(ext) for n in names) for ext in (".shp", ".shx", ".dbf")):
        raise SourceError("The City's 3D Massing download is missing part of the shapefile.")


def _ready(folder):
    return all(os.path.isfile(os.path.join(folder, STEM + ext)) for ext in (".shp", ".shx", ".dbf", ".npy"))


def _index(folder):
    """massing.npy: per record, its byte offset in the .shp and its box (NaN for null shapes)."""
    with open(os.path.join(folder, STEM + ".shx"), "rb") as f:
        offsets = shapefile.record_offsets(f.read())
    with open(os.path.join(folder, STEM + ".shp"), "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as shp:
        shapefile.check_header(shp)
        boxes = shapefile.bounding_boxes(shp, offsets)
    np.save(os.path.join(folder, STEM + ".npy"), np.column_stack([offsets.astype(float), boxes]))


def local_copy(net, cache_dir, edition, progress=None):
    """The folder with the edition's massing.shp/.shx/.dbf and its index, downloaded the first time."""
    root = os.path.join(cache_dir, FOLDER)
    folder = os.path.join(root, str(edition.year))
    if not _ready(folder):
        if progress:
            size = f"{edition.size / 1e6:.0f} MB" if edition.size else "it"
            progress(f"City massing model (first time: downloading {size})", 30)
        body = net.get(edition.url, source="toronto", check=_check_zip, keep=False, timeout=600)
        os.makedirs(root, exist_ok=True)
        staging = tempfile.mkdtemp(prefix=".staging-", dir=root)
        try:
            with zipfile.ZipFile(io.BytesIO(body)) as z:
                for name in z.namelist():
                    ext = os.path.splitext(name)[1].lower()
                    if ext in (".shp", ".shx", ".dbf", ".prj"):
                        with z.open(name) as src, open(os.path.join(staging, STEM + ext), "wb") as dst:
                            shutil.copyfileobj(src, dst)
            _index(staging)
            shutil.rmtree(folder, ignore_errors=True)
            os.replace(staging, folder)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    for name in os.listdir(root):
        if name.isdigit() and name != str(edition.year):
            shutil.rmtree(os.path.join(root, name), ignore_errors=True)
    return folder


def _to_local(frame):
    def convert(coords):
        lon, lat = merc_to_lonlat(coords[:, 0], coords[:, 1])
        return np.column_stack(frame.to_local(lon, lat))
    return convert


def site_parts(folder, frame, radius_m):
    """Every part over 0.5 m tall whose box meets the square around the circle of radius_m."""
    table = np.load(os.path.join(folder, STEM + ".npy"))
    x0, y0 = lonlat_to_merc(*frame.to_lonlat(-radius_m, -radius_m))
    x1, y1 = lonlat_to_merc(*frame.to_lonlat(radius_m, radius_m))
    boxes = table[:, 1:]
    with np.errstate(invalid="ignore"):  # null shapes have NaN boxes, which compare False
        rows = np.nonzero((boxes[:, 2] >= x0) & (boxes[:, 0] <= x1) & (boxes[:, 3] >= y0) & (boxes[:, 1] <= y1))[0]
    to_local = _to_local(frame)
    parts = []
    with open(os.path.join(folder, STEM + ".shp"), "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as shp, \
            open(os.path.join(folder, STEM + ".dbf"), "rb") as g, mmap.mmap(g.fileno(), 0, access=mmap.ACCESS_READ) as dbf:
        attributes = shapefile.DBF(dbf)
        for i in rows:
            row = attributes.record(int(i))
            height = (row.get("HEIGHT_MSL") or 0.0) - (row.get("SURF_ELEV") or 0.0)
            if height <= MIN_HEIGHT_M:
                continue
            local = []
            try:
                for poly in shapefile.polygons_from_rings(shapefile.polygon_rings(shp, table[i, 0])):
                    local += polygons(shapely.transform(poly, to_local))
            except shapely.errors.GEOSException:
                local = []  # one part the geometry library can't repair is left out
            if local:
                parts.append(Part(int(i), local, float(height), float(row.get("MIN_HEIGHT") or 0.0),
                                  SOURCES.get(row.get("HEIGHT_SRC") or "", "toronto_massing")))
        del attributes  # release the map before it closes
    return parts


def fetch(net, cache_dir, frame, radius_m, progress=None):
    """(parts, edition year) for the square around a circle of radius_m. Every failure is a SourceError;
    a local copy that can't be read is deleted so the next build downloads it again."""
    edition = newest_edition(net)
    folder = os.path.join(cache_dir, FOLDER, str(edition.year))
    try:
        folder = local_copy(net, cache_dir, edition, progress)
        return site_parts(folder, frame, radius_m), edition.year
    except SourceError:
        raise
    except Exception as e:  # not BaseException: Ctrl-C still stops the build
        shutil.rmtree(folder, ignore_errors=True)
        raise SourceError(f"The City's 3D Massing model couldn't be read ({type(e).__name__}: {e}).") from None
