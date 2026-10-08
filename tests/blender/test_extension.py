import json
import os
import sys
import tempfile

import bpy

import ghosttown
from ghosttown import look_build, materials, ops, props, runner, scene_build, site_use
from ghosttown.ghosttown_fetch import look_schema as ls
from ghosttown.ghosttown_fetch import request as rq
from helpers import FIXTURES, load_fixture, photo_doc

SLEEPER = [sys.executable, "-c", "import time; time.sleep(30)"]


class Settings:
    def __init__(self, location, site_name="", radius="300", fetch_photo=True, fetch_lidar=False):
        self.location, self.site_name, self.radius, self.fetch_photo = location, site_name, radius, fetch_photo
        self.fetch_lidar = fetch_lidar


def test_register_and_unregister_twice():
    for _ in range(2):
        ghosttown.register()
        assert hasattr(bpy.types.Scene, "ghosttown")
        bpy.ops.ghosttown.build.get_rna_type()   # hasattr(bpy.ops.ghosttown, ...) is true for any name; this raises
        ghosttown.unregister()
        assert not hasattr(bpy.types.Scene, "ghosttown")
        try:
            bpy.ops.ghosttown.build.get_rna_type()
        except KeyError:
            pass
        else:
            raise AssertionError("Build Context is still registered")


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


def test_only_pressing_esc_cancels_a_run():
    # Releasing an Esc that closed a menu, a text field or a move reaches the run too; it must pass through.
    from types import SimpleNamespace

    ghosttown.register()
    try:
        run = runner.Run(["unused"], work_dir=tempfile.mkdtemp(), extra_paths=[], argv=SLEEPER)
        runner.ACTIVE["build"] = run
        reports, op = [], _fake_operator()
        op.report = lambda *a: reports.append(a)
        result = ops.GHOSTTOWN_OT_build.modal(op, bpy.context, SimpleNamespace(type="ESC", value="RELEASE"))
        assert result == {"PASS_THROUGH"} and "build" in runner.ACTIVE and run.proc.poll() is None and reports == []
        result = ops.GHOSTTOWN_OT_build.modal(op, bpy.context, SimpleNamespace(type="ESC", value="PRESS"))
        assert result == {"CANCELLED"} and "build" not in runner.ACTIVE and run.proc.poll() is not None
        assert reports == [({"WARNING"}, "Cancelled.")]
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


def _restore_env(name, prior):
    """Leave an environment variable as a test found it: set again if it was set, removed if it wasn't."""
    if prior is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = prior


def test_the_token_falls_back_to_the_environment():
    from ghosttown import prefs

    prior = os.environ.get("GHOSTTOWN_MAPILLARY_TOKEN")  # whatever the developer's shell exports, or None
    ghosttown.register()
    os.environ["GHOSTTOWN_MAPILLARY_TOKEN"] = " MLY|abc "
    try:
        assert prefs.token(bpy.context) == "MLY|abc"
        del os.environ["GHOSTTOWN_MAPILLARY_TOKEN"]
        assert prefs.token(bpy.context) == ""
    finally:
        _restore_env("GHOSTTOWN_MAPILLARY_TOKEN", prior)
        ghosttown.unregister()


def test_the_token_in_preferences_wins_over_the_environment_and_is_masked():
    from ghosttown import prefs

    prior = os.environ.get("GHOSTTOWN_MAPILLARY_TOKEN")
    ghosttown.register()
    entry = None
    try:
        # register() adds only the classes; enabling the add-on is what gives Preferences an entry, so add one.
        entry = bpy.context.preferences.addons.new()
        entry.module = "ghosttown"
        assert isinstance(prefs.get(bpy.context), prefs.GhostTownPreferences)
        assert prefs.GhostTownPreferences.bl_rna.properties["mapillary_token"].subtype == "PASSWORD"
        os.environ["GHOSTTOWN_MAPILLARY_TOKEN"] = "MLY|env"
        assert prefs.token(bpy.context) == "MLY|env"  # the field starts blank, so the environment answers
        prefs.get(bpy.context).mapillary_token = "  MLY|pref  "
        assert prefs.token(bpy.context) == "MLY|pref"  # Preferences win over the environment, trimmed
        prefs.get(bpy.context).mapillary_token = "   "
        assert prefs.token(bpy.context) == "MLY|env"  # a blank field falls back to the environment again
        del os.environ["GHOSTTOWN_MAPILLARY_TOKEN"]
        assert prefs.token(bpy.context) == ""  # and with neither there is no token
    finally:
        _restore_env("GHOSTTOWN_MAPILLARY_TOKEN", prior)
        if entry is not None:
            bpy.context.preferences.addons.remove(entry)
        ghosttown.unregister()


LOOK = os.path.join(FIXTURES, "mini_look.json")
CREDIT = "Street photos © Mapillary contributors, CC BY-SA 4.0"
LABELS = "Labels from Mapillary · https://www.mapillary.com"


def _picked_site():
    root = scene_build.build(bpy.context.scene, load_fixture("mini_context.json"))
    bpy.context.scene.ghosttown.site = root
    return root


def test_street_look_registers_with_its_defaults():
    from ghosttown import ui

    ghosttown.register()
    try:
        assert ops.GHOSTTOWN_OT_street_look.is_registered and ops.GHOSTTOWN_OT_add_sky.is_registered
        for name in ("street_look", "add_sky"):   # hasattr(bpy.ops.ghosttown, ...) is true for any name, so look it up
            getattr(bpy.ops.ghosttown, name).get_rna_type()   # raises KeyError unless the operator is registered
        assert ui.GHOSTTOWN_PT_street_look.is_registered and ui.GHOSTTOWN_PT_street_look.bl_parent_id == "GHOSTTOWN_PT_site"
        assert ui.GHOSTTOWN_PT_street_look.bl_options == {"DEFAULT_CLOSED"}
        s = bpy.context.scene.ghosttown
        assert (s.look_budget, s.look_not_before, s.look_detail, s.look_keep) == (150, 0, False, True)
        assert (s.show_look, s.show_detail) == (True, True) and abs(s.look_brightness - 1.15) < 1e-6
    finally:
        ghosttown.unregister()


def test_street_look_says_why_it_cannot_start():
    prior = os.environ.get(ls.TOKEN_ENV)   # whatever the developer's shell exports, or None
    ghosttown.register()
    os.environ.pop(ls.TOKEN_ENV, None)
    try:
        assert ops.look_refusal(bpy.context, online=False) == ops.OFFLINE
        assert ops.look_refusal(bpy.context, online=True) == ops.NO_TOKEN
        os.environ[ls.TOKEN_ENV] = "MLY|abc"
        assert ops.look_refusal(bpy.context, online=True) == ops.NO_SITE
        _picked_site()
        assert ops.look_refusal(bpy.context, online=True) is None
        settings = bpy.context.scene.ghosttown
        settings.look_not_before = 1990   # the field takes it; the request doesn't
        assert ops.look_refusal(bpy.context, online=True) == "Not before must be 0 or a year from 2000 on."
        for year in (2019, 0):
            settings.look_not_before = year
            assert ops.look_refusal(bpy.context, online=True) is None
    finally:
        _restore_env(ls.TOKEN_ENV, prior)
        ghosttown.unregister()


def test_street_look_hands_the_token_over_in_the_environment_only():
    prior = os.environ.get(ls.TOKEN_ENV)
    ghosttown.register()
    os.environ[ls.TOKEN_ENV] = "MLY|secret"
    try:
        _picked_site()
        launch, problem = ops.look_launch(bpy.context, tempfile.mkdtemp(), online=True)
        assert problem is None and launch["env"] == {ls.TOKEN_ENV: "MLY|secret"}
        assert launch["args"][0] == "look" and launch["root"] == "Context · 320 Bay St"
        with open(launch["args"][1], encoding="utf-8") as f:
            req = json.load(f)
        assert ls.validate_request(req) == [] and "secret" not in json.dumps(req)
        assert not any("secret" in arg for arg in launch["args"])
    finally:
        _restore_env(ls.TOKEN_ENV, prior)
        ghosttown.unregister()


def test_street_look_needs_pillow_and_names_it_when_missing():
    from types import SimpleNamespace

    reports = []
    op = SimpleNamespace(key="look", needs=ops.GHOSTTOWN_OT_street_look.needs, report=lambda *a: reports.append(a))
    real = runner.ensure_wheels
    runner.ensure_wheels = lambda wheels, refresh, package="shapely": package != "PIL"
    try:
        assert ops._FetcherOperator._launch(op, bpy.context, ["look", "x"], tempfile.mkdtemp()) == {"CANCELLED"}
        assert reports == [({"ERROR"}, ops.MISSING_PILLOW)] and "look" not in runner.ACTIVE
        assert ops.GHOSTTOWN_OT_build.needs == (("shapely", ops.MISSING_SHAPELY),)
    finally:
        runner.ensure_wheels = real


def test_a_finished_look_is_reported_and_kept_on_the_site():
    ghosttown.register()
    try:
        root = _picked_site()
        reports = []
        text = ops.apply_look(bpy.context, root, LOOK, lambda *a: reports.append(a))
        assert text == root[look_build.SUMMARY_PROP] == "Look from photos: 1 building · guessed: 1 · 3 photos (2019–2025)"
        assert root[look_build.CREDITS_PROP] == CREDIT + "\n" + LABELS   # the panel's two credit lines
        assert root["credits"].splitlines()[-2:] == [CREDIT, LABELS]
        assert ({"WARNING"}, "Some areas couldn't be searched.") in reports and ({"INFO"}, text) in reports
    finally:
        ghosttown.unregister()


def test_a_broken_look_answer_changes_nothing():
    ghosttown.register()
    path = os.path.join(tempfile.mkdtemp(), "look.json")
    with open(path, "w") as f:
        json.dump({"schema": 9}, f)
    try:
        root = _picked_site()
        reports = []
        assert ops.apply_look(bpy.context, root, path, lambda *a: reports.append(a)) is None
        assert "schema" in reports[0][1] and look_build.LOOK_PROP not in root and look_build.SUMMARY_PROP not in root
    finally:
        ghosttown.unregister()


def test_the_switches_reach_the_materials_and_the_detail():
    ghosttown.register()
    try:
        root = _picked_site()
        ops.apply_look(bpy.context, root, LOOK, lambda *a: None)
        s = bpy.context.scene.ghosttown
        s.show_look, s.look_brightness, s.show_detail = False, 0.7, False
        node = bpy.data.materials["Context - Building"].node_tree.nodes[materials.LOOK_NODE]
        assert node.inputs["Look"].default_value == 0.0 and abs(node.inputs["Brightness"].default_value - 0.7) < 1e-6
        detail = next(c for c in root.children if c.get("ctx_group") == "Detail")
        assert detail.hide_viewport and detail.hide_render
    finally:
        ghosttown.unregister()


def test_a_rebuild_keeps_or_drops_the_look_as_set():
    ghosttown.register()
    path = os.path.join(FIXTURES, "mini_context.json")
    try:
        bpy.ops.ghosttown.import_context(filepath=path)
        ops.apply_look(bpy.context, bpy.data.collections["Context · 320 Bay St"], LOOK, lambda *a: None)
        bpy.ops.ghosttown.import_context(filepath=path)
        assert look_build.LOOK_PROP in bpy.data.collections["Context · 320 Bay St"]
        bpy.context.scene.ghosttown.look_keep = False
        bpy.ops.ghosttown.import_context(filepath=path)
        assert look_build.LOOK_PROP not in bpy.data.collections["Context · 320 Bay St"]
    finally:
        ghosttown.unregister()


def test_a_rebuild_that_drops_a_stored_look_says_so():
    ghosttown.register()
    path = os.path.join(FIXTURES, "mini_context.json")
    dropped = ({"WARNING"}, "The street look couldn't be put back on the rebuilt site; apply it again.")
    stored = (look_build.LOOK_PROP, look_build.SUMMARY_PROP, look_build.CREDITS_PROP)
    try:
        reports = []
        root = ops.import_into_scene(bpy.context, path, lambda *a: reports.append(a))
        ops.apply_look(bpy.context, root, LOOK, lambda *a: None)
        root = ops.import_into_scene(bpy.context, path, lambda *a: reports.append(a))   # a healthy carry-over
        assert look_build.LOOK_PROP in root and dropped not in reports
        root[look_build.LOOK_PROP] = "not json"   # a look that can't be put back
        root = ops.import_into_scene(bpy.context, path, lambda *a: reports.append(a))
        assert dropped in reports and [key for key in stored if key in root] == []
        ops.apply_look(bpy.context, root, LOOK, lambda *a: None)
        bpy.context.scene.ghosttown.look_keep = False
        reports.clear()
        root = ops.import_into_scene(bpy.context, path, lambda *a: reports.append(a))   # dropped as asked
        assert look_build.LOOK_PROP not in root and dropped not in reports
    finally:
        ghosttown.unregister()


def test_a_rebuild_dresses_a_fresh_material_with_the_switches_as_set():
    ghosttown.register()
    path = os.path.join(FIXTURES, "mini_context.json")
    try:
        bpy.ops.ghosttown.import_context(filepath=path)
        ops.apply_look(bpy.context, bpy.data.collections["Context · 320 Bay St"], LOOK, lambda *a: None)
        s = bpy.context.scene.ghosttown
        s.show_look, s.look_brightness = False, 0.8
        bpy.data.materials.remove(bpy.data.materials["Context - Building"])   # the rebuild makes it again, plain
        bpy.ops.ghosttown.import_context(filepath=path)
        node = bpy.data.materials["Context - Building"].node_tree.nodes[materials.LOOK_NODE]
        assert node.inputs["Look"].default_value == 0.0 and abs(node.inputs["Brightness"].default_value - 0.8) < 1e-6
    finally:
        ghosttown.unregister()


def test_cancel_stops_a_running_street_look_too():
    ghosttown.register()
    try:
        run = runner.Run(["unused"], work_dir=tempfile.mkdtemp(), extra_paths=[], argv=SLEEPER)
        runner.ACTIVE["look"] = run
        assert bpy.ops.ghosttown.cancel() == {"FINISHED"}
        assert run.proc.poll() is not None and "look" not in runner.ACTIVE
    finally:
        runner.cancel_all()
        ghosttown.unregister()


def test_each_panels_cancel_stops_only_its_own_run():
    ghosttown.register()
    try:
        build = runner.Run(["unused"], work_dir=tempfile.mkdtemp(), extra_paths=[], argv=SLEEPER)
        look = runner.Run(["unused"], work_dir=tempfile.mkdtemp(), extra_paths=[], argv=SLEEPER)
        runner.ACTIVE["build"], runner.ACTIVE["look"] = build, look
        assert bpy.ops.ghosttown.cancel(key="look") == {"FINISHED"}   # Street Look's Cancel
        assert look.proc.poll() is not None and "look" not in runner.ACTIVE
        assert build.proc.poll() is None and "build" in runner.ACTIVE   # Build goes on
        assert bpy.ops.ghosttown.cancel(key="build") == {"FINISHED"}   # Build's Cancel
        assert build.proc.poll() is not None and runner.ACTIVE == {}
    finally:
        runner.cancel_all()
        ghosttown.unregister()


def test_launching_street_look_gives_the_run_the_token_in_its_environment_only():
    from types import SimpleNamespace

    prior = os.environ.get(ls.TOKEN_ENV)
    ghosttown.register()
    os.environ[ls.TOKEN_ENV] = "MLY|secret"
    seen, real_run, real_ensure = {}, runner.Run, runner.ensure_wheels
    try:
        _picked_site()
        launch, problem = ops.look_launch(bpy.context, tempfile.mkdtemp(), online=True)
        assert problem is None
        runner.Run = lambda args, **kwargs: seen.update(args=args, **kwargs) or "run"   # no child is started
        runner.ensure_wheels = lambda wheels, refresh, package="shapely": True
        wm = SimpleNamespace(event_timer_add=lambda *a, **kw: "timer", modal_handler_add=lambda op: None)
        op = SimpleNamespace(key="look", needs=ops.GHOSTTOWN_OT_street_look.needs, report=lambda *a: None)
        context = SimpleNamespace(window_manager=wm, window=None)
        result = ops._FetcherOperator._launch(op, context, launch["args"], launch["work_dir"], env_extra=launch["env"])
        assert result == {"RUNNING_MODAL"} and runner.ACTIVE["look"] == "run"
        assert seen["env_extra"] == {ls.TOKEN_ENV: "MLY|secret"}   # the child's environment gets the token...
        assert seen["args"] == launch["args"] and "secret" not in repr(seen["args"])   # ...and its arguments don't
        assert seen["work_dir"] == launch["work_dir"]
    finally:
        runner.Run, runner.ensure_wheels = real_run, real_ensure
        runner.ACTIVE.pop("look", None)
        runner.STATUS.pop("look", None)
        _restore_env(ls.TOKEN_ENV, prior)
        ghosttown.unregister()


class DrawnLayout:
    """Stands in for a UILayout while a panel draws: every call lands in `drawn`, a box, row or column starts
    as enabled as its parent, and what Blender's own layout would refuse (a property, an operator or an icon
    that doesn't exist) fails here too."""

    def __init__(self, drawn, enabled=True):
        self.drawn, self.enabled = drawn, enabled

    def _nested(self, kind):
        self.drawn.append((kind,))
        return DrawnLayout(self.drawn, self.enabled)

    def box(self):
        return self._nested("box")

    def row(self, **kwargs):
        return self._nested("row")

    def column(self, **kwargs):
        return self._nested("column")

    def label(self, text="", icon="NONE"):
        self._check_icon(icon)
        self.drawn.append(("label", text))

    def prop(self, data, name, **kwargs):
        assert name in data.bl_rna.properties, name
        self.drawn.append(("prop", name))

    def operator(self, idname, text="", icon="NONE", **kwargs):
        module, name = idname.split(".")
        rna = getattr(getattr(bpy.ops, module), name).get_rna_type()   # raises KeyError for an unregistered operator
        self._check_icon(icon)
        self.drawn.append(("operator", idname, self.enabled))
        return OperatorProperties(self.drawn, idname, rna)

    @staticmethod
    def _check_icon(icon):
        icons = bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items.keys()
        assert icon == "NONE" or icon in icons, icon


class OperatorProperties:
    """What layout.operator returns: setting a property the operator doesn't have fails, as in Blender."""

    def __init__(self, drawn, idname, rna):
        self.__dict__.update(_drawn=drawn, _idname=idname, _rna=rna)

    def __setattr__(self, name, value):
        assert name in self._rna.properties, name
        self._drawn.append(("operator property", self._idname, name, value))


def _draw_street_look(width=2000, ui_scale=None):
    """What the Street Look panel draws now: the calls it made on its layout, in order. Background Blender has
    no region and reports online access as off, so the context gets a region (wide by default, so no sentence
    wraps) and look_refusal answers as if online access were on. ui_scale stands in for the Resolution Scale,
    which reads 0 in background Blender."""
    from types import SimpleNamespace

    from ghosttown import ui

    class Context:
        def __getattr__(self, name):   # everything else is the real context's
            return getattr(bpy.context, name)

    context = Context()
    context.region = SimpleNamespace(width=width)
    if ui_scale is not None:
        context.preferences = SimpleNamespace(system=SimpleNamespace(ui_scale=ui_scale),
                                              addons=bpy.context.preferences.addons)   # prefs.get reads these
    drawn, real = [], ops.look_refusal
    try:
        ops.look_refusal = lambda context, online=None: real(context, online=True)
        ui.GHOSTTOWN_PT_street_look.draw(SimpleNamespace(layout=DrawnLayout(drawn)), context)
    finally:
        ops.look_refusal = real
    return drawn


def test_the_street_look_panel_explains_a_refusal_and_offers_its_settings():
    prior = os.environ.get(ls.TOKEN_ENV)
    ghosttown.register()
    os.environ.pop(ls.TOKEN_ENV, None)
    try:
        drawn = _draw_street_look()   # no token
        assert ("box",) in drawn and ("label", ops.NO_TOKEN) in drawn
        assert ("operator", "ghosttown.street_look", False) in drawn   # Apply Street Look is greyed out

        os.environ[ls.TOKEN_ENV] = "MLY|abc"
        root = _picked_site()
        drawn = _draw_street_look()   # a token and a picked site
        assert ("box",) not in drawn and ("operator", "ghosttown.street_look", True) in drawn
        assert [d[1] for d in drawn if d[0] == "prop"] == [
            "look_budget", "look_not_before", "look_detail", "look_keep",   # the four settings
            "show_look", "show_detail", "look_brightness"]   # and the three switches
        assert ("operator", "ghosttown.add_sky", True) in drawn   # the scene has no world yet
        look_build.add_sky(bpy.context.scene)
        assert not any(d[:2] == ("operator", "ghosttown.add_sky") for d in _draw_street_look())

        root[look_build.SUMMARY_PROP] = "Look from photos: 2 buildings · guessed: 0"
        root[look_build.CREDITS_PROP] = CREDIT + "\n" + LABELS
        drawn = _draw_street_look()   # the site keeps a summary and credits
        assert ("box",) in drawn and ("label", "Look from photos: 2 buildings · guessed: 0") in drawn
        assert ("label", CREDIT) in drawn and ("label", LABELS) in drawn
    finally:
        _restore_env(ls.TOKEN_ENV, prior)
        ghosttown.unregister()


def test_the_no_token_hint_fits_a_retina_sidebar():
    # A 280 px sidebar at UI scale 2 reports 560 px and draws its text twice as large: about 40 characters fit.
    prior = os.environ.get(ls.TOKEN_ENV)
    ghosttown.register()
    os.environ.pop(ls.TOKEN_ENV, None)
    try:
        lines = [d[1] for d in _draw_street_look(width=560, ui_scale=2.0) if d[0] == "label"]
        assert len(lines) > 1 and " ".join(lines) == ops.NO_TOKEN and all(len(line) <= 40 for line in lines), lines
        # a narrow sidebar: GHOSTTOWN_MAPILLARY_TOKEN) is longer than a line, which textwrap breaks only with an int
        lines = [d[1] for d in _draw_street_look(width=150, ui_scale=1.0) if d[0] == "label"]
        assert "".join(lines).replace(" ", "") == ops.NO_TOKEN.replace(" ", "") and max(map(len, lines)) <= 21, lines
    finally:
        _restore_env(ls.TOKEN_ENV, prior)
        ghosttown.unregister()


def test_each_panels_cancel_button_names_its_own_run():
    from types import SimpleNamespace

    from ghosttown import ui

    ghosttown.register()
    try:
        _picked_site()
        runner.ACTIVE["build"] = runner.ACTIVE["look"] = "running"   # the panels only ask whether a run is there
        drawn = []
        ui.GHOSTTOWN_PT_main.draw(SimpleNamespace(layout=DrawnLayout(drawn)), bpy.context)
        assert ("operator property", "ghosttown.cancel", "key", "build") in drawn
        assert ("operator property", "ghosttown.cancel", "key", "look") in _draw_street_look()
    finally:
        runner.ACTIVE.pop("build", None)
        runner.ACTIVE.pop("look", None)
        ghosttown.unregister()


def test_preferences_show_the_cache_folder_in_use_on_two_lines():
    from types import SimpleNamespace

    from ghosttown import prefs

    default = "/Users/someone/Library/Application Support/Blender/5.2/extensions/.user/user_default/ghosttown/cache"
    real, asked = bpy.utils.extension_path_user, []
    ghosttown.register()
    try:
        # extension_path_user works only inside an installed extension, so it answers here for one
        bpy.utils.extension_path_user = lambda package, path="", create=False: asked.append(create) or default
        for field, shown in (("", default), ("/tmp/gt-cache/", "/tmp/gt-cache/")):
            drawn = []
            me = SimpleNamespace(layout=DrawnLayout(drawn), bl_rna=prefs.GhostTownPreferences.bl_rna, cache_dir=field)
            prefs.GhostTownPreferences.draw(me, bpy.context)
            labels = [d[1] for d in drawn if d[0] == "label"]
            assert labels[-2:] == [f"Or set {ls.TOKEN_ENV}.",
                                   "The token is saved in Blender's preferences file, never in your scene's .blend files."]
            folder = labels[:-2]
            assert "".join(folder) == shown and all(len(line) <= 60 for line in folder), folder
            assert len(folder) == (2 if field == "" else 1)
        assert asked == [False]   # showing the folder never makes it
    finally:
        bpy.utils.extension_path_user = real
        ghosttown.unregister()


def test_a_finished_look_goes_to_its_site_unless_the_site_has_gone():
    from types import SimpleNamespace

    ghosttown.register()
    try:
        root = _picked_site()
        name, reports = root.name, []
        op = SimpleNamespace(root_name=name, report=lambda *a: reports.append(a))
        answer = {"ok": True, "look": LOOK}
        assert ops.GHOSTTOWN_OT_street_look.finished(op, bpy.context, answer) == {"FINISHED"}
        assert look_build.LOOK_PROP in root and ({"INFO"}, root[look_build.SUMMARY_PROP]) in reports

        gone = [({"ERROR"}, "The site was removed while Street Look ran.")]
        scene_build.remove(root, bpy.context.scene)   # the site is removed while the fetch runs
        reports.clear()
        assert ops.GHOSTTOWN_OT_street_look.finished(op, bpy.context, answer) == {"CANCELLED"} and reports == gone
        other = bpy.data.collections.new(name)   # the name now belongs to a collection that isn't a Ghost Town site
        reports.clear()
        assert ops.GHOSTTOWN_OT_street_look.finished(op, bpy.context, answer) == {"CANCELLED"} and reports == gone
        assert look_build.LOOK_PROP not in other
    finally:
        ghosttown.unregister()


def test_street_look_from_the_search_menu_says_why_it_cannot_start():
    # F3 runs invoke even where the panel greys Apply out: with no token it says so and starts nothing.
    from types import SimpleNamespace

    from ghosttown import prefs

    prior = os.environ.get(ls.TOKEN_ENV)
    ghosttown.register()
    os.environ.pop(ls.TOKEN_ENV, None)
    real_refusal, real_cache_dir = ops.look_refusal, prefs.cache_dir
    try:
        _picked_site()
        ops.look_refusal = lambda context, online=None: real_refusal(context, online=True)   # background says offline
        prefs.cache_dir = lambda context: tempfile.mkdtemp()   # invoke reads it before the refusal
        reports, launched = [], []
        op = SimpleNamespace(report=lambda *a: reports.append(a),
                             _launch=lambda *a, **kw: launched.append(a) or {"RUNNING_MODAL"})
        assert ops.GHOSTTOWN_OT_street_look.invoke(op, bpy.context, None) == {"CANCELLED"}
        assert reports == [({"ERROR"}, ops.NO_TOKEN)] and launched == []
    finally:
        ops.look_refusal, prefs.cache_dir = real_refusal, real_cache_dir
        _restore_env(ls.TOKEN_ENV, prior)
        ghosttown.unregister()


def test_add_sky_runs_once_over_blenders_default_world():
    ghosttown.register()
    try:
        scene = bpy.context.scene
        assert scene.world is None and bpy.ops.ghosttown.add_sky.poll()
        assert bpy.ops.ghosttown.add_sky() == {"FINISHED"}
        assert scene.world.name == look_build.SKY_WORLD and look_build.SKY_SUN in scene.collection.objects
        assert not bpy.ops.ghosttown.add_sky.poll()   # the sky is the scene's own world now
    finally:
        ghosttown.unregister()


def test_applying_a_look_counts_its_detail_for_revit():
    ghosttown.register()
    try:
        root = _picked_site()
        root["ctx_triangles"] = -1   # a stale count
        ops.apply_look(bpy.context, root, LOOK, lambda *a: None)
        counted = root["ctx_triangles"]
        assert counted == site_use.count_triangles(root, bpy.context.evaluated_depsgraph_get()) > 0
    finally:
        ghosttown.unregister()


def test_the_photo_budget_allows_what_the_request_accepts():
    ghosttown.register()
    try:
        budget = props.GhostTownSettings.bl_rna.properties["look_budget"]
        assert (budget.hard_min, budget.hard_max) == ls.BUDGET_RANGE
    finally:
        ghosttown.unregister()


def test_street_look_does_not_start_on_a_failed_validation_or_without_buildings():
    prior = os.environ.get(ls.TOKEN_ENV)
    ghosttown.register()
    os.environ[ls.TOKEN_ENV] = "MLY|abc"
    real = ops.ls.validate_request
    try:
        root = _picked_site()
        cache = tempfile.mkdtemp()
        ops.ls.validate_request = lambda req: ["A made-up problem."]
        assert ops.look_launch(bpy.context, cache, online=True) == (None, "A made-up problem.")
        assert os.listdir(cache) == []   # nothing was written, not even the run folder

        ops.ls.validate_request = real
        for building in look_build.made_buildings(root):
            bpy.data.objects.remove(building)
        assert ops.look_launch(bpy.context, cache, online=True) == (None, ops.NO_BUILDINGS)
        assert os.listdir(cache) == []
    finally:
        ops.ls.validate_request = real
        _restore_env(ls.TOKEN_ENV, prior)
        ghosttown.unregister()


def test_invoking_street_look_passes_the_token_environment_and_the_site_to_the_launch():
    from types import SimpleNamespace

    from ghosttown import prefs

    prior = os.environ.get(ls.TOKEN_ENV)
    ghosttown.register()
    os.environ[ls.TOKEN_ENV] = "MLY|secret"
    cache, calls = tempfile.mkdtemp(), []
    real_refusal, real_cache_dir = ops.look_refusal, prefs.cache_dir
    try:
        root = _picked_site()
        ops.look_refusal = lambda context, online=None: real_refusal(context, online=True)   # background says offline
        prefs.cache_dir = lambda context: cache   # extension_path_user only works inside an installed extension
        op = SimpleNamespace(report=lambda *a: None,
                             _launch=lambda *a, **kw: calls.append((a, kw)) or {"RUNNING_MODAL"})
        assert ops.GHOSTTOWN_OT_street_look.invoke(op, bpy.context, None) == {"RUNNING_MODAL"}
        (args, kwargs), = calls
        assert op.root_name == root.name == "Context · 320 Bay St"   # finished() finds the site again by this name
        assert kwargs == {"env_extra": {ls.TOKEN_ENV: "MLY|secret"}}   # the token goes to the child's environment...
        _context, fetcher_args, work_dir = args
        assert fetcher_args[0] == "look" and os.path.dirname(fetcher_args[1]) == work_dir and work_dir.startswith(cache)
        assert "secret" not in repr(fetcher_args)   # ...and nowhere in its arguments
    finally:
        ops.look_refusal, prefs.cache_dir = real_refusal, real_cache_dir
        _restore_env(ls.TOKEN_ENV, prior)
        ghosttown.unregister()


def test_a_finished_look_that_cannot_be_applied_cancels_and_changes_nothing():
    from types import SimpleNamespace

    ghosttown.register()
    try:
        root = _picked_site()
        folder, reports = tempfile.mkdtemp(), []
        op = SimpleNamespace(root_name=root.name, report=lambda *a: reports.append(a))
        for text, said in (("{not json", "Couldn't read look.json"), (json.dumps({"schema": 9}), "schema")):
            path = os.path.join(folder, "look.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            reports.clear()
            assert ops.GHOSTTOWN_OT_street_look.finished(op, bpy.context, {"ok": True, "look": path}) == {"CANCELLED"}
            assert len(reports) == 1 and reports[0][0] == {"ERROR"} and said in reports[0][1], text
            assert look_build.LOOK_PROP not in root and look_build.SUMMARY_PROP not in root
    finally:
        ghosttown.unregister()
