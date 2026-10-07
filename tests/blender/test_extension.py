import json
import os
import sys
import tempfile

import bpy

import ghosttown
from ghosttown import ops, runner
from ghosttown.ghosttown_fetch import request as rq
from helpers import FIXTURES, photo_doc

SLEEPER = [sys.executable, "-c", "import time; time.sleep(30)"]


class Settings:
    def __init__(self, location, site_name="", radius="300", fetch_photo=True, fetch_lidar=False):
        self.location, self.site_name, self.radius, self.fetch_photo = location, site_name, radius, fetch_photo
        self.fetch_lidar = fetch_lidar


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


def _fake_operator(key="build"):
    from types import SimpleNamespace

    op = SimpleNamespace(key=key, _timer=None, report=lambda *args: None)
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


def test_one_address_match_fills_the_location_and_site_name():
    ghosttown.register()
    try:
        s = bpy.context.scene.ghosttown
        msg = ops.apply_results(s, [{"label": "320 Bay St", "lat": 43.649667039, "lon": -79.380991173, "source": "toronto"}])
        assert s.location == "43.649667039, -79.380991173" and s.site_name == "320 Bay St" and len(s.results) == 0
        assert "320 Bay St" in msg and ops.parse_location(s.location) == (43.649667039, -79.380991173)
    finally:
        ghosttown.unregister()


def test_several_matches_are_offered_and_one_is_picked():
    ghosttown.register()
    try:
        s = bpy.context.scene.ghosttown
        results = [{"label": f"{n} Bay St", "lat": 43.6496 + n * 1e-6, "lon": -79.381, "source": "toronto"} for n in (318, 320, 322)]
        msg = ops.apply_results(s, results)
        assert len(s.results) == 3 and "pick" in msg
        assert bpy.ops.ghosttown.pick(index=1) == {"FINISHED"}
        assert s.site_name == "320 Bay St" and s.location == f"{43.6496 + 320e-6!r}, -79.381" and len(s.results) == 0
    finally:
        ghosttown.unregister()


def test_no_match_says_what_to_do():
    ghosttown.register()
    try:
        s = bpy.context.scene.ghosttown
        assert "latitude, longitude" in ops.apply_results(s, []) and len(s.results) == 0
    finally:
        ghosttown.unregister()


def test_find_refuses_blank_text():
    ghosttown.register()
    try:
        s = bpy.context.scene.ghosttown
        s.location = "  "
        level, message = ops.find_refusal(s)
        assert level == "ERROR" and "Type an address" in message
    finally:
        ghosttown.unregister()


def test_find_leaves_coordinates_alone():
    ghosttown.register()
    try:
        s = bpy.context.scene.ghosttown
        s.location = "43.65, -79.38"
        level, message = ops.find_refusal(s)
        assert level == "INFO" and "latitude, longitude" in message and s.location == "43.65, -79.38"
        assert ops.find_refusal(Settings("320 Bay St")) is None
    finally:
        ghosttown.unregister()


def test_cancel_stops_a_running_find_too():
    ghosttown.register()
    try:
        run = runner.Run(["unused"], work_dir=tempfile.mkdtemp(), extra_paths=[], argv=SLEEPER)
        runner.ACTIVE["find"] = run
        assert bpy.ops.ghosttown.cancel() == {"FINISHED"}
        assert run.proc.poll() is not None and "find" not in runner.ACTIVE
    finally:
        runner.cancel_all()
        ghosttown.unregister()


def test_the_panel_and_the_add_on_carry_the_brand_name():
    import tomllib

    from ghosttown import ui

    assert ui.GHOSTTOWN_PT_main.bl_label == "Ghost Town" and ui.GHOSTTOWN_PT_main.bl_category == "Ghost Town"
    with open(os.path.join(os.path.dirname(ghosttown.__file__), "blender_manifest.toml"), "rb") as f:
        manifest = tomllib.load(f)
    assert manifest["name"] == "Ghost Town" and manifest["id"] == "ghosttown"


def test_the_panel_icon_loads_and_unloads_with_the_add_on():
    # Background mode hands out no UI icon ids, so this checks the loaded image; the GUI run checks the id.
    from ghosttown import ui

    assert not ui.icon_loaded()
    ghosttown.register()
    try:
        assert os.path.isfile(ui.ICON_FILE) and ui.icon_loaded()
        assert tuple(ui._previews["ghosttown"].image_size) == (64, 64)
    finally:
        ghosttown.unregister()
    assert not ui.icon_loaded() and ui.icon_id() == 0


def test_the_survey_point_comes_from_the_picked_site_and_copies():
    ghosttown.register()
    try:
        from ghosttown import georef
        bpy.ops.ghosttown.import_context(filepath=os.path.join(FIXTURES, "mini_context.json"))
        lines = georef.survey_lines(georef.survey_from(bpy.context.scene.ghosttown.site))
        assert lines[:2] == ["WGS 84 / UTM zone 17N (EPSG:32617)", "Easting 630564.787 m"]
        assert bpy.ops.ghosttown.copy_survey() == {"FINISHED"}
        if not bpy.app.background:  # background mode has no clipboard: writes are dropped
            assert bpy.context.window_manager.clipboard == "\n".join(lines)
    finally:
        ghosttown.unregister()


def test_copy_survey_waits_for_a_picked_site_with_a_survey_point():
    ghosttown.register()
    try:
        assert bpy.context.scene.ghosttown.site is None and not bpy.ops.ghosttown.copy_survey.poll()
    finally:
        ghosttown.unregister()


def test_the_site_panel_sits_under_the_main_panel_with_real_icons():
    ghosttown.register()
    try:
        from ghosttown import ui
        assert ui.GHOSTTOWN_PT_site.bl_parent_id == "GHOSTTOWN_PT_main"
        assert hasattr(bpy.types, "GHOSTTOWN_PT_site") and not hasattr(bpy.context.scene.ghosttown, "survey")
        icons = bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items.keys()
        assert all(name in icons for name in ui.SITE_ICONS)
    finally:
        ghosttown.unregister()


def test_the_solid_view_hint_is_in_the_panel_and_the_readme():
    from ghosttown import ui
    readme = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "README.md")
    with open(readme, encoding="utf-8") as f:
        assert ui.SOLID_HINT in f.read()
    assert "Material Preview" in ui.SOLID_HINT and "Color: Texture" in ui.SOLID_HINT


def test_the_roof_reset_warning_agrees_with_the_count():
    assert ops.roofs_reset_warning(1).startswith("1 edited building couldn't get its exact")
    assert ops.roofs_reset_warning(3).startswith("3 edited buildings couldn't get their exact")


def test_the_photo_is_fetched_unless_turned_off():
    with_photo = ops.make_request(Settings("43.649667, -79.380991"), "/tmp/gt-cache", now=0)
    without = ops.make_request(Settings("43.649667, -79.380991", fetch_photo=False), "/tmp/gt-cache", now=0)
    assert rq.validate(with_photo) == [] and rq.validate(without) == []
    assert set(with_photo["layers"]) - set(without["layers"]) == {"photo"}


def test_settings_offer_the_photo_and_a_site_picker_of_context_collections():
    ghosttown.register()
    try:
        from ghosttown import props
        settings = bpy.context.scene.ghosttown
        assert settings.fetch_photo is True and settings.site is None
        site = bpy.data.collections.new("Context · Test")
        site["ctx_root"] = True
        other = bpy.data.collections.new("My stuff")
        loose = bpy.data.collections.new("Context · Elsewhere")
        loose["ctx_root"] = True  # not linked into this scene
        for coll in (site, other):
            bpy.context.scene.collection.children.link(coll)
        assert props.is_site(settings, site) and not props.is_site(settings, other) and not props.is_site(settings, loose)
        settings.site = site
        assert settings.site == site
    finally:
        ghosttown.unregister()


def _write_context(doc, folder):
    path = os.path.join(folder, "context.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    return path


def test_import_with_a_photo_picks_the_site_and_names_the_photo_year():
    ghosttown.register()
    try:
        folder = tempfile.mkdtemp()
        path = _write_context(photo_doc(folder), folder)
        assert bpy.ops.ghosttown.import_context(filepath=path) == {"FINISHED"}
        settings = bpy.context.scene.ghosttown
        assert settings.site is not None and settings.site.name == "Context · 320 Bay St"
        assert settings.site.get("ctx_photo_image") and "aerial photo 2025" in settings.summary
    finally:
        ghosttown.unregister()


def test_import_without_the_photo_file_still_builds():
    ghosttown.register()
    try:
        folder = tempfile.mkdtemp()
        doc = photo_doc(folder)
        os.remove(os.path.join(folder, "photo.jpg"))
        assert bpy.ops.ghosttown.import_context(filepath=_write_context(doc, folder)) == {"FINISHED"}
        settings = bpy.context.scene.ghosttown
        assert settings.site is not None and not settings.site.get("ctx_photo_image")
        assert "aerial photo" not in settings.summary
    finally:
        ghosttown.unregister()


def test_import_of_a_damaged_photo_builds_without_it_and_says_why():
    ghosttown.register()
    try:
        folder = tempfile.mkdtemp()
        doc = photo_doc(folder)
        with open(os.path.join(folder, "photo.jpg"), "wb") as f:
            f.write(bytes(2048))  # not a picture at all
        reports = []
        root = ops.import_into_scene(bpy.context, _write_context(doc, folder), lambda level, text: reports.append((level, text)))
        settings = bpy.context.scene.ghosttown
        assert root is not None and settings.site == root and not root.get("ctx_photo_image")
        assert "aerial photo" not in settings.summary
        assert ({"WARNING"}, "The aerial photo file is missing or unreadable beside the context file, "
                             "so the site has no photo.") in reports
    finally:
        ghosttown.unregister()


def test_lidar_roofs_are_fetched_only_when_ticked():
    plain = ops.make_request(Settings("43.649667, -79.380991"), "/tmp/gt-cache", now=0)
    lidar = ops.make_request(Settings("43.649667, -79.380991", fetch_lidar=True), "/tmp/gt-cache", now=0)
    assert rq.validate(lidar) == [] and set(lidar["layers"]) - set(plain["layers"]) == {"lidar"}


def test_settings_start_without_lidar_and_at_full_detail_with_a_budget():
    ghosttown.register()
    try:
        from ghosttown import prefs
        settings = bpy.context.scene.ghosttown
        assert settings.fetch_lidar is False and settings.roof_detail == 100.0
        assert prefs.DEFAULT_BUDGET == 500_000 and prefs.triangle_budget(bpy.context) == 500_000
    finally:
        ghosttown.unregister()


def test_the_detail_slider_simplifies_the_picked_site_and_recounts():
    from ghosttown import site_use
    from test_site_lidar import buildings, lidar_site
    ghosttown.register()
    try:
        root, _ = lidar_site(dense=True)
        settings = bpy.context.scene.ghosttown
        settings.site = root
        settings.roof_detail = 40.0
        assert abs(root["roof_detail"] - 0.4) < 1e-6
        assert abs(buildings(root)[1].modifiers[site_use.DETAIL_MODIFIER].ratio - 0.4) < 1e-6
        site_use.count_later(root)()  # what the slider scheduled, run now
        assert root["ctx_triangles"] == site_use.count_triangles(root, bpy.context.evaluated_depsgraph_get())
    finally:
        ghosttown.unregister()


def test_picking_a_site_shows_its_roof_detail():
    from test_site_lidar import lidar_site
    ghosttown.register()
    try:
        root, _ = lidar_site()
        root["roof_detail"] = 0.25
        settings = bpy.context.scene.ghosttown
        settings.site = root
        assert settings.roof_detail == 25.0
    finally:
        ghosttown.unregister()


def test_triangle_counts_read_well_and_the_warning_says_what_to_do():
    from ghosttown import ui
    assert ui.triangles_text(1_400_000) == "1.4 M" and ui.triangles_text(86_000) == "86,000"
    assert " ".join(ui.HEAVY) == "Heavy for Revit: use Fitted or Flat roofs, or lower Roof detail, before exporting."


def test_a_recount_is_scheduled_again_once_a_file_load_has_dropped_its_timer():
    from ghosttown import site_use
    from test_site_lidar import lidar_site
    ghosttown.register()
    timers = []
    try:
        root, _ = lidar_site()
        first = site_use.count_later(root)
        timers.append(first)
        assert bpy.app.timers.is_registered(first)
        bpy.app.timers.unregister(first)  # what loading a file does to a pending timer
        second = site_use.count_later(root)
        timers.append(second)
        assert bpy.app.timers.is_registered(second)
        root["ctx_triangles"] = -1
        second()  # what the timer would run
        assert root["ctx_triangles"] == site_use.count_triangles(root, bpy.context.evaluated_depsgraph_get()) > 0
        third = site_use.count_later(root)
        timers.append(third)
        assert bpy.app.timers.is_registered(third) and site_use.count_later(root) is third  # one timer per site
    finally:
        for fn in timers:
            if bpy.app.timers.is_registered(fn):
                bpy.app.timers.unregister(fn)
        ghosttown.unregister()


def test_the_readme_explains_lidar_roofs_and_the_revit_budget():
    from ghosttown import ui
    readme = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "README.md")
    with open(readme, encoding="utf-8") as f:
        text = f.read()
    assert " ".join(ui.HEAVY) in text and "ws.geoservices.lrc.gov.on.ca" in text
    assert "Contains information licensed under the Open Government Licence – Ontario" in text


def test_the_token_falls_back_to_the_environment():
    from ghosttown import prefs

    ghosttown.register()
    os.environ["GHOSTTOWN_MAPILLARY_TOKEN"] = " MLY|abc "
    try:
        assert prefs.token(bpy.context) == "MLY|abc"
        del os.environ["GHOSTTOWN_MAPILLARY_TOKEN"]
        assert prefs.token(bpy.context) == ""
    finally:
        os.environ.pop("GHOSTTOWN_MAPILLARY_TOKEN", None)
        ghosttown.unregister()
