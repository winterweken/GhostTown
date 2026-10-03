import gzip
import math
import urllib.parse
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import box

from ghosttown_fetch import terrain, tiff
from ghosttown_fetch.frame import Frame, lonlat_to_merc
from ghosttown_fetch.net import SourceError
from ghosttown_fetch.sources import nrcan
from fakes import FakeNet
from tiff_samples import east_slope_tiff, write_tiff

FIX = Path(__file__).parent / "fixtures"
BAY = (43.649667, -79.380991)


def _grid_terrain(frame, half=300.0):
    grid, x0, y0, dx, dy = tiff.read(east_slope_tiff(frame, half=half))
    return terrain.GridTerrain(grid, x0, y0, dx, dy, frame, 2.0)


def test_web_mercator_reference_points():
    x, y = lonlat_to_merc(0.0, 0.0)
    assert float(x) == 0.0 and float(y) == pytest.approx(0.0, abs=1e-6)
    x, _ = lonlat_to_merc(180.0, 0.0)
    assert float(x) == pytest.approx(20037508.3428, abs=1e-3)


def test_grid_terrain_is_zero_at_the_centre_and_rises_east():
    t = _grid_terrain(Frame(*BAY))
    z = t.z(np.array([0.0, 100.0, 0.0]), np.array([0.0, 0.0, 100.0]))
    assert z[0] == pytest.approx(0.0, abs=1e-9) and z[1] > 1.0 and z[2] == pytest.approx(0.0, abs=1e-6)
    assert 80.0 < t.ground_at_centre_m < 100.0 and t.source == "nrcan-dtm"


def test_min_under_finds_the_low_side_of_a_footprint():
    t = _grid_terrain(Frame(*BAY))
    low = t.min_under(box(-50, -10, 50, 10))
    assert low == pytest.approx(float(t.z(np.array([-50.0]), np.array([0.0]))[0]), abs=0.05)


def test_build_url_covers_the_site_in_web_mercator():
    url = nrcan.build_url(Frame(*BAY), 330.0, 2.0)
    assert url.startswith(nrcan.ENDPOINT + "?")
    q = dict(urllib.parse.parse_qsl(url.split("?", 1)[1]))
    assert q["IDENTIFIER"] == "dtm" and q["GRIDBASECRS"] == "urn:ogc:def:crs:EPSG::3857"
    step = 2.0 / math.cos(math.radians(BAY[0]))
    assert q["GRIDOFFSETS"] == f"{step:.3f},{-step:.3f}"
    x0, y0, x1, y1 = (float(v) for v in q["BOUNDINGBOX"].split(",")[:4])
    cx, cy = lonlat_to_merc(BAY[1], BAY[0])
    assert x0 < float(cx) < x1 and y0 < float(cy) < y1
    assert x1 - x0 == pytest.approx(660.0 / math.cos(math.radians(BAY[0])), rel=0.01)


def test_load_uses_nrcan_inside_canada():
    f = Frame(*BAY)
    net = FakeNet({"nrcan": east_slope_tiff(f, half=200.0)})
    t, note = terrain.load(net, f, 150)
    assert isinstance(t, terrain.GridTerrain) and note is None and t.cell_m == 2.0
    assert "IDENTIFIER=dtm" in net.calls[0][0] and net.calls[0][1] == "nrcan"


def test_load_skips_the_request_outside_canada():
    net = FakeNet({})
    t, note = terrain.load(net, Frame(51.50735, -0.12776), 150)
    assert t.source == "flat" and net.calls == [] and note[0] == "info" and "Canada" in note[2]


def test_load_is_flat_when_nrcan_has_no_data_here():
    net = FakeNet({"nrcan": write_tiff(np.array([[-32767.0]]), 0.0, 0.0, 1.0, 1.0)})
    t, note = terrain.load(net, Frame(*BAY), 150)
    assert t.source == "flat" and note[0] == "info" and "no elevation" in note[2]


def test_load_is_flat_with_a_warning_when_nrcan_fails():
    net = FakeNet({"nrcan": SourceError("Natural Resources Canada answered HTTP 503; try again in a minute.")})
    t, note = terrain.load(net, Frame(*BAY), 150)
    assert t.source == "flat" and note[0] == "warn" and note[2].endswith("The ground is flat.")


def test_unreadable_elevation_is_a_source_error():
    with pytest.raises(SourceError, match="couldn't be read"):
        nrcan.fetch(FakeNet({"nrcan": b"<ows:ExceptionReport/>"}), Frame(*BAY), 200.0, 2.0)


def test_a_lakefront_grid_keeps_its_land_and_fills_the_lake_low():
    f = Frame(*BAY)

    def south_half(rows, cols):
        mask = np.zeros((rows, cols), dtype=bool)
        mask[rows // 2 + 5:, :] = True
        return mask

    t, note = terrain.load(FakeNet({"nrcan": east_slope_tiff(f, half=200.0, gaps=south_half)}), f, 150)
    assert isinstance(t, terrain.GridTerrain) and note is None and not np.isnan(t.grid).any()
    lake = float(t.z(np.array([0.0]), np.array([-120.0]))[0])
    assert lake <= 0.0


def test_cell_size_grows_for_large_sites():
    assert terrain.cell_for(300) == 2.0 and terrain.cell_for(1000) == 4.0


def test_real_bay_street_ground_level():
    data = gzip.decompress((FIX / "bay" / "nrcan_dtm.tif.gz").read_bytes())
    t, note = terrain.load(FakeNet({"nrcan": data}), Frame(43.649667039, -79.380991173), 150)
    assert note is None and t.ground_at_centre_m == pytest.approx(84.73, abs=0.05)


def test_an_island_site_that_is_mostly_lake_keeps_its_land_terrain():
    f = Frame(*BAY)

    def all_but_a_strip(rows, cols):
        mask = np.ones((rows, cols), dtype=bool)
        mask[:, cols // 2 - cols // 12: cols // 2 + cols // 12] = False  # about 17 % land
        return mask

    t, note = terrain.load(FakeNet({"nrcan": east_slope_tiff(f, half=200.0, gaps=all_but_a_strip)}), f, 150)
    assert isinstance(t, terrain.GridTerrain) and note is None
    assert float(t.z(np.array([20.0]), np.array([0.0]))[0]) > 0.5


def test_a_damaged_stored_elevation_file_gives_flat_ground_not_a_failed_build():
    class StoredAnswer:  # hands back a stored answer without checking it
        def get(self, url, *, source, data=None, check=None, timeout=120):
            return b"II*\x00 truncated"

    t, note = terrain.load(StoredAnswer(), Frame(*BAY), 150)
    assert t.source == "flat" and note[0] == "warn" and note[2].endswith("The ground is flat.")
