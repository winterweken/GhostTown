"""Which photos see which walls, and which photos to download.

A wall point counts as seen by a photo when the camera is 3-500 m away, faces the wall within 35 degrees of
square-on (in plan), is level (perspective and fisheye cameras within 12 degrees of pitch), has the point
inside the picture, and nothing stands between them."""
import math

import numpy as np

SPACING_ALONG_M, SPACING_UP_M = 3.0, 4.0
PROBE_M = 0.3
MIN_DIST_M, MAX_DIST_M = 3.0, 500.0
MAX_INCIDENCE_DEG = 35.0
MAX_PITCH_DEG = 12.0
FRAME_MARGIN = 0.02
USABLE_PPM = 5.0
PPM_CAP = 20.0
PER_BUILDING = 4
SIGHT_TOLERANCE_M = 1.0
FREE_BONUS = 1.5   # a photo already chosen for another building costs nothing
THIN_CELL_M, THIN_HEADING_DEG = 5.0, 30.0


class Samples:
    """Points on the buildings' exposed walls, with their wall's outward normal, owner, wall index, the
    wall area each stands for, and height above the owner's lowest point."""

    def __init__(self, P, N, building, wall, area, height):
        self.P, self.N, self.building, self.wall, self.area, self.height = P, N, building, wall, area, height

    def __len__(self):
        return len(self.P)

    def only(self, buildings):
        """The samples on these buildings (indices)."""
        m = np.isin(self.building, list(buildings))
        return Samples(self.P[m], self.N[m], self.building[m], self.wall[m], self.area[m], self.height[m])


def wall_samples(scene):
    P, N, owners, walls, areas, heights = [], [], [], [], [], []
    for w in range(len(scene.A)):
        a, b = scene.A[w], scene.B[w]
        z0, z1 = scene.wall_z0[w], scene.wall_z1[w]
        length, tall = float(np.hypot(*(b - a))), float(z1 - z0)
        nu = max(1, round(length / SPACING_ALONG_M))
        nv = max(1, round(tall / SPACING_UP_M))
        S, T = np.meshgrid((np.arange(nu) + 0.5) / nu, (np.arange(nv) + 0.5) / nv)
        xy = a + (b - a) * S.reshape(-1, 1)
        pts = np.column_stack([xy, z0 + tall * T.reshape(-1)])
        probe = pts.copy()
        probe[:, :2] += scene.N[w] * PROBE_M
        keep = ~scene.covered(probe)
        k = int(keep.sum())
        if not k:
            continue
        owner = int(scene.wall_owner[w])
        P.append(pts[keep])
        N.append(np.repeat(scene.N[w][None], k, axis=0))
        owners.append(np.full(k, owner))
        walls.append(np.full(k, w))
        areas.append(np.full(k, length * tall / (nu * nv)))
        heights.append(pts[keep, 2] - scene.base_z[owner])
    if not P:
        empty = np.zeros(0)
        return Samples(np.zeros((0, 3)), np.zeros((0, 2)), empty.astype(int), empty.astype(int), empty, empty)
    return Samples(np.concatenate(P), np.concatenate(N), np.concatenate(owners), np.concatenate(walls),
                   np.concatenate(areas), np.concatenate(heights))


def thin(cameras, cell_m=THIN_CELL_M, heading_deg=THIN_HEADING_DEG):
    """The newest camera per 5 m cell and 30° of heading (360° photos: per cell). Mapillary shoots every few
    metres along a street, and photos that close see the same walls: at 351 King St E this kept 5,937 of
    9,048 photos for about 1% less wall area seen well."""
    best = {}
    for i, c in enumerate(cameras):
        spherical = c.kind == "spherical"
        heading = None if spherical else int(math.degrees(math.atan2(c.forward[0], c.forward[1])) % 360 // heading_deg)
        key = (spherical, int(c.position[0] // cell_m), int(c.position[1] // cell_m), heading)
        j = best.get(key)
        if j is None or (c.year, c.id) > (cameras[j].year, cameras[j].id):
            best[key] = i
    return [cameras[i] for i in sorted(best.values())]


def views(cameras, samples, scene):
    """{camera index: (sample indices, pixels per metre)} for each camera that sees at least one point."""
    out = {}
    if not len(samples):
        return out
    cos_max = math.cos(math.radians(MAX_INCIDENCE_DEG))
    for ci, cam in enumerate(cameras):
        if cam.kind != "spherical" and abs(cam.pitch_deg()) > MAX_PITCH_DEG:
            continue
        if scene.covered(cam.position[None])[0]:
            continue   # a pose inside a building is wrong; it would "see" walls from inside
        d = samples.P - cam.position
        flat = np.hypot(d[:, 0], d[:, 1])
        m = (flat >= MIN_DIST_M) & (flat <= MAX_DIST_M)
        cos_inc = -(d[:, 0] * samples.N[:, 0] + d[:, 1] * samples.N[:, 1]) / np.maximum(flat, 1e-9)
        m &= cos_inc >= cos_max
        idx = np.nonzero(m)[0]
        if not len(idx):
            continue
        u, v, ok = cam.project(samples.P[idx])
        inside = ok & (u >= FRAME_MARGIN) & (u <= 1 - FRAME_MARGIN) & (v >= FRAME_MARGIN) & (v <= 1 - FRAME_MARGIN)
        idx = idx[inside]
        if not len(idx):
            continue
        target = samples.P[idx].copy()
        target[:, :2] += samples.N[idx] * 0.05
        ray = target - cam.position
        dist = np.linalg.norm(ray, axis=1)
        owner, hit = scene.first_hit(cam.position[None], ray / dist[:, None], dist + 0.5)
        idx = idx[(owner == samples.building[idx]) & (np.abs(hit - dist) <= SIGHT_TOLERANCE_M)]
        if len(idx):
            out[ci] = (idx, cam.pixels_per_metre(samples.P[idx], cos_inc[idx]))
    return out


def recency(year):
    if year >= 2022:
        return 1.0
    if year >= 2018:
        return 0.8
    return 0.6


def priority(scene, detail_ids):
    """Building indices: detail buildings first, then by distance from the site centre."""
    centres = {}
    for poly, b in zip(scene.solids, scene.solid_owner):
        c = poly.centroid
        centres.setdefault(int(b), []).append((c.x, c.y))
    dist = {b: float(np.hypot(*np.mean(v, axis=0))) for b, v in centres.items()}
    return sorted(dist, key=lambda b: (scene.ids[b] not in detail_ids, dist[b]))


def _usable(samples, idx, ppm, building=None):
    """Mask over one photo's seen points (sample indices idx, sharpness ppm): sharp enough to use, and on
    `building` when one is named."""
    ok = ppm >= USABLE_PPM
    return ok if building is None else ok & (samples.building[idx] == building)


def choose(cameras, seen, samples, *, budget, order):
    """{building index: [camera indices, in the order picked]}: each building in `order` gets up to PER_BUILDING.

    Pass one gives every building that has a usable photo its best one, whatever the budget: spec 6.4 never
    drops a building's only usable photo for budget. look.run serves at most max(`budget`, the number of detail
    buildings) buildings, so these first photos stay within that: detail buildings always come first, and up to
    20 may be asked for. Pass two, in `order` again, adds more photos to each building while the budget
    lasts: a photo nobody has chosen yet costs one from it, a photo already chosen is free.

    Each pick is the photo adding the most wall area x sharpness (capped at PPM_CAP) x recency. Points already
    covered count half as much each time, and a photo already chosen counts FREE_BONUS times as much."""
    by_building = {}
    for ci, (idx, ppm) in seen.items():
        for b in np.unique(samples.building[idx[_usable(samples, idx, ppm)]]):
            by_building.setdefault(int(b), []).append(ci)
    chosen, picks = set(), {}
    times = np.zeros(len(samples))   # how many picked photos cover each point; a point has one owner building

    def pick(b, may_add_new):
        """Add building b's best photo not yet picked for it (a new photo only if may_add_new); False if none."""
        best, best_gain = None, 0.0
        for ci in by_building.get(b, ()):
            if ci in picks.get(b, ()) or not (may_add_new or ci in chosen):
                continue
            idx, ppm = seen[ci]
            mine = _usable(samples, idx, ppm, b)
            k = idx[mine]
            gain = float((samples.area[k] * np.minimum(ppm[mine], PPM_CAP) / PPM_CAP * 0.5 ** times[k]).sum())
            gain *= recency(cameras[ci].year) * (FREE_BONUS if ci in chosen else 1.0)
            if gain > best_gain:
                best, best_gain = ci, gain
        if best is None:
            return False
        idx, ppm = seen[best]
        times[idx[_usable(samples, idx, ppm, b)]] += 1
        chosen.add(best)
        picks.setdefault(b, []).append(best)
        return True

    for b in order:
        pick(b, True)
    for b in order:
        while len(picks.get(b, ())) < PER_BUILDING:
            if not pick(b, len(chosen) < budget):
                break
    return picks
