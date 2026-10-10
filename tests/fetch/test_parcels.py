import json

import numpy as np

from ghosttown_fetch import parcels
from ghosttown_fetch.frame import Frame
from ghosttown_fetch.sources import toronto
from ghosttown_fetch.terrain import FlatTerrain
from fakes import FakeNet, form
from terrains import Ramp
from toronto_samples import LAT0, LON0, page, square

F = Frame(LAT0, LON0)


def _features(*features):
    return json.loads(page(*features))["features"]


def test_a_parcel_inside_becomes_one_closed_line_draped_15cm_up():
    el, = parcels.from_toronto(_features(square(0, 0, 20, OBJECTID=1, PARCELID=55, ADDRESS_NUMBER="320",
                                                LINEAR_NAME_FULL="Bay St")), F, FlatTerrain(), 100)
    assert el["id"] == "toronto:parcel:55" and el["name"] == "320 Bay St" and el["kind"] == "parcel"
    line, = el["lines"]
    pts = np.array(line["pts"])
    assert line["kind"] == "parcel" and np.allclose(pts[:, 2], 0.15) and np.allclose(pts[0], pts[-1])
    steps = np.linalg.norm(np.diff(pts[:, :2], axis=0), axis=1)
    assert steps.max() <= 2.0 + 1e-6 and steps.min() >= 0.003


def test_parcels_are_clipped_to_the_circle():
    el, = parcels.from_toronto(_features(square(-50, -10, 100, OBJECTID=2)), F, FlatTerrain(), 30)
    pts = np.vstack([np.array(line["pts"]) for line in el["lines"]])
    assert np.hypot(pts[:, 0], pts[:, 1]).max() <= 30.001 and el["id"] == "toronto:parcel:2" and el["name"] == ""


def test_parcel_lines_follow_the_terrain():
    el, = parcels.from_toronto(_features(square(0, 0, 20, OBJECTID=3)), F, Ramp(), 100)
    pts = np.array(el["lines"][0]["pts"])
    assert np.allclose(pts[:, 2], 0.1 * pts[:, 0] + 0.15, atol=0.001)


def test_fetch_parcels_asks_for_common_lots_only():
    net = FakeNet({"toronto": page(square(0, 0, 20, OBJECTID=1))})
    toronto.fetch_parcels(net, LAT0, LON0, 150)
    url, _, data = net.calls[0]
    assert url.endswith("/cot_geospatial27/FeatureServer/36/query")
    assert form(data)["where"] == "FEATURE_TYPE = 'COMMON'"
    assert form(data)["outFields"] == "OBJECTID,PARCELID,ADDRESS_NUMBER,LINEAR_NAME_FULL,DATE_EXPIRY"
