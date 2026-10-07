"""Street Look: a look for every building from Mapillary street photos. Request in, look.json out.

For each building: choose the photos that see its walls (selection), drop photos whose labels say the
pose is wrong or the view is blocked, keep only pixels that are labelled building and that the model
says show this building, calibrate each photo's exposure against its road, and read colour by height,
glass and floor height (appearance). Buildings without a usable photo get the guessed look."""
import numpy as np

from . import CREDITS, appearance, imagery, raycast, selection
from . import look_schema as ls
from . import terrain as terrain_mod
from .camera import Camera
from .frame import Frame
from .sources import mapillary

STRAIGHTEN_PPM = 6.0
MASK_GRID_W = 200
DROP_SKY_GROUND = 0.3
MIN_BUILDING = 0.3
GAIN_RANGE = (0.5, 2.0)
DETAIL_PAD_M = 2.0
MAX_SEARCH_M = 1000.0
MIN_PIXELS = 30


class NothingListed(Exception):
    """No part of the site could be searched for photos."""


def run(request, net, token, *, progress=None):
    progress = progress or (lambda stage, pct: None)
    frame = Frame(request["centre"]["lat"], request["centre"]["lon"])
    answer = ls.new_answer()
    scene = raycast.Scene(request["buildings"])
    detail = {b["id"] for b in request["buildings"] if b.get("detail")}
    # Photos are read for at most as many buildings as the budget, detail buildings first, then the nearest:
    # more could not all get photos anyway, and it keeps a 1,000 m site about as quick as a small one.
    order = selection.priority(scene, detail)[:max(request["budget_photos"], len(detail))]
    samples = selection.wall_samples(scene).only(order)
    reach = float(np.hypot(samples.P[:, 0], samples.P[:, 1]).max()) if len(samples) else 0.0
    search = min(reach + request["search_margin_m"], MAX_SEARCH_M)

    progress("Terrain", 5)
    terrain, note = terrain_mod.load(net, frame, search)
    if note:
        answer["notes"].append({"level": note[0], "code": note[1], "text": note[2]})

    progress("Finding photos", 15)
    images, failed = mapillary.list_images(net, frame, search, token)
    if failed and failed >= len(mapillary.tiles(frame, search)):
        raise NothingListed("Mapillary couldn't be searched; try again in a minute.")
    if failed:
        answer["notes"].append({"level": "warn", "code": "mapillary_tiles", "text": "Some areas couldn't be searched."})
    cameras = [c for c in (Camera.from_mapillary(im, frame, terrain) for im in images) if c is not None]
    if request.get("not_before_year"):
        cameras = [c for c in cameras if c.year >= request["not_before_year"]]
    cameras = selection.thin(cameras)

    progress("Choosing photos", 30)
    seen = selection.views(cameras, samples, scene)
    picks = selection.choose(cameras, seen, samples, budget=request["budget_photos"], order=order)

    progress("Downloading photos", 45)
    wanted = sorted({cameras[ci].id for chosen in picks.values() for ci in chosen})
    photos = mapillary.fetch_many(lambda i: mapillary.photo(net, i, token), wanted)
    labels = mapillary.fetch_many(lambda i: mapillary.detections(net, i, token), wanted)

    progress("Reading facades", 65)
    by_id = {c.id: c for c in cameras}
    pictures = {}
    for i in wanted:
        if isinstance(photos[i], Exception) or isinstance(labels[i], Exception):
            continue
        try:
            image = imagery.decode_linear(photos[i])
        except (OSError, ValueError):
            continue
        lab = imagery.Labels(labels[i], by_id[i].height / by_id[i].width)
        pictures[i] = (image, lab, imagery.road_luminance(image, lab))
    if len(pictures) < len(wanted):
        answer["notes"].append({"level": "info", "code": "mapillary_photos",
                                "text": f"{len(wanted) - len(pictures)} photos couldn't be read and were skipped."})
    roads = [p[2] for p in pictures.values() if p[2]]
    reference = float(np.median(roads)) if roads else None

    used, grids = set(), {}
    for b, bid in enumerate(scene.ids):
        entry, kept = _building(b, picks.get(b, []), cameras, seen, samples, scene, pictures, reference, grids)
        used.update(kept)
        if bid in detail:
            entry["detail_walls"] = _detail_walls(b, samples, scene)
        answer["buildings"][bid] = entry
    for b in request["buildings"]:   # buildings whose solids couldn't be read still get a look
        answer["buildings"].setdefault(b["id"], appearance.default_look())

    progress("Writing", 95)
    years = [by_id[i].year for i in used]
    answer["photos_used"] = len(used)
    answer["years"] = [min(years), max(years)] if years else None
    if used:
        answer["sources"].append({"key": "mapillary", "name": "Mapillary", "credit": CREDITS["mapillary"]})
    return answer


def _building(b, chosen, cameras, seen, samples, scene, pictures, reference, grids):
    """(look entry, ids of the photos it used) for building index b."""
    views, walls_grey, kept = [], [], []
    for ci in chosen:
        cam = cameras[ci]
        if cam.id not in pictures:
            continue
        image, lab, road = pictures[cam.id]
        idx, _ppm = seen[ci]
        mine = idx[samples.building[idx] == b]
        u, v, _ok = cam.project(samples.P[mine])
        kinds = lab.at(u, v)
        if (np.isin(kinds, (imagery.SKY, imagery.GROUND)).mean() > DROP_SKY_GROUND
                or (kinds == imagery.BUILDING).mean() < MIN_BUILDING):
            continue   # the pose is off (sky or ground where the wall should be) or the view is blocked
        gain = float(np.clip(reference / road, *GAIN_RANGE)) if reference and road else 1.0
        if cam.id not in grids:
            grids[cam.id] = _owner_grid(cam, scene)
        colours, heights, wall_ids = [], [], []
        for w in np.unique(samples.wall[mine]):
            got = _straighten(cam, int(w), b, scene, image, lab, grids[cam.id])
            if got is None:
                continue
            cols, hts, grey, mask = got
            colours.append(cols * gain)
            heights.append(hts)
            wall_ids.append(np.full(len(hts), int(w)))
            walls_grey.append((grey, mask))
        if colours:
            views.append((np.concatenate(colours), np.concatenate(heights), np.concatenate(wall_ids)))
            kept.append(ci)
    profile = appearance.band_profile(views)
    zones = appearance.zones(profile, appearance.glass_cells(views)) if profile else None
    if zones is None:
        return appearance.default_look(), []
    mine = samples.building == b
    seen_mask = np.zeros(len(samples), dtype=bool)
    for ci in kept:
        idx, ppm = seen[ci]
        seen_mask[idx[(samples.building[idx] == b) & (ppm >= selection.USABLE_PPM)]] = True
    share = float(samples.area[seen_mask & mine].sum() / max(samples.area[mine].sum(), 1e-9))
    entry = {"source": "photos", "photos": len(kept), "confidence": appearance.confidence(len(kept), share),
             "floor_h": appearance.floor_height(walls_grey, STRAIGHTEN_PPM), "zones": zones}
    return entry, [cameras[ci].id for ci in kept]


def _owner_grid(cam, scene):
    """Which building each cell of a MASK_GRID_W-wide pixel grid shows first (-1 for none)."""
    dirs, rows = cam.rays(MASK_GRID_W)
    owner, _dist = scene.first_hit(cam.position[None], dirs, selection.MAX_DIST_M + 100.0)
    return owner.reshape(rows, MASK_GRID_W)


def _straighten(cam, w, b, scene, image, lab, grid):
    """(colours, heights, grey rows, mask) for wall w seen straight on at STRAIGHTEN_PPM, keeping only
    pixels labelled building whose ray first meets building b; None when too little is left."""
    a, e = scene.A[w], scene.B[w] - scene.A[w]
    length = float(np.hypot(*e))
    z0, z1 = scene.wall_z0[w], scene.wall_z1[w]
    ns = max(2, int(length * STRAIGHTEN_PPM))
    nt = max(2, int((z1 - z0) * STRAIGHTEN_PPM))
    S, T = np.meshgrid((np.arange(ns) + 0.5) / ns, z1 - (np.arange(nt) + 0.5) / STRAIGHTEN_PPM)
    P = np.column_stack([a[0] + e[0] * S.ravel(), a[1] + e[1] * S.ravel(), T.ravel()])
    P[:, :2] += scene.N[w] * 0.05
    u, v, ok = cam.project(P)
    ok &= (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
    if ok.sum() < MIN_PIXELS:
        return None
    rows, cols = grid.shape
    ok[ok] &= grid[(v[ok] * rows).astype(int), (u[ok] * cols).astype(int)] == b
    ok[ok] &= lab.at(u[ok], v[ok]) == imagery.BUILDING
    if ok.sum() < MIN_PIXELS:
        return None
    colours = imagery.sample(image, u[ok], v[ok])
    grey = np.zeros(ns * nt, dtype=np.float32)
    grey[ok] = imagery.luminance(colours)
    return colours, P[ok, 2] - scene.base_z[b], grey.reshape(nt, ns), ok.reshape(nt, ns)


def _detail_walls(b, samples, scene):
    """Exposed wall spans of building b with the heights (above its lowest point) where they are exposed."""
    out = []
    base = scene.base_z[b]
    mine = samples.building == b
    for w in np.unique(samples.wall[mine]):
        hs = samples.height[mine & (samples.wall == w)]
        z0 = max(float(scene.wall_z0[w] - base), float(hs.min()) - DETAIL_PAD_M)
        z1 = min(float(scene.wall_z1[w] - base), float(hs.max()) + DETAIL_PAD_M)
        if z1 - z0 < 1.0:
            continue
        out.append({"a": [round(float(c), 3) for c in scene.A[w]], "b": [round(float(c), 3) for c in scene.B[w]],
                    "n": [round(float(c), 4) for c in scene.N[w]], "z0": round(z0, 2), "z1": round(z1, 2)})
    return out
