"""City of Toronto open data layers on gis.toronto.ca, asked for by site radius."""
from ..geom import feature_geometry, polygons, to_local
from . import arcgis

TOPO = "cot_geospatial3"    # the City's topographic layers
CITY = "cot_geospatial27"   # parcels, parks, address points, city boundary
BUILDINGS = (TOPO, 2)
BUILDING_WHERE = "SUBTYPE_DESC = 'Building Outline'"  # Miscellaneous Structure (canopies, kiosks) is left out
BUILDING_FIELDS = "BUILDINGID,SUBTYPE_DESC,DERIVED_HEIGHT,OBJECTID"
ID_CHUNK = 200
WHOLE_MARGIN_M = 250.0  # a building's other tiers are fetched this far beyond the circle (some ids recur kilometres away)


def fetch_buildings(net, lat, lon, radius_m):
    """Building tiers touching the circle, plus every other tier of those buildings so they come in whole."""
    near = arcgis.query(net, *BUILDINGS, arcgis.radius_params(lat, lon, radius_m, out_fields=BUILDING_FIELDS,
                                                               where=BUILDING_WHERE))
    found = {_oid(f): f for f in near}
    ids = sorted({int(p["BUILDINGID"]) for p in (_props(f) for f in near) if isinstance(p.get("BUILDINGID"), (int, float))})
    for start in range(0, len(ids), ID_CHUNK):
        chunk = ",".join(str(i) for i in ids[start:start + ID_CHUNK])
        params = arcgis.radius_params(lat, lon, radius_m + WHOLE_MARGIN_M, out_fields=BUILDING_FIELDS,
                                      where=f"BUILDINGID IN ({chunk}) AND {BUILDING_WHERE}")
        for f in arcgis.query(net, *BUILDINGS, params):
            found.setdefault(_oid(f), f)
    return list(found.values())


def _props(feature):
    return feature.get("properties") or {}


def _oid(feature):
    return _props(feature).get("OBJECTID")


TREES = (TOPO, 10)


def fetch_trees(net, lat, lon, radius_m):
    return arcgis.query(net, *TREES, arcgis.radius_params(lat, lon, radius_m, out_fields="OBJECTID,DERIVED_HEIGHT"))


PARCELS = (CITY, 36)


def fetch_parcels(net, lat, lon, radius_m):
    """Lot lines only: CONDO parcels overlap the COMMON ones they sit on."""
    return arcgis.query(net, *PARCELS, arcgis.radius_params(
        lat, lon, radius_m, out_fields="OBJECTID,PARCELID,ADDRESS_NUMBER,LINEAR_NAME_FULL",
        where="FEATURE_TYPE = 'COMMON'"))


GROUND = {
    "road": [(TOPO, 3, "1=1")],                              # road surfaces (edges, intersections, ramps, lanes)
    "sidewalk": [(TOPO, 6, "1=1")],
    "parking": [(TOPO, 13, "1=1")],
    "rail": [(TOPO, 14, "SUBTYPE_DESC = 'Rail Track'")],     # streetcar track runs inside roads
    "water": [(TOPO, 16, "1=1")],
    "green": [(CITY, 3, "1=1"), (TOPO, 9, "1=1")],           # City parks and treed areas
}
RAIL_HALF_WIDTH_M = 1.75


def fetch_ground(net, lat, lon, radius_m, frame, kinds=None):
    """{kind: [Polygon]} in local metres for the ground layout; rail lines are widened into surfaces."""
    pieces = {}
    for kind, layers in GROUND.items():
        if kinds is not None and kind not in kinds:
            continue
        for service, layer, where in layers:
            for feature in arcgis.query(net, service, layer,
                                        arcgis.radius_params(lat, lon, radius_m, out_fields="OBJECTID", where=where)):
                geom = feature_geometry(feature)
                if geom is None:
                    continue
                local = to_local(geom, frame)
                if local.geom_type in ("LineString", "MultiLineString"):
                    local = local.buffer(RAIL_HALF_WIDTH_M, cap_style="flat")
                found = polygons(local)
                if found:
                    pieces.setdefault(kind, []).extend(found)
    return pieces
