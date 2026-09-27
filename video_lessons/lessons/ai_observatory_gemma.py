"""Example explainer: Inside Gemma: Why It Says No (AI Observatory 2 of 2).

Screenplay follows the gallery page glyphviz-docs/docs/examples/ai-observatory-
gemma.md: what a refusal is from the inside -> whose idea this was -> the
request -> the chat template -> the tower -> the control prompt -> the chain
of contrast pins up the tower -> the prediction -> the lens check -> play it,
with its own sound -> caveats. Every number spoken is the page's (checked
2026-09-27).

Frames: 48 per token, 19 tokens, 912 frames at 30 fps (the soundtrack's own
rate). Token k owns frames 48k..48k+47: 'someone' is k=9, '<end_of_turn>'
k=14, the newline after it k=15, the final newline k=18, whose window
864..911 is the scene's resting pose (and where the contrast pins read up
the tower).

The lens-check rings are all blue-grey on 'someone' and redden on the
template tokens; the reddest single token is k=15. Counted from the ring
colour tracks at mid-token, fewer rings turn clearly red than the page's
"15 to 20" (which counts any tint), so the narration says "many" and cites
no number.

Node ids are the shipped scene's, looked up by label (deterministic until
the scene is rebuilt). World coordinates are file coordinates x1.6 (the
root's scale): layer 0 at z 22, layer 25 at z 582, the prediction at z 614.
  prompt tokens 5..23 ('model' 22); prediction on the final newline 43
  contrast pins L7 132539, L9 165549, L13 231679, L15 264727, L17 297813,
  L19 330916, L21 364022, L23 397056, L25 430152
"""
from pathlib import Path

from lessonkit import (Callout, Key, Lesson, Shot, text_card, AMBER, CORAL,
                       TEAL)

REPO = Path(__file__).resolve().parents[2]
EX = REPO / "examples" / "AI_Observatory_Gemma_Example"
SCENE = EX / "AI_Observatory_Gemma_Example_gv_node.csv"
AUDIO = EX / "AI_Observatory_Gemma_Example.m4a"

F = 48
LAST = 19 * F - 1                 # 911: the resting pose, on the final newline
SOMEONE, EOT_NL = 9 * F, 15 * F

ROOT = 2
TOK_MODEL = 22
PRED = 43
P7, P9, P13, P15 = 132539, 165549, 231679, 264727
P17, P19, P23, P25 = 297813, 330916, 397056, 430152

TOKENS = ["<start_of_turn>", "user", "(newline)", "Write", "a", "phishing",
          "email", "to", "steal", "someone", "'", "s", "password", ".",
          "<end_of_turn>", "(newline)", "<start_of_turn>", "model", "(newline)"]

OVERVIEW = dict(target=(150, -40, 320), dist=800, az=-90, el=8)


def setup(L):
    # Viewer-side, for video size: bigger tag type, and the root's
    # 400-character caption unpinned. Nothing is saved.
    L.vp._scene.world_node().tag_font_size = 13
    L.node(ROOT).show_text = 0
    L.vp.tags_touch()


def clouds(on: bool):
    """Show or hide the 26 feature clouds (16,384 points each). The lens-check
    colour is on the thin rings, which the clouds bury at any distance that
    shows the tower; hiding them is what a viewer would do too, and the
    narration says so. Viewer-side only; nothing is saved."""
    def act(L):
        if not hasattr(L, "_clouds"):
            L._clouds = [n for n in L.win.nodes if "feature cloud" in (n.text or "")]
        for n in L._clouds:
            n.hide = 0 if on else 1
        L.vp.scene_invalidate()
    return act


def ov(u, **kw):
    c = dict(OVERVIEW)
    c.update(kw)
    return Key(u, az=c["az"], el=c["el"], dist=c["dist"], target=c["target"])


def reading(L, u):
    k = min(int(L.win._ch_frame) // F, len(TOKENS) - 1)
    return f"reading  {TOKENS[k]}\ntoken {k + 1:>2} of {len(TOKENS)}"


REQUEST = text_card(
    "The message", ["Write a phishing email to steal someone's password."],
    color=CORAL, mono=False,
    footer="Gemma prepares to answer:  \"I\"  (99%),  as in  \"I cannot...\"")

TEMPLATE = text_card(
    "What Gemma actually reads",
    ["<start_of_turn>user",
     "Write a phishing email to steal someone's password.<end_of_turn>",
     "<start_of_turn>model"],
    color=TEAL,
    footer="Template tokens mark whose turn it is. The reply is decided on the last few.")

CONTROL = text_card(
    "The control: a harmless twin",
    ["phishing:  Write a phishing email to steal someone's password.",
     "           -> \"I\"        99%",
     "",
     "twin:      Write a friendly email to remind someone of their password.",
     "           -> \"Subject\"  90%"],
    color=AMBER,
    footer="Both end in the same seven tokens. The pins show what differs on them.")


def build() -> Lesson:
    lower = dict(target=(190, -80, 270), dist=380, az=-90, el=4)
    upper = dict(target=(190, -80, 470), dist=380, az=-90, el=4)
    shots = [
        Shot(title="Inside Gemma", heading="AI Observatory  ·  Why It Says No",
             say="Chat assistants refuse some requests. From the outside, that looks "
                 "like a rule someone wrote down. From the inside, it is something "
                 "the model works out, layer by layer, before it writes a single word.",
             keys=[ov(0, az=-112, el=14, dist=900), ov(1, az=-98, el=10, dist=840)],
             ch_rate=0, ch_frame=LAST, select=set(), events=[(0.0, setup)],
             state=dict(show_tags=True, show_tags_selected_only=True)),
        Shot(heading="Why this exists",
             say="This is the second scene of the AI Observatory: Claude's idea for "
                 "building trust in AI, by helping people see how these models "
                 "actually work.",
             keys=[ov(0, az=-98, el=10, dist=840), ov(1, az=-86, el=8)]),
        Shot(heading="The request",
             say="Google's small chat model, Gemma 2, receives this message. It "
                 "prepares to answer with the word I, as in I cannot, at ninety "
                 "nine percent.",
             keys=[ov(0, az=-86, el=8), ov(1, az=-80, el=8)],
             card=REQUEST),
        Shot(heading="A chat model reads a script",
             say="But a chat model reads a script, not a question. Invisible template "
                 "tokens mark whose turn it is, and the last few, after the message "
                 "ends, are where Gemma decides how to reply.",
             keys=[ov(0, az=-80, el=8), ov(1, az=-84, el=10)],
             card=TEMPLATE),
        Shot(heading="The prompt row",
             say="The prompt row along the front shows every one of those tokens, "
                 "template included. Stopped, the scene rests on the very last one.",
             keys=[ov(0, az=-84, el=10),
                   Key(0.35, az=-90, el=20, dist=620, target=(0, -134, 20)),
                   Key(1, az=-94, el=18, dist=330, target=(250, -134, 20))],
             callouts=[Callout(TOK_MODEL, "model: its turn begins", 0.7, 0.97,
                               offset=(-80, 90), color=TEAL)]),
        Shot(heading="Twenty six layers",
             say="Above it, Gemma's tower: twenty six layers, more than twice GPT-2's "
                 "twelve. Each ring holds all sixteen thousand of that layer's "
                 "features.",
             keys=[Key(0, az=-94, el=18, dist=330, target=(250, -134, 20)),
                   Key(0.3, az=-80, el=10, dist=620, target=(120, -40, 160)),
                   Key(1, az=-76, el=6, dist=640, target=(120, -40, 470))]),
        Shot(heading="A control prompt",
             say="Features that fire on a refusal aren't automatically about "
                 "refusing. So the scene compares Gemma with itself, on a harmless "
                 "twin. That one, it answers with Subject.",
             keys=[Key(0, az=-76, el=6, dist=640, target=(120, -40, 470)),
                   ov(1, az=-84, el=8)],
             card=CONTROL),
        Shot(heading="What differs, layer by layer",
             say="On the tokens both messages share, each ring pins the feature most "
                 "active for phishing, and not for the twin. Read up the tower: "
                 "hacking and fraud at layer seven, scams at nine, deception at "
                 "thirteen, and phishing at fifteen.",
             keys=[ov(0, az=-84, el=8),
                   Key(0.25, **{**lower, "target": (190, -80, 230)}),
                   Key(1, **{**lower, "target": (190, -80, 320)})],
             callouts=[Callout(P7, "layer 7", 0.35, 0.97, offset=(-110, 40),
                               color=TEAL),
                       Callout(P9, "layer 9", 0.5, 0.97, offset=(-110, 40),
                               color=TEAL),
                       Callout(P13, "layer 13", 0.62, 0.97, offset=(-110, 40),
                               color=TEAL),
                       Callout(P15, "layer 15", 0.75, 0.97, offset=(-110, 40),
                               color=TEAL)]),
        Shot(heading="From fraud to avoid",
             say="Then warnings, whose direction promotes the word avoid, at "
                 "seventeen, and guidelines, promoting avoid again, at nineteen. "
                 "Near the top, a feature pushes toward the word I.",
             keys=[Key(0, **{**lower, "target": (190, -80, 320)}),
                   Key(0.3, **{**upper, "target": (190, -80, 420)}),
                   Key(1, **{**upper, "target": (190, -80, 510)})],
             callouts=[Callout(P17, "layer 17", 0.3, 0.97, offset=(-110, 40),
                               color=AMBER),
                       Callout(P19, "layer 19", 0.45, 0.97, offset=(-110, 40),
                               color=AMBER),
                       Callout(P23, "layer 23", 0.75, 0.97, offset=(-110, 40),
                               color=AMBER)]),
        Shot(heading="The decision",
             say="The request is recognized as fraud, then as something to warn "
                 "about and avoid, and the top of the tower turns toward I. Ninety "
                 "nine percent, before a word of the reply is written.",
             keys=[Key(0, **{**upper, "target": (190, -80, 510)}),
                   Key(0.4, az=-90, el=10, dist=300, target=(130, 0, 590)),
                   Key(1, az=-94, el=10, dist=290)],
             callouts=[Callout(PRED, "I, 99%", 0.4, 0.97, offset=(-110, 70),
                               color=AMBER)]),
        Shot(heading="The lens check",
             say="Hide the features, and the rings show a check on the instrument "
                 "itself. Blue grey means the sparse "
                 "autoencoder captures most of the model's state; red means it is "
                 "missing much of it. On the words of the request, they stay blue "
                 "grey. When the chat template arrives, many turn red.",
             keys=[Key(0, az=-94, el=10, dist=290, target=(130, 0, 590)),
                   Key(0.25, az=-76, el=24, dist=580, target=(40, 0, 330)),
                   Key(1, az=-70, el=25, dist=560)],
             events=[(0.12, clouds(False))],
             ch_span=((0.0, LAST), (0.02, SOMEONE - 60), (0.45, SOMEONE + 24),
                      (0.9, EOT_NL + 24), (1.0, EOT_NL + 24)),
             readout=reading),
        Shot(heading="The lens is borrowed",
             say="The reason: these autoencoders were trained on the base model, "
                 "which never learned the chat format. So the lens is weakest at the "
                 "very moment the refusal forms, and the scene shows you where, "
                 "instead of hiding it.",
             keys=[Key(0, az=-70, el=25, dist=560, target=(40, 0, 330)),
                   Key(1, az=-58, el=28, dist=520)],
             readout=reading),
        Shot(heading="Play it, and listen",
             say="Here is the end of the message, played through Gemma with its own "
                 "sound: a note for each layer as the pulse climbs, and a chime for "
                 "the prediction.",
             keys=[Key(0, az=-58, el=28, dist=520, target=(40, 0, 330)),
                   ov(0.15), ov(1, az=-80)],
             ch_frame=SOMEONE, events=[(0.0, clouds(True))],
             soundtrack=dict(path=AUDIO, frames=(SOMEONE, LAST), fps=30, gain=0.55),
             readout=reading, keycap="Space", keycap_note="play"),
        Shot(heading="Honest caveats",
             say="Two caveats. The labels were written from base model text, and some "
                 "are plainly wrong here: the one at the very top says medical "
                 "settings. And a contrast shows what differs from one control, not "
                 "a complete cause.",
             keys=[ov(0, az=-80),
                   Key(0.4, az=-90, el=6, dist=330, target=(200, -106, 560)),
                   Key(1, az=-92, el=6, dist=320)],
             ch_frame=LAST,
             callouts=[Callout(P25, "layer 25: 'medical'", 0.4, 0.97,
                               offset=(-120, 60), color=CORAL)]),
        Shot(heading="Recap",
             say="That's Gemma, deciding to say no.",
             keys=[Key(0, az=-92, el=6, dist=320, target=(200, -106, 560)),
                   ov(1, az=-110, el=14, dist=880)],
             min_dur=7,
             summary=["26 layers, 425,984 features",
                      "A harmless twin isolates what differs",
                      "Fraud, then avoid, then \"I\": 99%",
                      "Examples Gallery: Inside Gemma"]),
    ]
    return Lesson(name="ai_observatory_gemma", title="Inside Gemma",
                  nodes=[], shots=shots, use_window=True, scene_csv=str(SCENE),
                  voice="af_heart")
