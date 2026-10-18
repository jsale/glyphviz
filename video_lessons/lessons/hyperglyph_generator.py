"""Lesson: the Hyperglyph Generator — discover a glyph, keep it, edit it, paint
with it.

A real HyperglyphGeneratorDialog and GlyphComposerDialog, grabbed through Qt
and driven through their own widgets and buttons. The rolls are real
Regenerate clicks: the dialog draws each new seed from Python's global RNG, so
the lesson seeds that RNG before each click (random.seed(1015), 1006, 1004) to
film particular designs. Idle Motion is the dialog's own, so its preview spins
on the video clock (Lesson.rate_clock).

The locked design is the 389-node one that seed 1808717700 gives at Max Nodes
800 / Branch Levels 5; Save Recipe writes it to out/ (the file chooser is
answered with the path), the Composer's Load Template reads it back, and the
Stamp list's Load... turns it into a brush.
"""
import random
from pathlib import Path

from PySide6.QtWidgets import QPushButton

from lessonkit import Key, Lesson, Sec, Shot
from lessons._common import world
from lessons._ui import (Script, Stroke, answering, chain, file_card, ground,
                         place)
from lessons.glyph_composer import (_btn, meadow, on_ready as composer_ready,
                                    row_step, select_row, step)

OUT = Path(__file__).resolve().parents[1] / "out" / "hyperglyph_generator"
ROLLS = (1015, 1006, 1004)               # the Regenerate presses filmed
KEEP_SEED = 1808717700                   # what random.seed(1004) draws
RECIPE = OUT / f"Hyperglyph_{KEEP_SEED}.json"
GEN_X, GEN_Y, GEN_SCALE = 0.52, 0.135, 0.95
WIDE = dict(az=-90, el=34, dist=135, target=(0, 0, -4))


def on_ready(L):
    from glyphviz_gl.hyperglyph_dialog import HyperglyphGeneratorDialog
    composer_ready(L)                    # the Composer dialog + Create panel
    OUT.mkdir(parents=True, exist_ok=True)
    gen = HyperglyphGeneratorDialog(L.win)
    gen.resize(700, 760)
    L.gen = gen
    L.show_gen = False
    L.pn_gen = place(L, gen, GEN_X, GEN_Y, GEN_SCALE, "Hyperglyph Generator")


def shifted(x, dist, k=0.36):
    return (x + k * dist, 0.0, 2.5)


def panel_gen(L, u):
    """Whichever window is up: the Generator, the Composer, or the Create panel."""
    if L.show_gen:
        return L.pn_gen
    if L.show_comp:
        return L.pn_comp
    return L.pn_create if L.show_create else None


def build() -> Lesson:
    def gbtn(L, text):
        return next(b for b in L.gen.findChildren(QPushButton) if b.text() == text)

    def gstep(u, w, do=None, **kw):
        st = dict(u=u, pn=lambda L: L.pn_gen, w=w, **kw)
        if do:
            st["do"] = do
        return st

    def roll(seed):
        def f(L):
            random.seed(seed)            # the seed this press will draw
            L.gen._regenerate()
        return f

    def open_gen(L):
        L.show_gen = True

    def set_levels(n):
        return lambda L: L.gen._w_branch_levels.setValue(n)

    def regen(L):
        L.gen._regenerate()              # Randomize is off: the Seed field rules

    def unrandomize(L):
        L.gen._w_randomize.setChecked(False)

    def insert(L):
        gbtn(L, "Insert into Scene").click()

    def save_recipe(L):
        assert L.gen._rng_seed == KEEP_SEED, L.gen._rng_seed
        with answering(save_path=RECIPE):
            gbtn(L, "Save Recipe…").click()

    def to_composer(L):
        L.show_gen = False
        L.show_comp = True

    def load_in_composer(L):
        with answering(open_path=RECIPE):
            L.dlg._load_template()

    def recolor(L):
        with answering(color=(255, 140, 30)):
            L.dlg._pick_start_color()
        L.dlg._do_preview()

    def to_create(L):
        L.show_comp = False
        L.show_create = True
        L.win._table.select_by_ids(set())

    def draw_on(L):
        L.win._draw_mode_btn.click()

    def load_stamp(L):
        with answering(open_path=RECIPE):
            L.win._on_draw_stamp_load()

    def spacing(L):
        L.win._draw_spacing.setValue(170)
        # The design reaches 13 units each way from its root, so draw it
        # 14 above the (sunken) meadow: a flock hovering over the ground.
        L.win._draw_z.setValue(14.0)
        L.win._draw_heading_jitter.setValue(180)
        L.win._draw_scale_jitter.setValue(40)

    # ---- 1: open
    s_open = Shot(
        title="Hyperglyph Generator", heading="Discover a glyph instead of designing one",
        say="The Glyph Composer is where you describe a glyph. The Hyperglyph "
            "Generator is where you discover one. Open it from the Tools menu, "
            "or press Control H.",
        keys=[Key(0, az=-90, el=28, dist=58, target=(0, 3, 3)),
              Key(1, az=-70, el=26, dist=46, target=shifted(0, 46))],
        keycap="Ctrl + H", keycap_note="Tools  >  Hyperglyph Generator",
        events=[(Sec(8.7), open_gen)], tail=2.0, panel=panel_gen)

    # ---- 2: parameters
    sc = Script([gstep(Sec(2.9), lambda L: L.gen._w_max_nodes,
                       do=lambda L: L.gen._w_max_nodes.setValue(800)),
                 gstep(Sec(4.9), lambda L: L.gen._w_branch_levels, click=False)],
                start=lambda L: (L.vp.width() * 0.62, L.vp.height() * 0.3))
    s_params = Shot(
        heading="Two limits",
        say="Max Nodes caps the size of the design. Branch Levels sets how "
            "deep it grows, counting the trunk.",
        keys=[Key(0, az=-70, el=26, dist=46, target=shifted(0, 46)),
              Key(1, az=-62, el=26, dist=46, target=shifted(0, 46))],
        panel=panel_gen, events=sc.events(), cursor=sc.cursor, tail=1.4)

    # ---- 3: regenerate
    sc = Script([gstep(Sec(1.6), lambda L: gbtn(L, "Regenerate"), do=roll(ROLLS[0])),
                 gstep(Sec(5.6), lambda L: L.gen._info_label, click=False,
                       rect=lambda L: L.pn_gen.rect(L.gen._info_label))])
    s_regen = Shot(
        heading="Regenerate",
        say="Press Regenerate, and a whole creature appears, all chosen for "
            "you. The readout gives its node count, family, palette and seed.",
        keys=[Key(0, az=-62, el=26, dist=46, target=shifted(0, 46)),
              Key(1, az=-55, el=26, dist=46, target=shifted(0, 46))],
        panel=panel_gen, events=sc.events(), cursor=sc.cursor, tail=1.6)

    # ---- 4: more rolls
    sc = Script([gstep(Sec(1.4), lambda L: gbtn(L, "Regenerate"), do=roll(ROLLS[1])),
                 gstep(Sec(3.6), lambda L: gbtn(L, "Regenerate"), do=roll(ROLLS[2]))])
    s_more = Shot(
        heading="Roll again",
        say="Press it again, and again. Every roll is a different design.",
        keys=[Key(0, az=-55, el=26, dist=46, target=shifted(0, 46)),
              Key(1, az=-50, el=26, dist=46, target=shifted(0, 46))],
        panel=panel_gen, events=sc.events(), cursor=sc.cursor, tail=3.0)

    # ---- 5: idle motion
    sc = Script([gstep(Sec(1.6), lambda L: L.gen._w_idle_motion, click=False)])
    s_idle = Shot(
        heading="Idle Motion",
        say="Idle Motion keeps every level turning against its parent, like "
            "an orrery, so a new hyperglyph is alive before any data drives it.",
        keys=[Key(0, az=-50, el=26, dist=46, target=shifted(0, 46)),
              Key(1, az=-46, el=26, dist=46, target=shifted(0, 46))],
        panel=panel_gen, events=sc.events(), cursor=sc.cursor, tail=2.4)

    # ---- 6: lock the seed
    sc = Script([gstep(Sec(3.2), lambda L: L.gen._w_randomize, do=unrandomize),
                 gstep(Sec(5.2), lambda L: L.gen._w_seed, click=False)])
    s_lock = Shot(
        heading="Lock it in",
        say="When one catches your eye, uncheck Randomize. That locks its "
            "seed, and the same seed, Max Nodes and Branch Levels always "
            "bring back the same design.",
        keys=[Key(0, az=-46, el=26, dist=46, target=shifted(0, 46)),
              Key(1, az=-42, el=26, dist=46, target=shifted(0, 46))],
        panel=panel_gen, events=sc.events(), cursor=sc.cursor, tail=1.6)

    # ---- 7: determinism
    sc = Script([gstep(Sec(1.7), lambda L: L.gen._w_branch_levels, do=set_levels(4)),
                 gstep(Sec(2.7), lambda L: gbtn(L, "Regenerate"), do=regen),
                 gstep(Sec(5.3), lambda L: L.gen._w_branch_levels, do=set_levels(5)),
                 gstep(Sec(6.4), lambda L: gbtn(L, "Regenerate"), do=regen)])
    s_same = Shot(
        heading="Same inputs, same design",
        say="Make it four levels, and Regenerate: a different design. Set it "
            "back to five, and Regenerate: the very same design returns.",
        keys=[Key(0, az=-42, el=26, dist=46, target=shifted(0, 46)),
              Key(1, az=-38, el=26, dist=46, target=shifted(0, 46))],
        panel=panel_gen, events=sc.events(), cursor=sc.cursor, tail=2.0)

    # ---- 8: insert
    sc = Script([gstep(Sec(1.8), lambda L: gbtn(L, "Insert into Scene"), do=insert)])
    s_insert = Shot(
        heading="Insert into Scene",
        say="Insert into Scene adds it to your scene, as a child of the "
            "selected node, or as a new root. Idle Motion comes along.",
        keys=[Key(0, az=-38, el=26, dist=46, target=shifted(0, 46)),
              Key(0.4, az=-30, el=22, dist=55, target=shifted(0, 55)),
              Key(1, az=10, el=20, dist=52, target=shifted(0, 52))],
        panel=panel_gen, events=sc.events(), cursor=sc.cursor, tail=3.0,
        min_dur=10.0)

    # ---- 9: save recipe
    sc = Script([gstep(Sec(1.8), lambda L: gbtn(L, "Save Recipe…"), do=save_recipe)])
    s_save = Shot(
        heading="Save Recipe",
        say="Save Recipe writes the design as a template, a small JSON file.",
        keys=[Key(0, az=10, el=20, dist=52, target=shifted(0, 52)),
              Key(1, az=22, el=20, dist=52, target=shifted(0, 52))],
        panel=panel_gen, events=sc.events(), cursor=sc.cursor, tail=2.6,
        card=file_card("Save Glyph Recipe", "...\\Documents",
                       [f"Hyperglyph_{KEEP_SEED}.json"], f"Hyperglyph_{KEEP_SEED}.json",
                       t0=0.30, t1=0.65))

    # ---- 10: edit it in the Composer
    sc = Script([step(Sec(3.7), lambda L: _btn(L, "Load Template…"),
                      do=load_in_composer),
                 row_step(Sec(5.6), 4, do=select_row(4)),
                 step(Sec(7.4), lambda L: L.dlg._w_color_start_btn, scroll=True,
                      do=recolor)])
    s_comp = Shot(
        heading="Edit it in the Composer",
        say="Open that file in the Glyph Composer with Load Template, and "
            "edit the design level by level. Pick a new color for a level, "
            "and the preview follows.",
        keys=[Key(0, az=22, el=20, dist=52, target=shifted(0, 52)),
              Key(1, az=30, el=20, dist=52, target=shifted(0, 52))],
        panel=panel_gen, events=[(Sec(0.3), to_composer)] + sc.events(),
        cursor=sc.cursor, tail=2.0)

    # ---- 11: paint a flock
    sc = Script([dict(u=Sec(3.2), pn=lambda L: L.pn_create,
                      w=lambda L: L.win._draw_stamp_load_btn, do=load_stamp),
                 dict(u=Sec(5.3), pn=lambda L: L.pn_create,
                      w=lambda L: L.win._draw_mode_btn, do=lambda L: (draw_on(L), spacing(L)))])
    flock = Stroke(ground([(-45, -20), (-15, -10), (15, -20), (45, -10)]),
                   Sec(6.6), Sec(12.6))
    s_flock = Shot(
        heading="Or paint with it",
        say="Or load the recipe into Draw Mode's Stamp list, and paint a "
            "flock of them. A recipe is always static, so the copies stand still.",
        keys=[Key(0, az=30, el=20, dist=52, target=shifted(0, 52)),
              Key(0.25, **WIDE)],
        panel=panel_gen, events=[(Sec(1.2), to_create)] + sc.events() + flock.events(),
        cursor=chain(sc.cursor, flock.cursor), tail=2.0, min_dur=17.0)

    s_recap = Shot(
        heading="Recap",
        say="For hundreds of designs at once, with ratings that steer later "
            "rolls, there is a command line version. That's the Hyperglyph "
            "Generator.",
        keys=[Key(0, **WIDE), Key(1, az=-70, el=34, dist=130, target=(0, 0, -4))],
        min_dur=7.0,
        summary=["Regenerate rolls a whole design",
                 "Uncheck Randomize to lock the seed",
                 "Insert into Scene, or Save Recipe",
                 "Edit it in the Composer, or paint with it"])

    shots = [s_open, s_params, s_regen, s_more, s_idle, s_lock, s_same,
             s_insert, s_save, s_comp, s_flock, s_recap]
    return Lesson(name="hyperglyph_generator", title="Hyperglyph Generator",
                  nodes=[world(), meadow((-60, 60, -34, 34), z=-14.0)], shots=shots, use_window=True,
                  size=(1920, 1080), rate_clock=True, on_ready=on_ready,
                  voice="af_heart")
