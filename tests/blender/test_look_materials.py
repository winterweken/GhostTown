import math
import os
import tempfile

import bpy
import numpy as np

from ghosttown import materials

BRICK, GLASS = (0.30, 0.12, 0.08), (0.20, 0.40, 0.60)


def _close(rgba, rgb):
    return all(abs(a - b) < 1e-6 for a, b in zip(tuple(rgba)[:3], rgb))


def test_the_group_sits_in_front_of_base_color_and_roughness():
    mat = materials.get_material("building")
    node = materials.ensure_street_look(mat, "building")
    bsdf = next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    assert node.node_tree.name == materials.LOOK_GROUP and mat.name == "Context - Building"
    assert bsdf.inputs["Base Color"].links[0].from_node == node
    assert bsdf.inputs["Roughness"].links[0].from_node == node
    assert _close(node.inputs["Plain Color"].default_value, materials.COLOURS["building"])


def test_adding_it_twice_changes_nothing():
    mat = materials.get_material("building")
    materials.ensure_street_look(mat, "building")
    count = len(mat.node_tree.nodes)
    materials.ensure_street_look(mat, "building")
    assert len(mat.node_tree.nodes) == count
    assert len([g for g in bpy.data.node_groups if g.name.startswith(materials.LOOK_GROUP)]) == 1


def test_switches_reach_every_material_with_the_group():
    mats = [materials.get_material(k) for k in ("building", "building_guessed")]
    for mat, kind in zip(mats, ("building", "building_guessed")):
        materials.ensure_street_look(mat, kind)
    materials.set_street_look(look=False, brightness=0.8)
    for mat in mats:
        node = mat.node_tree.nodes[materials.LOOK_NODE]
        assert node.inputs["Look"].default_value == 0.0 and abs(node.inputs["Brightness"].default_value - 0.8) < 1e-6


def test_get_material_keeps_the_group_and_refreshes_its_plain_colour():
    mat = materials.get_material("building")
    node = materials.ensure_street_look(mat, "building")
    node.inputs["Plain Color"].default_value = (1, 0, 0, 1)
    materials.get_material("building")
    assert mat.node_tree.nodes.get(materials.LOOK_NODE) == node
    assert _close(node.inputs["Plain Color"].default_value, materials.COLOURS["building"])


def test_the_detail_material_has_a_stable_name():
    assert materials.get_material("facade_detail").name == "Context - Facade detail"


def _box_with_look(on):
    verts = [(-10, 0, 0), (10, 0, 0), (10, 10, 0), (-10, 10, 0), (-10, 0, 30), (10, 0, 30), (10, 10, 30), (-10, 10, 30)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me = bpy.data.meshes.new("box")
    me.from_pydata(verts, [], faces)
    mat = materials.get_material("building")
    materials.ensure_street_look(mat, "building")
    me.materials.append(mat)
    ob = bpy.data.objects.new("box", me)
    bpy.context.scene.collection.objects.link(ob)
    zones = [(3.0, 1, (0.03, 0.03, 0.03)), (12.0, 2, BRICK), (1e5, 3, GLASS), (1e5, 0, (0, 0, 0))]
    ob["gt_look_on"] = 1.0 if on else 0.0
    ob["gt_look_base_z"], ob["gt_look_floor_h"] = 0.0, 3.5
    ob["gt_look_bay_glass"], ob["gt_look_bay_opaque"] = 1.5, 3.0
    for n, (top, kind, colour) in enumerate(zones, 1):
        ob[f"gt_look_z{n}_top"], ob[f"gt_look_z{n}_kind"], ob[f"gt_look_z{n}_colour"] = top, float(kind), list(colour)
    return ob


def _render_rows(heights):
    """Mean rendered colour of the box's south face at each height, seen square-on in an orthographic view
    lit by a plain white sky."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 8
    scene.cycles.device = "CPU"
    scene.view_settings.view_transform = "Standard"   # plain sRGB, so hues are not compressed
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 40, 80, 100
    world = bpy.data.worlds.new("white")
    world.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
    scene.world = world
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type, cam.data.ortho_scale = "ORTHO", 32.0
    cam.location, cam.rotation_euler = (0, -50, 15), (math.pi / 2, 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    path = os.path.join(tempfile.mkdtemp(), "look.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    px = np.array(bpy.data.images.load(path).pixels[:]).reshape(80, 40, 4)   # rows from the bottom
    return [px[int((h + 1.0) / 32.0 * 80), 12:28, :3].mean(axis=0) for h in heights]


def test_zones_reach_the_render():
    _box_with_look(on=True)
    brick, glass = _render_rows([8.0, 20.0])
    assert brick[0] > brick[2] * 1.3      # brick reads red
    assert glass[2] > glass[0] * 1.3      # glass reads blue


def test_without_a_look_the_plain_colour_shows():
    _box_with_look(on=False)
    row, = _render_rows([20.0])
    assert abs(row[0] - row[2]) < 0.05


# Reviewer's tests: probe the exact shader output values by routing Color or Roughness into an Emission shader
PLAIN = materials.COLOURS["building"]
SHOP, CAP = (0.12, 0.10, 0.09), (0.45, 0.45, 0.43)
DARK = materials.DARK_GLASS
ZONES = [(3.0, 1, SHOP), (12.0, 2, BRICK), (24.0, 3, GLASS), (1e5, 4, CAP)]
PX = 0.05          # metres per pixel: a 40 m view over 800 px


def _building(zones=ZONES, base_z=0.0, height=30.0, x0=-10.0, x1=10.0, on=1.0, name="b"):
    z0, z1 = base_z, base_z + height
    verts = [(x0, 0, z0), (x1, 0, z0), (x1, 10, z0), (x0, 10, z0), (x0, 0, z1), (x1, 0, z1), (x1, 10, z1), (x0, 10, z1)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob["gt_look_on"], ob["gt_look_base_z"], ob["gt_look_floor_h"] = on, base_z, 3.5
    ob["gt_look_bay_glass"], ob["gt_look_bay_opaque"] = 1.5, 3.0
    zones = list(zones) + [(1e5, 0, (0, 0, 0))] * (4 - len(zones))
    for n, (top, kind, colour) in enumerate(zones, 1):
        ob[f"gt_look_z{n}_top"], ob[f"gt_look_z{n}_kind"], ob[f"gt_look_z{n}_colour"] = top, float(kind), list(colour)
    return ob


def _probe(ob, channel):
    """Give the building a material that shows one output of the Street Look group, unlit."""
    mat = bpy.data.materials.new("probe " + channel)
    tree = mat.node_tree
    tree.nodes.clear()
    group = tree.nodes.new("ShaderNodeGroup")
    group.name = materials.LOOK_NODE            # so set_street_look reaches it
    group.node_tree = materials.street_look_group()
    group.inputs["Plain Color"].default_value = PLAIN + (1.0,)
    emit, out = tree.nodes.new("ShaderNodeEmission"), tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(group.outputs[channel], emit.inputs["Color"])
    tree.links.new(emit.outputs[0], out.inputs["Surface"])
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    return group


def _scene():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples, scene.cycles.device = 16, "CPU"
    scene.cycles.pixel_filter_type, scene.cycles.filter_width = "BOX", 1.0
    scene.cycles.use_denoising = False
    scene.render.resolution_x = scene.render.resolution_y = 800
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format, scene.render.image_settings.color_depth = "OPEN_EXR", "32"
    world = bpy.data.worlds.new("black")
    world.node_tree.nodes["Background"].inputs[0].default_value = (0, 0, 0, 1)
    scene.world = world
    return scene


def _shot(look_at_z=15.0, top=False):
    scene = bpy.context.scene
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type, cam.data.ortho_scale = "ORTHO", 40.0
    if top:
        cam.location, cam.rotation_euler = (0, 5, 80), (0, 0, 0)
    else:
        cam.location, cam.rotation_euler = (0, -50, look_at_z), (math.pi / 2, 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    path = os.path.join(tempfile.mkdtemp(), "probe.exr")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(path)
    px = np.array(img.pixels[:]).reshape(800, 800, 4)[:, :, :3]    # rows from the bottom
    bpy.data.images.remove(img)
    bpy.data.objects.remove(cam)
    return px


def _row(px, h, look_at_z=15.0):
    return px[int((h - (look_at_z - 20.0)) / PX), 200:600]      # the 20 m wide building


def _coverage(row, ch, ref, dark):
    """The share of a row (by length) that sits at the dark value rather than the reference."""
    return float(np.mean((ref - row[:, ch]) / (ref - dark)))


def _runs(row, ch, ref, dark):
    is_dark = (ref - row[:, ch]) / (ref - dark) > 0.5
    return int(np.sum(is_dark[1:] & ~is_dark[:-1]) + is_dark[0])


def _setup(channel="Color", **kw):
    _scene()
    ob = _building(**kw)
    group = _probe(ob, channel)
    return ob, group


B = 1.15


def test_zone_kinds_look_like_what_they_are():
    _setup()
    px = _shot()
    # storefront: dark glazing over 88% of every 3 m bay, below the fascia
    row = _row(px, 1.0)
    assert abs(_coverage(row, 0, SHOP[0] * B, DARK[0] * B) - 0.88) < 0.04
    # opaque: a window across 60% of every 3 m bay, at mid-floor
    row = _row(px, 8.925)
    assert abs(_coverage(row, 0, BRICK[0] * B, DARK[0] * B) - 0.58) < 0.04 and _runs(row, 0, BRICK[0] * B, DARK[0] * B) == 8
    row = _row(px, 8.0)                                                     # floor_frac 0.29: wall between window rows
    assert abs(_coverage(row, 0, BRICK[0] * B, DARK[0] * B)) < 0.02
    # glass: a 7 cm mullion every 1.5 m; a spandrel at the foot of every floor
    row = _row(px, 20.0)
    assert abs(_coverage(row, 2, GLASS[2] * B, DARK[2] * B) - 13 * 0.07 / 20) < 0.01
    assert abs(row[:, 2].max() - GLASS[2] * B) < 1e-3
    row = _row(px, 17.85)
    assert abs(row[:, 2].max() - GLASS[2] * B * 0.45) < 1e-3
    # a cap is flat colour
    row = _row(px, 27.0)
    assert np.allclose(row, np.array(CAP) * B, atol=1e-3)


def test_roughness_follows_the_kind():
    _setup("Roughness")
    px = _shot()
    rough = lambda h: _row(px, h)[:, 0]
    assert abs(rough(27.0) - 0.8).max() < 1e-3                       # cap
    assert abs(rough(8.0) - 0.85).max() < 1e-3                       # wall between windows
    assert abs(rough(8.925).min() - 0.10) < 1e-3                     # a window is glossy
    assert abs(rough(20.0).min() - 0.03) < 1e-3 and abs(rough(20.0).max() - 0.58) < 1e-3   # glass: smooth, mullions rough
    assert abs(rough(1.0).min() - 0.05) < 1e-3                       # shop glazing


def test_zone_heights_are_measured_from_the_lowest_point():
    _setup(base_z=5.0, zones=[(3.0, 1, SHOP), (12.0, 2, BRICK), (1e5, 3, GLASS)])
    px = _shot(look_at_z=20.0)
    assert abs(_row(px, 5.0 + 8.0, 20.0)[:, 0].max() - BRICK[0] * B) < 1e-3
    assert abs(_row(px, 5.0 + 20.0, 20.0)[:, 2].max() - GLASS[2] * B) < 1e-3


def test_the_switches_reach_the_picture():
    ob, group = _setup(zones=[(1e5, 2, BRICK)])
    px = _shot()
    assert abs(_row(px, 8.0)[:, 0].max() - BRICK[0] * B) < 1e-3
    materials.set_street_look(brightness=0.5)
    assert abs(_row(_shot(), 8.0)[:, 0].max() - BRICK[0] * 0.5) < 1e-3
    materials.set_street_look(look=False)
    assert np.allclose(_row(_shot(), 8.0), PLAIN, atol=1e-3)
    materials.set_street_look(look=True)
    ob["gt_look_on"] = 0.0
    assert np.allclose(_row(_shot(), 8.0), PLAIN, atol=1e-3)


def test_roofs_keep_the_plain_colour():
    _setup()
    px = _shot(top=True)
    assert np.allclose(px[400, 400], PLAIN, atol=1e-3)


def test_one_material_gives_each_building_its_own_look():
    _scene()
    a = _building(zones=[(1e5, 2, BRICK)], x0=-10, x1=-1, name="a")
    b = _building(zones=[(1e5, 2, (0.05, 0.40, 0.08))], x0=1, x1=10, name="b")
    _probe(a, "Color")
    b.data.materials.clear()
    b.data.materials.append(a.data.materials[0])
    px = _shot()
    row = _row(px, 8.0)
    assert abs(row[:190, 0].max() - BRICK[0] * B) < 1e-3 and abs(row[210:, 1].max() - 0.40 * B) < 1e-3


def test_the_interface_defaults():
    node = materials.ensure_street_look(materials.get_material("building"), "building")
    assert node.inputs["Look"].default_value == 1.0 and abs(node.inputs["Brightness"].default_value - 1.15) < 1e-6


def test_every_building_material_carries_the_group_with_its_own_plain_colour():
    names = {"building": "Context - Building", "building_on_site": "Context - Building (on site)",
             "building_guessed": "Context - Building (height guessed)"}
    assert set(materials.BUILDING_MATERIALS) == set(names)
    for kind in materials.BUILDING_MATERIALS:
        mat = materials.get_material(kind)
        node = materials.ensure_street_look(mat, kind)
        bsdf = next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
        assert mat.name == names[kind]
        assert all(abs(a - b) < 1e-6 for a, b in zip(node.inputs["Plain Color"].default_value, materials.COLOURS[kind] + (1.0,)))
        assert all(abs(a - b) < 1e-6 for a, b in zip(bsdf.inputs["Base Color"].default_value, materials.COLOURS[kind] + (1.0,)))
        assert abs(bsdf.inputs["Roughness"].default_value - materials.PLAIN_ROUGHNESS) < 1e-6
