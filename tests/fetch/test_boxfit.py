"""ghosttown_fetch.boxfit: an application's starting box, the largest rectangle inside its site."""
import pytest
import shapely
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon, box

from ghosttown_fetch import boxfit


def _inside(r, g, slack=0.75):
    return boxfit.footprint(*r).within(g.buffer(slack))


def test_a_turned_rectangle_gives_itself_back():
    g = affinity.rotate(box(0, 0, 20, 10), 30, origin=(0, 0))
    cx, cy, angle, w, d = boxfit.rectangle(g)
    assert angle == pytest.approx(30.0, abs=1e-6)
    assert w == pytest.approx(20.0, abs=1.0) and d == pytest.approx(10.0, abs=1.0)
    assert (cx, cy) == pytest.approx((g.centroid.x, g.centroid.y), abs=0.6)


def test_an_l_shaped_site_gets_one_arm_not_a_box_over_the_neighbours():
    g = shapely.union_all([box(0, 0, 30, 10), box(0, 0, 10, 30)])
    r = boxfit.rectangle(g)
    assert boxfit.footprint(*r).area == pytest.approx(300.0, rel=0.07) and _inside(r, g)


def test_a_triangle_gets_a_rectangle_inside_it():
    g = Polygon([(0, 0), (40, 0), (0, 30)])
    r = boxfit.rectangle(g)
    assert _inside(r, g) and boxfit.footprint(*r).area > 250.0


def test_a_strip_under_two_metres_wide_falls_back_to_its_rotated_rectangle():
    cx, cy, angle, w, d = boxfit.rectangle(box(0, 0, 40, 1.5))
    assert (cx, cy, angle) == pytest.approx((20.0, 0.75, 0.0)) and (w, d) == pytest.approx((40.0, 1.5))


def test_two_separate_parcels_give_a_rectangle_in_the_bigger_one():
    g = MultiPolygon([box(0, 0, 10, 10), box(20, 0, 50, 12)])
    cx, cy, angle, w, d = boxfit.rectangle(g)
    assert 20.0 < cx < 50.0 and w * d == pytest.approx(360.0, rel=0.1)


def test_a_two_kilometre_site_stays_under_the_cell_budget_and_fills_itself():
    g = affinity.rotate(box(0, 0, 2000, 1000), -20)
    cx, cy, angle, w, d = boxfit.rectangle(g)
    assert angle == pytest.approx(-20.0, abs=1e-6) and w == pytest.approx(2000, rel=0.01)
    assert d == pytest.approx(1000, rel=0.01)


@pytest.mark.parametrize("deg", [0.0, 45.0, 89.0, 91.0, 135.0, 179.0, -60.0])
def test_the_angle_is_folded_into_minus_ninety_to_ninety(deg):
    angle = boxfit.main_angle(affinity.rotate(box(0, 0, 30, 10), deg, origin=(0, 0)))
    assert -90.0 < angle <= 90.0
    assert ((angle - deg) % 180.0) == pytest.approx(0.0, abs=1e-6) or \
        ((angle - deg) % 180.0) == pytest.approx(180.0, abs=1e-6)


def test_the_footprint_is_the_box_turned_about_its_centre():
    fp = boxfit.footprint(5.0, 5.0, 90.0, 10.0, 4.0)
    assert fp.bounds == pytest.approx((3.0, 0.0, 7.0, 10.0))
