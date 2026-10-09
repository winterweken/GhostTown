"""Turn a request into a context document.

The centre decides the region. Inside the City of Toronto, the City's own layers supply buildings,
ground, trees and parcels; elsewhere, OpenStreetMap supplies buildings on plain ground. NRCan supplies
the terrain in Canada. Each source runs on its own: a failure becomes a warning note, and only a run
where every data source failed raises NothingFetched. Real-world outlines occasionally defeat the
geometry library; that too costs only the layer it happens in. In Ontario, with LiDAR roofs asked for,
Geospatial Ontario's LiDAR gives every building a second, measured roof, written beside the context.
In Toronto, with Development applications asked for, the City's application points, applications table,
building permits, address points and parcels become the development application sites, written only when every
one of those sources answered, so a build that couldn't look at them all leaves the boxes alone."""
import datetime
import os
import time

import numpy as np
import shapely
from shapely.geometry import Point

from . import (BUILDING_KINDS, applications, buildings, construction, fitted_roofs, ground, lidar_roofs, parcels,
               region, survey, trees)
from . import context as ctx
from . import terrain as terrain_mod
from .frame import Frame
from .geom import to_local
from .net import SourceError
from .sources import (ontario_lidar, osm, toronto, toronto_applications, toronto_massing, toronto_permits,
                      toronto_photo)

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
FITTED_STAGE = "Fitted roofs"
FITTED_KEPT = "Flat and LiDAR roofs are still available."


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
    text = f"LiDAR roofs: Geospatial Ontario, {counts['buildings']} buildings, {counts['triangles']:,} triangles."
    if counts["newer"] == 1:
        text += " 1 building part is newer than the LiDAR survey and keeps a flat top."
    elif counts["newer"]:
        text += f" {counts['newer']:,} building parts are newer than the LiDAR survey and keep flat tops."
    ctx.note(doc, "info", "lidar", text)
    _fitted(doc, heights, cell, out_dir, progress)


def _fitted(doc, heights, cell, out_dir, progress):
    """Fitted roofs written beside the LiDAR roofs as fitted_roofs.npz, with a `fitted` entry in the
    `lidar` block. A failure is a warning that leaves the LiDAR roofs as they are."""
    progress(FITTED_STAGE, 79)
    try:
        arrays, counts = fitted_roofs.build(doc["elements"], heights, cell)
        if arrays is None:
            return
        lidar_roofs.write(os.path.join(out_dir, fitted_roofs.FILE), arrays)
    except Exception as e:  # anything at all costs only the fitted roofs, never the build
        ctx.note(doc, "warn", "fitted", f"The fitted roofs couldn't be built ({str(e)[:80]}). {FITTED_KEPT}")
        return
    doc["lidar"]["fitted"] = {"file": fitted_roofs.FILE, "buildings": counts["buildings"],
                              "triangles": counts["triangles"]}
    ctx.note(doc, "info", "fitted", fitted_roofs.note_text(counts))


APPLICATIONS_STAGE = "Development applications"
APPLICATIONS_FAILED = "Development applications weren't refreshed, so any boxes were left as they are: {reason}"
NO_APPLICATIONS = "Development applications are fetched for sites in the City of Toronto only."
APPLICATIONS_UNHANDLED = "a parcel shape couldn't be handled."
APPLICATION_SOURCES = {"boundary": "the City of Toronto boundary",
                       "map": "the City's development applications map",
                       "parcels": "the City's property boundaries", "addresses": "the City's address points",
                       "table": "the City's development applications table",
                       "permits": "the City's building permits"}
NOTE_TABLE = ("{n} development application{s} {were} placed from the City's applications table, which its map "
              "doesn't show yet.")
NOTE_HOUSES = "{n} building permit{s} for new houses around the site {were} left out."
NOTE_UNPLACED = ("{n} building permit{s} around the site couldn't be placed: the City's address points don't have "
                 "{its} address{es}.")
NOTE_NO_PARCEL = "{n} development application{s} {were} left out: not inside any parcel."
NOTE_STATUS = ("The City gave {labels} as a development application status, which Ghost Town doesn't know yet, so "
               "it is shown as Under review.")


def _counted(n):
    """The words a note about `n` things reads: n, s, were, its, es."""
    one = n == 1
    return {"n": n, "s": "" if one else "s", "were": "was" if one else "were", "its": "its" if one else "their",
            "es": "" if one else "es"}


def _named(what, fetch):
    """fetch(), its failure said as from `what` (APPLICATION_SOURCES), so the note names the source."""
    try:
        return fetch()
    except SourceError as e:
        raise SourceError(f"{APPLICATION_SOURCES[what]} couldn't be fetched ({str(e).rstrip('.')}).") from e


def _massing_year(net, year, today):
    """The 3D Massing edition recently built reaches back to: the one this build used, else the newest the City
    lists, else last year."""
    if year:
        return int(year)
    try:
        return int(toronto_massing.newest_edition(net).year)
    except (SourceError, ValueError, KeyError, TypeError):
        return today.year - 1


def _applications(doc, net, frame, radius, terrain, parcel_answer, massing_year, now, progress):
    """The development application sites (design/development-applications.md §4), written as context.json's
    "applications" only when every source answered: otherwise one warning and no list, so the add-on leaves the
    boxes as they are. Ported from BHPlus assemble._applications (60d801e)."""
    progress(APPLICATIONS_STAGE, 72)
    today = datetime.date.fromtimestamp(now)
    iso = today.isoformat()
    lat, lon = frame.lat0, frame.lon0
    circle = Point(0.0, 0.0).buffer(radius, quad_segs=64)
    try:
        boundary = _named("boundary", lambda: region.fetch_boundary(net))
        map_answer = _named("map", lambda: toronto.fetch_applications(net, lat, lon, radius))
        if parcel_answer is None:
            parcel_answer = _named("parcels", lambda: toronto.fetch_parcels(net, lat, lon, radius))
        address_answer = _named("addresses", lambda: toronto.fetch_address_points(net, lat, lon, radius))
        table = _named("table", lambda: toronto_applications.get_table(net, iso))
        year = _massing_year(net, massing_year, today)
        live_rows = _named("permits", lambda: toronto_permits.get_live(
            net, construction.years_before(iso, construction.LIVE_YEARS), iso))
        done_rows = _named("permits", lambda: toronto_permits.get_completed(net, f"{year}-01-01", iso))
        city = to_local(boundary, frame)
        shapely.prepare(city)
        shapely.prepare(circle)

        def keep(g):
            return circle.contains(g) and city.contains(g)

        map_points = applications.features(map_answer, frame)
        folders = {applications.folder_of(p.get("FOLDERRSN")) for _, p in map_points} - {""}
        from_table = [(g, sp) for g, sp in applications.table_points(table, frame, folders) if keep(g)]
        described = _named("table", lambda: toronto_applications.descriptions(
            net, {sp["folderrsn"] for _, sp in from_table}, iso))
        for _, sp in from_table:
            text, link = described.get(sp["folderrsn"], ("", ""))
            sp["description"], sp["url"] = text, ctx.city_link(link)
        addresses = construction.Addresses(applications.features(address_answer, frame))
        live, live_houses, live_lost = construction.points(construction.live(live_rows, iso), "construction",
                                                           addresses, keep)
        done, done_houses, done_lost = construction.points(construction.completed(done_rows, year), "built",
                                                           addresses, keep)
        found = applications.build(map_points, applications.features(parcel_answer, frame), terrain, keep,
                                   now * 1000.0, clip=circle, more=from_table + live + done)
    except SourceError as e:
        ctx.note(doc, "warn", "applications", APPLICATIONS_FAILED.format(reason=str(e)))
        return
    except shapely.errors.ShapelyError:
        ctx.note(doc, "warn", "applications", APPLICATIONS_FAILED.format(reason=APPLICATIONS_UNHANDLED))
        return
    doc["applications"] = found["blocks"]
    doc["applications_date"] = iso
    ctx.add_source(doc, "toronto")
    boxed = {n for b in found["blocks"] for n in b["numbers"]}
    for count, text in ((len({sp["number"] for _, sp in from_table} & boxed), NOTE_TABLE),
                        (live_houses + done_houses, NOTE_HOUSES), (live_lost + done_lost, NOTE_UNPLACED),
                        (found["no_parcel"], NOTE_NO_PARCEL)):
        if count:
            ctx.note(doc, "info", "applications", text.format(**_counted(count)))
    if found["unknown"]:
        labels = ", ".join(f'"{label}"' for label in found["unknown"])
        ctx.note(doc, "info", "applications", NOTE_STATUS.format(labels=labels))


def assemble(request, net, *, progress=None, now=None):
    progress = progress or (lambda stage, pct: None)
    now = time.time() if now is None else now
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

    pieces, massing_year, parcel_answer = {}, None, None
    if where == "toronto":
        if "buildings" in layers:
            found = attempt("City buildings", 25, "city_buildings", "toronto",
                            lambda: _city_buildings(net, request, frame, radius, progress, doc))
            if found is not None:
                how, data, year = found
                massing_year = year if how == "massing" else None
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
                parcel_answer = found
                doc["elements"].extend(built("city_parcels", "City parcels",
                                             lambda: parcels.from_toronto(found, frame, terrain, radius)))
    elif "buildings" in layers:
        endpoint = request.get("overpass_url") or osm.ENDPOINT
        found = attempt("OpenStreetMap", 25, "osm", "osm", lambda: osm.fetch(net, lat, lon, radius, layers, endpoint=endpoint))
        if found is not None:
            doc["elements"].extend(built("osm", "OpenStreetMap buildings", lambda: buildings.from_osm(found, frame, terrain)))

    if tried and failed == tried:
        raise NothingFetched(" ".join(n["text"] for n in doc["notes"] if n["level"] == "warn"))

    if "applications" in layers:
        if where == "toronto":
            _applications(doc, net, frame, radius, terrain, parcel_answer, massing_year, now, progress)
        else:
            ctx.note(doc, "info", "applications", NO_APPLICATIONS)

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
