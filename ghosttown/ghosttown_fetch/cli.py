"""python -m ghosttown_fetch <selftest | fetch request.json>

stdout carries exactly one line of ASCII JSON and stderr stays empty, whatever happens.
On failure the run folder (when the request names one) gets error.txt with the details.
"""
import contextlib
import io
import json
import os
import platform
import sys
import traceback

from . import TOOL

USAGE = "Usage: python -m ghosttown_fetch selftest | fetch <request.json> | geocode <cache_dir> <text>"


def main(argv=None, *, net_factory=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            result = _dispatch(argv, net_factory)
        except BaseException as e:  # includes KeyboardInterrupt: still answer in one line
            result = {"ok": False, "error": f"The fetcher stopped unexpectedly ({type(e).__name__}: {e})."}
    print(json.dumps(result, ensure_ascii=True), flush=True)
    return 0 if result.get("ok") else 1


def _dispatch(argv, net_factory):
    if argv == ["selftest"]:
        return selftest()
    if len(argv) == 2 and argv[0] == "fetch":
        return fetch(argv[1], net_factory)
    if len(argv) == 3 and argv[0] == "geocode":
        return geocode(argv[1], argv[2], net_factory)
    return {"ok": False, "error": USAGE}


def selftest():
    try:
        import numpy
        import shapely
    except ImportError as e:
        return {"ok": False, "error": f"A required library is missing ({e.name}); reinstall Ghost Town."}
    major, minor = (int(p) for p in shapely.__version__.split(".")[:2])
    if (major, minor) < (2, 1):
        return {"ok": False, "error": f"shapely {shapely.__version__} is too old; Ghost Town needs 2.1 or later."}
    return {"ok": True, "tool": TOOL, "python": platform.python_version(), "numpy": numpy.__version__,
            "shapely": shapely.__version__, "geos": shapely.geos_version_string}


def fetch(path, net_factory):
    from . import request as rq

    doc, problems = rq.read(path)
    out_dir = doc.get("out_dir") if isinstance(doc, dict) else None
    if problems:
        return _fail(out_dir, "The request isn't valid: " + problems[0], "\n".join(problems))
    try:
        from . import context as ctx
        from .assemble import NothingFetched, assemble
        from .cache import atomic_write
        from .net import Net
    except ImportError as e:
        return _fail(out_dir, f"A required library is missing ({e.name}); reinstall Ghost Town.", traceback.format_exc())

    os.makedirs(out_dir, exist_ok=True)
    net = (net_factory or Net)(doc["cache_dir"], fresh=doc["fetch_fresh"])
    try:
        result = assemble(doc, net, progress=_progress_writer(out_dir))
    except NothingFetched as e:
        return _fail(out_dir, f"Nothing could be fetched. {e}", traceback.format_exc())
    except Exception as e:
        return _fail(out_dir, f"The fetch failed ({type(e).__name__}: {e}).", traceback.format_exc())

    problems = ctx.validate(result)
    if problems:
        return _fail(out_dir, "The fetcher built an invalid context: " + problems[0], "\n".join(problems))
    target = os.path.join(out_dir, "context.json")
    atomic_write(target, json.dumps(result, ensure_ascii=True, separators=(",", ":")).encode("ascii"))
    return {"ok": True, "context": os.path.abspath(target), "notes": len(result["notes"])}


def _progress_writer(out_dir):
    path = os.path.join(out_dir, "progress.jsonl")

    def write(stage, pct):
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"stage": stage, "pct": int(pct)}) + "\n")

    return write


def _fail(out_dir, sentence, detail):
    if isinstance(out_dir, str) and out_dir.strip():
        try:
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, "error.txt"), "w", encoding="utf-8") as f:
                f.write(sentence + "\n\n" + detail + "\n")
        except OSError:
            pass
    return {"ok": False, "error": sentence}


def geocode(cache_dir, text, net_factory):
    try:
        from .net import Net, SourceError
        from .sources import address
    except ImportError as e:
        return {"ok": False, "error": f"A required library is missing ({e.name}); reinstall Ghost Town."}
    net = (net_factory or Net)(cache_dir, fresh=False)
    try:
        return {"ok": True, "results": address.search(net, text)}
    except SourceError as e:
        return {"ok": False, "error": str(e)}
