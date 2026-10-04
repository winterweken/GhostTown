from ghosttown_fetch import context as ctx
from ghosttown_fetch.assemble import assemble
from shapefile_samples import part, square, zipped
from test_assemble import _city, _net, _req
from test_toronto_massing import package

ZIP = zipped([part(square(-20, -20, 40), 12.0), part(square(-5, -5, 10), 80.0),
              part(square(30, 0, 10), 9.0, source="Site Plan")])


def _massing(**overrides):
    return _city(**{"package_show?id=3d-massing": package(2099), "3DMassingShapefile_": ZIP, **overrides})


def _building_ids(doc):
    return sorted(e["id"] for e in doc["elements"] if e["kind"].startswith("building"))


def test_a_toronto_build_uses_the_massing_model(tmp_path):
    net = _net(toronto=_massing())
    doc = assemble(_req(tmp_path), net)
    assert _building_ids(doc) == ["toronto:massing:2099:0", "toronto:massing:2099:2"]
    assert {s["height_source"] for e in doc["elements"] for s in e["solids"]} == {"toronto_massing_lidar",
                                                                                 "toronto_massing_site_plan"}
    assert any(n["code"] == "city_massing" and n["level"] == "info" and n["text"] == "Buildings: City of Toronto 3D Massing 2099."
               for n in doc["notes"])
    assert not any("cot_geospatial3/FeatureServer/2/" in url for url, _, _ in net.calls)  # no outline query
    assert ctx.validate(doc) == []


def test_the_massing_copy_is_reused_on_the_next_build(tmp_path):
    net = _net(toronto=_massing())
    assemble(_req(tmp_path), net)
    assemble(_req(tmp_path), net)
    assert sum("3DMassingShapefile_" in url for url, _, _ in net.calls) == 1


def test_without_the_massing_model_the_outlines_are_used_with_one_warning(tmp_path):
    doc = assemble(_req(tmp_path), _net())  # _city() answers the portal with HTTP 503
    assert "toronto:building:7" in _building_ids(doc)
    warnings = [n for n in doc["notes"] if n["code"] == "city_massing"]
    assert len(warnings) == 1 and warnings[0]["level"] == "warn"
    assert warnings[0]["text"].endswith("Using the City's older building outlines instead.")


def test_a_damaged_massing_download_falls_back_too(tmp_path):
    doc = assemble(_req(tmp_path), _net(toronto=_massing(**{"3DMassingShapefile_": b"PK broken"})))
    assert "toronto:building:7" in _building_ids(doc)
    assert any(n["code"] == "city_massing" and n["level"] == "warn" for n in doc["notes"])


def test_buildings_not_asked_for_means_no_massing_request(tmp_path):
    net = _net(toronto=_massing())
    assemble(_req(tmp_path, layers=["terrain", "roads"]), net)
    assert not any("3d-massing" in url or "3DMassingShapefile_" in url for url, _, _ in net.calls)
