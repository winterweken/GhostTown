from ghosttown import geometry
from helpers import closed_and_outward, min_edge, signed_volume

SQUARE = [(0, 0), (10, 0), (10, 10), (0, 10)]


def _area(ring):
    return 0.5 * sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))


def test_prism_of_a_square_is_closed_and_outward():
    verts, faces = geometry.prism([SQUARE], 0.0, 5.0)
    assert len(verts) == 8 and len(faces) == 2 + 2 + 4
    assert closed_and_outward(verts, faces)
    assert abs(signed_volume(verts, faces) - 500.0) < 1e-6


def test_prism_with_a_courtyard():
    outer = [(0, 0), (30, 0), (30, 30), (0, 30)]
    hole = [(10, 10), (10, 20), (20, 20), (20, 10)]  # clockwise
    verts, faces = geometry.prism([outer, hole], -0.3, 12.0)
    assert closed_and_outward(verts, faces)
    assert abs(signed_volume(verts, faces) - 800.0 * 12.3) < 1e-6


def test_prism_of_a_concave_l_shape():
    ring = [(0, 0), (20, 0), (20, 5), (5, 5), (5, 20), (0, 20)]
    verts, faces = geometry.prism([ring], 0.0, 3.0)
    assert closed_and_outward(verts, faces)
    assert abs(signed_volume(verts, faces) - 175.0 * 3.0) < 1e-6


def test_clean_rings_reorients_a_clockwise_outer_and_ccw_hole():
    outer = list(reversed([(0, 0), (30, 0), (30, 30), (0, 30)]))
    hole = [(10, 10), (20, 10), (20, 20), (10, 20)]  # counter-clockwise: wrong for a hole
    rings = geometry.clean_rings([outer, hole])
    assert _area(rings[0]) > 0 and _area(rings[1]) < 0
    assert closed_and_outward(*geometry.prism(rings, 0.0, 1.0))


def test_clean_rings_merges_points_closer_than_3mm():
    ring = [(0, 0), (10, 0), (10.001, 0), (10, 10), (0, 10), (0, 0.0005)]
    out, = geometry.clean_rings([ring])
    assert len(out) == 4
    assert min_edge(*geometry.prism([out], 0.0, 1.0)) >= geometry.MIN_EDGE_M


def test_clean_rings_drops_degenerate_outers_and_holes():
    assert geometry.clean_rings([[(0, 0), (1, 0), (2, 0)]]) == []
    assert geometry.clean_rings([]) == []
    rings = geometry.clean_rings([SQUARE, [(1, 1), (1.001, 1), (1, 1.001)]])
    assert len(rings) == 1


def _tri_areas(verts, faces):
    out = []
    for f in faces:
        if len(f) == 3:
            (ax, ay, _), (bx, by, _), (cx, cy, _) = (verts[i] for i in f)
            out.append(abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay)) / 2)
    return out


def test_clean_rings_drops_collinear_and_nearly_collinear_points():
    ring = [(0, 0), (5, 0), (10, 0), (10, 10), (5, 10.00007), (0, 10)]
    out, = geometry.clean_rings([ring])
    assert len(out) == 4


def test_caps_have_no_zero_area_triangles():
    verts, faces = geometry.prism(geometry.clean_rings([[(0, 0), (5, 0), (10, 0), (10, 10), (0, 10)]]), 0.0, 3.0)
    assert min(_tri_areas(verts, faces)) > 1e-4


def test_is_closed_spots_an_open_mesh():
    verts, faces = geometry.prism([SQUARE], 0.0, 1.0)
    assert geometry.is_closed(faces)
    assert not geometry.is_closed(faces[1:])
