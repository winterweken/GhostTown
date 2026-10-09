"""Development application boxes in Blender (design/development-applications.md §5): one see-through,
status-coloured box per site, in the site's `Applications · <site>` collection, refreshed by each build that looked
at the applications and left alone by one that didn't. ghosttown_fetch.app_boxes makes the decisions; this module
measures the boxes, carries the decisions out and remembers what it placed. Never uses bpy.ops.

List and dict properties are JSON text, as the site collection's ctx_objects is."""
import datetime
import json

import bpy

from . import materials
from .ghosttown_fetch import APPLICATION_GROUPS, app_boxes

COLL_PREFIX = "Applications · "
SITE_PROP = "ctx_apps"            # on the Applications collection: the site label its boxes belong to
BOX_SITE = "ctx_app_site"         # on each box: the same label
MAX_NAME = 63
LEFT = "{name} shares its applications with another box, which took the update; it was left as it is."
OLDER = ("This context's development applications ({doc_date}) are older than the boxes' ({coll_date}), so the "
         "boxes were left as they are.")
NOT_FETCHED = ("Development applications weren't fetched this time (the tick was off), so the boxes were left as "
               "they are.")


def _json(block, key, default):
    """A JSON property read back, or `default` when it is missing, unreadable or of another type."""
    try:
        value = json.loads(block.get(key, ""))
    except (TypeError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def _entry_ok(e):
    centre = e.get("centre_m") if isinstance(e, dict) else None
    return (isinstance(e, dict) and isinstance(e.get("numbers"), list) and bool(e["numbers"])
            and all(isinstance(n, str) for n in e["numbers"]) and isinstance(centre, list) and len(centre) == 2
            and all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in centre))


def find(scene, label):
    """The site's Applications collection in this scene, or None (also for a label that is not a non-empty
    string, which would match a collection that has no mark at all)."""
    if not isinstance(label, str) or not label:
        return None
    for coll in scene.collection.children_recursive:
        if coll.get(SITE_PROP) == label:
            return coll
    return None


def detach(scene, label):
    """Take the site's Applications collection out of the old site collection, and out of every other collection
    but the scene's own, so removing the old site collection leaves it alone; returns it, or None. It stays
    linked to the scene collection until apply() links it into the new site collection, so a build that stops
    in between leaves the boxes in the scene instead of in no collection at all."""
    coll = find(scene, label)
    if coll is None:
        return None
    for parent in list(scene.collection.children_recursive):
        if parent != coll and coll.name in parent.children:
            parent.children.unlink(coll)
    if coll.name not in scene.collection.children:
        scene.collection.children.link(coll)
    return coll


def boxes(scene, label):
    """The site's box objects in this scene, wherever the user moved them, oldest first ([] for a label that is
    not a non-empty string, which would match every object that has no mark at all)."""
    if not isinstance(label, str) or not label:
        return []
    found = [ob for ob in scene.objects if ob.get(BOX_SITE) == label]
    return sorted(found, key=lambda ob: (str(ob.get("ctx_app_made", "")), ob.name))


def numbers_of(ob):
    return [n for n in _json(ob, "ctx_app_numbers", []) if isinstance(n, str)]


def applications_of(ob):
    """A box's applications and permits, newest first ([] for anything else)."""
    if ob is None:
        return []
    return [a for a in _json(ob, "ctx_app_applications", []) if isinstance(a, dict)]


def _measure(ob):
    """What app_boxes.touched compares: the box's transform and mesh, and whether it is parented or turned some
    other way."""
    verts = [list(v.co) for v in ob.data.vertices] if ob.type == "MESH" else []
    return {"location": list(ob.location), "rotation": list(ob.rotation_euler), "scale": list(ob.scale),
            "verts": verts, "other": ob.parent is not None or ob.rotation_mode != "XYZ"}


def _centre(ob):
    """Where the box stands in plan: the middle of its vertices, else its origin. Worked out from the box's own
    transform and its parent's, not from matrix_world, which Blender does not refresh until the next depsgraph
    update and so still holds the place the box had before this build moved it."""
    basis = ob.matrix_basis
    if ob.parent is not None:
        basis = ob.parent.matrix_world @ ob.matrix_parent_inverse @ basis
    if ob.type == "MESH" and len(ob.data.vertices):
        pts = [basis @ v.co for v in ob.data.vertices]
    else:
        pts = [basis.translation]
    return [sum(p.x for p in pts) / len(pts), sum(p.y for p in pts) / len(pts)]


def _numbers(values, count):
    return (isinstance(values, list) and len(values) == count
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values))


def _placed(ob):
    """What Ghost Town recorded when it placed the box, or None when the record is missing or damaged (a vector
    that is not three numbers, a mesh that is not a list of points), which app_boxes.touched counts as changed."""
    placed = _json(ob, "ctx_app_placed", {})
    verts = placed.get("verts")
    if not all(_numbers(placed.get(key), 3) for key in ("location", "rotation", "scale")):
        return None
    if not isinstance(verts, list) or not all(_numbers(v, 3) for v in verts):
        return None
    return placed


def _deleted(coll, present):
    """The boxes the user deleted: the collection's memory of them, and each box the last build left that no box
    in the scene carries a number of now."""
    remembered = [e for e in _json(coll, "ctx_app_deleted", []) if _entry_ok(e)]
    here = {n for ob in present for n in numbers_of(ob)}
    lately = [e for e in _json(coll, "ctx_app_boxes", []) if _entry_ok(e) and not here & set(e["numbers"])]
    return remembered + lately


def _remember(coll, present, deleted):
    coll["ctx_app_boxes"] = json.dumps([{"numbers": numbers_of(ob), "centre_m": _centre(ob)} for ob in present])
    coll["ctx_app_deleted"] = json.dumps([{"numbers": list(d["numbers"]), "centre_m": list(d["centre_m"])}
                                          for d in deleted])


def deleted_count(scene, coll):
    """How many boxes of this site the user has deleted."""
    return len(_deleted(coll, boxes(scene, coll[SITE_PROP])))


def bring_back(scene, coll):
    """Forget the deleted boxes, so the next build makes them again; returns how many were forgotten."""
    present = boxes(scene, coll[SITE_PROP])
    n = len(_deleted(coll, present))
    _remember(coll, present, [])
    return n


def status_counts(scene, coll):
    """[(group, number of boxes)] for the statuses this site's boxes have, in the panel's order."""
    groups = [ob.get("ctx_app_group") for ob in boxes(scene, coll[SITE_PROP])]
    return [(g, groups.count(g)) for g in APPLICATION_GROUPS + (app_boxes.CLOSED,) if g in groups]


def _word(word):
    """One word of an address in street capitals: 33RD -> 33rd, MCCAUL -> McCaul, QUEEN'S -> Queen's (str.title
    would make them 33Rd, Mccaul and Queen'S)."""
    if word[:1].isdigit():
        return word.lower()
    if word[:2].upper() == "MC" and len(word) > 2:
        return "Mc" + word[2:3].upper() + word[3:].lower()
    return word[:1].upper() + word[1:].lower()


def _place_name(site):
    """The lead application's first address, in street capitals, else its number."""
    lead = next((a for a in site["applications"] if a["number"] == site["main"]), site["applications"][0])
    address = lead["address"].split("; ")[0].strip()
    return " ".join(_word(w) for w in address.split()) if address else lead["number"]


def _rename(ob):
    """Name a box `<Status> · <place>`, unless the user has renamed it."""
    if ob.get("ctx_app_name") not in (None, ob.name):
        return
    ob.name = f"{app_boxes.LABELS[ob['ctx_app_group']]} · {ob.get('ctx_app_place', '')}"[:MAX_NAME]
    ob["ctx_app_name"] = ob.name          # Blender may have added .001
    if ob.type == "MESH" and ob.data.users == 1:
        ob.data.name = ob.name             # exporters that name things by mesh see the same name


def _set_shape(ob, site):
    """Give the box its site's starting box (a new mesh, its place and turn, no scale) and record it as placed."""
    old = ob.data
    me = bpy.data.meshes.new(ob.name)
    me.from_pydata([tuple(v) for v in app_boxes.box_verts(site)], [], [tuple(f) for f in app_boxes.BOX_FACES])
    me.validate(clean_customdata=False)
    me.update()
    if isinstance(old, bpy.types.Mesh):
        for mat in old.materials:
            me.materials.append(mat)
    ob.data = me
    if isinstance(old, bpy.types.Mesh) and old.users == 0:
        bpy.data.meshes.remove(old)
    location, rotation = app_boxes.placement(site)
    ob.location = location
    ob.rotation_mode = "XYZ"
    ob.rotation_euler = rotation
    ob.scale = (1.0, 1.0, 1.0)
    ob["ctx_app_placed"] = json.dumps(_measure(ob))


def _set_status(ob, group):
    mat = materials.application_material(group)
    if ob.type == "MESH":
        if ob.data.materials:
            ob.data.materials[0] = mat
        else:
            ob.data.materials.append(mat)
    ob.color = tuple(mat.diffuse_color)
    ob["ctx_app_group"] = group
    _rename(ob)


def _set_info(ob, site):
    ob["ctx_app_id"] = site["id"]
    ob["ctx_app_numbers"] = json.dumps(site["numbers"])
    ob["ctx_app_main"] = site["main"]
    ob["ctx_app_place"] = _place_name(site)
    ob["ctx_app_height_from"] = site["height_from"]
    ob["ctx_app_applications"] = json.dumps(site["applications"])


def _update(ob, site, reshape):
    if reshape:
        _set_shape(ob, site)
    _set_info(ob, site)
    _set_status(ob, site["group"])


def _new_box(coll, site, label, made):
    ob = bpy.data.objects.new("Application", bpy.data.meshes.new("Application"))
    coll.objects.link(ob)
    ob[BOX_SITE] = label
    ob["ctx_app_made"] = made
    _update(ob, site, reshape=True)
    return ob


def _remove(ob):
    data = ob.data
    bpy.data.objects.remove(ob)
    if isinstance(data, bpy.types.Mesh) and data.users == 0:
        bpy.data.meshes.remove(data)


def _carry(scene, coll, label, doc):
    """Carry the boxes, and the collection's memory of them, from the frame they were placed in into this
    build's, when the site is built again around another centre or on other ground."""
    frame = {"centre": {"lat": doc["centre"]["lat"], "lon": doc["centre"]["lon"]},
             "ground": doc.get("ground_at_centre_m")}
    old = _json(coll, "ctx_app_frame", {})
    coll["ctx_app_frame"] = json.dumps(frame)
    try:
        dx, dy, dz = app_boxes.shift(old["centre"], old.get("ground"), frame["centre"], frame["ground"])
    except (KeyError, TypeError, ValueError):
        return                                      # no frame recorded yet: nothing to carry
    if max(abs(dx), abs(dy), abs(dz)) < 1e-6:
        return
    for ob in boxes(scene, label):
        if ob.parent is None:
            ob.location = (ob.location.x + dx, ob.location.y + dy, ob.location.z + dz)
        placed = _json(ob, "ctx_app_placed", {})
        if isinstance(placed.get("location"), list) and len(placed["location"]) == 3:
            x, y, z = placed["location"]
            placed["location"] = [x + dx, y + dy, z + dz]
            ob["ctx_app_placed"] = json.dumps(placed)
    for key in ("ctx_app_boxes", "ctx_app_deleted"):
        entries = [e for e in _json(coll, key, []) if _entry_ok(e)]
        for e in entries:
            e["centre_m"] = [e["centre_m"][0] + dx, e["centre_m"][1] + dy]
        coll[key] = json.dumps(entries)


def apply(scene, root, doc, coll):
    """Carry out a build's plan for the site's boxes, and link the Applications collection into the new site
    collection `root`. `coll` is what detach() took out of the old site collection, or None. Returns the lines to
    report as (level, text), level "INFO" or "WARNING": the summary first, then one for each box left as it is;
    [] when the build did not look at the applications. A failure after the collection is linked leaves the
    boxes as they are and comes back as a warning, so the rest of the build goes on."""
    label = root["ctx_label"]
    sites = doc.get("applications")
    if coll is None:
        if sites is None:
            return []
        coll = bpy.data.collections.new(COLL_PREFIX + label)
        coll[SITE_PROP] = label
    root.children.link(coll)
    if coll.name in scene.collection.children:
        scene.collection.children.unlink(coll)         # detach() kept it here until now
    try:
        sites, said = _to_act_on(scene, coll, label, doc)
        return _refresh(scene, coll, label, doc, sites) + said
    except Exception as e:                              # the boxes are the user's work: never stop the build
        return [("WARNING", f"The development application boxes couldn't be updated ({type(e).__name__}: "
                            f"{str(e)[:80]}); they were left as they are.")]


def _to_act_on(scene, coll, label, doc):
    """(sites, lines): the applications this build acts on, None when it leaves the boxes as they are, and the
    line that says so when the user would wonder why: a context older than the boxes, or none fetched."""
    sites = doc.get("applications")
    doc_date, coll_date = doc.get("applications_date"), coll.get("ctx_app_date")
    if sites is not None:
        if all(isinstance(d, str) and d for d in (doc_date, coll_date)) and doc_date < coll_date:
            return None, [("INFO", OLDER.format(doc_date=doc_date, coll_date=coll_date))]
        return sites, []
    noted = any(isinstance(n, dict) and n.get("code") == "applications" for n in doc.get("notes", []))
    if noted or not boxes(scene, label):
        return None, []
    return None, [("INFO", NOT_FETCHED)]


def _refresh(scene, coll, label, doc, sites):
    _carry(scene, coll, label, doc)
    present = boxes(scene, label)
    states = [{"object": ob, "numbers": numbers_of(ob), "centre_m": _centre(ob),
               "touched": app_boxes.touched(_placed(ob), _measure(ob)),
               "closed": ob.get("ctx_app_group") == app_boxes.CLOSED} for ob in present]
    outcome = app_boxes.plan(sites, states, _deleted(coll, present), doc["radius_m"])
    if not outcome["looked"]:
        _remember(coll, present, outcome["deleted"])
        return []
    left = [state["object"].name for state, _ in outcome["left"]]
    for state, site in outcome["update"]:
        _update(state["object"], site, reshape=not state["touched"])
    made = datetime.datetime.now().isoformat(timespec="seconds")
    for i, site in enumerate(outcome["place"]):
        _new_box(coll, site, label, f"{made}.{i:04d}")
    for state in outcome["close"]:
        _set_status(state["object"], app_boxes.CLOSED)
    for state in outcome["remove"]:
        _remove(state["object"])
    _remember(coll, boxes(scene, label), outcome["deleted"])
    coll["ctx_app_date"] = doc.get("applications_date", "")
    return [("INFO", app_boxes.summary(sites, outcome, doc.get("applications_date", "")))] + [
        ("INFO", LEFT.format(name=n)) for n in left]
