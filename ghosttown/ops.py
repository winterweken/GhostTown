import json
import os
import re
import time

import bpy
from bpy.props import EnumProperty, IntProperty, StringProperty

from . import georef, prefs, runner, scene_build, site_photo, site_use
from .ghosttown_fetch import context as ctx
from .ghosttown_fetch import request as rq
from .ghosttown_fetch import LAYERS

OFFLINE = "Online access is off. Turn on Preferences › System › Network › Allow Online Access."
MISSING_SHAPELY = ("Ghost Town's shapely library isn't installed. Disable and re-enable Ghost Town in "
                   "Preferences › Add-ons, or reinstall it.")
NO_MATCH = "No Toronto address matched. Outside Toronto, enter latitude, longitude for now."
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
        return "Enter an address and press Find, or type latitude, longitude (for example 43.6497, -79.3810)."
    if abs(where[0]) < 1e-9 and abs(where[1]) < 1e-9:
        return "The location is 0, 0, in the Atlantic off West Africa; enter the site's latitude, longitude."
    return None


def find_refusal(settings):
    """(report level, sentence) when Find has nothing to look up, else None."""
    text = settings.location.strip()
    if not text:
        return "ERROR", "Type an address first, for example 320 Bay St."
    if parse_location(text) is not None:
        return "INFO", "That's already latitude, longitude; press Build Context."
    return None


def _stamp(now=None):
    return time.strftime("%Y%m%d-%H%M%S", time.localtime(now))


def request_layers(settings):
    """Every layer, less the photo when the user turned it off."""
    return [layer for layer in LAYERS if layer != "photo" or getattr(settings, "fetch_photo", True)]


def make_request(settings, cache_dir, overpass_url="", now=None):
    lat, lon = parse_location(settings.location)
    return rq.build(centre={"lat": lat, "lon": lon}, address=settings.site_name.strip(),
                    radius_m=float(settings.radius), cache_dir=cache_dir, layers=request_layers(settings),
                    out_dir=os.path.join(cache_dir, "runs", _stamp(now)), overpass_url=overpass_url)


def use_result(settings, label, lat, lon):
    settings.location = f"{lat}, {lon}"
    settings.site_name = label
    settings.results.clear()


def apply_results(settings, results):
    """Fill the panel from address-search results; returns the sentence to show."""
    settings.results.clear()
    if not results:
        return NO_MATCH
    if len(results) == 1:
        r = results[0]
        use_result(settings, r["label"], float(r["lat"]), float(r["lon"]))
        return f"Found {r['label']}."
    for r in results:
        item = settings.results.add()
        item.label, item.lat, item.lon = r["label"], repr(float(r["lat"])), repr(float(r["lon"]))
    return f"{len(results)} addresses match; pick one below."


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
    root = scene_build.build(context.scene, doc, folder=os.path.dirname(os.path.abspath(path)))
    settings = context.scene.ghosttown
    settings.site = root
    settings.summary = _summary(doc)
    photo = doc.get("photo")
    if photo and root.get("ctx_photo_image"):
        year = photo.get("year")
        settings.summary += f", aerial photo {year}" if year else ", aerial photo"
    elif photo:
        report({"WARNING"}, "The aerial photo file is missing beside the context file, so the site has no photo.")
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


class _FetcherOperator:
    """Shared modal loop: run the fetcher under `key`, poll it on a timer, hand its answer to `finished`."""
    key = ""
    _timer = None

    def _launch(self, context, args, work_dir):
        wheels = runner.wheels_site_packages()
        if not runner.ensure_wheels(wheels, refresh=bpy.ops.extensions.repo_refresh_all):
            self.report({"ERROR"}, MISSING_SHAPELY)
            return {"CANCELLED"}
        runner.ACTIVE[self.key] = runner.Run(args, work_dir=work_dir, extra_paths=[wheels])
        runner.STATUS[self.key] = "Starting…"
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.25, window=context.window)
        wm.modal_handler_add(self)
        _redraw(context)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        run = runner.ACTIVE.get(self.key)
        if run is None:  # cancelled from the panel, by a file load or by unregister
            self._stop(context)
            return {"CANCELLED"}
        if event.type == "ESC":
            runner.cancel(self.key)
            self._stop(context)
            self.report({"WARNING"}, "Cancelled.")
            return {"CANCELLED"}
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        result = run.poll()
        if result is None:
            progress = runner.read_progress(run.work_dir)
            if progress:
                runner.STATUS[self.key] = f"{progress[0]}… {progress[1]}%"
            _redraw(context)
            return {"PASS_THROUGH"}  # never swallow timer events other handlers rely on
        runner.ACTIVE.pop(self.key, None)
        self._stop(context)
        if not result.get("ok"):
            self.report({"ERROR"}, result.get("error") or "The fetch failed.")
            return {"CANCELLED"}
        return self.finished(context, result)

    def cancel(self, context):
        # Blender calls this when it tears the operator down unfinished (window closed, file loaded,
        # add-on disabled): stop the fetch so the panel is never left saying "running".
        runner.cancel(self.key)
        self._stop(context)

    def _stop(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        runner.STATUS.pop(self.key, None)
        _redraw(context)


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


class GHOSTTOWN_OT_build(_FetcherOperator, bpy.types.Operator):
    bl_idname = "ghosttown.build"
    bl_label = "Build Context"
    bl_description = "Fetch open data around the location and build it in this scene"
    bl_options = {"REGISTER", "UNDO"}
    key = "build"

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
        os.makedirs(req["out_dir"], exist_ok=True)
        path = os.path.join(req["out_dir"], "request.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(req, f, indent=1)
        return self._launch(context, ["fetch", path], req["out_dir"])

    def finished(self, context, result):
        root = import_into_scene(context, result["context"], self.report)
        return {"FINISHED"} if root is not None else {"CANCELLED"}


class GHOSTTOWN_OT_find(_FetcherOperator, bpy.types.Operator):
    bl_idname = "ghosttown.find"
    bl_label = "Find Address"
    bl_description = "Look up a City of Toronto address and use its location"
    bl_options = {"REGISTER"}
    key = "find"

    @classmethod
    def poll(cls, context):
        return "find" not in runner.ACTIVE

    def invoke(self, context, event):
        settings = context.scene.ghosttown
        refusal = find_refusal(settings)
        if refusal:
            self.report({refusal[0]}, refusal[1])
            return {"CANCELLED"}
        text = settings.location.strip()
        if not bpy.app.online_access:
            self.report({"ERROR"}, OFFLINE)
            return {"CANCELLED"}
        cache = prefs.cache_dir(context)
        return self._launch(context, ["geocode", cache, text], os.path.join(cache, "runs", "find-" + _stamp()))

    def finished(self, context, result):
        results = result.get("results") or []
        message = apply_results(context.scene.ghosttown, results)
        self.report({"INFO"} if results else {"WARNING"}, message)
        return {"FINISHED"}


class GHOSTTOWN_OT_pick(bpy.types.Operator):
    bl_idname = "ghosttown.pick"
    bl_label = "Use This Address"
    bl_description = "Use this address's location"
    bl_options = {"REGISTER", "UNDO"}

    index: IntProperty(default=0)

    def execute(self, context):
        settings = context.scene.ghosttown
        if not 0 <= self.index < len(settings.results):
            return {"CANCELLED"}
        item = settings.results[self.index]
        use_result(settings, item.label, item.lat, item.lon)
        return {"FINISHED"}


class GHOSTTOWN_OT_copy_survey(bpy.types.Operator):
    bl_idname = "ghosttown.copy_survey"
    bl_label = "Copy Survey Point"
    bl_description = "Copy where the context origin sits on the survey grid, for setting Revit's survey point"

    @classmethod
    def poll(cls, context):
        root = site_use.picked(context)
        return root is not None and georef.survey_from(root) is not None

    def execute(self, context):
        point = georef.survey_from(site_use.picked(context))
        context.window_manager.clipboard = "\n".join(georef.survey_lines(point))
        self.report({"INFO"}, "Copied the survey point.")
        return {"FINISHED"}


def _has_photo(context):
    root = site_use.picked(context)
    return context.mode == "OBJECT" and root is not None and bool(root.get("ctx_photo_material"))


class GHOSTTOWN_OT_use_ground(bpy.types.Operator):
    bl_idname = "ghosttown.use_ground"
    bl_label = "Ground"
    bl_description = "Show the aerial photo, or the colours by kind, on the picked site's ground"
    bl_options = {"REGISTER", "UNDO"}

    use: EnumProperty(items=(("colours", "Colours", "Colours by kind, as exported"),
                             ("photo", "Photo", "The aerial photo")))

    @classmethod
    def poll(cls, context):
        return _has_photo(context)

    def execute(self, context):
        site_use.apply_ground(site_use.picked(context), self.use)
        return {"FINISHED"}


class GHOSTTOWN_OT_use_roofs(bpy.types.Operator):
    bl_idname = "ghosttown.use_roofs"
    bl_label = "Roofs"
    bl_description = "Put the aerial photo on the roofs of the picked site's lower buildings, or keep them plain"
    bl_options = {"REGISTER", "UNDO"}

    use: EnumProperty(items=(("plain", "Plain", "Roofs keep their building colours"),
                             ("photo", "Photo", "The aerial photo on roofs, up to the height limit")))

    @classmethod
    def poll(cls, context):
        return _has_photo(context)

    def execute(self, context):
        reset = site_use.apply_roofs(site_use.picked(context), self.use, context.scene.ghosttown.roof_photo_max_m)
        if reset:
            self.report({"WARNING"}, f"{reset} edited buildings couldn't get their exact roof materials back; "
                                     "their roofs now use their first material.")
        return {"FINISHED"}


class GHOSTTOWN_OT_save_photo(bpy.types.Operator):
    bl_idname = "ghosttown.save_photo"
    bl_label = "Save Site Photo…"
    bl_description = "Save the picked site's aerial photo and a world file, to place under the model in Revit or CAD"

    directory: StringProperty(subtype="DIR_PATH")

    @classmethod
    def poll(cls, context):
        root = site_use.picked(context)
        return root is not None and bool(root.get("ctx_photo_image"))

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        try:
            jpg, _jgw, width = site_photo.save(site_use.picked(context), bpy.path.abspath(self.directory))
        except (OSError, ValueError) as e:
            self.report({"ERROR"}, f"Couldn't save the photo ({e}).")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Saved {os.path.basename(jpg)}. In Revit, set the image width to {width:g} m "
                              "and centre it on the origin.")
        return {"FINISHED"}


class GHOSTTOWN_OT_cancel(bpy.types.Operator):
    bl_idname = "ghosttown.cancel"
    bl_label = "Cancel"
    bl_description = "Stop the running fetch"

    def execute(self, context):
        runner.cancel("build")
        runner.cancel("find")
        return {"FINISHED"}
