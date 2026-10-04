"""Headless Blender tests.

    /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
        --python-exit-code 1 --python tests/blender/run.py [-- -k substring]

Discovers test_*.py here and runs every test_* function on a fresh empty file.
"""
import importlib.util
import os
import sys
import traceback

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [ROOT, HERE]  # `import ghosttown` and `import helpers`


def _defines_match(name, pattern):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return any(line.startswith("def test_") and pattern in f"{name}::{line[4:]}" for line in f)


def _report(exc):
    # Not traceback.print_exc(): its "did you mean" hint calls dir() on the failing object, which crashes
    # Blender when that object is RNA data already freed by unregister().
    traceback.print_tb(exc.__traceback__)
    print(f"{type(exc).__name__}: {exc}")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    pattern = argv[argv.index("-k") + 1] if "-k" in argv else ""
    total = failed = 0
    for name in sorted(os.listdir(HERE)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        if pattern and pattern not in name and not _defines_match(name, pattern):
            continue
        spec = importlib.util.spec_from_file_location(name[:-3], os.path.join(HERE, name))
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            total += 1
            failed += 1
            print("FAIL", name, "(import)")
            _report(e)
            continue
        for attr in sorted(a for a in dir(module) if a.startswith("test_")):
            label = f"{name}::{attr}"
            if pattern not in label:
                continue
            total += 1
            bpy.ops.wm.read_factory_settings(use_empty=True)
            try:
                getattr(module, attr)()
                print("PASS", label)
            except Exception as e:
                failed += 1
                print("FAIL", label)
                _report(e)
    print(f"{total - failed} passed, {failed} failed")
    if failed or not total:
        raise RuntimeError(f"{failed} of {total} Blender tests failed")


main()
