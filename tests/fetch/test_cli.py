import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ghosttown_fetch import cli
from ghosttown_fetch import request as rq
from ghosttown_fetch.net import SourceError
from fakes import FakeNet, router
from osm_samples import LAT0, LON0, body, square, way
from toronto_samples import page as city_page, polygon as city_polygon

GHOSTTOWN_DIR = str(Path(__file__).resolve().parents[2] / "ghosttown")


def _write_req(tmp_path, **changes):
    req = rq.build(centre={"lat": LAT0, "lon": LON0}, radius_m=150, cache_dir=str(tmp_path / "cache"),
                   out_dir=str(tmp_path / "run"), layers=["buildings"])
    req.update(changes)
    path = tmp_path / "request.json"
    path.write_text(json.dumps(req), encoding="utf-8")
    return path


FAR = city_polygon([(5000, 5000), (6000, 5000), (6000, 6000), (5000, 6000)])


def _net(answer):
    """A site outside Toronto: the City boundary says 'elsewhere' and OSM gives the answer."""
    return lambda cache_dir, fresh=False: FakeNet({"osm": answer, "toronto": router({"FeatureServer/40/": city_page(FAR)})})


def _one_line(capsys):
    out = capsys.readouterr()
    lines = out.out.strip().splitlines()
    assert len(lines) == 1, out.out
    assert out.err == ""
    lines[0].encode("ascii")
    return json.loads(lines[0])


def test_selftest_reports_versions(capsys):
    assert cli.main(["selftest"]) == 0
    res = _one_line(capsys)
    assert res["ok"] and res["shapely"].startswith("2.1") and res["geos"] and res["numpy"] and res["pillow"]


def test_fetch_writes_context_progress_and_one_line(tmp_path, capsys):
    path = _write_req(tmp_path)
    code = cli.main(["fetch", str(path)], net_factory=_net(body(way(1, square(0, 0, 10), {"building": "yes"}))))
    res = _one_line(capsys)
    assert code == 0 and res["ok"]
    with open(res["context"], encoding="utf-8") as f:
        doc = json.load(f)
    assert doc["counts"] == {"building_guessed": 1} and res["notes"] == len(doc["notes"])
    progress = (tmp_path / "run" / "progress.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(progress) >= 2 and json.loads(progress[-1])["pct"] >= 90


def test_an_invalid_request_fails_with_an_error_file(tmp_path, capsys):
    path = _write_req(tmp_path, radius_m=5)
    assert cli.main(["fetch", str(path)]) == 1
    res = _one_line(capsys)
    assert not res["ok"] and "radius_m" in res["error"]
    assert (tmp_path / "run" / "error.txt").is_file()


def test_an_unreadable_request_fails_cleanly(tmp_path, capsys):
    assert cli.main(["fetch", str(tmp_path / "missing.json")]) == 1
    assert "Couldn't read the request" in _one_line(capsys)["error"]


def test_all_sources_failing_is_exit_1(tmp_path, capsys):
    path = _write_req(tmp_path)
    code = cli.main(["fetch", str(path)], net_factory=_net(SourceError("OpenStreetMap answered HTTP 504; try again in a minute.")))
    res = _one_line(capsys)
    assert code == 1 and "504" in res["error"]
    assert (tmp_path / "run" / "error.txt").is_file()


def test_a_crash_is_still_one_line_and_stderr_stays_empty(tmp_path, capsys, monkeypatch):
    def boom(*args, **kwargs):
        print("noise on stderr", file=sys.stderr)
        raise RuntimeError("kaboom")

    monkeypatch.setattr("ghosttown_fetch.assemble.assemble", boom)
    path = _write_req(tmp_path)
    assert cli.main(["fetch", str(path)], net_factory=_net(b"{}")) == 1
    res = _one_line(capsys)
    assert "kaboom" in res["error"]
    assert "Traceback" in (tmp_path / "run" / "error.txt").read_text(encoding="utf-8")


def test_usage_error(capsys):
    assert cli.main(["nonsense"]) == 1
    assert "Usage" in _one_line(capsys)["error"]


def test_module_entry_point_prints_one_json_line():
    env = {**os.environ, "PYTHONPATH": GHOSTTOWN_DIR}
    out = subprocess.run([sys.executable, "-s", "-P", "-m", "ghosttown_fetch", "selftest"],
                         env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stderr == ""
    assert json.loads(out.stdout.strip())["ok"] is True


def _look_req(tmp_path, data, **changes):
    from look_samples import request

    path = tmp_path / "look_request.json"
    path.write_text(json.dumps(request(tmp_path, data, **changes)), encoding="utf-8")
    return path


def test_look_writes_look_json_and_one_line(tmp_path, capsys, monkeypatch):
    from look_samples import fake_net, street

    data = street()
    monkeypatch.setenv("GHOSTTOWN_MAPILLARY_TOKEN", "MLY|secret")
    code = cli.main(["look", str(_look_req(tmp_path, data))], net_factory=lambda cache_dir, fresh=False: fake_net(data))
    res = _one_line(capsys)
    assert code == 0 and res["ok"] and res["from_photos"] == 1 and res["guessed"] == 1 and res["years"] == [2024, 2024]
    with open(res["look"], encoding="utf-8") as f:
        assert json.load(f)["buildings"]["test:1"]["source"] == "photos"
    assert (tmp_path / "run" / "progress.jsonl").is_file()


def test_look_without_a_token_says_where_to_add_it(tmp_path, capsys, monkeypatch):
    from look_samples import street

    monkeypatch.delenv("GHOSTTOWN_MAPILLARY_TOKEN", raising=False)
    assert cli.main(["look", str(_look_req(tmp_path, street()))]) == 1
    assert "Mapillary token" in _one_line(capsys)["error"]


def test_a_rejected_token_is_one_plain_sentence(tmp_path, capsys, monkeypatch):
    from look_samples import fake_net, street

    data = street()
    monkeypatch.setenv("GHOSTTOWN_MAPILLARY_TOKEN", "MLY|secret")
    code = cli.main(["look", str(_look_req(tmp_path, data))],
                    net_factory=lambda cache_dir, fresh=False: fake_net(data, token_ok=False))
    assert code == 1 and _one_line(capsys)["error"] == "Mapillary refused the token; check it in Preferences."
    assert (tmp_path / "run" / "error.txt").is_file()


def test_ground_heights_that_cant_be_had_are_one_plain_sentence(tmp_path, capsys, monkeypatch):
    from look_samples import fake_net, street
    from ghosttown_fetch import look

    data = street()
    monkeypatch.setenv("GHOSTTOWN_MAPILLARY_TOKEN", "made-up-token")
    monkeypatch.setattr(look.terrain_mod, "load", lambda net, frame, r: (look.terrain_mod.FlatTerrain(), None))
    code = cli.main(["look", str(_look_req(tmp_path, data, ground_at_centre_m=100.0))],
                    net_factory=lambda cache_dir, fresh=False: fake_net(data))
    assert code == 1
    assert _one_line(capsys)["error"] == "Ground heights couldn't be fetched for the photos; try again in a minute."
    assert (tmp_path / "run" / "error.txt").is_file()


def test_mapillary_stopping_partway_is_one_plain_sentence(tmp_path, capsys, monkeypatch):
    from look_samples import fake_net, street
    from ghosttown_fetch.net import SourceError
    from ghosttown_fetch.sources import mapillary

    data = street()
    monkeypatch.setenv("GHOSTTOWN_MAPILLARY_TOKEN", "made-up-token")
    monkeypatch.setattr(mapillary, "OUTAGE_FAILURES", 3)
    net = fake_net(data)
    normal = net.answers["mapillary"]
    away = SourceError("Mapillary couldn't be reached (timed out); try again in a minute.")
    net.answers["mapillary"] = lambda url, body: away if "cdn.example/" in url else normal(url, body)
    code = cli.main(["look", str(_look_req(tmp_path, data))], net_factory=lambda cache_dir, fresh=False: net)
    assert code == 1 and _one_line(capsys)["error"] == "Mapillary couldn't be reached; try again in a minute."
    assert (tmp_path / "run" / "error.txt").is_file()


def test_an_invalid_look_request_fails_with_an_error_file(tmp_path, capsys, monkeypatch):
    from look_samples import street

    monkeypatch.setenv("GHOSTTOWN_MAPILLARY_TOKEN", "MLY|secret")
    path = _look_req(tmp_path, street(), budget_photos=1)
    assert cli.main(["look", str(path)]) == 1
    assert "budget_photos" in _one_line(capsys)["error"] and (tmp_path / "run" / "error.txt").is_file()


@pytest.mark.parametrize("token", [
    pytest.param("MLY|12\n34|ab", id="newline"),
    pytest.param("MLY|12 34|ab", id="space"),
    pytest.param("MLY|12\x7f34|ab", id="control"),
    pytest.param("MLY|12\N{RIGHT SINGLE QUOTATION MARK}34|ab", id="non-ascii"),
])
def test_a_token_that_cannot_go_in_a_header_is_refused_and_never_echoed(tmp_path, capsys, monkeypatch, token):
    from look_samples import street

    # Left alone, a newline makes http.client raise a ValueError that quotes the header, and the answer copies it.
    monkeypatch.setenv("GHOSTTOWN_MAPILLARY_TOKEN", token)
    assert cli.main(["look", str(_look_req(tmp_path, street()))]) == 1
    res = _one_line(capsys)
    assert res["error"] == "The Mapillary token isn't valid; check it in Preferences."
    run = tmp_path / "run"
    assert (run / "error.txt").is_file()
    written = [json.dumps(res)] + [p.read_text(encoding="utf-8") for p in run.rglob("*") if p.is_file()]
    # The quoted newline comes out as \n or \\n, never raw, so the halves either side of it are what catch a leak.
    for text in written:
        for piece in ("MLY|12", "34|ab", "12\n34", "12\\n34"):
            assert piece not in text
