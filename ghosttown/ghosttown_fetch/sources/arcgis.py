"""ArcGIS REST feature layers (City of Toronto): POSTed queries answered as GeoJSON, followed across pages."""
import json
import urllib.parse

from ..net import SourceError

BASE = "https://gis.toronto.ca/arcgis/rest/services"
MAX_PAGES = 50


def layer_url(service, layer):
    return f"{BASE}/{service}/FeatureServer/{layer}/query"


def radius_params(lat, lon, radius_m, *, out_fields="*", where="1=1"):
    return {
        "where": where,
        "geometry": f"{lon:.7f},{lat:.7f}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "distance": f"{radius_m:.0f}",
        "units": "esriSRUnit_Meter",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": out_fields,
        "outSR": "4326",
        "f": "geojson",
        "orderByFields": "OBJECTID",
    }


def query(net, service, layer, params, *, source="toronto"):
    """Every feature for one query. Page sizes are not reliable, so keep asking while the server
    says there is more and the last page was not empty."""
    url = layer_url(service, layer)
    features, offset = [], 0
    for _ in range(MAX_PAGES):
        data = urllib.parse.urlencode({**params, "resultOffset": str(offset)}).encode("ascii")
        page = _load(net.get(url, source=source, data=data, check=check))
        got = page.get("features") or []
        features += got
        more = page.get("exceededTransferLimit") or (page.get("properties") or {}).get("exceededTransferLimit")
        if not more or not got:
            return features
        offset += len(got)
    raise SourceError("The City of Toronto returned too many pages; try a smaller radius.")


def check(body):
    _load(body)


def _load(body):
    try:
        doc = json.loads(body)
    except ValueError:
        raise SourceError("The City of Toronto sent an answer that isn't JSON; try again in a minute.") from None
    if not isinstance(doc, dict):
        raise SourceError("The City of Toronto sent an answer that isn't JSON; try again in a minute.")
    if "error" in doc:
        error = doc["error"]
        detail = error.get("message", error) if isinstance(error, dict) else error
        raise SourceError(f"The City of Toronto refused a query ({str(detail)[:120]}); try again in a minute.")
    return doc
