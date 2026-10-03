"""Where the context sits on Earth, stored on the root collection and on the origin empty
(exporters ignore collection properties but keep object ones)."""
import json


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
    return p


def apply(id_block, values):
    for key, value in values.items():
        id_block[key] = value


def set_scene_units(scene):
    units = scene.unit_settings
    units.system = "METRIC"
    units.scale_length = 1.0
    units.length_unit = "METERS"
