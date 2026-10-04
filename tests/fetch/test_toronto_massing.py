import errno
import io
import json
import os
import shutil
import struct
import zipfile
from pathlib import Path

import pytest
from shapely.geometry import Point

from ghosttown_fetch import shapefile
from ghosttown_fetch.frame import Frame
from ghosttown_fetch.net import SourceError
from ghosttown_fetch.sources import toronto_massing as massing
from fakes import FakeNet, router
from shapefile_samples import part, square, zipped

F = Frame(43.65, -79.38)
DOWNLOADS = "https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/x/resource/y/download"


def package(*years):
    """A CKAN package_show answer listing these shapefile editions (and a multipatch to ignore)."""
    resources = [{"name": f"3DMassingShapefile_{y}_WGS84.zip", "size": 81415175,
                  "url": f"{DOWNLOADS}/3DMassingShapefile_{y}_WGS84.zip"} for y in years]
    resources.append({"name": "3DMassingMultipatch_2099_WGS84.zip", "url": f"{DOWNLOADS}/m.zip"})
    return json.dumps({"success": True, "result": {"resources": resources}}).encode("utf-8")


ZIP = zipped([part(square(0, 0, 10), 20.0), part(square(2000, 0, 10), 30.0), part(square(40, 0, 10), 0.3)])


def net_for(zip_bytes=ZIP, years=(2024, 2099)):
    return FakeNet({"toronto": router({"package_show?id=3d-massing": package(*years), "3DMassingShapefile_": zip_bytes})})


def test_the_newest_shapefile_edition_is_chosen():
    edition = massing.newest_edition(net_for())
    assert edition == massing.Edition(2099, f"{DOWNLOADS}/3DMassingShapefile_2099_WGS84.zip", 81415175)


@pytest.mark.parametrize("answer", [b"<html>", json.dumps({"success": False}).encode(),
                                    json.dumps({"success": True, "result": {"resources": []}}).encode()])
def test_no_edition_is_a_source_error(answer):
    with pytest.raises(SourceError):
        massing.newest_edition(FakeNet({"toronto": answer}))


def test_odd_entries_in_the_listing_are_skipped_not_fatal():
    good = {"name": "3DMassingShapefile_2099_WGS84.zip", "url": f"{DOWNLOADS}/z.zip", "size": "about 80 MB"}
    answer = json.dumps({"success": True, "result": {"resources": ["not a resource", None, good]}}).encode()
    assert massing.newest_edition(FakeNet({"toronto": answer})) == massing.Edition(2099, f"{DOWNLOADS}/z.zip", 0)


def _listing(*urls):
    resources = [{"name": f"3DMassingShapefile_{2090 + i}_WGS84.zip", "url": url} for i, url in enumerate(urls)]
    return FakeNet({"toronto": json.dumps({"success": True, "result": {"resources": resources}}).encode("utf-8")})


@pytest.mark.parametrize("url", [
    "http://ckan0.cf.opendata.inter.prod-toronto.ca/d/3DMassingShapefile_2099_WGS84.zip",  # not https
    "https://portal.example/d/3DMassingShapefile_2099_WGS84.zip",  # a foreign host
    "https://evil-toronto.ca/d/3DMassingShapefile_2099_WGS84.zip",  # ends in toronto.ca but not .toronto.ca
    "https://toronto.ca.evil.example/d/3DMassingShapefile_2099_WGS84.zip",
    "https://ckan0.cf.opendata.inter.prod-toronto.ca@evil.example/d/3DMassingShapefile_2099_WGS84.zip",
    "ftp://www.toronto.ca/d/3DMassingShapefile_2099_WGS84.zip",
    "//www.toronto.ca/d/3DMassingShapefile_2099_WGS84.zip",
    "https://[bad/3DMassingShapefile_2099_WGS84.zip"])
def test_an_edition_from_a_strange_url_is_skipped(url):
    good = f"{DOWNLOADS}/3DMassingShapefile_2090_WGS84.zip"
    assert massing.newest_edition(_listing(good, url)).url == good
    with pytest.raises(SourceError, match="lists no 3D Massing"):
        massing.newest_edition(_listing(url))


@pytest.mark.parametrize("url", ["https://ckan0.cf.opendata.inter.prod-toronto.ca/d/z.zip", "https://www.toronto.ca/d/z.zip",
                                 "https://OPEN.Toronto.CA/d/z.zip"])
def test_https_downloads_from_the_city_are_accepted(url):
    assert massing.newest_edition(_listing(url)).url == url


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
    old = massing.local_copy(net_for(), str(tmp_path), massing.Edition(2098, f"{DOWNLOADS}/3DMassingShapefile_2098_WGS84.zip", 0))
    new = massing.local_copy(net_for(), str(tmp_path), massing.Edition(2099, f"{DOWNLOADS}/3DMassingShapefile_2099_WGS84.zip", 0))
    assert not os.path.exists(old) and os.path.isdir(new)


def _ready_folder(tmp_path, year, content=b"x"):
    """A year folder that looks ready (its four files exist) without being a real copy."""
    folder = tmp_path / "toronto_massing" / str(year)
    folder.mkdir(parents=True, exist_ok=True)
    for ext in (".shp", ".shx", ".dbf", ".npy"):
        (folder / ("massing" + ext)).write_bytes(content)
    return folder


def _leftovers(tmp_path):
    return [n for n in os.listdir(tmp_path / "toronto_massing") if n.startswith(".staging-")]


def test_only_older_copies_are_deleted(tmp_path):
    older, newer = _ready_folder(tmp_path, 2097), _ready_folder(tmp_path, 2099)
    (tmp_path / "toronto_massing" / "notes").mkdir()
    folder = massing.local_copy(net_for(), str(tmp_path), massing.Edition(2098, f"{DOWNLOADS}/3DMassingShapefile_2098_WGS84.zip", 0))
    assert folder == str(tmp_path / "toronto_massing" / "2098") and massing._ready(folder)
    assert not older.exists() and massing._ready(str(newer)) and (tmp_path / "toronto_massing" / "notes").is_dir()


def test_a_copy_that_appears_during_the_download_is_kept_not_replaced(tmp_path):
    real_index = massing._index
    appeared = []

    def index_then_another_build_finishes(staging):
        real_index(staging)
        appeared.append(_ready_folder(tmp_path, 2099, b"theirs"))  # the other Blender instance got there first

    net = net_for()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(massing, "_index", index_then_another_build_finishes)
        folder = massing.local_copy(net, str(tmp_path), massing.newest_edition(net))
    assert folder == str(tmp_path / "toronto_massing" / "2099") and appeared
    assert (tmp_path / "toronto_massing" / "2099" / "massing.shp").read_bytes() == b"theirs"
    assert _leftovers(tmp_path) == []


def test_a_copy_that_appears_just_before_the_swap_is_kept_not_replaced(tmp_path):
    real_replace = os.replace

    def another_build_finishes_first(src, dst):
        _ready_folder(tmp_path, 2099, b"theirs")
        raise OSError(errno.ENOTEMPTY, "Directory not empty")

    net = net_for()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(massing.os, "replace", another_build_finishes_first)
        folder = massing.local_copy(net, str(tmp_path), massing.newest_edition(net))
    assert (tmp_path / "toronto_massing" / "2099" / "massing.shp").read_bytes() == b"theirs"
    assert folder == str(tmp_path / "toronto_massing" / "2099") and _leftovers(tmp_path) == []
    assert os.replace is real_replace


def test_a_half_made_folder_is_replaced_but_a_real_failure_still_raises(tmp_path):
    half = tmp_path / "toronto_massing" / "2099"
    half.mkdir(parents=True)
    (half / "massing.shp").write_bytes(b"left by a crashed run")  # not ready: no index
    net = net_for()
    folder = massing.local_copy(net, str(tmp_path), massing.newest_edition(net))
    assert massing._ready(folder) and (half / "massing.shp").read_bytes() != b"left by a crashed run"
    shutil.rmtree(folder)

    def disk_full(src, dst):
        raise OSError(errno.ENOSPC, "No space left on device")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(massing.os, "replace", disk_full)
        with pytest.raises(OSError):
            massing.local_copy(net, str(tmp_path), massing.newest_edition(net))
    assert _leftovers(tmp_path) == [] and not (tmp_path / "toronto_massing" / "2099").exists()


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


def _zip_with(*names):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name in names:
            z.writestr(name, b"x")
    return buffer, buffer.getvalue()


def test_a_zip_with_two_shapefiles_is_refused(tmp_path):
    _, body = _zip_with("a.shp", "a.shx", "a.dbf", "b.shp")
    with pytest.raises(SourceError, match="more than one"):
        massing._check_zip(body)
    with pytest.raises(SourceError, match="more than one"):
        massing.fetch(net_for(zip_bytes=body), str(tmp_path), F, 300)
    assert not (tmp_path / "toronto_massing" / "2099").exists()


def test_a_zip_that_unpacks_to_over_2_gb_is_refused(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name in ("a.shp", "a.shx", "a.dbf"):
            z.writestr(name, b"x")
        z.filelist[0].file_size = 3 * 1024 ** 3  # what a zip bomb's directory claims
    with pytest.raises(SourceError, match="unpacks to more than 2 GB"):
        massing._check_zip(buffer.getvalue())
    with pytest.raises(SourceError, match="2 GB"):
        massing.fetch(net_for(zip_bytes=buffer.getvalue()), str(tmp_path), F, 300)
    assert not (tmp_path / "toronto_massing" / "2099").exists()


def test_a_zip_with_one_shapefile_passes_the_check():
    massing._check_zip(ZIP)


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


def _row(avg, msl, surf, source="3D Model"):
    return {"MIN_HEIGHT": 0.0, "MAX_HEIGHT": 0.0, "AVG_HEIGHT": avg, "HEIGHT_MSL": msl, "SURF_ELEV": surf,
            "HEIGHT_SRC": source, "BLDG_SRC": source, "LONGITUDE": -79.38, "LATITUDE": 43.65}


def test_heights_come_from_avg_height_even_when_the_elevations_are_blank_or_wrong(tmp_path):
    records = [
        (part(square(0, 0, 10), 1.0)[0], _row(186.0, 0.0, 0.0)),                               # elevations blank
        (part(square(20, 0, 10), 1.0)[0], _row(5.1396, 4.8684, 140.29389, "Lidar-Derived")),   # MSL nonsense
        (part(square(40, 0, 10), 1.0)[0], _row(None, 92.0, 80.0, "Lidar-Derived")),            # no AVG: fall back
        (part(square(60, 0, 10), 1.0)[0], _row(0.4, 0.0, 0.0)),                                 # too low: dropped
    ]
    parts, _ = massing.fetch(net_for(zip_bytes=zipped(records)), str(tmp_path), F, 300)
    assert {p.record: round(p.height, 4) for p in parts} == {0: 186.0, 1: 5.1396, 2: 12.0}


def test_the_recorded_slice_keeps_its_lidar_buildings(tmp_path):
    net = FakeNet({"toronto": router({"package_show?id=3d-massing": package(2025), "3DMassingShapefile_": SUBSET})})
    parts, _ = massing.fetch(net, str(tmp_path), BAY, 150)
    assert sum(p.source == "toronto_massing_lidar" for p in parts) >= 50


def test_min_height_is_a_lidar_statistic_not_a_raised_base(tmp_path):
    row = dict(_row(12.0, 92.0, 80.0, "Lidar-Derived"), MIN_HEIGHT=5.8, MAX_HEIGHT=19.9)
    parts, _ = massing.fetch(net_for(zip_bytes=zipped([(part(square(0, 0, 10), 1.0)[0], row)])), str(tmp_path), F, 300)
    p, = parts
    assert p.base == 0.0 and p.height == pytest.approx(12.0)


def test_a_part_whose_height_is_not_a_finite_number_is_dropped(tmp_path):
    inf = float("inf")
    records = [
        (part(square(0, 0, 10), 1.0)[0], _row(inf, 0.0, 0.0)),        # AVG_HEIGHT is inf
        (part(square(20, 0, 10), 1.0)[0], _row(None, inf, 80.0)),     # no AVG: the fallback is inf
        (part(square(40, 0, 10), 1.0)[0], _row(None, inf, inf)),      # the fallback is NaN
        (part(square(60, 0, 10), 1.0)[0], _row(15.0, 95.0, 80.0)),    # a normal part
    ]
    parts, _ = massing.fetch(net_for(zip_bytes=zipped(records)), str(tmp_path), F, 300)
    table = shapefile.DBF((tmp_path / "toronto_massing" / "2099" / "massing.dbf").read_bytes())
    assert table.record(0)["AVG_HEIGHT"] == inf  # the file really holds inf
    assert [(p.record, p.height) for p in parts] == [(3, pytest.approx(15.0))]
