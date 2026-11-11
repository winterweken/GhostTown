# Ghost Town for Revit (prototype)

A pyRevit extension that lets Ghost Town's **Send to Revit…** (in Blender's Site panel) draw a site in the open
Revit project as native elements, instead of going through an OBJ and a DXF. Blender and Revit run on the same
Windows computer and talk over loopback (`127.0.0.1`):

| From Ghost Town | In Revit |
|---|---|
| Contour lines and the site's edge | One **toposolid**: the site circle as its boundary, the contour vertices (and the ground's heights along the edge) as its points |
| Ground pieces: road, sidewalk, parking, rail, water, green | **Subdivisions** of that toposolid, one per piece, on the toposolid type named after the piece's material (`Context - Road`, `Context - Water`…) when the project has one |
| Buildings and development application boxes | One **DirectShape** each in Generic Models, built from its triangles, every face on a `Context - <Kind>` material (made, with Ghost Town's colour, when missing) |
| Trees | **Planting** instances (see [Trees](#trees)) |
| Contour lines | **Model lines**, one sketch plane per height, in a `Context - Contour` line style |
| Lot lines | **Model lines** flat at z 0, in `Context - Parcel` and `Context - Parcel (site)` line styles. From Revit 2027 `PropertyLine.Create` could draw them as property lines; not done yet |
| Where the site is | **Site location** latitude and longitude, the **project position** (shared coordinates) and the **coordinate system** |

Everything happens in one undo step (**Ghost Town site**). A step that fails (say the toposolid) rolls back on
its own and the rest is still drawn; any element that fails is left out and named, with Revit's reason, in the
answer Blender reports. Revit's warnings are cleared silently, since nobody is at the keyboard to close a dialog.

This is a first prototype. It was written on a Mac and **has not yet run in Revit**: the [checklist](#test-checklist)
below is how to try it.

## Needs

- Revit **2024 or later** (toposolids arrived in 2024). On 2023 everything but the toposolid and its
  subdivisions is drawn.
- **pyRevit 5 or later**, with its default IronPython 2.7 engine. On the IronPython 3.4 engine use pyRevit
  6.5.0 or later, which fixed Routes for it.
- Ghost Town **0.9.0 or later** in Blender (it has **Send to Revit…**), **on the same Windows computer**. Revit runs only
  on Windows. If Revit runs in a Windows virtual machine on a Mac and Blender on the Mac, they aren't on the same
  computer: the VM's loopback isn't the Mac's, and this setup doesn't cover that.

## Install

1. Copy or clone the Ghost Town repository onto the computer, or download a release's **Source code (zip)**
   and unzip it. This folder, `revit\GhostTown.extension`, is the extension; pyRevit needs the folder
   **above** it.
2. Add that folder to pyRevit: **pyRevit › Settings › Custom Extension Directories › Add folder**, pick
   `…\GhostTown\revit`, **Save Settings and Reload**. Or, in a terminal:
   `pyrevit extensions paths add "C:\path\to\GhostTown\revit"`, then reload pyRevit.
3. Turn on Routes, pyRevit's web server, which is **off by default**: **pyRevit › Settings › Routes**, tick
   **Enable Routes Server**, keep the port at **48884**, **Save Settings and Reload**. Or
   `pyrevit configs routes enable` and `pyrevit configs routes port 48884`.
4. **Pin Routes to loopback** (next section), then restart Revit so the server starts on it.
5. Check it from a browser: `http://127.0.0.1:48884/ghosttown/status` answers with the Revit version and the
   open document's name.
6. Blender needs nothing more: **Send to Revit…** posts to `127.0.0.1:48884`. **Preferences › Add-ons ›
   Ghost Town** has **Revit host** and **Revit port** as a fallback; leave the host at `127.0.0.1`.

### Keep Routes on loopback: it has no authentication

Anything that can reach Routes' port can draw into, and slow down, the open Revit model, so it must listen on
`127.0.0.1` only, where only programs on this computer reach it.

pyRevit binds its server to the `host` of the `[routes]` section of its configuration, passed straight to
Python's `HTTPServer`. Left empty, which is the default, that means **every network interface** (pyRevit itself
describes it as `0.0.0.0`): anyone on your network could reach it. Pin it:

1. Close Revit. Open `%APPDATA%\pyRevit\pyRevit_config.ini` in Notepad.
2. In the `[routes]` section, set the host to loopback, keeping the lines already there:

   ```
   [routes]
   host = "127.0.0.1"
   ```

   Write the value the way the section's other values are written (pyRevit writes its strings in double quotes).
3. Start Revit, then check in a Command Prompt that it listens on loopback only:

   ```
   netstat -ano | findstr :48884
   ```

   The line should read `TCP 127.0.0.1:48884 … LISTENING`. `0.0.0.0:48884` or `[::]:48884` means it is still
   open to the network: check the ini (if the key is ignored, try `Host`, capitalised, as pyRevit's own code
   names it) and restart Revit.

Also: if Windows Defender Firewall asks whether Revit may accept connections, choose **Cancel** (untick both
networks); loopback doesn't need it. Never add a firewall rule or a router forward for the port, and turn Routes
off when you aren't using it.

### A second Revit

Each Revit open at the same time runs its own Routes server, and pyRevit gives each the first port not yet taken,
starting from 48884: the second Revit listens on 48885, the third on 48886. Blender sends to the port in its
preferences, 48884 unless changed; to send to another Revit, set **Revit port** to its port. Its status
(`http://127.0.0.1:48885/ghosttown/status`) names its open document.

## What lands where

- **Units.** Ghost Town sends metres; the extension converts to Revit's feet.
- **Origin.** The site centre (Ghost Town's origin) is Revit's internal origin. Elevation 0 is the ground at
  the site centre; the toposolid and trees are hosted on the level nearest elevation 0.
- **Shared coordinates.** With a survey point (the Site panel shows it), the shared coordinates are that
  survey grid: NAD83(CSRS) / MTM zone 10 (EPSG:2952) in Toronto, the site's UTM zone elsewhere. The internal
  origin is placed at the grid's easting and northing, at the ground's height above sea level, and turned by
  the grid convergence, so Revit's **True North** is grid north and project north is true north, as
  [Taking it into Revit](../../README.md#taking-it-into-revit) describes for doing it by hand. A Spot
  Coordinate on any point then reads its grid easting and northing. The survey point itself (the shared
  origin) sits at the grid's own origin, far from the site, as it does on any project on a survey grid; the
  Project Base Point at the internal origin shows the site centre's grid values.
- **Coordinate system.** The survey grid's EPSG code is passed to `SiteLocation.SetGeoCoordinateSystem`. If
  Revit doesn't know the code, the answer says so and the rest stands.
- **Site location.** Latitude and longitude of the site centre, for sun studies.

### Trees

The extension plants from the first of these planting families loaded in the project, by family name:
`RPC Tree - Deciduous`, `RPC Tree - Conifer`, `RPC Tree - Tropical`, else from any planting family. Load
`RPC Tree - Deciduous.rfa` from Revit's library (Planting folder) before sending. A planting family's height is
a type parameter, so trees are grouped by height in 2 m classes (2, 4, 6 … m) and each class gets its own type,
`<type> - Ghost Town 8 m`, duplicated from the family's first type with **Plant Height** (or **Height**) set to
the class. A later send reuses those types. Ghost Town's heights are the modelled trees' heights, ground to
crown top.

### Ground pieces

The subdivisions take the toposolid type named after their material when the project has one: make toposolid
types called `Context - Road`, `Context - Sidewalk`, `Context - Parking`, `Context - Rail`, `Context - Water` and
`Context - Green` (with the materials you want) to have them used. Otherwise each subdivision keeps the default
type. Plain ground (`Context - Ground`) is the toposolid itself. A flat site has no contours, so it gets no
toposolid and no subdivisions; Revit's answer notes it.

## Sending again

Each send draws a new copy: it doesn't replace what an earlier send drew. Undo it in Revit (**Ghost Town site**)
or delete the elements first. Everything it makes carries `Ghost Town` in its Comments.

## Test checklist

Do these on the Windows computer, with Blender and Revit both on it, in order, and note what fails and what Blender's report said.

1. [ ] Revit opens with pyRevit and no error mentioning Ghost Town or `startup.py` in pyRevit's output window.
2. [ ] With Routes on, `http://127.0.0.1:48884/ghosttown/status` in a browser answers `"ok": true`, the Revit
   version, and `"document": null` with no project open.
3. [ ] With a project open (a new one from the Architectural template is fine), the status answers its name and
   `"project": true`.
4. [ ] `netstat -ano | findstr :48884` shows Routes listening on `127.0.0.1:48884` only, and from another device on
   the network `http://<this-computer's-address>:48884/ghosttown/status` doesn't answer. With a second Revit
   open, its status answers on 48885, and Blender sends to it once **Revit port** is 48885.
5. [ ] In Blender, build a hilly site (one with contour lines) and press **Send to Revit…** with Revit's project
   open and RPC Tree - Deciduous loaded. Blender reports what Revit drew, and any failures as warnings.
6. [ ] Revit's undo list has one **Ghost Town site** entry, and undoing it removes everything.
7. [ ] Toposolid: there is one, its edge the site circle, its surface following the contour lines (section it, or
   compare with the contour model lines in a 3D view). Note how many points the answer says it took
   (`toposolid_points`) and whether Revit thinned them.
8. [ ] Subdivisions: roads, sidewalks, water and parks show as subdivisions of the toposolid. Make a
   `Context - Road` toposolid type, send again, and check the roads take it.
9. [ ] Buildings: one Generic Model per building, solid (they cut in a section), with their `Context - Building`,
   `Context - Building (on site)` and `Context - Building (height guessed)` materials and colours. Count them
   against Blender's Buildings collection. Note any the answer drew `buildings_as_mesh`.
10. [ ] Heights: a building's top in Revit is its Blender height (Blender's N panel, in metres) above level 0.
11. [ ] Trees: planting instances at the trees' places, standing on the toposolid (not floating or buried), with
    `… - Ghost Town 6 m`-style types whose Plant Height matches.
12. [ ] Contour lines: model lines at their heights, in the `Context - Contour` line style.
13. [ ] Lot lines: model lines in plan at level 0, in `Context - Parcel` and `Context - Parcel (site)` line styles.
14. [ ] Georeference, in a site plan: **Manage › Location** shows the site's place; with **Project North** the
    model sits as in Blender; switch the view's orientation to **True North** and it turns by the grid angle the
    Site panel shows, the right way (east of true north turns the model anticlockwise). A Spot Coordinate at the
    site centre reads the panel's easting, northing and elevation. If it turns the wrong way, the sign in
    `ghosttown_revit/site.py` `project_position` is the one to flip.
15. [ ] **Manage › Coordinates › Geographic Coordinate System** (Revit 2024 and later) shows the survey grid, or
    the answer said why it couldn't be set.
16. [ ] A send with no project open is refused with "No Revit document is open." in Blender, and Revit is unchanged.
17. [ ] A send with Revit closed: Blender says it couldn't reach Revit, quickly, without hanging.
18. [ ] A big site (1000 m, LiDAR roofs): note how long Revit takes and whether Blender's wait runs out.

## Files

- `startup.py` registers the `ghosttown` Routes API: `GET /ghosttown/status` and `POST /ghosttown/site`.
- `lib/ghosttown_revit/draw.py` draws a site with the Revit API.
- `lib/ghosttown_revit/site.py` is plain Python (no Revit): checking the payload, units, loops, points, faces,
  height classes, the project position and the answer. `tests/revit` tests it without Revit.
- The format Blender sends is described in `ghosttown/revit_bridge.py`.
