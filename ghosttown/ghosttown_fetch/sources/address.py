"""Toronto address search on the City's Address Point layer.

The City spells street types and directions in short form ("100 Queen St W"), so the street type
(the last word, or the one before a final direction) and a final direction are abbreviated;
everything else is left alone ("North York Blvd" keeps "North", "Avenue Rd" keeps "Avenue")."""
import json
import re
import urllib.parse

from . import arcgis

LAYER = ("cot_geospatial27", 101)
TYPES = {"STREET": "ST", "AVENUE": "AVE", "ROAD": "RD", "BOULEVARD": "BLVD", "DRIVE": "DR", "CRESCENT": "CRES",
         "COURT": "CRT", "PLACE": "PL", "TERRACE": "TER", "CIRCLE": "CIRC", "PARKWAY": "PKWY", "SQUARE": "SQ",
         "GARDENS": "GDNS", "HEIGHTS": "HTS", "TRAIL": "TRL", "GROVE": "GRV", "GATE": "GT"}
DIRECTIONS = {"WEST": "W", "EAST": "E", "NORTH": "N", "SOUTH": "S"}
_UNWANTED = re.compile(r"[^A-Z0-9 '\-/&]")


def normalise(text):
    s = (text or "").split(",")[0].upper().replace(".", " ")
    tokens = _UNWANTED.sub(" ", s).split()
    type_at = len(tokens) - 1
    if tokens and tokens[-1] in DIRECTIONS:
        tokens[-1] = DIRECTIONS[tokens[-1]]
        type_at -= 1
    if type_at >= 1 and tokens[type_at] in TYPES:
        tokens[type_at] = TYPES[tokens[type_at]]
    return " ".join(tokens)


def build_params(norm, limit):
    pattern = norm.replace("'", "''")
    return {"where": f"UPPER(ADDRESS_FULL) LIKE '{pattern}%'", "outFields": "ADDRESS_FULL,LATITUDE,LONGITUDE",
            "returnGeometry": "false", "orderByFields": "ADDRESS_FULL", "resultRecordCount": str(limit), "f": "json"}


def search(net, text, limit=5):
    norm = normalise(text)
    if not norm:
        return []
    data = urllib.parse.urlencode(build_params(norm, limit)).encode("ascii")
    doc = json.loads(net.get(arcgis.layer_url(*LAYER), source="toronto", data=data, check=arcgis.check))
    results = []
    for feature in (doc.get("features") or [])[:limit]:
        a = feature.get("attributes") or {}
        lat, lon = a.get("LATITUDE"), a.get("LONGITUDE")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            results.append({"label": a.get("ADDRESS_FULL") or norm, "lat": float(lat), "lon": float(lon),
                            "source": "toronto"})
    return results
