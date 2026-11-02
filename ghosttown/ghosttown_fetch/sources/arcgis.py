"""ArcGIS REST feature layers: POSTed queries answered as GeoJSON, followed across pages."""
import json
import urllib.parse

from ..net import SourceError

BASE = "https://gis.toronto.ca/arcgis/rest/services"
MAX_PAGES = 50


def layer_url(service, layer=None, *, base_url=None, server_type="FeatureServer"):
    if isinstance(service, str) and (service.startswith("http://") or service.startswith("https://")):
        if layer is not None:
            return f"{service.rstrip('/')}/{layer}/query"
        if service.endswith("/query"):
            return service
        return f"{service.rstrip('/')}/query"
    base = base_url or BASE
    return f"{base}/{service}/{server_type}/{layer}/query"


def radius_params(lat, lon, radius_m, *, out_fields="*", where="1=1", order_by="OBJECTID"):
    params = {
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
    }
    if order_by:
        params["orderByFields"] = order_by
    return params


def query(net, service, layer=None, params=None, *, source="toronto", source_name=None,
          base_url=None, server_type="FeatureServer", accept=None, max_age_days=None):
    """Every feature for one query. Page sizes are not reliable, so keep asking while the server
    says there is more and the last page was not empty. `accept(body)` may raise SourceError to
    refuse an answer before it is cached. `max_age_days`: how long a stored page is used (the cache's
    30 days when None)."""
    if params is None and isinstance(layer, dict):
        params, layer = layer, None
    url = layer_url(service, layer, base_url=base_url, server_type=server_type)
    name = source_name or ("The City of Toronto" if source == "toronto" else "The ArcGIS service")
    features, offset = [], 0
    for _ in range(MAX_PAGES):
        data = urllib.parse.urlencode({**params, "resultOffset": str(offset)}).encode("ascii")
        page = _load(net.get(url, source=source, data=data, check=accept or check, max_age_days=max_age_days), name)
        got = page.get("features") or []
        features += got
        more = page.get("exceededTransferLimit") or (page.get("properties") or {}).get("exceededTransferLimit")
        if not more or not got:
            return features
        offset += len(got)
    raise SourceError(f"{name} returned too many pages; try a smaller radius.")


def check(body, source_name="The City of Toronto"):
    _load(body, source_name)


def _load(body, source_name="The City of Toronto"):
    try:
        doc = json.loads(body)
    except ValueError:
        raise SourceError(f"{source_name} sent an answer that isn't JSON; try again in a minute.") from None
    if not isinstance(doc, dict):
        raise SourceError(f"{source_name} sent an answer that isn't JSON; try again in a minute.")
    if "error" in doc:
        error = doc["error"]
        detail = error.get("message", error) if isinstance(error, dict) else error
        raise SourceError(f"{source_name} refused a query ({str(detail)[:120]}); try again in a minute.")
    return doc

