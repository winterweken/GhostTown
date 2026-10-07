# Street Look: building appearance from street photos

Status: design approved in conversation, 2026-10-07; implementation plan in `design/street-look-plan.md`.
Builds on Ghost Town 0.3.0 (City massing, aerial photos, LiDAR and fitted roofs, the Site panel).

## 1. Summary

Street Look gives every building in a Ghost Town context a believable facade in Blender renders, derived from
Mapillary street photos: up to four height zones (for example storefront base, podium, body, cap), each with a
colour and a kind (storefront, opaque, glass or cap), plus a floor height. A few buildings the user selects can also get simple
detail geometry (floor bands, mullions, a storefront band). It is a separate step after Build Context, off by
default, and needs the user's own Mapillary token.

The look is a procedural shader driven by per-building values. No photo is ever stored in the .blend file. The
approach tolerates the metre-level camera errors, clutter and gaps found in testing; it does not try to be exact.

## 2. Goals and non-goals

Goals

- Realistic context for presentation renders: most buildings near the address look like themselves; the rest get
  a sensible default.
- Work wherever Mapillary has photos and Ghost Town has buildings (Toronto massing or OpenStreetMap).
- Keep today's defaults intact: clean massing, stable material names, Revit and BIM export unchanged.
- Bounded and visible cost: a photo budget, progress, Cancel, and a cache.

Non-goals (version 1)

- Exact photo textures on walls. Projecting photos through their cameras was tried and rejected: Mapillary's
  computed positions are 1–4 m and a few degrees off in downtown Toronto, and none of the four automatic
  corrections tried (edge matching, point-cloud fitting, label fitting, per-drive offsets) was reliable without a
  person checking.
- Material classes (brick, concrete, stone, metal), measured window spacing, roof shapes. See section 12.

## 3. What the tests showed

Throwaway tests on 2026-10-06/07 at 351 King St E, 320 Bay St, 235 Queens Quay W, 2300 Yonge St and 300 Borough
Dr, with the user's token. The code is not kept; the numbers are.

| Finding | Evidence |
|---|---|
| Photos from blocks away are the useful ones | Share of the target's visible wall seen level and head-on: 0–23% using photos within 60 m, 38–73% within 500 m. Median distance of the sharpest view: 63–201 m. |
| Coverage depends on building type | At ≥ 5 px/m (2048 px images): 71% for a 17 m waterfront building, 57% for an 87 m tower, 16% for a 296 m downtown complex. Photos needed to reach 90% of what all photos give: 5–11, but 37 for the 296 m complex. |
| Mapillary's labels separate building from clutter | Labels were present for all 200 photos checked. They catch trees, vehicles, people, poles and fencing, and a high share of target points landing on sky flags a bad camera pose (91% at 300 Borough Dr). Bus shelters and awnings are labelled as building and slip through. |
| A per-pixel model mask is needed | Without it, lower neighbouring buildings standing in front of the target were sampled as the target. |
| Exposure must be calibrated relative to the site | Assuming a fixed road brightness failed (every photo hit the clamp). Bringing each photo's road to the site's median road brightness worked (gains 0.5–2×). |
| Height zones come out of a colour-by-height profile | 351 King St E: dark storefront 0–9 m, podium 9–36 m, light blue glass 36–84 m, dark cap above. |
| Glass changes colour with viewpoint; walls do not | Spread of chromaticity across ≥ 3 views per 6 m band: about 0.08 on the podium, 0.15–0.19 on the glass. Brightness spread about 0.3–0.6 against 0.8–1.1. |
| Floor height is measurable; window spacing is not yet | The 351 King St E tower showed 3.5 m floors in 7 m two-storey boxes. Bay-spacing estimates sat at the edge of the search range (noise). |

## 4. User experience

1. Build Context as today.
2. In the Ghost Town tab, a Street Look section under the Site panel shows the token status, the settings,
   and an **Apply Street Look** button; it acts on the site picked there. Optionally select a few building
   objects and tick **Detail for selected**.
3. Apply runs in the background with progress and Cancel, like Build. Afterwards the section shows, for example,
   "Look from photos: 41 buildings · guessed: 23 · 128 photos (2014–2025)" and the credit line
   "Street photos © Mapillary contributors, CC BY-SA 4.0".
4. **Show street look** and **Show detail** switch the result on and off. **Photo brightness** (default 1.15)
   scales the measured colours.
5. If the scene still uses Blender's default world, Apply offers to add a `Ghost Town Sky` world (sky texture
   plus sun) so glass has something to reflect. It never replaces a world the user made.

Settings: photo budget (default 150), "Not before" year (default off), Detail for selected (default off),
Keep street look on rebuild (default on).
Preferences: Mapillary token (masked field), with the `GHOSTTOWN_MAPILLARY_TOKEN` environment variable as a
fallback. Without a token, Apply is disabled and the section points to Preferences.

## 5. Architecture

The existing split holds: the fetcher process does all network and analysis work; the Blender side only draws.

```
Street Look panel ─▶ look_request.json ─▶ fetcher process ─▶ look.json ─▶ building properties, shared
                     (+ token in env)     (ghosttown_fetch look)          node group, detail objects
```

### 5.1 New and changed pieces

Fetcher (`ghosttown/ghosttown_fetch/`, plain Python, never imports bpy):

- `cli.py`: a `look <look_request.json>` command beside `fetch` and `geocode`, with the same one-line JSON answer,
  `error.txt` and `progress.jsonl` conventions.
- `sources/mapillary.py`: photo listing by tiles, image metadata, thumbnail download, label download. Requests
  run about 8 at a time.
- `mvt.py`: a small decoder for the Mapbox Vector Tile polygons in which Mapillary encodes its labels (about 100
  lines; avoids a protobuf dependency).
- `raycast.py`: 2.5D ray casting against building solids. Ghost Town buildings are vertical prisms, so a ray only
  needs testing against wall segments (candidates from a shapely STRtree) plus a height check at the hit.
  Downward rays onto roofs are not handled; street cameras rarely look down.
- `look.py`: the pipeline in section 6.
- `net.py`: per-call request headers (for the token) and a cache-key override (Mapillary's photo links are
  signed and change); 0.3.0's `keep=False` already covers answers that must not be stored. Cache keys never
  include the token.
- `__init__.py`: `mapillary` in `SOURCE_NAMES` and `CREDITS`.

New dependency: **Pillow**, for JPEG decoding and polygon filling, bundled as per-platform wheels exactly like
shapely (`tools/fetch_wheels.py` and `blender_manifest.toml` cover both). Licence HPND, compatible with GPL.

Blender side (`ghosttown/`):

- `prefs.py`: the token field.
- `props.py`: Street Look settings and the result summary.
- `ui.py`: the Street Look section.
- `ops.py`: `GHOSTTOWN_OT_street_look`, built on the same `_FetcherOperator` pattern as Build; one undo step.
  It acts on the Site panel's picked site, and only on the site's own buildings (`site_use.made_objects`),
  as the aerial photo on roofs does; the user's duplicates are left alone.
- `runner.py`: passes the token in the child environment only.
- `look_build.py` (new): applies `look.json` (section 7).
- `materials.py`: the `Ghost Town · Street Look` node group and its insertion into the building materials; a new
  stable material kind `facade_detail` (`Context - Facade detail`).
- `scene_build.py`: carries the look across a rebuild (section 7.4).

Alternatives considered: a headless `blender -b` worker (no new wheels, but Blender's start-up time and memory on
every run, tests need Blender, and a second kind of child process), and analysis inside the open Blender on a
timer (no new process, but a sluggish interface and against "Blender only draws").

### 5.2 look_request.json

```json
{
  "schema": 1, "tool": "ghosttown 0.3.0",
  "centre": {"lat": 43.651769, "lon": -79.365065}, "radius_m": 300.0, "ground_at_centre_m": 80.783,
  "buildings": [
    {"id": "toronto:massing:2025:361309", "detail": true,
     "solids": [{"rings": [[[-21.4, -62.0], [71.4, -60.3], [70.8, 22.0], [-20.9, 20.6]]], "z0": -1.2, "z1": 85.4}]}
  ],
  "budget_photos": 150, "not_before_year": null, "search_margin_m": 200.0,
  "fetch_fresh": false,
  "cache_dir": "/Users/me/Library/Application Support/Blender/5.2/extensions/.user/user_default/ghosttown/cache",
  "out_dir": "<cache_dir>/runs/look-20261007-101500"
}
```

- `buildings` lists what is in the scene now, so deleted buildings are skipped and edited prisms are respected.
  Blender rebuilds each building's solids from its mesh: each connected part is a tier, its bottom outline is
  the ring set, and its lowest and highest points are z0 and z1, matching the `context.json` solid format.
  A building that keeps 0.3.0 roof shapes is read from its flat mesh, the prism set the fetcher models,
  whichever roof shape it shows.
- Ground heights for cameras come from the fetcher's own terrain source and cache, fetched for the search area
  (site radius plus `search_margin_m`). Outside Canada the ground is flat, as in Build.
- The token is never in this file.

### 5.3 look.json

```json
{
  "schema": 1, "tool": "ghosttown 0.3.0",
  "photos_used": 128, "years": [2014, 2025],
  "buildings": {
    "toronto:massing:2025:361309": {
      "source": "photos", "photos": 9, "confidence": 0.8, "floor_h": 3.5,
      "zones": [
        {"h0": 0, "h1": 9, "kind": "storefront", "colour": [0.073, 0.048, 0.042]},
        {"h0": 9, "h1": 36, "kind": "opaque", "colour": [0.269, 0.218, 0.250]},
        {"h0": 36, "h1": 84, "kind": "glass", "colour": [0.273, 0.451, 0.550]},
        {"h0": 84, "h1": null, "kind": "cap", "colour": [0.157, 0.131, 0.146]}
      ],
      "detail_walls": [{"a": [-21.4, -62.0], "b": [71.4, -60.3], "n": [0.018, -1.0], "z0": 9.0, "z1": 84.0}]
    }
  },
  "sources": [{"key": "mapillary", "name": "Mapillary", "credit": "Street photos © Mapillary contributors, CC BY-SA 4.0"}],
  "notes": []
}
```

Colours are linear RGB, as measured after exposure calibration. Heights are metres above the building's lowest
point. `detail_walls` appears only for buildings with `detail: true` and lists the exposed wall spans and heights.
Buildings without a usable photo have `"source": "guessed"` and the default zones (section 6.8).

## 6. Selection and extraction

### 6.1 List photos

- All Mapillary images within the site radius plus 200 m (capped at 1,000 m), listed in 100 m tiles.
- Fields: id, captured_at, camera_type, computed_geometry, computed_rotation, camera_parameters, width, height,
  sequence.
- Photos missing computed geometry or rotation are skipped.
- Near-duplicates are thinned: the newest photo per 5 m cell and 30° of heading (360° photos: per cell).
  Mapillary shoots every few metres along a street; at 351 King St E this kept 5,937 of 9,048 photos for
  about 1% less wall area seen well.
- Recency weight: 2022 or later ×1.0, 2018–2021 ×0.8, earlier ×0.6. "Not before" excludes older years.
- Poses: the computed position, the computed rotation (OpenSfM convention: world east-north-up to camera with x
  right, y down, z forward), camera height from the terrain plus 2.0 m (Mapillary altitudes are unreliable).

### 6.2 Points on each building

A grid of about 3 × 4 m over each building's exposed wall area. A point is exposed unless a probe 0.3 m out from
the wall lies inside or under another solid.

### 6.3 Which photo sees which point

| Rule | Value |
|---|---|
| Distance from camera | 3–500 m |
| Head-on, in plan | within 35° of square to the wall |
| Camera level (perspective and fisheye) | pitch within ±12° |
| In frame | 2% margin; perspective points with r² < 1.2 (avoids extreme corners) |
| Line of sight | the first wall hit is the point's own building, within 1 m of the point |
| Sharpness | px/m = focal length in pixels ÷ distance × cos(angle), at 2048 px; usable from 5 px/m |

360° photos have every point in frame; their focal length in pixels is width ÷ 2π.

### 6.4 Choose photos for the whole site

- A greedy pick that shares photos between buildings, scoring each photo by wall area covered × sharpness (capped
  at 20 px/m) × recency.
- Up to 4 photos per building, until the budget is spent.
- Priority: detail buildings first, then by distance from the address. A building's only usable photo is never
  dropped for budget.
- Photos are read for at most as many buildings as the budget, in that order; the rest get the guessed look.
  More could not all get photos anyway, and it keeps a 1,000 m site about as quick as a small one. The photo
  search reaches 200 m past the farthest of those buildings, capped at 1,000 m.

### 6.5 Label check and masks

- One labels download per chosen photo, rasterised at 512 px width.
- A photo is dropped for a building if more than 30% of that building's points land on sky or ground (bad pose),
  or fewer than 30% land on building (blocked).
- Otherwise only pixels labelled `construction--structure--building` are used. Thin clutter (wires, poles, street
  lights, signs) is masked but not counted against the photo.
- Per-pixel model mask: a ray grid 200 px wide per photo; a pixel counts for a building only if its ray first
  hits that building.

### 6.6 Exposure calibration

Each photo's gain brings its median road luminance (pixels labelled `construction--flat--road`, linear) to the
site's median road luminance, clamped to 0.5–2×. Photos with fewer than 500 road pixels get gain 1.

### 6.7 Profile, zones, glass and floors

- Straighten each visible wall in each photo at about 6 px/m (sample the photo at points on the wall plane).
- Profile: calibrated linear colour per 3 m height band, the median per photo, then the median across photos.
- Zones: split the bands where the kind changes, or where luminance changes by more than 30% or chromaticity
  (r, g, b divided by their sum) moves by more than 0.05 between neighbouring bands; merge runs shorter than 6 m;
  keep at most 4 zones by merging the most similar neighbours. A storefront base is set at the first band
  boundary between 3 and 9 m above the lowest point where the band above is at least 1.6 times as bright as the
  band below; without such a jump there is no storefront zone.
- Glass or opaque: with ≥ 3 views of a 6 m band, glass if chromaticity spread > 0.12 and log-brightness spread
  > 0.7. With fewer views, glass if blue minus red > 0.04 × max(luminance ÷ 0.1, 1). Known blind spot: lower-floor
  glass that mirrors the same street from every angle reads as opaque.
- Floor height: dominant spacing of horizontal edges in the straightened walls, searched over 2.8–6 m, accepted
  only when at least 2 walls agree within 0.25 m; otherwise 3.5 m.
- Window and mullion spacing are not measured in version 1: 1.5 m on glass, 3.0 m on opaque walls.

### 6.8 Defaults and confidence

- No usable photo: storefront 0–4.5 m, linear (0.32, 0.32, 0.31); opaque body above, (0.42, 0.42, 0.40);
  `"source": "guessed"`. The panel counts these like today's "height guessed".
- Confidence (0–1) = min(1, photos used ÷ 3) × the share of the building's exposed wall area seen at 5 px/m or
  better.

## 7. Blender integration

### 7.1 The look in the existing materials

- A node group, `Ghost Town · Street Look`, is inserted into `Context - Building`, `Context - Building (on site)`
  and `Context - Building (height guessed)`, between the Principled BSDF and its Base Color and Roughness inputs.
  Inputs: the plain colour, Look on/off, Photo brightness.
- Per-building values are custom properties on each building object (zone tops, kinds, colours; floor height;
  bay widths; lowest point; source; confidence), read through Attribute nodes of type Object. One material renders
  every building differently, and switching between flat, fitted and LiDAR roofs keeps the look, since the
  values sit on the object and every roof shape uses the same building materials. Roof faces keep the plain
  colour (or 0.3.0's aerial photo on roofs, which takes them into its own material).
- Material names, kinds and the plain colour (the BSDF default value) stay as today, so FBX and OBJ export and
  the Revit Object Styles mapping are unchanged. A Blender test confirms this (section 11).
- Rejected: a separate `Context - Building (street look)` material, which would add a name to every export.

### 7.2 Detail geometry for selected buildings

- One mesh per selected building, `Detail · <building>`, in a `Detail · <site>` collection under the context.
- From the building's zones and `detail_walls`: floor bands on every floor (heavier at zone boundaries), mullion
  fins at the glass bay width on glass zones, a band at the top of the storefront. Only on exposed walls and
  heights. About 4,000 faces for the 87 m test tower.
- Material `Context - Facade detail`. The massing is untouched; untick (exclude) the collection to leave detail
  out of an export. Show detail only hides it from viewports and renders, which FBX export ignores. Detail
  counts toward the site's Revit triangle figure.
- At most 20 buildings per run; about 5 recommended.
- Rejected for version 1: a Geometry Nodes modifier (hard to build and maintain from Python; exporters apply
  visible modifiers by default).

### 7.3 Switches and sky

- Show street look sets the node group's Look input; Show detail hides or shows the detail collection.
- Photo brightness is the node group input, so the stored colours stay as measured.
- `Ghost Town Sky`: Sky Texture (multiple scattering, sun disc off) at strength about 0.25 plus a sun lamp,
  added only if the scene's world is Blender's default and the user accepts.

### 7.4 Rebuild and undo

- The look is stored on the context collection as JSON keyed by building id, with the panel's summary and
  credit line beside it, like 0.3.0's other per-site state. When Build replaces a site,
  `scene_build.build` copies it from the old collection before removing it, re-applies the properties to the new
  objects with matching ids, and regenerates detail for buildings still present.
- Detail objects carry `ctx_id` and are listed in the collection's `ctx_objects`, so `remove()` handles them like
  everything else Ghost Town makes.
- Apply is one undo step. With Keep street look on rebuild unticked, a rebuild drops the look and its detail.

## 8. Settings, privacy, licensing

- The token is stored in Blender's user preferences, never in a .blend file, and reaches the fetcher only through
  its environment. It is sent only as an `Authorization: OAuth` header, never in a URL.
- New servers, contacted only when Apply is pressed: `graph.mapillary.com` (listings, metadata, labels) and
  Mapillary's image servers on `fbcdn.net` (photos). They receive the site's tile boxes, photo ids and the token.
  The README's privacy paragraph and its list of servers are updated.
- Photos and labels are cached by image id (Mapillary's download links expire) for the usual 30 days.
- Only derived values reach the .blend file, so CC BY-SA share-alike does not extend to users' files; the credit
  still applies. It appears in the panel, in the `Context origin` credits property, in README's data table and in
  CREDITS.md.
- Open before release: check Mapillary's API terms on caching and rate limits.

## 9. Failure handling

Each message is one plain sentence, as elsewhere in Ghost Town.

| Situation | Behaviour |
|---|---|
| No token | Apply disabled; the section points to Preferences. |
| Token rejected (HTTP 401 or 403) | "Mapillary refused the token; check it in Preferences." Nothing applied. |
| No coverage, or no usable photos | Every building gets the guessed look; a note says so. |
| Some listing tiles fail (429, 5xx) | Retry with backoff, continue with the rest, note "Some areas couldn't be searched." |
| A photo or its labels fail | Skip it; take the next-best photo. |
| Cancel or Esc | As Build: the process stops and nothing is applied. |
| A damaged cached file | Fetched again through `Net`'s existing `check` mechanism. |
| A photo missing fields | Skipped. |

## 10. Performance

Measured with the plan's code at 351 King St E (300 m, 87 buildings, 9,048 photos listed), 2026-10-07:

- The first version took 16 minutes, 11 of them choosing photos: each ray of up to 500 m was tested against
  every wall its bounding box touched, with GEOS predicates. Rays now go out in 50 m pieces, nearest first,
  with the crossing test in numpy, and near-duplicate photos are thinned: choosing takes 30 s and reading
  the facades (including the 200 px per-pixel grid) 33 s.
- Re-run with listings and photos cached: 66 s. A first run adds the listing (about 90 tiles, 3 MB) and
  about 110 photos with their labels, roughly 1–2 minutes more.
- Listing a 500 m radius with 8 parallel requests: about 30 s (3.5 min sequential in testing).

Five sites with `tools/look_accuracy.py` on the finished code, 2026-10-07 (300 m radius, 150-photo budget, one pass
each), measured with the add-on's own buildings-plus-terrain fetch, so the buildings stand on the same ground as the
cameras. The cache already held the City's massing model and the Mapillary listings and photos from earlier passes over
the same sites, and each run wrote 1–11 MB of new Mapillary cache, so the totals are warm-cache totals; a first run at
a new site adds the downloads, as above. Choosing and reading are CPU work, and 320 Bay St, the densest site, is the
slow one: 167 s choosing photos, 239 s in all. The building at the address is the one with a footprint corner nearest
it; its zones are heights in metres above its lowest point, the last running to the roof.

| Site | Buildings | From photos | Photos | Building at the address | Choosing s | Reading s | Total s |
|---|---|---|---|---|---|---|---|
| 351 King St E | 87 | 78 | 113 | photos, 0.19: opaque 0–30 · opaque 30–42 · opaque 42–60 · opaque 60– | 37 | 46 | 86 |
| 320 Bay St | 56 | 55 | 134 | photos, 0.14: opaque 0–18 · glass 18–156 · opaque 156–186 · opaque 186– | 167 | 66 | 239 |
| 235 Queens Quay W | 29 | 24 | 47 | photos, 0.04: opaque 0–9 · opaque 9–15 · cap 15– | 29 | 22 | 55 |
| 2300 Yonge St | 204 | 61 | 90 | photos, 0.09: glass 0–36 · opaque 36–51 · opaque 51–126 · cap 126– | 9 | 36 | 50 |
| 300 Borough Dr | 13 | 9 | 16 | photos, 0.02: opaque 0–12 · opaque 12– | 3 | 7 | 12 |

Peak memory (maximum resident set size) over the five runs: 1,801 MB, at 320 Bay St.

## 11. Testing

- Fetcher, offline pytest as today (`--disable-socket`): unit tests for the MVT decoder, the 2.5D ray caster,
  the selection rules, exposure calibration, zone splitting, the glass test, floor-height estimation and the
  `look.json` schema, on synthetic data.
- One end-to-end fetcher test on a small recorded fixture: a few listing tiles, about 5 photos downscaled to
  512 px, and their labels. Credits go in `tests/fetch/fixtures/README.md`, since the photos are CC BY-SA.
  `tools/record_fixtures.py` learns to record it.
- Blender tests (`tests/blender/run.py`): applying a `look.json` fixture to the mini context; node group and
  properties present; both switches; detail objects generated; rebuild carries the look; FBX and OBJ export keep
  today's material names.
- `tools/smoke_live.py`: an optional Street Look run when `GHOSTTOWN_MAPILLARY_TOKEN` is set.
- An accuracy script (not in CI) that reruns the five-site coverage table to catch selection regressions.

## 12. Later

- Setbacks and terraces from LiDAR for detail buildings. Ghost Town 0.3.0 already measures roofs from Geospatial
  Ontario's LiDAR surface and terrain models (fitted and sampled roofs); the same surface could place floor
  bands and fins only where a facade really rises, and catch setbacks the massing misses. Outside Ontario,
  NRCan's CanElevation point clouds (GTA 2023 at about 24.5 points/m², as 1 km COPC tiles that accept range
  requests) and the 1 m HRDEM surface and ground models are the national options.
- Material classes (brick, concrete, stone, metal) from texture cues or a vision model.
- Better lower-floor glass detection.
- Measured window and mullion spacing.
- Optional real-photo projection onto one hero building, with the user nudging the camera.
- Geometry Nodes detail.

## 13. Risks and open questions

- Mapillary's API terms (caching, rate limits): unverified.
- Old photos: most usable photos at the test sites are from 2014–2019; buildings change. Recency weighting and
  "Not before" mitigate.
- Colour fidelity: calibration is relative to the site, not absolute; Photo brightness is the user's control.
- Zone errors: lower-floor glass can read as an opaque podium; foreground buildings missing from the massing
  (or not yet built) can still be sampled.
- Facade reading on real photos, from the live run at 351 King St E (61 of 87 buildings from photos): the
  dark storefront and brick podiums came out right, but the 84 m tower's glass above 36 m read as opaque
  (three photos, whose colours varied too little for the glass test), and one building got a sky-blue top
  zone, likely sky at the roofline passing the building label. `tools/look_accuracy.py` should track both
  before release; eroding the building label by a few pixels and refusing sky-coloured top zones are the
  first things to try.
- The token sits in plain text in Blender's user preferences.
- Pillow adds about 3–5 MB to each platform package.
