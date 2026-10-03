import bpy
from bpy.props import EnumProperty, StringProperty

RADII = [
    ("150", "150 m", "A block or two"),
    ("300", "300 m", "The neighbourhood"),
    ("500", "500 m", "A wider area"),
    ("1000", "1000 m", "Large area; slower"),
]


class GhostTownSettings(bpy.types.PropertyGroup):
    # Text, not FloatProperty: Blender floats are single precision (about 0.5 m at these latitudes).
    location: StringProperty(
        name="Location", description="Latitude, longitude in degrees, e.g. 43.6497, -79.3810")
    site_name: StringProperty(
        name="Site name", description="Names the collection, e.g. the street address")
    radius: EnumProperty(name="Radius", items=RADII, default="300")
    summary: StringProperty(name="Last build")
    credits: StringProperty(name="Data credits")
