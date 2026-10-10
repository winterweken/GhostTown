"""Development applications (design/development-applications.md §4.3): the City of Toronto's open applications,
the building permits for new buildings and the applications only its table has, inside the circle, as sites, each
with a starting box.

An application point is the City address point it was filed at; an application only the City's table has is at
its table X/Y (mtm27), and a building permit at its address point (construction). Each is a status point. Each one
kept is placed in the current COMMON parcel it falls inside. Points that share a parcel, and one number's several
parcels, join into one site, the union of its parcels. A site's group is its most live point's
(APPLICATION_GROUPS), and its box starts as the largest rectangle inside it (boxfit), as tall as its newest permit
or planning application says (height_of), else as its floor area allows, on the lowest ground under it.

Ported from BHPlus bh_context/applications.py (60d801e). Ghost Town has no subject-site outline, so no site is left
out as the user's own, and each application carries the City's link to it (context.city_link) rather than a
Comments text."""
import datetime
import math
import re

import shapely
from shapely.geometry import MultiPolygon, Point, Polygon

from . import APPLICATION_GROUPS, boxfit, buildings, mtm27
from . import context as ctx
from .geom import GRID_M, feature_geometry, polygons, to_local
from .sources import ckan

REVIEW = ("Under Review", "Application Received", "Accepted", "In Process", "In Progress", "Hearing Scheduled",
          "Tentatively Scheduled", "Hearing Rescheduled", "Postponed", "Deferred", "Notice Prepared",
          "Prepare Notice", "Inactive", "Amend Drft Plan App")
APPROVED = ("Council Approved", "OMB Approved", "Approved", "Approved with Conditions", "NOAC Issued",
            "Draft Plan Approved", "Final Approval Completed", "Conditional Consent", "OMB Partially Approved",
            "Decision Issued", "Await Expiry Date")
APPEALED = ("OMB Appeal", "TLAB Appeal", "Appeal Received", "Appeal Received by TLAB", "Appeal Received by C of A",
            "Appeal Decision Pending", "Appealed", "Review of Decision Requested", "Motion Decision",
            "Appeal Dismissed")
REFUSED = ("Refused", "OMB Refused")
CLOSED_LABELS = ("Closed", "Withdrawn", "Application Withdrawn")     # the table has no STATUS_GROUP
PERMIT_GROUPS = ("construction", "built")
COA_TYPES = ("MV", "CO", "TLAB")
_GROUPS = (("review", REVIEW), ("approved", APPROVED), ("appealed", APPEALED))

METRES_RANGE = (3.0, 700.0)
MAX_STOREYS = 120
MIN_M_PER_STOREY = 2.5     # a stated height below storeys × this is a part's (a base, a ground floor), not the building's
_UNIT = r"(?:m|metres?|meters?)(?![\w²³])"          # never "m2", "m²" or a word that starts with m
_NUMBER = r"(?<![\d.,])(\d{1,3}(?:\.\d+)?)"         # never the tail of "1,500" or "2.5"
_METRES_AFTER = [re.compile(p, re.I) for p in (
    r"stor(?:eys?|y|ies)\s*\(\s*" + _NUMBER + r"\s*" + _UNIT,           # "66-storey (232 metres ...)"
    r"\bheights?\b[^.;\d]{0,40}?" + _NUMBER + r"\s*" + _UNIT,              # "a height of 300 metres", "Height: 45 m"
    _NUMBER + r"\s*" + _UNIT + r"\s+(?:tall|high|in\s+height)\b")]        # "155 m tall", "30 metres in height"
_STOREY = r"\s*-?\s*stor(?:eys?|y|ies)\b"
_STOREYS = re.compile(r"(?<![\d.,])(\d{1,3})" + _STOREY, re.I)                       # "21-storey", "50 storeys"
_STOREYS_BRACKETED = re.compile(r"\(\s*(\d{1,3})\s*\)" + _STOREY, re.I)              # "SIX (6) STOREY"
_STOREYS_STY = re.compile(r"(?<![\d.,])(\d{1,3})\s*-?\s*stys?\b", re.I)              # "9 sty"
_UNITS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
_TEENS = ("ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
          "nineteen")
_TENS = ("twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_WORD_NUMBERS = dict([(w, i + 1) for i, w in enumerate(_UNITS)] + [(w, i + 10) for i, w in enumerate(_TEENS)]
                     + [(w, 20 + 10 * i) for i, w in enumerate(_TENS)])
_STOREYS_WORDS = re.compile(r"\b(?:(" + "|".join(_TENS) + r")(?:[\s-]+(" + "|".join(_UNITS) + r"))?|("
                            + "|".join(_TEENS + _UNITS) + r"))" + _STOREY, re.I)   # "six-storey", "forty five storey"

FALLBACK_HEIGHT_M = buildings.LEVEL_M


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _label_group(label, kind):
    """(group, unknown label) of an open application's status label and folder type."""
    if label in REFUSED:
        return None, None
    if kind in COA_TYPES:
        return "coa", None
    for group, labels in _GROUPS:
        if label in labels:
            return group, None
    return "review", label


def group_of(props):
    """(group, unknown label) of one map application point's properties. The group is None for one left out: not
    in the Open status group, or refused. A Committee of Adjustment or TLAB application (COA_TYPES) is "coa"
    whatever its open label. An open planning label the tables lack counts as "review", and comes back as the
    unknown label so a note can name it."""
    if _text(props.get("STATUS_GROUP")) != "Open":
        return None, None
    return _label_group(_text(props.get("STATUS_DESC")), _text(props.get("FOLDERTYPE")))


def status_point(number, source, group, kind, status, date, description="", address="", floor_area_m2=0.0,
                 folderrsn="", unknown=None, url=""):
    """One application's or permit's facts as build() reads them."""
    return {"number": number, "source": source, "group": group, "type": kind, "status": status, "date": date,
            "description": description, "address": address, "floor_area_m2": float(floor_area_m2),
            "folderrsn": folderrsn, "unknown": unknown, "url": url}


def folder_of(value):
    """A FOLDERRSN as text digits ("5793154"), from the map's number or the table's text; "" for none."""
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)) and math.isfinite(value) and value == int(value):
        return str(int(value))
    text = _text(value)
    return text if text.isdigit() else ""


def _date(ms):
    """'YYYY-MM-DD' (UTC) of an epoch-milliseconds date, '' for none."""
    if not isinstance(ms, (int, float)) or isinstance(ms, bool):
        return ""
    try:
        return datetime.datetime.fromtimestamp(ms / 1000.0, datetime.timezone.utc).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return ""


def map_point(props):
    """The status point of one map application point, or None for one left out (group_of)."""
    number = _text(props.get("APPLICATION_NUMBER"))
    group, label = group_of(props)
    if not number or group is None:
        return None
    return status_point(number, "application", group, _text(props.get("FOLDERTYPE")),
                        _text(props.get("STATUS_DESC")), _date(props.get("SUBMIT_DATE")),
                        description=_text(props.get("FOLDERDESCRIPTION")), address=_text(props.get("FULL_ADDRESS")),
                        folderrsn=folder_of(props.get("FOLDERRSN")), unknown=label,
                        url=ctx.city_link(props.get("AIC_URL")))


def _coordinate(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 0 else None


def table_points(rows, frame, map_folders):
    """[(point in local metres, status point)] of the table's open, not refused applications that no map point
    carries (`map_folders`, the FOLDERRSNs of the map points around the site), each at its X/Y converted (mtm27).
    A row without a number, folder, readable submission date or usable X/Y is skipped. Descriptions and links are
    left empty for the caller to fill."""
    out = []
    for row in rows:
        folder = folder_of(row.get("FOLDERRSN"))
        number = "".join(_text(row.get("APPLICATION#")).split())
        label, kind = _text(row.get("STATUS")), _text(row.get("APPLICATION_TYPE"))
        x, y = _coordinate(row.get("X")), _coordinate(row.get("Y"))
        submitted = ckan.day(row.get("DATE_SUBMITTED"))
        if (not folder or folder in map_folders or not number or x is None or y is None or submitted is None
                or label in CLOSED_LABELS):
            continue
        group, unknown = _label_group(label, kind)
        if group is None:
            continue
        address = " ".join(t for t in (_text(row.get(k)) for k in ("STREET_NUM", "STREET_NAME", "STREET_TYPE",
                                                                   "STREET_DIRECTION")) if t)
        out.append((Point(*frame.to_local(*mtm27.to_lonlat(x, y))),
                    status_point(number, "application", group, kind, label, submitted, address=address,
                                 folderrsn=folder, unknown=unknown)))
    return out


def rank(group):
    """A group's place, most live first (APPLICATION_GROUPS)."""
    return APPLICATION_GROUPS.index(group)


def _storeys(text):
    """Every storey count the text names (1 to MAX_STOREYS), in figures, in brackets, as "sty" or in words."""
    found = [int(n) for pattern in (_STOREYS, _STOREYS_BRACKETED, _STOREYS_STY) for n in pattern.findall(text)]
    for tens, unit, small in _STOREYS_WORDS.findall(text):
        found.append(_WORD_NUMBERS[tens.lower()] + (_WORD_NUMBERS[unit.lower()] if unit else 0) if tens
                     else _WORD_NUMBERS[small.lower()])
    return [n for n in found if 0 < n <= MAX_STOREYS]


def height_of(description):
    """(metres, how it was found) from an application's description, or None when it states no height. A height
    in metres counts only where it is tied to the building: the first number after "height" in its clause ("a
    height of 300 metres"), one followed by "tall", "high" or "in height", or one in brackets right after an
    N-storey ("66-storey (232 metres ...)"), within METRES_RANGE. Square metres never count (the unit must be
    followed by neither a 2 nor a letter), nor a number that is the tail of a bigger one. When the description also
    names storeys, a height below MIN_M_PER_STOREY a storey is a part's (a base building's, a ground floor's) and is
    set aside. Else the most storeys it names (1 to MAX_STOREYS) × LEVEL_M. Storeys count in figures ("21-storey"),
    in brackets ("SIX (6) STOREY"), abbreviated ("9 sty") or in words ("forty-five storey")."""
    text = description if isinstance(description, str) else ""
    storeys = _storeys(text)
    floor = max(storeys) * MIN_M_PER_STOREY if storeys else METRES_RANGE[0]
    metres = [float(m) for pattern in _METRES_AFTER for m in pattern.findall(text)]
    metres = [m for m in metres if max(floor, METRES_RANGE[0]) <= m <= METRES_RANGE[1]]
    if metres:
        m = max(metres)
        return m, "description: {0:g} m".format(m)
    if storeys:
        n = max(storeys)
        return round(n * buildings.LEVEL_M, 3), "description: {0} storey{1}".format(n, "" if n == 1 else "s")
    return None


# ------------------------------------------------------------------ sites --

def features(answer, frame):
    """[(geometry in local metres, properties)] for each feature of an ArcGIS answer with a geometry; polygons are
    made valid, and ones with no area left are dropped."""
    out = []
    for feature in answer:
        geom = feature_geometry(feature)
        if geom is None:
            continue
        try:
            g = to_local(geom, frame)
        except (shapely.errors.ShapelyError, ValueError, TypeError):
            continue
        if g.geom_type in ("Polygon", "MultiPolygon"):
            g = _clean(g)
            if g.is_empty:
                continue
        out.append((g, feature.get("properties") or {}))
    return out


def _clean(g):
    """`g`'s valid polygonal part, on the millimetre grid (an empty Polygon for none)."""
    parts = polygons(g)
    if not parts:
        return Polygon()
    return parts[0] if len(parts) == 1 else MultiPolygon(parts)


def _union(geoms):
    geoms = [g for g in geoms if g is not None and not g.is_empty]
    if not geoms:
        return Polygon()
    try:
        return shapely.union_all(geoms, grid_size=GRID_M)
    except shapely.errors.GEOSException:
        return shapely.union_all([shapely.make_valid(g) for g in geoms], grid_size=GRID_M)


def _common(a, b):
    try:
        return shapely.intersection(a, b, grid_size=GRID_M)
    except shapely.errors.GEOSException:
        return shapely.intersection(shapely.make_valid(a), shapely.make_valid(b), grid_size=GRID_M)


def _current(props, now_ms):
    """Whether a parcel is current: no DATE_EXPIRY, or one still to come (epoch milliseconds)."""
    expiry = props.get("DATE_EXPIRY")
    return expiry is None or (isinstance(expiry, (int, float)) and not isinstance(expiry, bool) and expiry > now_ms)


def _parcels(parcel_features, now_ms):
    """[(key, geometry)] of the current COMMON parcels, records sharing a PARCELID joined."""
    by_id = {}
    for g, p in parcel_features:
        if g.geom_type not in ("Polygon", "MultiPolygon") or not _current(p, now_ms):
            continue
        if _text(p.get("FEATURE_TYPE") or "COMMON") != "COMMON":
            continue
        key = p.get("PARCELID") or p.get("OBJECTID")
        by_id[key] = _union([by_id[key], g]) if key in by_id else g
    return list(by_id.items())


class _Join:
    """Union-find over parcel keys."""

    def __init__(self):
        self.up = {}

    def find(self, k):
        self.up.setdefault(k, k)
        while self.up[k] != k:
            self.up[k] = self.up[self.up[k]]
            k = self.up[k]
        return k

    def join(self, a, b):
        self.up[self.find(a)] = self.find(b)


def _newest_first(apps):
    return sorted(sorted(apps, key=lambda a: a["number"]), key=lambda a: a["date"], reverse=True)


def _from_permit(said):
    return "permit" + said[len("description"):]


def _height(apps, group, area):
    """(metres, where from) of a site's box."""
    if group == "coa":
        return FALLBACK_HEIGHT_M, "C of A"
    permits = [a for a in _newest_first(apps) if a["source"] == "permit" and a["group"] == group]
    for a in permits:
        got = height_of(a["description"])
        if got is not None:
            return got[0], _from_permit(got[1])
    for a in _newest_first([a for a in apps if a["source"] == "application" and a["group"] != "coa"]):
        got = height_of(a["description"])
        if got is not None:
            return got
    for a in permits:
        if a["floor_area_m2"] > 0 and area > 0:
            n = min(MAX_STOREYS, max(1, int(math.ceil(a["floor_area_m2"] / area))))
            return round(n * buildings.LEVEL_M, 3), "estimated from floor area: {0} storey{1}".format(
                n, "" if n == 1 else "s")
    return FALLBACK_HEIGHT_M, "not stated"


def _block(apps, shape, terrain):
    group = min((a["group"] for a in apps), key=rank)
    ordered = _newest_first(apps)
    if group in PERMIT_GROUPS:
        main = next(a for a in ordered if a["group"] == group)["number"]
    else:
        planning = [a for a in ordered if a["group"] != "coa" and a["source"] == "application"]
        main = (planning or ordered)[0]["number"]
    cx, cy, angle, w, d = boxfit.rectangle(shape)
    height_m, height_from = _height(apps, group, w * d)
    base = terrain.min_under(boxfit.footprint(cx, cy, angle, w, d)) - buildings.SINK_M
    numbers = sorted(a["number"] for a in apps)
    return {
        "id": "app:" + numbers[0], "group": group, "numbers": numbers, "main": main,
        "centre_m": [round(cx, 3), round(cy, 3)], "angle_deg": round(angle, 3),
        "width_m": round(w, 3), "depth_m": round(d, 3), "height_m": round(height_m, 3), "base_m": round(base, 3),
        "height_from": height_from,
        "applications": [{"number": a["number"], "type": a["type"], "status": a["status"], "submitted": a["date"],
                          "address": "; ".join(sorted(a["addresses"])), "description": a["description"],
                          "source": a["source"], "floor_area_m2": round(a["floor_area_m2"], 1), "url": a["url"]}
                         for a in ordered],
    }


def build(points, parcel_features, terrain, keep, now_ms, clip=None, more=()):
    """The application sites as context.json's "applications" blocks.

    `points` and `parcel_features` are [(geometry in local metres, properties)] (features()); `keep(point)` says
    whether a point counts (inside the circle and the City); `clip` (the circle, or None) is what a site is cut to
    before its box is fitted, as the parcel lines are: a ravine or campus parcel otherwise runs far past the
    context. A site with nothing left inside `clip` gets no box. `more` is [(point in local metres, status point)]:
    the table's applications and the permits, which go through `keep` like the map points. Returns {"blocks":
    sorted by id, "no_parcel": applications none of whose kept points is inside a current COMMON parcel,
    "unknown": the open labels the status tables lack, sorted}."""
    keyed = _parcels(parcel_features, now_ms)
    shapes = dict(keyed)
    tree = shapely.STRtree([g for _, g in keyed]) if keyed else None
    apps, unknown = {}, set()

    def add(g, sp):
        if g.geom_type != "Point" or not keep(g):
            return
        if sp["unknown"]:
            unknown.add(sp["unknown"])
        a = apps.setdefault(sp["number"], dict(sp, addresses=[], parcels=set()))
        if sp["address"] and sp["address"] not in a["addresses"]:
            a["addresses"].append(sp["address"])
        if sp["url"] and not a["url"]:
            a["url"] = sp["url"]
        hits = [] if tree is None else [keyed[i] for i in tree.query(g, predicate="within")]
        if hits:
            a["parcels"].add(min(hits, key=lambda kg: kg[1].area)[0])

    for g, props in points:
        sp = map_point(props)
        if sp is not None:
            add(g, sp)
    for g, sp in more:
        add(g, sp)
    join = _Join()
    for a in apps.values():
        first = None
        for key in sorted(a["parcels"], key=str):
            if first is None:
                first = key
                join.find(key)
            else:
                join.join(key, first)
    sites = {}
    for a in apps.values():
        if a["parcels"]:
            sites.setdefault(join.find(next(iter(a["parcels"]))), []).append(a)
    blocks = []
    for members in sites.values():
        keys = set().union(*(a["parcels"] for a in members))
        shape = _union([shapes[k] for k in keys])
        inside = shape if clip is None else _clean(_common(shape, clip))
        if inside.is_empty or inside.area <= 0.0:
            continue
        blocks.append(_block(members, inside, terrain))
    return {"blocks": sorted(blocks, key=lambda b: b["id"]),
            "no_parcel": sum(1 for a in apps.values() if not a["parcels"]), "unknown": sorted(unknown)}
