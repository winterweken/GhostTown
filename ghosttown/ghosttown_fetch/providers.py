"""Declarative municipal open data provider registry.

Supports cities around Lake Ontario, Southern Ontario, and Windsor with municipal
ArcGIS REST layers for parcels, buildings, ground, and trees.
"""
import shapely
from shapely.geometry import Point

from . import buildings, parcels, trees
from .geom import feature_geometry, polygons, to_local
from .net import SourceError
from .sources import arcgis, ortho


class MunicipalProvider:
    def __init__(self, id, name, box, *, boundary=None, parcels_spec=None,
                 buildings_spec=None, ground_specs=None, trees_specs=None, photo_spec=None):
        self.id = id
        self.name = name
        self.source_key = id
        self.box = box  # (lat_min, lat_max, lon_min, lon_max)
        self.boundary = boundary
        self.parcels_spec = parcels_spec
        self.buildings_spec = buildings_spec
        self.ground_specs = ground_specs or {}
        self.trees_specs = trees_specs or []
        self.photo_spec = photo_spec

    def in_box(self, lat, lon):
        lat_min, lat_max, lon_min, lon_max = self.box
        return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max

    def fetch_boundary(self, net):
        if not self.boundary:
            return None
        url = self.boundary.get("url")
        where = self.boundary.get("where", "1=1")
        params = {"where": where, "outFields": "*", "returnGeometry": "true", "outSR": "4326", "f": "geojson"}
        parts = []
        for feature in arcgis.query(net, url, params, source=self.source_key, source_name=self.name):
            geom = feature_geometry(feature)
            if geom is not None:
                geom = shapely.make_valid(geom)
                parts += [p for p in shapely.get_parts(geom) if p.geom_type in ("Polygon", "MultiPolygon")]
        if not parts:
            raise SourceError(f"The {self.name} boundary came back empty; try again in a minute.")
        return shapely.union_all(parts)

    def fetch_parcels(self, net, lat, lon, radius_m):
        if not self.parcels_spec:
            return []
        spec = self.parcels_spec
        order_by = spec.get("order_by", "OBJECTID" if spec.get("id_field") != "FID" else "FID")
        params = arcgis.radius_params(lat, lon, radius_m,
                                      out_fields=spec.get("out_fields", "*"),
                                      where=spec.get("where", "1=1"),
                                      order_by=order_by)
        return arcgis.query(net, spec["url"], params, source=self.source_key, source_name=self.name)

    def build_parcels(self, features, frame, terrain, radius_m):
        if not self.parcels_spec or not features:
            return []
        spec = self.parcels_spec
        return parcels.from_features(features, frame, terrain, radius_m,
                                     source_key=self.source_key,
                                     id_field=spec.get("id_field", "OBJECTID"),
                                     name_fn=spec.get("name_fn"))

    def fetch_buildings(self, net, lat, lon, radius_m):
        if not self.buildings_spec:
            return []
        spec = self.buildings_spec
        margin = spec.get("margin_m", 250.0)
        order_by = spec.get("order_by", "OBJECTID" if spec.get("id_field") != "FID" else "FID")
        params = arcgis.radius_params(lat, lon, radius_m + margin,
                                      out_fields=spec.get("out_fields", "*"),
                                      where=spec.get("where", "1=1"),
                                      order_by=order_by)
        return arcgis.query(net, spec["url"], params, source=self.source_key, source_name=self.name)

    def build_buildings(self, features, frame, terrain, radius_m):
        if not self.buildings_spec or not features:
            return []
        spec = self.buildings_spec
        return buildings.from_features(features, frame, terrain, radius_m,
                                       source_key=self.source_key,
                                       height_fn=spec.get("height_fn"),
                                       id_fn=spec.get("id_fn"),
                                       filter_fn=spec.get("filter_fn"))

    def fetch_ground(self, net, lat, lon, radius_m, frame, kinds=None, skipped=None):
        pieces = {}
        for kind, layers in self.ground_specs.items():
            if kinds is not None and kind not in kinds:
                continue
            for spec in layers:
                url = spec["url"]
                where = spec.get("where", "1=1")
                buffer_m = spec.get("buffer_m")
                params = arcgis.radius_params(lat, lon, radius_m, out_fields="*", where=where)
                for feature in arcgis.query(net, url, params, source=self.source_key, source_name=self.name):
                    geom = feature_geometry(feature)
                    if geom is None:
                        continue
                    try:
                        local = to_local(geom, frame)
                        if local.geom_type in ("LineString", "MultiLineString") and buffer_m:
                            local = local.buffer(buffer_m, cap_style="flat")
                        found = polygons(local)
                    except shapely.errors.GEOSException:
                        if skipped is not None:
                            skipped.append((kind, (feature.get("properties") or {}).get("OBJECTID")))
                        continue
                    if found:
                        pieces.setdefault(kind, []).extend(found)
        return pieces

    def fetch_trees(self, net, lat, lon, radius_m):
        features = []
        for spec in self.trees_specs:
            url = spec["url"]
            where = spec.get("where", "1=1")
            params = arcgis.radius_params(lat, lon, radius_m, out_fields="*", where=where)
            features.extend(arcgis.query(net, url, params, source=self.source_key, source_name=self.name))
        return features

    def build_trees(self, features, frame, terrain):
        if not features:
            return []
        height_field = self.trees_specs[0].get("height_field") if self.trees_specs else None
        return trees.from_features(features, frame, terrain, source_key=self.source_key, height_field=height_field)

    def fetch_photo(self, net, frame, radius_m, out_dir):
        if self.photo_spec:
            spec = self.photo_spec
            url = spec["url"]
            year = spec.get("year")
            source_key = spec.get("source_key", self.source_key)
            return ortho.fetch(net, url, frame, radius_m, out_dir, source_key=source_key, year=year)
        if ortho.in_ontario(frame.lat0, frame.lon0):
            return ortho.fetch(net, ortho.ONTARIO_IMAGERY_URL, frame, radius_m, out_dir, source_key="ontario")
        return None


def _windsor_height(p):
    top, grd = p.get("Bld_Ht_Top"), p.get("Bld_Ht_Grd")
    if top is not None and grd is not None:
        try:
            diff = float(top) - float(grd)
            if diff >= 0.5:
                return diff
        except (ValueError, TypeError):
            pass
    return None


WINDSOR = MunicipalProvider(
    id="windsor",
    name="City of Windsor",
    box=(42.22, 42.36, -83.12, -82.88),
    boundary={
        "url": "https://mappmycity.ca/arcgis/rest/services/Boundaries/MapServer/11/query",
        "where": "1=1",
    },
    parcels_spec={
        "url": "https://mappmycity.ca/arcgis/rest/services/PropertyParcels/MapServer/4/query",
        "where": "1=1",
        "out_fields": "OBJECTID,LEGAL1,STATUS",
        "id_field": "OBJECTID",
        "name_fn": lambda p: (p.get("LEGAL1") or "").strip(),
    },
    buildings_spec={
        "url": "https://mappmycity.ca/arcgis/rest/services/PropertyParcels/MapServer/3/query",
        "where": "1=1",
        "out_fields": "OBJECTID,Bld_Ht_Top,Bld_Ht_Grd",
        "height_fn": _windsor_height,
        "id_fn": lambda p: f"obj{p.get('OBJECTID')}",
    },
    ground_specs={
        "water": [
            {"url": "https://mappmycity.ca/arcgis/rest/services/Boundaries/MapServer/2/query", "where": "1=1"},
            {"url": "https://mappmycity.ca/arcgis/rest/services/ParksEnvironment/MapServer/6/query", "where": "1=1"},
            {"url": "https://mappmycity.ca/arcgis/rest/services/Infrastructure/MapServer/26/query", "where": "1=1"},
            {"url": "https://mappmycity.ca/arcgis/rest/services/ParksEnvironment/MapServer/9/query", "where": "1=1", "buffer_m": 3.0},
        ],
        "road": [
            {"url": "https://mappmycity.ca/arcgis/rest/services/Transportation/MapServer/16/query", "where": "1=1", "buffer_m": 4.5},
            {"url": "https://mappmycity.ca/arcgis/rest/services/Transportation/MapServer/7/query", "where": "1=1"},
        ],
        "green": [
            {"url": "https://mappmycity.ca/arcgis/rest/services/ParksEnvironment/MapServer/4/query", "where": "1=1"},
            {"url": "https://mappmycity.ca/arcgis/rest/services/ParksEnvironment/MapServer/5/query", "where": "1=1"},
        ],
        "sidewalk": [
            {"url": "https://mappmycity.ca/arcgis/rest/services/Transportation/MapServer/13/query", "where": "1=1", "buffer_m": 1.5},
        ],
    },
    trees_specs=[
        {"url": "https://mappmycity.ca/arcgis/rest/services/ParksEnvironment/MapServer/2/query", "where": "1=1"},
        {"url": "https://mappmycity.ca/arcgis/rest/services/ParksEnvironment/MapServer/3/query", "where": "1=1"},
    ],
    photo_spec={
        "url": "https://mappmycity.ca/arcgis/rest/services/WINDSOR_AERIAL/Windsor_2024/MapServer/export",
        "year": 2024,
        "source_key": "windsor",
    },
)


MISSISSAUGA = MunicipalProvider(
    id="mississauga",
    name="City of Mississauga",
    box=(43.48, 43.76, -79.80, -79.52),
    parcels_spec={
        "url": "https://services6.arcgis.com/hM5ymMLbxIyWTjn2/arcgis/rest/services/Parcel/FeatureServer/0/query",
        "where": "1=1",
        "out_fields": "FID,CITY_PIN,GIS_AREA",
        "id_field": "CITY_PIN",
        "order_by": "FID",
        "name_fn": lambda p: f"PIN {p.get('CITY_PIN')}" if p.get("CITY_PIN") else "",
    },
    buildings_spec={
        "url": "https://services6.arcgis.com/hM5ymMLbxIyWTjn2/arcgis/rest/services/BldgRoof/FeatureServer/0/query",
        "where": "1=1",
        "out_fields": "FID,FtType,ZArea",
        "order_by": "FID",
        "id_fn": lambda p: f"obj{p.get('FID')}",
    },
    ground_specs={
        "water": [
            {"url": "https://services6.arcgis.com/hM5ymMLbxIyWTjn2/arcgis/rest/services/Waterbody/FeatureServer/0/query", "where": "1=1"},
        ],
        "road": [
            {"url": "https://services6.arcgis.com/hM5ymMLbxIyWTjn2/arcgis/rest/services/StreetCentreline/FeatureServer/0/query", "where": "1=1", "buffer_m": 4.5},
        ],
        "green": [
            {"url": "https://services6.arcgis.com/hM5ymMLbxIyWTjn2/arcgis/rest/services/Park_Boundary/FeatureServer/1/query", "where": "1=1"},
        ],
    },
)


MARKHAM = MunicipalProvider(
    id="markham",
    name="City of Markham",
    box=(43.79, 44.02, -79.46, -79.18),
    parcels_spec={
        "url": "https://services3.arcgis.com/OWiFbQmr7Eu5DHn1/arcgis/rest/services/Parcels/FeatureServer/0/query",
        "where": "1=1",
        "out_fields": "OBJECTID,ADDRESS,STREET",
        "id_field": "OBJECTID",
        "name_fn": lambda p: f"{p.get('ADDRESS', '')} {p.get('STREET', '')}".strip() or str(p.get("OBJECTID", "")),
    },
    ground_specs={
        "road": [
            {"url": "https://services3.arcgis.com/OWiFbQmr7Eu5DHn1/arcgis/rest/services/StreetRoads/FeatureServer/0/query", "where": "1=1", "buffer_m": 4.5},
        ],
        "green": [
            {"url": "https://services3.arcgis.com/OWiFbQmr7Eu5DHn1/arcgis/rest/services/Park_Areas/FeatureServer/0/query", "where": "1=1"},
        ],
    },
)


HAMILTON = MunicipalProvider(
    id="hamilton",
    name="City of Hamilton",
    box=(43.14, 43.37, -80.06, -79.68),
    parcels_spec={
        "url": "https://services.arcgis.com/rYz782eMbySr2srL/arcgis/rest/services/Hamilton_Assessment_Parcel/FeatureServer/0/query",
        "where": "1=1",
        "out_fields": "OBJECTID",
        "id_field": "OBJECTID",
    },
    ground_specs={
        "water": [
            {"url": "https://services.arcgis.com/rYz782eMbySr2srL/arcgis/rest/services/Waterbodies/FeatureServer/1/query", "where": "1=1"},
        ],
        "road": [
            {"url": "https://services.arcgis.com/rYz782eMbySr2srL/arcgis/rest/services/Street_Centreline/FeatureServer/14/query", "where": "1=1", "buffer_m": 4.5},
        ],
        "green": [
            {"url": "https://services.arcgis.com/rYz782eMbySr2srL/arcgis/rest/services/Parks_OD/FeatureServer/6/query", "where": "1=1"},
        ],
    },
)


PROVIDERS = {
    "windsor": WINDSOR,
    "mississauga": MISSISSAUGA,
    "markham": MARKHAM,
    "hamilton": HAMILTON,
}


def provider_by_id(provider_id):
    return PROVIDERS.get(provider_id)


def find_candidate_provider(lat, lon):
    for provider in PROVIDERS.values():
        if provider.in_box(lat, lon):
            return provider
    return None
