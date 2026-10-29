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


def test_survey_from_reads_the_stored_properties_back():
    block = {"survey_epsg": "EPSG:2952", "survey_name": "NAD83(CSRS) / MTM zone 10", "survey_easting_m": 314400.285,
             "survey_northing_m": 4834420.675, "survey_elevation_m": 84.712, "survey_grid_angle_deg": 0.082146}
    assert georef.survey_from(block) == POINT
    del block["survey_elevation_m"]
    assert georef.survey_from(block)["elevation_m"] is None
    assert georef.survey_from({"lat": 43.65}) is None


def test_survey_from_needs_all_five_required_properties():
    block = {"survey_epsg": "EPSG:2952", "survey_name": "NAD83(CSRS) / MTM zone 10", "survey_easting_m": 314400.285,
             "survey_northing_m": 4834420.675, "survey_grid_angle_deg": 0.082146}
    assert georef.survey_from(block)["elevation_m"] is None
    for missing in ("survey_epsg", "survey_name", "survey_easting_m", "survey_northing_m", "survey_grid_angle_deg"):
        partial = {k: v for k, v in block.items() if k != missing}
        assert georef.survey_from(partial) is None, missing


def test_set_scene_georef_from_doc():
    scene = {}
    doc = {
        "centre": {"lat": 43.649667, "lon": -79.380991},
        "survey": POINT,
    }
    georef.set_scene_georef(scene, doc)
    assert "+proj=tmerc" in scene["SRID"]
    assert "+lat_0=43.64966700" in scene["SRID"]
    assert "+lon_0=-79.38099100" in scene["SRID"]
    assert abs(scene["latitude"] - 43.649667) < 1e-6
    assert abs(scene["longitude"] - (-79.380991)) < 1e-6
    assert scene["crs x"] == 0.0
    assert scene["crs y"] == 0.0
    assert scene["scale"] == 1
    assert scene["survey_epsg"] == "EPSG:2952"
    assert scene["survey_name"] == "NAD83(CSRS) / MTM zone 10"
    assert scene["survey_easting_m"] == 314400.285
    assert scene["survey_northing_m"] == 4834420.675
    assert scene["survey_elevation_m"] == 84.712
    assert scene["survey_grid_angle_deg"] == 0.082146
    assert "_RNA_UI" in scene
    assert "SRID" in scene["_RNA_UI"]


def test_set_scene_georef_from_collection_block():
    scene = {}
    block = {
        "lat": 42.267,
        "lon": -82.928,
        "survey_epsg": "EPSG:26917",
        "survey_name": "NAD83 / UTM zone 17N",
        "survey_easting_m": 341000.0,
        "survey_northing_m": 4681000.0,
        "survey_grid_angle_deg": -1.1,
    }
    georef.set_scene_georef(scene, block)
    assert "+proj=tmerc" in scene["SRID"]
    assert "+lat_0=42.26700000" in scene["SRID"]
    assert "+lon_0=-82.92800000" in scene["SRID"]
    assert abs(scene["latitude"] - 42.267) < 1e-6
    assert abs(scene["longitude"] - (-82.928)) < 1e-6
    assert scene["crs x"] == 0.0
    assert scene["crs y"] == 0.0
    assert scene["survey_epsg"] == "EPSG:26917"
    assert scene["survey_grid_angle_deg"] == -1.1


def test_set_scene_georef_clears_stale_survey_elevation_and_survey_props():
    scene = {}
    doc1 = {
        "centre": {"lat": 43.649667, "lon": -79.380991},
        "survey": POINT,
    }
    georef.set_scene_georef(scene, doc1)
    assert scene["survey_elevation_m"] == 84.712
    assert scene["survey_easting_m"] == 314400.285

    # Switch to site with survey that has unknown elevation (None)
    point_without_elev = dict(POINT)
    point_without_elev["elevation_m"] = None
    doc2 = {
        "centre": {"lat": 43.65, "lon": -79.38},
        "survey": point_without_elev,
    }
    georef.set_scene_georef(scene, doc2)
    assert "survey_elevation_m" not in scene
    assert scene["survey_easting_m"] == 314400.285

    # Switch to site without survey at all
    doc3 = {
        "centre": {"lat": 43.65, "lon": -79.38},
    }
    georef.set_scene_georef(scene, doc3)
    assert "survey_easting_m" not in scene
    assert "survey_epsg" not in scene
    assert "survey_elevation_m" not in scene


def test_set_scene_georef_handles_invalid_target_or_doc():
    georef.set_scene_georef(None, {})
    scene = {}
    georef.set_scene_georef(scene, None)
    assert "SRID" not in scene

