from ghosttown import georef

POINT = {"epsg": "EPSG:2952", "name": "NAD83(CSRS) / MTM zone 10", "easting_m": 314400.285,
         "northing_m": 4834420.675, "elevation_m": 84.712, "grid_angle_deg": 0.082146}


def test_survey_lines_say_where_the_origin_sits_on_the_grid():
    assert georef.survey_lines(POINT) == [
        "NAD83(CSRS) / MTM zone 10 (EPSG:2952)",
        "Easting 314400.285 m",
        "Northing 4834420.675 m",
        "Elevation 84.712 m above sea level",
        "Grid north 0.0821° east of true north",
    ]


def test_survey_lines_for_a_west_angle_no_angle_and_an_unknown_elevation():
    lines = georef.survey_lines(dict(POINT, elevation_m=None, grid_angle_deg=-3.196986))
    assert lines[3] == "Elevation unknown (no terrain data)"
    assert lines[4] == "Grid north 3.1970° west of true north"
    assert georef.survey_lines(dict(POINT, grid_angle_deg=0.00001))[4] == "Grid north is true north"


def test_no_survey_lines_without_a_survey_point():
    assert georef.survey_lines(None) == []
