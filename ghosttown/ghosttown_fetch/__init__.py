"""Ghost Town fetcher: request.json in, context.json out; look_request.json in, look.json out.

Runs as `python -m ghosttown_fetch` on Blender's own Python. It never imports bpy.
This file, request.py, context.py and look_schema.py use the standard library only, so the
Blender add-on can import them without shapely, numpy or Pillow.
"""

__version__ = "0.4.0"
SCHEMA = 1
TOOL = "ghosttown " + __version__
HOMEPAGE = "https://github.com/winterweken/GhostTown"

BUILDING_KINDS = ("building", "building_on_site", "building_guessed")
GROUND_KINDS = ("water", "road", "sidewalk", "parking", "rail", "green", "ground")
KINDS = BUILDING_KINDS + GROUND_KINDS + ("tree", "parcel", "parcel_on_site")

LAYERS = ("buildings", "terrain", "roads", "sidewalks", "parking", "rail",
          "green", "water", "trees", "parcels", "photo", "lidar", "applications")
# Asked for, never by default: LiDAR roofs are a big download, and development applications are an awareness layer
# (design/development-applications.md §6.1).
OFF_BY_DEFAULT = ("lidar", "applications")
DEFAULT_LAYERS = tuple(layer for layer in LAYERS if layer not in OFF_BY_DEFAULT)
RADIUS_RANGE_M = (50.0, 1000.0)
SITE_LIMIT_M = 2000.0  # site outlines must sit within this distance of the centre
# Development applications (design/development-applications.md §4.3): a site's group, most live first, and its words.
APPLICATION_GROUPS = ("construction", "built", "appealed", "review", "approved", "coa")
GROUP_LABELS = {"construction": "Under construction", "built": "Recently built", "appealed": "Appealed",
                "review": "Under review", "approved": "Approved", "coa": "C of A"}

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
