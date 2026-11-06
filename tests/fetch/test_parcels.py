import json

import numpy as np

from ghosttown_fetch import parcels
from ghosttown_fetch.frame import Frame
from ghosttown_fetch.sources import toronto
from ghosttown_fetch.terrain import FlatTerrain
from fakes import FakeNet, form
from terrains import Ramp
from toronto_samples import LAT0, LON0, multipolygon, page, square

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


def test_a_lot_that_holds_the_whole_circle_has_no_line_and_the_other_lots_are_still_built():
    # A site inside one large lot (a park, seen 2026-11-05): the lot's edge never meets the circle.
    els = parcels.from_toronto(_features(square(-200, -200, 400, OBJECTID=1, PARCELID=77),
                                         square(0, 0, 20, OBJECTID=2, PARCELID=55)), F, FlatTerrain(), 100)
    assert [el["id"] for el in els] == ["toronto:parcel:55"]


def test_a_lot_of_two_pieces_has_lines_only_from_the_piece_that_crosses_the_circle():
    # A lot of two polygons (seen 2026-11-05): one lies well outside the circle, the other crosses it.
    lot = multipolygon(square(361, 0, 20), square(20, -10, 100), OBJECTID=4247)
    el, = parcels.from_features(_features(lot), F, FlatTerrain(), 30, source_key="windsor", id_field="OBJECTID")
    line, = el["lines"]
    pts = np.array(line["pts"])[:, :2]
    assert el["id"] == "windsor:parcel:4247"
    # the crossing piece's corner at (20, -10) is inside the circle; its two edges leave it at y = √(30² − 20²)
    # and x = √(30² − 10²)
    assert np.allclose(sorted([tuple(pts[0]), tuple(pts[-1])]), [(20.0, 22.361), (28.284, -10.0)], atol=0.01)
    assert [20.0, -10.0] in pts.tolist() and np.hypot(pts[:, 0], pts[:, 1]).max() <= 30.001


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
    assert form(data)["outFields"] == "OBJECTID,PARCELID,DATE_EXPIRY"


# The City's Property Boundary layer as it answered on 2026-11-04: its fields (ADDRESS_NUMBER and LINEAR_NAME_FULL
# had gone from it), and its answer to a query that asks for a field it doesn't have.
PROPERTY_BOUNDARY_FIELDS = {"OBJECTID", "Shape__Area", "Shape__Length", "FEATURE_TYPE", "DATE_EFFECTIVE",
                            "DATE_EXPIRY", "STATEDAREA", "TRANS_ID_CREATE", "TRANS_ID_EXPIRE", "PARCELID",
                            "GEOM_AREA", "SYSTEMSTARTDATE"}
REFUSAL = b'{"error":{"code":400,"extendedCode":-2147467259,"message":"Unable to complete operation.","details":[]}}'


def _property_boundary(*features):
    """A FakeNet answer that behaves like the City's layer: the page, or its refusal of a field it doesn't have."""
    def answer(url, data):
        asked = set(form(data)["outFields"].split(","))
        return page(*features) if asked <= PROPERTY_BOUNDARY_FIELDS else REFUSAL
    return answer


def test_fetch_parcels_asks_only_for_fields_the_citys_layer_has():
    net = FakeNet({"toronto": _property_boundary(square(0, 0, 20, OBJECTID=13408, PARCELID=5464980,
                                                        DATE_EXPIRY=32503698000000))})
    found = toronto.fetch_parcels(net, LAT0, LON0, 150)
    assert [f["properties"]["PARCELID"] for f in found] == [5464980]
