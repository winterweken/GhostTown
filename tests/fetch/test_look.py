import copy
import gc
import json
import warnings
import weakref

import numpy as np
import pytest

from ghosttown_fetch import camera as camera_mod
from ghosttown_fetch import imagery, look, raycast, terrain
from ghosttown_fetch import look_schema as ls
from ghosttown_fetch.net import SourceError
from ghosttown_fetch.sources import mapillary
from ghosttown_fetch.sources.mapillary import TokenRejected
from camera_samples import camera
from fakes import FakeNet
from look_samples import (BRICK, EXPOSURES, GLASS, GLASS_FACTORS, GREEN, Slope, fake_net, over_wall, request,
                          street)

TOKEN = "MLY|secret"
NONE_FOUND = {"level": "warn", "code": "mapillary_none",
              "text": "No usable street photos were found, so every building has the guessed look."}
DOWN = SourceError("Mapillary answered HTTP 500; try again in a minute.", status=500)
FOUR = {"90", "91", "92", "93"}   # the synthetic street's photos


def _reply(net, match, reply):
    """`net` with every request whose url contains `match` answered with `reply` (an error or bytes) instead."""
    normal = net.answers["mapillary"]
    net.answers["mapillary"] = lambda url, data: reply if match in url else normal(url, data)
    return net


def _note(answer, code):
    return next((n["text"] for n in answer["notes"] if n["code"] == code), None)


def test_a_street_gives_storefront_brick_and_glass_zones(tmp_path):
    data = street(detail=True)
    stages = []
    answer = look.run(request(tmp_path, data), fake_net(data), TOKEN, progress=lambda s, p: stages.append(s))
    assert ls.validate_answer(answer) == []
    e = answer["buildings"]["test:1"]
    assert e["source"] == "photos" and e["photos"] >= 3
    assert [(z["kind"], z["h0"]) for z in e["zones"]] == [("storefront", 0.0), ("opaque", 3.0), ("glass", 12.0)]
    assert np.allclose(e["zones"][1]["colour"], BRICK, rtol=0.15, atol=0.02)
    # every photo sees only the south wall, and one wall in four photos is one vote, not the two walls that must agree
    assert e["floor_h"] == 3.5 and 0 < e["confidence"] <= 1
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
                                  "credit": "Street photos © Mapillary contributors, CC BY-SA 4.0"},
                                 {"key": "mapillary_labels", "name": "Mapillary",
                                  "credit": "Labels from Mapillary · https://www.mapillary.com"}]
    assert all(TOKEN not in url and "MLY%7C" not in url for url, _source, _data in net.calls)   # nor URL-encoded
    # every call to Mapillary's API carries the token as a header, and nothing else does (the photo links are signed)
    api = [url for url, _source, _data in net.calls if url.startswith("https://graph.mapillary.com/")]
    assert api and net.headers.count({"Authorization": "OAuth " + TOKEN}) == len(api)
    assert net.headers.count({}) == len(net.calls) - len(api)


def test_no_coverage_means_every_building_is_guessed(tmp_path):
    empty = dict(street(), records=[])
    answer = look.run(request(tmp_path, empty), fake_net(empty), TOKEN)
    assert {e["source"] for e in answer["buildings"].values()} == {"guessed"}
    assert answer["photos_used"] == 0 and answer["sources"] == [] and ls.validate_answer(answer) == []
    assert NONE_FOUND in answer["notes"]


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


def test_every_detail_building_is_read_even_when_they_outnumber_the_budget(tmp_path):
    data = street()
    details = [dict(_box(f"detail:{i}", 200 + 20 * i, 200), detail=True) for i in range(12)]
    req = request(tmp_path, data, buildings=data["buildings"] + details, budget_photos=10)
    answer = look.run(req, fake_net(data), TOKEN)
    assert all(len(answer["buildings"][f"detail:{i}"]["detail_walls"]) == 4 for i in range(12))
    assert answer["buildings"]["test:1"]["source"] == "guessed"   # detail first: the twelve fill every place


def test_no_usable_photo_gets_a_note_even_when_photos_were_chosen(tmp_path):
    data = street()
    net = _reply(fake_net(data), "cdn.example/", DOWN)   # every photo fails to download
    answer = look.run(request(tmp_path, data), net, TOKEN)
    assert {e["source"] for e in answer["buildings"].values()} == {"guessed"}
    assert answer["photos_used"] == 0 and answer["years"] is None and answer["sources"] == []
    assert ls.validate_answer(answer) == []
    assert NONE_FOUND in answer["notes"]
    assert _note(answer, "mapillary_photos") == "4 photos couldn't be read and were skipped."


@pytest.mark.parametrize("how", ["photo", "labels", "jpeg"])
@pytest.mark.parametrize("failing, note", [(["90"], "1 photo couldn't be read and was skipped."),
                                           (["90", "91"], "2 photos couldn't be read and were skipped.")],
                         ids=["one photo", "two photos"])
def test_a_photo_or_its_labels_that_fail_are_skipped_and_noted(tmp_path, how, failing, note):
    data = street()
    net = fake_net(data)
    for image_id in failing:
        if how == "labels":
            _reply(net, f"/{image_id}/detections", DOWN)
        else:   # the photo's download fails, or it arrives as a JPEG that can't be decoded
            _reply(net, f"cdn.example/{image_id}.jpg", DOWN if how == "photo" else b"\xff\xd8\xff" + bytes(200))
    answer = look.run(request(tmp_path, data), net, TOKEN)
    assert answer["buildings"]["test:1"]["photos"] == 4 - len(failing) and answer["photos_used"] == 4 - len(failing)
    assert _note(answer, "mapillary_photos") == note
    assert NONE_FOUND not in answer["notes"]   # photos were still used


def test_listing_that_fails_everywhere_raises_nothing_listed(tmp_path):
    data = street()
    with pytest.raises(look.NothingListed):
        look.run(request(tmp_path, data), FakeNet({"mapillary": DOWN}), TOKEN)


def test_an_outage_stops_the_run_instead_of_guessing_every_building(tmp_path, monkeypatch):
    # The listing and the labels are answered, then every photo download finds nobody there. Three failures in a row
    # (eight in a real run) leave the rest unsent, and the run stops with a sentence rather than handing back a look
    # in which every building is guessed.
    monkeypatch.setattr(look.mapillary, "OUTAGE_FAILURES", 3)
    data = street()
    net = _reply(fake_net(data), "cdn.example/", SourceError("Mapillary couldn't be reached (timed out); try again "
                                                             "in a minute."))
    with pytest.raises(look.NotReached, match="^Mapillary couldn't be reached; try again in a minute.$"):
        look.run(request(tmp_path, data), net, TOKEN)


def test_one_failed_listing_tile_is_noted_and_the_rest_are_used(tmp_path):
    data = street()
    net = fake_net(data)
    normal, failing = net.answers["mapillary"], iter([DOWN])   # the first listing request fails

    def flaky(url, body):
        error = next(failing, None) if "/images?" in url else None
        return error if error is not None else normal(url, body)

    net.answers["mapillary"] = flaky
    answer = look.run(request(tmp_path, data), net, TOKEN)
    assert {"level": "warn", "code": "mapillary_tiles", "text": "Some areas couldn't be searched."} in answer["notes"]
    assert answer["buildings"]["test:1"]["source"] == "photos"


def test_photos_are_brought_to_the_median_road_before_their_colours_are_combined(tmp_path):
    # Each photo shows the glass in another colour and one photo is under-exposed. The glass zone is the median of the
    # glass colours only once every photo is calibrated against its road. (The brick can't tell: scaled by their own
    # exposures, the photos' median is the median exposure times the brick, calibrated or not.)
    data = street()
    answer = look.run(request(tmp_path, data), fake_net(data), TOKEN)
    glass = answer["buildings"]["test:1"]["zones"][-1]
    expected = np.median(EXPOSURES) * np.median([np.array(GLASS) * f for f in GLASS_FACTORS], axis=0)
    assert glass["kind"] == "glass" and np.allclose(glass["colour"], expected, rtol=0.05)


def test_confidence_is_the_share_of_the_wall_seen(tmp_path):
    data = street()
    entry = look.run(request(tmp_path, data), fake_net(data), TOKEN)["buildings"]["test:1"]
    assert entry["photos"] == 4   # three photos are enough for full confidence, but they see one wall in four
    assert entry["confidence"] == pytest.approx(0.25, abs=0.01)


# TARGET's street-facing wall has 8 rows of sample points, an eighth of its points each, 1.9, 5.6 ... 28.1 m up. The
# street has only these four photos, so a dropped one leaves three: no other photo can take its place.
@pytest.mark.parametrize("value, z0, z1, photos", [
    ("nature--sky", 22.5, 30.0, 4),                       # sky over the top 2 rows: 25%, kept
    ("nature--sky", 18.75, 30.0, 3),                      # over the top 3 rows: 37.5%, dropped
    ("construction--flat--sidewalk", 0.0, 7.5, 4),        # ground over the bottom 2 rows: kept
    ("construction--flat--sidewalk", 0.0, 11.25, 3),      # over the bottom 3 rows: dropped
], ids=["sky 25%", "sky 37.5%", "ground 25%", "ground 37.5%"])
def test_a_photo_whose_wall_lands_on_sky_or_ground_is_dropped_above_30_percent(tmp_path, value, z0, z1, photos):
    data = over_wall(street(), {"93"}, value, z0, z1)
    answer = look.run(request(tmp_path, data), fake_net(data), TOKEN)
    assert answer["buildings"]["test:1"]["photos"] == photos and answer["photos_used"] == photos


@pytest.mark.parametrize("z1, photos", [(18.75, 4), (22.5, 3)], ids=["building 37.5%", "building 25%"])
def test_a_photo_that_shows_less_than_30_percent_building_is_dropped(tmp_path, z1, photos):
    data = over_wall(street(), {"93"}, "object--vehicle--truck", 0.0, z1)   # a truck hides the wall up to z1
    answer = look.run(request(tmp_path, data), fake_net(data), TOKEN)
    assert answer["buildings"]["test:1"]["photos"] == photos and answer["photos_used"] == photos


def test_wires_over_the_wall_are_not_held_against_the_photo(tmp_path):
    # Wires cover the top three quarters: a quarter of the points are building, but all the points that are not wires
    data = over_wall(street(), {"93"}, "object--wire-group", 7.5, 30.0)
    answer = look.run(request(tmp_path, data), fake_net(data), TOKEN)
    assert answer["buildings"]["test:1"]["photos"] == 4


def test_sky_is_counted_among_all_the_points_wires_and_all(tmp_path):
    # Wires over the bottom quarter and sky over the top quarter. Sky is a quarter of the points, so the photo stays;
    # counted among the points the wires leave it would be a third, and the wires would have cost the photo.
    data = over_wall(over_wall(street(), {"93"}, "object--wire-group", 0.0, 7.5), {"93"}, "nature--sky", 22.5, 30.0)
    answer = look.run(request(tmp_path, data), fake_net(data), TOKEN)
    assert answer["buildings"]["test:1"]["photos"] == 4


def test_a_photo_with_wires_over_all_of_the_wall_is_skipped_quietly(tmp_path):
    data = over_wall(street(), {"93"}, "object--wire-group", 0.0, 30.0)
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)   # the mean of no points would warn
        answer = look.run(request(tmp_path, data), fake_net(data), TOKEN)
    assert answer["buildings"]["test:1"]["photos"] == 3


def _tinted(entry, colour):
    return any(np.allclose(z["colour"], colour, atol=0.1) for z in entry["zones"])


def test_a_building_in_front_does_not_tint_the_one_behind(tmp_path):
    data = street(occluded=True)   # a green block in every photo hides TARGET below about 15 m
    answer = look.run(request(tmp_path, data), fake_net(data), TOKEN)
    assert answer["buildings"]["test:1"]["source"] == "photos"
    assert not _tinted(answer["buildings"]["test:1"], GREEN)
    assert _tinted(answer["buildings"]["test:3"], GREEN)   # the block itself does read as green


def test_pixels_that_are_not_labelled_building_do_not_tint_the_wall(tmp_path):
    # A hedge, painted green over the middle floors of every photo and labelled vegetation
    data = over_wall(street(), FOUR, "nature--vegetation", 3.0, 12.0, paint=GREEN)
    pixels = imagery.decode_linear(data["photos"]["91"])
    assert ((pixels[..., 1] > 0.4) & (pixels[..., 0] < 0.15)).sum() > 1000   # the hedge is in the photo
    answer = look.run(request(tmp_path, data), fake_net(data), TOKEN)
    assert answer["buildings"]["test:1"]["source"] == "photos"
    assert not _tinted(answer["buildings"]["test:1"], GREEN)


def _decodes(monkeypatch, keep):
    """Patch look so that `keep` photos are kept decoded; returns (decoded photos alive at the start of each decode,
    weak references to every decoded photo)."""
    before, made = [], []
    real = imagery.decode_linear

    def decode(jpeg):
        before.append(sum(ref() is not None for ref in made))
        image = real(jpeg)
        made.append(weakref.ref(image))
        return image

    monkeypatch.setattr(look.imagery, "decode_linear", decode)
    monkeypatch.setattr(look, "DECODED_PHOTOS", keep)
    return before, made


def test_by_default_only_a_handful_of_photos_are_kept_decoded():
    assert 1 <= look.DECODED_PHOTOS <= 16   # 36 MiB each at 2048 x 1536, whatever the budget


def test_only_a_few_decoded_photos_are_alive_at_once_and_none_outlive_the_run(tmp_path, monkeypatch):
    before, made = _decodes(monkeypatch, keep=2)
    data = street()
    answer = look.run(request(tmp_path, data), fake_net(data), TOKEN)
    assert answer["buildings"]["test:1"]["photos"] == 4   # all four were read, though two fit
    assert len(before) > 4 and max(before) <= 2   # each decoded for its road, then again for the building
    gc.collect()
    assert not any(ref() is not None for ref in made)


def test_a_photo_two_buildings_use_is_decoded_once_for_both(tmp_path, monkeypatch):
    before, _made = _decodes(monkeypatch, keep=look.DECODED_PHOTOS)
    data = street(occluded=True)   # TARGET and the block in front of it are read from the same four photos
    answer = look.run(request(tmp_path, data), fake_net(data), TOKEN)
    assert answer["buildings"]["test:1"]["photos"] == answer["buildings"]["test:3"]["photos"] == 4
    assert len(before) <= 2 * 4   # once for each photo's road, once for the buildings that share it


def test_the_answer_does_not_depend_on_how_many_photos_are_kept_decoded(tmp_path, monkeypatch):
    data = street(occluded=True)
    data = dict(data, buildings=data["buildings"][::-1])   # the block is read first, so TARGET comes from cached photos
    wide = look.run(request(tmp_path, data), fake_net(data), TOKEN)
    monkeypatch.setattr(look, "DECODED_PHOTOS", 1)
    assert look.run(request(tmp_path, data), fake_net(data), TOKEN) == wide


def _zones(answer, bid="test:1"):
    return [(z["kind"], z["h0"], z["h1"]) for z in answer["buildings"][bid]["zones"]]


def _downloads(net):
    """Photo ids whose download was asked for, in order."""
    return [url.rsplit("/", 1)[1].split(".")[0] for url, _source, _data in net.calls if "cdn.example/" in url]


def _label_requests(net):
    return [url.split("graph.mapillary.com/", 1)[1].split("/")[0] for url, _s, _d in net.calls if "/detections" in url]


def test_a_photo_the_label_check_drops_is_replaced_by_the_next_best_one(tmp_path):
    # Sky over the top three rows of photo 93 drops it; photo 80, farther back and left out by choose, takes its place.
    # Labels come before photos, so 93 is never downloaded: with a budget of four, four photos are asked for.
    data = over_wall(street(extra=1), {"93"}, "nature--sky", 18.75, 30.0)
    net = fake_net(data)
    answer = look.run(request(tmp_path, data, budget_photos=4), net, TOKEN)
    assert answer["buildings"]["test:1"]["photos"] == 4 and answer["photos_used"] == 4
    assert sorted(_downloads(net)) == ["80", "90", "91", "92"]
    assert _note(answer, "mapillary_photos") is None   # a dropped photo is not one that couldn't be read


def test_without_a_drop_the_extra_photos_are_not_asked_for(tmp_path):
    data = street(extra=1)
    net = fake_net(data)
    answer = look.run(request(tmp_path, data), net, TOKEN)
    assert answer["buildings"]["test:1"]["photos"] == 4
    assert "80" not in _label_requests(net) and "80" not in _downloads(net)


@pytest.mark.parametrize("how", ["labels", "photo", "jpeg"])
def test_a_photo_whose_labels_or_photo_fail_is_replaced_and_noted(tmp_path, how):
    data = street(extra=1)
    net = fake_net(data)
    if how == "labels":
        _reply(net, "/93/detections", DOWN)
    else:   # the photo's download fails, or it arrives as a JPEG that can't be decoded
        _reply(net, "cdn.example/93.jpg", DOWN if how == "photo" else b"\xff\xd8\xff" + bytes(200))
    answer = look.run(request(tmp_path, data), net, TOKEN)
    assert answer["buildings"]["test:1"]["photos"] == 4 and answer["photos_used"] == 4
    assert "80" in _downloads(net)
    assert _note(answer, "mapillary_photos") == "1 photo couldn't be read and was skipped."
    if how == "labels":
        assert "93" not in _downloads(net)   # no labels, no point downloading it


def test_a_failed_download_gives_its_place_in_the_budget_back(tmp_path):
    # Budget four: 93's download fails, so 80 is downloaded in its place. Four photos arrive, no more.
    data = street(extra=1)
    net = _reply(fake_net(data), "cdn.example/93.jpg", DOWN)
    answer = look.run(request(tmp_path, data, budget_photos=4), net, TOKEN)
    assert answer["buildings"]["test:1"]["photos"] == 4
    assert sorted(i for i in _downloads(net) if i != "93") == ["80", "90", "91", "92"]


def _in_sequence(data, image_id, sequence):
    return dict(data, records=[dict(r, sequence=sequence) if r["id"] == image_id else r for r in data["records"]])


@pytest.mark.parametrize("value, z0, z1, first", [
    ("nature--sky", 18.75, 30.0, "81"),              # dropped for sky: its sequence's poses are suspect, 80 waits
    ("object--vehicle--truck", 0.0, 22.5, "80"),     # dropped for a truck in front: nothing against its sequence
], ids=["sky", "blocked"])
def test_after_a_sky_or_ground_drop_that_sequence_is_tried_last(tmp_path, value, z0, z1, first):
    # Photo 80, the better of the two extra photos, belongs to the sequence of photo 93, which the label check drops.
    data = _in_sequence(over_wall(street(extra=2), {"93"}, value, z0, z1), "80", "seq1")
    net = fake_net(data)
    answer = look.run(request(tmp_path, data), net, TOKEN)
    assert answer["buildings"]["test:1"]["photos"] == 4
    assert [i for i in _label_requests(net) if i.startswith("8")] == [first]


def test_a_building_tries_at_most_six_candidates(tmp_path):
    # 93 is dropped, and none of the seven extra photos has labels to be had: six are tried, one after another.
    data = over_wall(street(extra=7), {"93"}, "nature--sky", 18.75, 30.0)
    net = fake_net(data)
    gone = SourceError("Mapillary answered HTTP 404; try again in a minute.", status=404)
    for i in range(7):
        _reply(net, f"/8{i}/detections", gone)
    answer = look.run(request(tmp_path, data), net, TOKEN)
    assert answer["buildings"]["test:1"]["photos"] == 3
    assert len([i for i in _label_requests(net) if i.startswith("8")]) == look.REPLACE_TRIES == 6


def test_a_rejected_token_while_replacing_a_photo_is_raised(tmp_path):
    data = over_wall(street(extra=1), {"93"}, "nature--sky", 18.75, 30.0)
    net = _reply(fake_net(data), "/80/detections", SourceError("Mapillary answered HTTP 401.", status=401))
    with pytest.raises(TokenRejected):
        look.run(request(tmp_path, data), net, TOKEN)


def test_a_wing_in_front_of_a_wall_is_not_read_as_that_wall():
    # A 15 m podium (y -10 to 0) in front of a 60 m tower part (y 0 to 10) of one building, seen from 50 m south. Below
    # the line of sight over the podium's top, at 18.25 m, the tower's front wall is hidden: the pixels there show the
    # podium's front, 10 m nearer. Each pixel of this photo is as bright as the height of the surface it shows.
    part = {"id": "b", "solids": [{"rings": [[[-20, -10], [20, -10], [20, 0], [-20, 0]]], "z0": 0.0, "z1": 15.0},
                                  {"rings": [[[-20, 0], [20, 0], [20, 10], [-20, 10]]], "z0": 0.0, "z1": 60.0}]}
    scene = raycast.Scene([part])
    cam = camera((0.0, -50.0, 2.0), image_id="1")
    dirs, rows = cam.rays(512)
    owner, dist = scene.first_hit(cam.position[None], dirs, 1000.0)
    height = np.clip(cam.position[2] + dirs[:, 2] * dist, 0, 100) / 100.0
    image = np.where((owner == 0)[:, None], height[:, None] * np.ones(3), 0.0).reshape(rows, 512, 3)

    class AllBuilding:
        def at(self, u, v):
            return np.full(np.shape(u), imagery.BUILDING, dtype=np.uint8)

    front = next(w for w in range(len(scene.A)) if np.allclose(scene.A[w][1], 0) and np.allclose(scene.B[w][1], 0)
                 and scene.N[w][1] < 0)   # the tower part's south wall, at y = 0
    colours, heights, _grey, _mask = look._straighten(cam, front, 0, scene, image, AllBuilding(),
                                                      look._owner_grid(cam, scene))
    assert heights.min() > 18.25 - 0.5   # nothing from the hidden band; the grid's cells are about 0.35 m there
    off = np.abs(imagery.luminance(colours) * 100 - heights) > 1.0
    assert off.mean() < 0.02   # the wall itself, but for the row at the shadow line that straddles the podium's edge


def test_a_street_built_on_flat_ground_keeps_its_cameras_on_flat_ground(tmp_path, monkeypatch):
    # The scene was built without ground heights (ground_at_centre_m is None): its buildings stand on flat ground, so
    # its cameras must too, even where NRCan has heights. None are asked for.
    data = street()
    plain = look.run(request(tmp_path / "a", data), fake_net(data), TOKEN)
    asked = []
    monkeypatch.setattr(look.terrain_mod, "load", lambda net, frame, r: (asked.append(r), (Slope(0.05), None))[1])
    answer = look.run(request(tmp_path / "b", data), fake_net(data), TOKEN)
    assert asked == [] and _zones(answer) == _zones(plain) == [("storefront", 0.0, 3.0), ("opaque", 3.0, 12.0),
                                                             ("glass", 12.0, None)]


def test_a_street_built_on_ground_heights_stands_its_cameras_on_them(tmp_path, monkeypatch):
    # The street on ground rising 5 m per 100 m north: the cameras stand 2.5 to 4 m below the building's base. Read on
    # the same ground the scene was built on, it gives the flat street's zones; on flat cameras it wouldn't.
    data = street(slope=0.05)
    monkeypatch.setattr(look.terrain_mod, "load", lambda net, frame, r: (Slope(0.05), None))
    on_ground = look.run(request(tmp_path / "a", data, ground_at_centre_m=100.0), fake_net(data), TOKEN)
    flat = look.run(request(tmp_path / "b", data), fake_net(data), TOKEN)
    assert _zones(on_ground) == [("storefront", 0.0, 3.0), ("opaque", 3.0, 12.0), ("glass", 12.0, None)]
    assert _zones(flat) != _zones(on_ground)


def test_a_scene_built_on_ground_heights_stops_when_they_cant_be_had(tmp_path, monkeypatch):
    data = street()
    note = ("warn", "terrain", "Natural Resources Canada couldn't be reached; try again in a minute. "
                               "The ground is flat.")
    monkeypatch.setattr(look.terrain_mod, "load", lambda net, frame, r: (terrain.FlatTerrain(), note))
    net = fake_net(data)
    with pytest.raises(look.NoGround) as e:
        look.run(request(tmp_path, data, ground_at_centre_m=100.0), net, TOKEN)
    assert str(e.value) == "Ground heights couldn't be fetched for the photos; try again in a minute."
    assert net.calls == []   # nothing asked of Mapillary


def test_expired_photos_and_labels_are_deleted_at_the_end_of_a_run(tmp_path):
    data = street()
    net = fake_net(data)
    look.run(request(tmp_path, data), net, TOKEN)
    assert net.pruned == ["mapillary"]


THROTTLE_BODY = (b'{"error": {"message": "(#4) Application request limit reached", "type": "OAuthException", '
                 b'"code": 4, "error_subcode": 1349210}}')


def test_a_throttled_label_request_is_asked_again_then_skipped_without_its_text(tmp_path):
    # Photo 93's labels meet the request limit twice, a pause apart: the photo is skipped and noted like any photo
    # whose labels failed, and nothing of Mapillary's answer reaches the look.
    data = street(extra=1)
    throttled = SourceError("Mapillary answered HTTP 403; try again in a minute.", status=403, body=THROTTLE_BODY)
    net = _reply(fake_net(data), "/93/detections", throttled)
    answer = look.run(request(tmp_path, data), net, TOKEN)
    assert answer["buildings"]["test:1"]["photos"] == 4 and net.slept == [30]
    assert _label_requests(net).count("93") == 2
    assert _note(answer, "mapillary_photos") == "1 photo couldn't be read and was skipped."
    assert "request limit" not in json.dumps(answer)


def test_a_street_on_higher_ground_reads_the_same(tmp_path, monkeypatch):
    # The whole street 5 m higher, buildings and cameras alike: heights are measured from each building's lowest point,
    # so neither the zones nor the detail spans move.
    data = street(detail=True)
    flat = look.run(request(tmp_path / "a", data), fake_net(data), TOKEN)
    raised = copy.deepcopy(data["buildings"])
    for b in raised:
        for solid in b["solids"]:
            solid["z0"] += 5.0
            solid["z1"] += 5.0
    monkeypatch.setattr(camera_mod, "MOUNT_M", camera_mod.MOUNT_M + 5.0)
    up = look.run(request(tmp_path / "b", data, buildings=raised), fake_net(data), TOKEN)
    for bid, entry in flat["buildings"].items():
        assert _zones(up, bid) == _zones(flat, bid), bid
        assert up["buildings"][bid].get("detail_walls") == entry.get("detail_walls"), bid


def _opaque(answer):
    return np.array(next(z["colour"] for z in answer["buildings"]["test:1"]["zones"] if z["kind"] == "opaque"))


def test_gain_is_against_the_median_road_and_clamped(tmp_path, monkeypatch):
    # Photos 92 and 93 read their road at a fifth: the median road falls to 0.6, their gains of 3 and 5 are held to 2,
    # so the brick comes out at 0.9 of the plain run's (1.1 against the brightest road, 1.8 without the clamp).
    data = street()
    plain = _opaque(look.run(request(tmp_path / "a", data), fake_net(data), TOKEN))
    real, calls = imagery.road_luminance, []

    def dim(image, lab):
        calls.append(None)
        return real(image, lab) * (0.2 if len(calls) in (3, 4) else 1.0)   # the roads are read in id order

    monkeypatch.setattr(look.imagery, "road_luminance", dim)
    dimmed = _opaque(look.run(request(tmp_path / "b", data), fake_net(data), TOKEN))
    assert np.allclose(dimmed, 0.9 * plain, rtol=0.05), dimmed / plain
