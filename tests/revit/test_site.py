"""The Revit side's plain-Python parts (revit/GhostTown.extension/lib/ghosttown_revit/site.py), without Revit."""
import ast
import math
import os

import pytest

from ghosttown_revit import site as gs

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXTENSION = os.path.join(ROOT, "revit", "GhostTown.extension")
FT = 1 / 0.3048


def payload(**over):
    data = {"format": gs.FORMAT,
            "site": {"lat": 43.65, "lon": -79.38, "radius_m": 150.0,
                     "boundary": [[150.0, 0.0], [0.0, 150.0], [-150.0, 0.0], [0.0, -150.0]]},
            "buildings": [], "ground": [], "trees": [], "contours": [], "lot_lines": []}
    data.update(over)
    return data


def test_metres_become_feet():
    assert gs.feet(0.3048) == pytest.approx(1.0)
    assert gs.xyz_ft([3.048, -0.3048, 30.48]) == pytest.approx((10.0, -1.0, 100.0))
    assert gs.xyz_ft([3.048, 0.0], z=0.6096) == pytest.approx((10.0, 0.0, 2.0))
    assert gs.xyz_ft([3.048, 0.0]) == pytest.approx((10.0, 0.0, 0.0))


def test_a_good_payload_has_no_problems_and_a_bad_one_says_why_first():
    assert gs.check(payload()) == []
    assert "JSON object" in gs.check([])[0]
    assert "format 2" in gs.check(payload(format=2))[0]
    assert "boundary" in gs.check(payload(site={"lat": 1, "lon": 2, "radius_m": 3}))[0]
    assert "'trees' must be a list" in gs.check(payload(trees={}))[0]


def test_a_loop_closes_on_its_first_point_flat_at_its_height():
    square = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]       # first point repeated, as rings are written
    segments = gs.loop_segments(square, z=3.048)
    assert len(segments) == 4
    assert segments[-1][1] == segments[0][0]
    for (a, b), (c, _d) in zip(segments, segments[1:]):
        assert b == c                                             # each line starts where the last one ended
    assert all(p[2] == pytest.approx(10.0) for seg in segments for p in seg)


def test_points_closer_than_revit_draws_are_dropped_and_a_too_small_loop_is_none():
    near = [[0, 0, 0], [0.0005, 0, 0], [5, 0, 0], [5, 5, 0], [0.0004, 0.0004, 0]]
    segments = gs.polyline_segments(near, closed=True)
    assert len(segments) == 3                                      # the near-duplicates of the start went
    assert all(math.dist(a, b) >= gs.MIN_SEGMENT_FT for a, b in segments)
    assert gs.loop_segments([[0, 0], [1, 0], [0.0001, 0.0001]]) == []
    assert gs.polyline_segments([[0, 0, 0]]) == []


def test_an_open_polyline_keeps_its_ends_and_can_be_flattened():
    segments = gs.polyline_segments([[0, 0, 1], [10, 0, 2], [10, 10, 3]], z=0.0)
    assert len(segments) == 2 and segments[0][0] == (0.0, 0.0, 0.0) and segments[-1][1][2] == 0.0


def test_ray_casting_inside():
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert gs.inside((5, 5), square) and not gs.inside((15, 5), square) and not gs.inside((5, -1), square)


def test_topo_points_keep_the_edge_take_contour_vertices_inside_once_per_spacing_and_thin_past_the_cap():
    boundary = [[100 * math.cos(math.radians(a)), 100 * math.sin(math.radians(a))] for a in range(0, 360, 10)]
    edge = [[p[0], p[1], 1.0] for p in boundary]
    contours = [{"points": [[x, 0.0, 2.0] for x in (-150, -10, -9.9, 0, 10, 150)]}]   # two outside, one too near
    points = gs.topo_points(contours, edge, boundary)
    assert len(points) == len(edge) + 3
    radii = [math.hypot(p[0], p[1]) / FT for p in points[:len(edge)]]
    assert all(r == pytest.approx(100 - gs.EDGE_PULL_M) for r in radii)          # pulled inside the loop
    assert all(gs.inside((p[0] / FT, p[1] / FT), boundary) for p in points)
    many = [{"points": [[x * 0.6, y * 0.6, 0.0] for x in range(-100, 100) for y in range(-100, 100)]}]
    thinned = gs.topo_points(many, edge, boundary, max_points=1000)
    assert len(edge) < len(thinned) <= 1000


def test_building_faces_are_triangles_in_feet_on_their_materials_without_degenerate_ones():
    building = {"verts": [[0, 0, 0], [3.048, 0, 0], [0, 3.048, 0], [0, 0, 3.048], [6.096, 0, 0]],
                "triangles": [[0, 2, 1], [0, 1, 3], [0, 1, 4], [0, 0, 3]],   # the last two have no area
                "materials": ["Context - Building", "Context - Building (on site)"],
                "triangle_material": [0, 1, 0, 1]}
    faces = gs.building_faces(building)
    assert [name for _, name in faces] == ["Context - Building", "Context - Building (on site)"]
    assert [c for p in faces[0][0] for c in p] == pytest.approx([0, 0, 0, 0, 10, 0, 10, 0, 0])
    assert gs.building_faces({"verts": [[0, 0, 0], [1, 0, 0], [0, 1, 0]], "triangles": [[0, 1, 2]]})[0][1] == ""


def test_trees_are_planted_from_one_type_per_two_metres():
    assert [gs.height_class(h) for h in (0.5, 2.9, 3.1, 11.0, 30.0)] == [2.0, 2.0, 4.0, 12.0, 30.0]
    assert gs.planting_type_name("RPC Tree - Deciduous", 12.0) == "RPC Tree - Deciduous - Ghost Town 12 m"


def test_the_project_position_puts_the_site_centre_on_the_survey_grid():
    site = {"ground_at_centre_m": 80.0, "true_north_deg": 0.0,
            "survey": {"easting_m": 304.8, "northing_m": 609.6, "elevation_m": 84.7, "grid_angle_deg": 1.5}}
    east, north, elevation, angle = gs.project_position(site)
    assert (east, north) == pytest.approx((1000.0, 2000.0))
    assert elevation == pytest.approx(84.7 * FT)
    assert angle == pytest.approx(-math.radians(1.5))     # grid north east of true north: clockwise
    assert gs.project_position({"ground_at_centre_m": 3.048}) == pytest.approx((0, 0, 10.0, 0))
    assert gs.project_position({}) == (0, 0, 0, 0)


def test_colours_are_clamped_bytes():
    assert gs.rgb([12.4, 300, -2]) == (12, 255, 0)
    assert gs.rgb(None) == (128, 128, 128)


def test_counts_reach_the_answer_only_when_their_step_commits():
    answer = gs.Answer("2025")
    answer.drew("buildings", 3)
    answer.commit()
    answer.drew("trees", 5)
    answer.fail("tree", "tree 4", ValueError("no level"))
    answer.discard()
    out = answer.as_dict()
    assert out == {"ok": True, "format": gs.FORMAT, "revit": "2025", "drawn": {"buildings": 3},
                   "failures": [{"what": "tree", "id": "tree 4", "error": "no level"}], "notes": []}
    fatal = gs.Answer().fatal("No Revit document is open.")
    assert fatal["ok"] is False and fatal["error"] == "No Revit document is open."


def _revit_files():
    for folder, _dirs, files in os.walk(EXTENSION):
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(folder, name)


def test_the_revit_side_avoids_python_3_only_syntax():
    """pyRevit's default engine is IronPython 2.7: no f-strings, annotations, nonlocal, keyword-only
    arguments, `yield from`, async or the walrus."""
    files = list(_revit_files())
    assert len(files) >= 4
    banned = (ast.JoinedStr, ast.AnnAssign, ast.Nonlocal, ast.YieldFrom, ast.AsyncFunctionDef, ast.Await,
              ast.NamedExpr, ast.MatMult)
    for path in files:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), path)
        for node in ast.walk(tree):
            assert not isinstance(node, banned), f"{path}:{getattr(node, 'lineno', '?')} {type(node).__name__}"
            if isinstance(node, (ast.FunctionDef, ast.Lambda)):
                args = node.args
                assert not args.kwonlyargs and not args.posonlyargs, path
                assert not getattr(node, "returns", None), path
                assert all(a.annotation is None for a in args.args), path
            assert not (isinstance(node, ast.Call) and any(isinstance(a, ast.Starred) for a in node.args[:-1])), path



def test_the_formats_match_on_both_sides():
    with open(os.path.join(ROOT, "ghosttown", "revit_bridge.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    values = [n.value.value for n in tree.body if isinstance(n, ast.Assign)
              and any(getattr(t, "id", "") == "FORMAT" for t in n.targets)]
    assert values == [gs.FORMAT]
