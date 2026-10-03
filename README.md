# GhostTown

A Blender 5.2 extension that builds the site context around a location from open data, as clean
geometry you can take into Revit or any BIM tool.

**Version 0.1 builds OpenStreetMap buildings on flat ground.** Address search, terrain, roads,
sidewalks, green space, water, trees, parcels and City of Toronto data are on the way.

## Install

1. Download the zip for your platform from the GitHub releases page.
2. In Blender, go to Edit › Preferences › Get Extensions › ⌄ › Install from Disk… and pick the zip.
3. Go to Edit › Preferences › System › Network and turn on **Allow Online Access**.

## Use

1. In the 3D View, open the sidebar (N) and the **GhostTown** tab.
2. Fill in the fields:
   - **Location:** `latitude, longitude`, for example `43.6497, -79.3810`.
   - **Site name** (optional): it names the collection.
   - **Radius:** 150 / 300 / 500 / 1000 m.
3. Press **Build Context**. It takes about 10–30 s; press Esc or Cancel to stop.

The result is a collection `Context · <site>`:
- one object per building, with `ctx_id`, `ctx_kind` and `ctx_height_source` custom properties;
- one material per kind (`Context - Building`, `Context - Building (height guessed)`, …);
- a `Context origin` empty at 0,0,0 that carries the latitude, longitude and credits.

The geometry sits in metres, with x east, y north, and the location at the origin.

## Taking it into Revit

- **OBJ:** set **Up Axis: Z** (the default is Y).
- **FBX:** tick **Loose Edges** if you want parcel lines.
- In Revit, import **origin to origin**.
- Material names become the layers or materials you can control under Object Styles ›
  Imported Objects.

## Data

See [CREDITS.md](CREDITS.md). OpenStreetMap data is © OpenStreetMap contributors (ODbL).

## Development

```bash
uv sync                    # Python 3.13 dev env with numpy 2.3.4 and shapely 2.1.2
uv run pytest              # fetcher tests, offline
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python-exit-code 1 --python tests/blender/run.py    # Blender-side tests
tools/build.sh             # per-platform extension zips in dist/
tools/smoke_installed.sh   # install into a throwaway profile and run one live build
```

## Licence

GPL-3.0-or-later. See [LICENSE](LICENSE).
