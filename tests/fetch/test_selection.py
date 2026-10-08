import math

import numpy as np

from ghosttown_fetch import raycast, selection
from camera_samples import camera


def box(bid, x0, y0, x1, y1, z1=30.0):
    return {"id": bid, "solids": [{"rings": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]], "z0": 0.0, "z1": z1}]}


BOX = box("a", -10, -10, 10, 10)
TINY = box("t", -1, -1, 1, 1, z1=4.0)   # 2 x 2 x 4 m: one 8 m² sample per wall, the south one at (0, -1, 2)


def _views(cams, scene):
    s = selection.wall_samples(scene)
    return s, selection.views(cams, s, scene)


def _south_of_tiny(*shots):
    """Cameras due south of TINY, level with its south sample: one per (metres back from the wall, year). A photo
    sees that sample at 1228.8 / metres px/m, the camera's focal length (0.6 of 2048 px) over the distance."""
    return [camera((0, -1 - back, 2), year=year, image_id=f"c{i}") for i, (back, year) in enumerate(shots)]


def _at_incidence(deg, back=40.0):
    """A camera `back` metres from TINY's south sample, looking at it `deg` off square-on."""
    t = math.radians(deg)
    return camera((back * math.sin(t), -1 - back * math.cos(t), 2), heading_deg=-deg)


def test_samples_cover_every_exposed_wall():
    s = selection.wall_samples(raycast.Scene([BOX]))
    assert np.isclose(s.area.sum(), 80 * 30)
    assert set(np.round(s.height, 3)) == set(np.round(np.arange(8) * 3.75 + 1.875, 3))


def test_a_shared_wall_is_not_exposed():
    s = selection.wall_samples(raycast.Scene([box("a", 0, 0, 10, 10), box("b", 10, 0, 20, 10)]))
    assert not np.any(np.isclose(s.P[:, 0], 10.0))


def test_a_wall_is_exposed_unless_a_probe_0_3_m_out_lands_in_or_under_another_solid():
    def east_wall_heights(neighbour):   # the samples on a's east wall (x = 10) beside a neighbouring building
        s = selection.wall_samples(raycast.Scene([box("a", 0, 0, 10, 10), neighbour]))
        return sorted(set(np.round(s.height[(s.building == 0) & np.isclose(s.P[:, 0], 10.0)], 3)))

    assert east_wall_heights(box("b", 10.2, 0, 20.2, 10)) == []                  # 0.2 m away: the probe lands in b
    assert len(east_wall_heights(box("b", 10.4, 0, 20.4, 10))) == 8              # 0.4 m away: it lands in the gap
    roof = east_wall_heights(box("b", 10, 0, 20, 10, z1=12.0))                   # touching, but only 12 m high
    assert roof == [13.125, 16.875, 20.625, 24.375, 28.125]


def test_a_building_smaller_than_a_grid_cell_still_gets_a_point_on_each_wall():
    s = selection.wall_samples(raycast.Scene([box("kiosk", 0, 0, 1, 1, z1=1.5)]))
    assert len(s) == 4 and np.isclose(s.area.sum(), 4 * 1.5)


def test_heights_are_measured_from_the_buildings_lowest_point():
    # A podium from 10 to 20 m with a tower on it from 20 to 50 m: that building's lowest point is 10 m. Another
    # building, 100 m east, stands on a 5 m base.
    podium_and_tower = {"id": "p", "solids": [
        {"rings": [[[-10, -10], [10, -10], [10, 10], [-10, 10]]], "z0": 10.0, "z1": 20.0},
        {"rings": [[[-5, -5], [5, -5], [5, 5], [-5, 5]]], "z0": 20.0, "z1": 50.0}]}
    on_a_base = {"id": "q", "solids": [{"rings": [[[100, 0], [110, 0], [110, 10], [100, 10]]], "z0": 5.0, "z1": 35.0}]}
    s = selection.wall_samples(raycast.Scene([podium_and_tower, on_a_base]))
    assert np.allclose(s.height, s.P[:, 2] - np.where(s.building == 0, 10.0, 5.0))
    first, second = s.height[s.building == 0], s.height[s.building == 1]
    assert np.isclose(first.min(), 2.5) and np.isclose(first.max(), 38.125)   # the podium's first row, the tower's last
    assert np.isclose(second.min(), 1.875) and np.isclose(second.max(), 28.125)


def test_each_sample_names_its_wall_building_and_outward_normal():
    scene = raycast.Scene([box("a", 0, 0, 10, 10), box("b", 30, 0, 40, 10, z1=20.0)])
    s = selection.wall_samples(scene)
    assert set(s.building) == {0, 1} and np.array_equal(s.building, scene.wall_owner[s.wall])
    assert np.array_equal(s.N, scene.N[s.wall])


def test_only_keeps_exactly_the_samples_of_the_given_buildings():
    scene = raycast.Scene([box("a", 0, 0, 10, 10), box("b", 30, 0, 40, 10, z1=20.0), box("c", 60, 0, 70, 10, z1=10.0)])
    s = selection.wall_samples(scene)
    mask = (s.building == 0) | (s.building == 2)
    assert 0 < mask.sum() < len(s)
    for wanted in ([0, 2], {0, 2}):
        part = s.only(wanted)
        assert len(part) == mask.sum()
        for name in ("P", "N", "building", "wall", "area", "height"):
            assert np.array_equal(getattr(part, name), getattr(s, name)[mask]), name
    assert len(s.only([])) == 0


def test_an_empty_scene_has_no_samples_views_or_choices():
    scene = raycast.Scene([])
    s = selection.wall_samples(scene)
    assert len(s) == 0 and s.P.shape == (0, 3) and s.N.shape == (0, 2) and len(s.only([0])) == 0
    assert selection.views([camera((0, 0, 2))], s, scene) == {}
    assert selection.choose([], {}, s, budget=10, order=[]) == {}


def test_a_level_camera_square_on_sees_the_facing_wall_only():
    s, seen = _views([camera((0, -60, 2))], raycast.Scene([BOX]))
    idx, ppm = seen[0]
    assert len(idx) > 10 and np.allclose(s.N[idx], [0, -1]) and np.all(ppm > 5)


def test_pitched_distant_oblique_and_blocked_views_are_left_out():
    scene = raycast.Scene([BOX, box("wall", -30, -40, 30, -38, z1=40.0)])
    cams = [camera((0, -60, 2), pitch_deg=20), camera((0, -600, 2)), camera((-60, -60, 2), heading_deg=45),
            camera((0, -60, 2))]
    s, seen = _views(cams, scene)
    assert 0 not in seen and 1 not in seen          # pitched, too far
    for ci in (2, 3):                                # oblique to the target, blocked by the wall
        assert ci not in seen or not np.any(s.building[seen[ci][0]] == 0)


def test_a_camera_inside_a_building_sees_nothing():
    _s, seen = _views([camera((0, 0, 2))], raycast.Scene([BOX]))
    assert seen == {}


def test_a_camera_inside_a_low_building_does_not_see_over_its_walls():
    # 2 m up inside a 4 m shed, it looks over the shed's far wall at BOX's top rows; the camera outside does see BOX.
    scene = raycast.Scene([BOX, box("shed", -5, -65, 5, -55, z1=4.0)])
    _s, seen = _views([camera((0, -60, 2)), camera((0, -45, 2))], scene)
    assert sorted(seen) == [1]


def test_a_camera_facing_away_from_the_wall_sees_nothing():
    cams = [camera((0, -60, 2), heading_deg=h) for h in (180, 90, 270)]    # away, and each way along the wall
    _s, seen = _views(cams, raycast.Scene([BOX]))
    assert seen == {}


def test_rows_in_the_top_and_bottom_2_percent_of_the_picture_are_not_seen():
    # BOX's rows are 1.875 + 3.75 k m high. A camera level with the wall's middle (15 m) sees the top and bottom rows
    # 13.125 m above and below it. 21.5 m back they land 1.2% in from the picture's edge, 17 m back outside it;
    # either way the six rows between stay and those two go.
    cams = [camera((0, -10 - back, 15)) for back in (21.5, 17.0)]
    s, seen = _views(cams, raycast.Scene([BOX]))
    for ci in (0, 1):
        assert set(np.round(s.height[seen[ci][0]], 3)) == set(np.round(np.arange(1, 7) * 3.75 + 1.875, 3)), ci


def test_columns_in_the_left_and_right_2_percent_of_the_picture_are_not_seen():
    # A narrow lens (focal 0.8) 49 m back from low buildings to the right and left. Their middle columns (30 m out)
    # land 1% in from the picture's edge, their far columns (33 m) outside it; the near ones (27 m) stay.
    sides = raycast.Scene([box("right", 25, -10, 35, 0, z1=8.0), box("left", -35, -10, -25, 0, z1=8.0)])
    s, seen = _views([camera((0, -59, 2), focal=0.8)], sides)
    assert sorted(set(np.round(s.P[seen[0][0], 0], 1))) == [-26.7, 26.7]


def test_a_360_photo_sees_the_wall_straight_behind_it():
    # A 360° camera 50 m south of BOX, facing away from it: the wall sits on the picture's seam, where a 2% frame
    # margin would cut out every column within 7.2° of straight behind (the three middle ones, 0 and ±2.9 m).
    cam = camera((0, -60, 2), heading_deg=180, kind="spherical", width=2048, height=1024)
    s, seen = _views([cam], raycast.Scene([BOX]))
    south = seen[0][0][np.isclose(s.P[seen[0][0], 1], -10.0)]
    assert sorted(set(np.round(s.P[south, 0], 1))) == [-8.6, -5.7, -2.9, 0.0, 2.9, 5.7, 8.6]


def test_cameras_see_walls_from_3_to_500_m_away_in_plan():
    cams = [camera((0, -10 - back, 2)) for back in (2.9, 3.0, 500.0, 500.1)]    # metres from BOX's south wall
    _s, seen = _views(cams, raycast.Scene([BOX]))
    assert sorted(seen) == [1, 2]


def test_walls_are_seen_within_35_degrees_of_square_on_and_blur_with_the_angle():
    cams = [_at_incidence(d) for d in (30, 34, 36, 40)]
    _s, seen = _views(cams, raycast.Scene([TINY]))
    assert sorted(seen) == [0, 1]
    assert np.isclose(seen[0][1][0], 0.6 * 2048 / 40 * math.cos(math.radians(30)))   # focal px / distance x cos(angle)


def test_cameras_pitched_over_12_degrees_are_left_out_but_360_photos_are_not():
    cams = [camera((0, -60, 2), pitch_deg=p) for p in (11.9, -11.9, 12.1, -12.1)]
    cams += [camera((0, -60, 2), pitch_deg=14, kind="fisheye"), camera((0, -60, 2), pitch_deg=30, kind="spherical")]
    _s, seen = _views(cams, raycast.Scene([BOX]))
    assert sorted(seen) == [0, 1, 5]


def test_a_wing_of_the_same_building_can_hide_one_of_its_walls():
    # An L whose inner wall (y = 10, facing north, x 10 to 30) lies behind its west wing (x 0 to 10, up to y = 30) as
    # seen from the north-west. The first wall hit is the wing's, the point's own building, but about 20 m short of
    # the point. From the north-east the whole inner wall is in view.
    ell = {"id": "L", "solids": [{"rings": [[[0, 0], [30, 0], [30, 10], [10, 10], [10, 30], [0, 30]]],
                                  "z0": 0.0, "z1": 8.0}]}
    cams = [camera((-8, 70, 2), heading_deg=155), camera((25, 70, 2), heading_deg=180)]   # north-west, north-east
    s, seen = _views(cams, raycast.Scene([ell]))
    columns = []
    for ci in (0, 1):
        idx = seen[ci][0]
        columns.append(sorted(set(np.round(s.P[idx[np.isclose(s.P[idx, 1], 10.0)], 0], 1))))
    assert columns[0] == [20.0, 22.9, 25.7, 28.6]
    assert columns[1] == [11.4, 14.3, 17.1, 20.0, 22.9, 25.7, 28.6]


def test_a_wall_in_front_hides_a_wall_unless_it_is_the_buildings_own_and_within_1_m():
    # A 4 m high, 0.4 m thick shed stands in front of BOX's south wall, clear of the wall's 0.3 m probe, so the wall
    # stays exposed. Its face blocks the sight line to the lowest row from a camera level with it. Another building's
    # wall hides the row however close. The wall's own building's hides it only when over 1 m from the point: at 0.9 m
    # (a canopy, a bay) the point still counts as seen.
    for owner, depth, lowest_seen in (("other", 0.9, 5.625), ("same", 0.9, 1.875), ("same", 1.3, 5.625)):
        front, back = -10 - depth, -10 - depth + 0.4
        shed = {"rings": [[[-10, front], [10, front], [10, back], [-10, back]]], "z0": 0.0, "z1": 4.0}
        if owner == "other":
            buildings = [BOX, {"id": "shed", "solids": [shed]}]
        else:
            buildings = [{"id": "a", "solids": [BOX["solids"][0], shed]}]
        s, seen = _views([camera((0, -60, 2))], raycast.Scene(buildings))
        idx = seen[0][0]
        south = idx[(s.building[idx] == 0) & np.isclose(s.P[idx, 1], -10.0)]
        assert round(float(s.height[south].min()), 3) == lowest_seen, (owner, depth)


def test_thin_keeps_the_newest_photo_per_place_and_heading():
    old = camera((1, 1, 2), heading_deg=90, year=2016, image_id="old")
    new = camera((3, 4, 2), heading_deg=100, year=2024, image_id="new")      # same 5 m cell and 30° of heading
    back = camera((2, 2, 2), heading_deg=270, year=2016, image_id="back")    # same cell, looking the other way
    far = camera((12, 1, 2), heading_deg=90, year=2016, image_id="far")      # two cells along
    pano = camera((1, 2, 2), kind="spherical", year=2019, image_id="pano")
    pano2 = camera((4, 3, 2), heading_deg=180, kind="spherical", year=2015, image_id="pano2")   # heading is moot
    kept = [c.id for c in selection.thin([old, new, back, far, pano, pano2])]
    assert sorted(kept) == ["back", "far", "new", "pano"]


def test_thin_keeps_photos_in_other_cells_and_other_30_degree_bins_of_heading():
    # One 5 m cell holds headings 10°, 40° and 70°: three 30° bins, the first and last 60° apart. 12 m north is
    # another cell. Of two photos of one year in a cell and bin, the larger id stays; the kept keep their order.
    cams = [camera((1, 1, 2), heading_deg=10, year=2016, image_id="h10"),
            camera((2, 2, 2), heading_deg=40, year=2016, image_id="h40"),
            camera((3, 3, 2), heading_deg=70, year=2016, image_id="h70"),
            camera((1, 12, 2), heading_deg=10, year=2016, image_id="north"),
            camera((4, 1, 2), heading_deg=10, year=2016, image_id="h10-b")]
    assert [c.id for c in selection.thin(cams)] == ["h40", "h70", "north", "h10-b"]


def test_recency_weights():
    years = (2025, 2022, 2021, 2019, 2018, 2017, 2015)
    assert [selection.recency(y) for y in years] == [1.0, 1.0, 0.8, 0.8, 0.8, 0.6, 0.6]


def test_every_building_keeps_its_first_photo_whatever_the_budget():
    # Three buildings 200 m apart, one photo of each: spec 6.4 never drops a building's only usable photo for budget.
    scene = raycast.Scene([box(name, x - 10, -10, x + 10, 10) for name, x in (("a", 0), ("b", 200), ("c", 400))])
    cams = [camera((x, -60, 2), image_id=f"c{x}") for x in (0, 200, 400)]
    s, seen = _views(cams, scene)
    assert selection.choose(cams, seen, s, budget=1, order=[0, 1, 2]) == {0: [0], 1: [1], 2: [2]}


def test_choose_spends_the_budget_then_shares_what_was_chosen():
    # A is BOX, B is 20 m wide, 40 m east. a1 is the sharpest photo of A and sees only A; sh sees both, less sharply;
    # a2 is a blurrier photo of A (it sees part of B too); b1 is the sharpest photo of B and sees only B.
    scene = raycast.Scene([BOX, box("b", 40, -10, 60, 10)])
    spots = [(-12, -60), (25, -75), (-12, -110), (52, -60)]
    cams = [camera((x, y, 2), image_id=name) for name, (x, y) in zip(("a1", "sh", "a2", "b1"), spots)]
    s, seen = _views(cams, scene)
    a1, sh, a2, b1 = range(4)
    # Every building's first photo, a1 and b1, comes before the budget. The budget then buys photos for A first: with
    # 3, sh (sharper than a2) takes the third, and B reuses it for free but can't add a2; with plenty, A also takes a2,
    # and B shares that too.
    expected = {1: {0: [a1], 1: [b1]}, 2: {0: [a1], 1: [b1]}, 3: {0: [a1, sh], 1: [b1, sh]},
                100: {0: [a1, sh, a2], 1: [b1, sh, a2]}}
    for budget, picks in expected.items():
        assert selection.choose(cams, seen, s, budget=budget, order=[0, 1]) == picks, budget
    for budget in (4, 5, 6, 8):
        picks = selection.choose(cams, seen, s, budget=budget, order=[0, 1])
        assert set(picks) == {0, 1} and len({c for v in picks.values() for c in v}) <= budget
        assert all(len(v) <= selection.PER_BUILDING for v in picks.values())


def test_choose_serves_the_buildings_in_order_and_only_those():
    # Two buildings 200 m apart, two photos of each (60 and 90 m back). Three photos in all: the two first ones, and
    # the third is the second photo of whichever building comes first.
    scene = raycast.Scene([box("a", -10, -10, 10, 10), box("b", 190, -10, 210, 10)])
    cams = [camera((x, -back, 2), image_id=f"{name}{back}") for name, x in (("a", 0), ("b", 200)) for back in (60, 90)]
    s, seen = _views(cams, scene)
    a60, a90, b60, b90 = range(4)
    assert selection.choose(cams, seen, s, budget=3, order=[0, 1]) == {0: [a60, a90], 1: [b60]}
    assert selection.choose(cams, seen, s, budget=3, order=[1, 0]) == {0: [a60], 1: [b60, b90]}
    assert selection.choose(cams, seen, s, budget=3, order=[1]) == {1: [b60, b90]}


def test_choose_prefers_a_photo_it_already_has_but_not_a_much_blurrier_one():
    # A's only photo, "shared", also sees B, less sharply than B's own photo. Already chosen, it scores 1.5x as much
    # for B: enough to win B's first pick at 481 m² of sharp wall (722 against 600), not at 342 (513).
    scene = raycast.Scene([BOX, box("b", 40, -10, 60, 10)])
    for back, picks_for_b in ((-75, [0, 1]), (-110, [1, 0])):
        cams = [camera((25, back, 2), image_id="shared"), camera((52, -60, 2), image_id="own")]
        s, seen = _views(cams, scene)
        assert selection.choose(cams, seen, s, budget=10, order=[0, 1]) == {0: [0], 1: picks_for_b}, back


def test_choose_prefers_recent_photos():
    cams = [camera((0, -60, 2), year=2015, image_id="old"), camera((0, -60.5, 2), year=2025, image_id="new")]
    s, seen = _views(cams, raycast.Scene([BOX]))
    assert selection.choose(cams, seen, s, budget=10, order=[0])[0][0] == 1


def test_choose_prefers_the_sharper_photo():
    cams = _south_of_tiny((150, 2024), (80, 2024))          # 8.2 and 15.4 px/m
    s, seen = _views(cams, raycast.Scene([TINY]))
    assert selection.choose(cams, seen, s, budget=10, order=[0]) == {0: [1, 0]}


def test_sharpness_counts_up_to_20_px_per_metre_and_no_further():
    # 13.7 px/m in 2024 scores 0.68, 123 px/m in 2019 scores 1.0 x 0.8, 20.5 px/m in 2024 scores 1.0.
    cams = _south_of_tiny((90, 2024), (10, 2019), (60, 2024))
    s, seen = _views(cams, raycast.Scene([TINY]))
    assert selection.choose(cams, seen, s, budget=10, order=[0]) == {0: [2, 1, 0]}


def test_photos_are_usable_from_5_px_per_metre_and_blurrier_ones_are_never_chosen():
    # A lens of focal length 0.625 (1280 px at 2048 px wide), 257 and 256 m back: 4.98 and exactly 5 px/m.
    cams = [camera((0, -1 - back, 2), focal=0.625) for back in (257.0, 256.0)]
    s, seen = _views(cams, raycast.Scene([TINY]))
    assert sorted(seen) == [0, 1]                            # both see the wall; only the second is sharp enough
    assert selection.choose(cams, seen, s, budget=10, order=[0]) == {0: [1]}
    assert selection.choose(cams[:1], {0: seen[0]}, s, budget=10, order=[0]) == {}


def test_a_building_gets_at_most_its_four_best_photos():
    cams = _south_of_tiny((90, 2024), (60, 2024), (110, 2024), (70, 2024), (100, 2024), (80, 2024))
    s, seen = _views(cams, raycast.Scene([TINY]))
    assert selection.choose(cams, seen, s, budget=100, order=[0]) == {0: [1, 3, 5, 0]}   # 60, 70, 80 and 90 m back


def test_choose_counts_wall_area_not_points():
    # One building of two blocks 100 m apart, a photo of each at the same sharpness. The 4.6 m x 3 m wall of the
    # east block holds two 6.9 m² points, the 4.4 m x 4 m wall of the west block one of 17.6 m²: the larger area wins.
    two = {"id": "two", "solids": [
        {"rings": [[[100, 0], [104.6, 0], [104.6, 2], [100, 2]]], "z0": 0.0, "z1": 3.0},
        {"rings": [[[0, 0], [4.4, 0], [4.4, 2], [0, 2]]], "z0": 0.0, "z1": 4.0}]}
    cams = [camera((102.3, -50, 2), image_id="two points"), camera((2.2, -50, 2), image_id="one point")]
    s, seen = _views(cams, raycast.Scene([two]))
    assert selection.choose(cams, seen, s, budget=10, order=[0]) == {0: [1, 0]}


def test_a_point_already_covered_counts_half_each_time():
    # An 18 x 6 x 4 m building: six 12 m² points on its south wall, two on its east wall. Three photos from the south
    # see the six (about 63, 61 and 60 m² of sharp wall), one from the east sees the two (24). Once the first is in,
    # the second south photo is worth about 31 and beats the east photo's 24; the third's 15 then loses to it.
    scene = raycast.Scene([box("a", -9, -3, 9, 3, z1=4.0)])
    cams = [camera((0, -3 - back, 2), image_id=f"s{back}") for back in (70, 72, 74)]
    cams.append(camera((59, 0, 2), heading_deg=270, image_id="east"))
    s, seen = _views(cams, scene)
    assert selection.choose(cams, seen, s, budget=10, order=[0]) == {0: [0, 1, 3, 2]}


def test_priority_puts_detail_buildings_first():
    scene = raycast.Scene([box("near", 0, 0, 10, 10), box("far", 200, 0, 210, 10)])
    assert selection.priority(scene, set()) == [0, 1]
    assert selection.priority(scene, {"far"}) == [1, 0]


def test_priority_orders_buildings_by_distance_from_the_site_centre():
    # "split" has two blocks, 25 m west and 325 m east of the centre: it sits 150 m out, between "mid" and "far".
    split = {"id": "split", "solids": [box("s", -30, 0, -20, 10)["solids"][0], box("s", 320, 0, 330, 10)["solids"][0]]}
    scene = raycast.Scene([box("far", 200, 0, 210, 10), box("near", 0, 0, 10, 10), box("mid", 100, 0, 110, 10), split])
    assert selection.priority(scene, set()) == [1, 2, 3, 0]
    assert selection.priority(scene, {"split"}) == [3, 1, 2, 0]
