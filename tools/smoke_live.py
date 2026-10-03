"""Live smoke test of the installed extension; run by tools/smoke_installed.sh inside Blender."""
import importlib
import json
import os
import sys
import tempfile

import bpy

args = sys.argv[sys.argv.index("--") + 1:]
lat, lon, radius = float(args[0]), float(args[1]), float(args[2])
pkg = "bl_ext.user_default.ghosttown"
runner = importlib.import_module(pkg + ".runner")
scene_build = importlib.import_module(pkg + ".scene_build")
rq = importlib.import_module(pkg + ".ghosttown_fetch.request")

work = tempfile.mkdtemp(prefix="ghosttown-smoke-")
wheels = [runner.wheels_site_packages()]
result = runner.run_blocking(["selftest"], work_dir=os.path.join(work, "selftest"), extra_paths=wheels)
print("SELFTEST", result)
assert result["ok"], result

req = rq.build(centre={"lat": lat, "lon": lon}, address="Smoke test", radius_m=radius,
               cache_dir=os.path.join(work, "cache"), out_dir=os.path.join(work, "run"))
os.makedirs(req["out_dir"])
path = os.path.join(req["out_dir"], "request.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(req, f)
result = runner.run_blocking(["fetch", path], work_dir=req["out_dir"], extra_paths=wheels, timeout=300)
print("FETCH", result)
assert result["ok"], result

with open(result["context"], encoding="utf-8") as f:
    doc = json.load(f)
root = scene_build.build(bpy.context.scene, doc)
count = sum(1 for ob in root.all_objects if str(ob.get("ctx_kind", "")).startswith("building"))
print("BUILDINGS", count)
assert count >= 10, count
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(work, "smoke.blend"))
print("SMOKE OK", work)
