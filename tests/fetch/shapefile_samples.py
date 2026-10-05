"""Polygon shapefiles written for the tests, laid out like the City's 3D Massing download.

Local coordinates are metres around (43.65, -79.38), the centre toronto_samples uses; files hold Web
Mercator, with clockwise shells and counter-clockwise holes, as shapefiles do."""
import io
import struct
import zipfile

from ghosttown_fetch.frame import Frame, lonlat_to_merc

FIELDS = (("MIN_HEIGHT", "F", 19, 11), ("MAX_HEIGHT", "F", 19, 11), ("AVG_HEIGHT", "F", 19, 11),
          ("HEIGHT_MSL", "F", 19, 11), ("SURF_ELEV", "F", 19, 11), ("HEIGHT_SRC", "C", 30, 0),
          ("BLDG_SRC", "C", 30, 0), ("LONGITUDE", "F", 19, 11), ("LATITUDE", "F", 19, 11))
PRJ = (b'PROJCS["WGS_1984_Web_Mercator_Auxiliary_Sphere",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
       b'SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
       b'PROJECTION["Mercator_Auxiliary_Sphere"],UNIT["Meter",1.0]]')
_F = Frame(43.65, -79.38)


def _closed(ring):
    ring = [(float(x), float(y)) for x, y in ring]
    return ring if ring[0] == ring[-1] else ring + [ring[0]]


def _content(rings):
    if not rings:
        return struct.pack("<i", 0)  # a null shape
    rings = [_closed(r) for r in rings]
    pts = [p for r in rings for p in r]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    starts, n = [], 0
    for r in rings:
        starts.append(n)
        n += len(r)
    out = struct.pack("<i4d2i", 5, min(xs), min(ys), max(xs), max(ys), len(rings), len(pts))
    out += struct.pack(f"<{len(starts)}i", *starts)
    return out + b"".join(struct.pack("<2d", x, y) for x, y in pts)


def _header(length_bytes, bbox):
    return (struct.pack(">7i", 9994, 0, 0, 0, 0, 0, length_bytes // 2)
            + struct.pack("<2i", 1000, 5) + struct.pack("<8d", *bbox, 0.0, 0.0, 0.0, 0.0))


def _dbf(rows):
    header_len = 32 + 32 * len(FIELDS) + 1
    record_len = 1 + sum(width for _, _, width, _ in FIELDS)
    out = struct.pack("<B3BIHH20x", 3, 125, 12, 5, len(rows), header_len, record_len)
    for name, kind, width, decimals in FIELDS:
        out += struct.pack("<11sc4xBB14x", name.encode("ascii"), kind.encode("ascii"), width, decimals)
    out += b"\r"
    for row in rows:
        out += b" "
        for name, kind, width, decimals in FIELDS:
            value = row.get(name)
            if kind == "F":
                out += ("" if value is None else f"{float(value):.{decimals}e}").encode("ascii").rjust(width)
            else:
                out += str(value or "").encode("utf-8")[:width].ljust(width)
    return out + b"\x1a"


def write(records):
    """(.shp, .shx, .dbf) bytes for [(rings, row)]; rings in Web Mercator metres, row keyed by FIELDS."""
    pts = [p for rings, _ in records for r in rings for p in r]
    bbox = ((min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
            if pts else (0.0, 0.0, 0.0, 0.0))
    body, index, offset = b"", b"", 100
    for number, (rings, _) in enumerate(records, start=1):
        content = _content(rings)
        body += struct.pack(">2i", number, len(content) // 2) + content
        index += struct.pack(">2i", offset // 2, len(content) // 2)
        offset += 8 + len(content)
    return _header(100 + len(body), bbox) + body, _header(100 + len(index), bbox) + index, _dbf([r for _, r in records])


def zipped(records, stem="3DMassingShapefile_2099_WGS84"):
    shp, shx, dbf = write(records)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for ext, data in ((".shp", shp), (".shx", shx), (".dbf", dbf), (".prj", PRJ), (".cpg", b"UTF-8")):
            z.writestr(stem + ext, data)
        z.writestr("README_Metadata.xlsx", b"")
    return buffer.getvalue()


def merc_ring(points, clockwise=True):
    """Local-metre points as a Web Mercator ring, wound as asked."""
    ring = [tuple(float(v) for v in lonlat_to_merc(*_F.to_lonlat(x, y))) for x, y in points]
    twice_area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]))
    if (twice_area < 0) != clockwise:
        ring.reverse()
    return ring


def part(points, height, *, holes=(), ground=80.0, base=0.0, source="Lidar-Derived"):
    """A massing record: a footprint in local metres, standing `height` above its ground."""
    rings = [merc_ring(points)] + [merc_ring(h, clockwise=False) for h in holes]
    row = {"MIN_HEIGHT": base, "MAX_HEIGHT": 0.0, "AVG_HEIGHT": height, "HEIGHT_MSL": ground + height,
           "SURF_ELEV": ground, "HEIGHT_SRC": source, "BLDG_SRC": "Photogrammetrics",
           "LONGITUDE": -79.38, "LATITUDE": 43.65}
    return rings, row


def square(x0, y0, size):
    return [(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size)]
