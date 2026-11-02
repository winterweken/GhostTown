import json
import math
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FIXTURES = os.path.join(HERE, "fixtures")
PHOTO = os.path.join(ROOT, "tests", "fetch", "fixtures", "bay", "photo_128.jpg")


def load_fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


def add_photo(doc, folder):
    """`doc` with a 128 px photo covering ±150 m, its file copied into `folder` beside it."""
    shutil.copy(PHOTO, os.path.join(folder, "photo.jpg"))
    doc["photo"] = {"file": "photo.jpg", "year": 2025, "width_px": 128, "height_px": 128,
                    "bounds_m": [-150.0, -150.0, 150.0, 150.0], "source": "toronto"}
    return doc


def photo_doc(folder, address=None):
    """The mini context with a 128 px photo covering ±150 m, copied into `folder` beside it."""
    doc = load_fixture("mini_context.json")
    if address is not None:
        doc["address"] = address
    return add_photo(doc, folder)


def drum_doc(radius=150.0, slope=0.02, photo_folder=None, address=None):
    """The mini context on a sloping round site: three ground pieces tile the circle on the plane
    z = slope * x (ground 0-240 degrees, green 240-300, water 300-360, fans of 1 degree segments from the
    centre to the rim), the mini buildings plus osm:way:9 crossing the rim, and the mini tree plus one
    straddling it. With `photo_folder`, the photo too; `address` names the site."""
    doc = load_fixture("mini_context.json")
    if address:
        doc["address"] = address
    doc["radius_m"] = radius

    def fan(kind, start, end):
        verts = [[0.0, 0.0, 0.0]]
        for deg in range(start, end + 1):
            x, y = radius * math.cos(math.radians(deg)), radius * math.sin(math.radians(deg))
            verts.append([x, y, slope * x])
        faces = [[0, i, i + 1] for i in range(1, len(verts) - 1)]
        return {"id": "ground:" + kind, "kind": kind, "name": "", "solids": [], "lines": [],
                "meshes": [{"kind": kind, "verts": verts, "faces": faces}]}

    road = doc["elements"][0]
    assert road["id"] == "ground:road"
    ground = [fan("ground", 0, 240), fan("green", 240, 300), fan("water", 300, 360)]
    rim_tree = {"id": "tree:osm:9", "kind": "tree", "name": "", "solids": [], "lines": [], "meshes": [
        {"kind": "tree", "verts": [[radius, 0, slope * radius], [radius + 1, 0, slope * radius],
                                   [radius, 1, slope * radius], [radius, 0, slope * radius + 3]],
         "faces": [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]}]}
    across = {"id": "osm:way:9", "kind": "building", "name": "", "meshes": [], "lines": [], "solids": [
        {"kind": "building", "rings": [[[radius - 10, -5], [radius + 30, -5], [radius + 30, 5], [radius - 10, 5]]],
         "z0": -0.3, "z1": 20.0, "height_source": "osm_levels"}]}
    doc["elements"] = ground + [e for e in doc["elements"] if e is not road] + [across, rim_tree]
    return doc if photo_folder is None else add_photo(doc, photo_folder)


def fetch_tree_meshes(x, y, z, height):
    """The fetcher's own two meshes for one tree (ghosttown_fetch.trees.tree_meshes). trees.py imports shapely
    for reading features only, and Blender has none, so a stand-in for its geom module lets it load."""
    import importlib
    import sys
    import types

    names = ("ghosttown.ghosttown_fetch.geom", "ghosttown.ghosttown_fetch.trees")
    saved = {name: sys.modules.get(name) for name in names}
    if saved[names[1]] is None:
        stub = sys.modules[names[0]] = types.ModuleType(names[0])
        stub.feature_geometry = None
    try:
        trees = importlib.import_module(names[1])
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    return trees.tree_meshes(float(x), float(y), float(z), float(height))


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


LIDAR = {"file": "lidar_roofs.npz", "cell_m": 0.5, "year": None, "source": "ontario", "buildings": 2,
         "triangles": 28, "kinds": ["building", "building_on_site", "building_guessed"]}

FITTED = {"file": "fitted_roofs.npz", "buildings": 2, "triangles": 28}


def pyramid(x0, y0, x1, y1, z0, z1, apex):
    """A closed box with a pyramid roof: the apex is the one roof point off the outline."""
    verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1), ((x0 + x1) / 2, (y0 + y1) / 2, apex)]
    faces = [(0, 2, 1), (0, 3, 2), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6),
             (3, 0, 4), (3, 4, 7), (4, 5, 8), (5, 6, 8), (6, 7, 8), (7, 4, 8)]
    return verts, faces, [0] * 8 + [1]


def grid_box(x0, y0, size, n, z0, z1):
    """A closed box whose top is an n × n grid with a bump in it; the top's inner points are the roof
    interior. Dense enough for Roof detail to have something to simplify."""
    import math

    step = size / n
    verts, interior = [], []

    def vid(layer, i, j):
        return layer * (n + 1) ** 2 + i * (n + 1) + j

    for layer, z in ((0, z0), (1, z1)):
        for i in range(n + 1):
            for j in range(n + 1):
                inner = layer == 1 and 0 < i < n and 0 < j < n
                verts.append((x0 + i * step, y0 + j * step, z + (math.sin(i) * math.cos(j) if inner else 0.0)))
                interior.append(int(inner))
    faces = []
    for i in range(n):
        for j in range(n):
            a, b, c, d = vid(1, i, j), vid(1, i + 1, j), vid(1, i + 1, j + 1), vid(1, i, j + 1)
            faces += [(a, b, c), (a, c, d)]
            a, b, c, d = vid(0, i, j), vid(0, i + 1, j), vid(0, i + 1, j + 1), vid(0, i, j + 1)
            faces += [(a, c, b), (a, d, c)]
    ring = ([(i, 0) for i in range(n)] + [(n, j) for j in range(n)]
            + [(i, n) for i in range(n, 0, -1)] + [(0, j) for j in range(n, 0, -1)])
    for k in range(len(ring)):
        (i, j), (p, q) = ring[k], ring[(k + 1) % len(ring)]
        faces += [(vid(0, i, j), vid(0, p, q), vid(1, p, q)), (vid(0, i, j), vid(1, p, q), vid(1, i, j))]
    return verts, faces, interior


def write_lidar(folder, buildings, name="lidar_roofs.npz"):
    """lidar_roofs.npz (or `name`) in `folder`, laid out as the fetcher writes it: buildings is
    [(element id, verts, faces, interior, kind index)], faces indexing each building's own vertices."""
    import numpy as np

    verts, faces, kinds, interior, ids, vs, fs = [], [], [], [], [], [0], [0]
    for element_id, v, f, inner, kind in buildings:
        verts += v
        faces += f
        interior += inner
        kinds += [kind] * len(f)
        ids.append(element_id)
        vs.append(vs[-1] + len(v))
        fs.append(fs[-1] + len(f))
    np.savez_compressed(os.path.join(folder, name), verts=np.array(verts, dtype=np.float32),
                        faces=np.array(faces, dtype=np.int32), face_kind=np.array(kinds, dtype=np.uint8),
                        interior=np.array(interior, dtype=np.uint8), building_ids=np.array(ids, dtype=str),
                        vert_start=np.array(vs, dtype=np.int64), face_start=np.array(fs, dtype=np.int64),
                        kinds=np.array(LIDAR["kinds"], dtype=str))


def lidar_doc(folder, address=None, photo=False, dense=False):
    """The mini context with LiDAR roofs in `folder`: a pyramid on the tower, and on the shed a pyramid or
    (dense) a 20 × 20 grid. With the photo too when asked."""
    doc = photo_doc(folder, address) if photo else load_fixture("mini_context.json")
    if address is not None:
        doc["address"] = address
    shed = grid_box(30, 10, 20, 20, -0.3, 9.0) if dense else pyramid(30, 10, 50, 30, -0.3, 9.0, 11.0)
    write_lidar(folder, [("osm:way:1", *pyramid(0, 10, 20, 30, -0.3, 60.0, 64.0), 0), ("osm:way:2", *shed, 2)])
    doc["lidar"] = dict(LIDAR)
    return doc


def fitted_doc(folder, address=None, photo=False, dense=False):
    """lidar_doc with fitted roofs too: on each building a lower pyramid than its LiDAR one, the apex
    still the one point off the outline (fitted roofs flag none)."""
    doc = lidar_doc(folder, address=address, photo=photo, dense=dense)
    tower = pyramid(0, 10, 20, 30, -0.3, 60.0, 62.0)
    shed = pyramid(30, 10, 50, 30, -0.3, 9.0, 10.0)
    write_lidar(folder, [("osm:way:1", *tower[:2], [0] * 9, 0), ("osm:way:2", *shed[:2], [0] * 9, 2)],
                name="fitted_roofs.npz")
    doc["lidar"]["fitted"] = dict(FITTED)
    return doc


def open_only_at_the_top(verts, faces):
    """Every edge is shared by two faces except one closed loop of boundary edges, and that loop is the
    mesh's highest vertex ring: each of its vertices is the top of its wall column."""
    uses = {}
    for f in faces:
        for i in range(len(f)):
            edge = frozenset((f[i], f[(i + 1) % len(f)]))
            uses[edge] = uses.get(edge, 0) + 1
    if any(count > 2 for count in uses.values()):
        return False
    boundary = [tuple(e) for e, count in uses.items() if count == 1]
    around = {}
    for a, b in boundary:
        around.setdefault(a, []).append(b)
        around.setdefault(b, []).append(a)
    if not boundary or any(len(n) != 2 for n in around.values()):
        return False
    seen, stack = set(), [boundary[0][0]]
    while stack:
        v = stack.pop()
        if v not in seen:
            seen.add(v)
            stack.extend(around[v])
    if seen != set(around):
        return False                                   # more than one loop
    top = {}
    for x, y, z in verts:
        key = (round(x, 3), round(y, 3))
        top[key] = max(top.get(key, -math.inf), z)
    return all(verts[v][2] >= top[(round(verts[v][0], 3), round(verts[v][1], 3))] - 1e-6 for v in around)
