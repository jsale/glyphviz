"""Example explainer: Building GlyphViz (Examples Gallery).

Screenplay follows the gallery page glyphviz-docs/docs/examples/building-
glyphviz.md: what the scene is -> how it is laid out -> how to read one
column -> the views worth flying to -> what the record shows -> try it.
Every number spoken is the page's (dated 2026-09-25; the scene grows with
every session, so re-check the page before re-rendering).

Node ids are the shipped scene's, looked up by label:
  nameplates/rails/months/legend: 32313..32374 (pinned in the scene)
  tallest column, 2026-06-22 "Add audio support": root 2018, cap 2020
Camera angles come from tools/capture_example_shots.py's CAMERA table.
Azimuth 270, never 90: at 90 the web bank renders on the LEFT.
"""
from pathlib import Path

from lessonkit import Callout, Key, Lesson, Shot, AMBER, CORAL, TEAL, VIOLET, CHALK

REPO = Path(__file__).resolve().parents[2]
SCENE = REPO / "examples" / "Building_GlyphViz_Example" / "building_glyphviz_gv_node.csv"

# Scene landmarks
RAIL_DESKTOP, RAIL_WEB = 32335, 32346          # outer bank edges, June end
EMPTY_EX, EMPTY_DOCS = 32329, 32331            # web lanes with 0 sessions
TALL_X, TALL_Y = -49.4, 48.0                   # tallest column (root 2018)

# The Five Archetypes scene teaches reading, as the gallery page recommends:
# the full scene is too dense for a close-up (the tallest column stands in a
# crowd of same-day neighbours). Its FEATURE BUILD exemplar is root 206, a
# GlyphViz Web session at x = 10.
ARCH = SCENE.parent / "Five_Archetypes" / "building_glyphviz_archetypes_gv_node.csv"
A_X = 10.0
A_PROMPT1, A_THINK1, A_READ, A_WRITE, A_FAIL = 210, 211, 214, 241, 249
A_COMMIT = 328
A_PROMPT2 = 272      # "Apologies, I accidentally closed the session tab. ..."
BLUE, GREEN = (99, 140, 255), (110, 210, 120)

STATS = ("sessions      222\n"
         "prompts     1,034\n"
         "tool calls ~29,000\n"
         "commits       381")


def _ensure_scene():
    """The 6 MB scene CSV is gitignored; the repo ships it zipped (the Burn
    Record pattern). Unpack it on a fresh clone so the lesson reproduces."""
    if SCENE.exists():
        return
    import zipfile
    packed = SCENE.parent / "Building_GlyphViz_Scene.zip"
    with zipfile.ZipFile(packed) as z:
        z.extract(SCENE.name, SCENE.parent)


def build() -> Lesson:
    _ensure_scene()
    def fly(u, x, y, z, az=270.0, el=-3.0):
        return Key(u, eye=(x, y, z), az=az, el=el, dist=20.0)

    def bigger_labels(L):
        # A viewer-side setting (Properties > Display > Tag Text Size), raised
        # so pinned labels read at video size. Not saved to the scene.
        L.vp._scene.world_node().tag_font_size = 14
        L.vp.tags_touch()

    def per_prompt(L, u):
        rows = [("June", 16), ("July", 25), ("August", 39), ("September", 43)]
        shown = [r for i, r in enumerate(rows) if u > 0.15 + 0.17 * i]
        if not shown:
            return None
        return "tool calls per prompt\n" + "\n".join(
            f"{m:<10} {'█' * (v // 3)} {v}" for m, v in shown)

    shots = [
        Shot(title="Building GlyphViz", heading="An Examples Gallery scene",
             say="GlyphViz was built by Jeff Sale working with Claude Code, one "
                 "session at a time. This scene reads every one of those "
                 "sessions back, through the tool they produced.",
             keys=[Key(0, az=270, el=20, dist=250, target=(0, 120, 10)),
                   Key(1, az=268, el=22, dist=215)],
             events=[(0.0, bigger_labels)], select=set(),
             state=dict(show_tags=True, show_tags_selected_only=True)),
        Shot(heading="One column per session",
             say="Each column is one working session: two hundred and twenty "
                 "two of them, from June to September, holding over a thousand "
                 "prompts, twenty nine thousand tool calls, and three hundred "
                 "and eighty one commits.",
             keys=[Key(0, az=268, el=22, dist=215, target=(0, 120, 10)),
                   Key(1, az=250, el=30, dist=185, target=(0, 140, 10))],
             readout=lambda L, u: STATS if u > 0.1 else None),
        Shot(heading="Two projects, side by side",
             say="The desktop app fills the left bank. Its browser port, "
                 "GlyphViz Web, fills the right. A teal rail and an amber rail "
                 "tell you which side you're on.",
             # Back far enough that both outer rails (x = +/-96) are in frame.
             keys=[Key(0, az=250, el=30, dist=185, target=(0, 140, 10)),
                   Key(0.45, az=270, el=16, dist=175, target=(0, 40, 6)),
                   Key(1, az=271, el=15, dist=168)],
             callouts=[Callout(RAIL_DESKTOP, "teal rail: desktop", 0.45, 0.97,
                               offset=(40, -90), color=TEAL),
                       Callout(RAIL_WEB, "amber rail: web", 0.55, 0.97,
                               offset=(-40, -90), color=AMBER)]),
        Shot(heading="Five kinds of session",
             say="Within each bank, five lanes hold five kinds of session: "
                 "design talk, quick fix, feature build, example authoring, "
                 "and docs and release.",
             keys=[Key(0, az=271, el=15, dist=168, target=(0, 40, 6)),
                   Key(0.3, az=285, el=26, dist=70, target=(-51, 10, 6)),
                   Key(1, az=262, el=26, dist=70, target=(51, 10, 6))]),
        Shot(heading="Front to back: the calendar",
             say="Front to back is the calendar. Both banks share it, so a "
                 "look across the gap shows what each project was doing that "
                 "same week.",
             keys=[Key(0, az=262, el=26, dist=70, target=(51, 10, 6)),
                   Key(0.5, az=270, el=10, dist=60, target=(0, 150, 9)),
                   Key(1, az=270, el=9, dist=52, target=(0, 165, 9))]),
        Shot(heading="Learn to read a column",
             scene=str(ARCH),
             say="To learn to read a column, the example includes a smaller "
                 "scene: five columns, one typical session of each kind, with "
                 "its own legend.",
             keys=[Key(0, az=92, el=12, dist=62, target=(0, 0, 9)),
                   Key(0.45, az=94, el=10, dist=56),
                   Key(0.75, az=96, el=6, dist=26, target=(-38, 0, 9)),
                   Key(1, az=95, el=6, dist=25)],
             events=[(0.0, bigger_labels)]),
        Shot(heading="Reading a column, bottom up",
             say="Read a column from the bottom up. A white sphere is a prompt "
                 "from Jeff, and the violet wire sphere beside it is Claude "
                 "thinking. Then the tool calls: blue for exploring, green for "
                 "editing, and red cones where something failed.",
             keys=[Key(0, az=95, el=6, dist=25, target=(-38, 0, 9)),
                   # Look down steeply: the base glyphs must sit mid-frame,
                   # clear of the caption bar.
                   Key(0.2, az=110, el=34, dist=8, target=(A_X, 0, 0.3)),
                   Key(1, az=80, el=28, dist=8.5, target=(A_X, 0, 2.6))],
             callouts=[Callout(A_PROMPT1, "prompt", 0.2, 0.42, offset=(-130, -70),
                               color=CHALK),
                       Callout(A_THINK1, "thinking", 0.3, 0.52, offset=(120, -90),
                               color=VIOLET),
                       Callout(A_READ, "explore", 0.45, 0.66, offset=(-130, 40),
                               color=BLUE),
                       Callout(A_WRITE, "edit", 0.6, 0.8, offset=(130, 40),
                               color=GREEN),
                       Callout(A_FAIL, "error", 0.74, 0.97, offset=(-130, -60),
                               color=CORAL)]),
        Shot(heading="Height is how much happened",
             say="Gold rings around the axis are commits. The coil turns a "
                 "fixed step for every event, so a column's height measures "
                 "how much happened, not how long it took.",
             keys=[Key(0, az=80, el=28, dist=8.5, target=(A_X, 0, 2.6)),
                   Key(0.35, az=85, el=12, dist=10, target=(A_X, 0, 13.2)),
                   Key(1, az=92, el=10, dist=58, target=(0, 0, 10))],
             callouts=[Callout(A_COMMIT, "commit", 0.25, 0.6, offset=(130, -60),
                               color=AMBER)]),
        Shot(heading="Click anything",
             say="Click any glyph to read it. A prompt shows the first line of "
                 "what Jeff actually typed.",
             keys=[Key(0, az=92, el=10, dist=58, target=(0, 0, 10)),
                   # Aim 5.5 units to the prompt's screen-right (right vector
                   # at az 100 is (-0.985, -0.174, 0)), so the sphere sits at
                   # the left edge and its ~1000 px label fits.
                   Key(0.4, az=100, el=10, dist=9, target=(3.77, -2.34, 7.0)),
                   Key(1, az=100, el=10, dist=8.6)],
             select=set(), events=[(0.42, {"select": {A_PROMPT2}})],
             keycap="Click", keycap_note="read a glyph's label"),
        Shot(heading="Straight down a column",
             scene=str(SCENE),
             say="Back in the full scene, look straight down a column, and the "
                 "coil becomes a rosette. Thinking gathers in the middle, while "
                 "the tool calls ring the outside. This is the tallest column "
                 "of all: June twenty second, adding audio support.",
             keys=[Key(0, az=0, el=89, dist=90, target=(TALL_X, TALL_Y, 27)),
                   Key(0.6, az=0, el=89, dist=34),
                   Key(1, az=-25, el=89, dist=31)],
             select=set(), events=[(0.0, bigger_labels)]),
        Shot(heading="What the record shows",
             say="The record shows how the collaboration changed. In June, one "
                 "prompt set off about sixteen tool calls. By September, forty "
                 "three. Fewer prompts, and bigger handoffs.",
             keys=[Key(0, az=-25, el=89, dist=31, target=(TALL_X, TALL_Y, 27)),
                   Key(0.35, az=215, el=22, dist=170, target=(-40, 150, 10)),
                   Key(1, az=200, el=18, dist=185, target=(-40, 170, 10))],
             readout=per_prompt),
        Shot(heading="The web port was all engine",
             say="And the web port was all engine. Fifty one of its fifty nine "
                 "sessions were feature builds, and its example and "
                 "documentation lanes stand empty.",
             keys=[Key(0, az=200, el=18, dist=185, target=(-40, 170, 10)),
                   Key(0.4, az=262, el=24, dist=85, target=(60, 30, 6)),
                   Key(1, az=255, el=24, dist=80)],
             callouts=[Callout(EMPTY_EX, "empty", 0.45, 0.97, offset=(-60, -90),
                               color=AMBER),
                       Callout(EMPTY_DOCS, "empty", 0.5, 0.97, offset=(60, -90),
                               color=AMBER)]),
        Shot(heading="Try it yourself",
             say="Download it from the Examples Gallery, press C, and fly down "
                 "the gap yourself.",
             keys=[Key(0, az=255, el=24, dist=80, target=(60, 30, 6)),
                   fly(0.3, 0, -25, 7),
                   fly(1, 0, 120, 7)],
             keycap="C", keycap_note="Camera Mode: fly the gap"),
        Shot(heading="Recap",
             say="That's Building GlyphViz.",
             keys=[fly(0, 0, 120, 7), fly(1, 0, 150, 7)], min_dur=7,
             summary=["222 sessions, 1,034 prompts, 381 commits",
                      "One column per session, read bottom to top",
                      "Tool calls per prompt: 16 in June, 43 by September",
                      "Examples Gallery: iluvdata.org/glyphviz"]),
    ]
    return Lesson(name="building_glyphviz", title="Building GlyphViz",
                  nodes=[], shots=shots, scene_csv=str(SCENE),
                  voice="af_heart")
