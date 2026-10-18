"""Lesson: Glyph Composer (1/2) — build a glyph level by level, insert it, and
use it as a Draw Mode brush.

Everything is the real app. The Composer is a real GlyphComposerDialog,
grabbed through Qt and shown beside the 3D view; each edit goes through the
dialog's own widgets, so the level list, the preview and the node count are
the ones a user sees. "Insert into Scene" and "Use as Draw Brush" are the
dialog's own buttons, and the painting is real mouse events into the Viewport
(which Draw Mode turns into stamps).

The anemone it builds: a blue sphere, ten cones, and four stalked spheres per
cone. 1 + 10 + 40 + 40 links = 91 nodes (checked in `prepare` against the
number the narration speaks).
"""
from PySide6.QtWidgets import QPushButton

from glyphviz_core.glyph_recipe import default_recipe, generate_nodes
from glyphviz_core.node import NODE_TYPE_GRID, Node
from lessonkit import (AMBER, CORAL, TEAL, Callout, Key, Lesson, Sec, Shot,
                       VIOLET)
from lessons._common import world
from lessons._ui import Script, Stroke, chain, ground, place, set_combo

GEO_CONE, TOPO_SPHERE = 5, 2
EXPECTED_NODES = 91                      # spoken in the narration

# --- layout (fractions of the frame; scale relative to a 1080-line frame)
DLG_X, DLG_Y, DLG_SCALE = 0.49, 0.135, 0.9
CREATE_X, CREATE_Y = 0.015, 0.19          # top left, clear of the meadow


def meadow(extents=(-24, 24, -14, 14), segments=(24, 14), z=0.0) -> Node:
    """A small World Grid, cut down to a 48 x 28 window so a few-unit glyph is
    a sensible size on it (a whole-earth grid would make every stamp a speck).
    `z` sinks it below the origin, for glyphs too big to sit on the ground."""
    g = Node(id=2, type=NODE_TYPE_GRID, parent_id=0, branch_level=0,
             translate_x=0, translate_y=0, translate_z=z,
             rotate_x=0, rotate_y=0, rotate_z=0, scale_x=1, scale_y=1, scale_z=1,
             color_r=30, color_g=62, color_b=44, color_a=255,
             geometry=21, hide=0, topo=8)
    g.set_grid_extents(*extents)
    g.set_grid_segments(*segments)
    return g


# --- widget handles ----------------------------------------------------------

def _dlg(L):
    return L.dlg


def _btn(L, text):
    return next(b for b in L.dlg.findChildren(QPushButton) if b.text() == text)


def _row(L, idx):
    """Frame rectangle of row `idx` of the Branch Levels list."""
    lw = L.dlg._level_list
    r = lw.visualItemRect(lw.item(idx))
    p = lw.mapTo(L.dlg, r.topLeft())
    pn, s = L.pn_comp, L.pn_comp.scale
    return (pn.x + p.x() * s - 3, pn.y + p.y() * s - 3,
            pn.x + (p.x() + r.width()) * s + 3, pn.y + (p.y() + r.height()) * s + 3)


def _center(rect):
    return ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)


def _scrolled(L, w):
    """Scroll the parameter form so `w` shows, as a user would."""
    L.dlg._param_scroll.ensureWidgetVisible(w, 0, 30)
    return w


def step(u, w=None, do=None, scroll=False, **kw):
    """A pointer step on a Composer widget (a getter: it is rebuilt per level)."""
    st = dict(u=u, pn=lambda L: L.pn_comp, **kw)
    if w is not None:
        st["w"] = (lambda L: _scrolled(L, w(L))) if scroll else w
    if do:
        st["do"] = do
    return st


def row_step(u, idx, do=None):
    return dict(u=u, at=lambda L: _center(_row(L, idx)),
                rect=lambda L: _row(L, idx), do=do)


def edit(fn):
    """An edit through a widget, then the preview refresh Auto-preview's
    350 ms timer would have done (a headless render has no event loop)."""
    def act(L):
        fn(L)
        L.dlg._do_preview()
    return act


def select_row(idx):
    return lambda L: L.dlg._level_list.setCurrentRow(idx)


# --- the lesson --------------------------------------------------------------

def on_ready(L):
    from glyphviz_gl.glyph_composer_dialog import GlyphComposerDialog
    w = L.win
    dlg = GlyphComposerDialog(w)
    # Taller than its default so the preview (the point of the window) is big.
    dlg._mini_vp.setMinimumHeight(340)
    dlg._mini_vp.setMaximumHeight(380)
    dlg.resize(1022, 800)
    dlg._do_preview()
    L.dlg = dlg
    L.show_comp = False
    L.pn_comp = place(L, dlg, DLG_X, DLG_Y, DLG_SCALE, "Glyph Composer")
    # The Create group's Draw Mode rows, cropped out of the Properties panel.
    # A never-shown window hasn't laid its widgets out: give the group a width
    # and activate its layout, or every child still has its 640x480 default.
    grp = w._draw_mode_btn.parentWidget()
    grp.setFixedWidth(560)
    grp.layout().activate()
    grp.resize(560, grp.sizeHint().height())
    top = w._draw_mode_btn.mapTo(grp, w._draw_mode_btn.rect().topLeft()).y() - 8
    bot = (w._draw_scale_jitter.mapTo(grp, w._draw_scale_jitter.rect().bottomLeft()).y()
           + 10)
    L.create_grp = grp
    L.pn_create = place(L, grp, CREATE_X, CREATE_Y, 1.0, "Create",
                        crop=(0, top, grp.width(), bot))
    L.show_create = False


def shifted(x, dist, k=0.39):
    """An orbit target that puts world x=`x` in the free left part of the
    frame, clear of the Composer window on the right: the target moves right
    of the subject by k of the view distance (at azimuth -90 the camera's
    right vector is +X)."""
    return (x + k * dist, 0.0, 2.5)


def panel_comp(L, u):
    return L.pn_comp if L.show_comp else None


def panel_both(L, u):
    """The Composer while it is up, then the Create panel once the brush is
    chosen (the Composer closes when the user goes back to the view)."""
    return L.pn_comp if L.show_comp else (L.pn_create if L.show_create else None)


def build() -> Lesson:
    def show_comp(on):
        def f(L):
            L.show_comp = on
        return f

    def show_create(on):
        def f(L):
            L.show_create = on
        return f

    def orbit(a0, a1, dist, el=26, x=0.0, d1=None):
        return [Key(0, az=a0, el=el, dist=dist, target=shifted(x, dist)),
                Key(1, az=a1, el=el, dist=d1 or dist,
                    target=shifted(x, d1 or dist))]

    # ---- composing actions (all through the dialog's own widgets)
    def count(n):
        return edit(lambda L: L.dlg._w_count.setValue(n))

    def geometry(g):
        return edit(lambda L: set_combo(L.dlg._w_geo, g))

    def topo(t):
        return edit(lambda L: set_combo(L.dlg._w_topo, t))

    def altitude(v):
        return edit(lambda L: L.dlg._w_tz.setValue(v))

    def link_on(thickness):
        def f(L):
            L.dlg._w_link_box.setChecked(True)
            L.dlg._w_link_ratio.setValue(thickness)
        return edit(f)

    def add_level(L):
        _btn(L, "+ Add Level").click()
        L.dlg._do_preview()

    def name_it(L):
        L.dlg._name_edit.setText("Anemone")

    def insert(L):
        _btn(L, "Insert into Scene").click()

    def reset_view(L):
        L.dlg._reset_preview_camera()

    def brush(L):
        _btn(L, "Use as Draw Brush").click()
        L.show_comp = False
        L.show_create = True
        L.win._table.select_by_ids(set())     # the view is the user's again

    def spacing(L):
        L.win._draw_spacing.setValue(120)

    def heading(L):
        L.win._draw_heading_jitter.setValue(180)

    def scale(L):
        L.win._draw_scale_jitter.setValue(30)

    def create(w):
        return dict(pn=lambda L: L.pn_create, w=lambda L: getattr(L.win, w))

    WIDE = dict(az=-90, el=32, dist=42, target=(0, 0, 2))

    # ---- 1: open
    s_open = Shot(
        title="Glyph Composer", heading="Build a glyph, level by level",
        say="The Glyph Composer builds a whole hierarchy of glyphs from a few "
            "short descriptions. Open it from the Tools menu, or press Control G.",
        keys=[Key(0, az=-90, el=28, dist=58, target=(0, 3, 3)),
              Key(1, az=-70, el=26, dist=46, target=shifted(0, 46))],
        keycap="Ctrl + G", keycap_note="Tools  >  Glyph Composer",
        events=[(Sec(8.7), show_comp(True))], tail=2.0,
        panel=panel_comp)

    # ---- 2: levels
    sc = Script([row_step(Sec(4.4), 0),
                 row_step(Sec(7.7), 1, do=select_row(1))],
                start=lambda L: (L.vp.width() * 0.62, L.vp.height() * 0.30))
    s_levels = Shot(
        heading="One description per level",
        say="A glyph is described one level at a time. Level zero is the root. "
            "Level one describes the children of the root, and that one "
            "description applies to every parent at that depth.",
        keys=orbit(-70, -62, 46), panel=panel_comp, tail=1.2,
        events=sc.events(), cursor=sc.cursor)

    # ---- 3: edit level one
    sc = Script([step(Sec(2.9), lambda L: L.dlg._w_count, do=count(10)),
                 step(Sec(4.7), lambda L: L.dlg._w_geo, do=geometry(GEO_CONE)),
                 step(Sec(6.9), lambda L: L.dlg._w_topo, do=topo(TOPO_SPHERE))])
    s_edit = Shot(
        heading="Edit a level",
        say="Select level one. Raise the count to ten, make the geometry a "
            "cone, and give it the Sphere topology, which decides how the next "
            "level is arranged around each cone.",
        keys=orbit(-62, -55, 46), panel=panel_comp, tail=1.8,
        events=sc.events(), cursor=sc.cursor)

    # ---- 4: altitude + gradient
    sc = Script([step(Sec(2.6), lambda L: L.dlg._w_tz, do=altitude(0.2), scroll=True),
                 step(Sec(5.2), lambda L: L.dlg._w_gradient_cb, scroll=True,
                      click=False)])
    s_place = Shot(
        heading="Placement and color",
        say="Altitude lifts the cones off their parent. And the color gradient "
            "blends around the ring.",
        keys=orbit(-55, -50, 46), panel=panel_comp, tail=1.8,
        events=sc.events(), cursor=sc.cursor)

    # ---- 5: level two with links
    sc = Script([step(Sec(2.5), lambda L: _btn(L, "+ Add Level"), do=add_level),
                 step(Sec(4.0), lambda L: L.dlg._w_count, do=count(4)),
                 step(Sec(5.7), lambda L: L.dlg._w_tz, do=altitude(1.5), scroll=True),
                 step(Sec(7.4), lambda L: L.dlg._w_link_box, do=link_on(0.06),
                      scroll=True)])
    s_level2 = Shot(
        heading="Add a level",
        say="Add Level makes the next generation. Four spheres per cone, "
            "lifted well clear, with Link to Parent turned on. Each link "
            "becomes a stem.",
        keys=orbit(-50, -45, 46), panel=panel_comp, tail=1.6,
        events=sc.events(), cursor=sc.cursor)

    # ---- 6a: name + reset
    sc = Script([step(Sec(1.3), lambda L: L.dlg._name_edit, do=edit(name_it)),
                 step(Sec(3.0), lambda L: _btn(L, "Reset View"), do=reset_view)])
    s_name = Shot(
        heading="Name it",
        say="Give it a name, and reset the view so the whole glyph shows.",
        keys=orbit(-45, -42, 46), panel=panel_comp, tail=2.2,
        events=sc.events(), cursor=sc.cursor)

    # ---- 6b: insert
    sc = Script([step(Sec(2.0), lambda L: _btn(L, "Insert into Scene"), do=insert)])
    s_insert = Shot(
        heading="Insert into Scene",
        say="Now press Insert into Scene. The whole glyph, ninety-one nodes, "
            "arrives in your scene, as a child of the selected node, or as a "
            "new root.",
        keys=[Key(0, az=-42, el=26, dist=46, target=shifted(0, 46)),
              Key(0.4, az=-38, el=24, dist=18, target=shifted(0, 18)),
              Key(1, az=-20, el=22, dist=14, target=shifted(0, 14))],
        panel=panel_comp, events=sc.events(), cursor=sc.cursor, tail=1.2,
        callouts=[Callout(3, "the anemone", 0.62, 0.98, offset=(-150, -130),
                          ring=False, color=TEAL)])

    # ---- 7: brush
    sc = Script([step(Sec(2.3), lambda L: _btn(L, "Use as Draw Brush"), do=brush)])
    s_brush = Shot(
        heading="Use it as a brush",
        say="Or, press Use as Draw Brush. Draw Mode switches on, and every "
            "click, or drag, in the view stamps a copy of the glyph onto the "
            "World Grid.",
        keys=[Key(0, az=-20, el=22, dist=14, target=shifted(0, 14)),
              Key(0.30, az=-12, el=26, dist=16, target=shifted(0, 16)),
              Key(0.70, **WIDE)],
        panel=panel_both, events=sc.events(), cursor=sc.cursor, tail=1.0)

    # ---- 8: spacing + jitter
    sc = Script([dict(u=Sec(5.6), do=spacing, **create("_draw_spacing")),
                 dict(u=Sec(7.7), do=heading, **create("_draw_heading_jitter")),
                 dict(u=Sec(9.5), do=scale, **create("_draw_scale_jitter"))],
                start=lambda L: (L.vp.width() * 0.5, L.vp.height() * 0.5))
    s_jitter = Shot(
        heading="Spacing and jitter",
        say="Under Create, in the Properties panel, Stamp Spacing sets how far "
            "apart the stamps fall. Heading Jitter turns each one. Scale "
            "Jitter resizes it. So nothing repeats.",
        keys=[Key(0, **WIDE), Key(1, **WIDE)],
        panel=panel_both, events=sc.events(), cursor=sc.cursor, tail=1.6)

    # ---- 9: paint
    stroke = Stroke(ground([(-22, -11), (-10, -6), (2, -10), (16, -5)]),
                    Sec(1.2), Sec(7.0))
    s_paint = Shot(
        heading="Paint",
        say="Drag across the grid, and paint.",
        keys=[Key(0, **WIDE), Key(1, **WIDE)],
        panel=panel_both, events=stroke.events(), cursor=stroke.cursor,
        min_dur=9.0)

    s_recap = Shot(
        heading="Recap",
        say="That's the Glyph Composer: one description per level, then insert "
            "it, or paint with it. Next, painting with imported trees.",
        keys=[Key(0, **WIDE), Key(1, az=-70, el=32, dist=48, target=(0, 1, 2))],
        min_dur=6.5,
        summary=["One description per level: count, geometry, topology",
                 "Add Level, and Link to Parent for stems",
                 "Insert into Scene, or Use as Draw Brush",
                 "Spacing and jitter vary every stamp"])

    shots = [s_open, s_levels, s_edit, s_place, s_level2, s_name, s_insert,
             s_brush, s_jitter, s_paint, s_recap]
    return Lesson(name="glyph_composer", title="Glyph Composer",
                  nodes=[world(), meadow()], shots=shots, use_window=True,
                  size=(1920, 1080), rate_clock=True, on_ready=on_ready,
                  voice="af_heart")
