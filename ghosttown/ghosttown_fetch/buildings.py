"""Buildings as vertical prisms. Milestone 1: OpenStreetMap outlines and parts."""
import re

import shapely
from shapely.geometry import Point

from . import context as ctx
from .geom import feature_geometry, polygons, rings, to_local

LEVEL_M = 3.2      # storey height when only building:levels is known
GUESS_M = 9.0      # height when OpenStreetMap says nothing
SINK_M = 0.3       # bases sit this far below the lowest ground under the footprint
MIN_SOLID_M = 0.5  # thinner solids are dropped

_FEET_INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*'\s*(?:(\d+(?:\.\d+)?)\s*\")?")
_PLAIN = re.compile(r"(\d+(?:\.\d+)?)\s*(m|metres|meters|ft|feet)?")


def parse_length(text):
    """'12', '12 m', '12,5', "40'", '40 ft', '12\\'6"' -> metres; None when unreadable."""
    if text is None:
        return None
    s = str(text).strip().lower().replace(",", ".")
    m = _FEET_INCHES.fullmatch(s)
    if m:
        return float(m.group(1)) * 0.3048 + float(m.group(2) or 0) * 0.0254
    m = _PLAIN.fullmatch(s)
    if not m:
        return None
    value = float(m.group(1))
    return value * 0.3048 if m.group(2) in ("ft", "feet") else value


def _count(text):
    try:
        value = float(str(text).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def osm_height(tags):
    height = parse_length(tags.get("height"))
    if height:
        return height, "osm_height"
    levels = _count(tags.get("building:levels"))
    if levels:
        return levels * LEVEL_M, "osm_levels"
    return GUESS_M, "guessed"


def _min_height(tags):
    height = parse_length(tags.get("min_height"))
    if height is not None:
        return height
    levels = _count(tags.get("building:min_level"))
    return levels * LEVEL_M if levels else 0.0


def _wanted(tags, key):
    value = tags.get(key)
    if value is None or value == "no":
        return False
    raised = "min_height" in tags or "building:min_level" in tags
    return not (value == "roof" and not raised)  # a bare roof would become a solid block to the ground


def _name(tags):
    if tags.get("name"):
        return tags["name"]
    number, street = tags.get("addr:housenumber"), tags.get("addr:street")
    return f"{number} {street}" if number and street else ""


def from_osm(features, frame, terrain):
    outlines, parts = [], []
    for f in features:
        if _wanted(f.tags, "building"):
            target = outlines
        elif _wanted(f.tags, "building:part"):
            target = parts
        else:
            continue
        local = polygons(to_local(f.geom, frame))
        if local:
            target.append((f, local))

    owned = [[] for _ in outlines]
    orphans = []
    tree = shapely.STRtree([shapely.union_all(local) for _, local in outlines]) if outlines else None
    for f, local in parts:
        probe = shapely.union_all(local).point_on_surface()
        hits = list(tree.query(probe, predicate="within")) if tree is not None else []
        if hits:
            smallest = min(hits, key=lambda i: sum(p.area for p in outlines[i][1]))
            owned[smallest].append((f, local))
        else:
            orphans.append((f, local))

    elements = []
    for i, (f, local) in enumerate(outlines):
        el = _element(f, owned[i] or [(f, local)], terrain)
        if el:
            elements.append(el)
    for f, local in orphans:
        el = _element(f, [(f, local)], terrain)
        if el:
            elements.append(el)
    return elements


def _element(feature, pieces, terrain):
    solids = []
    for f, local in pieces:
        height, source = osm_height(f.tags)
        base = _min_height(f.tags)
        kind = "building_guessed" if source == "guessed" else "building"
        for poly in local:
            r = rings(poly)
            if r is None:
                continue
            ground = terrain.min_under(poly)
            z0 = ground + base if base > 0 else ground - SINK_M
            z1 = ground + height
            if z1 - z0 >= MIN_SOLID_M:
                solids.append(ctx.solid(kind, r, z0, z1, source))
    if not solids:
        return None
    kind = "building_guessed" if all(s["kind"] == "building_guessed" for s in solids) else "building"
    return ctx.element(feature.id, kind, name=_name(feature.tags), solids=solids)


SLIVER_M = 0.5          # what's left of a cut-back outline and thinner than 1 m is a digitising gap
CONTAINER_COVER = 0.8   # an outline covered this much by smaller ones is a whole-building outline
TOUCH_M = 0.05          # pieces this close share a boundary
MIN_SHARED_M = 0.5      # ...if they share at least this much of it


def _neighbour_height(part, neighbours):
    """Height of the resolved piece sharing the longest boundary with `part` (ties: the lower one)."""
    if not neighbours:
        return None
    grown = part.buffer(TOUCH_M)
    best = None
    for piece, height, _ in neighbours:
        if height is None or not piece.intersects(grown):
            continue
        shared = part.boundary.intersection(piece.buffer(TOUCH_M)).length
        if shared >= MIN_SHARED_M and (best is None or (round(shared, 2), -height) > best[0]):
            best = ((round(shared, 2), -height), height)
    return None if best is None else best[1]


def _cut_back(poly, smaller):
    """(rest, parts): `poly` without what the smaller outlines cover, and its pieces at least 1 m thick.

    The pieces come from opening `rest` (shrink, then grow back). GEOS can return an invalid polygon
    from that, so it is repaired, and the overlay falls back to a 1 mm grid, which always nodes."""
    rest = poly.difference(shapely.union_all(smaller))
    opened = shapely.buffer(shapely.buffer(rest, -SLIVER_M, join_style="mitre"), SLIVER_M, join_style="mitre")
    if not opened.is_valid:
        opened = shapely.make_valid(opened)
    try:
        kept = opened.intersection(rest)
    except shapely.errors.GEOSException:
        kept = shapely.intersection(opened, rest, grid_size=0.001)
    return rest, [part for part in polygons(kept) if part.area >= 4 * SLIVER_M * SLIVER_M]


def _resolve_overlaps(items):
    """[(Polygon, height | None, payload)] -> [(Polygon, height | None, inferred, payload)], no overlaps.

    The City draws a whole-building outline at the building's tallest height *and* every roof level
    inside it (sometimes under another BUILDINGID, sometimes twice). Smaller outlines win: each
    outline keeps only what no smaller one covers. What is left of an outline that was mostly
    covered is a digitising gap between roof levels, not a tower, so it takes the height of the
    roof level it shares the most boundary with (`inferred`), never more than its own."""
    geoms = [item[0] for item in items]
    if not geoms:
        return []
    tree = shapely.STRtree(geoms)
    order = sorted(range(len(geoms)), key=lambda i: (geoms[i].area, i))
    rank = {i: r for r, i in enumerate(order)}
    pieces = {}
    for i in order:
        poly, height, _ = items[i]
        smaller = [j for j in tree.query(poly, predicate="intersects")
                   if rank[j] < rank[i] and not poly.touches(geoms[j])]
        if not smaller:
            pieces[i] = [(poly, height, False)]
            continue
        try:
            rest, parts = _cut_back(poly, [geoms[j] for j in smaller])
        except shapely.errors.GEOSException:
            pieces[i] = [(poly, height, False)]  # one stubborn outline must not fail the build: keep it uncut
            continue
        container = rest.area <= (1.0 - CONTAINER_COVER) * poly.area
        neighbours = [piece for j in smaller for piece in pieces[j]] if container else []
        resolved = []
        for part in parts:
            near = _neighbour_height(part, neighbours)
            if near is not None and (height is None or near < height):
                resolved.append((part, near, True))
            else:
                resolved.append((part, height, False))
        pieces[i] = resolved
    return [(part, height, inferred, items[i][2]) for i in range(len(items)) for part, height, inferred in pieces[i]]


def from_toronto(features, frame, terrain, radius_m=None):
    """City building outlines grouped by BUILDINGID, overlaps resolved; every tier stands on the lowest
    ground under its whole building. With `radius_m`, only buildings touching the site circle are built
    (whole), while every outline given still takes part in resolving the overlaps."""
    items, footprints = [], {}
    for feature in features:
        props = feature.get("properties") or {}
        if props.get("SUBTYPE_DESC", "Building Outline") != "Building Outline":
            continue
        geom = feature_geometry(feature)
        if geom is None:
            continue
        bid = props.get("BUILDINGID")
        key = str(int(bid)) if isinstance(bid, (int, float)) else f"obj{props.get('OBJECTID')}"
        height = _count(props.get("DERIVED_HEIGHT"))
        if height is not None and height < MIN_SOLID_M:
            height = None
        for poly in polygons(to_local(geom, frame)):
            items.append((poly, height, key))
            footprints.setdefault(key, []).append(poly)

    wanted = set(footprints)
    if radius_m is not None:
        site = Point(0.0, 0.0).buffer(radius_m, quad_segs=64)
        wanted = {key for key, polys in footprints.items() if any(poly.intersects(site) for poly in polys)}

    groups = {}
    for poly, height, inferred, key in _resolve_overlaps(items):
        if key in wanted:
            groups.setdefault(key, []).append((poly, height, inferred))

    elements = []
    for key, tiers in groups.items():
        ground = terrain.min_under(shapely.union_all(footprints[key]))
        solids = []
        for poly, height, inferred in tiers:
            if height is None:
                kind, source, height = "building_guessed", "guessed", GUESS_M
            else:
                kind, source = "building", ("toronto_inferred" if inferred else "toronto_derived")
            r = rings(poly)
            if r is not None:
                solids.append(ctx.solid(kind, r, ground - SINK_M, ground + height, source))
        if solids:
            kind = "building_guessed" if all(s["kind"] == "building_guessed" for s in solids) else "building"
            elements.append(ctx.element(f"toronto:building:{key}", kind, solids=solids))
    return elements
