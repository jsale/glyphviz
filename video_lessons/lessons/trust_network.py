"""Example explainer: Trust and Betrayal (the Bitcoin OTC trust network).

Screenplay follows the gallery page glyphviz-docs/docs/examples/trust-
network.md: the marketplace -> the glyph, read on the scene's own labelled
specimen -> the colour key -> the shared frame -> links and cones -> then
the part a first-time viewer misses: the animation is the marketplace
GROWING over five real years, not a layout settling.

Every number spoken is the page's, or was measured on the shipped scene
through the real engine (2026-10-03):
  * 13 traders at frame 0, 922 at the end; 17,235 ratings drawn.
  * Running "distrusted" (mean received below -0.5, the page's class rule,
    read back from each root's channel-driven colour): 0 -> 119.
  * User 3744 (root 10335): 74 ratings received, 69 of them cones; 55 of
    the 74 arrive in March-April 2013. Appears at frame 54, red by 60.
  * Red clustering, final frame: a distrusted trader's 8 nearest roots are
    38% distrusted against a 13% base rate (~3x). Distrusted accounts first
    appear at a median frame of 56 (mid-2013) vs 33 for the rest, and they
    sit on the side of the cloud that grew last (centroid 80 units toward
    +Y). Not because they rated each other: links between two distrusted
    accounts are 13% of theirs, exactly chance. So the narration says
    "arrived late, gathered on the side that grew last", and no more.
Frame f is day 16.0 * f after 2010-11-08 (120 frames to 2016-01-25).
"""
import datetime as dt
from pathlib import Path

from lessonkit import Callout, Key, Lesson, Shot, AMBER, CHALK, CORAL, TEAL

REPO = Path(__file__).resolve().parents[2]
SCENE = (REPO / "examples" / "Trust_Network_Example" / "Bitcoin_Trust"
         / "Bitcoin_Trust_gv_node.csv")

# Landmarks (node ids, by label)
KEY, KEY_NORTH, KEY_SOUTH = 31190, 31191, 31203
KEY_RED, KEY_ROUTINE, KEY_GREEN = 31193, 31197, 31201
TRUSTED_1 = 2                  # "user 1 - 157 received (mean +4.0)": north spokes
                               # routine 76, trust 38, strong trust 43, no red
ACCUSED_3744 = 10335           # 69 accusation cones converge on it
ACCUSED_SPOKE = 10338          # "received strong distrust (-10 to -5): 68"
KEY_POS = (0.0, -304.0, 60.0)
# 3744 sits on the cloud's edge, outward (-0.47, 0.71, 0.46) from the centre.
# Seen from azimuth ~34, screen-right runs along that outward direction, so
# aiming 35 units inward of it puts the account right of centre with open sky
# beyond, and its accusers' cones arrive from the cloud on the left.
STARBURST = (-44.0, 67.0, 58.0)
RED_SIDE = (6.0, 80.0, 14.0)   # centroid of the distrusted accounts

T0 = dt.datetime(2010, 11, 8)
DAYS_PER_FRAME = 1904 / 119
LAST = 119
GREEN = (86, 240, 118)
RED = (232, 58, 58)


GUIDES = 31173      # legend + specimen glyph ids are 31173 and up


def pins(traders: bool, guides: bool):
    """Show or hide the scene's pinned labels: the eight pinned traders, and
    the guides (legend + specimen glyph). At video size, the trader pins
    stack over everything from a wide angle, and the legend's land on the
    cloud, so each shot asks for the ones it needs. Viewer-side; never saved."""
    def act(L):
        if not hasattr(L, "_pinned"):
            L._pinned = [n for n in L.win.nodes if n.show_text]
        for n in L._pinned:
            n.show_text = int(guides if n.id >= GUIDES else traders)
        L.vp.tags_touch()
    return act


def rating_links(on: bool):
    """Hide the 17,235 rating links while the glyph is being read, and bring
    them back when the narration introduces them. Up close, a solid cone
    passing the camera is a red girder (the gallery page's own warning), so
    reading a glyph inside the full cloud is hopeless. Applied only while the
    animation is paused; the first animation shot re-applies every channel-
    driven hide flag from frame 0."""
    def act(L):
        for n in L.win.nodes:
            if n.type == 7 and n.geometry in (5, 27):
                n.hide = 0 if on else 1
        L.vp.scene_touch()
        L.vp.tags_touch()
    return act


def guides(on: bool):
    """Hide or show the legend and the specimen glyph (not channel-driven).
    They stand on the +Y and -Y axes, so every wide shot of the growing cloud
    would have one of them floating in front of it; the animation section
    hides them and the closing shots bring them back. Viewer-side only."""
    def act(L):
        for n in L.win.nodes:
            if n.id >= GUIDES:
                n.hide = 0 if on else 1
        L.vp.scene_touch()
        L.vp.tags_touch()
    return act


def bigger_labels(L):
    # Viewer-side Tag Text Size for video legibility; never saved.
    L.vp._scene.world_node().tag_font_size = 13
    L.vp.tags_touch()


def _mean_of(n):
    """Invert the scene's mean_color: slate -> red or slate -> green."""
    if n.color_g < 151 and n.color_r > 136:
        return -3.0 * (n.color_r - 136) / (232 - 136)
    return 3.0 * (n.color_g - 152) / (240 - 152)


def clock(L, u):
    if not hasattr(L, "_roots"):
        nodes = L.win.nodes
        L._roots = [n for n in nodes if n.type == 5 and n.branch_level == 0
                    and n.parent_id == 0 and n.topo == 2 and n.id != KEY]
        L._ratings = [n for n in nodes if n.type == 7 and n.geometry in (5, 27)]
    f = int(L.win._ch_frame)
    day = T0 + dt.timedelta(days=f * DAYS_PER_FRAME)
    shown = [n for n in L._roots if not n.hide]
    red = sum(1 for n in shown if _mean_of(n) < -0.5)
    drawn = sum(1 for n in L._ratings if not n.hide)
    return (f"{day:%b %Y}   frame {f:>3}\n"
            f"traders     {len(shown):>6,}\n"
            f"ratings     {drawn:>6,}\n"
            f"distrusted  {red:>6,}")


def build() -> Lesson:
    ov = dict(target=(0, 0, 0), dist=560, el=22)
    shots = [
        Shot(title="Trust and Betrayal", heading="An Examples Gallery scene",
             say="Bitcoin O T C was a chat room marketplace where people sent real "
                 "money to strangers. Afterwards, they rated each other, from minus "
                 "ten to plus ten. Thirty five thousand of those ratings survive, "
                 "from 2010 to 2016.",
             keys=[Key(0, az=20, el=26, dist=640, target=(0, -20, 0)),
                   Key(1, az=34, el=ov["el"], dist=ov["dist"])],
             ch_rate=0, ch_frame=LAST, select=set(),
             events=[(0.0, bigger_labels), (0.0, pins(False, False))],
             state=dict(show_tags=True, show_tags_selected_only=True)),
        Shot(heading="One in ten is negative",
             say="One rating in ten is negative. In a marketplace, that isn't a bad "
                 "review. It's an accusation of theft.",
             keys=[Key(0, az=34, el=ov["el"], dist=ov["dist"], target=(0, -20, 0)),
                   Key(1, az=50, el=20, dist=500, target=(0, 0, 0))]),
        Shot(heading="Every trader is a glyph",
             say="In most graph tools, a person is a dot. Here, each of nine hundred "
                 "and twenty two traders is a glyph, built from their own reputation. "
                 "The scene includes a large one, labelled, to learn from.",
             keys=[Key(0, az=50, el=20, dist=500, target=(0, 0, 0)),
                   Key(0.55, az=25, el=16, dist=190, target=KEY_POS),
                   Key(1, az=20, el=14, dist=165)],
             events=[(0.45, rating_links(False)), (0.5, pins(False, True))]),
        Shot(heading="The trader",
             say="At the centre is the trader. Its shape is their reputation class. "
                 "Its colour is the average rating they've received, and its size is "
                 "how many ratings they carry.",
             keys=[Key(0, az=20, el=14, dist=165, target=KEY_POS),
                   Key(1, az=8, el=12, dist=150)],
             callouts=[Callout(KEY, "the trader", 0.15, 0.97, offset=(-190, 30),
                               color=CHALK)]),
        Shot(heading="North: received. South: given.",
             say="The hub at the north pole holds the ratings they received. The hub "
                 "at the south pole holds the ratings they gave.",
             keys=[Key(0, az=8, el=12, dist=150, target=KEY_POS),
                   Key(1, az=-4, el=10, dist=145)],
             callouts=[Callout(KEY_NORTH, "received", 0.1, 0.97, offset=(-170, -40),
                               color=TEAL),
                       Callout(KEY_SOUTH, "given", 0.35, 0.97, offset=(-170, 40),
                               color=AMBER)]),
        Shot(heading="Five bands of trust",
             say="Around each hub are up to five spokes, one for each band of the "
                 "scale: red for strong distrust, orange for distrust, slate for "
                 "routine, and two greens for trust. A spoke's size is how many "
                 "ratings fell in that band. An empty band has no spoke at all.",
             keys=[Key(0, az=-4, el=10, dist=145, target=KEY_POS),
                   Key(0.3, az=10, el=26, dist=72, target=(0, -304, 94)),
                   Key(1, az=40, el=30, dist=70)],
             callouts=[Callout(KEY_RED, "strong distrust", 0.3, 0.97,
                               offset=(-150, -60), color=RED),
                       Callout(KEY_ROUTINE, "routine", 0.45, 0.97,
                               offset=(140, -80), color=(150, 166, 196)),
                       Callout(KEY_GREEN, "strong trust", 0.6, 0.97,
                               offset=(150, 50), color=GREEN)]),
        Shot(heading="The colour key",
             say="The legend spells it out. Five reputation classes, each with its "
                 "own shape and colour, from red tetrahedra for the distrusted to "
                 "bright green dodecahedra for the most trusted.",
             keys=[Key(0, az=40, el=30, dist=70, target=(0, -304, 94)),
                   Key(0.55, az=0, el=6, dist=265, target=(0, 224, 96)),
                   Key(1, az=-4, el=6, dist=250)]),
        Shot(heading="Every glyph shares one frame",
             say="Every glyph is aligned the same way, so north always means "
                 "received. That makes them comparable at a glance. User one has two "
                 "big green spokes to the north, and no red at all: vouched for, "
                 "over and over.",
             keys=[Key(0, az=-4, el=6, dist=250, target=(0, 224, 96)),
                   Key(0.5, az=60, el=8, dist=26, target=TRUSTED_1),
                   Key(1, az=72, el=8, dist=24)],
             events=[(0.3, pins(False, False)), (0.5, {"select": {TRUSTED_1}})]),
        Shot(heading="A red spoke to the north",
             say="A red spoke to the north means accused. This account's is "
                 "huge: sixty eight ratings of minus five or worse. Click any part "
                 "of a glyph, and its label says what it encodes.",
             keys=[Key(0, az=72, el=8, dist=24, target=TRUSTED_1),
                   Key(0.45, az=200, el=8, dist=30, target=ACCUSED_3744),
                   Key(1, az=212, el=10, dist=28)],
             select=set(), events=[(0.55, {"select": {ACCUSED_SPOKE}})]),
        Shot(heading="Ratings are links",
             say="The ratings themselves are links. A plus one, the commonest "
                 "rating, only means the trade went through, so it's a faint line. "
                 "Strong praise is bright green, and a negative rating is red.",
             keys=[Key(0, az=212, el=10, dist=28, target=ACCUSED_3744),
                   Key(1, az=30, el=20, dist=380, target=(0, 20, 0))],
             select=set(), events=[(0.15, rating_links(True))]),
        Shot(heading="Cones point at the accused",
             say="When a rating is aimed at one of the twenty most accused accounts, "
                 "it becomes a cone, with its point on the accused. Sixty nine of "
                 "them converge on this one.",
             keys=[Key(0, az=30, el=20, dist=380, target=(0, 20, 0)),
                   Key(0.6, az=34, el=18, dist=150, target=STARBURST),
                   Key(1, az=40, el=18, dist=140)],
             callouts=[Callout(ACCUSED_3744, "user 3744", 0.6, 0.97,
                               offset=(120, -90), ring=False, color=CORAL)]),
        # ---- the animation: the marketplace itself growing
        Shot(heading="It isn't a layout settling",
             say="Now the part that's easy to miss. Press play, and this isn't a "
                 "graph spreading out. It's the marketplace itself growing, from "
                 "November 2010 to January 2016. It starts with thirteen traders.",
             keys=[Key(0, az=40, el=18, dist=140, target=STARBURST),
                   Key(0.3, az=40, el=24, dist=100, target=(-5, 16, 6)),
                   Key(1, az=48, el=24, dist=92)],
             ch_frame=0, ch_rate=0, readout=clock, events=[(0.2, guides(False))]),
        Shot(heading="Everything arrives when it happened",
             say="Each trader appears with their first rating. A spoke sprouts the "
                 "first time they earn a rating in that band, and each link appears "
                 "when it was given.",
             keys=[Key(0, az=48, el=24, dist=92, target=(-5, 16, 6)),
                   Key(1, az=66, el=24, dist=230, target=(0, 10, 12))],
             ch_span=(0, 28), readout=clock),
        Shot(heading="The layout chases the data",
             say="The data has no coordinates, only who rated whom. So the layout is "
                 "solved again at every frame, on just the network that existed "
                 "then. Newcomers emerge beside the people who first rated them.",
             keys=[Key(0, az=66, el=24, dist=230, target=(0, 10, 12)),
                   Key(1, az=88, el=22, dist=330, target=(0, 8, 6))],
             ch_span=(28, 50), readout=clock),
        Shot(heading="Spring 2013",
             say="Watch user thirty seven forty four. It appears in March 2013, and "
                 "within weeks, dozens of accusations converge on it, each cone "
                 "arriving as it was made.",
             keys=[Key(0, az=88, el=22, dist=330, target=(0, 8, 6)),
                   Key(0.3, az=34, el=22, dist=210, target=ACCUSED_3744),
                   Key(1, az=40, el=22, dist=190)],
             ch_span=((0.0, 50), (0.25, 53), (1.0, 62)), readout=clock,
             callouts=[Callout(ACCUSED_3744, "user 3744", 0.35, 0.97,
                               offset=(-150, -90), ring=False, color=CORAL)]),
        Shot(heading="Trust sours",
             say="A glyph's shape is its final verdict, but its colour is the "
                 "running average. So you can watch reputations sour: accounts swell "
                 "as ratings arrive, and drift from slate toward red.",
             keys=[Key(0, az=40, el=22, dist=190, target=ACCUSED_3744),
                   Key(1, az=120, el=22, dist=470, target=(0, 0, 0))],
             ch_span=(62, 86), readout=clock),
        Shot(heading="The red gathers",
             say="And the red doesn't scatter. Most distrusted accounts arrived late, "
                 "from 2013 on, and they gather on the side of the cloud that grew "
                 "last. A distrusted trader's nearest neighbours are three times as "
                 "likely to be distrusted too.",
             keys=[Key(0, az=120, el=22, dist=470, target=(0, 0, 0)),
                   Key(1, az=12, el=14, dist=330, target=(0, 45, 10))],
             ch_span=(86, LAST), readout=clock),
        Shot(heading="January 2016",
             say="By January 2016: nine hundred and twenty two traders, more than "
                 "seventeen thousand ratings drawn, and a hundred and nineteen "
                 "traders distrusted.",
             keys=[Key(0, az=12, el=14, dist=330, target=(0, 45, 10)),
                   Key(1, az=-6, el=18, dist=380, target=(0, 30, 10))],
             ch_span=(LAST, LAST), readout=clock),
        Shot(heading="Try it",
             say="Open it from the Examples Gallery, click any part of a glyph to "
                 "read it, and press Space to watch five years of trust and "
                 "betrayal unfold.",
             keys=[Key(0, az=-6, el=18, dist=380, target=(0, 30, 10)),
                   Key(1, az=30, el=22, dist=560, target=(0, 0, 0))],
             events=[(0.3, guides(True))]),
        Shot(heading="Recap",
             say="That's Trust and Betrayal.",
             keys=[Key(0, az=30, el=22, dist=560, target=(0, 0, 0)),
                   Key(1, az=40, el=22, dist=560)],
             min_dur=7,
             summary=["Each trader is a 3-level glyph of their reputation",
                      "North hub: received.  South hub: given",
                      "Shape = verdict.  Colour = running average",
                      "Playback is the marketplace growing, 2010-2016",
                      "Examples Gallery: Trust and Betrayal"]),
    ]
    return Lesson(name="trust_network", title="Trust and Betrayal", nodes=[],
                  shots=shots, use_window=True, scene_csv=str(SCENE),
                  voice="af_heart")
