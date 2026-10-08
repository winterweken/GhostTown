"""A building's look from its photos: colour by height, zones, glass, floor height.

Colours are linear RGB after exposure calibration; heights are metres above the building's lowest point.
A view is one photo's (colours, heights, wall ids) of the building's own, labelled, unblocked pixels."""
import numpy as np

BAND_M = 3.0
CELL_M = 6.0
MIN_BAND_PX = 20
MIN_PHOTOS_PER_BAND = 1
MIN_ZONE_M = 6.0
MAX_ZONES = 4
LUM_STEP = 0.30
CHROMA_STEP = 0.05
STOREFRONT_RANGE_M = (3.0, 9.0)
STOREFRONT_JUMP = 1.6
GLASS_CHROMA_SPREAD = 0.12
GLASS_LOG_LUM_SPREAD = 0.7
MIN_GLASS_VIEWS = 3
BLUE_RULE = 0.04
FLOOR_RANGE_M = (2.8, 6.0)
FLOOR_DEFAULT_M = 3.5
FLOOR_AGREE_M = 0.25
FLOOR_PEAK_MIN = 0.3
FLOOR_PEAK_SIGMAS = 3.0
FLOOR_EDGE_SPREAD = 1e-3
DEFAULT_ZONES = (
    {"h0": 0.0, "h1": 4.5, "kind": "storefront", "colour": (0.32, 0.32, 0.31)},
    {"h0": 4.5, "h1": None, "kind": "opaque", "colour": (0.42, 0.42, 0.40)},
)


def _lum(c):
    c = np.asarray(c, dtype=float)
    return c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722


def _chroma(c):
    c = np.asarray(c, dtype=float)
    return c / np.maximum(c.sum(-1, keepdims=True), 1e-9)


def band_profile(views):
    """{band: colour} per 3 m band: the median colour in each photo, then the median across photos. A photo
    counts for a band from 20 of its pixels; one photo is enough for a profile."""
    per = {}
    for colours, heights, _walls in views:
        bands = np.floor(heights / BAND_M).astype(int)
        for b in np.unique(bands):
            m = bands == b
            if b >= 0 and m.sum() >= MIN_BAND_PX:
                per.setdefault(int(b), []).append(np.median(colours[m], axis=0))
    return {b: np.median(v, axis=0) for b, v in sorted(per.items()) if len(v) >= MIN_PHOTOS_PER_BAND}


def glass_cells(views):
    """{6 m cell: is glass} for cells seen from at least three photos on the same wall. Glass changes
    colour with the viewpoint (it shows what it reflects); brick, stone and concrete do not."""
    per = {}
    for colours, heights, walls in views:
        cells = np.floor(heights / CELL_M).astype(int)
        for w, c in set(zip(walls.tolist(), cells.tolist())):
            m = (walls == w) & (cells == c)
            if m.sum() >= MIN_BAND_PX:
                per.setdefault((w, c), []).append(np.median(colours[m], axis=0))
    spreads = {}
    for (_w, c), cols in per.items():
        if len(cols) < MIN_GLASS_VIEWS:
            continue
        cols = np.array(cols)
        chroma = float(np.std(_chroma(cols), axis=0).sum())
        loglum = float(np.std(np.log(np.maximum(_lum(cols), 1e-4))))
        spreads.setdefault(c, []).append((chroma, loglum))
    return {c: bool(np.median([s[0] for s in v]) > GLASS_CHROMA_SPREAD
                    and np.median([s[1] for s in v]) > GLASS_LOG_LUM_SPREAD)
            for c, v in spreads.items()}


def _kind(band, colour, glass):
    cell = int(band * BAND_M // CELL_M)
    if cell in glass:
        return "glass" if glass[cell] else "opaque"
    c = np.asarray(colour)
    return "glass" if c[2] - c[0] > BLUE_RULE * max(_lum(c) / 0.1, 1.0) else "opaque"


def _difference(a, b):
    la, lb = _lum(a), _lum(b)
    return abs(la - lb) / max(la, lb, 1e-6), float(np.linalg.norm(_chroma(a) - _chroma(b)))


def _differs(a, b):
    lum, chroma = _difference(a, b)
    return lum > LUM_STEP or chroma > CHROMA_STEP


def _storefront(profile):
    """The band index where the storefront ends: the first boundary 3-9 m up where the band above is at
    least 1.6 times as bright as the band below. None without such a jump."""
    for b in sorted(profile):
        top = (b + 1) * BAND_M
        if STOREFRONT_RANGE_M[0] <= top <= STOREFRONT_RANGE_M[1] and (b + 1) in profile:
            if _lum(profile[b + 1]) >= STOREFRONT_JUMP * max(_lum(profile[b]), 1e-6):
                return b + 1
    return None


def _run(bands, kind, cols):
    return {"bands": list(bands), "kind": kind, "cols": list(cols)}


def _merge(a, b):
    if "storefront" in (a["kind"], b["kind"]):
        kind = "storefront"
    else:
        kind = a["kind"] if len(a["bands"]) >= len(b["bands"]) else b["kind"]
    return _run(a["bands"] + b["bands"], kind, a["cols"] + b["cols"])


def _thickness(run):
    return (max(run["bands"]) - min(run["bands"]) + 1) * BAND_M


def _colour(run):
    return np.median(run["cols"], axis=0)


def _is_cap(below, top):
    lb, lt = _lum(_colour(below)), _lum(_colour(top))
    return top["kind"] == "opaque" and max(lb, lt) >= STOREFRONT_JUMP * max(min(lb, lt), 1e-6)


def zones(profile, glass):
    """Up to four zones [{h0, h1, kind, colour}] from the band profile, or None without a profile."""
    if not profile:
        return None
    bands = sorted(profile)
    store = _storefront(profile)
    runs = []
    if store is not None:
        low = [b for b in bands if b < store]
        runs.append(_run(low, "storefront", [profile[b] for b in low]))
    for b in bands:
        if store is not None and b < store:
            continue
        kind = _kind(b, profile[b], glass)
        last = runs[-1] if runs else None
        if last is not None and last["kind"] == kind and not _differs(last["cols"][-1], profile[b]):
            last["bands"].append(b)
            last["cols"].append(profile[b])
        else:
            runs.append(_run([b], kind, [profile[b]]))
    # runs thinner than 6 m join a neighbour; a thin top run that contrasts with the run below is the cap
    i = 0
    while i < len(runs):
        r = runs[i]
        if r["kind"] in ("storefront", "cap") or _thickness(r) >= MIN_ZONE_M or len(runs) == 1:
            i += 1
            continue
        if i == len(runs) - 1 and i > 0 and runs[i - 1]["kind"] != "storefront" and _is_cap(runs[i - 1], r):
            r["kind"] = "cap"
            i += 1
            continue
        j = i - 1 if i > 0 and runs[i - 1]["kind"] != "storefront" else i + 1
        if j >= len(runs):
            i += 1
            continue
        lo, hi = min(i, j), max(i, j)
        runs[lo:hi + 1] = [_merge(runs[lo], runs[hi])]
        i = max(lo - 1, 0)
    # neighbours that ended up alike become one
    k = 0
    while k < len(runs) - 1:
        a, b = runs[k], runs[k + 1]
        if a["kind"] == b["kind"] and a["kind"] != "storefront" and not _differs(_colour(a), _colour(b)):
            runs[k:k + 2] = [_merge(a, b)]
        else:
            k += 1
    # at most four: merge the most alike neighbours (never the storefront)
    while len(runs) > MAX_ZONES:
        best, best_d = None, None
        for k in range(len(runs) - 1):
            if "storefront" in (runs[k]["kind"], runs[k + 1]["kind"]):
                continue
            d = sum(_difference(_colour(runs[k]), _colour(runs[k + 1])))
            if best_d is None or d < best_d:
                best, best_d = k, d
        if best is None:
            break
        runs[best:best + 2] = [_merge(runs[best], runs[best + 1])]
    out = []
    for k, r in enumerate(runs):
        out.append({"h0": 0.0 if k == 0 else float(min(r["bands"]) * BAND_M), "h1": None, "kind": r["kind"],
                    "colour": [round(float(c), 4) for c in _colour(r)]})
    for a, b in zip(out, out[1:]):
        a["h1"] = b["h0"]
    return out


def floor_height(walls, ppm, ids=None):
    """The dominant floor spacing in straightened walls [(grey rows top-down, mask)] at `ppm` pixels per
    metre: the strongest repeat of horizontal edges over 2.8-6 m, accepted when at least two walls agree
    within 0.25 m. `ids` names the wall each one shows (by default each is a wall of its own): a wall
    straightened from several photos votes once, with the median of their spacings, so one facade seen
    twice can't agree with itself. A repeat counts only if it is a peak of the autocorrelation inside the
    range (not at either end of it) and at least 0.3 and 3 / sqrt(rows) of its value at lag 0, the level a
    wall with no repeat reaches by chance; a featureless or smoothly shaded wall has none. Otherwise 3.5 m."""
    lo, hi = FLOOR_RANGE_M
    found = {}   # wall -> the spacings its photos show
    for wall, (grey, mask) in zip(range(len(walls)) if ids is None else ids, walls, strict=True):
        both = mask[1:] & mask[:-1]
        weight = both.sum(axis=1)
        rows = weight > 0
        used = int(rows.sum())
        if used < int(2 * hi * ppm):   # a wall shorter than two of the longest spacings can't show a repeat
            continue
        edges = (np.abs(np.diff(grey, axis=0)) * both).sum(axis=1) / np.maximum(weight, 1)
        p = np.where(rows, edges - edges[rows].mean(), 0.0)
        if p[rows].std() <= FLOOR_EDGE_SPREAD * edges[rows].mean():
            continue   # the same edge strength on every row, to rounding (a plain gradient): nothing repeats
        ac = np.correlate(p, p, "full")[len(p) - 1:]
        ac = ac / ac[0]
        lags = np.arange(len(ac)) / ppm
        window = np.flatnonzero((lags >= lo) & (lags <= hi))
        if not len(window):
            continue
        k = int(window[np.argmax(ac[window])])
        # The strongest lag is a peak (above the lag before it, not below the lag after) unless it is the first
        # or last lag of the range: there it is only the slope of something outside, the zero-lag peak of a
        # smooth wall or a repeat beyond 6 m.
        if window[0] < k < window[-1] and ac[k] >= max(FLOOR_PEAK_MIN, FLOOR_PEAK_SIGMAS / np.sqrt(used)):
            found.setdefault(wall, []).append(float(lags[k]))
    votes = [float(np.median(spacings)) for spacings in found.values()]
    best = []
    for value in votes:
        close = [f for f in votes if abs(f - value) <= FLOOR_AGREE_M]
        if len(close) > len(best):
            best = close
    return round(float(np.mean(best)), 2) if len(best) >= 2 else FLOOR_DEFAULT_M


def confidence(photos, seen_share):
    return round(min(1.0, photos / 3.0) * max(0.0, min(1.0, float(seen_share))), 3)


def default_look():
    return {"source": "guessed", "photos": 0, "confidence": 0.0, "floor_h": FLOOR_DEFAULT_M,
            "zones": [dict(z, colour=list(z["colour"])) for z in DEFAULT_ZONES]}
