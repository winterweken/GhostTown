# Street Look Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every building in a Ghost Town context a believable facade in Blender renders, derived from Mapillary street photos, plus opt-in detail geometry for a few selected buildings.

**Architecture:** A new `ghosttown_fetch look` command (plain Python: numpy, shapely and Pillow, never bpy) lists Mapillary photos around the site, chooses photos per building by line of sight, reads colour by height from labelled, exposure-calibrated pixels, and writes `look.json` (zones, floor height, detail wall spans). The Blender side stores those values as custom properties on each building, which one shared node group inside the existing building materials turns into a facade; detail is generated as separate meshes. Rebuilds carry the look over by building id.

**Tech Stack:** Python 3.13 (Blender 5.2's), numpy 2.3, shapely 2.1, Pillow 11.3 (new, bundled as wheels), Blender 5.2 Python API, pytest with pytest-socket, Blender's headless test runner.

**Spec:** `design/street-look.md` (read it first; this plan argues from it).

**Base:** Ghost Town 0.3.0, `origin/dev` at `f95f0e0`. The tasks were applied to that tree from this plan's own
text, and the fetcher and Blender test suites pass. Start from a `dev` that contains `f95f0e0`
(`git rebase --autostash origin/dev` if this checkout is older).

**Deviations.** The plan was executed task by task on 2026-10-07; reviews changed some task code, and the task
bodies below were left as written. The code is the truth. The changes: Task 7's `choose` picks in two passes
(spec §6.4); Task 8's manifest permission text is at most 64 characters; Task 9 sets MIN_PHOTOS_PER_BAND = 1 and
accepts a floor height only where the 2.8–6 m window's highest autocorrelation lies inside the window (never at its
first or last lag) and above a noise level, and skips flat walls; Task 10 decodes photos on
demand through a per-run LRU of 8, adds the `mapillary_none` warning and does not count thin clutter against a
photo; Task 11 refuses a token with control, space or non-ASCII characters; Task 12's stdlib guard also blocks
PIL; Task 15's `reapply` applies the scene's Show street look and Photo brightness, `apply` dresses before storing,
and a stored look that fails validation or dressing is dropped and the buildings undressed; Task 16 pins
registration, the token's path into the fetcher, the panel's draw, the finished guard and launch refusals; Task
17 saves the request with budget 10 while recording 6 photos, replays listings by bounding box, and keeps
buildings with a corner within 60 m; Task 18's accuracy tool fetches terrain with the buildings
(`layers=["buildings", "terrain"]`), so its cameras and buildings share the add-on's ground datum, and it refuses a
token with whitespace or non-ASCII characters before any request. The final fix wave (2026-10-07/08) replaces
photos the label check or a download drops (labels first, up to 6 tries per building, within the budget), reads
only a building's nearest surface (owner-grid depth check), uses the request's ground datum (flat ground when Build
had none; a mismatch stops the run), counts thin clutter in the sky/ground denominator, keeps the 2 % frame margin
off 360° cameras, refuses redirects on requests carrying the token, reports Mapillary's request limit as such,
deletes expired Mapillary cache files after a run, stops early in an outage, prunes and chunks the ray march and
sight tests, gives both tools the token check; in Blender it aligns detail bands and fins with the shader and clamps
floor_h to 1 m, matches Esc on press only with a per-panel Cancel, refuses Not before 1–1999 in plain words, adds
the "Labels from Mapillary" credit line, shows the resolved cache folder in Preferences and warns when a stored look
is dropped. Every commit after Task 14 carries the Claude Fable 5.1 trailer, except the fix wave's five fetcher
commits (cf5f7b0 to 05157e5), which carry Claude Opus 5.5's.

## Global Constraints

- Blender 5.2 or later, its Python 3.13. The fetcher (`ghosttown/ghosttown_fetch/`) never imports bpy.
- `ghosttown_fetch/__init__.py`, `request.py`, `context.py` and the new `look_schema.py` use the standard library only (the add-on imports them without numpy, shapely or Pillow).
- One new dependency: Pillow, bundled as per-platform wheels like shapely. No protobuf: Mapillary's label tiles are decoded by our own `mvt.py`.
- The Mapillary token reaches the fetcher only through the environment variable `GHOSTTOWN_MAPILLARY_TOKEN` and is sent only as the header `Authorization: OAuth <token>`. It never appears in a URL, a request file, the command line, a cache key or a cached file.
- Credit string, exactly: `Street photos © Mapillary contributors, CC BY-SA 4.0`. Source key `mapillary`, name `Mapillary`.
- Defaults and limits: photo budget 150 (10–500); search margin 200 m, search radius capped at 1,000 m; at most 4 photos per building; at most 20 detail buildings; Photo brightness 1.15; Keep street look on rebuild on; Not before off.
- Selection: distance 3–500 m; within 35° of square-on in plan; perspective and fisheye pitch within ±12°; in frame with a 2% margin and perspective r² < 1.2; line of sight to within 1 m of the point; usable sharpness ≥ 5 px/m at 2048 px; sharpness capped at 20 px/m in scoring; recency weights 2022+ ×1.0, 2018–2021 ×0.8, earlier ×0.6.
- Extraction: drop a photo for a building when > 30% of its points land on sky or ground or < 30% on building; per-pixel model mask 200 px wide; exposure gain clamped to 0.5–2×, needs ≥ 500 road pixels; 3 m bands, 6 m glass cells; glass when chromaticity spread > 0.12 and log-luminance spread > 0.7 over ≥ 3 views; zones merge below 6 m, at most 4; storefront jump 1.6× between 3 and 9 m; floor height searched over 2.8–6 m, accepted when 2 walls agree within 0.25 m, else 3.5 m.
- look.json: heights in metres above the building's lowest point; colours linear RGB; 1–4 zones; zone kinds `storefront`, `opaque`, `glass`, `cap`; the last zone's `h1` is `null`.
- Material names stay exactly `Context - Building`, `Context - Building (on site)`, `Context - Building (height guessed)`; the only new one is `Context - Facade detail`.
- Street Look acts on the Site panel's picked site and only on the site's own buildings (`site_use.made_objects`),
  like 0.3.0's aerial photo on roofs. A building that keeps roof shapes is read from its flat mesh (`site_use.FLAT_KEY`).
- Messages are one plain sentence. In prose the brand is "Ghost Town" (two words); `tests/fetch/test_package.py` fails any `GhostTown` outside allowed identifiers.
- Photos and labels are cached for 30 days by image id; only derived values reach the .blend file.
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A building mesh the user edited so it no longer has bottom faces (a plane, a boolean leftover): Apply must skip it, not crash. Test in Task 15 (`test_a_building_without_bottom_faces_is_left_out`).
2. A site where Mapillary has no photos at all: every building gets the guessed look and the run succeeds. Test in Task 10 (`test_no_coverage_means_every_building_is_guessed`).
3. A photo whose computed position falls inside a building (a bad pose): it must see nothing, never walls "from inside". Test in Task 7 (`test_a_camera_inside_a_building_sees_nothing`).
4. A building with detail that no longer exists when the look is re-applied (deleted, or gone after a rebuild): no error, no detail object for it. Test in Task 15 (`test_reapply_skips_buildings_that_are_gone`).
5. A 1,000 m site: the photo search must stay bounded (radius capped at 1,000 m, at most 400 listing tiles). Tests in Task 6 (`test_tiles_cover_the_circle_and_stay_bounded`) and Task 10 (`test_search_radius_follows_the_buildings_and_is_capped`, `test_photos_are_read_for_at_most_as_many_buildings_as_the_budget`).
6. A site with 0.3.0's fitted and LiDAR roofs: the request must describe the flat prisms, and switching roof shapes must keep the look. Test in Task 15 (`test_roof_shapes_share_the_look_and_the_request_reads_the_flat_mesh`).

## File structure

Fetcher (`ghosttown/ghosttown_fetch/`):

| File | Responsibility |
|---|---|
| `net.py` (modify) | Per-call headers, cache-key override, cache-only reads, HTTP status on errors |
| `__init__.py` (modify) | `mapillary` source name and credit, `LOOK_SCHEMA` |
| `look_schema.py` (new) | Build and validate `look_request.json` and `look.json`; standard library only |
| `mvt.py` (new) | Decode Mapbox Vector Tile polygons (Mapillary's labels) |
| `camera.py` (new) | Mapillary camera poses, projection, rays, sharpness |
| `raycast.py` (new) | 2.5D line of sight against building prisms |
| `sources/mapillary.py` (new) | Listings by tile, thumbnails, labels, parallel fetches, token errors |
| `selection.py` (new) | Wall sample points, which photo sees which point, photo choice |
| `imagery.py` (new) | Pillow decoding to linear light, label maps, road exposure |
| `appearance.py` (new) | Colour profile, glass test, zones, floor height, defaults |
| `look.py` (new) | The Street Look pipeline: request to answer |
| `cli.py` (modify) | `look` command; selftest reports Pillow |

Blender side (`ghosttown/`):

| File | Responsibility |
|---|---|
| `prefs.py` (modify) | Mapillary token field and `token()` |
| `runner.py` (modify) | Extra environment for the child process |
| `materials.py` (modify) | The Street Look node group and the `facade_detail` kind |
| `look_detail.py` (new) | Detail boxes from a look entry; pure Python |
| `look_build.py` (new) | Request from the scene, applying answers, switches, sky |
| `scene_build.py` (modify) | Carry the look across a rebuild |
| `site_use.py` (modify) | Detail meshes count toward the Revit triangle figure |
| `props.py`, `ops.py`, `ui.py`, `__init__.py` (modify) | Settings, operators, panel, registration |

Tests and tools: `tests/fetch/` (new `test_look_schema.py`, `test_mvt.py`, `test_camera.py`, `test_raycast.py`, `test_mapillary.py`, `test_selection.py`, `test_imagery.py`, `test_appearance.py`, `test_look.py`, `test_look_detail.py`, `test_look_recorded.py`; helpers `mvt_samples.py`, `camera_samples.py`, `look_samples.py`; recorded fixture `fixtures/kingst/`), `tests/blender/` (new `test_look_materials.py`, `test_look_build.py`, fixture `fixtures/mini_look.json`), `tools/fetch_wheels.py`, `tools/smoke_live.py`, new `tools/record_look_fixture.py` and `tools/look_accuracy.py`, `README.md`, `CREDITS.md`.

Commands used throughout:

- Fetcher tests: `uv run pytest tests/fetch/<file> -v`
- Blender tests: `/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py -- -k <substring>`

---

### Task 1: Net learns headers, cache keys and cache-only reads

**Files:**
- Modify: `ghosttown/ghosttown_fetch/net.py`
- Modify: `tests/fetch/fakes.py`
- Test: `tests/fetch/test_net.py`

**Interfaces:**
- Consumes: `Net.get(..., keep=)`, which 0.3.0 already has (`keep=False` neither reads nor writes the cache).
- Produces: `SourceError(message, status=None)` with `.status` (`Unreadable` inherits it); `Net.get(url, *, source, data=None, check=None, timeout=120, keep=True, headers=None, key=None)`; `Net.cached(source, key, check=None) -> bytes | None`; `FakeNet.get(...)` accepting the same keywords and recording `FakeNet.headers` (list of dicts); `FakeNet.cached(...) -> None`.

- [ ] **Step 1: Write the failing tests** (append to `tests/fetch/test_net.py`; it already imports `Transport` from `fakes`)

```python
def test_headers_are_sent_but_not_part_of_the_cache_key(tmp_path):
    t = Transport((200, b"ok"))
    net = Net(str(tmp_path), transport=t)
    assert net.get(URL, source="osm", headers={"Authorization": "OAuth secret"}) == b"ok"
    assert t.calls[0][2]["Authorization"] == "OAuth secret" and t.calls[0][2]["User-Agent"] == USER_AGENT
    assert net.get(URL, source="osm", headers={"Authorization": "OAuth other"}) == b"ok"
    assert len(t.calls) == 1
    for entry in (tmp_path / "osm").iterdir():
        assert "secret" not in entry.name and b"secret" not in entry.read_bytes()


def test_a_key_replaces_the_url_as_cache_key(tmp_path):
    t = Transport((200, b"img"))
    net = Net(str(tmp_path), transport=t)
    assert net.get("https://cdn.example/a?sig=1", source="osm", key="photo:7") == b"img"
    assert net.get("https://cdn.example/a?sig=2", source="osm", key="photo:7") == b"img"
    assert len(t.calls) == 1


def test_cached_reads_a_stored_answer_by_key(tmp_path):
    net = Net(str(tmp_path), transport=Transport((200, b"img")))
    assert net.cached("osm", "photo:7") is None
    net.get("https://cdn.example/a?sig=1", source="osm", key="photo:7")
    assert net.cached("osm", "photo:7") == b"img"
    assert Net(str(tmp_path), fresh=True, transport=Transport()).cached("osm", "photo:7") is None


def test_source_errors_carry_the_http_status(tmp_path):
    with pytest.raises(SourceError) as e:
        Net(str(tmp_path), transport=Transport((401, b"")), sleep=lambda s: None).get(URL, source="osm")
    assert e.value.status == 401
    with pytest.raises(SourceError) as e:
        Net(str(tmp_path), transport=Transport(OSError("x"), OSError("x")), sleep=lambda s: None).get(URL, source="osm")
    assert e.value.status is None
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `uv run pytest tests/fetch/test_net.py -v`
Expected: the four new tests FAIL (`TypeError: Net.get() got an unexpected keyword argument 'headers'`, `... 'key'`, `AttributeError: 'Net' object has no attribute 'cached'`, `AttributeError: 'SourceError' object has no attribute 'status'`).

- [ ] **Step 3: Implement**

In `ghosttown/ghosttown_fetch/net.py`, replace `class SourceError` (leave `Unreadable` as it is):

```python
class SourceError(Exception):
    """A source couldn't be fetched or read. The message is one plain sentence; `status` is the last HTTP
    status when a server answered, else None."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status
```

Replace `Net.get` and add `Net.cached` after it:

```python
    def get(self, url, *, source, data=None, check=None, timeout=120, keep=True, headers=None, key=None):
        """The answer's bytes. keep=False is for one-off downloads, like the City's 81 MB massing model,
        that skip the response cache because their caller keeps its own copy, and for answers that go
        stale, like signed links. `headers` are sent but never part of the cache key. `key` replaces the
        URL as the cache key, for answers whose URL changes (signed links)."""
        if key is None:
            key = url if data is None else url + "\n" + data.decode("utf-8", "replace")
        if keep and not self.fresh:
            body = self.cache.read(source, key)
            if body is not None and _still_good(body, check):
                return body
        name = SOURCE_NAMES.get(source, source)
        problem, status = f"{name} couldn't be reached", None
        send = {"User-Agent": USER_AGENT, **(headers or {})}
        for attempt in range(RETRIES + 1):
            if attempt:
                self.sleep(RETRY_WAIT_S)
            try:
                status, body = self.transport(url, data, send, timeout)
            except http.client.IncompleteRead:
                problem, status = f"{name} sent an answer that was cut off", None
                continue
            except (OSError, http.client.HTTPException) as e:
                problem, status = f"{name} couldn't be reached ({e})", None
                continue
            if status == 200:
                if check is not None:
                    try:
                        check(body)
                    except Unreadable:
                        if attempt < RETRIES:
                            continue
                        raise
                if keep:
                    self.cache.write(source, key, body)
                return body
            problem = f"{name} answered HTTP {status}"
            if status != 429 and status < 500:
                break
        raise SourceError(problem + "; try again in a minute.", status=status)

    def cached(self, source, key, check=None):
        """A stored answer by cache key, or None (also when fresh, expired or failing its check)."""
        if self.fresh:
            return None
        body = self.cache.read(source, key)
        return body if body is not None and _still_good(body, check) else None
```

In `tests/fetch/fakes.py`, replace `FakeNet.__init__` and `FakeNet.get` and add `cached`:

```python
    def __init__(self, answers):
        self.answers = answers
        self.calls = []
        self.keeps = []
        self.timeouts = []
        self.headers = []

    def get(self, url, *, source, data=None, check=None, timeout=120, keep=True, headers=None, key=None):
        self.calls.append((url, source, data))
        self.keeps.append(keep)
        self.timeouts.append(timeout)
        self.headers.append(dict(headers or {}))
        answer = self.answers[source]
        if callable(answer):
            answer = answer(url, data)
        if isinstance(answer, Exception):
            raise answer
        if check is not None:
            check(answer)
        return answer

    def cached(self, source, key, check=None):
        return None
```

- [ ] **Step 4: Run the tests to make sure they pass**

Run: `uv run pytest tests/fetch -q`
Expected: all pass (the existing suite included).

- [ ] **Step 5: Commit**

```bash
git add ghosttown/ghosttown_fetch/net.py tests/fetch/fakes.py tests/fetch/test_net.py
git commit -m "feat(fetch): per-call headers, cache keys and cache-only reads in Net

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Mapillary as a named source, and the look request and answer formats

**Files:**
- Modify: `ghosttown/ghosttown_fetch/__init__.py`
- Create: `ghosttown/ghosttown_fetch/look_schema.py`
- Test: `tests/fetch/test_package.py`, `tests/fetch/test_look_schema.py`

**Interfaces:**
- Consumes: `TOOL` from the package.
- Produces: `SOURCE_NAMES["mapillary"]`, `CREDITS["mapillary"]`, `LOOK_SCHEMA = 1`; `look_schema.TOKEN_ENV`, `ZONE_KINDS`, `BUDGET_RANGE`, `MAX_DETAIL`, `build_request(...) -> dict`, `validate_request(doc) -> list[str]`, `read_request(path) -> (doc, problems)`, `new_answer() -> dict`, `validate_answer(doc) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/fetch/test_package.py`:

```python
def test_mapillary_is_named_and_credited():
    assert cf.SOURCE_NAMES["mapillary"] == "Mapillary"
    assert cf.CREDITS["mapillary"] == "Street photos © Mapillary contributors, CC BY-SA 4.0"
    assert cf.LOOK_SCHEMA == 1
```

Create `tests/fetch/test_look_schema.py`:

```python
import json

from ghosttown_fetch import LOOK_SCHEMA, TOOL
from ghosttown_fetch import look_schema as ls

BOX = {"id": "t:1", "solids": [{"rings": [[[0, 0], [10, 0], [10, 10], [0, 10]]], "z0": 0, "z1": 20}]}


def _req(**changes):
    req = ls.build_request(centre={"lat": 43.65, "lon": -79.38}, radius_m=300, buildings=[BOX],
                           cache_dir="/c", out_dir="/c/runs/look-1")
    req.update(changes)
    return req


def test_a_built_request_is_valid_and_carries_no_token():
    req = _req()
    assert ls.validate_request(req) == []
    assert req["schema"] == LOOK_SCHEMA and req["tool"] == TOOL
    assert req["budget_photos"] == 150 and req["search_margin_m"] == 200.0 and req["not_before_year"] is None
    assert req["buildings"][0]["detail"] is False
    assert "token" not in json.dumps(req).lower()
    assert ls.TOKEN_ENV == "GHOSTTOWN_MAPILLARY_TOKEN"


def test_request_problems_are_plain_sentences():
    assert "radius_m" in ls.validate_request(_req(radius_m=5))[0]
    assert "budget_photos" in ls.validate_request(_req(budget_photos=5))[0]
    assert "not_before_year" in ls.validate_request(_req(not_before_year=1990))[0]
    assert "search_margin_m" in ls.validate_request(_req(search_margin_m=900))[0]
    flat = {"id": "x", "solids": [{"rings": BOX["solids"][0]["rings"], "z0": 5, "z1": 5}]}
    assert "z0 below z1" in ls.validate_request(_req(buildings=[flat]))[0]
    line = {"id": "x", "solids": [{"rings": [[[0, 0], [1, 1]]], "z0": 0, "z1": 5}]}
    assert "rings of at least 3" in ls.validate_request(_req(buildings=[line]))[0]


def test_at_most_twenty_buildings_have_detail():
    many = [dict(BOX, id=f"t:{i}", detail=True) for i in range(21)]
    assert any("At most 20" in p for p in ls.validate_request(_req(buildings=many)))


def test_not_before_zero_means_every_year():
    req = ls.build_request(centre={"lat": 1, "lon": 2}, radius_m=300, buildings=[], cache_dir="c", out_dir="o",
                           not_before_year=0)
    assert req["not_before_year"] is None


def test_read_request_reports_unreadable_files(tmp_path):
    doc, problems = ls.read_request(str(tmp_path / "missing.json"))
    assert doc is None and "Couldn't read" in problems[0]


ENTRY = {"source": "photos", "photos": 3, "confidence": 0.8, "floor_h": 3.5,
         "zones": [{"h0": 0, "h1": 3, "kind": "storefront", "colour": [0.05, 0.05, 0.05]},
                   {"h0": 3, "h1": None, "kind": "glass", "colour": [0.2, 0.4, 0.5]}]}


def _answer():
    doc = ls.new_answer()
    doc["buildings"]["t:1"] = json.loads(json.dumps(ENTRY))
    return doc


def test_answer_validation():
    assert ls.validate_answer(_answer()) == []
    gap = _answer()
    gap["buildings"]["t:1"]["zones"][1]["h0"] = 4
    assert "without gaps" in ls.validate_answer(gap)[0]
    closed = _answer()
    closed["buildings"]["t:1"]["zones"][1]["h1"] = 30
    assert "zone 2" in ls.validate_answer(closed)[0]
    brick = _answer()
    brick["buildings"]["t:1"]["zones"][0]["kind"] = "brick"
    assert "zone 1" in ls.validate_answer(brick)[0]
    assert "schema" in ls.validate_answer({"schema": 9})[0]
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `uv run pytest tests/fetch/test_package.py tests/fetch/test_look_schema.py -v`
Expected: FAIL with `KeyError: 'mapillary'` and `ImportError: cannot import name 'LOOK_SCHEMA'`.

- [ ] **Step 3: Implement**

In `ghosttown/ghosttown_fetch/__init__.py`, change the docstring's second paragraph and the source tables:

```python
"""Ghost Town fetcher: request.json in, context.json out; look_request.json in, look.json out.

Runs as `python -m ghosttown_fetch` on Blender's own Python. It never imports bpy.
This file, request.py, context.py and look_schema.py use the standard library only, so the
Blender add-on can import them without shapely, numpy or Pillow.
"""
```

```python
SOURCE_NAMES = {"osm": "OpenStreetMap", "toronto": "City of Toronto", "nrcan": "Natural Resources Canada",
                "ontario": "Geospatial Ontario", "mapillary": "Mapillary"}
CREDITS = {
    "osm": "© OpenStreetMap contributors",
    "toronto": "Contains information licensed under the Open Government Licence – Toronto",
    "nrcan": "Contains information licensed under the Open Government Licence – Canada",
    "ontario": "Contains information licensed under the Open Government Licence – Ontario",
    "mapillary": "Street photos © Mapillary contributors, CC BY-SA 4.0",
}
LOOK_SCHEMA = 1
```

Create `ghosttown/ghosttown_fetch/look_schema.py`:

```python
"""look_request.json and look.json: what Street Look asks the fetcher for and what it answers.
Standard library only, so the Blender add-on can import it.

In look.json, heights are metres above the building's lowest point and colours are linear RGB."""
import json
import math

from . import LOOK_SCHEMA, TOOL

TOKEN_ENV = "GHOSTTOWN_MAPILLARY_TOKEN"
ZONE_KINDS = ("storefront", "opaque", "glass", "cap")
BUDGET_RANGE = (10, 500)
MAX_DETAIL = 20
_MAX_PROBLEMS = 20


def build_request(*, centre, radius_m, buildings, cache_dir, out_dir, ground_at_centre_m=None,
                  budget_photos=150, not_before_year=None, search_margin_m=200.0, fetch_fresh=False):
    return {
        "schema": LOOK_SCHEMA,
        "tool": TOOL,
        "centre": {"lat": float(centre["lat"]), "lon": float(centre["lon"])},
        "radius_m": float(radius_m),
        "ground_at_centre_m": None if ground_at_centre_m is None else float(ground_at_centre_m),
        "buildings": [{"id": str(b["id"]), "detail": bool(b.get("detail", False)),
                       "solids": [{"rings": [[[float(x), float(y)] for x, y in ring] for ring in s["rings"]],
                                   "z0": float(s["z0"]), "z1": float(s["z1"])} for s in b["solids"]]}
                      for b in buildings],
        "budget_photos": int(budget_photos),
        "not_before_year": int(not_before_year) if not_before_year else None,
        "search_margin_m": float(search_margin_m),
        "fetch_fresh": bool(fetch_fresh),
        "cache_dir": str(cache_dir),
        "out_dir": str(out_dir),
    }


def validate_request(doc):
    """Plain-sentence problems with a look request (at most 20); empty means fine."""
    if not isinstance(doc, dict):
        return ["The street look request is not a JSON object."]
    problems = []
    if doc.get("schema") != LOOK_SCHEMA:
        problems.append(f"Unknown street look schema {doc.get('schema')!r}; this fetcher reads schema {LOOK_SCHEMA}.")
    c = doc.get("centre")
    if not (isinstance(c, dict) and _num(c.get("lat")) and _num(c.get("lon"))
            and -85 <= c["lat"] <= 85 and -180 <= c["lon"] <= 180):
        problems.append("centre must be {lat, lon} in degrees, with latitude within ±85.")
    if not (_num(doc.get("radius_m")) and 50 <= doc["radius_m"] <= 1000):
        problems.append("radius_m must be between 50 and 1000 m.")
    lo, hi = BUDGET_RANGE
    if not (_int(doc.get("budget_photos")) and lo <= doc["budget_photos"] <= hi):
        problems.append(f"budget_photos must be a whole number from {lo} to {hi}.")
    year = doc.get("not_before_year")
    if year is not None and not (_int(year) and 2000 <= year <= 2100):
        problems.append("not_before_year must be blank or a year from 2000 to 2100.")
    if not (_num(doc.get("search_margin_m")) and 0 <= doc["search_margin_m"] <= 500):
        problems.append("search_margin_m must be between 0 and 500 m.")
    buildings = doc.get("buildings")
    if not isinstance(buildings, list):
        problems.append("buildings must be a list.")
    else:
        if sum(1 for b in buildings if isinstance(b, dict) and b.get("detail")) > MAX_DETAIL:
            problems.append(f"At most {MAX_DETAIL} buildings can have detail.")
        for b in buildings:
            problems += _building_problems(b)
            if len(problems) >= _MAX_PROBLEMS:
                break
    for key in ("cache_dir", "out_dir"):
        if not (isinstance(doc.get(key), str) and doc[key].strip()):
            problems.append(f"{key} must be a folder path.")
    return problems[:_MAX_PROBLEMS]


def _building_problems(b):
    if not (isinstance(b, dict) and isinstance(b.get("id"), str) and b["id"]):
        return ["A building has no id."]
    solids = b.get("solids")
    if not (isinstance(solids, list) and solids):
        return [f"{b['id']}: a building needs at least one solid."]
    problems = []
    for s in solids:
        rings = s.get("rings") if isinstance(s, dict) else None
        if not (isinstance(rings, list) and rings and all(_ring(r) for r in rings)):
            problems.append(f"{b['id']}: a solid needs rings of at least 3 points.")
        elif not (_num(s.get("z0")) and _num(s.get("z1")) and s["z0"] < s["z1"]):
            problems.append(f"{b['id']}: a solid needs z0 below z1.")
    return problems


def _ring(ring):
    return (isinstance(ring, list) and len(ring) >= 3
            and all(isinstance(p, list) and len(p) == 2 and _num(p[0]) and _num(p[1]) for p in ring))


def read_request(path):
    """(doc, problems). doc is None when the file can't be read as JSON."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        return None, [f"Couldn't read the street look request ({e})."]
    return doc, validate_request(doc)


def new_answer():
    return {"schema": LOOK_SCHEMA, "tool": TOOL, "photos_used": 0, "years": None, "buildings": {},
            "sources": [], "notes": []}


def validate_answer(doc):
    """Plain-sentence problems with a look.json (at most 20); empty means fine."""
    if not isinstance(doc, dict):
        return ["The street look answer is not a JSON object."]
    if doc.get("schema") != LOOK_SCHEMA:
        return [f"Unknown street look schema {doc.get('schema')!r}; Ghost Town reads schema {LOOK_SCHEMA}."]
    problems = [f"The street look answer has no {key}." for key in ("buildings", "sources", "notes") if key not in doc]
    if problems:
        return problems
    for bid, entry in doc["buildings"].items():
        problems += _entry_problems(bid, entry)
        if len(problems) >= _MAX_PROBLEMS:
            break
    return problems[:_MAX_PROBLEMS]


def _entry_problems(bid, e):
    if not isinstance(e, dict):
        return [f"{bid}: not an object."]
    problems = []
    if e.get("source") not in ("photos", "guessed"):
        problems.append(f"{bid}: source must be photos or guessed.")
    if not (_num(e.get("floor_h")) and e["floor_h"] > 0):
        problems.append(f"{bid}: floor_h must be positive.")
    zones = e.get("zones")
    if not (isinstance(zones, list) and 1 <= len(zones) <= 4):
        return problems + [f"{bid}: zones must be a list of 1 to 4 zones."]
    last = None
    for i, z in enumerate(zones):
        final = i == len(zones) - 1
        if not (isinstance(z, dict) and z.get("kind") in ZONE_KINDS and _num(z.get("h0"))
                and (z.get("h1") is None if final else _num(z.get("h1")))
                and isinstance(z.get("colour"), list) and len(z["colour"]) == 3
                and all(_num(c) and c >= 0 for c in z["colour"])):
            problems.append(f"{bid}: zone {i + 1} is malformed.")
            continue
        if last is not None and abs(z["h0"] - last) > 1e-6:
            problems.append(f"{bid}: zones must follow each other without gaps.")
        last = z["h1"]
    return problems


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)
```

- [ ] **Step 4: Run the tests to make sure they pass**

Run: `uv run pytest tests/fetch/test_package.py tests/fetch/test_look_schema.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ghosttown/ghosttown_fetch/__init__.py ghosttown/ghosttown_fetch/look_schema.py tests/fetch/test_package.py tests/fetch/test_look_schema.py
git commit -m "feat(fetch): Mapillary source credit and the Street Look request and answer formats

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Decode Mapillary's label tiles

**Files:**
- Create: `ghosttown/ghosttown_fetch/mvt.py`
- Create: `tests/fetch/mvt_samples.py`
- Test: `tests/fetch/test_mvt.py`

**Interfaces:**
- Produces: `mvt.TileError(ValueError)`; `mvt.decode_polygons(data: bytes) -> list[(layer_name, [exterior, *holes])]`, each ring a list of `(x, y)` fractions of the tile extent with y down. Test helpers `mvt_samples.tile(polygons, *, name="mpy-or", extent=4096, kind=3) -> bytes` and `mvt_samples.detection(value, polygon_fraction, extent=4096) -> {"value", "geometry"}` (base64, exterior oriented as the spec requires).

- [ ] **Step 1: Write the test helper and the failing tests**

Create `tests/fetch/mvt_samples.py`:

```python
"""A minimal Mapbox Vector Tile encoder for tests: one layer of polygon features."""
import base64


def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _field(number, wire, payload):
    key = _varint((number << 3) | wire)
    if wire == 0:
        return key + _varint(payload)
    return key + _varint(len(payload)) + payload


def _zigzag(n):
    return (n << 1) ^ (n >> 63)


def _commands(rings):
    cmds, x, y = [], 0, 0
    for ring in rings:
        (x0, y0), rest = ring[0], ring[1:]
        cmds += [1 | (1 << 3), _zigzag(x0 - x), _zigzag(y0 - y)]
        x, y = x0, y0
        cmds.append(2 | (len(rest) << 3))
        for px, py in rest:
            cmds += [_zigzag(px - x), _zigzag(py - y)]
            x, y = px, py
        cmds.append(7 | (1 << 3))
    return cmds


def tile(polygons, *, name="mpy-or", extent=4096, kind=3):
    """One layer; each polygon is a list of rings of integer tile coordinates."""
    features = b""
    for rings in polygons:
        packed = b"".join(_varint(c) for c in _commands(rings))
        features += _field(2, 2, _field(3, 0, kind) + _field(4, 2, packed))
    layer = _field(15, 0, 2) + _field(1, 2, name.encode("utf-8")) + features + _field(5, 0, extent)
    return _field(3, 2, layer)


def _area(ring):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]))


def detection(value, polygon_fraction, extent=4096):
    """A Mapillary-style label: its value and a base64 tile with one polygon given as (u, v) fractions."""
    ring = [(round(u * extent), round(v * extent)) for u, v in polygon_fraction]
    if _area(ring) < 0:
        ring.reverse()   # exterior rings have positive area in tile coordinates (y down)
    return {"value": value, "geometry": base64.b64encode(tile([[ring]], extent=extent)).decode("ascii")}
```

Create `tests/fetch/test_mvt.py`:

```python
import base64

import pytest

from ghosttown_fetch import mvt
from mvt_samples import detection, tile

SQUARE = [(0, 0), (4096, 0), (4096, 4096), (0, 4096)]


def test_a_rectangle_comes_back_as_fractions_of_the_extent():
    (layer, rings), = mvt.decode_polygons(tile([[[(0, 0), (2048, 0), (2048, 1024), (0, 1024)]]]))
    assert layer == "mpy-or"
    assert rings == [[(0.0, 0.0), (0.5, 0.0), (0.5, 0.25), (0.0, 0.25)]]


def test_holes_stay_with_their_polygon():
    hole = [(1024, 1024), (1024, 3072), (3072, 3072), (3072, 1024)]   # opposite winding
    other = [(100, 100), (200, 100), (200, 200), (100, 200)]
    polys = mvt.decode_polygons(tile([[SQUARE, hole], [other]]))
    assert [len(rings) for _, rings in polys] == [2, 1]


def test_negative_deltas_and_other_extents():
    ring = [(300, 300), (100, 300), (100, 100), (300, 100)]   # drawn leftwards and upwards
    (_, rings), = mvt.decode_polygons(tile([[ring]], extent=400))
    assert rings[0] == [(0.75, 0.75), (0.25, 0.75), (0.25, 0.25), (0.75, 0.25)]


def test_lines_and_points_are_skipped():
    assert mvt.decode_polygons(tile([[[(0, 0), (10, 0), (10, 10)]]], kind=2)) == []


def test_a_cut_short_tile_is_an_error():
    data = tile([[SQUARE]])
    with pytest.raises(mvt.TileError):
        mvt.decode_polygons(data[:-5])


def test_detection_helper_orients_and_encodes():
    det = detection("nature--sky", [(0, 0), (0, 0.5), (1, 0.5), (1, 0)])   # counter-clockwise on screen
    (_, rings), = mvt.decode_polygons(base64.b64decode(det["geometry"]))
    assert det["value"] == "nature--sky" and len(rings) == 1 and len(rings[0]) == 4
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `uv run pytest tests/fetch/test_mvt.py -v`
Expected: FAIL with `ImportError: cannot import name 'mvt'`.

- [ ] **Step 3: Implement** `ghosttown/ghosttown_fetch/mvt.py`

```python
"""Polygons from a Mapbox Vector Tile, the format of Mapillary's image labels. Standard library only.

Coordinates come back as fractions of the tile extent with y pointing down, which for Mapillary's labels
are fractions of the image's width and height."""
MOVE_TO, LINE_TO, CLOSE_PATH = 1, 2, 7
POLYGON = 3


class TileError(ValueError):
    """The tile can't be read."""


def _varint(buf, i):
    shift = value = 0
    while True:
        if i >= len(buf):
            raise TileError("The tile ends inside a number.")
        b = buf[i]
        i += 1
        value |= (b & 0x7F) << shift
        if not b & 0x80:
            return value, i
        shift += 7
        if shift > 63:
            raise TileError("A number in the tile is too long.")


def _fields(buf):
    """(field number, wire type, value) for each field; length-delimited values are bytes."""
    i, out = 0, []
    while i < len(buf):
        key, i = _varint(buf, i)
        field, wire = key >> 3, key & 7
        if wire == 0:
            value, i = _varint(buf, i)
        elif wire == 2:
            n, i = _varint(buf, i)
            if i + n > len(buf):
                raise TileError("A field runs past the end of the tile.")
            value, i = bytes(buf[i:i + n]), i + n
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            if i + size > len(buf):
                raise TileError("A field runs past the end of the tile.")
            value, i = bytes(buf[i:i + size]), i + size
        else:
            raise TileError(f"Unknown wire type {wire}.")
        out.append((field, wire, value))
    return out


def _packed(value):
    nums, i = [], 0
    while i < len(value):
        n, i = _varint(value, i)
        nums.append(n)
    return nums


def _zigzag(n):
    return (n >> 1) ^ -(n & 1)


def _rings(commands):
    rings, ring, x, y, i = [], [], 0, 0, 0
    while i < len(commands):
        cmd, count = commands[i] & 7, commands[i] >> 3
        i += 1
        if cmd in (MOVE_TO, LINE_TO):
            if i + 2 * count > len(commands):
                raise TileError("A path in the tile is cut short.")
            for _ in range(count):
                x += _zigzag(commands[i])
                y += _zigzag(commands[i + 1])
                i += 2
                if cmd == MOVE_TO:
                    if len(ring) >= 3:
                        rings.append(ring)
                    ring = [(x, y)]
                else:
                    ring.append((x, y))
        elif cmd == CLOSE_PATH:
            if len(ring) >= 3:
                rings.append(ring)
            ring = []
        else:
            raise TileError(f"Unknown path command {cmd}.")
    if len(ring) >= 3:
        rings.append(ring)
    return rings


def _area(ring):
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]))


def decode_polygons(data):
    """[(layer name, [exterior, *holes])] for every polygon feature. A ring with positive area in tile
    coordinates starts a new polygon (as the MVT spec defines exteriors); the rings after it with negative
    area are its holes."""
    out = []
    for field, wire, layer in _fields(data):
        if field != 3 or wire != 2:
            continue
        name, extent, features = "", 4096, []
        for f2, w2, v2 in _fields(layer):
            if f2 == 1 and w2 == 2:
                name = v2.decode("utf-8", "replace")
            elif f2 == 5 and w2 == 0:
                extent = v2 or 4096
            elif f2 == 2 and w2 == 2:
                features.append(v2)
        for feature in features:
            kind, geometry = 0, []
            for f3, w3, v3 in _fields(feature):
                if f3 == 3 and w3 == 0:
                    kind = v3
                elif f3 == 4 and w3 == 2:
                    geometry = _packed(v3)
            if kind != POLYGON:
                continue
            polygon = None
            for ring in _rings(geometry):
                scaled = [(px / extent, py / extent) for px, py in ring]
                if polygon is None or _area(ring) > 0:
                    polygon = [scaled]
                    out.append((name, polygon))
                else:
                    polygon.append(scaled)
    return out
```

- [ ] **Step 4: Run the tests to make sure they pass**

Run: `uv run pytest tests/fetch/test_mvt.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ghosttown/ghosttown_fetch/mvt.py tests/fetch/mvt_samples.py tests/fetch/test_mvt.py
git commit -m "feat(fetch): decode Mapillary's vector-tile labels without protobuf

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Mapillary cameras in the local frame

**Files:**
- Create: `ghosttown/ghosttown_fetch/camera.py`
- Create: `tests/fetch/camera_samples.py`
- Test: `tests/fetch/test_camera.py`

**Interfaces:**
- Consumes: `Frame.to_local(lon, lat)`, terrain objects with `.z(xs, ys)` (`FlatTerrain`, `GridTerrain`).
- Produces: `camera.MOUNT_M = 2.0`, `THUMB_PX = 2048`, `MAX_R2 = 1.2`, `KINDS`; `rotvec_to_matrix(r) -> (3,3)`; `Camera(image_id, kind, position, R, *, focal=0.0, k1=0.0, k2=0.0, width, height, year, sequence="")` with `.id`, `.kind`, `.position`, `.R` (world offsets to camera axes x right, y down, z forward), `.focal`, `.k1`, `.k2`, `.width`, `.height`, `.year`, `.sequence`; `Camera.from_mapillary(image, frame, terrain) -> Camera | None`; `.forward`; `.pitch_deg()`; `.project(points) -> (u, v, ok)` (fractions from the top-left); `.pixels_per_metre(points, cos_incidence)`; `.rays(grid_w) -> (dirs (n, 3), rows)`. Test helpers `camera_samples.look_at(heading_deg, pitch_deg=0.0)`, `rotation_vector(R)`, `camera(position, heading_deg=0.0, pitch_deg=0.0, *, kind="perspective", focal=0.6, k1=0.0, k2=0.0, width=2048, height=1536, year=2024, image_id="c1")`.

- [ ] **Step 1: Write the test helper and the failing tests**

Create `tests/fetch/camera_samples.py`:

```python
import math

import numpy as np


def look_at(heading_deg, pitch_deg=0.0):
    """World-to-camera rotation for a camera looking along a compass heading (0 = north, clockwise) and
    tilted up by pitch: rows are the camera's right, down and forward axes."""
    h, p = math.radians(heading_deg), math.radians(pitch_deg)
    forward = np.array([math.sin(h) * math.cos(p), math.cos(h) * math.cos(p), math.sin(p)])
    right = np.array([math.cos(h), -math.sin(h), 0.0])
    down = np.cross(forward, right)
    return np.array([right, down, forward])


def rotation_vector(R):
    """Axis-angle vector of a rotation matrix. Not for half turns, which the tests never use."""
    angle = math.acos(max(-1.0, min(1.0, (np.trace(R) - 1) / 2)))
    if angle < 1e-9:
        return [0.0, 0.0, 0.0]
    axis = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]) / (2 * math.sin(angle))
    return (axis * angle).tolist()


def camera(position, heading_deg=0.0, pitch_deg=0.0, *, kind="perspective", focal=0.6, k1=0.0, k2=0.0,
           width=2048, height=1536, year=2024, image_id="c1"):
    from ghosttown_fetch.camera import Camera

    return Camera(image_id, kind, position, look_at(heading_deg, pitch_deg), focal=focal, k1=k1, k2=k2,
                  width=width, height=height, year=year)
```

Create `tests/fetch/test_camera.py`:

```python
import math

import numpy as np
import pytest

from ghosttown_fetch.camera import Camera, rotvec_to_matrix
from ghosttown_fetch.frame import Frame
from ghosttown_fetch.terrain import FlatTerrain
from camera_samples import camera, look_at, rotation_vector


def test_rotation_vectors_round_trip():
    assert np.allclose(rotvec_to_matrix([0, 0, 0]), np.eye(3))
    for heading, pitch in ((0, 0), (30, 5), (-40, -8)):
        R = look_at(heading, pitch)
        assert np.allclose(rotvec_to_matrix(rotation_vector(R)), R, atol=1e-9)


def test_a_camera_facing_north_sees_north_ahead():
    cam = camera((0, 0, 2))
    assert np.allclose(cam.forward, [0, 1, 0]) and abs(cam.pitch_deg()) < 1e-9
    u, v, ok = cam.project(np.array([[0, 10, 2], [3, 10, 2], [0, 10, 5], [0, -10, 2]]))
    assert ok.tolist() == [True, True, True, False]
    assert abs(u[0] - 0.5) < 1e-9 and abs(v[0] - 0.5) < 1e-9
    assert u[1] > 0.5 and v[2] < 0.5


def test_pitch_is_measured_from_level():
    assert abs(camera((0, 0, 2), pitch_deg=10).pitch_deg() - 10) < 1e-9


@pytest.mark.parametrize("kind,k1,k2,height", [("perspective", -0.1, 0.02, 1200), ("fisheye", 0.05, -0.01, 1200),
                                               ("spherical", 0.0, 0.0, 800)])
def test_rays_land_back_on_their_pixels(kind, k1, k2, height):
    cam = camera((5, -3, 2), heading_deg=20, pitch_deg=4, kind=kind, k1=k1, k2=k2, width=1600, height=height)
    dirs, rows = cam.rays(40)
    u, v, ok = cam.project(cam.position + dirs * 25.0)
    gu, gv = np.meshgrid((np.arange(40) + 0.5) / 40, (np.arange(rows) + 0.5) / rows)
    assert ok.mean() > 0.9
    assert np.allclose(u[ok], gu.ravel()[ok], atol=1e-6) and np.allclose(v[ok], gv.ravel()[ok], atol=1e-6)


def test_pixels_per_metre_falls_with_distance_and_angle():
    cam = camera((0, 0, 2))
    ppm = cam.pixels_per_metre(np.array([[0, 100, 2], [0, 50, 2]]), np.array([1.0, 0.5]))
    assert np.allclose(ppm, [0.6 * 2048 / 100, 0.6 * 2048 / 50 * 0.5])
    pano = camera((0, 0, 2), kind="spherical", width=4000, height=2000)
    assert np.isclose(pano.pixels_per_metre(np.array([[0, 100, 2]]), np.array([1.0]))[0], 2048 / (2 * math.pi) / 100)


RECORD = {"id": 77, "captured_at": 1717200000000, "camera_type": "perspective",
          "computed_geometry": {"type": "Point", "coordinates": [-79.38, 43.65]},
          "computed_rotation": [1.2, 0.0, 0.0], "camera_parameters": [0.55, -0.1, 0.01],
          "width": 4000, "height": 3000, "sequence": "abc"}


def test_from_mapillary_places_the_camera_on_the_ground():
    cam = Camera.from_mapillary(RECORD, Frame(43.65, -79.38), FlatTerrain())
    assert cam.id == "77" and cam.kind == "perspective" and cam.year == 2024 and cam.sequence == "abc"
    assert np.allclose(cam.position, [0, 0, 2.0]) and (cam.focal, cam.k1, cam.k2) == (0.55, -0.1, 0.01)


@pytest.mark.parametrize("change", [{"camera_parameters": None}, {"camera_type": "panorama"},
                                    {"computed_rotation": None}, {"width": 0}, {"computed_geometry": None}])
def test_from_mapillary_skips_records_it_cannot_use(change):
    record = dict(RECORD)
    record.update(change)
    assert Camera.from_mapillary(record, Frame(43.65, -79.38), FlatTerrain()) is None
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `uv run pytest tests/fetch/test_camera.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ghosttown_fetch.camera'`.

- [ ] **Step 3: Implement** `ghosttown/ghosttown_fetch/camera.py`

```python
"""Mapillary cameras in the site's local frame (x east, y north, z up): where they stand, where they look,
and where a point lands in the picture. Picture positions are fractions of width and height from the
top-left corner, the same for the original and the thumbnail."""
import math
import time

import numpy as np

MOUNT_M = 2.0     # camera height above the ground; Mapillary's altitudes are unreliable
THUMB_PX = 2048   # long side of the thumbnails Street Look downloads
MAX_R2 = 1.2      # perspective points further out than this sit in the lens's untrustworthy corners
KINDS = ("perspective", "fisheye", "spherical")


def rotvec_to_matrix(r):
    """Rotation matrix of an axis-angle vector (Rodrigues' formula)."""
    r = np.asarray(r, dtype=float)
    theta = float(np.linalg.norm(r))
    if theta < 1e-12:
        return np.eye(3)
    k = r / theta
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(theta) * K + (1 - math.cos(theta)) * K @ K


class Camera:
    """R turns world offsets into camera axes: x right, y down, z forward (OpenSfM's convention, which
    Mapillary's computed_rotation uses)."""

    def __init__(self, image_id, kind, position, R, *, focal=0.0, k1=0.0, k2=0.0, width, height, year,
                 sequence=""):
        self.id = str(image_id)
        self.kind = kind
        self.position = np.asarray(position, dtype=float)
        self.R = np.asarray(R, dtype=float)
        self.focal, self.k1, self.k2 = float(focal), float(k1), float(k2)
        self.width, self.height = int(width), int(height)
        self.year = int(year)
        self.sequence = sequence

    @classmethod
    def from_mapillary(cls, image, frame, terrain):
        """A Camera from one of Mapillary's image records, or None when it lacks what Street Look needs."""
        try:
            lon, lat = image["computed_geometry"]["coordinates"][:2]
            rotation = [float(c) for c in image["computed_rotation"]]
            kind = image["camera_type"]
            width, height = int(image["width"]), int(image["height"])
            year = time.gmtime(image["captured_at"] / 1000).tm_year
            params = [float(p) for p in (image.get("camera_parameters") or [])]
        except (KeyError, TypeError, ValueError, IndexError, OverflowError):
            return None
        if kind not in KINDS or width <= 0 or height <= 0 or len(rotation) != 3:
            return None
        if kind != "spherical" and not (params and params[0] > 0):
            return None
        x, y = frame.to_local(float(lon), float(lat))
        z = float(terrain.z(np.array([x]), np.array([y]))[0]) + MOUNT_M
        return cls(image["id"], kind, (x, y, z), rotvec_to_matrix(rotation),
                   focal=params[0] if params else 0.0, k1=params[1] if len(params) > 1 else 0.0,
                   k2=params[2] if len(params) > 2 else 0.0, width=width, height=height, year=year,
                   sequence=image.get("sequence") or "")

    @property
    def forward(self):
        return self.R[2]

    def pitch_deg(self):
        return math.degrees(math.asin(max(-1.0, min(1.0, float(self.forward[2])))))

    def project(self, points):
        """(u, v, ok) for (n, 3) points: picture fractions, and whether the point is in front of the camera
        in a trustworthy part of the lens. u and v can fall outside 0..1."""
        X = (np.asarray(points, dtype=float).reshape(-1, 3) - self.position) @ self.R.T
        if self.kind == "spherical":
            lon = np.arctan2(X[:, 0], X[:, 2])
            lat = np.arctan2(-X[:, 1], np.hypot(X[:, 0], X[:, 2]))
            u = lon / (2 * np.pi) + 0.5
            v = 0.5 - lat * self.width / (2 * np.pi * self.height)
            return u, v, np.ones(len(X), dtype=bool)
        z = X[:, 2]
        ok = z > 0.5
        zz = np.where(ok, z, 1.0)
        xn, yn = X[:, 0] / zz, X[:, 1] / zz
        if self.kind == "fisheye":
            r = np.hypot(xn, yn)
            th = np.arctan(r)
            s = np.where(r > 1e-9, th * (1 + self.k1 * th ** 2 + self.k2 * th ** 4) / np.maximum(r, 1e-9), 1.0)
        else:
            r2 = xn ** 2 + yn ** 2
            ok &= r2 < MAX_R2
            s = 1 + self.k1 * r2 + self.k2 * r2 ** 2
        side = max(self.width, self.height)
        u = self.focal * s * xn * side / self.width + 0.5
        v = self.focal * s * yn * side / self.height + 0.5
        return u, v, ok

    def pixels_per_metre(self, points, cos_incidence):
        """Thumbnail pixels per metre of wall at each point, shrunk by how obliquely the wall is seen."""
        dist = np.linalg.norm(np.asarray(points, dtype=float).reshape(-1, 3) - self.position, axis=1)
        if self.kind == "spherical":
            f_px = THUMB_PX * self.width / max(self.width, self.height) / (2 * np.pi)
        else:
            f_px = self.focal * THUMB_PX
        return f_px / np.maximum(dist, 1e-6) * np.asarray(cos_incidence, dtype=float)

    def rays(self, grid_w):
        """(directions, rows): unit world directions through the centres of a grid_w-wide pixel grid, row
        by row from the top-left."""
        rows = max(1, round(grid_w * self.height / self.width))
        U, V = np.meshgrid((np.arange(grid_w) + 0.5) / grid_w, (np.arange(rows) + 0.5) / rows)
        if self.kind == "spherical":
            lon = (U - 0.5) * 2 * np.pi
            lat = (0.5 - V) * 2 * np.pi * self.height / self.width
            X = np.stack([np.sin(lon) * np.cos(lat), -np.sin(lat), np.cos(lon) * np.cos(lat)], -1)
        else:
            side = max(self.width, self.height)
            xd = (U - 0.5) * self.width / (self.focal * side)
            yd = (V - 0.5) * self.height / (self.focal * side)
            if self.kind == "fisheye":
                rd = np.hypot(xd, yd)
                th = np.minimum(rd, 1.5)
                for _ in range(30):   # solve th * (1 + k1 th^2 + k2 th^4) = rd
                    f = th * (1 + self.k1 * th ** 2 + self.k2 * th ** 4) - rd
                    df = 1 + 3 * self.k1 * th ** 2 + 5 * self.k2 * th ** 4
                    th = th - f / np.where(np.abs(df) > 1e-9, df, 1e-9)
                scale = np.where(rd > 1e-9, np.tan(np.clip(th, 0.0, 1.5)) / np.maximum(rd, 1e-9), 1.0)
                xn, yn = xd * scale, yd * scale
            else:
                xn, yn = xd.copy(), yd.copy()
                for _ in range(20):   # undo the radial distortion
                    r2 = xn ** 2 + yn ** 2
                    s = 1 + self.k1 * r2 + self.k2 * r2 ** 2
                    xn, yn = xd / s, yd / s
            X = np.stack([xn, yn, np.ones_like(xn)], -1)
        D = X.reshape(-1, 3) @ self.R
        return D / np.linalg.norm(D, axis=1, keepdims=True), rows
```

- [ ] **Step 4: Run the tests to make sure they pass**

Run: `uv run pytest tests/fetch/test_camera.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ghosttown/ghosttown_fetch/camera.py tests/fetch/camera_samples.py tests/fetch/test_camera.py
git commit -m "feat(fetch): Mapillary camera poses, projection and rays

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Line of sight against building prisms

**Files:**
- Create: `ghosttown/ghosttown_fetch/raycast.py`
- Test: `tests/fetch/test_raycast.py`

**Interfaces:**
- Consumes: building dicts `{"id", "solids": [{"rings", "z0", "z1"}]}` (the `look_request.json` format).
- Produces: `raycast.Scene(buildings)` with `.ids`, `.solids` (shapely Polygons), `.solid_owner`, `.solid_z0`, `.solid_z1`, wall arrays `.A`, `.B` (n, 2), `.N` (n, 2, outward unit normals), `.wall_z0`, `.wall_z1`, `.wall_owner`, and `.base_z` (lowest z0 per building); `.first_hit(origins, dirs, max_dist) -> (owner int array, dist array)` (owner -1 and dist inf when nothing is hit); `.covered(points) -> bool array`. `first_hit` sends rays out in `SEGMENT_M = 50.0` m pieces, nearest first, querying the wall tree by bounding box and testing crossings in numpy: at 351 King St E (9,048 photos, 38,037 wall points) that took choosing photos from 70 ms to 4 ms per camera, with identical results.

- [ ] **Step 1: Write the failing tests** — create `tests/fetch/test_raycast.py`

```python
import math

import numpy as np

from ghosttown_fetch.raycast import Scene


def box(bid, x0, y0, x1, y1, z1=20.0, z0=0.0):
    return {"id": bid, "solids": [{"rings": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]], "z0": z0, "z1": z1}]}


def test_a_ray_stops_at_the_first_wall():
    scene = Scene([box("a", 0, 0, 10, 10)])
    owner, dist = scene.first_hit([[-5, 5, 1]], [[1, 0, 0]], 100.0)
    assert owner.tolist() == [0] and np.isclose(dist[0], 5.0)


def test_rays_over_the_roof_or_too_short_miss():
    scene = Scene([box("a", 0, 0, 10, 10)])
    owner, _ = scene.first_hit([[-5, 5, 25], [-5, 5, 1]], [[1, 0, 0], [1, 0, 0]], [100.0, 4.0])
    assert owner.tolist() == [-1, -1]


def test_a_rising_ray_hits_where_the_wall_is_tall_enough():
    scene = Scene([box("a", 0, 0, 10, 10)])
    d = np.array([[1, 0, 1]]) / math.sqrt(2)
    owner, dist = scene.first_hit([[-5, 5, 1]], d, 100.0)
    assert owner.tolist() == [0] and np.isclose(dist[0], 5 * math.sqrt(2))


def test_the_nearer_building_wins_and_vertical_rays_never_hit():
    scene = Scene([box("far", 20, 0, 30, 10), box("near", 0, 0, 10, 10)])
    owner, _ = scene.first_hit([[-5, 5, 1], [-5, 5, 1]], [[1, 0, 0], [0, 0, 1]], 100.0)
    assert owner.tolist() == [1, -1]


def test_normals_point_out_of_the_solid_also_into_courtyards():
    yard = {"id": "y", "solids": [{"rings": [[[0, 0], [0, 30], [30, 30], [30, 0]],     # given clockwise
                                             [[10, 10], [20, 10], [20, 20], [10, 20]]], "z0": 0.0, "z1": 10.0}]}
    scene = Scene([yard])
    west = np.isclose(scene.A[:, 0], 0) & np.isclose(scene.B[:, 0], 0)
    assert np.allclose(scene.N[west], [[-1, 0]])
    yard_west = np.isclose(scene.A[:, 0], 10) & np.isclose(scene.B[:, 0], 10)
    assert np.allclose(scene.N[yard_west], [[1, 0]])
    owner, dist = scene.first_hit([[15, 15, 1]], [[-1, 0, 0]], 100.0)   # from inside the courtyard
    assert owner.tolist() == [0] and np.isclose(dist[0], 5.0)


def test_covered_means_inside_the_footprint_and_under_the_roof():
    scene = Scene([box("a", 0, 0, 10, 10, z1=20.0)])
    assert scene.covered([[5, 5, 1], [5, 5, 25], [15, 5, 1]]).tolist() == [True, False, False]
    assert scene.base_z.tolist() == [0.0]
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `uv run pytest tests/fetch/test_raycast.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ghosttown_fetch.raycast'`.

- [ ] **Step 3: Implement** `ghosttown/ghosttown_fetch/raycast.py`

```python
"""Line of sight against Ghost Town's buildings. They are vertical prisms, so a ray can only be stopped by
a wall: each test is a 2D segment crossing plus a height check at the crossing. Rays that would come down
onto a roof are not stopped; street cameras rarely look down."""
import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

EPS = 1e-9
SEGMENT_M = 50.0   # rays are tested in pieces this long, nearest first


def _polygon(rings):
    """A solid's footprint: the ring with the largest area is the outline, rings inside it are courtyards.
    Exterior counter-clockwise, courtyards clockwise."""
    polys = sorted((Polygon(r) for r in rings if len(r) >= 3), key=lambda p: -abs(p.area))
    if not polys or abs(polys[0].area) <= 0:
        return None
    outer = Polygon(polys[0].exterior.coords)
    holes = [p.exterior.coords for p in polys[1:] if outer.contains(p)]
    poly = Polygon(outer.exterior.coords, holes)
    if not poly.is_valid:
        fixed = [g for g in shapely.get_parts(shapely.make_valid(poly)) if g.geom_type == "Polygon"]
        if not fixed:
            return None
        poly = max(fixed, key=lambda g: g.area)
    return orient(poly, sign=1.0)


class Scene:
    def __init__(self, buildings):
        self.ids = [b["id"] for b in buildings]
        polys, owners, z0s, z1s = [], [], [], []
        A, B, N, wz0, wz1, wown = [], [], [], [], [], []
        for bi, b in enumerate(buildings):
            for s in b["solids"]:
                poly = _polygon(s["rings"])
                if poly is None:
                    continue
                z0, z1 = float(s["z0"]), float(s["z1"])
                polys.append(poly)
                owners.append(bi)
                z0s.append(z0)
                z1s.append(z1)
                for ring in (poly.exterior, *poly.interiors):
                    pts = np.asarray(ring.coords)[:, :2]
                    for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
                        length = float(np.hypot(bx - ax, by - ay))
                        if length < 1e-6:
                            continue
                        A.append((ax, ay))
                        B.append((bx, by))
                        N.append(((by - ay) / length, -(bx - ax) / length))   # right of travel = outside
                        wz0.append(z0)
                        wz1.append(z1)
                        wown.append(bi)
        self.solids = polys
        self.solid_owner = np.asarray(owners, dtype=int)
        self.solid_z0 = np.asarray(z0s, dtype=float)
        self.solid_z1 = np.asarray(z1s, dtype=float)
        self.A = np.asarray(A, dtype=float).reshape(-1, 2)
        self.B = np.asarray(B, dtype=float).reshape(-1, 2)
        self.N = np.asarray(N, dtype=float).reshape(-1, 2)
        self.wall_z0 = np.asarray(wz0, dtype=float)
        self.wall_z1 = np.asarray(wz1, dtype=float)
        self.wall_owner = np.asarray(wown, dtype=int)
        self._walls = shapely.STRtree(shapely.linestrings(np.stack([self.A, self.B], 1))) if len(self.A) else None
        self._solids = shapely.STRtree(polys) if polys else None
        self.base_z = np.full(len(self.ids), np.inf)
        for bi, z0 in zip(self.solid_owner, self.solid_z0):
            self.base_z[bi] = min(self.base_z[bi], z0)

    def first_hit(self, origins, dirs, max_dist):
        """(owner, dist) per ray: the building index of the first wall each ray meets within max_dist
        metres (-1 for none) and the distance along the ray (inf for none). dirs are unit 3D vectors;
        one origin may serve every ray; max_dist is one number or one per ray."""
        D = np.asarray(dirs, dtype=float).reshape(-1, 3)
        n = len(D)
        O = np.asarray(origins, dtype=float).reshape(-1, 3)
        if len(O) == 1 and n > 1:
            O = np.repeat(O, n, axis=0)
        T = np.broadcast_to(np.asarray(max_dist, dtype=float), (n,))
        owner = np.full(n, -1, dtype=int)
        dist = np.full(n, np.inf)
        if self._walls is None or n == 0:
            return owner, dist
        live = np.nonzero(np.hypot(D[:, 0], D[:, 1]) > EPS)[0]   # vertical rays never meet a wall
        top = float(self.wall_z1.max())
        t0 = 0.0
        while len(live):
            # The rays go out in SEGMENT_M pieces, nearest first: a short piece's box meets only the walls
            # near it, so this costs far less than one query with the whole ray, and the first hit is the same.
            t1 = t0 + SEGMENT_M
            start = O[live, :2] + D[live, :2] * t0
            end = O[live, :2] + D[live, :2] * np.minimum(t1, T[live])[:, None]
            rays_i, walls_i = self._walls.query(shapely.linestrings(np.stack([start, end], 1)))   # boxes only
            r = live[rays_i]
            p0, d2 = O[r, :2], D[r, :2]
            a = self.A[walls_i]
            e = self.B[walls_i] - a
            denom = d2[:, 0] * e[:, 1] - d2[:, 1] * e[:, 0]
            ap = a - p0
            safe = np.where(np.abs(denom) > EPS, denom, 1.0)
            t = (ap[:, 0] * e[:, 1] - ap[:, 1] * e[:, 0]) / safe
            s = (ap[:, 0] * d2[:, 1] - ap[:, 1] * d2[:, 0]) / safe
            z = O[r, 2] + t * D[r, 2]
            good = ((np.abs(denom) > EPS) & (t > max(t0, 1e-6)) & (t <= np.minimum(t1, T[r]))
                    & (s >= -1e-9) & (s <= 1 + 1e-9)
                    & (z >= self.wall_z0[walls_i] - 1e-6) & (z <= self.wall_z1[walls_i] + 1e-6))
            r, t, w = r[good], t[good], walls_i[good]
            order = np.lexsort((t, r))
            r, t, w = r[order], t[order], w[order]
            first = np.ones(len(r), dtype=bool)
            first[1:] = r[1:] != r[:-1]
            owner[r[first]] = self.wall_owner[w[first]]
            dist[r[first]] = t[first]
            live = live[(owner[live] < 0) & (T[live] > t1)]
            live = live[~((D[live, 2] > 0) & (O[live, 2] + D[live, 2] * t1 > top))]   # above every roof, still rising
            t0 = t1
        return owner, dist

    def covered(self, points):
        """Whether each point is inside or under a solid: in its footprint and below its top."""
        P = np.asarray(points, dtype=float).reshape(-1, 3)
        out = np.zeros(len(P), dtype=bool)
        if self._solids is None or not len(P):
            return out
        pi, si = self._solids.query(shapely.points(P[:, :2]), predicate="intersects")
        hit = P[pi, 2] < self.solid_z1[si]
        out[pi[hit]] = True
        return out
```

- [ ] **Step 4: Run the tests to make sure they pass**

Run: `uv run pytest tests/fetch/test_raycast.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ghosttown/ghosttown_fetch/raycast.py tests/fetch/test_raycast.py
git commit -m "feat(fetch): 2.5D line of sight against building prisms

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The Mapillary source

**Files:**
- Create: `ghosttown/ghosttown_fetch/sources/mapillary.py`
- Test: `tests/fetch/test_mapillary.py`

**Interfaces:**
- Consumes: `Net.get(..., headers=, key=, keep=)`, `Net.cached(...)`, `SourceError(..., status=)` (Task 1); `Frame.to_lonlat`.
- Produces: `mapillary.API`, `TILE_M = 100.0`, `WORKERS = 8`, `LIST_FIELDS`, `REFUSED`; `TokenRejected(SourceError)`; `tiles(frame, radius_m) -> [(lon0, lat0, lon1, lat1)]`; `list_url(box) -> str`; `list_images(net, frame, radius_m, token, *, workers=WORKERS) -> (images, failed_tiles)`; `photo(net, image_id, token) -> bytes`; `detections(net, image_id, token) -> [{"value", "geometry"}]`; `fetch_many(fn, ids, *, workers=WORKERS) -> {id: result | SourceError}`.

- [ ] **Step 1: Write the failing tests** — create `tests/fetch/test_mapillary.py`

```python
import json

import pytest

from ghosttown_fetch.frame import Frame
from ghosttown_fetch.net import Net, SourceError
from ghosttown_fetch.sources import mapillary as m
from fakes import FakeNet, router

F = Frame(43.65, -79.38)
TOKEN = "MLY|secret"


def test_tiles_cover_the_circle_and_stay_bounded():
    assert len(m.tiles(F, 100)) == 4
    assert len(m.tiles(F, 150)) == 9
    assert len(m.tiles(F, 1000)) <= 400


def test_list_url_has_the_box_and_fields_but_no_token():
    url = m.list_url((-79.381, 43.649, -79.379, 43.651))
    assert url.startswith("https://graph.mapillary.com/images?") and "bbox=-79.3810000,43.6490000" in url
    assert "computed_rotation" in url and "MLY" not in url


def test_list_images_deduplicates_and_sends_the_token_in_a_header():
    body = json.dumps({"data": [{"id": "1"}, {"id": "2"}]}).encode()
    net = FakeNet({"mapillary": router({"/images?": body})})
    images, failed = m.list_images(net, F, 100, TOKEN)
    assert sorted(im["id"] for im in images) == ["1", "2"] and failed == 0
    assert net.headers and all(h["Authorization"] == "OAuth " + TOKEN for h in net.headers)
    assert all(TOKEN not in url for url, _source, _data in net.calls)


def test_a_failed_tile_is_counted_not_fatal():
    calls = []

    def answer(url, data):
        calls.append(url)
        if len(calls) == 1:
            return SourceError("Mapillary answered HTTP 500; try again in a minute.", status=500)
        return json.dumps({"data": [{"id": "1"}]}).encode()

    images, failed = m.list_images(FakeNet({"mapillary": answer}), F, 100, TOKEN, workers=1)
    assert failed == 1 and [im["id"] for im in images] == ["1"]


def test_a_rejected_token_stops_everything():
    net = FakeNet({"mapillary": SourceError("Mapillary answered HTTP 401; try again in a minute.", status=401)})
    with pytest.raises(m.TokenRejected, match="refused the token"):
        m.list_images(net, F, 100, TOKEN)


def test_an_unreadable_listing_is_a_source_error():
    net = FakeNet({"mapillary": b"<html>busy</html>"})
    images, failed = m.list_images(net, F, 100, TOKEN, workers=1)
    assert images == [] and failed == 4


class Transport:
    """Answers by URL substring, for a real Net."""

    def __init__(self, table):
        self.table, self.calls = table, []

    def __call__(self, url, data, headers, timeout):
        self.calls.append((url, headers))
        for key, body in self.table.items():
            if key in url:
                return 200, body
        return 404, b""


JPEG = b"\xff\xd8\xff" + b"x" * 200


def test_photos_are_cached_by_image_id_and_signed_links_are_not_stored(tmp_path):
    link = json.dumps({"id": "77", "thumb_2048_url": "https://cdn.example/77.jpg?sig=a"}).encode()
    t = Transport({"/77?fields=thumb_2048_url": link, "cdn.example/77.jpg": JPEG})
    net = Net(str(tmp_path), transport=t)
    assert m.photo(net, "77", TOKEN) == JPEG
    assert m.photo(net, "77", TOKEN) == JPEG
    assert len(t.calls) == 2                       # one link lookup, one download, then the cache
    assert not any(b"sig=a" in p.read_bytes() for p in (tmp_path / "mapillary").iterdir())
    assert "Authorization" not in t.calls[1][1]    # the image server never sees the token


def test_detections_keep_only_usable_entries():
    body = json.dumps({"data": [{"value": "nature--sky", "geometry": "AAAA"}, {"value": "x"}]}).encode()
    net = FakeNet({"mapillary": router({"/detections": body})})
    assert m.detections(net, "77", TOKEN) == [{"value": "nature--sky", "geometry": "AAAA"}]


def test_fetch_many_collects_failures_per_id():
    def fn(i):
        if i == "b":
            raise SourceError("nope")
        return i.upper()

    out = m.fetch_many(fn, ["a", "b"])
    assert out["a"] == "A" and isinstance(out["b"], SourceError)
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `uv run pytest tests/fetch/test_mapillary.py -v`
Expected: FAIL with `ImportError: cannot import name 'mapillary'`.

- [ ] **Step 3: Implement** `ghosttown/ghosttown_fetch/sources/mapillary.py`

```python
"""Mapillary street photos: listings by map tile, thumbnails and each image's labels.

The token travels in a header, never in a URL, so it is never part of a cache key. Thumbnail links are
signed and expire, so photos are cached by image id and the links themselves are never stored."""
import json
import math
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from ..net import SourceError

API = "https://graph.mapillary.com"
TILE_M = 100.0
WORKERS = 8
LIMIT = 2000
LIST_FIELDS = ("id,captured_at,camera_type,computed_geometry,computed_rotation,camera_parameters,width,"
               "height,sequence")
REFUSED = "Mapillary refused the token; check it in Preferences."
UNREADABLE = "Mapillary sent an answer that couldn't be read."


class TokenRejected(SourceError):
    """Mapillary said no to the token."""


def _json(body):
    try:
        doc = json.loads(body)
    except ValueError:
        raise SourceError(UNREADABLE) from None
    if not isinstance(doc, dict):
        raise SourceError(UNREADABLE)
    return doc


def check_json(body):
    _json(body)


def check_jpeg(body):
    if not (len(body) > 100 and body[:3] == b"\xff\xd8\xff"):
        raise SourceError("Mapillary sent a photo that couldn't be read.")


def _api(net, url, token, **kwargs):
    try:
        return net.get(url, source="mapillary", headers={"Authorization": "OAuth " + token}, **kwargs)
    except SourceError as e:
        if getattr(e, "status", None) in (401, 403):
            raise TokenRejected(REFUSED, status=e.status) from None
        raise


def tiles(frame, radius_m):
    """Boxes (lon0, lat0, lon1, lat1) of TILE_M squares that touch the circle."""
    n = max(1, math.ceil(2 * radius_m / TILE_M))
    half = n * TILE_M / 2
    out = []
    for i in range(n):
        for j in range(n):
            x0, y0 = -half + i * TILE_M, -half + j * TILE_M
            x1, y1 = x0 + TILE_M, y0 + TILE_M
            nearest_x, nearest_y = min(max(0.0, x0), x1), min(max(0.0, y0), y1)
            if math.hypot(nearest_x, nearest_y) > radius_m:
                continue
            lon0, lat0 = frame.to_lonlat(x0, y0)
            lon1, lat1 = frame.to_lonlat(x1, y1)
            out.append((lon0, lat0, lon1, lat1))
    return out


def list_url(box):
    query = urllib.parse.urlencode({"bbox": ",".join(f"{v:.7f}" for v in box), "fields": LIST_FIELDS,
                                    "limit": LIMIT}, safe=",")
    return f"{API}/images?{query}"


def list_images(net, frame, radius_m, token, *, workers=WORKERS):
    """(images, failed): image records within the circle, one per id, and how many tiles couldn't be
    listed. A rejected token stops everything."""
    def one(box):
        try:
            return _json(_api(net, list_url(box), token, check=check_json)).get("data") or [], None
        except TokenRejected:
            raise
        except SourceError as e:
            return [], e

    seen, failed = {}, 0
    with ThreadPoolExecutor(workers) as pool:
        for data, error in pool.map(one, tiles(frame, radius_m)):
            if error is not None:
                failed += 1
            for image in data:
                if isinstance(image, dict) and "id" in image:
                    seen[str(image["id"])] = image
    return list(seen.values()), failed


def photo(net, image_id, token):
    """The 2048 px thumbnail as JPEG bytes, cached by image id."""
    key = f"photo:{image_id}:2048"
    body = net.cached("mapillary", key, check=check_jpeg)
    if body is not None:
        return body
    link = _json(_api(net, f"{API}/{image_id}?fields=thumb_2048_url", token, check=check_json, keep=False))
    url = link.get("thumb_2048_url")
    if not url:
        raise SourceError("Mapillary has no thumbnail for one of the photos.")
    return net.get(url, source="mapillary", key=key, check=check_jpeg)


def detections(net, image_id, token):
    """Mapillary's labels for one image: [{"value", "geometry"}], geometry being a base64 vector tile."""
    doc = _json(_api(net, f"{API}/{image_id}/detections?fields=value,geometry", token, check=check_json))
    return [d for d in doc.get("data") or [] if isinstance(d, dict) and "value" in d and "geometry" in d]


def fetch_many(fn, ids, *, workers=WORKERS):
    """{id: fn(id) or the SourceError it raised}, run in parallel. A rejected token propagates."""
    def one(i):
        try:
            return i, fn(i)
        except TokenRejected:
            raise
        except SourceError as e:
            return i, e

    with ThreadPoolExecutor(workers) as pool:
        return dict(pool.map(one, list(ids)))
```

- [ ] **Step 4: Run the tests to make sure they pass**

Run: `uv run pytest tests/fetch/test_mapillary.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ghosttown/ghosttown_fetch/sources/mapillary.py tests/fetch/test_mapillary.py
git commit -m "feat(fetch): Mapillary listings, thumbnails and labels with the token in a header

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Which photos see which walls

**Files:**
- Create: `ghosttown/ghosttown_fetch/selection.py`
- Test: `tests/fetch/test_selection.py`

**Interfaces:**
- Consumes: `raycast.Scene` (Task 5), `camera.Camera` (Task 4), test helper `camera_samples.camera`.
- Produces: constants `SPACING_ALONG_M = 3.0`, `SPACING_UP_M = 4.0`, `MIN_DIST_M = 3.0`, `MAX_DIST_M = 500.0`, `MAX_INCIDENCE_DEG = 35.0`, `MAX_PITCH_DEG = 12.0`, `FRAME_MARGIN = 0.02`, `USABLE_PPM = 5.0`, `PPM_CAP = 20.0`, `PER_BUILDING = 4`, `SIGHT_TOLERANCE_M = 1.0`; `THIN_CELL_M = 5.0`, `THIN_HEADING_DEG = 30.0`; class `Samples` with arrays `.P (n, 3)`, `.N (n, 2)`, `.building`, `.wall`, `.area`, `.height` (above the building's lowest point) and `.only(building indices) -> Samples`; `wall_samples(scene) -> Samples`; `thin(cameras) -> [Camera]` (the newest per 5 m cell and 30° of heading); `views(cameras, samples, scene) -> {camera index: (sample indices, pixels per metre)}`; `recency(year) -> float`; `priority(scene, detail_ids) -> [building index]`; `choose(cameras, seen, samples, *, budget, order) -> {building index: [camera index]}`.

- [ ] **Step 1: Write the failing tests** — create `tests/fetch/test_selection.py`

```python
import numpy as np

from ghosttown_fetch import raycast, selection
from camera_samples import camera


def box(bid, x0, y0, x1, y1, z1=30.0):
    return {"id": bid, "solids": [{"rings": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]], "z0": 0.0, "z1": z1}]}


BOX = box("a", -10, -10, 10, 10)


def _views(cams, scene):
    s = selection.wall_samples(scene)
    return s, selection.views(cams, s, scene)


def test_samples_cover_every_exposed_wall():
    s = selection.wall_samples(raycast.Scene([BOX]))
    assert np.isclose(s.area.sum(), 80 * 30)
    assert set(np.round(s.height, 3)) == set(np.round(np.arange(8) * 3.75 + 1.875, 3))


def test_a_shared_wall_is_not_exposed():
    s = selection.wall_samples(raycast.Scene([box("a", 0, 0, 10, 10), box("b", 10, 0, 20, 10)]))
    assert not np.any(np.isclose(s.P[:, 0], 10.0))


def test_a_level_camera_square_on_sees_the_facing_wall_only():
    s, seen = _views([camera((0, -60, 2))], raycast.Scene([BOX]))
    idx, ppm = seen[0]
    assert len(idx) > 10 and np.allclose(s.N[idx], [0, -1]) and np.all(ppm > 5)


def test_pitched_distant_oblique_and_blocked_views_are_left_out():
    scene = raycast.Scene([BOX, box("wall", -30, -40, 30, -38, z1=40.0)])
    cams = [camera((0, -60, 2), pitch_deg=20), camera((0, -600, 2)), camera((-60, -60, 2), heading_deg=45),
            camera((0, -60, 2))]
    s, seen = _views(cams, scene)
    assert 0 not in seen and 1 not in seen          # pitched, too far
    for ci in (2, 3):                                # oblique to the target, blocked by the wall
        assert ci not in seen or not np.any(s.building[seen[ci][0]] == 0)


def test_a_camera_inside_a_building_sees_nothing():
    _s, seen = _views([camera((0, 0, 2))], raycast.Scene([BOX]))
    assert seen == {}


def test_thin_keeps_the_newest_photo_per_place_and_heading():
    old = camera((1, 1, 2), heading_deg=90, year=2016, image_id="old")
    new = camera((3, 4, 2), heading_deg=100, year=2024, image_id="new")      # same 5 m cell and 30° of heading
    back = camera((2, 2, 2), heading_deg=270, year=2016, image_id="back")    # same cell, looking the other way
    far = camera((12, 1, 2), heading_deg=90, year=2016, image_id="far")      # two cells along
    pano = camera((1, 2, 2), kind="spherical", year=2019, image_id="pano")
    pano2 = camera((4, 3, 2), heading_deg=180, kind="spherical", year=2015, image_id="pano2")   # heading is moot
    kept = [c.id for c in selection.thin([old, new, back, far, pano, pano2])]
    assert sorted(kept) == ["back", "far", "new", "pano"]


def test_recency_weights():
    assert [selection.recency(y) for y in (2025, 2022, 2019, 2015)] == [1.0, 1.0, 0.8, 0.6]


def test_choose_spends_the_budget_then_shares_what_was_chosen():
    scene = raycast.Scene([BOX, box("b", 40, -10, 60, 10)])
    spots = [(0, 0), (5, 0), (-5, 0), (50, 0), (30, 15), (20, 10)]
    cams = [camera((x, -70, 2), heading_deg=h, image_id=f"c{i}") for i, (x, h) in enumerate(spots)]
    s, seen = _views(cams, scene)
    picks = selection.choose(cams, seen, s, budget=3, order=[0, 1])
    chosen = {c for v in picks.values() for c in v}
    assert len(chosen) <= 3 and len(picks[0]) <= selection.PER_BUILDING
    assert set(picks.get(1, [])) <= set(picks[0])


def test_choose_prefers_recent_photos():
    cams = [camera((0, -60, 2), year=2015, image_id="old"), camera((0, -60.5, 2), year=2025, image_id="new")]
    s, seen = _views(cams, raycast.Scene([BOX]))
    assert selection.choose(cams, seen, s, budget=10, order=[0])[0][0] == 1


def test_priority_puts_detail_buildings_first():
    scene = raycast.Scene([box("near", 0, 0, 10, 10), box("far", 200, 0, 210, 10)])
    assert selection.priority(scene, set()) == [0, 1]
    assert selection.priority(scene, {"far"}) == [1, 0]
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `uv run pytest tests/fetch/test_selection.py -v`
Expected: FAIL with `ImportError: cannot import name 'selection'`.

- [ ] **Step 3: Implement** `ghosttown/ghosttown_fetch/selection.py`

```python
"""Which photos see which walls, and which photos to download.

A wall point counts as seen by a photo when the camera is 3-500 m away, faces the wall within 35 degrees of
square-on (in plan), is level (perspective and fisheye cameras within 12 degrees of pitch), has the point
inside the picture, and nothing stands between them."""
import math

import numpy as np

SPACING_ALONG_M, SPACING_UP_M = 3.0, 4.0
PROBE_M = 0.3
MIN_DIST_M, MAX_DIST_M = 3.0, 500.0
MAX_INCIDENCE_DEG = 35.0
MAX_PITCH_DEG = 12.0
FRAME_MARGIN = 0.02
USABLE_PPM = 5.0
PPM_CAP = 20.0
PER_BUILDING = 4
SIGHT_TOLERANCE_M = 1.0
FREE_BONUS = 1.5   # a photo already chosen for another building costs nothing
THIN_CELL_M, THIN_HEADING_DEG = 5.0, 30.0


class Samples:
    """Points on the buildings' exposed walls, with their wall's outward normal, owner, wall index, the
    wall area each stands for, and height above the owner's lowest point."""

    def __init__(self, P, N, building, wall, area, height):
        self.P, self.N, self.building, self.wall, self.area, self.height = P, N, building, wall, area, height

    def __len__(self):
        return len(self.P)

    def only(self, buildings):
        """The samples on these buildings (indices)."""
        m = np.isin(self.building, list(buildings))
        return Samples(self.P[m], self.N[m], self.building[m], self.wall[m], self.area[m], self.height[m])


def wall_samples(scene):
    P, N, owners, walls, areas, heights = [], [], [], [], [], []
    for w in range(len(scene.A)):
        a, b = scene.A[w], scene.B[w]
        z0, z1 = scene.wall_z0[w], scene.wall_z1[w]
        length, tall = float(np.hypot(*(b - a))), float(z1 - z0)
        nu = max(1, round(length / SPACING_ALONG_M))
        nv = max(1, round(tall / SPACING_UP_M))
        S, T = np.meshgrid((np.arange(nu) + 0.5) / nu, (np.arange(nv) + 0.5) / nv)
        xy = a + (b - a) * S.reshape(-1, 1)
        pts = np.column_stack([xy, z0 + tall * T.reshape(-1)])
        probe = pts.copy()
        probe[:, :2] += scene.N[w] * PROBE_M
        keep = ~scene.covered(probe)
        k = int(keep.sum())
        if not k:
            continue
        owner = int(scene.wall_owner[w])
        P.append(pts[keep])
        N.append(np.repeat(scene.N[w][None], k, axis=0))
        owners.append(np.full(k, owner))
        walls.append(np.full(k, w))
        areas.append(np.full(k, length * tall / (nu * nv)))
        heights.append(pts[keep, 2] - scene.base_z[owner])
    if not P:
        empty = np.zeros(0)
        return Samples(np.zeros((0, 3)), np.zeros((0, 2)), empty.astype(int), empty.astype(int), empty, empty)
    return Samples(np.concatenate(P), np.concatenate(N), np.concatenate(owners), np.concatenate(walls),
                   np.concatenate(areas), np.concatenate(heights))


def thin(cameras, cell_m=THIN_CELL_M, heading_deg=THIN_HEADING_DEG):
    """The newest camera per 5 m cell and 30° of heading (360° photos: per cell). Mapillary shoots every few
    metres along a street, and photos that close see the same walls: at 351 King St E this kept 5,937 of
    9,048 photos for about 1% less wall area seen well."""
    best = {}
    for i, c in enumerate(cameras):
        spherical = c.kind == "spherical"
        heading = None if spherical else int(math.degrees(math.atan2(c.forward[0], c.forward[1])) % 360 // heading_deg)
        key = (spherical, int(c.position[0] // cell_m), int(c.position[1] // cell_m), heading)
        j = best.get(key)
        if j is None or (c.year, c.id) > (cameras[j].year, cameras[j].id):
            best[key] = i
    return [cameras[i] for i in sorted(best.values())]


def views(cameras, samples, scene):
    """{camera index: (sample indices, pixels per metre)} for each camera that sees at least one point."""
    out = {}
    if not len(samples):
        return out
    cos_max = math.cos(math.radians(MAX_INCIDENCE_DEG))
    for ci, cam in enumerate(cameras):
        if cam.kind != "spherical" and abs(cam.pitch_deg()) > MAX_PITCH_DEG:
            continue
        if scene.covered(cam.position[None])[0]:
            continue   # a pose inside a building is wrong; it would "see" walls from inside
        d = samples.P - cam.position
        flat = np.hypot(d[:, 0], d[:, 1])
        m = (flat >= MIN_DIST_M) & (flat <= MAX_DIST_M)
        cos_inc = -(d[:, 0] * samples.N[:, 0] + d[:, 1] * samples.N[:, 1]) / np.maximum(flat, 1e-9)
        m &= cos_inc >= cos_max
        idx = np.nonzero(m)[0]
        if not len(idx):
            continue
        u, v, ok = cam.project(samples.P[idx])
        inside = ok & (u >= FRAME_MARGIN) & (u <= 1 - FRAME_MARGIN) & (v >= FRAME_MARGIN) & (v <= 1 - FRAME_MARGIN)
        idx = idx[inside]
        if not len(idx):
            continue
        target = samples.P[idx].copy()
        target[:, :2] += samples.N[idx] * 0.05
        ray = target - cam.position
        dist = np.linalg.norm(ray, axis=1)
        owner, hit = scene.first_hit(cam.position[None], ray / dist[:, None], dist + 0.5)
        idx = idx[(owner == samples.building[idx]) & (np.abs(hit - dist) <= SIGHT_TOLERANCE_M)]
        if len(idx):
            out[ci] = (idx, cam.pixels_per_metre(samples.P[idx], cos_inc[idx]))
    return out


def recency(year):
    if year >= 2022:
        return 1.0
    if year >= 2018:
        return 0.8
    return 0.6


def priority(scene, detail_ids):
    """Building indices: detail buildings first, then by distance from the site centre."""
    centres = {}
    for poly, b in zip(scene.solids, scene.solid_owner):
        c = poly.centroid
        centres.setdefault(int(b), []).append((c.x, c.y))
    dist = {b: float(np.hypot(*np.mean(v, axis=0))) for b, v in centres.items()}
    return sorted(dist, key=lambda b: (scene.ids[b] not in detail_ids, dist[b]))


def choose(cameras, seen, samples, *, budget, order):
    """{building index: [camera indices]}: up to PER_BUILDING photos per building, buildings in `order`,
    each pick the photo adding the most wall area x sharpness x recency (points already covered count
    half as much each time). A new photo costs one from the budget; photos already chosen are free, so
    once the budget is spent later buildings can still use them."""
    by_building = {}
    for ci, (idx, ppm) in seen.items():
        usable = idx[ppm >= USABLE_PPM]
        for b in np.unique(samples.building[usable]):
            by_building.setdefault(int(b), []).append(ci)
    chosen, picks = set(), {}
    for b in order:
        candidates = by_building.get(b)
        if not candidates:
            continue
        times = np.zeros(len(samples))
        picked = []
        for _ in range(PER_BUILDING):
            best, best_gain = None, 0.0
            for ci in candidates:
                if ci in picked or (ci not in chosen and len(chosen) >= budget):
                    continue
                idx, ppm = seen[ci]
                mine = (samples.building[idx] == b) & (ppm >= USABLE_PPM)
                if not mine.any():
                    continue
                k = idx[mine]
                gain = float((samples.area[k] * np.minimum(ppm[mine], PPM_CAP) / PPM_CAP * 0.5 ** times[k]).sum())
                gain *= recency(cameras[ci].year) * (FREE_BONUS if ci in chosen else 1.0)
                if gain > best_gain:
                    best, best_gain = ci, gain
            if best is None:
                break
            picked.append(best)
            chosen.add(best)
            idx, ppm = seen[best]
            times[idx[(samples.building[idx] == b) & (ppm >= USABLE_PPM)]] += 1
        if picked:
            picks[b] = picked
    return picks
```

- [ ] **Step 4: Run the tests to make sure they pass**

Run: `uv run pytest tests/fetch/test_selection.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ghosttown/ghosttown_fetch/selection.py tests/fetch/test_selection.py
git commit -m "feat(fetch): choose street photos per building by line of sight and sharpness

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Pillow, and photos and labels as arrays

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (via `uv lock`)
- Modify: `tools/fetch_wheels.py`
- Modify: `ghosttown/blender_manifest.toml` (wheels list rewritten by the tool; permission text by hand)
- Create: `ghosttown/ghosttown_fetch/imagery.py`
- Test: `tests/fetch/test_imagery.py`

**Interfaces:**
- Consumes: `mvt.decode_polygons` (Task 3), `mvt_samples.detection` (Task 3).
- Produces: `imagery.LABEL_WIDTH = 512`; kind codes `UNKNOWN, BUILDING, SKY, GROUND, CLUTTER, THIN = range(6)`; `kind_of(value) -> int`; `srgb_to_linear(a)`; `decode_linear(jpeg_bytes) -> (H, W, 3) float32`; `luminance(c)`; `Labels(detections, aspect)` with `.at(u, v) -> uint8 kinds` and `.road` (bool map); `road_luminance(image, labels) -> float | None`; `sample(image, u, v) -> (n, 3)`.

- [ ] **Step 1: Add Pillow to the development environment**

In `pyproject.toml`, change the dev group to:

```toml
[dependency-groups]
dev = ["numpy==2.3.4", "shapely==2.1.2", "pillow==11.3.0", "pytest>=8", "pytest-socket>=0.7"]
```

Run: `uv lock && uv sync`
Expected: `uv.lock` gains pillow 11.3.0; `uv run python -c "import PIL; print(PIL.__version__)"` prints `11.3.0`.

- [ ] **Step 2: Bundle Pillow wheels with the extension**

Replace `tools/fetch_wheels.py` with:

```python
"""Download the wheels the extension bundles into ghosttown/wheels/ (checksums verified) and list them in
ghosttown/blender_manifest.toml.

    python3 tools/fetch_wheels.py
"""
import hashlib
import json
import os
import re
import sys
import urllib.request

PACKAGES = {"shapely": "2.1.2", "pillow": "11.3.0"}
PLATFORMS = (  # one wheel per Blender platform; the first match in name order has the widest reach
    re.compile(r"-cp313-cp313-macosx_\d+_\d+_arm64\.whl$"),
    re.compile(r"-cp313-cp313-macosx_\d+_\d+_x86_64\.whl$"),
    re.compile(r"-cp313-cp313-win_amd64\.whl$"),
    re.compile(r"-cp313-cp313-manylinux[^-]*x86_64\.whl$"),
)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "ghosttown", "wheels")
MANIFEST = os.path.join(ROOT, "ghosttown", "blender_manifest.toml")


def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _pick(files, pattern):
    names = sorted(n for n in files if pattern.search(n))
    if not names:
        sys.exit(f"no wheel matches {pattern.pattern}")
    return names[0]


def _download(info, path):
    if os.path.exists(path) and _sha256(path) == info["digests"]["sha256"]:
        print("ok ", os.path.basename(path))
        return
    with urllib.request.urlopen(info["url"], timeout=300) as r:
        data = r.read()
    if hashlib.sha256(data).hexdigest() != info["digests"]["sha256"]:
        sys.exit(f"checksum mismatch for {os.path.basename(path)}")
    with open(path, "wb") as f:
        f.write(data)
    print("got", os.path.basename(path))


def _write_manifest(names):
    with open(MANIFEST, encoding="utf-8") as f:
        text = f.read()
    block = "wheels = [\n" + "".join(f'  "./wheels/{n}",\n' for n in names) + "]"
    new, count = re.subn(r'wheels = \[\n(?:  "[^"\n]*",\n)*\]', block, text)
    if count != 1:
        sys.exit("couldn't find the wheels list in blender_manifest.toml")
    if new != text:
        with open(MANIFEST, "w", encoding="utf-8") as f:
            f.write(new)
        print("updated blender_manifest.toml")


def main():
    os.makedirs(DEST, exist_ok=True)
    names = []
    for package, version in PACKAGES.items():
        with urllib.request.urlopen(f"https://pypi.org/pypi/{package}/{version}/json", timeout=60) as r:
            files = {f["filename"]: f for f in json.load(r)["urls"]}
        for pattern in PLATFORMS:
            name = _pick(files, pattern)
            _download(files[name], os.path.join(DEST, name))
            names.append(name)
    _write_manifest(names)


if __name__ == "__main__":
    main()
```

In `ghosttown/blender_manifest.toml`, change the permission line to:

```toml
network = "Download map, terrain and building data, and Mapillary street photos for Street Look"
```

Run: `python3 tools/fetch_wheels.py`
Expected: eight wheels in `ghosttown/wheels/` (four shapely, four pillow) and `blender_manifest.toml` listing all eight.

- [ ] **Step 3: Write the failing tests** — create `tests/fetch/test_imagery.py`

```python
import io

import numpy as np
from PIL import Image

from ghosttown_fetch import imagery
from mvt_samples import detection


def _jpeg(rgb, size=(64, 48)):
    buf = io.BytesIO()
    Image.new("RGB", size, rgb).save(buf, "JPEG", quality=95)
    return buf.getvalue()


def test_kinds():
    k = imagery.kind_of
    assert k("construction--structure--building") == imagery.BUILDING and k("nature--sky") == imagery.SKY
    assert k("construction--flat--road") == imagery.GROUND and k("nature--terrain") == imagery.GROUND
    assert k("object--wire-group") == imagery.THIN and k("object--support--pole") == imagery.THIN
    assert k("object--vehicle--car") == imagery.CLUTTER and k("nature--vegetation") == imagery.CLUTTER
    assert k("void--unlabeled") == imagery.UNKNOWN


def test_decode_gives_linear_light():
    img = imagery.decode_linear(_jpeg((128, 128, 128)))
    assert img.shape == (48, 64, 3) and abs(float(img.mean()) - 0.2159) < 0.01
    assert np.allclose(imagery.srgb_to_linear([0.0, 1.0]), [0.0, 1.0])


SKY = detection("nature--sky", [(0, 0), (1, 0), (1, 0.5), (0, 0.5)])
ROAD = detection("construction--flat--road", [(0, 0.5), (1, 0.5), (1, 1), (0, 1)])
HOUSE = detection("construction--structure--building", [(0.4, 0.3), (0.6, 0.3), (0.6, 0.7), (0.4, 0.7)])


def test_labels_paint_small_regions_over_big_ones():
    lab = imagery.Labels([SKY, ROAD, HOUSE], aspect=0.75)
    kinds = lab.at(np.array([0.1, 0.5, 0.5, 0.1, 1.5]), np.array([0.1, 0.4, 0.6, 0.9, 0.5]))
    assert kinds.tolist() == [imagery.SKY, imagery.BUILDING, imagery.BUILDING, imagery.GROUND, imagery.UNKNOWN]


def test_broken_label_geometry_is_skipped():
    lab = imagery.Labels([{"value": "nature--sky", "geometry": "not base64!"}, HOUSE], aspect=0.75)
    assert lab.at(np.array([0.5]), np.array([0.5]))[0] == imagery.BUILDING


def test_road_luminance_needs_enough_road():
    img = np.full((384, 512, 3), 0.1, dtype=np.float32)
    assert abs(imagery.road_luminance(img, imagery.Labels([ROAD, HOUSE], aspect=0.75)) - 0.1) < 1e-6
    corner = detection("construction--flat--road", [(0, 0.99), (0.01, 0.99), (0.01, 1), (0, 1)])
    assert imagery.road_luminance(img, imagery.Labels([corner], aspect=0.75)) is None


def test_sample_reads_colours_at_picture_fractions():
    img = np.zeros((10, 20, 3), dtype=np.float32)
    img[2, 5] = (1, 0, 0)
    assert np.allclose(imagery.sample(img, np.array([5.5 / 20]), np.array([2.5 / 10])), [[1, 0, 0]])
```

- [ ] **Step 4: Run them to make sure they fail**

Run: `uv run pytest tests/fetch/test_imagery.py -v`
Expected: FAIL with `ImportError: cannot import name 'imagery'`.

- [ ] **Step 5: Implement** `ghosttown/ghosttown_fetch/imagery.py`

```python
"""Photos as linear-light arrays, Mapillary's labels as a picture-sized map of kinds, and road brightness
for exposure calibration."""
import base64
import binascii
import io

import numpy as np
from PIL import Image, ImageDraw

from . import mvt

LABEL_WIDTH = 512
UNKNOWN, BUILDING, SKY, GROUND, CLUTTER, THIN = range(6)
BUILDING_LABEL = "construction--structure--building"
ROAD_LABEL = "construction--flat--road"
GROUND_PREFIXES = ("construction--flat--", "nature--terrain", "marking--")
THIN_PREFIXES = ("object--wire-group", "object--support--", "object--street-light", "object--traffic-sign",
                 "object--traffic-light", "object--sign--", "object--banner")
MIN_ROAD_PX = 500


def kind_of(value):
    if value == BUILDING_LABEL:
        return BUILDING
    if value == "nature--sky":
        return SKY
    if value.startswith(GROUND_PREFIXES):
        return GROUND
    if value.startswith(THIN_PREFIXES):
        return THIN
    if not value or value.startswith("void--"):
        return UNKNOWN
    return CLUTTER


def srgb_to_linear(a):
    a = np.asarray(a, dtype=np.float32)
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4).astype(np.float32)


def decode_linear(jpeg):
    """(H, W, 3) float32 linear RGB from JPEG bytes."""
    with Image.open(io.BytesIO(jpeg)) as im:
        return srgb_to_linear(np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0)


def luminance(c):
    c = np.asarray(c)
    return c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722


class Labels:
    """Mapillary's labels painted into a LABEL_WIDTH-wide map of kinds. Bigger regions are painted first,
    so smaller objects stay on top of the regions they sit in."""

    def __init__(self, detections, aspect):
        self.w = LABEL_WIDTH
        self.h = max(1, round(LABEL_WIDTH * aspect))
        shapes = []
        for det in detections:
            try:
                polygons = mvt.decode_polygons(base64.b64decode(det["geometry"]))
            except (binascii.Error, ValueError, KeyError, TypeError):
                continue
            for _layer, rings in polygons:
                ring = [(u * self.w, v * self.h) for u, v in rings[0]]
                if len(ring) >= 3:
                    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
                    shapes.append(((max(xs) - min(xs)) * (max(ys) - min(ys)), det["value"], ring))
        kinds = Image.new("L", (self.w, self.h), UNKNOWN)
        road = Image.new("L", (self.w, self.h), 0)
        draw_kinds, draw_road = ImageDraw.Draw(kinds), ImageDraw.Draw(road)
        for _area, value, ring in sorted(shapes, key=lambda s: -s[0]):
            draw_kinds.polygon(ring, fill=kind_of(value))
            draw_road.polygon(ring, fill=255 if value == ROAD_LABEL else 0)
        self.kinds = np.asarray(kinds)
        self.road = np.asarray(road) > 0

    def at(self, u, v):
        """Kinds at picture fractions; points outside the picture are UNKNOWN."""
        u, v = np.asarray(u, dtype=float), np.asarray(v, dtype=float)
        inside = (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
        out = np.full(u.shape, UNKNOWN, dtype=np.uint8)
        out[inside] = self.kinds[(v[inside] * self.h).astype(int), (u[inside] * self.w).astype(int)]
        return out


def road_luminance(image, labels):
    """Median linear luminance of the road in a photo, or None with fewer than MIN_ROAD_PX road pixels."""
    h, w = image.shape[:2]
    rows = np.arange(h) * labels.h // h
    cols = np.arange(w) * labels.w // w
    mask = labels.road[rows[:, None], cols[None, :]]
    if mask.sum() < MIN_ROAD_PX:
        return None
    return float(np.median(luminance(image[mask])))


def sample(image, u, v):
    """Colours (n, 3) at picture fractions (u, v)."""
    h, w = image.shape[:2]
    rows = np.clip((np.asarray(v) * h).astype(int), 0, h - 1)
    cols = np.clip((np.asarray(u) * w).astype(int), 0, w - 1)
    return image[rows, cols]
```

- [ ] **Step 6: Run the tests to make sure they pass**

Run: `uv run pytest tests/fetch/test_imagery.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock tools/fetch_wheels.py ghosttown/blender_manifest.toml ghosttown/ghosttown_fetch/imagery.py tests/fetch/test_imagery.py
git commit -m "feat(fetch): bundle Pillow; photos in linear light and Mapillary labels as kind maps

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: A building's look from its photos

**Files:**
- Create: `ghosttown/ghosttown_fetch/appearance.py`
- Test: `tests/fetch/test_appearance.py`

**Interfaces:**
- Consumes: per-photo views `(colours (n, 3) linear and calibrated, heights (n,) above the lowest point, wall ids (n,))`.
- Produces: constants `BAND_M = 3.0`, `CELL_M = 6.0`, `FLOOR_DEFAULT_M = 3.5` and the thresholds in Global Constraints; `band_profile(views) -> {band: colour}`; `glass_cells(views) -> {cell: bool}`; `zones(profile, glass) -> [zone] | None`; `floor_height(walls, ppm) -> float` where walls are `(grey rows top-down, mask)`; `confidence(photos, seen_share) -> float`; `default_look() -> entry`.

- [ ] **Step 1: Write the failing tests** — create `tests/fetch/test_appearance.py`

```python
import numpy as np

from ghosttown_fetch import appearance as ap

DARK = np.array([0.03, 0.03, 0.035])
BRICK = np.array([0.30, 0.12, 0.08])
GLASS = np.array([0.25, 0.40, 0.55])
FACTORS = [(1, 1, 1), (3.52, 2.2, 1.32), (0.5, 0.8, 1.6), (0.15, 0.15, 0.15)]   # glass seen from four places


def _colour(h, factor):
    if h < 3:
        return DARK
    if h < 12:
        return BRICK
    return GLASS * np.array(factor)


def _views(factors=FACTORS):
    heights = np.repeat(np.arange(0.25, 30, 0.5), 30)
    return [(np.array([_colour(h, f) for h in heights]), heights, np.zeros(len(heights), dtype=int))
            for f in factors]


def test_profile_is_a_median_per_band():
    prof = ap.band_profile(_views())
    assert sorted(prof) == list(range(10))
    assert np.allclose(prof[0], DARK) and np.allclose(prof[1], BRICK)


def test_glass_changes_with_the_view_and_walls_do_not():
    cells = ap.glass_cells(_views())
    assert cells[1] is False and cells[2] is True and cells[4] is True


def test_zones_storefront_body_and_glass():
    views = _views()
    z = ap.zones(ap.band_profile(views), ap.glass_cells(views))
    assert [(x["kind"], x["h0"], x["h1"]) for x in z] == [("storefront", 0.0, 3.0), ("opaque", 3.0, 12.0),
                                                           ("glass", 12.0, None)]
    assert np.allclose(z[1]["colour"], BRICK, atol=1e-3)


def test_with_too_few_views_blue_reads_as_glass():
    views = _views([(1, 1, 1), (0.5, 0.8, 1.6)])
    z = ap.zones(ap.band_profile(views), ap.glass_cells(views))
    assert [x["kind"] for x in z] == ["storefront", "opaque", "glass"]


def test_thin_runs_merge_and_a_contrasting_top_becomes_the_cap():
    prof = {b: BRICK for b in range(1, 9)}
    prof[0] = DARK
    prof[4] = np.array([0.3, 0.3, 0.3])      # a 3 m grey band merges back into the brick
    prof[9] = np.array([0.02, 0.02, 0.02])   # a dark parapet on top
    z = ap.zones(prof, {})
    assert [x["kind"] for x in z] == ["storefront", "opaque", "cap"] and z[-1]["h0"] == 27.0


def test_at_most_four_zones():
    colours = [[0.02] * 3, [0.3, 0.12, 0.08], [0.1, 0.3, 0.1], [0.3, 0.3, 0.3], [0.1, 0.1, 0.4], [0.5, 0.4, 0.1]]
    prof = {}
    for i, c in enumerate(colours):
        prof[2 * i] = prof[2 * i + 1] = np.array(c)    # 6 m runs, all different
    z = ap.zones(prof, {})
    assert len(z) == 4 and z[0]["h0"] == 0.0 and z[-1]["h1"] is None


def test_no_profile_means_no_zones():
    assert ap.zones({}, {}) is None


def test_floor_height_needs_two_walls_to_agree():
    ppm = 6.0
    rows = np.arange(int(30 * ppm))
    grey = np.where(((rows / ppm) % 4.0) < 0.3, 0.1, 0.6)[:, None] * np.ones((1, 60))
    mask = np.ones_like(grey, dtype=bool)
    assert abs(ap.floor_height([(grey, mask), (grey, mask)], ppm) - 4.0) < 0.2
    assert ap.floor_height([(grey, mask)], ppm) == ap.FLOOR_DEFAULT_M
    assert ap.floor_height([], ppm) == ap.FLOOR_DEFAULT_M


def test_confidence_and_the_guessed_look():
    assert ap.confidence(3, 0.5) == 0.5 and ap.confidence(1, 1.0) == round(1 / 3, 3)
    d = ap.default_look()
    assert d["source"] == "guessed" and d["photos"] == 0
    assert [z["kind"] for z in d["zones"]] == ["storefront", "opaque"] and d["zones"][-1]["h1"] is None
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `uv run pytest tests/fetch/test_appearance.py -v`
Expected: FAIL with `ImportError: cannot import name 'appearance'`.

- [ ] **Step 3: Implement** `ghosttown/ghosttown_fetch/appearance.py`

```python
"""A building's look from its photos: colour by height, zones, glass, floor height.

Colours are linear RGB after exposure calibration; heights are metres above the building's lowest point.
A view is one photo's (colours, heights, wall ids) of the building's own, labelled, unblocked pixels."""
import numpy as np

BAND_M = 3.0
CELL_M = 6.0
MIN_BAND_PX = 20
MIN_PHOTOS_PER_BAND = 2
MIN_ZONE_M = 6.0
MAX_ZONES = 4
LUM_STEP = 0.30
CHROMA_STEP = 0.05
STOREFRONT_RANGE_M = (3.0, 9.0)
STOREFRONT_JUMP = 1.6
GLASS_CHROMA_SPREAD = 0.12
GLASS_LOG_LUM_SPREAD = 0.7
MIN_GLASS_VIEWS = 3
BLUE_RULE = 0.04
FLOOR_RANGE_M = (2.8, 6.0)
FLOOR_DEFAULT_M = 3.5
FLOOR_AGREE_M = 0.25
DEFAULT_ZONES = (
    {"h0": 0.0, "h1": 4.5, "kind": "storefront", "colour": (0.32, 0.32, 0.31)},
    {"h0": 4.5, "h1": None, "kind": "opaque", "colour": (0.42, 0.42, 0.40)},
)


def _lum(c):
    c = np.asarray(c, dtype=float)
    return c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722


def _chroma(c):
    c = np.asarray(c, dtype=float)
    return c / np.maximum(c.sum(-1, keepdims=True), 1e-9)


def band_profile(views):
    """{band: colour} per 3 m band: the median colour in each photo, then the median across photos. Bands
    seen by fewer than two photos are left out."""
    per = {}
    for colours, heights, _walls in views:
        bands = np.floor(heights / BAND_M).astype(int)
        for b in np.unique(bands):
            m = bands == b
            if b >= 0 and m.sum() >= MIN_BAND_PX:
                per.setdefault(int(b), []).append(np.median(colours[m], axis=0))
    return {b: np.median(v, axis=0) for b, v in sorted(per.items()) if len(v) >= MIN_PHOTOS_PER_BAND}


def glass_cells(views):
    """{6 m cell: is glass} for cells seen from at least three photos on the same wall. Glass changes
    colour with the viewpoint (it shows what it reflects); brick, stone and concrete do not."""
    per = {}
    for colours, heights, walls in views:
        cells = np.floor(heights / CELL_M).astype(int)
        for w, c in set(zip(walls.tolist(), cells.tolist())):
            m = (walls == w) & (cells == c)
            if m.sum() >= MIN_BAND_PX:
                per.setdefault((w, c), []).append(np.median(colours[m], axis=0))
    spreads = {}
    for (_w, c), cols in per.items():
        if len(cols) < MIN_GLASS_VIEWS:
            continue
        cols = np.array(cols)
        chroma = float(np.std(_chroma(cols), axis=0).sum())
        loglum = float(np.std(np.log(np.maximum(_lum(cols), 1e-4))))
        spreads.setdefault(c, []).append((chroma, loglum))
    return {c: bool(np.median([s[0] for s in v]) > GLASS_CHROMA_SPREAD
                    and np.median([s[1] for s in v]) > GLASS_LOG_LUM_SPREAD)
            for c, v in spreads.items()}


def _kind(band, colour, glass):
    cell = int(band * BAND_M // CELL_M)
    if cell in glass:
        return "glass" if glass[cell] else "opaque"
    c = np.asarray(colour)
    return "glass" if c[2] - c[0] > BLUE_RULE * max(_lum(c) / 0.1, 1.0) else "opaque"


def _difference(a, b):
    la, lb = _lum(a), _lum(b)
    return abs(la - lb) / max(la, lb, 1e-6), float(np.linalg.norm(_chroma(a) - _chroma(b)))


def _differs(a, b):
    lum, chroma = _difference(a, b)
    return lum > LUM_STEP or chroma > CHROMA_STEP


def _storefront(profile):
    """The band index where the storefront ends: the first boundary 3-9 m up where the band above is at
    least 1.6 times as bright as the band below. None without such a jump."""
    for b in sorted(profile):
        top = (b + 1) * BAND_M
        if STOREFRONT_RANGE_M[0] <= top <= STOREFRONT_RANGE_M[1] and (b + 1) in profile:
            if _lum(profile[b + 1]) >= STOREFRONT_JUMP * max(_lum(profile[b]), 1e-6):
                return b + 1
    return None


def _run(bands, kind, cols):
    return {"bands": list(bands), "kind": kind, "cols": list(cols)}


def _merge(a, b):
    if "storefront" in (a["kind"], b["kind"]):
        kind = "storefront"
    else:
        kind = a["kind"] if len(a["bands"]) >= len(b["bands"]) else b["kind"]
    return _run(a["bands"] + b["bands"], kind, a["cols"] + b["cols"])


def _thickness(run):
    return (max(run["bands"]) - min(run["bands"]) + 1) * BAND_M


def _colour(run):
    return np.median(run["cols"], axis=0)


def _is_cap(below, top):
    lb, lt = _lum(_colour(below)), _lum(_colour(top))
    return top["kind"] == "opaque" and max(lb, lt) >= STOREFRONT_JUMP * max(min(lb, lt), 1e-6)


def zones(profile, glass):
    """Up to four zones [{h0, h1, kind, colour}] from the band profile, or None without a profile."""
    if not profile:
        return None
    bands = sorted(profile)
    store = _storefront(profile)
    runs = []
    if store is not None:
        low = [b for b in bands if b < store]
        runs.append(_run(low, "storefront", [profile[b] for b in low]))
    for b in bands:
        if store is not None and b < store:
            continue
        kind = _kind(b, profile[b], glass)
        last = runs[-1] if runs else None
        if last is not None and last["kind"] == kind and not _differs(last["cols"][-1], profile[b]):
            last["bands"].append(b)
            last["cols"].append(profile[b])
        else:
            runs.append(_run([b], kind, [profile[b]]))
    # runs thinner than 6 m join a neighbour; a thin top run that contrasts with the run below is the cap
    i = 0
    while i < len(runs):
        r = runs[i]
        if r["kind"] in ("storefront", "cap") or _thickness(r) >= MIN_ZONE_M or len(runs) == 1:
            i += 1
            continue
        if i == len(runs) - 1 and i > 0 and runs[i - 1]["kind"] != "storefront" and _is_cap(runs[i - 1], r):
            r["kind"] = "cap"
            i += 1
            continue
        j = i - 1 if i > 0 and runs[i - 1]["kind"] != "storefront" else i + 1
        if j >= len(runs):
            i += 1
            continue
        lo, hi = min(i, j), max(i, j)
        runs[lo:hi + 1] = [_merge(runs[lo], runs[hi])]
        i = max(lo - 1, 0)
    # neighbours that ended up alike become one
    k = 0
    while k < len(runs) - 1:
        a, b = runs[k], runs[k + 1]
        if a["kind"] == b["kind"] and a["kind"] != "storefront" and not _differs(_colour(a), _colour(b)):
            runs[k:k + 2] = [_merge(a, b)]
        else:
            k += 1
    # at most four: merge the most alike neighbours (never the storefront)
    while len(runs) > MAX_ZONES:
        best, best_d = None, None
        for k in range(len(runs) - 1):
            if "storefront" in (runs[k]["kind"], runs[k + 1]["kind"]):
                continue
            d = sum(_difference(_colour(runs[k]), _colour(runs[k + 1])))
            if best_d is None or d < best_d:
                best, best_d = k, d
        if best is None:
            break
        runs[best:best + 2] = [_merge(runs[best], runs[best + 1])]
    out = []
    for k, r in enumerate(runs):
        out.append({"h0": 0.0 if k == 0 else float(min(r["bands"]) * BAND_M), "h1": None, "kind": r["kind"],
                    "colour": [round(float(c), 4) for c in _colour(r)]})
    for a, b in zip(out, out[1:]):
        a["h1"] = b["h0"]
    return out


def floor_height(walls, ppm):
    """The dominant floor spacing in straightened walls [(grey rows top-down, mask)] at `ppm` pixels per
    metre: the strongest repeat of horizontal edges over 2.8-6 m, accepted when at least two walls agree
    within 0.25 m. Otherwise 3.5 m."""
    lo, hi = FLOOR_RANGE_M
    found = []
    for grey, mask in walls:
        both = mask[1:] & mask[:-1]
        weight = both.sum(axis=1)
        rows = weight > 0
        if rows.sum() < int(2 * hi * ppm):
            continue
        edges = (np.abs(np.diff(grey, axis=0)) * both).sum(axis=1) / np.maximum(weight, 1)
        p = np.where(rows, edges - edges[rows].mean(), 0.0)
        ac = np.correlate(p, p, "full")[len(p) - 1:]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        lags = np.arange(len(ac)) / ppm
        window = (lags >= lo) & (lags <= hi)
        if not window.any():
            continue
        k = int(np.argmax(np.where(window, ac, -np.inf)))
        if ac[k] > 0.1:
            found.append(float(lags[k]))
    best = []
    for value in found:
        close = [f for f in found if abs(f - value) <= FLOOR_AGREE_M]
        if len(close) > len(best):
            best = close
    return round(float(np.mean(best)), 2) if len(best) >= 2 else FLOOR_DEFAULT_M


def confidence(photos, seen_share):
    return round(min(1.0, photos / 3.0) * max(0.0, min(1.0, float(seen_share))), 3)


def default_look():
    return {"source": "guessed", "photos": 0, "confidence": 0.0, "floor_h": FLOOR_DEFAULT_M,
            "zones": [dict(z, colour=list(z["colour"])) for z in DEFAULT_ZONES]}
```

- [ ] **Step 4: Run the tests to make sure they pass**

Run: `uv run pytest tests/fetch/test_appearance.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ghosttown/ghosttown_fetch/appearance.py tests/fetch/test_appearance.py
git commit -m "feat(fetch): zones, glass and floor height from a building's photos

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: The Street Look pipeline

**Files:**
- Create: `ghosttown/ghosttown_fetch/look.py`
- Create: `tests/fetch/look_samples.py`
- Test: `tests/fetch/test_look.py`

**Interfaces:**
- Consumes: everything from Tasks 1–9; `terrain.load(net, frame, radius_m)`; `CREDITS["mapillary"]`.
- Produces: `look.run(request, net, token, *, progress=None) -> answer dict` (valid per `look_schema.validate_answer`). Photos are read for at most `budget_photos` buildings (detail first, then nearest the centre); the photo search reaches 200 m (`search_margin_m`) past the farthest of those buildings' wall points, capped at 1,000 m; cameras are thinned with `selection.thin`. `look.NothingListed(Exception)`; constants `STRAIGHTEN_PPM = 6.0`, `MASK_GRID_W = 200`, `MAX_SEARCH_M = 1000.0`. Test helpers `look_samples.street(detail=False) -> {"buildings", "cameras", "records", "labels", "photos"}` (cached), `fake_net(data, token_ok=True) -> FakeNet`, `request(tmp_path, data, **changes) -> look request`, constants `LAT0, LON0, BRICK`.

- [ ] **Step 1: Write the synthetic street** — create `tests/fetch/look_samples.py`

```python
"""A synthetic street for Street Look tests: one 30 m building, four cameras south of it, and the photos
and labels Mapillary would send for them. The building has a dark storefront to 3 m, brick to 12 m and
glass above that shows a different colour from each camera; dark floor lines run every 4 m."""
import functools
import io
import json

import numpy as np
from PIL import Image

from ghosttown_fetch import look_schema as ls
from ghosttown_fetch import raycast
from ghosttown_fetch.frame import Frame
from ghosttown_fetch.net import SourceError
from camera_samples import camera, rotation_vector
from fakes import FakeNet
from mvt_samples import detection

LAT0, LON0 = 51.5074, -0.1278   # outside Canada: flat ground and no terrain download
TARGET = {"id": "test:1", "solids": [{"rings": [[[-10, -10], [10, -10], [10, 10], [-10, 10]]], "z0": 0.0, "z1": 30.0}]}
FAR = {"id": "test:2", "solids": [{"rings": [[[300, 300], [310, 300], [310, 310], [300, 310]]], "z0": 0.0, "z1": 10.0}]}
STOREFRONT, BRICK, GLASS = (0.03, 0.03, 0.035), (0.30, 0.12, 0.08), (0.25, 0.40, 0.55)
SKY, ROAD = (0.55, 0.70, 0.90), (0.12, 0.12, 0.12)
FLOOR_M = 4.0
SPOTS = [(-15, -60), (0, -70), (15, -55), (5, -80)]
EXPOSURES = [1.0, 1.0, 0.6, 1.0]
GLASS_FACTORS = [(1, 1, 1), (3.52, 2.2, 1.32), (0.5, 0.8, 1.6), (0.15, 0.15, 0.15)]
PIXELS = 512


def _srgb(lin):
    lin = np.clip(lin, 0.0, 1.0)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)


def _hull(points):
    pts = sorted(set(map(tuple, np.round(points, 6))))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _render(cam, scene, exposure, factor):
    dirs, rows = cam.rays(PIXELS)
    owner, dist = scene.first_hit(cam.position[None], dirs, 1000.0)
    img = np.where((dirs[:, 2] > 0)[:, None], SKY, ROAD).astype(float)
    on = owner == 0
    h = cam.position[2] + dirs[on, 2] * dist[on]
    col = np.where((h < 3)[:, None], STOREFRONT, np.where((h < 12)[:, None], BRICK, np.array(GLASS) * factor))
    line = (h >= 3) & ((h / FLOOR_M) % 1.0 < 0.12)
    col[line] *= 0.35
    img[on] = col
    pixels = (_srgb(img * exposure).reshape(rows, PIXELS, 3) * 255).round().astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(pixels).save(buf, "JPEG", quality=95)
    return buf.getvalue()


def _labels(cam):
    corners = np.array([[x, y, z] for x in (-10, 10) for y in (-10, 10) for z in (0.0, 30.0)])
    u, v, ok = cam.project(corners)
    house = _hull(np.column_stack([np.clip(u[ok], 0, 1), np.clip(v[ok], 0, 1)]))
    return [detection("nature--sky", [(0, 0), (1, 0), (1, 0.5), (0, 0.5)]),
            detection("construction--flat--road", [(0, 0.5), (1, 0.5), (1, 1), (0, 1)]),
            detection("construction--structure--building", house)]


@functools.lru_cache(maxsize=None)
def _street():
    frame = Frame(LAT0, LON0)
    scene = raycast.Scene([TARGET])
    cams, records, labels, photos = [], [], {}, {}
    for i, ((x, y), exposure, factor) in enumerate(zip(SPOTS, EXPOSURES, GLASS_FACTORS)):
        heading = float(np.degrees(np.arctan2(-x, -y)))   # towards the building's centre
        cam = camera((x, y, 2.0), heading_deg=heading, image_id=f"9{i}", year=2024)
        lon, lat = frame.to_lonlat(x, y)
        records.append({"id": cam.id, "captured_at": 1717200000000, "camera_type": "perspective",
                        "computed_geometry": {"type": "Point", "coordinates": [lon, lat]},
                        "computed_rotation": rotation_vector(cam.R), "camera_parameters": [cam.focal, 0.0, 0.0],
                        "width": cam.width, "height": cam.height, "sequence": "seq1"})
        labels[cam.id] = _labels(cam)
        photos[cam.id] = _render(cam, scene, exposure, np.array(factor, dtype=float))
        cams.append(cam)
    return cams, records, labels, photos


def street(detail=False):
    cams, records, labels, photos = _street()
    return {"buildings": [dict(TARGET, detail=detail), dict(FAR)], "cameras": cams, "records": records,
            "labels": labels, "photos": photos}


def fake_net(data, token_ok=True):
    """A FakeNet that answers Mapillary's listing, link, photo and label requests for `data`."""
    def answer(url, _data):
        if not token_ok:
            return SourceError("Mapillary answered HTTP 401; try again in a minute.", status=401)
        if "/images?" in url:
            return json.dumps({"data": data["records"]}).encode()
        if url.startswith("https://cdn.example/"):
            return data["photos"][url.rsplit("/", 1)[1].split(".")[0]]
        image_id = url.split("graph.mapillary.com/", 1)[1].split("?")[0].split("/")[0]
        if "/detections" in url:
            return json.dumps({"data": data["labels"][image_id]}).encode()
        return json.dumps({"id": image_id, "thumb_2048_url": f"https://cdn.example/{image_id}.jpg"}).encode()

    return FakeNet({"mapillary": answer})


def request(tmp_path, data, **changes):
    req = ls.build_request(centre={"lat": LAT0, "lon": LON0}, radius_m=100, buildings=data["buildings"],
                           cache_dir=str(tmp_path / "cache"), out_dir=str(tmp_path / "run"), budget_photos=10)
    req.update(changes)
    return req
```

- [ ] **Step 2: Write the failing tests** — create `tests/fetch/test_look.py`

```python
import numpy as np
import pytest

from ghosttown_fetch import look
from ghosttown_fetch import look_schema as ls
from ghosttown_fetch.sources.mapillary import TokenRejected
from look_samples import BRICK, fake_net, request, street

TOKEN = "MLY|secret"


def test_a_street_gives_storefront_brick_and_glass_zones(tmp_path):
    data = street(detail=True)
    stages = []
    answer = look.run(request(tmp_path, data), fake_net(data), TOKEN, progress=lambda s, p: stages.append(s))
    assert ls.validate_answer(answer) == []
    e = answer["buildings"]["test:1"]
    assert e["source"] == "photos" and e["photos"] >= 3
    assert [(z["kind"], z["h0"]) for z in e["zones"]] == [("storefront", 0.0), ("opaque", 3.0), ("glass", 12.0)]
    assert np.allclose(e["zones"][1]["colour"], BRICK, rtol=0.15, atol=0.02)
    assert abs(e["floor_h"] - 4.0) <= 0.4 and 0 < e["confidence"] <= 1
    assert stages[0] == "Terrain" and stages[-1] == "Writing"


def test_buildings_no_photo_sees_get_the_guessed_look(tmp_path):
    data = street()
    answer = look.run(request(tmp_path, data), fake_net(data), TOKEN)
    far = answer["buildings"]["test:2"]
    assert far["source"] == "guessed" and far["photos"] == 0


def test_detail_walls_only_for_detail_buildings(tmp_path):
    data = street(detail=True)
    answer = look.run(request(tmp_path, data), fake_net(data), TOKEN)
    walls = answer["buildings"]["test:1"]["detail_walls"]
    assert len(walls) == 4 and all(w["z0"] == 0 and w["z1"] == 30 for w in walls)
    assert "detail_walls" not in answer["buildings"]["test:2"]


def test_credits_years_and_the_token_stays_in_headers(tmp_path):
    data = street()
    net = fake_net(data)
    answer = look.run(request(tmp_path, data), net, TOKEN)
    assert answer["photos_used"] >= 3 and answer["years"] == [2024, 2024]
    assert answer["sources"] == [{"key": "mapillary", "name": "Mapillary",
                                  "credit": "Street photos © Mapillary contributors, CC BY-SA 4.0"}]
    assert all(TOKEN not in url for url, _source, _data in net.calls)


def test_no_coverage_means_every_building_is_guessed(tmp_path):
    empty = dict(street(), records=[])
    answer = look.run(request(tmp_path, empty), fake_net(empty), TOKEN)
    assert {e["source"] for e in answer["buildings"].values()} == {"guessed"}
    assert answer["photos_used"] == 0 and answer["sources"] == [] and ls.validate_answer(answer) == []


def test_a_rejected_token_is_raised(tmp_path):
    data = street()
    with pytest.raises(TokenRejected):
        look.run(request(tmp_path, data), fake_net(data, token_ok=False), TOKEN)


def test_not_before_drops_older_photos(tmp_path):
    data = street()
    answer = look.run(request(tmp_path, data, not_before_year=2025), fake_net(data), TOKEN)
    assert answer["buildings"]["test:1"]["source"] == "guessed"


def _box(bid, x, y, size=10.0):
    ring = [[x, y], [x + size, y], [x + size, y + size], [x, y + size]]
    return {"id": bid, "solids": [{"rings": [ring], "z0": 0.0, "z1": 10.0}]}


def test_search_radius_follows_the_buildings_and_is_capped(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(look.mapillary, "list_images", lambda net, frame, r, token: (seen.append(r), ([], 0))[1])
    data = street()
    look.run(request(tmp_path, data, radius_m=1000, buildings=[data["buildings"][0]]), fake_net(data), TOKEN)
    assert 200 < seen[-1] < 215   # the 20 m target's farthest wall point, under 15 m out, plus the 200 m margin
    edge = _box("edge", 950, 0)
    look.run(request(tmp_path, data, radius_m=1000, buildings=data["buildings"] + [edge]), fake_net(data), TOKEN)
    assert seen[-1] == 1000.0


def test_photos_are_read_for_at_most_as_many_buildings_as_the_budget(tmp_path, monkeypatch):
    data = street()
    sheds = [_box(f"shed:{i}", 200 + 20 * i, 200) for i in range(12)]
    asked = []
    views = look.selection.views
    monkeypatch.setattr(look.selection, "views",
                        lambda cams, samples, scene: (asked.append({scene.ids[b] for b in samples.building.tolist()}),
                                                      views(cams, samples, scene))[1])
    answer = look.run(request(tmp_path, data, buildings=data["buildings"] + sheds, budget_photos=10), fake_net(data), TOKEN)
    assert len(asked[0]) == 10 and "test:1" in asked[0] and answer["buildings"]["test:1"]["source"] == "photos"
    assert len(answer["buildings"]) == 14
```

- [ ] **Step 3: Run them to make sure they fail**

Run: `uv run pytest tests/fetch/test_look.py -v`
Expected: FAIL with `ImportError: cannot import name 'look'`.

- [ ] **Step 4: Implement** `ghosttown/ghosttown_fetch/look.py`

```python
"""Street Look: a look for every building from Mapillary street photos. Request in, look.json out.

For each building: choose the photos that see its walls (selection), drop photos whose labels say the
pose is wrong or the view is blocked, keep only pixels that are labelled building and that the model
says show this building, calibrate each photo's exposure against its road, and read colour by height,
glass and floor height (appearance). Buildings without a usable photo get the guessed look."""
import numpy as np

from . import CREDITS, appearance, imagery, raycast, selection
from . import look_schema as ls
from . import terrain as terrain_mod
from .camera import Camera
from .frame import Frame
from .sources import mapillary

STRAIGHTEN_PPM = 6.0
MASK_GRID_W = 200
DROP_SKY_GROUND = 0.3
MIN_BUILDING = 0.3
GAIN_RANGE = (0.5, 2.0)
DETAIL_PAD_M = 2.0
MAX_SEARCH_M = 1000.0
MIN_PIXELS = 30


class NothingListed(Exception):
    """No part of the site could be searched for photos."""


def run(request, net, token, *, progress=None):
    progress = progress or (lambda stage, pct: None)
    frame = Frame(request["centre"]["lat"], request["centre"]["lon"])
    answer = ls.new_answer()
    scene = raycast.Scene(request["buildings"])
    detail = {b["id"] for b in request["buildings"] if b.get("detail")}
    # Photos are read for at most as many buildings as the budget, detail buildings first, then the nearest:
    # more could not all get photos anyway, and it keeps a 1,000 m site about as quick as a small one.
    order = selection.priority(scene, detail)[:max(request["budget_photos"], len(detail))]
    samples = selection.wall_samples(scene).only(order)
    reach = float(np.hypot(samples.P[:, 0], samples.P[:, 1]).max()) if len(samples) else 0.0
    search = min(reach + request["search_margin_m"], MAX_SEARCH_M)

    progress("Terrain", 5)
    terrain, note = terrain_mod.load(net, frame, search)
    if note:
        answer["notes"].append({"level": note[0], "code": note[1], "text": note[2]})

    progress("Finding photos", 15)
    images, failed = mapillary.list_images(net, frame, search, token)
    if failed and failed >= len(mapillary.tiles(frame, search)):
        raise NothingListed("Mapillary couldn't be searched; try again in a minute.")
    if failed:
        answer["notes"].append({"level": "warn", "code": "mapillary_tiles", "text": "Some areas couldn't be searched."})
    cameras = [c for c in (Camera.from_mapillary(im, frame, terrain) for im in images) if c is not None]
    if request.get("not_before_year"):
        cameras = [c for c in cameras if c.year >= request["not_before_year"]]
    cameras = selection.thin(cameras)

    progress("Choosing photos", 30)
    seen = selection.views(cameras, samples, scene)
    picks = selection.choose(cameras, seen, samples, budget=request["budget_photos"], order=order)

    progress("Downloading photos", 45)
    wanted = sorted({cameras[ci].id for chosen in picks.values() for ci in chosen})
    photos = mapillary.fetch_many(lambda i: mapillary.photo(net, i, token), wanted)
    labels = mapillary.fetch_many(lambda i: mapillary.detections(net, i, token), wanted)

    progress("Reading facades", 65)
    by_id = {c.id: c for c in cameras}
    pictures = {}
    for i in wanted:
        if isinstance(photos[i], Exception) or isinstance(labels[i], Exception):
            continue
        try:
            image = imagery.decode_linear(photos[i])
        except (OSError, ValueError):
            continue
        lab = imagery.Labels(labels[i], by_id[i].height / by_id[i].width)
        pictures[i] = (image, lab, imagery.road_luminance(image, lab))
    if len(pictures) < len(wanted):
        answer["notes"].append({"level": "info", "code": "mapillary_photos",
                                "text": f"{len(wanted) - len(pictures)} photos couldn't be read and were skipped."})
    roads = [p[2] for p in pictures.values() if p[2]]
    reference = float(np.median(roads)) if roads else None

    used, grids = set(), {}
    for b, bid in enumerate(scene.ids):
        entry, kept = _building(b, picks.get(b, []), cameras, seen, samples, scene, pictures, reference, grids)
        used.update(kept)
        if bid in detail:
            entry["detail_walls"] = _detail_walls(b, samples, scene)
        answer["buildings"][bid] = entry
    for b in request["buildings"]:   # buildings whose solids couldn't be read still get a look
        answer["buildings"].setdefault(b["id"], appearance.default_look())

    progress("Writing", 95)
    years = [by_id[i].year for i in used]
    answer["photos_used"] = len(used)
    answer["years"] = [min(years), max(years)] if years else None
    if used:
        answer["sources"].append({"key": "mapillary", "name": "Mapillary", "credit": CREDITS["mapillary"]})
    return answer


def _building(b, chosen, cameras, seen, samples, scene, pictures, reference, grids):
    """(look entry, ids of the photos it used) for building index b."""
    views, walls_grey, kept = [], [], []
    for ci in chosen:
        cam = cameras[ci]
        if cam.id not in pictures:
            continue
        image, lab, road = pictures[cam.id]
        idx, _ppm = seen[ci]
        mine = idx[samples.building[idx] == b]
        u, v, _ok = cam.project(samples.P[mine])
        kinds = lab.at(u, v)
        if (np.isin(kinds, (imagery.SKY, imagery.GROUND)).mean() > DROP_SKY_GROUND
                or (kinds == imagery.BUILDING).mean() < MIN_BUILDING):
            continue   # the pose is off (sky or ground where the wall should be) or the view is blocked
        gain = float(np.clip(reference / road, *GAIN_RANGE)) if reference and road else 1.0
        if cam.id not in grids:
            grids[cam.id] = _owner_grid(cam, scene)
        colours, heights, wall_ids = [], [], []
        for w in np.unique(samples.wall[mine]):
            got = _straighten(cam, int(w), b, scene, image, lab, grids[cam.id])
            if got is None:
                continue
            cols, hts, grey, mask = got
            colours.append(cols * gain)
            heights.append(hts)
            wall_ids.append(np.full(len(hts), int(w)))
            walls_grey.append((grey, mask))
        if colours:
            views.append((np.concatenate(colours), np.concatenate(heights), np.concatenate(wall_ids)))
            kept.append(ci)
    profile = appearance.band_profile(views)
    zones = appearance.zones(profile, appearance.glass_cells(views)) if profile else None
    if zones is None:
        return appearance.default_look(), []
    mine = samples.building == b
    seen_mask = np.zeros(len(samples), dtype=bool)
    for ci in kept:
        idx, ppm = seen[ci]
        seen_mask[idx[(samples.building[idx] == b) & (ppm >= selection.USABLE_PPM)]] = True
    share = float(samples.area[seen_mask & mine].sum() / max(samples.area[mine].sum(), 1e-9))
    entry = {"source": "photos", "photos": len(kept), "confidence": appearance.confidence(len(kept), share),
             "floor_h": appearance.floor_height(walls_grey, STRAIGHTEN_PPM), "zones": zones}
    return entry, [cameras[ci].id for ci in kept]


def _owner_grid(cam, scene):
    """Which building each cell of a MASK_GRID_W-wide pixel grid shows first (-1 for none)."""
    dirs, rows = cam.rays(MASK_GRID_W)
    owner, _dist = scene.first_hit(cam.position[None], dirs, selection.MAX_DIST_M + 100.0)
    return owner.reshape(rows, MASK_GRID_W)


def _straighten(cam, w, b, scene, image, lab, grid):
    """(colours, heights, grey rows, mask) for wall w seen straight on at STRAIGHTEN_PPM, keeping only
    pixels labelled building whose ray first meets building b; None when too little is left."""
    a, e = scene.A[w], scene.B[w] - scene.A[w]
    length = float(np.hypot(*e))
    z0, z1 = scene.wall_z0[w], scene.wall_z1[w]
    ns = max(2, int(length * STRAIGHTEN_PPM))
    nt = max(2, int((z1 - z0) * STRAIGHTEN_PPM))
    S, T = np.meshgrid((np.arange(ns) + 0.5) / ns, z1 - (np.arange(nt) + 0.5) / STRAIGHTEN_PPM)
    P = np.column_stack([a[0] + e[0] * S.ravel(), a[1] + e[1] * S.ravel(), T.ravel()])
    P[:, :2] += scene.N[w] * 0.05
    u, v, ok = cam.project(P)
    ok &= (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
    if ok.sum() < MIN_PIXELS:
        return None
    rows, cols = grid.shape
    ok[ok] &= grid[(v[ok] * rows).astype(int), (u[ok] * cols).astype(int)] == b
    ok[ok] &= lab.at(u[ok], v[ok]) == imagery.BUILDING
    if ok.sum() < MIN_PIXELS:
        return None
    colours = imagery.sample(image, u[ok], v[ok])
    grey = np.zeros(ns * nt, dtype=np.float32)
    grey[ok] = imagery.luminance(colours)
    return colours, P[ok, 2] - scene.base_z[b], grey.reshape(nt, ns), ok.reshape(nt, ns)


def _detail_walls(b, samples, scene):
    """Exposed wall spans of building b with the heights (above its lowest point) where they are exposed."""
    out = []
    base = scene.base_z[b]
    mine = samples.building == b
    for w in np.unique(samples.wall[mine]):
        hs = samples.height[mine & (samples.wall == w)]
        z0 = max(float(scene.wall_z0[w] - base), float(hs.min()) - DETAIL_PAD_M)
        z1 = min(float(scene.wall_z1[w] - base), float(hs.max()) + DETAIL_PAD_M)
        if z1 - z0 < 1.0:
            continue
        out.append({"a": [round(float(c), 3) for c in scene.A[w]], "b": [round(float(c), 3) for c in scene.B[w]],
                    "n": [round(float(c), 4) for c in scene.N[w]], "z0": round(z0, 2), "z1": round(z1, 2)})
    return out
```

- [ ] **Step 5: Run the tests to make sure they pass**

Run: `uv run pytest tests/fetch/test_look.py -v`
Expected: PASS (the synthetic street renders four 512 px photos once per test session; the module takes a few seconds).

- [ ] **Step 6: Run the whole fetcher suite**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add ghosttown/ghosttown_fetch/look.py tests/fetch/look_samples.py tests/fetch/test_look.py
git commit -m "feat(fetch): Street Look pipeline from Mapillary photos to look.json

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: The `look` command

**Files:**
- Modify: `ghosttown/ghosttown_fetch/cli.py`
- Test: `tests/fetch/test_cli.py`

**Interfaces:**
- Consumes: `look_schema.read_request`, `validate_answer`, `TOKEN_ENV` (Task 2); `look.run`, `look.NothingListed` (Task 10); `mapillary.TokenRejected` (Task 6).
- Produces: `python -m ghosttown_fetch look <look_request.json>` printing one line: `{"ok": true, "look": <path>, "from_photos": n, "guessed": n, "photos_used": n, "years": [a, b] | null}` or `{"ok": false, "error": <sentence>}` (with `error.txt` in the run folder); `selftest` also reports `"pillow"`.

- [ ] **Step 1: Write the failing tests**

In `tests/fetch/test_cli.py`, change the selftest assertion to:

```python
    assert res["ok"] and res["shapely"].startswith("2.1") and res["geos"] and res["numpy"] and res["pillow"]
```

and append:

```python
def _look_req(tmp_path, data, **changes):
    from look_samples import request

    path = tmp_path / "look_request.json"
    path.write_text(json.dumps(request(tmp_path, data, **changes)), encoding="utf-8")
    return path


def test_look_writes_look_json_and_one_line(tmp_path, capsys, monkeypatch):
    from look_samples import fake_net, street

    data = street()
    monkeypatch.setenv("GHOSTTOWN_MAPILLARY_TOKEN", "MLY|secret")
    code = cli.main(["look", str(_look_req(tmp_path, data))], net_factory=lambda cache_dir, fresh=False: fake_net(data))
    res = _one_line(capsys)
    assert code == 0 and res["ok"] and res["from_photos"] == 1 and res["guessed"] == 1 and res["years"] == [2024, 2024]
    with open(res["look"], encoding="utf-8") as f:
        assert json.load(f)["buildings"]["test:1"]["source"] == "photos"
    assert (tmp_path / "run" / "progress.jsonl").is_file()


def test_look_without_a_token_says_where_to_add_it(tmp_path, capsys, monkeypatch):
    from look_samples import street

    monkeypatch.delenv("GHOSTTOWN_MAPILLARY_TOKEN", raising=False)
    assert cli.main(["look", str(_look_req(tmp_path, street()))]) == 1
    assert "Mapillary token" in _one_line(capsys)["error"]


def test_a_rejected_token_is_one_plain_sentence(tmp_path, capsys, monkeypatch):
    from look_samples import fake_net, street

    data = street()
    monkeypatch.setenv("GHOSTTOWN_MAPILLARY_TOKEN", "MLY|secret")
    code = cli.main(["look", str(_look_req(tmp_path, data))],
                    net_factory=lambda cache_dir, fresh=False: fake_net(data, token_ok=False))
    assert code == 1 and _one_line(capsys)["error"] == "Mapillary refused the token; check it in Preferences."
    assert (tmp_path / "run" / "error.txt").is_file()


def test_an_invalid_look_request_fails_with_an_error_file(tmp_path, capsys, monkeypatch):
    from look_samples import street

    monkeypatch.setenv("GHOSTTOWN_MAPILLARY_TOKEN", "MLY|secret")
    path = _look_req(tmp_path, street(), budget_photos=1)
    assert cli.main(["look", str(path)]) == 1
    assert "budget_photos" in _one_line(capsys)["error"] and (tmp_path / "run" / "error.txt").is_file()
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `uv run pytest tests/fetch/test_cli.py -v`
Expected: the four new tests and the selftest test FAIL (`Usage` errors, `KeyError: 'pillow'`).

- [ ] **Step 3: Implement**

In `ghosttown/ghosttown_fetch/cli.py`:

Change the module docstring's first line and `USAGE`:

```python
"""python -m ghosttown_fetch <selftest | fetch request.json | geocode cache_dir text | look look_request.json>
```

```python
USAGE = ("Usage: python -m ghosttown_fetch selftest | fetch <request.json> | geocode <cache_dir> <text> | "
         "look <look_request.json>")
```

In `_dispatch`, before the final `return`, add:

```python
    if len(argv) == 2 and argv[0] == "look":
        return look(argv[1], net_factory)
```

In `selftest`, import Pillow with the others and report it:

```python
def selftest():
    try:
        import numpy
        import PIL
        import shapely
    except ImportError as e:
        return {"ok": False, "error": f"A required library is missing ({e.name}); reinstall Ghost Town."}
    major, minor = (int(p) for p in shapely.__version__.split(".")[:2])
    if (major, minor) < (2, 1):
        return {"ok": False, "error": f"shapely {shapely.__version__} is too old; Ghost Town needs 2.1 or later."}
    return {"ok": True, "tool": TOOL, "python": platform.python_version(), "numpy": numpy.__version__,
            "shapely": shapely.__version__, "geos": shapely.geos_version_string, "pillow": PIL.__version__}
```

Add the command:

```python
def look(path, net_factory):
    from . import look_schema as ls

    doc, problems = ls.read_request(path)
    out_dir = doc.get("out_dir") if isinstance(doc, dict) else None
    if problems:
        return _fail(out_dir, "The street look request isn't valid: " + problems[0], "\n".join(problems))
    token = os.environ.get(ls.TOKEN_ENV, "").strip()
    if not token:
        return _fail(out_dir, "Add your Mapillary token in Ghost Town's preferences.", "No token in the environment.")
    try:
        from . import look as look_mod
        from .cache import atomic_write
        from .net import Net
        from .sources.mapillary import TokenRejected
    except ImportError as e:
        return _fail(out_dir, f"A required library is missing ({e.name}); reinstall Ghost Town.", traceback.format_exc())

    os.makedirs(out_dir, exist_ok=True)
    net = (net_factory or Net)(doc["cache_dir"], fresh=doc["fetch_fresh"])
    try:
        answer = look_mod.run(doc, net, token, progress=_progress_writer(out_dir))
    except (TokenRejected, look_mod.NothingListed) as e:
        return _fail(out_dir, str(e), traceback.format_exc())
    except Exception as e:
        return _fail(out_dir, f"Street Look failed ({type(e).__name__}: {e}).", traceback.format_exc())
    problems = ls.validate_answer(answer)
    if problems:
        return _fail(out_dir, "Street Look built an invalid answer: " + problems[0], "\n".join(problems))
    target = os.path.join(out_dir, "look.json")
    atomic_write(target, json.dumps(answer, ensure_ascii=True, separators=(",", ":")).encode("ascii"))
    photos = sum(1 for e in answer["buildings"].values() if e["source"] == "photos")
    return {"ok": True, "look": os.path.abspath(target), "from_photos": photos,
            "guessed": len(answer["buildings"]) - photos, "photos_used": answer["photos_used"],
            "years": answer["years"]}
```

- [ ] **Step 4: Run the tests to make sure they pass**

Run: `uv run pytest tests/fetch -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add ghosttown/ghosttown_fetch/cli.py tests/fetch/test_cli.py
git commit -m "feat(fetch): python -m ghosttown_fetch look

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: The token in Preferences, and extra environment for the fetcher

**Files:**
- Modify: `ghosttown/prefs.py`
- Modify: `ghosttown/runner.py`
- Test: `tests/blender/test_runner.py`, `tests/blender/test_extension.py`

**Interfaces:**
- Consumes: `look_schema.TOKEN_ENV` (Task 2).
- Produces: `GhostTownPreferences.mapillary_token`; `prefs.token(context) -> str` (Preferences first, then the environment, else ""); `runner.environment(extra_paths, base=None, extra=None)`; `runner.Run(args, *, work_dir, extra_paths, argv=None, env_extra=None)`; `runner.run_blocking(..., env_extra=None)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/blender/test_runner.py`:

```python
def test_environment_adds_extra_variables():
    env = runner.environment(["/w"], base={"PATH": "/bin"}, extra={"GHOSTTOWN_MAPILLARY_TOKEN": "t"})
    assert env["GHOSTTOWN_MAPILLARY_TOKEN"] == "t" and env["PATH"] == "/bin"


def test_a_run_hands_extra_environment_to_the_child_only():
    code = "import os, json; print(json.dumps({'ok': True, 'token': os.environ.get('GHOSTTOWN_MAPILLARY_TOKEN')}))"
    run = runner.Run(["unused"], work_dir=tempfile.mkdtemp(), extra_paths=[], argv=[sys.executable, "-c", code],
                     env_extra={"GHOSTTOWN_MAPILLARY_TOKEN": "abc"})
    deadline = time.monotonic() + 30
    while (res := run.poll()) is None and time.monotonic() < deadline:
        time.sleep(0.05)
    assert res == {"ok": True, "token": "abc"}
    assert "GHOSTTOWN_MAPILLARY_TOKEN" not in os.environ
```

Append to `tests/blender/test_extension.py` (it already imports `os`):

```python
def test_the_token_falls_back_to_the_environment():
    from ghosttown import prefs

    ghosttown.register()
    os.environ["GHOSTTOWN_MAPILLARY_TOKEN"] = " MLY|abc "
    try:
        assert prefs.token(bpy.context) == "MLY|abc"
        del os.environ["GHOSTTOWN_MAPILLARY_TOKEN"]
        assert prefs.token(bpy.context) == ""
    finally:
        os.environ.pop("GHOSTTOWN_MAPILLARY_TOKEN", None)
        ghosttown.unregister()
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py -- -k token`
then `... -- -k environment`
Expected: FAIL (`TypeError: environment() got an unexpected keyword argument 'extra'`, `AttributeError: module 'ghosttown.prefs' has no attribute 'token'`).

- [ ] **Step 3: Implement**

In `ghosttown/runner.py`, replace `environment`, `Run.__init__` and `run_blocking`'s signature:

```python
def environment(extra_paths, base=None, extra=None):
    env = dict(os.environ if base is None else base)
    for key in ("PYTHONHOME", "PYTHONSTARTUP", "PYTHONPATH"):
        env.pop(key, None)
    env["PYTHONPATH"] = os.pathsep.join([EXT_DIR, *extra_paths])
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONUTF8"] = "1"
    env.update(extra or {})   # e.g. the Mapillary token: the child's environment only, never a file
    return env


class Run:
    def __init__(self, args, *, work_dir, extra_paths, argv=None, env_extra=None):
        os.makedirs(work_dir, exist_ok=True)
        self.work_dir = work_dir
        self._stdout = open(os.path.join(work_dir, "stdout.txt"), "wb")
        self._stderr = open(os.path.join(work_dir, "stderr.txt"), "wb")
        self.proc = subprocess.Popen(
            argv or command(*args), cwd=work_dir, env=environment(extra_paths, extra=env_extra),
            stdin=subprocess.DEVNULL, stdout=self._stdout, stderr=self._stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
```

```python
def run_blocking(args, *, work_dir, extra_paths, timeout=600, env_extra=None):
    run = Run(args, work_dir=work_dir, extra_paths=extra_paths, env_extra=env_extra)
```

(the rest of `run_blocking` is unchanged).

Replace `ghosttown/prefs.py` with (0.3.0's file plus the token field, its hint and `token()`):

```python
import os

import bpy
from bpy.props import IntProperty, StringProperty

from .ghosttown_fetch.look_schema import TOKEN_ENV

DEFAULT_OVERPASS = "https://overpass-api.de/api/interpreter"
DEFAULT_BUDGET = 500_000


class GhostTownPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    cache_dir: StringProperty(
        name="Cache folder", subtype="DIR_PATH",
        description="Where downloaded data and runs are kept. Leave blank for the extension's own folder")
    overpass_url: StringProperty(
        name="Overpass endpoint", default=DEFAULT_OVERPASS,
        description="OpenStreetMap Overpass API server")
    revit_triangle_budget: IntProperty(
        name="Revit triangle budget", default=DEFAULT_BUDGET, min=10_000,
        description="A site with more triangles than this is flagged as heavy for Revit")
    mapillary_token: StringProperty(
        name="Mapillary token", subtype="PASSWORD",
        description="Your Mapillary client token, for Street Look. Create one at mapillary.com/dashboard/developers")

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "cache_dir")
        col.prop(self, "overpass_url")
        col.prop(self, "revit_triangle_budget")
        col.prop(self, "mapillary_token")
        col.label(text=f"Or set {TOKEN_ENV}. The token stays in Blender's preferences, never in .blend files.")


def get(context):
    addon = context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


def cache_dir(context):
    """Resolved on use, never at import time: extension_path_user only works inside the extension."""
    p = get(context)
    if p is not None and p.cache_dir.strip():
        return bpy.path.abspath(p.cache_dir)
    return bpy.utils.extension_path_user(__package__, path="cache", create=True)


def triangle_budget(context):
    p = get(context)
    return p.revit_triangle_budget if p is not None else DEFAULT_BUDGET


def token(context):
    """The Mapillary token from Preferences, else from the environment; '' when there is none."""
    p = get(context)
    value = p.mapillary_token.strip() if p is not None else ""
    return value or os.environ.get(TOKEN_ENV, "").strip()
```

- [ ] **Step 4: Run the tests to make sure they pass**

Run: `/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py`
Expected: all Blender tests pass.

- [ ] **Step 5: Commit**

```bash
git add ghosttown/prefs.py ghosttown/runner.py tests/blender/test_runner.py tests/blender/test_extension.py
git commit -m "feat: Mapillary token in Preferences, passed to the fetcher in its environment only

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: The Street Look node group in the building materials

**Files:**
- Modify: `ghosttown/materials.py`
- Test: `tests/blender/test_look_materials.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `materials.LABELS["facade_detail"] = "Facade detail"`, `COLOURS["facade_detail"]`; `LOOK_GROUP = "Ghost Town · Street Look"`; `LOOK_NODE = "Ghost Town Street Look"`; `BUILDING_MATERIALS`; `KIND_CODES = {"storefront": 1, "opaque": 2, "glass": 3, "cap": 4}`; `MAX_ZONES = 4`; `street_look_group()`; `ensure_street_look(mat, kind) -> node | None`; `set_street_look(look=None, brightness=None)`. Per-object properties the group reads: `gt_look_on`, `gt_look_base_z`, `gt_look_floor_h`, `gt_look_bay_glass`, `gt_look_bay_opaque`, and for N in 1..4 `gt_look_z{N}_top` (top of zone N above the lowest point; 1e5 for "to the top"), `gt_look_z{N}_kind` (code, 0 = unused) and `gt_look_z{N}_colour` (linear RGB).

- [ ] **Step 1: Write the failing tests** — create `tests/blender/test_look_materials.py`

```python
import math
import os
import tempfile

import bpy
import numpy as np

from ghosttown import materials

BRICK, GLASS = (0.30, 0.12, 0.08), (0.20, 0.40, 0.60)


def _close(rgba, rgb):
    return all(abs(a - b) < 1e-6 for a, b in zip(tuple(rgba)[:3], rgb))


def test_the_group_sits_in_front_of_base_color_and_roughness():
    mat = materials.get_material("building")
    node = materials.ensure_street_look(mat, "building")
    bsdf = next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    assert node.node_tree.name == materials.LOOK_GROUP and mat.name == "Context - Building"
    assert bsdf.inputs["Base Color"].links[0].from_node == node
    assert bsdf.inputs["Roughness"].links[0].from_node == node
    assert _close(node.inputs["Plain Color"].default_value, materials.COLOURS["building"])


def test_adding_it_twice_changes_nothing():
    mat = materials.get_material("building")
    materials.ensure_street_look(mat, "building")
    count = len(mat.node_tree.nodes)
    materials.ensure_street_look(mat, "building")
    assert len(mat.node_tree.nodes) == count
    assert len([g for g in bpy.data.node_groups if g.name.startswith(materials.LOOK_GROUP)]) == 1


def test_switches_reach_every_material_with_the_group():
    mats = [materials.get_material(k) for k in ("building", "building_guessed")]
    for mat, kind in zip(mats, ("building", "building_guessed")):
        materials.ensure_street_look(mat, kind)
    materials.set_street_look(look=False, brightness=0.8)
    for mat in mats:
        node = mat.node_tree.nodes[materials.LOOK_NODE]
        assert node.inputs["Look"].default_value == 0.0 and abs(node.inputs["Brightness"].default_value - 0.8) < 1e-6


def test_get_material_keeps_the_group_and_refreshes_its_plain_colour():
    mat = materials.get_material("building")
    node = materials.ensure_street_look(mat, "building")
    node.inputs["Plain Color"].default_value = (1, 0, 0, 1)
    materials.get_material("building")
    assert mat.node_tree.nodes.get(materials.LOOK_NODE) == node
    assert _close(node.inputs["Plain Color"].default_value, materials.COLOURS["building"])


def test_the_detail_material_has_a_stable_name():
    assert materials.get_material("facade_detail").name == "Context - Facade detail"


def _box_with_look(on):
    verts = [(-10, 0, 0), (10, 0, 0), (10, 10, 0), (-10, 10, 0), (-10, 0, 30), (10, 0, 30), (10, 10, 30), (-10, 10, 30)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me = bpy.data.meshes.new("box")
    me.from_pydata(verts, [], faces)
    mat = materials.get_material("building")
    materials.ensure_street_look(mat, "building")
    me.materials.append(mat)
    ob = bpy.data.objects.new("box", me)
    bpy.context.scene.collection.objects.link(ob)
    zones = [(3.0, 1, (0.03, 0.03, 0.03)), (12.0, 2, BRICK), (1e5, 3, GLASS), (1e5, 0, (0, 0, 0))]
    ob["gt_look_on"] = 1.0 if on else 0.0
    ob["gt_look_base_z"], ob["gt_look_floor_h"] = 0.0, 3.5
    ob["gt_look_bay_glass"], ob["gt_look_bay_opaque"] = 1.5, 3.0
    for n, (top, kind, colour) in enumerate(zones, 1):
        ob[f"gt_look_z{n}_top"], ob[f"gt_look_z{n}_kind"], ob[f"gt_look_z{n}_colour"] = top, float(kind), list(colour)
    return ob


def _render_rows(heights):
    """Mean rendered colour of the box's south face at each height, seen square-on in an orthographic view
    lit by a plain white sky."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 8
    scene.cycles.device = "CPU"
    scene.view_settings.view_transform = "Standard"   # plain sRGB, so hues are not compressed
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 40, 80, 100
    world = bpy.data.worlds.new("white")
    world.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
    scene.world = world
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type, cam.data.ortho_scale = "ORTHO", 32.0
    cam.location, cam.rotation_euler = (0, -50, 15), (math.pi / 2, 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    path = os.path.join(tempfile.mkdtemp(), "look.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    px = np.array(bpy.data.images.load(path).pixels[:]).reshape(80, 40, 4)   # rows from the bottom
    return [px[int((h + 1.0) / 32.0 * 80), 12:28, :3].mean(axis=0) for h in heights]


def test_zones_reach_the_render():
    _box_with_look(on=True)
    brick, glass = _render_rows([8.0, 20.0])
    assert brick[0] > brick[2] * 1.3      # brick reads red
    assert glass[2] > glass[0] * 1.3      # glass reads blue


def test_without_a_look_the_plain_colour_shows():
    _box_with_look(on=False)
    row, = _render_rows([20.0])
    assert abs(row[0] - row[2]) < 0.05
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py -- -k look_materials`
Expected: FAIL with `AttributeError: module 'ghosttown.materials' has no attribute 'ensure_street_look'`.

- [ ] **Step 3: Implement** — replace `ghosttown/materials.py` with:

```python
"""One material per kind, named 'Context - <Label>'. Exporters carry these names over as layers or
materials, which is what Revit (Object Styles › Imported Objects) and other BIM tools see.

Street Look adds one shared node group in front of the building materials' Base Color and Roughness. It
reads each building's gt_look_* custom properties, so one material renders every building differently while
its name, and the plain colour exporters read, stay the same."""
import bpy

PREFIX = "Context - "
LABELS = {
    "building": "Building", "building_on_site": "Building (on site)", "building_guessed": "Building (height guessed)",
    "parcel": "Parcel", "parcel_on_site": "Parcel (site)",
    "ground": "Ground", "road": "Road", "sidewalk": "Sidewalk", "parking": "Parking",
    "rail": "Rail", "green": "Green", "water": "Water", "tree": "Tree",
    "facade_detail": "Facade detail",
}
COLOURS = {
    "building": (0.86, 0.86, 0.84), "building_on_site": (0.85, 0.20, 0.20), "building_guessed": (0.95, 0.62, 0.25),
    "parcel": (0.55, 0.25, 0.60), "parcel_on_site": (0.75, 0.10, 0.55),
    "ground": (0.80, 0.76, 0.66), "road": (0.33, 0.33, 0.35), "sidewalk": (0.70, 0.70, 0.70),
    "parking": (0.52, 0.52, 0.55), "rail": (0.45, 0.32, 0.22), "green": (0.45, 0.66, 0.35),
    "water": (0.30, 0.52, 0.80), "tree": (0.18, 0.42, 0.20),
    "facade_detail": (0.08, 0.085, 0.09),
}

LOOK_GROUP = "Ghost Town · Street Look"
LOOK_NODE = "Ghost Town Street Look"
BUILDING_MATERIALS = ("building", "building_on_site", "building_guessed")
KIND_CODES = {"storefront": 1, "opaque": 2, "glass": 3, "cap": 4}
MAX_ZONES = 4
DARK_GLASS = (0.03, 0.035, 0.04)
PLAIN_ROUGHNESS = 0.75


def material_name(kind):
    return PREFIX + LABELS[kind]


def get_material(kind):
    name = material_name(kind)
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    rgba = COLOURS[kind] + (1.0,)
    mat.diffuse_color = rgba
    if mat.node_tree is not None:
        for node in mat.node_tree.nodes:
            if node.bl_idname == "ShaderNodeBsdfPrincipled":
                node.inputs["Base Color"].default_value = rgba
                node.inputs["Roughness"].default_value = PLAIN_ROUGHNESS
        look = mat.node_tree.nodes.get(LOOK_NODE)
        if look is not None:
            look.inputs["Plain Color"].default_value = rgba
    return mat


def street_look_group():
    """The shared node group: Plain Color, Look (0 or 1) and Brightness in; Color and Roughness out."""
    group = bpy.data.node_groups.get(LOOK_GROUP)
    if group is not None:
        return group
    group = bpy.data.node_groups.new(LOOK_GROUP, "ShaderNodeTree")
    face = group.interface
    face.new_socket("Plain Color", in_out="INPUT", socket_type="NodeSocketColor")
    face.new_socket("Look", in_out="INPUT", socket_type="NodeSocketFloat").default_value = 1.0
    face.new_socket("Brightness", in_out="INPUT", socket_type="NodeSocketFloat").default_value = 1.15
    face.new_socket("Color", in_out="OUTPUT", socket_type="NodeSocketColor")
    face.new_socket("Roughness", in_out="OUTPUT", socket_type="NodeSocketFloat")
    _build_street_look(group)
    return group


def _build_street_look(group):
    nodes, links = group.nodes, group.links
    gin, gout = nodes.new("NodeGroupInput"), nodes.new("NodeGroupOutput")

    def feed(value, socket):
        if isinstance(value, (int, float)):
            socket.default_value = value
        elif isinstance(value, tuple):
            socket.default_value = (*value, 1.0) if len(value) == 3 else value
        else:
            links.new(value, socket)

    def math(op, a, b=None):
        node = nodes.new("ShaderNodeMath")
        node.operation = op
        feed(a, node.inputs[0])
        if b is not None:
            feed(b, node.inputs[1])
        return node.outputs[0]

    def equals(a, value):
        node = nodes.new("ShaderNodeMath")
        node.operation = "COMPARE"
        feed(a, node.inputs[0])
        node.inputs[1].default_value = value
        node.inputs[2].default_value = 0.25
        return node.outputs[0]

    def mix(fac, a, b):
        node = nodes.new("ShaderNodeMix")
        node.data_type = "RGBA"
        feed(fac, node.inputs["Factor"])
        feed(a, node.inputs["A"])
        feed(b, node.inputs["B"])
        return node.outputs["Result"]

    def blend(fac, a, b):
        """a where fac is 0, b where fac is 1, for numbers."""
        return math("ADD", math("MULTIPLY", a, math("SUBTRACT", 1.0, fac)), math("MULTIPLY", b, fac))

    def scale(colour, factor):
        node = nodes.new("ShaderNodeVectorMath")
        node.operation = "SCALE"
        feed(colour, node.inputs[0])
        feed(factor, node.inputs["Scale"])
        return node.outputs[0]

    def attr(name, output="Fac"):
        node = nodes.new("ShaderNodeAttribute")
        node.attribute_type = "OBJECT"
        node.attribute_name = name
        return node.outputs[output]

    def between(x, lo, hi):
        return math("MULTIPLY", math("GREATER_THAN", x, lo), math("LESS_THAN", x, hi))

    geometry = nodes.new("ShaderNodeNewGeometry")
    pos = nodes.new("ShaderNodeSeparateXYZ")
    links.new(geometry.outputs["Position"], pos.inputs[0])
    nrm = nodes.new("ShaderNodeSeparateXYZ")
    links.new(geometry.outputs["Normal"], nrm.inputs[0])
    # distance along a wall: the position on the wall's horizontal tangent (-ny, nx); height above its base
    along = math("SUBTRACT", math("MULTIPLY", pos.outputs[1], nrm.outputs[0]), math("MULTIPLY", pos.outputs[0], nrm.outputs[1]))
    h = math("SUBTRACT", pos.outputs[2], attr("gt_look_base_z"))
    floor_frac = math("FRACT", math("DIVIDE", h, math("MAXIMUM", attr("gt_look_floor_h"), 1.0)))
    bay_glass = math("MAXIMUM", attr("gt_look_bay_glass"), 0.5)
    bay_opaque = math("MAXIMUM", attr("gt_look_bay_opaque"), 0.5)
    spandrel = math("LESS_THAN", floor_frac, 0.2)
    mullion = math("LESS_THAN", math("FRACT", math("DIVIDE", along, bay_glass)), math("DIVIDE", 0.07, bay_glass))
    window = math("MULTIPLY", between(math("FRACT", math("DIVIDE", along, bay_opaque)), 0.2, 0.8),
                  between(floor_frac, 0.3, 0.82))
    shop_top = math("MINIMUM", 4.2, math("SUBTRACT", attr("gt_look_z1_top"), 0.6))
    shopfront = math("MULTIPLY", between(math("FRACT", math("DIVIDE", along, 3.0)), 0.06, 0.94), between(h, 0.4, shop_top))

    colour = gin.outputs["Plain Color"]
    rough = PLAIN_ROUGHNESS
    bottom = -1.0e5
    for n in range(1, MAX_ZONES + 1):
        top = attr(f"gt_look_z{n}_top")
        kind = attr(f"gt_look_z{n}_kind")
        c = attr(f"gt_look_z{n}_colour", "Color")
        inside = math("MULTIPLY", math("SUBTRACT", 1.0, math("LESS_THAN", h, bottom)), math("LESS_THAN", h, top))
        is_store, is_opaque, is_glass = equals(kind, 1.0), equals(kind, 2.0), equals(kind, 3.0)
        glass_c = mix(mullion, mix(spandrel, c, scale(c, 0.45)), DARK_GLASS)
        zone_c = mix(is_glass, mix(is_opaque, mix(is_store, c, mix(shopfront, c, DARK_GLASS)), mix(window, c, DARK_GLASS)), glass_c)
        zone_r = blend(is_glass, blend(is_opaque, blend(is_store, 0.8, math("SUBTRACT", 0.8, math("MULTIPLY", shopfront, 0.75))),
                                       math("SUBTRACT", 0.85, math("MULTIPLY", window, 0.75))),
                       math("ADD", math("MULTIPLY", math("MAXIMUM", spandrel, mullion), 0.55), 0.03))
        used = math("MULTIPLY", inside, math("GREATER_THAN", kind, 0.5))
        colour = mix(used, colour, zone_c)
        rough = blend(used, rough, zone_r)
        bottom = top
    on = math("MULTIPLY", math("MULTIPLY", attr("gt_look_on"), gin.outputs["Look"]),
              math("LESS_THAN", math("ABSOLUTE", nrm.outputs[2]), 0.5))   # roofs keep the plain colour
    links.new(mix(on, gin.outputs["Plain Color"], scale(colour, gin.outputs["Brightness"])), gout.inputs["Color"])
    links.new(blend(on, PLAIN_ROUGHNESS, rough), gout.inputs["Roughness"])


def ensure_street_look(mat, kind):
    """Put the Street Look group in front of a building material's Base Color and Roughness (once)."""
    tree = mat.node_tree
    if tree is None:
        return None
    bsdf = next((n for n in tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
    if bsdf is None:
        return None
    node = tree.nodes.get(LOOK_NODE)
    if node is None:
        node = tree.nodes.new("ShaderNodeGroup")
        node.name = node.label = LOOK_NODE
        node.node_tree = street_look_group()
        node.location = (bsdf.location.x - 300, bsdf.location.y)
        tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
        tree.links.new(node.outputs["Roughness"], bsdf.inputs["Roughness"])
    node.inputs["Plain Color"].default_value = COLOURS[kind] + (1.0,)
    return node


def set_street_look(look=None, brightness=None):
    """Set the Look switch and Photo brightness on every material carrying the group."""
    for mat in bpy.data.materials:
        node = mat.node_tree.nodes.get(LOOK_NODE) if mat.node_tree is not None else None
        if node is None:
            continue
        if look is not None:
            node.inputs["Look"].default_value = 1.0 if look else 0.0
        if brightness is not None:
            node.inputs["Brightness"].default_value = float(brightness)
```

- [ ] **Step 4: Run the tests to make sure they pass**

Run: `/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py -- -k look_materials`
Expected: PASS (the two render tests take a few seconds each on the CPU).

- [ ] **Step 5: Run every Blender test**

Run: `/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py`
Expected: all pass (the scene-build material tests still see only today's names, since nothing calls `ensure_street_look` there).

- [ ] **Step 6: Commit**

```bash
git add ghosttown/materials.py tests/blender/test_look_materials.py
git commit -m "feat: Street Look node group inside the building materials

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Detail geometry from a look entry

**Files:**
- Create: `ghosttown/look_detail.py`
- Test: `tests/fetch/test_look_detail.py` (pure Python, so it runs under pytest; `pythonpath` already includes `ghosttown`)

**Interfaces:**
- Consumes: a look.json building entry with `zones`, `floor_h` and `detail_walls` (Task 10).
- Produces: `look_detail.boxes(entry, base_z) -> (verts, faces)`: closed, outward-facing boxes for floor bands (heavier near zone boundaries), a band at the top of the storefront, and mullion fins at 1.5 m on glass zones.

- [ ] **Step 1: Write the failing tests** — create `tests/fetch/test_look_detail.py`

```python
import look_detail

ENTRY = {"floor_h": 4.0, "zones": [{"h0": 0, "h1": 3, "kind": "storefront", "colour": [0, 0, 0]},
                                   {"h0": 3, "h1": 12, "kind": "opaque", "colour": [0, 0, 0]},
                                   {"h0": 12, "h1": None, "kind": "glass", "colour": [0, 0, 0]}],
         "detail_walls": [{"a": [0, 0], "b": [10, 0], "n": [0, -1], "z0": 0, "z1": 30}]}


def _volume(verts, face):
    total = 0.0
    a = verts[face[0]]
    for i in range(1, len(face) - 1):
        b, c = verts[face[i]], verts[face[i + 1]]
        total += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
                  + a[2] * (b[0] * c[1] - b[1] * c[0]))
    return total / 6.0


def _boxes(verts, faces):
    return [faces[i:i + 6] for i in range(0, len(faces), 6)]


def test_floors_storefront_band_and_fins():
    verts, faces = look_detail.boxes(ENTRY, base_z=-0.3)
    # floors at 3 + 4k (7, 11, 15, 19, 23, 27), one storefront band, fins every 1.5 m on 10 m of glass
    assert len(faces) == 6 * (6 + 1 + 5) and len(verts) == 8 * 12
    assert min(v[2] for v in verts) >= -0.3 and max(v[2] for v in verts) <= 30 - 0.3


def test_every_box_is_closed_and_faces_out():
    for n in ([0, -1], [0, 1]):   # either side of the wall line
        entry = dict(ENTRY, detail_walls=[dict(ENTRY["detail_walls"][0], n=n)])
        verts, faces = look_detail.boxes(entry, base_z=0.0)
        for box in _boxes(verts, faces):
            assert sum(_volume(verts, f) for f in box) > 0


def test_a_band_near_a_zone_boundary_is_heavier():
    verts, faces = look_detail.boxes(ENTRY, base_z=0.0)
    heights = {}
    for box in _boxes(verts, faces):
        zs = sorted({verts[i][2] for f in box for i in f})
        xs = {verts[i][0] for f in box for i in f}
        if max(xs) - min(xs) > 5:   # a band, not a fin
            heights[round((zs[0] + zs[-1]) / 2, 2)] = zs[-1] - zs[0]
    assert heights[11.0] > heights[7.0]


def test_no_detail_walls_means_nothing():
    assert look_detail.boxes(dict(ENTRY, detail_walls=[]), base_z=0.0) == ([], [])
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `uv run pytest tests/fetch/test_look_detail.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'look_detail'`.

- [ ] **Step 3: Implement** `ghosttown/look_detail.py`

```python
"""Detail geometry for a building with Street Look: a band on every floor (heavier near zone boundaries),
a band at the top of the storefront, and mullion fins on glass. Pure Python, no bpy.

Heights in a look entry are metres above the building's lowest point; base_z turns them into scene z."""
import math

FLOOR_BAND = (0.10, 0.12)        # half height, depth (m)
ZONE_BAND = (0.25, 0.35)
STOREFRONT_BAND = (0.15, 0.50)
FIN = (0.04, 0.12)               # half width, depth
GLASS_BAY_M = 1.5
TOP_CLEARANCE_M = 0.2

# a unit box as (along, out, up) corners of right-handed outward faces
_FACES = (((0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)),
          ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)),
          ((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)),
          ((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)),
          ((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)),
          ((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)))


def _box(verts, faces, a, b, n, z0, z1, depth):
    """A closed box along a->b, from the wall out to `depth` metres along n, from z0 to z1."""
    k = len(verts)
    for p in (a, b):
        for d in (0.0, depth):
            for z in (z0, z1):
                verts.append((p[0] + n[0] * d, p[1] + n[1] * d, z))
    t = (b[0] - a[0], b[1] - a[1])
    left_handed = t[0] * n[1] - t[1] * n[0] < 0   # (along, out, up) mirrors a right-handed frame
    for face in _FACES:
        idx = [k + p * 4 + d * 2 + z for p, d, z in face]
        faces.append(tuple(reversed(idx)) if left_handed else tuple(idx))


def boxes(entry, base_z):
    """(verts, faces) for one building's detail."""
    verts, faces = [], []
    zones = entry["zones"]
    floor = float(entry.get("floor_h") or 3.5)
    boundaries = [z["h0"] for z in zones[1:]]
    shop_top = zones[1]["h0"] if zones[0]["kind"] == "storefront" and len(zones) > 1 else None
    glass = [(z["h0"], math.inf if z["h1"] is None else z["h1"]) for z in zones if z["kind"] == "glass"]
    origin = shop_top or 0.0
    for w in entry.get("detail_walls", []):
        a, b, n = w["a"], w["b"], w["n"]
        lo, hi = float(w["z0"]), float(w["z1"])
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length < 0.5 or hi - lo < 0.5:
            continue
        k = 1
        while origin + k * floor < hi - TOP_CLEARANCE_M:
            h = origin + k * floor
            k += 1
            if h < lo:
                continue
            half, depth = ZONE_BAND if any(abs(h - t) < floor / 2 for t in boundaries) else FLOOR_BAND
            _box(verts, faces, a, b, n, base_z + h - half, base_z + h + half, depth)
        if shop_top is not None and lo <= shop_top <= hi:
            half, depth = STOREFRONT_BAND
            _box(verts, faces, a, b, n, base_z + shop_top - half, base_z + shop_top + half, depth)
        tx, ty = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        for g0, g1 in glass:
            f0, f1 = max(lo, g0), min(hi, g1)
            if f1 - f0 < 1.0:
                continue
            for i in range(1, int(length / GLASS_BAY_M)):
                px, py = a[0] + tx * i * GLASS_BAY_M, a[1] + ty * i * GLASS_BAY_M
                _box(verts, faces, (px - tx * FIN[0], py - ty * FIN[0]), (px + tx * FIN[0], py + ty * FIN[0]), n,
                     base_z + f0, base_z + f1, FIN[1])
    return verts, faces
```

- [ ] **Step 4: Run the tests to make sure they pass**

Run: `uv run pytest tests/fetch/test_look_detail.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ghosttown/look_detail.py tests/fetch/test_look_detail.py
git commit -m "feat: detail geometry (floor bands, storefront band, mullion fins) from a look entry

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Applying a look in Blender

**Files:**
- Create: `ghosttown/look_build.py`
- Modify: `ghosttown/scene_build.py`
- Modify: `ghosttown/site_use.py`
- Create: `tests/blender/fixtures/mini_look.json`
- Test: `tests/blender/test_look_build.py`

**Interfaces:**
- Consumes: `look_schema.build_request`, `validate_request`, `validate_answer` (Task 2); `materials.ensure_street_look`, `set_street_look`, `get_material`, `material_name`, `KIND_CODES`, `MAX_ZONES`, `BUILDING_MATERIALS`, `LOOK_NODE` (Task 13); `look_detail.boxes` (Task 14); 0.3.0's `site_use.made_objects`, `meshes_of`, `FLAT_KEY`, `count_triangles`, `apply_roof_shapes`.
- Produces: `look_build.LOOK_PROP = "gt_look_json"`, `SUMMARY_PROP = "gt_look_summary"`, `CREDITS_PROP = "gt_look_credits"`, `DETAIL_GROUP = "Detail"`, `DETAIL_KIND = "facade_detail"`, `TOP = 1e5`, `SKY_WORLD = "Ghost Town Sky"`, `SKY_SUN = "Ghost Town Sky sun"`; `roots(scene)`, `made_buildings(root)`, `mesh_solids(ob) -> [{"rings", "z0", "z1"}]`, `make_request(root, settings, cache_dir, *, selected=(), now=None)`, `apply(scene, root, answer, settings=None) -> summary str`, `reapply(scene, root)`, `set_show_detail(scene, on)`, `summary(answer, present=None)`, `can_add_sky(scene)`, `add_sky(scene) -> world`; `scene_build.build(scene, doc, folder=None, *, keep_look=True)`; `site_use.SITE_KINDS` gains `facade_detail`. `settings` is anything with `look_detail`, `look_budget`, `look_not_before`, `show_look`, `show_detail` and `look_brightness` (the scene settings of Task 16; the tests use a stand-in).

Notes for the implementer:
- Only the site's own buildings take part (`site_use.made_objects`, as for the aerial photo on roofs); the user's duplicates are neither sent nor dressed.
- A building that keeps roof shapes (0.3.0's flat, fitted and LiDAR meshes) is read from its flat mesh, which is the prism set the fetcher models. The `gt_look_*` values live on the object, so they hold whichever roof shape is shown, and the node group sits in the building materials that every shape shares.
- `_set_props` calls `ob.update_tag()`: writing custom properties doesn't tag an object, so a building already on
  screen would keep rendering its old (or no) look. Headless tests only see it when the object was evaluated
  first, which `test_the_renderer_sees_the_values_of_buildings_already_on_screen` does.
- Values are world coordinates throughout: `mesh_solids` and `gt_look_base_z` read `matrix_world`, and the node group's Geometry Position is world space, so a building the user moved still lines up.
- The summary and credit line are stored on the site (`gt_look_summary`, `gt_look_credits`), like 0.3.0's other per-site state, so the panel shows the picked site's own result and a rebuild recomputes them.
- Detail meshes are exported with the site, so `facade_detail` joins `site_use.SITE_KINDS` and counts toward the Revit triangle figure.
- The sky's `sun_rotation` is a compass bearing (clockwise from +y, which is true north); `test_the_sky_glows_where_the_sun_lamp_shines_from` fails if it is mirrored.
- The OBJ exporter writes spaces in material names as underscores (`Context_-_Building`); that is today's behaviour, and the export test compares like with like.

- [ ] **Step 1: Write the fixture and the failing tests**

Create `tests/blender/fixtures/mini_look.json` (it matches `mini_context.json`: `osm:way:1` is the two-tier Tower whose lowest point is z = −0.3, `osm:way:2` the courtyard block; `osm:way:999` is not in the scene and must be ignored):

```json
{
  "schema": 1, "tool": "ghosttown 0.3.0", "photos_used": 3, "years": [2019, 2025],
  "buildings": {
    "osm:way:1": {
      "source": "photos", "photos": 3, "confidence": 0.7, "floor_h": 3.5,
      "zones": [
        {"h0": 0, "h1": 3, "kind": "storefront", "colour": [0.05, 0.05, 0.05]},
        {"h0": 3, "h1": 12, "kind": "opaque", "colour": [0.3, 0.12, 0.08]},
        {"h0": 12, "h1": null, "kind": "glass", "colour": [0.25, 0.4, 0.55]}
      ],
      "detail_walls": [
        {"a": [0, 10], "b": [20, 10], "n": [0, -1], "z0": 0.0, "z1": 12.3},
        {"a": [5, 15], "b": [15, 15], "n": [0, -1], "z0": 12.3, "z1": 60.3}
      ]
    },
    "osm:way:2": {
      "source": "guessed", "photos": 0, "confidence": 0.0, "floor_h": 3.5,
      "zones": [
        {"h0": 0, "h1": 4.5, "kind": "storefront", "colour": [0.32, 0.32, 0.31]},
        {"h0": 4.5, "h1": null, "kind": "opaque", "colour": [0.42, 0.42, 0.40]}
      ]
    },
    "osm:way:999": {
      "source": "guessed", "photos": 0, "confidence": 0.0, "floor_h": 3.5,
      "zones": [{"h0": 0, "h1": null, "kind": "opaque", "colour": [0.42, 0.42, 0.40]}]
    }
  },
  "sources": [{"key": "mapillary", "name": "Mapillary", "credit": "Street photos © Mapillary contributors, CC BY-SA 4.0"}],
  "notes": [{"level": "warn", "code": "mapillary_tiles", "text": "Some areas couldn't be searched."}]
}
```

Create `tests/blender/test_look_build.py`:

```python
import json
import math
import os
import re
import tempfile

import bmesh
import bpy
from mathutils import Vector

from ghosttown import look_build, look_detail, materials, scene_build, site_use
from ghosttown.ghosttown_fetch import look_schema as ls
from helpers import closed_and_outward, fitted_doc, load_fixture, mesh_arrays

CREDIT = "Street photos © Mapillary contributors, CC BY-SA 4.0"


class Settings:
    look_detail, look_budget, look_not_before = True, 150, 0
    show_look, show_detail, look_brightness = True, True, 1.15

    def __init__(self, **changes):
        self.__dict__.update(changes)


def _build(doc=None, **options):
    return scene_build.build(bpy.context.scene, doc or load_fixture("mini_context.json"), **options)


def _apply(root, settings=None):
    return look_build.apply(bpy.context.scene, root, load_fixture("mini_look.json"), settings or Settings())


def _building(bid):
    return next(ob for ob in bpy.data.objects if ob.get("ctx_id") == bid)


def _details():
    return [ob for ob in bpy.data.objects if ob.get("ctx_kind") == "facade_detail"]


def _area(ring):
    return 0.5 * sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))


def _points(ring):
    return {tuple(p) for p in ring}


def test_mesh_solids_read_back_the_tiers_and_courtyards():
    _build()
    low, high = sorted(look_build.mesh_solids(_building("osm:way:1")), key=lambda s: s["z1"])
    assert (low["z0"], low["z1"], high["z0"], high["z1"]) == (-0.3, 12.0, -0.3, 60.0)
    assert _points(low["rings"][0]) == {(0, 10), (20, 10), (20, 30), (0, 30)} and _area(low["rings"][0]) == 400
    assert _points(high["rings"][0]) == {(5, 15), (15, 15), (15, 25), (5, 25)}
    solid, = look_build.mesh_solids(_building("osm:way:2"))
    outer, hole = solid["rings"]
    assert _area(outer) == 400 and _area(hole) == -100 and _points(hole) == {(35, 15), (35, 25), (45, 25), (45, 15)}


def test_the_request_lists_the_buildings_and_marks_selected_detail():
    root = _build()
    tower = _building("osm:way:1")
    req = look_build.make_request(root, Settings(), "/tmp/gt-cache", selected=[tower], now=0)
    assert ls.validate_request(req) == []
    assert {b["id"]: b["detail"] for b in req["buildings"]} == {"osm:way:1": True, "osm:way:2": False}
    assert req["centre"] == {"lat": 43.649667, "lon": -79.380991} and req["radius_m"] == 150.0
    assert req["ground_at_centre_m"] == 84.7 and req["budget_photos"] == 150 and req["not_before_year"] is None
    assert req["out_dir"].startswith(os.path.join("/tmp/gt-cache", "runs", "look-"))
    off = look_build.make_request(root, Settings(look_detail=False, look_not_before=2019), "/tmp/gt-cache",
                                  selected=[tower], now=0)
    assert not any(b["detail"] for b in off["buildings"]) and off["not_before_year"] == 2019


def test_a_building_without_bottom_faces_is_left_out():
    root = _build()
    tower = _building("osm:way:1")
    bm = bmesh.new()
    bm.from_mesh(tower.data)
    bm.normal_update()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.normal.z < -0.99], context="FACES")
    bm.to_mesh(tower.data)
    bm.free()
    assert look_build.mesh_solids(tower) == []
    req = look_build.make_request(root, Settings(), "/tmp/gt-cache", selected=[tower], now=0)
    assert [b["id"] for b in req["buildings"]] == ["osm:way:2"] and ls.validate_request(req) == []


def test_apply_sets_properties_materials_credits_and_detail():
    root = _build()
    before = site_use.count_triangles(root, bpy.context.evaluated_depsgraph_get())
    assert _apply(root) == "Look from photos: 1 building · guessed: 1 · 3 photos (2019–2025)"
    assert root[look_build.SUMMARY_PROP].startswith("Look from photos") and root[look_build.CREDITS_PROP] == CREDIT
    tower = _building("osm:way:1")
    assert tower["gt_look_on"] == 1.0 and abs(tower["gt_look_base_z"] + 0.3) < 1e-6 and tower["gt_look_floor_h"] == 3.5
    assert [tower[f"gt_look_z{n}_kind"] for n in range(1, 5)] == [1.0, 2.0, 3.0, 0.0]
    assert [tower[f"gt_look_z{n}_top"] for n in range(1, 5)] == [3.0, 12.0, look_build.TOP, look_build.TOP]
    assert [round(c, 6) for c in tower["gt_look_z2_colour"]] == [0.3, 0.12, 0.08]
    guessed = _building("osm:way:2")
    assert guessed["gt_look_source"] == "guessed" and guessed["gt_look_z2_top"] == look_build.TOP
    names = sorted(m.name for m in bpy.data.materials if m.name.startswith("Context - "))
    assert names == sorted(["Context - Building", "Context - Building (height guessed)", "Context - Road",
                            "Context - Tree", "Context - Parcel", "Context - Facade detail"])
    for name in ("Context - Building", "Context - Building (height guessed)"):
        assert bpy.data.materials[name].node_tree.nodes.get(materials.LOOK_NODE) is not None
    assert bpy.data.materials["Context - Road"].node_tree.nodes.get(materials.LOOK_NODE) is None
    origin, = [ob for ob in root.objects if ob.get("ctx_id") == "origin"]
    for block in (root, origin):
        assert block["credits"].splitlines() == ["© OpenStreetMap contributors", CREDIT]
    detail, = _details()
    coll = detail.users_collection[0]
    assert detail.name == "Detail · Tower" and detail["ctx_id"] == "detail:osm:way:1"
    assert coll.get("ctx_group") == "Detail" and coll.name in root.children
    assert detail.name in json.loads(root["ctx_objects"]) and detail.data.materials[0].name == "Context - Facade detail"
    entry = load_fixture("mini_look.json")["buildings"]["osm:way:1"]
    assert len(detail.data.polygons) == len(look_detail.boxes(entry, base_z=-0.3)[1])
    assert closed_and_outward(*mesh_arrays(detail))
    triangles = sum(len(p.vertices) - 2 for p in detail.data.polygons)   # the detail counts for Revit
    assert site_use.count_triangles(root, bpy.context.evaluated_depsgraph_get()) == before + triangles


def test_the_renderer_sees_the_values_of_buildings_already_on_screen():
    root = _build()
    tower = _building("osm:way:1")
    assert "gt_look_on" not in tower.evaluated_get(bpy.context.evaluated_depsgraph_get())   # evaluated, as when shown
    _apply(root)
    assert tower.evaluated_get(bpy.context.evaluated_depsgraph_get())["gt_look_on"] == 1.0


def test_switches():
    root = _build()
    _apply(root, Settings(show_look=False, show_detail=False, look_brightness=0.8))
    node = bpy.data.materials["Context - Building"].node_tree.nodes[materials.LOOK_NODE]
    assert node.inputs["Look"].default_value == 0.0 and abs(node.inputs["Brightness"].default_value - 0.8) < 1e-6
    coll = _details()[0].users_collection[0]
    assert coll.hide_viewport and coll.hide_render
    look_build.set_show_detail(bpy.context.scene, True)
    assert not coll.hide_viewport and not coll.hide_render


def test_a_rebuild_keeps_the_look_and_regenerates_detail():
    _apply(_build())
    root = _build()
    assert json.loads(root[look_build.LOOK_PROP])["photos_used"] == 3 and CREDIT in root["credits"]
    assert root[look_build.SUMMARY_PROP] == "Look from photos: 1 building · guessed: 1 · 3 photos (2019–2025)"
    tower = _building("osm:way:1")
    assert tower["gt_look_on"] == 1.0 and tower["gt_look_z3_kind"] == 3.0
    detail, = _details()
    assert detail.name == "Detail · Tower" and detail.name in json.loads(root["ctx_objects"])
    assert all(me.users > 0 for me in bpy.data.meshes)


def test_a_rebuild_without_keep_drops_the_look():
    _apply(_build())
    root = _build(keep_look=False)
    assert look_build.LOOK_PROP not in root and "gt_look_on" not in _building("osm:way:1")
    assert _details() == [] and all(me.users > 0 for me in bpy.data.meshes) and CREDIT not in root["credits"]


def test_reapply_skips_buildings_that_are_gone():
    root = _build()
    _apply(root)
    bpy.data.objects.remove(_building("osm:way:1"))
    look_build.reapply(bpy.context.scene, root)
    assert _details() == [] and not [c for c in root.children if c.get("ctx_group") == "Detail"]
    assert not any(name.startswith("Detail") for name in json.loads(root["ctx_objects"]))
    assert _building("osm:way:2")["gt_look_on"] == 1.0


def _exported_material_names():
    folder = tempfile.mkdtemp()
    bpy.ops.wm.obj_export(filepath=os.path.join(folder, "site.obj"), export_materials=True)
    with open(os.path.join(folder, "site.mtl"), encoding="utf-8") as f:   # OBJ writes spaces as underscores
        from_obj = {line[len("newmtl "):].strip().replace("_", " ") for line in f if line.startswith("newmtl ")}
    bpy.ops.export_scene.fbx(filepath=os.path.join(folder, "site.fbx"))
    with open(os.path.join(folder, "site.fbx"), "rb") as f:   # binary FBX names objects "<name>\x00\x01<class>"
        from_fbx = {m.decode("utf-8") for m in re.findall(rb"(Context - [^\x00]+)\x00\x01Material", f.read())}
    return from_obj, from_fbx


def test_export_keeps_todays_material_names():
    root = _build()
    before_obj, before_fbx = _exported_material_names()
    _apply(root)
    after_obj, after_fbx = _exported_material_names()
    assert "Context - Building" in before_obj and "Context - Building" in before_fbx
    assert after_obj == before_obj | {"Context - Facade detail"}
    assert after_fbx == before_fbx | {"Context - Facade detail"}


def test_roof_shapes_share_the_look_and_the_request_reads_the_flat_mesh():
    folder = tempfile.mkdtemp()
    root = _build(fitted_doc(folder), folder=folder)
    tower = _building("osm:way:1")
    assert tower.data != tower[site_use.FLAT_KEY]   # a fitted roof shows after the build
    low, high = sorted(look_build.mesh_solids(tower), key=lambda s: s["z1"])
    assert (low["z1"], high["z1"]) == (12.0, 60.0)
    _apply(root)
    for use in ("lidar", "flat", "fitted"):
        site_use.apply_roof_shapes(root, use)
        assert tower["gt_look_on"] == 1.0 and abs(tower["gt_look_base_z"] + 0.3) < 1e-6
        assert any(m.node_tree.nodes.get(materials.LOOK_NODE) for m in tower.data.materials if m is not None)


def test_the_users_duplicates_are_neither_asked_about_nor_dressed():
    root = _build()
    tower = _building("osm:way:1")
    copy = tower.copy()
    copy.data = tower.data.copy()
    root.children["Buildings · 320 Bay St"].objects.link(copy)
    req = look_build.make_request(root, Settings(), "/tmp/gt-cache", now=0)
    assert sorted(b["id"] for b in req["buildings"]) == ["osm:way:1", "osm:way:2"]
    _apply(root)
    assert "gt_look_on" not in copy and tower["gt_look_on"] == 1.0


def test_add_sky_only_over_blenders_default_world():
    scene = bpy.context.scene
    assert scene.world is None and look_build.can_add_sky(scene)
    scene.world = bpy.data.worlds.new("World")
    assert scene.world.name == "World" and look_build.can_add_sky(scene)
    world = look_build.add_sky(scene)
    assert scene.world == world and world.name == look_build.SKY_WORLD and not look_build.can_add_sky(scene)
    sky = next(n for n in world.node_tree.nodes if n.bl_idname == "ShaderNodeTexSky")
    assert sky.sky_type == "MULTIPLE_SCATTERING" and not sky.sun_disc
    sun = bpy.data.objects[look_build.SKY_SUN]
    assert sun.data.type == "SUN" and sun.name in scene.collection.objects
    scene.world = bpy.data.worlds.new("Studio")
    assert not look_build.can_add_sky(scene)


def _sky_brightness(direction):
    """Mean rendered brightness of the world seen through a narrow camera pointing along direction."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 4
    scene.cycles.device = "CPU"
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x = scene.render.resolution_y = 16
    cam = scene.camera or bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    if scene.camera is None:
        scene.collection.objects.link(cam)
        scene.camera = cam
    cam.data.angle = math.radians(4)
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    path = os.path.join(tempfile.mkdtemp(), "sky.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    px = bpy.data.images.load(path).pixels[:]
    return sum(px[0::4]) / (len(px) / 4)


def test_the_sky_glows_where_the_sun_lamp_shines_from():
    look_build.add_sky(bpy.context.scene)
    sun = bpy.data.objects[look_build.SKY_SUN]
    sun.hide_render = True
    bpy.context.view_layer.update()
    to_sun = (sun.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
    mirrored = Vector((-to_sun.x, to_sun.y, to_sun.z))   # where the glow would be with east and west swapped
    bright, other = _sky_brightness(to_sun), _sky_brightness(mirrored)
    assert bright > 1.1 * other
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py -- -k look_build`
Expected: `FAIL test_look_build.py (import)` with `ImportError: cannot import name 'look_build' from 'ghosttown'`.

- [ ] **Step 3: Implement** `ghosttown/look_build.py`

```python
"""Street Look on the Blender side: the request from a site, and look.json applied to it.

The answer is stored on the context collection as JSON, so a rebuild can put it back on the new objects
by building id. Each building gets its values as gt_look_* custom properties, which the Street Look node
group in the building materials reads, whichever roof shape the building shows; detail buildings also
get a mesh in a Detail collection. Only the site's own buildings take part, never the user's duplicates.
"""
import json
import math
import os
import time
from collections import Counter

import bpy

from . import look_detail, materials, site_use
from .ghosttown_fetch import BUILDING_KINDS
from .ghosttown_fetch import look_schema as ls

LOOK_PROP = "gt_look_json"
SUMMARY_PROP, CREDITS_PROP = "gt_look_summary", "gt_look_credits"   # what the panel shows for the site
DETAIL_GROUP = "Detail"
DETAIL_KIND = "facade_detail"
TOP = 1.0e5                       # a zone top meaning "to the top of the building"
GLASS_BAY_M, OPAQUE_BAY_M = 1.5, 3.0
BOTTOM_NORMAL_Z = -0.99           # faces pointing this far down are a solid's underside
SKY_WORLD = "Ghost Town Sky"
SKY_SUN = "Ghost Town Sky sun"
SKY_STRENGTH = 0.25
SUN_ENERGY = 3.0
SUN_ELEVATION_DEG, SUN_AZIMUTH_DEG = 40.0, 200.0   # azimuth clockwise from north; +y is true north

_KIND_OF_MATERIAL = {materials.material_name(k): k for k in materials.BUILDING_MATERIALS}


def roots(scene):
    return [c for c in scene.collection.children_recursive if c.get("ctx_root")]


def made_buildings(root):
    """The site's own building objects (not the user's duplicates)."""
    return [ob for ob in site_use.made_objects(root, BUILDING_KINDS) if ob.type == "MESH"]


def _massing(ob):
    """The mesh the fetcher's prisms describe: the flat one when the building keeps roof shapes."""
    me = ob.get(site_use.FLAT_KEY)
    return ob.data if me is None else me


def mesh_solids(ob):
    """A building's solids as the fetcher reads them, in world coordinates: one per connected part of its
    flat mesh, with its underside's outline as rings (outline counter-clockwise, courtyards clockwise) and
    its lowest and highest points as z0 and z1. Parts without an underside are left out."""
    me = _massing(ob)
    co = [ob.matrix_world @ v.co for v in me.vertices]
    parent = list(range(len(co)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for poly in me.polygons:
        first = find(poly.vertices[0])
        for v in poly.vertices[1:]:
            other = find(v)
            if other != first:
                parent[other] = first
    to_world = ob.matrix_world.to_3x3().inverted_safe().transposed()
    undersides = {}   # part -> directed edges of its downward faces
    for poly in me.polygons:
        normal = to_world @ poly.normal
        if normal.length > 0 and normal.normalized().z < BOTTOM_NORMAL_Z:
            vs = poly.vertices
            undersides.setdefault(find(vs[0]), []).extend((vs[i], vs[(i + 1) % len(vs)]) for i in range(len(vs)))
    solids = []
    for part, directed in undersides.items():
        uses = Counter(frozenset(e) for e in directed)
        rings = []
        for loop in _loops([e for e in directed if uses[frozenset(e)] == 1]):
            ring = [[round(co[i].x, 3), round(co[i].y, 3)] for i in loop]
            if len(ring) >= 3 and abs(_area(ring)) > 1e-6:
                rings.append(ring)
        if not rings:
            continue
        rings.sort(key=lambda r: -abs(_area(r)))
        rings = [r if (_area(r) > 0) == (k == 0) else r[::-1] for k, r in enumerate(rings)]
        zs = [p.z for i, p in enumerate(co) if find(i) == part]
        solids.append({"rings": rings, "z0": round(min(zs), 3), "z1": round(max(zs), 3)})
    return solids


def _loops(edges):
    """Closed loops of vertex indices from directed boundary edges; open chains are dropped."""
    nxt = {}
    for a, b in edges:
        nxt.setdefault(a, []).append(b)
    loops = []
    while nxt:
        start = v = next(iter(nxt))
        loop = [start]
        while v in nxt:
            w = nxt[v].pop()
            if not nxt[v]:
                del nxt[v]
            if w == start:
                loops.append(loop)
                break
            loop.append(w)
            v = w
    return loops


def _area(ring):
    return 0.5 * sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))


def make_request(root, settings, cache_dir, *, selected=(), now=None):
    """The look request for a context collection: its buildings as they are now, with detail for the
    selected ones when Detail for selected is on."""
    chosen = {ob.name for ob in selected} if settings.look_detail else set()
    buildings = []
    for ob in made_buildings(root):
        solids = mesh_solids(ob)
        if solids:
            buildings.append({"id": ob["ctx_id"], "detail": ob.name in chosen, "solids": solids})
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    return ls.build_request(
        centre={"lat": root["lat"], "lon": root["lon"]}, radius_m=root["radius_m"],
        ground_at_centre_m=root.get("ground_at_centre_m"), buildings=buildings, cache_dir=cache_dir,
        out_dir=os.path.join(cache_dir, "runs", "look-" + stamp), budget_photos=settings.look_budget,
        not_before_year=settings.look_not_before or None)


def apply(scene, root, answer, settings=None):
    """Store a look.json answer on a context collection and dress its buildings; returns the summary."""
    root[LOOK_PROP] = json.dumps(answer, ensure_ascii=False, separators=(",", ":"))
    _dress(root, answer)
    if settings is not None:
        materials.set_street_look(look=settings.show_look, brightness=settings.look_brightness)
        set_show_detail(scene, settings.show_detail)
    return root[SUMMARY_PROP]


def reapply(scene, root):
    """Dress a context collection again from its stored look, e.g. after a rebuild. A stored look that
    can't be read is dropped."""
    try:
        answer = json.loads(root.get(LOOK_PROP, ""))
    except ValueError:
        answer = None
    if answer is None or ls.validate_answer(answer):
        for key in (LOOK_PROP, SUMMARY_PROP, CREDITS_PROP):
            root.pop(key, None)
        return
    _dress(root, answer)
    settings = getattr(scene, "ghosttown", None)
    if settings is not None:
        set_show_detail(scene, settings.show_detail)


def _dress(root, answer):
    """Values, materials, credits, detail and the summary for the site's buildings."""
    entries = answer["buildings"]
    dressed = set()
    for ob in made_buildings(root):
        for me in site_use.meshes_of(ob):   # every roof shape shares the building materials
            for mat in me.materials:
                if mat is not None and mat.name in _KIND_OF_MATERIAL:
                    materials.ensure_street_look(mat, _KIND_OF_MATERIAL[mat.name])
        entry = entries.get(ob["ctx_id"])
        _set_props(ob, entry)
        if entry is not None:
            dressed.add(ob["ctx_id"])
    _credit(root, answer["sources"])
    _rebuild_detail(root, entries)
    root[SUMMARY_PROP] = summary(answer, dressed)
    root[CREDITS_PROP] = "\n".join(dict.fromkeys(s["credit"] for s in answer["sources"]))


def _base_z(ob):
    return min((ob.matrix_world @ v.co).z for v in _massing(ob).vertices)


def _set_props(ob, entry):
    ob.update_tag()   # custom properties don't tag the object; without this, a building on screen keeps its old look
    if entry is None:
        ob["gt_look_on"] = 0.0
        return
    ob["gt_look_on"] = 1.0
    ob["gt_look_base_z"] = _base_z(ob)
    ob["gt_look_floor_h"] = float(entry["floor_h"])
    ob["gt_look_bay_glass"], ob["gt_look_bay_opaque"] = GLASS_BAY_M, OPAQUE_BAY_M
    ob["gt_look_source"] = entry["source"]
    ob["gt_look_confidence"] = float(entry.get("confidence", 0.0))
    zones = entry["zones"][:materials.MAX_ZONES]
    for n in range(1, materials.MAX_ZONES + 1):
        z = zones[n - 1] if n <= len(zones) else None
        ob[f"gt_look_z{n}_top"] = TOP if z is None or z["h1"] is None else float(z["h1"])
        ob[f"gt_look_z{n}_kind"] = 0.0 if z is None else float(materials.KIND_CODES[z["kind"]])
        ob[f"gt_look_z{n}_colour"] = [0.0, 0.0, 0.0] if z is None else [float(c) for c in z["colour"]]


def _credit(root, sources):
    """Add the look's credits to the collection's and the origin's (exporters keep the origin's)."""
    extra = [s["credit"] for s in sources]
    for block in [root, *(ob for ob in root.objects if ob.get("ctx_id") == "origin")]:
        lines = [line for line in str(block.get("credits", "")).splitlines() if line]
        block["credits"] = "\n".join(dict.fromkeys(lines + extra))


def _rebuild_detail(root, entries):
    """Replace the collection's detail meshes with ones made from the look entries."""
    made = json.loads(root.get("ctx_objects", "[]"))
    coll = next((c for c in root.children if c.get("ctx_group") == DETAIL_GROUP), None)
    if coll is not None:
        doomed = [ob for ob in coll.objects if ob.name in made and ob.get("ctx_kind") == DETAIL_KIND]
        gone = {ob.name for ob in doomed}
        made = [name for name in made if name not in gone]
        bpy.data.batch_remove(doomed + [ob.data for ob in doomed if ob.data is not None and ob.data.users == 1])
    new = []
    for ob in made_buildings(root):
        entry = entries.get(ob["ctx_id"])
        if entry and entry.get("detail_walls"):
            verts, faces = look_detail.boxes(entry, _base_z(ob))
            if faces:
                new.append(_detail_object(ob, verts, faces))
    if new and coll is None:
        coll = bpy.data.collections.new(f"{DETAIL_GROUP} · {root.get('ctx_label', root.name)}")
        coll["ctx_group"] = DETAIL_GROUP
        root.children.link(coll)
    for det in new:
        coll.objects.link(det)
        made.append(det.name)
    if coll is not None and not new and not coll.objects and not coll.children:
        bpy.data.collections.remove(coll)
    root["ctx_objects"] = json.dumps(made)


def _detail_object(building, verts, faces):
    name = f"Detail · {building.name}"
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.materials.append(materials.get_material(DETAIL_KIND))
    me.validate(clean_customdata=False)
    me.update()
    det = bpy.data.objects.new(name, me)
    det.color = materials.COLOURS[DETAIL_KIND] + (1.0,)
    det["ctx_id"] = f"detail:{building['ctx_id']}"
    det["ctx_kind"] = DETAIL_KIND
    return det


def set_show_detail(scene, on):
    """Show or hide the scene's detail collections, in viewports and in renders."""
    for root in roots(scene):
        for coll in root.children:
            if coll.get("ctx_group") == DETAIL_GROUP:
                coll.hide_viewport = coll.hide_render = not on


def summary(answer, present=None):
    """One line for the panel, e.g. 'Look from photos: 41 buildings · guessed: 23 · 128 photos (2014–2025)'.
    Counts only the buildings in `present` when given."""
    entries = [e for bid, e in answer["buildings"].items() if present is None or bid in present]
    n = sum(1 for e in entries if e["source"] == "photos")
    text = f"Look from photos: {n} building{'' if n == 1 else 's'} · guessed: {len(entries) - n}"
    k = answer.get("photos_used") or 0
    if k:
        text += f" · {k} photo{'' if k == 1 else 's'}"
        years = answer.get("years")
        if years:
            text += f" ({years[0]})" if years[0] == years[1] else f" ({years[0]}–{years[1]})"
    return text


def can_add_sky(scene):
    """True when the scene has no world or still has Blender's default one (a plain background)."""
    world = scene.world
    if world is None:
        return True
    if world.name != "World" or world.node_tree is None:
        return False
    return {n.bl_idname for n in world.node_tree.nodes} <= {"ShaderNodeBackground", "ShaderNodeOutputWorld"}


def add_sky(scene):
    """A sky texture world and a matching sun lamp, so glass has something to reflect."""
    world = bpy.data.worlds.get(SKY_WORLD) or bpy.data.worlds.new(SKY_WORLD)
    tree = world.node_tree
    tree.nodes.clear()
    out = tree.nodes.new("ShaderNodeOutputWorld")
    bg = tree.nodes.new("ShaderNodeBackground")
    sky = tree.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_disc = False
    sky.sun_elevation = math.radians(SUN_ELEVATION_DEG)
    sky.sun_rotation = math.radians(SUN_AZIMUTH_DEG)   # measured clockwise from +y, like a compass
    bg.inputs["Strength"].default_value = SKY_STRENGTH
    tree.links.new(sky.outputs["Color"], bg.inputs["Color"])
    tree.links.new(bg.outputs["Background"], out.inputs["Surface"])
    scene.world = world
    sun = bpy.data.objects.get(SKY_SUN)
    if sun is None:
        sun = bpy.data.objects.new(SKY_SUN, bpy.data.lights.new(SKY_SUN, "SUN"))
    sun.data.energy = SUN_ENERGY
    sun.rotation_euler = (math.radians(90.0 - SUN_ELEVATION_DEG), 0.0, math.radians(180.0 - SUN_AZIMUTH_DEG))
    if sun.name not in scene.collection.objects:
        scene.collection.objects.link(sun)
    return world
```

- [ ] **Step 4: Carry the look across a rebuild** in `ghosttown/scene_build.py`

Import it beside the others:

```python
from . import geometry, georef, look_build, materials, site_lidar, site_photo, site_use
```

Replace the start of `build`:

```python
def build(scene, doc, folder=None, *, keep_look=True):
    label = site_label(doc)
    old = find_root(scene, label)
    look = old.get(look_build.LOOK_PROP) if old is not None and keep_look else None
    if old is not None:
```

and its end, after the photo is attached, so the roof shapes and the photo are in place first:

```python
                pass  # a photo file Blender can't read: the site builds without a photo
    if look:
        root[look_build.LOOK_PROP] = look   # Street Look carries over to the new objects by building id
        look_build.reapply(scene, root)
    return root
```

`remove()` needs no change: the Detail collection carries `ctx_group`, and its objects are listed in `ctx_objects` with a `ctx_id`, so a rebuild removes them and their meshes like everything else Ghost Town made.

- [ ] **Step 5: Count detail for Revit** — in `ghosttown/site_use.py`:

```python
SITE_KINDS = BUILDING_KINDS + GROUND_KINDS + ("tree", "parcel", "parcel_on_site", "facade_detail")  # exported kinds
```

- [ ] **Step 6: Run the tests to make sure they pass**

Run: `/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py -- -k look_build`
Expected: `14 passed, 0 failed` (the sky test renders two 16 px images).

- [ ] **Step 7: Run every Blender test**

Run: `/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py`
Expected: all pass; the scene-build, roof-shape and photo tests are unchanged because a build without a stored look never calls `reapply`.

- [ ] **Step 8: Commit**

```bash
git add ghosttown/look_build.py ghosttown/scene_build.py ghosttown/site_use.py tests/blender/fixtures/mini_look.json tests/blender/test_look_build.py
git commit -m "feat: apply look.json to a site: building values, detail meshes, rebuild carry-over, sky

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: Settings, operators and the Street Look panel

**Files:**
- Modify: `ghosttown/props.py`
- Modify: `ghosttown/ops.py`
- Modify: `ghosttown/ui.py`
- Modify: `ghosttown/__init__.py`
- Test: `tests/blender/test_extension.py`

**Interfaces:**
- Consumes: `prefs.token` and `runner.Run(..., env_extra=)` (Task 12); `look_build` (Task 15); `look_schema.TOKEN_ENV`, `validate_request`, `validate_answer` (Task 2); `materials.set_street_look`, `LOOK_NODE` (Task 13); 0.3.0's `site_use.picked` and `count_triangles`.
- Produces: scene settings `look_budget`, `look_not_before`, `look_detail`, `look_keep`, `show_look`, `show_detail`, `look_brightness`; `ops.MISSING_PILLOW`, `NO_TOKEN`, `NO_SITE`, `NO_BUILDINGS`; `ops.look_refusal(context, online=None) -> sentence | None`; `ops.look_launch(context, cache_dir, online=None, now=None) -> (launch, None) | (None, sentence)` with `launch = {"args", "work_dir", "env", "root"}`; `ops.apply_look(context, root, path, report) -> summary | None`; `_FetcherOperator.needs` and `_FetcherOperator._launch(context, args, work_dir, env_extra=None)`; operators `ghosttown.street_look` (Apply Street Look) and `ghosttown.add_sky` (Add Sky); panel `GHOSTTOWN_PT_street_look`, a closed-by-default child of 0.3.0's Site panel that acts on the picked site.

`invoke` and `finished` stay thin so the logic is testable headless: background Blender has no window for a modal handler and reports online access as off, hence the `online` parameter.

- [ ] **Step 1: Write the failing tests**

In `tests/blender/test_extension.py`, widen the imports:

```python
import ghosttown
from ghosttown import look_build, materials, ops, runner, scene_build
from ghosttown.ghosttown_fetch import look_schema as ls
from ghosttown.ghosttown_fetch import request as rq
from helpers import FIXTURES, load_fixture, photo_doc
```

and append:

```python
LOOK = os.path.join(FIXTURES, "mini_look.json")
CREDIT = "Street photos © Mapillary contributors, CC BY-SA 4.0"


def _picked_site():
    root = scene_build.build(bpy.context.scene, load_fixture("mini_context.json"))
    bpy.context.scene.ghosttown.site = root
    return root


def test_street_look_registers_with_its_defaults():
    from ghosttown import ui

    ghosttown.register()
    try:
        assert hasattr(bpy.ops.ghosttown, "street_look") and hasattr(bpy.ops.ghosttown, "add_sky")
        assert ui.GHOSTTOWN_PT_street_look.is_registered and ui.GHOSTTOWN_PT_street_look.bl_parent_id == "GHOSTTOWN_PT_site"
        s = bpy.context.scene.ghosttown
        assert (s.look_budget, s.look_not_before, s.look_detail, s.look_keep) == (150, 0, False, True)
        assert (s.show_look, s.show_detail) == (True, True) and abs(s.look_brightness - 1.15) < 1e-6
    finally:
        ghosttown.unregister()


def test_street_look_says_why_it_cannot_start():
    ghosttown.register()
    os.environ.pop(ls.TOKEN_ENV, None)
    try:
        assert ops.look_refusal(bpy.context, online=False) == ops.OFFLINE
        assert ops.look_refusal(bpy.context, online=True) == ops.NO_TOKEN
        os.environ[ls.TOKEN_ENV] = "MLY|abc"
        assert ops.look_refusal(bpy.context, online=True) == ops.NO_SITE
        _picked_site()
        assert ops.look_refusal(bpy.context, online=True) is None
    finally:
        os.environ.pop(ls.TOKEN_ENV, None)
        ghosttown.unregister()


def test_street_look_hands_the_token_over_in_the_environment_only():
    ghosttown.register()
    os.environ[ls.TOKEN_ENV] = "MLY|secret"
    try:
        _picked_site()
        launch, problem = ops.look_launch(bpy.context, tempfile.mkdtemp(), online=True)
        assert problem is None and launch["env"] == {ls.TOKEN_ENV: "MLY|secret"}
        assert launch["args"][0] == "look" and launch["root"] == "Context · 320 Bay St"
        with open(launch["args"][1], encoding="utf-8") as f:
            req = json.load(f)
        assert ls.validate_request(req) == [] and "secret" not in json.dumps(req)
        assert not any("secret" in arg for arg in launch["args"])
    finally:
        os.environ.pop(ls.TOKEN_ENV, None)
        ghosttown.unregister()


def test_street_look_needs_pillow_and_names_it_when_missing():
    from types import SimpleNamespace

    real = runner.ensure_wheels
    runner.ensure_wheels = lambda wheels, refresh, package="shapely": package != "PIL"
    reports = []
    op = SimpleNamespace(key="look", needs=ops.GHOSTTOWN_OT_street_look.needs, report=lambda *a: reports.append(a))
    try:
        assert ops._FetcherOperator._launch(op, bpy.context, ["look", "x"], tempfile.mkdtemp()) == {"CANCELLED"}
        assert reports == [({"ERROR"}, ops.MISSING_PILLOW)] and "look" not in runner.ACTIVE
        assert ops.GHOSTTOWN_OT_build.needs == (("shapely", ops.MISSING_SHAPELY),)
    finally:
        runner.ensure_wheels = real


def test_a_finished_look_is_reported_and_kept_on_the_site():
    ghosttown.register()
    try:
        root = _picked_site()
        reports = []
        text = ops.apply_look(bpy.context, root, LOOK, lambda *a: reports.append(a))
        assert text == root[look_build.SUMMARY_PROP] == "Look from photos: 1 building · guessed: 1 · 3 photos (2019–2025)"
        assert root[look_build.CREDITS_PROP] == CREDIT and CREDIT in root["credits"]
        assert ({"WARNING"}, "Some areas couldn't be searched.") in reports and ({"INFO"}, text) in reports
    finally:
        ghosttown.unregister()


def test_a_broken_look_answer_changes_nothing():
    ghosttown.register()
    path = os.path.join(tempfile.mkdtemp(), "look.json")
    with open(path, "w") as f:
        json.dump({"schema": 9}, f)
    try:
        root = _picked_site()
        reports = []
        assert ops.apply_look(bpy.context, root, path, lambda *a: reports.append(a)) is None
        assert "schema" in reports[0][1] and look_build.LOOK_PROP not in root and look_build.SUMMARY_PROP not in root
    finally:
        ghosttown.unregister()


def test_the_switches_reach_the_materials_and_the_detail():
    ghosttown.register()
    try:
        root = _picked_site()
        ops.apply_look(bpy.context, root, LOOK, lambda *a: None)
        s = bpy.context.scene.ghosttown
        s.show_look, s.look_brightness, s.show_detail = False, 0.7, False
        node = bpy.data.materials["Context - Building"].node_tree.nodes[materials.LOOK_NODE]
        assert node.inputs["Look"].default_value == 0.0 and abs(node.inputs["Brightness"].default_value - 0.7) < 1e-6
        detail = next(c for c in root.children if c.get("ctx_group") == "Detail")
        assert detail.hide_viewport and detail.hide_render
    finally:
        ghosttown.unregister()


def test_a_rebuild_keeps_or_drops_the_look_as_set():
    ghosttown.register()
    path = os.path.join(FIXTURES, "mini_context.json")
    try:
        bpy.ops.ghosttown.import_context(filepath=path)
        ops.apply_look(bpy.context, bpy.data.collections["Context · 320 Bay St"], LOOK, lambda *a: None)
        bpy.ops.ghosttown.import_context(filepath=path)
        assert look_build.LOOK_PROP in bpy.data.collections["Context · 320 Bay St"]
        bpy.context.scene.ghosttown.look_keep = False
        bpy.ops.ghosttown.import_context(filepath=path)
        assert look_build.LOOK_PROP not in bpy.data.collections["Context · 320 Bay St"]
    finally:
        ghosttown.unregister()


def test_cancel_stops_a_running_street_look_too():
    ghosttown.register()
    try:
        run = runner.Run(["unused"], work_dir=tempfile.mkdtemp(), extra_paths=[], argv=SLEEPER)
        runner.ACTIVE["look"] = run
        assert bpy.ops.ghosttown.cancel() == {"FINISHED"}
        assert run.proc.poll() is not None and "look" not in runner.ACTIVE
    finally:
        runner.cancel_all()
        ghosttown.unregister()
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py -- -k test_extension`
Expected: the nine new tests FAIL (`AttributeError: module 'ghosttown.ops' has no attribute 'look_refusal'`, `... 'GHOSTTOWN_OT_street_look'`, `... 'apply_look'`, `... 'look_launch'`, and `AttributeError: bpy_struct: attribute "look_budget" from "GhostTownSettings" ...`); the existing ones pass.

- [ ] **Step 3: Implement the settings** in `ghosttown/props.py`

Import `IntProperty` too:

```python
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty,
                       StringProperty)
```

Add the switches' callbacks just above `class GhostTownResult` (lazy imports, like the roof callbacks):

```python
def _show_look(self, context):
    from . import materials
    materials.set_street_look(look=self.show_look)


def _show_detail(self, context):
    from . import look_build
    look_build.set_show_detail(self.id_data, self.show_detail)


def _look_brightness(self, context):
    from . import materials
    materials.set_street_look(brightness=self.look_brightness)
```

and append the settings to `GhostTownSettings`, after `roof_detail`:

```python
    look_budget: IntProperty(
        name="Photo budget", default=150, min=10, max=500,
        description="Download and read at most this many Mapillary photos")
    look_not_before: IntProperty(
        name="Not before", default=0, min=0, max=2100,
        description="Leave out photos taken before this year; 0 uses photos from any year")
    look_detail: BoolProperty(
        name="Detail for selected", default=False,
        description="Also model floor bands and mullions on the selected buildings (at most 20; about 5 is plenty)")
    look_keep: BoolProperty(
        name="Keep street look on rebuild", default=True,
        description="Build Context puts the street look back on the buildings that are still there")
    show_look: BoolProperty(
        name="Show street look", default=True, update=_show_look,
        description="Off shows the plain context colours again")
    show_detail: BoolProperty(
        name="Show detail", default=True, update=_show_detail,
        description="Show the detail meshes in viewports and renders. To leave them out of an export, untick their "
                    "Detail collection in the Outliner")
    look_brightness: FloatProperty(
        name="Photo brightness", default=1.15, min=0.2, max=3.0, update=_look_brightness,
        description="Scales the colours measured from the photos")
```

- [ ] **Step 4: Implement the operators** in `ghosttown/ops.py`

Widen the imports:

```python
from . import georef, look_build, prefs, runner, scene_build, site_photo, site_use
from .ghosttown_fetch import context as ctx
from .ghosttown_fetch import look_schema as ls
```

Replace the `NO_MATCH = ...` line with these lines:

```python
MISSING_PILLOW = ("Ghost Town's Pillow library isn't installed. Disable and re-enable Ghost Town in "
                  "Preferences › Add-ons, or reinstall it.")
NO_MATCH = "No Toronto address matched. Outside Toronto, enter latitude, longitude for now."
NO_TOKEN = f"Add your Mapillary token in Preferences › Add-ons › Ghost Town (or set {ls.TOKEN_ENV})."
NO_SITE = "Pick a site in the Site panel first."
NO_BUILDINGS = "This site has no buildings to dress."
```

In `import_into_scene`, honour Keep street look on rebuild:

```python
    root = scene_build.build(context.scene, doc, folder=os.path.dirname(os.path.abspath(path)),
                             keep_look=context.scene.ghosttown.look_keep)
```

Add the helpers just above `_redraw`:

```python
def look_refusal(context, online=None):
    """Why Apply Street Look can't start, as one sentence, or None."""
    if not (bpy.app.online_access if online is None else online):
        return OFFLINE
    if not prefs.token(context):
        return NO_TOKEN
    if site_use.picked(context) is None:
        return NO_SITE
    return None


def look_launch(context, cache_dir, online=None, now=None):
    """(launch, None) for Apply Street Look on the picked site, or (None, sentence) when it can't start.
    launch holds the fetcher arguments, the run folder, the child's extra environment and the site's
    name. The token goes in that environment only, never in the request file or the arguments."""
    refusal = look_refusal(context, online)
    if refusal:
        return None, refusal
    root = site_use.picked(context)
    req = look_build.make_request(root, context.scene.ghosttown, cache_dir,
                                  selected=context.selected_objects, now=now)
    if not req["buildings"]:
        return None, NO_BUILDINGS
    problems = ls.validate_request(req)
    if problems:
        return None, problems[0]
    os.makedirs(req["out_dir"], exist_ok=True)
    path = os.path.join(req["out_dir"], "look_request.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(req, f, indent=1)
    return {"args": ["look", path], "work_dir": req["out_dir"], "env": {ls.TOKEN_ENV: prefs.token(context)},
            "root": root.name}, None


def apply_look(context, root, path, report):
    """Read look.json and dress the site with it; the summary, or None after reporting a problem
    (nothing is changed then)."""
    try:
        with open(path, encoding="utf-8") as f:
            answer = json.load(f)
    except (OSError, ValueError) as e:
        report({"ERROR"}, f"Couldn't read {os.path.basename(path)} ({e}).")
        return None
    problems = ls.validate_answer(answer)
    if problems:
        report({"ERROR"}, problems[0])
        return None
    text = look_build.apply(context.scene, root, answer, context.scene.ghosttown)
    site_use.count_triangles(root, context.evaluated_depsgraph_get())   # detail counts for Revit
    for note in answer["notes"]:
        if note["level"] == "warn":
            report({"WARNING"}, note["text"])
    report({"INFO"}, text)
    return text
```

Replace the top of `_FetcherOperator` down to the `runner.ACTIVE[...]` line, so each operator names the libraries it needs and can hand the child extra environment:

```python
class _FetcherOperator:
    """Shared modal loop: run the fetcher under `key`, poll it on a timer, hand its answer to `finished`."""
    key = ""
    needs = (("shapely", MISSING_SHAPELY),)   # (package folder in the wheels, sentence when it's missing)
    _timer = None

    def _launch(self, context, args, work_dir, env_extra=None):
        wheels = runner.wheels_site_packages()
        for package, missing in self.needs:
            if not runner.ensure_wheels(wheels, refresh=bpy.ops.extensions.repo_refresh_all, package=package):
                self.report({"ERROR"}, missing)
                return {"CANCELLED"}
        runner.ACTIVE[self.key] = runner.Run(args, work_dir=work_dir, extra_paths=[wheels], env_extra=env_extra)
```

(the rest of `_launch`, from `runner.STATUS[self.key] = "Starting…"`, is unchanged).

Add the two operators just above `class GHOSTTOWN_OT_cancel`:

```python
class GHOSTTOWN_OT_street_look(_FetcherOperator, bpy.types.Operator):
    bl_idname = "ghosttown.street_look"
    bl_label = "Apply Street Look"
    bl_description = "Give the picked site's buildings colours and materials read from Mapillary street photos"
    bl_options = {"REGISTER", "UNDO"}
    key = "look"
    needs = (("shapely", MISSING_SHAPELY), ("PIL", MISSING_PILLOW))

    @classmethod
    def poll(cls, context):
        return "look" not in runner.ACTIVE

    def invoke(self, context, event):
        launch, problem = look_launch(context, prefs.cache_dir(context))
        if problem:
            self.report({"ERROR"}, problem)
            return {"CANCELLED"}
        self.root_name = launch["root"]
        return self._launch(context, launch["args"], launch["work_dir"], env_extra=launch["env"])

    def finished(self, context, result):
        root = bpy.data.collections.get(self.root_name)
        if root is None or not root.get("ctx_root"):
            self.report({"ERROR"}, "The site was removed while Street Look ran.")
            return {"CANCELLED"}
        return {"FINISHED"} if apply_look(context, root, result["look"], self.report) else {"CANCELLED"}


class GHOSTTOWN_OT_add_sky(bpy.types.Operator):
    bl_idname = "ghosttown.add_sky"
    bl_label = "Add Sky"
    bl_description = "Use a sky texture world and a sun lamp, so glass has something to reflect"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return look_build.can_add_sky(context.scene)

    def execute(self, context):
        look_build.add_sky(context.scene)
        self.report({"INFO"}, f"Added the {look_build.SKY_WORLD} world and a sun.")
        return {"FINISHED"}
```

In `GHOSTTOWN_OT_cancel.execute`, stop a running Street Look too:

```python
        runner.cancel("build")
        runner.cancel("find")
        runner.cancel("look")
```

- [ ] **Step 5: Add the panel** in `ghosttown/ui.py`

Widen the imports:

```python
import os
import textwrap

import bpy

from . import georef, look_build, ops, prefs, runner, site_use
```

and append:

```python
class GHOSTTOWN_PT_street_look(bpy.types.Panel):
    bl_idname = "GHOSTTOWN_PT_street_look"
    bl_label = "Street Look"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Ghost Town"
    bl_parent_id = "GHOSTTOWN_PT_site"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        settings = context.scene.ghosttown
        layout = self.layout
        refusal = ops.look_refusal(context)
        if refusal and refusal != ops.OFFLINE:   # the main panel already says when online access is off
            col = layout.box().column(align=True)
            for line in textwrap.wrap(refusal, max(20, context.region.width // 7)):
                col.label(text=line)
        col = layout.column()
        col.prop(settings, "look_budget")
        col.prop(settings, "look_not_before")
        col.prop(settings, "look_detail")
        col.prop(settings, "look_keep")
        if "look" in runner.ACTIVE:
            layout.label(text=runner.STATUS.get("look", "Working…"), icon="TIME")
            layout.operator("ghosttown.cancel", icon="CANCEL")
        else:
            row = layout.row()
            row.enabled = refusal is None
            row.operator("ghosttown.street_look", icon="IMAGE_DATA")
        if look_build.can_add_sky(context.scene):
            layout.operator("ghosttown.add_sky", icon="WORLD")
        col = layout.column()
        col.prop(settings, "show_look")
        col.prop(settings, "show_detail")
        col.prop(settings, "look_brightness")
        root = site_use.picked(context)
        if root is not None and root.get(look_build.SUMMARY_PROP):
            box = layout.box()
            box.label(text=root[look_build.SUMMARY_PROP], icon="CHECKMARK")
            for line in str(root.get(look_build.CREDITS_PROP, "")).splitlines():
                box.label(text=line)
```

- [ ] **Step 6: Register them** — in `ghosttown/__init__.py`, the end of `_CLASSES` becomes:

```python
    ops.GHOSTTOWN_OT_save_photo,
    ops.GHOSTTOWN_OT_street_look,
    ops.GHOSTTOWN_OT_add_sky,
    ops.GHOSTTOWN_OT_cancel,
    ui.GHOSTTOWN_PT_main,
    ui.GHOSTTOWN_PT_site,
    ui.GHOSTTOWN_PT_street_look,   # after its parent panel
)
```

- [ ] **Step 7: Run the tests to make sure they pass**

Run: `/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py -- -k test_extension`
Expected: all pass.

- [ ] **Step 8: Run every Blender test and the fetcher suite**

Run: `/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py`, then `uv run pytest -q`
Expected: all pass (`test_selftest_through_the_runner` needs Pillow in the dev venv, which Task 8's `uv sync` installed).

- [ ] **Step 9: Look at the panel in a real Blender**

Build the extension (`tools/build.sh`), install it in Blender 5.2 with Preferences › Get Extensions › Install from Disk, and open the Ghost Town tab. Check: Street Look sits closed under the Site panel; without a token it explains where to add one and Apply is greyed out; with a token and a picked site Apply is enabled; Add Sky shows only while the scene has no world or Blender's default one. Headless tests can't draw panels, so this is the only check of `draw()`.

- [ ] **Step 10: Commit**

```bash
git add ghosttown/props.py ghosttown/ops.py ghosttown/ui.py ghosttown/__init__.py tests/blender/test_extension.py
git commit -m "feat: Apply Street Look and Add Sky operators, settings and panel

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 17: A recorded street for the offline tests

**Files:**
- Create: `tools/record_look_fixture.py`
- Create (by recording): `tests/fetch/fixtures/kingst/look_request.json`, `tests/fetch/fixtures/kingst/mapillary.json.gz`
- Modify: `tests/fetch/fixtures/README.md`
- Test: `tests/fetch/test_look_recorded.py`

**Interfaces:**
- Consumes: `look.run` (Task 10), `look_schema.build_request` (Task 2), the fetcher's `cli.fetch`, `request.build` and `terrain.FlatTerrain` (0.3.0), `fakes.FakeNet` (Task 1).
- Produces: a recorder in 0.3.0's one-tool-per-fixture style, a fixture of about 370 KB, and one offline test on real photos.

The synthetic street of Task 10 checks the arithmetic; this checks the pipeline on real Mapillary photos and labels, recorded once and replayed offline. The order differs from the other tasks because the test needs the recording.

- [ ] **Step 1: Write the recorder** — create `tools/record_look_fixture.py`

```python
"""Record a small Mapillary street for the offline Street Look test.

    GHOSTTOWN_MAPILLARY_TOKEN=... uv run python tools/record_look_fixture.py [cache folder]

Builds the City's massing around 351 King St E, keeps the buildings within 60 m, runs Street Look on them with a
budget of 6 photos on flat ground, and writes tests/fetch/fixtures/kingst/: look_request.json, and
mapillary.json.gz with the listings cut down to the photos used, those photos at 512 px and their labels.
Pass a cache folder to reuse one that already holds the massing model (an 81 MB download).
Street photos © Mapillary contributors, CC BY-SA 4.0.
"""
import base64
import gzip
import io
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ghosttown"))

from PIL import Image  # noqa: E402

from ghosttown_fetch import cli, look, terrain  # noqa: E402
from ghosttown_fetch import look_schema as ls  # noqa: E402
from ghosttown_fetch import request as rq  # noqa: E402
from ghosttown_fetch.net import Net  # noqa: E402

CENTRE = {"lat": 43.651769, "lon": -79.365065}   # 351 King St E
KEEP_M = 60.0
BUDGET = 6
OUT = os.path.join(ROOT, "tests", "fetch", "fixtures", "kingst")


class Recorder:
    """A Net that keeps every answer Street Look got, by cache key or URL."""

    def __init__(self, net):
        self.net, self.answers = net, {}

    def get(self, url, *, key=None, **kwargs):
        body = self.net.get(url, key=key, **kwargs)
        self.answers[key or url] = body
        return body

    def cached(self, source, key, check=None):
        return None   # everything passes through get, so everything is recorded


def _near(el):
    return any(x * x + y * y <= KEEP_M ** 2 for s in el["solids"] for ring in s["rings"] for x, y in ring)


def _small(jpeg):
    im = Image.open(io.BytesIO(jpeg)).convert("RGB")
    im.thumbnail((512, 512))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85)
    return out.getvalue()


def main():
    token = os.environ.get(ls.TOKEN_ENV, "").strip()
    if not token:
        sys.exit(f"Set {ls.TOKEN_ENV} first.")
    work = tempfile.mkdtemp(prefix="ghosttown-look-fixture-")
    cache = sys.argv[1] if len(sys.argv) > 1 else os.path.join(work, "cache")
    req = rq.build(centre=CENTRE, radius_m=150, layers=["buildings"], cache_dir=cache,
                   out_dir=os.path.join(work, "run"))
    os.makedirs(req["out_dir"])
    path = os.path.join(req["out_dir"], "request.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(req, f)
    result = cli.fetch(path, None)
    if not result["ok"]:
        sys.exit(result["error"])
    with open(result["context"], encoding="utf-8") as f:
        doc = json.load(f)
    buildings = [{"id": el["id"], "solids": [{k: s[k] for k in ("rings", "z0", "z1")} for s in el["solids"]]}
                 for el in doc["elements"] if el["solids"] and _near(el)]
    look_req = ls.build_request(centre=CENTRE, radius_m=KEEP_M, buildings=buildings, cache_dir="unused",
                                out_dir="unused", budget_photos=BUDGET)
    terrain.load = lambda net, frame, radius_m: (terrain.FlatTerrain(), None)   # as in the test
    net = Recorder(Net(cache))
    answer = look.run(look_req, net, token)

    photos = {key.split(":")[1]: body for key, body in net.answers.items() if key.startswith("photo:")}
    labels = {url.split("/")[-2]: json.loads(body)["data"] for url, body in net.answers.items() if "/detections" in url}
    listings = {url: [im for im in json.loads(body)["data"] if str(im.get("id")) in photos]
                for url, body in net.answers.items() if "/images?" in url}
    data = {"listings": {url: ims for url, ims in listings.items() if ims},
            "photos": {i: base64.b64encode(_small(b)).decode("ascii") for i, b in photos.items()},
            "labels": {i: labels[i] for i in photos if i in labels}}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "look_request.json"), "w", encoding="utf-8") as f:
        json.dump(look_req, f, separators=(",", ":"))
    with gzip.open(os.path.join(OUT, "mapillary.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    size = sum(os.path.getsize(os.path.join(OUT, n)) for n in os.listdir(OUT))
    print(f"{len(buildings)} buildings; {len(photos)} photos recorded, {answer['photos_used']} used; {size / 1024:.0f} KB in {OUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Record**

Run: `GHOSTTOWN_MAPILLARY_TOKEN=<your token> uv run python tools/record_look_fixture.py "<extension cache folder>"` (the cache folder argument is optional; one that already holds the City's massing model saves an 81 MB download).
Expected: a line like `7 buildings; 6 photos recorded, 4 used; 368 KB in .../tests/fetch/fixtures/kingst`. Keep the fixture under about 500 KB; lower `BUDGET` if it is larger. Check that the token appears nowhere in the two files (`grep -c "MLY|" tests/fetch/fixtures/kingst/look_request.json` prints 0; the `.gz` holds only listings, photos and labels).

- [ ] **Step 3: Credit the recording** in `tests/fetch/fixtures/README.md`

Find:

```markdown
  Ontario. Contains information licensed under the Open Government Licence – Ontario.
```

Replace with:

```markdown
  Ontario. Contains information licensed under the Open Government Licence – Ontario.
- `kingst/look_request.json`, `kingst/mapillary.json.gz`: the City of Toronto's massing within 60 m of 351 King
  St E and six Mapillary street photos (512 px) with their labels, recorded by `tools/record_look_fixture.py`.
  Contains information licensed under the Open Government Licence – Toronto. Street photos © Mapillary
  contributors, CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/
```

- [ ] **Step 4: Write the test** — create `tests/fetch/test_look_recorded.py`

```python
"""Street Look on a recorded street: 351 King St E, its buildings within 60 m and six Mapillary photos with
their labels (tools/record_look_fixture.py). Real photos catch what the synthetic street can't."""
import base64
import gzip
import json
import os

import pytest

from fakes import FakeNet
from ghosttown_fetch import look, terrain
from ghosttown_fetch import look_schema as ls

HERE = os.path.join(os.path.dirname(__file__), "fixtures", "kingst")
TOWER = "toronto:massing:2025:361309"   # 351 King St E: dark shopfronts under lighter floors


def _lum(zone):
    r, g, b = zone["colour"]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _net(data):
    def answer(url, _data):
        if "/images?" in url:
            return json.dumps({"data": data["listings"].get(url, [])}).encode()
        if "?fields=thumb_2048_url" in url:
            image_id = url.split("/")[-1].split("?")[0]
            return json.dumps({"id": image_id, "thumb_2048_url": f"https://photos.test/{image_id}.jpg"}).encode()
        if url.startswith("https://photos.test/"):
            return base64.b64decode(data["photos"][url.rsplit("/", 1)[1][:-len(".jpg")]])
        if "/detections" in url:
            return json.dumps({"data": data["labels"][url.split("/")[-2]]}).encode()
        raise AssertionError(f"unexpected request {url}")

    return FakeNet({"mapillary": answer})


@pytest.fixture(scope="module")
def recorded():
    with open(os.path.join(HERE, "look_request.json"), encoding="utf-8") as f:
        req = json.load(f)
    with gzip.open(os.path.join(HERE, "mapillary.json.gz"), "rt", encoding="utf-8") as f:
        return req, json.load(f)


def test_the_recorded_street_gives_the_tower_its_dark_shopfronts(recorded, monkeypatch, tmp_path):
    req, data = recorded
    monkeypatch.setattr(terrain, "load", lambda net, frame, radius_m: (terrain.FlatTerrain(), None))
    answer = look.run(dict(req, cache_dir=str(tmp_path), out_dir=str(tmp_path / "run")), _net(data), "MLY|test")
    assert ls.validate_answer(answer) == []
    assert 3 <= answer["photos_used"] <= req["budget_photos"] and answer["sources"][0]["key"] == "mapillary"
    tower = answer["buildings"][TOWER]
    assert tower["source"] == "photos" and len(tower["zones"]) >= 2
    shop, above = tower["zones"][:2]
    assert shop["kind"] == "storefront" and _lum(shop) < _lum(above)
    assert set(answer["buildings"]) == {b["id"] for b in req["buildings"]}
```

- [ ] **Step 5: Run it**

Run: `uv run pytest tests/fetch/test_look_recorded.py -v`
Expected: PASS, offline (`--disable-socket` is on). The assertion is a fact about the street, dark shopfronts under lighter floors at 351 King St E, which the 2026-10-07 recording showed; if a new recording fails it, look at the answer before touching the test.

- [ ] **Step 6: Run the whole fetcher suite**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add tools/record_look_fixture.py tests/fetch/fixtures/kingst tests/fetch/fixtures/README.md tests/fetch/test_look_recorded.py
git commit -m "test(fetch): Street Look on a recorded street at 351 King St E

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 18: Live checks: the smoke test and five Toronto sites

**Files:**
- Modify: `tools/smoke_live.py`
- Create: `tools/look_accuracy.py`

**Interfaces:**
- Consumes: the installed extension's `look_build.make_request` and `apply` (Task 15), `runner.run_blocking(..., env_extra=)` (Task 12); the fetcher's `look.run` (Task 10).
- Produces: a smoke test that applies Street Look when `GHOSTTOWN_MAPILLARY_TOKEN` is set; `tools/look_accuracy.py [cache folder] [site name ...]` printing one Markdown table row per site.

- [ ] **Step 1: Street Look in the smoke test** — in `tools/smoke_live.py`, add to the docstring:

```python
With GHOSTTOWN_MAPILLARY_TOKEN set, it also applies Street Look to the site (a budget of 60 photos).
```

and insert just before `bpy.ops.wm.save_as_mainfile(...)`:

```python
token = os.environ.get("GHOSTTOWN_MAPILLARY_TOKEN", "").strip()
if token:
    look_build = importlib.import_module(pkg + ".look_build")
    ls = importlib.import_module(pkg + ".ghosttown_fetch.look_schema")

    class LookSettings:
        look_detail, look_budget, look_not_before = False, 60, 0
        show_look, show_detail, look_brightness = True, True, 1.15

    look_req = look_build.make_request(root, LookSettings(), cache)
    os.makedirs(look_req["out_dir"])
    path = os.path.join(look_req["out_dir"], "look_request.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(look_req, f)
    result = runner.run_blocking(["look", path], work_dir=look_req["out_dir"], extra_paths=wheels, timeout=900,
                                 env_extra={ls.TOKEN_ENV: token})
    print("LOOK", result)
    assert result["ok"], result
    with open(result["look"], encoding="utf-8") as f:
        print("LOOK SUMMARY", look_build.apply(bpy.context.scene, root, json.load(f), LookSettings()))
    if doc["region"] == "toronto":
        assert result["from_photos"] >= 1, result
```

- [ ] **Step 2: The accuracy tool** — create `tools/look_accuracy.py`

```python
"""Street Look on five Toronto sites, to catch changes for the worse in choosing photos or reading facades.
Not part of CI: it needs the network and a Mapillary token, and takes a few minutes a site.

    GHOSTTOWN_MAPILLARY_TOKEN=... uv run python tools/look_accuracy.py [cache folder] [site name ...]

For each site it prints how many buildings got their look from photos, what the building at the address got,
and how long each stage took. Compare with the numbers in design/street-look.md (sections 3 and 10)."""
import json
import math
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ghosttown"))

from ghosttown_fetch import cli, look  # noqa: E402
from ghosttown_fetch import look_schema as ls  # noqa: E402
from ghosttown_fetch import request as rq  # noqa: E402
from ghosttown_fetch.net import Net  # noqa: E402

SITES = {
    "351 King St E": (43.651768898, -79.365064762),
    "320 Bay St": (43.649667039, -79.380991173),
    "235 Queens Quay W": (43.63923186, -79.383105327),
    "2300 Yonge St": (43.707157575, -79.399083527),
    "300 Borough Dr": (43.7762918562, -79.2580219048),
}
RADIUS_M = 300.0


def _buildings(lat, lon, cache, work):
    req = rq.build(centre={"lat": lat, "lon": lon}, radius_m=RADIUS_M, layers=["buildings"], cache_dir=cache,
                   out_dir=os.path.join(work, "run"))
    os.makedirs(req["out_dir"])
    path = os.path.join(req["out_dir"], "request.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(req, f)
    result = cli.fetch(path, None)
    if not result["ok"]:
        raise SystemExit(result["error"])
    with open(result["context"], encoding="utf-8") as f:
        doc = json.load(f)
    return [{"id": el["id"], "solids": [{k: s[k] for k in ("rings", "z0", "z1")} for s in el["solids"]]}
            for el in doc["elements"] if el["solids"]], doc.get("ground_at_centre_m")


def _at_address(buildings):
    """The building with a footprint corner nearest the address."""
    return min(buildings, key=lambda b: min(math.hypot(x, y) for s in b["solids"] for ring in s["rings"]
                                            for x, y in ring))["id"]


def _zones(entry):
    return " · ".join(f"{z['kind']} {z['h0']:g}–{'' if z['h1'] is None else format(z['h1'], 'g')}"
                      for z in entry["zones"])


def run_site(name, lat, lon, cache, token):
    work = tempfile.mkdtemp(prefix="ghosttown-accuracy-")
    buildings, ground = _buildings(lat, lon, cache, work)
    req = ls.build_request(centre={"lat": lat, "lon": lon}, radius_m=RADIUS_M, buildings=buildings,
                           ground_at_centre_m=ground, cache_dir=cache, out_dir=os.path.join(work, "look"))
    stages, start = {}, time.monotonic()
    answer = look.run(req, Net(cache), token, progress=lambda stage, pct: stages.setdefault(stage, time.monotonic() - start))
    total = time.monotonic() - start
    times = sorted(stages.items(), key=lambda kv: kv[1]) + [("End", total)]
    took = {a: round(t1 - t0) for (a, t0), (_b, t1) in zip(times, times[1:])}
    target = answer["buildings"][_at_address(buildings)]
    photos = sum(1 for e in answer["buildings"].values() if e["source"] == "photos")
    return (f"| {name} | {len(buildings)} | {photos} | {answer['photos_used']} | {target['source']}, "
            f"{target['confidence']:.2f}: {_zones(target)} | {took.get('Choosing photos', 0)} | "
            f"{took.get('Reading facades', 0)} | {round(total)} |")


def main():
    token = os.environ.get(ls.TOKEN_ENV, "").strip()
    if not token:
        sys.exit(f"Set {ls.TOKEN_ENV} first.")
    cache = sys.argv[1] if len(sys.argv) > 1 else os.path.join(tempfile.mkdtemp(prefix="ghosttown-accuracy-"), "cache")
    names = sys.argv[2:] or list(SITES)
    print("| Site | Buildings | From photos | Photos | Building at the address | Choosing s | Reading s | Total s |")
    print("|---|---|---|---|---|---|---|---|")
    for name in names:
        print(run_site(name, *SITES[name], cache, token), flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the smoke test against a fresh package**

Run: `tools/build.sh`, then `GHOSTTOWN_MAPILLARY_TOKEN=<your token> tools/smoke_installed.sh "43.651769, -79.365065" 150`
Expected: `SELFTEST` reports `pillow 11.3.0`, then `LOOK SUMMARY Look from photos: ...` and `SMOKE OK`. (On 2026-10-07 with the plan's code: 24 buildings, 18 from photos, 6 guessed, 37 photos.)

- [ ] **Step 4: Run the five sites**

Run: `GHOSTTOWN_MAPILLARY_TOKEN=<your token> uv run python tools/look_accuracy.py "<extension cache folder>"`
Expected: five rows. The 2026-10-07 row for 351 King St E, with listings cached: 87 buildings, 58 from photos, 112 photos, about 40 s choosing, 40 s reading, 95 s in all. Put the table in `design/street-look.md` section 10 with the date. The building at the address is the one to look at: at 351 King St E a dark storefront and a wall should come out every time; its glass (36–84 m) came out on some runs and not others, which is the first thing to improve (see the spec's section 13).

- [ ] **Step 5: Commit**

```bash
git add tools/smoke_live.py tools/look_accuracy.py design/street-look.md
git commit -m "test: Street Look in the live smoke test, and a five-site accuracy run

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 19: Documentation and credits

**Files:**
- Modify: `README.md`
- Modify: `CREDITS.md`

**Interfaces:**
- Consumes: the behaviour of Tasks 1–18.
- Produces: user-facing docs for Street Look: what it gives, how to use it, Revit, credits, privacy, limits, how it works, development.

- [ ] **Step 1: README** — make these replacements in `README.md`, in order:

Find:

```markdown
- **Aerial photo** (Toronto): the City's newest aerial photo of the site, kept inside the .blend file,
  for the ground and low roofs. See [Use](#use).
```

Replace with:

```markdown
- **Aerial photo** (Toronto): the City's newest aerial photo of the site, kept inside the .blend file,
  for the ground and low roofs. See [Use](#use).
- **Street Look** (a step after the build, with your own Mapillary token): facades coloured from street
  photos, with storefront, wall, glass and cap zones and window patterns, plus floor bands and mullions on
  a few buildings you pick. See [Street Look](#street-look).
```

Find:

```markdown
It bundles the one library it needs (shapely), so there is nothing to `pip install`.
```

Replace with:

```markdown
It bundles the libraries it needs (shapely, and Pillow for Street Look), so there is nothing to `pip install`.
```

Find:

```markdown
Switching never downloads anything again, and each site in a file keeps its own choices.
```

Replace with:

```markdown
Switching never downloads anything again, and each site in a file keeps its own choices.

### Street Look

Street Look gives a site's buildings colours and materials read from Mapillary's street photos: a dark
storefront, a brick or concrete body, glass with mullions, a cap, at measured heights, with windows spaced by
the floor height it finds. It is a separate step after Build Context and needs your own free Mapillary token:
create one at mapillary.com/dashboard/developers and paste it in Preferences › Add-ons › Ghost Town ›
**Mapillary token** (or set `GHOSTTOWN_MAPILLARY_TOKEN`).

1. Build Context, then open **Street Look** under the Site panel. It works on the site picked there.
2. Optionally select up to 20 buildings (about 5 is plenty) and tick **Detail for selected** to model floor
   bands, a storefront band and mullion fins on them, in a `Detail · <site>` collection.
3. Press **Apply Street Look**. A 300 m site in downtown Toronto takes about 2–3 minutes the first time,
   while the photos download, and about a minute after that. Cancel or Esc stops it; Ctrl+Z undoes it.
4. **Show street look**, **Show detail** and **Photo brightness** change the result without fetching again.
   **Add Sky**, shown while the scene has no world or Blender's default one, adds a sky texture and a sun so
   glass has something to reflect.

A building no photo shows clearly gets a plain storefront-and-body look, and the panel counts it as guessed:
"Look from photos: 61 buildings · guessed: 26 · 108 photos (2014–2025)". **Photo budget** (150 to start)
caps the photos read, nearest buildings first; **Not before** leaves out older photos. With **Keep street look
on rebuild** (on), Build Context puts the look back on the buildings that are still there. The look is a
shader driven by values on each building, so material names stay as they are, roof shapes and the roof photo
keep working, and no photo is stored in the .blend file.
```

Find:

```markdown
- Fitted roofs export as closed solids of a few faces each: the lightest measured roofs, and the ones to
  take into Revit.
```

Replace with:

```markdown
- Fitted roofs export as closed solids of a few faces each: the lightest measured roofs, and the ones to
  take into Revit.
- Street Look changes how buildings render, not their materials' names. Its detail meshes sit in the
  `Detail · <site>` collection with the `Context - Facade detail` material and count toward the triangle
  figure; exclude that collection (untick it in the Outliner) to leave them out of an export.
```

Find:

```markdown
| OpenStreetMap | Buildings outside Toronto | © OpenStreetMap contributors (ODbL) |
```

Replace with:

```markdown
| OpenStreetMap | Buildings outside Toronto | © OpenStreetMap contributors (ODbL) |
| Mapillary | Street Look: facade colours read from street photos | Street photos © Mapillary contributors, CC BY-SA 4.0 |
```

Find:

```markdown
As or Preferences › Save & Load).
```

Replace with:

```markdown
As or Preferences › Save & Load).

**Apply Street Look** contacts `graph.mapillary.com` (photo listings and labels) and Mapillary's image servers
on `fbcdn.net`, and only then. They receive the area around the site, the ids of the photos read and your
Mapillary token, which Ghost Town sends only in a request header and never stores in a .blend file. Photos and
labels are cached on your computer for 30 days; only the colours and heights read from them reach the .blend
file.
```

Find:

```markdown
Natural Resources Canada, the Province of Ontario or OpenStreetMap.
```

Replace with:

```markdown
Natural Resources Canada, the Province of Ontario, OpenStreetMap or Mapillary.
```

Find:

```markdown
- Rebuilding a site resets colours you changed on the `Context - …` materials.
```

Replace with:

```markdown
- Rebuilding a site resets colours you changed on the `Context - …` materials.
- Street Look reads facades from street photos, many from 2014–2019: glass in the lower floors that mirrors
  the street, or tall glass seen in only a few photos, can read as an opaque wall; sky at a roofline can tint
  a building's top; a building changed or built since the photos gets what they show.
- Street Look's windows and mullions are evenly spaced (1.5 m on glass, 3 m on walls) at the measured floor
  height, not each building's own.
```

Find:

```markdown
- `ghosttown/*.py` is the extension: panel, operators, the process runner and the scene builder.
```

Replace with:

```markdown
- `ghosttown/*.py` is the extension: panel, operators, the process runner and the scene builder.
- Street Look is a second fetcher command, `look`: it reads `look_request.json` and writes `look.json`, with
  the Mapillary token in the process's environment only.
```

Find:

```markdown
tools/smoke_installed.sh "320 Bay St" 300   # macOS: install into a throwaway profile, build a live site
```

Replace with:

```markdown
tools/smoke_installed.sh "320 Bay St" 300   # macOS: install into a throwaway profile, build a live site
                                            # (and apply Street Look when GHOSTTOWN_MAPILLARY_TOKEN is set)
uv run python tools/look_accuracy.py        # Street Look on five Toronto sites (needs the token)
```

- [ ] **Step 2: CREDITS.md**

Find:

```markdown
- **Geospatial Ontario** lidar-derived Digital Surface and Terrain Models: Contains information licensed under the
  Open Government Licence – Ontario. https://www.ontario.ca/page/open-government-licence-ontario
```

Replace with:

```markdown
- **Geospatial Ontario** lidar-derived Digital Surface and Terrain Models: Contains information licensed under the
  Open Government Licence – Ontario. https://www.ontario.ca/page/open-government-licence-ontario
- **Mapillary** street photos, from which Street Look reads facade colours (no photo is stored in your file):
  Street photos © Mapillary contributors, CC BY-SA 4.0. https://creativecommons.org/licenses/by-sa/4.0/
```

- [ ] **Step 3: Check Mapillary's terms** (the spec's open item in section 8)

Read Mapillary's current API terms of use and developer documentation on caching and rate limits. Record what
they say, with the date, in `design/street-look.md` section 8. If they don't allow keeping photos and labels
for 30 days, give the `mapillary` source its own shorter cache age in `Net` and say so in the README's privacy
paragraph; if they set a request rate, keep `sources/mapillary.WORKERS` under it.

- [ ] **Step 4: Check the brand and the numbers**

Run: `uv run pytest tests/fetch/test_package.py -v` (the brand test covers the add-on's files) and read the new README text once more: "Ghost Town" is two words in prose, and the times quoted match Task 18's run.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md CREDITS.md design/street-look.md
git commit -m "docs: Street Look in the README and credits

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 20: Look at it in Blender

Headless tests can't judge a facade. This is the check that caught Task 15's `update_tag` bug and the 16-minute first version of `first_hit`.

- [ ] **Step 1:** Install the package from Task 18's `tools/build.sh` in Blender 5.2, add your token in Preferences, and in a new scene build 351 King St E (`43.651769, -79.365065`) at 300 m.
- [ ] **Step 2:** Select the three buildings nearest the address, tick **Detail for selected**, and press **Apply Street Look**. Expected: the panel shows a summary like "Look from photos: 61 buildings · guessed: 26 · 108 photos (2014–2025)" and the credit line, in about 2–3 minutes the first time and about a minute after.
- [ ] **Step 3:** Press **Add Sky**, put a camera at street level south-west of the tower (for example at `(-90, -116, 1.7)` looking at `(25, -20, 38)`), and look in Rendered view with Cycles and with EEVEE. Expected: storefronts, walls with windows and glass with mullions on most buildings, without nudging anything; the detail bands on the three selected buildings; switching **Show street look** off brings back the plain colours, and back on restores the look.
- [ ] **Step 4:** Switch **Roof shapes** on a LiDAR site (or **Roofs: Photo** on a Toronto one) and check that the look stays on the walls.
- [ ] **Step 5:** Rebuild the site with Build Context and check the look and the detail come back; untick **Keep street look on rebuild**, rebuild, and check they are gone.
