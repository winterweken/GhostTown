"""Detail geometry for a building with Street Look: a band on every floor (heavier near zone boundaries),
a band at the top of the storefront, and mullion fins on glass. Pure Python, no bpy.

Heights in a look entry are metres above the building's lowest point; base_z turns them into scene z.
The bands and fins sit on the lines the Street Look shader paints (materials.py), so the 3D detail and the
painted facade coincide: floor lines at whole floors above the building's lowest point, mullions at multiples
of the glass bay along the wall, measured from the model's origin."""
import math

FLOOR_BAND = (0.10, 0.12)        # half height, depth (m)
ZONE_BAND = (0.25, 0.35)
STOREFRONT_BAND = (0.15, 0.50)
FIN = (0.04, 0.12)               # half width, depth
GLASS_BAY_M = 1.5
TOP_CLEARANCE_M = 0.2
MIN_FLOOR_M = 1.0                # the shader's own floor on floor_h, so a damaged look can't make millions of bands

# a unit box as (along, out, up) corners of right-handed outward faces
_FACES = (((0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)),
          ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)),
          ((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)),
          ((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)),
          ((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)),
          ((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)))


def _box(verts, faces, a, b, n, z0, z1, depth):
    """A closed box along a->b, from the wall out to `depth` metres along n, from z0 to z1."""
    k = len(verts)
    for p in (a, b):
        for d in (0.0, depth):
            for z in (z0, z1):
                verts.append((p[0] + n[0] * d, p[1] + n[1] * d, z))
    t = (b[0] - a[0], b[1] - a[1])
    left_handed = t[0] * n[1] - t[1] * n[0] < 0   # (along, out, up) mirrors a right-handed frame
    for face in _FACES:
        idx = [k + p * 4 + d * 2 + z for p, d, z in face]
        faces.append(tuple(reversed(idx)) if left_handed else tuple(idx))


def _along(p, n):
    """Distance along a wall from the model's origin, as the shader measures it: p on the wall's horizontal
    tangent (-ny, nx). It grows from a to b when n is the right-hand normal of a->b."""
    return p[1] * n[0] - p[0] * n[1]


def boxes(entry, base_z):
    """(verts, faces) for one building's detail."""
    verts, faces = [], []
    zones = entry["zones"]
    floor = max(float(entry.get("floor_h") or 3.5), MIN_FLOOR_M)
    shop_top = zones[1]["h0"] if zones[0]["kind"] == "storefront" and len(zones) > 1 else None
    # the zone boundaries a heavy band marks; the storefront's top has a band of its own
    boundaries = [z["h0"] for z in zones[1 if shop_top is None else 2:]]
    glass = [(z["h0"], math.inf if z["h1"] is None else z["h1"]) for z in zones if z["kind"] == "glass"]
    for w in entry.get("detail_walls", []):
        a, b, n = w["a"], w["b"], w["n"]
        lo, hi = float(w["z0"]), float(w["z1"])
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length < 0.5 or hi - lo < 0.5:
            continue
        k = 1
        while k * floor < hi - TOP_CLEARANCE_M:   # the floor lines, never re-based on the wall's own z0
            h = k * floor
            k += 1
            if h < lo or (shop_top is not None and h <= shop_top):
                continue
            # the band nearest a zone boundary is heavy, so it can sit up to half a floor from the colour change
            half, depth = ZONE_BAND if any(abs(h - t) < floor / 2 for t in boundaries) else FLOOR_BAND
            _box(verts, faces, a, b, n, base_z + h - half, base_z + h + half, depth)
        if shop_top is not None and lo <= shop_top <= hi:
            half, depth = STOREFRONT_BAND
            _box(verts, faces, a, b, n, base_z + shop_top - half, base_z + shop_top + half, depth)
        tx, ty = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        a0, b0 = _along(a, n), _along(b, n)
        fins = []   # metres from a to each painted mullion whose fin fits on the wall; the corners get none
        if abs(b0 - a0) > 1e-9:
            for k in range(math.floor(min(a0, b0) / GLASS_BAY_M), math.ceil(max(a0, b0) / GLASS_BAY_M) + 1):
                s = (k * GLASS_BAY_M - a0) / (b0 - a0) * length
                if FIN[0] <= s <= length - FIN[0]:
                    fins.append(s)
        for g0, g1 in glass:
            f0, f1 = max(lo, g0), min(hi, g1)
            if f1 - f0 < 1.0:
                continue
            for s in fins:
                px, py = a[0] + tx * s, a[1] + ty * s
                _box(verts, faces, (px - tx * FIN[0], py - ty * FIN[0]), (px + tx * FIN[0], py + ty * FIN[0]), n,
                     base_z + f0, base_z + f1, FIN[1])
    return verts, faces
