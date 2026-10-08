"""Polygons from a Mapbox Vector Tile, the format of Mapillary's image labels. Standard library only.

Coordinates come back as fractions of the tile extent with y pointing down, which for Mapillary's labels
are fractions of the image's width and height."""
MOVE_TO, LINE_TO, CLOSE_PATH = 1, 2, 7
POLYGON = 3


class TileError(ValueError):
    """The tile can't be read."""


def _varint(buf, i):
    shift = value = 0
    while True:
        if i >= len(buf):
            raise TileError("The tile ends inside a number.")
        b = buf[i]
        i += 1
        value |= (b & 0x7F) << shift
        if not b & 0x80:
            return value, i
        shift += 7
        if shift > 63:
            raise TileError("A number in the tile is too long.")


def _fields(buf):
    """(field number, wire type, value) for each field; length-delimited values are bytes."""
    i, out = 0, []
    while i < len(buf):
        key, i = _varint(buf, i)
        field, wire = key >> 3, key & 7
        if wire == 0:
            value, i = _varint(buf, i)
        elif wire == 2:
            n, i = _varint(buf, i)
            if i + n > len(buf):
                raise TileError("A field runs past the end of the tile.")
            value, i = bytes(buf[i:i + n]), i + n
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            if i + size > len(buf):
                raise TileError("A field runs past the end of the tile.")
            value, i = bytes(buf[i:i + size]), i + size
        else:
            raise TileError(f"Unknown wire type {wire}.")
        out.append((field, wire, value))
    return out


def _packed(value):
    nums, i = [], 0
    while i < len(value):
        n, i = _varint(value, i)
        nums.append(n)
    return nums


def _zigzag(n):
    return (n >> 1) ^ -(n & 1)


def _rings(commands):
    rings, ring, x, y, i = [], [], 0, 0, 0
    while i < len(commands):
        cmd, count = commands[i] & 7, commands[i] >> 3
        i += 1
        if cmd in (MOVE_TO, LINE_TO):
            if i + 2 * count > len(commands):
                raise TileError("A path in the tile is cut short.")
            for _ in range(count):
                x += _zigzag(commands[i])
                y += _zigzag(commands[i + 1])
                i += 2
                if cmd == MOVE_TO:
                    if len(ring) >= 3:
                        rings.append(ring)
                    ring = [(x, y)]
                else:
                    ring.append((x, y))
        elif cmd == CLOSE_PATH:
            if len(ring) >= 3:
                rings.append(ring)
            ring = []
        else:
            raise TileError(f"Unknown path command {cmd}.")
    if len(ring) >= 3:
        rings.append(ring)
    return rings


def _area(ring):
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]))


def decode_polygons(data):
    """[(layer name, [exterior, *holes])] for every polygon feature. A ring with positive area in tile
    coordinates starts a new polygon (as the MVT spec defines exteriors); the rings after it with negative
    area are its holes."""
    out = []
    for field, wire, layer in _fields(data):
        if field != 3 or wire != 2:
            continue
        name, extent, features = "", 4096, []
        for f2, w2, v2 in _fields(layer):
            if f2 == 1 and w2 == 2:
                name = v2.decode("utf-8", "replace")
            elif f2 == 5 and w2 == 0:
                extent = v2 or 4096
            elif f2 == 2 and w2 == 2:
                features.append(v2)
        for feature in features:
            kind, geometry = 0, []
            for f3, w3, v3 in _fields(feature):
                if f3 == 3 and w3 == 0:
                    kind = v3
                elif f3 == 4 and w3 == 2:
                    geometry = _packed(v3)
            if kind != POLYGON:
                continue
            polygon = None
            for ring in _rings(geometry):
                scaled = [(px / extent, py / extent) for px, py in ring]
                if polygon is None or _area(ring) > 0:
                    polygon = [scaled]
                    out.append((name, polygon))
                else:
                    polygon.append(scaled)
    return out
