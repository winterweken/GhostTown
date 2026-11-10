"""Send to Revit: the picked site as JSON to Ghost Town's pyRevit extension (revit/GhostTown.extension in the
repository), which draws it in the open Revit project as native elements. The site is read as Export for
Revit reads it (revit_export.plain_site): its visible objects, plain ground and roofs, modifiers applied.

Format 1 (FORMAT below; the Revit side's ghosttown_revit/site.py has the same number). One JSON object, sent as
POST http://<host>:<port>/ghosttown/site with Content-Type application/json. Lengths are metres in the site's
frame, the OBJ export's: x east, y north, z up, the origin at the site centre on the ground, z 0 being
ground_at_centre_m above sea level. Points are [x, y, z] (or [x, y] in plan), to the millimetre.

    format       1
    tool         "ghosttown 0.8.1"
    site         label, address
                 lat, lon             the site centre, WGS 84 degrees
                 radius_m
                 ground_at_centre_m   metres above sea level at the origin, or null when unknown
                 true_north_deg       true north's bearing from +y, clockwise; 0, since +y is true north
                 crs_wkt              the site frame as a transverse Mercator on the centre (WKT 1), which it
                                      matches to millimetres within 1 km
                 survey               where the origin sits on the survey grid, or null: epsg, name,
                                      easting_m, northing_m, elevation_m (or null), grid_angle_deg (+ when
                                      grid north lies east of true north)
                 boundary             the site circle in plan: 256 corners on the radius, counterclockwise
                 edge_points          ground vertices on that circle, for the toposolid's rim
    materials    {name: [r, g, b]}, sRGB 0-255, for every material named below
    buildings    [{id, name, kind, verts, triangles: [[i, j, k]...], materials: [name...],
                  triangle_material: [index into materials, one per triangle]}]: each building and
                 development application box (kind "application"), triangles counterclockwise seen from
                 outside
    ground       [{id, kind, material, loops: [[[x, y]...]...]}]: each connected piece of road, sidewalk,
                 parking, rail, water, green and plain ground in plan; its first loop is the outside
                 (counterclockwise), the others its holes (clockwise); no loop repeats its first point
    trees        [{id, x, y, z, height_m}]: (x, y) the trunk, z the tree's lowest point, height_m to the
                 crown's top
    contours     [{z, material, points, closed}]: closed lines don't repeat their first point
    lot_lines    [{id, kind, material, points, closed}]: kind parcel, or parcel_on_site for the site's own

Revit answers {ok, format, revit (its version), drawn: {what: count}, failures: [{what, id, error}],
notes: [...]}, with error when ok is false.
"""
import ipaddress
import json
import math
import urllib.error
import urllib.request

import numpy as np

from . import georef, materials, revit_export, site_apps, site_contours
from .ghosttown_fetch import BUILDING_KINDS, CIRCLE_QUAD_SEGS, GROUND_KINDS, TOOL

FORMAT = 1
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 48884             # pyRevit Routes' port
PATH = "/ghosttown/site"
TIMEOUT_S = 600                  # a big site takes Revit minutes
EDGE_TOLERANCE_M = 0.05          # a ground vertex this close to the radius lies on the site's edge
MAX_EDGE_POINTS = 4 * CIRCLE_QUAD_SEGS * 2
WELD_DIGITS = 3                  # ground vertices are joined when they match to the millimetre in plan
STRAIGHT_M = 0.01                # a loop point within this of the line through its neighbours is dropped
CONTAINS_M = 0.01                # slack when a tree part's plan box sits inside another's
MAX_FAILURES_SHOWN = 5
LINE_KINDS = ("parcel", "parcel_on_site")
APPLICATION = "application"
DRAWN = (  # what Revit drew, in the report's order: answer key, singular, plural
    ("toposolid", "toposolid", "toposolids"),
    ("ground_subdivisions", "ground subdivision", "ground subdivisions"),
    ("buildings", "building", "buildings"),
    ("trees", "tree", "trees"),
    ("contour_lines", "contour line", "contour lines"),
    ("lot_lines", "lot line", "lot lines"),
    ("materials_created", "new material", "new materials"),
    ("planting_types_created", "new planting type", "new planting types"),
)
QUIET = ("georeference", "coordinate_system", "toposolid_points", "buildings_as_mesh")   # said otherwise


class BridgeError(Exception):
    """Sending failed; the message is the sentence to show."""


# ---- plain geometry, no bpy ---------------------------------------------------------------------------------

def site_wkt(lat, lon):
    """The site frame (x east, y north, metres, origin at the centre) as WKT 1: a transverse Mercator on the
    centre with scale 1, the CRS georef.set_scene_georef gives the scene."""
    return ('PROJCS["Ghost Town site %.6f, %.6f",GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,'
            '298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],'
            'PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",%.8f],'
            'PARAMETER["central_meridian",%.8f],PARAMETER["scale_factor",1],PARAMETER["false_easting",0],'
            'PARAMETER["false_northing",0],UNIT["metre",1],AXIS["Easting",EAST],AXIS["Northing",NORTH]]'
            % (lat, lon, lat, lon))


def boundary(radius):
    """The site circle as the fetcher cuts the ground to it: 4 × CIRCLE_QUAD_SEGS corners on the radius."""
    n = 4 * CIRCLE_QUAD_SEGS
    return [[round(radius * math.cos(2 * math.pi * k / n), 3), round(radius * math.sin(2 * math.pi * k / n), 3)]
            for k in range(n)]


def srgb(linear_rgb):
    """Blender's linear colour as sRGB 0-255."""
    def one(c):
        c = min(1.0, max(0.0, float(c)))
        return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return [int(round(255 * one(c))) for c in linear_rgb[:3]]


class _Sets:
    """Union-find over vertex indices."""

    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, a):
        while self.parent[a] != a:
            self.parent[a] = self.parent[self.parent[a]]
            a = self.parent[a]
        return a

    def join(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


def _components(n, faces):
    sets = _Sets(n)
    for f in faces:
        for v in f[1:]:
            sets.join(f[0], v)
    return sets


def weld_plan(verts, faces, digits=WELD_DIGITS):
    """(plan points, faces) with vertices that match in plan to `digits` decimals made one; faces left with
    fewer than three corners go."""
    index, points, remap = {}, [], []
    for v in verts:
        key = (round(v[0], digits), round(v[1], digits))
        if key not in index:
            index[key] = len(points)
            points.append(key)
        remap.append(index[key])
    out = []
    for f in faces:
        g = [remap[i] for i in f]
        if len(set(g)) == len(g) >= 3:
            out.append(g)
    return points, out


def _area(points):
    return 0.5 * sum(points[i - 1][0] * points[i][1] - points[i][0] * points[i - 1][1] for i in range(len(points)))


def _straightened(points):
    """The loop without points lying (within STRAIGHT_M) on the line through their neighbours."""
    pts = list(points)
    i = 0
    while len(pts) > 3 and i < len(pts):
        (ax, ay), (bx, by), (cx, cy) = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
        length = math.hypot(cx - ax, cy - ay)
        off = abs((cx - ax) * (by - ay) - (cy - ay) * (bx - ax)) / length if length else 0.0
        if off < STRAIGHT_M:
            del pts[i]
        else:
            i += 1
    return pts


def plan_pieces(verts, faces):
    """The connected pieces of a mesh in plan, each [outside, hole, ...] as lists of [x, y], the outside
    counterclockwise and holes clockwise. Built from its boundary edges: those only one face uses."""
    points, faces = weld_plan(verts, faces)
    uses = {}
    for f in faces:
        for i in range(len(f)):
            key = frozenset((f[i - 1], f[i]))
            uses[key] = uses.get(key, 0) + 1
    after = {}
    for f in faces:
        for i in range(len(f)):
            a, b = f[i - 1], f[i]
            if uses[frozenset((a, b))] == 1:
                after.setdefault(a, []).append(b)
    loops = []
    while after:
        start = next(iter(after))
        loop, v = [start], start
        while True:
            nxt = after[v].pop()
            if not after[v]:
                del after[v]
            if nxt == start or nxt not in after:
                break
            loop.append(nxt)
            v = nxt
        if len(loop) >= 3:
            loops.append(loop)
    sets = _components(len(points), faces)
    pieces = {}
    for loop in loops:
        xy = _straightened([list(points[i]) for i in loop])
        if len(xy) >= 3 and abs(_area(xy)) > 1e-6:
            pieces.setdefault(sets.find(loop[0]), []).append(xy)
    out = []
    for key in sorted(pieces):
        rings = sorted(pieces[key], key=lambda r: -abs(_area(r)))
        rings = [r if (_area(r) > 0) == (i == 0) else r[::-1] for i, r in enumerate(rings)]
        out.append(rings)
    return out


def tree_parts(verts, faces):
    """Trees from a merged tree mesh: its loose parts grouped by plan box, a part inside another's box (a
    trunk in its crown) joining it. Each tree is (x, y) of its smallest part's box centre (the trunk), z its
    lowest point and its height to its highest."""
    sets = _components(len(verts), faces)
    boxes = {}
    for f in faces:
        root = sets.find(f[0])
        for i in f:
            x, y, z = verts[i]
            b = boxes.setdefault(root, [x, y, z, x, y, z])
            b[0], b[1], b[2] = min(b[0], x), min(b[1], y), min(b[2], z)
            b[3], b[4], b[5] = max(b[3], x), max(b[4], y), max(b[5], z)
    parts = sorted(boxes.values(), key=lambda b: -(b[3] - b[0]) * (b[4] - b[1]))
    groups = []
    for b in parts:
        home = next((g for g in groups if g[0][0] - CONTAINS_M <= b[0] and g[0][1] - CONTAINS_M <= b[1]
                     and b[3] <= g[0][3] + CONTAINS_M and b[4] <= g[0][4] + CONTAINS_M), None)
        if home is None:
            groups.append([b])
        else:
            home.append(b)
    trees = []
    for g in groups:
        trunk = g[-1]
        low, high = min(b[2] for b in g), max(b[5] for b in g)
        trees.append({"x": round((trunk[0] + trunk[3]) / 2, 3), "y": round((trunk[1] + trunk[4]) / 2, 3),
                      "z": round(low, 3), "height_m": round(high - low, 3)})
    trees.sort(key=lambda t: (t["x"], t["y"]))
    return trees


def edge_points(verts, radius, limit=MAX_EDGE_POINTS):
    """Vertices lying on the site circle, one per millimetre spot, sorted by angle, every k-th past `limit`."""
    seen, out = set(), []
    for x, y, z in verts:
        if abs(math.hypot(x, y) - radius) <= EDGE_TOLERANCE_M:
            key = (round(x, 3), round(y, 3))
            if key not in seen:
                seen.add(key)
                out.append([key[0], key[1], round(z, 3)])
    out.sort(key=lambda p: math.atan2(p[1], p[0]))
    step = max(1, math.ceil(len(out) / limit))
    return out[::step]


# ---- reading the site in Blender ----------------------------------------------------------------------------

def _evaluated(ob, depsgraph):
    """(world verts as an (n, 3) array, triangles as an (m, 3) array, triangle material indices, slot material
    names) of the object with its modifiers."""
    ev = ob.evaluated_get(depsgraph)
    me = ev.to_mesh()
    try:
        me.calc_loop_triangles()
        co = np.empty(len(me.vertices) * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        tris = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", tris)
        which = np.empty(len(me.loop_triangles), dtype=np.int64)
        me.loop_triangles.foreach_get("material_index", which)
    finally:
        ev.to_mesh_clear()
    world = np.array(ob.matrix_world, dtype=np.float64)
    co = co.reshape(-1, 3) @ world[:3, :3].T + world[:3, 3]
    names = [slot.material.name if slot.material else "" for slot in ev.material_slots]
    return co, tris.reshape(-1, 3), which, names


def _kind(ob):
    if site_apps.BOX_SITE in ob:
        return APPLICATION
    return ob.get("ctx_kind", "")


def payload(context, root, applications=True):
    """The site as format 1 (see the module's docstring), read through revit_export.plain_site."""
    used = {}
    out = {"format": FORMAT, "tool": TOOL, "site": _site(root), "materials": used, "buildings": [],
           "ground": [], "trees": [], "contours": [], "lot_lines": []}

    def material(name):
        if name and name not in used:
            mat = context.blend_data.materials.get(name)
            used[name] = srgb(mat.diffuse_color) if mat is not None else [128, 128, 128]
        return name

    with revit_export.plain_site(context, root, applications) as obs:
        context.view_layer.update()
        depsgraph = context.evaluated_depsgraph_get()
        rim = []
        for ob in obs:
            kind = _kind(ob)
            if ob.type != "MESH" or not kind:
                continue
            if kind in BUILDING_KINDS or kind == APPLICATION:
                co, tris, which, names = _evaluated(ob, depsgraph)
                if not len(tris):
                    continue
                names = [material(n) for n in names] or [material(materials.material_name("building"))]
                out["buildings"].append({
                    "id": ob.get("ctx_id") or ob.name, "name": ob.name, "kind": kind,
                    "verts": np.round(co, 3).tolist(), "triangles": tris.tolist(),
                    "materials": names, "triangle_material": np.clip(which, 0, len(names) - 1).tolist()})
            elif kind in GROUND_KINDS:
                co, tris, _which, _names = _evaluated(ob, depsgraph)
                rim += co.tolist()
                name = material(materials.material_name(kind))
                for n, loops in enumerate(plan_pieces(co.tolist(), tris.tolist()), 1):
                    out["ground"].append({"id": f"{kind} {n}", "kind": kind, "material": name,
                                          "loops": [[[round(x, 3), round(y, 3)] for x, y in r] for r in loops]})
            elif kind == "tree":
                co, tris, _which, _names = _evaluated(ob, depsgraph)
                for n, tree in enumerate(tree_parts(co.tolist(), tris.tolist()), 1):
                    out["trees"].append({"id": f"tree {n}", **tree})
            elif kind == "contour":
                name = material(materials.material_name(kind))
                for points, closed in site_contours.polylines(ob):
                    out["contours"].append({"z": round(points[0][2], 3), "material": name, "closed": closed,
                                            "points": [[round(c, 3) for c in p] for p in points]})
            elif kind in LINE_KINDS:
                name = material(materials.material_name(kind))
                for n, (points, closed) in enumerate(site_contours.polylines(ob), 1):
                    out["lot_lines"].append({"id": f"{kind} {n}", "kind": kind, "material": name, "closed": closed,
                                             "points": [[round(c, 3) for c in p] for p in points]})
        out["site"]["edge_points"] = edge_points(rim, out["site"]["radius_m"])
    return out


def _site(root):
    lat, lon = float(root.get("lat", 0.0)), float(root.get("lon", 0.0))
    radius = float(root.get("radius_m", 0.0))
    ground = root.get("ground_at_centre_m")
    survey = None
    point = georef.survey_from(root)
    if point:
        survey = {key: point[key] for key in ("epsg", "name", "easting_m", "northing_m", "elevation_m",
                                              "grid_angle_deg")}
    return {"label": root.get("ctx_label", ""), "address": root.get("address", ""), "lat": lat, "lon": lon,
            "radius_m": radius, "ground_at_centre_m": None if ground is None else float(ground),
            "true_north_deg": float(root.get("true_north_deg", 0.0)), "crs_wkt": site_wkt(lat, lon),
            "survey": survey, "boundary": boundary(radius), "edge_points": []}


def counts(data):
    """What a payload holds, as one sentence's worth: '3 buildings, 4 ground pieces, …'."""
    parts = [(len(data[key]), one, many) for key, one, many in
             (("buildings", "building", "buildings"), ("ground", "ground piece", "ground pieces"),
              ("trees", "tree", "trees"), ("contours", "contour line", "contour lines"),
              ("lot_lines", "lot line", "lot lines"))]
    return ", ".join(f"{n} {one if n == 1 else many}" for n, one, many in parts if n) or "nothing"


# ---- sending ------------------------------------------------------------------------------------------------

def is_loopback(host):
    host = host.strip().strip("[]")
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def refusal(host, port, online):
    """Why the site can't be sent to this address, as a sentence, or None. Another computer is a network
    connection, which Blender's Allow Online Access governs; this one isn't."""
    if not host.strip():
        return "Set the Revit host in Preferences › Add-ons › Ghost Town."
    if not 0 < int(port) < 65536:
        return "The Revit port must be from 1 to 65535."
    if not online and not is_loopback(host):
        return ("Online access is off, and Revit is on another computer. Turn on Preferences › System › "
                "Network › Allow Online Access, or run Revit on this computer and send to localhost.")
    return None


def url(host, port):
    host = host.strip()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"                          # an IPv6 address
    return f"http://{host}:{int(port)}{PATH}"


def send(data, host, port, timeout=TIMEOUT_S):
    """POST the payload to Revit and return its answer (a dict). BridgeError when Revit can't be reached or
    doesn't answer with a JSON object. Never through a proxy: Revit is on this computer or this network."""
    request = urllib.request.Request(url(host, port), data=json.dumps(data, separators=(",", ":")).encode("utf-8"),
                                     method="POST", headers={"Content-Type": "application/json", "User-Agent": TOOL})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    where = f"{host.strip()}:{int(port)}"
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as e:
        raise BridgeError(f"Revit at {where} answered {e.code}: {_reason(e.read())}") from None
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", None) or e
        raise BridgeError(f"Couldn't reach Revit at {where} ({reason}). Check that Revit is open with pyRevit's "
                          "Routes server on and Ghost Town's extension loaded, and the host and port in "
                          "Preferences › Add-ons › Ghost Town.") from None
    try:
        answer = json.loads(body.decode("utf-8"))
    except ValueError:
        answer = None
    if not isinstance(answer, dict):
        raise BridgeError(f"Revit at {where} answered something other than Ghost Town's JSON. Is the port "
                          "pyRevit's Routes port?")
    return answer


def _reason(body):
    """pyRevit's error body ({"exception": {"message": …}}) or our own answer, as text."""
    try:
        data = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, AttributeError):
        return "no reason given"
    if isinstance(data, dict):
        exc = data.get("exception")
        if isinstance(exc, dict):
            return str(exc.get("message") or exc)
        if data.get("error"):
            return str(data["error"])
    return "no reason given"


def report_lines(answer):
    """[(level, sentence)] for an answer from Revit: what it drew, then its failures and notes."""
    if not answer.get("ok"):
        return [("ERROR", f"Revit couldn't draw the site: {answer.get('error') or 'no reason given'}")]
    drawn = answer.get("drawn") or {}
    parts = [f"{drawn[key]} {one if drawn[key] == 1 else many}" for key, one, many in DRAWN if drawn.get(key)]
    known = {key for key, _one, _many in DRAWN} | set(QUIET)
    parts += [f"{n} {key.replace('_', ' ')}" for key, n in sorted(drawn.items()) if key not in known and n]
    revit = f"Revit {answer['revit']}" if answer.get("revit") else "Revit"
    text = f"{revit} drew {', '.join(parts)}" if parts else f"{revit} drew nothing"
    if drawn.get("georeference"):
        text += ", and placed the site on " + ("its survey grid" if drawn.get("coordinate_system") else "the map")
    lines = [("INFO", text + ".")]
    meshes = drawn.get("buildings_as_mesh")
    if meshes:
        lines.append(("WARNING", f"{meshes} building{' came' if meshes == 1 else 's came'} in as a mesh, not a "
                                 "solid: one material, and no cutting in sections."))
    failures = answer.get("failures") or []
    for f in failures[:MAX_FAILURES_SHOWN]:
        what = " ".join(str(part) for part in (f.get("what"), f.get("id")) if part)
        lines.append(("WARNING", f"Revit couldn't draw {what}: {f.get('error') or 'no reason given'}"))
    if len(failures) > MAX_FAILURES_SHOWN:
        rest = len(failures) - MAX_FAILURES_SHOWN
        lines.append(("WARNING", f"…and {rest} more failure{'' if rest == 1 else 's'}."))
    lines += [("INFO", str(note)) for note in answer.get("notes") or []]
    return lines
