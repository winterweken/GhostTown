import gzip
import math
import urllib.parse
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import box

from ghosttown_fetch import terrain, tiff
from ghosttown_fetch.frame import Frame, lonlat_to_merc
from ghosttown_fetch.net import Net, SourceError, Unreadable
from ghosttown_fetch.sources import nrcan
from fakes import FakeNet, Transport
from tiff_samples import east_slope_tiff, nrcan_server, write_tiff

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


def _plane(frame):
    """Heights on a tilted plane through 85 m at the site centre, as a function of Web Mercator metres."""
    cx, cy = (float(v) for v in lonlat_to_merc(frame.lon0, frame.lat0))
    return lambda mx, my: 85.0 + 0.01 * (mx - cx) + 0.02 * (my - cy)


def _centres(grid, x0, y0, dx, dy):
    """Web Mercator centres of a grid's pixels as (columns' x, rows' y)."""
    return x0 + dx * (np.arange(grid.shape[1]) + 0.5), y0 - dy * (np.arange(grid.shape[0]) + 0.5)


def test_the_requests_cover_the_site_in_web_mercator():
    net = FakeNet({"nrcan": nrcan_server(_plane(Frame(*BAY)))})
    nrcan.fetch(net, Frame(*BAY), 330.0, 2.0)
    step = 2.0 / math.cos(math.radians(BAY[0]))
    boxes = []
    for url, _source, _data in net.calls:
        assert url.startswith(nrcan.ENDPOINT + "?")
        q = dict(urllib.parse.parse_qsl(url.split("?", 1)[1]))
        assert q["IDENTIFIER"] == "dtm" and q["GRIDBASECRS"] == "urn:ogc:def:crs:EPSG::3857"
        assert q["GRIDOFFSETS"] == f"{step:.3f},{-step:.3f}"
        boxes.append([float(v) for v in q["BOUNDINGBOX"].split(",")[:4]])
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    cx, cy = lonlat_to_merc(BAY[1], BAY[0])
    assert x0 < float(cx) < x1 and y0 < float(cy) < y1
    assert x1 - x0 == pytest.approx(660.0 / math.cos(math.radians(BAY[0])), rel=0.01)


def test_a_small_site_takes_one_request():
    net = FakeNet({"nrcan": nrcan_server(_plane(Frame(*BAY)))})
    nrcan.fetch(net, Frame(*BAY), 180.0, 2.0)
    assert len(net.calls) == 1


@pytest.mark.parametrize("radius", [300, 1000])
def test_a_site_bigger_than_one_tile_comes_in_pieces_joined_without_seams(radius):
    # NRCan answers `null` for a coverage bigger than one 256-pixel tile; a 300 m site is 331 pixels across
    f = Frame(*BAY)
    height = _plane(f)
    t, note = terrain.load(FakeNet({"nrcan": nrcan_server(height)}), f, radius)
    assert isinstance(t, terrain.GridTerrain) and note is None
    xs, ys = _centres(t.grid, t.x0, t.y0, t.dx, t.dy)
    np.testing.assert_allclose(t.grid, height(xs[None, :], ys[:, None]), atol=1e-3)
    half = radius + terrain.MARGIN_M
    lons, lats = f.to_lonlat(np.array([-half, half]), np.array([-half, half]))
    sx, sy = lonlat_to_merc(lons, lats)
    assert t.x0 <= sx[0] and xs[-1] >= sx[1] and ys[-1] <= sy[0] and t.y0 >= sy[1]


def test_a_piece_nrcan_has_no_data_for_leaves_a_gap_in_the_joined_grid():
    f = Frame(*BAY)
    height = _plane(f)
    cx, _ = lonlat_to_merc(f.lon0, f.lat0)
    placeholder = gzip.decompress((FIX / "london" / "nrcan_dtm.tif.gz").read_bytes())  # NRCan's 1×1 "no data"
    server = nrcan_server(height)

    def answer(url, data):
        east = float(dict(urllib.parse.parse_qsl(url.split("?", 1)[1]))["BOUNDINGBOX"].split(",")[2])
        return placeholder if east < float(cx) + 10.0 else server(url, data)  # nothing west of the centre

    grid, x0, y0, dx, dy = nrcan.fetch(FakeNet({"nrcan": answer}), f, 330.0, 2.0)
    xs, ys = _centres(grid, x0, y0, dx, dy)
    west, east = xs < float(cx) - 10.0, xs > float(cx) + 10.0
    assert np.isnan(grid[:, west]).all()
    np.testing.assert_allclose(grid[:, east], height(xs[None, east], ys[:, None]), atol=1e-3)


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


@pytest.mark.parametrize("radius", [150, 300])
def test_load_is_flat_when_nrcan_has_no_data_here(radius):
    net = FakeNet({"nrcan": write_tiff(np.array([[-32767.0]]), 0.0, 0.0, 1.0, 1.0)})
    t, note = terrain.load(net, Frame(*BAY), radius)
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


def test_pieces_that_dont_line_up_give_flat_ground_with_a_warning():
    f = Frame(*BAY)
    server, calls = nrcan_server(_plane(f)), []

    def answer(url, data):
        calls.append(url)
        if len(calls) == 2:  # one piece comes back five pixels east of where it was asked for
            q = dict(urllib.parse.parse_qsl(url.split("?", 1)[1]))
            x0, y0, x1, y1 = (float(v) for v in q["BOUNDINGBOX"].split(",")[:4])
            step = float(q["GRIDOFFSETS"].split(",")[0])
            url = nrcan.build_url((x0 + 5 * step, y0, x1 + 5 * step, y1), step)
        return server(url, data)

    t, note = terrain.load(FakeNet({"nrcan": answer}), f, 300)
    assert t.source == "flat" and note[0] == "warn" and "line up" in note[2]


def test_an_unreadable_nrcan_answer_asks_once_more_and_is_never_stored(tmp_path):
    f = Frame(*BAY)
    good = nrcan_server(_plane(f))
    url = nrcan.pieces(f, 180.0, 2.0)[3][0][2]
    tif = good(url, None)
    net = Net(str(tmp_path), transport=Transport((200, b"null"), (200, tif)), sleep=lambda s: None)
    t, note = terrain.load(net, f, 150)
    assert t.source == "nrcan-dtm" and note is None
    assert [p.read_bytes() for p in (tmp_path / "nrcan").iterdir()] == [tif]


def test_two_unreadable_nrcan_answers_give_flat_ground_and_store_nothing(tmp_path):
    net = Net(str(tmp_path), transport=Transport((200, b"null"), (200, b"null")), sleep=lambda s: None)
    t, note = terrain.load(net, Frame(*BAY), 150)
    assert t.source == "flat" and note == ("warn", "terrain", "Natural Resources Canada sent elevation data that "
                                           "couldn't be read (This isn't a TIFF file.) The ground is flat.")
    assert not (tmp_path / "nrcan").exists()


@pytest.mark.parametrize("body", [b"null", b"<html><body>502 Bad Gateway</body></html>", b"MM\x00*\x00\x00\x00\x08cut"])
def test_nrcan_answers_that_cant_be_read_are_worth_asking_for_again(body):
    with pytest.raises(Unreadable):
        nrcan.check(body)
