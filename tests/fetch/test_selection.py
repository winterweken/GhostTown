import numpy as np

from ghosttown_fetch import raycast, selection
from camera_samples import camera


def box(bid, x0, y0, x1, y1, z1=30.0):
    return {"id": bid, "solids": [{"rings": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]], "z0": 0.0, "z1": z1}]}


BOX = box("a", -10, -10, 10, 10)


def _views(cams, scene):
    s = selection.wall_samples(scene)
    return s, selection.views(cams, s, scene)


def test_samples_cover_every_exposed_wall():
    s = selection.wall_samples(raycast.Scene([BOX]))
    assert np.isclose(s.area.sum(), 80 * 30)
    assert set(np.round(s.height, 3)) == set(np.round(np.arange(8) * 3.75 + 1.875, 3))


def test_a_shared_wall_is_not_exposed():
    s = selection.wall_samples(raycast.Scene([box("a", 0, 0, 10, 10), box("b", 10, 0, 20, 10)]))
    assert not np.any(np.isclose(s.P[:, 0], 10.0))


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


def test_thin_keeps_the_newest_photo_per_place_and_heading():
    old = camera((1, 1, 2), heading_deg=90, year=2016, image_id="old")
    new = camera((3, 4, 2), heading_deg=100, year=2024, image_id="new")      # same 5 m cell and 30° of heading
    back = camera((2, 2, 2), heading_deg=270, year=2016, image_id="back")    # same cell, looking the other way
    far = camera((12, 1, 2), heading_deg=90, year=2016, image_id="far")      # two cells along
    pano = camera((1, 2, 2), kind="spherical", year=2019, image_id="pano")
    pano2 = camera((4, 3, 2), heading_deg=180, kind="spherical", year=2015, image_id="pano2")   # heading is moot
    kept = [c.id for c in selection.thin([old, new, back, far, pano, pano2])]
    assert sorted(kept) == ["back", "far", "new", "pano"]


def test_recency_weights():
    assert [selection.recency(y) for y in (2025, 2022, 2019, 2015)] == [1.0, 1.0, 0.8, 0.6]


def test_choose_spends_the_budget_then_shares_what_was_chosen():
    scene = raycast.Scene([BOX, box("b", 40, -10, 60, 10)])
    spots = [(0, 0), (5, 0), (-5, 0), (50, 0), (30, 15), (20, 10)]
    cams = [camera((x, -70, 2), heading_deg=h, image_id=f"c{i}") for i, (x, h) in enumerate(spots)]
    s, seen = _views(cams, scene)
    picks = selection.choose(cams, seen, s, budget=3, order=[0, 1])
    chosen = {c for v in picks.values() for c in v}
    assert len(chosen) <= 3 and len(picks[0]) <= selection.PER_BUILDING
    assert set(picks.get(1, [])) <= set(picks[0])


def test_choose_prefers_recent_photos():
    cams = [camera((0, -60, 2), year=2015, image_id="old"), camera((0, -60.5, 2), year=2025, image_id="new")]
    s, seen = _views(cams, raycast.Scene([BOX]))
    assert selection.choose(cams, seen, s, budget=10, order=[0])[0][0] == 1


def test_priority_puts_detail_buildings_first():
    scene = raycast.Scene([box("near", 0, 0, 10, 10), box("far", 200, 0, 210, 10)])
    assert selection.priority(scene, set()) == [0, 1]
    assert selection.priority(scene, {"far"}) == [1, 0]
