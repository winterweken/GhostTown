import json
import os
import sys
import tempfile
import time

from ghosttown import runner
from helpers import ROOT

VENV_SITE = os.path.join(ROOT, ".venv", "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages")
SLEEPER = [sys.executable, "-c", "import time; time.sleep(30)"]


def test_command_runs_blenders_python_on_the_fetch_package():
    assert runner.command("selftest") == [sys.executable, "-s", "-P", "-m", "ghosttown_fetch", "selftest"]


def test_environment_points_at_the_extension_and_wheels():
    env = runner.environment(["/wheels"], base={"PYTHONHOME": "x", "PYTHONPATH": "y", "PYTHONSTARTUP": "z", "PATH": "/bin"})
    assert "PYTHONHOME" not in env and "PYTHONSTARTUP" not in env
    assert env["PYTHONPATH"] == os.pathsep.join([runner.EXT_DIR, "/wheels"])
    assert env["PYTHONNOUSERSITE"] == "1" and env["PYTHONUTF8"] == "1" and env["PATH"] == "/bin"


def test_selftest_through_the_runner():
    assert os.path.isdir(VENV_SITE), "run `uv sync` first: the dev venv supplies shapely for this test"
    res = runner.run_blocking(["selftest"], work_dir=tempfile.mkdtemp(), extra_paths=[VENV_SITE])
    assert res["ok"], res
    assert res["shapely"].startswith("2.1") and res["python"].startswith("3.13")


def test_no_json_line_is_a_failure_with_the_details():
    work = tempfile.mkdtemp()
    with open(os.path.join(work, "stdout.txt"), "w") as f:
        f.write("garbage\n")
    with open(os.path.join(work, "error.txt"), "w") as f:
        f.write("Traceback (most recent call last):\nValueError: boom\n")
    res = runner.parse_result(work)
    assert res["ok"] is False and "without an answer" in res["error"] and "boom" in res["error"]


def test_the_last_json_line_is_the_answer():
    work = tempfile.mkdtemp()
    with open(os.path.join(work, "stdout.txt"), "w") as f:
        f.write('{"ok": true, "context": "/x/context.json", "notes": 0}\n')
    assert runner.parse_result(work) == {"ok": True, "context": "/x/context.json", "notes": 0}


def test_cancel_stops_a_running_process_quickly():
    run = runner.Run(["unused"], work_dir=tempfile.mkdtemp(), extra_paths=[], argv=SLEEPER)
    assert run.poll() is None
    started = time.monotonic()
    run.cancel()
    assert run.proc.poll() is not None and time.monotonic() - started < 5


def test_cancel_all_empties_active_runs():
    for key in ("a", "b"):
        runner.ACTIVE[key] = runner.Run(["unused"], work_dir=tempfile.mkdtemp(), extra_paths=[], argv=SLEEPER)
        runner.STATUS[key] = "Working…"
    procs = [run.proc for run in runner.ACTIVE.values()]
    runner.cancel_all()
    assert runner.ACTIVE == {} and runner.STATUS == {}
    assert all(p.poll() is not None for p in procs)


def test_progress_reads_the_last_line():
    work = tempfile.mkdtemp()
    assert runner.read_progress(work) is None
    with open(os.path.join(work, "progress.jsonl"), "w") as f:
        f.write(json.dumps({"stage": "OpenStreetMap", "pct": 10}) + "\n" + json.dumps({"stage": "Buildings", "pct": 60}) + "\n")
    assert runner.read_progress(work) == ("Buildings", 60)


def _put_shapely(folder):
    os.makedirs(os.path.join(folder, "shapely"), exist_ok=True)
    open(os.path.join(folder, "shapely", "__init__.py"), "w").close()


def test_ensure_wheels_resyncs_once_when_shapely_is_missing():
    folder = tempfile.mkdtemp()
    calls = []

    def refresh():
        calls.append(1)
        _put_shapely(folder)

    assert runner.ensure_wheels(folder, refresh) is True and calls == [1]
    assert runner.ensure_wheels(folder, refresh) is True and calls == [1]  # present: no re-sync


def test_ensure_wheels_reports_failure_when_the_resync_does_not_help():
    def boom():
        raise RuntimeError("sync failed")

    assert runner.ensure_wheels(tempfile.mkdtemp(), lambda: None) is False
    assert runner.ensure_wheels(tempfile.mkdtemp(), boom) is False


def test_environment_adds_extra_variables():
    env = runner.environment(["/w"], base={"PATH": "/bin"}, extra={"GHOSTTOWN_MAPILLARY_TOKEN": "t"})
    assert env["GHOSTTOWN_MAPILLARY_TOKEN"] == "t" and env["PATH"] == "/bin"


def test_a_run_hands_extra_environment_to_the_child_only():
    code = "import os, json; print(json.dumps({'ok': True, 'token': os.environ.get('GHOSTTOWN_MAPILLARY_TOKEN')}))"
    run = runner.Run(["unused"], work_dir=tempfile.mkdtemp(), extra_paths=[], argv=[sys.executable, "-c", code],
                     env_extra={"GHOSTTOWN_MAPILLARY_TOKEN": "abc"})
    deadline = time.monotonic() + 30
    while (res := run.poll()) is None and time.monotonic() < deadline:
        time.sleep(0.05)
    assert res == {"ok": True, "token": "abc"}
    assert "GHOSTTOWN_MAPILLARY_TOKEN" not in os.environ
