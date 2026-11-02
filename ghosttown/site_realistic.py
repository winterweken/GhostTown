"""The earth drum under a site on the Realistic ground look: a ring wall around the site's circle and a
flat base, open on top where the ground pieces close it."""
import json
import math

import bpy
import numpy as np

from . import realistic, site_use
from .ghosttown_fetch import BUILDING_KINDS, CIRCLE_QUAD_SEGS, GROUND_KINDS

EARTH_DEPTH_M = 15.0     # the base sits this far below the rim's lowest point
RING_SPACING_M = 1.0     # about one wall vertex every metre around the circle
RIM_TOLERANCE_M = 0.5    # ground vertices this close to the radius count as the rim
EARTH = "earth"
CUTTER = "earth_cutter"
TRIM = site_use.EDGE_TRIM
CLOSED_KINDS = ("tree", "facade_detail")   # every part closed: the Manifold solver trims them fast and right
TRIM_KINDS = BUILDING_KINDS + CLOSED_KINDS  # what gets cut at the drum's wall
TRIM_TOLERANCE_M = 0.01  # a vertex this far past the radius counts as crossing
CUTTER_ABOVE_M = 10.0    # the cutter rises this far above the tallest object it may trim


def ring_angles(root):
    """The angles (radians, from 0) of the wall's vertices, about RING_SPACING_M apart. The cutter that
    trims buildings at the drum uses the same ones."""
    n = max(64, math.ceil(2 * math.pi * root["radius_m"] / RING_SPACING_M))
    return np.arange(n) * (2 * math.pi / n)


def wall_radius(root):
    """The radius of the earth wall and the cutter: the inscribed radius of the ground's site polygon, so the
    ground's rim overhangs the wall a little rather than leaving a slit, and trims land on the wall."""
    return root["radius_m"] * math.cos(math.pi / (4 * CIRCLE_QUAD_SEGS))


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
    r = wall_radius(root)
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


def _world_points(ob, me):
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    world = np.array(ob.matrix_world)
    return co.reshape(-1, 3) @ world[:3, :3].T + world[:3, 3]


def make_cutter(root):
    """The site's hidden cutter: a closed cylinder on the earth wall's circle, from below the drum's base
    to above the tallest object that can be trimmed. Replaces any it has."""
    old = find(root, CUTTER)
    if old is not None:
        _forget(root, old)
    angles = ring_angles(root)
    n = len(angles)
    r = wall_radius(root)
    rim = rim_heights(root, angles)
    top = float(rim.max())
    for ob in site_use.made_objects(root, TRIM_KINDS):
        for me in site_use.meshes_of(ob):
            if len(me.vertices):
                top = max(top, float(_world_points(ob, me)[:, 2].max()))
    bottom = float(rim.min()) - EARTH_DEPTH_M - 1.0
    x, y = r * np.cos(angles), r * np.sin(angles)
    verts = np.concatenate([np.column_stack([x, y, np.full(n, bottom)]),
                            np.column_stack([x, y, np.full(n, top + CUTTER_ABOVE_M)])])
    nxt = (np.arange(n) + 1) % n
    faces = [(i, nxt[i], n + nxt[i], n + i) for i in range(n)]
    faces += [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    name = f"Earth cutter · {root['ctx_label']}"
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts.tolist(), [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    ob["ctx_id"] = CUTTER
    ob["ctx_kind"] = CUTTER
    ob.hide_viewport = ob.hide_render = True
    root.objects.link(ob)
    root["ctx_objects"] = json.dumps(json.loads(root.get("ctx_objects", "[]")) + [ob.name])
    return ob


def crosses_edge(root, ob):
    """True when a vertex of any mesh the object can show lies past the drum's wall."""
    limit = wall_radius(root) + TRIM_TOLERANCE_M
    return any(len(me.vertices) and (np.hypot(*_world_points(ob, me)[:, :2].T) > limit).any()
               for me in site_use.meshes_of(ob))


def add_trim(root):
    """Cut what crosses the site's circle flat at the drum's wall, with a Boolean modifier that is never
    applied and goes after the object's other modifiers. Trees and facade detail use the Manifold solver
    (Exact can empty a merged object whose closed parts overlap, like tree crowns); buildings use Exact,
    which tolerates massing that isn't closed. Makes the cutter if the site has none. Returns how many
    objects carry the trim."""
    cutter = find(root, CUTTER) or make_cutter(root)
    count = 0
    for ob in site_use.made_objects(root, TRIM_KINDS):
        mod = ob.modifiers.get(TRIM)
        if mod is None:
            if not crosses_edge(root, ob):
                continue
            mod = ob.modifiers.new(TRIM, "BOOLEAN")
            mod.operation = "INTERSECT"
            if ob["ctx_kind"] in CLOSED_KINDS:
                mod.solver = "MANIFOLD"
            else:
                mod.solver = "EXACT"
                mod.use_hole_tolerant = True
        mod.object = cutter
        count += 1
    return count


def remove_trim(root):
    """Remove every trim modifier on the site's objects and the cutter."""
    for ob in root.all_objects:
        mod = ob.modifiers.get(TRIM)
        if mod is not None:
            ob.modifiers.remove(mod)
    old = find(root, CUTTER)
    if old is not None:
        _forget(root, old)
