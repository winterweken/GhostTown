import numpy as np
import pytest
import shapely

from ghosttown_fetch import context as ctx
from ghosttown_fetch import lidar_roofs as roofs
from ghosttown_fetch import tiff
from ghosttown_fetch.frame import Frame
from ghosttown_fetch.sources import ontario_lidar as lidar
from lidar_samples import BAY_SURFACE, BAY_TERRAIN


class Field:
    """Heights above ground from a function of local x and y (NaN where there is none)."""

    def __init__(self, f):
        self.f = f

    def sample(self, xs, ys):
        return self.f(np.asarray(xs, dtype=float), np.asarray(ys, dtype=float))


FLAT20 = Field(lambda x, y: np.full(x.shape, 20.0))


def square(x0, y0, size):
    return [[x0, y0], [x0 + size, y0], [x0 + size, y0 + size], [x0, y0 + size]]


def volume(verts, faces):
    a, b, c = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def closed_outward(verts, faces):
    return roofs.closed(faces) and volume(verts, faces) > 0


def solid(ring, z1, kind="building", source="toronto_massing_lidar", z0=-0.3, ground=0.0):
    return ctx.solid(kind, [ring], z0, z1, source, ground=ground)


def test_a_flat_lidar_roof_makes_a_closed_box_at_the_lidar_height():
    v, f, inner = roofs.roof_solid([square(0, 0, 10)], -0.3, 18.0, 0.0, FLAT20, 0.5, city=True)
    assert closed_outward(v, f)
    assert np.allclose(v[inner][:, 2], 20.0) and inner.sum() == 19 * 19
    assert volume(v, f) == pytest.approx(100 * 20.3, rel=1e-6)


def test_a_pitched_roof_follows_the_lidar():
    ridge = Field(lambda x, y: 15.0 - np.abs(y - 5.0))
    v, f, inner = roofs.roof_solid([square(0, 0, 10)], -0.3, 12.0, 0.0, ridge, 0.5, city=True)
    assert closed_outward(v, f)
    top = v[inner]
    assert np.allclose(top[:, 2], 15.0 - np.abs(top[:, 1] - 5.0))


def test_eaves_sample_inside_the_outline_not_the_ground_beside_it():
    field = Field(lambda x, y: np.where((x > 0) & (x < 10) & (y > 0) & (y < 10), 20.0, 0.0))
    v, f, _ = roofs.roof_solid([square(0, 0, 10)], -0.3, 18.0, 0.0, field, 0.5, city=False)
    assert np.allclose(v[v[:, 2] > 0][:, 2], 20.0)


def test_city_outliers_take_the_citys_height():
    odd = Field(lambda x, y: np.where(x < 3, 40.0, np.where(x < 6, 1.0, np.nan)))  # a crane, a gap, no data
    v, f, inner = roofs.roof_solid([square(0, 0, 10)], -0.3, 18.0, 0.0, odd, 0.5, city=True)
    assert closed_outward(v, f) and np.allclose(v[inner][:, 2], 18.0)


def test_other_buildings_keep_lidar_heights_between_2_and_400_m():
    field = Field(lambda x, y: np.where(x < 3, 0.5, np.where(x < 6, 900.0, np.nan)))
    v, f, inner = roofs.roof_solid([square(0, 0, 10)], -0.3, 9.0, 0.0, field, 0.5, city=False)
    x, z = v[inner][:, 0], v[inner][:, 2]
    assert np.allclose(z[x < 2.9], 2.0) and np.allclose(z[(x > 3.1) & (x < 5.9)], 400.0)
    assert np.allclose(z[x > 6.1], 9.0)  # no LiDAR: the building's own height


def test_a_courtyard_gets_walls_and_stays_open():
    v, f, _ = roofs.roof_solid([square(0, 0, 20), square(5, 5, 10)[::-1]], -0.3, 18.0, 0.0, FLAT20, 0.5, city=True)
    assert closed_outward(v, f)
    assert volume(v, f) == pytest.approx(300 * 20.3, rel=1e-6)


@pytest.mark.parametrize("ring", [
    square(0.1, 0.1, 0.3),                                                          # inside one cell
    [[0.0, 0.0], [10.0, 0.001], [10.0, 10.0], [0.0, 10.0]],                          # a corner 1 mm off the grid
    [[0.0, 0.0], [7.0, 7.0], [0.0, 14.0], [-7.0, 7.0]],                              # turned 45 degrees
    [[0.2, 0.2], [9.73, 0.21], [9.74, 3.0], [4.0, 3.002], [4.0, 9.9], [0.2, 9.9]],   # an L off the grid
])
def test_awkward_outlines_still_close(ring):
    made = roofs.roof_solid([ring], -0.3, 18.0, 0.0, FLAT20, 0.5, city=True)
    assert made is not None and closed_outward(made[0], made[1])


def test_real_lidar_at_320_bay_street_tops_the_tower():
    heights = lidar.Heights(tiff.read(BAY_SURFACE), tiff.read(BAY_TERRAIN), Frame(43.649667, -79.380991))
    v, f, inner = roofs.roof_solid([square(-5, -5, 10)], -0.3, 73.8, 0.0, heights, 0.5, city=True)
    assert closed_outward(v, f) and abs(float(np.median(v[inner][:, 2])) - 73.8) < 6


def test_build_slices_each_building_and_names_the_kinds():
    els = [ctx.element("a", "building", solids=[solid(square(0, 0, 10), 18.0), solid(square(10, 0, 10), 18.0)]),
           ctx.element("ground:road", "road", meshes=[{"kind": "road", "verts": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                                                      "faces": [[0, 1, 2]]}]),
           ctx.element("b", "building_guessed", solids=[solid(square(30, 0, 5), 9.0, "building_guessed", "guessed")])]
    arrays, counts = roofs.build(els, FLAT20, 0.5)
    assert list(arrays["building_ids"]) == ["a", "b"] and counts["buildings"] == 2 and counts["flat"] == 0
    vs, fs = arrays["vert_start"], arrays["face_start"]
    assert vs[-1] == len(arrays["verts"]) and fs[-1] == len(arrays["faces"]) == counts["triangles"]
    for b in range(2):
        faces = arrays["faces"][fs[b]:fs[b + 1]]
        assert faces.min() == 0 and faces.max() == vs[b + 1] - vs[b] - 1 and roofs.closed(faces)
    assert list(arrays["kinds"]) == ["building", "building_on_site", "building_guessed"]
    assert set(arrays["face_kind"][:fs[1]].tolist()) == {0} and set(arrays["face_kind"][fs[1]:].tolist()) == {2}
    assert arrays["verts"].dtype == np.float32 and arrays["faces"].dtype == np.int32
    assert len(arrays["interior"]) == len(arrays["verts"])


def test_a_solid_without_its_ground_measures_up_from_its_base():
    s = ctx.solid("building", [square(0, 0, 10)], 9.7, 30.0, "osm_height")
    arrays, _ = roofs.build([ctx.element("a", "building", solids=[s])], FLAT20, 0.5)
    assert np.allclose(arrays["verts"][arrays["interior"].astype(bool)][:, 2], 30.0)


def test_a_solid_whose_roof_cant_be_built_keeps_a_flat_closed_top(monkeypatch):
    monkeypatch.setattr(roofs, "roof_solid", lambda *args: None)
    arrays, counts = roofs.build([ctx.element("a", "building", solids=[solid(square(0, 0, 10), 18.0)])], FLAT20, 0.5)
    assert counts == {"buildings": 1, "triangles": 12, "flat": 1}
    v, f = arrays["verts"], arrays["faces"]
    assert closed_outward(v.astype(float), f) and sorted(set(v[:, 2].tolist())) == [pytest.approx(-0.3), 18.0]


def test_one_solid_the_geometry_library_chokes_on_keeps_a_flat_top_and_the_rest_keep_their_roofs(monkeypatch):
    real = roofs.roof_solid

    def choke_on_the_low_solid(rings, z0, z1, *rest):
        if z1 == 12.0:
            raise shapely.errors.GEOSException("boom")
        return real(rings, z0, z1, *rest)

    monkeypatch.setattr(roofs, "roof_solid", choke_on_the_low_solid)
    els = [ctx.element("a", "building", solids=[solid(square(0, 0, 10), 18.0), solid(square(10, 0, 10), 12.0)])]
    arrays, counts = roofs.build(els, FLAT20, 0.5)
    assert list(arrays["building_ids"]) == ["a"] and counts["buildings"] == 1 and counts["flat"] == 1
    v, f = arrays["verts"], arrays["faces"]
    assert roofs.closed(f) and closed_outward(v.astype(float), f) and counts["triangles"] == len(f)
    roof = v[arrays["interior"].astype(bool)]
    assert len(roof) and np.allclose(roof[:, 2], 20.0)  # the first solid's roof follows the LiDAR
    assert 12.0 in v[:, 2] and (v[v[:, 0] > 10][:, 2] <= 12.0).all()  # the second keeps its flat top


def test_no_buildings_no_arrays():
    assert roofs.build([], FLAT20, 0.5) == (None, {"buildings": 0, "triangles": 0, "flat": 0})


def test_the_file_reads_back_without_pickles(tmp_path):
    arrays, _ = roofs.build([ctx.element("a", "building", solids=[solid(square(0, 0, 10), 18.0)])], FLAT20, 0.5)
    path = tmp_path / roofs.FILE
    roofs.write(str(path), arrays)
    with np.load(path) as data:
        assert set(data.files) == set(arrays) and list(data["building_ids"]) == ["a"]
        assert np.array_equal(data["faces"], arrays["faces"])


def test_coverage_is_the_share_of_the_footprints_with_lidar():
    half = Field(lambda x, y: np.where(x < 20, 5.0, np.nan))
    els = [ctx.element("a", "building", solids=[solid(square(0, 0, 40), 18.0)])]
    assert roofs.coverage(half, els) == pytest.approx(0.5, abs=0.06)
    assert roofs.coverage(FLAT20, []) == 0.0


def test_buildings_from_the_city_model_keep_their_massing():
    els = [ctx.element("toronto:massing:2025:7", "building", solids=[solid(square(0, 0, 10), 18.0)]),
           ctx.element("osm:way:1", "building", solids=[solid(square(20, 0, 10), 9.0, source="osm_height")]),
           ctx.element("toronto:building:3", "building", solids=[solid(square(40, 0, 10), 12.0, source="toronto_derived")])]
    arrays, counts = roofs.build(els, FLAT20, 0.5)
    assert list(arrays["building_ids"]) == ["osm:way:1", "toronto:building:3"] and counts["buildings"] == 2
    assert [roofs.wanted(el) for el in els] == [False, True, True]
    assert roofs.coverage(Field(lambda x, y: np.where(x < 15, np.nan, 5.0)), els) == 1.0  # the City's part isn't counted
