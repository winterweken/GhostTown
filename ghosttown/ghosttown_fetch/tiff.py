"""Minimal GeoTIFF reader for NRCan elevation: one band of uncompressed 32-bit floats, striped or tiled
(with padding), in either byte order, georeferenced by ModelPixelScale and ModelTiepoint."""
import struct

import numpy as np

_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8, 16: 8}
_FMT = {1: "B", 3: "H", 4: "I", 6: "b", 8: "h", 9: "i", 11: "f", 12: "d", 16: "Q"}


class TiffError(ValueError):
    """The elevation file can't be read; the message is one sentence."""


def read(data):
    """-> (grid, x0, y0, dx, dy): float64 rows × cols with NaN for nodata; top-left corner; pixel size."""
    if len(data) < 8 or data[:4] not in (b"II*\x00", b"MM\x00*"):
        raise TiffError("This isn't a TIFF file.")
    bo = "<" if data[:2] == b"II" else ">"
    try:
        tags = _tags(data, bo)
    except struct.error:
        raise TiffError("The TIFF file is cut short.") from None
    w, h = _one(tags, 256, 0), _one(tags, 257, 0)
    if w <= 0 or h <= 0:
        raise TiffError("The TIFF file has no image size.")
    if _one(tags, 259, 1) != 1:
        raise TiffError("Compressed TIFFs aren't supported.")
    if _one(tags, 258, 32) != 32 or _one(tags, 339, 1) != 3 or _one(tags, 277, 1) != 1:
        raise TiffError("Only single-band 32-bit float TIFFs are supported.")
    dtype = np.dtype(bo + "f4")
    try:
        grid = _tiled(data, dtype, w, h, tags) if 322 in tags else _striped(data, dtype, w, h, tags)
    except (ValueError, IndexError, KeyError):
        raise TiffError("The TIFF file is cut short.") from None
    grid = grid.astype(np.float64)
    nodata = tags.get(42113)
    if isinstance(nodata, str):
        try:
            grid[grid == float(nodata)] = np.nan
        except ValueError:
            pass
    grid[~np.isfinite(grid)] = np.nan
    if 33550 not in tags or 33922 not in tags:
        raise TiffError("The TIFF file has no georeferencing.")
    dx, dy = tags[33550][0], tags[33550][1]
    i, j, _k, x, y, _z = tags[33922][:6]
    return grid, x - i * dx, y + j * dy, dx, dy


def _tags(data, bo):
    (ifd,) = struct.unpack_from(bo + "I", data, 4)
    (n,) = struct.unpack_from(bo + "H", data, ifd)
    tags = {}
    for k in range(n):
        at = ifd + 2 + 12 * k
        tag, typ, count = struct.unpack_from(bo + "HHI", data, at)
        size = _SIZE.get(typ, 1) * count
        where = at + 8
        if size > 4:
            (where,) = struct.unpack_from(bo + "I", data, where)
        raw = data[where:where + size]
        if len(raw) < size:
            raise struct.error("short tag")
        if typ == 2:
            tags[tag] = raw.split(b"\0", 1)[0].decode("ascii", "replace")
        elif typ in _FMT:
            tags[tag] = struct.unpack(bo + _FMT[typ] * count, raw)
    return tags


def _one(tags, tag, default):
    value = tags.get(tag)
    return value[0] if isinstance(value, tuple) and value else default


def _tiled(data, dtype, w, h, tags):
    tw, th = _one(tags, 322, 0), _one(tags, 323, 0)
    across, down = -(-w // tw), -(-h // th)
    offsets = tags[324]
    if len(offsets) < across * down:
        raise ValueError("missing tiles")
    canvas = np.empty((down * th, across * tw), dtype=dtype)
    for k in range(across * down):
        row, col = divmod(k, across)
        block = np.frombuffer(data, dtype=dtype, count=tw * th, offset=offsets[k]).reshape(th, tw)
        canvas[row * th:(row + 1) * th, col * tw:(col + 1) * tw] = block
    return canvas[:h, :w]


def _striped(data, dtype, w, h, tags):
    joined = b"".join(data[o:o + c] for o, c in zip(tags[273], tags[279]))
    flat = np.frombuffer(joined, dtype=dtype, count=len(joined) // dtype.itemsize)
    if flat.size < w * h:
        raise ValueError("short strips")
    return flat[:w * h].reshape(h, w)
