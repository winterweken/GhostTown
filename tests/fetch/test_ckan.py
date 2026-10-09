"""ghosttown_fetch.sources.ckan, toronto_applications and toronto_permits: the City's Open Data tables, read page by
page, stopped at a date, shape-checked and cached for the day. Ported from BHPlus tests/test_context_ckan.py."""
import json
import os
import time

import pytest

from ghosttown_fetch.net import Net, SourceError
from ghosttown_fetch.sources import ckan, toronto_applications, toronto_permits
from ckan_samples import answer, query
from fakes import FakeNet, Transport

TODAY = "2026-10-09"


def _net(serve):
    return FakeNet({ckan.SOURCE: serve})


def _raw(page):
    return lambda url, data: page if isinstance(page, bytes) else json.dumps(page).encode("utf-8")


def _ok(records, total):
    """A (status, body) answer from Transport: one page of the City's table."""
    return 200, json.dumps({"result": {"records": records, "total": total}}).encode("utf-8")


def test_the_search_url_names_the_resource_filters_fields_and_order():
    q = query(ckan.search_url("abc", offset=20, filters={"WORK": "New Building", "STATUS": ["A", "B"]},
                              fields=("X", "Y"), sort="ISSUED_DATE desc", limit=5))
    assert q["resource_id"] == "abc" and (q["offset"], q["limit"]) == ("20", "5")
    assert json.loads(q["filters"]) == {"STATUS": ["A", "B"], "WORK": "New Building"}
    assert q["fields"] == "X,Y" and q["sort"] == "ISSUED_DATE desc"
    assert ckan.search_url("abc").startswith(ckan.SEARCH + "?")


def test_read_takes_every_page_and_keeps_each_for_the_day():
    rows = [{"N": i} for i in range(25)]
    net = _net(answer({"abc": rows}))
    assert ckan.read(net, "abc", "test rows", TODAY, fields=("N",)) == rows
    assert len(net.calls) == 1 and net.ages == [ckan.MAX_AGE_DAYS]
    assert net.keys == [net.calls[0][0] + "\n" + TODAY]          # a new day never reads yesterday's pages


def test_read_pages_by_the_page_size(monkeypatch):
    monkeypatch.setattr(ckan, "PAGE_SIZE", 10)
    rows = [{"N": i} for i in range(25)]
    net = _net(answer({"abc": rows}))
    assert ckan.read(net, "abc", "test rows", TODAY) == rows and len(net.calls) == 3


def test_read_stops_at_the_first_row_stop_names_and_keeps_the_nulls_before_it():
    rows = [{"D": None}, {"D": "2026-01-02"}, {"D": "2025-12-31"}, {"D": "2025-06-01"}]
    got = ckan.read(_net(answer({"abc": rows})), "abc", "test rows", TODAY,
                    stop=lambda r: r["D"] is not None and r["D"] < "2026-01-01")
    assert got == rows[:2]


@pytest.mark.parametrize("page", [
    {"success": False, "error": {"message": "field not found"}}, {"result": {"records": "x", "total": 1}},
    {"result": {"records": [{"N": [1]}], "total": 1}}, {"result": {"records": [], "total": "many"}}, [],
    b"<html>"])
def test_read_refuses_an_answer_that_is_not_records(page):
    with pytest.raises(SourceError, match="test rows"):
        ckan.read(_net(_raw(page)), "abc", "test rows", TODAY)


def test_read_stops_past_the_row_limit():
    rows = [{"N": i} for i in range(12)]
    with pytest.raises(SourceError, match="more than 10"):
        ckan.read(_net(answer({"abc": rows})), "abc", "test rows", TODAY, max_rows=10)


def test_read_refuses_a_page_that_comes_back_empty_before_the_total(monkeypatch):
    monkeypatch.setattr(ckan, "PAGE_SIZE", 10)
    rows = [{"N": i} for i in range(25)]

    def short(url, data):
        start = int(query(url)["offset"])
        return json.dumps({"result": {"records": rows[start:start + 10] if start < 10 else [],
                                      "total": len(rows)}}).encode("utf-8")
    with pytest.raises(SourceError, match="fewer rows"):
        ckan.read(_net(short), "abc", "test rows", TODAY)


def test_read_refuses_a_table_whose_total_changes_between_pages(monkeypatch):
    monkeypatch.setattr(ckan, "PAGE_SIZE", 10)
    rows = [{"N": i} for i in range(25)]

    def reloading(url, data):
        start = int(query(url)["offset"])
        return json.dumps({"result": {"records": rows[start:start + 10],
                                      "total": 25 if start == 0 else 30}}).encode("utf-8")
    with pytest.raises(SourceError, match="changed"):
        ckan.read(_net(reloading), "abc", "test rows", TODAY)


@pytest.mark.parametrize("value, day", [("2025-07-31", "2025-07-31"), ("2026-03-09T00:00:00", "2026-03-09"),
                                        ("", None), (None, None), ("31/07/2025", None), (20250731, None)])
def test_day_reads_the_date_part_or_none(value, day):
    assert ckan.day(value) == day


def _permit(number, issued, status="Inspection", completed=None):
    return {"PERMIT_NUM": number, "REVISION_NUM": "00", "STATUS": status, "ISSUED_DATE": issued,
            "COMPLETED_DATE": completed, "WORK": "New Building"}


def test_live_permits_are_read_newest_issued_first_until_the_cutoff():
    rows = [_permit("A", None), _permit("B", "2026-01-01"), _permit("C", "2021-01-01"), _permit("D", "2019-01-01")]
    net = _net(answer({toronto_permits.LIVE: rows}))
    got = toronto_permits.get_live(net, "2020-10-09", TODAY)
    assert [r["PERMIT_NUM"] for r in got] == ["A", "B", "C"]
    q = query(net.calls[0][0])
    assert json.loads(q["filters"]) == {"STATUS": ["Inspection", "Permit Issued"], "WORK": "New Building"}
    assert q["sort"] == "ISSUED_DATE desc, _id" and "DESCRIPTION" in q["fields"].split(",")


def test_completed_permits_are_read_newest_completed_first():
    rows = [_permit("A", "2020-01-01", "Closed", "2026-02-01"), _permit("B", "2019-01-01", "Closed", "2024-06-01")]
    net = _net(answer({toronto_permits.DONE: rows}))
    got = toronto_permits.get_completed(net, "2025-01-01", TODAY)
    assert [r["PERMIT_NUM"] for r in got] == ["A"]
    q = query(net.calls[0][0])
    assert json.loads(q["filters"]) == {"STATUS": "Closed", "WORK": "New Building"}
    assert q["sort"] == "COMPLETED_DATE desc, _id"


def test_the_table_is_read_whole_without_descriptions_or_links():
    rows = [{"APPLICATION#": "26 1 STE 10 SA", "FOLDERRSN": "1", "DESCRIPTION": "long", "APPLICATION_URL": "x"}]
    net = _net(answer({toronto_applications.RESOURCE: rows}))
    got = toronto_applications.get_table(net, TODAY)
    assert got[0]["APPLICATION#"] == "26 1 STE 10 SA" and "DESCRIPTION" not in got[0]
    q = query(net.calls[0][0])
    assert q["sort"] == "_id" and "DESCRIPTION" not in q["fields"] and "APPLICATION_URL" not in q["fields"]


def test_descriptions_and_links_are_asked_for_only_the_folders_given():
    rows = [{"FOLDERRSN": "1", "DESCRIPTION": " a 9-storey building ", "APPLICATION_URL": "http://app.toronto.ca/AIC/x"},
            {"FOLDERRSN": "1", "DESCRIPTION": "again", "APPLICATION_URL": "other"},
            {"FOLDERRSN": "2", "DESCRIPTION": "", "APPLICATION_URL": None},
            {"FOLDERRSN": "3", "DESCRIPTION": "not asked", "APPLICATION_URL": ""}]
    net = _net(answer({toronto_applications.RESOURCE: rows}))
    got = toronto_applications.descriptions(net, {"1", "2", "4"}, TODAY)
    assert got == {"1": ("a 9-storey building", "http://app.toronto.ca/AIC/x"), "2": ("", ""), "4": ("", "")}
    assert json.loads(query(net.calls[0][0])["filters"]) == {"FOLDERRSN": ["1", "2", "4"]}
    assert toronto_applications.descriptions(net, set(), TODAY) == {} and len(net.calls) == 1


@pytest.mark.parametrize("get", [
    lambda net: toronto_applications.get_table(net, TODAY),
    lambda net: toronto_permits.get_live(net, "2020-10-09", TODAY),
    lambda net: toronto_permits.get_completed(net, "2025-01-01", TODAY)])
def test_a_city_wide_list_that_comes_back_empty_is_refused(get):
    net = _net(answer({toronto_applications.RESOURCE: [], toronto_permits.LIVE: [], toronto_permits.DONE: []}))
    with pytest.raises(SourceError, match="no rows"):
        get(net)


def test_a_read_prunes_its_own_folder_at_a_day():
    net = _net(answer({"abc": [{"N": 1}]}))
    ckan.read(net, "abc", "test rows", TODAY)
    assert net.pruned == [(ckan.SOURCE, 1)]


def test_a_read_deletes_the_days_older_than_a_day_from_its_folder(tmp_path):
    net = Net(str(tmp_path), transport=Transport(_ok([{"N": 1}], 1)))
    old = net.cache._path(ckan.SOURCE, "last week")
    net.cache.write(ckan.SOURCE, "last week", b"x")
    os.utime(old, (time.time() - 2 * 86400,) * 2)
    assert ckan.read(net, "abc", "test rows", TODAY) == [{"N": 1}]
    assert not os.path.exists(old)


def test_a_table_whose_total_changes_is_refused_and_its_second_page_is_not_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(ckan, "PAGE_SIZE", 10)
    rows = [{"N": i} for i in range(25)]
    t = Transport(_ok(rows[:10], 25), _ok(rows[10:20], 30), _ok(rows[10:20], 25), _ok(rows[20:], 25))
    net = Net(str(tmp_path), transport=t)
    with pytest.raises(SourceError, match="changed"):
        ckan.read(net, "abc", "test rows", TODAY)
    assert ckan.read(net, "abc", "test rows", TODAY) == rows
    assert [query(c[0])["offset"] for c in t.calls] == ["0", "10", "10", "20"]   # page one kept; two asked again


def test_a_short_page_is_refused_and_not_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(ckan, "PAGE_SIZE", 10)
    rows = [{"N": i} for i in range(25)]
    t = Transport(_ok(rows[:10], 25), _ok([], 25), _ok(rows[10:20], 25), _ok(rows[20:], 25))
    net = Net(str(tmp_path), transport=t)
    with pytest.raises(SourceError, match="fewer rows"):
        ckan.read(net, "abc", "test rows", TODAY)
    assert ckan.read(net, "abc", "test rows", TODAY) == rows
    assert [query(c[0])["offset"] for c in t.calls] == ["0", "10", "10", "20"]


def test_an_empty_city_wide_table_is_refused_and_not_kept(tmp_path):
    rows = [{"APPLICATION#": "26 1 STE 10 SA", "FOLDERRSN": "1"}]
    t = Transport(_ok([], 0), _ok(rows, 1))
    net = Net(str(tmp_path), transport=t)
    with pytest.raises(SourceError, match="no rows"):
        toronto_applications.get_table(net, TODAY)
    assert toronto_applications.get_table(net, TODAY) == rows
    assert len(t.calls) == 2
