# Ghost Town brand

Blender add-on that generates 3D city context: buildings, roads, trees, parcels.
**Tagline:** No more ghost towns.

The Ghost Town name and logo are © winterweken and are not covered by the GPL that covers the code.

## The mark

A ghost-shaped tower (rounded dome, two eye windows, notched hem) standing in a staggered skyline of
faded neighbours. Your model is the solid ghost; the generated context is the faded city.

Two versions:
- **Mark + long shadows:** primary. Low sun from the left; shadows fall to the lower right. The ghost's
  shadow carries its eyes. Use at 128 px and up.
- **Mark (no shadows):** for small sizes (64 px and below), favicons and Blender UI icons.

## Colours

| Role | Hex |
|---|---|
| Ink (dark background, text) | `#141413` |
| Paper (light background) | `#f3f2ee` |
| Mint accent (mark on ink) | `#94f6cc`, `oklch(0.9 0.11 165)` |
| Muted text (tagline on paper) | `#55534d` |

Opacities inside the mark (always the mark colour, never a new colour):
- Neighbour buildings: 22%
- Neighbour shadows: 10%
- Ghost shadow: 28%

Approved pairings: ink on paper or white · mint on ink · white on ink or photos.

## Typography

**Space Mono** (Google Fonts, free, OFL): https://fonts.google.com/specimen/Space+Mono
- Wordmark: Space Mono Bold, uppercase "GHOST TOWN", tracking −2%
- Tagline and body: Space Mono Regular
- Labels: Space Mono Regular, uppercase, +4% tracking (for example BUILDINGS · ROADS · TREES · PARCELS)

## Files

```
png/hero/     README and add-on page banner (2x)
png/icon/     16, 32, 64 (no shadow) · 128, 256, 512, 1024 (shadow) · light 16 and 32
png/lockup/   horizontal light and dark, stacked light (3x)
png/mark/     1200 px wide transparent PNGs of each mark
svg/icon/     icon-small (no shadows), icon-large (shadows), icon-small-light
svg/mark/     mark and mark-shadow in ink, white and mint (transparent background)
```

The lockups are provided as PNG only: their SVG sources use live Space Mono text.
The add-on's panel icon, `ghosttown/icons/ghosttown.png`, is `png/icon/ghosttown-icon-64.png`.

## Usage

- **Clear space:** at least the ghost's width on all sides.
- **Minimum size:** shadow mark 96 px wide; plain mark 16 px.
- Don't recolour the neighbours or shadows separately, rotate, add effects, or flip the shadow direction.
- The wordmark always sits to the right of the mark (horizontal) or stacked GHOST / TOWN beside it.

## Geometry (for rebuilding in Blender or Figma)

Plain mark, 160 × 140 units, gap 4 between buildings.
- Building widths, left to right: 10, 20, 14, **44 (ghost)**, 22, 10, 16
- Heights: 44, 102, 70, **140**, 82, 108, 52
- Ghost: dome radius 22; eyes 9 × 16 at 9 and 26 from the ghost's left edge, 30 from the top; hem notch
  14 wide × 12 tall, centred.
- Shadows: sheared 62° to the right from the ground line; length about 27% of building height.
