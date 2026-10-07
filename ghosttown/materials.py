"""One material per kind, named 'Context - <Label>'. Exporters carry these names over as layers or
materials, which is what Revit (Object Styles › Imported Objects) and other BIM tools see.

Street Look adds one shared node group in front of the building materials' Base Color and Roughness. It
reads each building's gt_look_* custom properties, so one material renders every building differently while
its name, and the plain colour exporters read, stay the same."""
import bpy

PREFIX = "Context - "
LABELS = {
    "building": "Building", "building_on_site": "Building (on site)", "building_guessed": "Building (height guessed)",
    "parcel": "Parcel", "parcel_on_site": "Parcel (site)",
    "ground": "Ground", "road": "Road", "sidewalk": "Sidewalk", "parking": "Parking",
    "rail": "Rail", "green": "Green", "water": "Water", "tree": "Tree",
    "facade_detail": "Facade detail",
}
COLOURS = {
    "building": (0.86, 0.86, 0.84), "building_on_site": (0.85, 0.20, 0.20), "building_guessed": (0.95, 0.62, 0.25),
    "parcel": (0.55, 0.25, 0.60), "parcel_on_site": (0.75, 0.10, 0.55),
    "ground": (0.80, 0.76, 0.66), "road": (0.33, 0.33, 0.35), "sidewalk": (0.70, 0.70, 0.70),
    "parking": (0.52, 0.52, 0.55), "rail": (0.45, 0.32, 0.22), "green": (0.45, 0.66, 0.35),
    "water": (0.30, 0.52, 0.80), "tree": (0.18, 0.42, 0.20),
    "facade_detail": (0.08, 0.085, 0.09),
}

LOOK_GROUP = "Ghost Town · Street Look"
LOOK_NODE = "Ghost Town Street Look"
BUILDING_MATERIALS = ("building", "building_on_site", "building_guessed")
KIND_CODES = {"storefront": 1, "opaque": 2, "glass": 3, "cap": 4}
MAX_ZONES = 4
DARK_GLASS = (0.03, 0.035, 0.04)
PLAIN_ROUGHNESS = 0.75


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
                node.inputs["Roughness"].default_value = PLAIN_ROUGHNESS
        look = mat.node_tree.nodes.get(LOOK_NODE)
        if look is not None:
            look.inputs["Plain Color"].default_value = rgba
    return mat


def street_look_group():
    """The shared node group: Plain Color, Look (0 or 1) and Brightness in; Color and Roughness out."""
    group = bpy.data.node_groups.get(LOOK_GROUP)
    if group is not None:
        return group
    group = bpy.data.node_groups.new(LOOK_GROUP, "ShaderNodeTree")
    face = group.interface
    face.new_socket("Plain Color", in_out="INPUT", socket_type="NodeSocketColor")
    face.new_socket("Look", in_out="INPUT", socket_type="NodeSocketFloat").default_value = 1.0
    face.new_socket("Brightness", in_out="INPUT", socket_type="NodeSocketFloat").default_value = 1.15
    face.new_socket("Color", in_out="OUTPUT", socket_type="NodeSocketColor")
    face.new_socket("Roughness", in_out="OUTPUT", socket_type="NodeSocketFloat")
    _build_street_look(group)
    return group


def _build_street_look(group):
    nodes, links = group.nodes, group.links
    gin, gout = nodes.new("NodeGroupInput"), nodes.new("NodeGroupOutput")

    def feed(value, socket):
        if isinstance(value, (int, float)):
            socket.default_value = value
        elif isinstance(value, tuple):
            socket.default_value = (*value, 1.0) if len(value) == 3 else value
        else:
            links.new(value, socket)

    def math(op, a, b=None):
        node = nodes.new("ShaderNodeMath")
        node.operation = op
        feed(a, node.inputs[0])
        if b is not None:
            feed(b, node.inputs[1])
        return node.outputs[0]

    def equals(a, value):
        node = nodes.new("ShaderNodeMath")
        node.operation = "COMPARE"
        feed(a, node.inputs[0])
        node.inputs[1].default_value = value
        node.inputs[2].default_value = 0.25
        return node.outputs[0]

    def mix(fac, a, b):
        node = nodes.new("ShaderNodeMix")
        node.data_type = "RGBA"
        feed(fac, node.inputs["Factor"])
        feed(a, node.inputs["A"])
        feed(b, node.inputs["B"])
        return node.outputs["Result"]

    def blend(fac, a, b):
        """a where fac is 0, b where fac is 1, for numbers."""
        return math("ADD", math("MULTIPLY", a, math("SUBTRACT", 1.0, fac)), math("MULTIPLY", b, fac))

    def scale(colour, factor):
        node = nodes.new("ShaderNodeVectorMath")
        node.operation = "SCALE"
        feed(colour, node.inputs[0])
        feed(factor, node.inputs["Scale"])
        return node.outputs[0]

    def attr(name, output="Fac"):
        node = nodes.new("ShaderNodeAttribute")
        node.attribute_type = "OBJECT"
        node.attribute_name = name
        return node.outputs[output]

    def between(x, lo, hi):
        return math("MULTIPLY", math("GREATER_THAN", x, lo), math("LESS_THAN", x, hi))

    geometry = nodes.new("ShaderNodeNewGeometry")
    pos = nodes.new("ShaderNodeSeparateXYZ")
    links.new(geometry.outputs["Position"], pos.inputs[0])
    nrm = nodes.new("ShaderNodeSeparateXYZ")
    links.new(geometry.outputs["Normal"], nrm.inputs[0])
    # distance along a wall: the position on the wall's horizontal tangent (-ny, nx); height above its base
    along = math("SUBTRACT", math("MULTIPLY", pos.outputs[1], nrm.outputs[0]), math("MULTIPLY", pos.outputs[0], nrm.outputs[1]))
    h = math("SUBTRACT", pos.outputs[2], attr("gt_look_base_z"))
    floor_frac = math("FRACT", math("DIVIDE", h, math("MAXIMUM", attr("gt_look_floor_h"), 1.0)))
    bay_glass = math("MAXIMUM", attr("gt_look_bay_glass"), 0.5)
    bay_opaque = math("MAXIMUM", attr("gt_look_bay_opaque"), 0.5)
    spandrel = math("LESS_THAN", floor_frac, 0.2)
    mullion = math("LESS_THAN", math("FRACT", math("DIVIDE", along, bay_glass)), math("DIVIDE", 0.07, bay_glass))
    window = math("MULTIPLY", between(math("FRACT", math("DIVIDE", along, bay_opaque)), 0.2, 0.8),
                  between(floor_frac, 0.3, 0.82))
    shop_top = math("MINIMUM", 4.2, math("SUBTRACT", attr("gt_look_z1_top"), 0.6))
    shopfront = math("MULTIPLY", between(math("FRACT", math("DIVIDE", along, 3.0)), 0.06, 0.94), between(h, 0.4, shop_top))

    colour = gin.outputs["Plain Color"]
    rough = PLAIN_ROUGHNESS
    bottom = -1.0e5
    for n in range(1, MAX_ZONES + 1):
        top = attr(f"gt_look_z{n}_top")
        kind = attr(f"gt_look_z{n}_kind")
        c = attr(f"gt_look_z{n}_colour", "Color")
        inside = math("MULTIPLY", math("SUBTRACT", 1.0, math("LESS_THAN", h, bottom)), math("LESS_THAN", h, top))
        is_store, is_opaque, is_glass = equals(kind, 1.0), equals(kind, 2.0), equals(kind, 3.0)
        glass_c = mix(mullion, mix(spandrel, c, scale(c, 0.45)), DARK_GLASS)
        zone_c = mix(is_glass, mix(is_opaque, mix(is_store, c, mix(shopfront, c, DARK_GLASS)), mix(window, c, DARK_GLASS)), glass_c)
        zone_r = blend(is_glass, blend(is_opaque, blend(is_store, 0.8, math("SUBTRACT", 0.8, math("MULTIPLY", shopfront, 0.75))),
                                       math("SUBTRACT", 0.85, math("MULTIPLY", window, 0.75))),
                       math("ADD", math("MULTIPLY", math("MAXIMUM", spandrel, mullion), 0.55), 0.03))
        used = math("MULTIPLY", inside, math("GREATER_THAN", kind, 0.5))
        colour = mix(used, colour, zone_c)
        rough = blend(used, rough, zone_r)
        bottom = top
    on = math("MULTIPLY", math("MULTIPLY", attr("gt_look_on"), gin.outputs["Look"]),
              math("LESS_THAN", math("ABSOLUTE", nrm.outputs[2]), 0.5))   # roofs keep the plain colour
    links.new(mix(on, gin.outputs["Plain Color"], scale(colour, gin.outputs["Brightness"])), gout.inputs["Color"])
    links.new(blend(on, PLAIN_ROUGHNESS, rough), gout.inputs["Roughness"])


def ensure_street_look(mat, kind):
    """Put the Street Look group in front of a building material's Base Color and Roughness (once)."""
    tree = mat.node_tree
    if tree is None:
        return None
    bsdf = next((n for n in tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
    if bsdf is None:
        return None
    node = tree.nodes.get(LOOK_NODE)
    if node is None:
        node = tree.nodes.new("ShaderNodeGroup")
        node.name = node.label = LOOK_NODE
        node.node_tree = street_look_group()
        node.location = (bsdf.location.x - 300, bsdf.location.y)
        tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
        tree.links.new(node.outputs["Roughness"], bsdf.inputs["Roughness"])
    node.inputs["Plain Color"].default_value = COLOURS[kind] + (1.0,)
    return node


def set_street_look(look=None, brightness=None):
    """Set the Look switch and Photo brightness on every material carrying the group."""
    for mat in bpy.data.materials:
        node = mat.node_tree.nodes.get(LOOK_NODE) if mat.node_tree is not None else None
        if node is None:
            continue
        if look is not None:
            node.inputs["Look"].default_value = 1.0 if look else 0.0
        if brightness is not None:
            node.inputs["Brightness"].default_value = float(brightness)
