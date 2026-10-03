"""GhostTown fetcher: request.json in, context.json out.

Runs as `python -m ghosttown_fetch` on Blender's own Python. It never imports bpy.
This file, request.py and context.py use the standard library only, so the
Blender add-on can import them without shapely or numpy.
"""

__version__ = "0.1.0"
SCHEMA = 1
TOOL = "ghosttown " + __version__
HOMEPAGE = "https://github.com/winterweken/GhostTown"

BUILDING_KINDS = ("building", "building_on_site", "building_guessed")
GROUND_KINDS = ("water", "road", "sidewalk", "parking", "rail", "green", "ground")
KINDS = BUILDING_KINDS + GROUND_KINDS + ("tree", "parcel", "parcel_on_site")

LAYERS = ("buildings", "terrain", "roads", "sidewalks", "parking", "rail",
          "green", "water", "trees", "parcels")
RADIUS_RANGE_M = (50.0, 1000.0)
SITE_LIMIT_M = 2000.0  # site outlines must sit within this distance of the centre

SOURCE_NAMES = {"osm": "OpenStreetMap", "toronto": "City of Toronto", "nrcan": "Natural Resources Canada"}
CREDITS = {
    "osm": "© OpenStreetMap contributors",
    "toronto": "Contains information licensed under the Open Government Licence – Toronto",
    "nrcan": "Contains information licensed under the Open Government Licence – Canada",
}
