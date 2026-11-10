# -*- coding: utf-8 -*-
"""Draw a Ghost Town site in the open Revit document as native elements. Called by startup.py's route on
Revit's main thread (pyRevit runs a handler that takes `doc` through an ExternalEvent).

One transaction group holds one transaction per step: georeference, toposolid, ground subdivisions,
buildings, trees, contour lines, lot lines. A step that fails rolls back alone and the others stay; a
single element that fails is left out and named in the answer. Warnings are deleted before they reach a
dialog (nobody is at the keyboard to close one); an error rolls its step back and is reported.

Untested on this side so far: it was written on a Mac without Revit. ghosttown_revit.site holds the parts
tested without Revit. Revit 2024 or later (Toposolid).
"""
from __future__ import division

import math

import clr  # noqa: F401  (loads the .NET bridge pyRevit already has)
from Autodesk.Revit.DB import (BuiltInCategory, BuiltInParameter, Color, CurveArray, CurveLoop, DirectShape,
                               ElementId, ElementTypeGroup, FailureProcessingResult, FailureSeverity, FamilySymbol,
                               FilteredElementCollector, GraphicsStyleType, IFailuresPreprocessor, Level, Line,
                               Material, Plane, ProjectPosition, SketchPlane, TessellatedFace,
                               TessellatedShapeBuilder, TessellatedShapeBuilderFallback,
                               TessellatedShapeBuilderOutcome, TessellatedShapeBuilderTarget, Transaction,
                               TransactionGroup, TransactionStatus, XYZ)
from Autodesk.Revit.DB.Structure import StructuralType
from System.Collections.Generic import List

from ghosttown_revit import site as gs

try:
    from Autodesk.Revit.DB import Toposolid, ToposolidType
except ImportError:                       # Revit 2023 and earlier: no toposolids
    Toposolid = ToposolidType = None

APP_ID = "Ghost Town"
# Planting families looked for first, by family name; any loaded planting family does otherwise.
PLANTING_FAMILIES = ("RPC Tree - Deciduous", "RPC Tree - Conifer", "RPC Tree - Tropical")
# Type parameters tried, in order, for a planting type's height.
HEIGHT_PARAMETERS = ("Plant Height", "Height")


class _Quiet(IFailuresPreprocessor):
    """Deletes warnings; on an error, rolls the transaction back without a dialog and keeps its text."""

    def __init__(self):
        self.errors = []

    def PreprocessFailures(self, accessor):
        rollback = False
        for failure in accessor.GetFailureMessages():
            if failure.GetSeverity() == FailureSeverity.Warning:
                accessor.DeleteWarning(failure)
            else:
                self.errors.append(failure.GetDescriptionText())
                rollback = True
        return FailureProcessingResult.ProceedWithRollBack if rollback else FailureProcessingResult.Continue


def _xyz(p):
    return XYZ(p[0], p[1], p[2])


def _lines(segments):
    return [Line.CreateBound(_xyz(a), _xyz(b)) for a, b in segments]


def _curve_loop(segments):
    loop = CurveLoop()
    for line in _lines(segments):
        loop.Append(line)
    return loop


def _loops(xy_loops, z=0.0):
    out = List[CurveLoop]()
    for xy in xy_loops:
        segments = gs.loop_segments(xy, z)
        if segments:
            out.Add(_curve_loop(segments))
    return out


def _level(doc):
    """The level nearest elevation 0, where the toposolid and the trees are hosted."""
    levels = list(FilteredElementCollector(doc).OfClass(Level))
    return min(levels, key=lambda lv: abs(lv.Elevation)) if levels else None


def _by_name(doc, cls, name):
    for element in FilteredElementCollector(doc).OfClass(cls):
        if element.Name == name:
            return element
    return None


def _step(doc, name, answer, work, data):
    """Run one step in its own transaction; its counts reach the answer only once it commits."""
    t = Transaction(doc, "Ghost Town " + name)
    quiet = _Quiet()
    options = t.GetFailureHandlingOptions()
    options.SetFailuresPreprocessor(quiet)
    options.SetClearAfterRollback(True)
    t.SetFailureHandlingOptions(options)
    t.Start()
    try:
        work(doc, data, answer)
        if t.Commit() == TransactionStatus.Committed:
            answer.commit()
            return
        answer.discard()
        answer.fail(name, "", "Revit rolled the step back: " + ("; ".join(quiet.errors) or "no reason given"))
    except Exception as e:  # noqa: BLE001 - every failure goes back to Blender, none stays in Revit
        if t.GetStatus() == TransactionStatus.Started:
            t.RollBack()
        answer.discard()
        answer.fail(name, "", e)


def georeference(doc, data, answer):
    site = data["site"]
    location = doc.SiteLocation
    location.Latitude = math.radians(float(site["lat"]))
    location.Longitude = math.radians(float(site["lon"]))
    if site.get("address"):
        try:
            location.PlaceName = site["address"]
        except Exception:  # noqa: BLE001 - a read-only place name in some templates
            pass
    east, north, elevation, angle = gs.project_position(site)
    doc.ActiveProjectLocation.SetProjectPosition(XYZ.Zero, ProjectPosition(east, north, elevation, angle))
    answer.drew("georeference")
    survey = site.get("survey") or {}
    if survey.get("epsg"):
        try:
            location.SetGeoCoordinateSystem(survey["epsg"])
            answer.drew("coordinate_system")
        except Exception as e:  # noqa: BLE001
            answer.fail("coordinate system", survey["epsg"], e)


def _topo_type(doc, name=None):
    if name:
        found = _by_name(doc, ToposolidType, name)
        return found.Id if found is not None else None
    type_id = doc.GetDefaultElementTypeId(ElementTypeGroup.ToposolidType)
    if type_id is None or type_id == ElementId.InvalidElementId:
        first = FilteredElementCollector(doc).OfClass(ToposolidType).FirstElement()
        type_id = first.Id if first is not None else None
    return type_id


_made = {}   # the toposolid made by this request, for the ground step


def toposolid(doc, data, answer):
    _made.pop("toposolid", None)
    if Toposolid is None:
        answer.fail("toposolid", "", "Toposolids need Revit 2024 or later.")
        return
    if not data.get("contours"):
        answer.note("The site has no contour lines (flat ground), so no toposolid and no ground subdivisions.")
        return
    site = data["site"]
    level = _level(doc)
    type_id = _topo_type(doc)
    if level is None or type_id is None:
        answer.fail("toposolid", "", "The document needs a level and a toposolid type.")
        return
    points = List[XYZ]([_xyz(p) for p in gs.topo_points(data["contours"], site.get("edge_points", []),
                                                         site["boundary"])])
    topo = Toposolid.Create(doc, _loops([site["boundary"]]), points, type_id, level.Id)
    topo.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS).Set("Ghost Town site")
    _made["toposolid"] = topo.Id
    answer.drew("toposolid")
    answer.drew("toposolid_points", points.Count)


def ground(doc, data, answer):
    topo_id = _made.get("toposolid")
    pieces = [p for p in data.get("ground", []) if p.get("kind") not in gs.NOT_SUBDIVIDED]
    if not pieces:
        return
    topo = doc.GetElement(topo_id) if topo_id is not None else None
    if topo is None:
        answer.note("%d ground pieces weren't drawn: they subdivide the toposolid, and there is none."
                    % len(pieces))
        return
    for piece in pieces:
        ident = "%s %s" % (piece.get("kind"), piece.get("id", ""))
        try:
            loops = _loops(piece["loops"])
            if loops.Count == 0:
                answer.fail("ground", ident, "no loop long enough to draw")
                continue
            sub = topo.CreateSubDivision(doc, loops)
            type_id = _topo_type(doc, piece.get("material"))
            if type_id is not None:
                sub.ChangeTypeId(type_id)
            answer.drew("ground_subdivisions")
        except Exception as e:  # noqa: BLE001
            answer.fail("ground", ident, e)


def _materials(doc, data, answer):
    """Material ids by name: each Ghost Town material, made with its colour when the document lacks it."""
    ids = {}
    for name, colour in sorted((data.get("materials") or {}).items()):
        material = _by_name(doc, Material, name)
        if material is None:
            try:
                material = doc.GetElement(Material.Create(doc, name))
                r, g, b = gs.rgb(colour)
                material.Color = Color(r, g, b)
                answer.drew("materials_created")
            except Exception as e:  # noqa: BLE001
                answer.fail("material", name, e)
                continue
        ids[name] = material.Id
    return ids


def buildings(doc, data, answer):
    ids = _materials(doc, data, answer)
    category = ElementId(BuiltInCategory.OST_GenericModel)
    for building in data.get("buildings", []):
        ident = building.get("id") or building.get("name") or "?"
        try:
            faces = gs.building_faces(building)
            if not faces:
                answer.fail("building", ident, "no triangles with any area")
                continue
            builder = TessellatedShapeBuilder()
            builder.OpenConnectedFaceSet(True)
            for corners, material in faces:
                builder.AddFace(TessellatedFace(List[XYZ]([_xyz(p) for p in corners]),
                                                ids.get(material, ElementId.InvalidElementId)))
            builder.CloseConnectedFaceSet()
            builder.Target = TessellatedShapeBuilderTarget.AnyGeometry
            builder.Fallback = TessellatedShapeBuilderFallback.Mesh
            builder.Build()
            result = builder.GetBuildResult()
            if result.Outcome == TessellatedShapeBuilderOutcome.Nothing:
                answer.fail("building", ident, "Revit made no shape from its triangles")
                continue
            shape = DirectShape.CreateElement(doc, category)
            shape.ApplicationId = APP_ID
            shape.ApplicationDataId = ident
            shape.SetShape(result.GetGeometricalObjects())
            label = building.get("name") or ident
            try:
                shape.SetName(label)
            except Exception:  # noqa: BLE001 - SetName arrived in Revit 2022; the comment carries it anyway
                pass
            shape.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS).Set(
                "Ghost Town %s %s" % (building.get("kind", ""), ident))
            answer.drew("buildings")
            if result.Outcome == TessellatedShapeBuilderOutcome.Mesh:
                answer.drew("buildings_as_mesh")      # a mesh, not a solid: one material, no cutting
        except Exception as e:  # noqa: BLE001
            answer.fail("building", ident, e)


def _planting_base(doc):
    symbols = list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Planting).OfClass(FamilySymbol))
    for family in PLANTING_FAMILIES:
        for symbol in symbols:
            if symbol.Family.Name == family:
                return symbol
    return symbols[0] if symbols else None


def _height_parameter(symbol):
    for name in HEIGHT_PARAMETERS:
        p = symbol.LookupParameter(name)
        if p is not None and not p.IsReadOnly:
            return p
    return None


def _planting_type(doc, base, cls, made, answer):
    """The planting type for one height class: found by name in the base's family, else duplicated from the
    base with its height set."""
    if cls in made:
        return made[cls]
    name = gs.planting_type_name(base.Name, cls)
    symbol = None
    for sid in base.Family.GetFamilySymbolIds():
        candidate = doc.GetElement(sid)
        if candidate.Name == name:
            symbol = candidate
    if symbol is None:
        symbol = base.Duplicate(name)
        height = _height_parameter(symbol)
        if height is not None:
            height.Set(gs.feet(cls))
        else:
            answer.note("%s has no Plant Height type parameter; every tree has its height." % base.Family.Name)
        answer.drew("planting_types_created")
    if not symbol.IsActive:
        symbol.Activate()
        doc.Regenerate()
    made[cls] = symbol
    return symbol


def trees(doc, data, answer):
    found = data.get("trees", [])
    if not found:
        return
    base = _planting_base(doc)
    level = _level(doc)
    if base is None or level is None:
        answer.fail("trees", "", "No planting family is loaded (and a level is needed): load "
                                 "Planting\\RPC Tree - Deciduous.rfa from Revit's library and send again.")
        return
    made = {}
    for i, tree in enumerate(found):
        ident = tree.get("id") or "tree %d" % (i + 1)
        try:
            symbol = _planting_type(doc, base, gs.height_class(tree["height_m"]), made, answer)
            doc.Create.NewFamilyInstance(_xyz(gs.xyz_ft((tree["x"], tree["y"], tree["z"]))), symbol, level,
                                         StructuralType.NonStructural)
            answer.drew("trees")
        except Exception as e:  # noqa: BLE001
            answer.fail("tree", ident, e)


def _line_style(doc, name, colour):
    """The Lines subcategory `name` (made with its colour when missing) as a graphics style, or None."""
    try:
        lines = doc.Settings.Categories.get_Item(BuiltInCategory.OST_Lines)
        sub = lines.SubCategories.get_Item(name) if lines.SubCategories.Contains(name) else None
        if sub is None:
            sub = doc.Settings.Categories.NewSubcategory(lines, name)
            if colour:
                r, g, b = gs.rgb(colour)
                sub.LineColor = Color(r, g, b)
        return sub.GetGraphicsStyle(GraphicsStyleType.Projection)
    except Exception:  # noqa: BLE001 - the lines draw in the default style then
        return None


def _model_lines(doc, segments, plane_z_ft, style, planes):
    key = round(plane_z_ft, 4)
    if key not in planes:
        planes[key] = SketchPlane.Create(doc, Plane.CreateByNormalAndOrigin(XYZ.BasisZ, XYZ(0, 0, plane_z_ft)))
    curves = CurveArray()
    for line in _lines(segments):
        curves.Append(line)
    made = doc.Create.NewModelCurveArray(curves, planes[key])
    if style is not None:
        for curve in made:
            curve.LineStyle = style
    return made.Size


def contours(doc, data, answer):
    colours = data.get("materials") or {}
    planes = {}
    for line in data.get("contours", []):
        points = line.get("points", [])
        if not points:
            continue
        z = float(points[0][2])                    # a contour lies at one height
        ident = "%.2f m" % z
        try:
            segments = gs.polyline_segments(points, line.get("closed", False), z=z)
            if not segments:
                answer.fail("contour", ident, "too short to draw")
                continue
            name = line.get("material") or "Context - Contour"
            _model_lines(doc, segments, gs.feet(z), _line_style(doc, name, colours.get(name)), planes)
            answer.drew("contour_lines")
        except Exception as e:  # noqa: BLE001
            answer.fail("contour", ident, e)


def lot_lines(doc, data, answer):
    """Lot lines as model lines flat at z 0. From Revit 2027, PropertyLine.Create could draw them as
    property lines instead."""
    colours = data.get("materials") or {}
    planes = {}
    for i, line in enumerate(data.get("lot_lines", [])):
        ident = line.get("id") or "lot line %d" % (i + 1)
        try:
            segments = gs.polyline_segments(line.get("points", []), line.get("closed", False), z=0.0)
            if not segments:
                answer.fail("lot line", ident, "too short to draw")
                continue
            name = line.get("material") or "Context - Parcel"
            _model_lines(doc, segments, 0.0, _line_style(doc, name, colours.get(name)), planes)
            answer.drew("lot_lines")
        except Exception as e:  # noqa: BLE001
            answer.fail("lot line", ident, e)


STEPS = (("georeference", georeference), ("toposolid", toposolid), ("ground", ground),
         ("buildings", buildings), ("trees", trees), ("contours", contours), ("lot lines", lot_lines))


def handle(doc, data):
    """Draw the payload; the answer as a dict, never an exception."""
    answer = gs.Answer()
    try:
        if doc is None:
            return answer.fatal("No Revit document is open. Open or start a project, then send again.")
        answer.revit = doc.Application.VersionNumber
        if doc.IsFamilyDocument:
            return answer.fatal("The open document is a family. Open a project, then send again.")
        problems = gs.check(data)
        if problems:
            return answer.fatal(problems[0])
        group = TransactionGroup(doc, "Ghost Town site")
        group.Start()
        try:
            for name, work in STEPS:
                _step(doc, name, answer, work, data)
            group.Assimilate()
        except Exception:
            if group.HasStarted() and not group.HasEnded():
                group.RollBack()
            raise
        return answer.as_dict()
    except Exception as e:  # noqa: BLE001
        return answer.fatal(e)
