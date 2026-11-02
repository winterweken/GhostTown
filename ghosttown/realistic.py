"""The Realistic ground look: one procedural material per ground surface, plus the layered earth of the
site's round drum, named 'Ghost Town Realistic · <Surface>'. Every one is built from shader nodes driven by
world-space position in metres (no images, no UVs, nothing tiles), so a 2 m patch is 2 m on every site.
The earth's bands follow gt_depth, a float point attribute holding metres below the rim.

Like the other materials, one that exists already is used as it is, so the user's tweaks stay."""
import bpy

from .materials import _linear

PREFIX = "Ghost Town Realistic · "
EARTH = "Earth"
SURFACES = {"ground": "Open ground", "green": "Grass", "road": "Asphalt", "sidewalk": "Concrete",
            "parking": "Lot asphalt", "rail": "Ballast", "water": "Water"}
DEPTH_ATTRIBUTE = "gt_depth"
EARTH_DEPTH_M = 18.0   # the earth ramp's far end, in metres below the rim
VIEWPORT = {"Open ground": (104, 112, 62), "Grass": (46, 90, 34), "Asphalt": (56, 57, 60),
            "Concrete": (166, 162, 154), "Lot asphalt": (78, 78, 80), "Ballast": (100, 94, 86),
            "Water": (14, 76, 84), EARTH: (120, 88, 58)}
FRAMES = (("Pattern", -1500), ("Colour", -820), ("Bump", -440))


def _rgb(srgb):
    """An sRGB colour (0-255 channels) as a linear RGBA tuple."""
    return tuple(_linear(c / 255.0) for c in srgb) + (1.0,)


class _Tree:
    """Node helpers: each returns an output socket, and numbers or colours (sRGB 0-255) stand in for sockets."""

    def __init__(self, mat):
        self.nodes, self.links = mat.node_tree.nodes, mat.node_tree.links
        self.frames, self.count = {}, dict.fromkeys(dict(FRAMES), 0)
        for label, x in FRAMES:
            frame = self.nodes.new("NodeFrame")
            frame.name = frame.label = label
            frame.location = (x, 300)
            self.frames[label] = frame
        self.bsdf = next(n for n in self.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
        self.pos = self.add("ShaderNodeNewGeometry", "Pattern").outputs["Position"]

    def add(self, idname, frame, **props):
        node = self.nodes.new(idname)
        node.parent = self.frames[frame]
        i = self.count[frame]
        self.count[frame] += 1
        node.location = ((i % 4) * 230, -(i // 4) * 260)
        for key, value in props.items():
            setattr(node, key, value)
        return node

    def feed(self, socket, value):
        if value is None:
            return
        if isinstance(value, (int, float)):
            socket.default_value = value
        elif isinstance(value, tuple):
            socket.default_value = _rgb(value) if socket.type == "RGBA" else value
        else:
            self.links.new(value, socket)

    def math(self, op, a, b=None, c=None, clamp=False, frame="Pattern"):
        node = self.add("ShaderNodeMath", frame, operation=op, use_clamp=clamp)
        for socket, value in zip(node.inputs, (a, b, c)):
            self.feed(socket, value)
        return node.outputs[0]

    def vector(self, op, a, b, c=None):
        node = self.add("ShaderNodeVectorMath", "Pattern", operation=op)
        for socket, value in zip(node.inputs, (a, b, c)):
            self.feed(socket, value)
        return node.outputs[0]

    def lerp(self, fac, a, b):
        """a where fac is 0, b where it is 1, for numbers."""
        return self.math("MULTIPLY_ADD", self.math("SUBTRACT", b, a), fac, a)

    def span(self, value, a, b, lo=0.0, hi=1.0, smooth=True):
        """value from a..b onto lo..hi, held at the ends; smoothstep unless smooth is False."""
        node = self.add("ShaderNodeMapRange", "Pattern", clamp=True,
                        interpolation_type="SMOOTHSTEP" if smooth else "LINEAR")
        for name, v in (("Value", value), ("From Min", a), ("From Max", b), ("To Min", lo), ("To Max", hi)):
            self.feed(node.inputs[name], v)
        return node.outputs["Result"]

    def shift(self, vec, seed):
        """vec moved by a fixed offset, so two noises at nearby scales don't line up."""
        vec = self.pos if vec is None else vec
        return self.vector("ADD", vec, (seed * 37.1, seed * 71.7, seed * 13.3)) if seed else vec

    def stretch(self, sx, sy, sz, vec=None):
        return self.vector("MULTIPLY", self.pos if vec is None else vec, (sx, sy, sz))

    def warp(self, scale, amount, seed=0, vec=None):
        """vec pushed about by a noise of its own, up to `amount` metres each way."""
        node = self.add("ShaderNodeTexNoise", "Pattern", noise_dimensions="3D")
        self.feed(node.inputs["Vector"], self.shift(vec, seed + 50))
        self.feed(node.inputs["Scale"], scale)
        self.feed(node.inputs["Detail"], 2.0)
        offset = self.vector("SUBTRACT", node.outputs["Color"], (0.5, 0.5, 0.5))
        return self.vector("MULTIPLY_ADD", offset, (amount * 2,) * 3, self.pos if vec is None else vec)

    def noise(self, scale, detail=4.0, rough=0.5, distortion=0.0, seed=0, vec=None):
        node = self.add("ShaderNodeTexNoise", "Pattern", noise_dimensions="3D")
        self.feed(node.inputs["Vector"], self.shift(vec, seed))
        for name, v in (("Scale", scale), ("Detail", detail), ("Roughness", rough), ("Distortion", distortion)):
            self.feed(node.inputs[name], v)
        return node.outputs["Fac"]

    def voronoi(self, scale, seed=0, vec=None):
        node = self.add("ShaderNodeTexVoronoi", "Pattern", voronoi_dimensions="3D", feature="F1")
        self.feed(node.inputs["Vector"], self.shift(vec, seed))
        self.feed(node.inputs["Scale"], scale)
        return node.outputs["Distance"], self.bw(node.outputs["Color"])

    def bw(self, colour):
        node = self.add("ShaderNodeRGBToBW", "Pattern")
        self.links.new(colour, node.inputs[0])
        return node.outputs[0]

    def ramp(self, fac, stops):
        """Colour along (position, sRGB) stops."""
        node = self.add("ShaderNodeValToRGB", "Colour")
        elements = node.color_ramp.elements
        for position, _ in stops[1:-1]:
            elements.new(position)
        elements[0].position, elements[len(stops) - 1].position = stops[0][0], stops[-1][0]
        for i, (_, srgb) in enumerate(stops):
            elements[i].color = _rgb(srgb)
        self.links.new(fac, node.inputs["Fac"])
        return node.outputs["Color"]

    def mix(self, fac, a, b):
        node = self.add("ShaderNodeMix", "Colour", data_type="RGBA")
        for socket, v in ((node.inputs[0], fac), (node.inputs[6], a), (node.inputs[7], b)):   # Factor, A, B (colour)
            self.feed(socket, v)
        return node.outputs[2]

    def bump(self, height, strength, distance, normal=None):
        node = self.add("ShaderNodeBump", "Bump")
        for name, v in (("Height", height), ("Strength", strength), ("Distance", distance), ("Normal", normal)):
            self.feed(node.inputs[name], v)
        return node.outputs["Normal"]

    def finish(self, colour, roughness, normal=None, **inputs):
        for name, v in (("Base Color", colour), ("Roughness", roughness), ("Normal", normal), *inputs.items()):
            self.feed(self.bsdf.inputs[name], v)


def _open_ground(t):
    """Mown grass with dry yellowed areas and patches of bare soil, mixed at 2-20 m."""
    mid, blades = t.noise(0.5, 4, 0.55, seed=1), t.noise(18.0, 3, 0.6, seed=2)
    grass = t.mix(t.span(mid, 0.4, 0.6, 0.0, 0.5), t.ramp(blades, [(0.25, (66, 90, 38)), (0.75, (102, 124, 56))]),
                  (82, 106, 44))
    dry = t.mix(t.span(t.noise(0.07, 3, 0.5, 0.5, seed=3), 0.5, 0.72, 0.0, 0.85), grass,
                t.ramp(blades, [(0.3, (140, 128, 72)), (0.7, (166, 152, 90))]))
    bare = t.span(t.math("MULTIPLY", t.span(t.noise(0.16, 4, 0.55, 0.8, seed=4), 0.58, 0.7),
                         t.span(mid, 0.45, 0.62)), 0.0, 0.6, 0.0, 1.0)
    colour = t.mix(bare, dry, t.ramp(blades, [(0.3, (90, 72, 50)), (0.7, (124, 100, 72))]))
    grain = t.noise(70.0, 3, 0.6, seed=5)
    normal = t.bump(grain, 0.3, 0.02, t.bump(t.noise(4.0, 3, 0.5), 0.15, 0.1))
    t.finish(colour, t.lerp(bare, 0.95, 0.85), normal)


def _grass(t):
    """Lush, dark, even lawn with clover-scale tufts and faint mowing stripes."""
    clover, blades = t.noise(3.0, 4, 0.55, seed=1), t.noise(26.0, 4, 0.6, seed=2)
    wave = t.add("ShaderNodeTexWave", "Pattern", wave_type="BANDS", bands_direction="X")
    t.links.new(t.warp(0.15, 1.5), wave.inputs["Vector"])
    for name, v in (("Scale", 0.12), ("Distortion", 2.0), ("Detail", 1.0)):
        t.feed(wave.inputs[name], v)
    lawn = t.ramp(blades, [(0.3, (32, 70, 24)), (0.7, (56, 102, 38))])
    lawn = t.mix(t.span(clover, 0.4, 0.62, 0.0, 0.5), lawn, (76, 118, 44))
    colour = t.mix(t.math("MULTIPLY", wave.outputs["Fac"], 0.22), lawn, (72, 114, 46))
    normal = t.bump(blades, 0.35, 0.02, t.bump(clover, 0.2, 0.05))
    t.finish(colour, 0.92, normal)


def _asphalt(t, tones, lighter, oil=False):
    """Fine aggregate over faint wear and darker patching; `oil` adds glossy dark stains."""
    grain, (_, cell) = t.noise(70.0, 6, 0.7), t.voronoi(110.0, seed=1)
    tone = t.ramp(t.math("ADD", t.math("MULTIPLY", grain, 0.55), t.math("MULTIPLY", cell, 0.45)), tones)
    colour = t.mix(t.span(t.noise(0.25, 4, 0.5, 0.5, seed=2), 0.45, 0.7, 0.0, 0.55), tone, lighter)
    patch = t.span(t.noise(0.15, 2, 0.5, 0.9, seed=3), 0.6, 0.615)
    colour = t.mix(t.math("MULTIPLY", patch, 0.6), colour, tones[0][1])
    rough = t.lerp(patch, t.math("MULTIPLY_ADD", t.math("SUBTRACT", grain, 0.5), 0.3, 0.84), 0.7)
    if oil:
        stain = t.span(t.noise(0.4, 2, 0.5, 0.5, seed=4), 0.64, 0.74, 0.0, 0.85)
        colour = t.mix(stain, colour, (24, 24, 28))
        rough = t.lerp(stain, rough, 0.35)
    height = t.math("ADD", t.math("MULTIPLY", grain, 0.6), t.math("MULTIPLY", cell, 0.4))
    t.finish(colour, rough, t.bump(patch, 0.1, 0.01, t.bump(height, 0.5, 0.01)))


def _concrete(t):
    """Light warm grey with fine grain, staining and a few pits; no slab joints (no direction data)."""
    grain, (pits, _) = t.noise(90.0, 6, 0.6), t.voronoi(40.0, seed=1)
    colour = t.ramp(grain, [(0.25, (146, 142, 134)), (0.75, (188, 184, 176))])
    colour = t.mix(t.span(t.noise(0.12, 3, 0.5, seed=2), 0.4, 0.65, 0.0, 0.7), colour, (172, 164, 148))
    colour = t.mix(t.span(t.noise(0.35, 3, 0.5, 0.5, seed=3), 0.52, 0.75, 0.0, 0.4), colour, (118, 110, 98))
    pitted = t.span(pits, 0.06, 0.14, 0.15, 0.0)
    colour = t.mix(pitted, colour, (110, 108, 102))
    t.finish(colour, 0.9, t.bump(grain, 0.5, 0.01, t.bump(pitted, 0.4, 0.006, t.bump(t.noise(12.0, 3, 0.5, seed=4), 0.2, 0.02))))


def _ballast(t):
    """Grey-brown crushed stone: two sizes of cell, darker crevices, strong relief."""
    big, big_tone = t.voronoi(14.0)
    small, small_tone = t.voronoi(35.0, seed=1)
    stones = [(0.0, (70, 66, 62)), (0.5, (104, 98, 90)), (1.0, (128, 116, 102))]
    colour = t.mix(0.35, t.ramp(big_tone, stones), t.ramp(small_tone, stones))
    colour = t.mix(t.span(t.noise(1.5, 3, 0.5, seed=2), 0.4, 0.62, 0.0, 0.35), colour, (110, 92, 72))
    colour = t.mix(t.span(big, 0.3, 0.75, 0.0, 0.7), colour, (28, 26, 24))
    height = t.math("ADD", t.math("MULTIPLY", t.math("SUBTRACT", 1.0, big), 0.7),
                    t.math("MULTIPLY", t.math("SUBTRACT", 1.0, small), 0.3))
    t.finish(colour, 0.9, t.bump(height, 1.0, 0.05))


def _water(t):
    """Deep teal and glossy; ripples at 0.5-3 m as bump, strong enough to turn terrain undulation into waves."""
    tint = t.ramp(t.noise(0.06, 3, 0.5, seed=1), [(0.4, (10, 64, 72)), (0.6, (20, 88, 96))])
    swell, chop, fine = t.noise(0.25, 2, 0.5, seed=2), t.noise(0.7, 3, 0.5, 0.4, seed=3), t.noise(2.2, 4, 0.55, 0.3, seed=4)
    height = t.math("ADD", t.math("ADD", t.math("MULTIPLY", swell, 0.2), t.math("MULTIPLY", chop, 0.5)),
                    t.math("MULTIPLY", fine, 0.3))
    t.finish(tint, 0.05, t.bump(height, 1.0, 0.3), IOR=1.333)


def _earth(t):
    """Bands by depth below the rim, their edges wobbled by noise: thin dark topsoil with roots, brown subsoil,
    paler clay with stones thickening toward the base."""
    attribute = t.add("ShaderNodeAttribute", "Pattern", attribute_type="GEOMETRY", attribute_name=DEPTH_ATTRIBUTE)
    depth = attribute.outputs["Fac"]
    for scale, amount in ((0.45, 1.2), (2.0, 0.3), (8.0, 0.05)):
        depth = t.math("ADD", depth, t.math("MULTIPLY", t.math("SUBTRACT", t.noise(scale, 4, 0.55, seed=scale), 0.5),
                                            amount * 2))
    bands = t.ramp(t.math("DIVIDE", depth, EARTH_DEPTH_M), [
        (0.0, (42, 30, 21)), (0.045, (50, 36, 24)), (0.065, (112, 80, 52)), (0.30, (126, 92, 60)),
        (0.38, (150, 120, 86)), (1.0, (186, 162, 128))])
    strata = t.noise(1.0, 3, 0.5, seed=7, vec=t.stretch(0.15, 0.15, 2.5))
    colour = t.mix(t.span(strata, 0.42, 0.6, 0.0, 0.3), bands, (96, 70, 46))
    topsoil = t.span(depth, 0.4, 1.4, 1.0, 0.0, smooth=False)
    roots = t.span(t.noise(1.0, 4, 0.6, seed=8, vec=t.stretch(14.0, 14.0, 1.2)), 0.52, 0.62)
    colour = t.mix(t.math("MULTIPLY", roots, topsoil), colour, (20, 14, 10))
    relief = t.noise(60.0, 3, 0.6, seed=9)
    rough = 0.95
    for scale, from_m, to_m, seed in ((2.4, 3.0, 9.0, 1), (8.0, 6.0, 12.0, 2)):
        dist, cell = t.voronoi(scale, seed=seed)
        present = t.math("GREATER_THAN", cell, t.span(depth, from_m, to_m, 1.0, 0.35, smooth=False))
        stone = t.math("MULTIPLY", present, t.span(dist, 0.28, 0.4, 1.0, 0.0))
        colour = t.mix(stone, colour, t.ramp(cell, [(0.35, (108, 102, 94)), (1.0, (152, 142, 128))]))
        rough = t.lerp(stone, rough, 0.8)
        relief = t.math("ADD", relief, t.math("MULTIPLY", stone, t.math("SUBTRACT", 1.0, dist)))
    t.finish(colour, rough, t.bump(relief, 0.8, 0.1))


BUILDERS = {"Open ground": _open_ground, "Grass": _grass, "Lot asphalt": lambda t: _asphalt(
    t, [(0.2, (58, 59, 62)), (0.5, (78, 78, 80)), (0.8, (104, 103, 102))], (126, 124, 120), oil=True),
            "Asphalt": lambda t: _asphalt(t, [(0.2, (40, 41, 44)), (0.5, (58, 59, 62)), (0.8, (86, 86, 88))],
                                          (78, 78, 80)),
            "Concrete": _concrete, "Ballast": _ballast, "Water": _water, EARTH: _earth}


def get_material(surface):
    """The shared material for a SURFACES value or EARTH: one that exists already is returned untouched."""
    name = PREFIX + surface
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        BUILDERS[surface](_Tree(mat))
        mat.diffuse_color = _rgb(VIEWPORT[surface])
    return mat
