import bpy

from . import runner


class GHOSTTOWN_PT_main(bpy.types.Panel):
    bl_idname = "GHOSTTOWN_PT_main"
    bl_label = "GhostTown"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GhostTown"

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
