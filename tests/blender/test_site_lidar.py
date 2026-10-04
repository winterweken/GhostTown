import os
import tempfile
import zlib

import bpy
import numpy as np

from ghosttown import materials, scene_build, site_lidar, site_use
from helpers import closed_and_outward, lidar_doc, load_fixture, mesh_arrays


def lidar_site(**kw):
    folder = tempfile.mkdtemp()
    return scene_build.build(bpy.context.scene, lidar_doc(folder, **kw), folder=folder), folder


def buildings(root):
    return sorted((ob for ob in root.all_objects if str(ob.get("ctx_kind", "")).startswith("building")),
                  key=lambda ob: ob["ctx_id"])


def test_each_building_shows_its_lidar_mesh_and_keeps_its_flat_one():
    root, _ = lidar_site()
    tower, shed = buildings(root)
    for ob in (tower, shed):
        flat, lidar = ob[site_use.FLAT_KEY], ob[site_use.LIDAR_KEY]
        assert ob.data == lidar and lidar.name == ob.name + " · LiDAR" and flat != lidar
        assert (len(lidar.vertices), len(lidar.polygons)) == (9, 14) and closed_and_outward(*mesh_arrays(ob))
    assert [m.name for m in tower.data.materials] == ["Context - Building"]
    assert [m.name for m in shed.data.materials] == ["Context - Building (height guessed)"]
    assert root["use_roof_shapes"] == "lidar" and root["roof_detail"] == 1.0 and root["lidar_cell_m"] == 0.5
    assert site_use.has_lidar(root)


def test_the_roof_interior_group_holds_only_roof_points_off_the_outline():
    root, _ = lidar_site()
    tower = buildings(root)[0]
    group = tower.vertex_groups[site_use.ROOF_GROUP]
    assert [v.index for v in tower.data.vertices if any(g.group == group.index for g in v.groups)] == [8]
    tower.data = tower[site_use.FLAT_KEY]
    assert site_use.ROOF_GROUP not in tower.vertex_groups  # the group belongs to the LiDAR mesh


def test_both_meshes_survive_saving_and_reopening():
    root, folder = lidar_site()
    name = buildings(root)[0].name
    path = os.path.join(folder, "site.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    tower = bpy.data.objects[name]
    flat, lidar = tower[site_use.FLAT_KEY], tower[site_use.LIDAR_KEY]
    assert tower.data == lidar and flat.users == 1 and len(flat.polygons) > 0
    assert site_use.ROOF_GROUP in tower.vertex_groups


def test_with_a_photo_both_meshes_get_the_photo_uv_map():
    root, _ = lidar_site(photo=True)
    for ob in buildings(root):
        assert all("Site photo" in me.uv_layers for me in (ob[site_use.FLAT_KEY], ob[site_use.LIDAR_KEY]))


def test_a_rebuild_leaves_no_mesh_behind():
    folder = tempfile.mkdtemp()
    doc = lidar_doc(folder)
    scene_build.build(bpy.context.scene, doc, folder=folder)
    count = len(bpy.data.meshes)
    scene_build.build(bpy.context.scene, doc, folder=folder)
    assert len(bpy.data.meshes) == count and all(me.users for me in bpy.data.meshes)


def test_a_kept_duplicate_keeps_the_meshes_it_uses():
    root, _ = lidar_site()
    tower = buildings(root)[0]
    copy = tower.copy()
    bpy.context.scene.collection.objects.link(copy)
    shown, flat = tower.data, tower[site_use.FLAT_KEY]
    scene_build.remove(root, bpy.context.scene)
    assert copy.data == shown and shown.name in bpy.data.meshes and flat.name in bpy.data.meshes


def test_a_damaged_roofs_file_builds_flat_roofs():
    for damage in (b"not a zip", None):
        folder = tempfile.mkdtemp()
        doc = lidar_doc(folder)
        path = os.path.join(folder, "lidar_roofs.npz")
        with open(path, "rb") as f:
            whole = f.read()
        with open(path, "wb") as f:
            f.write(damage if damage is not None else whole[: len(whole) // 2])
        root = scene_build.build(bpy.context.scene, doc, folder=folder)
        assert not site_use.has_lidar(root) and "use_roof_shapes" not in root
        assert all(site_use.FLAT_KEY not in ob for ob in buildings(root))
        scene_build.remove(root, bpy.context.scene)


def test_an_older_context_without_lidar_builds_unchanged():
    root = scene_build.build(bpy.context.scene, load_fixture("mini_context.json"))
    assert all(site_use.LIDAR_KEY not in ob for ob in buildings(root)) and "use_roof_shapes" not in root


def rewrite_lidar(folder, change):
    """lidar_roofs.npz in `folder` saved again after `change(arrays)` has altered its arrays."""
    path = os.path.join(folder, "lidar_roofs.npz")
    with np.load(path) as data:
        arrays = {key: data[key] for key in data.files}
    change(arrays)
    np.savez_compressed(path, **arrays)


def break_compressed_data(folder):
    """Flip four bytes at the first place that makes the compressed data undecodable, so reading an
    array fails with zlib's own error rather than a bad-zip one."""
    path = os.path.join(folder, "lidar_roofs.npz")
    with open(path, "rb") as f:
        whole = f.read()
    for at in range(0, len(whole) - 4, 7):
        damaged = bytearray(whole)
        for i in range(at, at + 4):
            damaged[i] ^= 0xFF
        with open(path, "wb") as f:
            f.write(damaged)
        try:
            with np.load(path) as data:
                for key in data.files:
                    data[key]
        except zlib.error:
            return
        except Exception:
            pass
    raise AssertionError("no byte flip made the compressed data undecodable")


def assert_flat_roofs(root, label):
    assert not site_use.has_lidar(root), label
    assert not any(key in root for key in ("use_roof_shapes", "roof_detail", "lidar_cell_m", "lidar_year")), label
    for ob in buildings(root):
        assert site_use.FLAT_KEY not in ob and site_use.LIDAR_KEY not in ob, label
        assert not ob.data.name.endswith(site_lidar.SUFFIX) and site_use.ROOF_GROUP not in ob.vertex_groups, label
    assert not [me for me in bpy.data.meshes if me.name.endswith(site_lidar.SUFFIX)], label


def malformed_roofs_files():
    """Each way a roofs file can be malformed, as a function that damages the file in a folder."""

    def altered(**changes):
        return lambda arrays: arrays.update({key: f(arrays) for key, f in changes.items()})

    return {
        "compressed data that zlib can't read": break_compressed_data,
        "face kinds past the kinds": lambda f: rewrite_lidar(f, altered(face_kind=lambda a: a["face_kind"] + 5)),
        "fewer face kinds than faces": lambda f: rewrite_lidar(f, altered(face_kind=lambda a: a["face_kind"][:-3])),
        "float slice starts": lambda f: rewrite_lidar(f, altered(vert_start=lambda a: a["vert_start"].astype(float),
                                                                  face_start=lambda a: a["face_start"].astype(float))),
        "vertices that aren't x y z": lambda f: rewrite_lidar(f, altered(verts=lambda a: a["verts"][:, :2])),
        "float faces": lambda f: rewrite_lidar(f, altered(faces=lambda a: a["faces"].astype(np.float32))),
        "fewer interior flags than vertices": lambda f: rewrite_lidar(f, altered(interior=lambda a: a["interior"][:-1])),
        "a kind that isn't a building": lambda f: rewrite_lidar(
            f, altered(kinds=lambda a: np.array(["building", "tree", "building_guessed"]))),
        "starts that don't begin at zero": lambda f: rewrite_lidar(
            f, altered(vert_start=lambda a: a["vert_start"] + 1, face_start=lambda a: a["face_start"] + 1)),
        "starts that go backwards": lambda f: rewrite_lidar(
            f, altered(vert_start=lambda a: np.array([0, 20, 18], dtype=np.int64))),
        "starts that stop short of the faces": lambda f: rewrite_lidar(
            f, altered(face_start=lambda a: a["face_start"] - np.array([0, 0, 1]))),
        "one start too few": lambda f: rewrite_lidar(f, altered(vert_start=lambda a: a["vert_start"][:-1])),
        "an array missing": lambda f: rewrite_lidar(f, lambda a: a.pop("interior")),
    }


def test_a_roofs_file_that_is_not_well_formed_builds_flat_roofs():
    for label, damage in malformed_roofs_files().items():
        folder = tempfile.mkdtemp()
        doc = lidar_doc(folder)
        damage(folder)
        root = scene_build.build(bpy.context.scene, doc, folder=folder)
        assert_flat_roofs(root, label)
        scene_build.remove(root, bpy.context.scene)


def test_a_slice_that_indexes_outside_its_own_vertices_keeps_only_that_building_flat():
    folder = tempfile.mkdtemp()
    doc = lidar_doc(folder)

    def point_past_the_vertices(arrays):
        faces = arrays["faces"].copy()
        faces[14:] += 9  # the shed's faces (the second slice) reach the tower's vertices and beyond
        arrays["faces"] = faces

    rewrite_lidar(folder, point_past_the_vertices)
    root = scene_build.build(bpy.context.scene, doc, folder=folder)
    tower, shed = buildings(root)
    assert site_use.LIDAR_KEY in tower and site_use.LIDAR_KEY not in shed and site_use.has_lidar(root)


def test_a_mesh_that_fails_half_way_is_removed_and_the_site_keeps_its_flat_roofs():
    real = materials.get_material

    def fails_for_the_shed(kind):
        # The flat meshes are built before any LiDAR mesh exists; the shed's comes after the tower's.
        if kind == "building_guessed" and any(me.name.endswith(site_lidar.SUFFIX) for me in bpy.data.meshes):
            raise ValueError("no material")
        return real(kind)

    folder = tempfile.mkdtemp()
    doc = lidar_doc(folder)
    materials.get_material = fails_for_the_shed
    try:
        root = scene_build.build(bpy.context.scene, doc, folder=folder)
    finally:
        materials.get_material = real
    assert_flat_roofs(root, "the shed's mesh failed after it was made")
    assert all(me.users for me in bpy.data.meshes)
