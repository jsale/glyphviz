#!/usr/bin/env python3
"""The Breathing Century — Century Reef + Channels playback, 1909 -> 2011.

Clock: cyclecount 1..103 == seasons 1909-10 .. 2011-12 (year = 1908 + step).

Choreography:
  * Every disc, pedestal, and Cup marker is dormant (color_a = 0) until its
    season arrives, then snaps to its final alpha and stays — the reef GROWS.
    Compression: all nodes born in year Y with final alpha A share channel
    (Y, A), so ~1,600 animated glyphs need only ~200 channels/tracks.
  * A translucent "tide" torus at the center breathes with league-wide
    goals per game: scale_x/y/z ride one track, color_r/g/b ride three more
    (cold blue = dead puck, hot orange = firewagon hockey).

Files (name-paired with the node CSV):
  century_reef_gv_node.csv       (regenerated: + ch_input_id column, + tide)
  century_reef_gv_ch-map.csv
  century_reef_gv_ch-tracks.csv

Format derived from working GaiaViz-lineage examples (RHR_Channel_Anim1,
Channels_Example). If this GlyphViz build expects the legacy column name,
rename ch_input_id -> np_ch_in_id in the node header.
"""
import csv, math
import pandas as pd

import os
UP = os.environ.get("HOCKEY_DATA", "./data")  # folder with the hockey history CSVs (Teams, Scoring, Master, SeriesPost, AwardsPlayers, HOF, TeamVsTeam)
OD = "."   # scene files are written beside the script
Y0, Y1 = 1909, 2011
NSTEP = Y1 - Y0 + 1                      # 103

t = pd.read_csv(f"{UP}/Teams.csv")
sp = pd.read_csv(f"{UP}/SeriesPost.csv")
t["ppct"] = t.Pts / (2 * t.G)
t["dpg"] = (t.GF - t.GA) / t.G

scf = sp[sp["round"] == "SCF"][["year", "tmIDWinner"]]
key = t.set_index(["tmID", "year"]).franchID
cup_fy = {(key.get((r.tmIDWinner, r.year)), r.year) for r in scf.itertuples()}

fr = t.groupby("franchID").agg(
    first=("year", "min"), last=("year", "max"), n=("year", "count"),
    name=("name", lambda x: x.iloc[-1])).reset_index()
fr = fr.sort_values(["first", "franchID"]).reset_index(drop=True)
cups_per = {f: sum(1 for ff, _ in cup_fy if ff == f) for f in fr.franchID}

# league goals-per-game per year (both teams; each game counted twice in G)
gpg = (t.groupby("year").GF.sum() / (t.groupby("year").G.sum() / 2)).to_dict()
for y in range(Y0, Y1 + 1):              # 2004-05 lockout: tide holds its breath
    if y not in gpg:
        gpg[y] = gpg[y - 1]
gmin, gmax = min(gpg.values()), max(gpg.values())
def tide_scale(y):
    return round(1.6 + 3.4 * (gpg[y] - gmin) / (gmax - gmin), 4)
def tide_color(y):
    u = (gpg[y] - gmin) / (gmax - gmin)
    lo, hi = (60, 120, 220), (255, 120, 40)
    return tuple(round(lo[i] + (hi[i] - lo[i]) * u) for i in range(3))

LEAGUE_COLOR = {"NHL": (198, 204, 214), "WHA": (40, 130, 255),
                "NHA": (176, 124, 62), "PCHA": (110, 155, 190),
                "WCHL": (150, 110, 165)}
def diff_color(dpg):
    x = max(-1.5, min(1.5, dpg)) / 1.5
    lo, mid, hi = (35, 70, 215), (150, 155, 165), (255, 185, 30)
    a, b, u = (lo, mid, x + 1) if x < 0 else (mid, hi, x)
    return tuple(round(a[i] + (b[i] - a[i]) * u) for i in range(3))

# ---- channel registry: (birth_year, final_alpha) -> channel id ----
chan_of, tracks = {}, {}                 # tracks[ch] = list of NSTEP values
def birth_channel(year, alpha):
    k = (year, alpha)
    if k not in chan_of:
        ch = len(chan_of) + 1
        chan_of[k] = ch
        tracks[ch] = [alpha if (Y0 + s) >= year else 0 for s in range(NSTEP)]
    return chan_of[k]

COLS = ["id", "type", "parent_id", "branch_level",
        "translate_x", "translate_y", "translate_z",
        "rotate_x", "rotate_y", "rotate_z",
        "scale_x", "scale_y", "scale_z",
        "color_r", "color_g", "color_b", "color_a",
        "geometry", "hide", "topo",
        "ratio", "color_index", "palette_id", "ch_input_id",
        "rotate_rate_z", "text"]
rows, _next = [], [1]
def node(type=5, parent=0, level=0, t3=(0, 0, 0), sc=(1, 1, 1),
         rgb=(200, 200, 200), a=255, geo=3, topo=0, ratio=0.1,
         cidx=0, pal=0, ch=0, rrz=0.0, text=""):
    nid = _next[0]; _next[0] += 1
    rows.append(dict(zip(COLS, [
        nid, type, parent, level,
        round(t3[0], 6), round(t3[1], 6), round(t3[2], 6), 0, 0, 0,
        round(sc[0], 6), round(sc[1], 6), round(sc[2], 6),
        rgb[0], rgb[1], rgb[2], a, geo, 0, topo, ratio, cidx, pal, ch, rrz,
        "".join(ch_ for ch_ in text if ch_.isprintable())])))
    return nid

R, STEP_DEG = 15.0, 3.96

node(type=0, rgb=(8, 10, 20), geo=0)                                   # World
node(parent=0, sc=(16, 16, 16), rgb=(70, 76, 92), geo=6, topo=0,
     ratio=0.0625, cidx=15, text="The Century Ring - 1909 to 2012")
hub = node(parent=0, sc=(1, 1, 1), rgb=(20, 20, 26), geo=22, topo=0,
           ratio=0.08, rrz=0.015,
           text="Century Reef - press Play: one step per season, 1909-10 on")

for i, f in fr.iterrows():
    ang = i * 360.0 / len(fr)
    aR = math.radians(ang)
    seasons = t[t.franchID == f.franchID].sort_values("year")
    ped = node(parent=hub, level=1,
               t3=(R * math.cos(aR), R * math.sin(aR), 0),
               sc=(1, 1, 1), rgb=LEAGUE_COLOR[seasons.lgID.iloc[0]],
               geo=19, topo=6, cidx=15, ch=birth_channel(int(f.first), 255),
               text=(f"{f['name']} ({f.franchID}) - {f.n} seasons "
                     f"{f.first}-{str(f.last + 1)[2:]}"
                     + (f" - {cups_per[f.franchID]} Stanley Cups"
                        if cups_per[f.franchID] else "")))
    for j, s in enumerate(seasons.itertuples()):
        w = 0.2 + 0.6 * max(0.0, min(1.0, s.ppct))
        made_po = isinstance(s.playoff, str) and s.playoff != ""
        alpha = 255 if made_po else 175
        rec = f"{int(s.W)}-{int(s.L)}" + (f"-{int(s.T)}" if pd.notna(s.T) else "")
        node(parent=ped, level=2, t3=(j * STEP_DEG, 0, 0),
             sc=(w, w, 0.2), rgb=diff_color(s.dpg), a=alpha, geo=19, topo=0,
             cidx=round(127 * (max(-1.5, min(1.5, s.dpg)) / 3 + 0.5)), pal=8,
             ch=birth_channel(int(s.year), alpha),
             text=(f"{s.year}-{str(s.year + 1)[2:]} {s.name} [{s.lgID}] - "
                   f"{int(s.Pts)} pts ({rec}) GF {int(s.GF)} / GA {int(s.GA)}"))
        if (f.franchID, s.year) in cup_fy:
            node(parent=ped, level=2, t3=(j * STEP_DEG, ang, 0.85),
                 sc=(0.28, 0.28, 0.28), rgb=(255, 215, 0), geo=9, topo=0,
                 cidx=4, ch=birth_channel(int(s.year), 255),
                 text=f"Stanley Cup {s.year + 1} - {s.name}")

# ---- the tide: league goals-per-game breathing at the center ----
tide_ch = len(chan_of) + 1
mean_y = min(gpg, key=lambda y: abs(gpg[y] - sum(gpg.values()) / len(gpg)))
node(parent=0, t3=(0, 0, 0.6), sc=(tide_scale(mean_y),) * 3,
     rgb=tide_color(mean_y), a=120, geo=7, topo=0, ratio=0.35, cidx=7,
     ch=tide_ch,
     text=("The Tide - league goals per game: "
           f"low {gmin:.2f}, high {gmax:.2f}"))
tr_scale = tide_ch
tracks[tr_scale] = [tide_scale(Y0 + s) for s in range(NSTEP)]
tr_r, tr_g, tr_b = tide_ch + 1, tide_ch + 2, tide_ch + 3
for k, tr in enumerate((tr_r, tr_g, tr_b)):
    tracks[tr] = [tide_color(Y0 + s)[k] for s in range(NSTEP)]

# ---- write node file ----
with open(f"{OD}/century_reef_gv_node.csv", "w", newline="",
          encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=COLS, lineterminator="\r\n")
    w.writeheader(); w.writerows(rows)

# ---- write ch-map ----
maprows = []
for (_, alpha), ch in sorted(chan_of.items(), key=lambda kv: kv[1]):
    maprows.append([len(maprows) + 1, ch, ch, "color_a", 0, 0, 0])
for attr, tr in [("scale_x", tr_scale), ("scale_y", tr_scale),
                 ("scale_z", tr_scale), ("color_r", tr_r),
                 ("color_g", tr_g), ("color_b", tr_b)]:
    maprows.append([len(maprows) + 1, tide_ch, tr, attr, 0, 0, 0])
with open(f"{OD}/century_reef_gv_ch-map.csv", "w", newline="",
          encoding="utf-8") as fh:
    w = csv.writer(fh, lineterminator="\r\n")
    w.writerow(["id", "channel_id", "track_id", "attribute",
                "track_table_id", "ch_map_table_id", "record_id"])
    w.writerows(maprows)

# ---- write ch-tracks (rows = time steps, cols = tracks) ----
ntr = max(tracks)
with open(f"{OD}/century_reef_gv_ch-tracks.csv", "w", newline="",
          encoding="utf-8") as fh:
    w = csv.writer(fh, lineterminator="\r\n")
    w.writerow(["cyclecount"] + [f"ch{k}" for k in range(1, ntr + 1)])
    for s in range(NSTEP):
        w.writerow([s + 1] + [tracks[k][s] if k in tracks else 0
                              for k in range(1, ntr + 1)])

print(f"nodes: {len(rows)} | channels: {len(chan_of)} birth + 1 tide "
      f"| tracks: {ntr} | steps: {NSTEP} | ch-map rows: {len(maprows)}")
