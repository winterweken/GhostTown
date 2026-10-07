"""A synthetic street for Street Look tests: one 30 m building, four cameras south of it, and the photos
and labels Mapillary would send for them. The building has a dark storefront to 3 m, brick to 12 m and
glass above that shows a different colour from each camera; dark floor lines run every 4 m."""
import functools
import io
import json

import numpy as np
from PIL import Image

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
STOREFRONT, BRICK, GLASS = (0.03, 0.03, 0.035), (0.30, 0.12, 0.08), (0.25, 0.40, 0.55)
SKY, ROAD = (0.55, 0.70, 0.90), (0.12, 0.12, 0.12)
FLOOR_M = 4.0
SPOTS = [(-15, -60), (0, -70), (15, -55), (5, -80)]
EXPOSURES = [1.0, 1.0, 0.6, 1.0]
GLASS_FACTORS = [(1, 1, 1), (3.52, 2.2, 1.32), (0.5, 0.8, 1.6), (0.15, 0.15, 0.15)]
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


def _render(cam, scene, exposure, factor):
    dirs, rows = cam.rays(PIXELS)
    owner, dist = scene.first_hit(cam.position[None], dirs, 1000.0)
    img = np.where((dirs[:, 2] > 0)[:, None], SKY, ROAD).astype(float)
    on = owner == 0
    h = cam.position[2] + dirs[on, 2] * dist[on]
    col = np.where((h < 3)[:, None], STOREFRONT, np.where((h < 12)[:, None], BRICK, np.array(GLASS) * factor))
    line = (h >= 3) & ((h / FLOOR_M) % 1.0 < 0.12)
    col[line] *= 0.35
    img[on] = col
    pixels = (_srgb(img * exposure).reshape(rows, PIXELS, 3) * 255).round().astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(pixels).save(buf, "JPEG", quality=95)
    return buf.getvalue()


def _labels(cam):
    corners = np.array([[x, y, z] for x in (-10, 10) for y in (-10, 10) for z in (0.0, 30.0)])
    u, v, ok = cam.project(corners)
    house = _hull(np.column_stack([np.clip(u[ok], 0, 1), np.clip(v[ok], 0, 1)]))
    return [detection("nature--sky", [(0, 0), (1, 0), (1, 0.5), (0, 0.5)]),
            detection("construction--flat--road", [(0, 0.5), (1, 0.5), (1, 1), (0, 1)]),
            detection("construction--structure--building", house)]


@functools.lru_cache(maxsize=None)
def _street():
    frame = Frame(LAT0, LON0)
    scene = raycast.Scene([TARGET])
    cams, records, labels, photos = [], [], {}, {}
    for i, ((x, y), exposure, factor) in enumerate(zip(SPOTS, EXPOSURES, GLASS_FACTORS)):
        heading = float(np.degrees(np.arctan2(-x, -y)))   # towards the building's centre
        cam = camera((x, y, 2.0), heading_deg=heading, image_id=f"9{i}", year=2024)
        lon, lat = frame.to_lonlat(x, y)
        records.append({"id": cam.id, "captured_at": 1717200000000, "camera_type": "perspective",
                        "computed_geometry": {"type": "Point", "coordinates": [lon, lat]},
                        "computed_rotation": rotation_vector(cam.R), "camera_parameters": [cam.focal, 0.0, 0.0],
                        "width": cam.width, "height": cam.height, "sequence": "seq1"})
        labels[cam.id] = _labels(cam)
        photos[cam.id] = _render(cam, scene, exposure, np.array(factor, dtype=float))
        cams.append(cam)
    return cams, records, labels, photos


def street(detail=False):
    cams, records, labels, photos = _street()
    return {"buildings": [dict(TARGET, detail=detail), dict(FAR)], "cameras": cams, "records": records,
            "labels": labels, "photos": photos}


def fake_net(data, token_ok=True):
    """A FakeNet that answers Mapillary's listing, link, photo and label requests for `data`."""
    def answer(url, _data):
        if not token_ok:
            return SourceError("Mapillary answered HTTP 401; try again in a minute.", status=401)
        if "/images?" in url:
            return json.dumps({"data": data["records"]}).encode()
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
