import bpy
from bpy.props import StringProperty

DEFAULT_OVERPASS = "https://overpass-api.de/api/interpreter"


class GhostTownPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    cache_dir: StringProperty(
        name="Cache folder", subtype="DIR_PATH",
        description="Where downloaded data and runs are kept. Leave blank for the extension's own folder")
    overpass_url: StringProperty(
        name="Overpass endpoint", default=DEFAULT_OVERPASS,
        description="OpenStreetMap Overpass API server")

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "cache_dir")
        col.prop(self, "overpass_url")


def get(context):
    addon = context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


def cache_dir(context):
    """Resolved on use, never at import time: extension_path_user only works inside the extension."""
    p = get(context)
    if p is not None and p.cache_dir.strip():
        return bpy.path.abspath(p.cache_dir)
    return bpy.utils.extension_path_user(__package__, path="cache", create=True)
