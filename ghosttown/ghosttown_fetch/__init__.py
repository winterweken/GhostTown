"""Ghost Town fetcher: request.json in, context.json out; look_request.json in, look.json out.

Runs as `python -m ghosttown_fetch` on Blender's own Python. It never imports bpy.
This file, request.py, context.py and look_schema.py use the standard library only, so the
Blender add-on can import them without shapely, numpy or Pillow.
"""

__version__ = "0.3.0"
SCHEMA = 1
TOOL = "ghosttown " + __version__
HOMEPAGE = "https://github.com/winterweken/GhostTown"

BUILDING_KINDS = ("building", "building_on_site", "building_guessed")
GROUND_KINDS = ("water", "road", "sidewalk", "parking", "rail", "green", "ground")
KINDS = BUILDING_KINDS + GROUND_KINDS + ("tree", "parcel", "parcel_on_site")

LAYERS = ("buildings", "terrain", "roads", "sidewalks", "parking", "rail",
          "green", "water", "trees", "parcels", "photo", "lidar")
DEFAULT_LAYERS = tuple(layer for layer in LAYERS if layer != "lidar")  # LiDAR roofs are a big download: asked for
RADIUS_RANGE_M = (50.0, 1000.0)
SITE_LIMIT_M = 2000.0  # site outlines must sit within this distance of the centre

SOURCE_NAMES = {"osm": "OpenStreetMap", "toronto": "City of Toronto", "nrcan": "Natural Resources Canada",
                "ontario": "Geospatial Ontario", "mapillary": "Mapillary", "mapillary_labels": "Mapillary"}
CREDITS = {
    "osm": "© OpenStreetMap contributors",
    "toronto": "Contains information licensed under the Open Government Licence – Toronto",
    "nrcan": "Contains information licensed under the Open Government Licence – Canada",
    "ontario": "Contains information licensed under the Open Government Licence – Ontario",
    "mapillary": "Street photos © Mapillary contributors, CC BY-SA 4.0",
    "mapillary_labels": "Labels from Mapillary · https://www.mapillary.com",   # the labels are Mapillary's own data
}
LOOK_SCHEMA = 1
