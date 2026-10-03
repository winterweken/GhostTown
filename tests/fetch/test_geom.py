from shapely.geometry import LineString, MultiPolygon, Polygon

from ghosttown_fetch.geom import polygons, rings


def _area(ring):
    return 0.5 * sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))


def test_polygons_flattens_and_drops_non_polygons():
    mp = MultiPolygon([Polygon([(0, 0), (1, 0), (1, 1)]), Polygon([(5, 5), (6, 5), (6, 6)])])
    assert len(polygons(mp)) == 2
    assert polygons(LineString([(0, 0), (1, 1)])) == []
    assert polygons(None) == []


def test_polygons_repairs_a_bow_tie():
    bow = Polygon([(0, 0), (10, 10), (10, 0), (0, 10), (0, 0)])
    parts = polygons(bow)
    assert len(parts) == 2 and all(p.is_valid for p in parts)


def test_rings_orient_outer_ccw_and_holes_cw_unclosed_mm():
    poly = Polygon([(0, 0), (0, 30), (30, 30), (30, 0)], [[(10, 10), (20, 10), (20, 20), (10, 20)]])
    outer, hole = rings(poly)
    assert _area(outer) > 0 and _area(hole) < 0
    assert outer[0] != outer[-1] and len(outer) == 4
    r = rings(Polygon([(0.00049, 0), (10.0004, 0), (10, 10)]))
    assert r[0][0] == [0.0, 0.0] and r[0][1] == [10.0, 0.0]


def test_rings_drop_points_that_collapse_after_rounding():
    poly = Polygon([(0, 0), (10, 0), (10.0001, 0.0001), (10, 10), (0, 10)])
    assert len(rings(poly)[0]) == 4


def _touching(rs):
    from shapely.geometry import LinearRing

    lrs = [LinearRing(r) for r in rs]
    if not all(lr.is_simple for lr in lrs):
        return True
    return any(a.intersects(b) for i, a in enumerate(lrs) for b in lrs[i + 1:])


def test_a_courtyard_touching_the_facade_at_a_node_is_separated():
    poly = Polygon([(0, 0), (30, 0), (30, 30), (0, 30), (0, 10)], [[(0, 10), (10, 12), (10, 8)]])
    parts = polygons(poly)
    assert parts and not any(_touching(rings(p)) for p in parts)
    assert abs(sum(p.area for p in parts) - poly.area) < 0.5


def test_two_courtyards_sharing_a_node_are_separated():
    holes = [[(10, 10), (15, 10), (15, 15), (10, 15)], [(15, 15), (20, 15), (20, 20), (15, 20)]]
    poly = Polygon([(0, 0), (30, 0), (30, 30), (0, 30)], holes)
    parts = polygons(poly)
    assert parts and not any(_touching(rings(p)) for p in parts)


def test_to_local_puts_the_centre_at_the_origin():
    from shapely.geometry import Point

    from ghosttown_fetch.frame import Frame
    from ghosttown_fetch.geom import to_local

    p = to_local(Point(-79.38, 43.65), Frame(43.65, -79.38))
    assert abs(p.x) < 1e-9 and abs(p.y) < 1e-9


def test_feature_geometry_reads_geojson_and_survives_junk():
    from ghosttown_fetch.geom import feature_geometry

    good = {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [-79.38, 43.65]}}
    assert feature_geometry(good).geom_type == "Point"
    assert feature_geometry({"properties": {}}) is None
    assert feature_geometry({"geometry": {"type": "Polygon", "coordinates": "nonsense"}}) is None
    assert feature_geometry(None) is None


def test_rings_that_nearly_touch_are_separated_before_rounding_makes_them_touch():
    # The courtyard corner sits 0.4 mm inside the wall: rounded to millimetres it would land on it.
    poly = Polygon([(0, 0), (30.0004, 0), (30.0004, 30), (0, 30)], [[(10, 10), (30, 12), (10, 14)]])
    parts = polygons(poly)
    assert parts
    for p in parts:
        assert Polygon(rings(p)[0], rings(p)[1:]).is_valid and not _touching(rings(p))
