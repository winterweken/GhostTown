import base64

import pytest

from ghosttown_fetch import mvt
from mvt_samples import detection, tile

SQUARE = [(0, 0), (4096, 0), (4096, 4096), (0, 4096)]


def test_a_rectangle_comes_back_as_fractions_of_the_extent():
    (layer, rings), = mvt.decode_polygons(tile([[[(0, 0), (2048, 0), (2048, 1024), (0, 1024)]]]))
    assert layer == "mpy-or"
    assert rings == [[(0.0, 0.0), (0.5, 0.0), (0.5, 0.25), (0.0, 0.25)]]


def test_holes_stay_with_their_polygon():
    hole = [(1024, 1024), (1024, 3072), (3072, 3072), (3072, 1024)]   # opposite winding
    other = [(100, 100), (200, 100), (200, 200), (100, 200)]
    polys = mvt.decode_polygons(tile([[SQUARE, hole], [other]]))
    assert [len(rings) for _, rings in polys] == [2, 1]


def test_negative_deltas_and_other_extents():
    ring = [(300, 300), (100, 300), (100, 100), (300, 100)]   # drawn leftwards and upwards
    (_, rings), = mvt.decode_polygons(tile([[ring]], extent=400))
    assert rings[0] == [(0.75, 0.75), (0.25, 0.75), (0.25, 0.25), (0.75, 0.25)]


def test_lines_and_points_are_skipped():
    assert mvt.decode_polygons(tile([[[(0, 0), (10, 0), (10, 10)]]], kind=2)) == []


def test_a_cut_short_tile_is_an_error():
    data = tile([[SQUARE]])
    with pytest.raises(mvt.TileError):
        mvt.decode_polygons(data[:-5])


def test_detection_helper_encodes_one_ring():
    det = detection("nature--sky", [(0, 0), (0, 0.5), (1, 0.5), (1, 0)])
    (_, rings), = mvt.decode_polygons(base64.b64decode(det["geometry"]))
    assert det["value"] == "nature--sky" and len(rings) == 1 and len(rings[0]) == 4
