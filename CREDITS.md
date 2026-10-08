# Data credits

Ghost Town downloads open data at build time. Credit the sources you use in anything you publish:

- **OpenStreetMap**: © OpenStreetMap contributors, available under the Open Database License (ODbL) 1.0.
  https://www.openstreetmap.org/copyright
- **City of Toronto** open data (buildings, aerial photos, ground, trees, parcels, addresses): Contains
  information licensed under the Open Government Licence – Toronto. https://open.toronto.ca/open-data-license/
- **Natural Resources Canada** HRDEM elevation: Contains information licensed under the Open Government Licence – Canada.
  https://open.canada.ca/en/open-government-licence-canada
- **Geospatial Ontario** lidar-derived Digital Surface and Terrain Models: Contains information licensed under the
  Open Government Licence – Ontario. https://www.ontario.ca/page/open-government-licence-ontario
- **Mapillary** street photos, from which Street Look reads facade colours (no photo is stored in your file), and the
  labels Mapillary extracts from them: Street photos © Mapillary contributors, CC BY-SA 4.0,
  https://creativecommons.org/licenses/by-sa/4.0/ — https://www.mapillary.com. The six resized photos in
  `tests/fetch/fixtures/kingst/` are CC BY-SA 4.0, not GPL-3 (see that folder's README for each photo's credit).

The add-on also lists the credits for each build in its panel and stores them on the context
collection (`credits` custom property).
