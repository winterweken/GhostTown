"""Live smoke test of the installed extension; run by tools/smoke_installed.sh inside Blender.

    ... --python tools/smoke_live.py -- "<address or lat, lon>" <radius_m> [lidar]
"""
import importlib
import json
import os
import sys
import tempfile

import bpy

args = sys.argv[sys.argv.index("--") + 1:]
query, radius = args[0], float(args[1])
with_lidar = len(args) > 2 and args[2] == "lidar"
pkg = "bl_ext.user_default.ghosttown"
runner = importlib.import_module(pkg + ".runner")
scene_build = importlib.import_module(pkg + ".scene_build")
ops = importlib.import_module(pkg + ".ops")
rq = importlib.import_module(pkg + ".ghosttown_fetch.request")

work = tempfile.mkdtemp(prefix="ghosttown-smoke-")
cache = os.path.join(work, "cache")
wheels = [runner.wheels_site_packages()]
result = runner.run_blocking(["selftest"], work_dir=os.path.join(work, "selftest"), extra_paths=wheels)
print("SELFTEST", result)
assert result["ok"], result

where = ops.parse_location(query)
if where is None:
    result = runner.run_blocking(["geocode", cache, query], work_dir=os.path.join(work, "find"), extra_paths=wheels)
    print("GEOCODE", result)
    assert result["ok"] and result["results"], result
    where = (result["results"][0]["lat"], result["results"][0]["lon"])

req = rq.build(centre={"lat": where[0], "lon": where[1]}, address="Smoke test", radius_m=radius,
               layers=list(rq.DEFAULT_LAYERS) + (["lidar"] if with_lidar else []),
               cache_dir=cache, out_dir=os.path.join(work, "run"))
os.makedirs(req["out_dir"])
path = os.path.join(req["out_dir"], "request.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(req, f)
result = runner.run_blocking(["fetch", path], work_dir=req["out_dir"], extra_paths=wheels,
                             timeout=900 if with_lidar else 300)
print("FETCH", result)
assert result["ok"], result

with open(result["context"], encoding="utf-8") as f:
    doc = json.load(f)
print("REGION", doc["region"], "TERRAIN", doc["terrain"], "GROUND_ASL", doc["ground_at_centre_m"])
print("COUNTS", doc["counts"])
print("SURVEY", doc.get("survey"))
print("PHOTO", doc.get("photo"))
print("LIDAR", doc.get("lidar"))
print("NOTES", [n["text"] for n in doc["notes"]])
root = scene_build.build(bpy.context.scene, doc, folder=os.path.dirname(result["context"]))
buildings = sum(1 for ob in root.all_objects if str(ob.get("ctx_kind", "")).startswith("building"))
print("BUILDINGS", buildings)
assert buildings >= 10, buildings
assert "ground" in doc["counts"], doc["counts"]
if doc["region"] == "toronto":
    assert {"road", "tree", "parcel"} <= set(doc["counts"]), doc["counts"]
    assert root.get("ctx_photo_image") and bpy.data.images[root["ctx_photo_image"]].packed_file, doc.get("photo")
    assert doc["terrain"]["source"] == "nrcan-dtm", doc["terrain"]
if with_lidar:
    site_use = importlib.import_module(pkg + ".site_use")
    city_model = any(n["code"] == "lidar" and "3D Massing" in n["text"] for n in doc["notes"])
    assert doc.get("lidar") or city_model, [n["text"] for n in doc["notes"]]
    if doc.get("lidar"):
        assert site_use.has_lidar(root) and root["use_roof_shapes"] == "lidar"
        print("TRIANGLES", site_use.count_triangles(root, bpy.context.evaluated_depsgraph_get()))
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(work, "smoke.blend"))
print("SMOKE OK", work)
