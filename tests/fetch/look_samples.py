"""A synthetic street for Street Look tests: one 30 m building, four cameras south of it, and the photos
and labels Mapillary would send for them. The building has a dark storefront to 3 m, brick to 12 m and
glass above that shows a different colour from each camera; dark floor lines run every 4 m.
street(occluded=True) puts a green block between the cameras and the building; street(extra=n) adds n farther
photos that choose leaves out, for a building to replace a lost photo with; street(slope=k) stands the street on
ground rising k metres per metre north; over_wall() lays a label, and optionally paint, over the building's wall
in some of the photos."""
import copy
import functools
import io
import json
import urllib.parse

import numpy as np
from PIL import Image, ImageDraw

from ghosttown_fetch import look_schema as ls
from ghosttown_fetch import raycast
from ghosttown_fetch.frame import Frame
from ghosttown_fetch.net import SourceError
from camera_samples import camera, rotation_vector
from fakes import FakeNet
from mvt_samples import detection

LAT0, LON0 = 51.5074, -0.1278   # outside Canada: flat ground and no terrain download
TARGET = {"id": "test:1", "solids": [{"rings": [[[-10, -10], [10, -10], [10, 10], [-10, 10]]], "z0": 0.0, "z1": 30.0}]}
FAR = {"id": "test:2", "solids": [{"rings": [[[300, 300], [310, 300], [310, 310], [300, 310]]], "z0": 0.0, "z1": 10.0}]}
# street(occluded=True) adds a green 12 m block between the cameras and TARGET: it hides TARGET's lower floors
OCCLUDER = {"id": "test:3", "solids": [{"rings": [[[-16, -22], [16, -22], [16, -16], [-16, -16]]],
                                        "z0": 0.0, "z1": 12.0}]}
GREEN = (0.05, 0.60, 0.05)   # the occluder's colour, and the only green in the street
STOREFRONT, BRICK, GLASS = (0.03, 0.03, 0.035), (0.30, 0.12, 0.08), (0.25, 0.40, 0.55)
SKY, ROAD = (0.55, 0.70, 0.90), (0.12, 0.12, 0.12)
FLOOR_M = 4.0
SPOTS = [(-15, -60), (0, -70), (15, -55), (5, -80)]
EXPOSURES = [1.0, 1.0, 0.6, 1.0]
GLASS_FACTORS = [(1, 1, 1), (3.52, 2.2, 1.32), (0.5, 0.8, 1.6), (0.15, 0.15, 0.15)]
# Farther back than the four, so blurrier: usable, but each one worse than all of them. Ids 80, 81 ..., sequence seq2.
EXTRA_SPOTS = [(-5, -95), (10, -100), (-10, -105), (0, -110), (5, -115), (-15, -120), (15, -125)]
PIXELS = 512


def _srgb(lin):
    lin = np.clip(lin, 0.0, 1.0)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)


def _hull(points):
    pts = sorted(set(map(tuple, np.round(points, 6))))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _render(cam, scene, exposure, factor, base=0.0):
    dirs, rows = cam.rays(PIXELS)
    owner, dist = scene.first_hit(cam.position[None], dirs, 1000.0)
    img = np.where((dirs[:, 2] > 0)[:, None], SKY, ROAD).astype(float)
    on = owner == 0
    h = cam.position[2] + dirs[on, 2] * dist[on] - base   # above the building's lowest point
    col = np.where((h < 3)[:, None], STOREFRONT, np.where((h < 12)[:, None], BRICK, np.array(GLASS) * factor))
    line = (h >= 3) & ((h / FLOOR_M) % 1.0 < 0.12)
    col[line] *= 0.35
    img[on] = col
    img[owner == 1] = GREEN   # the occluder, in a scene that has one
    pixels = (_srgb(img * exposure).reshape(rows, PIXELS, 3) * 255).round().astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(pixels).save(buf, "JPEG", quality=95)
    return buf.getvalue()


def _house(cam, building):
    """The label Mapillary draws for a one-box building: the hull of its corners as `cam` sees them."""
    solid = building["solids"][0]
    xs, ys = zip(*solid["rings"][0])
    corners = np.array([[x, y, z] for x in (min(xs), max(xs)) for y in (min(ys), max(ys))
                        for z in (solid["z0"], solid["z1"])])
    u, v, ok = cam.project(corners)
    return detection("construction--structure--building",
                     _hull(np.column_stack([np.clip(u[ok], 0, 1), np.clip(v[ok], 0, 1)])))


def _labels(cam, blocks):
    return ([detection("nature--sky", [(0, 0), (1, 0), (1, 0.5), (0, 0.5)]),
             detection("construction--flat--road", [(0, 0.5), (1, 0.5), (1, 1), (0, 1)])]
            + [_house(cam, b) for b in blocks])


class Slope:
    """Ground rising k metres per metre north (z = k y), as NRCan's heights would stand a sloped street."""
    source, cell_m, ground_at_centre_m = "nrcan-dtm", 2.0, 100.0

    def __init__(self, k):
        self.k = k

    def z(self, xs, ys):
        return self.k * np.asarray(ys, dtype=float)


def _raised(building, k):
    """`building` standing on Slope(k): every solid from the lowest ground under the footprint, as tall as before."""
    if not k:
        return dict(building)
    out = dict(building, solids=[])
    for solid in building["solids"]:
        z0 = k * min(y for ring in solid["rings"] for _x, y in ring)
        out["solids"].append(dict(solid, z0=z0, z1=z0 + solid["z1"] - solid["z0"]))
    return out


@functools.lru_cache(maxsize=None)
def _shot(i, occluded, slope):
    """(camera, listing record, labels, photo) for the i-th camera: SPOTS first, then EXTRA_SPOTS."""
    frame = Frame(LAT0, LON0)
    target = _raised(TARGET, slope)
    blocks = [target, OCCLUDER] if occluded else [target]
    extra = i >= len(SPOTS)
    x, y = EXTRA_SPOTS[i - len(SPOTS)] if extra else SPOTS[i]
    exposure, factor = (1.0, (1, 1, 1)) if extra else (EXPOSURES[i], GLASS_FACTORS[i])
    heading = float(np.degrees(np.arctan2(-x, -y)))   # towards the building's centre
    image_id = f"8{i - len(SPOTS)}" if extra else f"9{i}"
    cam = camera((x, y, slope * y + 2.0), heading_deg=heading, image_id=image_id, year=2024)
    lon, lat = frame.to_lonlat(x, y)
    record = {"id": cam.id, "captured_at": 1717200000000, "camera_type": "perspective",
              "computed_geometry": {"type": "Point", "coordinates": [lon, lat]},
              "computed_rotation": rotation_vector(cam.R), "camera_parameters": [cam.focal, 0.0, 0.0],
              "width": cam.width, "height": cam.height, "sequence": "seq2" if extra else "seq1"}
    photo = _render(cam, raycast.Scene(blocks), exposure, np.array(factor, dtype=float), target["solids"][0]["z0"])
    return cam, record, _labels(cam, blocks), photo


def street(detail=False, occluded=False, extra=0, slope=0.0):
    shots = [_shot(i, occluded, slope) for i in range(len(SPOTS) + extra)]
    cams, records = [s[0] for s in shots], copy.deepcopy([s[1] for s in shots])   # a test may change its own copy
    labels, photos = copy.deepcopy({s[0].id: s[2] for s in shots}), {s[0].id: s[3] for s in shots}
    buildings = [dict(_raised(TARGET, slope), detail=detail), _raised(FAR, slope)]
    buildings += [dict(OCCLUDER)] if occluded else []
    return {"buildings": buildings, "cameras": cams, "records": records, "labels": labels, "photos": photos}


def _painted(jpeg, polygon, rgb):
    im = Image.open(io.BytesIO(jpeg)).convert("RGB")
    fill = tuple(int(c) for c in (_srgb(np.array(rgb)) * 255).round())
    ImageDraw.Draw(im).polygon([(u * im.width, v * im.height) for u, v in polygon], fill=fill)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=95)
    return buf.getvalue()


def over_wall(data, ids, value, z0=0.0, z1=30.0, paint=None):
    """`data` with a label `value` laid over TARGET's street-facing wall between heights z0 and z1, in the photos
    `ids` (a car, a pole, a patch of sky). With `paint` (linear RGB) the patch is also drawn into those photos."""
    labels, photos = dict(data["labels"]), dict(data["photos"])
    for cam in data["cameras"]:
        if cam.id in ids:
            u, v, _ok = cam.project(np.array([[x, -10.0, z] for z in (z0, z1) for x in (-10.0, 10.0)]))
            patch = _hull(np.column_stack([np.clip(u, 0, 1), np.clip(v, 0, 1)]))
            labels[cam.id] = labels[cam.id] + [detection(value, patch)]
            if paint is not None:
                photos[cam.id] = _painted(photos[cam.id], patch, paint)
    return dict(data, labels=labels, photos=photos)


def fake_net(data, token_ok=True):
    """A FakeNet that answers Mapillary's listing, link, photo and label requests for `data`."""
    def answer(url, _data):
        if not token_ok:
            return SourceError("Mapillary answered HTTP 401; try again in a minute.", status=401)
        if "/images?" in url:   # Mapillary answers only the fields asked for
            fields = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["fields"][0].split(",")
            return json.dumps({"data": [{k: r[k] for k in fields if k in r} for r in data["records"]]}).encode()
        if url.startswith("https://cdn.example/"):
            return data["photos"][url.rsplit("/", 1)[1].split(".")[0]]
        image_id = url.split("graph.mapillary.com/", 1)[1].split("?")[0].split("/")[0]
        if "/detections" in url:
            return json.dumps({"data": data["labels"][image_id]}).encode()
        return json.dumps({"id": image_id, "thumb_2048_url": f"https://cdn.example/{image_id}.jpg"}).encode()

    return FakeNet({"mapillary": answer})


def request(tmp_path, data, **changes):
    req = ls.build_request(centre={"lat": LAT0, "lon": LON0}, radius_m=100, buildings=data["buildings"],
                           cache_dir=str(tmp_path / "cache"), out_dir=str(tmp_path / "run"), budget_photos=10)
    req.update(changes)
    return req
