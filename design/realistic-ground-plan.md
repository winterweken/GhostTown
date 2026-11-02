# Realistic ground Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Site panel's Ground switch gets a third choice, **Realistic**: procedural textured materials on the
site's ground pieces, the site cut out as a round drum of layered earth, and everything that crosses the edge
trimmed flat at it, all undone by switching back.

**Architecture:** Add-on only (`ghosttown/`, bpy); the fetcher is untouched. `realistic.py` builds the shared
`Ghost Town Realistic · <Surface>` node materials. `site_realistic.py` makes and removes a site's earth drum,
its cutter and the edge-trim modifiers. `site_use.apply_ground` gains `"realistic"` and calls both, using the
object-linked material slot pattern Photo already uses. The operator, the panel row and `scene_build.remove`
follow.

**Tech Stack:** Python 3.13, numpy 2.3, Blender 5.2 (`bpy`, shader nodes, Boolean modifier), headless tests
through `tests/blender/run.py`.

**Spec:** `design/realistic-ground.md` (approved 2026-11-01). Read it first; section numbers below (§n) refer
to it.

## Global Constraints

- Blender 5.2 or later. No new dependencies; no image textures and no files added to the package.
- New modules never use `bpy.ops` (as `scene_build.py` and `site_*.py` don't).
- The `Context - <Kind>` materials, their colours and `materials.COLOURS` are never changed by anything here.
- Ground choices: `"colours"`, `"photo"`, `"realistic"`, stored in `root["use_ground"]`; a missing value means
  Colours. A fresh build still sets `"photo"` on a site with a photo and leaves the key unset otherwise.
- Names, exactly: materials `Ghost Town Realistic · Open ground`, `· Grass`, `· Asphalt`, `· Concrete`,
  `· Lot asphalt`, `· Ballast`, `· Water`, `· Earth`; objects `Earth · <site>` (`ctx_kind = "earth"`) and
  `Earth cutter · <site>` (`ctx_kind = "earth_cutter"`), where `<site>` is the same suffix the site's other objects
  use; modifier `Ghost Town edge trim`.
- Ground kind → surface: ground → Open ground, green → Grass, road → Asphalt, sidewalk → Concrete,
  parking → Lot asphalt, rail → Ballast, water → Water.
- Drum: wall vertices about every 1 m around the site circle (`n = max(64, ceil(2πr / 1.0))`), top edge within
  0.05 m of the ground pieces' outer edge, flat base at the rim's lowest point − 15 m (`EARTH_DEPTH_M = 15.0`).
- Trimmed kinds: `BUILDING_KINDS + ("tree", "facade_detail")`; development application boxes are never trimmed.
- Panel copy while Realistic shows: `Switch to Colours before exporting for Revit.`
- Work on branch `feat/realistic-ground` off `dev`. The working tree already holds uncommitted edits that are not
  this plan's (version bumps, and the City shadow-study colours in `ghosttown/materials.py`): **stage only the
  files a task names**, never `git add -A`. Commit messages end
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Run Blender tests with
  `/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py -- -k <substring>`;
  a pass ends `N passed, 0 failed`.

## Review Focus

1. **A site whose ground pieces don't reach all the way round the rim** (an older build, or a user deleted a
   piece): the wall interpolates across the gap; with no ground pieces at all, the drum is flat at
   `root["ground_at_centre_m"]`. Never an error. Tests in Task 2.
2. **The user deleted the earth, the cutter or a ground object by hand, then switches:** no error; switching to
   Realistic again makes a fresh drum and cutter, switching away cleans up what's left. Test in Task 4.
3. **A building's roof shape is switched (flat, fitted, LiDAR) while Realistic shows:** the trim follows the new
   mesh because the modifier is on the object, and a building whose *other* roof mesh crosses the edge is trimmed
   too. Test in Task 3.
4. **Two sites in one scene:** Realistic on one leaves the other's slots, objects and modifiers alone; each has
   its own drum and cutter, and both share one set of materials. Test in Task 4.
5. **A restyled Realistic material:** the user changed `Ghost Town Realistic · Grass`; a second site or a second
   switch reuses it untouched. Test in Task 1.

---

### Task 1: The Realistic materials

**Files:**
- Create: `ghosttown/realistic.py`
- Modify: `tests/blender/helpers.py` (add `drum_doc`)
- Test: `tests/blender/test_realistic.py`

**Interfaces:**
- Produces: `realistic.SURFACES: dict[str, str]` (ground kind → surface label, per Global Constraints);
  `realistic.EARTH = "Earth"`; `realistic.PREFIX = "Ghost Town Realistic · "`;
  `realistic.get_material(surface: str) -> bpy.types.Material` (surface is a `SURFACES` value or `EARTH`).
- Produces: `helpers.drum_doc(radius=150.0, slope=0.02, photo_folder=None) -> dict`, a context doc built from
  `mini_context.json` with `radius_m = radius`, the road replaced by three ground pieces that tile the whole circle
  on the plane `z = slope · x`, each a fan of 1° segments from the centre to the rim: `ground` from 0° to 240°,
  `green` from 240° to 300°, `water` from 300° to 360°; the mini buildings, one extra building `osm:way:9` with ring `[[r−10, −5], [r+30, −5], [r+30, 5],
  [r−10, 5]]`, `z0 = −0.3`, `z1 = 20.0`, and the mini tree plus one tree straddling the rim at `x ≈ r`. With
  `photo_folder`, it also gets `photo_doc`'s photo block and file (refactor `photo_doc` to share that part).

- [ ] **Step 1: Create the branch**

Run: `git switch -c feat/realistic-ground dev` (carries the uncommitted working tree; see Global Constraints).

- [ ] **Step 2: Write the failing tests** in `tests/blender/test_realistic.py`

```python
from ghosttown import realistic

ALL = list(dict.fromkeys(realistic.SURFACES.values())) + [realistic.EARTH]

def test_every_surface_has_a_named_procedural_material():
    for surface in ALL:
        mat = realistic.get_material(surface)
        assert mat.name == "Ghost Town Realistic · " + surface
        nodes = mat.node_tree.nodes
        assert not any(n.bl_idname == "ShaderNodeTexImage" for n in nodes)
        out = next(n for n in nodes if n.bl_idname == "ShaderNodeOutputMaterial")
        assert out.inputs["Surface"].is_linked
        assert any(n.bl_idname == "ShaderNodeNewGeometry" for n in nodes)   # world-space position drives it

def test_surfaces_cover_the_seven_ground_kinds():
    assert realistic.SURFACES == {"ground": "Open ground", "green": "Grass", "road": "Asphalt",
                                  "sidewalk": "Concrete", "parking": "Lot asphalt", "rail": "Ballast",
                                  "water": "Water"}

def test_an_existing_material_is_reused_as_the_user_left_it():
    mat = realistic.get_material("Grass")
    mat.diffuse_color = (1.0, 0.0, 1.0, 1.0)
    assert realistic.get_material("Grass") is mat and tuple(mat.diffuse_color) == (1.0, 0.0, 1.0, 1.0)
    assert sum(m.name.startswith("Ghost Town Realistic · Grass") for m in bpy.data.materials) == 1

def test_water_is_glossy_and_viewport_colours_are_not_the_plain_ones():
    water = realistic.get_material("Water")
    bsdf = next(n for n in water.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    assert bsdf.inputs["Roughness"].default_value <= 0.1
    for surface in ALL:
        assert tuple(realistic.get_material(surface).diffuse_color)[3] == 1.0
```

- [ ] **Step 3: Run them to see them fail**

Run the Blender tests with `-k test_realistic`. Expected: FAIL (`No module named ghosttown.realistic`).

- [ ] **Step 4: Implement `ghosttown/realistic.py`**

`get_material(surface)` returns `bpy.data.materials[PREFIX + surface]` when it exists, else builds it: one
Principled BSDF fed by a node graph per surface, all driven by `ShaderNodeNewGeometry.Position` (metres), to the
§5 table's looks and §6's earth bands. The earth's bands follow depth below the rim, read from the mesh's float
point attribute `gt_depth` (metres below the rim at that angle; Task 2 writes it) with a `ShaderNodeAttribute` of
type GEOMETRY.
Set `diffuse_color` to the look's average colour, alpha 1. Lay nodes out in labelled frames ("Pattern",
"Colour", "Bump"). Module docstring in the style of `materials.py`.

- [ ] **Step 5: Add `drum_doc` to `tests/blender/helpers.py`**, then run `-k test_realistic` again.

Expected: `4 passed, 0 failed`.

- [ ] **Step 6: Commit**

```bash
git add ghosttown/realistic.py tests/blender/test_realistic.py tests/blender/helpers.py
git commit -m "feat(realistic): procedural Realistic ground and earth materials"
```

### Task 2: The earth drum

**Files:**
- Create: `ghosttown/site_realistic.py`
- Test: `tests/blender/test_site_realistic.py`

**Interfaces:**
- Consumes: `realistic.get_material`, `realistic.EARTH`; `site_use.made_objects`, `GROUND_KINDS`.
- Produces: `site_realistic.EARTH_DEPTH_M = 15.0`;
  `site_realistic.rim_heights(root, angles: np.ndarray) -> np.ndarray` (terrain height at each angle on the
  circle); `site_realistic.make_earth(root) -> bpy.types.Object` (replaces any earth the site already has, links
  it in `root`, adds its name to `root["ctx_objects"]`, writes the `gt_depth` point attribute);
  `site_realistic.remove_earth(root) -> None`; `site_realistic.find(root, kind: str) -> Object | None` (the site's
  own `earth` or `earth_cutter`, looked up by `ctx_kind` among `made_objects`).

- [ ] **Step 1: Write the failing tests**

```python
def drum_site(**kw):
    folder = tempfile.mkdtemp()
    return scene_build.build(bpy.context.scene, drum_doc(**kw), folder=folder)

def test_the_drum_is_closed_and_meets_the_ground_at_the_rim():
    root = drum_site()
    earth = site_realistic.make_earth(root)
    verts, faces = mesh_arrays(earth)
    assert open_only_at_the_top(verts, faces)                    # wall + base; the ground pieces cover the top
    r = root["radius_m"]
    for a in np.linspace(0, 2 * np.pi, 37)[:-1]:
        near = [z for x, y, z in verts
                if abs((math.atan2(y, x) - a + math.pi) % (2 * math.pi) - math.pi) < 0.004]
        top = max(near)
        assert abs(top - 0.02 * r * math.cos(a)) < 0.05          # the plane z = 0.02 x at the rim

def test_the_base_is_flat_fifteen_metres_below_the_lowest_rim_point():
    root = drum_site()
    verts, _ = mesh_arrays(site_realistic.make_earth(root))
    bottom = min(z for *_, z in verts)
    assert abs(bottom - (-0.02 * root["radius_m"] - 15.0)) < 0.05
    assert max(z for *_, z in verts if z < bottom + 1.0) - bottom < 1e-4          # the base ring is flat

def test_one_earth_per_site_recorded_for_removal():
    root = drum_site()
    site_realistic.make_earth(root); earth = site_realistic.make_earth(root)
    assert [o for o in root.all_objects if o.get("ctx_kind") == "earth"] == [earth]
    assert earth.name in json.loads(root["ctx_objects"]) and earth.material_slots[0].material.name.endswith("Earth")
    site_realistic.remove_earth(root)
    assert site_realistic.find(root, "earth") is None and earth.name not in json.loads(root["ctx_objects"])

def test_a_gap_in_the_ground_is_bridged_and_no_ground_is_flat():
    root = drum_site()
    bpy.data.objects.remove(next(o for o in root.all_objects if o.get("ctx_kind") == "green"))
    assert open_only_at_the_top(*mesh_arrays(site_realistic.make_earth(root)))
    for ob in [o for o in root.all_objects if o.get("ctx_kind") in GROUND_KINDS]:
        bpy.data.objects.remove(ob)
    verts, _ = mesh_arrays(site_realistic.make_earth(root))
    assert abs(max(z for *_, z in verts) - root["ground_at_centre_m"]) < 1e-4
```

`open_only_at_the_top(verts, faces)` is a new helper in `tests/blender/helpers.py`: every edge is shared by two
faces except one closed loop of boundary edges, and that loop is the mesh's highest vertex ring (each of its
vertices is the top of its wall column).

- [ ] **Step 2: Run them to see them fail** (`-k test_site_realistic`). Expected: FAIL (no module).

- [ ] **Step 3: Implement `rim_heights`, `make_earth`, `remove_earth`, `find` in `ghosttown/site_realistic.py`**

`rim_heights`: gather boundary vertices (edges used by one face) of the site's `GROUND_KINDS` objects in world
space, keep those within 0.5 m of the radius, sort by angle and `np.interp(angles, a, z, period=2π)`; none left →
`root["ground_at_centre_m"]` everywhere. `make_earth`: a ring of `n` top vertices at `rim_heights`, `n` bottom vertices at `min − EARTH_DEPTH_M`, quads
between them and one n-gon cap at the bottom, normals outward; build it with `from_pydata`, no `bpy.ops`. The top
stays open: a top cap across uneven terrain would poke up through the ground pieces, which already close it.
Write `gt_depth` (top ring 0, bottom ring `rim − base`).

- [ ] **Step 4: Run them** (`-k test_site_realistic`). Expected: `4 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add ghosttown/site_realistic.py tests/blender/test_site_realistic.py tests/blender/helpers.py
git commit -m "feat(realistic): the earth drum under a site"
```

### Task 3: Trimming at the edge

**Files:**
- Modify: `ghosttown/site_realistic.py`, `ghosttown/site_use.py` (`count_triangles`)
- Test: `tests/blender/test_site_realistic.py`

**Interfaces:**
- Consumes: Task 2's `find`, `rim_heights`; `site_use.meshes_of`, `BUILDING_KINDS`.
- Produces: `site_realistic.TRIM = "Ghost Town edge trim"`; `site_realistic.TRIM_KINDS`;
  `site_realistic.add_trim(root) -> int` (number of objects trimmed; makes the cutter if missing);
  `site_realistic.remove_trim(root) -> None` (removes every `TRIM` modifier on the site's objects and the cutter).

- [ ] **Step 1: Write the failing tests**

```python
def test_only_what_crosses_the_edge_is_trimmed_to_the_circle():
    root = drum_site(); r = root["radius_m"]
    assert site_realistic.add_trim(root) == 2                     # osm:way:9 and the merged trees
    cutter = site_realistic.find(root, "earth_cutter")
    assert cutter.hide_viewport and cutter.hide_render
    dg = bpy.context.evaluated_depsgraph_get()
    for ob in root.all_objects:
        mods = [m for m in ob.modifiers if m.name == site_realistic.TRIM]
        crosses = ob.get("ctx_id") == "osm:way:9" or ob.get("ctx_kind") == "tree"
        assert len(mods) == (1 if crosses else 0)
        if mods:
            assert mods[0].object == cutter and mods[0].operation == "INTERSECT"
            me = ob.evaluated_get(dg).data
            assert len(me.vertices) > 0
            assert max(math.hypot(*(ob.matrix_world @ v.co).xy) for v in me.vertices) < r + 0.05

def test_switching_roof_shape_keeps_the_trim():
    root = drum_site(); site_realistic.add_trim(root)
    ob = next(o for o in root.all_objects if o.get("ctx_id") == "osm:way:9")
    ob.data = ob.data.copy()                                      # stands in for a roof-shape swap
    me = ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    assert max(math.hypot(*(ob.matrix_world @ v.co).xy) for v in me.vertices) < root["radius_m"] + 0.05

def test_a_building_whose_other_roof_mesh_crosses_is_trimmed():
    root = drum_site()
    ob = next(o for o in root.all_objects if o.get("ctx_id") == "osm:way:1")
    far = bpy.data.meshes.new("far"); far.from_pydata([(0, 0, 0), (400, 0, 0), (0, 1, 1)], [], [(0, 1, 2)])
    ob[site_use.LIDAR_KEY] = far
    site_realistic.add_trim(root)
    assert any(m.name == site_realistic.TRIM for m in ob.modifiers)

def test_removing_the_trim_leaves_nothing_and_the_revit_count_ignores_it():
    root = drum_site(); dg = bpy.context.evaluated_depsgraph_get()
    before = site_use.count_triangles(root, dg)
    site_realistic.make_earth(root); site_realistic.add_trim(root)
    assert site_use.count_triangles(root, bpy.context.evaluated_depsgraph_get()) == before
    site_realistic.remove_trim(root)
    assert site_realistic.find(root, "earth_cutter") is None
    assert not any(m.name == site_realistic.TRIM for o in root.all_objects for m in o.modifiers)
```

- [ ] **Step 2: Run them to see them fail** (`-k test_site_realistic`). Expected: the 4 new tests FAIL.

- [ ] **Step 3: Implement `add_trim` / `remove_trim`**

Cutter: a closed `n`-sided cylinder (same `n` and angles as the earth wall) from `min(rim) − EARTH_DEPTH_M − 1`
to `max(object top) + 10`, `hide_viewport = hide_render = True`, recorded in `ctx_objects`. An object of
`TRIM_KINDS` is trimmed when any vertex of any mesh in `meshes_of(ob)` is beyond `radius + 0.01` in world XY;
its modifier is added last (after `Ghost Town roof detail`), `operation="INTERSECT"`, `solver="EXACT"`,
`use_hole_tolerant=True`. Never applied. `add_trim` is idempotent (an object never gets two).

- [ ] **Step 4: Make `site_use.count_triangles` ignore the trim**

Turn every `site_realistic.TRIM` modifier's `show_viewport` off, `bpy.context.view_layer.update()`, evaluate
with a fresh `bpy.context.evaluated_depsgraph_get()` (the passed one is stale after the toggle), count, then
restore each modifier's previous `show_viewport` and update again. Keep the existing docstring's warning.

- [ ] **Step 5: Run the file and the existing LiDAR/roof tests**

Run `-k test_site_realistic`, then `-k test_site_lidar` and `-k test_roof_shapes`. Expected: all `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add ghosttown/site_realistic.py ghosttown/site_use.py tests/blender/test_site_realistic.py
git commit -m "feat(realistic): trim what crosses the site's edge"
```

### Task 4: The Realistic choice: `apply_ground`, the operator, the panel and removal

**Files:**
- Modify: `ghosttown/site_use.py` (`apply_ground`), `ghosttown/ops.py` (`GHOSTTOWN_OT_use_ground`),
  `ghosttown/ui.py` (Site panel), `ghosttown/scene_build.py` (`remove`)
- Test: `tests/blender/test_site_realistic.py`, `tests/blender/test_site_photo.py` (one new test)

**Interfaces:**
- Consumes: `realistic.SURFACES`, `realistic.get_material`; `site_realistic.make_earth`, `remove_earth`,
  `add_trim`, `remove_trim`, `find`.
- Produces: `site_use.apply_ground(root, use)` with `use in ("colours", "photo", "realistic")`;
  `site_use.ground_choice(root) -> str` (`root.get("use_ground") or "colours"`);
  `ui.EXPORT_HINT = "Switch to Colours before exporting for Revit."`.

- [ ] **Step 1: Write the failing tests**

```python
def slots(root):
    return {o["ctx_kind"]: (o.material_slots[0].link, o.material_slots[0].material.name, o.data.materials[0].name)
            for o in site_use.made_objects(root, GROUND_KINDS)}

def test_realistic_puts_each_surface_on_the_object_and_keeps_the_context_material():
    root = drum_site()
    site_use.apply_ground(root, "realistic")
    for kind, (link, shown, data) in slots(root).items():
        assert link == "OBJECT" and shown == "Ghost Town Realistic · " + realistic.SURFACES[kind]
        assert data == materials.material_name(kind)
    assert root["use_ground"] == "realistic" and site_realistic.find(root, "earth") is not None

def test_every_switching_order_ends_clean():
    folder = tempfile.mkdtemp()
    root = scene_build.build(bpy.context.scene, drum_doc(photo_folder=folder), folder=folder)
    for path in itertools.permutations(("colours", "photo", "realistic")):
        for use in path + path[:1]:
            site_use.apply_ground(root, use)
        last = path[0]
        assert sum(o.get("ctx_kind") == "earth" for o in root.all_objects) == (last == "realistic")
        assert any(m.name == site_realistic.TRIM for o in root.all_objects for m in o.modifiers) == (last == "realistic")
        links = {link for link, *_ in slots(root).values()}
        assert links == ({"DATA"} if last == "colours" else {"OBJECT"})

def test_hand_deleted_pieces_never_break_a_switch():
    root = drum_site(); site_use.apply_ground(root, "realistic")
    bpy.data.objects.remove(site_realistic.find(root, "earth"))
    bpy.data.objects.remove(site_realistic.find(root, "earth_cutter"))
    site_use.apply_ground(root, "colours"); site_use.apply_ground(root, "realistic")
    assert site_realistic.find(root, "earth") and site_realistic.find(root, "earth_cutter")

def test_two_sites_keep_their_own_choice_and_share_materials():
    a, b = drum_site(), drum_site()
    site_use.apply_ground(a, "realistic")
    assert {link for link, *_ in slots(b).values()} == {"DATA"} and site_realistic.find(b, "earth") is None
    site_use.apply_ground(b, "realistic")
    assert sum(m.name == "Ghost Town Realistic · Grass" for m in bpy.data.materials) == 1

def test_removing_a_realistic_site_leaves_nothing_behind():
    root = drum_site(); site_use.apply_ground(root, "realistic")
    scene_build.remove(root, bpy.context.scene)
    assert not any(o.get("ctx_kind") in ("earth", "earth_cutter") for o in bpy.data.objects)
    assert not any(m.name == site_realistic.TRIM for o in bpy.data.objects for m in o.modifiers)

def test_realistic_survives_save_and_reload():
    root = drum_site(); site_use.apply_ground(root, "realistic")
    path = os.path.join(tempfile.mkdtemp(), "r.blend"); name = root.name
    bpy.ops.wm.save_as_mainfile(filepath=path); bpy.ops.wm.open_mainfile(filepath=path)
    root = bpy.data.collections[name]
    assert root["use_ground"] == "realistic" and site_realistic.find(root, "earth") is not None

def test_the_operator_refuses_photo_without_a_photo_and_allows_realistic():
    root = drum_site(); bpy.context.scene.ghosttown.site = root
    assert bpy.ops.ghosttown.use_ground(use="photo") == {"CANCELLED"}
    assert bpy.ops.ghosttown.use_ground(use="realistic") == {"FINISHED"}
```

In `test_site_photo.py`, add `test_a_photo_site_still_opens_on_photo_and_can_go_realistic` (built photo site:
`use_ground == "photo"`; `apply_ground(root, "realistic")` then `"photo"` puts the photo material back on the road
slot). Tests may use `bpy.ops.wm.*` and `bpy.ops.ghosttown.*`; the add-on code may not.

- [ ] **Step 2: Run them to see them fail** (`-k test_site_realistic`, `-k test_site_photo`). Expected: new tests
FAIL (`apply_ground` ignores `"realistic"`; operator poll needs a photo).

- [ ] **Step 3: Extend `site_use.apply_ground`**

`"realistic"`: every ground object's first slot → `link = "OBJECT"`, material
`realistic.get_material(realistic.SURFACES[kind])`; then `site_realistic.make_earth(root)` and `add_trim(root)`.
Any other value: `remove_trim(root)` and `remove_earth(root)` first, then today's behaviour. Import
`site_realistic` and `realistic` inside the function (they import `site_use`). Update the docstring for three
values. Add `ground_choice`.

- [ ] **Step 4: Update `GHOSTTOWN_OT_use_ground`**

Enum gains `("realistic", "Realistic", "Textured ground on a cut-out drum of earth, for renders")`. Poll: a picked
site in Object Mode (`site_use.picked(context)` and `context.mode == "OBJECT"`). `execute`: `"photo"` on a site
without a photo → `self.report({"ERROR"}, "This site has no aerial photo.")`, `{"CANCELLED"}`. Description:
"Show colours by kind, the aerial photo, or Realistic ground on the picked site".

- [ ] **Step 5: Move the Ground row in `ui.py`**

Right after the survey box and before the Aerial photo box, a box with
`_choice(box, "Ground", "ghosttown.use_ground", site_use.ground_choice(root), options)`, where options are
Colours, Photo (only if `site_use.has_photo(root)`) and Realistic, then `SOLID_HINT`, then `EXPORT_HINT` with icon
`ERROR` when the choice is `"realistic"`. Remove the Ground row and its hint from the Aerial photo box (Roofs and
Save Site Photo stay there).

- [ ] **Step 6: `scene_build.remove`**

Call `site_use.apply_ground(root, "colours")` when the site has a photo **or** `ground_choice(root) ==
"realistic"`; keep `apply_roofs(root, "plain")` under the photo condition only.

- [ ] **Step 7: Run the whole Blender suite.** Expected: `0 failed` (261 before this plan, plus the new tests).

- [ ] **Step 8: Commit**

```bash
git add ghosttown/site_use.py ghosttown/ops.py ghosttown/ui.py ghosttown/scene_build.py \
        tests/blender/test_site_realistic.py tests/blender/test_site_photo.py tests/blender/helpers.py
git commit -m "feat(realistic): Realistic in the Ground switch"
```

### Task 5: Docs, and the check in the user's own Blender

**Files:**
- Modify: `README.md` (Site panel list near line 135, the export advice near line 203)

- [ ] **Step 1: README**

Replace `- **Ground: Colours | Photo** …` with a line for **Ground: Colours | Photo | Realistic**: Photo when the
site has its aerial photo; Realistic gives the ground textured materials, cuts the site out as a drum of earth and
trims what crosses the edge, for renders. In the export advice, add Realistic next to Photo (set Ground to Colours
before exporting).

- [ ] **Step 2: Full suites**

Run the whole Blender suite and `uv run pytest -q tests/fetch`. Expected: `0 failed` and all fetch tests passing.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: the Realistic ground choice"
```

- [ ] **Step 4: Visual check in the user's Blender** (ask the user first; their permission is per session)

Build a dev zip into the scratchpad (`Blender --factory-startup --command extension build --source-dir ghosttown
--output-dir <scratchpad> --split-platforms`; never `tools/build.sh`, which deletes `dist/`), install the
`macos_arm64` zip with `bpy.ops.extensions.package_install_files(..., repo="user_default", overwrite=True)`,
pick the HTO Park colour check site (43.6385, -79.3880, 300 m), switch Ground to Realistic, and leave the viewport
in Material Preview on an oblique camera named `Realistic` that shows the drum edge with the trimmed towers, plus
one street-level view. Screenshot both for the user.
