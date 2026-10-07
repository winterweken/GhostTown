"""Mapillary street photos: listings by map tile, thumbnails and each image's labels.

The token travels in a header, never in a URL, so it is never part of a cache key. Thumbnail links are
signed and expire, so photos are cached by image id and the links themselves are never stored."""
import json
import math
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from ..net import SourceError

API = "https://graph.mapillary.com"
TILE_M = 100.0
WORKERS = 8
LIMIT = 2000
LIST_FIELDS = ("id,captured_at,camera_type,computed_geometry,computed_rotation,camera_parameters,width,"
               "height,sequence")
REFUSED = "Mapillary refused the token; check it in Preferences."
UNREADABLE = "Mapillary sent an answer that couldn't be read."


class TokenRejected(SourceError):
    """Mapillary said no to the token."""


def _json(body):
    try:
        doc = json.loads(body)
    except ValueError:
        raise SourceError(UNREADABLE) from None
    if not isinstance(doc, dict):
        raise SourceError(UNREADABLE)
    return doc


def check_json(body):
    _json(body)


def check_jpeg(body):
    if not (len(body) > 100 and body[:3] == b"\xff\xd8\xff"):
        raise SourceError("Mapillary sent a photo that couldn't be read.")


def _api(net, url, token, **kwargs):
    try:
        return net.get(url, source="mapillary", headers={"Authorization": "OAuth " + token}, **kwargs)
    except SourceError as e:
        if getattr(e, "status", None) in (401, 403):
            raise TokenRejected(REFUSED, status=e.status) from None
        raise


def tiles(frame, radius_m):
    """Boxes (lon0, lat0, lon1, lat1) of TILE_M squares that touch the circle."""
    n = max(1, math.ceil(2 * radius_m / TILE_M))
    half = n * TILE_M / 2
    out = []
    for i in range(n):
        for j in range(n):
            x0, y0 = -half + i * TILE_M, -half + j * TILE_M
            x1, y1 = x0 + TILE_M, y0 + TILE_M
            nearest_x, nearest_y = min(max(0.0, x0), x1), min(max(0.0, y0), y1)
            if math.hypot(nearest_x, nearest_y) > radius_m:
                continue
            lon0, lat0 = frame.to_lonlat(x0, y0)
            lon1, lat1 = frame.to_lonlat(x1, y1)
            out.append((lon0, lat0, lon1, lat1))
    return out


def list_url(box):
    query = urllib.parse.urlencode({"bbox": ",".join(f"{v:.7f}" for v in box), "fields": LIST_FIELDS,
                                    "limit": LIMIT}, safe=",")
    return f"{API}/images?{query}"


def list_images(net, frame, radius_m, token, *, workers=WORKERS):
    """(images, failed): image records within the circle, one per id, and how many tiles couldn't be
    listed. A rejected token stops everything."""
    def one(box):
        try:
            return _json(_api(net, list_url(box), token, check=check_json)).get("data") or [], None
        except TokenRejected:
            raise
        except SourceError as e:
            return [], e

    seen, failed = {}, 0
    with ThreadPoolExecutor(workers) as pool:
        for data, error in pool.map(one, tiles(frame, radius_m)):
            if error is not None:
                failed += 1
            for image in data:
                if isinstance(image, dict) and "id" in image:
                    seen[str(image["id"])] = image
    return list(seen.values()), failed


def photo(net, image_id, token):
    """The 2048 px thumbnail as JPEG bytes, cached by image id."""
    key = f"photo:{image_id}:2048"
    body = net.cached("mapillary", key, check=check_jpeg)
    if body is not None:
        return body
    link = _json(_api(net, f"{API}/{image_id}?fields=thumb_2048_url", token, check=check_json, keep=False))
    url = link.get("thumb_2048_url")
    if not url:
        raise SourceError("Mapillary has no thumbnail for one of the photos.")
    return net.get(url, source="mapillary", key=key, check=check_jpeg)


def detections(net, image_id, token):
    """Mapillary's labels for one image: [{"value", "geometry"}], geometry being a base64 vector tile."""
    doc = _json(_api(net, f"{API}/{image_id}/detections?fields=value,geometry", token, check=check_json))
    return [d for d in doc.get("data") or [] if isinstance(d, dict) and "value" in d and "geometry" in d]


def fetch_many(fn, ids, *, workers=WORKERS):
    """{id: fn(id) or the SourceError it raised}, run in parallel. A rejected token propagates."""
    def one(i):
        try:
            return i, fn(i)
        except TokenRejected:
            raise
        except SourceError as e:
            return i, e

    with ThreadPoolExecutor(workers) as pool:
        return dict(pool.map(one, list(ids)))
