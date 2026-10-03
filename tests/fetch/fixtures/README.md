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
