"""ghosttown_fetch.applications: the City's development applications as sites. Ported from BHPlus
tests/test_context_applications.py; Ghost Town has no subject-site rule, and each application carries its City
link instead of a Comments text."""
import gzip
import json
import math
import os

import pytest
import shapely
from shapely.geometry import Point
from shapely.geometry import box as rect

from ghosttown_fetch import applications, boxfit, mtm27
from ghosttown_fetch.frame import Frame
from ghosttown_fetch.geom import to_local
from ghosttown_fetch.terrain import FlatTerrain
from toronto_samples import LAT0, LON0, page, point, polygon, square

KINGBAY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "kingbay")


def _props(status="Under Review", group="Open", kind="OZ", **more):
    props = {"STATUS_DESC": status, "STATUS_GROUP": group, "FOLDERTYPE": kind}
    props.update(more)
    return props


@pytest.mark.parametrize("status, group", [
    ("Under Review", "review"), ("Under Review ", "review"), ("Hearing Scheduled", "review"),
    ("NOAC Issued", "approved"), ("Council Approved", "approved"), ("Decision Issued", "approved"),
    ("OMB Appeal", "appealed"), ("Appeal Dismissed", "appealed"), ("TLAB Appeal", "appealed")])
def test_each_open_label_falls_in_its_group(status, group):
    assert applications.group_of(_props(status)) == (group, None)


@pytest.mark.parametrize("props", [
    _props("Closed", group="Closed"), _props("Withdrawn", group="Closed"), _props("Refused"),
    _props("OMB Refused"), _props("Under Review", group=None), {}])
def test_closed_and_refused_applications_are_left_out(props):
    assert applications.group_of(props) == (None, None)


@pytest.mark.parametrize("kind", ["MV", "CO", "TLAB"])
def test_committee_of_adjustment_is_its_own_group_whatever_its_label(kind):
    assert applications.group_of(_props("Conditional Consent", kind=kind)) == ("coa", None)
    assert applications.group_of(_props("Something New", kind=kind)) == ("coa", None)
    assert applications.group_of(_props("Refused", kind=kind)) == (None, None)


def test_an_unknown_open_label_counts_as_under_review_and_is_named():
    assert applications.group_of(_props("Awaiting Something")) == ("review", "Awaiting Something")


@pytest.mark.parametrize("text, metres, said", [
    ("a 66-storey (232 metres including mechanical penthouse) mixed-use building, 14,778 square metres of office",
     232.0, "description: 232 m"),
    ("a 65-storey office-retail building with a height of 300 metres, and a 3-storey pavilion",
     300.0, "description: 300 m"),
    ("the 12-storey office building with a 65-storey mixed-use building that includes a 5-storey base building, "
     "for an overall building height of 222.3 metres", 222.3, "description: 222.3 m"),
    ("a 10-storey (34.5 m) building", 34.5, "description: 34.5 m"),
    ("Height: 45 m", 45.0, "description: 45 m"),
    ("The proposal is for  a 50 storey mixed use building 34,975 square metres of residential floor area",
     160.0, "description: 50 storeys"),
    ("Site Plan Approval for a 64-storey non-residential building having a gross floor area of 163,201.0 square "
     "metres.", 204.8, "description: 64 storeys"),
    ("a 1-storey addition", 3.2, "description: 1 storey"),
])
def test_the_height_comes_from_the_description(text, metres, said):
    got = applications.height_of(text)
    assert got[0] == pytest.approx(metres) and got[1] == said


@pytest.mark.parametrize("text", [
    "rear yard setback of 7.5 m", "a 500 m² addition", "a height of 1,222 m2", "1.5 storey dwelling",
    "a 400-storey tower", "nothing here", "", None])
def test_square_metres_and_setbacks_are_never_heights(text):
    assert applications.height_of(text) is None


@pytest.mark.parametrize("text, metres", [
    ("a 45-storey tower on a 6-storey base building, base building height of 21 metres", 144.0),
    ("a 40-storey tower with a streetwall height of 20 m", 128.0),
    ("an 8-storey building with a ground floor height of 4.5 m", 25.6),
    ("a building with a maximum height of 42 m, set back 120 m from the rail corridor", 42.0),
    ("a tower 155 m tall", 155.0),
    ("a building 30 metres in height", 30.0),
    ("a height of 1,500 m", None),
])
def test_only_a_whole_building_height_counts(text, metres):
    got = applications.height_of(text)
    assert (got is None) if metres is None else (got[0] == pytest.approx(metres))


def test_a_metre_height_beats_the_storeys():
    assert applications.height_of("a 50-storey tower with a height of 180 m")[0] == pytest.approx(180.0)


@pytest.mark.parametrize("text, metres, said", [
    ("Proposal to construct a six-storey apartment building with 10 dwelling units.", 19.2, "description: 6 storeys"),
    ("BUILD SIX (6) STOREY BUILDING WITH NINETEEN (19) RESIDENTIAL UNITS", 19.2, "description: 6 storeys"),
    ("Proposal to construct a 9 sty hospital with 3 levels of below grade parking.", 28.8, "description: 9 storeys"),
    ("a forty-five storey tower", 144.0, "description: 45 storeys"),
    ("a forty five storey tower and a three-storey podium", 144.0, "description: 45 storeys"),
    ("a new eight storey student residence", 25.6, "description: 8 storeys"),
    ("a seventeen-storey hotel", 54.4, "description: 17 storeys"),
])
def test_spelled_out_bracketed_and_abbreviated_storeys_count(text, metres, said):
    got = applications.height_of(text)
    assert got[0] == pytest.approx(metres) and got[1] == said


@pytest.mark.parametrize("text", ["5 styles of brick", "two 3-storey blocks and one more", "1.5 storey dwelling"])
def test_the_new_phrasings_do_not_misread(text):
    got = applications.height_of(text)
    assert got is None or got[1] == "description: 3 storeys"


# ------------------------------------------------------------------ sites --

NOW_MS = 1790000000.0 * 1000.0
P1, P2, P3 = rect(0, 0, 40, 30), rect(40, 0, 80, 30), rect(0, 30, 40, 60)
CIRCLE = Point(0.0, 0.0).buffer(150.0, quad_segs=64)


def _parcel(g, pid, kind="COMMON", expiry=None):
    return g, {"PARCELID": pid, "FEATURE_TYPE": kind, "DATE_EXPIRY": expiry}


PARCELS = [_parcel(P1, 1), _parcel(P2, 2), _parcel(P3, 3)]


def _point(x, y, number, status="Under Review", kind="OZ", submitted=1600000000000, text="", address="1 Main St"):
    return Point(x, y), {"APPLICATION_NUMBER": number, "STATUS_GROUP": "Open", "STATUS_DESC": status,
                         "FOLDERTYPE": kind, "SUBMIT_DATE": submitted, "FOLDERDESCRIPTION": text,
                         "FULL_ADDRESS": address}


def _build(points, parcels=PARCELS, terrain=None, keep=None, clip=None, more=()):
    return applications.build(points, parcels, terrain or FlatTerrain(), keep or (lambda p: True), NOW_MS,
                              clip=clip, more=more)


def _fp(block):
    return boxfit.footprint(*block["centre_m"], block["angle_deg"], block["width_m"], block["depth_m"])


def test_applications_sharing_a_parcel_are_one_site_and_the_most_live_one_colours_it():
    got = _build([_point(10, 10, "A1OZ", "Council Approved"), _point(20, 20, "B2SA", "OMB Appeal", kind="SA")])
    (block,) = got["blocks"]
    assert block["id"] == "app:A1OZ" and block["numbers"] == ["A1OZ", "B2SA"] and block["group"] == "appealed"
    assert _fp(block).within(P1.buffer(0.75))


def test_one_application_on_two_parcels_and_a_chain_through_them_join_into_one_site():
    got = _build([_point(10, 10, "A"), _point(50, 10, "A"), _point(60, 20, "B"), _point(10, 40, "C"),
                  _point(30, 50, "B")])
    (block,) = got["blocks"]
    assert block["numbers"] == ["A", "B", "C"]
    assert _fp(block).within(shapely.union_all([P1, P2, P3]).buffer(0.75))


def test_separate_parcels_are_separate_sites_sorted_by_id():
    got = _build([_point(50, 10, "Z9"), _point(10, 10, "A1")])
    assert [b["id"] for b in got["blocks"]] == ["app:A1", "app:Z9"]


def test_a_planning_application_beats_a_committee_of_adjustment_one_and_is_the_main_one():
    got = _build([_point(10, 10, "MV1", "Hearing Scheduled", kind="MV", submitted=1700000000000),
                  _point(12, 10, "OZ1", "Council Approved", submitted=1600000000000, text="a 20-storey tower")])
    (block,) = got["blocks"]
    assert block["group"] == "approved" and block["main"] == "OZ1"
    assert block["height_m"] == pytest.approx(64.0) and block["height_from"] == "description: 20 storeys"


def test_a_committee_of_adjustment_site_starts_low_whatever_its_description_says():
    (block,) = _build([_point(10, 10, "CO1", "Conditional Consent", kind="CO",
                              text="alter the existing 26-storey building")])["blocks"]
    assert block["group"] == "coa" and block["height_m"] == pytest.approx(3.2) and block["height_from"] == "C of A"


def test_the_newest_planning_application_that_states_a_height_sets_it():
    older = _point(10, 10, "OLD", submitted=1500000000000, text="a 40-storey tower")
    newer = _point(12, 10, "NEW", kind="SA", submitted=1650000000000, text="a 45-storey tower")
    silent = _point(14, 10, "NEWEST", kind="SA", submitted=1700000000000, text="site plan revisions")
    (block,) = _build([older, newer, silent])["blocks"]
    assert block["height_m"] == pytest.approx(144.0) and block["main"] == "NEWEST"
    assert block["height_from"] == "description: 45 storeys"
    assert [a["number"] for a in block["applications"]] == ["NEWEST", "NEW", "OLD"]       # newest first


def test_no_stated_height_starts_at_one_storey():
    (block,) = _build([_point(10, 10, "A", text="redevelop the site")])["blocks"]
    assert block["height_m"] == pytest.approx(3.2) and block["height_from"] == "not stated"


def test_each_application_is_listed_with_its_date_and_addresses():
    got = _build([_point(10, 10, "A", submitted=1629950400000, address="199 BAY ST"),
                  _point(50, 10, "A", submitted=1629950400000, address="25 KING ST W")])
    (app,) = got["blocks"][0]["applications"]
    assert app == {"number": "A", "type": "OZ", "status": "Under Review", "submitted": "2021-08-26",
                   "address": "199 BAY ST; 25 KING ST W", "description": "", "source": "application",
                   "floor_area_m2": 0.0, "url": ""}


def test_the_site_at_the_centre_gets_its_box_like_any_other():
    got = _build([_point(0.5, 0.5, "MINE"), _point(50, 10, "THEIRS")])
    assert [b["id"] for b in got["blocks"]] == ["app:MINE", "app:THEIRS"] and "on_site" not in got


def test_a_map_application_keeps_its_city_link_and_drops_any_other():
    mine = _point(10, 10, "A")
    mine[1]["AIC_URL"] = "http://app.toronto.ca/AIC/index.do?folderRsn=abc"
    theirs = _point(50, 10, "B")
    theirs[1]["AIC_URL"] = "https://example.com/AIC"
    links = {a["number"]: a["url"] for b in _build([mine, theirs])["blocks"] for a in b["applications"]}
    assert links == {"A": "http://app.toronto.ca/AIC/index.do?folderRsn=abc", "B": ""}


def test_a_point_in_no_parcel_is_left_out_and_counted_once_per_application():
    got = _build([_point(500, 500, "LOST"), _point(510, 500, "LOST"), _point(10, 10, "A")])
    assert [b["id"] for b in got["blocks"]] == ["app:A"] and got["no_parcel"] == 1


def test_only_points_inside_keep_count():
    got = _build([_point(10, 10, "A"), _point(50, 10, "A")], keep=lambda p: p.x < 40)
    (block,) = got["blocks"]
    assert _fp(block).within(P1.buffer(0.75))


def test_closed_and_refused_points_are_ignored_and_unknown_labels_are_named_once():
    closed = _point(10, 10, "A", "Closed")
    closed[1]["STATUS_GROUP"] = "Closed"
    got = _build([closed, _point(50, 10, "B", "Refused"), _point(10, 40, "C", "Odd"), _point(12, 40, "D", "Odd")])
    assert [b["id"] for b in got["blocks"]] == ["app:C"] and got["blocks"][0]["numbers"] == ["C", "D"]
    assert got["unknown"] == ["Odd"]


def test_a_condo_parcel_or_an_expired_one_is_not_the_site():
    parcels = [_parcel(rect(5, 5, 15, 15), 9, kind="CONDO"), _parcel(rect(0, 0, 20, 20), 8, expiry=1.0),
               _parcel(P1, 1)]
    (block,) = _build([_point(10, 10, "A")], parcels=parcels)["blocks"]
    assert block["width_m"] * block["depth_m"] > 1000.0                       # P1, not the condo or expired one


def test_the_base_is_the_lowest_ground_under_the_box_less_thirty_centimetres():
    class Slope:
        def min_under(self, polygon):
            return 0.1 * polygon.bounds[0]
    (block,) = _build([_point(10, 10, "A")], terrain=Slope())["blocks"]
    assert block["base_m"] == pytest.approx(0.1 * _fp(block).bounds[0] - 0.3, abs=1e-3)


def test_a_ravine_parcel_far_past_the_circle_gets_a_box_inside_the_circle():
    got = _build([_point(10, 10, "A")], parcels=[_parcel(rect(-1000, 0, 1000, 200), 7)], clip=CIRCLE)
    (block,) = got["blocks"]
    assert _fp(block).within(CIRCLE.buffer(0.75)) and _fp(block).area > 10000.0


def test_a_site_whose_clipped_shape_is_empty_is_skipped():
    got = _build([_point(510, 510, "A")], parcels=[_parcel(rect(500, 500, 520, 520), 7)], clip=CIRCLE)
    assert got["blocks"] == []


def _recorded(name):
    with gzip.open(os.path.join(KINGBAY, name), "rb") as f:
        return json.loads(f.read())["features"]


def test_king_and_bay_is_one_sixty_four_storey_site_over_two_parcels():
    frame = Frame(43.6487, -79.3806)
    points = applications.features(_recorded("applications.json.gz"), frame)
    parcels = applications.features(_recorded("parcels.json.gz"), frame)
    got = applications.build(points, parcels, FlatTerrain(), CIRCLE.contains, NOW_MS)
    (block,) = got["blocks"]
    assert block["id"] == "app:21204526STE13SA" and block["group"] == "review"
    assert block["height_m"] == pytest.approx(204.8) and block["base_m"] == pytest.approx(-0.3)
    two = shapely.union_all([g for g, p in parcels if p["PARCELID"] in (5471200, 5470818)])
    assert _fp(block).within(two.buffer(0.75))
    assert block["applications"][0]["url"] == \
        "http://app.toronto.ca/AIC/index.do?folderRsn=Ty0oJaST6ds4pVkViotbpA%3D%3D"
    assert got["no_parcel"] == 0 and got["unknown"] == []


def test_features_are_local_and_leave_out_what_has_no_geometry_or_no_area():
    answer = json.loads(page(square(0, 0, 10, PARCELID=1), point(5, 5, ADDRESS_POINT_ID=2),
                             polygon([(0, 0), (10, 0), (20, 0)], PARCELID=3),
                             {"type": "Feature", "geometry": None, "properties": {"PARCELID": 4}}))["features"]
    got = applications.features(answer, Frame(LAT0, LON0))
    assert [p for _, p in got] == [{"PARCELID": 1}, {"ADDRESS_POINT_ID": 2}]
    assert got[0][0].area == pytest.approx(100.0, rel=1e-3)
    assert got[1][0].coords[0] == pytest.approx((5.0, 5.0), abs=1e-3)


# ------------------------------------------------- permits and the table --

def _permit(x, y, number="21 123456 BLD", group="construction", text="", floor=0.0, date="2023-05-03",
            status="Inspection", kind="Apartment Building"):
    return Point(x, y), applications.status_point(number, "permit", group, kind, status, date, description=text,
                                                  address="1 Main St", floor_area_m2=floor)


def test_a_live_permit_beats_an_approved_application_and_leads_the_box():
    got = _build([_point(10, 10, "OZ1", "NOAC Issued", text="a 20-storey tower")],
                 more=[_permit(12, 12, text="a 21 storey apartment building")])
    (block,) = got["blocks"]
    assert block["group"] == "construction" and block["main"] == "21 123456 BLD"
    assert block["numbers"] == ["21 123456 BLD", "OZ1"]
    assert block["height_m"] == pytest.approx(67.2) and block["height_from"] == "permit: 21 storeys"
    assert [a["number"] for a in block["applications"]] == ["21 123456 BLD", "OZ1"]
    permit = block["applications"][0]
    assert permit == {"number": "21 123456 BLD", "type": "Apartment Building", "status": "Inspection",
                      "submitted": "2023-05-03", "address": "1 Main St", "description": "a 21 storey apartment building",
                      "source": "permit", "floor_area_m2": 0.0, "url": ""}


def test_a_recently_built_site_beats_an_application_under_review():
    got = _build([_point(10, 10, "SA1", "Under Review")],
                 more=[_permit(12, 12, "17 1 BLD", "built", status="Closed", date="2026-03-01")])
    (block,) = got["blocks"]
    assert block["group"] == "built" and block["main"] == "17 1 BLD"


def test_a_site_with_a_live_and_a_completed_permit_is_under_construction():
    got = _build([], more=[_permit(10, 10, "17 1 BLD", "built", text="a 6 storey building", status="Closed",
                                   date="2025-06-01"),
                           _permit(12, 12, "22 9 BLD", text="a 30 storey tower")])
    (block,) = got["blocks"]
    assert block["group"] == "construction" and block["numbers"] == ["17 1 BLD", "22 9 BLD"]
    assert block["main"] == "22 9 BLD" and block["height_m"] == pytest.approx(96.0)


def test_with_no_stated_height_a_construction_site_takes_its_applications_then_its_floor_area():
    (block,) = _build([_point(10, 10, "OZ1", "NOAC Issued", text="a 12-storey building")],
                      more=[_permit(12, 12, floor=50000.0)])["blocks"]
    assert block["height_from"] == "description: 12 storeys"
    (block,) = _build([], more=[_permit(12, 12, floor=4000.0)])["blocks"]
    storeys = math.ceil(4000.0 / (block["width_m"] * block["depth_m"]))
    assert block["height_from"] == "estimated from floor area: {0} storey{1}".format(storeys, "" if storeys == 1 else "s")
    assert block["height_m"] == pytest.approx(storeys * 3.2)
    (block,) = _build([], more=[_permit(12, 12)])["blocks"]
    assert block["height_from"] == "not stated" and block["height_m"] == pytest.approx(3.2)


def test_the_floor_area_estimate_is_at_least_one_storey_and_at_most_the_cap():
    (low,) = _build([], more=[_permit(12, 12, floor=1.0)])["blocks"]
    (high,) = _build([], more=[_permit(12, 12, floor=1e9)])["blocks"]
    assert low["height_m"] == pytest.approx(3.2)
    assert high["height_m"] == pytest.approx(applications.MAX_STOREYS * 3.2)


def test_permit_points_go_through_keep_like_the_map_points():
    assert _build([], more=[_permit(50, 10)], keep=lambda p: p.x < 40)["blocks"] == []


# --------------------------------------------------------------- the table --

FRAME = Frame(43.7615, -79.4111)


def _table_row(number="26 100001 NNY 23 SA", status="Under Review", x="311948.715", y="4846544.07",
               folder="9999999", kind="SA", submitted="2026-03-09T00:00:00"):
    return {"APPLICATION#": number, "APPLICATION_TYPE": kind, "STATUS": status, "DATE_SUBMITTED": submitted,
            "X": x, "Y": y, "FOLDERRSN": folder, "STREET_NUM": "4800", "STREET_NAME": "YONGE", "STREET_TYPE": "ST",
            "STREET_DIRECTION": " "}


def test_a_table_row_becomes_a_status_point_at_its_converted_place():
    ((g, sp),) = applications.table_points([_table_row()], FRAME, set())
    lon, lat = mtm27.to_lonlat(311948.715, 4846544.07)
    assert g.distance(to_local(Point(lon, lat), FRAME)) < 1e-6
    assert sp == applications.status_point("26100001NNY23SA", "application", "review", "SA", "Under Review",
                                           "2026-03-09", address="4800 YONGE ST", folderrsn="9999999")


def test_a_table_row_the_map_has_is_left_to_the_map():
    assert applications.table_points([_table_row(folder="4083248")], FRAME, {"4083248"}) == []


@pytest.mark.parametrize("status", ["Closed", "Refused", "OMB Refused", "Withdrawn"])
def test_closed_and_refused_table_rows_are_left_out(status):
    assert applications.table_points([_table_row(status=status)], FRAME, set()) == []


def test_table_statuses_are_trimmed_and_an_unknown_one_is_named():
    ((_, sp),) = applications.table_points([_table_row(status="Under Review ")], FRAME, set())
    assert sp["group"] == "review" and sp["unknown"] is None
    ((_, sp),) = applications.table_points([_table_row(status="Circulated")], FRAME, set())
    assert sp["group"] == "review" and sp["unknown"] == "Circulated"


@pytest.mark.parametrize("x, y", [("", "4846544.07"), (None, None), ("0", "0"), ("abc", "1"), ("nan", "4846544"),
                                  ("-5", "4846544")])
def test_table_rows_without_usable_coordinates_are_skipped(x, y):
    assert applications.table_points([_table_row(x=x, y=y)], FRAME, set()) == []


@pytest.mark.parametrize("submitted", [None, "", "09/03/2026", 20260309])
def test_a_table_row_with_an_unreadable_submission_date_is_skipped(submitted):
    assert applications.table_points([_table_row(submitted=submitted)], FRAME, set()) == []


def test_a_table_row_without_a_number_or_folder_is_skipped():
    assert applications.table_points([_table_row(number="  ")], FRAME, set()) == []
    assert applications.table_points([_table_row(folder=None)], FRAME, set()) == []


@pytest.mark.parametrize("value, folder", [(4083248, "4083248"), (4083248.0, "4083248"), ("5793154", "5793154"),
                                           (" 5793154 ", "5793154"), (None, ""), ("x1", ""), (True, "")])
def test_folder_of_reads_both_sources(value, folder):
    assert applications.folder_of(value) == folder


def test_an_unknown_table_label_reaches_the_build_result():
    more = applications.table_points([_table_row(status="Circulated", x="314092.389", y="4833631.921")],
                                     Frame(43.644570184, -79.384621957), set())
    parcel = (rect(-50, -50, 50, 50), {"PARCELID": 1, "FEATURE_TYPE": "COMMON", "DATE_EXPIRY": None})
    got = applications.build([], [parcel], FlatTerrain(), lambda p: True, NOW_MS, more=more)
    assert got["unknown"] == ["Circulated"] and got["blocks"][0]["numbers"] == ["26100001NNY23SA"]
