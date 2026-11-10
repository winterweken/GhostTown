import http.server
import json
import math
import socket
import threading
from types import SimpleNamespace

import bpy

import ghosttown
from ghosttown import materials, ops, prefs, revit_bridge, scene_build, site_apps, site_realistic, site_use
from ghosttown.ghosttown_fetch import context as ctx
from helpers import closed_and_outward, drum_doc, load_fixture

OPEN = [[-10.0, -10.0, 0.3], [0.0, -5.0, 0.3], [10.0, -10.0, 0.3]]
RING = [[20.0, 20.0, 0.8], [30.0, 20.0, 0.8], [30.0, 30.0, 0.8], [20.0, 30.0, 0.8], [20.0, 20.0, 0.8]]
ANSWER = {"ok": True, "format": 1, "revit": "2025", "notes": [], "failures": [],
          "drawn": {"georeference": 1, "coordinate_system": 1, "toposolid": 1, "toposolid_points": 900,
                    "ground_subdivisions": 3, "buildings": 3, "trees": 2, "contour_lines": 2, "lot_lines": 1}}


def drum_site():
    """The drum site (sloping ground, water and green in fans, three buildings, two trees, a lot) with an
    open contour line and a ring."""
    doc = drum_doc()
    for height, pts in (("85", OPEN), ("85.5", RING)):
        doc["elements"].append(ctx.element(f"contour:{height}", "contour", lines=[{"kind": "contour", "pts": pts}]))
    return scene_build.build(bpy.context.scene, doc)


def site_payload(root=None, **kw):
    return revit_bridge.payload(bpy.context, root or drum_site(), **kw)


# ---- the serialiser on the fixtures -------------------------------------------------------------------------

def test_the_payload_is_format_1_json_with_where_the_site_is():
    data = site_payload()
    assert data["format"] == revit_bridge.FORMAT == 1 and data["tool"].startswith("ghosttown ")
    json.dumps(data)                                                         # nothing Blender-only in it
    site = data["site"]
    assert (site["lat"], site["lon"], site["radius_m"]) == (43.649667, -79.380991, 150.0)
    assert site["ground_at_centre_m"] == 84.7 and site["true_north_deg"] == 0.0 and site["address"] == "320 Bay St"
    assert site["survey"] == {"epsg": "EPSG:32617", "name": "WGS 84 / UTM zone 17N", "easting_m": 630564.787,
                              "northing_m": 4834236.788, "elevation_m": 84.7, "grid_angle_deg": 1.117674}
    assert site["crs_wkt"].startswith("PROJCS[") and '"central_meridian",-79.38099100]' in site["crs_wkt"]
    assert len(site["boundary"]) == 256 and site["boundary"][0] == [150.0, 0.0]
    assert all(abs(math.hypot(x, y) - 150.0) < 1e-3 for x, y in site["boundary"])


def test_buildings_go_as_closed_outward_triangles_on_their_materials():
    data = site_payload()
    by_id = {b["id"]: b for b in data["buildings"]}
    assert set(by_id) == {"osm:way:1", "osm:way:2", "osm:way:9"}
    assert by_id["osm:way:2"]["kind"] == "building_guessed" and by_id["osm:way:1"]["name"] == "Tower"
    for b in by_id.values():
        assert closed_and_outward(b["verts"], b["triangles"]), b["id"]
        assert len(b["triangle_material"]) == len(b["triangles"])
        assert all(name in data["materials"] for name in b["materials"])
    assert max(v[2] for v in by_id["osm:way:1"]["verts"]) == 60.0
    assert max(v[0] for v in by_id["osm:way:9"]["verts"]) == 180.0              # untrimmed, as the OBJ goes
    building = materials.material_name("building")
    assert data["materials"][building] == revit_bridge.srgb(materials.COLOURS["building"])


def test_ground_pieces_are_plan_loops_one_per_connected_piece():
    data = site_payload()
    kinds = sorted(p["kind"] for p in data["ground"])
    assert kinds == ["green", "ground", "water"]                                # the drum has no road
    doc = load_fixture("mini_context.json")
    doc["address"] = "Road site"                                                  # beside the drum, not over it
    mini = scene_build.build(bpy.context.scene, doc)
    road, = revit_bridge.payload(bpy.context, mini)["ground"]
    assert road["material"] == "Context - Road" and len(road["loops"]) == 1
    assert sorted(map(tuple, road["loops"][0])) == [(-10, -3), (-10, 3), (10, -3), (10, 3)]
    green = next(p for p in data["ground"] if p["kind"] == "green")
    outside = green["loops"][0]
    assert revit_bridge._area(outside) > 0 and [0.0, 0.0] in outside            # the fan's centre
    assert len(outside) == 1 + 61                                                 # centre + rim, no fan spokes
    edge = data["site"]["edge_points"]
    assert len(edge) >= 256 and all(abs(math.hypot(x, y) - 150.0) <= 0.05 for x, y, _z in edge)
    assert all(abs(z - 0.02 * x) < 1e-3 for x, _y, z in edge)                   # on the sloping ground


def test_trees_go_as_points_with_heights():
    data = site_payload()
    assert [(t["x"], t["y"], t["z"], t["height_m"]) for t in data["trees"]] == [
        (60.5, 0.5, 0.0, 7.0),                       # the trunk inside its crown: one tree
        (150.5, 0.5, 3.0, 3.0)]                     # the rim tree, on the slope


def test_contours_and_lot_lines_go_as_polylines():
    data = site_payload()
    contours = sorted(data["contours"], key=lambda c: c["z"])
    assert [(c["z"], c["closed"], len(c["points"])) for c in contours] == [(0.3, False, 3), (0.8, True, 4)]
    assert contours[0]["points"] == OPEN and contours[0]["material"] == "Context - Contour"
    lot, = data["lot_lines"]
    assert lot["kind"] == "parcel" and lot["closed"] and len(lot["points"]) == 4
    assert lot["material"] == "Context - Parcel" and "Context - Parcel" in data["materials"]


def test_the_site_reads_plain_and_comes_back_as_it_was():
    root = drum_site()
    site_use.apply_ground(root, "realistic")
    tree = next(o for o in root.all_objects if o.get("ctx_kind") == "tree")
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    tree.select_set(True)
    bpy.context.view_layer.objects.active = tree
    data = site_payload(root)
    assert not any("Realistic" in name or name == "Earth" for name in data["materials"])
    assert max(v[0] for b in data["buildings"] for v in b["verts"]) == 180.0   # no edge trim
    assert root["use_ground"] == "realistic" and site_realistic.find(root, "earth") is not None
    assert [o for o in bpy.context.view_layer.objects if o.select_get()] == [tree]


def test_application_boxes_go_as_buildings_unless_left_out():
    root = drum_site()
    me = bpy.data.meshes.new("Box")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)], [],
                   [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
    box = bpy.data.objects.new("Box", me)
    box[site_apps.BOX_SITE] = root["ctx_label"]
    bpy.context.scene.collection.objects.link(box)
    kinds = [b["kind"] for b in site_payload(root)["buildings"]]
    assert kinds.count("application") == 1
    assert "application" not in [b["kind"] for b in site_payload(root, applications=False)["buildings"]]


# ---- plain geometry -----------------------------------------------------------------------------------------

def test_a_piece_with_a_hole_has_its_outside_first_and_triangle_soup_is_welded():
    outer, inner = [(0, 0), (10, 0), (10, 10), (0, 10)], [(3, 3), (7, 3), (7, 7), (3, 7)]
    verts = [(x, y, 0.0) for x, y in outer + inner]
    faces = []
    for i in range(4):
        j = (i + 1) % 4
        faces += [(i, j, 4 + j), (i, 4 + j, 4 + i)]
    piece, = revit_bridge.plan_pieces(verts, faces)
    assert len(piece) == 2 and revit_bridge._area(piece[0]) == 100 and revit_bridge._area(piece[1]) == -16
    soup = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 0, 0.001), (1, 1, 0), (0, 1, 0)]   # no shared indices
    piece, = revit_bridge.plan_pieces(soup, [(0, 1, 2), (3, 4, 5)])
    assert len(piece) == 1 and len(piece[0]) == 4
    two = revit_bridge.plan_pieces([(0, 0, 0), (1, 0, 0), (0, 1, 0), (5, 5, 0), (6, 5, 0), (5, 6, 0)],
                                   [(0, 1, 2), (3, 4, 5)])
    assert len(two) == 2


def test_a_loop_drops_points_on_a_straight_edge():
    verts = [(0, 0, 0), (5, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)]
    piece, = revit_bridge.plan_pieces(verts, [(0, 1, 4), (1, 2, 3), (1, 3, 4)])
    assert sorted(map(tuple, piece[0])) == [(0, 0), (0, 10), (10, 0), (10, 10)]


def test_side_by_side_trees_stay_apart():
    def box(x, y, z0, z1, size):
        verts = [(x - size, y - size, z0), (x + size, y - size, z0), (x, y + size, z0), (x, y, z1)]
        return verts, [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]

    verts, faces = [], []
    for part in (box(0, 0, 0, 5, 0.2), box(0, 0, 3, 9, 3), box(20, 0, 1, 4, 0.2), box(20, 0, 2, 7, 2)):
        faces += [tuple(i + len(verts) for i in f) for f in part[1]]
        verts += part[0]
    trees = revit_bridge.tree_parts(verts, faces)
    assert [(t["x"], t["z"], t["height_m"]) for t in trees] == [(0.0, 0.0, 9.0), (20.0, 1.0, 6.0)]


# ---- sending ------------------------------------------------------------------------------------------------

class _Receiver(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.server.seen.append({"path": self.path, "type": self.headers["Content-Type"], "body": body})
        status, reply = self.server.reply
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(reply if isinstance(reply, bytes) else json.dumps(reply).encode("utf-8"))

    def log_message(self, *args):
        pass


class StandIn:
    """pyRevit's Routes server, standing in: records each request and answers `reply` with `status`."""

    def __init__(self, reply=ANSWER, status=200):
        self.server = http.server.HTTPServer(("127.0.0.1", 0), _Receiver)
        self.server.seen, self.server.reply = [], (status, reply)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def seen(self):
        return self.server.seen

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def test_send_posts_the_json_to_the_site_route_and_returns_the_answer():
    data = {"format": 1, "site": {"lat": 1.0}}
    with StandIn() as revit:
        answer = revit_bridge.send(data, "127.0.0.1", revit.port)
    request, = revit.seen
    assert request["path"] == "/ghosttown/site" and request["type"] == "application/json"
    assert json.loads(request["body"]) == data and answer == ANSWER


def test_send_says_why_when_revit_refuses_or_answers_nonsense():
    with StandIn({"exception": {"message": "name 'doc' is not defined"}}, status=500) as revit:
        try:
            revit_bridge.send({}, "127.0.0.1", revit.port)
            raise AssertionError("no error")
        except revit_bridge.BridgeError as e:
            assert "answered 500" in str(e) and "name 'doc' is not defined" in str(e)
    with StandIn(b"<html>not Revit</html>") as revit:
        try:
            revit_bridge.send({}, "127.0.0.1", revit.port)
            raise AssertionError("no error")
        except revit_bridge.BridgeError as e:
            assert "Routes port" in str(e)


def test_send_says_so_when_nothing_listens():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]                      # free, and nothing listening on it
    try:
        revit_bridge.send({}, "127.0.0.1", port, timeout=5)
        raise AssertionError("no error")
    except revit_bridge.BridgeError as e:
        assert str(e).startswith(f"Couldn't reach Revit at 127.0.0.1:{port}") and "Preferences" in str(e)


def test_another_computer_needs_online_access_and_this_one_does_not():
    assert revit_bridge.refusal("localhost", 48884, online=False) is None
    assert revit_bridge.refusal("127.0.0.1", 48884, online=False) is None
    assert revit_bridge.refusal("::1", 48884, online=False) is None
    assert "Allow Online Access" in revit_bridge.refusal("192.168.1.20", 48884, online=False)
    assert revit_bridge.refusal("192.168.1.20", 48884, online=True) is None
    assert "port" in revit_bridge.refusal("localhost", 0, online=True)
    assert revit_bridge.url("::1", 48884) == "http://[::1]:48884/ghosttown/site"


def test_the_answer_is_reported_like_a_build():
    lines = revit_bridge.report_lines(ANSWER)
    assert lines == [("INFO", "Revit 2025 drew 1 toposolid, 3 ground subdivisions, 3 buildings, 2 trees, "
                              "2 contour lines, 1 lot line, and placed the site on its survey grid.")]
    failures = [{"what": "tree", "id": f"tree {n}", "error": "no level"} for n in range(7)]
    lines = revit_bridge.report_lines(dict(ANSWER, failures=failures, notes=["A note."],
                                           drawn={"buildings": 2, "buildings_as_mesh": 1}))
    assert lines[0] == ("INFO", "Revit 2025 drew 2 buildings.")
    assert lines[1][0] == "WARNING" and "1 building came in as a mesh" in lines[1][1]
    assert lines[2] == ("WARNING", "Revit couldn't draw tree tree 0: no level")
    assert lines[-2] == ("WARNING", "…and 2 more failures.") and lines[-1] == ("INFO", "A note.")
    assert revit_bridge.report_lines({"ok": False, "error": "No Revit document is open."}) == [
        ("ERROR", "Revit couldn't draw the site: No Revit document is open.")]


def _send_with_the_operator(port, reply=ANSWER):
    ghosttown.register()
    saved = prefs.revit_address
    try:
        bpy.context.scene.ghosttown.site = drum_site()
        assert bpy.ops.ghosttown.send_revit.poll()
        prefs.revit_address = lambda context: ("127.0.0.1", port)
        reports = []
        op = SimpleNamespace(applications=True, report=lambda level, said: reports.append((level.pop(), said)))
        return ops.GHOSTTOWN_OT_send_revit.execute(op, bpy.context), reports
    finally:
        prefs.revit_address = saved
        ghosttown.unregister()


def test_the_operator_sends_the_picked_site_and_reports_what_revit_drew():
    with StandIn() as revit:
        result, reports = _send_with_the_operator(revit.port)
    assert result == {"FINISHED"}
    assert reports == revit_bridge.report_lines(ANSWER)
    sent = json.loads(revit.seen[0]["body"])
    assert sent["format"] == 1 and len(sent["buildings"]) == 3 and sent["site"]["address"] == "320 Bay St"


def test_the_operator_reports_revits_error():
    with StandIn({"ok": False, "format": 1, "error": "No Revit document is open."}) as revit:
        result, reports = _send_with_the_operator(revit.port)
    assert result == {"CANCELLED"}
    assert reports == [("ERROR", "Revit couldn't draw the site: No Revit document is open.")]


def test_the_operator_needs_a_picked_site_and_defaults_to_loopback():
    ghosttown.register()
    try:
        bpy.context.scene.ghosttown.site = None
        assert not bpy.ops.ghosttown.send_revit.poll()
        assert prefs.revit_address(bpy.context) == ("127.0.0.1", 48884)
    finally:
        ghosttown.unregister()
