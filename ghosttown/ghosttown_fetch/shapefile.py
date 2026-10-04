"""Reading ESRI polygon shapefiles (.shp, .shx) and their dBase tables (.dbf). Standard library, numpy
and shapely only.

Just what the City's 3D Massing model needs. Records are read one at a time from bytes or a memory
map, so a site never loads the whole city. Rings come back as copies, so the map can be closed."""
import struct

import numpy as np
from shapely.geometry import Polygon

POLYGON_TYPES = (5, 15, 25)  # Polygon, PolygonZ, PolygonM: the x, y part is laid out the same


class ShapefileError(ValueError):
    """The files aren't a polygon shapefile Ghost Town can read."""


def check_header(shp):
    if len(shp) < 100 or struct.unpack_from(">i", shp, 0)[0] != 9994:
        raise ShapefileError("not a shapefile")
    shape_type = struct.unpack_from("<i", shp, 32)[0]
    if shape_type not in POLYGON_TYPES:
        raise ShapefileError(f"shape type {shape_type} isn't polygons")


def record_offsets(shx):
    """Byte offset of each record's header in the .shp, from the .shx index."""
    if len(shx) < 100 or (len(shx) - 100) % 8 or struct.unpack_from(">i", shx, 0)[0] != 9994:
        raise ShapefileError("not a shapefile index")
    words = np.frombuffer(shx, dtype=">i4", offset=100).reshape(-1, 2)
    return words[:, 0].astype(np.int64) * 2


def bounding_boxes(shp, offsets):
    """(n, 4) [xmin, ymin, xmax, ymax] per record; NaN rows for null shapes."""
    out = np.full((len(offsets), 4), np.nan)
    for i, offset in enumerate(offsets):
        content = int(offset) + 8
        if struct.unpack_from("<i", shp, content)[0] in POLYGON_TYPES:
            out[i] = struct.unpack_from("<4d", shp, content + 4)
    return out


def polygon_rings(shp, offset):
    """The record's rings as (k, 2) arrays (copies); [] for a null shape."""
    content = int(offset) + 8
    if struct.unpack_from("<i", shp, content)[0] not in POLYGON_TYPES:
        return []
    nparts, npoints = struct.unpack_from("<2i", shp, content + 36)
    starts = list(struct.unpack_from(f"<{nparts}i", shp, content + 44)) + [npoints]
    points = np.frombuffer(shp, dtype="<f8", count=npoints * 2, offset=content + 44 + 4 * nparts).reshape(-1, 2)
    return [points[starts[k]:starts[k + 1]].copy() for k in range(nparts)]


def _twice_signed_area(ring):
    x, y = ring[:, 0], ring[:, 1]
    return float(np.dot(x[:-1], y[1:]) - np.dot(x[1:], y[:-1]))


def polygons_from_rings(rings):
    """Clockwise rings are shells and counter-clockwise ones holes, each hole going to the smallest
    shell that holds it. A hole with no shell around it is taken as a shell (its winding was wrong).
    Rings under four points are skipped. The polygons may still need repair."""
    shells, holes = [], []
    for ring in rings:
        if len(ring) >= 4:
            (shells if _twice_signed_area(ring) < 0 else holes).append(ring)
    outlines = [Polygon(shell) for shell in shells]
    owned = [[] for _ in shells]
    for hole in holes:
        probe = Polygon(hole).representative_point()
        inside = [i for i, outline in enumerate(outlines) if outline.contains(probe)]
        if inside:
            owned[min(inside, key=lambda i: outlines[i].area)].append(hole)
        else:
            shells.append(hole)
            outlines.append(Polygon(hole))
            owned.append([])
    return [Polygon(shell, owned[i]) for i, shell in enumerate(shells)]


class DBF:
    """A dBase table read record by record from bytes or a memory map."""

    def __init__(self, data, encoding="utf-8"):
        if len(data) < 33:
            raise ShapefileError("not a dBase table")
        self.data, self.encoding = data, encoding
        self.count, self.header_len, self.record_len = struct.unpack_from("<IHH", data, 4)
        self.fields, pos, start = [], 32, 1
        while pos + 32 <= self.header_len and data[pos] != 0x0D:
            name = bytes(data[pos:pos + 11]).split(b"\0")[0].decode("ascii", "replace")
            self.fields.append((name, chr(data[pos + 11]), start, data[pos + 16]))
            start += data[pos + 16]
            pos += 32

    def __len__(self):
        return self.count

    def record(self, i):
        base = self.header_len + i * self.record_len
        row = {}
        for name, kind, start, width in self.fields:
            raw = bytes(self.data[base + start:base + start + width]).strip()
            if kind in "NF":
                try:
                    row[name] = float(raw) if raw and not raw.startswith(b"*") else None
                except ValueError:
                    row[name] = None
            else:
                row[name] = raw.decode(self.encoding, "replace")
        return row
