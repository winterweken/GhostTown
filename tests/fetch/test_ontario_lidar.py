import numpy as np
import pytest

from ghosttown_fetch.frame import Frame, lonlat_to_merc, merc_to_lonlat
from ghosttown_fetch.net import Net, SourceError
from ghosttown_fetch.sources import ontario_lidar as lidar
from fakes import FakeNet, router
from lidar_samples import BAY_SURFACE, BAY_TERRAIN, LAKE_NONE, rasters
from tiff_samples import write_tiff
from toronto_samples import LAT0, LON0

F = Frame(LAT0, LON0)
BAY = Frame(43.649667, -79.380991)
SQUARE = (-40.0, -40.0, 40.0, 40.0)


@pytest.mark.parametrize("lat, lon, inside", [
    (43.6497, -79.3810, True), (44.2312, -76.4860, True), (42.9849, -81.2453, True),
    (45.5017, -73.5673, False), (49.8954, -97.1385, False), (51.2794, -80.6463, False),
])
def test_covers_the_services_extent(lat, lon, inside):
    assert lidar.covers(lat, lon) is inside


def test_the_roof_grid_is_half_a_metre_up_to_300_m_then_one():
    assert [lidar.cell_for(r) for r in (150, 300, 500, 1000)] == [0.5, 0.5, 1.0, 1.0]


def test_the_area_matches_the_local_bounds_with_ground_sized_pixels():
    box, size = lidar.area(F, (-150.0, -150.0, 150.0, 150.0), 0.5)
    lons, lats = merc_to_lonlat([box[0], box[2]], [box[1], box[3]])
    xs, ys = F.to_local(np.asarray(lons), np.asarray(lats))
    assert np.allclose(xs, [-150, 150], atol=0.01) and np.allclose(ys, [-150, 150], atol=0.1)
    assert all(abs(n - 600) <= 3 for n in size)  # 0.5 m pixels, give or take Mercator's half a percent


def test_export_url_asks_for_one_uncompressed_float_tiff():
    url = lidar.export_url(lidar.SURFACE, (1.0, 2.0, 3.0, 4.0), (600, 601))
    assert url.startswith(lidar.ROOT + "/Ontario_DSM_LidarDerived/ImageServer/exportImage?")
    for part in ("bbox=1.000%2C2.000%2C3.000%2C4.000", "bboxSR=3857", "imageSR=3857", "size=600%2C601",
                 "format=tiff", "pixelType=F32", "compression=None", "f=image"):
        assert part in url, part


def test_check_accepts_a_real_image_and_refuses_an_error_answer():
    lidar.check(BAY_SURFACE)
    with pytest.raises(SourceError, match="Ontario's LiDAR service sent an image Ghost Town can't read"):
        lidar.check(b'{"error":{"code":500,"message":"Error exporting image"}}')


def test_heights_are_surface_minus_terrain_and_nan_where_there_is_none():
    surface, terrain = rasters(F, tops=[(-10, -10, 10, 10, 20.0)], gaps=lambda x, y: x > 40)
    heights = lidar.Heights(lidar.tiff.read(surface), lidar.tiff.read(terrain), F)
    got = heights.sample(np.array([0.0, -30.0, 50.0, 500.0]), np.array([0.0, 0.0, 0.0, 0.0]))
    assert got[0] == pytest.approx(20.0) and got[1] == pytest.approx(0.0)
    assert np.isnan(got[2]) and np.isnan(got[3])


def test_heights_are_read_at_pixel_centres():
    step, east, north = 0.7, 0.1, 0.05  # Mercator metres a pixel; metres of height per Mercator metre
    lons, lats = F.to_lonlat(np.array([-60.0, 60.0]), np.array([-60.0, 60.0]))
    mx, my = lonlat_to_merc(lons, lats)
    cols, rows = int((mx[1] - mx[0]) / step), int((my[1] - my[0]) / step)
    cx = mx[0] + (np.arange(cols) + 0.5) * step  # a pixel's value belongs to its centre
    cy = my[1] - (np.arange(rows) + 0.5) * step
    ramp = east * (cx[None, :] - mx[0]) + north * (cy[:, None] - my[0])  # height above the flat terrain
    corner = (float(mx[0]), float(my[1]), step, step)
    surface = write_tiff(ramp, *corner, tile=64, nodata=None)
    terrain = write_tiff(np.zeros_like(ramp), *corner, tile=64, nodata=None)
    heights = lidar.Heights(lidar.tiff.read(surface), lidar.tiff.read(terrain), F)
    xs, ys = np.array([0.0, 17.3, -23.9, 41.2]), np.array([0.0, -31.4, 12.6, 8.8])
    px, py = lonlat_to_merc(*F.to_lonlat(xs, ys))
    expected = east * (px - mx[0]) + north * (py - my[0])
    assert np.allclose(heights.sample(xs, ys), expected, atol=0.001)  # half a pixel off would be 35 mm


def test_real_heights_at_320_bay_street_match_the_citys_tower():
    heights = lidar.Heights(lidar.tiff.read(BAY_SURFACE), lidar.tiff.read(BAY_TERRAIN), BAY)
    at_address = heights.sample(np.array([0.0, 2.0, -2.0]), np.array([0.0, 2.0, -2.0]))
    assert np.all((at_address > 60) & (at_address < 80))  # the City says 73.8 m
    assert np.isfinite(heights.grid).all()


def test_fetch_asks_for_the_surface_then_the_terrain_with_a_long_wait():
    surface, terrain = rasters(F, tops=[(-10, -10, 10, 10, 20.0)])
    net = FakeNet({"ontario": router({"Ontario_DSM_LidarDerived": surface, "Ontario_DTM_LidarDerived": terrain})})
    heights = lidar.fetch(net, F, SQUARE, 0.5)
    assert heights.sample(np.array([0.0]), np.array([0.0]))[0] == pytest.approx(20.0)
    assert [lidar.SURFACE in url for url, _, _ in net.calls] == [True, False]
    assert {source for _, source, _ in net.calls} == {"ontario"} and net.timeouts == [240, 240]


def test_outside_the_surveys_there_is_no_lidar_and_no_terrain_request():
    net = FakeNet({"ontario": router({"Ontario_DSM_LidarDerived": LAKE_NONE})})
    with pytest.raises(lidar.NoLidar, match="Ontario has no LiDAR here."):
        lidar.fetch(net, F, SQUARE, 0.5)
    assert len(net.calls) == 1


class Transport:
    """Stands in for the network under a real Net: answers each request with the next body as HTTP 200."""

    def __init__(self, *bodies):
        self.bodies = list(bodies)
        self.calls = []

    def __call__(self, url, data, headers, timeout):
        self.calls.append(url)
        return 200, self.bodies.pop(0)


def test_an_empty_answer_is_never_stored_so_a_later_build_asks_again(tmp_path):
    transport = Transport(LAKE_NONE, LAKE_NONE)
    net = Net(str(tmp_path), transport=transport)
    for _ in range(2):
        with pytest.raises(lidar.NoLidar, match="Ontario has no LiDAR here."):
            lidar.fetch(net, F, SQUARE, 0.5)
    assert len(transport.calls) == 2 and all(lidar.SURFACE in url for url in transport.calls)
    assert not list((tmp_path / "ontario").glob("*"))


def test_an_empty_answer_stored_by_an_older_version_is_fetched_again(tmp_path):
    surface, terrain = rasters(F, tops=[(-10, -10, 10, 10, 20.0)])
    transport = Transport(surface, terrain)
    net = Net(str(tmp_path), transport=transport)
    net.cache.write("ontario", lidar.export_url(lidar.SURFACE, *lidar.area(F, SQUARE, 0.5)), LAKE_NONE)
    heights = lidar.fetch(net, F, SQUARE, 0.5)
    assert heights.sample(np.array([0.0]), np.array([0.0]))[0] == pytest.approx(20.0)
    assert [lidar.SURFACE in url for url in transport.calls] == [True, False]


def test_a_failing_service_is_a_source_error():
    net = FakeNet({"ontario": SourceError("Geospatial Ontario answered HTTP 503; try again in a minute.")})
    with pytest.raises(SourceError, match="HTTP 503"):
        lidar.fetch(net, F, SQUARE, 0.5)


def test_images_that_dont_line_up_are_refused():
    small, _ = rasters(F, half=30.0)
    _, big = rasters(F, half=60.0)
    with pytest.raises(SourceError, match="don't line up"):
        lidar.Heights(lidar.tiff.read(small), lidar.tiff.read(big), F)
