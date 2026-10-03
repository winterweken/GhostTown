import json
import os
import sys
import tempfile

import bpy

import ghosttown
from ghosttown import ops, runner
from ghosttown.ghosttown_fetch import request as rq
from helpers import FIXTURES

SLEEPER = [sys.executable, "-c", "import time; time.sleep(30)"]


class Settings:
    def __init__(self, location, site_name="", radius="300"):
        self.location, self.site_name, self.radius = location, site_name, radius


def test_register_and_unregister_twice():
    for _ in range(2):
        ghosttown.register()
        assert hasattr(bpy.types.Scene, "ghosttown") and hasattr(bpy.ops.ghosttown, "build")
        ghosttown.unregister()
        assert not hasattr(bpy.types.Scene, "ghosttown")


def test_import_context_operator_builds_the_fixture():
    ghosttown.register()
    try:
        result = bpy.ops.ghosttown.import_context(filepath=os.path.join(FIXTURES, "mini_context.json"))
        assert result == {"FINISHED"}
        assert bpy.data.collections.get("Context · 320 Bay St") is not None
        assert "building" in bpy.context.scene.ghosttown.summary
        assert bpy.context.scene.ghosttown.credits == "© OpenStreetMap contributors"
    finally:
        ghosttown.unregister()


def test_import_context_refuses_a_broken_file():
    ghosttown.register()
    path = os.path.join(tempfile.mkdtemp(), "context.json")
    with open(path, "w") as f:
        json.dump({"schema": 9}, f)
    try:
        bpy.ops.ghosttown.import_context(filepath=path)
        raise AssertionError("expected the operator to report an error")
    except RuntimeError as e:
        assert "schema" in str(e)
    finally:
        ghosttown.unregister()


def test_parse_location():
    assert ops.parse_location("43.6497, -79.3810") == (43.6497, -79.381)
    assert ops.parse_location(" 43.6497 -79.3810 ") == (43.6497, -79.381)
    assert ops.parse_location("43.6497,-79.3810") == (43.6497, -79.381)
    for bad in ("", "Bay St", "91, 0", "43.6, -181", "1, 2, 3"):
        assert ops.parse_location(bad) is None, bad


def test_check_inputs_refuses_blank_junk_and_null_island():
    assert "latitude, longitude" in ops.check_inputs(Settings(""))
    assert "latitude, longitude" in ops.check_inputs(Settings("Bay St"))
    assert "0, 0" in ops.check_inputs(Settings("0, 0"))
    assert ops.check_inputs(Settings("43.65, -79.38")) is None


def test_make_request_is_valid_and_lands_in_the_cache():
    req = ops.make_request(Settings("43.649667, -79.380991", "320 Bay St", "150"), "/tmp/gt-cache", now=0)
    assert rq.validate(req) == []
    assert req["centre"] == {"lat": 43.649667, "lon": -79.380991} and req["radius_m"] == 150.0
    assert req["address"] == "320 Bay St" and req["out_dir"].startswith(os.path.join("/tmp/gt-cache", "runs", ""))


def test_unregister_and_file_load_cancel_running_fetches():
    ghosttown.register()
    run = runner.Run(["unused"], work_dir=tempfile.mkdtemp(), extra_paths=[], argv=SLEEPER)
    runner.ACTIVE["build"] = run
    ghosttown._on_load_pre(None)
    assert run.proc.poll() is not None and runner.ACTIVE == {}
    run2 = runner.Run(["unused"], work_dir=tempfile.mkdtemp(), extra_paths=[], argv=SLEEPER)
    runner.ACTIVE["build"] = run2
    ghosttown.unregister()
    assert run2.proc.poll() is not None and runner.ACTIVE == {}


def _fake_operator():
    from types import SimpleNamespace

    op = SimpleNamespace(_timer=None, report=lambda *args: None)
    op._stop = lambda context: ops.GHOSTTOWN_OT_build._stop(op, context)
    return op


def test_modal_passes_timer_events_through_while_the_fetch_runs():
    from types import SimpleNamespace

    ghosttown.register()
    try:
        runner.ACTIVE["build"] = runner.Run(["unused"], work_dir=tempfile.mkdtemp(), extra_paths=[], argv=SLEEPER)
        result = ops.GHOSTTOWN_OT_build.modal(_fake_operator(), bpy.context, SimpleNamespace(type="TIMER"))
        assert result == {"PASS_THROUGH"} and "build" in runner.ACTIVE
    finally:
        runner.cancel_all()
        ghosttown.unregister()


def test_cancelling_the_operator_stops_the_fetch():
    ghosttown.register()
    try:
        run = runner.Run(["unused"], work_dir=tempfile.mkdtemp(), extra_paths=[], argv=SLEEPER)
        runner.ACTIVE["build"] = run
        ops.GHOSTTOWN_OT_build.cancel(_fake_operator(), bpy.context)
        assert run.proc.poll() is not None and "build" not in runner.ACTIVE
    finally:
        runner.cancel_all()
        ghosttown.unregister()
