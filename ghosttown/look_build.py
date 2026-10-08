"""Street Look on the Blender side: the request from a site, and look.json applied to it.

The answer is stored on the context collection as JSON, so a rebuild can put it back on the new objects
by building id. Each building gets its values as gt_look_* custom properties, which the Street Look node
group in the building materials reads, whichever roof shape the building shows; detail buildings also
get a mesh in a Detail collection. Only the site's own buildings take part, never the user's duplicates.
"""
import json
import math
import os
import time
from collections import Counter

import bpy

from . import look_detail, materials, site_use
from .ghosttown_fetch import BUILDING_KINDS
from .ghosttown_fetch import look_schema as ls

LOOK_PROP = "gt_look_json"
SUMMARY_PROP, CREDITS_PROP = "gt_look_summary", "gt_look_credits"   # what the panel shows for the site
DETAIL_GROUP = "Detail"
DETAIL_KIND = "facade_detail"
TOP = 1.0e5                       # a zone top meaning "to the top of the building"
GLASS_BAY_M, OPAQUE_BAY_M = 1.5, 3.0
BOTTOM_NORMAL_Z = -0.99           # faces pointing this far down are a solid's underside
DETAIL_FIT_M = 0.5                # a rebuild keeps stored detail walls whose ends lie this near the footprint
SKY_WORLD = "Ghost Town Sky"
SKY_SUN = "Ghost Town Sky sun"
SKY_STRENGTH = 0.25
SUN_ENERGY = 3.0
SUN_ELEVATION_DEG, SUN_AZIMUTH_DEG = 40.0, 200.0   # azimuth clockwise from north; +y is true north

_KIND_OF_MATERIAL = {materials.material_name(k): k for k in materials.BUILDING_MATERIALS}


def roots(scene):
    return [c for c in scene.collection.children_recursive if c.get("ctx_root")]


def made_buildings(root):
    """The site's own building objects (not the user's duplicates)."""
    return [ob for ob in site_use.made_objects(root, BUILDING_KINDS) if ob.type == "MESH"]


def _massing(ob):
    """The mesh the fetcher's prisms describe: the flat one when the building keeps roof shapes."""
    me = ob.get(site_use.FLAT_KEY)
    return ob.data if me is None else me


def mesh_solids(ob):
    """A building's solids as the fetcher reads them, in world coordinates: one per connected part of its
    flat mesh, with its underside's outline as rings (outline counter-clockwise, courtyards clockwise) and
    its lowest and highest points as z0 and z1. Parts without an underside are left out."""
    me = _massing(ob)
    co = [ob.matrix_world @ v.co for v in me.vertices]
    parent = list(range(len(co)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for poly in me.polygons:
        first = find(poly.vertices[0])
        for v in poly.vertices[1:]:
            other = find(v)
            if other != first:
                parent[other] = first
    to_world = ob.matrix_world.to_3x3().inverted_safe().transposed()
    undersides = {}   # part -> directed edges of its downward faces
    for poly in me.polygons:
        normal = to_world @ poly.normal
        if normal.length > 0 and normal.normalized().z < BOTTOM_NORMAL_Z:
            vs = poly.vertices
            undersides.setdefault(find(vs[0]), []).extend((vs[i], vs[(i + 1) % len(vs)]) for i in range(len(vs)))
    solids = []
    for part, directed in undersides.items():
        uses = Counter(frozenset(e) for e in directed)
        rings = []
        for loop in _loops([e for e in directed if uses[frozenset(e)] == 1]):
            ring = [[round(co[i].x, 3), round(co[i].y, 3)] for i in loop]
            if len(ring) >= 3 and abs(_area(ring)) > 1e-6:
                rings.append(ring)
        if not rings:
            continue
        rings.sort(key=lambda r: -abs(_area(r)))
        rings = [r if (_area(r) > 0) == (k == 0) else r[::-1] for k, r in enumerate(rings)]
        zs = [p.z for i, p in enumerate(co) if find(i) == part]
        solids.append({"rings": rings, "z0": round(min(zs), 3), "z1": round(max(zs), 3)})
    return solids


def _loops(edges):
    """Closed loops of vertex indices from directed boundary edges; open chains are dropped."""
    nxt = {}
    for a, b in edges:
        nxt.setdefault(a, []).append(b)
    loops = []
    while nxt:
        start = v = next(iter(nxt))
        loop = [start]
        while v in nxt:
            w = nxt[v].pop()
            if not nxt[v]:
                del nxt[v]
            if w == start:
                loops.append(loop)
                break
            loop.append(w)
            v = w
    return loops


def _area(ring):
    return 0.5 * sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))


def make_request(root, settings, cache_dir, *, selected=(), now=None):
    """The look request for a context collection: its buildings as they are now, with detail for the
    selected ones when Detail for selected is on."""
    chosen = {ob.name for ob in selected} if settings.look_detail else set()
    buildings = []
    for ob in made_buildings(root):
        solids = mesh_solids(ob)
        if solids:
            buildings.append({"id": ob["ctx_id"], "detail": ob.name in chosen, "solids": solids})
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    return ls.build_request(
        centre={"lat": root["lat"], "lon": root["lon"]}, radius_m=root["radius_m"],
        ground_at_centre_m=root.get("ground_at_centre_m"), buildings=buildings, cache_dir=cache_dir,
        out_dir=os.path.join(cache_dir, "runs", "look-" + stamp), budget_photos=settings.look_budget,
        not_before_year=settings.look_not_before or None)


def apply(scene, root, answer, settings=None):
    """Dress a context collection's buildings from a look.json answer and store it there; returns the
    summary. An answer that can't be applied raises, and is not stored for a rebuild to carry over."""
    _dress(root, answer)
    root[LOOK_PROP] = json.dumps(answer, ensure_ascii=False, separators=(",", ":"))
    if settings is not None:
        materials.set_street_look(look=settings.show_look, brightness=settings.look_brightness)
        set_show_detail(scene, settings.show_detail)
    return root[SUMMARY_PROP]


def reapply(scene, root):
    """Dress a context collection again from its stored look, e.g. after a rebuild; a building whose stored
    detail walls no longer lie on it gets no detail. A stored look that can't be read, validated or applied
    is dropped, and the buildings keep the plain look; returns True when it dropped the look, so the caller
    can say so."""
    try:
        answer = json.loads(root.get(LOOK_PROP, ""))
        usable = answer is not None and not ls.validate_answer(answer)
        if usable:
            _drop_moved_detail(root, answer["buildings"])
            _dress(root, answer)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError):   # a look damaged or edited by hand
        usable = False
    if not usable:
        for key in (LOOK_PROP, SUMMARY_PROP, CREDITS_PROP):
            root.pop(key, None)
        _undress(root)   # a look that failed part-way may already have dressed buildings and made detail
        return True
    settings = getattr(scene, "ghosttown", None)
    if settings is not None:
        materials.set_street_look(look=settings.show_look, brightness=settings.look_brightness)
        set_show_detail(scene, settings.show_detail)
    return False


def _drop_moved_detail(root, entries):
    """Forget a building's stored detail walls when they no longer lie on it (a site fetched again around a
    nudged centre, a changed footprint), so its bands don't float off the facade: each wall's ends must be
    within DETAIL_FIT_M of one of its footprint rings, any tier. The shader look stays, as its heights are
    from the building's lowest point. The stored look keeps the walls, so each rebuild checks again."""
    for ob in made_buildings(root):
        entry = entries.get(ob["ctx_id"])
        if entry and entry.get("detail_walls"):
            edges = [(r[i - 1], r[i]) for s in mesh_solids(ob) for r in s["rings"] for i in range(len(r))]
            if not all(any(_to_segment(p, a, b) <= DETAIL_FIT_M for a, b in edges)
                       for w in entry["detail_walls"] for p in (w["a"], w["b"])):
                del entry["detail_walls"]


def _to_segment(p, a, b):
    """Distance in plan from point p to the segment a-b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / max(dx * dx + dy * dy, 1e-12)))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _dress(root, answer):
    """Values, materials, credits, detail and the summary for the site's buildings."""
    entries = answer["buildings"]
    dressed = set()
    for ob in made_buildings(root):
        for me in site_use.meshes_of(ob):   # every roof shape shares the building materials
            for mat in me.materials:
                if mat is not None and mat.name in _KIND_OF_MATERIAL:
                    materials.ensure_street_look(mat, _KIND_OF_MATERIAL[mat.name])
        entry = entries.get(ob["ctx_id"])
        _set_props(ob, entry)
        if entry is not None:
            dressed.add(ob["ctx_id"])
    _credit(root, answer["sources"])
    _rebuild_detail(root, entries)
    root[SUMMARY_PROP] = summary(answer, dressed)
    root[CREDITS_PROP] = "\n".join(dict.fromkeys(s["credit"] for s in answer["sources"]))


def _undress(root):
    """Leave a context collection with the plain look: no building shows a look, and there is no detail."""
    for ob in made_buildings(root):
        _set_props(ob, None)
    _rebuild_detail(root, {})


def _base_z(ob):
    return min((ob.matrix_world @ v.co).z for v in _massing(ob).vertices)


def _set_props(ob, entry):
    ob.update_tag()   # custom properties don't tag the object; without this, a building on screen keeps its old look
    if entry is None:
        ob["gt_look_on"] = 0.0
        return
    ob["gt_look_on"] = 1.0
    ob["gt_look_base_z"] = _base_z(ob)
    ob["gt_look_floor_h"] = float(entry["floor_h"])
    ob["gt_look_bay_glass"], ob["gt_look_bay_opaque"] = GLASS_BAY_M, OPAQUE_BAY_M
    ob["gt_look_source"] = entry["source"]
    ob["gt_look_confidence"] = float(entry.get("confidence", 0.0))
    zones = entry["zones"][:materials.MAX_ZONES]
    for n in range(1, materials.MAX_ZONES + 1):
        z = zones[n - 1] if n <= len(zones) else None
        ob[f"gt_look_z{n}_top"] = TOP if z is None or z["h1"] is None else float(z["h1"])
        ob[f"gt_look_z{n}_kind"] = 0.0 if z is None else float(materials.KIND_CODES[z["kind"]])
        ob[f"gt_look_z{n}_colour"] = [0.0, 0.0, 0.0] if z is None else [float(c) for c in z["colour"]]


def _credit(root, sources):
    """Add the look's credits to the collection's and the origin's (exporters keep the origin's)."""
    extra = [s["credit"] for s in sources]
    for block in [root, *(ob for ob in root.objects if ob.get("ctx_id") == "origin")]:
        lines = [line for line in str(block.get("credits", "")).splitlines() if line]
        block["credits"] = "\n".join(dict.fromkeys(lines + extra))


def _rebuild_detail(root, entries):
    """Replace the collection's detail meshes with ones made from the look entries."""
    made = json.loads(root.get("ctx_objects", "[]"))
    coll = next((c for c in root.children if c.get("ctx_group") == DETAIL_GROUP), None)
    if coll is not None:
        doomed = [ob for ob in coll.objects if ob.name in made and ob.get("ctx_kind") == DETAIL_KIND]
        gone = {ob.name for ob in doomed}
        made = [name for name in made if name not in gone]
        bpy.data.batch_remove(doomed + [ob.data for ob in doomed if ob.data is not None and ob.data.users == 1])
    new = []
    for ob in made_buildings(root):
        entry = entries.get(ob["ctx_id"])
        if entry and entry.get("detail_walls"):
            verts, faces = look_detail.boxes(entry, _base_z(ob))
            if faces:
                new.append(_detail_object(ob, verts, faces))
    if new and coll is None:
        coll = bpy.data.collections.new(f"{DETAIL_GROUP} · {root.get('ctx_label', root.name)}")
        coll["ctx_group"] = DETAIL_GROUP
        root.children.link(coll)
    for det in new:
        coll.objects.link(det)
        made.append(det.name)
    if coll is not None and not new and not coll.objects and not coll.children:
        bpy.data.collections.remove(coll)
    root["ctx_objects"] = json.dumps(made)


def _detail_object(building, verts, faces):
    name = f"Detail · {building.name}"
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.materials.append(materials.get_material(DETAIL_KIND))
    me.validate(clean_customdata=False)
    me.update()
    det = bpy.data.objects.new(name, me)
    det.color = materials.COLOURS[DETAIL_KIND] + (1.0,)
    det["ctx_id"] = f"detail:{building['ctx_id']}"
    det["ctx_kind"] = DETAIL_KIND
    return det


def set_show_detail(scene, on):
    """Show or hide the scene's detail collections, in viewports and in renders."""
    for root in roots(scene):
        for coll in root.children:
            if coll.get("ctx_group") == DETAIL_GROUP:
                coll.hide_viewport = coll.hide_render = not on


def summary(answer, present=None):
    """One line for the panel, e.g. 'Look from photos: 41 buildings · guessed: 23 · 128 photos (2014–2025)'.
    Counts only the buildings in `present` when given."""
    entries = [e for bid, e in answer["buildings"].items() if present is None or bid in present]
    n = sum(1 for e in entries if e["source"] == "photos")
    text = f"Look from photos: {n} building{'' if n == 1 else 's'} · guessed: {len(entries) - n}"
    k = answer.get("photos_used") or 0
    if k:
        text += f" · {k} photo{'' if k == 1 else 's'}"
        years = answer.get("years")
        if years:
            text += f" ({years[0]})" if years[0] == years[1] else f" ({years[0]}–{years[1]})"
    return text


def can_add_sky(scene):
    """True when the scene has no world or still has Blender's default one (a plain background)."""
    world = scene.world
    if world is None:
        return True
    if world.name != "World" or world.node_tree is None:
        return False
    return {n.bl_idname for n in world.node_tree.nodes} <= {"ShaderNodeBackground", "ShaderNodeOutputWorld"}


def add_sky(scene):
    """A sky texture world and a matching sun lamp, so glass has something to reflect."""
    world = bpy.data.worlds.get(SKY_WORLD) or bpy.data.worlds.new(SKY_WORLD)
    tree = world.node_tree
    tree.nodes.clear()
    out = tree.nodes.new("ShaderNodeOutputWorld")
    bg = tree.nodes.new("ShaderNodeBackground")
    sky = tree.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_disc = False
    sky.sun_elevation = math.radians(SUN_ELEVATION_DEG)
    sky.sun_rotation = math.radians(SUN_AZIMUTH_DEG)   # measured clockwise from +y, like a compass
    bg.inputs["Strength"].default_value = SKY_STRENGTH
    tree.links.new(sky.outputs["Color"], bg.inputs["Color"])
    tree.links.new(bg.outputs["Background"], out.inputs["Surface"])
    scene.world = world
    sun = bpy.data.objects.get(SKY_SUN)
    if sun is None:
        sun = bpy.data.objects.new(SKY_SUN, bpy.data.lights.new(SKY_SUN, "SUN"))
    sun.data.energy = SUN_ENERGY
    sun.rotation_euler = (math.radians(90.0 - SUN_ELEVATION_DEG), 0.0, math.radians(180.0 - SUN_AZIMUTH_DEG))
    if sun.name not in scene.collection.objects:
        scene.collection.objects.link(sun)
    return world
