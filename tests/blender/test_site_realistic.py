import json
import math
import tempfile

import bpy
import numpy as np

from ghosttown import scene_build, site_realistic
from ghosttown.ghosttown_fetch import GROUND_KINDS
from helpers import drum_doc, mesh_arrays, open_only_at_the_top


def drum_site(**kw):
    folder = tempfile.mkdtemp()
    return scene_build.build(bpy.context.scene, drum_doc(**kw), folder=folder)


def test_the_drum_is_closed_and_meets_the_ground_at_the_rim():
    root = drum_site()
    earth = site_realistic.make_earth(root)
    verts, faces = mesh_arrays(earth)
    assert open_only_at_the_top(verts, faces)                    # wall + base; the ground pieces cover the top
    r = root["radius_m"]
    for a in np.linspace(0, 2 * np.pi, 37)[:-1]:
        near = [z for x, y, z in verts
                if abs((math.atan2(y, x) - a + math.pi) % (2 * math.pi) - math.pi) < 0.004]
        top = max(near)
        assert abs(top - 0.02 * r * math.cos(a)) < 0.05          # the plane z = 0.02 x at the rim


def test_the_base_is_flat_fifteen_metres_below_the_lowest_rim_point():
    root = drum_site()
    verts, _ = mesh_arrays(site_realistic.make_earth(root))
    bottom = min(z for *_, z in verts)
    assert abs(bottom - (-0.02 * root["radius_m"] - 15.0)) < 0.05
    assert max(z for *_, z in verts if z < bottom + 1.0) - bottom < 1e-4          # the base ring is flat


def test_one_earth_per_site_recorded_for_removal():
    root = drum_site()
    site_realistic.make_earth(root); earth = site_realistic.make_earth(root)
    assert [o for o in root.all_objects if o.get("ctx_kind") == "earth"] == [earth]
    name = earth.name
    assert name in json.loads(root["ctx_objects"]) and earth.material_slots[0].material.name.endswith("Earth")
    site_realistic.remove_earth(root)
    assert site_realistic.find(root, "earth") is None and name not in json.loads(root["ctx_objects"])
    assert not [m for m in bpy.data.meshes if m.name.startswith("Earth")]


def test_a_gap_in_the_ground_is_bridged_and_no_ground_is_flat():
    root = drum_site()
    bpy.data.objects.remove(next(o for o in root.all_objects if o.get("ctx_kind") == "green"))
    assert open_only_at_the_top(*mesh_arrays(site_realistic.make_earth(root)))
    for ob in [o for o in root.all_objects if o.get("ctx_kind") in GROUND_KINDS]:
        bpy.data.objects.remove(ob)
    verts, _ = mesh_arrays(site_realistic.make_earth(root))
    assert abs(max(z for *_, z in verts) - root["ground_at_centre_m"]) < 1e-4


def test_the_earth_carries_depth_below_the_rim_and_is_named_for_the_site():
    root = drum_site()
    earth = site_realistic.make_earth(root)
    assert earth.name == "Earth · " + root["ctx_label"] and earth["ctx_id"] == "earth"
    attribute = earth.data.attributes["gt_depth"]
    assert attribute.domain == "POINT" and attribute.data_type == "FLOAT"
    depth = np.array([d.value for d in attribute.data])
    z = np.array([v.co.z for v in earth.data.vertices])
    n = len(z) // 2
    assert np.allclose(depth[:n], 0.0) and np.allclose(depth[n:], z[:n] - z[n:])
    assert np.allclose(z[n:], z[n:].min())


def test_the_wall_faces_outward_and_the_base_faces_down():
    earth = site_realistic.make_earth(drum_site())
    assert min(p.normal.z for p in earth.data.polygons) < -0.99
    assert all(p.normal.to_2d().dot(p.center.to_2d()) > 0 for p in earth.data.polygons if abs(p.normal.z) < 0.5)


def test_the_ring_helper_gives_about_a_vertex_a_metre_and_at_least_sixty_four():
    root = drum_site()
    angles = site_realistic.ring_angles(root)
    assert len(angles) == max(64, math.ceil(2 * math.pi * root["radius_m"])) and angles[0] == 0.0
    assert len(site_realistic.make_earth(root).data.vertices) == 2 * len(angles)
    small = drum_site(radius=5.0)
    assert len(site_realistic.ring_angles(small)) == 64
    assert len(site_realistic.make_earth(small).data.vertices) == 128


def test_removing_the_site_removes_its_earth():
    root = drum_site()
    site_realistic.make_earth(root)
    scene_build.remove(root, bpy.context.scene)
    assert not [o for o in bpy.data.objects if o.get("ctx_kind") == "earth"]
    assert not [m for m in bpy.data.meshes if m.name.startswith("Earth")]
