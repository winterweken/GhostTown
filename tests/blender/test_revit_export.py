import os
import tempfile

import bpy

import ghosttown
from ghosttown import revit_export, scene_build, site_realistic, site_use
from helpers import drum_doc


def photo_drum_site():
    folder = tempfile.mkdtemp()
    return scene_build.build(bpy.context.scene, drum_doc(photo_folder=folder), folder=folder)


def exported(root, **kw):
    path = os.path.join(tempfile.mkdtemp(), "site.obj")
    count = revit_export.export(bpy.context, root, path, **kw)
    with open(path, encoding="utf-8") as f:
        obj = f.read()
    with open(path[:-4] + ".mtl", encoding="utf-8") as f:
        mtl = f.read()
    return count, obj, mtl


def materials_in(mtl):
    """Material names as Blender wrote them, spaces back in (OBJ writes them as underscores)."""
    return {line.split(" ", 1)[1].strip().replace("_", " ") for line in mtl.splitlines() if line.startswith("newmtl ")}


def test_a_realistic_photo_site_exports_plain_context_and_comes_back_as_it_was():
    root = photo_drum_site()
    site_use.apply_roofs(root, "photo")
    site_use.apply_ground(root, "realistic")
    count, obj, mtl = exported(root)
    names = materials_in(mtl)
    assert "Context - Building" in names and "Context - Ground" in names and "Context - Water" in names
    assert not any(n.startswith(("Ghost Town Realistic", "Site photo")) for n in names)
    assert "Earth" not in obj and count == len(revit_export.objects_to_export(root))
    assert root["use_ground"] == "realistic" and root["use_roofs"] == "photo"
    assert site_realistic.find(root, "earth") is not None and site_realistic.find(root, "earth_cutter") is not None


def test_buildings_export_whole_and_z_up():
    root = photo_drum_site()
    site_use.apply_ground(root, "realistic")
    _, obj, _ = exported(root)
    verts = [tuple(map(float, line.split()[1:4])) for line in obj.splitlines() if line.startswith("v ")]
    assert max(x for x, _, _ in verts) > root["radius_m"] + 20          # osm:way:9 untrimmed, to r + 30
    assert abs(max(z for *_, z in verts) - 60.0) < 0.5                 # the 60 m tower stands on Z


def test_selection_and_active_object_are_restored():
    root = photo_drum_site()
    keep = next(o for o in root.all_objects if o.get("ctx_kind") == "tree")
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    keep.select_set(True)
    bpy.context.view_layer.objects.active = keep
    exported(root)
    assert [o for o in bpy.context.view_layer.objects if o.select_get()] == [keep]
    assert bpy.context.view_layer.objects.active == keep


def test_hidden_objects_and_facade_detail_stay_out_unless_asked():
    root = photo_drum_site()
    tree = next(o for o in root.all_objects if o.get("ctx_kind") == "tree")
    tree.hide_set(True)
    names = {o.name for o in revit_export.objects_to_export(root)}
    assert tree.name not in names
    assert not any(o.get("ctx_kind") in ("earth", "earth_cutter", "facade_detail") for o in
                   revit_export.objects_to_export(root))


def test_the_operator_needs_a_picked_site():
    ghosttown.register()
    try:
        bpy.context.scene.ghosttown.site = None
        assert not bpy.ops.ghosttown.export_revit.poll()
        bpy.context.scene.ghosttown.site = photo_drum_site()
        assert bpy.ops.ghosttown.export_revit.poll()
    finally:
        ghosttown.unregister()
