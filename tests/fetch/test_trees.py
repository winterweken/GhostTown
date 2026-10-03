import json

import numpy as np
import pytest

from ghosttown_fetch import context as ctx
from ghosttown_fetch import request as rq
from ghosttown_fetch import trees
from ghosttown_fetch.frame import Frame
from ghosttown_fetch.sources import toronto
from fakes import FakeNet, form
from terrains import Ramp
from toronto_samples import LAT0, LON0, page, point


def _closed_outward(verts, faces):
    directed = set()
    for f in faces:
        for i in range(3):
            e = (f[i], f[(i + 1) % 3])
            if e in directed:
                return False
            directed.add(e)
    if any((b, a) not in directed for a, b in directed):
        return False
    v = np.array(verts, dtype=float)
    vol = sum(np.dot(v[a], np.cross(v[b], v[c])) for a, b, c in faces) / 6
    return vol > 0


def _crown_radius(height):
    crown = np.array(trees.tree_meshes(0.0, 0.0, 0.0, height)[1]["verts"])
    return float(np.linalg.norm(crown - crown.mean(axis=0), axis=1).max())


def test_tree_meshes_are_closed_and_outward():
    for h in (2.0, 8.0, 30.0):
        for m in trees.tree_meshes(10.0, 20.0, 5.0, h):
            assert m["kind"] == "tree" and _closed_outward(m["verts"], m["faces"])


def test_crown_size_follows_height_within_limits():
    assert _crown_radius(2.0) == pytest.approx(1.5, abs=0.002)
    assert _crown_radius(10.0) == pytest.approx(3.0, abs=0.002)
    assert _crown_radius(40.0) == pytest.approx(6.0, abs=0.002)


def test_the_crown_stays_clear_of_the_ground():
    for h in (2.0, 3.0, 8.0):
        crown = np.array(trees.tree_meshes(0.0, 0.0, 5.0, h)[1]["verts"])
        assert crown[:, 2].min() >= 5.0 + 0.5 - 0.002


def test_city_trees_use_their_height_and_stand_on_the_terrain():
    feats = json.loads(page(point(10, 0, OBJECTID=1, DERIVED_HEIGHT=12.0), point(20, 0, OBJECTID=2, DERIVED_HEIGHT=None),
                            point(30, 0, OBJECTID=3, DERIVED_HEIGHT=500.0)))["features"]
    els = trees.from_toronto(feats, Frame(LAT0, LON0), Ramp())
    assert [e["id"] for e in els] == ["tree:toronto:1", "tree:toronto:2", "tree:toronto:3"]
    bottoms = [min(v[2] for m in e["meshes"] for v in m["verts"]) for e in els]
    assert bottoms == pytest.approx([0.9, 1.9, 2.9], abs=0.01)
    tops = [max(v[2] for m in e["meshes"] for v in m["verts"]) - (b + 0.1) for e, b in zip(els, bottoms)]
    assert tops[0] == pytest.approx(12.0, rel=0.1) and tops[1] == pytest.approx(8.0, rel=0.1) and tops[2] == pytest.approx(tops[1])
    req = rq.build(centre={"lat": LAT0, "lon": LON0}, radius_m=150, cache_dir="c", out_dir="o")
    doc = ctx.new(req, region="toronto", terrain_source="test")
    doc["elements"] = els
    assert ctx.validate(ctx.finish(doc)) == []


def test_fetch_trees_asks_the_topographic_tree_layer():
    net = FakeNet({"toronto": page(point(0, 0, OBJECTID=1, DERIVED_HEIGHT=9.0))})
    feats = toronto.fetch_trees(net, LAT0, LON0, 150)
    assert len(feats) == 1 and net.calls[0][0].endswith("/cot_geospatial3/FeatureServer/10/query")
    assert form(net.calls[0][2])["outFields"] == "OBJECTID,DERIVED_HEIGHT"
