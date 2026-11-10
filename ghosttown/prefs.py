import os

import bpy
from bpy.props import IntProperty, StringProperty

from .ghosttown_fetch.look_schema import TOKEN_ENV
from .revit_bridge import DEFAULT_HOST, DEFAULT_PORT

DEFAULT_OVERPASS = "https://overpass-api.de/api/interpreter"
DEFAULT_BUDGET = 500_000


class GhostTownPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    cache_dir: StringProperty(
        name="Cache folder", subtype="DIR_PATH",
        description="Where downloaded data and runs are kept. Leave blank for Ghost Town's own folder under "
                    "Blender's extensions folder, shown below")
    overpass_url: StringProperty(
        name="Overpass endpoint", default=DEFAULT_OVERPASS,
        description="OpenStreetMap Overpass API server")
    revit_triangle_budget: IntProperty(
        name="Revit triangle budget", default=DEFAULT_BUDGET, min=10_000,
        description="A site with more triangles than this is flagged as heavy for Revit")
    revit_host: StringProperty(
        name="Revit host", default=DEFAULT_HOST,
        description="The computer Revit runs on, with pyRevit's Routes server and Ghost Town's extension, for "
                    "Send to Revit: localhost for this one, else its name or address on your network")
    revit_port: IntProperty(
        name="Revit port", default=DEFAULT_PORT, min=1, max=65535,
        description="pyRevit Routes' port on that computer (48884 unless changed in pyRevit's settings)")
    mapillary_token: StringProperty(
        name="Mapillary token", subtype="PASSWORD",
        description="Your Mapillary client token, for Street Look. Create one at mapillary.com/dashboard/developers")

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "cache_dir")
        # the folder in use; never cache_dir(), whose create=True would make the folder on every redraw
        if self.cache_dir.strip():
            folder = bpy.path.abspath(self.cache_dir)
        else:
            folder = bpy.utils.extension_path_user(__package__, path="cache", create=False)
        for line in path_lines(folder):
            col.label(text=line)
        col.prop(self, "overpass_url")
        col.prop(self, "revit_triangle_budget")
        row = col.row(align=True)
        row.prop(self, "revit_host")
        row.prop(self, "revit_port")
        col.prop(self, "mapillary_token")
        col.label(text=f"Or set {TOKEN_ENV}.")
        col.label(text="The token is saved in Blender's preferences file, never in your scene's .blend files.")


def path_lines(path, width=60):
    """A folder as one or two labels, broken after a path separator, so the Preferences window (about 500 px)
    doesn't clip the middle out of a long one."""
    if len(path) <= width:
        return [path]
    cuts = [i + 1 for i, ch in enumerate(path) if ch in "/\\" and 0 < i < len(path) - 1]
    if not cuts:
        return [path]
    cut = min(cuts, key=lambda i: max(i, len(path) - i))
    return [path[:cut], path[cut:]]


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


def revit_address(context):
    """(host, port) Send to Revit posts to."""
    p = get(context)
    if p is None:
        return DEFAULT_HOST, DEFAULT_PORT
    return p.revit_host.strip() or DEFAULT_HOST, p.revit_port


def token(context):
    """The Mapillary token from Preferences, else from the environment; '' when there is none."""
    p = get(context)
    value = p.mapillary_token.strip() if p is not None else ""
    return value or os.environ.get(TOKEN_ENV, "").strip()
