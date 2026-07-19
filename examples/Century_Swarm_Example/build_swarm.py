#!/usr/bin/env python3
"""The Century Swarm — every player-season with 25+ games, 1921-2011, as a
hyperglyph placed at its coordinates in scoring phase space.

Axes (position IS the meaning):
  X = goals per game   (0 .. 1.31)  -> snipers drift right
  Y = assists per game (0 .. 2.04)  -> playmakers drift deep
  Z = season year      (1921-2011)  -> the century rises

Each of the 29,140 rows is a parent sphere (size = points per game, color =
position: red centers, orange LW, gold RW, blue defense, green goalies)
carrying facet satellites: goals cone (+X), assists sphere (-X), PIM cube
(+Y), and a +/- octahedron (-Y, green/red by sign) when the stat exists
(1959 onward). ~140,000 nodes total.

Reading the shape: the swarm hugs the low corner (most seasons are
ordinary), bulges outward through the 1980s, contracts in the dead-puck
years — and the transcendent seasons physically escape the cloud.
Defensemen form a blue wall along low-G; Orr's seasons are blue glyphs deep
in forward territory.

Bounding: cloud centered near origin, ~56 x 55 x 50 units.
"""
import csv, math
import pandas as pd
import numpy as np

import os
UP = os.environ.get("HOCKEY_DATA", "./data")  # folder with the hockey history CSVs (Teams, Scoring, Master, SeriesPost, AwardsPlayers, HOF, TeamVsTeam)
OUT = "./century_swarm_gv_node.csv"

s = pd.read_csv(f"{UP}/Scoring.csv", low_memory=False)
mast = pd.read_csv(f"{UP}/Master.csv", low_memory=False)
mast = mast.dropna(subset=["playerID"]).drop_duplicates("playerID") \
           .set_index("playerID")

q = s[s.GP >= 25].copy()
q["gpg"] = q.G / q.GP
q["apg"] = q.A / q.GP
q["ppg"] = q.Pts / q.GP
q["pos"] = q.playerID.map(mast.pos).fillna("?").astype(str).str[0]
q["PM"] = q["+/-"]
q["first"] = q.playerID.map(mast.firstName).fillna("")
q["last"] = q.playerID.map(mast.lastName).fillna("")
q = q.sort_values(["year", "playerID", "stint"]).reset_index(drop=True)

# --- phase-space mapping (centered so nothing strays far from origin) ---
SX, SY = 42.0, 27.0                # per-unit-rate stretch
def X(gpg): return gpg * SX - 26.0            # -26 .. +29
def Yc(apg): return apg * SY - 26.0           # -26 .. +29
def Z(year): return (year - 1921) * 0.55 - 24.0   # -24 .. +25.5

POS_COLOR = {"C": ((225, 55, 65), 2), "L": ((255, 145, 0), 6),
             "R": ((255, 205, 40), 10), "W": ((255, 170, 20), 6),
             "F": ((255, 170, 20), 6), "D": ((60, 130, 255), 12),
             "G": ((0, 200, 120), 9), "?": ((150, 155, 165), 15)}
MAXPPG, MAXG, MAXA = 2.77, 92.0, 163.0
PIMCAP, PMCAP = 250.0, 100.0

COLS = ["id", "type", "parent_id", "branch_level",
        "translate_x", "translate_y", "translate_z",
        "rotate_x", "rotate_y", "rotate_z",
        "scale_x", "scale_y", "scale_z",
        "color_r", "color_g", "color_b", "color_a",
        "geometry", "hide", "topo",
        "ratio", "facet", "color_index", "palette_id", "text"]

fh = open(OUT, "w", newline="", encoding="utf-8")
w = csv.writer(fh, lineterminator="\r\n")
w.writerow(COLS)
_next = [0]
def emit(type=5, parent=0, level=0, t3=(0, 0, 0), sc=(1, 1, 1),
         rgb=(200, 200, 200), a=255, geo=3, topo=0, ratio=0.1, facet=0,
         cidx=0, pal=0, text=""):
    _next[0] += 1
    w.writerow([_next[0], type, parent, level,
                round(t3[0], 4), round(t3[1], 4), round(t3[2], 4), 0, 0, 0,
                round(sc[0], 4), round(sc[1], 4), round(sc[2], 4),
                rgb[0], rgb[1], rgb[2], a, geo, 0, topo, ratio, facet,
                cidx, pal, "".join(c for c in text if c.isprintable())])
    return _next[0]

emit(type=0, rgb=(8, 10, 20), geo=0)                       # World
root = emit(parent=0, sc=(1, 1, 1), rgb=(20, 20, 26), geo=22, ratio=0.06,
            text=("The Century Swarm - 29,140 player-seasons (25+ GP), "
                  "1921-22 to 2011-12 - X goals/gm, Y assists/gm, Z year"))

# axis + decade guides
for yr in range(1930, 2011, 10):
    emit(parent=root, level=1, t3=(X(0) - 2.5, Yc(0) - 2.5, Z(yr)),
         sc=(0.45, 0.45, 0.45), rgb=(120, 128, 150), geo=1, cidx=15,
         text=f"{yr}s")
for gv in (0.5, 1.0):
    emit(parent=root, level=1, t3=(X(gv), Yc(0) - 2.5, Z(1921) - 2),
         sc=(0.4, 0.4, 0.4), rgb=(255, 145, 60), geo=5, cidx=6,
         text=f"{gv:g} goal/game")
for av in (0.5, 1.0, 1.5, 2.0):
    emit(parent=root, level=1, t3=(X(0) - 2.5, Yc(av), Z(1921) - 2),
         sc=(0.4, 0.4, 0.4), rgb=(80, 170, 255), geo=3, cidx=12,
         text=f"{av:g} assist/game")

for r in q.itertuples():
    rgb, cidx = POS_COLOR.get(r.pos, POS_COLOR["?"])
    psc = 0.6 + 0.4 * min(r.ppg / MAXPPG, 1.0)
    yy = str(int(r.year) + 1)[2:]
    label = (f"{int(r.year)}-{yy} {r.first} {r.last} ({r.tmID}) "
             f"[{r.pos}] - {int(r.Pts)} Pts ({int(r.G)}G {int(r.A)}A) "
             f"in {int(r.GP)} GP")
    p = emit(parent=root, level=1,
             t3=(X(r.gpg), Yc(r.apg), Z(int(r.year))),
             sc=(psc, psc, psc), rgb=rgb, geo=3, topo=1, cidx=cidx,
             text=label)
    for val, mx, srgb, geo, fct, ci, txt in (
            (r.G, MAXG, (255, 60, 60), 5, 1, 2, f"{int(r.G)} G"),
            (r.A, MAXA, (0, 152, 255), 3, 2, 12, f"{int(r.A)} A"),
            (min(r.PIM if pd.notna(r.PIM) else 0, PIMCAP), PIMCAP,
             (255, 168, 0), 1, 3, 6,
             f"{int(r.PIM) if pd.notna(r.PIM) else 0} PIM")):
        sc = 0.34 + 0.3 * min(val / mx, 1.0)
        emit(parent=p, level=2, t3=(0, 0, 0.12), sc=(sc, sc, sc),
             rgb=srgb, geo=geo, facet=fct, cidx=ci, text=txt)
    if pd.notna(r.PM):
        pmv = float(r.PM)
        pmc, pmi = ((0, 200, 80), 9) if pmv >= 0 else ((220, 40, 40), 14)
        sc = 0.34 + 0.3 * min(abs(pmv) / PMCAP, 1.0)
        emit(parent=p, level=2, t3=(0, 0, 0.12), sc=(sc, sc, sc),
             rgb=pmc, geo=11, facet=4, cidx=pmi,
             text=f"{'+' if pmv >= 0 else ''}{int(pmv)}")

fh.close()
print(f"wrote {_next[0]} nodes -> {OUT}")
