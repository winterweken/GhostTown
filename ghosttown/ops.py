import json
import os
import re
import time

import bpy
from bpy.props import StringProperty

from . import prefs, runner, scene_build
from .ghosttown_fetch import context as ctx
from .ghosttown_fetch import request as rq

OFFLINE = "Online access is off. Turn on Preferences › System › Network › Allow Online Access."
MISSING_SHAPELY = ("GhostTown's shapely library isn't installed. Disable and re-enable GhostTown in "
                   "Preferences › Add-ons, or reinstall it.")
_LOCATION = re.compile(r"\s*(-?\d+(?:\.\d+)?)\s*[,\s]\s*(-?\d+(?:\.\d+)?)\s*")


def parse_location(text):
    m = _LOCATION.fullmatch(text or "")
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    if not (-85 <= lat <= 85 and -180 <= lon <= 180):
        return None
    return lat, lon


def check_inputs(settings):
    where = parse_location(settings.location)
    if where is None:
        return "Enter the location as latitude, longitude (for example 43.6497, -79.3810)."
    if abs(where[0]) < 1e-9 and abs(where[1]) < 1e-9:
        return "The location is 0, 0, in the Atlantic off West Africa; enter the site's latitude, longitude."
    return None


def make_request(settings, cache_dir, overpass_url="", now=None):
    lat, lon = parse_location(settings.location)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    return rq.build(centre={"lat": lat, "lon": lon}, address=settings.site_name.strip(),
                    radius_m=float(settings.radius), cache_dir=cache_dir,
                    out_dir=os.path.join(cache_dir, "runs", stamp), overpass_url=overpass_url)


def _summary(doc):
    parts = [f"{n} {kind.replace('_', ' ')}" for kind, n in doc.get("counts", {}).items() if n]
    return ", ".join(parts) or "nothing found"


def import_into_scene(context, path, report):
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        report({"ERROR"}, f"Couldn't read {os.path.basename(path)} ({e}).")
        return None
    problems = ctx.validate(doc)
    if problems:
        report({"ERROR"}, problems[0])
        return None
    root = scene_build.build(context.scene, doc)
    settings = context.scene.ghosttown
    settings.summary = _summary(doc)
    settings.credits = "\n".join(dict.fromkeys(s["credit"] for s in doc["sources"]))
    for note in doc["notes"]:
        if note["level"] == "warn":
            report({"WARNING"}, note["text"])
    report({"INFO"}, f"Built {root.name}: {settings.summary}")
    return root


def _redraw(context):
    screen = getattr(context, "screen", None)
    for area in (screen.areas if screen else ()):
        if area.type == "VIEW_3D":
            area.tag_redraw()


class GHOSTTOWN_OT_import_context(bpy.types.Operator):
    bl_idname = "ghosttown.import_context"
    bl_label = "Import Context JSON"
    bl_description = "Build a context.json file (from an earlier run) into this scene"
    bl_options = {"REGISTER", "UNDO"}

    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        root = import_into_scene(context, self.filepath, self.report)
        return {"FINISHED"} if root is not None else {"CANCELLED"}


class GHOSTTOWN_OT_build(bpy.types.Operator):
    bl_idname = "ghosttown.build"
    bl_label = "Build Context"
    bl_description = "Fetch open data around the location and build it in this scene"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None

    @classmethod
    def poll(cls, context):
        return "build" not in runner.ACTIVE

    def invoke(self, context, event):
        if not bpy.app.online_access:
            self.report({"ERROR"}, OFFLINE)
            return {"CANCELLED"}
        settings = context.scene.ghosttown
        problem = check_inputs(settings)
        if problem:
            self.report({"ERROR"}, problem)
            return {"CANCELLED"}
        p = prefs.get(context)
        req = make_request(settings, prefs.cache_dir(context), overpass_url=p.overpass_url if p else "")
        problems = rq.validate(req)
        if problems:
            self.report({"ERROR"}, problems[0])
            return {"CANCELLED"}
        wheels = runner.wheels_site_packages()
        if not runner.ensure_wheels(wheels, refresh=bpy.ops.extensions.repo_refresh_all):
            self.report({"ERROR"}, MISSING_SHAPELY)
            return {"CANCELLED"}
        os.makedirs(req["out_dir"], exist_ok=True)
        path = os.path.join(req["out_dir"], "request.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(req, f, indent=1)
        runner.ACTIVE["build"] = runner.Run(["fetch", path], work_dir=req["out_dir"], extra_paths=[wheels])
        runner.STATUS["build"] = "Starting…"
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.25, window=context.window)
        wm.modal_handler_add(self)
        _redraw(context)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        run = runner.ACTIVE.get("build")
        if run is None:  # cancelled from the panel, by a file load or by unregister
            self._stop(context)
            return {"CANCELLED"}
        if event.type == "ESC":
            runner.cancel("build")
            self._stop(context)
            self.report({"WARNING"}, "Build cancelled.")
            return {"CANCELLED"}
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        result = run.poll()
        if result is None:
            progress = runner.read_progress(run.work_dir)
            if progress:
                runner.STATUS["build"] = f"{progress[0]}… {progress[1]}%"
            _redraw(context)
            return {"PASS_THROUGH"}  # never swallow timer events other handlers rely on
        runner.ACTIVE.pop("build", None)
        self._stop(context)
        if not result.get("ok"):
            self.report({"ERROR"}, result.get("error") or "The fetch failed.")
            return {"CANCELLED"}
        root = import_into_scene(context, result["context"], self.report)
        return {"FINISHED"} if root is not None else {"CANCELLED"}

    def cancel(self, context):
        # Blender calls this when it tears the operator down unfinished (window closed, file loaded,
        # add-on disabled): stop the fetch so the panel is never left saying "running".
        runner.cancel("build")
        self._stop(context)

    def _stop(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        runner.STATUS.pop("build", None)
        _redraw(context)


class GHOSTTOWN_OT_cancel(bpy.types.Operator):
    bl_idname = "ghosttown.cancel"
    bl_label = "Cancel"
    bl_description = "Stop the running fetch"

    def execute(self, context):
        runner.cancel("build")
        return {"FINISHED"}
