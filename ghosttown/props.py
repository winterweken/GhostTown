import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, PointerProperty, StringProperty

RADII = [
    ("150", "150 m", "A block or two"),
    ("300", "300 m", "The neighbourhood"),
    ("500", "500 m", "A wider area"),
    ("1000", "1000 m", "Large area; slower"),
]


def is_site(settings, collection):
    """The Site picker lists only this scene's Ghost Town context collections."""
    return bool(collection.get("ctx_root")) and collection in settings.id_data.collection.children_recursive


def _site_picked(self, context):
    root = self.site
    if root is not None and "roof_photo_max_m" in root:
        self["roof_photo_max_m"] = float(root["roof_photo_max_m"])  # item assignment: no update loop
    if root is not None and "roof_detail" in root:
        self["roof_detail"] = 100.0 * float(root["roof_detail"])


def _roof_limit_changed(self, context):
    from . import site_use
    root = site_use.picked(context)
    if root is None or not root.get("ctx_photo_material"):
        return
    if root.get("use_roofs") == "photo" and context.mode == "OBJECT":
        site_use.apply_roofs(root, "photo", self.roof_photo_max_m)
    else:
        root["roof_photo_max_m"] = float(self.roof_photo_max_m)


def _roof_detail_changed(self, context):
    from . import site_use
    root = site_use.picked(context)
    if root is None or not site_use.has_lidar(root) or context.mode != "OBJECT":
        return
    site_use.apply_roof_detail(root, self.roof_detail / 100.0)
    site_use.count_later(root)


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
    results: CollectionProperty(type=GhostTownResult)
    fetch_photo: BoolProperty(
        name="Aerial photo", default=True,
        description="Toronto: fetch the City's newest aerial photo of the site (one download)")
    fetch_lidar: BoolProperty(
        name="LiDAR roofs (slower)", default=False,
        description="Ontario: fetch the province's LiDAR and measure roofs from it, fitted and sampled, for "
                    "buildings the City of Toronto's 3D Massing model doesn't cover. "
                    "A large download; the first request can take a minute")
    site: PointerProperty(
        type=bpy.types.Collection, name="Site", poll=is_site, update=_site_picked,
        description="The Ghost Town site whose data the Site panel shows")
    roof_photo_max_m: FloatProperty(
        name="Up to", default=20.0, min=1.0, max=500.0, unit="LENGTH", update=_roof_limit_changed,
        description="Only buildings up to this tall get the photo on their roofs; taller ones lean in the photo")
    roof_detail: FloatProperty(
        name="Roof detail", default=100.0, min=5.0, max=100.0, subtype="PERCENTAGE", update=_roof_detail_changed,
        description="Simplify LiDAR roofs without moving their edges; lower it for a lighter Revit import")
