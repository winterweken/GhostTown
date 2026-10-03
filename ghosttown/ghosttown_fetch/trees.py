"""Trees as two closed low-poly meshes: a hexagonal trunk and an icosahedron crown."""
import math

import numpy as np

from . import context as ctx
from .geom import feature_geometry

DEFAULT_HEIGHT_M = 8.0
HEIGHT_RANGE_M = (2.0, 60.0)

_PHI = (1 + 5 ** 0.5) / 2
_NORM = math.sqrt(1 + _PHI ** 2)
_UNIT = [(x / _NORM, y / _NORM, z / _NORM) for x, y, z in [
    (-1, _PHI, 0), (1, _PHI, 0), (-1, -_PHI, 0), (1, -_PHI, 0), (0, -1, _PHI), (0, 1, _PHI),
    (0, -1, -_PHI), (0, 1, -_PHI), (_PHI, 0, -1), (_PHI, 0, 1), (-_PHI, 0, -1), (-_PHI, 0, 1)]]
_FACES = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
          (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5),
          (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]


def _outward(verts, faces):
    v = np.array(verts)
    volume = sum(np.dot(v[a], np.cross(v[b], v[c])) for a, b, c in faces)
    return faces if volume > 0 else [(a, c, b) for a, b, c in faces]


_FACES = _outward(_UNIT, _FACES)


def _r(value):
    return round(float(value), 3)


def tree_meshes(x, y, z, height):
    """A trunk from just below the ground into the crown, and a crown sized from the tree's height."""
    trunk_r = min(0.3, max(0.15, 0.02 * height))
    crown_r = min(6.0, max(1.5, 0.3 * height))
    crown_z = z + max(0.65 * height, crown_r + 0.5)
    ring = [(x + trunk_r * math.cos(k * math.pi / 3), y + trunk_r * math.sin(k * math.pi / 3)) for k in range(6)]
    trunk_verts = [[_r(px), _r(py), _r(z - 0.1)] for px, py in ring] + [[_r(px), _r(py), _r(crown_z)] for px, py in ring]
    trunk_faces = [[0, k + 1, k] for k in range(1, 5)] + [[6, 6 + k, 7 + k] for k in range(1, 5)]
    for k in range(6):
        a, b = k, (k + 1) % 6
        trunk_faces += [[a, b, b + 6], [a, b + 6, a + 6]]
    crown_verts = [[_r(x + crown_r * ux), _r(y + crown_r * uy), _r(crown_z + crown_r * uz)] for ux, uy, uz in _UNIT]
    return [{"kind": "tree", "verts": trunk_verts, "faces": trunk_faces},
            {"kind": "tree", "verts": crown_verts, "faces": [list(f) for f in _FACES]}]


def from_toronto(features, frame, terrain):
    lo, hi = HEIGHT_RANGE_M
    found = []
    for feature in features:
        geom = feature_geometry(feature)
        if geom is None or geom.geom_type != "Point":
            continue
        props = feature.get("properties") or {}
        h = props.get("DERIVED_HEIGHT")
        height = float(h) if isinstance(h, (int, float)) and lo <= h <= hi else DEFAULT_HEIGHT_M
        x, y = frame.to_local(geom.x, geom.y)
        found.append((props.get("OBJECTID"), x, y, height))
    if not found:
        return []
    zs = terrain.z(np.array([p[1] for p in found]), np.array([p[2] for p in found]))
    return [ctx.element(f"tree:toronto:{oid}", "tree", meshes=tree_meshes(x, y, float(z), height))
            for (oid, x, y, height), z in zip(found, zs)]
