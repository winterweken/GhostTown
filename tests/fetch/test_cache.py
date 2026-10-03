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
