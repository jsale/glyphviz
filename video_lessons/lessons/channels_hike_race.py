"""Channels 2 of 3: real recorded data (the Multi-Hike Ghost Race example).

Filmed on the shipped scene, opened through File > Open's own path so its
channel files load exactly as a user's would. The race clock is driven with
Shot.ch_span, chained so playback never skips a frame.

Facts, measured from the shipped ch-tracks (2026-09-26):
  1800 frames span 0..138 elapsed minutes (~4.6 s of real time per frame).
  Climber channels 1/11/21 (fast) summit at frames 540-584 and stop at
  1037-1063 (79-81 min, back at the trailhead: out and back).
  Climber channels 31/41/51 (slow) summit at 797-921 and stop at 1782-1799.
  Summit ~(-51, -119, 116); trailhead ~(78, 72, 22).
Tag file: fast #1 2020-10-07 79 min avgHR 124 ... slow #6 2019-09-02 138 min.
Dashboards sit at x=220, y=0,40..200; each holds 3 plots along local X
(0, 105, 210; width 100, height 30) with a needle per plot.
"""
from pathlib import Path

from lessonkit import Callout, Key, Lesson, Shot, AMBER, CORAL, TEAL, CHALK

REPO = Path(__file__).resolve().parents[2]
SCENE = REPO / "examples" / "Multi_Hike_Race_Example" / "Multi_Hike_Race_Example_gv_node.csv"

FAST1, FAST2, FAST3 = 1445, 1695, 1945
SLOW4, SLOW5, SLOW6 = 2195, 2445, 2695
DASH1 = 1455
NEEDLE_ELEV, NEEDLE_HR, NEEDLE_PACE = 1675, 1676, 1677
SUMMIT = (-51.0, -119.0, 110.0)
TRAILHEAD = (78.0, 72.0, 22.0)
MOUNTAIN = (0.0, -20.0, 40.0)
OVERVIEW = (170.0, 30.0, 20.0)
DASHES = (375.0, 100.0, 15.0)
MINUTES = 138.0
LAST = 1799


def clock(L, u):
    f = int(L.win._ch_frame) if L.win is not None else 0
    return f"race clock  {f / LAST * MINUTES:5.1f} min\nframe       {f:>5} / {LAST}"


def build() -> Lesson:
    shots = [
        Shot(title="Channels: The Ghost Race", heading="Real recorded data",
             say="Channels can replay real recorded data. This example races six "
                 "of Jeff Sale's own hikes up Cowles Mountain in San Diego: his "
                 "three fastest and three slowest, all starting together.",
             keys=[Key(0, az=305, el=38, dist=700, target=OVERVIEW),
                   Key(1, az=292, el=36, dist=640)],
             ch_rate=0, ch_frame=0, select=set(),
             # Every climber and dashboard carries a long label; drawn all at
             # once they bury the scene, so the callouts do the naming.
             state=dict(show_tags=False)),
        Shot(heading="GPS drives position",
             say="Each pin is one hike. Its channel drives translate X, Y, and Z "
                 "straight from the GPS track, over the real terrain. Warm pins "
                 "are the fast hikes; cool pins, the slow ones.",
             keys=[Key(0, az=292, el=36, dist=640, target=OVERVIEW),
                   Key(0.5, az=255, el=38, dist=95, target=TRAILHEAD),
                   Key(1, az=262, el=38, dist=88)],
             callouts=[Callout(FAST1, "fast #1, 79 min", 0.5, 0.97,
                               offset=(110, -80), color=CORAL),
                       Callout(SLOW4, "slow #4, 137 min", 0.55, 0.97,
                               offset=(-120, 60), color=TEAL)]),
        Shot(heading="The race begins",
             say="Press play, and the race begins. Every frame is about four and "
                 "a half seconds of real time, so the whole race plays in about "
                 "a minute.",
             keys=[Key(0, az=262, el=38, dist=88, target=TRAILHEAD),
                   Key(1, az=245, el=42, dist=170, target=FAST1)],
             ch_span=(0, 300), keycap="Space", keycap_note="play",
             readout=clock),
        Shot(heading="The summit",
             say="The fast hikes reach the summit in about forty minutes, and "
                 "turn for home while the slow hikes are still climbing.",
             keys=[Key(0, az=245, el=42, dist=170, target=FAST1),
                   Key(1, az=232, el=36, dist=150, target=SUMMIT)],
             ch_span=(300, 620), readout=clock,
             callouts=[Callout(FAST1, "fast #1", 0.45, 0.97, offset=(90, -70),
                               color=CORAL),
                       Callout(SLOW4, "slow #4", 0.5, 0.97, offset=(-100, 60),
                               color=TEAL)]),
        Shot(heading="A dashboard for every hike",
             say="Off to the side, each hike has a dashboard: elevation, heart "
                 "rate, and pace, plotted over the whole hike. A needle on each "
                 "plot moves on the same clock as its climber.",
             keys=[Key(0, az=232, el=36, dist=150, target=SUMMIT),
                   Key(0.45, az=268, el=18, dist=175, target=(330, 0, 15)),
                   Key(1, az=274, el=18, dist=168)],
             ch_span=(620, 800), readout=clock,
             callouts=[Callout(NEEDLE_ELEV, "elevation", 0.5, 0.97, offset=(-60, -90)),
                       Callout(NEEDLE_HR, "heart rate", 0.58, 0.97, offset=(-40, -110)),
                       Callout(NEEDLE_PACE, "pace", 0.66, 0.97, offset=(60, -90))]),
        Shot(heading="Compare all six",
             say="Every dashboard shares the same axes, so one look across them "
                 "compares all six. The slow hikes' plots run longer, and their "
                 "heart rates run lower.",
             keys=[Key(0, az=274, el=18, dist=168, target=(330, 0, 15)),
                   Key(0.5, az=292, el=30, dist=330, target=DASHES),
                   Key(1, az=298, el=32, dist=320)],
             ch_span=(800, 990), readout=clock),
        Shot(heading="Home first",
             say="The fast hikers are back at the trailhead in about eighty "
                 "minutes. Their pins stop, and their needles reach the end of "
                 "their plots. The slow hikes are still coming down.",
             keys=[Key(0, az=298, el=32, dist=320, target=DASHES),
                   Key(0.5, az=258, el=44, dist=230, target=(30, -20, 60)),
                   Key(1, az=252, el=42, dist=180)],
             ch_span=(990, 1300), readout=clock,
             callouts=[Callout(FAST1, "fast #1: home", 0.55, 0.97, offset=(90, -70),
                               color=CORAL),
                       Callout(SLOW5, "slow #5", 0.6, 0.97, offset=(-100, 60),
                               color=TEAL)]),
        Shot(heading="The finish",
             say="The last slow hike comes home at a hundred and thirty eight "
                 "minutes. Six real walks, replayed side by side.",
             keys=[Key(0, az=252, el=42, dist=180, target=(30, -20, 60)),
                   Key(0.6, az=255, el=38, dist=110, target=TRAILHEAD),
                   Key(1, az=248, el=38, dist=115)],
             ch_span=(1300, LAST), readout=clock),
        Shot(heading="Your own tracks",
             say="Any recorded track works the same way: a run, a ride, a "
                 "delivery route. It's three columns in a tracks file, and one "
                 "channel number on the node.",
             keys=[Key(0, az=248, el=38, dist=115, target=TRAILHEAD),
                   Key(1, az=300, el=36, dist=680, target=OVERVIEW)],
             ch_span=(LAST, LAST)),
        Shot(heading="Recap",
             say="That's the Ghost Race.",
             keys=[Key(0, az=300, el=36, dist=680, target=OVERVIEW),
                   Key(1, az=308, el=36, dist=700)], min_dur=7,
             summary=["GPS columns drive translate X, Y and Z",
                      "One clock: pins and plot needles move together",
                      "Same axes on every dashboard: compare at a glance",
                      "Examples Gallery: Multi-Hike Ghost Race"]),
    ]
    return Lesson(name="channels_hike_race", title="Channels: The Ghost Race",
                  nodes=[], shots=shots, use_window=True, scene_csv=str(SCENE),
                  voice="af_heart")
