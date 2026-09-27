"""Channels 1 of 3: how nodes come alive (the Sine Wave example).

Filmed on a LESSON COPY of examples/SineWave_Example, written into the
lesson's out/ folder at render time (the shipped example is never touched).
The copy adds what the demo needs and the example lacks:

  * still nodes to bring to life: one octahedron (STILL) and a hub with a
    flat ring of 12 spheres (HUB, RING), all with Channel In = 0;
  * channels that do something other than bob, so the video can show that a
    channel carries its behaviour with it:
        33  pulse   scale_x/y/z   <- track 33
        34  colour  color_r/g/b   <- tracks 34, 35, 36
        41..52 ripple  translate_z <- tracks 41..52, one frequency, each a
               1/12 lap later, so ring child k on channel 40+k makes a wave.

Every Channel In change goes through the Properties panel's own spin box
(MainWindow._insp_ch_in), so the rebinding is the app's, not the lesson's.
The readout prints that spin box and the hint label beside it verbatim.
"""
import colorsys
import math
import shutil
from pathlib import Path

import pandas as pd

from lessonkit import Callout, Key, Lesson, Shot, AMBER, CHALK, CORAL, TEAL, VIOLET, BG

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "examples" / "SineWave_Example"
STEM = "SineWave_Example"

SPHERE_ROOT, TORUS_ROOT = 1, 34
CH1_CHILD, CH32_CHILD = 2, 33         # Sphere root's first and last children
STILL = 301
HUB = 310
RING = list(range(311, 323))          # 12 children
STILL_POS = (-150.0, -38.0, 0.0)
HUB_POS = (-95.0, -45.0, 0.0)
RING_R = 9.0

N_FRAMES = 512
CH_PULSE, CH_COLOUR, CH_RIPPLE0 = 33, 34, 40


def _prepare(lesson, scene_dir: Path):
    """Write the lesson copy: node + tag + the extended ch-map/ch-tracks."""
    d = scene_dir / "sine_wave_lesson"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)

    nodes = pd.read_csv(SRC / f"{STEM}_gv_node.csv")
    base = {c: 0 for c in nodes.columns}
    base.update(type=5, scale_x=1, scale_y=1, scale_z=1, color_a=255, ratio=0.1)

    def row(**kw):
        r = dict(base)
        r.update(kw)
        return r

    extra = [row(id=STILL, parent_id=0, branch_level=0,
                 translate_x=STILL_POS[0], translate_y=STILL_POS[1],
                 scale_x=3, scale_y=3, scale_z=3,
                 color_r=236, color_g=240, color_b=255, geometry=11),
             row(id=HUB, parent_id=0, branch_level=0,
                 translate_x=HUB_POS[0], translate_y=HUB_POS[1],
                 scale_x=1.5, scale_y=1.5, scale_z=1.5,
                 color_r=VIOLET[0], color_g=VIOLET[1], color_b=VIOLET[2],
                 geometry=3)]
    for k, nid in enumerate(RING):
        a = 2 * math.pi * k / len(RING)
        extra.append(row(id=nid, parent_id=HUB, branch_level=1,
                         translate_x=round(RING_R * math.cos(a) / 1.5, 4),
                         translate_y=round(RING_R * math.sin(a) / 1.5, 4),
                         scale_x=0.6, scale_y=0.6, scale_z=0.6,
                         color_r=TEAL[0], color_g=TEAL[1], color_b=TEAL[2],
                         geometry=3))
    pd.concat([nodes, pd.DataFrame(extra)], ignore_index=True).to_csv(
        d / "sine_wave_lesson_gv_node.csv", index=False)

    tags = pd.read_csv(SRC / f"{STEM}_gv_tag.csv")
    more = [dict(id=STILL, table_id=0, record_id=STILL, title="a still node"),
            dict(id=HUB, table_id=0, record_id=HUB, title="a still ring")]
    more += [dict(id=n, table_id=0, record_id=n, title=f"{k + 1}")
             for k, n in enumerate(RING)]
    pd.concat([tags, pd.DataFrame(more)], ignore_index=True).to_csv(
        d / "sine_wave_lesson_gv_tag.csv", index=False)

    cmap = pd.read_csv(SRC / f"{STEM}_gv_ch-map.csv")
    rows = [(CH_PULSE, 33, a) for a in ("scale_x", "scale_y", "scale_z")]
    rows += [(CH_COLOUR, 34, "color_r"), (CH_COLOUR, 35, "color_g"),
             (CH_COLOUR, 36, "color_b")]
    rows += [(CH_RIPPLE0 + k, CH_RIPPLE0 + k, "translate_z") for k in range(1, 13)]
    nid = int(cmap["id"].max()) + 1
    add = [dict(id=nid + i, channel_id=c, track_id=t, attribute=a,
                track_table_id=0, ch_map_table_id=0, record_id=0)
           for i, (c, t, a) in enumerate(rows)]
    pd.concat([cmap, pd.DataFrame(add)], ignore_index=True).to_csv(
        d / "sine_wave_lesson_gv_ch-map.csv", index=False)

    tr = pd.read_csv(SRC / f"{STEM}_gv_ch-tracks.csv")
    f = tr["cyclecount"].to_numpy()
    tr["ch33"] = (3.0 * (1 + 0.35 * pd.Series(f).map(
        lambda i: math.sin(2 * math.pi * 8 * i / N_FRAMES)))).round(4)
    rgb = [colorsys.hsv_to_rgb((2 * i / N_FRAMES) % 1.0, 0.75, 1.0) for i in f]
    for j, col in enumerate(("ch34", "ch35", "ch36")):
        tr[col] = [round(c[j] * 255) for c in rgb]
    for k in range(1, 13):
        ph = 2 * math.pi * (k - 1) / 12
        tr[f"ch{CH_RIPPLE0 + k}"] = [
            round(2.5 * math.sin(2 * math.pi * 4 * i / N_FRAMES - ph), 4) for i in f]
    tr.to_csv(d / "sine_wave_lesson_gv_ch-tracks.csv", index=False)

    lesson.scene_csv = str(d / "sine_wave_lesson_gv_node.csv")


# --- the "user's" actions, through the app's own widgets ----------------------

def select(*ids):
    return lambda L: L.win._table.select_by_ids(set(ids))


def channel_in(value):
    """Properties > Channel In, applied to the current selection."""
    return lambda L: L.win._insp_ch_in.setValue(value)


def panel(L, u):
    """The Channel In row exactly as the Properties panel shows it."""
    w = L.win
    sel = w._selected_nodes
    if not sel:
        return None
    who = f"node {sel[0].id}" if len(sel) == 1 else f"{len(sel)} nodes"
    v = w._insp_ch_in.value()
    hint = w._insp_ch_in_hint.text()
    if len(hint) > 38:
        hint = hint[:36] + "…"
    return (f"selected    {who}\n"
            f"Channel In  {v if v else 'none'}\n"
            f"{hint}")


def steps(*pairs):
    def f(u):
        cur = pairs[0]
        for p in pairs:
            if u >= p[0]:
                cur = p
        return cur[1], cur[2]
    return f


def _files_card():
    """Two tables, read from the shipped example's own files."""
    tr = pd.read_csv(SRC / f"{STEM}_gv_ch-tracks.csv", nrows=6)
    cm = pd.read_csv(SRC / f"{STEM}_gv_ch-map.csv", nrows=4)
    t_lines = [f"{'frame':>5}  {'ch1':>6}  {'ch2':>6}  …  {'ch32':>6}"]
    for _, r in tr.iterrows():
        t_lines.append(f"{int(r.cyclecount):>5}  {r.ch1:>6.2f}  {r.ch2:>6.2f}  …  {r.ch32:>6.2f}")
    t_lines.append(f"{'…':>5}")
    m_lines = [f"{'channel':>7}  {'track':>5}  attribute"]
    for _, r in cm.iterrows():
        m_lines.append(f"{int(r.channel_id):>7}  {int(r.track_id):>5}  {r.attribute}")
    m_lines.append(f"{'…':>7}")

    def draw(ov, d, u):
        a = min(1.0, u / 0.08, (1 - u) / 0.08)
        if a <= 0:
            return
        s = ov.s
        d.rectangle((0, 0, ov.w, ov.h), fill=(*BG, int(200 * a)))
        panels = [("ch-tracks.csv", "the numbers: a column per channel, a row per frame",
                   t_lines, TEAL, 0.04),
                  ("ch-map.csv", "what each channel drives",
                   m_lines, AMBER, 0.30)]
        x = ov.w * 0.07
        for title, sub, lines, col, t0 in panels:
            pa = a * min(1.0, max(0.0, (u - t0) / 0.1))
            if pa <= 0:
                x += ov.w * 0.46
                continue
            y = ov.h * 0.17
            d.text((x, y), title, font=ov.f_head, fill=(*col, int(255 * pa)))
            d.text((x, y + 30 * s), sub, font=ov.f_note, fill=(180, 186, 210, int(230 * pa)))
            y += 74 * s
            w = max(d.textlength(l, font=ov.f_mono) for l in lines) + 30 * s
            ov._box(d, (x - 12 * s, y - 10 * s, x - 12 * s + w, y + 30 * s * len(lines) + 6 * s),
                    fill=(8, 8, 16, int(220 * pa)), outline=(*col, int(255 * pa)))
            for i, l in enumerate(lines):
                d.text((x, y + i * 30 * s), l, font=ov.f_mono,
                       fill=(*CHALK, int(245 * pa)))
            x += ov.w * 0.46
        # The third piece: the node's own column.
        pa = a * min(1.0, max(0.0, (u - 0.58) / 0.1))
        if pa > 0:
            y = ov.h * 0.64
            x = ov.w * 0.07
            d.text((x, y), "…and one column in the node file:  ch_input_id",
                   font=ov.f_head, fill=(*CORAL, int(255 * pa)))
            d.text((x, y + 32 * s),
                   "the node's channel. In the app it's the Properties panel's Channel In field.",
                   font=ov.f_note, fill=(180, 186, 210, int(230 * pa)))
    return draw


def build() -> Lesson:
    def bigger_labels(L):
        w = L.vp._scene.world_node() if hasattr(L.vp._scene, "world_node") else None
        if w is not None:
            w.tag_font_size = 14
        L.vp.tags_touch()

    wide = dict(target=(0, 0, 0))
    shots = [
        Shot(title="Channels", heading="How nodes come alive",
             say="Channels bring a GlyphViz scene to life. A table of numbers, "
                 "one row per frame, drives a node's position, size, or colour.",
             keys=[Key(0, az=250, el=24, dist=330, **wide), Key(1, az=262, el=22, dist=300)],
             ch_rate=30, ch_frame=0, select=set(),
             events=[(0.0, bigger_labels)],
             state=dict(show_tags=True, show_tags_selected_only=False)),
        Shot(heading="The Sine Wave example",
             say="This is the Sine Wave example. Open it and press Space, and "
                 "seven rings of spheres ripple, one for each topology.",
             keys=[Key(0, az=262, el=22, dist=300, **wide),
                   Key(1, az=275, el=18, dist=140, target=(-110, 0, 0))],
             keycap="Space", keycap_note="play and pause"),
        Shot(heading="One channel per child",
             say="Each child follows its own channel. Channel one rises and "
                 "falls once per loop. Channel thirty two does it thirty two times.",
             keys=[Key(0, az=275, el=18, dist=140, target=(-110, 0, 0)),
                   Key(0.3, az=250, el=16, dist=28, target=SPHERE_ROOT),
                   Key(1, az=240, el=18, dist=26)],
             callouts=[Callout(CH1_CHILD, "channel 1", 0.3, 0.97, offset=(110, -80), color=TEAL),
                       Callout(CH32_CHILD, "channel 32", 0.4, 0.97, offset=(-110, -80), color=CORAL)]),
        Shot(heading="Two files do the work",
             say="Two files do the work. The tracks file holds the numbers: a "
                 "column per channel, a row per frame. The map file says what "
                 "each channel drives. Here, every channel drives translate Z: "
                 "height. And each node names its channel in one column.",
             keys=[Key(0, az=240, el=18, dist=26, target=SPHERE_ROOT),
                   Key(1, az=225, el=20, dist=30)],
             card=_files_card()),
        Shot(heading="Channel In",
             say="In the app, that column is Channel In, in the Properties "
                 "panel. Here's a node with no channel. It sits still.",
             keys=[Key(0, az=225, el=20, dist=30, target=SPHERE_ROOT),
                   Key(0.4, az=255, el=18, dist=26, target=STILL),
                   Key(1, az=262, el=18, dist=24)],
             events=[(0.35, select(STILL))],
             keycap=steps((0.0, "Click", "select it"),
                          (0.35, "Properties", "Channel In")),
             readout=panel),
        Shot(heading="Bring it to life",
             say="Set Channel In to thirty three, a channel that drives size, "
                 "and the node starts to pulse.",
             keys=[Key(0, az=262, el=18, dist=24, target=STILL),
                   Key(1, az=272, el=16, dist=22)],
             events=[(0.3, channel_in(CH_PULSE))],
             keycap="Channel In", keycap_note="33",
             readout=panel),
        Shot(heading="The channel carries the behaviour",
             say="Change it to thirty four, and the same node cycles through "
                 "colour instead. The channel decides what moves.",
             keys=[Key(0, az=272, el=16, dist=22, target=STILL),
                   Key(1, az=284, el=18, dist=22)],
             events=[(0.25, channel_in(CH_COLOUR))],
             keycap="Channel In", keycap_note="34",
             readout=panel),
        Shot(heading="Bind a parent, and the family follows",
             say="Channels work through the hierarchy. The Sphere's hub has no "
                 "channel. Give it channel three, and the whole ring rises and "
                 "falls, each child still riding its own wave.",
             keys=[Key(0, az=284, el=18, dist=22, target=STILL),
                   Key(0.3, az=250, el=12, dist=34, target=(-150, 0, 0)),
                   Key(1, az=235, el=10, dist=36)],
             events=[(0.2, select(SPHERE_ROOT)), (0.45, channel_in(3))],
             keycap=steps((0.0, "Click", "select the Sphere's hub"),
                          (0.45, "Channel In", "3")),
             readout=panel),
        Shot(heading="A group at once",
             say="Select several nodes and set one value, and they move as one. "
                 "Here, twelve children join the colour channel together.",
             keys=[Key(0, az=235, el=10, dist=36, target=(-150, 0, 0)),
                   Key(0.3, az=262, el=36, dist=34, target=HUB),
                   Key(1, az=275, el=34, dist=32)],
             events=[(0.3, select(*RING)), (0.5, channel_in(CH_COLOUR))],
             keycap=steps((0.0, "Ctrl + Click", "select the ring"),
                          (0.5, "Channel In", "34")),
             readout=panel),
        Shot(heading="A wave",
             say="Now give each child its own channel, each one a step later in "
                 "time, and a wave runs around the ring.",
             keys=[Key(0, az=275, el=34, dist=32, target=HUB),
                   Key(0.3, az=285, el=16, dist=30),
                   Key(1, az=300, el=14, dist=30)],
             events=[ev for k, n in enumerate(RING)
                     for ev in ((0.12 + 0.05 * k, select(n)),
                                (0.12 + 0.05 * k + 0.02, channel_in(CH_RIPPLE0 + k + 1)))],
             keycap=steps((0.0, "Channel In", "41, 42, 43 … 52, one per child")),
             readout=panel, min_dur=9),
        Shot(heading="Watch it run",
             say="One field, one number per node. Any data you can put in a "
                 "column can drive a scene.",
             keys=[Key(0, az=300, el=20, dist=30, target=HUB),
                   Key(1, az=250, el=24, dist=150, target=(-90, -10, 0))],
             select=set(), min_dur=6),
        Shot(heading="Recap",
             say="That's Channels.",
             keys=[Key(0, az=250, el=24, dist=150, target=(-90, -10, 0)),
                   Key(1, az=240, el=24, dist=170)], min_dur=7,
             summary=["ch-tracks: the numbers, a row per frame",
                      "ch-map: what each channel drives",
                      "Channel In: which channel a node follows",
                      "Bind a parent, and its children follow"]),
    ]
    return Lesson(name="channels_sine", title="Channels", nodes=[], shots=shots,
                  use_window=True, prepare=_prepare, voice="af_heart")
