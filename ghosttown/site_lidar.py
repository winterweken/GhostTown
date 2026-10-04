"""LiDAR roofs in Blender: a second mesh for each building, built from the fetcher's lidar_roofs.npz.

The building object keeps both meshes in ID properties (which also keeps them in the file when they
aren't shown), and shows one; site_use switches between them."""
import zipfile

import bpy
import numpy as np

from . import materials, site_use
from .ghosttown_fetch import BUILDING_KINDS

SUFFIX = " · LiDAR"


def _mesh(name, verts, faces, face_kind, kinds):
    """A triangle mesh built with foreach_set (LiDAR roofs run to millions of triangles), its materials
    the building kinds in the order its faces first use them, as the flat mesh lists them."""
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", np.ascontiguousarray(verts, dtype=np.float32).ravel())
    me.loops.add(faces.size)
    me.loops.foreach_set("vertex_index", np.ascontiguousarray(faces, dtype=np.int32).ravel())
    me.polygons.add(len(faces))
    me.polygons.foreach_set("loop_start", np.arange(0, faces.size, 3, dtype=np.int32))
    order = list(dict.fromkeys(face_kind.tolist()))
    for k in order:
        me.materials.append(materials.get_material(kinds[k]))
    slot = np.zeros(len(kinds), dtype=np.int32)
    slot[order] = np.arange(len(order), dtype=np.int32)
    me.polygons.foreach_set("material_index", slot[face_kind])
    me.update(calc_edges=True)
    me.validate(clean_customdata=False)
    return me


def _read(path):
    try:
        with np.load(path) as data:
            arrays = {key: data[key] for key in ("verts", "faces", "face_kind", "interior", "building_ids",
                                                 "vert_start", "face_start", "kinds")}
    except (zipfile.BadZipFile, EOFError) as e:
        raise ValueError(f"the LiDAR roofs file is damaged ({e})") from None
    starts = (arrays["vert_start"], arrays["face_start"])
    if any(len(s) != len(arrays["building_ids"]) + 1 for s in starts):
        raise ValueError("the LiDAR roofs file's slices don't match its buildings")
    return arrays


def attach(root, path, block):
    """Give every building in the site its LiDAR mesh and show it. Raises OSError, ValueError or KeyError
    when the file can't be read, leaving the site as it was."""
    data = _read(path)
    kinds = [str(k) for k in data["kinds"]]
    buildings = {ob["ctx_id"]: ob for ob in site_use.made_objects(root, BUILDING_KINDS)}
    vs, fs = data["vert_start"], data["face_start"]
    made = []
    try:
        for b, building_id in enumerate(str(i) for i in data["building_ids"]):
            ob = buildings.get(building_id)
            if ob is None:
                continue
            verts = data["verts"][vs[b]:vs[b + 1]]
            faces = data["faces"][fs[b]:fs[b + 1]]
            if len(faces) == 0 or faces.min() < 0 or faces.max() >= len(verts):
                continue  # a damaged slice: this building keeps its flat roof only
            me = _mesh(ob.name + SUFFIX, verts, faces, data["face_kind"][fs[b]:fs[b + 1]], kinds)
            made.append((ob, ob.data, me))
            ob[site_use.FLAT_KEY] = ob.data
            ob[site_use.LIDAR_KEY] = me
            ob.data = me
            group = ob.vertex_groups.new(name=site_use.ROOF_GROUP)
            group.add(np.flatnonzero(data["interior"][vs[b]:vs[b + 1]]).tolist(), 1.0, "REPLACE")
    except Exception:
        for ob, flat, me in made:
            ob.data = flat
            for key in (site_use.FLAT_KEY, site_use.LIDAR_KEY):
                del ob[key]
            bpy.data.meshes.remove(me)
        raise
    if not made:
        return False
    root["lidar_cell_m"] = float(block["cell_m"])
    root["lidar_year"] = int(block.get("year") or 0)
    root["use_roof_shapes"] = "lidar"
    root["roof_detail"] = 1.0
    return True
