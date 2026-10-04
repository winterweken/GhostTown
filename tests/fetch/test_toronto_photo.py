import math

import pytest

from ghosttown_fetch.frame import Frame, lonlat_to_merc
from ghosttown_fetch.net import SourceError
from ghosttown_fetch.sources import toronto_photo as photo
from fakes import FakeNet, router
from photo_samples import ANSWERS, JPEG, LISTING, listing

BAY = Frame(43.649667, -79.380991)


def test_newest_yearly_photo_is_chosen():
    net = FakeNet({"toronto": LISTING})
    assert photo.newest(net) == ("basemap/cot_ortho_2025_color_8cm", 2025)
    assert net.calls[0][0] == photo.LISTING


@pytest.mark.parametrize("answer", [
    listing("basemap/cot_topo"),
    SourceError("City of Toronto answered HTTP 503; try again in a minute."),
    b"<html>busy</html>",
])
def test_without_a_yearly_photo_the_current_year_service_is_used(answer):
    assert photo.newest(FakeNet({"toronto": answer})) == ("basemap/cot_ortho", None)


@pytest.mark.parametrize("radius, px", [(50, 1250), (150, 3750), (300, 4096), (500, 4096), (1000, 4096)])
def test_size_follows_the_radius_up_to_4096(radius, px):
    assert photo.size_px(radius) == px


@pytest.mark.parametrize("radius", [150, 1000])
def test_area_is_the_site_square_in_mercator_and_back(radius):
    box, bounds = photo.area(BAY, radius)
    assert bounds == pytest.approx([-radius, -radius, radius, radius], abs=0.002)
    k = 1 / math.cos(math.radians(BAY.lat0))
    assert box[2] - box[0] == pytest.approx(2 * radius * k, rel=0.005)
    assert box[3] - box[1] == pytest.approx(2 * radius * k, rel=0.005)


def test_a_straight_mapping_across_the_photo_stays_within_10_cm_at_1000_m():
    box, bounds = photo.area(BAY, 1000)
    for y in (-700.0, -250.0, 0.0, 400.0, 900.0):
        lon, lat = BAY.to_lonlat(0.0, y)
        _, my = lonlat_to_merc(lon, lat)
        v = (float(my) - box[1]) / (box[3] - box[1])        # where the pixel row sits in the photo
        mapped = bounds[1] + v * (bounds[3] - bounds[1])     # what Blender's UV map assumes
        assert abs(mapped - y) < 0.10


def test_check_accepts_a_real_photo_and_rejects_errors():
    photo.check(JPEG)
    for bad in (b'{"error": {"code": 400}}' * 60, b"<html>" + b"x" * 2000, JPEG[: len(JPEG) // 2], JPEG[:500]):
        with pytest.raises(SourceError, match="whole JPEG"):
            photo.check(bad)


def test_fetch_writes_the_photo_and_returns_its_block(tmp_path):
    net = FakeNet({"toronto": router(ANSWERS)})
    block = photo.fetch(net, BAY, 150, str(tmp_path / "run"))
    assert (tmp_path / "run" / "photo.jpg").read_bytes() == JPEG
    assert block == {"file": "photo.jpg", "year": 2025, "width_px": 3750, "height_px": 3750,
                     "bounds_m": pytest.approx([-150, -150, 150, 150], abs=0.002), "source": "toronto"}
    url = net.calls[1][0]
    assert "/basemap/cot_ortho_2025_color_8cm/MapServer/export?" in url
    assert "size=3750%2C3750" in url and "format=jpg" in url and "f=image" in url and "bboxSR=3857" in url


def test_a_failed_photo_raises_and_writes_nothing(tmp_path):
    net = FakeNet({"toronto": router({**ANSWERS, "/MapServer/export?": b'{"error":{"code":500}}' * 50})})
    with pytest.raises(SourceError):
        photo.fetch(net, BAY, 150, str(tmp_path))
    assert not (tmp_path / "photo.jpg").exists()
