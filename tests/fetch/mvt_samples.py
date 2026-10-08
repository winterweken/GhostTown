"""A minimal Mapbox Vector Tile encoder for tests: one layer of polygon features."""
import base64


def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _field(number, wire, payload):
    key = _varint((number << 3) | wire)
    if wire == 0:
        return key + _varint(payload)
    return key + _varint(len(payload)) + payload


def _zigzag(n):
    return (n << 1) ^ (n >> 63)


def _commands(rings):
    cmds, x, y = [], 0, 0
    for ring in rings:
        (x0, y0), rest = ring[0], ring[1:]
        cmds += [1 | (1 << 3), _zigzag(x0 - x), _zigzag(y0 - y)]
        x, y = x0, y0
        cmds.append(2 | (len(rest) << 3))
        for px, py in rest:
            cmds += [_zigzag(px - x), _zigzag(py - y)]
            x, y = px, py
        cmds.append(7 | (1 << 3))
    return cmds


def tile(polygons, *, name="mpy-or", extent=4096, kind=3):
    """One layer; each polygon is a list of rings of integer tile coordinates."""
    features = b""
    for rings in polygons:
        packed = b"".join(_varint(c) for c in _commands(rings))
        features += _field(2, 2, _field(3, 0, kind) + _field(4, 2, packed))
    layer = _field(15, 0, 2) + _field(1, 2, name.encode("utf-8")) + features + _field(5, 0, extent)
    return _field(3, 2, layer)


def _area(ring):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]))


def detection(value, polygon_fraction, extent=4096):
    """A Mapillary-style label: its value and a base64 tile with one polygon given as (u, v) fractions."""
    ring = [(round(u * extent), round(v * extent)) for u, v in polygon_fraction]
    if _area(ring) < 0:
        ring.reverse()   # exterior rings have positive area in tile coordinates (y down)
    return {"value": value, "geometry": base64.b64encode(tile([[ring]], extent=extent)).decode("ascii")}
