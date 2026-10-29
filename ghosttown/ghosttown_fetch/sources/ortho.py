"""Export orthophotos from ArcGIS MapServer services (Ontario Imagery, Windsor, etc.)."""
import os
import urllib.parse

from ..cache import atomic_write
from . import toronto_photo

ONTARIO_IMAGERY_URL = "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_Imagery/Ontario_Imagery_Web_Map_Service/MapServer/export"
ONTARIO_BOX = (41.6, 56.9, -95.2, -74.3)


def in_ontario(lat, lon):
    lat_min, lat_max, lon_min, lon_max = ONTARIO_BOX
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def export_url(base_url, box, size):
    query = urllib.parse.urlencode({
        "bbox": ",".join(f"{v:.3f}" for v in box),
        "bboxSR": 3857,
        "imageSR": 3857,
        "size": f"{size},{size}",
        "format": "jpg",
        "f": "image",
    })
    clean_base = base_url if base_url.endswith("/export") else f"{base_url.rstrip('/')}/export"
    return f"{clean_base}?{query}"


def fetch(net, url, frame, radius_m, out_dir, source_key="ontario", year=None):
    box, bounds = toronto_photo.area(frame, radius_m)
    size = toronto_photo.size_px(radius_m)
    body = net.get(export_url(url, box, size), source=source_key, check=toronto_photo.check)
    atomic_write(os.path.join(out_dir, toronto_photo.FILE), body)
    return {
        "file": toronto_photo.FILE,
        "year": year,
        "width_px": size,
        "height_px": size,
        "bounds_m": bounds,
        "source": source_key,
    }
