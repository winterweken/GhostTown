import numpy as np

from ghosttown_fetch import appearance as ap

DARK = np.array([0.03, 0.03, 0.035])
BRICK = np.array([0.30, 0.12, 0.08])
GLASS = np.array([0.25, 0.40, 0.55])
FACTORS = [(1, 1, 1), (3.52, 2.2, 1.32), (0.5, 0.8, 1.6), (0.15, 0.15, 0.15)]   # glass seen from four places


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


def test_profile_is_a_median_per_band():
    prof = ap.band_profile(_views())
    assert sorted(prof) == list(range(10))
    assert np.allclose(prof[0], DARK) and np.allclose(prof[1], BRICK)


def test_glass_changes_with_the_view_and_walls_do_not():
    cells = ap.glass_cells(_views())
    assert cells[1] is False and cells[2] is True and cells[4] is True


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


def test_thin_runs_merge_and_a_contrasting_top_becomes_the_cap():
    prof = {b: BRICK for b in range(1, 9)}
    prof[0] = DARK
    prof[4] = np.array([0.3, 0.3, 0.3])      # a 3 m grey band merges back into the brick
    prof[9] = np.array([0.02, 0.02, 0.02])   # a dark parapet on top
    z = ap.zones(prof, {})
    assert [x["kind"] for x in z] == ["storefront", "opaque", "cap"] and z[-1]["h0"] == 27.0


def test_at_most_four_zones():
    colours = [[0.02] * 3, [0.3, 0.12, 0.08], [0.1, 0.3, 0.1], [0.3, 0.3, 0.3], [0.1, 0.1, 0.4], [0.5, 0.4, 0.1]]
    prof = {}
    for i, c in enumerate(colours):
        prof[2 * i] = prof[2 * i + 1] = np.array(c)    # 6 m runs, all different
    z = ap.zones(prof, {})
    assert len(z) == 4 and z[0]["h0"] == 0.0 and z[-1]["h1"] is None


def test_no_profile_means_no_zones():
    assert ap.zones({}, {}) is None


def test_floor_height_needs_two_walls_to_agree():
    ppm = 6.0
    rows = np.arange(int(30 * ppm))
    grey = np.where(((rows / ppm) % 4.0) < 0.3, 0.1, 0.6)[:, None] * np.ones((1, 60))
    mask = np.ones_like(grey, dtype=bool)
    assert abs(ap.floor_height([(grey, mask), (grey, mask)], ppm) - 4.0) < 0.2
    assert ap.floor_height([(grey, mask)], ppm) == ap.FLOOR_DEFAULT_M
    assert ap.floor_height([], ppm) == ap.FLOOR_DEFAULT_M


def test_confidence_and_the_guessed_look():
    assert ap.confidence(3, 0.5) == 0.5 and ap.confidence(1, 1.0) == round(1 / 3, 3)
    d = ap.default_look()
    assert d["source"] == "guessed" and d["photos"] == 0
    assert [z["kind"] for z in d["zones"]] == ["storefront", "opaque"] and d["zones"][-1]["h1"] is None
