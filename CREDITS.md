# Data credits

Ghost Town downloads open data at build time. Credit the sources you use in anything you publish:

- **OpenStreetMap**: © OpenStreetMap contributors, available under the Open Database License (ODbL) 1.0.
  https://www.openstreetmap.org/copyright
- **City of Toronto** open data (buildings, aerial photos, ground, trees, parcels, addresses, development applications,
  building permits): Contains information licensed under the Open Government Licence – Toronto.
  https://open.toronto.ca/open-data-license/
- **Natural Resources Canada** HRDEM elevation: Contains information licensed under the Open Government Licence – Canada.
  https://open.canada.ca/en/open-government-licence-canada
- **Geospatial Ontario** lidar-derived Digital Surface and Terrain Models: Contains information licensed under the
  Open Government Licence – Ontario. https://www.ontario.ca/page/open-government-licence-ontario
- **Mapillary** street photos, from which Street Look reads facade colours (no photo is stored in your file), and the
  labels, which are data Mapillary extracted from the photos, used under Mapillary's terms
  (https://www.mapillary.com/terms). Street photos © Mapillary contributors, CC BY-SA 4.0,
  https://creativecommons.org/licenses/by-sa/4.0/ — https://www.mapillary.com. The panel and the stored credits
  carry two lines: "Street photos © Mapillary contributors, CC BY-SA 4.0" and "Labels from Mapillary ·
  https://www.mapillary.com". The six resized photos in `tests/fetch/fixtures/kingst/` are CC BY-SA 4.0, not GPL-3
  (see `tests/fetch/fixtures/README.md` for each photo's credit), beside Mapillary's labels and listing records for
  those photos, whose redistribution is open (see that README). The Mapillary logo in the README is Mapillary's
  own, shown unmodified from https://github.com/mapillary/mapillary_press under CC BY-ND 4.0
  (https://creativecommons.org/licenses/by-nd/4.0/).

The add-on also lists the credits for each build in its panel and stores them on the context
collection (`credits` custom property).
