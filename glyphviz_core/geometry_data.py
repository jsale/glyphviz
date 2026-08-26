"""
Pure geometry constants and math shared by the kernel (topology/scene) and
the GL renderer (glyphviz_gl.geometry) — no OpenGL/Qt dependency, so this
module is safe to import from anything, including a future non-GL (e.g.
OpenXR/three.js) presentation layer.
"""
import math

# IDs match ANTz kNPgeo* enum
GEO_CUBE_WIRE      = 0
GEO_CUBE           = 1
GEO_SPHERE_WIRE    = 2
GEO_SPHERE         = 3
GEO_CONE_WIRE      = 4
GEO_CONE           = 5
GEO_TORUS_WIRE     = 6
GEO_TORUS          = 7
GEO_DODECA_WIRE    = 8
GEO_DODECA         = 9
GEO_OCTA_WIRE      = 10
GEO_OCTA           = 11
GEO_TETRA_WIRE     = 12
GEO_TETRA          = 13
GEO_ICOSA_WIRE     = 14
GEO_ICOSA          = 15
GEO_PIN            = 16
GEO_PIN_WIRE       = 17
GEO_CYLINDER_WIRE  = 18
GEO_CYLINDER       = 19
GEO_GRID_WIRE      = 20
GEO_GRID           = 21
GEO_POINT          = 22
# GlyphViz extension (no ANTz/GaiaViz equivalent): an arbitrary triangle mesh
# imported from an external file (OBJ, STL, ...) via glyphviz_core.mesh_loader,
# selected per-node by Node.mesh_id rather than by a fixed shape.
GEO_MESH           = 23
# GlyphViz extensions (no ANTz/GaiaViz equivalent): flat 2-D marker shapes,
# the same idea as Point but with a recognizable outline -- useful as cheap,
# scatter-plot-style markers for large point clouds. Unlike Point these are
# ordinary world-space flat plates (like Square/Grid), scaled by the node's
# normal scale_x/y/z and compiled into display lists for performance at
# scale, rather than fixed-pixel-size GL_POINTS sprites.
GEO_CIRCLE         = 24
GEO_CROSS          = 25
GEO_STAR           = 26
# GlyphViz extensions (no ANTz/GaiaViz equivalent): the two LINE render modes
# for Link (type=7) nodes specifically -- meaningless on any other node type.
# GEO_LINE is the classic thin GL_LINES connector (the only mode Links had for
# a long time, and still the default); GEO_LINE_PRISM instead builds a small
# textured 4-sided tube between the link's A-end and B-end, so a texture
# (optionally scrolled via rotate_rate_z, see viewport._draw_topology_overlays)
# can indicate directed flow -- e.g. for directed-graph edges.
#
# EVERY OTHER geometry id above is also valid on a Link node, and renders that
# glyph stretched between the link's two ends (ANTz's own behavior --
# npDrawLink, npgldraw.c:961): `ratio` is the thickness on both cross-axes and
# the endpoint distance is the length. The mode is chosen by `geometry` alone;
# glyphviz_core/link_geometry.py owns the transform and the LINK_LINE_GEOMETRIES
# set that decides which ids stay line-drawn. See _draw_topology_overlays() in
# glyphviz_gl/viewport.py.
GEO_LINE           = 27
GEO_LINE_PRISM     = 28
# GlyphViz extensions (no ANTz/GaiaViz equivalent): INTERIOR variants of the
# three shapes that enclose a volume and take a texture. Each renders its
# INSIDE surface and culls its outside -- the shape is invisible from without
# and reads correctly from within, which is what a 360deg video sphere, a
# cylindrical panorama or a video room needs.
#
# "Interior" is deliberately NOT "back-face culling turned off". Looking at
# the inside of an outward-mapped surface is inherently a MIRROR view, so a
# node that merely stopped culling would play every video backwards (measured:
# a texture reading "R" comes back as a mirrored glyph). The fix is mirrored
# geometry/UVs, which live in the compiled display list -- i.e. in the shape,
# which is why this is a geometry id and not a per-node flag or a node type.
# Staying single-sided (rather than two-sided) also keeps one fragment per
# pixel and leaves alpha blending on a translucent node well-defined.
#
# The two cylinder ids are one shape with and without its end caps: an open
# tube for a cylindrical panorama (or a link you fly through), a capped one
# for a closed room. The Properties panel presents that pair as a "Caps"
# checkbox which simply swaps the id -- no new column, so the choice travels
# with the CSV like every other geometry decision.
GEO_CUBE_INTERIOR          = 29
GEO_SPHERE_INTERIOR        = 30
GEO_CYLINDER_INTERIOR      = 31
GEO_CYLINDER_INTERIOR_OPEN = 32
# GlyphViz extensions (no ANTz/GaiaViz equivalent): a torus whose cross-section
# is a RECTANGLE rather than a circle -- a flat machined band, the kind of ring
# an armillary sphere, an astrolabe or a graduated dial is built from. The
# rounded torus reads as soft tubing and its specular highlight slides around
# the tube; a flat ring has four real faces, each with a constant normal and a
# crisp edge, which is what makes it read as an instrument and what makes a
# texture (degree markings, a zodiac strip, a ruler scale) lie flat and legible
# on it.
#
# It takes its two proportions from fields that already exist, so there is no
# new column and every existing control works on it unchanged:
#
#   * `ratio` is the band's RADIAL width -- exactly the meaning it already has
#     on a torus, where the tube spans radius (1 - 2*ratio) .. 1 and z +/-ratio
#     (see torus_radii below). The default cross-section is therefore SQUARE,
#     and a Torus <-> Flat Ring swap changes only the look: the two shapes have
#     identical extents and TOPO_TORUS places children on both identically.
#   * `scale_z` is the band's HEIGHT, as it already is for a torus -- it just
#     stretches a rectangle now instead of an ellipse.
#
# That covers both of the forms a ring instrument is built from: a wide, thin
# washer (large ratio, small scale_z -- a graduated dial read face-on) and a
# tall, thin hoop (small ratio, large scale_z -- a meridian band whose broad
# face points outward).
#
# Like the torus, the SHAPE depends on `ratio`, so these ids cannot be baked
# into one fixed display list at setup() time; they join the torus in the lazy
# per-ratio cache (GeoRenderer.ensure_ratio_list, RATIO_SHAPED_GEOMETRIES).
# Height staying in glScalef rather than in the compiled geometry is what keeps
# that cache one-dimensional and bounded.
GEO_RING           = 33
GEO_RING_WIRE      = 34
GEO_COUNT          = 35

GEO_NAMES = {
    GEO_CUBE_WIRE:     "Cube Wire",
    GEO_CUBE:          "Cube",
    GEO_SPHERE_WIRE:   "Sphere Wire",
    GEO_SPHERE:        "Sphere",
    GEO_CONE_WIRE:     "Cone Wire",
    GEO_CONE:          "Cone",
    GEO_TORUS_WIRE:    "Torus Wire",
    GEO_TORUS:         "Torus",
    GEO_DODECA_WIRE:   "Dodecahedron Wire",
    GEO_DODECA:        "Dodecahedron",
    GEO_OCTA_WIRE:     "Octahedron Wire",
    GEO_OCTA:          "Octahedron",
    GEO_TETRA_WIRE:    "Tetrahedron Wire",
    GEO_TETRA:         "Tetrahedron",
    GEO_ICOSA_WIRE:    "Icosahedron Wire",
    GEO_ICOSA:         "Icosahedron",
    GEO_PIN:           "Pin",
    GEO_PIN_WIRE:      "Pin Wire",
    GEO_CYLINDER_WIRE: "Cylinder Wire",
    GEO_CYLINDER:      "Cylinder",
    GEO_GRID_WIRE:     "Grid Wire",
    GEO_GRID:          "Grid",
    GEO_POINT:         "Point",
    GEO_MESH:          "Mesh (Imported)",
    GEO_CIRCLE:        "Circle",
    GEO_CROSS:         "Cross",
    GEO_STAR:          "Star",
    GEO_LINE:          "Line",
    GEO_LINE_PRISM:    "Prism (Textured)",
    GEO_CUBE_INTERIOR:          "Cube (Interior)",
    GEO_SPHERE_INTERIOR:        "Sphere (Interior)",
    GEO_CYLINDER_INTERIOR:      "Cylinder (Interior)",
    GEO_CYLINDER_INTERIOR_OPEN: "Cylinder (Interior, Open)",
    GEO_RING:          "Flat Ring",
    GEO_RING_WIRE:     "Flat Ring Wire",
}

# Seen from inside, culled from outside — see the block comment above.
INTERIOR_GEOMETRIES = frozenset({
    GEO_CUBE_INTERIOR, GEO_SPHERE_INTERIOR,
    GEO_CYLINDER_INTERIOR, GEO_CYLINDER_INTERIOR_OPEN,
})

# The interior cylinder's end caps, as a pair of ids rather than a column.
CYLINDER_INTERIOR_BY_CAPS = {
    True:  GEO_CYLINDER_INTERIOR,
    False: GEO_CYLINDER_INTERIOR_OPEN,
}


def has_caps(geometry: int) -> bool:
    """Whether *geometry* is an interior cylinder that draws its end caps.
    False for the open variant — and for everything that isn't one, which has
    no caps to speak of."""
    return geometry == GEO_CYLINDER_INTERIOR


def with_caps(geometry: int, caps: bool) -> int:
    """*geometry* switched to the capped/open member of its pair. A no-op for
    any id that isn't an interior cylinder."""
    if geometry in CYLINDER_INTERIOR_BY_CAPS.values():
        return CYLINDER_INTERIOR_BY_CAPS[bool(caps)]
    return geometry

_WIRE_IDS = frozenset({
    GEO_CUBE_WIRE, GEO_SPHERE_WIRE, GEO_CONE_WIRE, GEO_TORUS_WIRE,
    GEO_DODECA_WIRE, GEO_OCTA_WIRE, GEO_TETRA_WIRE, GEO_ICOSA_WIRE,
    GEO_PIN_WIRE, GEO_CYLINDER_WIRE, GEO_GRID_WIRE, GEO_RING_WIRE,
})

# Maps each wireframe geometry to its solid equivalent for FBO picking:
# the pick pass draws solid silhouettes so any click inside the bounding
# shape registers a hit, not just clicks that land on a visible wire.
WIRE_TO_SOLID = {
    GEO_CUBE_WIRE:     GEO_CUBE,
    GEO_SPHERE_WIRE:   GEO_SPHERE,
    GEO_CONE_WIRE:     GEO_CONE,
    GEO_TORUS_WIRE:    GEO_TORUS,
    GEO_DODECA_WIRE:   GEO_DODECA,
    GEO_OCTA_WIRE:     GEO_OCTA,
    GEO_TETRA_WIRE:    GEO_TETRA,
    GEO_ICOSA_WIRE:    GEO_ICOSA,
    GEO_PIN_WIRE:      GEO_PIN,
    GEO_CYLINDER_WIRE: GEO_CYLINDER,
    GEO_GRID_WIRE:     GEO_GRID,
    GEO_RING_WIRE:     GEO_RING,
}


# A torus glyph's shape — not just its size — is governed by its per-node
# `ratio` property (mirrors GaiaViz/ANTz: "ratio sets the inner and outer
# radius of a torus... default ratio is 0.1 = 10% of the outer radius"):
# the minor (tube) radius is `ratio` of the torus's overall ("outer") radius,
# and the major (orbital) radius makes up the remainder, so the rendered
# donut's total extent always equals the unit "size" radius passed to
# GeoRenderer.draw — exposed so topology code can place children precisely
# on the rendered surface.
TORUS_DEFAULT_RATIO = 0.14  # half of the prior fixed minor-radius proportion (0.28)

# The geometries whose SHAPE — not merely their size — is set by the node's own
# `ratio`, and which therefore cannot be compiled into a single fixed display
# list at setup() time. They go through GeoRenderer.ensure_ratio_list instead,
# which caches one list per distinct (quantized) ratio actually seen. Anything
# that pre-warms or dispatches those lists reads this set rather than naming
# the ids, so a future ratio-shaped glyph joins by editing one line here.
RATIO_SHAPED_GEOMETRIES = frozenset({
    GEO_TORUS, GEO_TORUS_WIRE, GEO_RING, GEO_RING_WIRE,
})


def torus_radii(ratio: float, size: float = 1.0) -> tuple[float, float]:
    """Major/minor radii of a torus glyph for a given `ratio` and overall size."""
    minor = ratio * size
    return size - minor, minor


def ring_dims(ratio: float, size: float = 1.0) -> tuple[float, float, float]:
    """(outer radius, inner radius, half-height) of a Flat Ring glyph.

    Deliberately the torus's own extents, restated as a box rather than a
    tube: `torus_radii` puts the tube between radius `size - 2*ratio*size` and
    `size`, spanning z +/- `ratio*size`, and that is exactly the rectangle
    swept here. So Torus <-> Flat Ring is a pure change of look — same
    silhouette, same bounding extents, and `_torus_offset` places children of a
    TOPO_TORUS parent identically whichever of the two the parent wears.

    The half-height is the glyph's LOCAL one; a node's `scale_z` multiplies it
    at draw time, which is how the band's height is set independently of its
    radial width (scale_z == scale_x gives the square cross-section).

    A `ratio` at or past 0.5 closes the hole; the inner radius clamps at 0 and
    the ring becomes a solid wheel rather than inverting.
    """
    major, minor = torus_radii(ratio, size)
    return size, max(0.0, major - minor), minor


# Cylinder/rod proportions relative to the unit "size" radius — exposed so
# topology code can place children precisely on the rendered surface.
CYLINDER_RADIUS_RATIO = 1.0
CYLINDER_HEIGHT_RATIO = 2.0

# Rod topology scales the cylinder geometry: narrow (0.25x) and long (5x).
ROD_RADIUS_FACTOR = 0.25
ROD_HEIGHT_FACTOR = 5.0

# Pushpin glyph — a cone ten times as tall as its base is wide, apex at the
# local ORIGIN and shaft rising along +Z, closed at the top by a dome of the
# cone's own base radius (so the dome adds a further 10% and the total height
# is 110% of the shaft). Both numbers are ANTz's, from DrawPinDL
# (npgeometry.c:493, `npGLSolidCone(kNPoffsetPin * 0.1f, kNPoffsetPin, ...)`
# with `kNPoffsetPin = 5.0` documented as "cone point to center of dome"),
# rescaled by 1/5 to this module's "fits within radius ~1" convention.
#
# Apex-at-the-origin is the load-bearing part, not a stylistic choice:
# TOPO_PIN places children at `base_radius + translate_x` along +Z
# (topology._pin_offset), so they only ride the shaft if the shaft is the +Z
# half of the glyph. PIN_HEIGHT = 1.0 = the default base_scale then puts a
# child with translate_x = 0 exactly at the dome's center, which is where
# ANTz's own pin children sit.
PIN_HEIGHT = 1.0
PIN_RADIUS = 0.1 * PIN_HEIGHT

# Flat square ("Grid"/"Square") glyph — lies in the local XY plane, normal
# along +Z, matching ANTz's Grid node (topo=plane, geometry=Square) and the
# viewport's own XY-at-Z=0 world grid orientation. Half-extent chosen so the
# square's corners reach exactly radius 1.0, per this module's "fits within
# radius ~1" convention.
GRID_HALF_EXTENT = 1.0 / math.sqrt(2.0)
