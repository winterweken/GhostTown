import math

import numpy as np
import pytest
import shapely

from shapely.geometry import box

from ghosttown_fetch import context as ctx
from ghosttown_fetch import contours
from ghosttown_fetch import request as rq
from ghosttown_fetch.terrain import FlatTerrain
from terrains import Ramp

R = 100.0


class Cone:
    """A hill 20 m high at the centre, falling 1 m every 5 m: its contours are circles."""
    source = "test"
    ground_at_centre_m = 100.0
    cell_m = 1.0

    def z(self, xs, ys):
        return 20.0 - 0.2 * np.hypot(np.asarray(xs, dtype=float), np.asarray(ys, dtype=float))


def _by_id(els):
    return {el["id"]: el for el in els}


def test_a_ramp_gives_straight_lines_every_half_metre_at_round_heights_above_sea_level():
    els = contours.elements(Ramp(), R)
    assert [el["kind"] for el in els] == ["contour"] * 39
    assert els[0]["id"] == "contour:70.5" and els[-1]["id"] == "contour:89.5"   # 80 m at the centre, z = x / 10
    for el in els:
        height = float(el["id"].split(":")[1])
        line, = el["lines"]
        pts = np.array(line["pts"])
        assert line["kind"] == "contour" and len(pts) == 2                     # a straight chord simplifies to its ends
        assert np.allclose(pts[:, 0], 10 * (height - 80.0), atol=1e-6)         # x where z reaches the level
        assert np.allclose(pts[:, 2], height - 80.0)                           # z is the level, in local metres
        half = math.sqrt(R * R - pts[0, 0] ** 2)
        assert abs(abs(pts[:, 1]).min() - half) < 0.5 and pts[0, 1] * pts[1, 1] < 0  # cut at the circle


def test_a_hill_gives_closed_rings_of_the_right_size():
    el = _by_id(contours.elements(Cone(), R))["contour:110"]
    line, = el["lines"]
    pts = np.array(line["pts"])
    assert np.allclose(pts[0], pts[-1]) and len(pts) > 20
    assert np.allclose(pts[:, 2], 10.0)
    radii = np.hypot(pts[:, 0], pts[:, 1])
    assert abs(radii.mean() - 50.0) < 0.3 and radii.std() < 0.3
    length = np.linalg.norm(np.diff(pts[:, :2], axis=0), axis=1).sum()
    assert abs(length - 2 * math.pi * 50.0) < 0.01 * 2 * math.pi * 50.0


def test_rings_beyond_the_circle_are_cut_or_left_out():
    els = _by_id(contours.elements(Cone(), R))
    assert "contour:99.5" not in els                      # a 102.5 m ring lies outside the 100 m site
    cut = els["contour:100.5"]                            # a 97.5 m ring is inside, whole
    assert len(cut["lines"]) == 1 and np.allclose(cut["lines"][0]["pts"][0], cut["lines"][0]["pts"][-1])
    for el in els.values():
        for line in el["lines"]:
            assert (np.hypot(*np.array(line["pts"])[:, :2].T) <= R + 0.01).all()


def _ends(lines):
    """Each line's two ends, rounded, as a sorted list of sorted pairs."""
    return sorted(tuple(sorted((round(x, 3), round(y, 3)) for x, y in ((c[0][0], c[0][1]), (c[-1][0], c[-1][1]))))
                  for c in (line.coords for line in lines))


def test_a_saddle_joins_the_corners_the_centre_sides_with():
    xs = ys = np.array([0.0, 10.0])
    clip = box(-1, -1, 11, 11)
    high_centre = contours.level_lines(xs, ys, np.array([[1.0, -1.0], [-1.0, 1.0]]), 0.0, clip)   # centre 0: above
    assert _ends(high_centre) == [((0.0, 5.0), (5.0, 10.0)), ((5.0, 0.0), (10.0, 5.0))]   # cuts off the low corners
    low_centre = contours.level_lines(xs, ys, np.array([[1.0, -2.0], [-2.0, 1.0]]), 0.0, clip)    # centre -0.5: below
    assert _ends(low_centre) == [((0.0, 3.333), (3.333, 0.0)), ((6.667, 10.0), (10.0, 6.667))]   # the high ones
    mirrored = contours.level_lines(xs, ys, np.array([[-1.0, 1.0], [1.0, -1.0]]), 0.0, clip)      # the other saddle
    assert _ends(mirrored) == [((0.0, 5.0), (5.0, 0.0)), ((5.0, 10.0), (10.0, 5.0))]


def test_a_crest_exactly_on_a_level_keeps_its_line_whole():
    class Ridge:
        source = "test"
        ground_at_centre_m = 100.0
        cell_m = 1.0

        def z(self, xs, ys):
            return -np.abs(np.asarray(xs, dtype=float))

    el = _by_id(contours.elements(Ridge(), 30.0))["contour:100"]
    for line in el["lines"]:
        pts = np.array(line["pts"])
        assert np.allclose(pts[:, 0], 0.0, atol=1e-6) and abs(abs(pts[:, 1]).max() - 30.0) < 1.0  # a whole chord


def test_the_floor_drops_speck_rings_but_keeps_short_open_pieces():
    xs = ys = np.arange(-5.0, 5.5, 0.5)
    gx, gy = np.meshgrid(xs, ys)
    speck = contours.level_lines(xs, ys, 1.5 - np.hypot(gx, gy), 0.5, box(-10, -10, 10, 10))      # a 6 m ring
    bump = contours.level_lines(xs, ys, 3.0 - np.hypot(gx, gy), 0.5, box(-10, -10, 10, 10))       # a 16 m ring
    assert speck == [] and len(bump) == 1 and bump[0].is_closed
    chord = contours.level_lines(xs, ys, gx.copy(), 2.0, box(0, 0, 4, 3))                           # 3 m, open
    assert len(chord) == 1 and not chord[0].is_closed and abs(chord[0].length - 3.0) < 1e-6


def test_flat_ground_has_no_contours():
    assert contours.elements(FlatTerrain(), R) == []


def test_contours_are_valid_context():
    req = rq.build(centre={"lat": 43.65, "lon": -79.38}, radius_m=R, cache_dir="c", out_dir="o")
    doc = ctx.new(req, region="toronto", terrain_source="test", ground_at_centre_m=80.0, cell_m=1.0)
    doc["elements"] = contours.elements(Ramp(), R)
    assert ctx.validate(ctx.finish(doc)) == [] and doc["counts"] == {"contour": 39}


def test_a_1000m_site_contours_in_seconds():
    import time

    class Hills:
        source = "test"
        ground_at_centre_m = 100.0
        cell_m = 4.0

        def z(self, xs, ys):
            xs, ys = np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)
            return 30.0 * np.sin(xs / 150.0) * np.cos(ys / 130.0)

    started = time.monotonic()
    els = contours.elements(Hills(), 1000.0)
    assert time.monotonic() - started < 20.0
    assert len(els) >= 12 and sum(len(el["lines"]) for el in els) > 50   # 60 m of relief, at worst every 5 m


def _points(els):
    return sum(len(line["pts"]) for el in els for line in el["lines"])


def test_a_big_hilly_site_stays_under_revits_10000_points_on_a_coarser_interval():
    class Hills:
        source = "test"
        ground_at_centre_m = 100.0
        cell_m = 4.0

        def z(self, xs, ys):
            xs, ys = np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)
            return 30.0 * np.sin(xs / 150.0) * np.cos(ys / 130.0)

    els = contours.elements(Hills(), 1000.0)
    assert _points(els) <= contours.MAX_POINTS
    heights = [float(el["id"].split(":")[1]) for el in els]
    interval = min(b - a for a, b in zip(heights, heights[1:]))
    assert interval in (1.0, 2.0, 5.0) and all(h % interval == 0 for h in heights)   # every level is on the interval
    assert len(els) >= 60 / 5                                                        # 60 m of relief at 5 m at worst


def _star(radius, corners=100):
    """A closed ring of 101 points whose corners step 10 m in and out, so no tolerance here can drop one."""
    angles = np.linspace(0.0, 2 * math.pi, corners, endpoint=False)
    r = radius + 10.0 * (-1.0) ** np.arange(corners)
    xy = np.column_stack([r * np.cos(angles), r * np.sin(angles)])
    return shapely.LineString(np.vstack([xy, xy[:1]]))


def test_steep_ground_goes_past_5_m_to_the_next_round_interval_that_fits():
    levels = {100.0 + 0.5 * k: [_star(500.0)] for k in range(1600)}       # 100.0 to 899.5 m, 101 points a level
    interval, _, out = contours.thinned(levels)
    assert interval == 10.0 and sorted(out) == [100.0 + 10.0 * k for k in range(80)]   # every 5 m is 16,160 points
    assert sum(shapely.get_num_coordinates(line) for lines in out.values() for line in lines) == 8080


def test_one_level_too_big_for_the_budget_is_still_drawn():
    class Bumps:
        """An egg-carton of 16 m bumps under half a metre high: thousands of small rings at one level."""
        source = "test"
        ground_at_centre_m = 100.3
        cell_m = 1.0

        def z(self, xs, ys):
            xs, ys = np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)
            return 0.4 * np.cos(2 * math.pi * xs / 16.0) * np.cos(2 * math.pi * ys / 16.0)

    els = contours.elements(Bumps(), 400.0)
    assert [el["id"] for el in els] == ["contour:100"]       # no wider interval has fewer levels than this one
    assert _points(els) > contours.MAX_POINTS and contours.count_points(els) == _points(els)


def test_a_small_site_keeps_the_half_metre_interval_and_the_fine_tolerance():
    els = _by_id(contours.elements(Cone(), R))
    assert "contour:100.5" in els and "contour:119.5" in els
    pts = np.array(els["contour:110"]["lines"][0]["pts"])
    coarse = shapely.simplify(shapely.LineString(pts[:, :2]), 2.0)
    assert len(pts) > shapely.get_num_coordinates(coarse) * 2
    assert _points(els.values()) <= contours.MAX_POINTS
