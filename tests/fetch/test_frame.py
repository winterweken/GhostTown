import numpy as np
import pytest

from ghosttown_fetch.frame import Frame, lonlat_to_merc, merc_to_lonlat

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


@pytest.mark.parametrize("lon, lat", [(-79.380991, 43.649667), (0.0, 0.0), (151.2093, -33.8688), (-123.1, 49.3)])
def test_web_mercator_round_trip(lon, lat):
    x, y = lonlat_to_merc(lon, lat)
    back_lon, back_lat = merc_to_lonlat(x, y)
    assert back_lon == pytest.approx(lon, abs=1e-12) and back_lat == pytest.approx(lat, abs=1e-12)


def test_web_mercator_inverse_accepts_numpy_arrays():
    lon, lat = merc_to_lonlat(np.array([0.0, -8836651.51595168]), np.array([0.0, 5411386.4482460115]))
    assert lon[0] == 0.0 and lat[0] == 0.0
    assert lon[1] == pytest.approx(-79.380991173, abs=1e-8) and lat[1] == pytest.approx(43.649667039, abs=1e-8)
