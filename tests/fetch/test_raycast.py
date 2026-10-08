import math

import numpy as np

from ghosttown_fetch.raycast import Scene


def box(bid, x0, y0, x1, y1, z1=20.0, z0=0.0):
    return {"id": bid, "solids": [{"rings": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]], "z0": z0, "z1": z1}]}


def poly(bid, ring, z0=0.0, z1=20.0, extra_rings=()):
    return {"id": bid, "solids": [{"rings": [ring, *extra_rings], "z0": z0, "z1": z1}]}


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
    assert west.sum() == 1
    assert np.allclose(scene.N[west], [[-1, 0]])
    yard_west = np.isclose(scene.A[:, 0], 10) & np.isclose(scene.B[:, 0], 10)
    assert yard_west.sum() == 1
    assert np.allclose(scene.N[yard_west], [[1, 0]])
    owner, dist = scene.first_hit([[15, 15, 1]], [[-1, 0, 0]], 100.0)   # from inside the courtyard
    assert owner.tolist() == [0] and np.isclose(dist[0], 5.0)


def test_covered_means_inside_the_footprint_and_under_the_roof():
    scene = Scene([box("a", 0, 0, 10, 10, z1=20.0)])
    assert scene.covered([[5, 5, 1], [5, 5, 25], [15, 5, 1]]).tolist() == [True, False, False]
    assert scene.base_z.tolist() == [0.0]


def test_a_slanting_ray_that_passes_beside_a_building_misses():
    scene = Scene([box("a", 0, 0, 10, 10)])
    s = 1 / math.sqrt(2)
    owner, _ = scene.first_hit([[-5, -20, 1], [-5, 15, 1]], [[s, s, 0], [1, 0, 0]], 100.0)
    assert owner.tolist() == [-1, -1]


def test_a_nearer_wall_in_a_later_piece_beats_a_long_wall_that_only_touches_the_first_piece():
    long_diagonal = poly("long", [[40, 0], [200, 0], [200, 10]], z1=50.0)
    nearer = box("near", 60, 0, 65, 10)
    scene = Scene([long_diagonal, nearer])
    owner, dist = scene.first_hit([[0, 5, 1]], [[1, 0, 0]], 500.0)
    assert owner.tolist() == [1] and np.isclose(dist[0], 60.0)


def test_rays_keep_their_first_hit_across_several_pieces():
    scene = Scene([box("far", 155, 0, 165, 10), box("near", 55, 0, 65, 10)])
    owner, dist = scene.first_hit([[0, 5, 1]], [[1, 0, 0]], 500.0)
    assert owner.tolist() == [1] and np.isclose(dist[0], 55.0)


def test_a_slowly_rising_ray_still_hits_a_wall_a_hundred_metres_out():
    scene = Scene([box("a", 120, 0, 130, 10)])
    a = math.radians(2.0)
    owner, dist = scene.first_hit([[0, 5, 1]], [[math.cos(a), 0, math.sin(a)]], 500.0)
    assert owner.tolist() == [0] and np.isclose(dist[0] * math.cos(a), 120.0)


def test_rays_pass_under_a_raised_solid():
    scene = Scene([box("a", 0, 0, 10, 10, z0=5.0, z1=20.0)])
    owner, _ = scene.first_hit([[-5, 5, 1], [-5, 5, 6]], [[1, 0, 0], [1, 0, 0]], 100.0)
    assert owner.tolist() == [-1, 0]


def test_covered_follows_the_footprint_not_its_bounding_box():
    ell = poly("L", [[0, 0], [20, 0], [20, 10], [10, 10], [10, 20], [0, 20]])
    scene = Scene([ell])
    assert scene.covered([[5, 15, 1], [15, 15, 1], [15, 5, 1]]).tolist() == [True, False, True]


def test_a_courtyard_is_not_covered():
    yard = poly("y", [[0, 0], [30, 0], [30, 30], [0, 30]], extra_rings=[[[10, 10], [20, 10], [20, 20], [10, 20]]])
    scene = Scene([yard])
    assert scene.covered([[5, 5, 1], [15, 15, 1]]).tolist() == [True, False]


def test_a_self_crossing_outline_is_repaired():
    bow = poly("bow", [[0, 0], [10, 10], [10, 0], [0, 6]])
    scene = Scene([bow])
    assert all(p.is_valid for p in scene.solids) and len(scene.A) == 3


def test_base_z_is_the_lowest_z0_among_a_buildings_solids():
    b = {"id": "t", "solids": [
        {"rings": [[[0, 0], [10, 0], [10, 10], [0, 10]]], "z0": 2.0, "z1": 12.0},
        {"rings": [[[0, 0], [5, 0], [5, 5], [0, 5]]], "z0": 12.0, "z1": 30.0}]}
    assert Scene([b]).base_z.tolist() == [2.0]


def _brute_first_hit(scene, origin, dirs, max_dist):
    """The first wall each ray crosses, checked against every wall: the answer first_hit must give."""
    a, e = scene.A, scene.B - scene.A
    owner, dist = np.full(len(dirs), -1), np.full(len(dirs), np.inf)
    for i, d in enumerate(dirs):
        denom = d[0] * e[:, 1] - d[1] * e[:, 0]
        ok = np.abs(denom) > 1e-9
        safe = np.where(ok, denom, 1.0)
        ap = a - origin[:2]
        t = (ap[:, 0] * e[:, 1] - ap[:, 1] * e[:, 0]) / safe
        s = (ap[:, 0] * d[1] - ap[:, 1] * d[0]) / safe
        z = origin[2] + t * d[2]
        ok &= (t > 1e-6) & (t <= max_dist) & (s >= -1e-9) & (s <= 1 + 1e-9)
        ok &= (z >= scene.wall_z0 - 1e-6) & (z <= scene.wall_z1 + 1e-6)
        if ok.any():
            w = np.flatnonzero(ok)[np.argmin(t[ok])]
            owner[i], dist[i] = scene.wall_owner[w], t[w]
    return owner, dist


def test_many_rays_falling_and_rising_through_raised_buildings_meet_the_walls_a_brute_force_check_does():
    # More rays than one batch holds, from a camera 2 m up among buildings standing on bases from -3 to 6 m. A ray
    # that falls below every wall's foot is dropped early, so this pins that it could have hit nothing there.
    rng = np.random.default_rng(7)
    buildings = [box(f"b{i}", x, y, x + rng.uniform(5, 30), y + rng.uniform(5, 30), z0=z0, z1=z0 + rng.uniform(3, 60))
                 for i, (x, y, z0) in enumerate(zip(rng.uniform(-300, 280, 40), rng.uniform(-300, 280, 40),
                                                    rng.uniform(-3, 6, 40)))]
    scene = Scene(buildings)
    origin = np.array([0.0, 0.0, 2.0])
    dirs = rng.normal(size=(9000, 3)) * [1, 1, 0.15]
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    owner, dist = scene.first_hit(origin[None], dirs, 600.0)
    expected_owner, expected_dist = _brute_first_hit(scene, origin, dirs, 600.0)
    assert len(dirs) > 4096 and (owner >= 0).sum() > 1000 and (dirs[owner < 0, 2] < 0).sum() > 1000
    assert np.array_equal(owner, expected_owner) and np.allclose(dist, expected_dist, rtol=0, atol=1e-9)
