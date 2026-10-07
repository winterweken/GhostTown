# Recorded source answers

Recorded with `uv run python tools/record_fixtures.py`. Answers are gzipped exactly as received.

- `*/osm.json.gz`: OpenStreetMap data © OpenStreetMap contributors, available under the
  Open Database License (ODbL) 1.0, https://www.openstreetmap.org/copyright
- `*/nrcan_dtm.tif.gz`: NRCan HRDEM bare-earth elevation from
  `datacube.services.geo.ca/wrapper/ogc/elevation-hrdem-mosaic` (WCS 1.1.1, coverage `dtm`, EPSG:3857, a
  ±200 m box, GRIDOFFSETS 2,-2). Contains information licensed under the Open Government Licence – Canada.
  The London file is NRCan's 1×1 placeholder for a site outside Canada.
- `bay/toronto_*.json.gz`: City of Toronto open data. Contains information licensed under the Open Government
  Licence – Toronto.
- `bay/massing_subset.zip`: a slice of the City of Toronto 3D Massing model (2025), recorded by
  `tools/record_massing_fixture.py`. Contains information licensed under the Open Government Licence – Toronto.
- `ontario/bay_*.tif.gz`, `ontario/lake_none.tif`: Geospatial Ontario's lidar-derived surface and terrain models
  (`ws.geoservices.lrc.gov.on.ca`, ImageServer `exportImage`, a ±40 m box at 0.5 m around 320 Bay St),
  recorded by `tools/record_lidar_fixture.py`; `lake_none.tif` is the service's empty answer out in Lake
  Ontario. Contains information licensed under the Open Government Licence – Ontario.
- `kingst/look_request.json`, `kingst/mapillary.json.gz`: the City of Toronto's massing within 60 m of 351 King
  St E and six Mapillary street photos (512 px) with their labels, recorded by `tools/record_look_fixture.py`.
  Contains information licensed under the Open Government Licence – Toronto. Street photos © Mapillary
  contributors, CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/
