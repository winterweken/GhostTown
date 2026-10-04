import io
import json
import os
import struct
import zipfile
from pathlib import Path

import pytest
from shapely.geometry import Point

from ghosttown_fetch.frame import Frame
from ghosttown_fetch.net import SourceError
from ghosttown_fetch.sources import toronto_massing as massing
from fakes import FakeNet, router
from shapefile_samples import part, square, zipped

F = Frame(43.65, -79.38)


def package(*years):
    """A CKAN package_show answer listing these shapefile editions (and a multipatch to ignore)."""
    resources = [{"name": f"3DMassingShapefile_{y}_WGS84.zip", "size": 81415175,
                  "url": f"https://portal.example/download/3DMassingShapefile_{y}_WGS84.zip"} for y in years]
    resources.append({"name": "3DMassingMultipatch_2099_WGS84.zip", "url": "https://portal.example/m.zip"})
    return json.dumps({"success": True, "result": {"resources": resources}}).encode("utf-8")


ZIP = zipped([part(square(0, 0, 10), 20.0), part(square(2000, 0, 10), 30.0), part(square(40, 0, 10), 0.3)])


def net_for(zip_bytes=ZIP, years=(2024, 2099)):
    return FakeNet({"toronto": router({"package_show?id=3d-massing": package(*years), "3DMassingShapefile_": zip_bytes})})


def test_the_newest_shapefile_edition_is_chosen():
    edition = massing.newest_edition(net_for())
    assert edition == massing.Edition(2099, "https://portal.example/download/3DMassingShapefile_2099_WGS84.zip", 81415175)


@pytest.mark.parametrize("answer", [b"<html>", json.dumps({"success": False}).encode(),
                                    json.dumps({"success": True, "result": {"resources": []}}).encode()])
def test_no_edition_is_a_source_error(answer):
    with pytest.raises(SourceError):
        massing.newest_edition(FakeNet({"toronto": answer}))


def test_odd_entries_in_the_listing_are_skipped_not_fatal():
    good = {"name": "3DMassingShapefile_2099_WGS84.zip", "url": "https://portal.example/z.zip", "size": "about 80 MB"}
    answer = json.dumps({"success": True, "result": {"resources": ["not a resource", None, good]}}).encode()
    assert massing.newest_edition(FakeNet({"toronto": answer})) == massing.Edition(2099, "https://portal.example/z.zip", 0)


def test_first_use_downloads_unpacks_and_indexes_then_reuses_the_copy(tmp_path):
    net = net_for()
    seen = []
    folder = massing.local_copy(net, str(tmp_path), massing.newest_edition(net), progress=lambda s, p: seen.append((s, p)))
    assert folder == str(tmp_path / "toronto_massing" / "2099")
    assert sorted(os.listdir(folder)) == ["massing.dbf", "massing.npy", "massing.prj", "massing.shp", "massing.shx"]
    assert net.keeps[-1] is False and seen == [("City massing model (first time: downloading 81 MB)", 30)]
    before = len(net.calls)
    assert massing.local_copy(net, str(tmp_path), massing.newest_edition(net)) == folder
    assert not any("3DMassingShapefile_" in url for url, _, _ in net.calls[before:])


def test_a_newer_edition_replaces_the_old_copy(tmp_path):
    old = massing.local_copy(net_for(), str(tmp_path), massing.Edition(2098, "https://portal.example/3DMassingShapefile_2098_WGS84.zip", 0))
    new = massing.local_copy(net_for(), str(tmp_path), massing.Edition(2099, "https://portal.example/3DMassingShapefile_2099_WGS84.zip", 0))
    assert not os.path.exists(old) and os.path.isdir(new)


def test_site_parts_come_in_local_metres_with_heights_and_sources(tmp_path):
    net = net_for()
    parts = massing.site_parts(massing.local_copy(net, str(tmp_path), massing.newest_edition(net)), F, 300)
    assert [p.record for p in parts] == [0]  # the 2 km part is outside; the 0.3 m part is dropped
    p = parts[0]
    assert p.height == pytest.approx(20.0) and p.base == 0.0 and p.source == "toronto_massing_lidar"
    poly, = p.polygons
    assert poly.bounds == pytest.approx((0, 0, 10, 10), abs=0.01) and poly.area == pytest.approx(100, rel=1e-3)


def test_fetch_returns_the_parts_and_the_edition_year(tmp_path):
    parts, year = massing.fetch(net_for(), str(tmp_path), F, 300)
    assert year == 2099 and [p.record for p in parts] == [0]


def test_a_damaged_download_is_a_source_error_and_leaves_nothing_behind(tmp_path):
    with pytest.raises(SourceError, match="zip"):
        massing.fetch(net_for(zip_bytes=b"PK\x03\x04 truncated"), str(tmp_path), F, 300)
    assert not (tmp_path / "toronto_massing" / "2099").exists()


def test_a_zip_without_the_shapefile_is_refused(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("readme.txt", b"no shapes here")
    with pytest.raises(SourceError, match="missing"):
        massing.fetch(net_for(zip_bytes=buffer.getvalue()), str(tmp_path), F, 300)


def test_an_unreadable_copy_is_deleted_and_fetched_again(tmp_path):
    net = net_for()
    folder = massing.local_copy(net, str(tmp_path), massing.newest_edition(net))
    with open(os.path.join(folder, "massing.npy"), "wb") as f:
        f.write(b"not an index")
    with pytest.raises(SourceError):
        massing.fetch(net, str(tmp_path), F, 300)
    assert not os.path.exists(folder)
    parts, _ = massing.fetch(net, str(tmp_path), F, 300)
    assert [p.record for p in parts] == [0]


def test_a_damaged_part_is_repaired_or_skipped_not_fatal(tmp_path):
    bow_tie = part([(0, 0), (10, 10), (10, 0), (0, 10)], 9.0)  # a self-intersecting footprint
    good = part(square(50, 0, 10), 12.0)
    parts, _ = massing.fetch(net_for(zip_bytes=zipped([bow_tie, good])), str(tmp_path), F, 300)
    assert 1 in [p.record for p in parts] and all(poly.is_valid for p in parts for poly in p.polygons)


def test_a_corrupt_member_that_passes_the_zip_check_falls_back_cleanly(tmp_path):
    data = zipped([part(square(7 * i, 3 * (i % 5), 5 + i % 4), 10.0 + i) for i in range(60)])
    z = zipfile.ZipFile(io.BytesIO(data))
    info = next(i for i in z.infolist() if i.filename.endswith(".shp"))
    name_len, extra_len = struct.unpack_from("<HH", data, info.header_offset + 26)
    start = info.header_offset + 30 + name_len + extra_len
    assert info.compress_size > 200  # long enough to damage well inside the stream
    middle = start + info.compress_size // 2
    damaged = data[:middle] + b"\xff" * 16 + data[middle + 16:]
    massing._check_zip(damaged)  # the directory is intact, so the download check passes
    with pytest.raises(SourceError):
        massing.fetch(net_for(zip_bytes=damaged), str(tmp_path), F, 300)
    root = tmp_path / "toronto_massing"
    assert not root.exists() or os.listdir(root) == []


SUBSET = (Path(__file__).parent / "fixtures" / "bay" / "massing_subset.zip").read_bytes()
BAY = Frame(43.649667, -79.380991)


def test_the_recorded_slice_reads_back_as_real_parts(tmp_path):
    net = FakeNet({"toronto": router({"package_show?id=3d-massing": package(2025), "3DMassingShapefile_": SUBSET})})
    parts, year = massing.fetch(net, str(tmp_path), BAY, 150)
    assert year == 2025 and len(parts) >= 70
    assert {"toronto_massing_lidar", "toronto_massing_3d_model", "toronto_massing_site_plan"} <= {p.source for p in parts}
    at_address = [p for p in parts if any(poly.contains(Point(0, 0)) for poly in p.polygons)]
    assert at_address and max(p.height for p in at_address) == pytest.approx(75.85, abs=0.5)
    assert all(poly.is_valid for p in parts for poly in p.polygons)
