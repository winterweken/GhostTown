"""Turn a request into a context document.

The centre decides the region. Inside the City of Toronto, the City's own layers supply buildings,
ground, trees and parcels; elsewhere, OpenStreetMap supplies buildings on plain ground. NRCan supplies
the terrain in Canada. Each source runs on its own: a failure becomes a warning note, and only a run
where every data source failed raises NothingFetched. Real-world outlines occasionally defeat the
geometry library; that too costs only the layer it happens in. In Ontario, with LiDAR roofs asked for,
Geospatial Ontario's LiDAR gives every building a second, measured roof, written beside the context."""
import os

import numpy as np
import shapely

from . import BUILDING_KINDS, buildings, ground, lidar_roofs, parcels, region, survey, trees
from . import context as ctx
from . import terrain as terrain_mod
from .frame import Frame
from .net import SourceError
from .sources import ontario_lidar, osm, toronto, toronto_massing, toronto_photo

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


def _city_buildings(net, request, frame, radius, progress, doc):
    """("massing", parts, year) from the City's newest 3D Massing edition (or, when that can't be had, the
    newest one saved on this computer, with a note saying so), else ("outlines", features, None) from the
    older topographic outlines, with one warning saying so."""
    try:
        parts, year = toronto_massing.fetch(net, request["cache_dir"], frame, radius + toronto.WHOLE_MARGIN_M, progress,
                                            note=lambda text: ctx.note(doc, "info", "city_massing", text))
    except SourceError as e:
        ctx.note(doc, "warn", "city_massing", f"{e} Using the City's older building outlines instead.")
        return "outlines", toronto.fetch_buildings(net, frame.lat0, frame.lon0, radius), None
    ctx.note(doc, "info", "city_massing", f"Buildings: City of Toronto 3D Massing {year}.")
    return "massing", parts, year


LIDAR_STAGE = "LiDAR (the first request can take a minute)"
FLAT_ROOFS = "The buildings keep flat roofs."
CITY_MODEL_ONLY = "The buildings come from the City's 3D Massing model, so no LiDAR was fetched."


def _lidar(doc, net, frame, radius, out_dir, progress):
    """LiDAR roofs for the site's buildings outside the City's 3D Massing model, written beside the context
    as lidar_roofs.npz, with a `lidar` block saying so; otherwise a note says why there are none."""
    if not any(el["kind"] in BUILDING_KINDS for el in doc["elements"]):
        return
    outlines = [s["rings"][0] for el in doc["elements"] if lidar_roofs.wanted(el) for s in el["solids"]]
    if not outlines:
        ctx.note(doc, "info", "lidar", CITY_MODEL_ONLY)
        return
    if not ontario_lidar.covers(frame.lat0, frame.lon0):
        ctx.note(doc, "info", "lidar", f"LiDAR roofs are available in Ontario only. {FLAT_ROOFS}")
        return
    progress(LIDAR_STAGE, 77)
    cell = ontario_lidar.cell_for(radius)
    reach = radius + toronto.WHOLE_MARGIN_M
    xy = np.array([p for ring in outlines for p in ring], dtype=float)
    bounds = [max(xy[:, 0].min() - 2 * cell, -reach), max(xy[:, 1].min() - 2 * cell, -reach),
              min(xy[:, 0].max() + 2 * cell, reach), min(xy[:, 1].max() + 2 * cell, reach)]
    try:
        heights = ontario_lidar.fetch(net, frame, bounds, cell)
        if lidar_roofs.coverage(heights, doc["elements"]) < lidar_roofs.MIN_COVERAGE:
            raise ontario_lidar.NoLidar(ontario_lidar.NONE_HERE)
    except ontario_lidar.NoLidar as e:
        ctx.note(doc, "info", "lidar", f"{e} {FLAT_ROOFS}")
        return
    except SourceError as e:
        ctx.note(doc, "warn", "lidar", f"{e} {FLAT_ROOFS}")
        return
    except shapely.errors.GEOSException as e:
        ctx.note(doc, "warn", "lidar", f"The LiDAR roofs couldn't be built ({str(e)[:80]}). {FLAT_ROOFS}")
        return
    progress("LiDAR roofs", 78)
    try:
        arrays, counts = lidar_roofs.build(doc["elements"], heights, cell)
        if arrays is None:
            return
        lidar_roofs.write(os.path.join(out_dir, lidar_roofs.FILE), arrays)
    except shapely.errors.GEOSException as e:
        ctx.note(doc, "warn", "lidar", f"The LiDAR roofs couldn't be built ({str(e)[:80]}). {FLAT_ROOFS}")
        return
    except OSError as e:
        ctx.note(doc, "warn", "lidar", f"The LiDAR roofs couldn't be saved ({e}). {FLAT_ROOFS}")
        return
    doc["lidar"] = {"file": lidar_roofs.FILE, "cell_m": cell, "year": None, "source": "ontario",
                    "buildings": counts["buildings"], "triangles": counts["triangles"], "kinds": list(BUILDING_KINDS)}
    ctx.add_source(doc, "ontario")
    ctx.note(doc, "info", "lidar", f"LiDAR roofs: Geospatial Ontario, {counts['buildings']} buildings, "
                                   f"{counts['triangles']:,} triangles.")


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
                            lambda: _city_buildings(net, request, frame, radius, progress, doc))
            if found is not None:
                how, data, year = found
                if how == "massing":
                    make = lambda: buildings.from_massing(data, terrain, radius, year)  # noqa: E731
                else:
                    make = lambda: buildings.from_toronto(data, frame, terrain, radius)  # noqa: E731
                doc["elements"].extend(built("city_buildings", "City buildings", make))
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

    if where == "toronto" and "photo" in layers:
        progress("Site photo", 75)
        try:
            doc["photo"] = toronto_photo.fetch(net, frame, radius, request["out_dir"])
        except SourceError as e:
            ctx.note(doc, "warn", "city_photo", f"{e} The site has no aerial photo.")
        except OSError as e:
            ctx.note(doc, "warn", "city_photo", f"The aerial photo couldn't be saved ({e}). The site has no aerial photo.")
        else:
            ctx.add_source(doc, "toronto")
            year = doc["photo"]["year"]
            ctx.note(doc, "info", "city_photo", f"Aerial photo: City of Toronto, {year or 'current year'}.")

    if "lidar" in layers:
        _lidar(doc, net, frame, radius, request["out_dir"], progress)

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
