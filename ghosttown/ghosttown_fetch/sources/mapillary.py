"""Mapillary street photos: listings by map tile, thumbnails and each image's labels.

The token travels in a header, never in a URL, so it is never part of a cache key. Thumbnail links are
signed and expire, so photos are cached by image id and the links themselves are never stored."""
import json
import math
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from ..net import RETRY_WAIT_S, SourceError

API = "https://graph.mapillary.com"
TILE_M = 100.0
WORKERS = 8
LIMIT = 2000
OUTAGE_FAILURES = 8   # requests in a row finding Mapillary unreachable, down or throttling before the rest are not sent
LIST_FIELDS = ("id,captured_at,camera_type,computed_geometry,computed_rotation,camera_parameters,width,"
               "height,sequence")
REFUSED = "Mapillary refused the token; check it in Preferences."
THROTTLED = "Mapillary's request limit was reached; try again in a minute."
NOT_REACHED = "Mapillary couldn't be reached; try again in a minute."
UNREADABLE = "Mapillary sent an answer that couldn't be read."


class TokenRejected(SourceError):
    """Mapillary said no to the token."""


class Throttled(SourceError):
    """Mapillary turned a request away twice, a pause apart: its request limit was reached."""


class NotSent(SourceError):
    """A request left unsent because Mapillary had stopped answering (OUTAGE_FAILURES failures in a row). Its
    message is the sentence for the whole run."""


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


def _throttled(error):
    """Whether a failed answer is Mapillary's request limit ("Application request limit reached": HTTP 403 with
    Graph error code 4, subcode 1349210), which comes as a 403 like a refused token."""
    if getattr(error, "status", None) != 403:
        return False
    try:
        detail = json.loads(error.body or b"").get("error") or {}
        return detail.get("code") == 4 and detail.get("error_subcode") == 1349210
    except (ValueError, AttributeError, TypeError):
        return False


def _api(net, url, token, **kwargs):
    """A Graph API answer, the token in the header. A request turned away for the request limit is asked once
    more after a pause, then raises Throttled; any other 401 or 403 is a refused token."""
    for attempt in range(2):
        try:
            return net.get(url, source="mapillary", headers={"Authorization": "OAuth " + token}, **kwargs)
        except SourceError as e:
            if not _throttled(e):
                if getattr(e, "status", None) in (401, 403):
                    raise TokenRejected(REFUSED, status=e.status) from None
                raise
        if not attempt:
            net.sleep(RETRY_WAIT_S)
    raise Throttled(THROTTLED, status=403)


class _Outage:
    """Counts the failed requests in a row, in the order they finish, that find Mapillary unreachable, down or
    throttling (no HTTP status, 429, 5xx or the request limit); any other answer starts the count again. From
    OUTAGE_FAILURES on, the requests still waiting are not sent and come back as NotSent at once: an outage
    costs one round of retries rather than one per request. A refused token stops them the same way."""

    def __init__(self):
        self.lock = threading.Lock()
        self.failures, self.cut = 0, None

    def answered(self, error=None):
        with self.lock:
            if self.cut is not None:
                return
            status = getattr(error, "status", None)
            down = status is None or status == 429 or status >= 500 or isinstance(error, Throttled)
            if error is not None and down:
                self.failures += 1
                if self.failures >= OUTAGE_FAILURES:
                    self.cut = NotSent(THROTTLED if isinstance(error, Throttled) else NOT_REACHED)
            else:
                self.failures = 0

    def refused(self):
        self.cut = NotSent(REFUSED)


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
    listed. A rejected token stops everything; in an outage the tiles not yet asked for count as failed."""
    outage = _Outage()

    def one(box):
        if outage.cut is not None:
            return [], outage.cut
        try:
            data = _json(_api(net, list_url(box), token, check=check_json)).get("data") or []
        except TokenRejected:
            outage.refused()
            raise
        except SourceError as e:
            outage.answered(e)
            return [], e
        outage.answered()
        return data, None

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
    """{id: fn(id) or the SourceError it raised}, run in parallel. A rejected token propagates. In an outage the
    ids not yet asked for get NotSent without being asked; the caller decides what that means for the run."""
    outage = _Outage()

    def one(i):
        if outage.cut is not None:
            return i, outage.cut
        try:
            out = fn(i)
        except TokenRejected:
            outage.refused()
            raise
        except SourceError as e:
            outage.answered(e)
            return i, e
        outage.answered()
        return i, out

    with ThreadPoolExecutor(workers) as pool:
        return dict(pool.map(one, list(ids)))
