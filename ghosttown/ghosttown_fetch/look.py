"""Street Look: a look for every building from Mapillary street photos. Request in, look.json out.

For each building: choose the photos that see its walls (selection), drop photos whose labels say the
pose is wrong or the view is blocked and take the next-best ones in their place, keep only pixels that are
labelled building and that the model says show this building's nearest surface, calibrate each photo's
exposure against its road, and read colour by height, glass and floor height (appearance). Buildings
without a usable photo get the guessed look."""
import collections
import functools

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
POSE, BLOCKED = "pose", "blocked"   # why the label check drops a photo: sky or ground on the wall, or a blocked view
GAIN_RANGE = (0.5, 2.0)
DETAIL_PAD_M = 2.0
MAX_SEARCH_M = 1000.0
MIN_PIXELS = 30
DECODED_PHOTOS = 8   # photos kept decoded at once; each is 36 MiB at 2048 x 1536, so never all of a site's photos
REPLACE_TRIES = 6    # candidates a building may try in place of the photos it loses
DEPTH_SLACK_M, DEPTH_SLACK = 1.0, 0.005   # a pixel's surface may lie this much nearer than its wall point (m, share)
NO_GROUND = "Ground heights couldn't be fetched for the photos; try again in a minute."


class NothingListed(Exception):
    """No part of the site could be searched for photos."""


class NoGround(Exception):
    """The scene stands on ground heights, but the look run couldn't fetch them for its cameras."""


class NotReached(Exception):
    """Mapillary stopped answering while photos or labels were being fetched, and none came."""


def _decoder(jpegs):
    """decoded(image id): a photo's pixels, held only while it is one of the DECODED_PHOTOS most recently used.
    One cache per run, so nothing stays in memory once the run is over. Every building that uses a photo gets
    the same array, so readers must not change it."""
    return functools.lru_cache(maxsize=DECODED_PHOTOS)(lambda image_id: imagery.decode_linear(jpegs[image_id]))


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
    terrain = _terrain(request, net, frame, search)

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
    whole = {}

    def points(ci):
        """The sample indices photo ci sees, sharp or not: the label check weighs them all. One sight test per
        photo whose labels are checked; choosing only ever looks at the sharp ones."""
        if ci not in whole:
            got = selection.sight(cameras[ci], samples, scene)
            whole[ci] = got[0] if got is not None else np.zeros(0, dtype=int)
        return whole[ci]

    choice = _Choice(cameras, seen, samples, order, picks, request["budget_photos"], points)
    choice.start(net, token)
    photos, pictures = {}, {}
    decoded = _decoder(photos)
    # {image id: (loader of its pixels, labels, road luminance)} for the photos that can be read. A photo is decoded
    # here once, for its road, and dropped; the buildings that use it decode it again through the small cache. One
    # that can't be downloaded or decoded is replaced like a photo the label check drops, while candidates remain.
    while True:
        wanted = sorted(choice.ids() - pictures.keys())
        if not wanted:
            break
        got = _reached(mapillary.fetch_many(lambda i: mapillary.photo(net, i, token), wanted))
        lost = []
        for i in wanted:
            if isinstance(got[i], Exception):
                lost.append(i)
                continue
            choice.downloaded.add(i)
            try:
                image = imagery.decode_linear(got[i])
            except (OSError, ValueError):
                lost.append(i)
                continue
            lab = choice.labels[i]
            road = imagery.road_luminance(image, lab)
            del image
            photos[i] = got[i]
            pictures[i] = (functools.partial(decoded, i), lab, road)
        if not lost:
            break
        choice.lose(lost)
        choice.fill(net, token)
    choice.labels.clear()   # the photos read keep theirs in `pictures`
    skipped = len(choice.unreadable)
    if skipped:
        text = (f"{skipped} photo couldn't be read and was skipped." if skipped == 1
                else f"{skipped} photos couldn't be read and were skipped.")
        answer["notes"].append({"level": "info", "code": "mapillary_photos", "text": text})
    roads = [p[2] for p in pictures.values() if p[2]]
    reference = float(np.median(roads)) if roads else None

    progress("Reading facades", 65)
    reading = _Reading(cameras, seen, choice.points, samples, scene, pictures, reference)
    used = set()
    for b, bid in enumerate(scene.ids):
        entry, kept = _building(b, choice.kept.get(b, []), reading)
        used.update(kept)
        if bid in detail:
            entry["detail_walls"] = _detail_walls(b, samples, scene)
        answer["buildings"][bid] = entry
    if not used:
        answer["notes"].append({"level": "warn", "code": "mapillary_none",
                                "text": "No usable street photos were found, so every building has the guessed look."})

    progress("Writing", 95)
    by_id = {c.id: c for c in cameras}
    years = [by_id[i].year for i in used]
    answer["photos_used"] = len(used)
    answer["years"] = [min(years), max(years)] if years else None
    if used:
        answer["sources"].append({"key": "mapillary", "name": "Mapillary", "credit": CREDITS["mapillary"]})
    prune = getattr(net, "prune", None)   # stand-ins for Net in tests and tools may have no cache
    if prune:
        prune("mapillary")   # photos and labels are reused for 30 days, then deleted
    return answer


def _terrain(request, net, frame, search):
    """The ground the cameras stand on: the scene's own. A scene built on flat ground (no ground_at_centre_m) gets
    flat cameras and no download. A scene built on ground heights needs them again here, and the run stops when
    they can't be had: cameras on flat ground would read every height off by the slope under them."""
    if request.get("ground_at_centre_m") is None:
        return terrain_mod.FlatTerrain()
    terrain, _note = terrain_mod.load(net, frame, search)
    if terrain.ground_at_centre_m is None:
        raise NoGround(NO_GROUND)
    return terrain


def _reached(got):
    """`got`, from mapillary.fetch_many, unless Mapillary stopped answering partway and nothing came at all: then
    the run stops with NotReached. Short of that, the photos that failed are skipped (spec 9)."""
    if got and all(isinstance(v, Exception) for v in got.values()):
        cut = next((v for v in got.values() if isinstance(v, mapillary.NotSent)), None)
        if cut is not None:
            raise NotReached(str(cut))
    return got


def _label_fault(cam, lab, idx, samples, b):
    """Spec 6.5's label check for the photo `cam` and building b, over b's points the photo sees (sample indices
    idx): POSE when more than DROP_SKY_GROUND of them land on sky or ground (the pose is off), BLOCKED when fewer
    than MIN_BUILDING of those that aren't thin clutter land on building or only thin clutter is in view, else
    None. Wires, poles and signs are masked out later but never held against the photo."""
    mine = idx[samples.building[idx] == b]
    u, v, _ok = cam.project(samples.P[mine])
    kinds = lab.at(u, v)
    solid = kinds[kinds != imagery.THIN]
    if not len(solid):
        return BLOCKED
    if np.isin(kinds, (imagery.SKY, imagery.GROUND)).mean() > DROP_SKY_GROUND:
        return POSE
    if (solid == imagery.BUILDING).mean() < MIN_BUILDING:
        return BLOCKED
    return None


class _Choice:
    """The photos each building is read from (`kept`), starting from selection.choose's picks.

    Labels come first, for the picks: a pick whose labels can't be fetched or fail the label check is dropped,
    and so later is one whose photo can't be downloaded or decoded (`lose`). A building that lost a pick then
    tries its next candidates (`fill`), until it has as many photos as it was picked or has tried REPLACE_TRIES:
    labels only, best first by choose's own gain (coverage by the photos it keeps, FREE_BONUS for a photo already
    in use). Candidates from the sequence of a photo dropped for sky or ground come after every other, since that
    sequence's poses tend to share the fault. A building short only because the budget ran out is not topped up.
    A replacement takes only a place that a dropped or failed pick gave back, so no more photos are kept than
    choose picked; and no more photos are downloaded than the budget, or than choose's first picks when detail
    buildings need more."""

    def __init__(self, cameras, seen, samples, order, picks, budget, points):
        self.cameras, self.seen, self.samples, self.order, self.picks = cameras, seen, samples, order, picks
        self.points = points   # points(camera index): the sample indices the photo sees, sharp or not
        self.by_id = {c.id: c for c in cameras}
        self.candidates = selection.candidates(seen, samples)
        self.wanted = {cameras[ci].id for chosen in picks.values() for ci in chosen}
        first = {cameras[chosen[0]].id for chosen in picks.values() if chosen}   # choose's pass one
        self.places, self.downloads = len(self.wanted), max(budget, len(first))
        self.kept, self.uses = {}, collections.Counter()
        self.times = np.zeros(len(samples))
        self.tried, self.later = collections.defaultdict(set), collections.defaultdict(set)
        self.tries = collections.Counter()
        self.labels = {}           # {image id: imagery.Labels, or None when they couldn't be fetched}
        self.downloaded = set()    # image ids whose photo has been downloaded, readable or not
        self.lost = set()          # image ids that can't be used: labels or photo failed
        self.unreadable = set()    # photos chosen to be read that couldn't be: the note counts them

    def ids(self):
        """The photos some building keeps."""
        return {i for i, n in self.uses.items() if n}

    def start(self, net, token):
        """Fetch the picks' labels, keep the picks that pass, and replace the rest."""
        self._fetch_labels(net, token, self.wanted)
        self.unreadable |= {i for i in self.wanted if self.labels[i] is None}
        for b in self.order:
            for ci in self.picks.get(b, ()):
                self.tried[b].add(ci)
                self._judge(b, ci)
        self.fill(net, token)

    def fill(self, net, token):
        """Let the buildings that lost a pick try their next candidates, in rounds of one each, in priority order,
        whose labels are fetched together."""
        while True:
            room = min(self.places - len(self.ids()), self.downloads - len(self.ids() | self.downloaded))
            batch, reserved = [], set()
            for b in self.order:
                if len(self.kept.get(b, ())) >= len(self.picks.get(b, ())) or self.tries[b] >= REPLACE_TRIES:
                    continue
                ci = self._next(b, len(reserved) < room, reserved)
                if ci is None:
                    continue
                self.tries[b] += 1
                self.tried[b].add(ci)
                if not self.uses[self.cameras[ci].id]:
                    reserved.add(self.cameras[ci].id)   # a new photo: one place in the budget, whoever keeps it
                batch.append((b, ci))
            if not batch:
                return
            self._fetch_labels(net, token, {self.cameras[ci].id for _b, ci in batch})
            for b, ci in batch:
                self._judge(b, ci)

    def lose(self, ids):
        """Photos that can't be read after all: every building that kept one loses it."""
        ids = set(ids)
        self.lost |= ids
        self.unreadable |= ids
        for b, chosen in self.kept.items():
            for ci in [ci for ci in chosen if self.cameras[ci].id in ids]:
                chosen.remove(ci)
                self.uses[self.cameras[ci].id] -= 1
                selection.cover(self.times, self.seen, self.samples, ci, b, -1)

    def _next(self, b, room, reserved):
        """Building b's best candidate not yet tried (a photo not yet in use only when there is `room`)."""
        best, best_rank = None, None
        for ci in self.candidates.get(b, ()):
            cam = self.cameras[ci]
            if ci in self.tried[b] or cam.id in self.lost:
                continue
            free = bool(self.uses[cam.id]) or cam.id in reserved
            if not (free or room):
                continue
            rank = (not (cam.sequence and cam.sequence in self.later[b]),
                    selection.gain(self.cameras, self.seen, self.samples, ci, b, self.times, free))
            if best is None or rank > best_rank:
                best, best_rank = ci, rank
        return best

    def _judge(self, b, ci):
        """Keep photo ci for building b when its labels came and pass the label check."""
        cam = self.cameras[ci]
        lab = self.labels.get(cam.id)
        if lab is None:
            return
        fault = _label_fault(cam, lab, self.points(ci), self.samples, b)
        if fault is not None:
            if fault == POSE and cam.sequence:
                self.later[b].add(cam.sequence)
            return
        self.kept.setdefault(b, []).append(ci)
        self.uses[cam.id] += 1
        selection.cover(self.times, self.seen, self.samples, ci, b)

    def _fetch_labels(self, net, token, ids):
        need = sorted(i for i in ids if i not in self.labels)
        got = _reached(mapillary.fetch_many(lambda i: mapillary.detections(net, i, token), need))
        for i in need:
            if isinstance(got[i], Exception):
                self.labels[i] = None
                self.lost.add(i)
            else:
                self.labels[i] = imagery.Labels(got[i], self.by_id[i].height / self.by_id[i].width)


class _Reading:
    """What reading the facades needs, the same for every building of a run. `grids` holds each photo's owner
    grid once it is made."""

    def __init__(self, cameras, seen, points, samples, scene, pictures, reference):
        self.cameras, self.seen, self.points, self.samples, self.scene = cameras, seen, points, samples, scene
        self.pictures, self.reference = pictures, reference
        self.grids = {}


def _building(b, chosen, reading):
    """(look entry, ids of the photos it used) for building index b."""
    cameras, samples, scene = reading.cameras, reading.samples, reading.scene
    views, walls_grey, kept = [], [], []
    for ci in chosen:
        cam = cameras[ci]
        if cam.id not in reading.pictures:
            continue
        load, lab, road = reading.pictures[cam.id]
        idx = reading.points(ci)
        if _label_fault(cam, lab, idx, samples, b) is not None:
            continue   # the label check already kept such photos out; this is a safety net
        gain = float(np.clip(reading.reference / road, *GAIN_RANGE)) if reading.reference and road else 1.0
        if cam.id not in reading.grids:
            reading.grids[cam.id] = _owner_grid(cam, scene)
        image = load()
        colours, heights, wall_ids = [], [], []
        for w in np.unique(samples.wall[idx[samples.building[idx] == b]]):
            got = _straighten(cam, int(w), b, scene, image, lab, reading.grids[cam.id])
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
        idx, ppm = reading.seen[ci]
        seen_mask[idx[(samples.building[idx] == b) & (ppm >= selection.USABLE_PPM)]] = True
    share = float(samples.area[seen_mask & mine].sum() / max(samples.area[mine].sum(), 1e-9))
    entry = {"source": "photos", "photos": len(kept), "confidence": appearance.confidence(len(kept), share),
             "floor_h": appearance.floor_height(walls_grey, STRAIGHTEN_PPM), "zones": zones}
    return entry, [cameras[ci].id for ci in kept]


def _owner_grid(cam, scene):
    """(owner, depth): which building each cell of a MASK_GRID_W-wide pixel grid shows first (-1 for none), and
    how far along the cell's ray that surface is."""
    dirs, rows = cam.rays(MASK_GRID_W)
    owner, dist = scene.first_hit(cam.position[None], dirs, selection.MAX_DIST_M + 100.0)
    return owner.reshape(rows, MASK_GRID_W).astype(np.int32), dist.reshape(rows, MASK_GRID_W).astype(np.float32)


def _straighten(cam, w, b, scene, image, lab, grid):
    """(colours, heights, grey rows, mask) for wall w seen straight on at STRAIGHTEN_PPM, keeping only
    pixels labelled building whose ray first meets building b at the wall itself; None when too little is left.
    A pixel whose surface lies nearer than its wall point (by more than max(DEPTH_SLACK_M, DEPTH_SLACK of the
    distance)) shows something in front of the wall, often a nearer part of the same building, and is not read."""
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
    owner, depth = grid
    rows, cols = owner.shape
    r, c = (v[ok] * rows).astype(int), (u[ok] * cols).astype(int)
    d = np.linalg.norm(P[ok] - cam.position, axis=1)
    ok[ok] &= (owner[r, c] == b) & (depth[r, c] >= d - np.maximum(DEPTH_SLACK_M, DEPTH_SLACK * d))
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
