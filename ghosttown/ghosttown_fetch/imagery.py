"""Photos as linear-light arrays, Mapillary's labels as a picture-sized map of kinds, and road brightness
for exposure calibration."""
import base64
import binascii
import io

import numpy as np
from PIL import Image, ImageDraw

from . import mvt

LABEL_WIDTH = 512
UNKNOWN, BUILDING, SKY, GROUND, CLUTTER, THIN = range(6)
BUILDING_LABEL = "construction--structure--building"
ROAD_LABEL = "construction--flat--road"
GROUND_PREFIXES = ("construction--flat--", "nature--terrain", "marking--")
THIN_PREFIXES = ("object--wire-group", "object--support--", "object--street-light", "object--traffic-sign",
                 "object--traffic-light", "object--sign--", "object--banner")
MIN_ROAD_PX = 500


def kind_of(value):
    if value == BUILDING_LABEL:
        return BUILDING
    if value == "nature--sky":
        return SKY
    if value.startswith(GROUND_PREFIXES):
        return GROUND
    if value.startswith(THIN_PREFIXES):
        return THIN
    if not value or value.startswith("void--"):
        return UNKNOWN
    return CLUTTER


def srgb_to_linear(a):
    a = np.asarray(a, dtype=np.float32)
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4).astype(np.float32)


def decode_linear(jpeg):
    """(H, W, 3) float32 linear RGB from JPEG bytes."""
    with Image.open(io.BytesIO(jpeg)) as im:
        return srgb_to_linear(np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0)


def luminance(c):
    c = np.asarray(c)
    return c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722


class Labels:
    """Mapillary's labels painted into a LABEL_WIDTH-wide map of kinds. Bigger regions are painted first,
    so smaller objects stay on top of the regions they sit in."""

    def __init__(self, detections, aspect):
        self.w = LABEL_WIDTH
        self.h = max(1, round(LABEL_WIDTH * aspect))
        shapes = []
        for det in detections:
            try:
                polygons = mvt.decode_polygons(base64.b64decode(det["geometry"]))
            except (binascii.Error, ValueError, KeyError, TypeError):
                continue
            for _layer, rings in polygons:
                ring = [(u * self.w, v * self.h) for u, v in rings[0]]
                if len(ring) >= 3:
                    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
                    shapes.append(((max(xs) - min(xs)) * (max(ys) - min(ys)), det["value"], ring))
        kinds = Image.new("L", (self.w, self.h), UNKNOWN)
        road = Image.new("L", (self.w, self.h), 0)
        draw_kinds, draw_road = ImageDraw.Draw(kinds), ImageDraw.Draw(road)
        for _area, value, ring in sorted(shapes, key=lambda s: -s[0]):
            draw_kinds.polygon(ring, fill=kind_of(value))
            draw_road.polygon(ring, fill=255 if value == ROAD_LABEL else 0)
        self.kinds = np.asarray(kinds)
        self.road = np.asarray(road) > 0

    def at(self, u, v):
        """Kinds at picture fractions; points outside the picture are UNKNOWN."""
        u, v = np.asarray(u, dtype=float), np.asarray(v, dtype=float)
        inside = (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
        out = np.full(u.shape, UNKNOWN, dtype=np.uint8)
        out[inside] = self.kinds[(v[inside] * self.h).astype(int), (u[inside] * self.w).astype(int)]
        return out


def road_luminance(image, labels):
    """Median linear luminance of the road in a photo, or None with fewer than MIN_ROAD_PX road pixels."""
    h, w = image.shape[:2]
    rows = np.arange(h) * labels.h // h
    cols = np.arange(w) * labels.w // w
    mask = labels.road[rows[:, None], cols[None, :]]
    if mask.sum() < MIN_ROAD_PX:
        return None
    return float(np.median(luminance(image[mask])))


def sample(image, u, v):
    """Colours (n, 3) at picture fractions (u, v)."""
    h, w = image.shape[:2]
    rows = np.clip((np.asarray(v) * h).astype(int), 0, h - 1)
    cols = np.clip((np.asarray(u) * w).astype(int), 0, w - 1)
    return image[rows, cols]
