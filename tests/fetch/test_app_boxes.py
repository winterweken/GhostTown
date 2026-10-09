"""ghosttown_fetch.app_boxes: what a build does to each development application box. The planner's rules are
ported from BHPlus tests/test_site_applications_boxes.py; Ghost Town has no pinning, no other family's types and no
Align, and an untouched box takes its site's new starting box (design §2, decision 4)."""
import math

import pytest

from ghosttown_fetch import app_boxes
from ghosttown_fetch.frame import Frame


def _site(number, *more, group="review", centre=(10.0, 0.0), w=30.0, d=20.0, h=45.0, angle=0.0,
          source="application"):
    numbers = sorted((number,) + more)
    return {"id": "app:" + numbers[0], "group": group, "numbers": numbers, "main": number,
            "centre_m": list(centre), "angle_deg": angle, "width_m": w, "depth_m": d, "height_m": h, "base_m": -0.3,
            "height_from": "not stated",
            "applications": [{"number": n, "type": "OZ", "status": "Under Review", "submitted": "2024-01-01",
                              "address": "1 Main St", "description": "", "source": source, "floor_area_m2": 0.0,
                              "url": ""} for n in numbers]}


def _box(*numbers, centre=(10.0, 0.0), touched=False, closed=False):
    return {"numbers": list(numbers), "centre_m": list(centre), "touched": touched, "closed": closed}


def _gone(*numbers, centre=(10.0, 0.0)):
    return {"numbers": list(numbers), "centre_m": list(centre)}


def _only(got, **expected):
    for key in ("place", "update", "close", "remove", "keep", "deleted", "left"):
        assert got[key] == expected.get(key, []), key


def test_a_new_site_gets_a_box():
    site = _site("A")
    got = app_boxes.plan([site], [], [], 300)
    _only(got, place=[site])
    assert got["looked"] is True


def test_a_matching_box_is_updated():
    box, site = _box("A"), _site("A", group="approved", centre=(50.0, 5.0))
    _only(app_boxes.plan([site], [box], [], 300), update=[(box, site)])


def test_a_box_matched_through_any_number_follows_a_merged_site():
    box, site = _box("A"), _site("A", "B")
    _only(app_boxes.plan([site], [box], [], 300), update=[(box, site)])


def test_an_untouched_box_whose_applications_closed_is_removed():
    box = _box("A")
    _only(app_boxes.plan([], [box], [], 300), remove=[box])


def test_a_changed_box_whose_applications_closed_turns_closed():
    box = _box("A", touched=True)
    _only(app_boxes.plan([], [box], [], 300), close=[box])


def test_a_box_already_closed_is_left_alone():
    box = _box("A", touched=True, closed=True)
    _only(app_boxes.plan([], [box], [], 300), keep=[box])


def test_a_box_outside_this_builds_circle_is_kept():
    box = _box("A", centre=(400.0, 0.0))
    _only(app_boxes.plan([], [box], [], 300), keep=[box])


def test_a_build_that_did_not_look_changes_no_box_and_forgets_nothing():
    box, gone = _box("A"), _gone("B")
    got = app_boxes.plan(None, [box], [gone], 300)
    _only(got, keep=[box], deleted=[gone])
    assert got["looked"] is False


def test_a_deleted_box_stays_deleted_until_its_applications_close():
    gone = _gone("A")
    _only(app_boxes.plan([_site("A")], [], [gone], 300), deleted=[gone])
    _only(app_boxes.plan([], [], [gone], 300))                               # closed: forgotten


def test_a_deleted_box_outside_this_builds_circle_stays_deleted():
    gone = _gone("A", centre=(400.0, 0.0))
    _only(app_boxes.plan([], [], [gone], 300), deleted=[gone])


def test_one_site_two_boxes_the_changed_one_wins_and_the_other_is_left():
    old, edited = _box("A"), _box("A", touched=True)
    site = _site("A")
    _only(app_boxes.plan([site], [old, edited], [], 300), update=[(edited, site)], left=[(old, site)])


def test_one_site_two_untouched_boxes_the_older_wins():
    old, copy = _box("A"), _box("A")
    site = _site("A")
    _only(app_boxes.plan([site], [old, copy], [], 300), update=[(old, site)], left=[(copy, site)])


def test_one_box_split_into_two_sites_follows_the_first_and_the_other_gets_a_new_box():
    box = _box("A", "B")
    first, second = _site("A"), _site("B", centre=(60.0, 0.0))
    _only(app_boxes.plan([first, second], [box], [], 300), update=[(box, first)], place=[second])


def _permit_site(group="construction", centre=(12.0, 1.0)):
    return _site("21 1 BLD", group=group, centre=centre, source="permit")


def test_an_edited_box_whose_application_closed_follows_the_permit_on_its_spot():
    box, site = _box("A", touched=True), _permit_site()
    _only(app_boxes.plan([site], [box], [], 300), update=[(box, site)])


def test_an_untouched_box_follows_it_too_rather_than_a_second_box_beside_it():
    box, site = _box("A"), _permit_site(group="built")
    _only(app_boxes.plan([site], [box], [], 300), update=[(box, site)])


def test_the_spot_is_the_permit_sites_turned_rectangle():
    box = _box("A", centre=(12.0, 12.0))                    # on the site's box only when it is turned 90°
    turned = _site("21 1 BLD", group="construction", centre=(12.0, 1.0), w=30.0, d=4.0, angle=90.0, source="permit")
    _only(app_boxes.plan([turned], [box], [], 300), update=[(box, turned)])
    flat = _site("21 1 BLD", group="construction", centre=(12.0, 1.0), w=30.0, d=4.0, angle=0.0, source="permit")
    _only(app_boxes.plan([flat], [box], [], 300), place=[flat], remove=[box])


def test_only_a_construction_or_built_site_takes_over_a_box_by_its_spot():
    box, site = _box("A"), _site("B", centre=(12.0, 1.0))
    _only(app_boxes.plan([site], [box], [], 300), place=[site], remove=[box])


def test_a_box_a_number_already_matched_is_not_taken_by_a_permit_site():
    box = _box("A")
    mine, permit = _site("A"), _permit_site()
    _only(app_boxes.plan([mine, permit], [box], [], 300), update=[(box, mine)], place=[permit])


def test_a_deleted_box_on_the_spot_keeps_the_permit_site_away():
    gone, site = _gone("A"), _permit_site()
    _only(app_boxes.plan([site], [], [gone], 300), deleted=[gone])


PLACED = {"location": [10.0, 0.0, -0.3], "rotation": [0.0, 0.0, 0.5], "scale": [1.0, 1.0, 1.0],
          "verts": [list(v) for v in app_boxes.box_verts(_site("A"))], "other": False}


def _now(**change):
    now = {"location": list(PLACED["location"]), "rotation": list(PLACED["rotation"]),
           "scale": list(PLACED["scale"]), "verts": [list(v) for v in PLACED["verts"]], "other": False}
    now.update(change)
    return now


def test_touched_ignores_float_rounding():
    assert app_boxes.touched(PLACED, _now(location=[10.0000004, 0.0, -0.3000003], rotation=[0.0, 0.0, 0.5000001]))\
        is False


@pytest.mark.parametrize("change", [
    {"location": [10.002, 0.0, -0.3]}, {"rotation": [0.0, 0.0, 0.5 + math.radians(0.1)]},
    {"scale": [1.001, 1.0, 1.0]}, {"other": True}])
def test_touched_reads_a_move_a_turn_a_scale_and_a_parent(change):
    assert app_boxes.touched(PLACED, _now(**change)) is True


def test_touched_reads_an_edit_mode_change():
    verts = [list(v) for v in PLACED["verts"]]
    verts[4][2] += 0.5                                       # a top corner pulled up
    assert app_boxes.touched(PLACED, _now(verts=verts)) is True
    assert app_boxes.touched(PLACED, _now(verts=verts[:7])) is True


def test_a_full_turn_is_no_turn_and_nothing_to_compare_counts_as_changed():
    assert app_boxes.touched(PLACED, _now(rotation=[0.0, 0.0, 0.5 + 2 * math.pi])) is False
    assert app_boxes.touched(None, _now()) is True and app_boxes.touched(PLACED, None) is True


def _volume(verts, faces):
    total = 0.0
    for f in faces:
        a = verts[f[0]]
        for i in range(1, len(f) - 1):
            b, c = verts[f[i]], verts[f[i + 1]]
            total += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
                      + a[2] * (b[0] * c[1] - b[1] * c[0]))
    return total / 6.0


def test_the_box_is_closed_outward_and_as_big_as_the_site():
    verts, faces = app_boxes.box_verts(_site("A", w=30.0, d=20.0, h=45.0)), app_boxes.BOX_FACES
    assert _volume(verts, faces) == pytest.approx(30.0 * 20.0 * 45.0)
    edges = [(f[i], f[(i + 1) % 4]) for f in faces for i in range(4)]
    assert sorted(edges) == sorted((b, a) for a, b in edges)            # every edge once each way: closed


def test_the_box_stands_on_its_base_turned_to_its_angle():
    location, rotation = app_boxes.placement(_site("A", centre=(5.0, 6.0), angle=30.0))
    assert location == [5.0, 6.0, -0.3] and rotation == pytest.approx([0.0, 0.0, math.radians(30.0)])


def test_a_new_centre_carries_a_box_to_the_same_real_place():
    old = {"lat": 43.65, "lon": -79.38}
    lon, lat = Frame(43.65, -79.38).to_lonlat(100.0, 0.0)
    dx, dy, dz = app_boxes.shift(old, 84.7, {"lat": lat, "lon": lon}, 83.2)
    assert (dx, dy) == pytest.approx((-100.0, 0.0), abs=1e-6) and dz == pytest.approx(1.5)


def test_the_same_centre_or_flat_ground_moves_nothing():
    c = {"lat": 43.65, "lon": -79.38}
    assert app_boxes.shift(c, None, c, 80.0) == pytest.approx((0.0, 0.0, 0.0))


def test_the_summary_counts_sites_by_status_and_says_what_changed():
    sites = [_permit_site(), _site("A", group="review"), _site("B", "C", group="coa", centre=(80.0, 0.0))]
    outcome = {"looked": True, "update": [(_box("A", touched=True), sites[1])], "remove": [_box("X")],
               "close": [_box("Y", touched=True)], "place": [], "keep": [], "deleted": [], "left": []}
    assert app_boxes.summary(sites, outcome, "2026-10-09") == (
        "Development applications (City of Toronto, 2026-10-09): 3 sites from 3 applications and 1 building permit: "
        "1 under construction, 1 under review, 1 C of A. 1 box kept at the size you gave it. 1 closed box removed. "
        "1 turned grey (Closed).")


def test_the_summary_of_a_quiet_site():
    assert app_boxes.summary([], app_boxes.plan([], [], [], 300), "2026-10-09") == \
        "Development applications (City of Toronto, 2026-10-09): none around the site."
