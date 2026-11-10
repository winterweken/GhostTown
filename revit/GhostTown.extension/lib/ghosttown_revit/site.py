# -*- coding: utf-8 -*-
"""The parts of drawing a Ghost Town site in Revit that need no Revit: checking what Blender sent, metres to
feet, loops and polylines as segments long enough for Revit, the toposolid's points, a building's triangles
as faces, planting height classes, the project position, and the answer sent back.

Plain Python that runs on IronPython 2.7 (pyRevit's default engine), IronPython 3.4 and CPython 3, so no
f-strings, keyword-only arguments or other Python 3-only syntax. The format Blender sends is described in
ghosttown/revit_bridge.py; FORMAT here must match its FORMAT.
"""
from __future__ import division

import math

FORMAT = 1
METRES_PER_FOOT = 0.3048
MIN_SEGMENT_FT = 0.01        # 3 mm; Revit refuses lines shorter than its ShortCurveTolerance (about 0.0026 ft)
MAX_TOPO_POINTS = 10000      # Revit's own toposolid importer thins past about this many points
TOPO_SPACING_M = 0.5         # contour vertices closer than this (in plan) to one already kept add nothing
EDGE_PULL_M = 0.05           # the site's edge points move this far inwards, to sit inside the boundary loop
MIN_FACE_AREA_FT2 = 1e-6
HEIGHT_STEP_M = 2.0          # trees are planted from one type per this many metres of height
NOT_SUBDIVIDED = ("ground",)  # the plain ground is the toposolid itself
SECTIONS = ("buildings", "ground", "trees", "contours", "lot_lines")


def feet(metres):
    return float(metres) / METRES_PER_FOOT


def xyz_ft(point, z=None):
    """(x, y, z) in feet from a point in metres, its z replaced by `z` (metres) when given."""
    return (feet(point[0]), feet(point[1]), feet(point[2] if z is None and len(point) > 2 else (z or 0.0)))


def check(data):
    """Problems with a payload as sentences, the first the one to show; [] when it can be drawn."""
    if not isinstance(data, dict):
        return ["Ghost Town sent no site: the request body wasn't a JSON object."]
    if data.get("format") != FORMAT:
        return ["Ghost Town sent site format %s; this Revit extension reads format %d. Update both to the same "
                "Ghost Town version." % (data.get("format"), FORMAT)]
    site = data.get("site")
    if not isinstance(site, dict):
        return ["The site has no 'site' block (where it is)."]
    problems = []
    for key in ("lat", "lon", "radius_m", "boundary"):
        if key not in site:
            problems.append("The site block has no '%s'." % key)
    for key in SECTIONS:
        if not isinstance(data.get(key, []), list):
            problems.append("'%s' must be a list." % key)
    return problems


def _far_enough(a, b):
    return math.sqrt(sum((p - q) ** 2 for p, q in zip(a, b))) >= MIN_SEGMENT_FT


def polyline_segments(points, closed=False, z=None):
    """The segments of a polyline given in metres, as ((x, y, z), (x, y, z)) in feet, a point too close to the
    last one kept left out. A closed one ends where it started. `z` (metres) flattens the line onto that
    height. [] when fewer than two points (three for a closed one) are left."""
    kept = []
    for p in points:
        q = xyz_ft(p, z)
        if not kept or _far_enough(kept[-1], q):
            kept.append(q)
    if closed:
        while len(kept) > 1 and not _far_enough(kept[-1], kept[0]):
            kept.pop()                                   # the repeated first point, or one next to it
        if len(kept) < 3:
            return []
        kept.append(kept[0])
    if len(kept) < 2:
        return []
    return list(zip(kept[:-1], kept[1:]))


def loop_segments(xy_points, z=0.0):
    """A closed loop in plan (metres) at height `z`: a CurveLoop's lines, closed, planar and parallel to XY."""
    return polyline_segments([(p[0], p[1], z) for p in xy_points], closed=True)


def inside(xy, polygon):
    """True when the point lies inside the polygon (both in the same units), by ray casting."""
    x, y = xy[0], xy[1]
    result = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i][0], polygon[i][1]
        xj, yj = polygon[j][0], polygon[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            result = not result
        j = i
    return result


def _pulled_in(p, centre, by):
    dx, dy = p[0] - centre[0], p[1] - centre[1]
    d = math.hypot(dx, dy)
    if d <= by:
        return (centre[0], centre[1], p[2])
    k = (d - by) / d
    return (centre[0] + dx * k, centre[1] + dy * k, p[2])


def topo_points(contours, edge_points, boundary, max_points=MAX_TOPO_POINTS, spacing=TOPO_SPACING_M):
    """The toposolid's points in feet: the site edge's points pulled a little inwards, then the contour
    vertices inside the boundary, one per `spacing` metres in plan, every k-th of them when there are more
    than `max_points` in all. Contours are the payload's {"points": [[x, y, z]...]}; metres in."""
    n = len(boundary)
    centre = (sum(p[0] for p in boundary) / n, sum(p[1] for p in boundary) / n) if n else (0.0, 0.0)
    edge = [_pulled_in(p, centre, EDGE_PULL_M) for p in edge_points]
    seen, inner = set(), []
    for line in contours:
        for p in line.get("points", []):
            key = (int(math.floor(p[0] / spacing)), int(math.floor(p[1] / spacing)))
            if key in seen or not inside(p, boundary):
                continue
            seen.add(key)
            inner.append(p)
    room = max(0, max_points - len(edge))
    if len(inner) > room:
        step = int(math.ceil(len(inner) / float(room))) if room else len(inner) + 1
        inner = inner[::step]
    return [xyz_ft(p) for p in edge[:max_points] + inner]


def _area_ft2(a, b, c):
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    cx, cy, cz = u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]
    return 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)


def building_faces(building):
    """A building's triangles as ((a, b, c) in feet, material name), its vertices in the payload's order
    (Blender writes them outward). A triangle with a repeated corner or no area is left out."""
    verts = [xyz_ft(v) for v in building.get("verts", [])]
    names = building.get("materials") or [""]
    which = building.get("triangle_material") or []
    faces = []
    for t, tri in enumerate(building.get("triangles", [])):
        a, b, c = verts[tri[0]], verts[tri[1]], verts[tri[2]]
        if len(set(tri)) < 3 or _area_ft2(a, b, c) < MIN_FACE_AREA_FT2:
            continue
        index = which[t] if t < len(which) else 0
        faces.append(((a, b, c), names[index] if 0 <= index < len(names) else names[0]))
    return faces


def height_class(height_m, step=HEIGHT_STEP_M):
    """The planting type a tree of this height is placed from: its height rounded to `step` metres, never
    below one step."""
    return max(step, step * round(float(height_m) / step))


def planting_type_name(base, height_class_m):
    return u"%s - Ghost Town %g m" % (base, height_class_m)


def project_position(site):
    """(east-west ft, north-south ft, elevation ft, angle in radians) for SetProjectPosition at the internal
    origin, which is the site centre. With a survey point the shared coordinates are its grid: the origin
    sits at the grid easting and northing, and the angle turns project north (the model's +Y, true north
    rotated by true_north_deg) onto grid north. Revit measures the angle counterclockwise; the grid angle
    is + when grid north lies east (clockwise) of true north, hence the minus. Without a survey point the
    shared coordinates are the site's own frame. The elevation is the ground at the centre."""
    survey = site.get("survey") or {}
    turn = float(site.get("true_north_deg") or 0.0) + float(survey.get("grid_angle_deg") or 0.0)
    elevation = survey.get("elevation_m")
    if elevation is None:
        elevation = site.get("ground_at_centre_m") or 0.0
    return (feet(survey.get("easting_m") or 0.0), feet(survey.get("northing_m") or 0.0), feet(elevation),
            -math.radians(turn))


def rgb(colour):
    """An [r, g, b] of 0-255 as three ints in range, grey when it's missing or malformed."""
    try:
        return tuple(max(0, min(255, int(round(float(c))))) for c in colour[:3])
    except (TypeError, ValueError, IndexError):
        return (128, 128, 128)


class Answer(object):
    """What goes back to Blender: what was drawn, by count, and every failure with what it was and its id.
    Counts made inside a transaction wait in `pending` until it commits, so a rolled-back step counts
    nothing."""

    def __init__(self, revit=""):
        self.revit = revit
        self.drawn = {}
        self.pending = {}
        self.failures = []
        self.notes = []
        self.error = None

    def drew(self, what, n=1):
        self.pending[what] = self.pending.get(what, 0) + n

    def commit(self):
        for what, n in self.pending.items():
            self.drawn[what] = self.drawn.get(what, 0) + n
        self.pending = {}

    def discard(self):
        self.pending = {}

    def fail(self, what, ident, error):
        self.failures.append({"what": what, "id": ident or "", "error": u"%s" % (error,)})

    def note(self, text):
        self.notes.append(text)

    def fatal(self, error):
        self.error = u"%s" % (error,)
        return self.as_dict()

    def as_dict(self):
        out = {"ok": self.error is None, "format": FORMAT, "revit": self.revit, "drawn": dict(self.drawn),
               "failures": list(self.failures), "notes": list(self.notes)}
        if self.error is not None:
            out["error"] = self.error
        return out
