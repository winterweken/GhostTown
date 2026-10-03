"""Buildings as vertical prisms. Milestone 1: OpenStreetMap outlines and parts."""
import re

import shapely

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


SLIVER_M = 0.5  # what's left of a cut-back outline and thinner than 1 m is a digitising gap, not building


def _resolve_overlaps(items):
    """[(Polygon, payload)] -> the same without overlaps: where outlines overlap, the smaller one wins.

    The City draws a whole-building outline at the building's tallest height *and* every roof level
    inside it (sometimes under another BUILDINGID, sometimes twice). Painting the largest first and the
    smaller ones on top leaves each roof level at its own height and the big outline only where nothing
    else covers it."""
    geoms = [p for p, _ in items]
    if not geoms:
        return []
    tree = shapely.STRtree(geoms)
    rank = {i: r for r, i in enumerate(sorted(range(len(geoms)), key=lambda i: (geoms[i].area, i)))}
    out = []
    for i, (poly, payload) in enumerate(items):
        smaller = [geoms[j] for j in tree.query(poly, predicate="intersects")
                   if rank[j] < rank[i] and not poly.touches(geoms[j])]
        if not smaller:
            out.append((poly, payload))
            continue
        rest = poly.difference(shapely.union_all(smaller))
        rest = shapely.buffer(shapely.buffer(rest, -SLIVER_M, join_style="mitre"), SLIVER_M, join_style="mitre")
        out += [(part, payload) for part in polygons(rest)]
    return out


def from_toronto(features, frame, terrain):
    """City building outlines grouped by BUILDINGID, overlaps resolved; every tier stands on the lowest
    ground under its whole building."""
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
        for poly in polygons(to_local(geom, frame)):
            items.append((poly, (key, props)))
            footprints.setdefault(key, []).append(poly)

    groups = {}
    for poly, (key, props) in _resolve_overlaps(items):
        groups.setdefault(key, []).append((props, poly))

    elements = []
    for key, tiers in groups.items():
        ground = terrain.min_under(shapely.union_all(footprints[key]))
        solids = []
        for props, poly in tiers:
            height = _count(props.get("DERIVED_HEIGHT"))
            if height is None or height < MIN_SOLID_M:
                kind, source, height = "building_guessed", "guessed", GUESS_M
            else:
                kind, source = "building", "toronto_derived"
            r = rings(poly)
            if r is not None:
                solids.append(ctx.solid(kind, r, ground - SINK_M, ground + height, source))
        if solids:
            kind = "building_guessed" if all(s["kind"] == "building_guessed" for s in solids) else "building"
            elements.append(ctx.element(f"toronto:building:{key}", kind, solids=solids))
    return elements
