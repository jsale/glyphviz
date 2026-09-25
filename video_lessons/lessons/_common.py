"""Scene-building helpers shared by the lessons."""
from glyphviz_core.node import Node, ROTATION_MODE_EULER_XYZ

TYPE_WORLD, TYPE_GLYPH = 0, 5

# Geometry / topology ids (glyphviz-skill/references/node-csv-format.md)
G_CUBE, G_SPHERE, G_CONE, G_TORUS = 1, 3, 5, 7
G_OCTA, G_ICOSA, G_CYL, G_POINT = 11, 15, 19, 22
T_NONE, T_SPHERE, T_TORUS = 0, 2, 3


def world(bg=(14, 14, 26), **kw) -> Node:
    """The type-0 World row: carries the background colour and scene-wide
    tag settings. Never drawn."""
    n = glyph(1, 0, 0, geometry=G_POINT, color=(*bg, 255), hide=1, **kw)
    n.type = TYPE_WORLD
    return n


def glyph(id, parent, level, pos=(0, 0, 0), scale=(1, 1, 1), color=(200, 200, 200, 255),
          geometry=G_SPHERE, topo=T_NONE, hide=0, ratio=0.1, text="", rot=(0, 0, 0),
          **kw) -> Node:
    if len(color) == 3:
        color = (*color, 255)
    if not isinstance(scale, (tuple, list)):
        scale = (scale, scale, scale)
    n = Node(id=id, type=TYPE_GLYPH, parent_id=parent, branch_level=level,
             translate_x=pos[0], translate_y=pos[1], translate_z=pos[2],
             rotate_x=rot[0], rotate_y=rot[1], rotate_z=rot[2],
             scale_x=scale[0], scale_y=scale[1], scale_z=scale[2],
             color_r=color[0], color_g=color[1], color_b=color[2], color_a=color[3],
             geometry=geometry, hide=hide, topo=topo, ratio=ratio,
             rotation_mode=ROTATION_MODE_EULER_XYZ)
    n.text = text
    for k, v in kw.items():
        setattr(n, k, v)
    return n
