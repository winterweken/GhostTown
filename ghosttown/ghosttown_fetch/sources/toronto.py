"""City of Toronto open data layers on gis.toronto.ca, asked for by site radius."""
from . import arcgis

TOPO = "cot_geospatial3"    # the City's topographic layers
CITY = "cot_geospatial27"   # parcels, parks, address points, city boundary
BUILDINGS = (TOPO, 2)
BUILDING_WHERE = "SUBTYPE_DESC = 'Building Outline'"  # Miscellaneous Structure (canopies, kiosks) is left out
BUILDING_FIELDS = "BUILDINGID,SUBTYPE_DESC,DERIVED_HEIGHT,OBJECTID"
ID_CHUNK = 200


def fetch_buildings(net, lat, lon, radius_m):
    """Building tiers touching the circle, plus every other tier of those buildings so they come in whole."""
    near = arcgis.query(net, *BUILDINGS, arcgis.radius_params(lat, lon, radius_m, out_fields=BUILDING_FIELDS,
                                                               where=BUILDING_WHERE))
    found = {_oid(f): f for f in near}
    ids = sorted({int(p["BUILDINGID"]) for p in (_props(f) for f in near) if isinstance(p.get("BUILDINGID"), (int, float))})
    for start in range(0, len(ids), ID_CHUNK):
        chunk = ",".join(str(i) for i in ids[start:start + ID_CHUNK])
        params = {"where": f"BUILDINGID IN ({chunk}) AND {BUILDING_WHERE}", "outFields": BUILDING_FIELDS,
                  "outSR": "4326", "f": "geojson", "orderByFields": "OBJECTID"}
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
