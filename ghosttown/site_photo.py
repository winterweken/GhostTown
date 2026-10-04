"""The site's aerial photo in Blender: packed image, straight-down UV maps and the photo material."""
import os

import bpy
import numpy as np

from . import materials, site_use
from .ghosttown_fetch import BUILDING_KINDS, GROUND_KINDS

UV_NAME = "Site photo"
PREFIX = "Site photo · "
DEFAULT_ROOF_MAX_M = 20.0


def add_uvs(ob, bounds):
    """A UV map projecting the photo straight down: u and v run 0 to 1 across bounds_m."""
    me = ob.data
    xmin, ymin, xmax, ymax = bounds
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    vi = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", vi)
    uv = np.empty((len(vi), 2), dtype=np.float32)
    uv[:, 0] = (co[vi, 0] - xmin) / (xmax - xmin)
    uv[:, 1] = (co[vi, 1] - ymin) / (ymax - ymin)
    layer = me.uv_layers.get(UV_NAME) or me.uv_layers.new(name=UV_NAME)
    layer.data.foreach_set("uv", uv.ravel())


def _material(label, image):
    material = bpy.data.materials.new(PREFIX + label)
    tree = material.node_tree
    bsdf = next(n for n in tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.9
    texture = tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    texture.extension = "CLIP"
    texture.location = (-420, 260)
    uvmap = tree.nodes.new("ShaderNodeUVMap")
    uvmap.uv_map = UV_NAME
    uvmap.location = (-640, 260)
    tree.links.new(uvmap.outputs["UV"], texture.inputs["Vector"])
    tree.links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
    material.diffuse_color = materials.COLOURS["ground"] + (1.0,)
    return material


def attach(root, origin, label, path, photo):
    """Pack the photo into the file, map it onto the site's ground and buildings, record it on the
    root and origin, and show it on the ground (roofs stay plain). Raises RuntimeError when Blender
    can't read the file and ValueError when it reads as an empty image; nothing is left behind."""
    image = bpy.data.images.load(path, check_existing=False)
    material = None
    try:
        if min(image.size) == 0:  # a damaged file loads as 0 x 0
            raise ValueError("the photo file isn't a readable picture")
        image.name = PREFIX + label
        image.pack()
        # A name of its own, relative to the .blend: not the cache path, and not "photo.jpg" shared by every site.
        image.filepath_raw = "//" + bpy.path.clean_name(label) + " photo.jpg"
        material = _material(label, image)
        for ob in site_use.made_objects(root, GROUND_KINDS + BUILDING_KINDS):
            add_uvs(ob, photo["bounds_m"])
    except Exception:
        if material is not None:
            bpy.data.materials.remove(material)
        bpy.data.images.remove(image)
        raise
    xmin, ymin, xmax, ymax = (float(v) for v in photo["bounds_m"])
    root["ctx_photo_image"] = image.name
    root["ctx_photo_material"] = material.name
    # Pointers hold a real user each, so the photo stays in the file when no object shows it, and go
    # when the root collection is removed.
    root["ctx_photo_image_id"] = image
    root["ctx_photo_material_id"] = material
    root["photo_bounds_m"] = [xmin, ymin, xmax, ymax]
    root["photo_px"] = [int(photo["width_px"]), int(photo["height_px"])]
    for block in (root, origin):
        block["photo_year"] = int(photo.get("year") or 0)
        block["photo_width_m"] = xmax - xmin
    root["use_roofs"] = "plain"
    root["roof_photo_max_m"] = DEFAULT_ROOF_MAX_M
    site_use.apply_ground(root, "photo")


def forget(material_name, image_name):
    """After a site's objects are gone: delete its photo material, then its image, unless something
    else (a duplicate the user kept, say) still uses them."""
    material = bpy.data.materials.get(material_name or "")
    if material is not None and material.users == 0:
        bpy.data.materials.remove(material)
    image = bpy.data.images.get(image_name or "")
    if image is not None and image.users == 0:
        bpy.data.images.remove(image)


def save(root, directory):
    """Write the site's photo as '<site> photo.jpg', plus a world file (.jgw) in the model's own
    metres, origin at the site centre. Returns (jpg path, jgw path, width in metres)."""
    image = site_use.photo_image(root)
    if image is None:
        raise ValueError("the photo isn't in this file")
    if image.packed_file is not None:
        data = image.packed_file.data
    else:  # Unpack Resources wrote it beside the .blend
        source = bpy.path.abspath(image.filepath)
        if not os.path.isfile(source):
            raise ValueError("the photo isn't in this file")
        with open(source, "rb") as f:
            data = f.read()
    stem = bpy.path.clean_name(root.get("ctx_label", "site")) + " photo"
    xmin, ymin, xmax, ymax = (float(v) for v in root["photo_bounds_m"])
    width_px, height_px = (int(v) for v in root["photo_px"])
    os.makedirs(directory, exist_ok=True)
    jpg = os.path.join(directory, stem + ".jpg")
    with open(jpg, "wb") as f:
        f.write(data)
    px, py = (xmax - xmin) / width_px, (ymax - ymin) / height_px
    jgw = os.path.join(directory, stem + ".jgw")
    with open(jgw, "w", encoding="ascii") as f:
        f.write(f"{px:.6f}\n0.000000\n0.000000\n{-py:.6f}\n{xmin + px / 2:.6f}\n{ymax - py / 2:.6f}\n")
    return jpg, jgw, xmax - xmin
