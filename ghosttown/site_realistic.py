"""The earth drum under a site on the Realistic ground look: a ring wall around the site's circle and a
flat base, open on top where the ground pieces close it."""
import json
import math

import bpy
import numpy as np

from . import realistic, site_use
from .ghosttown_fetch import GROUND_KINDS

EARTH_DEPTH_M = 15.0     # the base sits this far below the rim's lowest point
RING_SPACING_M = 1.0     # about one wall vertex every metre around the circle
RIM_TOLERANCE_M = 0.5    # ground vertices this close to the radius count as the rim
EARTH = "earth"


def ring_angles(root):
    """The angles (radians, from 0) of the wall's vertices, about RING_SPACING_M apart. The cutter that
    trims buildings at the drum uses the same ones."""
    n = max(16, math.ceil(2 * math.pi * root["radius_m"] / RING_SPACING_M))
    return np.arange(n) * (2 * math.pi / n)


def rim_heights(root, angles):
    """The terrain height at each angle on the site's circle, from the boundary vertices of the ground
    pieces nearest the rim; the site's ground height at the centre where there are none."""
    points = []
    for ob in site_use.made_objects(root, GROUND_KINDS):
        me = ob.data
        count = {}
        for poly in me.polygons:
            for key in poly.edge_keys:
                count[key] = count.get(key, 0) + 1
        rim = sorted({v for key, c in count.items() if c == 1 for v in key})
        co = np.empty(len(me.vertices) * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)[rim]
        if len(co):
            world = np.array(ob.matrix_world)
            points.append(co @ world[:3, :3].T + world[:3, 3])
    points = np.concatenate(points) if points else np.empty((0, 3))
    near = points[np.abs(np.hypot(points[:, 0], points[:, 1]) - root["radius_m"]) <= RIM_TOLERANCE_M]
    if not len(near):
        return np.full(len(angles), float(root.get("ground_at_centre_m", 0.0)))
    theta = np.arctan2(near[:, 1], near[:, 0]) % (2 * math.pi)
    order = np.argsort(theta)
    return np.interp(np.asarray(angles) % (2 * math.pi), theta[order], near[order, 2], period=2 * math.pi)


def find(root, kind):
    """The site's own `earth` or `earth_cutter`, or None."""
    found = site_use.made_objects(root, (kind,))
    return found[0] if found else None


def _forget(root, ob):
    names = [n for n in json.loads(root.get("ctx_objects", "[]")) if n != ob.name]
    root["ctx_objects"] = json.dumps(names)
    me = ob.data
    bpy.data.objects.remove(ob)
    if me is not None and me.users == 0:
        bpy.data.meshes.remove(me)


def remove_earth(root):
    old = find(root, EARTH)
    if old is not None:
        _forget(root, old)


def make_earth(root):
    """The site's earth drum, replacing any it has: made, linked in the root and recorded for removal."""
    remove_earth(root)
    angles = ring_angles(root)
    n = len(angles)
    rim = rim_heights(root, angles)
    base = float(rim.min()) - EARTH_DEPTH_M
    r = root["radius_m"]
    x, y = r * np.cos(angles), r * np.sin(angles)
    verts = np.concatenate([np.column_stack([x, y, rim]), np.column_stack([x, y, np.full(n, base)])])
    nxt = (np.arange(n) + 1) % n
    faces = [(i, n + i, n + nxt[i], nxt[i]) for i in range(n)] + [tuple(range(2 * n - 1, n - 1, -1))]
    name = f"Earth · {root['ctx_label']}"
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts.tolist(), [], faces)
    me.materials.append(realistic.get_material(realistic.EARTH))
    depth = me.attributes.new(realistic.DEPTH_ATTRIBUTE, "FLOAT", "POINT")
    depth.data.foreach_set("value", np.concatenate([np.zeros(n), rim - base]).astype(np.float32))
    me.update()
    ob = bpy.data.objects.new(name, me)
    ob["ctx_id"] = "earth"
    ob["ctx_kind"] = EARTH
    root.objects.link(ob)
    root["ctx_objects"] = json.dumps(json.loads(root.get("ctx_objects", "[]")) + [ob.name])
    return ob
