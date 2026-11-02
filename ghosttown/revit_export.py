"""Export for Revit: the picked site as one OBJ in metres, Z up, origin to origin, every piece on its
`Context - <Kind>` material. Ground and roofs show their plain colours for the export (no photo, no
Realistic earth or edge trim) and go back to what the site showed. Uses bpy.ops.wm.obj_export, which has
no data API."""
import bpy

from . import site_apps, site_use

EXCLUDED_KINDS = ("facade_detail",)   # Street Look's detail: heavy, and for renders; opt in


def objects_to_export(root, applications=True, detail=False):
    """The site's own visible objects that go to Revit: buildings, ground, trees and parcels, the
    development application boxes unless left out, Street Look's detail only when asked."""
    kinds = site_use.SITE_KINDS if detail else tuple(k for k in site_use.SITE_KINDS if k not in EXCLUDED_KINDS)
    obs = site_use.made_objects(root, kinds)
    if applications:
        obs += [ob for ob in site_apps.boxes(bpy.context.scene, root.get("ctx_label")) if ob not in obs]
    return [ob for ob in obs if ob.visible_get()]


def export(context, root, path, applications=True, detail=False):
    """Write the site to `path` (.obj, with its .mtl beside it) and return how many objects went in. The
    selection is kept by name: plain ground deletes the Realistic earth, which comes back under its name."""
    ground, roofs = site_use.ground_choice(root), root.get("use_roofs")
    layer = context.view_layer
    selected = {ob.name for ob in layer.objects if ob.select_get()}
    active = layer.objects.active.name if layer.objects.active else None
    try:
        if ground != "colours":
            site_use.apply_ground(root, "colours")
        if roofs == "photo":
            site_use.apply_roofs(root, "plain")
        obs = objects_to_export(root, applications, detail)
        for ob in layer.objects:
            ob.select_set(ob in obs)
        bpy.ops.wm.obj_export(filepath=path, check_existing=False, export_selected_objects=True,
                              apply_modifiers=True, export_eval_mode="DAG_EVAL_VIEWPORT",
                              forward_axis="Y", up_axis="Z", global_scale=1.0, export_materials=True,
                              path_mode="STRIP", export_uv=False, export_colors=False,
                              export_object_groups=True, export_triangulated_mesh=False)
        return len(obs)
    finally:
        if roofs == "photo":
            site_use.apply_roofs(root, "photo")
        if ground != "colours":
            site_use.apply_ground(root, ground)
        for ob in layer.objects:
            ob.select_set(ob.name in selected)
        layer.objects.active = layer.objects.get(active) if active else None
