import ghosttown_fetch as cf


def test_version_and_tool():
    assert cf.__version__ == "0.1.0"
    assert cf.TOOL == "ghosttown 0.1.0"
    assert cf.SCHEMA == 1


def test_kinds_are_unique_and_grouped():
    assert len(cf.KINDS) == len(set(cf.KINDS)) == 13
    assert set(cf.GROUND_KINDS) <= set(cf.KINDS)
    assert set(cf.BUILDING_KINDS) <= set(cf.KINDS)
    assert "ground" in cf.GROUND_KINDS


def test_every_source_has_a_name_and_credit():
    assert set(cf.SOURCE_NAMES) == set(cf.CREDITS)
    assert cf.CREDITS["osm"] == "© OpenStreetMap contributors"


def test_city_of_toronto_and_nrcan_are_credited():
    assert cf.SOURCE_NAMES["toronto"] == "City of Toronto"
    assert cf.CREDITS["toronto"] == "Contains information licensed under the Open Government Licence – Toronto"
    assert cf.SOURCE_NAMES["nrcan"] == "Natural Resources Canada"
    assert cf.CREDITS["nrcan"] == "Contains information licensed under the Open Government Licence – Canada"
