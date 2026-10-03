"""Buildings as vertical prisms. Milestone 1: OpenStreetMap outlines and parts."""
import re

import shapely

from . import context as ctx
from .geom import polygons, rings, to_local

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
