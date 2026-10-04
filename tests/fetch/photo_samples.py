"""The City's photo services as the tests see them: a recorded 128 px photo and a folder listing."""
import json
from pathlib import Path

JPEG = (Path(__file__).parent / "fixtures" / "bay" / "photo_128.jpg").read_bytes()


def listing(*names):
    return json.dumps({"currentVersion": 11.3, "folders": [],
                       "services": [{"name": n, "type": "MapServer"} for n in names]}).encode("utf-8")


LISTING = listing("basemap/cot_ortho", "basemap/cot_ortho_2023_color_10cm", "basemap/cot_ortho_2025_color_8cm",
                  "basemap/cot_ortho_2024_color_8cm", "basemap/cot_historic_aerial_1931", "basemap/cot_topo")
ANSWERS = {"rest/services/basemap?f=json": LISTING, "/MapServer/export?": JPEG}
