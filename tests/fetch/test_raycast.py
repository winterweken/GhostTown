import math

import numpy as np

from ghosttown_fetch.raycast import Scene


def box(bid, x0, y0, x1, y1, z1=20.0, z0=0.0):
    return {"id": bid, "solids": [{"rings": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]], "z0": z0, "z1": z1}]}


def test_a_ray_stops_at_the_first_wall():
    scene = Scene([box("a", 0, 0, 10, 10)])
    owner, dist = scene.first_hit([[-5, 5, 1]], [[1, 0, 0]], 100.0)
    assert owner.tolist() == [0] and np.isclose(dist[0], 5.0)


def test_rays_over_the_roof_or_too_short_miss():
    scene = Scene([box("a", 0, 0, 10, 10)])
    owner, _ = scene.first_hit([[-5, 5, 25], [-5, 5, 1]], [[1, 0, 0], [1, 0, 0]], [100.0, 4.0])
    assert owner.tolist() == [-1, -1]


def test_a_rising_ray_hits_where_the_wall_is_tall_enough():
    scene = Scene([box("a", 0, 0, 10, 10)])
    d = np.array([[1, 0, 1]]) / math.sqrt(2)
    owner, dist = scene.first_hit([[-5, 5, 1]], d, 100.0)
    assert owner.tolist() == [0] and np.isclose(dist[0], 5 * math.sqrt(2))


def test_the_nearer_building_wins_and_vertical_rays_never_hit():
    scene = Scene([box("far", 20, 0, 30, 10), box("near", 0, 0, 10, 10)])
    owner, _ = scene.first_hit([[-5, 5, 1], [-5, 5, 1]], [[1, 0, 0], [0, 0, 1]], 100.0)
    assert owner.tolist() == [1, -1]


def test_normals_point_out_of_the_solid_also_into_courtyards():
    yard = {"id": "y", "solids": [{"rings": [[[0, 0], [0, 30], [30, 30], [30, 0]],     # given clockwise
                                             [[10, 10], [20, 10], [20, 20], [10, 20]]], "z0": 0.0, "z1": 10.0}]}
    scene = Scene([yard])
    west = np.isclose(scene.A[:, 0], 0) & np.isclose(scene.B[:, 0], 0)
    assert np.allclose(scene.N[west], [[-1, 0]])
    yard_west = np.isclose(scene.A[:, 0], 10) & np.isclose(scene.B[:, 0], 10)
    assert np.allclose(scene.N[yard_west], [[1, 0]])
    owner, dist = scene.first_hit([[15, 15, 1]], [[-1, 0, 0]], 100.0)   # from inside the courtyard
    assert owner.tolist() == [0] and np.isclose(dist[0], 5.0)


def test_covered_means_inside_the_footprint_and_under_the_roof():
    scene = Scene([box("a", 0, 0, 10, 10, z1=20.0)])
    assert scene.covered([[5, 5, 1], [5, 5, 25], [15, 5, 1]]).tolist() == [True, False, False]
    assert scene.base_z.tolist() == [0.0]
