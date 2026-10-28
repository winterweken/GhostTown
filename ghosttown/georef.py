"""Where the context sits on Earth, stored on the root collection and on the origin empty
(exporters ignore collection properties but keep object ones)."""
import json

SURVEY_REQUIRED = ("survey_epsg", "survey_name", "survey_easting_m", "survey_northing_m", "survey_grid_angle_deg")


def props(doc):
    p = {
        "lat": float(doc["centre"]["lat"]),
        "lon": float(doc["centre"]["lon"]),
        "address": doc.get("address", ""),
        "radius_m": float(doc["radius_m"]),
        "terrain_source": doc["terrain"]["source"],
        "region": doc.get("region", "world"),
        "true_north_deg": 0.0,  # +y is true north
        "credits": "\n".join(dict.fromkeys(s["credit"] for s in doc["sources"])),
        "notes_json": json.dumps(doc["notes"], ensure_ascii=False),
    }
    if doc.get("ground_at_centre_m") is not None:
        p["ground_at_centre_m"] = float(doc["ground_at_centre_m"])
    point = doc.get("survey")
    if point:
        p["survey_epsg"] = point["epsg"]
        p["survey_name"] = point["name"]
        p["survey_easting_m"] = float(point["easting_m"])
        p["survey_northing_m"] = float(point["northing_m"])
        if point.get("elevation_m") is not None:
            p["survey_elevation_m"] = float(point["elevation_m"])
        p["survey_grid_angle_deg"] = float(point["grid_angle_deg"])
    return p


def survey_from(block):
    """The survey point stored on a context collection or origin empty, in survey_lines' form, or None
    unless all of its required properties are there (a user may have deleted some)."""
    if not all(key in block for key in SURVEY_REQUIRED):
        return None
    return {"epsg": block["survey_epsg"], "name": block["survey_name"],
            "easting_m": block["survey_easting_m"], "northing_m": block["survey_northing_m"],
            "elevation_m": block.get("survey_elevation_m"), "grid_angle_deg": block["survey_grid_angle_deg"]}


def survey_lines(point):
    """Where the origin sits on the survey grid, as the panel shows it and Copy puts it on the clipboard."""
    if not point:
        return []
    angle = point["grid_angle_deg"]
    if round(abs(angle), 4) == 0:
        north = "Grid north is true north"
    else:
        north = f"Grid north {abs(angle):.4f}° {'east' if angle > 0 else 'west'} of true north"
    elevation = point.get("elevation_m")
    return [
        f"{point['name']} ({point['epsg']})",
        f"Easting {point['easting_m']:.3f} m",
        f"Northing {point['northing_m']:.3f} m",
        "Elevation unknown (no terrain data)" if elevation is None else f"Elevation {elevation:.3f} m above sea level",
        north,
    ]


def apply(id_block, values):
    for key, value in values.items():
        id_block[key] = value


def set_scene_units(scene):
    units = scene.unit_settings
    units.system = "METRIC"
    units.scale_length = 1.0
    units.length_unit = "METERS"


def set_scene_georef(scene, doc_or_block):
    """Set scene-level georeferencing on the Blender scene.

    Stores standard BlenderGIS / GIS properties (SRID, latitude, longitude,
    crs x, crs y, scale) so that BlenderGIS and other GIS tools immediately
    recognize the scene as georeferenced to WGS84 (EPSG:4326). Also sets survey
    grid properties if available.
    """
    if not hasattr(scene, "__setitem__"):
        return

    if isinstance(doc_or_block, dict) and "centre" in doc_or_block:
        centre = doc_or_block.get("centre") or {}
        lat = float(centre.get("lat", 0.0))
        lon = float(centre.get("lon", 0.0))
        survey = doc_or_block.get("survey")
    else:
        try:
            lat = float(doc_or_block.get("lat", 0.0))
            lon = float(doc_or_block.get("lon", 0.0))
        except (TypeError, ValueError, AttributeError):
            return
        survey = survey_from(doc_or_block)

    # Standard scene-level GIS properties (matches BlenderGIS GeoScene)
    scene["SRID"] = "EPSG:4326"
    scene["latitude"] = lat
    scene["longitude"] = lon
    scene["crs x"] = lon
    scene["crs y"] = lat
    scene["scale"] = 1

    # Metadata for Blender's custom property UI inspector
    rna_ui = scene.get("_RNA_UI")
    if rna_ui is None:
        try:
            scene["_RNA_UI"] = {}
            rna_ui = scene["_RNA_UI"]
        except Exception:
            rna_ui = None
    if isinstance(rna_ui, dict):
        rna_ui["SRID"] = {"description": "Map Coordinate Reference System", "default": "EPSG:4326"}
        rna_ui["latitude"] = {"description": "Scene origin latitude", "default": 0.0, "min": -90.0, "max": 90.0}
        rna_ui["longitude"] = {"description": "Scene origin longitude", "default": 0.0, "min": -180.0, "max": 180.0}
        rna_ui["crs x"] = {"description": "Scene x origin in CRS space", "default": 0.0}
        rna_ui["crs y"] = {"description": "Scene y origin in CRS space", "default": 0.0}
        rna_ui["scale"] = {"description": "Scene scale factor", "default": 1.0}

    # Survey grid properties
    if survey:
        scene["survey_epsg"] = survey["epsg"]
        scene["survey_name"] = survey["name"]
        scene["survey_easting_m"] = float(survey["easting_m"])
        scene["survey_northing_m"] = float(survey["northing_m"])
        scene["survey_grid_angle_deg"] = float(survey["grid_angle_deg"])
        if survey.get("elevation_m") is not None:
            scene["survey_elevation_m"] = float(survey["elevation_m"])

    # If BlenderGIS is loaded, synchronize its wrapper
    try:
        import sys
        mod = sys.modules.get("BlenderGIS-2215.geoscene")
        if not mod:
            for k, m in sys.modules.items():
                if k.endswith(".geoscene") and hasattr(m, "GeoScene"):
                    mod = m
                    break
        if mod and hasattr(mod, "GeoScene"):
            geoscn = mod.GeoScene(scene)
            geoscn.crs = "EPSG:4326"
            geoscn.setOriginGeo(lon, lat)
    except Exception:
        pass

