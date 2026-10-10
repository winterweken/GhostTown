# Development applications: what is proposed, going up or just finished around the site

Status: design approved in conversation, 2026-10-09, one section at a time; implementation plan to follow in
`design/development-applications-plan.md`. Builds on Ghost Town 0.4.0.

Ported from BHPlus's Build Context, where the same feature shipped on 2026-10-08 (BHPlus `main` at `60d801e`,
PRs #77 and #79). Its two specs are the parents of this one:
`docs/superpowers/specs/2026-10-08-site-applications-design.md` and
`docs/superpowers/specs/2026-10-08-site-construction-design.md` in the BHPlus repo. Everything this spec does
not change follows them, and their code at that commit is the reference for every table and parser named here.

## 1. Summary

A new fetch option, **Development applications** (Toronto only, off by default), puts a status-coloured,
see-through box on every site near the address that has a development application in, a building going up, or a
building finished since the City's 3D Massing release. Each box sits on the lot the application is filed on, is as
tall as the application or permit says, and carries the applications' numbers, statuses, descriptions and links.
A rebuild refreshes every box's status and keeps the boxes the user has reshaped.

It is an awareness aid for designing in context: which neighbours are changing, and how tall they will be. The
heights are the City's own words, read from free text, and the footprints are a starting guess.

## 2. Decisions (the user's, 2026-10-09)

1. **Bring BHPlus's development-applications feature into Ghost Town**, with the City data it uses.
2. **Approach A, port it whole:** applications, under construction and recently built, as one layer refreshed by
   Build Context. No separate refresh button (approach B) and no applications-only first step (approach C).
3. **The searched address's own application gets a box,** like any other. BHPlus leaves out a site mostly inside
   the user's drawn outline; Ghost Town has no outline, and a lookup of an address is often to see what is
   proposed there.
4. **An untouched box takes the new starting size on a rebuild** (★ in the design conversation). BHPlus keeps
   every matched box's size, so a box that started at 3.2 m ("height not stated") would stay 3.2 m after its
   permit says 21 storeys. A box the user changed always keeps the user's size and place.
5. **Sections 1 to 4 of the design** as written below: the data, the boxes, rebuilds, and the panel, notes and
   testing.

Left out of BHPlus's feature, because Blender does not need them: Make Editable (a Blender box is already an
editable mesh), the seed families and their types, pinning, Align, and hiding from the shadow study (Ghost Town
has none).

## 3. The City's data

As BHPlus verified on 2026-10-08 and re-checked here on 2026-10-09 (26,648 table rows; 15,683 map points). All
from hosts Ghost Town already uses (`gis.toronto.ca` and the City's CKAN portal), under the Open Government
Licence – Toronto credit Ghost Town already carries.

| Source | Where | Gives |
|---|---|---|
| Application points | `cot_geospatial11/FeatureServer/60` ("IBMS Application Information Centre"), WGS84 GeoJSON, 2,000 a page | one point per address per application, planning and Committee of Adjustment (MV, CO, TLAB); `APPLICATION_NUMBER`, `FOLDERTYPE`, `FOLDERRSN`, `STATUS_GROUP`, `STATUS_DESC`, `SUBMIT_DATE`, `FOLDERDESCRIPTION`, `FULL_ADDRESS`, `AIC_URL` |
| Applications table | CKAN `development-applications`, datastore resource `8907d8ed-c515-4ce9-b674-9f8c6eefcf0d`, daily | every planning application since 2008, including open ones the map does not show yet; X/Y in NAD27 MTM zone 10; `APPLICATION_URL` |
| Live building permits | CKAN `building-permits-active-permits`, resource `6d0229af-bc54-46de-9c2b-26759b01dd05` | new buildings in Inspection or Permit Issued |
| Completed building permits | CKAN `building-permits-cleared-permits`, resource `a96c0ba4-3026-402b-b09d-5b1268b8f810` | new buildings closed, with a completed date |
| Address points | `cot_geospatial27/FeatureServer/101` | where a permit's `GEO_ID` is |
| Parcels | `cot_geospatial27/FeatureServer/36`, as Ghost Town fetches today | the lot each point falls in |

No source has heights or footprints. Heights come from the descriptions; footprints from the parcels.

## 4. The fetcher

### 4.1 When it runs

Only when `"applications"` is in the request's layers and the site is in Toronto (`where == "toronto"`), after the
City layers and before the ground, as one extra like the aerial photo: it never counts towards `NothingFetched`,
and a failure is a warning that leaves the rest of the build as it is. Outside Toronto an info note says the
layer is Toronto only.

`LAYERS` gains `"applications"`, and `DEFAULT_LAYERS` leaves it out (as it leaves out `"lidar"`).

### 4.2 Fetch and cache

Ported from BHPlus `sources/city.py` (the `"application"` layer), `sources/ckan.py`, `sources/devapps.py` and
`sources/permits.py`, through Ghost Town's `Net` and `sources/arcgis.py`:

| Source | Query | Kept for |
|---|---|---|
| Application points | radius query on the circle | 1 day |
| Applications table | CKAN `datastore_search`, whole City, every row, fields without `DESCRIPTION` (about 3 MB) | 1 day |
| The table's descriptions | one `datastore_search` filtered to the `FOLDERRSN`s kept, with their `APPLICATION_URL` | 1 day |
| Live permits | `WORK` "New Building", `STATUS` Inspection or Permit Issued, `sort=ISSUED_DATE desc`, read to the cutoff | 1 day |
| Completed permits | `WORK` "New Building", `STATUS` Closed, `sort=COMPLETED_DATE desc`, read to the cutoff | 1 day |
| Address points | radius query on the circle | 7 days |
| Parcels | as the Parcels layer, fetched even when Parcels is unticked | as today (30 days) |

CKAN pages are cached by their URL and the day, so the pages of one read come from one day.

`Net.get` gains a `max_age_days` argument that overrides the cache's 30 days for one call, and `Cache.read` takes
the same. Each CKAN source stops after 50,000 rows, and every answer is checked for shape before it is used or
cached, as the City layers' are. The request's `fetch_fresh` bypasses these caches too.

The cutoffs, house filter, revision folding and the massing year are BHPlus construction spec §4.1 as written:
live permits issued within 6 years of today; completed permits completed on or after 1 January of the massing year
and issued no more than 10 years before completion; houses (`PERMIT_TYPE` "New Houses", or `STRUCTURE_TYPE`
starting "SFD", "2 Unit" or "3+ Unit") left out and counted. **The massing year** is the 3D Massing edition the
build used (`_city_buildings`' year); when the build used none, the newest edition in the City's listing
(`toronto_massing.newest_edition`); when that cannot be had either, last year.

**All or nothing:** the run counts as having looked at applications only when every source above answered, fresh
or from the cache. If any fails, `context.json` gets no `applications` block, and one warning names the source:
"Development applications weren't refreshed: the City's building permits couldn't be fetched (<reason>), so the
boxes were left as they are." A partial picture never removes or greys a box.

### 4.3 Sites, statuses and heights

Ported from BHPlus `applications.py`, `construction.py`, `boxfit.py` and `mtm.py`, with their tests:

1. **Status points.** Every map application, table-only application and kept permit becomes a point with a number,
   source, group, type, status, date, description, address, floor area and, for applications, a link. Table
   numbers lose their spaces (`26 126924 STE 10 SA` → `26126924STE10SA`) so a box keeps its identity when the
   City later maps the application. A permit's number is its `PERMIT_NUM`.
2. **Placing.** A map application at its point; a table-only application at its X/Y through BHPlus's fixed
   quadratic (median 0.17 m, worst 1.01 m); a permit at the address point whose `ADDRESS_POINT_ID` is its
   `GEO_ID`, else by street number and name. A point is kept when inside the circle and the City.
3. **Sites.** Each point joins the current COMMON parcel it falls in (the smallest, if several); a point in no
   parcel is left out and counted. Points sharing a parcel, and one number's several parcels, merge into one site,
   the union of its parcels.
4. **No subject-site rule** (decision 3). BHPlus's step "a site more than half inside the subject site outline is
   left out" is not ported.
5. **Status.** BHPlus's status tables, unchanged; a site's group is its highest member's, in the order
   `("construction", "built", "appealed", "review", "approved", "coa")`. Closed and refused applications are left
   out. An open label the tables do not know counts as Under review, with an info note naming it.
6. **The starting box.** The largest rectangle inside the site clipped to the circle, turned to the site's main
   direction (BHPlus `boxfit`, 1 m grid, at most 250,000 cells; the minimum rotated rectangle when the largest is
   under 2 m a side). Its base is the lowest ground under it less `buildings.SINK_M` (0.3 m).
7. **Height,** first that answers: for an Under construction or Recently built site, the newest permit's stated
   height, then the newest planning application's, then the permit's floor area over the box's area (at least 1,
   at most 120 storeys); for the rest, the newest open planning application's; else 3.2 m, "not stated". A
   C of A site starts at 3.2 m. Storeys are × `buildings.LEVEL_M` (3.2 m). The parser is BHPlus's, with its
   metres rules and its spelled-out ("forty-five"), bracketed ("SIX (6) STOREY") and "sty" forms.

### 4.4 In context.json

An optional top-level list, `"applications"`, written only when the run looked for applications and every source
answered (§4.2); it may be empty. Its absence tells the add-on to leave the boxes alone. The schema stays 1.

Each site is BHPlus's block, plus `"url"` on each application:

```json
{"id": "app:<smallest number>", "group": "construction|built|appealed|review|approved|coa",
 "numbers": ["..."], "main": "<number>", "centre_m": [x, y], "angle_deg": 0.0,
 "width_m": 0.0, "depth_m": 0.0, "height_m": 0.0, "base_m": 0.0, "height_from": "permit: 21 storeys",
 "applications": [{"number": "...", "source": "application|permit", "type": "...", "status": "...",
                   "submitted": "YYYY-MM-DD", "address": "...", "description": "...",
                   "floor_area_m2": 0.0, "url": "https://..."}]}
```

`url` is the map's `AIC_URL` or the table's `APPLICATION_URL`, kept only when it is an `http(s)` address on
`toronto.ca` or one of its subdomains, else `""`; permits have `""`. Applications are newest first. BHPlus's
`"comments"` string is not written: the panel shows the applications themselves (§6.2).

`context.py` validates the block both ways (what the fetcher writes and what the add-on reads), as BHPlus
`context_doc` does, with the new groups and keys. Beside the list, `"applications_date"` is the day of the run
(`YYYY-MM-DD`): the data is at most a day older, the caches' age. The City is credited as `toronto`.

## 5. The boxes in Blender

### 5.1 Objects

- **Collection:** `Applications · <site>`, inside `Context · <site>`, marked `ctx_apps = <site label>`. It is not
  one of the collections `scene_build.remove` deletes: `build` takes it out of the old site collection before
  removing that, and links it into the new one (§5.3).
- **One object per site,** named `<Status> · <address of the main application>`, for example
  `Under construction · 1 Yonge St`. Its origin is the box's base centre (`centre_m`, `base_m`), turned by
  `angle_deg` about z; its mesh is a closed box of 8 vertices, ±width/2, ±depth/2, 0 to height.
- **Material:** one per status, `Context - Application (<Status>)`, made the way `materials.py` makes the others,
  at 30 % transparency in Solid view (viewport colour alpha 0.7), Material Preview and EEVEE (blended surface).
  A material that already exists is used as it is, so the user's restyling stays. Colours, from BHPlus (its
  shadow-study palette):

  | Status | RGB |
  |---|---|
  | Under review | 255, 168, 106 |
  | Approved | 58, 192, 201 |
  | Appealed | 255, 57, 95 |
  | Under construction | 108, 130, 166 |
  | C of A | 212, 143, 249 |
  | Recently built | 150, 150, 150 |
  | Closed | 210, 210, 210 |

- **Custom properties:** `ctx_app_site` (the site label), `ctx_app_id`, `ctx_app_group`, `ctx_app_numbers`,
  `ctx_app_main`, `ctx_app_height_from`, `ctx_app_applications` (JSON), `ctx_app_made` (when Ghost Town first
  placed the box, ISO date and time, which decides "the older" in §5.3), and `ctx_app_placed`: the location,
  rotation, scale and 24 vertex coordinates Ghost Town last gave the box.
- **On the collection:** `ctx_app_boxes` (each box's numbers as the last build left them, which is how a deleted
  box is noticed) and `ctx_app_deleted` (the boxes the user deleted) each hold `{"numbers": [...], "centre_m": [x, y]}`
  per box (the centre is how a permit site on a deleted box's spot stays away), `ctx_app_date` is the applications'
  fetch date, for the panel, and `ctx_app_frame` (`{"centre": {lat, lon}, "ground": metres or null}`) is the frame
  the boxes were placed in.
- **Editing** is plain Blender: grab, rotate, scale, the Scale Cage tool's one-sided handles, and Edit Mode.
- **Not a building:** boxes carry no `ctx_kind` and no `ctx_id`, so Street Look, Roof shapes, LiDAR roofs and
  photo-on-roofs, which look for building kinds, pass them by. They export with the rest of the collection.

### 5.2 Changed by the user

A box is **touched** when its location differs from `ctx_app_placed` by more than 1 mm, its rotation by more than
0.05°, its scale by more than 0.0001, or its mesh has a different vertex count or any vertex more than 1 mm from
where Ghost Town put it. The add-on measures this; the decisions below take it as given.

### 5.3 On a rebuild

The decisions are a pure function, ported from BHPlus `boxes.plan` and kept standard-library only in
`ghosttown_fetch` (as `context.py` is), so plain pytest covers it. Its inputs: the new sites, the existing boxes
(numbers, touched, age), the deleted numbers and the circle. Its output: what to do with each box and site.

- **Found:** the boxes are the objects in the scene whose `ctx_app_site` is this site's label, wherever the user
  has moved them.
- **Matching:** a box matches a site when they share any number.
- **A matched box:** its status, material, name and properties refresh. If it is untouched, its mesh and
  transform become the new starting box (decision 4); if touched, the user's shape and place stay.
- **A new site:** a new box, in the Applications collection.
- **A box none of whose numbers is in a site:** removed if untouched; if touched, it stays and becomes
  **Closed** (grey), its applications kept.
- **A box the user deleted** (a box the last build placed that is no longer in the scene): stays deleted. The
  collection remembers it as its numbers and where it stood (`ctx_app_deleted` holds `{"numbers": [...],
  "centre_m": [x, y]}` entries, §5.1), and a site sharing any of those numbers is not made. **Bring back deleted
  boxes (N)** (§6.2, N the number of deleted boxes) clears the list, and the next build makes them again. If the
  user deletes the whole Applications collection, the memory goes with it and the next build starts afresh.
- **No `applications` block** (layer unticked, outside the City, a source failed): every box is left exactly as
  it is, carried into the new site collection, and the notes say why.
- **A box outside this build's circle** (a rebuild at a smaller radius): left as it is.
- **One site matching two boxes:** the touched one takes it, else the older; the other is left as it is and a
  note names it.
- **Undo:** all of it happens inside the build, which stays one undo step.

## 6. Panel and notes

### 6.1 Fetch

A third tick under Aerial photo and LiDAR roofs, **Development applications** (`fetch_applications`, off by
default), with the tooltip "Toronto: boxes on nearby sites with an open development application, under
construction or recently built (City applications and building permits; houses left out)".

### 6.2 Site panel

When the site has an Applications collection, an **Applications** box shows:

- one row per status present: an editable swatch, its label and the number of sites. The swatch is the material's
  viewport colour, and the material's Base Color follows it through drivers, so a change shows in Solid view,
  Material Preview and renders alike;
- the date of the data;
- **Bring back deleted boxes (N)** when N > 0.

When the active object is a box, it also shows its status and height source, then each application or permit:
number · type · status · date, its address, its description, and **Open in City AIC** (`wm.url_open`) when it has a
`toronto.ca` link. The link is checked again when the button is clicked. Each application's description is wrapped
to the panel's width, up to 8 lines (a ninth line shows as "…"); the title and address lines are wrapped to it too.

### 6.3 Notes

BHPlus's summary and notes, worded for Ghost Town's build report:

- "Development applications (City of Toronto, 2026-10-09): 9 sites from 10 applications and 2 building permits: 2
  under construction, 1 recently built, 3 under review, 2 approved, 1 C of A. 1 box kept at the size you gave it. 1
  closed box removed. 1 turned grey (Closed)."
- A source that failed (§4.2), as a warning.
- Outside Toronto, as info.
- Houses left out, applications placed from the table, permits that couldn't be placed, points inside no parcel,
  an unknown status label, and two boxes for one site, each only when it applies.
- A context whose development applications are older than the boxes' (its `applications_date` before the
  collection's `ctx_app_date`) leaves the boxes as they are, as info: "This context's development applications
  (2026-10-01) are older than the boxes' (2026-10-09), so the boxes were left as they are."
- A build with no `applications` block and no `applications` note, while the site has boxes, says as info:
  "Development applications weren't fetched this time (the tick was off), so the boxes were left as they are."

## 7. Testing

- **Fetcher, plain pytest (no network, `--disable-socket`):** BHPlus's tests and recorded fixtures for the
  status tables and precedence, site merging, every height phrasing, box fitting (L-shaped, thin, large), the X/Y
  conversion within 1 m in four parts of the City, CKAN paging (cutoffs, nulls sorted first, 50,000 rows, a
  malformed answer refused), the house filter, revision folding, permit placing (id, street fallback, unplaced),
  table numbers normalised and deduplicated, and all or nothing as each source fails in turn. New: the per-call
  cache age, no subject-site rule, `url` kept only on `toronto.ca`, and the `context.py` checks both ways.
- **The rebuild planner, plain pytest:** every rule in §5.3, decision 4 included.
- **Blender suite (`tests/blender`, headless):** boxes made with their materials and properties; a rebuild that
  renames, recolours, resizes an untouched box, keeps a touched one, removes or greys a closed one; deleted boxes
  stay deleted and come back after Bring back; boxes carried across a rebuild with no `applications` block, and
  found in a collection the user moved them to; one undo step; Street Look and the roof switches skip boxes.
- **Live, in the user's open Blender file:** King & Bay at 300 m (BHPlus's test site: 13 applications) and a site
  with a tower known to be under construction, each with a camera for the user to look through; then a box
  edited, the site rebuilt, and the edit seen kept.

## 8. Rollout

One branch, `feat/development-applications`, off `dev`, and one plan. The fetcher work comes first and is
complete and tested on its own (it changes nothing in Blender until the add-on reads the block), then the add-on.
The README gains a "What you get" bullet, a Use step and a Site panel paragraph; CREDITS already names the
Toronto licence. A release (0.5.0) is a separate step afterwards.

## 9. Port map

| BHPlus (`BH+.extension/lib/bh_context/`, `60d801e`) | Ghost Town |
|---|---|
| `sources/city.py` `"application"` layer | `ghosttown_fetch/sources/toronto.py`: `fetch_applications`, `fetch_address_points` |
| `sources/ckan.py` | `ghosttown_fetch/sources/ckan.py` |
| `sources/devapps.py` | `ghosttown_fetch/sources/toronto_applications.py` |
| `sources/permits.py` | `ghosttown_fetch/sources/toronto_permits.py` |
| `mtm.py` | `ghosttown_fetch/mtm27.py` |
| `boxfit.py` | `ghosttown_fetch/boxfit.py` |
| `applications.py`, `construction.py` | `ghosttown_fetch/applications.py`, `ghosttown_fetch/construction.py` |
| `assemble.py` applications attempt | `ghosttown_fetch/assemble.py` `_applications` |
| `context_doc.py` checks | `ghosttown_fetch/context.py` |
| `cache.py` per-source age | `ghosttown_fetch/cache.py`, `net.py` |
| `boxes.py` `plan`, `touched` rules | `ghosttown_fetch/app_boxes.py` (standard library only) |
| `applications_revit.py`, `record.py` | `ghosttown/site_apps.py` (bpy), `scene_build.py`, `materials.py` |
| dialog and summary | `ghosttown/props.py`, `ui.py`, `ops.py` |
| `editable*.py`, `families/`, shadow study | not ported |

## 10. Rulings (Claude's calls, for the user to overrule)

1. **Boxes keep `ctx_app_*` properties instead of `ctx_kind`/`ctx_id`,** so nothing that walks buildings or
   `ctx_objects` ever reaches them and `remove` cannot delete them.
2. **A box's name leads with its status,** so the Outliner sorts and scans by status. The name changes when the
   status does; the numbers are its identity.
3. **"Touched" compares the mesh as well as the transform,** so an Edit Mode change counts like a scale does.
4. **Only `toronto.ca` links are kept** for Open in City AIC, so the panel never opens an address that came from
   anywhere else.
5. **No legend object in the scene:** the colour swatches in the Site panel are the legend.
