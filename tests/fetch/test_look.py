import numpy as np
import pytest

from ghosttown_fetch import look
from ghosttown_fetch import look_schema as ls
from ghosttown_fetch.sources.mapillary import TokenRejected
from look_samples import BRICK, fake_net, request, street

TOKEN = "MLY|secret"


def test_a_street_gives_storefront_brick_and_glass_zones(tmp_path):
    data = street(detail=True)
    stages = []
    answer = look.run(request(tmp_path, data), fake_net(data), TOKEN, progress=lambda s, p: stages.append(s))
    assert ls.validate_answer(answer) == []
    e = answer["buildings"]["test:1"]
    assert e["source"] == "photos" and e["photos"] >= 3
    assert [(z["kind"], z["h0"]) for z in e["zones"]] == [("storefront", 0.0), ("opaque", 3.0), ("glass", 12.0)]
    assert np.allclose(e["zones"][1]["colour"], BRICK, rtol=0.15, atol=0.02)
    assert abs(e["floor_h"] - 4.0) <= 0.4 and 0 < e["confidence"] <= 1
    assert stages[0] == "Terrain" and stages[-1] == "Writing"


def test_buildings_no_photo_sees_get_the_guessed_look(tmp_path):
    data = street()
    answer = look.run(request(tmp_path, data), fake_net(data), TOKEN)
    far = answer["buildings"]["test:2"]
    assert far["source"] == "guessed" and far["photos"] == 0


def test_detail_walls_only_for_detail_buildings(tmp_path):
    data = street(detail=True)
    answer = look.run(request(tmp_path, data), fake_net(data), TOKEN)
    walls = answer["buildings"]["test:1"]["detail_walls"]
    assert len(walls) == 4 and all(w["z0"] == 0 and w["z1"] == 30 for w in walls)
    assert "detail_walls" not in answer["buildings"]["test:2"]


def test_credits_years_and_the_token_stays_in_headers(tmp_path):
    data = street()
    net = fake_net(data)
    answer = look.run(request(tmp_path, data), net, TOKEN)
    assert answer["photos_used"] >= 3 and answer["years"] == [2024, 2024]
    assert answer["sources"] == [{"key": "mapillary", "name": "Mapillary",
                                  "credit": "Street photos © Mapillary contributors, CC BY-SA 4.0"}]
    assert all(TOKEN not in url for url, _source, _data in net.calls)


def test_no_coverage_means_every_building_is_guessed(tmp_path):
    empty = dict(street(), records=[])
    answer = look.run(request(tmp_path, empty), fake_net(empty), TOKEN)
    assert {e["source"] for e in answer["buildings"].values()} == {"guessed"}
    assert answer["photos_used"] == 0 and answer["sources"] == [] and ls.validate_answer(answer) == []


def test_a_rejected_token_is_raised(tmp_path):
    data = street()
    with pytest.raises(TokenRejected):
        look.run(request(tmp_path, data), fake_net(data, token_ok=False), TOKEN)


def test_not_before_drops_older_photos(tmp_path):
    data = street()
    answer = look.run(request(tmp_path, data, not_before_year=2025), fake_net(data), TOKEN)
    assert answer["buildings"]["test:1"]["source"] == "guessed"


def _box(bid, x, y, size=10.0):
    ring = [[x, y], [x + size, y], [x + size, y + size], [x, y + size]]
    return {"id": bid, "solids": [{"rings": [ring], "z0": 0.0, "z1": 10.0}]}


def test_search_radius_follows_the_buildings_and_is_capped(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(look.mapillary, "list_images", lambda net, frame, r, token: (seen.append(r), ([], 0))[1])
    data = street()
    look.run(request(tmp_path, data, radius_m=1000, buildings=[data["buildings"][0]]), fake_net(data), TOKEN)
    assert 200 < seen[-1] < 215   # the 20 m target's farthest wall point, under 15 m out, plus the 200 m margin
    edge = _box("edge", 950, 0)
    look.run(request(tmp_path, data, radius_m=1000, buildings=data["buildings"] + [edge]), fake_net(data), TOKEN)
    assert seen[-1] == 1000.0


def test_photos_are_read_for_at_most_as_many_buildings_as_the_budget(tmp_path, monkeypatch):
    data = street()
    sheds = [_box(f"shed:{i}", 200 + 20 * i, 200) for i in range(12)]
    asked = []
    views = look.selection.views
    monkeypatch.setattr(look.selection, "views",
                        lambda cams, samples, scene: (asked.append({scene.ids[b] for b in samples.building.tolist()}),
                                                      views(cams, samples, scene))[1])
    answer = look.run(request(tmp_path, data, buildings=data["buildings"] + sheds, budget_photos=10), fake_net(data), TOKEN)
    assert len(asked[0]) == 10 and "test:1" in asked[0] and answer["buildings"]["test:1"]["source"] == "photos"
    assert len(answer["buildings"]) == 14
