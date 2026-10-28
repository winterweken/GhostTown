import json
import pytest

# pyrefly: ignore[missing-import]
from ghosttown_fetch import assemble, providers, terrain
from ghosttown_fetch.frame import Frame
from fakes import FakeNet
from toronto_samples import square, page


def _w_poly(x0, y0, size, frame, **props):
    p0 = frame.to_lonlat(x0, y0)
    p1 = frame.to_lonlat(x0 + size, y0)
    p2 = frame.to_lonlat(x0 + size, y0 + size)
    p3 = frame.to_lonlat(x0, y0 + size)
    ring = [[p0[0], p0[1]], [p1[0], p1[1]], [p2[0], p2[1]], [p3[0], p3[1]], [p0[0], p0[1]]]
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": props}


def test_provider_lookup_and_in_box():
    assert providers.find_candidate_provider(42.317, -83.036).id == "windsor"
    assert providers.find_candidate_provider(43.589, -79.644).id == "mississauga"
    assert providers.find_candidate_provider(43.856, -79.337).id == "markham"
    assert providers.find_candidate_provider(43.256, -79.869).id == "hamilton"
    assert providers.find_candidate_provider(35.68, 139.76) is None


def test_windsor_building_height_computation():
    fn = providers.WINDSOR.buildings_spec["height_fn"]
    assert fn({"Bld_Ht_Top": 187.5, "Bld_Ht_Grd": 183.0}) == pytest.approx(4.5)
    assert fn({"Bld_Ht_Top": 12.0}) == 12.0
    assert fn({"Bld_Ht_Top": 0.2}) is None
    assert fn({"Bld_Ht_Top": "invalid"}) is None


def test_windsor_parcels_build():
    frame = Frame(42.317, -83.036)
    t = terrain.FlatTerrain()
    poly = _w_poly(0, 0, 20, frame, OBJECTID=42, LEGAL1="LOT 10 PLAN 50", STATUS="ACTIVE")
    prov = providers.WINDSOR
    els = prov.build_parcels([poly], frame, t, 150)
    assert len(els) == 1
    el = els[0]
    assert el["id"] == "windsor:parcel:42"
    assert el["kind"] == "parcel"
    assert el["name"] == "LOT 10 PLAN 50"
    assert len(el["lines"]) == 1
    assert el["lines"][0]["kind"] == "parcel"


def test_windsor_buildings_build():
    frame = Frame(42.317, -83.036)
    t = terrain.FlatTerrain()
    poly = _w_poly(0, 0, 15, frame, OBJECTID=101, Bld_Ht_Top=18.5, Bld_Ht_Grd=10.0)
    prov = providers.WINDSOR
    els = prov.build_buildings([poly], frame, t, 150)
    assert len(els) == 1
    el = els[0]
    assert el["id"] == "windsor:building:obj101"
    assert el["kind"] == "building"
    assert len(el["solids"]) == 1
    solid = el["solids"][0]
    assert solid["kind"] == "building"
    assert solid["height_source"] == "windsor_derived"
    assert solid["z1"] == pytest.approx(8.5)


def test_windsor_trees_build():
    frame = Frame(42.317, -83.036)
    t = terrain.FlatTerrain()
    pt = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-83.036, 42.317]},
        "properties": {"OBJECTID": 555}
    }
    prov = providers.WINDSOR
    els = prov.build_trees([pt], frame, t)
    assert len(els) == 1
    assert els[0]["id"] == "tree:windsor:555"
    assert els[0]["kind"] == "tree"
    assert len(els[0]["meshes"]) == 2  # trunk and crown


def test_mississauga_parcels_build():
    frame = Frame(43.589, -79.644)
    t = terrain.FlatTerrain()
    poly = _w_poly(0, 0, 25, frame, FID=1, CITY_PIN="12345678")
    prov = providers.MISSISSAUGA
    els = prov.build_parcels([poly], frame, t, 150)
    assert len(els) == 1
    assert els[0]["id"] == "mississauga:parcel:12345678"
    assert els[0]["name"] == "PIN 12345678"


def test_assemble_windsor_end_to_end():
    req = {
        "centre": {"lat": 42.317, "lon": -83.036},
        "radius_m": 150,
        "layers": ["buildings", "parcels", "trees", "roads", "water", "green", "terrain"],
        "cache_dir": "/tmp/test_cache",
        "out_dir": "/tmp/test_out",
    }
    frame = Frame(42.317, -83.036)
    bldg = _w_poly(0, 0, 15, frame, OBJECTID=1, Bld_Ht_Top=25.0, Bld_Ht_Grd=10.0)
    parcel = _w_poly(0, 0, 25, frame, OBJECTID=2, LEGAL1="CON 1 LOT 5")
    tree = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-83.036, 42.317]}, "properties": {"OBJECTID": 3}}
    park = _w_poly(30, 30, 20, frame, OBJECTID=4)
    bdy = _w_poly(-300, -300, 600, frame, OBJECTID=5)

    def dispatch(url, data):
        if "PropertyParcels" in url and "/3/" in url:
            return page(bldg)
        if "PropertyParcels" in url and "/4/" in url:
            return page(parcel)
        if "ParksEnvironment" in url and ("/2/" in url or "/3/" in url):
            return page(tree)
        if "ParksEnvironment" in url and ("/4/" in url or "/5/" in url):
            return page(park)
        if "Boundaries" in url and "/11/" in url:
            return page(bdy)
        return page()

    net = FakeNet({
        "windsor": dispatch,
        "nrcan": json.dumps({"elevation": 10.0}).encode(),
    })

    doc = assemble.assemble(req, net)
    assert doc["region"] == "windsor"
    assert any(s["key"] == "windsor" for s in doc["sources"])
    assert any(el["kind"] == "building" for el in doc["elements"])
    assert any(el["kind"] == "parcel" for el in doc["elements"])
    assert any(el["kind"] == "tree" for el in doc["elements"])
    assert any(n["text"] == "Buildings: City of Windsor." for n in doc["notes"])


def test_markham_parcels_build():
    frame = Frame(43.856, -79.337)
    t = terrain.FlatTerrain()
    poly = _w_poly(0, 0, 30, frame, OBJECTID=999)
    prov = providers.MARKHAM
    els = prov.build_parcels([poly], frame, t, 150)
    assert len(els) == 1
    assert els[0]["id"] == "markham:parcel:999"


def test_hamilton_parcels_build():
    frame = Frame(43.256, -79.869)
    t = terrain.FlatTerrain()
    poly = _w_poly(0, 0, 30, frame, OBJECTID=888)
    prov = providers.HAMILTON
    els = prov.build_parcels([poly], frame, t, 150)
    assert len(els) == 1
    assert els[0]["id"] == "hamilton:parcel:888"


def test_assemble_boundary_crossing_warning():
    req = {
        "centre": {"lat": 42.317, "lon": -83.036},
        "radius_m": 500,
        "layers": ["parcels", "terrain"],
        "cache_dir": "/tmp/test_cache",
        "out_dir": "/tmp/test_out",
    }
    frame = Frame(42.317, -83.036)
    # Boundary is only 200m across, so a 500m circle crosses it!
    bdy = _w_poly(-100, -100, 200, frame, OBJECTID=5)
    parcel = _w_poly(0, 0, 25, frame, OBJECTID=2, LEGAL1="CON 1 LOT 5")

    def dispatch(url, data):
        if "Boundaries" in url and "/11/" in url:
            return page(bdy)
        if "PropertyParcels" in url and "/4/" in url:
            return page(parcel)
        return page()

    net = FakeNet({
        "windsor": dispatch,
        "nrcan": json.dumps({"elevation": 10.0}).encode(),
    })
    doc = assemble.assemble(req, net)
    assert doc["region"] == "windsor"
    assert any("outside the City of Windsor" in n["text"] for n in doc["notes"] if n["level"] == "warn")


def test_municipal_ground_specs_cover_roads_water_green():
    assert "road" in providers.WINDSOR.ground_specs
    assert "water" in providers.WINDSOR.ground_specs
    assert "green" in providers.WINDSOR.ground_specs
    assert "sidewalk" in providers.WINDSOR.ground_specs

    assert "road" in providers.MISSISSAUGA.ground_specs
    assert "water" in providers.MISSISSAUGA.ground_specs
    assert "green" in providers.MISSISSAUGA.ground_specs

    assert "road" in providers.HAMILTON.ground_specs
    assert "water" in providers.HAMILTON.ground_specs
    assert "green" in providers.HAMILTON.ground_specs

    assert "road" in providers.MARKHAM.ground_specs
    assert "green" in providers.MARKHAM.ground_specs


def test_windsor_photo_fetch(tmp_path):
    from photo_samples import JPEG
    prov = providers.WINDSOR
    net = FakeNet({"windsor": JPEG})
    res = prov.fetch_photo(net, Frame(42.317, -83.036), 150, str(tmp_path))
    assert res is not None
    assert res["file"] == "photo.jpg"
    assert res["year"] == 2024
    assert res["source"] == "windsor"
    assert (tmp_path / "photo.jpg").read_bytes() == JPEG


def test_mississauga_photo_fallback_ontario(tmp_path):
    from photo_samples import JPEG
    prov = providers.MISSISSAUGA
    net = FakeNet({"ontario": JPEG})
    res = prov.fetch_photo(net, Frame(43.589, -79.644), 150, str(tmp_path))
    assert res is not None
    assert res["file"] == "photo.jpg"
    assert res["source"] == "ontario"
    assert (tmp_path / "photo.jpg").read_bytes() == JPEG


def test_assemble_windsor_with_photo_and_roads(tmp_path):
    from photo_samples import JPEG
    req = {
        "centre": {"lat": 42.317, "lon": -83.036},
        "radius_m": 150,
        "layers": ["parcels", "roads", "water", "photo"],
        "cache_dir": str(tmp_path / "cache"),
        "out_dir": str(tmp_path / "out"),
    }
    frame = Frame(42.317, -83.036)
    bdy = _w_poly(-300, -300, 600, frame, OBJECTID=1)
    road_line = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[-83.038, 42.317], [-83.034, 42.317]],
        },
        "properties": {"OBJECTID": 10},
    }

    def dispatch(url, data):
        if "Boundaries" in url and "/11/" in url:
            return page(bdy)
        if "Transportation" in url and "/16/" in url:
            return page(road_line)
        if "/export?" in url:
            return JPEG
        return page()

    net = FakeNet({
        "windsor": dispatch,
    })
    doc = assemble.assemble(req, net)
    assert doc["region"] == "windsor"
    assert doc["photo"]["file"] == "photo.jpg"
    assert doc["photo"]["year"] == 2024
    assert any(n["code"] == "windsor_photo" and n["level"] == "info" for n in doc["notes"])
    assert (tmp_path / "out" / "photo.jpg").is_file()



