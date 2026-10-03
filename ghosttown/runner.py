"""Run the fetcher as `python -s -P -m ghosttown_fetch ...` on Blender's own Python.

No threads: the build operator polls Run.poll() from a modal timer. Blender installs every
extension's wheels into one shared site-packages folder; it goes on PYTHONPATH after this
extension's own folder (which holds the ghosttown_fetch package).
"""
import json
import os
import subprocess
import sys
import time

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
CANCEL_GRACE_S = 3

ACTIVE = {}  # key -> Run; module state, so nothing stale is ever saved in a .blend
STATUS = {}  # key -> status text for the panel


def wheels_site_packages():
    import bpy

    return os.path.join(bpy.utils.user_resource("EXTENSIONS"), ".local", "lib",
                        f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages")


def ensure_wheels(wheels_dir, refresh, package="shapely"):
    """True when `package` is unpacked in the shared wheels folder. Blender's own extension syncs
    can drop an extension's unpacked wheels while the extension stays enabled; when that happens,
    ask Blender to re-sync once (`refresh`) before giving up."""
    def present():
        return os.path.isfile(os.path.join(wheels_dir, package, "__init__.py"))

    if present():
        return True
    try:
        refresh()
    except Exception:
        return False
    return present()


def command(*args):
    return [sys.executable, "-s", "-P", "-m", "ghosttown_fetch", *(str(a) for a in args)]


def environment(extra_paths, base=None):
    env = dict(os.environ if base is None else base)
    for key in ("PYTHONHOME", "PYTHONSTARTUP", "PYTHONPATH"):
        env.pop(key, None)
    env["PYTHONPATH"] = os.pathsep.join([EXT_DIR, *extra_paths])
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONUTF8"] = "1"
    return env


class Run:
    def __init__(self, args, *, work_dir, extra_paths, argv=None):
        os.makedirs(work_dir, exist_ok=True)
        self.work_dir = work_dir
        self._stdout = open(os.path.join(work_dir, "stdout.txt"), "wb")
        self._stderr = open(os.path.join(work_dir, "stderr.txt"), "wb")
        self.proc = subprocess.Popen(
            argv or command(*args), cwd=work_dir, env=environment(extra_paths),
            stdin=subprocess.DEVNULL, stdout=self._stdout, stderr=self._stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def poll(self):
        """None while running, else the parsed answer."""
        if self.proc.poll() is None:
            return None
        self._close()
        return parse_result(self.work_dir)

    def cancel(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=CANCEL_GRACE_S)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self._close()

    def _close(self):
        for f in (self._stdout, self._stderr):
            if not f.closed:
                f.close()


def parse_result(work_dir):
    lines = [line for line in _read(os.path.join(work_dir, "stdout.txt")).splitlines() if line.strip()]
    if lines:
        try:
            result = json.loads(lines[-1])
        except ValueError:
            result = None
        if isinstance(result, dict) and "ok" in result:
            return result
    detail = (_read(os.path.join(work_dir, "error.txt")) or _read(os.path.join(work_dir, "stderr.txt"))).strip()
    message = "The fetcher stopped without an answer."
    if detail:
        message += " " + detail.splitlines()[-1][:300]
    return {"ok": False, "error": message}


def read_progress(work_dir):
    lines = _read(os.path.join(work_dir, "progress.jsonl")).splitlines()
    if not lines:
        return None
    try:
        last = json.loads(lines[-1])
        return last["stage"], int(last["pct"])
    except (ValueError, KeyError, TypeError):
        return None


def run_blocking(args, *, work_dir, extra_paths, timeout=600):
    run = Run(args, work_dir=work_dir, extra_paths=extra_paths)
    deadline = time.monotonic() + timeout
    while (result := run.poll()) is None:
        if time.monotonic() > deadline:
            run.cancel()
            return {"ok": False, "error": f"The fetcher took longer than {timeout} s and was stopped."}
        time.sleep(0.1)
    return result


def cancel(key):
    run = ACTIVE.pop(key, None)
    STATUS.pop(key, None)
    if run is not None:
        run.cancel()


def cancel_all():
    for key in list(ACTIVE):
        cancel(key)


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""
