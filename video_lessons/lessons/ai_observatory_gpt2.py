"""Example explainer: Inside GPT-2: Mary and John (AI Observatory 1 of 2).

Screenplay follows the gallery page glyphviz-docs/docs/examples/ai-observatory-
gpt2.md: why look inside -> whose idea this was -> the prompt -> the tower ->
features -> lit features and the giving chain -> rods -> attention heads and
the tug of war -> the prediction -> play it, with its own sound -> trace a
circuit -> caveats. Every number spoken is the page's (checked 2026-09-27).

Frames: 36 per token, 14 tokens, 504 frames at 30 fps (the soundtrack's own
rate). Token k owns frames 36k..36k+35; 'gave' is k=10, the last 'to' k=13,
whose window 468..503 is the scene's resting pose.

Node ids are the shipped scene's, looked up by label (the generator is
deterministic, so they hold until the scene is rebuilt):
  prompt tokens 5..18 ('Mary' 6, last 'to' 18); prediction on 'to' 33
  layer hubs 34 (L0) .. 272233 (L11); pinned features on the giving side
  98845 (L3) 123589 (L4) 148401 (L5) 173095 (L6) 197872 (L7), 296900 (L11)
  heads L9.H9 222703, L9.H6 222700, L10.H7 247477, L11.H10 272246
"""
from pathlib import Path

from lessonkit import Callout, Key, Lesson, Shot, AMBER, TEAL, VIOLET

REPO = Path(__file__).resolve().parents[2]
EX = REPO / "examples" / "AI_Observatory_GPT2_Example"
SCENE = EX / "AI_Observatory_GPT2_Example_gv_node.csv"
AUDIO = EX / "AI_Observatory_GPT2_Example.m4a"

F = 36
LAST = 14 * F - 1                 # 503: the resting pose, on the last 'to'


ROOT = 2
TOK_TO = 18
PRED = 33
L0_HUB, L11_HUB = 34, 272233
F_L3, F_L4, F_L6 = 98845, 123589, 173095
H9_9, H9_6, H10_7, H11_10 = 222703, 222700, 247477, 272246
BLUE = (99, 140, 255)

# World units: the root is scaled 1.6, so every file coordinate is x1.6 here
# (layer 0 at z 22, layer 11 at z 269, the prediction at z 301).
OVERVIEW = dict(target=(50, -40, 150), dist=560, az=-90, el=10)


def setup(L):
    # Viewer-side, for video size: bigger tag type (Properties > Display >
    # Tag Text Size), and the root's 130-character caption unpinned so it
    # doesn't run across every wide shot. Nothing is saved.
    L.vp._scene.world_node().tag_font_size = 13
    L.node(ROOT).show_text = 0
    L.vp.tags_touch()


WORDS = ["When", "Mary", "and", "John", "went", "to", "the", "store", ",",
         "John", "gave", "a", "drink", "to"]


def reading(L, u):
    k = min(int(L.win._ch_frame) // F, len(WORDS) - 1)
    return f"reading   {WORDS[k]!r:<9}\nword {k + 1:>2} of {len(WORDS)}"


def ov(u, **kw):
    c = dict(OVERVIEW)
    c.update(kw)
    return Key(u, az=c["az"], el=c["el"], dist=c["dist"], target=c["target"])


def build() -> Lesson:
    shots = [
        Shot(title="Inside GPT-2", heading="AI Observatory  ·  Mary and John",
             say="Even the people who build AI models can't easily see what "
                 "happens inside them. This scene lets you watch one at work: "
                 "GPT-2 small, reading a single sentence.",
             keys=[ov(0, az=-110, el=16, dist=640), ov(1, az=-96, el=12, dist=590)],
             ch_rate=0, ch_frame=LAST, select=set(), events=[(0.0, setup)],
             state=dict(show_tags=True, show_tags_selected_only=True)),
        Shot(heading="Why this exists",
             say="The AI Observatory was Claude's idea: a way to build trust in "
                 "AI by helping people see how these models actually work.",
             keys=[ov(0, az=-96, el=12, dist=590), ov(1, az=-86, el=10, dist=570)]),
        Shot(heading="The prompt",
             say="Along the front runs the prompt, one cube per token. When Mary "
                 "and John went to the store, John gave a drink to. The model's "
                 "job is to guess the next word.",
             keys=[ov(0, az=-86, el=10, dist=570),
                   Key(0.4, az=-90, el=22, dist=440, target=(20, -134, 12)),
                   Key(1, az=-88, el=20, dist=420)],
             callouts=[Callout(TOK_TO, "the word being read", 0.45, 0.97,
                               offset=(-60, 90), color=AMBER)]),
        Shot(heading="A tower of layers",
             say="Above it stands the model. Each of GPT-2's twelve layers is a "
                 "ring, and the spine through them is the residual stream: the "
                 "running total every layer reads from, and writes back to.",
             keys=[Key(0, az=-88, el=20, dist=420, target=(20, -134, 12)),
                   Key(0.35, az=-80, el=14, dist=420, target=(40, -20, 60)),
                   Key(1, az=-76, el=8, dist=480, target=(40, 0, 150))],
             callouts=[Callout(L0_HUB, "layer 0", 0.3, 0.6, offset=(-110, 50),
                               color=TEAL),
                       Callout(L11_HUB, "layer 11", 0.7, 0.98, offset=(-110, -60),
                               color=TEAL)]),
        Shot(heading="Every feature, in its place",
             say="Every point on a ring is a feature: one concept in a dictionary "
                 "learned by a sparse autoencoder. Nearly three hundred thousand of "
                 "them, placed by meaning, so a colour is a neighbourhood of "
                 "related ideas.",
             # Down into the tower from just above the top ring.
             keys=[Key(0, az=-76, el=8, dist=480, target=(40, 0, 150)),
                   Key(0.45, az=-60, el=40, dist=170, target=(40, -80, 269)),
                   Key(1, az=-50, el=42, dist=160)]),
        Shot(heading="What fires, lights up",
             say="The features firing right now become spheres, sized by how "
                 "strongly they fire, and the strongest on each layer pins its "
                 "label. Click any one to read it.",
             keys=[Key(0, az=-50, el=42, dist=160, target=(40, -80, 269)),
                   Key(0.45, az=-88, el=8, dist=210, target=(110, -99, 150)),
                   Key(1, az=-90, el=6, dist=200)],
             callouts=[Callout(F_L6, "a lit feature", 0.5, 0.97, offset=(-120, 70),
                               color=AMBER)],
             keycap="Click", keycap_note="read any feature's label"),
        Shot(heading="One idea, refined",
             say="Read them up this side of the tower, and the model is tracking "
                 "one idea: providing relief, then giving or donating, then the "
                 "action of giving something to someone. Six features in six "
                 "layers, sharpening one thought.",
             # The column L3..L8 stands at x 33-91, y -58..-99, z 91-199; aim
             # right of it so the pinned labels run across the frame.
             keys=[Key(0, az=-90, el=6, dist=200, target=(110, -99, 150)),
                   Key(0.2, az=-90, el=4, dist=270, target=(150, -95, 120)),
                   Key(1, az=-90, el=4, dist=270, target=(150, -95, 160))],
             callouts=[Callout(F_L3, "layer 3", 0.15, 0.45, offset=(-110, 30),
                               color=TEAL),
                       Callout(F_L4, "layer 4", 0.35, 0.65, offset=(-110, 30),
                               color=TEAL),
                       Callout(F_L6, "layer 6", 0.55, 0.97, offset=(-110, 30),
                               color=TEAL)]),
        Shot(heading="Attribution rods",
             say="The rods show which features drove which, from each layer to "
                 "the next. Orange pushes the next feature up, blue pushes it "
                 "down, and a thicker rod carries more.",
             keys=[Key(0, az=-90, el=4, dist=270, target=(150, -95, 160)),
                   Key(1, az=-62, el=20, dist=300, target=(50, -70, 160))]),
        Shot(heading="Attention heads",
             say="On a smaller inner ring below each layer sit its twelve "
                 "attention heads, the cones. They are the only way information "
                 "moves between words: each one looks back at an earlier word, "
                 "and fetches from it.",
             keys=[Key(0, az=-62, el=20, dist=300, target=(50, -70, 160)),
                   Key(0.5, az=-140, el=20, dist=230, target=(-20, -10, 230)),
                   Key(1, az=-130, el=18, dist=220)],
             callouts=[Callout(H9_9, "an attention head", 0.55, 0.97,
                               offset=(-130, 80), color=VIOLET)]),
        Shot(heading="A tug of war",
             say="On the last word, two heads look at Mary and push the answer "
                 "toward it. Another stares at the very same word, and pushes "
                 "back.",
             keys=[Key(0, az=-130, el=18, dist=220, target=(-20, -10, 230)),
                   Key(0.4, az=-100, el=12, dist=190, target=(10, -20, 228)),
                   Key(1, az=-104, el=12, dist=180)],
             callouts=[Callout(H9_9, "L9.H9  +3.03", 0.4, 0.97, offset=(-150, 60),
                               color=AMBER),
                       Callout(H9_6, "L9.H6  +2.75", 0.45, 0.97, offset=(-120, -80),
                               color=AMBER),
                       Callout(H10_7, "L10.H7  -3.16", 0.6, 0.97, offset=(150, -100),
                               color=BLUE)]),
        Shot(heading="The prediction",
             say="What survives reaches the top. GPT-2 predicts Mary, at sixty "
                 "eight percent.",
             keys=[Key(0, az=-104, el=12, dist=180, target=(10, -20, 228)),
                   Key(1, az=-90, el=12, dist=210, target=(70, 0, 290))],
             callouts=[Callout(PRED, "Mary, 68%", 0.4, 0.97, offset=(-120, 60),
                               color=AMBER)]),
        Shot(heading="Play it, and listen",
             say="Press Space, and the sentence plays through the model one word "
                 "at a time. The sound is made from the same numbers. Each layer "
                 "sounds its own note as the pulse climbs, louder when its "
                 "features fire harder, and a chime at the top marks the "
                 "prediction. Listen.",
             keys=[Key(0, az=-90, el=12, dist=210, target=(70, 0, 290)),
                   ov(0.2), ov(1, az=-80)],
             ch_frame=0, soundtrack=dict(path=AUDIO, frames=(0, LAST), fps=30,
                                         gain=0.55),
             readout=reading, keycap="Space", keycap_note="play"),
        Shot(heading="Trace a circuit",
             say="Researchers call the next step tracing a circuit, and you can do "
                 "it by hand. Stop on a word, click a lit sphere, read its label, "
                 "then follow its rods up the tower to the prediction.",
             keys=[ov(0, az=-80),
                   Key(0.5, az=-88, el=6, dist=230, target=(120, -99, 150)),
                   Key(1, az=-90, el=6, dist=240, target=(130, -95, 200))],
             ch_frame=LAST, select=set(), events=[(0.55, {"select": {F_L6}})]),
        Shot(heading="Honest caveats",
             say="Two caveats. The dictionary is a lens, not the model: it misses "
                 "part of what the model does. And the labels are machine-written "
                 "guesses. Click a few, and judge them for yourself.",
             keys=[Key(0, az=-90, el=6, dist=240, target=(130, -95, 200)),
                   ov(1, az=-100, el=14, dist=600)],
             select=set()),
        Shot(heading="Recap",
             say="That's GPT-2, reading one sentence.",
             keys=[ov(0, az=-100, el=14, dist=600), ov(1, az=-120, el=18, dist=640)],
             min_dur=7,
             summary=["Rings are layers; points are features",
                      "Spheres fire, rods drive, cones fetch",
                      "Heads tug the answer both ways: Mary, 68%",
                      "Examples Gallery: Inside GPT-2"]),
    ]
    return Lesson(name="ai_observatory_gpt2", title="Inside GPT-2",
                  nodes=[], shots=shots, use_window=True, scene_csv=str(SCENE),
                  voice="af_heart")
