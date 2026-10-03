import os

import bpy

from . import runner

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
        if "build" in runner.ACTIVE:
            layout.label(text=runner.STATUS.get("build", "Working…"), icon="TIME")
            layout.operator("ghosttown.cancel", icon="CANCEL")
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
