import os
import textwrap

import bpy

from . import georef, look_build, materials, ops, prefs, runner, site_apps, site_use
from .ghosttown_fetch import app_boxes
from .ghosttown_fetch import context as ctx

ICON_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "ghosttown.png")
_previews = None


def load_icons():
    """The Ghost Town mark for the panel header. Called on register."""
    global _previews
    import bpy.utils.previews

    unload_icons()
    _previews = bpy.utils.previews.new()
    if os.path.isfile(ICON_FILE):
        _previews.load("ghosttown", ICON_FILE, "IMAGE")


def unload_icons():
    global _previews
    if _previews is not None:
        bpy.utils.previews.remove(_previews)
        _previews = None


def icon_loaded():
    return _previews is not None and "ghosttown" in _previews


def icon_id():
    """Blender's id for the mark, or 0 (no icon) when it isn't loaded."""
    return _previews["ghosttown"].icon_id if icon_loaded() else 0


class GHOSTTOWN_PT_main(bpy.types.Panel):
    bl_idname = "GHOSTTOWN_PT_main"
    bl_label = "Ghost Town"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Ghost Town"

    def draw_header(self, context):
        mark = icon_id()
        if mark:
            self.layout.label(text="", icon_value=mark)

    def draw(self, context):
        settings = context.scene.ghosttown
        layout = self.layout
        if not bpy.app.online_access:
            box = layout.box()
            box.label(text="Online access is off", icon="ERROR")
            box.label(text="Preferences › System › Network")
        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(settings, "location")
        find = row.row(align=True)
        find.enabled = bpy.app.online_access and "find" not in runner.ACTIVE
        find.operator("ghosttown.find", text="", icon="VIEWZOOM")
        col.prop(settings, "site_name")
        if "find" in runner.ACTIVE:
            layout.label(text="Searching…", icon="TIME")
        if settings.results:
            box = layout.box()
            box.label(text="Pick an address:")
            for i, item in enumerate(settings.results):
                box.operator("ghosttown.pick", text=item.label).index = i
        layout.prop(settings, "radius")
        col = layout.column()
        col.label(text="Fetch")
        col.prop(settings, "fetch_photo")
        col.prop(settings, "fetch_lidar")
        col.prop(settings, "fetch_applications")
        if "build" in runner.ACTIVE:
            layout.label(text=runner.STATUS.get("build", "Working…"), icon="TIME")
            layout.operator("ghosttown.cancel", icon="CANCEL").key = "build"
        else:
            row = layout.row()
            row.enabled = bpy.app.online_access
            row.operator("ghosttown.build", icon="WORLD")
        layout.operator("ghosttown.import_context", icon="FILEBROWSER")
        if settings.summary:
            box = layout.box()
            box.label(text=settings.summary, icon="CHECKMARK")
            for line in settings.credits.splitlines():
                box.label(text=line)


SITE_ICONS = ("EMPTY_AXIS", "COPYDOWN", "IMAGE_DATA", "INFO", "EXPORT", "MOD_DECIM", "ERROR", "HOME", "URL",
              "LOOP_BACK", "OBJECT_DATA")
HEAVY = ("Heavy for Revit: use Fitted or Flat roofs,", "or lower Roof detail, before exporting.")
ROOF_SHAPES = {"flat": "Flat", "fitted": "Fitted", "lidar": "LiDAR"}


def triangles_text(count):
    """'1.4 M' or '86,000'."""
    return f"{count / 1e6:.1f} M" if count >= 1_000_000 else f"{count:,}"


# The default Solid view colours by material, so it never shows the photo on the ground.
SOLID_HINT = "Shows in Material Preview, or Solid view with Color: Texture."


def _choice(layout, label, operator, current, options):
    row = layout.row(align=True)
    row.label(text=label)
    for value, text in options:
        row.operator(operator, text=text, depress=current == value).use = value


MAX_DESCRIPTION_LINES = 8


def _applications_box(layout, context, coll):
    """The site's development application boxes: a swatch and count per status, the data's date, Bring Back,
    and, when the active object is one of them, its applications."""
    box = layout.box()
    date = coll.get("ctx_app_date", "")
    box.label(text=f"Development applications {date}".strip(), icon="HOME")
    col = box.column(align=True)
    for group, n in site_apps.status_counts(context.scene, coll):
        row = col.row(align=True)
        mat = bpy.data.materials.get(materials.application_name(group))
        split = row.split(factor=0.15, align=True)
        if mat is not None:
            split.prop(mat, "diffuse_color", text="")
        else:
            split.label(text="")
        split.label(text=f"{app_boxes.LABELS[group]}: {n}")
    gone = site_apps.deleted_count(context.scene, coll)
    if gone:
        box.operator("ghosttown.apps_bring_back", text=f"Bring Back Deleted Boxes ({gone})", icon="LOOP_BACK")
    ob = context.active_object
    if ob is None or ob.get(site_apps.BOX_SITE) != coll.get(site_apps.SITE_PROP):
        return
    detail = box.box()
    group = ob.get("ctx_app_group", "review")
    detail.label(text=f"{app_boxes.LABELS.get(group, group)} · {ob.get('ctx_app_height_from', '')}",
                 icon="OBJECT_DATA")
    width = hint_width(context)
    for a in site_apps.applications_of(ob):
        col = detail.column(align=True)
        col.label(text=" · ".join(str(a.get(k, "")) for k in ("number", "type", "status", "submitted") if a.get(k)))
        if a.get("address"):
            col.label(text=str(a["address"]))
        lines = textwrap.wrap(str(a.get("description", "")), width)
        for line in lines[:MAX_DESCRIPTION_LINES]:
            col.label(text=line)
        if len(lines) > MAX_DESCRIPTION_LINES:
            col.label(text="…")
        if ctx.city_link(a.get("url")):
            col.operator("ghosttown.open_application", icon="URL").number = str(a.get("number", ""))


class GHOSTTOWN_PT_site(bpy.types.Panel):
    bl_idname = "GHOSTTOWN_PT_site"
    bl_label = "Site"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Ghost Town"
    bl_parent_id = "GHOSTTOWN_PT_main"

    @classmethod
    def poll(cls, context):
        return any(c.get("ctx_root") for c in context.scene.collection.children_recursive)

    def draw(self, context):
        layout = self.layout
        settings = context.scene.ghosttown
        layout.prop(settings, "site")
        root = site_use.picked(context)
        if root is None:
            return
        point = georef.survey_from(root)
        if point:
            box = layout.box()
            row = box.row()
            row.label(text="Survey point (for Revit)", icon="EMPTY_AXIS")
            row.operator("ghosttown.copy_survey", text="", icon="COPYDOWN")
            col = box.column(align=True)
            for line in georef.survey_lines(point):
                col.label(text=line)
        if site_use.has_photo(root):
            box = layout.box()
            year = root.get("photo_year") or 0
            box.label(text=f"Aerial photo {year}" if year else "Aerial photo", icon="IMAGE_DATA")
            _choice(box, "Ground", "ghosttown.use_ground", root.get("use_ground"),
                    (("colours", "Colours"), ("photo", "Photo")))
            box.label(text=SOLID_HINT, icon="INFO")
            _choice(box, "Roofs", "ghosttown.use_roofs", root.get("use_roofs"),
                    (("plain", "Plain"), ("photo", "Photo")))
            if root.get("use_roofs") == "photo":
                box.prop(settings, "roof_photo_max_m")
                box.label(text="Taller buildings lean in the photo.", icon="INFO")
            box.operator("ghosttown.save_photo", icon="EXPORT")
        if site_use.has_lidar(root):
            box = layout.box()
            box.label(text="LiDAR roofs", icon="MOD_DECIM")
            _choice(box, "Roof shapes", "ghosttown.use_roof_shapes", root.get("use_roof_shapes"),
                    [(use, ROOF_SHAPES[use]) for use in site_use.roof_choices(root)])
            if root.get("use_roof_shapes") == "lidar":
                box.prop(settings, "roof_detail")
            count = root.get("ctx_triangles")
            if count is not None:
                heavy = count > prefs.triangle_budget(context)
                box.label(text=f"For Revit: {triangles_text(count)} triangles", icon="ERROR" if heavy else "INFO")
                if heavy:
                    for line in HEAVY:
                        box.label(text=line)
        apps = site_apps.find(context.scene, root.get("ctx_label"))
        if apps is not None:
            _applications_box(layout, context, apps)


def hint_width(context):
    """Characters that fit across the sidebar. region.width is in pixels at the UI scale (twice as many on a
    Retina screen, where the text is twice as large too); ui_scale reads 0 in background Blender. An int:
    textwrap raises on a float width once a word is longer than the line."""
    scale = max(1.0, context.preferences.system.ui_scale)
    return max(20, int(context.region.width / scale) // 7)


class GHOSTTOWN_PT_street_look(bpy.types.Panel):
    bl_idname = "GHOSTTOWN_PT_street_look"
    bl_label = "Street Look"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Ghost Town"
    bl_parent_id = "GHOSTTOWN_PT_site"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        settings = context.scene.ghosttown
        layout = self.layout
        refusal = ops.look_refusal(context)
        if refusal and refusal != ops.OFFLINE:   # the main panel already says when online access is off
            col = layout.box().column(align=True)
            for line in textwrap.wrap(refusal, hint_width(context)):
                col.label(text=line)
        col = layout.column()
        col.prop(settings, "look_budget")
        col.prop(settings, "look_not_before")
        col.prop(settings, "look_detail")
        col.prop(settings, "look_keep")
        if "look" in runner.ACTIVE:
            layout.label(text=runner.STATUS.get("look", "Working…"), icon="TIME")
            layout.operator("ghosttown.cancel", icon="CANCEL").key = "look"
        else:
            row = layout.row()
            row.enabled = refusal is None
            row.operator("ghosttown.street_look", icon="IMAGE_DATA")
        if look_build.can_add_sky(context.scene):
            layout.operator("ghosttown.add_sky", icon="WORLD")
        col = layout.column()
        col.prop(settings, "show_look")
        col.prop(settings, "show_detail")
        col.prop(settings, "look_brightness")
        root = site_use.picked(context)
        if root is not None and root.get(look_build.SUMMARY_PROP):
            box = layout.box()
            box.label(text=root[look_build.SUMMARY_PROP], icon="CHECKMARK")
            for line in str(root.get(look_build.CREDITS_PROP, "")).splitlines():
                box.label(text=line)
