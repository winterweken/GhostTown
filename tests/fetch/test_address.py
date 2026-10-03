import gzip
import json
from pathlib import Path

import pytest

from ghosttown_fetch import cli
from ghosttown_fetch.net import SourceError
from ghosttown_fetch.sources import address
from fakes import FakeNet, form

FIX = Path(__file__).parent / "fixtures"
ANSWER = json.dumps({"features": [{"attributes": {"ADDRESS_FULL": "320 Bay St", "LATITUDE": 43.649667039,
                                                  "LONGITUDE": -79.380991173}}]}).encode()


@pytest.mark.parametrize("text, norm", [
    ("320 Bay St", "320 BAY ST"),
    ("320 Bay Street, Toronto, ON", "320 BAY ST"),
    ("100 Queen Street West", "100 QUEEN ST W"),
    ("57 winnifred avenue", "57 WINNIFRED AVE"),
    ("1 North York Boulevard", "1 NORTH YORK BLVD"),
    ("1 Avenue Road", "1 AVENUE RD"),
    ("12 St. Clair Ave W", "12 ST CLAIR AVE W"),
    ("O'Connor Dr", "O'CONNOR DR"),
    ("320 Bay Street Toronto ON", "320 BAY ST"),
    ("100 Queen St W Toronto Ontario M5H 2N2", "100 QUEEN ST W"),
    ("100 queen street west toronto on m5h2n2 canada", "100 QUEEN ST W"),
    ("100 Toronto St", "100 TORONTO ST"),
    ("100 Ontario", "100 ONTARIO"),
    ("   ", ""),
])
def test_normalise(text, norm):
    assert address.normalise(text) == norm


def test_quotes_are_escaped_in_the_query():
    assert "LIKE 'O''CONNOR DR%'" in address.build_params("O'CONNOR DR", 5)["where"]


def test_search_returns_labelled_coordinates():
    net = FakeNet({"toronto": ANSWER})
    results = address.search(net, "320 Bay Street")
    assert results == [{"label": "320 Bay St", "lat": 43.649667039, "lon": -79.380991173, "source": "toronto"}]
    url, source, data = net.calls[0]
    assert url.endswith("/cot_geospatial27/FeatureServer/101/query") and source == "toronto"
    assert form(data)["where"] == "UPPER(ADDRESS_FULL) LIKE '320 BAY ST%'" and form(data)["resultRecordCount"] == "5"


def test_blank_text_makes_no_request():
    net = FakeNet({})
    assert address.search(net, " , ") == [] and net.calls == []


def test_recorded_answer_for_320_bay_st():
    body = gzip.decompress((FIX / "bay" / "toronto_address.json.gz").read_bytes())
    results = address.search(FakeNet({"toronto": body}), "320 Bay St")
    assert results[0]["label"] == "320 Bay St"
    assert results[0]["lat"] == pytest.approx(43.649667, abs=1e-5) and results[0]["lon"] == pytest.approx(-79.380991, abs=1e-5)


def _one_line(capsys):
    out = capsys.readouterr()
    lines = out.out.strip().splitlines()
    assert len(lines) == 1 and out.err == ""
    return json.loads(lines[0])


def test_cli_geocode_prints_one_line(tmp_path, capsys):
    code = cli.main(["geocode", str(tmp_path), "320 Bay St"], net_factory=lambda c, fresh=False: FakeNet({"toronto": ANSWER}))
    res = _one_line(capsys)
    assert code == 0 and res["ok"] and res["results"][0]["label"] == "320 Bay St"


def test_cli_geocode_with_no_match_is_ok_and_empty(tmp_path, capsys):
    empty = json.dumps({"features": []}).encode()
    code = cli.main(["geocode", str(tmp_path), "1 Nowhere Lane"], net_factory=lambda c, fresh=False: FakeNet({"toronto": empty}))
    assert code == 0 and _one_line(capsys) == {"ok": True, "results": []}


def test_cli_geocode_reports_a_failure_in_one_sentence(tmp_path, capsys):
    broken = SourceError("City of Toronto answered HTTP 503; try again in a minute.")
    code = cli.main(["geocode", str(tmp_path), "320 Bay St"], net_factory=lambda c, fresh=False: FakeNet({"toronto": broken}))
    res = _one_line(capsys)
    assert code == 1 and res == {"ok": False, "error": "City of Toronto answered HTTP 503; try again in a minute."}
