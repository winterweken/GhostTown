"""LiDAR and fitted roofs in Blender: more meshes for each building, built from the fetcher's
lidar_roofs.npz and fitted_roofs.npz.

The building object keeps its flat mesh and these in ID properties (which also keeps them in the file
when they aren't shown), and shows one; site_use switches between them."""
import zipfile
import zlib

import bpy
import numpy as np

from . import materials, site_use
from .ghosttown_fetch import BUILDING_KINDS

SUFFIX = " · LiDAR"
FITTED_SUFFIX = " · Fitted"


def _mesh(name, verts, faces, face_kind, kinds, flat=False):
    """A triangle mesh built with foreach_set (LiDAR roofs run to millions of triangles), its materials
    the building kinds in the order its faces first use them, as the flat mesh lists them; flat-shaded
    when `flat`, like the flat meshes (fitted roofs are solids), else smooth. Nothing is left behind when
    it fails."""
    me = bpy.data.meshes.new(name)
    try:
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
        if flat:
            me.shade_flat()
        me.update(calc_edges=True)
        me.validate(clean_customdata=False)
    except Exception:
        bpy.data.meshes.remove(me)
        raise
    return me


ARRAYS = ("verts", "faces", "face_kind", "interior", "building_ids", "vert_start", "face_start", "kinds")


def _check(a):
    """Raise ValueError unless the arrays are laid out as the fetcher writes them, so nothing malformed
    reaches the mesh building."""
    verts, faces, face_kind, interior = a["verts"], a["faces"], a["face_kind"], a["interior"]
    ids, kinds = a["building_ids"], a["kinds"]
    if verts.ndim != 2 or verts.shape[1] != 3 or verts.dtype.kind not in "fiu":
        raise ValueError("the LiDAR roofs file's vertices aren't x, y, z numbers")
    if faces.ndim != 2 or faces.shape[1] != 3 or faces.dtype.kind not in "iu":
        raise ValueError("the LiDAR roofs file's faces aren't triangles of whole numbers")
    if ids.ndim != 1 or kinds.ndim != 1 or ids.dtype.kind != "U" or kinds.dtype.kind != "U":
        raise ValueError("the LiDAR roofs file's building ids and kinds aren't lists of names")
    if any(str(k) not in BUILDING_KINDS for k in kinds):
        raise ValueError("the LiDAR roofs file has a kind that isn't a building")
    if face_kind.shape != (len(faces),) or face_kind.dtype.kind not in "iu":
        raise ValueError("the LiDAR roofs file doesn't give each triangle a kind")
    if len(face_kind) and (face_kind.min() < 0 or face_kind.max() >= len(kinds)):
        raise ValueError("the LiDAR roofs file has a triangle of an unknown kind")
    if interior.shape != (len(verts),):
        raise ValueError("the LiDAR roofs file doesn't flag each vertex as roof interior or not")
    for starts, total in ((a["vert_start"], len(verts)), (a["face_start"], len(faces))):
        if (starts.shape != (len(ids) + 1,) or starts.dtype.kind not in "iu" or starts[0] != 0
                or starts[-1] != total or (np.diff(starts) < 0).any()):
            raise ValueError("the LiDAR roofs file's slices don't match its buildings")


def _read(path):
    """The file's arrays, once they are known to be well formed. Raises OSError when it can't be opened
    and ValueError when it is damaged or isn't laid out as the fetcher writes it."""
    try:
        with np.load(path) as data:
            missing = [key for key in ARRAYS if key not in data.files]
            if missing:
                raise ValueError(f"the LiDAR roofs file has no '{missing[0]}'")
            arrays = {key: data[key] for key in ARRAYS}
    except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError) as e:
        raise ValueError(f"the LiDAR roofs file is damaged ({e})") from None
    _check(arrays)
    return arrays


def _attach(root, data, key, suffix, interior=None, flat=False):
    """Give each building listed in `data` a mesh kept under `key` (its flat mesh under FLAT_KEY, unless it
    has one there already) and show it; with `interior`, the roof interior group too, and with `flat`,
    flat shading. Returns how many buildings got one. When a mesh fails, removes every mesh it made, puts
    back what each building showed, and raises."""
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
                continue  # a damaged slice: this building goes without this roof shape
            me = _mesh(ob.name + suffix, verts, faces, data["face_kind"][fs[b]:fs[b + 1]], kinds, flat)
            made.append((ob, ob.data, me, site_use.FLAT_KEY in ob))
            if site_use.FLAT_KEY not in ob:
                ob[site_use.FLAT_KEY] = ob.data
            ob[key] = me
            ob.data = me
            if interior is not None:
                group = ob.vertex_groups.new(name=site_use.ROOF_GROUP)
                group.add(np.flatnonzero(interior[vs[b]:vs[b + 1]]).tolist(), 1.0, "REPLACE")
    except Exception:
        for ob, shown, me, had_flat in made:
            ob.data = shown
            del ob[key]
            if not had_flat:
                del ob[site_use.FLAT_KEY]
            bpy.data.meshes.remove(me)
        raise
    return len(made)


def _settle(root, block, use):
    root["lidar_cell_m"] = float(block["cell_m"])
    root["lidar_year"] = int(block.get("year") or 0)
    root["use_roof_shapes"] = use
    root["roof_detail"] = 1.0


def attach(root, path, block):
    """Give every building in the site its LiDAR mesh and show it. Raises OSError or ValueError when the
    file can't be read, leaving the site as it was."""
    data = _read(path)
    if not _attach(root, data, site_use.LIDAR_KEY, SUFFIX, interior=data["interior"]):
        return False
    _settle(root, block, "lidar")
    return True


def attach_fitted(root, path, block):
    """Give every building in the site its fitted mesh and show it: fitted roofs are what a build shows.
    Raises OSError or ValueError when the file can't be read, leaving the site as it was."""
    data = _read(path)
    if not _attach(root, data, site_use.FITTED_KEY, FITTED_SUFFIX, flat=True):
        return False
    _settle(root, block, "fitted")
    return True
