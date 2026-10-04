from ghosttown_fetch import context as ctx
from ghosttown_fetch.assemble import assemble
from photo_samples import JPEG
from test_assemble import FAR, _city, _net, _req
from toronto_samples import page


def test_a_toronto_build_carries_the_photo_beside_the_context(tmp_path):
    doc = assemble(_req(tmp_path), _net())
    assert doc["photo"]["file"] == "photo.jpg" and doc["photo"]["year"] == 2025
    assert (tmp_path / "o" / "photo.jpg").read_bytes() == JPEG
    assert any(n["code"] == "city_photo" and n["level"] == "info" and "2025" in n["text"] for n in doc["notes"])
    assert ctx.validate(doc) == []


def test_a_failed_photo_is_a_warning_and_the_build_goes_on(tmp_path):
    net = _net(toronto=_city(**{"/MapServer/export?": b'{"error":{"code":500}}' * 50}))
    doc = assemble(_req(tmp_path), net)
    assert "photo" not in doc and "toronto:building:7" in {e["id"] for e in doc["elements"]}
    assert any(n["code"] == "city_photo" and n["level"] == "warn" and n["text"].endswith("The site has no aerial photo.")
               for n in doc["notes"])


def test_no_photo_when_it_is_not_asked_for(tmp_path):
    net = _net()
    doc = assemble(_req(tmp_path, layers=["buildings", "terrain"]), net)
    assert "photo" not in doc and not any("MapServer/export" in url for url, _, _ in net.calls)


def test_no_photo_outside_toronto(tmp_path):
    net = _net(toronto=_city(**{"FeatureServer/40/": page(FAR)}))
    doc = assemble(_req(tmp_path), net)
    assert "photo" not in doc and not any("MapServer/export" in url for url, _, _ in net.calls)
