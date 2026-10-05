import math

import numpy as np
import pytest
import shapely
from shapely.affinity import rotate
from shapely.geometry import box

from ghosttown_fetch import fitted_roofs as fit
from test_lidar_roofs import FLAT20, Field, closed_outward, square

CELL = 0.5

def rect(cx, cy, length, width, deg=0.0):
    """A length x width rectangle centred on cx, cy, its long side turned `deg` from the x axis."""
    return rotate(box(cx - length / 2, cy - width / 2, cx + length / 2, cy + width / 2), deg, origin=(cx, cy))

def gable(cx, cy, deg, offset, H=9.0, s=0.5):
    """Heights above ground of a gable whose ridge runs `deg` from the x axis, `offset` m across from cx, cy."""
    th = math.radians(deg)

    def f(x, y):
        u = -(x - cx) * math.sin(th) + (y - cy) * math.cos(th)
        return H - s * np.abs(u - offset)
    return Field(f)

def hip(cx, cy, length, width, H=9.0, s=0.5):
    """A hip roof on an axis-aligned length x width house: every plane at the same pitch."""
    a = (length - width) / 2
    return Field(lambda x, y: H - s * np.maximum(np.abs(y - cy), np.abs(x - cx) - a))

def fitted(poly, field, **kw):
    x, y, z = fit.house_samples(poly, 9.0, field, CELL, city=False)
    return fit.fit_house(x, y, z, poly, **kw)

def ridge_angle_error(m, deg):
    return math.degrees(fit._apart(m["th"], math.radians(deg)))

def test_a_gable_comes_back_with_its_ridge():
    poly = rect(5, 3, 16, 10, 30)
    m = fitted(poly, gable(5, 3, 30, 1.0))
    assert m["kind"] == "gable" and ridge_angle_error(m, 30) <= 3
    _, u = fit._frame(np.array([5.0]), np.array([3.0]), m["th"])
    assert m["u0"] - u[0] == pytest.approx(1.0, abs=0.25)  # the ridge sits 1 m off the middle, on its own side
    assert m["H"] == pytest.approx(9.0, abs=0.1) and m["error"] < 0.1

@pytest.mark.parametrize("field, kind", [
    (hip(0, 0, 14, 10), "hip"),
    (Field(lambda x, y: 4.0 + 0.3 * (x + 7)), "shed"),
    (Field(lambda x, y: np.full(x.shape, 6.0)), "flat"),
])
def test_each_roof_comes_back_as_itself(field, kind):
    assert fitted(rect(0, 0, 14, 10), field)["kind"] == kind

def test_a_hip_comes_back_with_level_ends():
    m = fitted(rect(0, 0, 14, 10), hip(0, 0, 14, 10))
    assert m["kind"] == "hip" and m["a"] == pytest.approx(2.0, abs=0.01)
    assert m["H"] == pytest.approx(9.0, abs=0.01) and m["s"] == pytest.approx(0.5, abs=0.01) and m["error"] < 0.01

def test_a_tree_crown_over_part_of_a_gable_changes_nothing():
    plain = gable(0, 0, 0, 0.0)
    crowned = Field(lambda x, y: plain.sample(x, y) + np.where((x > 1.5) & (y > 2), 6.0, 0.0))  # about 10 %
    m = fitted(rect(0, 0, 16, 10), crowned)
    assert m["kind"] == "gable" and abs(m["H"] - 9.0) < 0.3 and ridge_angle_error(m, 0) <= 3

def test_too_few_samples_or_no_roof_shape_fits_nothing():
    assert fitted(rect(0, 0, 1.5, 1.5), FLAT20) is None
    rng = np.random.default_rng(7)
    noise = Field(lambda x, y: rng.uniform(2.0, 20.0, size=np.shape(x)))
    assert fitted(rect(0, 0, 14, 10), noise) is None

@pytest.mark.parametrize("tag, kind", [("flat", "flat"), ("skillion", "shed"), ("gabled", "gable"),
                                       ("hipped", "hip"), ("half-hipped", "hip"), ("dome", "gable")])
def test_a_roof_shape_tag_picks_the_roof(tag, kind):
    assert fitted(rect(0, 0, 16, 10), gable(0, 0, 0, 0.0), roof={"shape": tag})["kind"] == kind

def test_a_tag_the_survey_disagrees_with_gives_way():
    steep = gable(0, 0, 0, 0.0, H=12.0, s=1.5)  # a flat roof would miss it by more than 1.5 m
    assert fitted(rect(0, 0, 16, 10), steep, roof={"shape": "flat"})["kind"] == "gable"

def test_a_height_tag_sets_the_top_and_roof_height_the_slope():
    poly = rect(0, 0, 16, 10)
    m = fitted(poly, gable(0, 0, 0, 0.0), top=8.5)
    assert m["kind"] == "gable" and m["H"] == 8.5
    m = fitted(poly, gable(0, 0, 0, 0.0), roof={"height": 2.0}, top=9.0)
    outline = shapely.get_coordinates(poly.exterior)
    assert m["H"] == 9.0 and fit.roof_z(m, outline[:, 0], outline[:, 1]).min() == pytest.approx(7.0)

def test_roof_height_without_a_known_top_changes_nothing():
    free = fitted(rect(0, 0, 16, 10), gable(0, 0, 0, 0.0))
    tagged = fitted(rect(0, 0, 16, 10), gable(0, 0, 0, 0.0), roof={"height": 6.0})
    assert tagged == free

def test_the_house_samples_stay_inside_the_walls_and_lose_the_crowns():
    poly = rect(0, 0, 16, 10)
    x, y, z = fit.house_samples(poly, 9.0, Field(lambda x, y: np.where(x > 6, 30.0, 8.0)), CELL, city=False)
    assert np.abs(x).max() <= 7.0 and np.abs(y).max() <= 4.0 and z.max() == pytest.approx(8.0 + 3.0)

def test_city_outline_samples_drop_cranes_and_gaps():
    poly = rect(0, 0, 16, 10)
    field = Field(lambda x, y: np.where(x < -4, 40.0, np.where(x < 0, 1.0, 12.0)))
    _, _, z = fit.house_samples(poly, 12.0, field, CELL, city=True)
    assert len(z) and np.allclose(z, 12.0)


MODELS = [
    {"kind": "flat", "h": 6.0},
    {"kind": "shed", "c": [0.2, 0.1, 5.0]},
    {"kind": "gable", "th": math.radians(30), "u0": 0.7, "H": 9.0, "s": 0.5},
    {"kind": "hip", "th": 0.0, "u0": 0.0, "v0": 0.0, "a": 2.0, "H": 9.0, "s": 0.5},
    {"kind": "hip", "th": 0.0, "u0": 0.0, "v0": 0.0, "a": 0.0, "H": 9.0, "s": 0.5},  # a pyramid
]

OUTLINES = [
    square(-7, -5, 12),
    np.asarray(rect(0, 0, 14, 10, 30).exterior.coords)[:-1].tolist(),
    [[-7, -5], [7, -5], [7, 0], [0, 0], [0, 6], [-7, 6]],                         # an L
    [[-7.13, -5.02], [6.91, -4.97], [7.04, 5.11], [-6.88, 4.93]],                  # off the grid
]

@pytest.mark.parametrize("m", MODELS)
@pytest.mark.parametrize("ring", OUTLINES)
def test_house_solids_close_and_their_planes_reach_the_walls(m, ring):
    verts, faces = fit.house_solid([ring], -0.3, 0.0, m)
    assert closed_outward(verts, faces)
    roof = verts[verts[:, 2] > 0]
    want = np.maximum(fit.roof_z(m, roof[:, 0], roof[:, 1]), fit.LOWEST_ROOF_M)
    assert np.allclose(roof[:, 2], want, atol=1e-6)
    corners = np.asarray(ring, dtype=float)
    assert np.allclose(fit.roof_z(m, corners[:, 0], corners[:, 1]).clip(fit.LOWEST_ROOF_M),
                       [roof[np.argmin(np.hypot(*(roof[:, :2] - c).T))][2] for c in corners], atol=1e-6)

def test_a_house_with_a_courtyard_keeps_it_open():
    verts, faces = fit.house_solid([square(0, 0, 20), square(5, 5, 10)[::-1]], -0.3, 0.0, MODELS[2])
    assert closed_outward(verts, faces)

def test_a_roof_never_dips_under_2_m_or_its_base():
    steep = {"kind": "gable", "th": 0.0, "u0": 0.0, "H": 6.0, "s": 2.0}  # eaves would be at -4 m
    verts, faces = fit.house_solid([square(-5, -5, 10)], -0.3, 0.0, steep)
    assert closed_outward(verts, faces) and verts[verts[:, 2] > 0][:, 2].min() == pytest.approx(2.0)
