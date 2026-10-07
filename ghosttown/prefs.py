import os

import bpy
from bpy.props import IntProperty, StringProperty

from .ghosttown_fetch.look_schema import TOKEN_ENV

DEFAULT_OVERPASS = "https://overpass-api.de/api/interpreter"
DEFAULT_BUDGET = 500_000


class GhostTownPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    cache_dir: StringProperty(
        name="Cache folder", subtype="DIR_PATH",
        description="Where downloaded data and runs are kept. Leave blank for the extension's own folder")
    overpass_url: StringProperty(
        name="Overpass endpoint", default=DEFAULT_OVERPASS,
        description="OpenStreetMap Overpass API server")
    revit_triangle_budget: IntProperty(
        name="Revit triangle budget", default=DEFAULT_BUDGET, min=10_000,
        description="A site with more triangles than this is flagged as heavy for Revit")
    mapillary_token: StringProperty(
        name="Mapillary token", subtype="PASSWORD",
        description="Your Mapillary client token, for Street Look. Create one at mapillary.com/dashboard/developers")

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "cache_dir")
        col.prop(self, "overpass_url")
        col.prop(self, "revit_triangle_budget")
        col.prop(self, "mapillary_token")
        col.label(text=f"Or set {TOKEN_ENV}. The token stays in Blender's preferences, never in .blend files.")


def get(context):
    addon = context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


def cache_dir(context):
    """Resolved on use, never at import time: extension_path_user only works inside the extension."""
    p = get(context)
    if p is not None and p.cache_dir.strip():
        return bpy.path.abspath(p.cache_dir)
    return bpy.utils.extension_path_user(__package__, path="cache", create=True)


def triangle_budget(context):
    p = get(context)
    return p.revit_triangle_budget if p is not None else DEFAULT_BUDGET


def token(context):
    """The Mapillary token from Preferences, else from the environment; '' when there is none."""
    p = get(context)
    value = p.mapillary_token.strip() if p is not None else ""
    return value or os.environ.get(TOKEN_ENV, "").strip()
