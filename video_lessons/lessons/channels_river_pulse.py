"""Channels 3 of 3: at scale (San Diego River Watershed Atlas: The Pulse).

Filmed on the shipped scene through File > Open's own path. Screenplay and
every number spoken come from the gallery page glyphviz-docs/docs/examples/
sd-river-pulse.md (checked 2026-09-26): 1,372 monthly frames from May 1912,
772 animated tracks, 70,809 nodes; Feb 1927 record month (1,871 cfs at Mast
Rd); Jan 1916 Cuyamaca's wettest month (36.5 in) with no flow record; dams
1934 / 1943; no dry month since September 1968.

Frame f is the month f after May 1912: Jan 1916 = 44, Feb 1927 = 177.

Landmarks (node ids, by label): Mast Rd flow ribbon 69670; Cuyamaca rain
column 69906; the panel's dam labels 70151 / 70155; the "now" cursor 70160;
the panel titles 69911 / 70163. Camera angles build on tools/
capture_example_shots.py's "sd-river-pulse" entry.
"""
from pathlib import Path

from glyphviz_core.channel_engine import channel_id_of
from lessonkit import Callout, Key, Lesson, Shot, AMBER, CORAL, TEAL, CHALK

REPO = Path(__file__).resolve().parents[2]
SCENE = REPO / "examples" / "San_Diego_River_Pulse_Example" / "sd_river_pulse_gv_node.csv"

RIBBON_MAST = 69670
RAIN_CUYAMACA = 69906
DAM_EL_CAP, DAM_SAN_VIC = 70151, 70155
CURSOR = 70160
CENTURY_TITLE, DECADE_TITLE = 69911, 70163
YEAR_LABEL = 70745        # one of the bank of 115 year labels (1993)

JAN_1916, FEB_1927, LAST = 44, 177, 1371
OVERVIEW = dict(target=(40, 0, 50), dist=500, az=240, el=35)
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def pins(on: bool):
    """Show or hide the scene's STATIC pinned labels (legend, panel axes,
    places). At video size they stack into an unreadable pile from any
    map-wide angle, so the map shots hide them and the panel shots bring them
    back. A viewer-side choice for the video; the channel-driven date labels
    are never touched, and nothing is saved."""
    def act(L):
        if not hasattr(L, "_pinned"):
            L._pinned = [n for n in L.win.nodes
                         if n.show_text and not channel_id_of(n)]
        for n in L._pinned:
            n.show_text = 1 if on else 0
        L.vp.tags_touch()
    return act


def month_of(f: int) -> str:
    m = 4 + f
    return f"{MONTHS[m % 12]} {1912 + m // 12}"


def clock(L, u):
    f = int(L.win._ch_frame)
    return f"{month_of(f):<14}\nframe {f:>4} / {LAST}"


def build() -> Lesson:
    ov = OVERVIEW
    shots = [
        Shot(title="Channels: The Pulse", heading="A century of the San Diego River",
             say="Channels scale up. This scene plays the San Diego River month by "
                 "month since May nineteen twelve: thirteen hundred and seventy two "
                 "frames, with seven hundred and seventy two tracks animating at once.",
             keys=[Key(0, az=ov["az"] - 10, el=ov["el"] + 6, dist=ov["dist"] + 60,
                       target=ov["target"]),
                   Key(1, az=ov["az"], el=ov["el"], dist=ov["dist"])],
             ch_rate=0, ch_frame=0, select=set(), events=[(0.0, pins(False))],
             state=dict(show_tags=True, show_tags_selected_only=True)),
        Shot(heading="Rain over the mountains",
             say="Rain columns rise over four rain stations in the mountains. Height "
                 "is the month's rainfall. Colour compares it with the same month in "
                 "other years: ochre for drier, blue for wetter.",
             keys=[Key(0, az=ov["az"], el=ov["el"], dist=ov["dist"], target=ov["target"]),
                   Key(0.5, az=225, el=22, dist=290, target=RAIN_CUYAMACA),
                   Key(1, az=232, el=22, dist=280)],
             ch_span=(0, 30), readout=clock),
        Shot(heading="January 1916",
             say="January nineteen sixteen is Cuyamaca's wettest month on record: "
                 "thirty six and a half inches. And the river gauge recorded "
                 "nothing that winter, so its ribbon is hidden, not guessed.",
             keys=[Key(0, az=232, el=22, dist=280, target=RAIN_CUYAMACA),
                   Key(1, az=240, el=20, dist=270)],
             ch_span=((0.0, 30), (0.3, JAN_1916), (1.0, JAN_1916)), readout=clock,
             callouts=[Callout(RAIN_CUYAMACA, "Cuyamaca", 0.35, 0.97,
                               offset=(-110, -90), ring=False, color=TEAL)]),
        Shot(heading="The river's pulse",
             say="Down on the river, each stream gauge drives a ribbon over the reach "
                 "it measures. Width is the month's flow. Watch it swell each winter.",
             keys=[Key(0, az=240, el=20, dist=270, target=RAIN_CUYAMACA),
                   Key(0.45, az=210, el=38, dist=190, target=(-100, -70, 5)),
                   Key(1, az=200, el=40, dist=180)],
             ch_span=(JAN_1916, 160), readout=clock,
             callouts=[Callout(RIBBON_MAST, "Mast Rd flow", 0.5, 0.97,
                               offset=(90, -90), ring=False, color=TEAL)]),
        Shot(heading="February 1927",
             say="February nineteen twenty seven is still the record month: eighteen "
                 "hundred and seventy one cubic feet per second, averaged over the "
                 "whole month.",
             keys=[Key(0, az=200, el=40, dist=180, target=(-100, -70, 5)),
                   Key(1, az=192, el=36, dist=165)],
             ch_span=((0.0, 160), (0.3, FEB_1927), (1.0, FEB_1927)), readout=clock),
        Shot(heading="The long view",
             say="Beyond the watershed's east edge, a panel keeps the long view: every "
                 "water year since nineteen thirteen below, and the last ten years, "
                 "month by month, above. A cursor sweeps as the clock runs.",
             keys=[Key(0, az=192, el=36, dist=165, target=(-100, -70, 5)),
                   Key(0.5, az=182, el=6, dist=430, target=(225, 0, 205)),
                   Key(1, az=184, el=6, dist=410)],
             ch_span=(FEB_1927, 380), readout=clock, events=[(0.4, pins(True))],
             callouts=[Callout(CURSOR, "now", 0.55, 0.97, offset=(80, -60),
                               ring=False, color=AMBER)]),
        Shot(heading="The dams change the river",
             say="Watch the yearly flow line after the dams: El Capitan in nineteen "
                 "thirty four, San Vicente in nineteen forty three. The river's wild "
                 "swings flatten out.",
             keys=[Key(0, az=184, el=6, dist=410, target=(225, 0, 205)),
                   Key(1, az=186, el=4, dist=260, target=(225, 40, 140))],
             ch_span=(380, 700), readout=clock,
             callouts=[Callout(DAM_EL_CAP, "El Capitan Dam", 0.2, 0.97,
                               offset=(-40, -110), ring=False, color=CORAL),
                       Callout(DAM_SAN_VIC, "San Vicente Dam", 0.3, 0.97,
                               offset=(60, 90), ring=False, color=CORAL)]),
        Shot(heading="The whole century",
             say="At full speed, the rest of the century pulses by. The river hasn't "
                 "run dry since September nineteen sixty eight.",
             keys=[Key(0, az=186, el=4, dist=260, target=(225, 40, 140)),
                   Key(0.4, az=ov["az"], el=ov["el"] + 4, dist=ov["dist"] - 40,
                       target=ov["target"]),
                   Key(1, az=ov["az"] + 12, el=ov["el"] + 6, dist=ov["dist"] - 60)],
             ch_span=(700, 1300), readout=clock, events=[(0.3, pins(False))]),
        Shot(heading="Even the date is a channel",
             say="Channels can't change a label's text, only whether it shows. So the "
                 "running date is a bank of year and month labels, and each frame "
                 "shows one of each.",
             keys=[Key(0, az=ov["az"] + 12, el=ov["el"] + 6, dist=ov["dist"] - 60,
                       target=ov["target"]),
                   Key(0.5, az=188, el=6, dist=150, target=(225, -115, 305)),
                   Key(1, az=190, el=6, dist=140)],
             ch_span=(1300, LAST), readout=clock, events=[(0.4, pins(True))]),
        Shot(heading="Recap",
             say="That's the Pulse.",
             keys=[Key(0, az=190, el=6, dist=140, target=(225, -115, 305)),
                   Key(1, az=ov["az"], el=ov["el"], dist=ov["dist"], target=ov["target"])],
             ch_span=(LAST, LAST), min_dur=7, events=[(0.0, pins(False))],
             summary=["1,372 monthly frames, 772 tracks, 70,809 nodes",
                      "Width, height, colour, visibility: all channels",
                      "Missing data drawn as missing",
                      "Examples Gallery: San Diego River Watershed Atlas"]),
    ]
    return Lesson(name="channels_river_pulse", title="Channels: The Pulse",
                  nodes=[], shots=shots, use_window=True, scene_csv=str(SCENE),
                  voice="af_heart")
