"""Turn a request into a context document. Each source runs on its own: a failed source becomes a
warning note, and only a run where every attempted source failed raises NothingFetched."""
from . import LAYERS, buildings
from . import context as ctx
from .frame import Frame
from .net import SourceError
from .sources import osm
from .terrain import FlatTerrain

BUILT = ("buildings",)  # layers this version can build


class NothingFetched(Exception):
    """Every source that was tried failed."""


def assemble(request, net, *, progress=None):
    progress = progress or (lambda stage, pct: None)
    lat, lon = request["centre"]["lat"], request["centre"]["lon"]
    radius, layers = request["radius_m"], request["layers"]
    frame, terrain = Frame(lat, lon), FlatTerrain()
    doc = ctx.new(request, region="world", terrain_source=terrain.source)

    later = [layer for layer in LAYERS if layer in layers and layer not in BUILT]
    if later:
        ctx.note(doc, "info", "later", "Not in this version yet: " + ", ".join(later) + ".")

    tried = failed = 0
    if "buildings" in layers:
        tried += 1
        progress("OpenStreetMap", 10)
        try:
            features = osm.fetch(net, lat, lon, radius, layers, endpoint=request.get("overpass_url") or osm.ENDPOINT)
        except SourceError as e:
            failed += 1
            ctx.note(doc, "warn", "osm", str(e))
        else:
            ctx.add_source(doc, "osm")
            progress("Buildings", 60)
            doc["elements"].extend(buildings.from_osm(features, frame, terrain))

    if tried and failed == tried:
        raise NothingFetched(" ".join(n["text"] for n in doc["notes"] if n["level"] == "warn"))
    progress("Writing", 95)
    return ctx.finish(doc)
