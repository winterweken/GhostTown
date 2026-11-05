"""Save Contours (DXF): the picked site's contour lines as a DXF on one layer, for Revit's Toposolid › Create from
Import › Create from CAD, which reads 3D contour lines from a DWG, DXF or DGN import and places the toposolid's
points along them. The OBJ from Export for Revit carries the same lines, but Revit builds a toposolid only from
the layers of a DWG, DXF or DGN import.

The file is an ASCII DXF of release 12, the form every reader opens: one 3D POLYLINE per contour line on the
`CONTEXT_-_CONTOUR` layer, a ring flagged closed with its points written once. The layer can't be named
`Context - Contour` after the lines' material: a release 12 name holds only A-Z, 0-9, $, _ and -, 31 of them at
most, and AutoCAD is reported to refuse release 12 files whose layer names have spaces, commas or dots in
them, or are too long. So the layer is the material's name in those letters. Coordinates are the model's
metres, origin at the site centre, so the DXF imported origin to origin lands on the OBJ."""
import math
import re

import numpy as np

from . import materials, site_use

ACADVER = "AC1009"   # release 12
NAME_MAX = 31        # the most characters a release 12 name holds
_NOT_IN_A_NAME = re.compile(r"[^A-Z0-9$_-]")   # and every character it can't hold
COLOUR = 34          # AutoCAD colour index: a brown, like the Contour material
RING_GAP_M = 0.001   # a chain whose ends meet this closely is a ring: the fetcher repeats a ring's first point last
_OPEN, _CLOSED = 8, 9   # POLYLINE flags: 3D polyline, and a closed one
_VERTEX_3D = 32


def contour_objects(root):
    """The site's contour objects: Contour · <site> as built, none on flat ground."""
    return site_use.made_objects(root, ("contour",))


def polylines(ob):
    """[(points, closed)] rebuilt from the object's loose edges, the points in world metres: open chains are
    walked from their ends first, then rings from what is left. A chain whose ends meet is a ring, its repeated
    point dropped."""
    me = ob.data
    edges = np.empty(len(me.edges) * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", edges)
    edges = edges.reshape(-1, 2)
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    world = np.array(ob.matrix_world, dtype=float)
    co = co.reshape(-1, 3).astype(float) @ world[:3, :3].T + world[:3, 3]
    links = {}                                       # vertex -> [(neighbour, edge)], in index order
    for e, (a, b) in enumerate(edges.tolist()):
        links.setdefault(a, []).append((b, e))
        links.setdefault(b, []).append((a, e))
    for near in links.values():
        near.sort()
    used = [False] * len(edges)

    def walk(start):
        chain, v = [start], start
        while True:
            step = next(((w, e) for w, e in links[v] if not used[e]), None)
            if step is None:
                return chain
            v, e = step
            used[e] = True
            chain.append(v)

    chains = []
    for v in sorted(v for v, near in links.items() if len(near) == 1):
        if not used[links[v][0][1]]:
            chains.append(walk(v))
    for e, (a, _b) in enumerate(edges.tolist()):     # rings, and whatever a junction left over
        while not used[e]:
            chains.append(walk(a))
    out = []
    for chain in chains:
        points = co[chain]
        closed = len(chain) >= 4 and (chain[0] == chain[-1] or math.dist(points[0], points[-1]) < RING_GAP_M)
        out.append(([tuple(p) for p in (points[:-1] if closed else points)], closed))
    return out


def _num(value):
    """Metres to 3 decimals, the fetcher's own precision, without a signed zero."""
    text = f"{value:.3f}"
    return "0.000" if text == "-0.000" else text


def layer_name(name):
    """`name` in release 12's letters: upper case, an underscore for each character outside A-Z, 0-9, $, _ and -,
    and 31 characters at most."""
    return _NOT_IN_A_NAME.sub("_", name.upper())[:NAME_MAX]


def contour_layer():
    """The DXF's layer, which is the name Revit lists to tick: the Contour material's, in release 12's letters."""
    return layer_name(materials.material_name("contour"))


def dxf(lines, layer):
    """The DXF text: a release 12 header, the CONTINUOUS linetype, layers 0 and `layer`, then one POLYLINE with
    its VERTEX entries and SEQEND per line, every entity on `layer`, which is written as given and so has to be
    a release 12 name (layer_name). Group code on one line, right-justified in three characters as AutoCAD
    writes it, value on the next, CR LF between."""
    out = [(0, "SECTION"), (2, "HEADER"), (9, "$ACADVER"), (1, ACADVER), (0, "ENDSEC"),
           (0, "SECTION"), (2, "TABLES"),
           (0, "TABLE"), (2, "LTYPE"), (70, 1),
           (0, "LTYPE"), (2, "CONTINUOUS"), (70, 0), (3, "Solid line"), (72, 65), (73, 0), (40, "0.0"),
           (0, "ENDTAB"),
           (0, "TABLE"), (2, "LAYER"), (70, 2),
           (0, "LAYER"), (2, "0"), (70, 0), (62, 7), (6, "CONTINUOUS"),
           (0, "LAYER"), (2, layer), (70, 0), (62, COLOUR), (6, "CONTINUOUS"),
           (0, "ENDTAB"), (0, "ENDSEC"),
           (0, "SECTION"), (2, "ENTITIES")]
    for points, closed in lines:
        out += [(0, "POLYLINE"), (8, layer), (66, 1), (70, _CLOSED if closed else _OPEN),
                (10, "0.0"), (20, "0.0"), (30, "0.0")]
        for x, y, z in points:
            out += [(0, "VERTEX"), (8, layer), (10, _num(x)), (20, _num(y)), (30, _num(z)), (70, _VERTEX_3D)]
        out += [(0, "SEQEND"), (8, layer)]
    out += [(0, "ENDSEC"), (0, "EOF")]
    return "".join(f"{code:3d}\r\n{value}\r\n" for code, value in out)


def save(root, path):
    """Write the site's contour lines to `path` as a DXF and return how many polylines it holds. ValueError when
    the site has no contour object, or its lines are gone."""
    lines = [line for ob in contour_objects(root) for line in polylines(ob)]
    if not lines:
        raise ValueError("this site has no contour lines")
    with open(path, "w", encoding="ascii", newline="") as f:
        f.write(dxf(lines, contour_layer()))
    return len(lines)
