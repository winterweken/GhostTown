import numpy as np
import pytest

from ghosttown_fetch.frame import Frame

BAY = (43.649667039, -79.380991173)


def test_equator_scale_matches_wgs84_reference():
    f = Frame(0.0, 0.0)
    assert f.kx == pytest.approx(111319.49, abs=0.01)  # 1 degree of longitude at the equator
    assert f.ky == pytest.approx(110574.27, abs=0.05)  # 1 degree of latitude at the equator


def test_centre_is_the_origin():
    f = Frame(*BAY)
    assert f.to_local(BAY[1], BAY[0]) == (0.0, 0.0)


def test_axes_point_east_and_north():
    f = Frame(*BAY)
    x, y = f.to_local(BAY[1] + 0.001, BAY[0])
    assert x > 0 and y == 0
    x, y = f.to_local(BAY[1], BAY[0] + 0.001)
    assert x == 0 and y > 0


@pytest.mark.parametrize("x, y", [(1000, 0), (0, -1000), (707.1, 707.1), (-950.5, 312.25)])
def test_round_trip_within_a_micrometre(x, y):
    f = Frame(*BAY)
    x2, y2 = f.to_local(*f.to_lonlat(x, y))
    assert abs(x2 - x) < 1e-6 and abs(y2 - y) < 1e-6


def test_accepts_numpy_arrays():
    f = Frame(*BAY)
    xs, ys = f.to_local(np.array([BAY[1], BAY[1] + 0.01]), np.array([BAY[0], BAY[0]]))
    assert xs.shape == (2,) and xs[0] == 0 and xs[1] == pytest.approx(806.77, abs=0.01)
