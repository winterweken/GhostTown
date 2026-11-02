# Realistic ground: a presentable look for built context, cut out as a round earth drum

Status: design agreed in conversation, 2026-11-01; awaiting the user's approval of this document. Implementation
plan to follow in `design/realistic-ground-plan.md`. Builds on Ghost Town 0.6.0 (dev at `e7e976b`, plus the City
shadow-study colours for Green, Water and Parcel (site) in `ghosttown/materials.py`, uncommitted at the time of
writing).

## 1. Summary

The Site panel's **Ground** switch gets a third choice, **Realistic**, next to Colours and Photo. It gives the
picked site's ground surfaces (open ground, grass, roads, sidewalks, parking, rail and water) procedural,
textured materials, and cuts the site out as a **round drum**: the ground on top and layered earth showing around
its edge, down to a flat base. Switching back to Colours or Photo puts the site back exactly as it was.

It is a ready-made preset, so anyone who builds context can make a presentable render (the diorama look of the
reference image the user shared: textured grass and soil, glossy water, the site lifted out of the world on a
block of earth) without setting up materials themselves.

## 2. Decisions (the user's, 2026-11-01)

1. **Realistic is a second option.** The plain look (colours by kind, with the City of Toronto shadow-study
   colours) stays the default after a build. Realistic is chosen per site.
2. **Earth and ground matter most.** Of everything in the reference image, the textured ground and the earth
   showing on the cut sides are what the preset must get right.
3. **The site stays round.** The cut-out follows Ghost Town's round site, a drum, not the reference's square
   block.
4. **How the textures are made is Claude's call** (decided in §5: procedural shader nodes, nothing downloaded).
5. **Buildings that cross the edge are trimmed at it** while Realistic shows, like a model-maker's diorama, and
   come back whole when switching away (decided after the builder check, §6.1).
6. Agreed in the playback: it lives in the Ground switch; roads, sidewalks, parking, rail and water come along as
   part of the ground; buildings, Street Look and trees are left alone; exported material names don't change.

## 3. Goals, non-goals, anti-goals

**Goals**

- One click on a built site gives a render-ready ground: no texture hunting, node wiring or UV work.
- Reads as real at the scale people look at a site: the whole 300–1000 m drum from an oblique camera, down to a
  street-level view of one block without obvious repetition.
- Fully reversible and per site, like the Photo choice.

**Non-goals**

- Building and tree materials (Street Look covers buildings; trees stay as built; only their trim at the edge,
  §6.1, changes), lane markings or curbs (no data for them), a
  square cut-out, scene lighting or render settings (Add Sky already exists; Realistic changes materials and adds
  the earth and trims what crosses the edge, nothing else in the scene).
- Being the default, or a fetch option. Nothing is fetched; it works on any already-built site, with or without
  an aerial photo.

**Anti-goals** (would count as a failure even if it works)

- Changing the `Context - <Kind>` materials or their colours. Exporters and Revit read those names and colours;
  they must be byte-for-byte what Colours shows. (An export taken *while Realistic shows* carries the Realistic
  materials and the earth, as one taken while Photo shows carries the photo today; switch to Colours before
  exporting for Revit. Claude's call: the panel says so under the Ground row while Realistic is on.)
- Visible tiling or a repeating stamp pattern across the site.
- Growing the extension download with texture images.
- Leaving anything behind: switching away, removing the site or rebuilding must not strand the earth object or
  slot overrides.

## 4. The switch

- The Ground row in the Site panel shows whenever a site is picked, not only when it has a photo: **Colours ·
  Photo · Realistic**, with Photo only present when the site has its aerial photo. Today the row sits in the
  Aerial photo box; it moves to its own place above that box so it shows without a photo. The Solid-mode hint
  that explains Material Preview stays with it.
- `ghosttown.use_ground`'s `use` enum gains `"realistic"`; its poll needs a picked site in Object Mode (no longer a
  photo), and `"photo"` without a photo is refused with a report.
- `site_use.apply_ground(root, use)` handles the three values. The site's choice stays in `root["use_ground"]`,
  as now.
- After a build nothing changes from today: a site with its aerial photo shows Photo (`site_photo.attach` sets
  it), one without shows Colours. A site without a photo has no `root["use_ground"]` today; treat a missing
  value as Colours (Claude's call). Switching between any two choices works in every order.

## 5. Materials

**How they are made (Claude's call).** Every Realistic material is built from Blender shader nodes: noise,
Voronoi and musgrave-style layering driven by world-space position in metres, colour ramps for variation, and
bump for surface relief. No image textures, no downloads, nothing added to the zip. World-space coordinates mean
no UVs are needed, the scale is real (a 2 m patch is 2 m on every site) and nothing tiles. Photo-scanned textures
would look more real up close but cost tens of MB and need anti-tiling work; procedural wins for a preset viewed
mostly at site scale.

**Where they go.** Like the photo, Realistic sets each ground object's first material slot to link to the
**object** and puts the Realistic material there; the mesh keeps its `Context - <Kind>` material underneath.
Switching to Colours sets the slot back to the mesh's data; to Photo, the photo material. This is the existing
`apply_ground` pattern with a third material source.

**One shared set per file**, named `Ghost Town Realistic · <Surface>`, made the first time any site needs it and
reused by every site. A material that already exists is used as it is, so a user's tweaks survive (the rule
`materials.application_material` already follows).

**Viewport colour.** Each Realistic material's `diffuse_color` is a sensible average of its look, so Solid mode
with material colour still reads; Material Preview and Rendered show the real thing, as the existing hint explains.

| Ground kind | Realistic surface | Look (targets; exact values are the builder's) |
|---|---|---|
| ground | Open ground | Mown grass with patchy bare soil and dry, yellowed areas, mixed at 2–20 m scales |
| green | Grass | Lusher, darker, more even grass than open ground, with clover-scale and lawn-stripe-scale variation |
| road | Asphalt | Dark grey, fine aggregate grain, faint wear and patching |
| sidewalk | Concrete | Light warm grey concrete with fine grain and staining; no slab joints (no direction data) |
| parking | Lot asphalt | Like road, a little lighter and more faded, with oil-stain patches |
| rail | Ballast | Grey-brown crushed stone, coarse grain and strong bump |
| water | Water | Deep teal, glossy (roughness about 0.05), fine ripples as bump at 0.5–3 m |
| (new) earth | Earth | See §6 |

Water follows the terrain mesh today (this test site's lake surface spans about 2 m of height). Flattening it is
out of scope; the ripples' bump should be strong enough that the small undulation reads as waves.

## 6. The earth drum

**Shape.** A ring wall around the site's outer edge plus a flat bottom cap, open on top where the ground pieces close it. The top edge of the
wall follows the terrain along the site's circle, so it meets the ground pieces with no gap; the bottom is flat at
`(lowest point of the rim) − 15 m` (Claude's call on depth: deep enough to read as a block from an oblique
camera, shallow enough not to dwarf low-rise context). Vertices about every 1 m around the circle.

**Where the top edge comes from.** The ground pieces (all `GROUND_KINDS` objects of the site) already end on the
site's circle. The wall's top height at each angle is taken from those objects' boundary vertices nearest the
circle at that angle, interpolated. The builder may instead raycast down onto the ground objects; either is fine
as long as the seam test in §8 passes.

**Object.** One mesh object, `Earth · <site>`, `ctx_kind = "earth"`, in the site's collection, recorded in the
root's `ctx_objects` so `scene_build.remove` deletes it. It exists only while the site shows Realistic: made when
Realistic is chosen, deleted when switching to Colours or Photo. It is not in `site_use.SITE_KINDS`, so the
triangle count for Revit ignores it. Its one material is `Ghost Town Realistic · Earth`.

**Earth material.** Layered by height below the rim, in world space: a thin dark topsoil band with root texture
just under the grass line, a thicker brown subsoil, then paler clay with scattered stones toward the base. Band
edges are warped by noise so they are not ruled lines, and stones are Voronoi cells with bump. The bottom cap is
the deepest layer's colour.

### 6.1 Trimming what crosses the edge

Ghost Town keeps every building that touches the site circle and builds it whole (outlines are fetched up to
`WHOLE_MARGIN_M`, 250 m, beyond it), so some stick out past the drum; on the HTO Park test site five do, one by
171 m. While Realistic shows they are cut off flat at the drum's wall.

- **How:** one cutter object per site, `Earth cutter · <site>`: a closed cylinder at the site's radius, from below
  the drum's base to well above the tallest building, hidden in viewport and render, recorded in `ctx_objects`.
  Each made object that reaches past the circle gets a Boolean modifier, `Ghost Town edge trim`, set to Intersect
  with that cutter. The cut is capped, so a trimmed building shows a solid flat face on the drum's edge.
- **What gets it:** the site's buildings (every `BUILDING_KINDS` object with a vertex beyond the radius, for each
  of the meshes a building keeps), the merged Tree object, and Street Look's facade detail objects when they cross.
  Development application boxes are the user's to move and are left alone. Ground pieces already end at the circle.
- **Undo:** switching to Colours or Photo removes every `Ghost Town edge trim` modifier and deletes the cutter, so
  meshes are untouched throughout; nothing is applied.
- **Revit count:** `site_use.count_triangles` ignores the trim (counts as if the modifier were off), so the
  figure in the panel is the Colours figure whatever the switch shows.
- **Solver:** the builder picks it; City massing meshes are not always manifold, so the test site's buildings
  must trim without holes or vanished buildings (§8).

## 7. Lifecycle

- **Remove site:** `scene_build.remove` already calls `apply_ground(root, "colours")` before deleting a site with
  a photo; it does so for a Realistic site too, which deletes the earth object and the cutter, removes the trim
  modifiers and resets the slots.
- **Rebuild:** a rebuild replaces the site and shows what a fresh build shows (§4). (Keeping Realistic across a rebuild is a
  possible follow-up, not part of this.)
- **Duplicates the user made** of ground objects share meshes, not object slots: they keep whatever their own
  object slots say, as with Photo today.
- **Save and reload:** materials, slot links and the earth object are ordinary data; nothing depends on Python
  state.
- **Shared materials** stay in the file after the last Realistic site is switched off (zero users, purged on save
  like any orphan); they are not deleted explicitly.

## 8. Testing

Headless Blender tests (`tests/blender/`, runner `tests/blender/run.py`), on a built fixture site:

- Realistic: every ground object's first slot links to the object with its kind's Realistic material; the mesh's
  data material is still `Context - <Kind>` and the `Context - <Kind>` colours are unchanged.
- Colours ↔ Photo ↔ Realistic in every order end in the right slots, and only one earth object ever exists.
- The earth object: closed except along its top ring, which the ground pieces cover (a top cap across uneven
  terrain would poke through them); its top edge is within 0.05 m of the ground pieces' outer edge height
  at sampled angles (the seam test); its bottom is flat at the rim's lowest point minus 15 m.
- Switching away and removing the site leave no earth object and no object-linked slots.
- Trim: every building and tree object reaching past the radius has exactly one `Ghost Town edge trim` modifier
  aimed at the site's cutter, none inside the circle does, the evaluated meshes have no vertex beyond the radius
  (plus a small tolerance) and none comes out empty; switching away leaves no modifier and no cutter, and the
  Revit triangle count is the same in Colours and Realistic.
- Realistic works on a site with no photo; Photo is refused on one.
- Existing Realistic materials are reused, not replaced or duplicated, across two sites.
- Save, reload, and the site still shows Realistic.

Then a visual check in the user's open Blender: the HTO Park test site in Realistic from an oblique camera and at
street level, with Material Preview and an EEVEE render.

## 9. What is left to the builder

- Node graphs and every colour, scale and bump value, within the targets in §5 and §6.
- How the rim height is sampled (§6), and the panel layout details within §4.
- Node layout and frame labels in the material editor (keep them tidy: users will open these to tweak).

## 10. Rulings (Claude's calls, for the user to overrule)

1. Procedural shader nodes, no image textures (§5).
2. Drum depth 15 m below the rim's lowest point (§6).
3. The earth object exists only while Realistic is shown, and isn't counted in the Revit triangle total (§6).
4. Realistic changes materials, adds the earth and trims what crosses the edge, nothing else: no lighting, world
   or render settings (§3).
5. A fresh build or rebuild shows what it shows today: Photo with a photo, else Colours (§4, §7).
6. Water isn't flattened (§5).
7. Exports taken while Realistic shows carry its materials and the earth; the panel tells users to switch to
   Colours before exporting for Revit (§3).
8. Trimming uses a Boolean modifier against a hidden cylinder, never applied; application boxes aren't trimmed,
   and the Revit count ignores the trim (§6.1).
