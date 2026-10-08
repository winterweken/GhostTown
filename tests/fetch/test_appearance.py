import numpy as np
import pytest

from ghosttown_fetch import appearance as ap

DARK = np.array([0.03, 0.03, 0.035])
BRICK = np.array([0.30, 0.12, 0.08])
GLASS = np.array([0.25, 0.40, 0.55])
FACTORS = [(1, 1, 1), (3.52, 2.2, 1.32), (0.5, 0.8, 1.6), (0.15, 0.15, 0.15)]   # glass seen from four places
LUMA = np.array([0.2126, 0.7152, 0.0722])   # linear luminance weights


def _colour(h, factor):
    if h < 3:
        return DARK
    if h < 12:
        return BRICK
    return GLASS * np.array(factor)


def _views(factors=FACTORS):
    heights = np.repeat(np.arange(0.25, 30, 0.5), 30)
    return [(np.array([_colour(h, f) for h in heights]), heights, np.zeros(len(heights), dtype=int))
            for f in factors]


def _grey(lum):
    return np.full(3, float(lum))


def _swatch(chroma, lum):
    """The linear colour with this chromaticity (r, g, b divided by their sum) and this luminance."""
    chroma = np.asarray(chroma, dtype=float)
    return chroma * lum / (chroma @ LUMA)


def _photo(*patches):
    """One photo's view from patches of (colour, h0, h1, pixels[, wall]): that many pixels of a wall (default 0)
    spread over h0-h1 m."""
    colours = np.concatenate([np.tile(p[0], (p[3], 1)) for p in patches])
    heights = np.concatenate([p[1] + (np.arange(p[3]) + 0.5) * (p[2] - p[1]) / p[3] for p in patches])
    walls = np.concatenate([np.full(p[3], p[4] if len(p) > 4 else 0, dtype=int) for p in patches])
    return colours, heights, walls


def test_profile_is_a_median_per_band():
    prof = ap.band_profile(_views())
    assert sorted(prof) == list(range(10))
    assert np.allclose(prof[0], DARK) and np.allclose(prof[1], BRICK)


def test_one_photo_is_enough_for_a_profile():
    views = _views([(1, 1, 1)])
    prof = ap.band_profile(views)
    assert sorted(prof) == list(range(10)) and np.allclose(prof[1], BRICK)
    assert [x["kind"] for x in ap.zones(prof, ap.glass_cells(views))] == ["storefront", "opaque", "glass"]


def test_a_photos_band_colour_is_the_median_of_its_pixels():
    # 30 dark pixels and 20 bright ones in one band: a median ignores the bright 40%, a mean would not
    photo = _photo((_grey(0.1), 0, 3, 30), (_grey(0.9), 0, 3, 20))
    assert np.allclose(ap.band_profile([photo, photo])[0], _grey(0.1))


def test_the_profile_is_the_median_across_photos_not_the_mean():
    # one photo in three sees the band bright (a reflection, a truck): the other two decide
    views = [_photo((c, 0, 3, 30)) for c in (BRICK, _grey(0.9), BRICK)]
    assert np.allclose(ap.band_profile(views)[0], BRICK)


def test_a_band_needs_20_pixels_in_a_photo_to_count():
    photo = _photo((BRICK, 0, 3, 19), (BRICK, 3, 6, 20))
    assert sorted(ap.band_profile([photo, photo])) == [1]


def test_pixels_below_the_lowest_point_are_not_a_band():
    photo = _photo((BRICK, -3, -0.1, 30), (BRICK, 0, 3, 30))
    assert sorted(ap.band_profile([photo, photo])) == [0]


def test_glass_changes_with_the_view_and_walls_do_not():
    cells = ap.glass_cells(_views())
    assert cells[1] is False and cells[2] is True and cells[4] is True


def _flicker(chroma, loglum, views=4, lum=0.2):
    """Colours alternating between two that differ by this spread of chromaticity (the three channels'
    standard deviations added) and of log-luminance."""
    colours = []
    for sign in [1, -1, 1, -1][:views]:
        c = np.array([1 / 3 + sign * chroma / 2, 1 / 3 - sign * chroma / 2, 1 / 3])
        colours.append(_swatch(c, lum * np.exp(sign * loglum)))
    return colours


def _cell_seen_as(colours):
    """glass_cells for one 6 m cell (6-12 m up) of one wall, seen once in each colour."""
    return ap.glass_cells([_photo((c, 6.0, 12.0, 30)) for c in colours])


@pytest.mark.parametrize("chroma, loglum, glass", [
    (0.14, 0.8, True),                          # colour and brightness both change with the view
    (0.14, 0.0, False), (0.0, 0.8, False),      # only one of the two does
    (0.14, 0.6, False), (0.10, 0.8, False)])    # each just under its limit (0.7 and 0.12)
def test_a_cell_is_glass_only_when_colour_and_brightness_both_change_with_the_view(chroma, loglum, glass):
    assert _cell_seen_as(_flicker(chroma, loglum)) == {1: glass}


def test_a_cell_is_judged_from_three_views_of_a_wall():
    assert _cell_seen_as(_flicker(0.2, 1.0, views=3)) == {1: True}
    assert _cell_seen_as(_flicker(0.2, 1.0, views=2)) == {}


def test_views_of_different_walls_are_not_judged_together():
    # the colour changes from photo to photo, but each photo sees a different wall: no wall has three views
    photos = [_photo((c, 6.0, 12.0, 30, wall)) for wall, c in enumerate(_flicker(0.2, 1.0, views=3))]
    assert ap.glass_cells(photos) == {}


def test_a_cell_on_several_walls_is_judged_by_the_middle_wall():
    def seen(*per_wall):   # per_wall[w]: the four colours wall w shows, one per photo
        return ap.glass_cells([_photo(*[(colours[i], 6.0, 12.0, 30, w) for w, colours in enumerate(per_wall)])
                               for i in range(4)])

    mirror, plain = _flicker(0.14, 0.8), [_grey(0.2)] * 4
    assert seen(mirror, mirror, plain) == {1: True}    # two walls change with the view, one does not
    assert seen(mirror, plain, plain) == {1: False}    # one wall does, two do not


def test_zones_storefront_body_and_glass():
    views = _views()
    z = ap.zones(ap.band_profile(views), ap.glass_cells(views))
    assert [(x["kind"], x["h0"], x["h1"]) for x in z] == [("storefront", 0.0, 3.0), ("opaque", 3.0, 12.0),
                                                           ("glass", 12.0, None)]
    assert np.allclose(z[1]["colour"], BRICK, atol=1e-3)


def test_with_too_few_views_blue_reads_as_glass():
    views = _views([(1, 1, 1), (0.5, 0.8, 1.6)])
    z = ap.zones(ap.band_profile(views), ap.glass_cells(views))
    assert [x["kind"] for x in z] == ["storefront", "opaque", "glass"]


def _bluish(lum, lead):
    """A linear colour of this luminance whose blue is `lead` above its red."""
    red = 0.02
    blue = red + lead
    return np.array([red, (lum - 0.2126 * red - 0.0722 * blue) / 0.7152, blue])


@pytest.mark.parametrize("lum, lead, kind", [
    (0.1, 0.05, "glass"), (0.1, 0.03, "opaque"),     # the rule is 0.04 up to a luminance of 0.1
    (0.5, 0.25, "glass"), (0.5, 0.15, "opaque"),     # beyond that it grows with luminance: 0.2 at 0.5
    (0.02, 0.05, "glass"), (0.02, 0.03, "opaque")])  # and it doesn't shrink below 0.04 for dark walls
def test_without_views_blue_has_to_lead_by_more_on_a_brighter_wall(lum, lead, kind):
    z = ap.zones({0: _bluish(lum, lead), 1: _bluish(lum, lead)}, {})
    assert [x["kind"] for x in z] == [kind]


def test_what_the_views_say_beats_the_blue_rule():
    def kinds(colour, glass):
        return [x["kind"] for x in ap.zones({0: colour, 1: colour}, glass)]

    assert kinds(_bluish(0.3, 0.2), {0: False}) == ["opaque"]   # blue, but the same from every view
    assert kinds(_grey(0.3), {0: True}) == ["glass"]            # not blue, but it mirrors the street


def test_thin_runs_merge_and_a_contrasting_top_becomes_the_cap():
    prof = {b: BRICK for b in range(1, 9)}
    prof[0] = DARK
    prof[4] = np.array([0.3, 0.3, 0.3])      # a 3 m grey band merges back into the brick
    prof[9] = np.array([0.02, 0.02, 0.02])   # a dark parapet on top
    z = ap.zones(prof, {})
    assert [x["kind"] for x in z] == ["storefront", "opaque", "cap"] and z[-1]["h0"] == 27.0


@pytest.mark.parametrize("contrast, kinds", [(1.65, ["opaque", "cap"]), (1.55, ["opaque"])])
def test_a_thin_top_at_least_1_6_times_darker_than_the_wall_below_is_a_cap(contrast, kinds):
    prof = {b: _grey(0.2) for b in range(9)}
    prof[9] = _grey(0.2 / contrast)
    assert [x["kind"] for x in ap.zones(prof, {})] == kinds


def test_at_most_four_zones():
    colours = [[0.02] * 3, [0.3, 0.12, 0.08], [0.1, 0.3, 0.1], [0.3, 0.3, 0.3], [0.1, 0.1, 0.4], [0.5, 0.4, 0.1]]
    prof = {}
    for i, c in enumerate(colours):
        prof[2 * i] = prof[2 * i + 1] = np.array(c)    # 6 m runs, all different
    z = ap.zones(prof, {})
    assert len(z) == 4 and z[0]["h0"] == 0.0 and z[-1]["h1"] is None


def test_no_profile_means_no_zones():
    assert ap.zones({}, {}) is None


ONE_ZONE = [("opaque", 0.0, None)]
TWO_ZONES = [("opaque", 0.0, 6.0), ("opaque", 6.0, None)]


def _two_runs(upper):
    """Zones of a wall that is grey 0.4 for 6 m and then `upper` for 6 m (nothing to tell glass by)."""
    z = ap.zones({0: _grey(0.4), 1: _grey(0.4), 2: upper, 3: upper}, {})
    return [(x["kind"], x["h0"], x["h1"]) for x in z]


@pytest.mark.parametrize("dimmer, expected", [(0.75, ONE_ZONE), (0.65, TWO_ZONES)])   # 25% and 35% less luminance
def test_zones_split_where_luminance_changes_by_more_than_30_percent(dimmer, expected):
    assert _two_runs(_grey(0.4 * dimmer)) == expected


@pytest.mark.parametrize("move, expected", [(0.04, ONE_ZONE), (0.06, TWO_ZONES)])
def test_zones_split_where_chromaticity_moves_by_more_than_0_05(move, expected):
    shifted = _swatch([1 / 3 + move / 2 ** 0.5, 1 / 3 - move / 2 ** 0.5, 1 / 3], 0.4)   # same luminance as the grey
    assert _two_runs(shifted) == expected


def _step(jump_band, ratio):
    """Bands under `jump_band` are grey 0.1; the four from it up are `ratio` times as bright."""
    return {b: _grey(0.1 if b < jump_band else 0.1 * ratio) for b in range(jump_band + 4)}


@pytest.mark.parametrize("ratio, kinds", [(1.65, ["storefront", "opaque"]), (1.55, ["opaque"])])
def test_a_storefront_ends_where_the_wall_above_is_1_6_times_as_bright(ratio, kinds):
    assert [x["kind"] for x in ap.zones(_step(1, ratio), {})] == kinds


@pytest.mark.parametrize("jump_at, kinds", [(3.0, ["storefront", "opaque"]), (9.0, ["storefront", "opaque"]),
                                            (12.0, ["opaque", "opaque"])])
def test_only_a_jump_between_3_and_9_m_up_makes_a_storefront(jump_at, kinds):
    z = ap.zones(_step(int(jump_at / 3), 2.0), {})
    assert [x["kind"] for x in z] == kinds and z[0]["h1"] == jump_at


def _banded_wall(spacing, ppm=6.0, height=30.0):
    """A straightened wall (grey rows top-down, mask) with a dark band 0.3 m thick every `spacing` metres."""
    rows = np.arange(int(height * ppm))
    grey = np.where(rows % round(spacing * ppm) < round(0.3 * ppm), 0.1, 0.6)[:, None] * np.ones((1, 60))
    return grey, np.ones_like(grey, dtype=bool)


def _edge_wall(rows, edges):
    """A wall `rows` rows tall whose only horizontal edges are `edges` {row: strength}, so its autocorrelation is
    known exactly."""
    strength = np.zeros(rows)
    for row, value in edges.items():
        strength[row] = value
    steps = np.where(np.arange(rows) % 2 == 0, strength, -strength)
    grey = np.concatenate([[0.0], np.cumsum(steps)])[:, None] * np.ones((1, 8))
    return grey, np.ones(grey.shape, dtype=bool)


def test_floor_height_needs_two_walls_to_agree():
    ppm = 6.0
    wall = _banded_wall(4.0, ppm)
    assert abs(ap.floor_height([wall, wall], ppm) - 4.0) < 0.2
    assert ap.floor_height([wall], ppm) == ap.FLOOR_DEFAULT_M
    assert ap.floor_height([], ppm) == ap.FLOOR_DEFAULT_M


def test_one_wall_seen_in_two_photos_is_one_vote():
    # a facade photographed from two spots (its repeating awnings or signs, say) can't agree with itself
    wall = _banded_wall(4.0)
    assert ap.floor_height([wall, wall], 6.0, ids=[7, 7]) == ap.FLOOR_DEFAULT_M
    assert ap.floor_height([wall, wall], 6.0, ids=[7, 9]) == pytest.approx(4.0, abs=0.01)


def test_a_wall_votes_with_the_median_of_its_photos():
    # wall 1 in three photos (4.0, 4.0, 4.4) votes 4.0 and wall 2 in one votes 4.2: the floor height is the mean
    # of two walls (4.1), not of four photos (4.15), and wall 1's stray 4.4 is outvoted by its other photos
    ppm = 20.0
    walls = [_banded_wall(4.0, ppm), _banded_wall(4.0, ppm), _banded_wall(4.4, ppm), _banded_wall(4.2, ppm)]
    assert ap.floor_height(walls, ppm, ids=[1, 1, 1, 2]) == pytest.approx(4.1, abs=0.01)


def test_a_featureless_wall_has_no_floor_height():
    flat = np.full((181, 60), 0.5)
    # texture with no repeat: its highest lag in the range is 4.0 m, at 0.18 of lag 0 (the old level was 0.1)
    texture = 0.5 + 0.02 * np.random.default_rng(27).standard_normal((181, 60))
    mask = np.ones(flat.shape, dtype=bool)
    assert ap.floor_height([(flat, mask), (flat, mask)], 6.0) == 3.5
    assert ap.floor_height([(texture, mask), (texture, mask)], 6.0) == 3.5
    assert ap.floor_height([_banded_wall(4.0), (texture, mask)], 6.0) == 3.5   # a wall with no repeat votes for nothing


def test_a_smooth_wall_has_no_floor_height():
    # darkening smoothly up the wall: no edges repeat, but the autocorrelation falls from lag 0 all through the
    # range, so its highest value in it is at the near end (2.83 m)
    shade = (0.2 + 0.6 * np.linspace(0.0, 1.0, 181) ** 2)[:, None] * np.ones((1, 60))
    mask = np.ones(shade.shape, dtype=bool)
    assert ap.floor_height([(shade, mask), (shade, mask)], 6.0) == 3.5


@pytest.mark.parametrize("dtype", [np.float64, np.float32])
def test_a_plain_gradient_has_no_floor_height(dtype):
    # every row differs from the next by the same amount, to rounding: the rounding errors repeat, the wall doesn't
    grey = (np.linspace(0.2, 0.8, 181)[:, None] * np.ones((1, 60))).astype(dtype)
    mask = np.ones(grey.shape, dtype=bool)
    assert ap.floor_height([(grey, mask), (grey, mask)], 6.0) == 3.5


@pytest.mark.parametrize("a, b, expected", [(4.0, 4.2, 4.1), (4.0, 4.3, 3.5), (3.5, 5.0, 3.5)])
def test_floor_height_walls_agree_within_a_quarter_of_a_metre(a, b, expected):
    # 0.2 m apart agree (their mean), 0.3 m and 1.5 m apart do not
    ppm = 20.0
    assert ap.floor_height([_banded_wall(a, ppm), _banded_wall(b, ppm)], ppm) == pytest.approx(expected, abs=0.01)


@pytest.mark.parametrize("spacing, expected", [(2.9, 2.9), (5.8, 5.8), (6.0, 3.5), (6.6, 3.5)])
def test_floor_height_is_searched_from_2_8_to_6_m(spacing, expected):
    # 6.0 m is the last lag in the range, so nothing after it shows it to be a peak; 6.6 m is out of it
    ppm = 20.0
    wall = _banded_wall(spacing, ppm)
    assert ap.floor_height([wall, wall], ppm) == pytest.approx(expected, abs=0.01)


def test_a_repeat_under_2_8_m_is_not_a_floor_spacing():
    # edges 2.5 m apart: that lag is out of the range, and its multiple at 5 m is too weak (0.26) to count
    wall = _edge_wall(180, {0: 1.0, 15: 1.0, 30: 1.0, 45: 1.0, 82: 1.8})
    assert ap.floor_height([wall, wall], 6.0) == 3.5


def _weak_repeat(rows, stray):
    # edges 4 m apart (at 6 px/m) and one stray edge: the autocorrelation at 4 m is a share of its value at 0
    return _edge_wall(rows, {0: 1.0, 24: 1.0, 48: 1.0, 38: stray})


def test_a_weak_repeat_has_to_stand_out_of_the_noise():
    short, long, faint = _weak_repeat(80, 1.6), _weak_repeat(180, 1.6), _weak_repeat(180, 2.0)   # 0.32, 0.35, 0.27
    assert ap.floor_height([short, short], 6.0) == 3.5    # under 3 / sqrt(80 rows) = 0.34
    assert ap.floor_height([long, long], 6.0) == 4.0      # over 3 / sqrt(180) = 0.22 and the 0.3 floor
    assert ap.floor_height([faint, faint], 6.0) == 3.5    # under that 0.3
    grey, mask = short                                    # 100 more rows with nothing measured don't make it longer
    padded = (np.vstack([grey, np.zeros((100, 8))]), np.vstack([mask, np.zeros((100, 8), dtype=bool)]))
    assert ap.floor_height([padded, padded], 6.0) == 3.5


@pytest.mark.parametrize("height, expected", [(11.0, 3.5), (13.0, 4.0)])
def test_a_wall_shorter_than_two_longest_spacings_is_not_measured(height, expected):
    # two of 6 m is 12 m: a 4 m repeat on 11 m of wall is left alone, on 13 m it is measured
    wall = _banded_wall(4.0, height=height)
    assert ap.floor_height([wall, wall], 6.0) == expected


def test_confidence_and_the_guessed_look():
    assert ap.confidence(3, 0.5) == 0.5 and ap.confidence(1, 1.0) == round(1 / 3, 3)
    d = ap.default_look()
    assert d["source"] == "guessed" and d["photos"] == 0
    assert [z["kind"] for z in d["zones"]] == ["storefront", "opaque"] and d["zones"][-1]["h1"] is None


def test_confidence_is_held_between_0_and_1():
    assert ap.confidence(6, 1.0) == 1.0    # more than three photos
    assert ap.confidence(3, 1.7) == 1.0    # a share over the whole wall
    assert ap.confidence(3, -0.2) == 0.0
    assert ap.confidence(0, 1.0) == 0.0


def test_the_guessed_look_is_a_storefront_to_4_5_m_under_a_plain_body():
    assert ap.default_look() == {
        "source": "guessed", "photos": 0, "confidence": 0.0, "floor_h": 3.5,
        "zones": [{"h0": 0.0, "h1": 4.5, "kind": "storefront", "colour": [0.32, 0.32, 0.31]},
                  {"h0": 4.5, "h1": None, "kind": "opaque", "colour": [0.42, 0.42, 0.40]}]}


def test_each_guessed_look_is_its_own_copy():
    first = ap.default_look()
    first["zones"][0]["colour"][0] = 0.0
    first["zones"].pop()
    again = ap.default_look()
    assert len(again["zones"]) == 2 and again["zones"][0]["colour"] == [0.32, 0.32, 0.31]
