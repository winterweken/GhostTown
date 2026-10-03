import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FIXTURES = os.path.join(HERE, "fixtures")


def load_fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


def mesh_arrays(ob):
    me = ob.data
    return [tuple(v.co) for v in me.vertices], [tuple(p.vertices) for p in me.polygons]


def signed_volume(verts, faces):
    total = 0.0
    for f in faces:
        ax, ay, az = verts[f[0]]
        for i in range(1, len(f) - 1):
            bx, by, bz = verts[f[i]]
            cx, cy, cz = verts[f[i + 1]]
            total += ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)
    return total / 6.0


def closed_and_outward(verts, faces):
    """Every edge is used once in each direction (closed, consistent) and the volume is positive."""
    directed = set()
    for f in faces:
        for i in range(len(f)):
            edge = (f[i], f[(i + 1) % len(f)])
            if edge in directed:
                return False
            directed.add(edge)
    if any((b, a) not in directed for a, b in directed):
        return False
    return signed_volume(verts, faces) > 0


def min_edge(verts, faces):
    best = float("inf")
    for f in faces:
        for i in range(len(f)):
            a, b = verts[f[i]], verts[f[(i + 1) % len(f)]]
            best = min(best, sum((p - q) ** 2 for p, q in zip(a, b)) ** 0.5)
    return best
