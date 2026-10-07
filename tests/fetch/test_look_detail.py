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


def test_floors_storefront_band_and_fins():
    verts, faces = look_detail.boxes(ENTRY, base_z=-0.3)
    # floors at 3 + 4k (7, 11, 15, 19, 23, 27), one storefront band, fins every 1.5 m on 10 m of glass
    assert len(faces) == 6 * (6 + 1 + 5) and len(verts) == 8 * 12
    assert min(v[2] for v in verts) >= -0.3 and max(v[2] for v in verts) <= 30 - 0.3


def test_every_box_is_closed_and_faces_out():
    for n in ([0, -1], [0, 1]):   # either side of the wall line
        entry = dict(ENTRY, detail_walls=[dict(ENTRY["detail_walls"][0], n=n)])
        verts, faces = look_detail.boxes(entry, base_z=0.0)
        for box in _boxes(verts, faces):
            assert sum(_volume(verts, f) for f in box) > 0


def test_a_band_near_a_zone_boundary_is_heavier():
    verts, faces = look_detail.boxes(ENTRY, base_z=0.0)
    heights = {}
    for box in _boxes(verts, faces):
        zs = sorted({verts[i][2] for f in box for i in f})
        xs = {verts[i][0] for f in box for i in f}
        if max(xs) - min(xs) > 5:   # a band, not a fin
            heights[round((zs[0] + zs[-1]) / 2, 2)] = zs[-1] - zs[0]
    assert heights[11.0] > heights[7.0]


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
    """Detail must respect z0 and z1 bounds, and TOP_CLEARANCE_M."""
    entry = dict(ENTRY, detail_walls=[{"a": [0, 0], "b": [10, 0], "n": [0, -1],
                                        "z0": 9.0, "z1": 30.0}])
    verts, faces = look_detail.boxes(entry, base_z=0.0)

    # Storefront at 3.0 is below z0=9.0, so no storefront band
    for box in _boxes(verts, faces):
        zs = sorted({verts[i][2] for f in box for i in f})
        xs = {verts[i][0] for f in box for i in f}
        mid_z = (zs[0] + zs[-1]) / 2.0
        if max(xs) - min(xs) > 5:  # it's a band (floor or storefront), not a fin
            assert mid_z != 3.0, "No storefront band below z0"

    # Every band centre must be >= z0 and < z1 - TOP_CLEARANCE_M
    for box in _boxes(verts, faces):
        zs = sorted({verts[i][2] for f in box for i in f})
        xs = {verts[i][0] for f in box for i in f}
        mid_z = (zs[0] + zs[-1]) / 2.0
        if max(xs) - min(xs) > 5:  # band
            assert mid_z >= 9.0 and mid_z < 30.0 - look_detail.TOP_CLEARANCE_M

    # Every fin's z extent lies within [max(z0, glass_h0), z1]
    for box in _boxes(verts, faces):
        zs = sorted({verts[i][2] for f in box for i in f})
        xs = {verts[i][0] for f in box for i in f}
        if max(xs) - min(xs) < 5:  # it's a fin
            assert zs[0] >= max(9.0, 12.0) and zs[-1] <= 30.0


def test_rotated_wall():
    """Wall at arbitrary angle and position must place fins along the wall correctly."""
    entry = dict(ENTRY, detail_walls=[{"a": [0, 0], "b": [6, 8], "n": [0.8, -0.6],
                                        "z0": 0, "z1": 30}])
    verts, faces = look_detail.boxes(entry, base_z=0.0)

    # Wall line: a + t * (b - a) for t in [0, 1]; length 10
    wall_dir = (6.0, 8.0)
    wall_len = math.hypot(wall_dir[0], wall_dir[1])
    assert abs(wall_len - 10.0) < 1e-9
    unit_dir = (wall_dir[0] / wall_len, wall_dir[1] / wall_len)

    # Find fins (small x/y extent)
    D = max(look_detail.FLOOR_BAND[1], look_detail.ZONE_BAND[1],
            look_detail.STOREFRONT_BAND[1], look_detail.FIN[1])
    for box in _boxes(verts, faces):
        xs = {verts[i][0] for f in box for i in f}
        ys = {verts[i][1] for f in box for i in f}
        extent = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
        if extent < 3.0:  # fin-like
            # Fin centre on the wall line
            centre_x = sum(xs) / len(xs)
            centre_y = sum(ys) / len(ys)
            # Distance from a to centre along wall direction
            rel = (centre_x - 0.0, centre_y - 0.0)
            t = rel[0] * unit_dir[0] + rel[1] * unit_dir[1]
            # t should be a multiple of GLASS_BAY_M, within tolerance
            bay_multiple = t / look_detail.GLASS_BAY_M
            remainder = bay_multiple - round(bay_multiple)
            assert abs(remainder) < 1e-9, f"Fin at t={t} not multiple of GLASS_BAY_M"

            # Every vertex on n side
            n = (0.8, -0.6)
            for f in box:
                for i in f:
                    v = verts[i]
                    dot = (v[0] - 0.0) * n[0] + (v[1] - 0.0) * n[1]
                    assert -1e-9 <= dot <= D + 1e-9


def test_guards():
    """Missing detail_walls key, short walls, and floor_h default must be handled."""
    # No "detail_walls" key
    entry_no_walls = {k: v for k, v in ENTRY.items() if k != "detail_walls"}
    assert look_detail.boxes(entry_no_walls, base_z=0.0) == ([], [])

    # Wall shorter than 0.5 m (horizontal)
    short_wall = dict(ENTRY, detail_walls=[{"a": [0, 0], "b": [0.3, 0], "n": [0, -1], "z0": 0, "z1": 30}])
    assert look_detail.boxes(short_wall, base_z=0.0) == ([], [])

    # floor_h: None defaults to 3.5 m spacing
    entry_no_floor = dict(ENTRY, floor_h=None)
    verts, faces = look_detail.boxes(entry_no_floor, base_z=0.0)
    assert len(faces) > 0  # Should still generate geometry
    for box in _boxes(verts, faces):
        zs = sorted({verts[i][2] for f in box for i in f})
        xs = {verts[i][0] for f in box for i in f}
        if max(xs) - min(xs) > 5:  # band
            # Bands should be at 3.5 m intervals starting from storefront top (3.0)
            mid_z = (zs[0] + zs[-1]) / 2.0
            if mid_z < 30.0:
                # Distance from origin should be multiple of 3.5
                dist = mid_z - 3.0
                multiple = dist / 3.5
                remainder = multiple - round(multiple)
                assert abs(remainder) < 0.1, f"Band at {mid_z} not multiple of 3.5 from 3.0"
