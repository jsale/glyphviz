"""Lesson: Glyph Composer (2/2) — import a template, paint a forest.

The Glyph Composer's Load Template button and Draw Mode's brush list are the
app's own: two Tree Designer templates (assets/trees/*.json, written by
assets/make_trees.mjs, which runs the designer's own buildRecipe) are loaded
through the real `_load_template` and `_on_draw_stamp_load` handlers (the file
chooser is answered with the path), and the forest is real mouse strokes into
the Viewport, stamped by Draw Mode.
"""
from pathlib import Path

from lessonkit import Callout, Key, Lesson, Sec, Shot, TEAL
from lessons._common import world
from lessons._ui import (Script, Stroke, answering, chain, file_card, ground,
                         image_card, place, set_combo)
from lessons.glyph_composer import (_btn, meadow, on_ready, panel_both,
                                    panel_comp, row_step, select_row, shifted,
                                    step)

REPO = Path(__file__).resolve().parents[2]
TREES = REPO / "video_lessons" / "assets" / "trees"
OAK = TREES / "Mighty_Oak.json"
CHERRY = TREES / "Cherry_Blossom.json"
DESIGNER_SHOT = REPO / "glyphviz-docs" / "docs" / "assets" / "screenshots" / "tree-designer-presets.png"

WIDE = dict(az=-90, el=34, dist=105, target=(0, 0, 4))


def build() -> Lesson:
    def show_comp(on):
        def f(L):
            L.show_comp = on
        return f

    def load_oak(L):
        with answering(open_path=OAK):
            L.dlg._load_template()

    def brush(L):
        w = L.win
        _btn(L, "Use as Draw Brush").click()
        L.show_comp = False
        L.show_create = True
        # Tree-sized settings: a wide spacing, and some jitter so the stamps
        # differ (the knobs Part 1 introduced).
        w._draw_spacing.setValue(90)
        w._draw_heading_jitter.setValue(180)
        w._draw_scale_jitter.setValue(25)

    def load_cherry(L):
        with answering(open_path=CHERRY):
            L.win._on_draw_stamp_load()

    def pick_stamp(i):
        return lambda L: L.win._draw_stamp_combo.setCurrentIndex(i)

    def leave_draw(L):
        L.vp.set_draw_mode(False)
        L.show_create = False

    # ---- 1: what a template is
    s_intro = Shot(
        title="Paint a Forest", heading="Import a template, paint with it",
        say="A Glyph Composer template is a small JSON file, so a glyph made "
            "anywhere can be loaded here. The Hyperglyph Tree Designer, which "
            "runs in your browser, exports branching trees as templates.",
        keys=[Key(0, **WIDE), Key(1, az=-80, el=32, dist=100, target=(0, 0, 4))],
        card=image_card(DESIGNER_SHOT, "Hyperglyph Tree Designer",
                        "Download .json  ->  a Glyph Composer template",
                        t0=0.50, t1=0.99, width=0.46),
        tail=2.0)

    # ---- 2: load the oak
    sc = Script([step(Sec(2.6), lambda L: _btn(L, "Load Template…"))])
    s_load = Shot(
        heading="Load Template",
        say="In the Composer, press Load Template and choose the file. Here, "
            "a mighty oak.",
        keys=[Key(0, **WIDE), Key(1, az=-60, el=26, dist=34, target=shifted(0, 34))],
        panel=panel_comp, events=[(Sec(0.0), show_comp(True))] + sc.events()
        + [(Sec(5.9), load_oak)],
        cursor=sc.cursor, tail=3.4,
        card=file_card("Load Glyph Template", "...\\Downloads",
                       ["Cherry_Blossom.json", "Mighty_Oak.json"], "Mighty_Oak.json",
                       t0=0.33, t1=0.76))

    # ---- 3: look inside
    sc = Script([row_step(Sec(3.0), 2, do=select_row(2)),
                 row_step(Sec(5.8), 6, do=select_row(6))],
                start=lambda L: (L.vp.width() * 0.62, L.vp.height() * 0.30))
    s_inside = Shot(
        heading="Seven levels",
        say="Seven levels of limbs, joints and leaves, four hundred and "
            "eighty-six nodes, all from one small file.",
        keys=[Key(0, az=-60, el=26, dist=34, target=shifted(0, 34)),
              Key(1, az=-50, el=24, dist=34, target=shifted(0, 34))],
        panel=panel_comp, events=sc.events(), cursor=sc.cursor, tail=1.6)

    # ---- 4: brush + oaks
    sc = Script([step(Sec(1.9), lambda L: _btn(L, "Use as Draw Brush"), do=brush)])
    oaks1 = Stroke(ground([(-34, 21), (-18, 29), (-2, 21), (14, 29), (30, 21), (46, 28)]),
                   Sec(3.4), Sec(10.6))
    s_oaks = Shot(
        heading="A brush of oaks",
        say="Press Use as Draw Brush, and drag. Every stamp is a whole oak, "
            "turned and sized a little differently, so the forest looks grown, "
            "not copied.",
        keys=[Key(0, az=-50, el=24, dist=34, target=shifted(0, 34)),
              Key(0.22, **WIDE)],
        panel=panel_both, tail=2.0,
        events=sc.events() + oaks1.events(), cursor=chain(sc.cursor, oaks1.cursor),
        min_dur=13.0)

    # ---- 5: cherry
    sc = Script([dict(u=Sec(3.0), pn=lambda L: L.pn_create,
                      w=lambda L: L.win._draw_stamp_load_btn, do=load_cherry)],
                start=lambda L: (L.vp.width() * 0.5, L.vp.height() * 0.5))
    cherries = Stroke(ground([(-44, 8), (-26, 1), (-8, 9), (10, 0), (28, 9), (44, 2)]),
                      Sec(4.8), Sec(10.8))
    s_cherry = Shot(
        heading="A second template",
        say="Load a second template, a cherry tree, straight into the Stamp "
            "list. Both brushes stay available.",
        keys=[Key(0, **WIDE), Key(1, **WIDE)],
        panel=panel_both, tail=1.5,
        events=sc.events() + cherries.events(),
        cursor=chain(sc.cursor, cherries.cursor), min_dur=12.5)

    # ---- 6: switch brush
    sc = Script([dict(u=Sec(1.9), pn=lambda L: L.pn_create,
                      w=lambda L: L.win._draw_stamp_combo, do=pick_stamp(1))],
                start=lambda L: (L.vp.width() * 0.5, L.vp.height() * 0.5))
    oaks2 = Stroke(ground([(-44, -14), (-28, -23), (-10, -13), (8, -24), (26, -14), (42, -23)]),
                   Sec(3.4), Sec(8.2))
    s_switch = Shot(
        heading="Switch brushes",
        say="Switch between them as you paint, to mix the two in one scene.",
        keys=[Key(0, **WIDE), Key(1, **WIDE)],
        panel=panel_both, tail=1.5,
        events=sc.events() + oaks2.events(),
        cursor=chain(sc.cursor, oaks2.cursor), min_dur=10.0)

    # ---- 7: leave draw mode, look around
    s_look = Shot(
        heading="Look around",
        say="Press D, or Escape, to leave Draw Mode, then look around. Two "
            "imported templates, one forest, painted in a minute.",
        keys=[Key(0, **WIDE),
              Key(0.30, az=-70, el=24, dist=88, target=(0, 4, 5)),
              Key(1, az=-10, el=22, dist=80, target=(0, 4, 5))],
        keycap="D", keycap_note="or Esc: leave Draw Mode",
        events=[(Sec(2.7), leave_draw)], tail=2.5, min_dur=12.0)

    s_recap = Shot(
        heading="Recap",
        say="Any template becomes a brush: Load Template in the Composer, or "
            "Load in the Stamp list. Next, the Hyperglyph Generator.",
        keys=[Key(0, az=-10, el=22, dist=80, target=(0, 4, 5)),
              Key(1, az=20, el=24, dist=82, target=(0, 4, 5))],
        min_dur=7.0,
        summary=["Templates are small .json files, from anywhere",
                 "Composer: Load Template, then Use as Draw Brush",
                 "Or Load... in the Stamp list: keep several brushes",
                 "Heading and Scale Jitter make a forest, not a copy"])

    shots = [s_intro, s_load, s_inside, s_oaks, s_cherry, s_switch, s_look,
             s_recap]
    return Lesson(name="glyph_composer_forest", title="Glyph Composer",
                  nodes=[world(), meadow((-60, 60, -34, 34))], shots=shots, use_window=True,
                  size=(1920, 1080), rate_clock=True, on_ready=on_ready,
                  voice="af_heart")
