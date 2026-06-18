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
GEO_COUNT          = 23

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
}

_WIRE_IDS = frozenset({
    GEO_CUBE_WIRE, GEO_SPHERE_WIRE, GEO_CONE_WIRE, GEO_TORUS_WIRE,
    GEO_DODECA_WIRE, GEO_OCTA_WIRE, GEO_TETRA_WIRE, GEO_ICOSA_WIRE,
    GEO_PIN_WIRE, GEO_CYLINDER_WIRE, GEO_GRID_WIRE,
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


def torus_radii(ratio: float, size: float = 1.0) -> tuple[float, float]:
    """Major/minor radii of a torus glyph for a given `ratio` and overall size."""
    minor = ratio * size
    return size - minor, minor


# Cylinder/rod proportions relative to the unit "size" radius — exposed so
# topology code can place children precisely on the rendered surface.
CYLINDER_RADIUS_RATIO = 1.0
CYLINDER_HEIGHT_RATIO = 2.0

# Rod topology scales the cylinder geometry: narrow (0.25x) and long (5x).
ROD_RADIUS_FACTOR = 0.25
ROD_HEIGHT_FACTOR = 5.0

# Flat square ("Grid"/"Square") glyph — lies in the local XY plane, normal
# along +Z, matching ANTz's Grid node (topo=plane, geometry=Square) and the
# viewport's own XY-at-Z=0 world grid orientation. Half-extent chosen so the
# square's corners reach exactly radius 1.0, per this module's "fits within
# radius ~1" convention.
GRID_HALF_EXTENT = 1.0 / math.sqrt(2.0)
