"""One material per kind, named 'Context - <Label>'. Exporters carry these names over as layers or
materials, which is what Revit (Object Styles › Imported Objects) and other BIM tools see."""
import bpy

PREFIX = "Context - "
LABELS = {
    "building": "Building", "building_on_site": "Building (on site)", "building_guessed": "Building (height guessed)",
    "parcel": "Parcel", "parcel_on_site": "Parcel (site)",
    "ground": "Ground", "road": "Road", "sidewalk": "Sidewalk", "parking": "Parking",
    "rail": "Rail", "green": "Green", "water": "Water", "tree": "Tree",
}
COLOURS = {
    "building": (0.86, 0.86, 0.84), "building_on_site": (0.85, 0.20, 0.20), "building_guessed": (0.95, 0.62, 0.25),
    "parcel": (0.55, 0.25, 0.60), "parcel_on_site": (0.75, 0.10, 0.55),
    "ground": (0.80, 0.76, 0.66), "road": (0.33, 0.33, 0.35), "sidewalk": (0.70, 0.70, 0.70),
    "parking": (0.52, 0.52, 0.55), "rail": (0.45, 0.32, 0.22), "green": (0.45, 0.66, 0.35),
    "water": (0.30, 0.52, 0.80), "tree": (0.18, 0.42, 0.20),
}


def material_name(kind):
    return PREFIX + LABELS[kind]


def get_material(kind):
    name = material_name(kind)
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    rgba = COLOURS[kind] + (1.0,)
    mat.diffuse_color = rgba
    if mat.node_tree is not None:
        for node in mat.node_tree.nodes:
            if node.bl_idname == "ShaderNodeBsdfPrincipled":
                node.inputs["Base Color"].default_value = rgba
                node.inputs["Roughness"].default_value = 0.75
    return mat
