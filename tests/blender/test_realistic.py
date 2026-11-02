import bpy

from ghosttown import realistic

ALL = list(dict.fromkeys(realistic.SURFACES.values())) + [realistic.EARTH]


def test_every_surface_has_a_named_procedural_material():
    for surface in ALL:
        mat = realistic.get_material(surface)
        assert mat.name == "Ghost Town Realistic · " + surface
        nodes = mat.node_tree.nodes
        assert not any(n.bl_idname == "ShaderNodeTexImage" for n in nodes)
        out = next(n for n in nodes if n.bl_idname == "ShaderNodeOutputMaterial")
        assert out.inputs["Surface"].is_linked
        assert any(n.bl_idname == "ShaderNodeNewGeometry" for n in nodes)   # world-space position drives it


def test_surfaces_cover_the_seven_ground_kinds():
    assert realistic.SURFACES == {"ground": "Open ground", "green": "Grass", "road": "Asphalt",
                                  "sidewalk": "Concrete", "parking": "Lot asphalt", "rail": "Ballast",
                                  "water": "Water"}


def test_an_existing_material_is_reused_as_the_user_left_it():
    mat = realistic.get_material("Grass")
    mat.diffuse_color = (1.0, 0.0, 1.0, 1.0)
    assert realistic.get_material("Grass") is mat and tuple(mat.diffuse_color) == (1.0, 0.0, 1.0, 1.0)
    assert sum(m.name.startswith("Ghost Town Realistic · Grass") for m in bpy.data.materials) == 1


def test_water_is_glossy_and_viewport_colours_are_not_the_plain_ones():
    water = realistic.get_material("Water")
    bsdf = next(n for n in water.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    assert bsdf.inputs["Roughness"].default_value <= 0.1
    for surface in ALL:
        assert tuple(realistic.get_material(surface).diffuse_color)[3] == 1.0


def test_the_earth_reads_depth_from_the_geometry_attribute():
    nodes = realistic.get_material(realistic.EARTH).node_tree.nodes
    assert any(n.bl_idname == "ShaderNodeAttribute" and n.attribute_type == "GEOMETRY"
               and n.attribute_name == realistic.DEPTH_ATTRIBUTE for n in nodes)
