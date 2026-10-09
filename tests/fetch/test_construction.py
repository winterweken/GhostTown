"""ghosttown_fetch.construction: the City's building permits as status points: houses left out, revisions folded,
the live and completed cutoffs, and each permit placed at its address point. Ported from BHPlus
tests/test_context_construction.py."""
import pytest
from shapely.geometry import Point

from ghosttown_fetch import construction

TODAY = "2026-10-08"


def _row(number="21 123456 BLD", revision="00", status="Inspection", issued="2023-05-03", completed=None,
         kind="New Building", structure="Apartment Building", geo="30123033", num="1141", street="BLOOR",
         street_type="ST", direction="W", text="a 21 storey apartment building", **floors):
    row = {"PERMIT_NUM": number, "REVISION_NUM": revision, "STATUS": status, "ISSUED_DATE": issued,
           "COMPLETED_DATE": completed, "PERMIT_TYPE": kind, "STRUCTURE_TYPE": structure, "GEO_ID": geo,
           "STREET_NUM": num, "STREET_NAME": street, "STREET_TYPE": street_type, "STREET_DIRECTION": direction,
           "DESCRIPTION": text}
    row.update(floors)
    return row


def _address(x, y, pid, number, name, kind="St", direction="W"):
    return Point(x, y), {"ADDRESS_POINT_ID": pid, "LO_NUM": number, "LINEAR_NAME": name,
                         "LINEAR_NAME_TYPE": kind, "LINEAR_NAME_DIR": direction}


ADDRESSES = construction.Addresses([
    _address(10, 10, 30123033, 1141, "Bloor"), _address(30, 10, 30123040, 1151, "Bloor"),
    _address(50, 10, 30123050, 1177, "Danforth", kind="Ave", direction=None),
    _address(70, 10, 30123060, 200, "Brown's Line", kind=None, direction=None),
    _address(90, 10, 30123070, 12, "The Queensway", kind=None, direction=None)])


@pytest.mark.parametrize("kind, structure, house", [
    ("New Houses", "Apartment Building", True), ("New Building", "SFD - Detached", True),
    ("New Building", " SFD - Townhouse ", True), ("New Building", "2 Unit - Detached", True),
    ("New Building", "3+ Unit - Semi-detached", True), ("New Building", "Apartment Building", False),
    ("Residential Building Permit", "Stacked Townhouses", False), ("New Building", None, False)])
def test_houses_are_new_house_permits_and_house_structures(kind, structure, house):
    assert construction.is_house(_row(kind=kind, structure=structure)) is house


def test_revisions_fold_into_their_permit():
    rows = [_row("A", "01", issued="2024-01-01"), _row("A", "00", issued="2023-01-01"),
            _row("B", "02"), _row("B", "01", issued="2022-02-02")]
    folded = construction.fold(rows)
    assert [(r["PERMIT_NUM"], r["REVISION_NUM"]) for r in folded] == [("A", "00"), ("B", "01")]


@pytest.mark.parametrize("iso, n, want", [("2026-10-08", 6, "2020-10-08"), ("2028-02-29", 6, "2022-02-28"),
                                          ("2026-01-01", 10, "2016-01-01")])
def test_years_before_handles_the_edges(iso, n, want):
    assert construction.years_before(iso, n) == want


def test_live_permits_are_the_ones_issued_within_six_years():
    rows = [_row("NEW", issued="2025-01-01"), _row("EDGE", issued="2020-10-08"), _row("OLD", issued="2003-04-01"),
            _row("NONE", issued=None), _row("ODD", status="Under Review", issued="2025-01-01")]
    assert [r["PERMIT_NUM"] for r in construction.live(rows, TODAY)] == ["NEW", "EDGE"]


def test_completed_permits_finished_since_the_massing_year_and_were_issued_within_ten_years_of_it():
    rows = [_row("DONE", status="Closed", issued="2022-02-23", completed="2026-03-01"),
            _row("EARLY", status="Closed", issued="2022-02-23", completed="2024-12-31"),
            _row("TIDY", status="Closed", issued="2001-05-01", completed="2026-06-01"),
            _row("EDGE", status="Closed", issued="2015-01-01", completed="2025-01-01"),
            _row("DORMANT", status="Closed - Dormant", issued="2022-01-01", completed="2026-01-01"),
            _row("NODATE", status="Closed", issued=None, completed="2026-01-01")]
    assert [r["PERMIT_NUM"] for r in construction.completed(rows, "2025")] == ["DONE", "EDGE"]
    assert [r["PERMIT_NUM"] for r in construction.completed(rows, 2025)] == ["DONE", "EDGE"]


def test_the_floor_area_adds_every_use_and_counts_text_as_zero():
    assert construction.floor_area(_row(RESIDENTIAL=1201.56, MERCANTILE="69.4", ASSEMBLY="n/a", INDUSTRIAL=None)) \
        == pytest.approx(1270.96)
    assert construction.floor_area(_row()) == 0.0


def test_a_floor_area_that_is_not_finite_counts_zero():
    assert construction.floor_area(_row(RESIDENTIAL="1e999", MERCANTILE="inf", ASSEMBLY="nan", INDUSTRIAL=50.0)) \
        == 50.0
    assert construction.floor_area(_row(RESIDENTIAL=float("inf"), MERCANTILE=float("nan"))) == 0.0


def test_a_permit_is_at_its_address_point_by_id():
    assert ADDRESSES.locate(_row(geo="30123040", num="1")).coords[0] == (30.0, 10.0)


def test_a_retired_id_falls_back_to_the_street_number_and_name():
    assert ADDRESSES.locate(_row(geo="6710176")).coords[0] == (10.0, 10.0)                # 1141 Bloor St W
    assert ADDRESSES.locate(_row(geo="1", num="200", street="BROWNS LINE", street_type="",
                                 direction="")).coords[0] == (70.0, 10.0)
    assert ADDRESSES.locate(_row(geo="1", num="12", street="THE QUEENSWAY", street_type="  ",
                                 direction="")).coords[0] == (90.0, 10.0)


def test_a_ranged_or_suffixed_street_number_matches_its_leading_number():
    assert ADDRESSES.locate(_row(geo=None, num="1177-1181", street="DANFORTH", street_type="AVE",
                                 direction="")).coords[0] == (50.0, 10.0)
    assert ADDRESSES.locate(_row(geo="", num="1151A")).coords[0] == (30.0, 10.0)


def test_a_different_street_type_or_direction_does_not_match():
    assert ADDRESSES.locate(_row(geo="1", street_type="AVE")) is None
    assert ADDRESSES.locate(_row(geo="1", direction="E")) is None


def test_nearby_says_a_permit_should_have_been_here():
    assert ADDRESSES.nearby(_row(geo="1", num="1145")) is True               # Bloor, between 1141 and 1151
    assert ADDRESSES.nearby(_row(geo="1", num="5000")) is False              # Bloor, far past this circle
    assert ADDRESSES.nearby(_row(geo="1", street="YONGE")) is False          # not a street here


def test_nearby_minds_the_direction_like_locate_does():
    assert ADDRESSES.nearby(_row(geo="1", num="1145", direction="E")) is False   # Bloor St E: across town
    assert ADDRESSES.nearby(_row(geo="1", num="1145", direction="")) is True     # no direction: may be this one


def test_points_are_the_kept_non_house_permits_and_count_houses_and_the_unplaced():
    rows = [_row("APT", text="a 21 storey apartment building", RESIDENTIAL=21000),
            _row("HOUSE", kind="New Houses", geo="30123040"),
            _row("FAR", geo="30123070"),                                     # keep() refuses it
            _row("LOST", geo="1", num="1145"),
            _row("ELSEWHERE", geo="1", street="YONGE", num="5000")]
    got, houses, unplaced = construction.points(rows, "construction", ADDRESSES, keep=lambda p: p.x < 80)
    assert (houses, unplaced) == (1, 1)
    ((g, sp),) = got
    assert g.coords[0] == (10.0, 10.0)
    assert sp == {"number": "APT", "source": "permit", "group": "construction", "type": "Apartment Building",
                  "status": "Inspection", "date": "2023-05-03", "description": "a 21 storey apartment building",
                  "address": "1141 BLOOR ST W", "floor_area_m2": 21000.0, "folderrsn": "", "unknown": None,
                  "url": ""}


def test_a_completed_permit_is_dated_by_its_completion():
    ((_, sp),), _, _ = construction.points([_row("DONE", status="Closed", completed="2026-03-01")], "built",
                                           ADDRESSES, keep=lambda p: True)
    assert sp["group"] == "built" and sp["date"] == "2026-03-01"
