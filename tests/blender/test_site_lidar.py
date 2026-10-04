import os
import tempfile

import bpy

from ghosttown import scene_build, site_use
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
