import ghosttown_fetch as cf


def test_version_and_tool():
    assert cf.__version__ == "0.3.0"
    assert cf.TOOL == "ghosttown 0.3.0"
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


def test_the_name_people_read_is_ghost_town():
    # "GhostTown" as one word is only for identifiers: class names, the User-Agent token and the repo URL.
    import re
    from pathlib import Path

    allowed = re.compile(r"class GhostTown|GhostTown(Settings|Result|Preferences)|USER_AGENT|winterweken/GhostTown")
    root = Path(__file__).resolve().parents[2]
    offenders = []
    for path in [*sorted((root / "ghosttown").rglob("*.py")), root / "ghosttown" / "blender_manifest.toml",
                 root / "CREDITS.md", root / "pyproject.toml"]:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "GhostTown" in line and not allowed.search(line):
                offenders.append(f"{path.relative_to(root)}:{number}")
    assert offenders == []


def test_messages_use_the_brand_name():
    from ghosttown_fetch import context as ctx

    assert "Ghost Town reads schema 1" in ctx.validate({"schema": 9})[0]


def test_mapillary_is_named_and_credited():
    assert cf.SOURCE_NAMES["mapillary"] == "Mapillary"
    assert cf.CREDITS["mapillary"] == "Street photos © Mapillary contributors, CC BY-SA 4.0"
    assert cf.LOOK_SCHEMA == 1
