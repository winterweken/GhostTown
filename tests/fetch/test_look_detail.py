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
