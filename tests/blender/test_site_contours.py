import os
import re
import tempfile
from types import SimpleNamespace

import bpy

import ghosttown
from ghosttown import ops, scene_build, site_contours
from ghosttown.ghosttown_fetch import context as ctx
from helpers import load_fixture

LAYER = "CONTEXT_-_CONTOUR"   # the material's name, Context - Contour, in release 12's letters
R12_NAME = re.compile(r"[A-Z0-9$_-]{1,31}")   # all a release 12 name may hold
HEADER = "  0\r\nSECTION\r\n  2\r\nHEADER\r\n  9\r\n$ACADVER\r\n  1\r\nAC1009\r\n  0\r\nENDSEC\r\n"
# contour:85 is an open line 0.3 m over the site centre (ground_at_centre_m 84.7); contour:85.5 a ring 0.8 m over
# it, its first point repeated last, as the fetcher writes rings.
OPEN = [[-10.0, -10.0, 0.3], [0.0, -5.0, 0.3], [10.0, -10.0, 0.3]]
RING = [[20.0, 20.0, 0.8], [30.0, 20.0, 0.8], [30.0, 30.0, 0.8], [20.0, 30.0, 0.8], [20.0, 20.0, 0.8]]


def contour_site(contours=True):
    doc = load_fixture("mini_context.json")
    if contours:
        for height, pts in (("85", OPEN), ("85.5", RING)):
            doc["elements"].append(ctx.element(f"contour:{height}", "contour", lines=[{"kind": "contour", "pts": pts}]))
    return scene_build.build(bpy.context.scene, doc)


def saved(root):
    path = os.path.join(tempfile.mkdtemp(), "contours.dxf")
    count = site_contours.save(root, path)
    with open(path, "rb") as f:
        return count, f.read().decode("ascii")


def saved_by_the_operator():
    """The DXF the operator's execute wrote, and its one report as (level, text)."""
    ghosttown.register()
    try:
        bpy.context.scene.ghosttown.site = contour_site()
        path, reports = os.path.join(tempfile.mkdtemp(), "contours.dxf"), []
        op = SimpleNamespace(filepath=path, report=lambda level, said: reports.append((level, said)))
        assert ops.GHOSTTOWN_OT_save_contours.execute(op, bpy.context) == {"FINISHED"}
        report, = reports
        with open(path, "rb") as f:
            return f.read().decode("ascii"), report
    finally:
        ghosttown.unregister()


def pairs(text):
    """The DXF as (group code, value) pairs, the values as written."""
    lines = text.split("\r\n")
    assert lines.pop() == "" and len(lines) % 2 == 0
    return [(int(lines[i]), lines[i + 1]) for i in range(0, len(lines), 2)]


def layers(text):
    """The names in the LAYER table."""
    section = pairs(text)
    return [section[i + 1][1] for i, pair in enumerate(section) if pair == (0, "LAYER")]


def entities(text):
    """The ENTITIES section as [[(code, value), ...] per entity], each starting with its (0, kind) pair."""
    section = pairs(text)
    start = section.index((2, "ENTITIES")) + 1
    out = []
    for code, value in section[start:section.index((0, "ENDSEC"), start)]:
        if code == 0:
            out.append([])
        out[-1].append((code, value))
    return out


def polylines(text):
    """[(flag 70, [(x, y, z) as written])], one per POLYLINE."""
    out = []
    for entity in entities(text):
        fields = dict(entity[1:])
        if entity[0] == (0, "POLYLINE"):
            out.append((int(fields[70]), []))
        elif entity[0] == (0, "VERTEX"):
            out[-1][1].append((fields[10], fields[20], fields[30]))
    return out


def test_the_dxf_is_release_12_with_one_polyline_per_line_on_the_contour_layer():
    count, text = saved(contour_site())
    assert count == 2
    assert text.startswith(HEADER) and text.endswith("  0\r\nEOF\r\n")
    assert all(len(line) == 3 for line in text.split("\r\n")[0::2] if line)   # group codes padded to three
    assert layers(text) == ["0", LAYER]
    assert text.count("0\r\nPOLYLINE\r\n") == 2 and text.count("0\r\nSEQEND\r\n") == 2
    (open_flag, open_pts), (ring_flag, ring_pts) = sorted(polylines(text), key=lambda line: line[1][0][2])
    assert open_flag == 8 and open_pts == [("-10.000", "-10.000", "0.300"), ("0.000", "-5.000", "0.300"),
                                            ("10.000", "-10.000", "0.300")]
    assert ring_flag == 9 and ring_pts == [("20.000", "20.000", "0.800"), ("30.000", "20.000", "0.800"),
                                            ("30.000", "30.000", "0.800"), ("20.000", "30.000", "0.800")]


def test_every_entity_is_a_3d_polyline_part_on_the_layer():
    _, text = saved(contour_site())
    kinds = [entity[0][1] for entity in entities(text)]
    assert kinds == ["POLYLINE"] + ["VERTEX"] * 3 + ["SEQEND", "POLYLINE"] + ["VERTEX"] * 4 + ["SEQEND"]
    for entity in entities(text):
        kind, fields = entity[0][1], entity[1:]
        if kind == "POLYLINE":
            assert fields[:2] == [(8, LAYER), (66, "1")] and fields[2][0] == 70 and fields[2][1] in ("8", "9")
            assert fields[3:] == [(10, "0.0"), (20, "0.0"), (30, "0.0")]
        elif kind == "VERTEX":
            assert [code for code, _ in fields] == [8, 10, 20, 30, 70]
            assert fields[0] == (8, LAYER) and fields[-1] == (70, "32")
        else:
            assert kind == "SEQEND" and fields == [(8, LAYER)]
    tables = pairs(text)[pairs(text).index((2, "TABLES")):pairs(text).index((2, "ENTITIES"))]
    assert tables[1:11] == [(0, "TABLE"), (2, "LTYPE"), (70, "1"), (0, "LTYPE"), (2, "CONTINUOUS"), (70, "0"),
                            (3, "Solid line"), (72, "65"), (73, "0"), (40, "0.0")]
    assert tables[11:] == [(0, "ENDTAB"), (0, "TABLE"), (2, "LAYER"), (70, "2"),
                           (0, "LAYER"), (2, "0"), (70, "0"), (62, "7"), (6, "CONTINUOUS"),
                           (0, "LAYER"), (2, LAYER), (70, "0"), (62, "34"), (6, "CONTINUOUS"),
                           (0, "ENDTAB"), (0, "ENDSEC"), (0, "SECTION")]


def test_a_layer_name_is_the_name_in_release_12s_letters():
    """Upper case, an underscore for each character outside A-Z, 0-9, $, _ and -, and 31 characters at most."""
    for name, want in (("Context - Contour", "CONTEXT_-_CONTOUR"),
                       ("CONTEXT_-_CONTOUR", "CONTEXT_-_CONTOUR"),   # in release 12's letters already
                       ("TOPO-2$_A", "TOPO-2$_A"),
                       ("contour", "CONTOUR"),                       # lower case
                       ("on  site", "ON__SITE"),                     # each space
                       ("Contour 0.5 m", "CONTOUR_0_5_M"),           # dots
                       ("topo/lines\\minor", "TOPO_LINES_MINOR"),    # slashes
                       ("Contours · Église", "CONTOURS____GLISE"),   # a sign and a letter outside ASCII
                       ("Höhe in m²", "H_HE_IN_M_"),                 # ² is a digit, but not one of 0-9
                       ("Straße", "STRASSE"),                        # upper case comes first: ß is SS
                       ("Context - Building (height guessed)", "CONTEXT_-_BUILDING__HEIGHT_GUES"),   # 35 cut to 31
                       ("ß" * 20, "S" * 31)):                        # cut after the upper case, which can lengthen
        assert site_contours.layer_name(name) == want, name


def test_a_layer_name_is_a_release_12_name_whatever_it_is_made_from():
    for code in range(0x3000):   # controls and line ends, ASCII, accented and non-Latin letters, signs
        name = site_contours.layer_name(f"a{chr(code)}b")
        assert R12_NAME.fullmatch(name), (code, name)


def test_every_name_in_the_dxf_is_a_release_12_name():
    """A release 12 name is of A-Z, 0-9, $, _ and -, 31 characters at most. AutoCAD is reported to refuse
    release 12 files whose layer names have spaces, commas or dots in them, or are too long."""
    _, text = saved(contour_site())
    section = pairs(text)
    start = section.index((2, "TABLES")) + 1
    tables = section[start:section.index((0, "ENDSEC"), start)]
    names = [value for code, value in tables if code == 2]        # each table, then each of its entries
    linetypes = [value for code, value in section if code == 6]   # the linetype a layer points at
    on = [value for code, value in section if code == 8]          # the layer an entity is on
    assert (len(names), len(linetypes), len(on)) == (5, 2, 11)
    for name in names + linetypes + on:
        assert R12_NAME.fullmatch(name), name
    assert all([code for code, _ in entity].count(8) == 1 for entity in entities(text))
    layer, = set(on)                                              # every entity on the one layer
    assert layer == LAYER and layer in layers(text)


def test_save_refuses_a_site_without_contours():
    try:
        site_contours.save(contour_site(contours=False), os.path.join(tempfile.mkdtemp(), "contours.dxf"))
    except ValueError as e:
        assert "no contour lines" in str(e)
    else:
        raise AssertionError("save should refuse a site without contours")


def test_the_operator_polls_only_with_contours_and_writes_the_file():
    ghosttown.register()
    try:
        bpy.context.scene.ghosttown.site = contour_site(contours=False)
        assert not bpy.ops.ghosttown.save_contours.poll()
        bpy.context.scene.ghosttown.site = contour_site()
        assert bpy.ops.ghosttown.save_contours.poll()
        path = os.path.join(tempfile.mkdtemp(), "site contours")   # the extension is added
        assert bpy.ops.ghosttown.save_contours(filepath=path) == {"FINISHED"}
        with open(path + ".dxf", "rb") as f:
            text = f.read().decode("ascii")   # bytes: text mode would fold the CR LF line ends
        assert text.startswith(HEADER) and len(polylines(text)) == 2
    finally:
        ghosttown.unregister()


def test_the_operator_reports_the_layer_the_file_has():
    """The report tells the user which layer to tick in Revit: the one the file's lines are on."""
    text, (level, said) = saved_by_the_operator()
    layer, = {dict(entity)[8] for entity in entities(text)}
    assert level == {"INFO"} and layer in said, (layer, said)
    assert layer == LAYER


def test_the_operator_reports_how_revit_has_to_import_the_file():
    """Of what Autodesk's help asks for a toposolid from an import, two things fall to the user: the import
    isn't made with Current View Only, and the toposolid is made in a 3D view. The file can't say its units,
    so the report does."""
    _, (_, said) = saved_by_the_operator()
    needed = ("Current View Only unticked", "units in meters", "origin to origin", "in a 3D view")
    missing = [words for words in needed if words not in said]
    assert not missing, (missing, said)


def test_a_moved_site_shifts_the_heights():
    root = contour_site()
    lines, = site_contours.contour_objects(root)
    lines.location.z = 2.0
    bpy.context.view_layer.update()
    _, text = saved(root)
    assert sorted({z for _flag, pts in polylines(text) for _x, _y, z in pts}) == ["2.300", "2.800"]


def test_a_ring_merged_at_its_ends_is_closed_and_a_chain_is_open():
    """Merge by Distance joins a ring's repeated point to its first: the ring is still one closed polyline."""
    me = bpy.data.meshes.new("lines")
    verts = [(5, -5, 2), (5, 0, 2), (5, 15, 2), (0, 0, 1), (10, 0, 1), (10, 10, 1), (0, 10, 1)]
    me.from_pydata(verts, [(5, 6), (6, 3), (3, 4), (4, 5), (0, 1), (2, 1)], [])
    ob = bpy.data.objects.new("lines", me)
    bpy.context.scene.collection.objects.link(ob)
    found = site_contours.polylines(ob)
    assert [(len(points), closed) for points, closed in found] == [(3, False), (4, True)]
    assert found[0][0] == [(5.0, -5.0, 2.0), (5.0, 0.0, 2.0), (5.0, 15.0, 2.0)]
    assert sorted(found[1][0]) == [(0.0, 0.0, 1.0), (0.0, 10.0, 1.0), (10.0, 0.0, 1.0), (10.0, 10.0, 1.0)]
