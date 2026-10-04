import pytest

from ghosttown_fetch import survey

# Expected values from pyproj 3.7 (PROJ), always_xy: MTM from NAD83(CSRS) EPSG:4617 and UTM from WGS 84
# EPSG:4326, so both are the plain projection with no datum shift (Ghost Town takes latitude and longitude
# as given). Convergence is pyproj's meridian_convergence (+ means grid north lies east of true north).
CASES = [
    ("Toronto City Hall", 43.653482, -79.383935, 2952, 314162.2040, 4834844.1634, 0.0801192),
    ("320 Bay St", 43.649667, -79.380991, 2952, 314400.2849, 4834420.6747, 0.0821457),
    ("Etobicoke, west of the meridian", 43.62, -79.62, 2952, 295115.0092, 4831124.9636, -0.0827847),
    ("1.5 degrees off the meridian", 43.80, -78.00, 2952, 425501.2212, 4852208.8491, 1.0383396),
    ("Toronto in UTM 17N", 43.653482, -79.383935, 32617, 630319.1140, 4834655.8661, 1.1157185),
    ("Sydney, UTM 56S", -33.8688, 151.2093, 32756, 334368.6336, 6250948.3454, 0.9981719),
    ("Bergen, UTM 32V", 60.39299, 5.32415, 32632, 297477.3070, 6700830.0632, -3.1969861),
    ("Longyearbyen, UTM 33X", 78.2232, 15.6267, 32633, 514278.7151, 8683355.4695, 0.6135091),
    ("Quito, UTM 17S", -0.1807, -78.4678, 32717, 781861.4575, 9980007.5669, -0.0079914),
]


def _grid(epsg, lat, lon):
    return survey.MTM10 if epsg == 2952 else survey.utm(lat, lon)


@pytest.mark.parametrize("name, lat, lon, epsg, e, n, gamma", CASES, ids=[c[0] for c in CASES])
def test_projection_matches_proj_to_a_millimetre(name, lat, lon, epsg, e, n, gamma):
    grid = _grid(epsg, lat, lon)
    assert grid.epsg == epsg
    easting, northing, angle = survey.project(grid, lat, lon)
    assert easting == pytest.approx(e, abs=0.001) and northing == pytest.approx(n, abs=0.001)
    assert angle == pytest.approx(gamma, abs=1e-5)


@pytest.mark.parametrize("lat, lon, epsg", [
    (43.65, -79.38, 32617), (60.39, 5.32, 32632), (60.39, 2.9, 32631), (78.22, 15.63, 32633),
    (78.22, 8.9, 32631), (-33.87, 151.21, 32756), (-0.18, -78.47, 32717), (10.0, 180.0, 32660),
])
def test_utm_zone_follows_the_standard_including_norway_and_svalbard(lat, lon, epsg):
    assert survey.utm(lat, lon).epsg == epsg


def test_toronto_uses_the_city_grid_and_elsewhere_the_utm_zone():
    assert survey.grid_for("toronto", 43.65, -79.38).epsg == 2952
    assert survey.grid_for("world", 43.65, -79.38).epsg == 32617
    assert survey.MTM10.name == "NAD83(CSRS) / MTM zone 10"
    assert survey.utm(-33.87, 151.21).name == "WGS 84 / UTM zone 56S"


def test_survey_point_is_rounded_and_keeps_an_unknown_elevation_empty():
    p = survey.survey_point("toronto", 43.649667, -79.380991, 84.71234)
    assert p == {"epsg": "EPSG:2952", "name": "NAD83(CSRS) / MTM zone 10", "easting_m": 314400.285,
                 "northing_m": 4834420.675, "elevation_m": 84.712, "grid_angle_deg": 0.082146}
    assert survey.survey_point("world", 51.5007, -0.1246, None)["elevation_m"] is None
