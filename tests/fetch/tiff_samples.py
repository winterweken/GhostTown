"""Minimal GeoTIFF writer for tests: single-band float32, striped or tiled, either byte order."""
import struct
import urllib.parse

import numpy as np


def write_tiff(grid, x, y, dx, dy, *, big_endian=False, tile=None, rows_per_strip=2, nodata="-32767",
               compression=1, tie_pixel=(0, 0), edit=None, sparse=()):
    bo = ">" if big_endian else "<"
    arr = np.asarray(grid, dtype=bo + "f4")
    h, w = arr.shape
    blocks = []
    if tile:
        down, across = -(-h // tile), -(-w // tile)
        canvas = np.zeros((down * tile, across * tile), dtype=arr.dtype)
        canvas[:h, :w] = arr
        for r in range(down):
            for c in range(across):
                blocks.append(canvas[r * tile:(r + 1) * tile, c * tile:(c + 1) * tile].tobytes())
    else:
        for r in range(0, h, rows_per_strip):
            blocks.append(arr[r:r + rows_per_strip].tobytes())
    data = bytearray(b"MM\x00*" if big_endian else b"II*\x00") + b"\0\0\0\0"
    offsets = []
    for block in blocks:
        offsets.append(len(data))
        data += block
    counts = [len(b) for b in blocks]
    for k in sparse:  # a sparse file leaves these tiles out
        offsets[k] = counts[k] = 0
    i, j = tie_pixel
    entries = [(256, 4, [w]), (257, 4, [h]), (258, 3, [32]), (259, 3, [compression]), (277, 3, [1]),
               (339, 3, [3]), (33550, 12, [dx, dy, 0.0]), (33922, 12, [float(i), float(j), 0.0, x, y, 0.0])]
    if nodata is not None:
        entries.append((42113, 2, nodata))
    if tile:
        entries += [(322, 4, [tile]), (323, 4, [tile]), (324, 4, offsets), (325, 4, counts)]
    else:
        entries += [(273, 4, offsets), (278, 4, [rows_per_strip]), (279, 4, counts)]
    if edit is not None:
        entries = edit(entries)  # tests damage tags here
    entries.sort()
    if len(data) % 2:
        data += b"\0"
    ifd_at = len(data)
    struct.pack_into(bo + "I", data, 4, ifd_at)
    extra_at = ifd_at + 2 + 12 * len(entries) + 4
    ifd, extra = bytearray(struct.pack(bo + "H", len(entries))), bytearray()
    for tag, typ, vals in entries:
        if typ == 2:
            payload, count = vals.encode("ascii") + b"\0", len(vals) + 1
        else:
            fmt = {3: "H", 4: "I", 12: "d"}[typ]
            payload, count = struct.pack(bo + fmt * len(vals), *vals), len(vals)
        if len(payload) <= 4:
            field = payload.ljust(4, b"\0")
        else:
            field = struct.pack(bo + "I", extra_at + len(extra))
            extra += payload + (b"\0" if len(payload) % 2 else b"")
        ifd += struct.pack(bo + "HHI", tag, typ, count) + field
    ifd += b"\0\0\0\0"
    return bytes(data + ifd + extra)


def east_slope_tiff(frame, half=300.0, step=2.0, rise_per_col=0.05, base=80.0, gaps=None):
    """A Web Mercator grid around `frame` whose height rises eastwards; `gaps(rows, cols)` marks nodata."""
    from ghosttown_fetch.frame import lonlat_to_merc

    lons, lats = frame.to_lonlat(np.array([-half, half]), np.array([-half, half]))
    xs, ys = lonlat_to_merc(lons, lats)
    cols, rows = int((xs[1] - xs[0]) / step), int((ys[1] - ys[0]) / step)
    grid = base + rise_per_col * np.tile(np.arange(cols, dtype=float), (rows, 1))
    if gaps is not None:
        grid[gaps(rows, cols)] = -32767.0
    return write_tiff(grid, float(xs[0]), float(ys[1]), step, step)


def nrcan_server(height, tile=256):
    """A FakeNet answer that acts like NRCan's WCS as seen live on 2026-10-04. The coverage reaches half a
    pixel past the box on every side and holds int(width / offset) + 1 pixels each way, stretched to fit, so
    a box a whole number of pixels wide can lose a pixel to rounding. Each height is `height(mx, my)` at its
    pixel's centre, and a coverage bigger than one GeoTIFF tile comes back as `null`."""
    def answer(url, data):
        q = dict(urllib.parse.parse_qsl(url.split("?", 1)[1]))
        x0, y0, x1, y1 = (float(v) for v in q["BOUNDINGBOX"].split(",")[:4])
        step = float(q["GRIDOFFSETS"].split(",")[0])
        cols, rows = int((x1 - x0) / step) + 1, int((y1 - y0) / step) + 1
        if max(cols, rows) > tile:
            return b"null"
        dx, dy = (x1 - x0 + step) / cols, (y1 - y0 + step) / rows
        left, top = x0 - step / 2, y1 + step / 2
        mx, my = left + dx * (np.arange(cols) + 0.5), top - dy * (np.arange(rows) + 0.5)
        grid = np.broadcast_to(height(mx[None, :], my[:, None]), (rows, cols))
        return write_tiff(grid, left, top, dx, dy, tile=tile)
    return answer
