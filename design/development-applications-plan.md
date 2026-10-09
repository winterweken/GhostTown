# Development applications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Toronto build with **Development applications** ticked gets one see-through, status-coloured box per
nearby site with an open development application, a building going up or one just finished, refreshed by every
build and kept where the user reshaped it.

**Architecture:** The fetcher (`ghosttown/ghosttown_fetch`, plain Python with shapely and numpy, run outside
Blender) ports BHPlus's applications pipeline: City map points, the applications table and building permits
become status points, joined to parcels into sites, each with a starting box, written as an optional
`applications` list in `context.json` only when every source answered. The add-on (`ghosttown/`, bpy) turns that
list into box objects in an `Applications · <site>` collection that each build carries over; the decisions about
each box are a pure function in `ghosttown_fetch/app_boxes.py`, so plain pytest covers them.

**Tech Stack:** Python 3.13, shapely 2.1, numpy 2.3, pytest (`uv run pytest`, sockets disabled), Blender 5.2
(`bpy`, headless tests through `tests/blender/run.py`).

**Spec:** `design/development-applications.md` (approved 2026-10-09). The port's reference is the BHPlus repo at
`/Users/inscrip/code/BHPlus`, commit `60d801e` (`main`), directory `BH+.extension/lib/bh_context/`. Read a file
there with `git -C /Users/inscrip/code/BHPlus show 60d801e:"BH+.extension/lib/bh_context/<file>"`.

## Global Constraints

- Blender 5.2 or later; Python 3.13; shapely 2.1.2, numpy 2.3.4, Pillow 11.3.0 only. No new dependencies.
- `ghosttown/ghosttown_fetch/__init__.py`, `request.py`, `context.py` and `look_schema.py` stay standard library
  only (the add-on imports them without shapely). `app_boxes.py` may import `frame.py` (numpy, which Blender has)
  but never shapely or bpy.
- The fetcher never imports bpy. `scene_build.py` and the new `site_apps.py` never use `bpy.ops`.
- Fetch tests run with sockets disabled: every network answer in a test comes from `tests/fetch/fakes.py`.
- `LAYERS` gains `"applications"`; `DEFAULT_LAYERS` leaves out `"lidar"` and `"applications"`.
- `APPLICATION_GROUPS = ("construction", "built", "appealed", "review", "approved", "coa")`, which is also the
  precedence; labels "Under construction", "Recently built", "Appealed", "Under review", "Approved", "C of A";
  a box whose applications closed and that the user kept is "Closed".
- Box colours, sRGB 0–255: Under review 255,168,106; Approved 58,192,201; Appealed 255,57,95; Under construction
  108,130,166; C of A 212,143,249; Recently built 150,150,150; Closed 210,210,210. 30 % transparent (alpha 0.7).
- Caches: application points 1 day, applications table 1 day, permits 1 day, address points 7 days, parcels as
  today (30 days). CKAN pages are keyed by the URL and the day, so a new day never reads yesterday's pages.
- Permits: live = Inspection or Permit Issued, issued within 6 years of today; completed = Closed on or after
  1 January of the massing year, issued at most 10 years before completion; houses (`PERMIT_TYPE` "New Houses",
  or `STRUCTURE_TYPE` starting "SFD", "2 Unit" or "3+ Unit") left out and counted. CKAN reads stop at 50,000 rows.
- Heights: storeys × 3.2 m (`buildings.LEVEL_M`), at most 120 storeys; a box's base is the lowest ground under it
  less 0.3 m (`buildings.SINK_M`); a C of A site and a site with no stated height start at 3.2 m.
- "Touched": location more than 1 mm, rotation more than 0.05°, scale more than 0.0001 from what Ghost Town
  placed, any vertex more than 1 mm away or another vertex count, a parent, or a rotation mode other than XYZ.
- Only `http(s)` links on `toronto.ca` or its subdomains are kept and opened.
- Commit after every task, on branch `feat/development-applications`, with messages ending
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A duplicated box (Shift+D):** the copy carries the same numbers, so two boxes match one site. Expected: one
   is updated, the other is left as it is and a note names it; neither is removed. Test in Task 9.
2. **A box renamed or moved into the user's own collection:** expected to be found by its properties and updated
   where it is, never duplicated. Test in Task 9.
3. **A restyled status material:** the user recoloured `Context - Application (Approved)`; a rebuild must not
   reset it. Test in Task 9.
4. **The City half-answers** (the table answers, the permits time out, or a CKAN page comes back short):
   expected: no `applications` list, one warning naming the source, and every box left exactly as it was. Tests
   in Tasks 3 and 7 (fetcher) and Task 9 (boxes carried).
5. **A rebuild of the same site name around another centre:** expected: the boxes are carried to the same real
   place in the new frame, not left at their old local coordinates. Tests in Tasks 8 and 9.

---

## File structure

| File | Responsibility |
|---|---|
| `ghosttown/ghosttown_fetch/__init__.py` | layer list, groups and labels (modify) |
| `ghosttown/ghosttown_fetch/cache.py`, `net.py`, `sources/arcgis.py` | a per-call cache age (modify) |
| `ghosttown/ghosttown_fetch/mtm27.py` | the City's NAD27 MTM 10 grid to lon/lat (create, BHPlus `mtm.py`) |
| `ghosttown/ghosttown_fetch/boxfit.py` | the largest rectangle inside a site (create, BHPlus `boxfit.py`) |
| `ghosttown/ghosttown_fetch/sources/ckan.py` | the City's CKAN tables, paged and checked (create) |
| `ghosttown/ghosttown_fetch/sources/toronto_applications.py` | the applications table and its descriptions (create, BHPlus `sources/devapps.py`) |
| `ghosttown/ghosttown_fetch/sources/toronto_permits.py` | live and completed new-building permits (create, BHPlus `sources/permits.py`) |
| `ghosttown/ghosttown_fetch/construction.py` | permits as status points at their address points (create) |
| `ghosttown/ghosttown_fetch/applications.py` | status points into sites with starting boxes (create) |
| `ghosttown/ghosttown_fetch/context.py` | the `applications` block's checks, `city_link` (modify) |
| `ghosttown/ghosttown_fetch/sources/toronto.py` | application points, address points, parcels' expiry (modify) |
| `ghosttown/ghosttown_fetch/assemble.py` | the applications step, all or nothing (modify) |
| `ghosttown/ghosttown_fetch/app_boxes.py` | what a build does to each box; box geometry; the summary line (create) |
| `ghosttown/materials.py` | the status materials (modify) |
| `ghosttown/site_apps.py` | box objects in Blender: measure, place, update, close, remove, remember (create) |
| `ghosttown/scene_build.py` | carry the Applications collection across a rebuild (modify) |
| `ghosttown/props.py`, `ops.py`, `ui.py`, `__init__.py` | the tick, the operators, the panel (modify) |
| `README.md`, `tests/fetch/fixtures/README.md` | docs (modify) |

---

### Task 1: Layer constants, a per-call cache age, and the spec's port details

**Files:**
- Modify: `ghosttown/ghosttown_fetch/__init__.py:17-19`
- Modify: `ghosttown/ghosttown_fetch/cache.py` (`Cache.read`)
- Modify: `ghosttown/ghosttown_fetch/net.py` (`Net.get`)
- Modify: `ghosttown/ghosttown_fetch/sources/arcgis.py` (`query`)
- Modify: `tests/fetch/fakes.py` (`FakeNet.get`)
- Modify: `tests/fetch/test_request.py:65`
- Modify: `design/development-applications.md` (§4.2, §4.4, §5.1)
- Test: `tests/fetch/test_cache.py`, `tests/fetch/test_net.py`, `tests/fetch/test_arcgis.py`, `tests/fetch/test_request.py`

**Interfaces:**
- Produces: `ghosttown_fetch.LAYERS` (with `"applications"`), `OFF_BY_DEFAULT`, `DEFAULT_LAYERS`,
  `APPLICATION_GROUPS`, `GROUP_LABELS`; `Cache.read(source, key, max_age_days=None)`;
  `Net.get(url, *, source, data=None, check=None, timeout=120, keep=True, headers=None, key=None, max_age_days=None)`;
  `arcgis.query(net, service, layer, params, *, source="toronto", accept=None, max_age_days=None)`;
  `FakeNet` records `keys` and `ages` per call.

- [ ] **Step 1: Write the failing tests**

Append to `tests/fetch/test_cache.py`:

```python
def test_a_read_can_ask_for_a_shorter_age(tmp_path):
    now = [1_000_000.0]
    c = Cache(str(tmp_path), max_age_days=30, clock=lambda: now[0])
    c.write("toronto", "k", b"x")
    now[0] += 0.5 * 86400
    assert c.read("toronto", "k", max_age_days=1) == b"x"
    now[0] += 0.6 * 86400
    assert c.read("toronto", "k", max_age_days=1) is None
    assert c.read("toronto", "k") == b"x"      # the cache's own 30 days still hold for other readers
```

Append to `tests/fetch/test_net.py` (add `import os` and `import time` to its imports):

```python
def test_an_answer_older_than_its_age_is_fetched_again(tmp_path):
    t = Transport((200, b"old"), (200, b"new"))
    net = Net(str(tmp_path), transport=t)
    assert net.get(URL, source="toronto", max_age_days=1) == b"old"
    os.utime(net.cache._path("toronto", URL), (time.time() - 2 * 86400,) * 2)
    assert net.get(URL, source="toronto") == b"old"                  # 30 days for a caller that doesn't say
    assert net.get(URL, source="toronto", max_age_days=1) == b"new"
    assert len(t.calls) == 2
```

Append to `tests/fetch/test_arcgis.py`:

```python
def test_query_hands_its_age_to_the_cache():
    net = FakeNet({"toronto": lambda url, data: page(square(0, 0, 5, OBJECTID=1))})
    arcgis.query(net, "cot_geospatial11", 60, arcgis.radius_params(43.65, -79.38, 150), max_age_days=1)
    arcgis.query(net, "cot_geospatial3", 2, arcgis.radius_params(43.65, -79.38, 150))
    assert net.ages == [1, None]
```

In `tests/fetch/test_request.py`, replace line 65:

```python
    assert "lidar" in LAYERS and set(LAYERS) - set(DEFAULT_LAYERS) == {"lidar", "applications"}
```

and append:

```python
def test_development_applications_are_a_layer_asked_for():
    from ghosttown_fetch import APPLICATION_GROUPS, GROUP_LABELS
    assert "applications" in LAYERS and "applications" not in DEFAULT_LAYERS
    assert rq.validate(good(layers=list(DEFAULT_LAYERS) + ["applications"])) == []
    assert APPLICATION_GROUPS == ("construction", "built", "appealed", "review", "approved", "coa")
    assert [GROUP_LABELS[g] for g in APPLICATION_GROUPS] == [
        "Under construction", "Recently built", "Appealed", "Under review", "Approved", "C of A"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/fetch/test_cache.py tests/fetch/test_net.py tests/fetch/test_arcgis.py tests/fetch/test_request.py -q`
Expected: FAIL (`unexpected keyword argument 'max_age_days'`, `AttributeError: ... 'ages'`, `ImportError: APPLICATION_GROUPS`).

- [ ] **Step 3: Implement**

`ghosttown/ghosttown_fetch/__init__.py`, replace the `LAYERS` and `DEFAULT_LAYERS` lines with:

```python
LAYERS = ("buildings", "terrain", "roads", "sidewalks", "parking", "rail",
          "green", "water", "trees", "parcels", "photo", "lidar", "applications")
# Asked for, never by default: LiDAR roofs are a big download, and development applications are an awareness layer
# (design/development-applications.md §6.1).
OFF_BY_DEFAULT = ("lidar", "applications")
DEFAULT_LAYERS = tuple(layer for layer in LAYERS if layer not in OFF_BY_DEFAULT)
```

and after `SITE_LIMIT_M`:

```python
# Development applications (design/development-applications.md §4.3): a site's group, most live first, and its words.
APPLICATION_GROUPS = ("construction", "built", "appealed", "review", "approved", "coa")
GROUP_LABELS = {"construction": "Under construction", "built": "Recently built", "appealed": "Appealed",
                "review": "Under review", "approved": "Approved", "coa": "C of A"}
```

`ghosttown/ghosttown_fetch/cache.py`, change the module docstring's first line to
`"""A plain file cache: <root>/<source>/<sha1(key)>, used for max_age_days (or less, for one read); prune() deletes what is older."""`
and `read` to:

```python
    def read(self, source, key, max_age_days=None):
        """The stored bytes, or None when missing or older than the cache's age (or `max_age_days`, for a source
        that changes faster)."""
        path = self._path(source, key)
        max_age_s = self.max_age_s if max_age_days is None else max_age_days * 86400
        try:
            if self.clock() - os.path.getmtime(path) > max_age_s:
                return None
            with open(path, "rb") as f:
                return f.read()
        except OSError:
            return None
```

`ghosttown/ghosttown_fetch/net.py`, `Net.get`: add `max_age_days=None` to the signature after `key=None`, add to
its docstring `max_age_days, when given, is how old a stored answer may be instead of the cache's 30 days.`, and
change the cache read to `body = self.cache.read(source, key, max_age_days)`.

`ghosttown/ghosttown_fetch/sources/arcgis.py`, `query`: add `max_age_days=None` after `accept=None`, say in its
docstring `max_age_days: how long a stored page is used (the cache's 30 days when None).`, and pass it on:

```python
        page = _load(net.get(url, source=source, data=data, check=accept or check, max_age_days=max_age_days))
```

`tests/fetch/fakes.py`, `FakeNet`: add `self.keys = []` and `self.ages = []` in `__init__`, and make `get`:

```python
    def get(self, url, *, source, data=None, check=None, timeout=120, keep=True, headers=None, key=None,
            max_age_days=None):
        self.calls.append((url, source, data))
        self.keeps.append(keep)
        self.timeouts.append(timeout)
        self.headers.append(dict(headers or {}))
        self.requests.append((url, dict(headers or {})))
        self.keys.append(key)
        self.ages.append(max_age_days)
        answer = self.answers[source]
        if callable(answer):
            answer = answer(url, data)
        if isinstance(answer, Exception):
            raise answer
        if check is not None:
            check(answer)
        return answer
```

`design/development-applications.md`, three port details the plan settles:
- §4.2 table, row "The table's descriptions": change its query to "one `datastore_search` filtered to the
  `FOLDERRSN`s kept, with their `APPLICATION_URL`" and "Kept for" to "1 day". Under the table add: "CKAN pages
  are cached by their URL and the day, so the pages of one read come from one day."
- §4.4: replace "The doc's `sources` gain the applications' fetch dates: `"city-applications"` and
  `"city-permits"`." with "Beside the list, `"applications_date"` is the day of the run (`YYYY-MM-DD`): the data
  is at most a day older, the caches' age. The City is credited as `toronto`."
- §5.1, "On the collection": say `ctx_app_boxes` and `ctx_app_deleted` hold `{"numbers": [...], "centre_m":
  [x, y]}` per box (the centre is how a permit site on a deleted box's spot stays away), and add
  `ctx_app_frame` (`{"centre": {lat, lon}, "ground": metres or null}`, the frame the boxes were placed in).

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest -q`
Expected: all pass (802 before this task, plus the new ones).

- [ ] **Step 5: Commit**

```bash
git add ghosttown/ghosttown_fetch/__init__.py ghosttown/ghosttown_fetch/cache.py ghosttown/ghosttown_fetch/net.py \
  ghosttown/ghosttown_fetch/sources/arcgis.py tests/fetch design/development-applications.md
git commit -m "feat(fetch): the applications layer, its groups, and a cache age per call

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The City's old grid to lon/lat, and the largest rectangle inside a site

**Files:**
- Create: `ghosttown/ghosttown_fetch/mtm27.py`
- Create: `ghosttown/ghosttown_fetch/boxfit.py`
- Test: `tests/fetch/test_mtm27.py`, `tests/fetch/test_boxfit.py`

**Interfaces:**
- Produces: `mtm27.to_lonlat(x, y) -> (lon, lat)`;
  `boxfit.rectangle(g) -> (cx, cy, angle_deg, width_m, depth_m)` (width along `angle_deg`, degrees in (-90, 90]
  counter-clockwise from east); `boxfit.footprint(cx, cy, angle_deg, width_m, depth_m) -> Polygon`;
  `boxfit.main_angle(g) -> float`.

- [ ] **Step 1: Write the failing tests**

`tests/fetch/test_mtm27.py`:

```python
"""ghosttown_fetch.mtm27: the City's NAD27 MTM zone 10 grid to lon/lat, pinned against real pairs from the City's
applications map layer, which carries both (recorded 2026-10-08 for BHPlus)."""
import math

import pytest

from ghosttown_fetch import mtm27

PAIRS = {
    "downtown": (314092.389, 4833631.921, -79.384621957, 43.644570184),
    "scarborough": (326459.867, 4848821.714, -79.230713042, 43.781039958),
    "etobicoke": (301605.975, 4833147.722, -79.539390076, 43.640261437),
    "north york": (312175.499, 4847574.18, -79.40819269, 43.770089582),
    "far east": (333186.727, 4850842.951, -79.147035606, 43.799006924),
    "far north-west": (296994.854, 4843994.5, -79.596702223, 43.737862428),
}


def _metres(lon, lat, lon2, lat2):
    return math.hypot((lon - lon2) * 111320.0 * math.cos(math.radians(lat)), (lat - lat2) * 111320.0)


@pytest.mark.parametrize("name", sorted(PAIRS))
def test_each_part_of_the_city_converts_within_a_metre(name):
    x, y, lon, lat = PAIRS[name]
    got = mtm27.to_lonlat(x, y)
    assert _metres(got[0], got[1], lon, lat) < 1.0
```

`tests/fetch/test_boxfit.py`:

```python
"""ghosttown_fetch.boxfit: an application's starting box, the largest rectangle inside its site."""
import pytest
import shapely
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon, box

from ghosttown_fetch import boxfit


def _inside(r, g, slack=0.75):
    return boxfit.footprint(*r).within(g.buffer(slack))


def test_a_turned_rectangle_gives_itself_back():
    g = affinity.rotate(box(0, 0, 20, 10), 30, origin=(0, 0))
    cx, cy, angle, w, d = boxfit.rectangle(g)
    assert angle == pytest.approx(30.0, abs=1e-6)
    assert w == pytest.approx(20.0, abs=1.0) and d == pytest.approx(10.0, abs=1.0)
    assert (cx, cy) == pytest.approx((g.centroid.x, g.centroid.y), abs=0.6)


def test_an_l_shaped_site_gets_one_arm_not_a_box_over_the_neighbours():
    g = shapely.union_all([box(0, 0, 30, 10), box(0, 0, 10, 30)])
    r = boxfit.rectangle(g)
    assert boxfit.footprint(*r).area == pytest.approx(300.0, rel=0.07) and _inside(r, g)


def test_a_triangle_gets_a_rectangle_inside_it():
    g = Polygon([(0, 0), (40, 0), (0, 30)])
    r = boxfit.rectangle(g)
    assert _inside(r, g) and boxfit.footprint(*r).area > 250.0


def test_a_strip_under_two_metres_wide_falls_back_to_its_rotated_rectangle():
    cx, cy, angle, w, d = boxfit.rectangle(box(0, 0, 40, 1.5))
    assert (cx, cy, angle) == pytest.approx((20.0, 0.75, 0.0)) and (w, d) == pytest.approx((40.0, 1.5))


def test_two_separate_parcels_give_a_rectangle_in_the_bigger_one():
    g = MultiPolygon([box(0, 0, 10, 10), box(20, 0, 50, 12)])
    cx, cy, angle, w, d = boxfit.rectangle(g)
    assert 20.0 < cx < 50.0 and w * d == pytest.approx(360.0, rel=0.1)


def test_a_two_kilometre_site_stays_under_the_cell_budget_and_fills_itself():
    g = affinity.rotate(box(0, 0, 2000, 1000), -20)
    cx, cy, angle, w, d = boxfit.rectangle(g)
    assert angle == pytest.approx(-20.0, abs=1e-6) and w == pytest.approx(2000, rel=0.01)
    assert d == pytest.approx(1000, rel=0.01)


@pytest.mark.parametrize("deg", [0.0, 45.0, 89.0, 91.0, 135.0, 179.0, -60.0])
def test_the_angle_is_folded_into_minus_ninety_to_ninety(deg):
    angle = boxfit.main_angle(affinity.rotate(box(0, 0, 30, 10), deg, origin=(0, 0)))
    assert -90.0 < angle <= 90.0
    assert ((angle - deg) % 180.0) == pytest.approx(0.0, abs=1e-6) or \
        ((angle - deg) % 180.0) == pytest.approx(180.0, abs=1e-6)


def test_the_footprint_is_the_box_turned_about_its_centre():
    fp = boxfit.footprint(5.0, 5.0, 90.0, 10.0, 4.0)
    assert fp.bounds == pytest.approx((3.0, 0.0, 7.0, 10.0))
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/fetch/test_mtm27.py tests/fetch/test_boxfit.py -q`
Expected: FAIL with `ImportError: cannot import name 'mtm27'` / `'boxfit'`.

- [ ] **Step 3: Implement**

`ghosttown/ghosttown_fetch/mtm27.py`:

```python
"""The City of Toronto's old survey grid (NAD27, MTM zone 10) to lon/lat. The City's development applications
table gives its points only as X/Y on that grid. A quadratic in X and Y, fitted for BHPlus on all 15,683 points of
the City's applications map layer (which carries each point's NAD27 X/Y beside its longitude and latitude), is
within 1.01 m anywhere in the City, median 0.17 m; a plain affine is 40 m out at the edges. Good inside Toronto
only. Ported from BHPlus bh_context/mtm.py (60d801e). Standard library only."""
X0, Y0 = 315000.0, 4840000.0       # the fit's origin; its terms are in kilometres from it
LON = (-79.37325191775103, 0.0124071203594951, 1.8840177570581942e-05, -4.1180539278887763e-10,
       1.8640172725799175e-06, -6.313294613144159e-09)
LAT = (43.7018799591393, -1.3668036939638655e-05, 0.009001308169981952, -6.710819506449647e-07,
       -7.401185141775182e-09, 5.20160818360635e-09)


def to_lonlat(x, y):
    """(lon, lat) of NAD27 MTM zone 10 (x, y) in metres."""
    u, v = (x - X0) / 1000.0, (y - Y0) / 1000.0
    terms = (1.0, u, v, u * u, u * v, v * v)
    return sum(c * t for c, t in zip(LON, terms)), sum(c * t for c, t in zip(LAT, terms))
```

`ghosttown/ghosttown_fetch/boxfit.py`:

```python
"""An application's starting box (design/development-applications.md §4.3): the largest rectangle inside its site,
turned to the site's main direction (the long side of its minimum rotated rectangle).

The site is turned flat, laid on a grid (CELL_M, coarser when the grid would pass MAX_CELLS) and shrunk by half a
cell, and the largest block of cells whose centres are inside is the rectangle: it stays inside the site to a
fraction of a cell. A site that has no such block at least MIN_SIDE_M a side (a strip, a sliver) gets its minimum
rotated rectangle instead. Ported from BHPlus bh_context/boxfit.py (60d801e)."""
import math

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import box

CELL_M = 1.0
MAX_CELLS = 250000
MIN_SIDE_M = 2.0


def _fold(angle):
    """Degrees folded into (-90, 90]: a box turned half round is the same box."""
    while angle <= -90.0:
        angle += 180.0
    while angle > 90.0:
        angle -= 180.0
    return angle


def main_angle(g):
    """Degrees in (-90, 90], counter-clockwise from east, of the long side of `g`'s minimum rotated rectangle
    (0 for a shape with no area)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        rect = shapely.oriented_envelope(g)
    if rect.geom_type != "Polygon":
        return 0.0
    xy = np.asarray(rect.exterior.coords)
    a, b = xy[1] - xy[0], xy[2] - xy[1]
    edge = a if math.hypot(*a) >= math.hypot(*b) else b
    return round(_fold(math.degrees(math.atan2(edge[1], edge[0]))), 6)


def footprint(cx, cy, angle_deg, width_m, depth_m):
    """The box's outline: width along angle_deg, turned about its centre."""
    flat = box(cx - width_m / 2.0, cy - depth_m / 2.0, cx + width_m / 2.0, cy + depth_m / 2.0)
    return affinity.rotate(flat, angle_deg, origin=(cx, cy))


def _largest(mask):
    """(row0, col0, rows, cols) of the largest all-True block of a 2D bool array, or None: row by row, the tallest
    run of True above each cell is a histogram, and its largest rectangle is found with a stack."""
    h, w = mask.shape
    heights = np.zeros(w, dtype=np.int64)
    best_area, best = 0, None
    for r in range(h):
        heights = np.where(mask[r], heights + 1, 0)
        stack = []
        for c in range(w + 1):
            cur = int(heights[c]) if c < w else 0
            start = c
            while stack and stack[-1][1] >= cur:
                s, tall = stack.pop()
                if tall * (c - s) > best_area:
                    best_area, best = tall * (c - s), (r - tall + 1, s, tall, c - s)
                start = s
            stack.append((start, cur))
    return best


def _envelope(g, angle, about):
    with np.errstate(divide="ignore", invalid="ignore"):
        rect = shapely.oriented_envelope(g)
    flat = affinity.rotate(rect, -angle, origin=about)
    x0, y0, x1, y1 = flat.bounds
    p = affinity.rotate(shapely.Point((x0 + x1) / 2.0, (y0 + y1) / 2.0), angle, origin=about)
    return p.x, p.y, angle, x1 - x0, y1 - y0


def rectangle(g):
    """(cx, cy, angle_deg, width_m, depth_m): the largest rectangle inside `g` (a Polygon or MultiPolygon in local
    metres, with area) whose sides run along and across its main direction; width runs along angle_deg."""
    angle = main_angle(g)
    about = g.centroid
    flat = affinity.rotate(g, -angle, origin=about)
    x0, y0, x1, y1 = flat.bounds
    cell = max(CELL_M, math.sqrt((x1 - x0) * (y1 - y0) / MAX_CELLS))
    inner = flat.buffer(-cell / 2.0 + 1e-6)
    nx, ny = max(1, int(math.ceil((x1 - x0) / cell))), max(1, int(math.ceil((y1 - y0) / cell)))
    gx, gy = np.meshgrid(x0 + cell * (np.arange(nx) + 0.5), y0 + cell * (np.arange(ny) + 0.5))
    mask = shapely.contains_xy(inner, gx, gy) if not inner.is_empty else np.zeros(gx.shape, dtype=bool)
    found = _largest(mask)
    if found is not None:
        r0, c0, rows, cols = found
        w, d = cols * cell, rows * cell
        if min(w, d) >= MIN_SIDE_M:
            p = affinity.rotate(shapely.Point(x0 + cell * (c0 + cols / 2.0), y0 + cell * (r0 + rows / 2.0)),
                                angle, origin=about)
            return p.x, p.y, angle, w, d
    return _envelope(g, angle, about)
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/fetch/test_mtm27.py tests/fetch/test_boxfit.py -q`
Expected: PASS (6 + 14 tests).

- [ ] **Step 5: Commit**

```bash
git add ghosttown/ghosttown_fetch/mtm27.py ghosttown/ghosttown_fetch/boxfit.py tests/fetch/test_mtm27.py tests/fetch/test_boxfit.py
git commit -m "feat(fetch): the City's NAD27 grid to lon/lat, and the largest box inside a site, from BHPlus

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 3: The City's Open Data tables: the applications table and building permits

**Files:**
- Create: `ghosttown/ghosttown_fetch/sources/ckan.py`
- Create: `ghosttown/ghosttown_fetch/sources/toronto_applications.py`
- Create: `ghosttown/ghosttown_fetch/sources/toronto_permits.py`
- Create: `tests/fetch/ckan_samples.py`
- Test: `tests/fetch/test_ckan.py`

**Interfaces:**
- Consumes: `Net.get(..., key=..., max_age_days=...)` (Task 1); `mtm27.to_lonlat` (Task 2, in `ckan_samples`).
- Produces:
  - `ckan.read(net, resource, what, today, *, filters=None, fields=None, sort=None, stop=None, max_rows=MAX_ROWS) -> [row]`
  - `ckan.day(value) -> "YYYY-MM-DD" | None`, `ckan.none_is_wrong(rows, what)`, `ckan.search_url(...)`,
    `ckan.SEARCH`, `ckan.MAX_AGE_DAYS = 1`
  - `toronto_applications.RESOURCE`, `get_table(net, today) -> [row]`,
    `descriptions(net, folders, today) -> {folder: (description, url)}`
  - `toronto_permits.LIVE`, `DONE`, `LIVE_STATUSES`, `FLOOR_FIELDS`, `get_live(net, since, today)`,
    `get_completed(net, since, today)` (each `-> [row]`, newest first)
  - `tests/fetch/ckan_samples.py`: `answer(tables)` (a FakeNet answer), `query(url) -> dict`,
    `mtm27_xy(lon, lat) -> (x, y)`
  - `today` is always a `"YYYY-MM-DD"` string.

- [ ] **Step 1: Write the test helpers and the failing tests**

`tests/fetch/ckan_samples.py`:

```python
"""Answers shaped like the City of Toronto's CKAN datastore_search, served from rows held in memory."""
import json
import urllib.parse

from ghosttown_fetch import mtm27


def query(url):
    return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}


def answer(tables):
    """A FakeNet answer for datastore_search over `tables` ({resource id: rows, in the order the City sorts them}):
    rows matched by `filters` (a list means any of its values), cut to `fields`, paged by offset and limit."""
    def serve(url, data):
        q = query(url)
        rows = tables[q["resource_id"]]
        for key, want in json.loads(q.get("filters", "{}")).items():
            allowed = want if isinstance(want, list) else [want]
            rows = [r for r in rows if r.get(key) in allowed]
        if q.get("fields"):
            rows = [{k: r.get(k) for k in q["fields"].split(",")} for r in rows]
        start, limit = int(q["offset"]), int(q["limit"])
        return json.dumps({"success": True, "result": {"records": rows[start:start + limit],
                                                       "total": len(rows)}}).encode("utf-8")
    return serve


def mtm27_xy(lon, lat):
    """The NAD27 MTM zone 10 X/Y that mtm27.to_lonlat takes to (lon, lat), found by Newton's method."""
    x, y = 314092.389, 4833631.921
    for _ in range(8):
        lo, la = mtm27.to_lonlat(x, y)
        ax, ay = mtm27.to_lonlat(x + 1.0, y)
        bx, by = mtm27.to_lonlat(x, y + 1.0)
        a, b, c, d = ax - lo, bx - lo, ay - la, by - la      # d(lon, lat) / d(x, y), per metre
        det = a * d - b * c
        ex, ey = lon - lo, lat - la
        x += (ex * d - ey * b) / det
        y += (ey * a - ex * c) / det
    return x, y
```

`tests/fetch/test_ckan.py`:

```python
"""ghosttown_fetch.sources.ckan, toronto_applications and toronto_permits: the City's Open Data tables, read page by
page, stopped at a date, shape-checked and cached for the day. Ported from BHPlus tests/test_context_ckan.py."""
import json

import pytest

from ghosttown_fetch.net import SourceError
from ghosttown_fetch.sources import ckan, toronto_applications, toronto_permits
from ckan_samples import answer, query
from fakes import FakeNet

TODAY = "2026-10-09"


def _net(serve):
    return FakeNet({"toronto": serve})


def _raw(page):
    return lambda url, data: page if isinstance(page, bytes) else json.dumps(page).encode("utf-8")


def test_the_search_url_names_the_resource_filters_fields_and_order():
    q = query(ckan.search_url("abc", offset=20, filters={"WORK": "New Building", "STATUS": ["A", "B"]},
                              fields=("X", "Y"), sort="ISSUED_DATE desc", limit=5))
    assert q["resource_id"] == "abc" and (q["offset"], q["limit"]) == ("20", "5")
    assert json.loads(q["filters"]) == {"STATUS": ["A", "B"], "WORK": "New Building"}
    assert q["fields"] == "X,Y" and q["sort"] == "ISSUED_DATE desc"
    assert ckan.search_url("abc").startswith(ckan.SEARCH + "?")


def test_read_takes_every_page_and_keeps_each_for_the_day():
    rows = [{"N": i} for i in range(25)]
    net = _net(answer({"abc": rows}))
    assert ckan.read(net, "abc", "test rows", TODAY, fields=("N",)) == rows
    assert len(net.calls) == 1 and net.ages == [ckan.MAX_AGE_DAYS]
    assert net.keys == [net.calls[0][0] + "\n" + TODAY]          # a new day never reads yesterday's pages


def test_read_pages_by_the_page_size(monkeypatch):
    monkeypatch.setattr(ckan, "PAGE_SIZE", 10)
    rows = [{"N": i} for i in range(25)]
    net = _net(answer({"abc": rows}))
    assert ckan.read(net, "abc", "test rows", TODAY) == rows and len(net.calls) == 3


def test_read_stops_at_the_first_row_stop_names_and_keeps_the_nulls_before_it():
    rows = [{"D": None}, {"D": "2026-01-02"}, {"D": "2025-12-31"}, {"D": "2025-06-01"}]
    got = ckan.read(_net(answer({"abc": rows})), "abc", "test rows", TODAY,
                    stop=lambda r: r["D"] is not None and r["D"] < "2026-01-01")
    assert got == rows[:2]


@pytest.mark.parametrize("page", [
    {"success": False, "error": {"message": "field not found"}}, {"result": {"records": "x", "total": 1}},
    {"result": {"records": [{"N": [1]}], "total": 1}}, {"result": {"records": [], "total": "many"}}, [],
    b"<html>"])
def test_read_refuses_an_answer_that_is_not_records(page):
    with pytest.raises(SourceError, match="test rows"):
        ckan.read(_net(_raw(page)), "abc", "test rows", TODAY)


def test_read_stops_past_the_row_limit():
    rows = [{"N": i} for i in range(12)]
    with pytest.raises(SourceError, match="more than 10"):
        ckan.read(_net(answer({"abc": rows})), "abc", "test rows", TODAY, max_rows=10)


def test_read_refuses_a_page_that_comes_back_empty_before_the_total(monkeypatch):
    monkeypatch.setattr(ckan, "PAGE_SIZE", 10)
    rows = [{"N": i} for i in range(25)]

    def short(url, data):
        start = int(query(url)["offset"])
        return json.dumps({"result": {"records": rows[start:start + 10] if start < 10 else [],
                                      "total": len(rows)}}).encode("utf-8")
    with pytest.raises(SourceError, match="fewer rows"):
        ckan.read(_net(short), "abc", "test rows", TODAY)


def test_read_refuses_a_table_whose_total_changes_between_pages(monkeypatch):
    monkeypatch.setattr(ckan, "PAGE_SIZE", 10)
    rows = [{"N": i} for i in range(25)]

    def reloading(url, data):
        start = int(query(url)["offset"])
        return json.dumps({"result": {"records": rows[start:start + 10],
                                      "total": 25 if start == 0 else 30}}).encode("utf-8")
    with pytest.raises(SourceError, match="changed"):
        ckan.read(_net(reloading), "abc", "test rows", TODAY)


@pytest.mark.parametrize("value, day", [("2025-07-31", "2025-07-31"), ("2026-03-09T00:00:00", "2026-03-09"),
                                        ("", None), (None, None), ("31/07/2025", None), (20250731, None)])
def test_day_reads_the_date_part_or_none(value, day):
    assert ckan.day(value) == day


def _permit(number, issued, status="Inspection", completed=None):
    return {"PERMIT_NUM": number, "REVISION_NUM": "00", "STATUS": status, "ISSUED_DATE": issued,
            "COMPLETED_DATE": completed, "WORK": "New Building"}


def test_live_permits_are_read_newest_issued_first_until_the_cutoff():
    rows = [_permit("A", None), _permit("B", "2026-01-01"), _permit("C", "2021-01-01"), _permit("D", "2019-01-01")]
    net = _net(answer({toronto_permits.LIVE: rows}))
    got = toronto_permits.get_live(net, "2020-10-09", TODAY)
    assert [r["PERMIT_NUM"] for r in got] == ["A", "B", "C"]
    q = query(net.calls[0][0])
    assert json.loads(q["filters"]) == {"STATUS": ["Inspection", "Permit Issued"], "WORK": "New Building"}
    assert q["sort"] == "ISSUED_DATE desc, _id" and "DESCRIPTION" in q["fields"].split(",")


def test_completed_permits_are_read_newest_completed_first():
    rows = [_permit("A", "2020-01-01", "Closed", "2026-02-01"), _permit("B", "2019-01-01", "Closed", "2024-06-01")]
    net = _net(answer({toronto_permits.DONE: rows}))
    got = toronto_permits.get_completed(net, "2025-01-01", TODAY)
    assert [r["PERMIT_NUM"] for r in got] == ["A"]
    q = query(net.calls[0][0])
    assert json.loads(q["filters"]) == {"STATUS": "Closed", "WORK": "New Building"}
    assert q["sort"] == "COMPLETED_DATE desc, _id"


def test_the_table_is_read_whole_without_descriptions_or_links():
    rows = [{"APPLICATION#": "26 1 STE 10 SA", "FOLDERRSN": "1", "DESCRIPTION": "long", "APPLICATION_URL": "x"}]
    net = _net(answer({toronto_applications.RESOURCE: rows}))
    got = toronto_applications.get_table(net, TODAY)
    assert got[0]["APPLICATION#"] == "26 1 STE 10 SA" and "DESCRIPTION" not in got[0]
    q = query(net.calls[0][0])
    assert q["sort"] == "_id" and "DESCRIPTION" not in q["fields"] and "APPLICATION_URL" not in q["fields"]


def test_descriptions_and_links_are_asked_for_only_the_folders_given():
    rows = [{"FOLDERRSN": "1", "DESCRIPTION": " a 9-storey building ", "APPLICATION_URL": "http://app.toronto.ca/AIC/x"},
            {"FOLDERRSN": "1", "DESCRIPTION": "again", "APPLICATION_URL": "other"},
            {"FOLDERRSN": "2", "DESCRIPTION": "", "APPLICATION_URL": None},
            {"FOLDERRSN": "3", "DESCRIPTION": "not asked", "APPLICATION_URL": ""}]
    net = _net(answer({toronto_applications.RESOURCE: rows}))
    got = toronto_applications.descriptions(net, {"1", "2", "4"}, TODAY)
    assert got == {"1": ("a 9-storey building", "http://app.toronto.ca/AIC/x"), "2": ("", ""), "4": ("", "")}
    assert json.loads(query(net.calls[0][0])["filters"]) == {"FOLDERRSN": ["1", "2", "4"]}
    assert toronto_applications.descriptions(net, set(), TODAY) == {} and len(net.calls) == 1


@pytest.mark.parametrize("get", [
    lambda net: toronto_applications.get_table(net, TODAY),
    lambda net: toronto_permits.get_live(net, "2020-10-09", TODAY),
    lambda net: toronto_permits.get_completed(net, "2025-01-01", TODAY)])
def test_a_city_wide_list_that_comes_back_empty_is_refused(get):
    net = _net(answer({toronto_applications.RESOURCE: [], toronto_permits.LIVE: [], toronto_permits.DONE: []}))
    with pytest.raises(SourceError, match="no rows"):
        get(net)
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/fetch/test_ckan.py -q`
Expected: FAIL with `ImportError: cannot import name 'ckan'`.

- [ ] **Step 3: Implement**

`ghosttown/ghosttown_fetch/sources/ckan.py`:

```python
"""The City of Toronto's Open Data tables (CKAN datastore_search), read page by page in a given order until a row
says stop. Every page must be a list of flat records (text, numbers, true/false or nothing) before any of it is
used or cached; a page that comes back empty before the table's total, or a total that changes between pages (the
City reloading the table), is refused rather than taken as the whole table; and a table that runs past MAX_ROWS is
refused rather than read on forever. Pages are kept for the day they were read: the cache key carries the day, so
the pages of one read never mix two days of the City's table. Ported from BHPlus bh_context/sources/ckan.py."""
import json
import math
import re
import urllib.parse

from ..net import SourceError

SEARCH = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/datastore_search"
SOURCE = "toronto"
PAGE_SIZE = 10000
MAX_ROWS = 50000
MAX_AGE_DAYS = 1          # the City refreshes these tables daily
_DAY = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:$|T)")


def search_url(resource, offset=0, filters=None, fields=None, sort=None, limit=None):
    """The datastore_search URL for one page of `resource`."""
    params = [("resource_id", resource), ("limit", PAGE_SIZE if limit is None else limit), ("offset", offset)]
    if filters:
        params.append(("filters", json.dumps(filters, sort_keys=True)))
    if fields:
        params.append(("fields", ",".join(fields)))
    if sort:
        params.append(("sort", sort))
    return SEARCH + "?" + urllib.parse.urlencode(params)


def _value_ok(v):
    return v is None or isinstance(v, (str, bool, int)) or (isinstance(v, float) and math.isfinite(v))


def rows_ok(rows):
    """Whether `rows` is a list of flat records whose keys are text."""
    return isinstance(rows, list) and all(
        isinstance(r, dict) and all(isinstance(k, str) and _value_ok(v) for k, v in r.items()) for r in rows)


def _page(body, what):
    """A page's `result` ({"records", "total"}), or a SourceError naming the table."""
    try:
        page = json.loads(body)
    except ValueError:
        page = None
    result = page.get("result") if isinstance(page, dict) else None
    total = result.get("total") if isinstance(result, dict) else None
    if not (isinstance(result, dict) and rows_ok(result.get("records")) and isinstance(total, int)
            and not isinstance(total, bool)):
        raise SourceError(f"The City's Open Data portal sent an answer for its {what} that couldn't be read; "
                          "try again later.")
    return result


def read(net, resource, what, today, *, filters=None, fields=None, sort=None, stop=None, max_rows=MAX_ROWS):
    """Every row of `resource` matching `filters`, in `sort` order, until `stop(row)` is true (that row and every
    one after it are left unread). `what` names the table in the errors ("building permits"); `today`
    ('YYYY-MM-DD') keys the cached pages."""
    rows, offset, total = [], 0, None

    def check(body):
        _page(body, what)

    while True:
        url = search_url(resource, offset, filters, fields, sort)
        result = _page(net.get(url, source=SOURCE, check=check, key=url + "\n" + today, max_age_days=MAX_AGE_DAYS),
                       what)
        records = result["records"]
        if total is not None and result["total"] != total:
            raise SourceError(f"The City's {what} changed while they were read; try again later.")
        total = result["total"]
        if not records and offset < total:
            raise SourceError(f"The City's Open Data portal sent fewer rows of its {what} than it said it has; "
                              "try again later.")
        for row in records:
            if stop is not None and stop(row):
                return rows
            if len(rows) >= max_rows:
                raise SourceError(f"The City's {what} have more than {max_rows:,} rows to read; try again later.")
            rows.append(row)
        offset += len(records)
        if not records or offset >= total:
            return rows


def none_is_wrong(rows, what):
    """`rows`, or a SourceError when a list that is never empty (the whole City's) came back empty."""
    if not rows:
        raise SourceError(f"The City's Open Data portal sent no rows for its {what}; try again later.")
    return rows


def day(value):
    """The 'YYYY-MM-DD' a CKAN date text starts with ('2026-03-09T00:00:00' too), else None."""
    m = _DAY.match(value) if isinstance(value, str) else None
    return m.group(1) if m else None
```

`ghosttown/ghosttown_fetch/sources/toronto_applications.py`:

```python
"""The City's development applications table (CKAN): every application with its status and its point as NAD27 MTM
X/Y, read whole without the long descriptions and links; the descriptions and links of the few a build places are
asked for afterwards by FOLDERRSN. Both are kept for the day (ckan.read). Ported from BHPlus
bh_context/sources/devapps.py."""
from . import ckan

RESOURCE = "8907d8ed-c515-4ce9-b674-9f8c6eefcf0d"
WHAT = "development applications table"
FIELDS = ("APPLICATION#", "APPLICATION_TYPE", "STATUS", "DATE_SUBMITTED", "X", "Y", "FOLDERRSN", "STREET_NUM",
          "STREET_NAME", "STREET_TYPE", "STREET_DIRECTION")


def get_table(net, today):
    """Every row, read in row-id order so the pages neither skip nor repeat a row; an empty table is refused."""
    return ckan.none_is_wrong(ckan.read(net, RESOURCE, WHAT, today, fields=FIELDS, sort="_id"), WHAT)


def descriptions(net, folders, today):
    """{FOLDERRSN: (description, link)} for the applications `folders` names: the first text that says something
    and the first link, each "" when the City gives none."""
    if not folders:
        return {}
    wanted = sorted(folders)
    rows = ckan.read(net, RESOURCE, WHAT, today, filters={"FOLDERRSN": wanted},
                     fields=("FOLDERRSN", "DESCRIPTION", "APPLICATION_URL"))
    texts, links = {}, {}
    for row in rows:
        folder = row.get("FOLDERRSN")
        if not isinstance(folder, str):
            continue
        text, link = row.get("DESCRIPTION"), row.get("APPLICATION_URL")
        if isinstance(text, str) and text.strip() and folder not in texts:
            texts[folder] = text.strip()
        if isinstance(link, str) and link.strip() and folder not in links:
            links[folder] = link.strip()
    return {folder: (texts.get(folder, ""), links.get(folder, "")) for folder in wanted}
```

`ghosttown/ghosttown_fetch/sources/toronto_permits.py`:

```python
"""The City's building permits for new buildings (CKAN): the live ones (Inspection, Permit Issued) newest issued
first, and the completed ones (Closed) newest completed first, each read back only to a cutoff day, with the row id
breaking ties so the pages neither skip nor repeat a row. An empty list is refused (the City always has some).
Ported from BHPlus bh_context/sources/permits.py."""
from . import ckan

LIVE = "6d0229af-bc54-46de-9c2b-26759b01dd05"          # building-permits-active-permits
DONE = "a96c0ba4-3026-402b-b09d-5b1268b8f810"          # building-permits-cleared-permits, since 2017
WHAT = "building permits"
LIVE_STATUSES = ("Inspection", "Permit Issued")
FLOOR_FIELDS = ("ASSEMBLY", "INSTITUTIONAL", "RESIDENTIAL", "BUSINESS_AND_PERSONAL_SERVICES", "MERCANTILE",
                "INDUSTRIAL")                               # floor area by use, m²
FIELDS = ("PERMIT_NUM", "REVISION_NUM", "PERMIT_TYPE", "STRUCTURE_TYPE", "STATUS", "GEO_ID", "STREET_NUM",
          "STREET_NAME", "STREET_TYPE", "STREET_DIRECTION", "ISSUED_DATE", "COMPLETED_DATE",
          "DESCRIPTION") + FLOOR_FIELDS


def _before(value, since):
    d = ckan.day(value)
    return d is not None and d < since


def _get(net, resource, filters, field, since, today):
    return ckan.none_is_wrong(ckan.read(net, resource, WHAT, today, filters=filters, fields=FIELDS,
                                        sort=field + " desc, _id", stop=lambda row: _before(row.get(field), since)),
                              WHAT)


def get_live(net, since, today):
    """Live new-building permits issued on or after `since` ('YYYY-MM-DD'), newest first, with any whose issued
    date is missing."""
    return _get(net, LIVE, {"WORK": "New Building", "STATUS": list(LIVE_STATUSES)}, "ISSUED_DATE", since, today)


def get_completed(net, since, today):
    """New-building permits closed on or after `since`, newest first."""
    return _get(net, DONE, {"WORK": "New Building", "STATUS": "Closed"}, "COMPLETED_DATE", since, today)
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/fetch/test_ckan.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ghosttown/ghosttown_fetch/sources/ckan.py ghosttown/ghosttown_fetch/sources/toronto_applications.py \
  ghosttown/ghosttown_fetch/sources/toronto_permits.py tests/fetch/ckan_samples.py tests/fetch/test_ckan.py
git commit -m "feat(fetch): the City's applications table and building permits, paged, checked and kept for the day

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Building permits as status points

**Files:**
- Create: `ghosttown/ghosttown_fetch/construction.py`
- Test: `tests/fetch/test_construction.py`

**Interfaces:**
- Consumes: `ckan.day`, `toronto_permits.FLOOR_FIELDS`, `LIVE_STATUSES` (Task 3).
- Produces: `construction.LIVE_YEARS = 6`, `BUILT_ISSUED_YEARS = 10`, `years_before(iso, n)`, `is_house(row)`,
  `fold(rows)`, `live(rows, today)`, `completed(rows, year)`, `floor_area(row)`,
  `Addresses(features)` with `.locate(row) -> Point | None` and `.nearby(row) -> bool`,
  `points(rows, group, addresses, keep) -> ([(Point, status point)], houses, unplaced)`. A status point is
  `{"number", "source", "group", "type", "status", "date", "description", "address", "floor_area_m2",
  "folderrsn", "unknown", "url"}` (Task 6's `applications.status_point` makes the same shape).

- [ ] **Step 1: Write the failing test**

`tests/fetch/test_construction.py`:

```python
"""ghosttown_fetch.construction: the City's building permits as status points: houses left out, revisions folded,
the live and completed cutoffs, and each permit placed at its address point. Ported from BHPlus
tests/test_context_construction.py."""
import pytest
from shapely.geometry import Point

from ghosttown_fetch import construction

TODAY = "2026-10-08"


def _row(number="21 123456 BLD", revision="00", status="Inspection", issued="2023-05-03", completed=None,
         kind="New Building", structure="Apartment Building", geo="30123033", num="1141", street="BLOOR",
         street_type="ST", direction="W", text="a 21 storey apartment building", **floors):
    row = {"PERMIT_NUM": number, "REVISION_NUM": revision, "STATUS": status, "ISSUED_DATE": issued,
           "COMPLETED_DATE": completed, "PERMIT_TYPE": kind, "STRUCTURE_TYPE": structure, "GEO_ID": geo,
           "STREET_NUM": num, "STREET_NAME": street, "STREET_TYPE": street_type, "STREET_DIRECTION": direction,
           "DESCRIPTION": text}
    row.update(floors)
    return row


def _address(x, y, pid, number, name, kind="St", direction="W"):
    return Point(x, y), {"ADDRESS_POINT_ID": pid, "LO_NUM": number, "LINEAR_NAME": name,
                         "LINEAR_NAME_TYPE": kind, "LINEAR_NAME_DIR": direction}


ADDRESSES = construction.Addresses([
    _address(10, 10, 30123033, 1141, "Bloor"), _address(30, 10, 30123040, 1151, "Bloor"),
    _address(50, 10, 30123050, 1177, "Danforth", kind="Ave", direction=None),
    _address(70, 10, 30123060, 200, "Brown's Line", kind=None, direction=None),
    _address(90, 10, 30123070, 12, "The Queensway", kind=None, direction=None)])


@pytest.mark.parametrize("kind, structure, house", [
    ("New Houses", "Apartment Building", True), ("New Building", "SFD - Detached", True),
    ("New Building", " SFD - Townhouse ", True), ("New Building", "2 Unit - Detached", True),
    ("New Building", "3+ Unit - Semi-detached", True), ("New Building", "Apartment Building", False),
    ("Residential Building Permit", "Stacked Townhouses", False), ("New Building", None, False)])
def test_houses_are_new_house_permits_and_house_structures(kind, structure, house):
    assert construction.is_house(_row(kind=kind, structure=structure)) is house


def test_revisions_fold_into_their_permit():
    rows = [_row("A", "01", issued="2024-01-01"), _row("A", "00", issued="2023-01-01"),
            _row("B", "02"), _row("B", "01", issued="2022-02-02")]
    folded = construction.fold(rows)
    assert [(r["PERMIT_NUM"], r["REVISION_NUM"]) for r in folded] == [("A", "00"), ("B", "01")]


@pytest.mark.parametrize("iso, n, want", [("2026-10-08", 6, "2020-10-08"), ("2028-02-29", 6, "2022-02-28"),
                                          ("2026-01-01", 10, "2016-01-01")])
def test_years_before_handles_the_edges(iso, n, want):
    assert construction.years_before(iso, n) == want


def test_live_permits_are_the_ones_issued_within_six_years():
    rows = [_row("NEW", issued="2025-01-01"), _row("EDGE", issued="2020-10-08"), _row("OLD", issued="2003-04-01"),
            _row("NONE", issued=None), _row("ODD", status="Under Review", issued="2025-01-01")]
    assert [r["PERMIT_NUM"] for r in construction.live(rows, TODAY)] == ["NEW", "EDGE"]


def test_completed_permits_finished_since_the_massing_year_and_were_issued_within_ten_years_of_it():
    rows = [_row("DONE", status="Closed", issued="2022-02-23", completed="2026-03-01"),
            _row("EARLY", status="Closed", issued="2022-02-23", completed="2024-12-31"),
            _row("TIDY", status="Closed", issued="2001-05-01", completed="2026-06-01"),
            _row("EDGE", status="Closed", issued="2015-01-01", completed="2025-01-01"),
            _row("DORMANT", status="Closed - Dormant", issued="2022-01-01", completed="2026-01-01"),
            _row("NODATE", status="Closed", issued=None, completed="2026-01-01")]
    assert [r["PERMIT_NUM"] for r in construction.completed(rows, "2025")] == ["DONE", "EDGE"]
    assert [r["PERMIT_NUM"] for r in construction.completed(rows, 2025)] == ["DONE", "EDGE"]


def test_the_floor_area_adds_every_use_and_counts_text_as_zero():
    assert construction.floor_area(_row(RESIDENTIAL=1201.56, MERCANTILE="69.4", ASSEMBLY="n/a", INDUSTRIAL=None)) \
        == pytest.approx(1270.96)
    assert construction.floor_area(_row()) == 0.0


def test_a_permit_is_at_its_address_point_by_id():
    assert ADDRESSES.locate(_row(geo="30123040", num="1")).coords[0] == (30.0, 10.0)


def test_a_retired_id_falls_back_to_the_street_number_and_name():
    assert ADDRESSES.locate(_row(geo="6710176")).coords[0] == (10.0, 10.0)                # 1141 Bloor St W
    assert ADDRESSES.locate(_row(geo="1", num="200", street="BROWNS LINE", street_type="",
                                 direction="")).coords[0] == (70.0, 10.0)
    assert ADDRESSES.locate(_row(geo="1", num="12", street="THE QUEENSWAY", street_type="  ",
                                 direction="")).coords[0] == (90.0, 10.0)


def test_a_ranged_or_suffixed_street_number_matches_its_leading_number():
    assert ADDRESSES.locate(_row(geo=None, num="1177-1181", street="DANFORTH", street_type="AVE",
                                 direction="")).coords[0] == (50.0, 10.0)
    assert ADDRESSES.locate(_row(geo="", num="1151A")).coords[0] == (30.0, 10.0)


def test_a_different_street_type_or_direction_does_not_match():
    assert ADDRESSES.locate(_row(geo="1", street_type="AVE")) is None
    assert ADDRESSES.locate(_row(geo="1", direction="E")) is None


def test_nearby_says_a_permit_should_have_been_here():
    assert ADDRESSES.nearby(_row(geo="1", num="1145")) is True               # Bloor, between 1141 and 1151
    assert ADDRESSES.nearby(_row(geo="1", num="5000")) is False              # Bloor, far past this circle
    assert ADDRESSES.nearby(_row(geo="1", street="YONGE")) is False          # not a street here


def test_nearby_minds_the_direction_like_locate_does():
    assert ADDRESSES.nearby(_row(geo="1", num="1145", direction="E")) is False   # Bloor St E: across town
    assert ADDRESSES.nearby(_row(geo="1", num="1145", direction="")) is True     # no direction: may be this one


def test_points_are_the_kept_non_house_permits_and_count_houses_and_the_unplaced():
    rows = [_row("APT", text="a 21 storey apartment building", RESIDENTIAL=21000),
            _row("HOUSE", kind="New Houses", geo="30123040"),
            _row("FAR", geo="30123070"),                                     # keep() refuses it
            _row("LOST", geo="1", num="1145"),
            _row("ELSEWHERE", geo="1", street="YONGE", num="5000")]
    got, houses, unplaced = construction.points(rows, "construction", ADDRESSES, keep=lambda p: p.x < 80)
    assert (houses, unplaced) == (1, 1)
    ((g, sp),) = got
    assert g.coords[0] == (10.0, 10.0)
    assert sp == {"number": "APT", "source": "permit", "group": "construction", "type": "Apartment Building",
                  "status": "Inspection", "date": "2023-05-03", "description": "a 21 storey apartment building",
                  "address": "1141 BLOOR ST W", "floor_area_m2": 21000.0, "folderrsn": "", "unknown": None,
                  "url": ""}


def test_a_completed_permit_is_dated_by_its_completion():
    ((_, sp),), _, _ = construction.points([_row("DONE", status="Closed", completed="2026-03-01")], "built",
                                           ADDRESSES, keep=lambda p: True)
    assert sp["group"] == "built" and sp["date"] == "2026-03-01"
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/fetch/test_construction.py -q`
Expected: FAIL with `ImportError: cannot import name 'construction'`.

- [ ] **Step 3: Implement**

Create `ghosttown/ghosttown_fetch/construction.py` from BHPlus with the commands below, then edit it:

```bash
git -C /Users/inscrip/code/BHPlus show 60d801e:"BH+.extension/lib/bh_context/construction.py" > ghosttown/ghosttown_fetch/construction.py
```

Edits, all of them:
1. Delete the first line (`# -*- coding: utf-8 -*-`).
2. Replace the docstring's first line `"""Building permits as status points (spec 2026-10-08 construction §4).` with
   `"""Building permits as status points (design/development-applications.md §4.3).` and add, as the
   docstring's last paragraph before its closing `"""`: `Ported from BHPlus bh_context/construction.py (60d801e).`
3. Replace the two imports
   `from bh_context.sources import ckan` and
   `from bh_context.sources.permits import FLOOR_FIELDS, LIVE_STATUSES` with
   ```python
   from .sources import ckan
   from .sources.toronto_permits import FLOOR_FIELDS, LIVE_STATUSES
   ```
4. Replace `class Addresses(object):` with `class Addresses:`.
5. In `points`, the status point dict gains `"url": ""` after `"unknown": None`:
   ```python
        out.append((g, {"number": _text(row.get("PERMIT_NUM")), "source": "permit", "group": group,
                        "type": _text(row.get("STRUCTURE_TYPE")), "status": _text(row.get("STATUS")), "date": date,
                        "description": _text(row.get("DESCRIPTION")), "address": _address(row),
                        "floor_area_m2": round(floor_area(row), 1), "folderrsn": "", "unknown": None, "url": ""}))
   ```
6. `completed(rows, year)` builds `since = "{0}-01-01".format(year)`, so an int year works; leave it.

- [ ] **Step 4: Run it to see it pass**

Run: `uv run pytest tests/fetch/test_construction.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ghosttown/ghosttown_fetch/construction.py tests/fetch/test_construction.py
git commit -m "feat(fetch): building permits as status points at their address points, from BHPlus

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 5: The `applications` block in context.json, and the City links it may carry

**Files:**
- Modify: `ghosttown/ghosttown_fetch/context.py`
- Test: `tests/fetch/test_context.py`

**Interfaces:**
- Consumes: `APPLICATION_GROUPS` (Task 1).
- Produces: `context.city_link(url) -> str` (the trimmed link when it is `http(s)` on `toronto.ca` or a subdomain,
  else `""`); `context.APPLICATION_KEYS`, `APPLICATION_SOURCES`; `validate(doc)` checks an optional
  `"applications"` list and its `"applications_date"`. A site block is
  `{"id": "app:<smallest number>", "group", "numbers", "main", "centre_m": [x, y], "angle_deg", "width_m",
  "depth_m", "height_m", "base_m", "height_from", "applications": [{"number", "type", "status", "submitted",
  "address", "description", "source", "floor_area_m2", "url"}]}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/fetch/test_context.py` (add `import pytest` to its imports if it isn't there):

```python
def _apps_doc(sites, date="2026-10-09"):
    doc = ctx.finish(ctx.new({"centre": {"lat": 43.65, "lon": -79.38}, "radius_m": 150.0}, region="toronto",
                             terrain_source="flat"))
    doc["applications"] = sites
    if date is not None:
        doc["applications_date"] = date
    return doc


def _app_entry(number="A1", **over):
    entry = {"number": number, "type": "OZ", "status": "Under Review", "submitted": "2024-01-01",
             "address": "1 Main St", "description": "a 14-storey building", "source": "application",
             "floor_area_m2": 0.0, "url": "http://app.toronto.ca/AIC/index.do?folderRsn=abc"}
    entry.update(over)
    return entry


def _app_site(**over):
    site = {"id": "app:21 1 BLD", "group": "construction", "numbers": ["21 1 BLD", "A1"], "main": "21 1 BLD",
            "centre_m": [10.0, 5.0], "angle_deg": 12.5, "width_m": 30.0, "depth_m": 20.0, "height_m": 45.0,
            "base_m": -0.3, "height_from": "permit: 14 storeys",
            "applications": [_app_entry("21 1 BLD", type="Apartment Building", status="Inspection", source="permit",
                                        description="", floor_area_m2=1200.0, url=""),
                             _app_entry("A1")]}
    site.update(over)
    return site


def test_a_doc_with_application_sites_is_valid():
    other = _app_site(id="app:B", group="review", numbers=["B"], main="B", applications=[_app_entry("B")])
    assert ctx.validate(_apps_doc([_app_site(), other])) == []
    assert ctx.validate(_apps_doc([])) == []


@pytest.mark.parametrize("change, words", [
    ({"group": "rumoured"}, "unknown group"),
    ({"numbers": ["A1", "A1"]}, "distinct"),
    ({"main": "Z"}, "main application"),
    ({"centre_m": [1.0]}, "no centre"),
    ({"angle_deg": float("nan")}, "angle_deg"),
    ({"width_m": 0.0}, "width_m"),
    ({"height_from": ""}, "height is from"),
    ({"applications": []}, "do not match"),
    ({"id": "A1"}, "no id"),
])
def test_a_broken_application_site_is_named(change, words):
    problems = ctx.validate(_apps_doc([_app_site(**change)]))
    assert len(problems) == 1 and words in problems[0]


@pytest.mark.parametrize("change", [{"source": "rumour"}, {"url": "https://example.com/AIC"},
                                    {"floor_area_m2": -1.0}, {"description": None}, {"submitted": 20240101}])
def test_a_broken_application_entry_is_refused(change):
    site = _app_site()
    site["applications"][1].update(change)
    problems = ctx.validate(_apps_doc([site]))
    assert len(problems) == 1 and "do not match" in problems[0]


def test_two_sites_may_not_share_an_id_or_a_number():
    a = _app_site()
    b = _app_site(numbers=["A1", "B"], main="B", applications=[_app_entry("A1"), _app_entry("B")])
    problems = ctx.validate(_apps_doc([a, b]))
    assert "Application site id app:21 1 BLD is used twice." in problems
    assert "Application A1 is in two sites." in problems


def test_applications_need_their_day_and_must_be_a_list():
    day = "The applications need the day they were fetched, as YYYY-MM-DD."
    assert ctx.validate(_apps_doc([], date=None)) == [day]
    assert ctx.validate(_apps_doc([], date="9 Oct")) == [day]
    assert ctx.validate(_apps_doc({})) == ["The applications must be a list."]


@pytest.mark.parametrize("url, want", [
    ("http://app.toronto.ca/AIC/index.do?folderRsn=abc", "http://app.toronto.ca/AIC/index.do?folderRsn=abc"),
    ("https://secure.toronto.ca/x", "https://secure.toronto.ca/x"), ("https://toronto.ca/", "https://toronto.ca/"),
    (" https://www.toronto.ca/a ", "https://www.toronto.ca/a"),
    ("https://toronto.ca.evil.com/x", ""), ("https://eviltoronto.ca/x", ""), ("ftp://app.toronto.ca/x", ""),
    ("javascript:alert(1)", ""), ("", ""), (None, ""), ("http://[::1", "")])
def test_only_links_on_toronto_ca_are_kept(url, want):
    assert ctx.city_link(url) == want
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/fetch/test_context.py -q`
Expected: FAIL (`AttributeError: module 'ghosttown_fetch.context' has no attribute 'city_link'`, and the broken
sites validate clean).

- [ ] **Step 3: Implement**

In `ghosttown/ghosttown_fetch/context.py`:

Add to the module docstring, as its last paragraph: `Development application sites (design/development-applications.md
§4.4) come in an optional top-level "applications" list, with the day they were fetched as "applications_date".`

Imports become:

```python
import math
import re
import urllib.parse

from . import APPLICATION_GROUPS, BUILDING_KINDS, CREDITS, GROUND_KINDS, KINDS, SCHEMA, SOURCE_NAMES, TOOL
```

After `_MAX_PROBLEMS = 20` add:

```python
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
APPLICATION_KEYS = ("number", "type", "status", "submitted", "address", "description", "source", "url")
APPLICATION_SOURCES = ("application", "permit")
```

In `validate`, after the `lidar` check:

```python
    if "applications" in doc:
        problems += _applications_problems(doc)
```

Before `def _num(v):` add:

```python
def city_link(url):
    """`url`, trimmed, when it is an http(s) address on toronto.ca or one of its subdomains, else "": the only
    links the Site panel opens."""
    if not isinstance(url, str):
        return ""
    url = url.strip()
    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        return ""
    if parts.scheme in ("http", "https") and (host == "toronto.ca" or host.endswith(".toronto.ca")):
        return url
    return ""


def _text(v):
    return isinstance(v, str) and v.strip() != ""


def _xy(v):
    return isinstance(v, list) and len(v) == 2 and all(_num(c) for c in v)


def _entry_ok(a):
    return (isinstance(a, dict) and all(isinstance(a.get(k), str) for k in APPLICATION_KEYS)
            and _text(a["number"]) and a["source"] in APPLICATION_SOURCES
            and _num(a.get("floor_area_m2")) and a["floor_area_m2"] >= 0
            and (a["url"] == "" or city_link(a["url"]) == a["url"]))


def _application_problem(site):
    """What is wrong with one application site, as a phrase, or None."""
    if not isinstance(site, dict):
        return "an application site is not an object"
    sid = site.get("id")
    if not (_text(sid) and sid.startswith("app:") and len(sid) > 4):
        return "an application site has no id"
    if site.get("group") not in APPLICATION_GROUPS:
        return f"application site {sid} has an unknown group"
    numbers = site.get("numbers")
    if not (isinstance(numbers, list) and numbers and all(_text(n) for n in numbers)
            and len(set(numbers)) == len(numbers)):
        return f"application site {sid} has no list of distinct application numbers"
    if site.get("main") not in numbers:
        return f"application site {sid}'s main application is not one of its numbers"
    if not _xy(site.get("centre_m")):
        return f"application site {sid} has no centre"
    for key in ("angle_deg", "base_m"):
        if not _num(site.get(key)):
            return f"application site {sid}'s {key} is not a finite number"
    for key in ("width_m", "depth_m", "height_m"):
        if not (_num(site.get(key)) and site[key] > 0):
            return f"application site {sid}'s {key} is not a positive number"
    if not _text(site.get("height_from")):
        return f"application site {sid} doesn't say where its height is from"
    apps = site.get("applications")
    if not (isinstance(apps, list) and apps and all(_entry_ok(a) for a in apps)
            and sorted(a["number"] for a in apps) == sorted(numbers)):
        return f"application site {sid}'s applications do not match its numbers"
    return None


def _applications_problems(doc):
    sites = doc["applications"]
    if not isinstance(sites, list):
        return ["The applications must be a list."]
    problems, ids, owner = [], set(), {}
    for site in sites:
        problem = _application_problem(site)
        if problem:
            problems.append(problem[0].upper() + problem[1:] + ".")
            continue
        if site["id"] in ids:
            problems.append(f"Application site id {site['id']} is used twice.")
        ids.add(site["id"])
        for number in site["numbers"]:
            if owner.setdefault(number, site["id"]) != site["id"]:
                problems.append(f"Application {number} is in two sites.")
    date = doc.get("applications_date")
    if not (isinstance(date, str) and _DAY.fullmatch(date)):
        problems.append("The applications need the day they were fetched, as YYYY-MM-DD.")
    return problems
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/fetch/test_context.py -q`
Expected: PASS, `test_schema_modules_are_stdlib_only` included (it imports `context.py` with numpy, shapely and
Pillow blocked).

- [ ] **Step 5: Commit**

```bash
git add ghosttown/ghosttown_fetch/context.py tests/fetch/test_context.py
git commit -m "feat(fetch): context.json's development application sites are checked both ways; City links only

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Status points into sites with starting boxes

**Files:**
- Create: `ghosttown/ghosttown_fetch/applications.py`
- Create: `tests/fetch/fixtures/kingbay/applications.json.gz`, `tests/fetch/fixtures/kingbay/parcels.json.gz`
- Modify: `tests/fetch/fixtures/README.md`
- Test: `tests/fetch/test_applications.py`

**Interfaces:**
- Consumes: `mtm27.to_lonlat` and `boxfit` (Task 2), `ckan.day` (Task 3), `context.city_link` (Task 5),
  `buildings.LEVEL_M`, `buildings.SINK_M`, `geom.feature_geometry`, `geom.to_local`, `geom.polygons`,
  `geom.GRID_M`, `Frame.to_local(lon, lat)`, `terrain.min_under(polygon)` (existing).
- Produces:
  - `applications.features(answer, frame) -> [(geometry in local metres, properties)]` (an ArcGIS answer's
    features list in, Points and cleaned Polygons out)
  - `applications.status_point(number, source, group, kind, status, date, description="", address="",
    floor_area_m2=0.0, folderrsn="", unknown=None, url="")`
  - `applications.group_of(props)`, `map_point(props)`, `folder_of(value)`,
    `table_points(rows, frame, map_folders) -> [(Point, status point)]`, `height_of(description)`, `rank(group)`,
    `MAX_STOREYS = 120`
  - `applications.build(points, parcel_features, terrain, keep, now_ms, clip=None, more=()) ->
    {"blocks": [site block, sorted by id], "no_parcel": int, "unknown": [label]}`

- [ ] **Step 1: Copy the recorded King & Bay answers**

```bash
mkdir -p tests/fetch/fixtures/kingbay
git -C /Users/inscrip/code/BHPlus show 60d801e:tests/fixtures/site_context/kingbay_application.json.gz > tests/fetch/fixtures/kingbay/applications.json.gz
git -C /Users/inscrip/code/BHPlus show 60d801e:tests/fixtures/site_context/kingbay_parcel.json.gz > tests/fetch/fixtures/kingbay/parcels.json.gz
gunzip -t tests/fetch/fixtures/kingbay/*.json.gz
```

Expected: no output from `gunzip -t` (both files whole).

Append to `tests/fetch/fixtures/README.md`:

```markdown
- `kingbay/applications.json.gz`, `kingbay/parcels.json.gz`: the City of Toronto's development application points
  (`cot_geospatial11/FeatureServer/60`) and property boundaries (`cot_geospatial27/FeatureServer/36`) around King
  St W and Bay St, recorded on 2026-10-08 for BHPlus's Build Context (its `kingbay_application.json.gz` and
  `kingbay_parcel.json.gz`). Contains information licensed under the Open Government Licence – Toronto.
```

- [ ] **Step 2: Write the failing tests**

`tests/fetch/test_applications.py`:

```python
"""ghosttown_fetch.applications: the City's development applications as sites. Ported from BHPlus
tests/test_context_applications.py; Ghost Town has no subject-site rule, and each application carries its City
link instead of a Comments text."""
import gzip
import json
import math
import os

import pytest
import shapely
from shapely.geometry import Point
from shapely.geometry import box as rect

from ghosttown_fetch import applications, boxfit, mtm27
from ghosttown_fetch.frame import Frame
from ghosttown_fetch.geom import to_local
from ghosttown_fetch.terrain import FlatTerrain
from toronto_samples import LAT0, LON0, page, point, polygon, square

KINGBAY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "kingbay")


def _props(status="Under Review", group="Open", kind="OZ", **more):
    props = {"STATUS_DESC": status, "STATUS_GROUP": group, "FOLDERTYPE": kind}
    props.update(more)
    return props


@pytest.mark.parametrize("status, group", [
    ("Under Review", "review"), ("Under Review ", "review"), ("Hearing Scheduled", "review"),
    ("NOAC Issued", "approved"), ("Council Approved", "approved"), ("Decision Issued", "approved"),
    ("OMB Appeal", "appealed"), ("Appeal Dismissed", "appealed"), ("TLAB Appeal", "appealed")])
def test_each_open_label_falls_in_its_group(status, group):
    assert applications.group_of(_props(status)) == (group, None)


@pytest.mark.parametrize("props", [
    _props("Closed", group="Closed"), _props("Withdrawn", group="Closed"), _props("Refused"),
    _props("OMB Refused"), _props("Under Review", group=None), {}])
def test_closed_and_refused_applications_are_left_out(props):
    assert applications.group_of(props) == (None, None)


@pytest.mark.parametrize("kind", ["MV", "CO", "TLAB"])
def test_committee_of_adjustment_is_its_own_group_whatever_its_label(kind):
    assert applications.group_of(_props("Conditional Consent", kind=kind)) == ("coa", None)
    assert applications.group_of(_props("Something New", kind=kind)) == ("coa", None)
    assert applications.group_of(_props("Refused", kind=kind)) == (None, None)


def test_an_unknown_open_label_counts_as_under_review_and_is_named():
    assert applications.group_of(_props("Awaiting Something")) == ("review", "Awaiting Something")


@pytest.mark.parametrize("text, metres, said", [
    ("a 66-storey (232 metres including mechanical penthouse) mixed-use building, 14,778 square metres of office",
     232.0, "description: 232 m"),
    ("a 65-storey office-retail building with a height of 300 metres, and a 3-storey pavilion",
     300.0, "description: 300 m"),
    ("the 12-storey office building with a 65-storey mixed-use building that includes a 5-storey base building, "
     "for an overall building height of 222.3 metres", 222.3, "description: 222.3 m"),
    ("a 10-storey (34.5 m) building", 34.5, "description: 34.5 m"),
    ("Height: 45 m", 45.0, "description: 45 m"),
    ("The proposal is for  a 50 storey mixed use building 34,975 square metres of residential floor area",
     160.0, "description: 50 storeys"),
    ("Site Plan Approval for a 64-storey non-residential building having a gross floor area of 163,201.0 square "
     "metres.", 204.8, "description: 64 storeys"),
    ("a 1-storey addition", 3.2, "description: 1 storey"),
])
def test_the_height_comes_from_the_description(text, metres, said):
    got = applications.height_of(text)
    assert got[0] == pytest.approx(metres) and got[1] == said


@pytest.mark.parametrize("text", [
    "rear yard setback of 7.5 m", "a 500 m² addition", "a height of 1,222 m2", "1.5 storey dwelling",
    "a 400-storey tower", "nothing here", "", None])
def test_square_metres_and_setbacks_are_never_heights(text):
    assert applications.height_of(text) is None


@pytest.mark.parametrize("text, metres", [
    ("a 45-storey tower on a 6-storey base building, base building height of 21 metres", 144.0),
    ("a 40-storey tower with a streetwall height of 20 m", 128.0),
    ("an 8-storey building with a ground floor height of 4.5 m", 25.6),
    ("a building with a maximum height of 42 m, set back 120 m from the rail corridor", 42.0),
    ("a tower 155 m tall", 155.0),
    ("a building 30 metres in height", 30.0),
    ("a height of 1,500 m", None),
])
def test_only_a_whole_building_height_counts(text, metres):
    got = applications.height_of(text)
    assert (got is None) if metres is None else (got[0] == pytest.approx(metres))


def test_a_metre_height_beats_the_storeys():
    assert applications.height_of("a 50-storey tower with a height of 180 m")[0] == pytest.approx(180.0)


@pytest.mark.parametrize("text, metres, said", [
    ("Proposal to construct a six-storey apartment building with 10 dwelling units.", 19.2, "description: 6 storeys"),
    ("BUILD SIX (6) STOREY BUILDING WITH NINETEEN (19) RESIDENTIAL UNITS", 19.2, "description: 6 storeys"),
    ("Proposal to construct a 9 sty hospital with 3 levels of below grade parking.", 28.8, "description: 9 storeys"),
    ("a forty-five storey tower", 144.0, "description: 45 storeys"),
    ("a forty five storey tower and a three-storey podium", 144.0, "description: 45 storeys"),
    ("a new eight storey student residence", 25.6, "description: 8 storeys"),
    ("a seventeen-storey hotel", 54.4, "description: 17 storeys"),
])
def test_spelled_out_bracketed_and_abbreviated_storeys_count(text, metres, said):
    got = applications.height_of(text)
    assert got[0] == pytest.approx(metres) and got[1] == said


@pytest.mark.parametrize("text", ["5 styles of brick", "two 3-storey blocks and one more", "1.5 storey dwelling"])
def test_the_new_phrasings_do_not_misread(text):
    got = applications.height_of(text)
    assert got is None or got[1] == "description: 3 storeys"


# ------------------------------------------------------------------ sites --

NOW_MS = 1790000000.0 * 1000.0
P1, P2, P3 = rect(0, 0, 40, 30), rect(40, 0, 80, 30), rect(0, 30, 40, 60)
CIRCLE = Point(0.0, 0.0).buffer(150.0, quad_segs=64)


def _parcel(g, pid, kind="COMMON", expiry=None):
    return g, {"PARCELID": pid, "FEATURE_TYPE": kind, "DATE_EXPIRY": expiry}


PARCELS = [_parcel(P1, 1), _parcel(P2, 2), _parcel(P3, 3)]


def _point(x, y, number, status="Under Review", kind="OZ", submitted=1600000000000, text="", address="1 Main St"):
    return Point(x, y), {"APPLICATION_NUMBER": number, "STATUS_GROUP": "Open", "STATUS_DESC": status,
                         "FOLDERTYPE": kind, "SUBMIT_DATE": submitted, "FOLDERDESCRIPTION": text,
                         "FULL_ADDRESS": address}


def _build(points, parcels=PARCELS, terrain=None, keep=None, clip=None, more=()):
    return applications.build(points, parcels, terrain or FlatTerrain(), keep or (lambda p: True), NOW_MS,
                              clip=clip, more=more)


def _fp(block):
    return boxfit.footprint(*block["centre_m"], block["angle_deg"], block["width_m"], block["depth_m"])


def test_applications_sharing_a_parcel_are_one_site_and_the_most_live_one_colours_it():
    got = _build([_point(10, 10, "A1OZ", "Council Approved"), _point(20, 20, "B2SA", "OMB Appeal", kind="SA")])
    (block,) = got["blocks"]
    assert block["id"] == "app:A1OZ" and block["numbers"] == ["A1OZ", "B2SA"] and block["group"] == "appealed"
    assert _fp(block).within(P1.buffer(0.75))


def test_one_application_on_two_parcels_and_a_chain_through_them_join_into_one_site():
    got = _build([_point(10, 10, "A"), _point(50, 10, "A"), _point(60, 20, "B"), _point(10, 40, "C"),
                  _point(30, 50, "B")])
    (block,) = got["blocks"]
    assert block["numbers"] == ["A", "B", "C"]
    assert _fp(block).within(shapely.union_all([P1, P2, P3]).buffer(0.75))


def test_separate_parcels_are_separate_sites_sorted_by_id():
    got = _build([_point(50, 10, "Z9"), _point(10, 10, "A1")])
    assert [b["id"] for b in got["blocks"]] == ["app:A1", "app:Z9"]


def test_a_planning_application_beats_a_committee_of_adjustment_one_and_is_the_main_one():
    got = _build([_point(10, 10, "MV1", "Hearing Scheduled", kind="MV", submitted=1700000000000),
                  _point(12, 10, "OZ1", "Council Approved", submitted=1600000000000, text="a 20-storey tower")])
    (block,) = got["blocks"]
    assert block["group"] == "approved" and block["main"] == "OZ1"
    assert block["height_m"] == pytest.approx(64.0) and block["height_from"] == "description: 20 storeys"


def test_a_committee_of_adjustment_site_starts_low_whatever_its_description_says():
    (block,) = _build([_point(10, 10, "CO1", "Conditional Consent", kind="CO",
                              text="alter the existing 26-storey building")])["blocks"]
    assert block["group"] == "coa" and block["height_m"] == pytest.approx(3.2) and block["height_from"] == "C of A"


def test_the_newest_planning_application_that_states_a_height_sets_it():
    older = _point(10, 10, "OLD", submitted=1500000000000, text="a 40-storey tower")
    newer = _point(12, 10, "NEW", kind="SA", submitted=1650000000000, text="a 45-storey tower")
    silent = _point(14, 10, "NEWEST", kind="SA", submitted=1700000000000, text="site plan revisions")
    (block,) = _build([older, newer, silent])["blocks"]
    assert block["height_m"] == pytest.approx(144.0) and block["main"] == "NEWEST"
    assert block["height_from"] == "description: 45 storeys"
    assert [a["number"] for a in block["applications"]] == ["NEWEST", "NEW", "OLD"]       # newest first


def test_no_stated_height_starts_at_one_storey():
    (block,) = _build([_point(10, 10, "A", text="redevelop the site")])["blocks"]
    assert block["height_m"] == pytest.approx(3.2) and block["height_from"] == "not stated"


def test_each_application_is_listed_with_its_date_and_addresses():
    got = _build([_point(10, 10, "A", submitted=1629950400000, address="199 BAY ST"),
                  _point(50, 10, "A", submitted=1629950400000, address="25 KING ST W")])
    (app,) = got["blocks"][0]["applications"]
    assert app == {"number": "A", "type": "OZ", "status": "Under Review", "submitted": "2021-08-26",
                   "address": "199 BAY ST; 25 KING ST W", "description": "", "source": "application",
                   "floor_area_m2": 0.0, "url": ""}


def test_the_site_at_the_centre_gets_its_box_like_any_other():
    got = _build([_point(0.5, 0.5, "MINE"), _point(50, 10, "THEIRS")])
    assert [b["id"] for b in got["blocks"]] == ["app:MINE", "app:THEIRS"] and "on_site" not in got


def test_a_map_application_keeps_its_city_link_and_drops_any_other():
    mine = _point(10, 10, "A")
    mine[1]["AIC_URL"] = "http://app.toronto.ca/AIC/index.do?folderRsn=abc"
    theirs = _point(50, 10, "B")
    theirs[1]["AIC_URL"] = "https://example.com/AIC"
    links = {a["number"]: a["url"] for b in _build([mine, theirs])["blocks"] for a in b["applications"]}
    assert links == {"A": "http://app.toronto.ca/AIC/index.do?folderRsn=abc", "B": ""}


def test_a_point_in_no_parcel_is_left_out_and_counted_once_per_application():
    got = _build([_point(500, 500, "LOST"), _point(510, 500, "LOST"), _point(10, 10, "A")])
    assert [b["id"] for b in got["blocks"]] == ["app:A"] and got["no_parcel"] == 1


def test_only_points_inside_keep_count():
    got = _build([_point(10, 10, "A"), _point(50, 10, "A")], keep=lambda p: p.x < 40)
    (block,) = got["blocks"]
    assert _fp(block).within(P1.buffer(0.75))


def test_closed_and_refused_points_are_ignored_and_unknown_labels_are_named_once():
    closed = _point(10, 10, "A", "Closed")
    closed[1]["STATUS_GROUP"] = "Closed"
    got = _build([closed, _point(50, 10, "B", "Refused"), _point(10, 40, "C", "Odd"), _point(12, 40, "D", "Odd")])
    assert [b["id"] for b in got["blocks"]] == ["app:C"] and got["blocks"][0]["numbers"] == ["C", "D"]
    assert got["unknown"] == ["Odd"]


def test_a_condo_parcel_or_an_expired_one_is_not_the_site():
    parcels = [_parcel(rect(5, 5, 15, 15), 9, kind="CONDO"), _parcel(rect(0, 0, 20, 20), 8, expiry=1.0),
               _parcel(P1, 1)]
    (block,) = _build([_point(10, 10, "A")], parcels=parcels)["blocks"]
    assert block["width_m"] * block["depth_m"] > 1000.0                       # P1, not the condo or expired one


def test_the_base_is_the_lowest_ground_under_the_box_less_thirty_centimetres():
    class Slope:
        def min_under(self, polygon):
            return 0.1 * polygon.bounds[0]
    (block,) = _build([_point(10, 10, "A")], terrain=Slope())["blocks"]
    assert block["base_m"] == pytest.approx(0.1 * _fp(block).bounds[0] - 0.3, abs=1e-3)


def test_a_ravine_parcel_far_past_the_circle_gets_a_box_inside_the_circle():
    got = _build([_point(10, 10, "A")], parcels=[_parcel(rect(-1000, 0, 1000, 200), 7)], clip=CIRCLE)
    (block,) = got["blocks"]
    assert _fp(block).within(CIRCLE.buffer(0.75)) and _fp(block).area > 10000.0


def test_a_site_whose_clipped_shape_is_empty_is_skipped():
    got = _build([_point(510, 510, "A")], parcels=[_parcel(rect(500, 500, 520, 520), 7)], clip=CIRCLE)
    assert got["blocks"] == []


def _recorded(name):
    with gzip.open(os.path.join(KINGBAY, name), "rb") as f:
        return json.loads(f.read())["features"]


def test_king_and_bay_is_one_sixty_four_storey_site_over_two_parcels():
    frame = Frame(43.6487, -79.3806)
    points = applications.features(_recorded("applications.json.gz"), frame)
    parcels = applications.features(_recorded("parcels.json.gz"), frame)
    got = applications.build(points, parcels, FlatTerrain(), CIRCLE.contains, NOW_MS)
    (block,) = got["blocks"]
    assert block["id"] == "app:21204526STE13SA" and block["group"] == "review"
    assert block["height_m"] == pytest.approx(204.8) and block["base_m"] == pytest.approx(-0.3)
    two = shapely.union_all([g for g, p in parcels if p["PARCELID"] in (5471200, 5470818)])
    assert _fp(block).within(two.buffer(0.75))
    assert block["applications"][0]["url"] == \
        "http://app.toronto.ca/AIC/index.do?folderRsn=Ty0oJaST6ds4pVkViotbpA%3D%3D"
    assert got["no_parcel"] == 0 and got["unknown"] == []


def test_features_are_local_and_leave_out_what_has_no_geometry_or_no_area():
    answer = json.loads(page(square(0, 0, 10, PARCELID=1), point(5, 5, ADDRESS_POINT_ID=2),
                             polygon([(0, 0), (10, 0), (20, 0)], PARCELID=3),
                             {"type": "Feature", "geometry": None, "properties": {"PARCELID": 4}}))["features"]
    got = applications.features(answer, Frame(LAT0, LON0))
    assert [p for _, p in got] == [{"PARCELID": 1}, {"ADDRESS_POINT_ID": 2}]
    assert got[0][0].area == pytest.approx(100.0, rel=1e-3)
    assert got[1][0].coords[0] == pytest.approx((5.0, 5.0), abs=1e-3)


# ------------------------------------------------- permits and the table --

def _permit(x, y, number="21 123456 BLD", group="construction", text="", floor=0.0, date="2023-05-03",
            status="Inspection", kind="Apartment Building"):
    return Point(x, y), applications.status_point(number, "permit", group, kind, status, date, description=text,
                                                  address="1 Main St", floor_area_m2=floor)


def test_a_live_permit_beats_an_approved_application_and_leads_the_box():
    got = _build([_point(10, 10, "OZ1", "NOAC Issued", text="a 20-storey tower")],
                 more=[_permit(12, 12, text="a 21 storey apartment building")])
    (block,) = got["blocks"]
    assert block["group"] == "construction" and block["main"] == "21 123456 BLD"
    assert block["numbers"] == ["21 123456 BLD", "OZ1"]
    assert block["height_m"] == pytest.approx(67.2) and block["height_from"] == "permit: 21 storeys"
    assert [a["number"] for a in block["applications"]] == ["21 123456 BLD", "OZ1"]
    permit = block["applications"][0]
    assert permit == {"number": "21 123456 BLD", "type": "Apartment Building", "status": "Inspection",
                      "submitted": "2023-05-03", "address": "1 Main St", "description": "a 21 storey apartment building",
                      "source": "permit", "floor_area_m2": 0.0, "url": ""}


def test_a_recently_built_site_beats_an_application_under_review():
    got = _build([_point(10, 10, "SA1", "Under Review")],
                 more=[_permit(12, 12, "17 1 BLD", "built", status="Closed", date="2026-03-01")])
    (block,) = got["blocks"]
    assert block["group"] == "built" and block["main"] == "17 1 BLD"


def test_a_site_with_a_live_and_a_completed_permit_is_under_construction():
    got = _build([], more=[_permit(10, 10, "17 1 BLD", "built", text="a 6 storey building", status="Closed",
                                   date="2025-06-01"),
                           _permit(12, 12, "22 9 BLD", text="a 30 storey tower")])
    (block,) = got["blocks"]
    assert block["group"] == "construction" and block["numbers"] == ["17 1 BLD", "22 9 BLD"]
    assert block["main"] == "22 9 BLD" and block["height_m"] == pytest.approx(96.0)


def test_with_no_stated_height_a_construction_site_takes_its_applications_then_its_floor_area():
    (block,) = _build([_point(10, 10, "OZ1", "NOAC Issued", text="a 12-storey building")],
                      more=[_permit(12, 12, floor=50000.0)])["blocks"]
    assert block["height_from"] == "description: 12 storeys"
    (block,) = _build([], more=[_permit(12, 12, floor=4000.0)])["blocks"]
    storeys = math.ceil(4000.0 / (block["width_m"] * block["depth_m"]))
    assert block["height_from"] == "estimated from floor area: {0} storey{1}".format(storeys, "" if storeys == 1 else "s")
    assert block["height_m"] == pytest.approx(storeys * 3.2)
    (block,) = _build([], more=[_permit(12, 12)])["blocks"]
    assert block["height_from"] == "not stated" and block["height_m"] == pytest.approx(3.2)


def test_the_floor_area_estimate_is_at_least_one_storey_and_at_most_the_cap():
    (low,) = _build([], more=[_permit(12, 12, floor=1.0)])["blocks"]
    (high,) = _build([], more=[_permit(12, 12, floor=1e9)])["blocks"]
    assert low["height_m"] == pytest.approx(3.2)
    assert high["height_m"] == pytest.approx(applications.MAX_STOREYS * 3.2)


def test_permit_points_go_through_keep_like_the_map_points():
    assert _build([], more=[_permit(50, 10)], keep=lambda p: p.x < 40)["blocks"] == []


# --------------------------------------------------------------- the table --

FRAME = Frame(43.7615, -79.4111)


def _table_row(number="26 100001 NNY 23 SA", status="Under Review", x="311948.715", y="4846544.07",
               folder="9999999", kind="SA", submitted="2026-03-09T00:00:00"):
    return {"APPLICATION#": number, "APPLICATION_TYPE": kind, "STATUS": status, "DATE_SUBMITTED": submitted,
            "X": x, "Y": y, "FOLDERRSN": folder, "STREET_NUM": "4800", "STREET_NAME": "YONGE", "STREET_TYPE": "ST",
            "STREET_DIRECTION": " "}


def test_a_table_row_becomes_a_status_point_at_its_converted_place():
    ((g, sp),) = applications.table_points([_table_row()], FRAME, set())
    lon, lat = mtm27.to_lonlat(311948.715, 4846544.07)
    assert g.distance(to_local(Point(lon, lat), FRAME)) < 1e-6
    assert sp == applications.status_point("26100001NNY23SA", "application", "review", "SA", "Under Review",
                                           "2026-03-09", address="4800 YONGE ST", folderrsn="9999999")


def test_a_table_row_the_map_has_is_left_to_the_map():
    assert applications.table_points([_table_row(folder="4083248")], FRAME, {"4083248"}) == []


@pytest.mark.parametrize("status", ["Closed", "Refused", "OMB Refused", "Withdrawn"])
def test_closed_and_refused_table_rows_are_left_out(status):
    assert applications.table_points([_table_row(status=status)], FRAME, set()) == []


def test_table_statuses_are_trimmed_and_an_unknown_one_is_named():
    ((_, sp),) = applications.table_points([_table_row(status="Under Review ")], FRAME, set())
    assert sp["group"] == "review" and sp["unknown"] is None
    ((_, sp),) = applications.table_points([_table_row(status="Circulated")], FRAME, set())
    assert sp["group"] == "review" and sp["unknown"] == "Circulated"


@pytest.mark.parametrize("x, y", [("", "4846544.07"), (None, None), ("0", "0"), ("abc", "1"), ("nan", "4846544"),
                                  ("-5", "4846544")])
def test_table_rows_without_usable_coordinates_are_skipped(x, y):
    assert applications.table_points([_table_row(x=x, y=y)], FRAME, set()) == []


@pytest.mark.parametrize("submitted", [None, "", "09/03/2026", 20260309])
def test_a_table_row_with_an_unreadable_submission_date_is_skipped(submitted):
    assert applications.table_points([_table_row(submitted=submitted)], FRAME, set()) == []


def test_a_table_row_without_a_number_or_folder_is_skipped():
    assert applications.table_points([_table_row(number="  ")], FRAME, set()) == []
    assert applications.table_points([_table_row(folder=None)], FRAME, set()) == []


@pytest.mark.parametrize("value, folder", [(4083248, "4083248"), (4083248.0, "4083248"), ("5793154", "5793154"),
                                           (" 5793154 ", "5793154"), (None, ""), ("x1", ""), (True, "")])
def test_folder_of_reads_both_sources(value, folder):
    assert applications.folder_of(value) == folder


def test_an_unknown_table_label_reaches_the_build_result():
    more = applications.table_points([_table_row(status="Circulated", x="314092.389", y="4833631.921")],
                                     Frame(43.644570184, -79.384621957), set())
    parcel = (rect(-50, -50, 50, 50), {"PARCELID": 1, "FEATURE_TYPE": "COMMON", "DATE_EXPIRY": None})
    got = applications.build([], [parcel], FlatTerrain(), lambda p: True, NOW_MS, more=more)
    assert got["unknown"] == ["Circulated"] and got["blocks"][0]["numbers"] == ["26100001NNY23SA"]
```

- [ ] **Step 3: Run them to see them fail**

Run: `uv run pytest tests/fetch/test_applications.py -q`
Expected: FAIL with `ImportError: cannot import name 'applications'`.

- [ ] **Step 4: Implement**

`ghosttown/ghosttown_fetch/applications.py`:

```python
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
```

- [ ] **Step 5: Run them to see them pass**

Run: `uv run pytest tests/fetch/test_applications.py -q`
Expected: PASS. If the King & Bay test's footprint misses the two parcels by more than the 0.75 m slack, check
that `features()` kept both parcels (`PARCELID` 5471200 and 5470818) and that `_parcels` joined none of the
expired records: print `[(p["PARCELID"], p.get("DATE_EXPIRY")) for _, p in parcels]`.

- [ ] **Step 6: Commit**

```bash
git add ghosttown/ghosttown_fetch/applications.py tests/fetch/test_applications.py tests/fetch/fixtures/kingbay \
  tests/fetch/fixtures/README.md
git commit -m "feat(fetch): development applications, permits and table-only applications as sites with starting boxes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 7: The applications step in a build: every source, all or nothing

**Files:**
- Modify: `ghosttown/ghosttown_fetch/sources/toronto.py`
- Modify: `ghosttown/ghosttown_fetch/assemble.py`
- Modify: `tests/fetch/test_parcels.py:49`
- Test: `tests/fetch/test_assemble_applications.py`

**Interfaces:**
- Consumes: Tasks 1–6: `arcgis.query(..., max_age_days=)`, `toronto_applications.get_table/descriptions`,
  `toronto_permits.get_live/get_completed`, `construction.*`, `applications.features/table_points/folder_of/build`,
  `context.city_link`; existing `region.fetch_boundary(net)`, `toronto_massing.newest_edition(net)`,
  `geom.to_local`.
- Produces: `toronto.fetch_applications(net, lat, lon, radius_m)`, `toronto.fetch_address_points(net, lat, lon,
  radius_m)` (each the ArcGIS features list), `toronto.APPLICATION_FIELDS`, `toronto.ADDRESS_FIELDS`;
  `fetch_parcels` also asks for `DATE_EXPIRY`; `assemble(request, net, *, progress=None, now=None)` writes
  `doc["applications"]` (a list of site blocks) and `doc["applications_date"]` (`"YYYY-MM-DD"`) only when every
  source answered; its notes about them have code `"applications"`.

- [ ] **Step 1: Write the failing tests**

In `tests/fetch/test_parcels.py`, line 49 becomes:

```python
    assert form(data)["outFields"] == "OBJECTID,PARCELID,ADDRESS_NUMBER,LINEAR_NAME_FULL,DATE_EXPIRY"
```

`tests/fetch/test_assemble_applications.py`:

```python
"""assemble with Development applications ticked (design/development-applications.md §4): every source of the boxes
fetched as one step, written into context.json only when all of them answered."""
import datetime
import urllib.parse

import pytest

from ghosttown_fetch import DEFAULT_LAYERS
from ghosttown_fetch import context as ctx
from ghosttown_fetch import request as rq
from ghosttown_fetch.assemble import assemble
from ghosttown_fetch.frame import Frame
from ghosttown_fetch.net import SourceError
from ghosttown_fetch.sources import arcgis, toronto, toronto_applications, toronto_permits
from ckan_samples import answer, mtm27_xy
from fakes import FakeNet, form, router
from osm_samples import body, way
from osm_samples import square as osm_square
from tiff_samples import east_slope_tiff
from toronto_samples import LAT0, LON0, page, point, polygon, square
import photo_samples

NOW = datetime.datetime(2026, 10, 9, 12, 0).timestamp()
TODAY = "2026-10-09"
CITY = polygon([(-3000, -3000), (3000, -3000), (3000, 3000), (-3000, 3000)], AREA_NAME="Toronto")
FAR = polygon([(5000, 5000), (6000, 5000), (6000, 6000), (5000, 6000)], AREA_NAME="Elsewhere")
OSM = body(way(1, osm_square(0, 0, 10), {"building": "yes", "height": "20"}))
DOWN = SourceError("City of Toronto answered HTTP 503; try again in a minute.")
LOTS = [square(-20, -20, 40, OBJECTID=3, PARCELID=55),    # the mapped application and the live permit beside it
        square(60, -20, 40, OBJECTID=4, PARCELID=56),     # the application only the table has
        square(-20, 60, 40, OBJECTID=5, PARCELID=57)]     # the completed permit
APP = point(0, 0, OBJECTID=1, APPLICATION_NUMBER="25100001STE10OZ", FOLDERTYPE="OZ", FOLDERRSN=111,
            STATUS_GROUP="Open", STATUS_DESC="NOAC Issued", SUBMIT_DATE=1740000000000,
            FOLDERDESCRIPTION="a 10-storey building", FULL_ADDRESS="1 TEST ST",
            AIC_URL="http://app.toronto.ca/AIC/index.do?folderRsn=abc")


def _address(x, y, pid, number):
    return point(x, y, OBJECTID=pid, ADDRESS_POINT_ID=pid, LO_NUM=number, LINEAR_NAME="Test",
                 LINEAR_NAME_TYPE="St", LINEAR_NAME_DIR=None)


ADDRESSES = [_address(10, 10, 900, 5), _address(0, 80, 901, 9), _address(-10, 10, 902, 3)]


def _xy(x, y):
    return [f"{v:.3f}" for v in mtm27_xy(*Frame(LAT0, LON0).to_lonlat(x, y))]


def _row(number, kind, status, submitted, folder, x, y, text="", link=""):
    return {"APPLICATION#": number, "APPLICATION_TYPE": kind, "STATUS": status, "DATE_SUBMITTED": submitted,
            "X": x, "Y": y, "FOLDERRSN": folder, "STREET_NUM": "80", "STREET_NAME": "TEST", "STREET_TYPE": "ST",
            "STREET_DIRECTION": " ", "DESCRIPTION": text, "APPLICATION_URL": link}


TABLE = [_row("25 100001 STE 10 OZ", "OZ", "NOAC Issued", "2025-02-19T00:00:00", "111", "1", "1"),
         _row("26 200002 STE 10 SA", "SA", "Under Review", "2026-09-01T00:00:00", "222", *_xy(80.0, 0.0),
              text="a 12-storey building", link="http://app.toronto.ca/AIC/index.do?folderRsn=def")]


def _permit(number, geo, status, issued, completed=None, text="", kind="New Building", structure="Apartment Building"):
    return {"PERMIT_NUM": number, "REVISION_NUM": "00", "PERMIT_TYPE": kind, "STRUCTURE_TYPE": structure,
            "STATUS": status, "GEO_ID": geo, "STREET_NUM": "5", "STREET_NAME": "TEST", "STREET_TYPE": "ST",
            "STREET_DIRECTION": "", "ISSUED_DATE": issued, "COMPLETED_DATE": completed, "DESCRIPTION": text,
            "WORK": "New Building"}


LIVE = [_permit("24 111111 BLD", "900", "Inspection", "2024-05-01", text="a 21 storey apartment building"),
        _permit("24 222222 BLD", "902", "Permit Issued", "2024-06-01", kind="New Houses", structure="SFD - Detached")]
DONE = [_permit("19 333333 BLD", "901", "Closed", "2019-03-01", "2025-08-01", text="a 6 storey building"),
        _permit("18 444444 BLD", "901", "Closed", "2018-03-01", "2024-12-31")]
TABLES = {toronto_applications.RESOURCE: TABLE, toronto_permits.LIVE: LIVE, toronto_permits.DONE: DONE}


def _city(**overrides):
    table = {
        "FeatureServer/40/": page(CITY),
        "cot_geospatial11/FeatureServer/60/": page(APP),
        "cot_geospatial27/FeatureServer/101/": page(*ADDRESSES),
        "cot_geospatial27/FeatureServer/36/": page(*LOTS),
        "datastore_search": answer(TABLES),
        "package_show?id=3d-massing": DOWN,     # no massing: recently built reaches back to 1 January last year
        "FeatureServer/": page(),
    }
    table.update(photo_samples.ANSWERS)
    for key, value in overrides.items():    # an existing key keeps its place, so the catch-all stays after it
        table[key] = value
    return router(table)


def _req(tmp_path, layers=DEFAULT_LAYERS + ("applications",)):
    return rq.build(centre={"lat": LAT0, "lon": LON0}, radius_m=150, cache_dir=str(tmp_path / "c"),
                    out_dir=str(tmp_path / "o"), address="Test site", layers=layers)


def _run(tmp_path, layers=DEFAULT_LAYERS + ("applications",), **overrides):
    net = FakeNet({"toronto": _city(**overrides), "nrcan": east_slope_tiff(Frame(LAT0, LON0), half=200.0),
                   "osm": OSM})
    return assemble(_req(tmp_path, layers), net, now=NOW), net


def _notes(doc):
    return [n for n in doc["notes"] if n["code"] == "applications"]


def test_applications_permits_and_the_table_become_three_sites(tmp_path):
    doc, _ = _run(tmp_path)
    assert ctx.validate(doc) == [] and doc["applications_date"] == TODAY
    sites = {s["id"]: s for s in doc["applications"]}
    assert sorted(sites) == ["app:19 333333 BLD", "app:24 111111 BLD", "app:26200002STE10SA"]
    going_up = sites["app:24 111111 BLD"]
    assert going_up["group"] == "construction" and going_up["numbers"] == ["24 111111 BLD", "25100001STE10OZ"]
    assert going_up["height_from"] == "permit: 21 storeys"
    built = sites["app:19 333333 BLD"]
    assert built["group"] == "built" and built["height_from"] == "permit: 6 storeys"
    table = sites["app:26200002STE10SA"]
    assert table["group"] == "review" and table["height_from"] == "description: 12 storeys"
    assert table["applications"][0]["url"] == "http://app.toronto.ca/AIC/index.do?folderRsn=def"
    texts = [n["text"] for n in _notes(doc)]
    assert "1 development application was placed from the City's applications table, which its map doesn't show " \
           "yet." in texts
    assert "1 building permit for new houses around the site was left out." in texts
    assert all(n["level"] == "info" for n in _notes(doc))


def test_recently_built_reaches_back_to_the_massing_year(tmp_path):
    doc, _ = _run(tmp_path)
    numbers = {n for s in doc["applications"] for n in s["numbers"]}
    assert "18 444444 BLD" not in numbers               # completed 2024-12-31, before 1 January 2025


def test_unticked_applications_ask_the_city_for_none_of_it(tmp_path):
    doc, net = _run(tmp_path, layers=DEFAULT_LAYERS)
    assert "applications" not in doc and "applications_date" not in doc and _notes(doc) == []
    assert not any("datastore_search" in url or "FeatureServer/60/" in url or "FeatureServer/101/" in url
                   for url, _, _ in net.calls)


@pytest.mark.parametrize("key, words", [
    ("cot_geospatial11/FeatureServer/60/", "the City's development applications map"),
    ("cot_geospatial27/FeatureServer/101/", "the City's address points"),
    ("cot_geospatial27/FeatureServer/36/", "the City's property boundaries"),
])
def test_a_city_layer_that_fails_leaves_the_boxes_alone(tmp_path, key, words):
    doc, _ = _run(tmp_path, **{key: DOWN})
    assert "applications" not in doc and "applications_date" not in doc
    (note,) = _notes(doc)
    assert note["level"] == "warn" and words in note["text"] and "left as they are" in note["text"]


def _ckan_down(resource, only=None):
    tables = answer(TABLES)

    def serve(url, data):
        text = urllib.parse.unquote_plus(url)
        if resource in url and (only is None or only in text):
            return DOWN
        return tables(url, data)
    return serve


@pytest.mark.parametrize("resource, only, words", [
    (toronto_applications.RESOURCE, None, "the City's development applications table"),
    (toronto_applications.RESOURCE, "DESCRIPTION", "the City's development applications table"),
    (toronto_permits.LIVE, None, "the City's building permits"),
    (toronto_permits.DONE, None, "the City's building permits"),
])
def test_an_open_data_table_that_fails_leaves_the_boxes_alone(tmp_path, resource, only, words):
    doc, _ = _run(tmp_path, datastore_search=_ckan_down(resource, only))
    assert "applications" not in doc
    (note,) = _notes(doc)
    assert note["level"] == "warn" and words in note["text"]


def test_outside_toronto_the_applications_are_not_asked_for(tmp_path):
    doc, net = _run(tmp_path, **{"FeatureServer/40/": page(FAR)})
    assert "applications" not in doc
    (note,) = _notes(doc)
    assert note["level"] == "info" and "City of Toronto only" in note["text"]
    assert not any("datastore_search" in url for url, _, _ in net.calls)


def test_parcels_are_fetched_for_the_boxes_even_when_lot_lines_are_unticked(tmp_path):
    layers = tuple(layer for layer in DEFAULT_LAYERS if layer != "parcels") + ("applications",)
    doc, net = _run(tmp_path, layers=layers)
    assert len(doc["applications"]) == 3 and not any(el["kind"] == "parcel" for el in doc["elements"])
    assert sum("FeatureServer/36/" in url for url, _, _ in net.calls) == 1


def test_the_lot_lines_parcels_serve_the_boxes_too(tmp_path):
    _, net = _run(tmp_path)
    assert sum("FeatureServer/36/" in url for url, _, _ in net.calls) == 1


def test_the_city_layers_ask_for_what_the_boxes_read_and_keep_it_as_long_as_it_lasts(tmp_path):
    _, net = _run(tmp_path)
    forms = {url: form(data) for url, _, data in net.calls if data}
    ages = {url: age for (url, _, _), age in zip(net.calls, net.ages)}
    apps, addresses = arcgis.layer_url("cot_geospatial11", 60), arcgis.layer_url("cot_geospatial27", 101)
    assert forms[apps]["outFields"] == toronto.APPLICATION_FIELDS and ages[apps] == 1
    assert forms[addresses]["outFields"] == toronto.ADDRESS_FIELDS and ages[addresses] == 7
    assert "DATE_EXPIRY" in forms[arcgis.layer_url("cot_geospatial27", 36)]["outFields"].split(",")


def test_the_applications_stage_comes_in_order(tmp_path):
    stages = []
    net = FakeNet({"toronto": _city(), "nrcan": east_slope_tiff(Frame(LAT0, LON0), half=200.0), "osm": OSM})
    assemble(_req(tmp_path), net, progress=lambda stage, pct: stages.append(pct), now=NOW)
    assert stages == sorted(stages) and 72 in stages
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/fetch/test_assemble_applications.py tests/fetch/test_parcels.py -q`
Expected: FAIL (`assemble() got an unexpected keyword argument 'now'`, the parcel fields).

- [ ] **Step 3: Implement the City layers**

In `ghosttown/ghosttown_fetch/sources/toronto.py`, `fetch_parcels` asks for the parcels' expiry too (the boxes join
only current parcels):

```python
def fetch_parcels(net, lat, lon, radius_m):
    """Lot lines only: CONDO parcels overlap the COMMON ones they sit on. DATE_EXPIRY tells a current parcel from
    a retired one, which the development application boxes need."""
    return arcgis.query(net, *PARCELS, arcgis.radius_params(
        lat, lon, radius_m, out_fields="OBJECTID,PARCELID,ADDRESS_NUMBER,LINEAR_NAME_FULL,DATE_EXPIRY",
        where="FEATURE_TYPE = 'COMMON'"))
```

and at the end of the file:

```python
APPLICATIONS = ("cot_geospatial11", 60)   # the IBMS Application Information Centre's development application points
APPLICATION_FIELDS = ("OBJECTID,APPLICATION_NUMBER,FOLDERTYPE,FOLDERRSN,STATUS_GROUP,STATUS_DESC,SUBMIT_DATE,"
                      "FOLDERDESCRIPTION,FULL_ADDRESS,AIC_URL")
APPLICATIONS_MAX_AGE_DAYS = 1             # the City updates them daily, and a rebuild must show today's statuses
ADDRESSES = (CITY, 101)                   # address points: where a building permit is
ADDRESS_FIELDS = "OBJECTID,ADDRESS_POINT_ID,LO_NUM,LINEAR_NAME,LINEAR_NAME_TYPE,LINEAR_NAME_DIR"
ADDRESSES_MAX_AGE_DAYS = 7                # a new building's address points come with it


def fetch_applications(net, lat, lon, radius_m):
    """Every development application point in the circle: one per address per application, open or closed."""
    return arcgis.query(net, *APPLICATIONS, arcgis.radius_params(lat, lon, radius_m, out_fields=APPLICATION_FIELDS),
                        max_age_days=APPLICATIONS_MAX_AGE_DAYS)


def fetch_address_points(net, lat, lon, radius_m):
    """Every City address point in the circle."""
    return arcgis.query(net, *ADDRESSES, arcgis.radius_params(lat, lon, radius_m, out_fields=ADDRESS_FIELDS),
                        max_age_days=ADDRESSES_MAX_AGE_DAYS)
```

- [ ] **Step 4: Implement the applications step**

In `ghosttown/ghosttown_fetch/assemble.py`:

Add to the module docstring, as its last sentences: `In Toronto, with Development applications asked for, the
City's application points, applications table, building permits, address points and parcels become the
development application sites, written only when every one of those sources answered, so a build that couldn't
look at them all leaves the boxes alone.`

Imports become (keep every existing name):

```python
import datetime
import os
import time

import numpy as np
import shapely
from shapely.geometry import Point

from . import (BUILDING_KINDS, applications, buildings, construction, fitted_roofs, ground, lidar_roofs, parcels,
               region, survey, trees)
from . import context as ctx
from . import terrain as terrain_mod
from .frame import Frame
from .geom import to_local
from .net import SourceError
from .sources import (ontario_lidar, osm, toronto, toronto_applications, toronto_massing, toronto_permits,
                      toronto_photo)
```

After `_fitted` add:

```python
APPLICATIONS_STAGE = "Development applications"
APPLICATIONS_FAILED = "Development applications weren't refreshed, so any boxes were left as they are: {reason}"
NO_APPLICATIONS = "Development applications are fetched for sites in the City of Toronto only."
APPLICATIONS_UNHANDLED = "a parcel shape couldn't be handled."
APPLICATION_SOURCES = {"boundary": "the City of Toronto boundary",
                       "map": "the City's development applications map",
                       "parcels": "the City's property boundaries", "addresses": "the City's address points",
                       "table": "the City's development applications table",
                       "permits": "the City's building permits"}
NOTE_TABLE = ("{n} development application{s} {were} placed from the City's applications table, which its map "
              "doesn't show yet.")
NOTE_HOUSES = "{n} building permit{s} for new houses around the site {were} left out."
NOTE_UNPLACED = ("{n} building permit{s} around the site couldn't be placed: the City's address points don't have "
                 "{its} address{es}.")
NOTE_NO_PARCEL = "{n} development application{s} {were} left out: not inside any parcel."
NOTE_STATUS = ("The City gave {labels} as a development application status, which Ghost Town doesn't know yet, so "
               "it is shown as Under review.")


def _counted(n):
    """The words a note about `n` things reads: n, s, were, its, es."""
    one = n == 1
    return {"n": n, "s": "" if one else "s", "were": "was" if one else "were", "its": "its" if one else "their",
            "es": "" if one else "es"}


def _named(what, fetch):
    """fetch(), its failure said as from `what` (APPLICATION_SOURCES), so the note names the source."""
    try:
        return fetch()
    except SourceError as e:
        raise SourceError(f"{APPLICATION_SOURCES[what]} couldn't be fetched ({str(e).rstrip('.')}).") from e


def _massing_year(net, year, today):
    """The 3D Massing edition recently built reaches back to: the one this build used, else the newest the City
    lists, else last year."""
    if year:
        return int(year)
    try:
        return int(toronto_massing.newest_edition(net).year)
    except (SourceError, ValueError, KeyError, TypeError):
        return today.year - 1


def _applications(doc, net, frame, radius, terrain, parcel_answer, massing_year, now, progress):
    """The development application sites (design/development-applications.md §4), written as context.json's
    "applications" only when every source answered: otherwise one warning and no list, so the add-on leaves the
    boxes as they are. Ported from BHPlus assemble._applications (60d801e)."""
    progress(APPLICATIONS_STAGE, 72)
    today = datetime.date.fromtimestamp(now)
    iso = today.isoformat()
    lat, lon = frame.lat0, frame.lon0
    circle = Point(0.0, 0.0).buffer(radius, quad_segs=64)
    try:
        boundary = _named("boundary", lambda: region.fetch_boundary(net))
        map_answer = _named("map", lambda: toronto.fetch_applications(net, lat, lon, radius))
        if parcel_answer is None:
            parcel_answer = _named("parcels", lambda: toronto.fetch_parcels(net, lat, lon, radius))
        address_answer = _named("addresses", lambda: toronto.fetch_address_points(net, lat, lon, radius))
        table = _named("table", lambda: toronto_applications.get_table(net, iso))
        year = _massing_year(net, massing_year, today)
        live_rows = _named("permits", lambda: toronto_permits.get_live(
            net, construction.years_before(iso, construction.LIVE_YEARS), iso))
        done_rows = _named("permits", lambda: toronto_permits.get_completed(net, f"{year}-01-01", iso))
        city = to_local(boundary, frame)
        shapely.prepare(city)
        shapely.prepare(circle)

        def keep(g):
            return circle.contains(g) and city.contains(g)

        map_points = applications.features(map_answer, frame)
        folders = {applications.folder_of(p.get("FOLDERRSN")) for _, p in map_points} - {""}
        from_table = [(g, sp) for g, sp in applications.table_points(table, frame, folders) if keep(g)]
        described = _named("table", lambda: toronto_applications.descriptions(
            net, {sp["folderrsn"] for _, sp in from_table}, iso))
        for _, sp in from_table:
            text, link = described.get(sp["folderrsn"], ("", ""))
            sp["description"], sp["url"] = text, ctx.city_link(link)
        addresses = construction.Addresses(applications.features(address_answer, frame))
        live, live_houses, live_lost = construction.points(construction.live(live_rows, iso), "construction",
                                                           addresses, keep)
        done, done_houses, done_lost = construction.points(construction.completed(done_rows, year), "built",
                                                           addresses, keep)
        found = applications.build(map_points, applications.features(parcel_answer, frame), terrain, keep,
                                   now * 1000.0, clip=circle, more=from_table + live + done)
    except SourceError as e:
        ctx.note(doc, "warn", "applications", APPLICATIONS_FAILED.format(reason=str(e)))
        return
    except shapely.errors.ShapelyError:
        ctx.note(doc, "warn", "applications", APPLICATIONS_FAILED.format(reason=APPLICATIONS_UNHANDLED))
        return
    doc["applications"] = found["blocks"]
    doc["applications_date"] = iso
    ctx.add_source(doc, "toronto")
    boxed = {n for b in found["blocks"] for n in b["numbers"]}
    for count, text in ((len({sp["number"] for _, sp in from_table} & boxed), NOTE_TABLE),
                        (live_houses + done_houses, NOTE_HOUSES), (live_lost + done_lost, NOTE_UNPLACED),
                        (found["no_parcel"], NOTE_NO_PARCEL)):
        if count:
            ctx.note(doc, "info", "applications", text.format(**_counted(count)))
    if found["unknown"]:
        labels = ", ".join(f'"{label}"' for label in found["unknown"])
        ctx.note(doc, "info", "applications", NOTE_STATUS.format(labels=labels))
```

In `assemble`:
1. The signature becomes `def assemble(request, net, *, progress=None, now=None):` and its first lines
   `progress = progress or (lambda stage, pct: None)` and `now = time.time() if now is None else now`.
2. `pieces = {}` becomes `pieces, massing_year, parcel_answer = {}, None, None`.
3. In the City buildings branch, after `how, data, year = found`, add `massing_year = year if how == "massing" else None`.
4. In the City parcels branch, inside `if found is not None:`, first add `parcel_answer = found`.
5. Right after the `NothingFetched` check and before the `photo` block, add:

```python
    if "applications" in layers:
        if where == "toronto":
            _applications(doc, net, frame, radius, terrain, parcel_answer, massing_year, now, progress)
        else:
            ctx.note(doc, "info", "applications", NO_APPLICATIONS)
```

- [ ] **Step 5: Run the whole fetcher suite**

Run: `uv run pytest -q`
Expected: all pass. `test_the_applications_stage_comes_in_order` pins 72 between the parcels (65) and the photo
(75).

- [ ] **Step 6: Commit**

```bash
git add ghosttown/ghosttown_fetch/sources/toronto.py ghosttown/ghosttown_fetch/assemble.py \
  tests/fetch/test_parcels.py tests/fetch/test_assemble_applications.py
git commit -m "feat(fetch): a build with Development applications ticked writes the sites, only when every source answered

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: What a build does to each box, the box's shape, and the report line

**Files:**
- Create: `ghosttown/ghosttown_fetch/app_boxes.py`
- Test: `tests/fetch/test_app_boxes.py`

**Interfaces:**
- Consumes: `APPLICATION_GROUPS`, `GROUP_LABELS` (Task 1), `Frame` (existing).
- Produces:
  - `app_boxes.CLOSED = "closed"`, `LABELS` (the group labels plus `"closed": "Closed"`), `COLOURS_SRGB`,
    `ALPHA = 0.7`, `BOX_FACES`, `PERMIT_GROUPS`
  - `box_verts(site) -> [[x, y, z] × 8]` (the box in its own axes, origin at its base centre)
  - `placement(site) -> ([x, y, base], [0, 0, angle in radians])`
  - `touched(placed, now) -> bool`, where each is `{"location": [3], "rotation": [3] radians, "scale": [3],
    "verts": [[3], ...], "other": bool}` or None
  - `shift(old_centre, old_ground, new_centre, new_ground) -> (dx, dy, dz)`
  - `plan(sites, boxes, deleted, radius_m) -> {"looked", "place", "update", "close", "remove", "keep", "deleted",
    "left"}`: `boxes` are dicts with at least `numbers`, `touched`, `closed`, `centre_m`, oldest first; `deleted`
    entries are `{"numbers", "centre_m"}`; `update` and `left` hold `(box, site)` pairs
  - `summary(sites, outcome, date) -> str`

- [ ] **Step 1: Write the failing tests**

`tests/fetch/test_app_boxes.py`:

```python
"""ghosttown_fetch.app_boxes: what a build does to each development application box. The planner's rules are
ported from BHPlus tests/test_site_applications_boxes.py; Ghost Town has no pinning, no other family's types and no
Align, and an untouched box takes its site's new starting box (design §2, decision 4)."""
import math

import pytest

from ghosttown_fetch import app_boxes
from ghosttown_fetch.frame import Frame


def _site(number, *more, group="review", centre=(10.0, 0.0), w=30.0, d=20.0, h=45.0, angle=0.0,
          source="application"):
    numbers = sorted((number,) + more)
    return {"id": "app:" + numbers[0], "group": group, "numbers": numbers, "main": number,
            "centre_m": list(centre), "angle_deg": angle, "width_m": w, "depth_m": d, "height_m": h, "base_m": -0.3,
            "height_from": "not stated",
            "applications": [{"number": n, "type": "OZ", "status": "Under Review", "submitted": "2024-01-01",
                              "address": "1 Main St", "description": "", "source": source, "floor_area_m2": 0.0,
                              "url": ""} for n in numbers]}


def _box(*numbers, centre=(10.0, 0.0), touched=False, closed=False):
    return {"numbers": list(numbers), "centre_m": list(centre), "touched": touched, "closed": closed}


def _gone(*numbers, centre=(10.0, 0.0)):
    return {"numbers": list(numbers), "centre_m": list(centre)}


def _only(got, **expected):
    for key in ("place", "update", "close", "remove", "keep", "deleted", "left"):
        assert got[key] == expected.get(key, []), key


def test_a_new_site_gets_a_box():
    site = _site("A")
    got = app_boxes.plan([site], [], [], 300)
    _only(got, place=[site])
    assert got["looked"] is True


def test_a_matching_box_is_updated():
    box, site = _box("A"), _site("A", group="approved", centre=(50.0, 5.0))
    _only(app_boxes.plan([site], [box], [], 300), update=[(box, site)])


def test_a_box_matched_through_any_number_follows_a_merged_site():
    box, site = _box("A"), _site("A", "B")
    _only(app_boxes.plan([site], [box], [], 300), update=[(box, site)])


def test_an_untouched_box_whose_applications_closed_is_removed():
    box = _box("A")
    _only(app_boxes.plan([], [box], [], 300), remove=[box])


def test_a_changed_box_whose_applications_closed_turns_closed():
    box = _box("A", touched=True)
    _only(app_boxes.plan([], [box], [], 300), close=[box])


def test_a_box_already_closed_is_left_alone():
    box = _box("A", touched=True, closed=True)
    _only(app_boxes.plan([], [box], [], 300), keep=[box])


def test_a_box_outside_this_builds_circle_is_kept():
    box = _box("A", centre=(400.0, 0.0))
    _only(app_boxes.plan([], [box], [], 300), keep=[box])


def test_a_build_that_did_not_look_changes_no_box_and_forgets_nothing():
    box, gone = _box("A"), _gone("B")
    got = app_boxes.plan(None, [box], [gone], 300)
    _only(got, keep=[box], deleted=[gone])
    assert got["looked"] is False


def test_a_deleted_box_stays_deleted_until_its_applications_close():
    gone = _gone("A")
    _only(app_boxes.plan([_site("A")], [], [gone], 300), deleted=[gone])
    _only(app_boxes.plan([], [], [gone], 300))                               # closed: forgotten


def test_a_deleted_box_outside_this_builds_circle_stays_deleted():
    gone = _gone("A", centre=(400.0, 0.0))
    _only(app_boxes.plan([], [], [gone], 300), deleted=[gone])


def test_one_site_two_boxes_the_changed_one_wins_and_the_other_is_left():
    old, edited = _box("A"), _box("A", touched=True)
    site = _site("A")
    _only(app_boxes.plan([site], [old, edited], [], 300), update=[(edited, site)], left=[(old, site)])


def test_one_site_two_untouched_boxes_the_older_wins():
    old, copy = _box("A"), _box("A")
    site = _site("A")
    _only(app_boxes.plan([site], [old, copy], [], 300), update=[(old, site)], left=[(copy, site)])


def test_one_box_split_into_two_sites_follows_the_first_and_the_other_gets_a_new_box():
    box = _box("A", "B")
    first, second = _site("A"), _site("B", centre=(60.0, 0.0))
    _only(app_boxes.plan([first, second], [box], [], 300), update=[(box, first)], place=[second])


def _permit_site(group="construction", centre=(12.0, 1.0)):
    return _site("21 1 BLD", group=group, centre=centre, source="permit")


def test_an_edited_box_whose_application_closed_follows_the_permit_on_its_spot():
    box, site = _box("A", touched=True), _permit_site()
    _only(app_boxes.plan([site], [box], [], 300), update=[(box, site)])


def test_an_untouched_box_follows_it_too_rather_than_a_second_box_beside_it():
    box, site = _box("A"), _permit_site(group="built")
    _only(app_boxes.plan([site], [box], [], 300), update=[(box, site)])


def test_the_spot_is_the_permit_sites_turned_rectangle():
    box = _box("A", centre=(12.0, 12.0))                    # on the site's box only when it is turned 90°
    turned = _site("21 1 BLD", group="construction", centre=(12.0, 1.0), w=30.0, d=4.0, angle=90.0, source="permit")
    _only(app_boxes.plan([turned], [box], [], 300), update=[(box, turned)])
    flat = _site("21 1 BLD", group="construction", centre=(12.0, 1.0), w=30.0, d=4.0, angle=0.0, source="permit")
    _only(app_boxes.plan([flat], [box], [], 300), place=[flat], remove=[box])


def test_only_a_construction_or_built_site_takes_over_a_box_by_its_spot():
    box, site = _box("A"), _site("B", centre=(12.0, 1.0))
    _only(app_boxes.plan([site], [box], [], 300), place=[site], remove=[box])


def test_a_box_a_number_already_matched_is_not_taken_by_a_permit_site():
    box = _box("A")
    mine, permit = _site("A"), _permit_site()
    _only(app_boxes.plan([mine, permit], [box], [], 300), update=[(box, mine)], place=[permit])


def test_a_deleted_box_on_the_spot_keeps_the_permit_site_away():
    gone, site = _gone("A"), _permit_site()
    _only(app_boxes.plan([site], [], [gone], 300), deleted=[gone])


PLACED = {"location": [10.0, 0.0, -0.3], "rotation": [0.0, 0.0, 0.5], "scale": [1.0, 1.0, 1.0],
          "verts": [list(v) for v in app_boxes.box_verts(_site("A"))], "other": False}


def _now(**change):
    now = {"location": list(PLACED["location"]), "rotation": list(PLACED["rotation"]),
           "scale": list(PLACED["scale"]), "verts": [list(v) for v in PLACED["verts"]], "other": False}
    now.update(change)
    return now


def test_touched_ignores_float_rounding():
    assert app_boxes.touched(PLACED, _now(location=[10.0000004, 0.0, -0.3000003], rotation=[0.0, 0.0, 0.5000001]))\
        is False


@pytest.mark.parametrize("change", [
    {"location": [10.002, 0.0, -0.3]}, {"rotation": [0.0, 0.0, 0.5 + math.radians(0.1)]},
    {"scale": [1.001, 1.0, 1.0]}, {"other": True}])
def test_touched_reads_a_move_a_turn_a_scale_and_a_parent(change):
    assert app_boxes.touched(PLACED, _now(**change)) is True


def test_touched_reads_an_edit_mode_change():
    verts = [list(v) for v in PLACED["verts"]]
    verts[4][2] += 0.5                                       # a top corner pulled up
    assert app_boxes.touched(PLACED, _now(verts=verts)) is True
    assert app_boxes.touched(PLACED, _now(verts=verts[:7])) is True


def test_a_full_turn_is_no_turn_and_nothing_to_compare_counts_as_changed():
    assert app_boxes.touched(PLACED, _now(rotation=[0.0, 0.0, 0.5 + 2 * math.pi])) is False
    assert app_boxes.touched(None, _now()) is True and app_boxes.touched(PLACED, None) is True


def _volume(verts, faces):
    total = 0.0
    for f in faces:
        a = verts[f[0]]
        for i in range(1, len(f) - 1):
            b, c = verts[f[i]], verts[f[i + 1]]
            total += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
                      + a[2] * (b[0] * c[1] - b[1] * c[0]))
    return total / 6.0


def test_the_box_is_closed_outward_and_as_big_as_the_site():
    verts, faces = app_boxes.box_verts(_site("A", w=30.0, d=20.0, h=45.0)), app_boxes.BOX_FACES
    assert _volume(verts, faces) == pytest.approx(30.0 * 20.0 * 45.0)
    edges = [(f[i], f[(i + 1) % 4]) for f in faces for i in range(4)]
    assert sorted(edges) == sorted((b, a) for a, b in edges)            # every edge once each way: closed


def test_the_box_stands_on_its_base_turned_to_its_angle():
    location, rotation = app_boxes.placement(_site("A", centre=(5.0, 6.0), angle=30.0))
    assert location == [5.0, 6.0, -0.3] and rotation == pytest.approx([0.0, 0.0, math.radians(30.0)])


def test_a_new_centre_carries_a_box_to_the_same_real_place():
    old = {"lat": 43.65, "lon": -79.38}
    lon, lat = Frame(43.65, -79.38).to_lonlat(100.0, 0.0)
    dx, dy, dz = app_boxes.shift(old, 84.7, {"lat": lat, "lon": lon}, 83.2)
    assert (dx, dy) == pytest.approx((-100.0, 0.0), abs=1e-6) and dz == pytest.approx(1.5)


def test_the_same_centre_or_flat_ground_moves_nothing():
    c = {"lat": 43.65, "lon": -79.38}
    assert app_boxes.shift(c, None, c, 80.0) == pytest.approx((0.0, 0.0, 0.0))


def test_the_summary_counts_sites_by_status_and_says_what_changed():
    sites = [_permit_site(), _site("A", group="review"), _site("B", "C", group="coa", centre=(80.0, 0.0))]
    outcome = {"looked": True, "update": [(_box("A", touched=True), sites[1])], "remove": [_box("X")],
               "close": [_box("Y", touched=True)], "place": [], "keep": [], "deleted": [], "left": []}
    assert app_boxes.summary(sites, outcome, "2026-10-09") == (
        "Development applications (City of Toronto, 2026-10-09): 3 sites from 3 applications and 1 building permit: "
        "1 under construction, 1 under review, 1 C of A. 1 box kept at the size you gave it. 1 closed box removed. "
        "1 turned grey (Closed).")


def test_the_summary_of_a_quiet_site():
    assert app_boxes.summary([], app_boxes.plan([], [], [], 300), "2026-10-09") == \
        "Development applications (City of Toronto, 2026-10-09): none around the site."
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/fetch/test_app_boxes.py -q`
Expected: FAIL with `ImportError: cannot import name 'app_boxes'`.

- [ ] **Step 3: Implement**

`ghosttown/ghosttown_fetch/app_boxes.py`:

```python
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
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/fetch/test_app_boxes.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ghosttown/ghosttown_fetch/app_boxes.py tests/fetch/test_app_boxes.py
git commit -m "feat(fetch): what a build does to each application box, its shape, and the report line

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 9: The boxes in Blender

**Files:**
- Modify: `ghosttown/materials.py`
- Create: `ghosttown/site_apps.py`
- Modify: `ghosttown/scene_build.py` (`build`, module docstring)
- Modify: `ghosttown/ops.py` (`import_into_scene`)
- Test: `tests/blender/test_site_apps.py`

**Interfaces:**
- Consumes: `app_boxes.*` (Task 8); a validated context doc with optional `applications`, `applications_date`
  (Tasks 5, 7).
- Produces:
  - `materials.application_name(group) -> str`, `materials.application_material(group) -> Material`
  - `site_apps.COLL_PREFIX = "Applications · "`, `SITE_PROP = "ctx_apps"`, `BOX_SITE = "ctx_app_site"`
  - `site_apps.find(scene, label) -> Collection | None`, `detach(scene, label) -> Collection | None`,
    `apply(scene, root, doc, coll) -> [str]` (report lines), `boxes(scene, label) -> [Object]` (oldest first),
    `numbers_of(ob)`, `applications_of(ob) -> [dict]`, `deleted_count(scene, coll) -> int`,
    `bring_back(scene, coll) -> int`, `status_counts(scene, coll) -> [(group, n)]`
  - Box object properties: `ctx_app_site`, `ctx_app_id`, `ctx_app_group`, `ctx_app_numbers` (JSON),
    `ctx_app_main`, `ctx_app_place`, `ctx_app_name`, `ctx_app_height_from`, `ctx_app_applications` (JSON),
    `ctx_app_made`, `ctx_app_placed` (JSON). Collection properties: `ctx_apps`, `ctx_app_boxes`, `ctx_app_deleted`,
    `ctx_app_frame` (JSON), `ctx_app_date`.

The Blender suite runs with:

```bash
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py -- -k site_apps
```

There is no pytest inside Blender: tests are plain functions with `assert`, each on a fresh empty file.

- [ ] **Step 1: Write the failing tests**

`tests/blender/test_site_apps.py`:

```python
"""Development application boxes in Blender (design/development-applications.md §5): made, refreshed, kept,
greyed, removed, remembered when deleted and carried across a rebuild."""
import json
import math

import bpy

from ghosttown import scene_build, site_apps, site_use
from ghosttown.ghosttown_fetch import BUILDING_KINDS
from ghosttown.ghosttown_fetch.frame import Frame
from helpers import closed_and_outward, load_fixture, mesh_arrays

SITE = "320 Bay St"
LINK = "http://app.toronto.ca/AIC/index.do?folderRsn=abc"


def _site(number, *more, group="review", centre=(40.0, 10.0), w=30.0, d=20.0, h=45.0, angle=0.0,
          address="25 KING ST W"):
    numbers = sorted((number,) + more)
    return {"id": "app:" + numbers[0], "group": group, "numbers": numbers, "main": number,
            "centre_m": list(centre), "angle_deg": angle, "width_m": w, "depth_m": d, "height_m": h, "base_m": -0.3,
            "height_from": "description: 14 storeys",
            "applications": [{"number": n, "type": "OZ", "status": "Under Review", "submitted": "2024-01-01",
                              "address": address, "description": "a 14-storey building with retail at grade",
                              "source": "application", "floor_area_m2": 0.0, "url": LINK} for n in numbers]}


def _doc(sites, centre=None):
    doc = load_fixture("mini_context.json")
    if sites is not None:
        doc["applications"] = sites
        doc["applications_date"] = "2026-10-09"
    if centre is not None:
        doc["centre"] = centre
    return doc


def _build(sites, lines=None, centre=None):
    report = None if lines is None else (lambda level, text: lines.append(text))
    return scene_build.build(bpy.context.scene, _doc(sites, centre), report=report)


def _boxes():
    return site_apps.boxes(bpy.context.scene, SITE)


def _height(ob):
    zs = [v.co.z for v in ob.data.vertices]
    return max(zs) - min(zs)


def _close(a, b, tol=1e-4):
    return all(math.isclose(x, y, abs_tol=tol) for x, y in zip(a, b))


def test_a_build_with_applications_makes_one_see_through_box_per_site():
    root = _build([_site("A", angle=30.0)])
    coll = root.children[f"Applications · {SITE}"]
    (box,) = coll.objects
    assert box.name == "Under review · 25 King St W" and box["ctx_app_group"] == "review"
    assert len(box.data.vertices) == 8 and closed_and_outward(*mesh_arrays(box))
    assert _close(box.location, (40.0, 10.0, -0.3)) and math.isclose(box.rotation_euler.z, math.radians(30.0),
                                                                     abs_tol=1e-6)
    assert math.isclose(_height(box), 45.0, abs_tol=1e-4)
    mat = box.data.materials[0]
    assert mat.name == "Context - Application (Under review)" and math.isclose(mat.diffuse_color[3], 0.7,
                                                                               abs_tol=1e-6)
    assert json.loads(box["ctx_app_numbers"]) == ["A"] and box["ctx_app_height_from"] == "description: 14 storeys"
    assert site_apps.applications_of(box)[0]["url"] == LINK
    assert box not in site_use.made_objects(root, BUILDING_KINDS)    # Street Look and the roof switches pass it by


def test_a_build_without_applications_makes_no_collection():
    root = _build(None)
    assert not any(c.get(site_apps.SITE_PROP) for c in root.children_recursive)


def test_a_rebuild_refreshes_the_status_and_resizes_an_untouched_box():
    _build([_site("A")])
    (box,) = _boxes()
    lines = []
    _build([_site("A", group="approved", h=60.0)], lines)
    assert _boxes() == [box] and box.name == "Approved · 25 King St W"
    assert math.isclose(_height(box), 60.0, abs_tol=1e-4)
    assert box.data.materials[0].name == "Context - Application (Approved)"
    assert lines[0] == "Development applications (City of Toronto, 2026-10-09): 1 site from 1 application: 1 approved."


def test_a_box_the_user_scaled_keeps_its_shape_and_takes_the_new_status():
    _build([_site("A")])
    (box,) = _boxes()
    box.scale.x = 2.0
    lines = []
    _build([_site("A", group="approved", h=60.0)], lines)
    assert box.scale.x == 2.0 and math.isclose(_height(box), 45.0, abs_tol=1e-4)
    assert box.data.materials[0].name == "Context - Application (Approved)"
    assert "1 box kept at the size you gave it." in lines[0]


def test_a_closed_box_is_removed_untouched_and_turns_grey_when_changed():
    _build([_site("A"), _site("B", centre=(-40.0, 10.0), address="1 BAY ST")])
    edited = next(ob for ob in _boxes() if ob["ctx_app_main"] == "B")
    edited.location.x += 5.0
    _build([])
    assert _boxes() == [edited] and edited.name == "Closed · 1 Bay St" and edited["ctx_app_group"] == "closed"
    assert edited.data.materials[0].name == "Context - Application (Closed)"


def test_a_deleted_box_stays_deleted_until_brought_back():
    _build([_site("A")])
    (box,) = _boxes()
    bpy.data.objects.remove(box)
    _build([_site("A")])
    assert _boxes() == []
    coll = site_apps.find(bpy.context.scene, SITE)
    assert site_apps.deleted_count(bpy.context.scene, coll) == 1
    assert site_apps.bring_back(bpy.context.scene, coll) == 1
    assert site_apps.deleted_count(bpy.context.scene, coll) == 0
    _build([_site("A")])
    assert len(_boxes()) == 1


def test_a_build_that_did_not_look_leaves_every_box_and_carries_it():
    _build([_site("A")])
    (box,) = _boxes()
    box.location.y += 3.0
    root = _build(None)
    assert _boxes() == [box] and list(root.children[f"Applications · {SITE}"].objects) == [box]
    assert math.isclose(box.location.y, 13.0, abs_tol=1e-4)


def test_a_box_renamed_and_moved_into_the_users_collection_is_updated_there():
    _build([_site("A")])
    (box,) = _boxes()
    mine = bpy.data.collections.new("My boxes")
    bpy.context.scene.collection.children.link(mine)
    mine.objects.link(box)
    for coll in list(box.users_collection):
        if coll != mine:
            coll.objects.unlink(box)
    box.name = "my tower"
    _build([_site("A", group="appealed")])
    assert _boxes() == [box] and [c.name for c in box.users_collection] == ["My boxes"]
    assert box.name == "my tower" and box["ctx_app_group"] == "appealed"


def test_a_duplicated_box_is_left_as_it_is_and_named():
    _build([_site("A")])
    (box,) = _boxes()
    copy = box.copy()
    copy.data = box.data.copy()
    box.users_collection[0].objects.link(copy)
    lines = []
    _build([_site("A", group="approved")], lines)
    assert sorted(ob["ctx_app_group"] for ob in _boxes()) == ["approved", "review"]
    assert box["ctx_app_group"] == "approved"
    assert any(copy.name in line and "left as it is" in line for line in lines)


def test_a_restyled_status_material_keeps_its_colour():
    _build([_site("A")])
    mat = bpy.data.materials["Context - Application (Under review)"]
    mat.diffuse_color = (1.0, 0.0, 0.0, 0.5)
    _build([_site("A")])
    assert _close(mat.diffuse_color, (1.0, 0.0, 0.0, 0.5))


def test_a_site_built_again_around_another_centre_carries_its_boxes():
    _build([_site("A")])
    (box,) = _boxes()
    doc = load_fixture("mini_context.json")
    lon, lat = Frame(doc["centre"]["lat"], doc["centre"]["lon"]).to_lonlat(10.0, 0.0)
    _build(None, centre={"lat": lat, "lon": lon})
    assert _close(box.location[:2], (30.0, 10.0), tol=1e-3)
    _build([_site("A", group="approved", centre=(30.0, 10.0), h=60.0)], centre={"lat": lat, "lon": lon})
    assert box["ctx_app_group"] == "approved" and math.isclose(_height(box), 60.0, abs_tol=1e-4)   # still untouched
```

- [ ] **Step 2: Run them to see them fail**

Run: `/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py -- -k site_apps`
Expected: `FAIL test_site_apps.py (import)` with `ImportError: cannot import name 'site_apps'`.

- [ ] **Step 3: Implement the materials**

In `ghosttown/materials.py`, add `from .ghosttown_fetch import app_boxes` after `import bpy`, and after
`get_material`:

```python
def application_name(group):
    """`Context - Application (<Status>)`."""
    return f"{PREFIX}Application ({app_boxes.LABELS[group]})"


def _linear(c):
    """An sRGB channel (0-1) in Blender's linear colour space."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def application_material(group):
    """The see-through material of a development application box's status, made once with its colour (BHPlus's
    palette); one that exists already is used as it is, so the user's restyling stays."""
    name = application_name(group)
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    rgb = tuple(_linear(c / 255.0) for c in app_boxes.COLOURS_SRGB[group])
    mat.diffuse_color = rgb + (app_boxes.ALPHA,)
    mat.surface_render_method = "BLENDED"
    mat.use_backface_culling = False
    if mat.node_tree is not None:
        for node in mat.node_tree.nodes:
            if node.bl_idname == "ShaderNodeBsdfPrincipled":
                node.inputs["Base Color"].default_value = rgb + (1.0,)
                node.inputs["Alpha"].default_value = app_boxes.ALPHA
                node.inputs["Roughness"].default_value = PLAIN_ROUGHNESS
    return mat
```

- [ ] **Step 4: Implement the boxes**

`ghosttown/site_apps.py`:

```python
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
    """The site's Applications collection in this scene, or None."""
    for coll in scene.collection.children_recursive:
        if coll.get(SITE_PROP) == label:
            return coll
    return None


def detach(scene, label):
    """Take the site's Applications collection out of every collection in this scene, so removing the old site
    collection leaves it alone; returns it, or None."""
    coll = find(scene, label)
    if coll is None:
        return None
    for parent in [scene.collection, *scene.collection.children_recursive]:
        if parent != coll and coll.name in parent.children:
            parent.children.unlink(coll)
    return coll


def boxes(scene, label):
    """The site's box objects in this scene, wherever the user moved them, oldest first."""
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
    """Where the box stands in plan: the middle of its vertices, else its origin."""
    mw = ob.matrix_world
    if ob.type == "MESH" and len(ob.data.vertices):
        pts = [mw @ v.co for v in ob.data.vertices]
    else:
        pts = [mw.translation]
    return [sum(p.x for p in pts) / len(pts), sum(p.y for p in pts) / len(pts)]


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


def _place_name(site):
    """The lead application's first address, in title case, else its number."""
    lead = next((a for a in site["applications"] if a["number"] == site["main"]), site["applications"][0])
    address = lead["address"].split("; ")[0].strip()
    return address.title() if address else lead["number"]


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
    report: the summary first, then one for each box left as it is; [] when the build did not look at the
    applications."""
    label = root["ctx_label"]
    sites = doc.get("applications")
    if coll is None:
        if sites is None:
            return []
        coll = bpy.data.collections.new(COLL_PREFIX + label)
        coll[SITE_PROP] = label
    root.children.link(coll)
    _carry(scene, coll, label, doc)
    present = boxes(scene, label)
    states = [{"object": ob, "numbers": numbers_of(ob), "centre_m": _centre(ob),
               "touched": app_boxes.touched(_json(ob, "ctx_app_placed", {}) or None, _measure(ob)),
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
    return [app_boxes.summary(sites, outcome, doc.get("applications_date", ""))] + [LEFT.format(name=n) for n in left]
```

- [ ] **Step 5: Carry the collection across a rebuild, and report**

In `ghosttown/scene_build.py`:
- Add `site_apps` to the `from . import ...` line.
- Add to the module docstring: `The site's development application boxes live in their own Applications
  collection, which a rebuild takes out of the old site collection before removing it and links into the new one
  (site_apps).`
- In `build`, right after `look = ...` and before `if old is not None: remove(old, scene)`:

```python
    apps = site_apps.detach(scene, label)      # the boxes outlive a rebuild; site_apps.apply decides each one
```

- After `root["ctx_objects"] = json.dumps(made)`:

```python
    for line in site_apps.apply(scene, root, doc, apps):
        if report is not None:
            report({"INFO"}, line)
```

In `ghosttown/ops.py`:
- Add `site_apps` to the `from . import ...` line.
- In `import_into_scene`, before `site_use.count_triangles(...)`:

```python
    apps = site_apps.find(context.scene, root["ctx_label"])
    if apps is not None:
        n = len(site_apps.boxes(context.scene, root["ctx_label"]))
        settings.summary += f", {n} application box{'' if n == 1 else 'es'}"
```

- Replace the notes loop with one that also reports the applications' info notes:

```python
    for note in doc["notes"]:
        if note["level"] == "warn":
            report({"WARNING"}, note["text"])
        elif note["code"] == "applications":
            report({"INFO"}, note["text"])
```

- [ ] **Step 6: Run the Blender suite**

Run: `/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py`
Expected: every test passes, the new `test_site_apps.py` ones included (the suite printed 218 passed before this
work).

- [ ] **Step 7: Commit**

```bash
git add ghosttown/materials.py ghosttown/site_apps.py ghosttown/scene_build.py ghosttown/ops.py tests/blender/test_site_apps.py
git commit -m "feat(blender): development application boxes, refreshed by each build and kept where you shaped them

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: The tick, the Site panel and its two buttons

**Files:**
- Modify: `ghosttown/props.py` (`GhostTownSettings`)
- Modify: `ghosttown/ops.py` (`request_layers`, two operators)
- Modify: `ghosttown/ui.py` (Fetch column, `GHOSTTOWN_PT_site.draw`)
- Modify: `ghosttown/__init__.py` (`_CLASSES`)
- Test: `tests/blender/test_extension.py`

**Interfaces:**
- Consumes: `site_apps.*`, `materials.application_name` (Task 9), `context.city_link` (Task 5).
- Produces: `settings.fetch_applications` (default False); operators `ghosttown.apps_bring_back` and
  `ghosttown.open_application(number=str)`; `ops.open_url(url)` (the one place a link is opened, so tests can
  stand in for it).

- [ ] **Step 1: Write the failing tests**

In `tests/blender/test_extension.py`:
- `Settings.__init__` gains `fetch_applications=False` and sets `self.fetch_applications = fetch_applications`.
- Add `site_apps` to the `from ghosttown import ...` line.
- Append:

```python
def test_development_applications_are_asked_for_only_when_ticked():
    assert "applications" not in ops.request_layers(Settings("43.65, -79.38"))
    assert "applications" in ops.request_layers(Settings("43.65, -79.38", fetch_applications=True))


def _apps_site():
    doc = load_fixture("mini_context.json")
    doc["applications"] = [{
        "id": "app:A", "group": "review", "numbers": ["A"], "main": "A", "centre_m": [40.0, 10.0],
        "angle_deg": 0.0, "width_m": 30.0, "depth_m": 20.0, "height_m": 45.0, "base_m": -0.3,
        "height_from": "not stated",
        "applications": [{"number": "A", "type": "OZ", "status": "Under Review", "submitted": "2024-01-01",
                          "address": "25 KING ST W", "description": "", "source": "application",
                          "floor_area_m2": 0.0, "url": "http://app.toronto.ca/AIC/index.do?folderRsn=abc"}]}]
    doc["applications_date"] = "2026-10-09"
    root = scene_build.build(bpy.context.scene, doc)
    bpy.context.scene.ghosttown.site = root
    return root, doc


def test_bring_back_forgets_the_deleted_boxes():
    ghosttown.register()
    try:
        root, _ = _apps_site()
        (box,) = site_apps.boxes(bpy.context.scene, root["ctx_label"])
        bpy.data.objects.remove(box)
        assert bpy.ops.ghosttown.apps_bring_back() == {"FINISHED"}
        assert site_apps.deleted_count(bpy.context.scene, site_apps.find(bpy.context.scene, root["ctx_label"])) == 0
    finally:
        ghosttown.unregister()


def test_open_application_opens_only_a_city_link():
    ghosttown.register()
    opened, real = [], ops.open_url
    ops.open_url = opened.append
    try:
        root, _ = _apps_site()
        (box,) = site_apps.boxes(bpy.context.scene, root["ctx_label"])
        bpy.context.view_layer.objects.active = box
        assert bpy.ops.ghosttown.open_application(number="A") == {"FINISHED"}
        apps = site_apps.applications_of(box)
        apps[0]["url"] = "https://example.com/not-the-city"
        box["ctx_app_applications"] = json.dumps(apps)
        assert bpy.ops.ghosttown.open_application(number="A") == {"CANCELLED"}
        assert opened == ["http://app.toronto.ca/AIC/index.do?folderRsn=abc"]
    finally:
        ops.open_url = real
        ghosttown.unregister()
```

- [ ] **Step 2: Run them to see them fail**

Run: `/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py -- -k test_extension`
Expected: the three new tests FAIL (`applications` asked for unticked by `request_layers`' default of True, no
`apps_bring_back` operator).

- [ ] **Step 3: Implement**

`ghosttown/props.py`, in `GhostTownSettings` after `fetch_lidar`:

```python
    fetch_applications: BoolProperty(
        name="Development applications", default=False,
        description="Toronto: boxes on nearby sites with an open development application, under construction or "
                    "recently built (City applications and building permits; houses left out)")
```

`ghosttown/ops.py`:
- `ops.py` already imports `from .ghosttown_fetch import context as ctx`, and Task 9 added `site_apps` to its
  `from . import ...` line.
- `request_layers`:

```python
def request_layers(settings):
    """Every layer, less the photo when the user turned it off; LiDAR roofs and development applications only when
    ticked."""
    wanted = {"photo": getattr(settings, "fetch_photo", True), "lidar": getattr(settings, "fetch_lidar", False),
              "applications": getattr(settings, "fetch_applications", False)}
    return [layer for layer in LAYERS if wanted.get(layer, True)]
```

- After `GHOSTTOWN_OT_save_photo`, add:

```python
def _apps(context):
    root = site_use.picked(context)
    return None if root is None else site_apps.find(context.scene, root.get("ctx_label"))


class GHOSTTOWN_OT_apps_bring_back(bpy.types.Operator):
    bl_idname = "ghosttown.apps_bring_back"
    bl_label = "Bring Back Deleted Boxes"
    bl_description = "Forget which development application boxes you deleted, so the next Build Context makes them again"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _apps(context) is not None

    def execute(self, context):
        n = site_apps.bring_back(context.scene, _apps(context))
        self.report({"INFO"}, f"The next Build Context brings back {n} box{'' if n == 1 else 'es'}.")
        return {"FINISHED"}


def open_url(url):
    """Open a link in the user's browser: the one place Ghost Town does."""
    bpy.ops.wm.url_open(url=url)


class GHOSTTOWN_OT_open_application(bpy.types.Operator):
    bl_idname = "ghosttown.open_application"
    bl_label = "Open in City AIC"
    bl_description = "Open this application on the City of Toronto's Application Information Centre"
    bl_options = {"REGISTER"}

    number: StringProperty(name="Application")

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and site_apps.BOX_SITE in ob

    def execute(self, context):
        link = next((ctx.city_link(a.get("url")) for a in site_apps.applications_of(context.active_object)
                     if a.get("number") == self.number), "")
        if not link:
            self.report({"ERROR"}, "This application has no City of Toronto link.")
            return {"CANCELLED"}
        open_url(link)
        return {"FINISHED"}
```

`ghosttown/__init__.py`, `_CLASSES`: add `ops.GHOSTTOWN_OT_apps_bring_back,` and
`ops.GHOSTTOWN_OT_open_application,` after `ops.GHOSTTOWN_OT_save_photo,`.

`ghosttown/ui.py`:
- Imports: `from . import georef, look_build, materials, ops, prefs, runner, site_apps, site_use` and
  `from .ghosttown_fetch import app_boxes`.
- In `GHOSTTOWN_PT_main.draw`, under `col.prop(settings, "fetch_lidar")`, add `col.prop(settings, "fetch_applications")`.
- Add `"HOME", "URL", "LOOP_BACK", "OBJECT_DATA"` to `SITE_ICONS` (it lists the icons the Site panel uses;
  `test_extension.py` checks each is a real Blender icon).
- Above `class GHOSTTOWN_PT_site`, add:

```python
MAX_DESCRIPTION_LINES = 8


def _applications_box(layout, context, coll):
    """The site's development application boxes: a swatch and count per status, the data's date, Bring Back,
    and, when the active object is one of them, its applications."""
    box = layout.box()
    date = coll.get("ctx_app_date", "")
    box.label(text=f"Development applications {date}".strip(), icon="HOME")
    col = box.column(align=True)
    for group, n in site_apps.status_counts(context.scene, coll):
        row = col.row(align=True)
        mat = bpy.data.materials.get(materials.application_name(group))
        split = row.split(factor=0.15, align=True)
        if mat is not None:
            split.prop(mat, "diffuse_color", text="")
        else:
            split.label(text="")
        split.label(text=f"{app_boxes.LABELS[group]}: {n}")
    gone = site_apps.deleted_count(context.scene, coll)
    if gone:
        box.operator("ghosttown.apps_bring_back", text=f"Bring Back Deleted Boxes ({gone})", icon="LOOP_BACK")
    ob = context.active_object
    if ob is None or ob.get(site_apps.BOX_SITE) != coll.get(site_apps.SITE_PROP):
        return
    detail = box.box()
    group = ob.get("ctx_app_group", "review")
    detail.label(text=f"{app_boxes.LABELS.get(group, group)} · {ob.get('ctx_app_height_from', '')}",
                 icon="OBJECT_DATA")
    width = hint_width(context)
    for a in site_apps.applications_of(ob):
        col = detail.column(align=True)
        col.label(text=" · ".join(str(a.get(k, "")) for k in ("number", "type", "status", "submitted") if a.get(k)))
        if a.get("address"):
            col.label(text=str(a["address"]))
        lines = textwrap.wrap(str(a.get("description", "")), width)
        for line in lines[:MAX_DESCRIPTION_LINES]:
            col.label(text=line)
        if len(lines) > MAX_DESCRIPTION_LINES:
            col.label(text="…")
        if ctx.city_link(a.get("url")):
            col.operator("ghosttown.open_application", icon="URL").number = str(a.get("number", ""))
```

  and add `from .ghosttown_fetch import context as ctx` to the imports.
- At the end of `GHOSTTOWN_PT_site.draw` (after the LiDAR block), add:

```python
        apps = site_apps.find(context.scene, root.get("ctx_label"))
        if apps is not None:
            _applications_box(layout, context, apps)
```

`hint_width` is defined further down `ui.py`; it is only called at draw time, so the order is fine.

- [ ] **Step 4: Run the whole Blender suite**

Run: `/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py`
Expected: every test passes.

- [ ] **Step 5: Commit**

```bash
git add ghosttown/props.py ghosttown/ops.py ghosttown/ui.py ghosttown/__init__.py tests/blender/test_extension.py
git commit -m "feat(blender): the Development applications tick, the Site panel's boxes, Bring Back and Open in City AIC

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Docs, and the check in the user's own Blender

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write the docs**

In `README.md`:
- In **What you get**, after the **Aerial photo** bullet, add:

```markdown
- **Development applications** (Toronto, asked for): a see-through box on every nearby site with an open
  development application, a building going up or one just finished, coloured by where it stands: under
  construction, recently built, appealed, under review, approved, or Committee of Adjustment. Each box sits on its
  lot and is as tall as the City's description or building permit says. See [Use](#use).
```

- In **Use**, step 5 (**Fetch**), add a sentence at its end: `Tick **Development applications** to put a box on
  every nearby site with an open development application, under construction or finished since the City's 3D
  Massing (City of Toronto applications and building permits; houses left out). The first build of the day takes a
  few seconds more.`
- After the LiDAR roofs list in **Use** (after the **For Revit** bullet), add:

```markdown
When the site has development application boxes, **Development applications** lists them by status, each with its
colour (change it there to restyle every box of that status). Select a box to see its applications and permits,
their status, date and description, and **Open in City AIC** for the City's page about each. Reshape a box as you
like: grab, rotate, scale (the **Scale Cage** tool moves one side at a time) or edit its mesh. Building the site
again refreshes each box's status and keeps the shape you gave it; a box whose applications all closed is removed,
or turned grey (**Closed**) if you changed it. A box you delete stays deleted; **Bring Back Deleted Boxes** makes
the next build put them back.
```

- [ ] **Step 2: Run both suites**

```bash
uv run pytest -q
```

```bash
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py
```

Expected: everything passes. Note the counts for the report.

- [ ] **Step 3: Build a development zip without touching dist/**

`tools/build.sh` deletes `dist/`, which holds the 0.4.0 release zips: don't run it. Build one zip into the
session's scratchpad instead (`$SCRATCH` below):

```bash
python3 tools/fetch_wheels.py
/Applications/Blender.app/Contents/MacOS/Blender --factory-startup --command extension build --source-dir ghosttown --output-dir "$SCRATCH/devzip" --split-platforms
```

Expected: `$SCRATCH/devzip/ghosttown-0.4.0-macos_arm64.zip` among the outputs.

- [ ] **Step 4: Check it in the user's open Blender (Blender MCP)**

The user asked for the test to run in their open Blender file. Don't save the file. With the Blender MCP tools:
1. Read the scene (`get_objects_summary`) and note what is there, so nothing of the user's is touched.
2. Install the development zip: `bpy.ops.extensions.package_install_files(filepath=<zip>, repo="user_default",
   enable_on_install=True)`.
3. Build King & Bay: set `scene.ghosttown.location = "43.6487, -79.3806"`, `site_name = "King & Bay (applications)"`,
   `radius = "300"`, `fetch_applications = True`, and run **Build Context** from a 3D View context
   (`bpy.ops.ghosttown.build("INVOKE_DEFAULT")` inside `bpy.context.temp_override(window=..., area=<VIEW_3D>,
   region=<its WINDOW region>)`), then poll `ghosttown.runner.ACTIVE` until the run ends. If invoking from the MCP
   can't start the modal run, fall back to running the fetcher by hand
   (`uv run python -m ghosttown_fetch fetch <request.json>` from `ghosttown/`, after writing the request with
   `ops.make_request`) and `bpy.ops.ghosttown.import_context(filepath=<context.json>)`.
4. Check: an `Applications · King & Bay (applications)` collection; boxes with status names; at least one site
   reading `21204526STE13SA` under review about 205 m tall; the summary line in the Info log. Note any Under
   construction or Recently built box; if there is none, build a second site where the City's live permits show a
   tower going up (look one up in the live permits table) and check its box.
5. Add a camera looking at the boxes from the south-west, about 45° down, and show the user the view
   (`get_screenshot_of_window_as_image` or `render_viewport_to_path`), per their standing preference.
6. Scale one box (`scale.x = 1.5`), build the site again, and check the box kept its shape and the summary says
   "1 box kept at the size you gave it."
7. Check the Site panel draws (screenshot of the sidebar with a box selected) and that Solid view shows the boxes
   see-through. If Solid view shows them opaque, report it with the screenshot rather than changing the design.

- [ ] **Step 5: Commit the docs**

```bash
git add README.md
git commit -m "docs: development application boxes in What you get and Use

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
