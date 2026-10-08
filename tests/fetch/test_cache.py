import os

from ghosttown_fetch.cache import Cache, atomic_write


def test_round_trip_per_source(tmp_path):
    c = Cache(str(tmp_path))
    assert c.read("osm", "k") is None
    c.write("osm", "k", b"x")
    assert c.read("osm", "k") == b"x"
    assert c.read("other", "k") is None


def test_entries_expire(tmp_path):
    now = [1_000_000.0]
    c = Cache(str(tmp_path), max_age_days=30, clock=lambda: now[0])
    c.write("osm", "k", b"x")
    now[0] += 29 * 86400
    assert c.read("osm", "k") == b"x"
    now[0] += 2 * 86400
    assert c.read("osm", "k") is None


def test_atomic_write_leaves_no_temp_files(tmp_path):
    target = tmp_path / "a.json"
    atomic_write(str(target), b"1")
    atomic_write(str(target), b"2")
    assert sorted(os.listdir(tmp_path)) == ["a.json"]
    assert target.read_bytes() == b"2"


def test_prune_deletes_a_sources_files_older_than_the_age(tmp_path):
    c = Cache(str(tmp_path), max_age_days=30)
    day = 86400
    for source, key, age in (("mapillary", "old", 31), ("mapillary", "recent", 29), ("osm", "old", 31)):
        c.write(source, key, key.encode())
        os.utime(c._path(source, key), (c.clock() - age * day,) * 2)
    c.prune("mapillary")
    assert c.read("mapillary", "recent") == b"recent" and len(os.listdir(tmp_path / "mapillary")) == 1
    assert len(os.listdir(tmp_path / "osm")) == 1   # other sources are left alone
    c.prune("nothing-yet")                          # a folder that doesn't exist is fine
