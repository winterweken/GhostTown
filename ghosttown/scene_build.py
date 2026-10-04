"""context.json -> Blender collections and objects. Never uses bpy.ops.

Buildings get one object each; ground kinds, trees and parcels are merged per kind.
The root collection remembers which collections and objects this build made (by tag and by
name), so a re-run removes exactly those and keeps everything the user added, duplicated or
linked elsewhere.
"""
import json
import os

import bpy

from . import geometry, georef, materials, site_photo
from .ghosttown_fetch import BUILDING_KINDS
from .ghosttown_fetch import context as ctx

ROOT_PREFIX = "Context · "
GROUP_ORDER = ("Buildings", "Ground", "Trees", "Parcels")
MAX_LABEL = 60


def _group(kind):
    if kind in BUILDING_KINDS:
        return "Buildings"
    if kind == "tree":
        return "Trees"
    if kind in ("parcel", "parcel_on_site"):
        return "Parcels"
    return "Ground"


def site_label(doc):
    label = (doc.get("address") or "").strip()
    if not label:
        label = f'{doc["centre"]["lat"]:.5f}, {doc["centre"]["lon"]:.5f}'
    return label[:MAX_LABEL]


def find_root(scene, label):
    """This scene's context collection for a site label, or None. Other scenes are never touched."""
    for coll in scene.collection.children_recursive:
        if coll.get("ctx_root") and coll.get("ctx_label") == label:
            return coll
    return None


def build(scene, doc, folder=None):
    label = site_label(doc)
    old = find_root(scene, label)
    if old is not None:
        remove(old, scene)
    georef.set_scene_units(scene)
    root = bpy.data.collections.new(ROOT_PREFIX + label)
    root["ctx_root"] = True
    root["ctx_label"] = label
    scene.collection.children.link(root)

    elements = list(ctx.iter_elements(doc))
    needed = {_group(el["kind"]) for el in elements}
    groups = {}
    for name in GROUP_ORDER:
        if name in needed:
            groups[name] = bpy.data.collections.new(f"{name} · {label}")
            groups[name]["ctx_group"] = name
            root.children.link(groups[name])

    made = []
    merged = {}  # (shape, kind) -> [verts, items]
    for el in elements:
        if el["solids"]:
            ob = _building_object(el)
            if ob is not None:
                groups["Buildings"].objects.link(ob)
                made.append(ob.name)
        for mesh in el["meshes"]:
            _append(merged.setdefault(("mesh", mesh["kind"]), [[], []]), mesh["verts"], mesh["faces"])
        for line in el["lines"]:
            acc = merged.setdefault(("line", line["kind"]), [[], []])
            start = len(acc[0])
            acc[0].extend(tuple(p) for p in line["pts"])
            acc[1].extend((start + i, start + i + 1) for i in range(len(line["pts"]) - 1))

    for (shape, kind), (verts, items) in merged.items():
        name = f"{materials.LABELS[kind]} · {label}"
        if shape == "mesh":
            ob = _mesh_object(name, verts, faces=items, kinds=[kind])
        else:
            ob = _mesh_object(name, verts, edges=items, kinds=[kind])
        ob["ctx_id"] = f"merged:{kind}"
        ob["ctx_kind"] = kind
        groups[_group(kind)].objects.link(ob)
        made.append(ob.name)

    origin = bpy.data.objects.new(f"Context origin · {label}", None)
    origin.empty_display_type = "ARROWS"
    origin.empty_display_size = 10.0
    origin["ctx_id"] = "origin"
    values = georef.props(doc)
    georef.apply(root, values)
    georef.apply(origin, values)
    root.objects.link(origin)
    made.append(origin.name)
    root["ctx_objects"] = json.dumps(made)
    photo = doc.get("photo")
    if photo and folder:
        path = os.path.join(folder, photo["file"])
        if os.path.isfile(path):
            site_photo.attach(root, origin, label, path, photo)
    return root


def remove(root, scene):
    """Delete a context collection and what Ghost Town made in it. The user's objects, duplicates and
    sub-collections are kept; anything that would be left with no parent moves to the scene collection."""
    photo_assets = (root.get("ctx_photo_material"), root.get("ctx_photo_image"))
    made = set(json.loads(root.get("ctx_objects", "[]")))
    ours = [root] + [c for c in root.children_recursive if c.get("ctx_group")]
    ours_names = {c.name for c in ours}

    doomed, meshes, kept_objects, kept_collections = [], [], [], []
    for coll in ours:
        for ob in coll.objects:
            if ob.name in made and "ctx_id" in ob:
                if ob not in doomed:
                    doomed.append(ob)
                    if ob.data is not None and ob.data.users == 1:
                        meshes.append(ob.data)
            elif ob not in kept_objects:
                kept_objects.append(ob)
        for child in coll.children:
            if child.name not in ours_names and child not in kept_collections:
                kept_collections.append(child)

    for ob in kept_objects:
        if not any(c.name not in ours_names for c in ob.users_collection):
            scene.collection.objects.link(ob)
    for child in kept_collections:
        parents = [c for c in bpy.data.collections if c.name not in ours_names and child.name in c.children]
        in_a_scene = any(child.name in s.collection.children for s in bpy.data.scenes)
        if not parents and not in_a_scene:
            scene.collection.children.link(child)

    bpy.data.batch_remove(doomed + meshes + ours)
    site_photo.forget(*photo_assets)


def _append(acc, verts, faces):
    start = len(acc[0])
    acc[0].extend(tuple(v) for v in verts)
    acc[1].extend(tuple(i + start for i in f) for f in faces)


def _closed_prism(rings, z0, z1):
    """A closed prism, or None. Falls back to the outer ring alone if the courtyards break closure."""
    verts, faces = geometry.prism(rings, z0, z1)
    if geometry.is_closed(faces):
        return verts, faces, False
    if len(rings) > 1:
        verts, faces = geometry.prism(rings[:1], z0, z1)
        if geometry.is_closed(faces):
            return verts, faces, True
    return None


def _building_object(el):
    verts, faces, material_index, kinds = [], [], [], []
    repaired = False
    for s in el["solids"]:
        rings = geometry.clean_rings(s["rings"])
        if not rings:
            continue
        prism = _closed_prism(rings, s["z0"], s["z1"])
        if prism is None:
            repaired = True
            continue
        v, f, dropped_holes = prism
        repaired = repaired or dropped_holes
        if s["kind"] not in kinds:
            kinds.append(s["kind"])
        start = len(verts)
        verts += v
        faces += [tuple(i + start for i in face) for face in f]
        material_index += [kinds.index(s["kind"])] * len(f)
    if not faces:
        return None
    ob = _mesh_object(el["name"] or el["id"], verts, faces=faces, kinds=kinds, material_index=material_index)
    ob["ctx_id"] = el["id"]
    ob["ctx_kind"] = el["kind"]
    ob["ctx_source"] = el["id"].split(":", 1)[0]
    ob["ctx_height_source"] = ", ".join(sorted({s["height_source"] for s in el["solids"]}))
    ob["ctx_height_m"] = round(max(s["z1"] - s["z0"] for s in el["solids"]), 3)
    if repaired:
        ob["ctx_repaired"] = True  # a courtyard or a broken solid was left out to keep the mesh closed
    return ob


def _mesh_object(name, verts, *, faces=(), edges=(), kinds, material_index=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, list(edges), list(faces))
    for kind in kinds:
        me.materials.append(materials.get_material(kind))
    if material_index:
        me.polygons.foreach_set("material_index", material_index)
    me.validate(clean_customdata=False)
    me.update()
    ob = bpy.data.objects.new(name, me)
    ob.color = materials.COLOURS[kinds[0]] + (1.0,)
    return ob
