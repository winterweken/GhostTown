import time

import numpy as np
import pytest
from shapely.geometry import box

from ghosttown_fetch import context as ctx
from ghosttown_fetch import ground
from ghosttown_fetch import request as rq
from ghosttown_fetch.terrain import FlatTerrain
from terrains import Ramp

R = 100.0
DISC = ground.disc(R)
ROAD = box(-200, -5, 200, 5)


def _areas(faces):
    out = {}
    for kind, face in faces:
        out[kind] = out.get(kind, 0.0) + face.area
    return out


def _tri_areas(m):
    v = np.array(m["verts"])
    f = np.array(m["faces"])
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return ((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1])) / 2


def test_layout_covers_the_disc_exactly_once():
    areas = _areas(ground.layout({"road": [ROAD], "sidewalk": [box(-200, -8, 200, 8)]}, R))
    assert sum(areas.values()) == pytest.approx(DISC.area, rel=1e-6)
    assert areas["road"] == pytest.approx(DISC.intersection(ROAD).area, rel=1e-4)
    assert areas["sidewalk"] == pytest.approx(DISC.intersection(box(-200, -8, 200, 8)).area - areas["road"], rel=1e-3)


def test_water_beats_road():
    areas = _areas(ground.layout({"road": [ROAD], "water": [box(-10, -50, 10, 50)]}, R))
    assert areas["road"] == pytest.approx(DISC.intersection(ROAD).area - 20 * 10, rel=1e-3)


def test_faces_are_split_on_the_grid():
    faces = ground.layout({}, R)
    cell = ground.cell_size(R)
    assert {k for k, _ in faces} == {"ground"} and max(f.area for _, f in faces) <= cell * cell + 1e-6


def test_without_plain_ground_only_the_pieces_remain():
    faces = ground.layout({"road": [ROAD]}, R, include_ground=False)
    assert {k for k, _ in faces} == {"road"}


def test_mesh_is_counter_clockwise_complete_and_shares_seams():
    meshes = ground.mesh(ground.layout({"road": [ROAD]}, R), FlatTerrain())
    total = 0.0
    for m in meshes.values():
        areas = _tri_areas(m)
        assert (areas > 0).all()
        total += areas.sum()
    assert total == pytest.approx(DISC.area, rel=1e-3)
    road = {tuple(p[:2]) for p in meshes["road"]["verts"]}
    plain = {tuple(p[:2]) for p in meshes["ground"]["verts"]}
    assert len(road & plain) > 20


def test_no_edge_is_shorter_than_3mm():
    sliver = box(-200, 5.0005, 200, 5.0015)
    meshes = ground.mesh(ground.layout({"road": [ROAD], "sidewalk": [sliver]}, R), FlatTerrain())
    for m in meshes.values():
        v = np.array(m["verts"])[:, :2]
        for f in m["faces"]:
            for i in range(3):
                assert np.linalg.norm(v[f[i]] - v[f[(i + 1) % 3]]) >= 0.003 - 1e-9


def test_ground_is_draped_on_the_terrain():
    meshes = ground.mesh(ground.layout({"road": [ROAD]}, R), Ramp())
    for m in meshes.values():
        v = np.array(m["verts"])
        assert np.allclose(v[:, 2], 0.1 * v[:, 0], atol=0.001)


def test_water_sits_at_its_shoreline_level():
    meshes = ground.mesh(ground.layout({"water": [box(10, -30, 60, 30)]}, R), Ramp())
    plain = {tuple(p[:2]) for p in meshes["ground"]["verts"]}
    inner = [p for p in meshes["water"]["verts"] if tuple(p[:2]) not in plain]
    assert inner and len({p[2] for p in inner}) == 1
    assert 0.9 <= inner[0][2] < 3.5


def test_elements_are_valid_context_in_order():
    els = ground.elements(ground.layout({"road": [ROAD], "water": [box(-10, 20, 10, 40)]}, R), FlatTerrain())
    assert [e["id"] for e in els] == ["ground:water", "ground:road", "ground:ground"]
    req = rq.build(centre={"lat": 43.65, "lon": -79.38}, radius_m=R, cache_dir="c", out_dir="o")
    doc = ctx.new(req, region="toronto", terrain_source="flat")
    doc["elements"] = els
    assert ctx.validate(ctx.finish(doc)) == []


def test_a_1000m_site_with_many_pieces_lays_out_in_seconds():
    rng = np.random.default_rng(1)
    pieces = {"road": [box(x, -1000, x + 12, 1000) for x in range(-1000, 1000, 80)],
              "sidewalk": [box(x - 3, -1000, x, 1000) for x in range(-1000, 1000, 80)],
              "green": [box(x, y, x + 30, y + 30) for x, y in rng.uniform(-900, 900, (150, 2))]}
    started = time.monotonic()
    meshes = ground.mesh(ground.layout(pieces, 1000.0), FlatTerrain())
    assert time.monotonic() - started < 30.0
    assert sum(len(m["faces"]) for m in meshes.values()) > 10000


def test_each_water_body_sits_at_its_own_shoreline():
    meshes = ground.mesh(ground.layout({"water": [box(-80, -10, -60, 10), box(60, -10, 80, 10)]}, R), Ramp())
    plain = {tuple(p[:2]) for p in meshes["ground"]["verts"]}
    inner = [p for p in meshes["water"]["verts"] if tuple(p[:2]) not in plain]
    west = {p[2] for p in inner if p[0] < 0}
    east = {p[2] for p in inner if p[0] > 0}
    assert len(west) == 1 and len(east) == 1
    assert -8.2 <= west.pop() <= -7.5 and 5.8 <= east.pop() <= 6.5
