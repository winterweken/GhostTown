"""What a build does to each development application box (design/development-applications.md §5.3), the box's
shape, and the report line, kept off Blender so plain pytest covers them. The planner is ported from BHPlus
bh_context/boxes.py (60d801e); Ghost Town has no pinning, no other family's types and no Align, and a box in Blender
is an object the add-on measures and hands in.

A box is a dict {"numbers": [...], "touched": bool, "closed": bool (grey Closed already), "centre_m": [x, y] (where
it stands now, in this build's local metres), ...whatever else the caller keeps on it}; boxes come oldest first. A
deleted box is {"numbers": [...], "centre_m": [x, y]}. No shapely and no bpy here: the add-on imports it."""
import math

from . import APPLICATION_GROUPS, GROUP_LABELS
from .frame import Frame

PERMIT_GROUPS = ("construction", "built")
CLOSED = "closed"
LABELS = dict(GROUP_LABELS, closed="Closed")
# BHPlus's box colours, its shadow study's Toronto palette (construction spec §5.1), sRGB 0-255.
COLOURS_SRGB = {"review": (255, 168, 106), "approved": (58, 192, 201), "appealed": (255, 57, 95),
                "construction": (108, 130, 166), "coa": (212, 143, 249), "built": (150, 150, 150),
                "closed": (210, 210, 210)}
ALPHA = 0.7                       # 30 % see-through: the context behind a box shows
TOL_M = 0.001
TOL_DEG = 0.05
TOL_SCALE = 1e-4
BOX_FACES = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))   # outward


def box_verts(site):
    """The 8 corners of a site's starting box in its own axes: x along its angle, origin at its base centre."""
    w, d, h = site["width_m"] / 2.0, site["depth_m"] / 2.0, float(site["height_m"])
    return [[-w, -d, 0.0], [w, -d, 0.0], [w, d, 0.0], [-w, d, 0.0],
            [-w, -d, h], [w, -d, h], [w, d, h], [-w, d, h]]


def placement(site):
    """(location, rotation in radians) of a site's box object."""
    return ([float(site["centre_m"][0]), float(site["centre_m"][1]), float(site["base_m"])],
            [0.0, 0.0, math.radians(site["angle_deg"])])


def touched(placed, now, tol_m=TOL_M, tol_deg=TOL_DEG, tol_scale=TOL_SCALE):
    """Whether the user changed a box since Ghost Town placed it: moved more than tol_m, turned more than tol_deg
    about any axis (a whole turn is none), scaled more than tol_scale, parented or turned some other way ("other"),
    or its mesh changed (another vertex count, or a vertex more than tol_m away). Nothing to compare with (None)
    counts as changed, so such a box is never removed."""
    if not placed or not now or now.get("other"):
        return True
    if any(abs(a - b) > tol_m for a, b in zip(now["location"], placed["location"])):
        return True
    for a, b in zip(now["rotation"], placed["rotation"]):
        turn = math.degrees(abs(a - b)) % 360.0
        if min(turn, 360.0 - turn) > tol_deg:
            return True
    if any(abs(a - b) > tol_scale for a, b in zip(now["scale"], placed["scale"])):
        return True
    if len(now["verts"]) != len(placed["verts"]):
        return True
    return any(abs(a - b) > tol_m for p, q in zip(now["verts"], placed["verts"]) for a, b in zip(p, q))


def shift(old_centre, old_ground, new_centre, new_ground):
    """(dx, dy, dz) that carries a point from an old build's local metres into a new one's at the same real place:
    where the old origin lies in the new frame, and how much lower the new z = 0 is (0 when either is flat)."""
    dx, dy = Frame(new_centre["lat"], new_centre["lon"]).to_local(old_centre["lon"], old_centre["lat"])
    dz = 0.0 if old_ground is None or new_ground is None else float(old_ground) - float(new_ground)
    return float(dx), float(dy), dz


def _on(site, xy):
    """Whether the point `xy` is on the site's starting box, its width along its angle."""
    a = math.radians(site["angle_deg"])
    dx, dy = xy[0] - site["centre_m"][0], xy[1] - site["centre_m"][1]
    along, across = dx * math.cos(a) + dy * math.sin(a), -dx * math.sin(a) + dy * math.cos(a)
    return abs(along) <= site["width_m"] / 2.0 and abs(across) <= site["depth_m"] / 2.0


def _far(xy, radius_m):
    return math.hypot(xy[0], xy[1]) > radius_m


def plan(sites, boxes, deleted, radius_m):
    """What a build does to each box.

    `sites` is context.json's "applications" (None when the build did not look); `boxes` the boxes in the scene,
    oldest first; `deleted` the boxes the user deleted. Returns {"looked", "place": [site], "update": [(box,
    site)], "close": [box], "remove": [box], "keep": [box], "deleted": [deleted box to remember], "left": [(box,
    site)]}:
    - a build that did not look keeps every box and remembers every deleted one;
    - each site goes to the boxes sharing any of its numbers: the one the user changed, else the oldest, is
      updated; the others are left as they are;
    - a site whose numbers a deleted box carries gets no box;
    - an Under construction or Recently built site no number matches is claimed by a box no site matched whose
      centre is on its starting box (the user's, else the oldest), or kept away by a deleted box there: a permit
      carries none of the numbers of the application it follows;
    - a site nothing matches gets a new box;
    - a box no site matches is kept when it is Closed already or outside this build's circle, turned Closed when
      the user changed it, else removed;
    - a deleted box is remembered while any of its numbers is in a site, a permit site on its spot is kept away by
      it, or it lies outside this build's circle; else it is forgotten."""
    out = {key: [] for key in ("place", "update", "close", "remove", "keep", "deleted", "left")}
    out["looked"] = sites is not None
    boxes, deleted = list(boxes or []), list(deleted or [])
    if sites is None:
        out["keep"], out["deleted"] = boxes, deleted
        return out
    taken = set()
    for site in sites:
        numbers = set(site["numbers"])
        candidates = [b for b in boxes if id(b) not in taken and numbers & set(b["numbers"])]
        if not candidates:
            if not any(numbers & set(d["numbers"]) for d in deleted):
                out["place"].append(site)
            continue
        winner = next((b for b in candidates if b["touched"]), candidates[0])
        for b in candidates:
            taken.add(id(b))
            if b is not winner:
                out["left"].append((b, site))
        out["update"].append((winner, site))
    held = set()
    for site in [s for s in out["place"] if s["group"] in PERMIT_GROUPS]:
        here = [b for b in boxes if id(b) not in taken and _on(site, b["centre_m"])]
        if here:
            heir = next((b for b in here if b["touched"]), here[0])
            taken.add(id(heir))
            out["place"].remove(site)
            out["update"].append((heir, site))
            continue
        gone = [d for d in deleted if _on(site, d["centre_m"])]
        if gone:
            out["place"].remove(site)
            held.update(id(d) for d in gone)
    for b in boxes:
        if id(b) in taken:
            continue
        if b["closed"] or _far(b["centre_m"], radius_m):
            out["keep"].append(b)
        elif b["touched"]:
            out["close"].append(b)
        else:
            out["remove"].append(b)
    live = {n for site in sites for n in site["numbers"]}
    for d in deleted:
        if live & set(d["numbers"]) or id(d) in held or _far(d["centre_m"], radius_m):
            out["deleted"].append(d)
    return out


def _plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def _word(group):
    return GROUP_LABELS[group] if group == "coa" else GROUP_LABELS[group].lower()


def summary(sites, outcome, date):
    """The build report's line about the boxes (design §6.3)."""
    head = f"Development applications (City of Toronto, {date})" if date else "Development applications (City of Toronto)"
    if not sites:
        text = f"{head}: none around the site."
    else:
        apps = sum(1 for s in sites for a in s["applications"] if a["source"] == "application")
        permits = sum(1 for s in sites for a in s["applications"] if a["source"] == "permit")
        sources = " and ".join(part for part in (
            _plural(apps, "application", "applications") if apps else "",
            _plural(permits, "building permit", "building permits") if permits else "") if part)
        counts = ", ".join(f"{n} {_word(g)}" for g in APPLICATION_GROUPS
                           for n in [sum(1 for s in sites if s["group"] == g)] if n)
        text = f"{head}: {_plural(len(sites), 'site', 'sites')} from {sources}: {counts}."
    kept = sum(1 for box, _ in outcome["update"] if box["touched"])
    if kept:
        text += f" {_plural(kept, 'box', 'boxes')} kept at the size you gave {'it' if kept == 1 else 'them'}."
    if outcome["remove"]:
        text += f" {_plural(len(outcome['remove']), 'closed box', 'closed boxes')} removed."
    if outcome["close"]:
        text += f" {len(outcome['close'])} turned grey (Closed)."
    return text
