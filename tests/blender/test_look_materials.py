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
