import math
import look_detail

ENTRY = {"floor_h": 4.0, "zones": [{"h0": 0, "h1": 3, "kind": "storefront", "colour": [0, 0, 0]},
                                   {"h0": 3, "h1": 12, "kind": "opaque", "colour": [0, 0, 0]},
                                   {"h0": 12, "h1": None, "kind": "glass", "colour": [0, 0, 0]}],
         "detail_walls": [{"a": [0, 0], "b": [10, 0], "n": [0, -1], "z0": 0, "z1": 30}]}


def _volume(verts, face):
    total = 0.0
    a = verts[face[0]]
    for i in range(1, len(face) - 1):
        b, c = verts[face[i]], verts[face[i + 1]]
        total += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
                  + a[2] * (b[0] * c[1] - b[1] * c[0]))
    return total / 6.0


def _boxes(verts, faces):
    return [faces[i:i + 6] for i in range(0, len(faces), 6)]


def _band_centres(verts, faces):
    out = []
    for box in _boxes(verts, faces):
        zs = sorted({verts[i][2] for f in box for i in f})
        xs = {verts[i][0] for f in box for i in f}
        if max(xs) - min(xs) > 5:
            out.append(round((zs[0] + zs[-1]) / 2, 6))
    return sorted(out)


def _fin_spans(verts, faces):
    out = []
    for box in _boxes(verts, faces):
        zs = sorted({verts[i][2] for f in box for i in f})
        xs = {verts[i][0] for f in box for i in f}
        if max(xs) - min(xs) < 1:
            out.append((zs[0], zs[-1]))
    return out


def test_floors_storefront_band_and_fins():
    verts, faces = look_detail.boxes(ENTRY, base_z=-0.3)
    # floors at 4k above the base (4 … 28), one storefront band, fins on the mullions the shader paints every 1.5 m
    # from the model's origin: the corner mullion at 0 gets no fin, the one at 9 does
    assert len(faces) == 6 * (7 + 1 + 6) and len(verts) == 8 * 14
    assert min(v[2] for v in verts) >= -0.3 and max(v[2] for v in verts) <= 30 - 0.3


def test_every_box_is_closed_and_faces_out():
    for n in ([0, -1], [0, 1]):   # either side of the wall line
        entry = dict(ENTRY, detail_walls=[dict(ENTRY["detail_walls"][0], n=n)])
        verts, faces = look_detail.boxes(entry, base_z=0.0)
        for box in _boxes(verts, faces):
            assert sum(_volume(verts, f) for f in box) > 0


def test_a_band_near_a_zone_boundary_is_heavier():
    # the floor band nearest the opaque-to-glass boundary at 12 is heavy; the storefront's top (3) has its own band,
    # so the floor band at 4 beside it stays light
    verts, faces = look_detail.boxes(ENTRY, base_z=0.0)
    heights = {}
    for box in _boxes(verts, faces):
        zs = sorted({verts[i][2] for f in box for i in f})
        xs = {verts[i][0] for f in box for i in f}
        if max(xs) - min(xs) > 5:   # a band, not a fin
            heights[round((zs[0] + zs[-1]) / 2, 2)] = round(zs[-1] - zs[0], 6)
    assert heights[12.0] > heights[8.0] == heights[4.0]


def test_the_heavy_band_is_the_floor_band_nearest_the_boundary():
    # 3.5 m floors: the boundary at 12 has no floor line on it; the nearest, 10.5, is heavy and 14 is not
    verts, faces = look_detail.boxes(dict(ENTRY, floor_h=3.5), base_z=0.0)
    heights = {}
    for box in _boxes(verts, faces):
        zs = sorted({verts[i][2] for f in box for i in f})
        xs = {verts[i][0] for f in box for i in f}
        if max(xs) - min(xs) > 5:
            heights[round((zs[0] + zs[-1]) / 2, 2)] = round(zs[-1] - zs[0], 6)
    assert heights[10.5] > heights[14.0] == heights[7.0]


def test_no_detail_walls_means_nothing():
    assert look_detail.boxes(dict(ENTRY, detail_walls=[]), base_z=0.0) == ([], [])


def test_boxes_protrude_on_n_side():
    """Boxes must protrude on the n side, not the opposite."""
    D = max(look_detail.FLOOR_BAND[1], look_detail.ZONE_BAND[1],
            look_detail.STOREFRONT_BAND[1], look_detail.FIN[1])
    for n in ([0, -1], [0, 1]):
        entry = dict(ENTRY, detail_walls=[dict(ENTRY["detail_walls"][0], n=n)])
        verts, faces = look_detail.boxes(entry, base_z=0.0)
        for v in verts:
            dot = v[0] * n[0] + v[1] * n[1]
            assert 0 <= dot <= D, f"Vertex {v} with n={n} has dot product {dot}"


def test_base_z_shifts_everything():
    """base_z must shift every z coordinate; x and y unchanged, same faces."""
    verts0, faces0 = look_detail.boxes(ENTRY, base_z=0.0)
    verts10, faces10 = look_detail.boxes(ENTRY, base_z=10.0)
    assert faces0 == faces10, "Faces must be identical"
    assert len(verts0) == len(verts10), "Vertex count must match"
    for i, (v0, v10) in enumerate(zip(verts0, verts10)):
        assert v0[0] == v10[0], f"Vertex {i}: x mismatch {v0[0]} vs {v10[0]}"
        assert v0[1] == v10[1], f"Vertex {i}: y mismatch {v0[1]} vs {v10[1]}"
        assert abs(v10[2] - v0[2] - 10.0) < 1e-9, f"Vertex {i}: z shift wrong {v10[2]} vs {v0[2]} + 10"


def test_only_exposed_heights_get_detail():
    """Detail must respect z0 and z1 bounds exactly; the floor lines stay at 4k above the base, not above z0."""
    entry = dict(ENTRY, detail_walls=[{"a": [0, 0], "b": [10, 0], "n": [0, -1],
                                        "z0": 9.0, "z1": 30.0}])
    verts, faces = look_detail.boxes(entry, base_z=0.0)
    assert _band_centres(verts, faces) == [12.0, 16.0, 20.0, 24.0, 28.0]
    # Every fin's z extent lies within [max(z0, glass_h0), z1]
    for z0, z1 in _fin_spans(verts, faces):
        assert z0 >= max(9.0, 12.0) and z1 <= 30.0


def test_rotated_wall():
    """Wall at arbitrary angle must place fins and bands correctly. With a at the origin, the shader's distance
    along the wall is the distance from a, so every fin sits a multiple of 1.5 m from a."""
    entry = dict(ENTRY, detail_walls=[{"a": [0, 0], "b": [6, 8], "n": [0.8, -0.6],
                                        "z0": 0, "z1": 30}])
    verts, faces = look_detail.boxes(entry, base_z=0.0)

    # Wall line direction for projection: (0.6, 0.8) is unit vector along wall
    D = max(look_detail.FLOOR_BAND[1], look_detail.ZONE_BAND[1],
            look_detail.STOREFRONT_BAND[1], look_detail.FIN[1])
    fin_count = 0
    for box in _boxes(verts, faces):
        xs = {verts[i][0] for f in box for i in f}
        ys = {verts[i][1] for f in box for i in f}
        extent = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
        if extent < 3.0:  # fin-like
            fin_count += 1
            # Fin centre on the wall line
            centre_x = sum(xs) / len(xs)
            centre_y = sum(ys) / len(ys)
            # Distance from a to centre along wall direction
            rel = (centre_x - 0.0, centre_y - 0.0)
            t = rel[0] * 0.6 + rel[1] * 0.8  # unit wall direction
            # t should be a multiple of GLASS_BAY_M
            bay_multiple = t / look_detail.GLASS_BAY_M
            remainder = bay_multiple - round(bay_multiple)
            assert abs(remainder) < 1e-9, f"Fin at t={t} not multiple of GLASS_BAY_M"
            # The fin stands out of the wall on the n side, no deeper than the deepest box
            n = (0.8, -0.6)
            for f in box:
                for i in f:
                    v = verts[i]
                    dot = (v[0] - 0.0) * n[0] + (v[1] - 0.0) * n[1]
                    assert -1e-9 <= dot <= D + 1e-9
        elif max(xs) - min(xs) > 5:  # band
            # Bands must span from a to b along wall direction
            ts = [v[0] * 0.6 + v[1] * 0.8 for fc in box for i in fc for v in [verts[i]]]
            assert abs(min(ts)) < 1e-9 and abs(max(ts) - 10.0) < 1e-9
    assert fin_count == 6   # at 1.5 … 9 m from a; the corner at 0 gets none


def test_guards():
    """Missing detail_walls key, short walls, and floor_h default must be handled."""
    # No "detail_walls" key
    entry_no_walls = {k: v for k, v in ENTRY.items() if k != "detail_walls"}
    assert look_detail.boxes(entry_no_walls, base_z=0.0) == ([], [])

    # Wall shorter than 0.5 m (horizontal)
    short_wall = dict(ENTRY, detail_walls=[{"a": [0, 0], "b": [0.3, 0], "n": [0, -1], "z0": 0, "z1": 30}])
    assert look_detail.boxes(short_wall, base_z=0.0) == ([], [])

    # floor_h: None defaults to 3.5 m spacing: floors at 3.5k above the base, beside the storefront band at 3
    entry_no_floor = dict(ENTRY, floor_h=None)
    verts, faces = look_detail.boxes(entry_no_floor, base_z=0.0)
    assert _band_centres(verts, faces) == [3.0, 3.5, 7.0, 10.5, 14.0, 17.5, 21.0, 24.5, 28.0]


def test_fins_start_at_wall_z0_when_it_is_above_the_glass():
    """Fins must respect z0 lower bound even when above glass start."""
    v, f = look_detail.boxes(dict(ENTRY, detail_walls=[dict(ENTRY["detail_walls"][0], z0=15.0)]), 0.0)
    spans = _fin_spans(v, f)
    assert len(spans) == 6 and all(lo == 15.0 and hi == 30.0 for lo, hi in spans)


def test_fins_stay_inside_a_glass_zone_with_a_wall_above_it():
    # opaque 0–12 · glass 12–24 · opaque 24–: every fin spans exactly the glass, six of them on the 10 m wall
    zones = [{"h0": 0, "h1": 12, "kind": "opaque", "colour": [0, 0, 0]},
             {"h0": 12, "h1": 24, "kind": "glass", "colour": [0, 0, 0]},
             {"h0": 24, "h1": None, "kind": "opaque", "colour": [0, 0, 0]}]
    v, f = look_detail.boxes(dict(ENTRY, zones=zones), 0.0)
    assert _fin_spans(v, f) == [(12.0, 24.0)] * 6


def test_floor_bands_stop_below_the_wall_top():
    """Floor bands must not exceed wall z1: floors at 4, 8, 12 and 16 under a 20 m top, and the storefront band."""
    v, f = look_detail.boxes(dict(ENTRY, detail_walls=[dict(ENTRY["detail_walls"][0], z1=20.0)]), 0.0)
    assert _band_centres(v, f) == [3.0, 4.0, 8.0, 12.0, 16.0]


def test_no_floor_band_within_the_top_clearance():
    """No band within 0.2 m of the wall top: the floor line at 28 gets a band under a 28.3 m top, not under 28.1."""
    v, f = look_detail.boxes(dict(ENTRY, detail_walls=[dict(ENTRY["detail_walls"][0], z1=28.1)]), 0.0)
    assert 28.0 not in _band_centres(v, f) and 24.0 in _band_centres(v, f)
    v, f = look_detail.boxes(dict(ENTRY, detail_walls=[dict(ENTRY["detail_walls"][0], z1=28.3)]), 0.0)
    assert 28.0 in _band_centres(v, f)


def test_rotated_wall_bands_span_a_to_b():
    """Rotated wall bands must span endpoint to endpoint: seven floors and the storefront band."""
    wall = {"a": [0, 0], "b": [6, 8], "n": [0.8, -0.6], "z0": 0, "z1": 30}
    v, f = look_detail.boxes(dict(ENTRY, detail_walls=[wall]), 0.0)
    seen = 0
    for box in _boxes(v, f):
        ts = [v[i][0] * 0.6 + v[i][1] * 0.8 for fc in box for i in fc]
        if max(ts) - min(ts) > 5:
            seen += 1
            assert abs(min(ts)) < 1e-9 and abs(max(ts) - 10.0) < 1e-9
    assert seen == 8


def _centre(verts, box):
    pts = {verts[i] for face in box for i in face}
    return [sum(p[k] for p in pts) / len(pts) for k in range(3)]


def test_bands_and_fins_sit_on_the_lines_the_shader_paints():
    """On a wall away from the origin, every fin centre is on a painted mullion (the shader's distance along the
    wall, from the origin, a multiple of 1.5 m) and every floor band on a painted floor line (a whole number of
    floors above the base). Here that puts the fins at 1.0, 2.5 … 8.5 m from a, not at multiples of 1.5 from a."""
    wall = {"a": [2.2, -7.0], "b": [2.2, 3.0], "n": [1.0, 0.0], "z0": 0, "z1": 30}
    entry = dict(ENTRY, floor_h=3.7, detail_walls=[wall])
    verts, faces = look_detail.boxes(entry, base_z=5.0)
    fins = []
    for box in _boxes(verts, faces):
        x, y, z = _centre(verts, box)
        ys = {verts[i][1] for face in box for i in face}
        if max(ys) - min(ys) < 1:   # a fin
            along = y * 1.0 - x * 0.0
            assert abs(along / 1.5 - round(along / 1.5)) < 1e-9, along
            fins.append(round(y - wall["a"][1], 6))
        elif abs(z - 5.0 - 3.0) > 1e-9:   # a floor band (the storefront band sits at the storefront's top)
            h = z - 5.0
            assert abs(h / 3.7 - round(h / 3.7)) < 1e-9, h
    assert fins == [1.0, 2.5, 4.0, 5.5, 7.0, 8.5]


def test_a_tiny_floor_height_gives_the_shaders_1_m_grid_not_a_hang():
    verts, faces = look_detail.boxes(dict(ENTRY, floor_h=0.001), base_z=0.0)
    assert _band_centres(verts, faces) == [3.0] + [float(h) for h in range(4, 30)]
