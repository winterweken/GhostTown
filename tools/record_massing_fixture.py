"""Record a slice of the City's newest 3D Massing edition for the offline tests.

    uv run python tools/record_massing_fixture.py

Writes tests/fetch/fixtures/bay/massing_subset.zip: every part whose box meets ±200 m around
320 Bay St, in the download's own layout. The first run downloads the whole edition (81 MB) into
.cache-record/. Contains information licensed under the Open Government Licence – Toronto.
"""
import mmap
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "ghosttown"), os.path.join(ROOT, "tests", "fetch")]

from ghosttown_fetch import shapefile  # noqa: E402
from ghosttown_fetch.frame import Frame, lonlat_to_merc  # noqa: E402
from ghosttown_fetch.net import Net  # noqa: E402
from ghosttown_fetch.sources import toronto_massing as massing  # noqa: E402
from shapefile_samples import zipped  # noqa: E402

if __name__ == "__main__":
    cache = os.path.join(ROOT, ".cache-record")
    net = Net(cache)
    edition = massing.newest_edition(net)
    folder = massing.local_copy(net, cache, edition, progress=lambda stage, pct: print(stage))
    table = np.load(os.path.join(folder, "massing.npy"))
    frame = Frame(43.649667, -79.380991)
    x0, y0 = lonlat_to_merc(*frame.to_lonlat(-200.0, -200.0))
    x1, y1 = lonlat_to_merc(*frame.to_lonlat(200.0, 200.0))
    boxes = table[:, 1:]
    with np.errstate(invalid="ignore"):
        rows = np.nonzero((boxes[:, 2] >= x0) & (boxes[:, 0] <= x1) & (boxes[:, 3] >= y0) & (boxes[:, 1] <= y1))[0]
    records = []
    with open(os.path.join(folder, "massing.shp"), "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as shp, \
            open(os.path.join(folder, "massing.dbf"), "rb") as g, mmap.mmap(g.fileno(), 0, access=mmap.ACCESS_READ) as dbf:
        attributes = shapefile.DBF(dbf)
        for i in rows:
            rings = [[tuple(p) for p in ring.tolist()] for ring in shapefile.polygon_rings(shp, table[i, 0])]
            records.append((rings, attributes.record(int(i))))
        del attributes
    data = zipped(records, stem=f"3DMassingShapefile_{edition.year}_WGS84")
    path = os.path.join(ROOT, "tests", "fetch", "fixtures", "bay", "massing_subset.zip")
    with open(path, "wb") as out:
        out.write(data)
    print(f"{edition.year}: {len(records)} parts, {len(data):,} bytes -> {path}")
