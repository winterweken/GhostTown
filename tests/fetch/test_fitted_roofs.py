import math

import numpy as np
import pytest
import shapely
from shapely.affinity import rotate
from shapely.geometry import Polygon, box

from ghosttown_fetch import context as ctx
from ghosttown_fetch import fitted_roofs as fit
from ghosttown_fetch import lidar_roofs
from test_lidar_roofs import FLAT20, Field, closed_outward, east_of, solid, square, volume

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
    top = verts[faces[(verts[faces][:, :, 2] > 0).all(axis=1)]].mean(axis=1)  # each top triangle's middle
    assert np.allclose(top[:, 2], fit.roof_z(m, top[:, 0], top[:, 1]), atol=1e-6)  # flat on its own plane

def test_a_house_with_a_courtyard_keeps_it_open():
    verts, faces = fit.house_solid([square(0, 0, 20), square(5, 5, 10)[::-1]], -0.3, 0.0, MODELS[2])
    assert closed_outward(verts, faces)
    x, y = verts[:, 0], verts[:, 1]
    assert not ((x > 5) & (x < 15) & (y > 5) & (y < 15)).any()  # nothing inside the courtyard

def test_a_roof_never_dips_under_2_m_or_its_base():
    steep = {"kind": "gable", "th": 0.0, "u0": 0.0, "H": 6.0, "s": 2.0}  # eaves would be at -4 m
    verts, faces = fit.house_solid([square(-5, -5, 10)], -0.3, 0.0, steep)
    assert closed_outward(verts, faces) and verts[verts[:, 2] > 0][:, 2].min() == pytest.approx(2.0)


def heights_at(*blocks, base=None):
    """A roof made of axis-aligned blocks (x0, y0, x1, y1, height), later blocks over earlier ones."""
    def f(x, y):
        z = np.full(np.shape(x), np.nan) if base is None else np.full(np.shape(x), float(base))
        for x0, y0, x1, y1, height in blocks:
            z = np.where((x >= x0) & (x < x1) & (y >= y0) & (y < y1), height, z)
        return z
    return Field(f)

def tier_levels(parts):
    return sorted(round(level, 1) for _, level in parts)

def test_a_tower_on_a_podium_is_two_tiers_that_fill_the_footprint():
    podium = box(0, 0, 40, 40)
    parts = fit.tiers(podium, 10.0, heights_at((0, 0, 40, 40, 10.0), (12.5, 12.5, 27.5, 27.5, 40.0)), CELL, city=False)
    assert tier_levels(parts) == [10.0, 40.0]
    assert sum(p.area for p, _ in parts) == pytest.approx(1600.0, abs=1e-6)
    tower, = [p for p, level in parts if level > 20]
    assert tower.area == pytest.approx(225.0, rel=0.1)

@pytest.mark.parametrize("extra, levels", [
    ((10, 10, 16, 15, 16.0), [12.0, 16.0]),  # a 30 m2 penthouse 4 m up is a tier
    ((10, 10, 12.5, 14, 16.0), [12.0]),      # a 10 m2 lift overrun is not
])
def test_a_penthouse_is_a_tier_and_a_lift_overrun_is_not(extra, levels):
    parts = fit.tiers(box(0, 0, 30, 30), 12.0, heights_at((0, 0, 30, 30, 12.0), extra), CELL, city=False)
    assert tier_levels(parts) == levels

def test_a_parapet_is_not_a_tier():
    roof = heights_at((0, 0, 30, 30, 13.0), (0.5, 0.5, 29.5, 29.5, 12.0))  # 1 m higher round the edge
    assert tier_levels(fit.tiers(box(0, 0, 30, 30), 12.0, roof, CELL, city=False)) == [12.0]

def test_a_tree_crown_on_a_low_roof_is_not_a_tier():
    rng = np.random.default_rng(3)
    flat = heights_at((0, 0, 30, 30, 6.0))
    crown = Field(lambda x, y: np.where((x > 20) & (x < 28) & (y > 20) & (y < 27.5),
                                        rng.uniform(6.0, 14.0, size=np.shape(x)), flat.sample(x, y)))
    assert tier_levels(fit.tiers(box(0, 0, 30, 30), 6.0, crown, CELL, city=False)) == [6.0]


def test_a_smooth_spot_in_a_rough_crown_is_not_a_tier():
    rng = np.random.default_rng(3)
    roof = heights_at((0, 0, 40, 40, 6.0))

    def crowned(x, y):
        crown = (x > 20) & (x < 32) & (y > 20) & (y < 32)
        z = np.where(crown, rng.uniform(6.0, 14.0, size=np.shape(x)), roof.sample(x, y))
        return np.where((np.abs(x - 26) < 1) & (np.abs(y - 26) < 1), 11.0, z)  # a smooth 2 x 2 m top at 11 m
    assert tier_levels(fit.tiers(box(0, 0, 40, 40), 6.0, Field(crowned), CELL, city=False)) == [6.0]


def test_a_taller_solid_over_the_outline_adds_no_tier():
    lidar = heights_at((0, 0, 40, 40, 10.0), (12.5, 12.5, 27.5, 27.5, 40.0))
    parts = fit.tiers(box(0, 0, 40, 40), 10.0, lidar, CELL, city=False, taller=box(12.5, 12.5, 27.5, 27.5))
    assert tier_levels(parts) == [10.0] and parts[0][0].area == pytest.approx(1600.0)

def test_too_little_smooth_roof_is_no_tiers():
    assert fit.tiers(box(0, 0, 40, 40), 10.0, heights_at((0, 0, 3, 3, 10.0)), CELL, city=False) is None

def test_an_l_shaped_building_keeps_its_shape_in_tiers():
    ell = Polygon([(0, 0), (40, 0), (40, 15), (15, 15), (15, 40), (0, 40)])
    parts = fit.tiers(ell, 8.0, heights_at((0, 0, 40, 40, 8.0), (0, 20, 15, 40, 20.0)), CELL, city=False)
    assert tier_levels(parts) == [8.0, 20.0]
    assert shapely.union_all([p for p, _ in parts]).symmetric_difference(ell).area < 1e-6
    assert sum(p.area for p, _ in parts) == pytest.approx(ell.area, abs=1e-6)  # and they don't overlap


def house(ring, top=9.0, source="guessed", kind="building_guessed", **extra):
    s = solid(ring, top, kind=kind, source=source)
    s.update(extra)
    return s

def test_build_fits_houses_tiers_larger_buildings_and_counts_them():
    els = [ctx.element("osm:way:1", "building_guessed", solids=[house(square(-8, -5, 16)[:2] + [[8, 5], [-8, 5]])]),
           ctx.element("osm:way:2", "building", solids=[house(square(100, 0, 40), 12.0, "osm_levels", "building")])]
    field = Field(lambda x, y: np.where(x < 50, gable(0, 0, 0, 0.0).sample(x, y),
                                        heights_at((100, 0, 140, 40, 10.0), (112.5, 12.5, 127.5, 27.5, 40.0)).sample(x, y)))
    arrays, counts = fit.build(els, field, CELL)
    assert list(arrays["building_ids"]) == ["osm:way:1", "osm:way:2"]
    assert (counts["gable"], counts["larger"], counts["tiers"], counts["unfitted"], counts["newer"]) == (1, 1, 2, 0, 0)
    vs, fs = arrays["vert_start"], arrays["face_start"]
    assert counts["triangles"] == fs[-1] == len(arrays["faces"]) and counts["buildings"] == 2
    for b in range(2):
        v, f = arrays["verts"][vs[b]:vs[b + 1]].astype(float), arrays["faces"][fs[b]:fs[b + 1]]
        assert f.min() == 0 and f.max() == len(v) - 1 and lidar_roofs.closed(f) and volume(v, f) > 0
    assert not arrays["interior"].any() and len(arrays["interior"]) == len(arrays["verts"])
    plain, _ = lidar_roofs.build(els, field, CELL)
    assert list(arrays) == list(plain) and all(arrays[k].dtype == plain[k].dtype for k in arrays)
    assert set(data_kinds(arrays, 0)) == {2} and set(data_kinds(arrays, 1)) == {0}

def data_kinds(arrays, b):
    fs = arrays["face_start"]
    return arrays["face_kind"][fs[b]:fs[b + 1]].tolist()

def test_build_hands_the_height_tag_and_roof_tags_to_the_fitter():
    ring = square(-8, -5, 16)[:2] + [[8, 5], [-8, 5]]
    tops, roofs = [], []
    for s in (house(ring, 10.0, "osm_height", "building"), house(ring, 10.0, "osm_levels", "building"),
              house(ring, 10.0, "osm_levels", "building", roof={"shape": "flat"})):
        arrays, counts = fit.build([ctx.element("a", "building", solids=[s])], gable(0, 0, 0, 0.0), CELL)
        tops.append(round(float(arrays["verts"][:, 2].max()), 2))
        roofs.append(next(k for k in ("flat", "shed", "gable", "hip") if counts[k]))
    assert tops[:2] == [10.0, 9.0] and roofs[1:] == ["gable", "flat"]  # the height tag sets the top, the shape tag the roof

def test_a_house_that_cant_be_fitted_keeps_a_flat_top_at_its_measured_height():
    rng = np.random.default_rng(1)
    noise = Field(lambda x, y: rng.uniform(5.0, 13.0, size=np.shape(x)))
    arrays, counts = fit.build([ctx.element("a", "building", solids=[house(square(0, 0, 10), 15.0)])], noise, CELL)
    assert counts["unfitted"] == 1 and counts["triangles"] == 12
    top = arrays["verts"][:, 2].max()
    assert 8.0 < top < 10.0  # the median of 5-13 m, not the solid's own 15 m
    assert sorted(set(np.round(arrays["verts"][:, 2], 3).tolist()))[0] == pytest.approx(-0.3)

def test_no_lidar_at_all_keeps_the_solids_own_height():
    nothing = Field(lambda x, y: np.full(np.shape(x), np.nan))
    arrays, counts = fit.build([ctx.element("a", "building", solids=[house(square(0, 0, 10), 9.0)])], nothing, CELL)
    assert counts["unfitted"] == 1 and arrays["verts"][:, 2].max() == pytest.approx(9.0)

def test_a_building_newer_than_the_survey_keeps_its_own_height():
    s = solid(square(0, 0, 10), 48.0, source="osm_levels")
    arrays, counts = fit.build([ctx.element("a", "building", solids=[s])], east_of(7.0, 0.5, 30.0), CELL)
    assert counts["newer"] == 1 and arrays["verts"][:, 2].max() == pytest.approx(48.0)

def test_city_model_buildings_are_left_alone():
    els = [ctx.element("toronto:massing:2025:7", "building", solids=[solid(square(0, 0, 10), 18.0)])]
    assert fit.build(els, FLAT20, CELL) == (None, dict.fromkeys(
        ("buildings", "triangles", "flat", "shed", "gable", "hip", "larger", "tiers", "unfitted", "newer"), 0))

def test_a_separate_taller_building_over_a_podium_grows_no_copy():
    podium = solid(square(0, 0, 40), 10.0, source="osm_levels")
    tower = solid(square(12.5, 12.5, 15), 40.0, source="osm_levels")
    lidar = heights_at((0, 0, 40, 40, 10.0), (12.5, 12.5, 27.5, 27.5, 40.0))
    _, counts = fit.build([ctx.element("p", "building", solids=[podium]), ctx.element("t", "building", solids=[tower])],
                          lidar, CELL)
    assert counts["larger"] == 2 and counts["tiers"] == 2  # one tier each

def test_one_solid_the_geometry_library_chokes_on_keeps_a_flat_top(monkeypatch):
    def boom(*args, **kw):
        raise shapely.errors.GEOSException("boom")

    monkeypatch.setattr(fit, "house_solid", boom)
    arrays, counts = fit.build([ctx.element("a", "building", solids=[house(square(-8, -5, 16)[:2] + [[8, 5], [-8, 5]])])],
                               gable(0, 0, 0, 0.0), CELL)
    assert counts["unfitted"] == 1 and counts["triangles"] == 12

@pytest.mark.parametrize("counts, text", [
    ({"gable": 46, "hip": 10, "shed": 11, "flat": 0, "larger": 3, "tiers": 77, "unfitted": 0},
     "Fitted roofs: 67 houses (46 gable, 10 hip, 11 shed), 3 larger buildings in 77 tiers."),
    ({"gable": 0, "hip": 0, "shed": 0, "flat": 1, "larger": 1, "tiers": 1, "unfitted": 2},
     "Fitted roofs: 1 house (1 flat), 1 larger building in 1 tier. "
     "2 kept a flat top at the measured height."),
    ({"gable": 0, "hip": 0, "shed": 0, "flat": 0, "larger": 0, "tiers": 0, "unfitted": 4},
     "Fitted roofs: none could be fitted. 4 kept a flat top at the measured height."),
])
def test_the_note_says_what_was_fitted(counts, text):
    assert fit.note_text(counts) == text
