import bpy
from bpy.props import CollectionProperty, EnumProperty, StringProperty

RADII = [
    ("150", "150 m", "A block or two"),
    ("300", "300 m", "The neighbourhood"),
    ("500", "500 m", "A wider area"),
    ("1000", "1000 m", "Large area; slower"),
]


class GhostTownResult(bpy.types.PropertyGroup):
    # Strings, not floats: Blender floats are single precision.
    label: StringProperty(name="Address")
    lat: StringProperty(name="Latitude")
    lon: StringProperty(name="Longitude")


class GhostTownSettings(bpy.types.PropertyGroup):
    # Text, not FloatProperty: Blender floats are single precision (about 0.5 m at these latitudes).
    location: StringProperty(
        name="Location", description="An address in Toronto (then press Find), or latitude, longitude")
    site_name: StringProperty(
        name="Site name", description="Names the collection, e.g. the street address")
    radius: EnumProperty(name="Radius", items=RADII, default="300")
    summary: StringProperty(name="Last build")
    credits: StringProperty(name="Data credits")
    survey: StringProperty(name="Survey point", description="The context origin on the survey grid, for Revit's survey point")
    results: CollectionProperty(type=GhostTownResult)
