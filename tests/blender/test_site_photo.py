import os
import shutil
import tempfile

import bpy

import ghosttown
from ghosttown import scene_build, site_photo, site_use
from helpers import load_fixture, photo_doc, PHOTO

SITE = "320 Bay St"


def photo_site(address=None):
    folder = tempfile.mkdtemp()
    return scene_build.build(bpy.context.scene, photo_doc(folder, address), folder=folder), folder


def ground(root):
    return [ob for ob in root.all_objects if ob.get("ctx_kind") == "road"]


def buildings(root):
    return sorted((ob for ob in root.all_objects if str(ob.get("ctx_kind", "")).startswith("building")),
                  key=lambda ob: ob["ctx_id"])


def test_the_photo_is_packed_and_shown_on_the_ground():
    root, _ = photo_site()
    image = bpy.data.images[root["ctx_photo_image"]]
    assert image.name == f"Site photo · {SITE}" and image.packed_file is not None
    mat = bpy.data.materials[root["ctx_photo_material"]]
    assert mat.name == f"Site photo · {SITE}"
    tex = next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeTexImage")
    uvmap = next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeUVMap")
    assert tex.image == image and tex.extension == "CLIP" and uvmap.uv_map == "Site photo"
    road, = ground(root)
    slot = road.material_slots[0]
    assert slot.link == "OBJECT" and slot.material == mat and road.data.materials[0].name == "Context - Road"
    assert root["use_ground"] == "photo" and root["use_roofs"] == "plain" and root["roof_photo_max_m"] == 20.0
    assert root["photo_year"] == 2025 and root["photo_width_m"] == 300.0
    assert list(root["photo_px"]) == [128, 128] and list(root["photo_bounds_m"]) == [-150.0, -150.0, 150.0, 150.0]
    origin, = [ob for ob in root.objects if ob.get("ctx_id") == "origin"]
    assert origin["photo_year"] == 2025 and origin["photo_width_m"] == 300.0


def test_ground_and_buildings_get_a_straight_down_uv_map():
    root, _ = photo_site()
    for ob in ground(root) + buildings(root):
        uv = ob.data.uv_layers["Site photo"]
        for loop, data in zip(ob.data.loops, uv.data):
            x, y, _ = ob.data.vertices[loop.vertex_index].co
            assert abs(data.uv[0] - (x + 150) / 300) < 1e-5 and abs(data.uv[1] - (y + 150) / 300) < 1e-5


def test_buildings_record_their_height_for_the_roof_limit():
    root = scene_build.build(bpy.context.scene, load_fixture("mini_context.json"))
    tower, shed = buildings(root)
    assert tower["ctx_height_m"] == 60.3 and shed["ctx_height_m"] == 9.3


def test_without_the_photo_file_the_site_builds_without_a_photo():
    folder = tempfile.mkdtemp()
    doc = photo_doc(folder)
    os.remove(os.path.join(folder, "photo.jpg"))
    root = scene_build.build(bpy.context.scene, doc, folder=folder)
    assert "ctx_photo_image" not in root and not any(i.name.startswith("Site photo") for i in bpy.data.images)
    road, = ground(root)
    assert road.material_slots[0].link == "DATA" and "Site photo" not in road.data.uv_layers


def _assert_built_without_a_photo(root):
    assert "ctx_photo_image" not in root and "ctx_photo_material" not in root and "use_ground" not in root
    assert not bpy.data.images and not any(m.name.startswith("Site photo") for m in bpy.data.materials)
    road, = ground(root)
    assert road.material_slots[0].link == "DATA" and "Site photo" not in road.data.uv_layers


def test_a_damaged_photo_file_builds_the_site_without_a_photo():
    folder = tempfile.mkdtemp()
    doc = photo_doc(folder)
    with open(os.path.join(folder, "photo.jpg"), "wb") as f:
        f.write(bytes(2048))  # Blender loads this as a 0 x 0 image
    _assert_built_without_a_photo(scene_build.build(bpy.context.scene, doc, folder=folder))


def test_an_unreadable_photo_file_builds_the_site_without_a_photo():
    folder = tempfile.mkdtemp()
    doc = photo_doc(folder)
    path = os.path.join(folder, "photo.jpg")
    os.chmod(path, 0)  # Blender raises RuntimeError: Cannot read
    try:
        root = scene_build.build(bpy.context.scene, doc, folder=folder)
    finally:
        os.chmod(path, 0o644)
    _assert_built_without_a_photo(root)


def test_without_a_folder_the_photo_is_skipped():
    root = scene_build.build(bpy.context.scene, photo_doc(tempfile.mkdtemp()))
    assert "ctx_photo_image" not in root


def test_a_rebuild_replaces_the_photo_without_duplicates():
    photo_site()
    photo_site()
    assert [i.name for i in bpy.data.images if i.name.startswith("Site photo")] == [f"Site photo · {SITE}"]
    assert [m.name for m in bpy.data.materials if m.name.startswith("Site photo")] == [f"Site photo · {SITE}"]


def test_a_rebuild_replaces_the_photo_even_when_its_objects_are_gone():
    root, _ = photo_site()
    for ob in ground(root):
        bpy.data.objects.remove(ob)
    photo_site()
    assert [i.name for i in bpy.data.images if i.name.startswith("Site photo")] == [f"Site photo · {SITE}"]
    assert [m.name for m in bpy.data.materials if m.name.startswith("Site photo")] == [f"Site photo · {SITE}"]


def test_a_rebuild_first_returns_the_site_to_plain_so_a_kept_duplicate_is_clean():
    root, _ = photo_site()
    _tower, shed = buildings(root)
    names = [m.name for m in shed.data.materials]
    site_use.apply_roofs(root, "photo", 100.0)
    assert site_use.INDEX_ATTR in shed.data.attributes
    twin = shed.copy()  # an Alt+D linked duplicate: it shares the mesh
    bpy.context.scene.collection.objects.link(twin)
    photo_site()
    assert twin.data.users == 1 and [m.name for m in twin.data.materials] == names
    assert site_use.INDEX_ATTR not in twin.data.attributes
    assert all(p.material_index < len(names) for p in twin.data.polygons)
    assert [i.name for i in bpy.data.images if i.name.startswith("Site photo")] == [f"Site photo · {SITE}"]
    assert [m.name for m in bpy.data.materials if m.name.startswith("Site photo")] == [f"Site photo · {SITE}"]


def test_removing_a_site_removes_its_photo():
    root, _ = photo_site()
    scene_build.remove(root, bpy.context.scene)
    assert not any(i.name.startswith("Site photo") for i in bpy.data.images)
    assert not any(m.name.startswith("Site photo") for m in bpy.data.materials)


def test_the_photo_survives_saving_and_reopening_the_file():
    _, folder = photo_site()
    path = os.path.join(tempfile.mkdtemp(), "site.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    shutil.rmtree(folder)  # the cache can be cleared; the photo is in the .blend
    bpy.ops.wm.open_mainfile(filepath=path)
    image = bpy.data.images[f"Site photo · {SITE}"]
    assert image.packed_file is not None and tuple(image.size) == (128, 128)
    road = next(ob for ob in bpy.data.objects if ob.get("ctx_kind") == "road")
    assert road.material_slots[0].link == "OBJECT" and road.material_slots[0].material.name == f"Site photo · {SITE}"


def test_the_photo_outlives_the_objects_that_showed_it():
    root, folder = photo_site()
    for ob in ground(root):
        bpy.data.objects.remove(ob)  # nothing draws the photo now, and roofs are plain
    site_use.apply_roofs(root, "plain")
    shutil.rmtree(folder)
    path = os.path.join(tempfile.mkdtemp(), "site.blend")
    for _ in range(2):  # a datablock nothing uses is dropped on save, so it takes two rounds to notice
        bpy.ops.wm.save_as_mainfile(filepath=path)
        bpy.ops.wm.open_mainfile(filepath=path)
    root = next(c for c in bpy.data.collections if c.get("ctx_root"))
    assert bpy.data.images.get(f"Site photo · {SITE}") and bpy.data.materials.get(f"Site photo · {SITE}")
    assert site_use.has_photo(root) and site_use.photo_image(root).packed_file is not None
    tower, _shed = buildings(root)
    site_use.apply_roofs(root, "photo", 100.0)
    assert [m.name for m in tower.data.materials][-1] == f"Site photo · {SITE}"


def test_the_packed_image_is_named_for_its_site_and_not_for_the_cache():
    root, folder = photo_site()
    image = site_use.photo_image(root)
    assert image.filepath == "//320_Bay_St photo.jpg" and image.packed_file is not None
    assert folder not in image.filepath and "photo.jpg" != os.path.basename(image.filepath)
    other, _ = photo_site(address="Second site")
    assert site_use.photo_image(other).filepath == "//Second_site photo.jpg"
    assert site_use.photo_image(other).filepath != image.filepath


def test_the_saved_blend_holds_no_path_to_the_cache_folder():
    root, folder = photo_site()
    blend = os.path.join(tempfile.mkdtemp(), "site.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=False)  # plain, so its bytes can be searched
    with open(blend, "rb") as f:
        saved = f.read()
    assert os.path.basename(folder).encode() not in saved and folder.encode() not in saved
    assert b"320_Bay_St photo.jpg" in saved


def test_two_sites_unpack_to_two_files_with_their_own_bytes():
    first, _ = photo_site()
    folder = tempfile.mkdtemp()
    doc = photo_doc(folder, "Second site")
    with open(PHOTO, "rb") as f:
        original = f.read()
    with open(os.path.join(folder, "photo.jpg"), "wb") as f:
        f.write(original + bytes(16))  # bytes after the end of the picture: still the same picture, other file
    second = scene_build.build(bpy.context.scene, doc, folder=folder)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(tempfile.mkdtemp(), "site.blend"))
    paths = []
    for root, expected in ((first, original), (second, original + bytes(16))):
        image = site_use.photo_image(root)
        image.unpack(method="WRITE_LOCAL")
        paths.append(bpy.path.abspath(image.filepath))
        with open(paths[-1], "rb") as f:
            assert f.read() == expected
    assert paths[0] != paths[1] and [os.path.basename(p) for p in paths] == ["320_Bay_St photo.jpg", "Second_site photo.jpg"]


def test_the_packed_photo_keeps_its_size_and_colour_space():
    root, _ = photo_site()
    image = site_use.photo_image(root)
    assert image.packed_file is not None and tuple(image.size) == (128, 128) and image.source == "FILE"
    assert image.colorspace_settings.name == "sRGB"
    with open(PHOTO, "rb") as f:
        assert image.packed_file.data == f.read()


def test_save_reads_the_photo_from_disk_after_unpacking_resources():
    root, _ = photo_site()
    blend_dir = tempfile.mkdtemp()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(blend_dir, "site.blend"))
    image = site_use.photo_image(root)
    image.unpack(method="WRITE_LOCAL")
    on_disk = os.path.realpath(bpy.path.abspath(image.filepath))
    assert image.packed_file is None and os.path.isfile(on_disk)
    assert os.path.commonpath([on_disk, os.path.realpath(blend_dir)]) == os.path.realpath(blend_dir)
    jpg, _jgw, _width = site_photo.save(root, tempfile.mkdtemp())
    with open(jpg, "rb") as saved, open(PHOTO, "rb") as original:
        assert saved.read() == original.read()
    os.remove(on_disk)  # neither packed nor on disk: nothing to save
    try:
        site_photo.save(root, tempfile.mkdtemp())
    except ValueError as e:
        assert "isn't in this file" in str(e)
    else:
        raise AssertionError("save should refuse when the photo is gone")


def test_save_writes_the_photo_and_a_world_file_in_model_coordinates():
    root, _ = photo_site()
    out = tempfile.mkdtemp()
    jpg, jgw, width = site_photo.save(root, out)
    assert os.path.basename(jpg) == "320_Bay_St photo.jpg" and os.path.basename(jgw) == "320_Bay_St photo.jgw"
    assert width == 300.0
    with open(jpg, "rb") as saved, open(PHOTO, "rb") as original:
        assert saved.read() == original.read()
    with open(jgw, encoding="ascii") as f:
        a, d, b, e, c, f_ = (float(v) for v in f.read().split())
    pixel = 300.0 / 128
    assert abs(a - pixel) < 1e-6 and d == 0 and b == 0 and abs(e + pixel) < 1e-6
    assert abs(c - (-150 + pixel / 2)) < 1e-6 and abs(f_ - (150 - pixel / 2)) < 1e-6


def test_the_save_operator_writes_for_the_picked_site():
    ghosttown.register()
    try:
        root, _ = photo_site()
        bpy.context.scene.ghosttown.site = root
        out = tempfile.mkdtemp()
        assert bpy.ops.ghosttown.save_photo(directory=out) == {"FINISHED"}
        assert sorted(os.listdir(out)) == ["320_Bay_St photo.jgw", "320_Bay_St photo.jpg"]
    finally:
        ghosttown.unregister()
