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
