"""Turn a request into a context document.

The centre decides the region. Inside the City of Toronto, the City's own layers supply buildings,
ground, trees and parcels; elsewhere, OpenStreetMap supplies buildings on plain ground. NRCan supplies
the terrain in Canada. Each source runs on its own: a failure becomes a warning note, and only a run
where every data source failed raises NothingFetched. Real-world outlines occasionally defeat the
geometry library; that too costs only the layer it happens in."""
import shapely

from . import buildings, ground, parcels, region, survey, trees
from . import context as ctx
from . import terrain as terrain_mod
from .frame import Frame
from .net import SourceError
from .sources import osm, toronto

KIND_LAYERS = {"road": "roads", "sidewalk": "sidewalks", "parking": "parking", "rail": "rail",
               "green": "green", "water": "water"}


class NothingFetched(Exception):
    """Every data source that was tried failed."""


def _region(net, frame, radius):
    if not region.near_toronto(frame.lat0, frame.lon0):
        return "world", None
    try:
        boundary = region.fetch_boundary(net)
    except SourceError as e:
        return "world", ("warn", "region", f"{e} The site is treated as outside Toronto.")
    except shapely.errors.GEOSException as e:
        return "world", ("warn", "region", f"The City of Toronto boundary couldn't be read ({str(e)[:80]}). "
                                           "The site is treated as outside Toronto.")
    where, crosses = region.classify(boundary, frame, radius)
    if crosses and where == "toronto":
        return where, ("warn", "boundary", "Part of the circle is outside the City of Toronto; that part has no City data.")
    if crosses:
        return where, ("info", "boundary", "Part of the circle is in the City of Toronto, but City data is used only "
                                           "for sites centred in Toronto.")
    return where, None


def assemble(request, net, *, progress=None):
    progress = progress or (lambda stage, pct: None)
    lat, lon = request["centre"]["lat"], request["centre"]["lon"]
    radius, layers = request["radius_m"], request["layers"]
    frame = Frame(lat, lon)

    progress("City boundary", 5)
    where, note = _region(net, frame, radius)
    doc = ctx.new(request, region=where, terrain_source="flat")
    if note:
        ctx.note(doc, *note)

    progress("Terrain", 15)
    if "terrain" in layers:
        terrain, note = terrain_mod.load(net, frame, radius)
        if note:
            ctx.note(doc, *note)
    else:
        terrain = terrain_mod.FlatTerrain()
    if terrain.source != "flat":
        ctx.add_source(doc, "nrcan")
    doc["terrain"] = {"source": terrain.source, "cell_m": terrain.cell_m}
    doc["ground_at_centre_m"] = terrain.ground_at_centre_m
    doc["survey"] = survey.survey_point(where, lat, lon, terrain.ground_at_centre_m)

    tried = failed = 0

    def attempt(stage, pct, code, source, fetch):
        nonlocal tried, failed
        progress(stage, pct)
        tried += 1
        try:
            result = fetch()
        except SourceError as e:
            failed += 1
            ctx.note(doc, "warn", code, str(e))
            return None
        except shapely.errors.GEOSException as e:  # sources turn answers into geometry as they read them
            failed += 1
            ctx.note(doc, "warn", code, f"{stage} couldn't be read ({str(e)[:80]}).")
            return None
        ctx.add_source(doc, source)
        return result

    def built(code, what, make):
        try:
            return make()
        except shapely.errors.GEOSException as e:
            ctx.note(doc, "warn", code, f"{what} couldn't be built from the source geometry ({str(e)[:80]}).")
            return []

    pieces = {}
    if where == "toronto":
        if "buildings" in layers:
            found = attempt("City buildings", 25, "city_buildings", "toronto",
                            lambda: toronto.fetch_buildings(net, lat, lon, radius))
            if found is not None:
                doc["elements"].extend(built("city_buildings", "City buildings",
                                             lambda: buildings.from_toronto(found, frame, terrain, radius)))
        kinds = [kind for kind, layer in KIND_LAYERS.items() if layer in layers]
        if kinds:
            skipped = []
            found = attempt("City ground", 40, "city_ground", "toronto",
                            lambda: toronto.fetch_ground(net, lat, lon, radius, frame, kinds=kinds, skipped=skipped))
            pieces = found or {}
            if skipped:
                shapes = ("1 City ground shape couldn't be read and was" if len(skipped) == 1
                          else f"{len(skipped)} City ground shapes couldn't be read and were")
                ctx.note(doc, "warn", "city_ground", f"{shapes} left out; plain ground fills the gap.")
        if "trees" in layers:
            found = attempt("City trees", 55, "city_trees", "toronto", lambda: toronto.fetch_trees(net, lat, lon, radius))
            if found is not None:
                doc["elements"].extend(built("city_trees", "City trees", lambda: trees.from_toronto(found, frame, terrain)))
        if "parcels" in layers:
            found = attempt("City parcels", 65, "city_parcels", "toronto",
                            lambda: toronto.fetch_parcels(net, lat, lon, radius))
            if found is not None:
                doc["elements"].extend(built("city_parcels", "City parcels",
                                             lambda: parcels.from_toronto(found, frame, terrain, radius)))
    elif "buildings" in layers:
        endpoint = request.get("overpass_url") or osm.ENDPOINT
        found = attempt("OpenStreetMap", 25, "osm", "osm", lambda: osm.fetch(net, lat, lon, radius, layers, endpoint=endpoint))
        if found is not None:
            doc["elements"].extend(built("osm", "OpenStreetMap buildings", lambda: buildings.from_osm(found, frame, terrain)))

    if tried and failed == tried:
        raise NothingFetched(" ".join(n["text"] for n in doc["notes"] if n["level"] == "warn"))

    progress("Ground", 80)
    plain = "terrain" in layers
    try:
        surface = ground.elements(ground.layout(pieces, radius, include_ground=plain), terrain)
    except shapely.errors.GEOSException as e:
        ctx.note(doc, "warn", "ground", f"The ground pieces couldn't be laid out ({str(e)[:80]}), so the ground is plain.")
        surface = ground.elements(ground.layout({}, radius, include_ground=plain), terrain)
    doc["elements"].extend(surface)
    progress("Writing", 95)
    return ctx.finish(doc)
