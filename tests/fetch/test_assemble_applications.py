"""assemble with Development applications ticked (design/development-applications.md §4): every source of the boxes
fetched as one step, written into context.json only when all of them answered."""
import datetime
import urllib.parse

import pytest

from ghosttown_fetch import DEFAULT_LAYERS, applications
from ghosttown_fetch import context as ctx
from ghosttown_fetch import request as rq
from ghosttown_fetch.assemble import assemble
from ghosttown_fetch.frame import Frame
from ghosttown_fetch.net import SourceError
from ghosttown_fetch.sources import arcgis, ckan, toronto, toronto_applications, toronto_permits
from ckan_samples import answer, mtm27_xy
from fakes import FakeNet, form, router
from osm_samples import body, way
from osm_samples import square as osm_square
from tiff_samples import east_slope_tiff
from toronto_samples import LAT0, LON0, page, point, polygon, square
import photo_samples

NOW = datetime.datetime(2026, 10, 9, 12, 0).timestamp()
TODAY = "2026-10-09"
CITY = polygon([(-3000, -3000), (3000, -3000), (3000, 3000), (-3000, 3000)], AREA_NAME="Toronto")
FAR = polygon([(5000, 5000), (6000, 5000), (6000, 6000), (5000, 6000)], AREA_NAME="Elsewhere")
OSM = body(way(1, osm_square(0, 0, 10), {"building": "yes", "height": "20"}))
DOWN = SourceError("City of Toronto answered HTTP 503; try again in a minute.")
LOTS = [square(-20, -20, 40, OBJECTID=3, PARCELID=55),    # the mapped application and the live permit beside it
        square(60, -20, 40, OBJECTID=4, PARCELID=56),     # the application only the table has
        square(-20, 60, 40, OBJECTID=5, PARCELID=57)]     # the completed permit
APP = point(0, 0, OBJECTID=1, APPLICATION_NUMBER="25100001STE10OZ", FOLDERTYPE="OZ", FOLDERRSN=111,
            STATUS_GROUP="Open", STATUS_DESC="NOAC Issued", SUBMIT_DATE=1740000000000,
            FOLDERDESCRIPTION="a 10-storey building", FULL_ADDRESS="1 TEST ST",
            AIC_URL="http://app.toronto.ca/AIC/index.do?folderRsn=abc")


def _address(x, y, pid, number):
    return point(x, y, OBJECTID=pid, ADDRESS_POINT_ID=pid, LO_NUM=number, LINEAR_NAME="Test",
                 LINEAR_NAME_TYPE="St", LINEAR_NAME_DIR=None)


ADDRESSES = [_address(10, 10, 900, 5), _address(0, 80, 901, 9), _address(-10, 10, 902, 3)]


def _xy(x, y):
    return [f"{v:.3f}" for v in mtm27_xy(*Frame(LAT0, LON0).to_lonlat(x, y))]


def _row(number, kind, status, submitted, folder, x, y, text="", link=""):
    return {"APPLICATION#": number, "APPLICATION_TYPE": kind, "STATUS": status, "DATE_SUBMITTED": submitted,
            "X": x, "Y": y, "FOLDERRSN": folder, "STREET_NUM": "80", "STREET_NAME": "TEST", "STREET_TYPE": "ST",
            "STREET_DIRECTION": " ", "DESCRIPTION": text, "APPLICATION_URL": link}


TABLE = [_row("25 100001 STE 10 OZ", "OZ", "NOAC Issued", "2025-02-19T00:00:00", "111", "1", "1"),
         _row("26 200002 STE 10 SA", "SA", "Under Review", "2026-09-01T00:00:00", "222", *_xy(80.0, 0.0),
              text="a 12-storey building", link="http://app.toronto.ca/AIC/index.do?folderRsn=def")]


def _permit(number, geo, status, issued, completed=None, text="", kind="New Building", structure="Apartment Building"):
    return {"PERMIT_NUM": number, "REVISION_NUM": "00", "PERMIT_TYPE": kind, "STRUCTURE_TYPE": structure,
            "STATUS": status, "GEO_ID": geo, "STREET_NUM": "5", "STREET_NAME": "TEST", "STREET_TYPE": "ST",
            "STREET_DIRECTION": "", "ISSUED_DATE": issued, "COMPLETED_DATE": completed, "DESCRIPTION": text,
            "WORK": "New Building"}


LIVE = [_permit("24 111111 BLD", "900", "Inspection", "2024-05-01", text="a 21 storey apartment building"),
        _permit("24 222222 BLD", "902", "Permit Issued", "2024-06-01", kind="New Houses", structure="SFD - Detached")]
DONE = [_permit("19 333333 BLD", "901", "Closed", "2019-03-01", "2025-08-01", text="a 6 storey building"),
        _permit("18 444444 BLD", "901", "Closed", "2018-03-01", "2024-12-31")]
TABLES = {toronto_applications.RESOURCE: TABLE, toronto_permits.LIVE: LIVE, toronto_permits.DONE: DONE}


def _city(**overrides):
    table = {
        "FeatureServer/40/": page(CITY),
        "cot_geospatial11/FeatureServer/60/": page(APP),
        "cot_geospatial27/FeatureServer/101/": page(*ADDRESSES),
        "cot_geospatial27/FeatureServer/36/": page(*LOTS),
        "package_show?id=3d-massing": DOWN,     # no massing: recently built reaches back to 1 January last year
        "FeatureServer/": page(),
    }
    table.update(photo_samples.ANSWERS)
    for key, value in overrides.items():    # an existing key keeps its place, so the catch-all stays after it
        table[key] = value
    return router(table)


def _req(tmp_path, layers=DEFAULT_LAYERS + ("applications",)):
    return rq.build(centre={"lat": LAT0, "lon": LON0}, radius_m=150, cache_dir=str(tmp_path / "c"),
                    out_dir=str(tmp_path / "o"), address="Test site", layers=layers)


def _run(tmp_path, layers=DEFAULT_LAYERS + ("applications",), tables=None, **overrides):
    net = FakeNet({"toronto": _city(**overrides), ckan.SOURCE: tables or answer(TABLES),
                   "nrcan": east_slope_tiff(Frame(LAT0, LON0), half=200.0), "osm": OSM})
    return assemble(_req(tmp_path, layers), net, now=NOW), net


def _notes(doc):
    return [n for n in doc["notes"] if n["code"] == "applications"]


def test_applications_permits_and_the_table_become_three_sites(tmp_path):
    doc, _ = _run(tmp_path)
    assert ctx.validate(doc) == [] and doc["applications_date"] == TODAY
    sites = {s["id"]: s for s in doc["applications"]}
    assert sorted(sites) == ["app:19 333333 BLD", "app:24 111111 BLD", "app:26200002STE10SA"]
    going_up = sites["app:24 111111 BLD"]
    assert going_up["group"] == "construction" and going_up["numbers"] == ["24 111111 BLD", "25100001STE10OZ"]
    assert going_up["height_from"] == "permit: 21 storeys"
    built = sites["app:19 333333 BLD"]
    assert built["group"] == "built" and built["height_from"] == "permit: 6 storeys"
    table = sites["app:26200002STE10SA"]
    assert table["group"] == "review" and table["height_from"] == "description: 12 storeys"
    assert table["applications"][0]["url"] == "http://app.toronto.ca/AIC/index.do?folderRsn=def"
    texts = [n["text"] for n in _notes(doc)]
    assert "1 development application was placed from the City's applications table, which its map doesn't show " \
           "yet." in texts
    assert "1 building permit for new houses around the site was left out." in texts
    assert all(n["level"] == "info" for n in _notes(doc))


def test_recently_built_reaches_back_to_the_massing_year(tmp_path):
    doc, _ = _run(tmp_path)
    numbers = {n for s in doc["applications"] for n in s["numbers"]}
    assert "18 444444 BLD" not in numbers               # completed 2024-12-31, before 1 January 2025


def test_unticked_applications_ask_the_city_for_none_of_it(tmp_path):
    doc, net = _run(tmp_path, layers=DEFAULT_LAYERS)
    assert "applications" not in doc and "applications_date" not in doc and _notes(doc) == []
    assert not any("datastore_search" in url or "FeatureServer/60/" in url or "FeatureServer/101/" in url
                   for url, _, _ in net.calls)


@pytest.mark.parametrize("key, words", [
    ("cot_geospatial11/FeatureServer/60/", "the City's development applications map"),
    ("cot_geospatial27/FeatureServer/101/", "the City's address points"),
    ("cot_geospatial27/FeatureServer/36/", "the City's property boundaries"),
])
def test_a_city_layer_that_fails_leaves_the_boxes_alone(tmp_path, key, words):
    doc, _ = _run(tmp_path, **{key: DOWN})
    assert "applications" not in doc and "applications_date" not in doc
    (note,) = _notes(doc)
    assert note["level"] == "warn" and words in note["text"] and "left as they are" in note["text"]


def _ckan_down(resource, only=None):
    tables = answer(TABLES)

    def serve(url, data):
        text = urllib.parse.unquote_plus(url)
        if resource in url and (only is None or only in text):
            return DOWN
        return tables(url, data)
    return serve


@pytest.mark.parametrize("resource, only, words", [
    (toronto_applications.RESOURCE, None, "the City's development applications table"),
    (toronto_applications.RESOURCE, "DESCRIPTION", "the City's development applications table"),
    (toronto_permits.LIVE, None, "the City's building permits"),
    (toronto_permits.DONE, None, "the City's building permits"),
])
def test_an_open_data_table_that_fails_leaves_the_boxes_alone(tmp_path, resource, only, words):
    doc, _ = _run(tmp_path, tables=_ckan_down(resource, only))
    assert "applications" not in doc
    (note,) = _notes(doc)
    assert note["level"] == "warn" and words in note["text"]


def test_outside_toronto_the_applications_are_not_asked_for(tmp_path):
    doc, net = _run(tmp_path, **{"FeatureServer/40/": page(FAR)})
    assert "applications" not in doc
    (note,) = _notes(doc)
    assert note["level"] == "info" and "City of Toronto only" in note["text"]
    assert not any("datastore_search" in url for url, _, _ in net.calls)


def test_parcels_are_fetched_for_the_boxes_even_when_lot_lines_are_unticked(tmp_path):
    layers = tuple(layer for layer in DEFAULT_LAYERS if layer != "parcels") + ("applications",)
    doc, net = _run(tmp_path, layers=layers)
    assert len(doc["applications"]) == 3 and not any(el["kind"] == "parcel" for el in doc["elements"])
    assert sum("FeatureServer/36/" in url for url, _, _ in net.calls) == 1


def test_the_lot_lines_parcels_serve_the_boxes_too(tmp_path):
    _, net = _run(tmp_path)
    assert sum("FeatureServer/36/" in url for url, _, _ in net.calls) == 1


def test_the_city_layers_ask_for_what_the_boxes_read_and_keep_it_as_long_as_it_lasts(tmp_path):
    _, net = _run(tmp_path)
    forms = {url: form(data) for url, _, data in net.calls if data}
    ages = {url: age for (url, _, _), age in zip(net.calls, net.ages)}
    apps, addresses = arcgis.layer_url("cot_geospatial11", 60), arcgis.layer_url("cot_geospatial27", 101)
    assert forms[apps]["outFields"] == toronto.APPLICATION_FIELDS and ages[apps] == 1
    assert forms[addresses]["outFields"] == toronto.ADDRESS_FIELDS and ages[addresses] == 7
    assert "DATE_EXPIRY" in forms[arcgis.layer_url("cot_geospatial27", 36)]["outFields"].split(",")


def test_the_applications_stage_comes_in_order(tmp_path):
    stages = []
    net = FakeNet({"toronto": _city(), ckan.SOURCE: answer(TABLES),
                   "nrcan": east_slope_tiff(Frame(LAT0, LON0), half=200.0), "osm": OSM})
    assemble(_req(tmp_path), net, progress=lambda stage, pct: stages.append(pct), now=NOW)
    assert stages == sorted(stages) and 72 in stages


def test_an_unexpected_error_costs_only_the_applications(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise ValueError("boom")
    monkeypatch.setattr(applications, "build", boom)
    doc, _ = _run(tmp_path)
    assert "applications" not in doc and "applications_date" not in doc
    assert {"toronto:parcel:55", "toronto:parcel:56", "toronto:parcel:57"} <= {el["id"] for el in doc["elements"]}
    (note,) = _notes(doc)
    assert note["level"] == "warn" and "ValueError" in note["text"] and "left as they are" in note["text"]


def test_malformed_sites_are_not_written(tmp_path, monkeypatch):
    monkeypatch.setattr(applications, "build", lambda *args, **kwargs: {"blocks": [{"id": "bad"}], "no_parcel": 0,
                                                                         "unknown": []})
    doc, _ = _run(tmp_path)
    assert "applications" not in doc and "applications_date" not in doc
    (note,) = _notes(doc)
    assert note["level"] == "warn" and "malformed" in note["text"] and "left as they are" in note["text"]
    assert ctx.validate(doc) == []


def test_a_permit_with_an_impossible_floor_area_does_not_stop_the_build(tmp_path):
    huge = dict(_permit("24 555555 BLD", "901", "Inspection", "2024-05-01", text=""), RESIDENTIAL="1e999")
    doc, _ = _run(tmp_path, tables=answer(dict(TABLES, **{toronto_permits.LIVE: [huge]})))
    assert ctx.validate(doc) == [] and _notes(doc) and all(n["level"] == "info" for n in _notes(doc))
    (site,) = [s for s in doc["applications"] if "24 555555 BLD" in s["numbers"]]
    assert site["group"] == "construction" and site["height_from"] == "not stated"
