import numpy as np
import pytest
import shapely

from ghosttown_fetch import DEFAULT_LAYERS
from ghosttown_fetch import context as ctx
from ghosttown_fetch import lidar_roofs
from ghosttown_fetch.assemble import CITY_MODEL_ONLY, LIDAR_STAGE, assemble
from ghosttown_fetch.frame import Frame
from ghosttown_fetch.net import SourceError
from ghosttown_fetch.sources import ontario_lidar
from fakes import FakeNet, router
from lidar_samples import LAKE_NONE, rasters
from test_assemble import FAR, OSM, TIER, _city, _req
from test_assemble_massing import _massing
from tiff_samples import east_slope_tiff
from toronto_samples import LAT0, LON0, page, square

F = Frame(LAT0, LON0)
WITH_LIDAR = list(DEFAULT_LAYERS) + ["lidar"]
FLAT_ROOFS = "The buildings keep flat roofs."


def _lidar(**kw):
    surface, terrain = rasters(F, half=80.0, **kw)
    return router({"Ontario_DSM_LidarDerived": surface, "Ontario_DTM_LidarDerived": terrain})


def _net(ontario, toronto=None):
    return FakeNet({"toronto": toronto or _city(), "nrcan": east_slope_tiff(F, half=200.0), "osm": OSM,
                    "ontario": ontario})


def _notes(doc, level):
    return [n["text"] for n in doc["notes"] if n["code"] == "lidar" and n["level"] == level]


def test_city_outlines_get_lidar_roofs_beside_the_context(tmp_path):
    # _city() has the 3D Massing model down, so the buildings are the City's older outlines.
    doc = assemble(_req(tmp_path, layers=WITH_LIDAR), _net(_lidar(tops=[(0, 0, 10, 10, 22.0)])))
    block = doc["lidar"]
    assert (block["file"], block["cell_m"], block["source"], block["year"]) == ("lidar_roofs.npz", 0.5, "ontario", None)
    assert block["kinds"] == ["building", "building_on_site", "building_guessed"]
    with np.load(tmp_path / "o" / "lidar_roofs.npz") as data:
        assert list(data["building_ids"]) == ["toronto:building:7"]
        assert block["buildings"] == 1 and block["triangles"] == len(data["faces"])
    assert "ontario" in {s["key"] for s in doc["sources"]} and ctx.validate(doc) == []
    assert _notes(doc, "info") and not _notes(doc, "warn")
    assert "newer" not in " ".join(_notes(doc, "info"))  # a roof the survey did see needs no second sentence


def test_a_building_over_bare_ground_is_newer_than_the_survey_and_the_note_says_so(tmp_path):
    doc = assemble(_req(tmp_path, layers=WITH_LIDAR), _net(_lidar()))  # the survey saw only ground there
    assert doc["lidar"]["buildings"] == 1 and (tmp_path / "o" / "lidar_roofs.npz").exists() and ctx.validate(doc) == []
    info, = _notes(doc, "info")
    assert info.startswith("LiDAR roofs: Geospatial Ontario, 1 buildings, 12 triangles. ")
    assert info.endswith(" 1 building part is newer than the LiDAR survey and keeps a flat top.")


def test_the_note_counts_the_building_parts_newer_than_the_survey(tmp_path):
    second = square(30, 0, 10, BUILDINGID=8, OBJECTID=11, DERIVED_HEIGHT=20.0, SUBTYPE_DESC="Building Outline")
    toronto = _city(**{"BUILDINGID IN": page(TIER, second), "cot_geospatial3/FeatureServer/2/": page(TIER, second)})
    doc = assemble(_req(tmp_path, layers=WITH_LIDAR), _net(_lidar(), toronto=toronto))
    assert doc["lidar"]["buildings"] == 2
    info, = _notes(doc, "info")
    assert info.endswith(" 2 building parts are newer than the LiDAR survey and keep flat tops.")


def test_osm_buildings_in_ontario_get_lidar_roofs_too(tmp_path):
    net = _net(_lidar(tops=[(0, 0, 10, 10, 22.0)]), toronto=_city(**{"FeatureServer/40/": page(FAR)}))
    doc = assemble(_req(tmp_path, layers=WITH_LIDAR), net)
    assert doc["region"] == "world" and doc["lidar"]["buildings"] == 1


def test_no_lidar_request_unless_asked(tmp_path):
    net = _net(AssertionError("LiDAR asked for"))
    doc = assemble(_req(tmp_path), net)
    assert "lidar" not in doc and all(source != "ontario" for _, source, _ in net.calls)


def test_outside_ontario_there_is_no_request_and_a_note_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(ontario_lidar, "covers", lambda lat, lon: False)
    net = _net(AssertionError("LiDAR asked for"))
    doc = assemble(_req(tmp_path, layers=WITH_LIDAR), net)
    assert "lidar" not in doc and all(source != "ontario" for _, source, _ in net.calls)
    assert _notes(doc, "info") == [f"LiDAR roofs are available in Ontario only. {FLAT_ROOFS}"]


def test_a_failing_service_is_a_warning_and_the_build_goes_on(tmp_path):
    down = SourceError("Geospatial Ontario couldn't be reached (timed out); try again in a minute.")
    doc = assemble(_req(tmp_path, layers=WITH_LIDAR), _net(down))
    assert "lidar" not in doc and "toronto:building:7" in {e["id"] for e in doc["elements"]}
    assert _notes(doc, "warn") == [f"{down} {FLAT_ROOFS}"] and not (tmp_path / "o" / "lidar_roofs.npz").exists()


def test_a_site_outside_the_surveys_has_no_lidar(tmp_path):
    doc = assemble(_req(tmp_path, layers=WITH_LIDAR), _net(router({"Ontario_DSM_LidarDerived": LAKE_NONE})))
    assert "lidar" not in doc and _notes(doc, "info") == [f"Ontario has no LiDAR here. {FLAT_ROOFS}"]


def test_too_little_lidar_under_the_buildings_counts_as_none(tmp_path):
    doc = assemble(_req(tmp_path, layers=WITH_LIDAR), _net(_lidar(gaps=lambda x, y: (x > -20) & (x < 20))))
    assert "lidar" not in doc and _notes(doc, "info") == [f"Ontario has no LiDAR here. {FLAT_ROOFS}"]


def test_a_geometry_error_in_the_coverage_check_is_a_warning_and_the_build_goes_on(tmp_path, monkeypatch):
    def boom(*args, **kw):
        raise shapely.errors.GEOSException("boom")

    monkeypatch.setattr(lidar_roofs, "coverage", boom)
    doc = assemble(_req(tmp_path, layers=WITH_LIDAR), _net(_lidar(tops=[(0, 0, 10, 10, 22.0)])))
    assert "lidar" not in doc and "toronto:building:7" in {e["id"] for e in doc["elements"]}
    assert _notes(doc, "warn") == [f"The LiDAR roofs couldn't be built (boom). {FLAT_ROOFS}"]
    assert not (tmp_path / "o" / "lidar_roofs.npz").exists()


def test_the_progress_line_warns_the_first_request_is_slow(tmp_path):
    stages = []
    assemble(_req(tmp_path, layers=WITH_LIDAR), _net(_lidar()), progress=lambda stage, pct: stages.append((stage, pct)))
    assert (LIDAR_STAGE, 77) in stages and LIDAR_STAGE == "LiDAR (the first request can take a minute)"


def test_buildings_from_the_city_model_fetch_no_lidar(tmp_path):
    net = _net(AssertionError("LiDAR asked for"), toronto=_massing())
    doc = assemble(_req(tmp_path, layers=WITH_LIDAR), net)
    assert "lidar" not in doc and all(source != "ontario" for _, source, _ in net.calls)
    assert _notes(doc, "info") == [CITY_MODEL_ONLY]
