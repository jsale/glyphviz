"""Lesson: Parents and children — the introductory hierarchy lesson.

Played as a user would do it, through a real MainWindow's own handlers (the
same ones the keys and buttons reach): N creates the default octahedron,
New Object Defaults choose each generation's look, Shift+N adds children,
and the Properties panel's Topology list re-lays a parent's children.

Why Rod for the topology change: the lesson builds children with the app's
own step lattice (translate_x steps around, wrapping to a new translate_y
row each 360). Under Point that lattice is a dome of latitude rings; Sphere,
Torus and Cylinder give nearly the same dome at these defaults, so a switch
between them barely reads on screen. Rod reads x as HEIGHT up the rod and y
as the angle around it, so the dome visibly re-forms into columns -- and
every child carries its own subtree along. (Pin/Cube would read the 0..330
steps as distances and throw children hundreds of units away; that is the
Topo Scale lesson, not this one.)
"""
from PySide6.QtGui import QColor

from glyphviz_core.topology import TOPO_NAMES
from lessonkit import Callout, Key, Lesson, Shot, AMBER, CORAL, TEAL
from lessons._common import world

G_CUBE, G_SPHERE, G_CONE = 1, 3, 5
T_POINT, T_ROD = 7, 6

# Ids as the app assigns them (max id + 1), world row = 1.
ROOT = 2
FIRST_LAP = range(3, 15)          # 12 children, one lap at a 30 deg step
MORE_LAPS = range(15, 39)         # 24 more: laps two and three
CHILD = 3                         # the child that gets grandchildren
GRAND = range(39, 47)             # 8 cones
GRAND0 = 39                       # the cone that gets great-grandchildren
GREAT = range(47, 53)             # 6 cubes
BURST = 108                       # nine more laps: columns all the way round


# --- the "user's" actions: each is exactly what a key or widget does -------

def press_n(L):
    L.win._create_root_node()                # N / New Node


def press_shift_n(L):
    L.win._create_child_node()               # Shift+N / New Child


def select(node_id):
    return lambda L: L.win._table.select_by_id(node_id)   # a click


def defaults(geo=None, rgb=None, scale=None, step=None, child_z=None):
    """Create panel > New Object Defaults, as a user sets them."""
    def act(L):
        w = L.win
        if geo is not None:
            w._new_geo.setCurrentIndex(w._new_geo.findData(geo))
        if rgb is not None:
            w._new_obj_color = QColor(*rgb, 255)
        if scale is not None:
            for sb in (w._new_scale_x, w._new_scale_y, w._new_scale_z):
                sb.setValue(scale)
        if step is not None:
            w._new_step.setValue(step)
        if child_z is not None:
            w._new_child_z.setValue(child_z)
    return act


def topology(topo):
    """Properties > Topology list, applied to the current selection."""
    return lambda L: L.win._insp_topo.setCurrentIndex(L.win._insp_topo.findData(topo))


def spread(action, n, a, b):
    """n presses of the same key, evenly between shot fractions a and b."""
    return [(a + (b - a) * i / max(n - 1, 1), action) for i in range(n)]


def readout(L, u):
    nodes = [n for n in L.win.nodes if n.type != 0]
    root = L.vp._scene.node_by_id(ROOT)
    if root is None:
        return f"nodes  {len(nodes)}"
    return (f"nodes             {len(nodes)}\n"
            f"parent topology   {TOPO_NAMES.get(root.topo, root.topo)}")


def build() -> Lesson:
    def orbit(a0, a1, el=26, dist=22.0, target=(0, 0, 1.5), el1=None, dist1=None):
        return [Key(0, az=a0, el=el, dist=dist, target=target),
                Key(1, az=a1, el=el1 if el1 is not None else el,
                    dist=dist1 if dist1 is not None else dist)]

    def steps(*pairs):
        """Keycap that changes as the 'user' works: [(u_from, key, note)]."""
        def f(u):
            cur = pairs[0]
            for p in pairs:
                if u >= p[0]:
                    cur = p
            return cur[1], cur[2]
        return f

    shots = [
        Shot(title="Parents and Children", heading="Building a hierarchy",
             say="Everything in a GlyphViz scene is a node, and any node can "
                 "be a parent. Let's build a family, one key at a time.",
             keys=orbit(20, 40, el=30, dist=16, target=(0, 0, 0))),
        Shot(heading="A new node",
             say="Press N, or click New Node, and an object appears: an "
                 "octahedron, the default shape.",
             keys=orbit(40, 55, el=28, dist=9, target=(0, 0, 0)),
             events=[(0.25, press_n)],
             keycap="N", keycap_note="or  Create > New Node",
             callouts=[Callout(ROOT, "parent", 0.4, 0.97, offset=(110, -90),
                               ring=False)]),
        Shot(heading="Choose how the children look",
             say="Before adding children, choose their look. Under New Object "
                 "Defaults, pick a sphere, a color, and a smaller size.",
             keys=orbit(55, 75, el=28, dist=9, target=(0, 0, 0)),
             events=[(0.25, defaults(geo=G_SPHERE)),
                     (0.45, defaults(rgb=TEAL)),
                     (0.65, defaults(scale=0.35, step=30))],
             keycap=steps((0.0, "Create", "New Object Defaults"),
                          (0.25, "Geometry", "Sphere"),
                          (0.45, "Color", "teal"),
                          (0.65, "Scale", "0.35     Placement Step  30"))),
        Shot(heading="Add children",
             say="With the parent selected, press Shift N. Each press adds "
                 "one child, spaced around its parent.",
             keys=orbit(75, 115, el=35, dist=22, target=(0, 0, 0.5)),
             events=spread(press_shift_n, len(FIRST_LAP), 0.18, 0.85),
             keycap="Shift + N", keycap_note="add a child",
             readout=readout),
        Shot(heading="Keep going",
             say="Keep pressing. After a full lap, each new child starts the "
                 "next ring.",
             keys=orbit(115, 160, el=35, dist=22, target=(0, 0, 1.5), el1=42),
             events=spread(press_shift_n, len(MORE_LAPS), 0.1, 0.8),
             keycap="Shift + N", keycap_note="... and again",
             readout=readout),
        Shot(heading="Grandchildren",
             say="Any child can be a parent too. Select one, switch to coral "
                 "cones, and add grandchildren.",
             keys=[Key(0, az=160, el=42, dist=22, target=(0, 0, 1.5)),
                   Key(0.3, az=40, el=24, dist=8, target=CHILD),
                   Key(1, az=20, el=20, dist=7)],
             events=[(0.12, select(CHILD)),
                     (0.3, defaults(geo=G_CONE, rgb=CORAL, scale=0.5, step=45,
                                    child_z=3))]
                    + spread(press_shift_n, len(GRAND), 0.45, 0.88),
             keycap=steps((0.0, "Click", "select one child"),
                          (0.3, "Geometry", "Cone     Color  coral"),
                          (0.45, "Shift + N", "add grandchildren")),
             readout=readout),
        Shot(heading="And so on",
             say="And so on, as deep as you like. Here, amber cubes on a "
                 "single cone.",
             keys=[Key(0, az=20, el=20, dist=7, target=CHILD),
                   Key(0.3, az=0, el=18, dist=3.2, target=GRAND0),
                   Key(1, az=-25, el=22, dist=2.8)],
             events=[(0.12, select(GRAND0)),
                     (0.3, defaults(geo=G_CUBE, rgb=AMBER, step=60))]
                    + spread(press_shift_n, len(GREAT), 0.45, 0.88),
             keycap=steps((0.0, "Click", "select a grandchild"),
                          (0.3, "Geometry", "Cube     Color  amber"),
                          (0.45, "Shift + N", "add great-grandchildren")),
             readout=readout),
        Shot(heading="Topology arranges children",
             say="A parent's topology decides where its children go. Give "
                 "this child the Rod topology, and its cones line up along it.",
             # The Rod lays the cones out along the child's outward axis, a
             # column longer than the close-up: frame its middle cone, wider.
             keys=[Key(0, az=-25, el=22, dist=2.8, target=GRAND0),
                   Key(0.3, az=30, el=18, dist=9, target=CHILD),
                   Key(0.6, az=45, el=20, dist=14, target=GRAND0 + 4),
                   Key(1, az=60, el=18, dist=15)],
             events=[(0.2, select(CHILD)), (0.5, topology(T_ROD))],
             keycap=steps((0.0, "Click", "select the child"),
                          (0.5, "Properties", "Topology:  Rod")),
             callouts=[Callout(CHILD, "Rod", 0.55, 0.97, offset=(-120, -90),
                               ring=False, color=TEAL)]),
        Shot(heading="The whole family follows",
             say="Now give the parent the Rod topology. The dome re-forms into "
                 "columns, and every child carries its own children along.",
             keys=[Key(0, az=60, el=18, dist=15, target=GRAND0 + 4),
                   Key(0.35, az=70, el=18, dist=34, target=(0, 0, 6)),
                   Key(1, az=110, el=14, dist=36)],
             events=[(0.15, select(ROOT)), (0.45, topology(T_ROD))],
             keycap=steps((0.0, "Click", "select the parent"),
                          (0.45, "Properties", "Topology:  Rod")),
             readout=readout),
        Shot(heading="No fixed limit",
             say="There's no fixed limit. A node can hold as many children as "
                 "memory allows, and each one can have children of its own.",
             keys=orbit(110, 200, el=18, dist=36, target=(0, 0, 6), el1=24,
                        dist1=40),
             events=[(0.05, defaults(geo=G_SPHERE, rgb=TEAL, scale=0.35, step=30,
                                     child_z=5))]
                    + spread(press_shift_n, BURST, 0.12, 0.8),
             keycap="Shift + N", keycap_note="held down",
             readout=readout),
        Shot(heading="Recap",
             say="That's parents and children.",
             keys=orbit(200, 240, el=24, dist=40, target=(0, 0, 6)), min_dur=6,
             summary=["N: a new node      Shift+N: a child of the selection",
                      "New Object Defaults: shape, color, size of what comes next",
                      "Any child can be a parent, to any depth",
                      "Topology: how a parent arranges its children"]),
    ]
    return Lesson(name="parent_children", title="Parents and Children",
                  nodes=[world()], shots=shots, use_window=True,
                  voice="af_heart")
