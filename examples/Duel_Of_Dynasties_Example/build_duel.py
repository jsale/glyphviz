#!/usr/bin/env python3
"""Duel of Dynasties — Gretzky, Howe, Lemieux: three career orreries on one
plane, one career-relative channel clock.

Clock: cyclecount k = 1..34 == "years since debut" (Howe's 34-year span
1946-1979 sets the length). Each player's ring is laid out on the same
calendar-relative arc, so retirement gaps are visible holes: Howe's
1971-72 sabbatical, Lemieux's 1994 injury year, 1997-99 retirement, and
the 2004 lockout.

Choreography per season (player p, career-year k):
  * season sphere: invisible until k, flares to 1.25x scale for one step,
    settles to its authored size (points, normalized to the shared 215 max)
  * stat glyphs, award stack, Cup ring, and points-curve vertex of that
    year: appear at k and stay (shared alpha channel per (p,k))
  * HOF icosahedron: appears at the player's REAL induction year -
    mid-career for Howe (1972) and Lemieux (1997), both of whom unretired
    after enshrinement.

Files: duel_of_dynasties_gv_node.csv / _gv_ch-map.csv / _gv_ch-tracks.csv
"""
import csv, math
import pandas as pd

import os
UP = os.environ.get("HOCKEY_DATA", "./data")  # folder with the hockey history CSVs (Teams, Scoring, Master, SeriesPost, AwardsPlayers, HOF, TeamVsTeam)
OD = "."   # scene files are written beside the script

s = pd.read_csv(f"{UP}/Scoring.csv", low_memory=False)
ap = pd.read_csv(f"{UP}/AwardsPlayers.csv")
sp = pd.read_csv(f"{UP}/SeriesPost.csv")
hof = pd.read_csv(f"{UP}/HOF.csv")

PLAYERS = [
    ("gretzwa01", "Wayne Gretzky", -12.5),
    ("howego01",  "Gordie Howe",     0.0),
    ("lemiema01", "Mario Lemieux", +12.5),
]
TEAM_COLOR = {
    "IND": ((0, 60, 150), 3), "EDO": ((252, 76, 2), 6),
    "EDM": ((252, 76, 2), 6), "LAK": ((176, 183, 188), 15),
    "STL": ((0, 47, 135), 3), "NYR": ((0, 56, 168), 3),
    "DET": ((206, 17, 38), 2), "HOU": ((0, 102, 255), 12),
    "NEW": ((0, 130, 90), 9), "HAR": ((0, 130, 90), 9),
    "PIT": ((255, 184, 28), 4),
}
AWARD_STYLE = {
    "Art Ross": ((255, 200, 40), 9, 10), "Hart": ((220, 30, 30), 15, 2),
    "Conn Smythe": ((0, 255, 255), 5, 7), "Pearson": ((152, 0, 255), 11, 5),
    "Lady Byng": ((255, 180, 255), 3, 11), "Plus-Minus": ((0, 200, 80), 10, 9),
    "First Team All-Star": ((255, 255, 255), 13, 19),
    "Second Team All-Star": ((170, 170, 170), 13, 15),
    "Kaplan": ((185, 255, 0), 1, 13), "Calder": ((0, 180, 255), 1, 12),
    "Masterton": ((255, 255, 180), 3, 18), "All-Rookie": ((120, 220, 255), 13, 12),
    "Davidson": ((40, 130, 255), 15, 12),
}
AWARD_RANK = {n: i for i, n in enumerate(AWARD_STYLE)}
MAXPTS, MAXG, MAXA, MAXPIM, MAXPM = 215.0, 92.0, 163.0, 109.0, 98.0
NSTEP = 34

scf = sp[sp["round"] == "SCF"][["year", "tmIDWinner"]]

COLS = ["id", "type", "parent_id", "branch_level",
        "translate_x", "translate_y", "translate_z",
        "rotate_x", "rotate_y", "rotate_z",
        "scale_x", "scale_y", "scale_z",
        "color_r", "color_g", "color_b", "color_a",
        "geometry", "hide", "topo",
        "ratio", "facet", "color_index", "palette_id", "ch_input_id",
        "rotate_rate_z", "text"]
rows, _next = [], [1]
def node(type=5, parent=0, level=0, t3=(0, 0, 0), sc=(1, 1, 1),
         rgb=(200, 200, 200), a=255, geo=3, topo=0, ratio=0.1, facet=0,
         cidx=0, pal=0, ch=0, rrz=0.0, text=""):
    nid = _next[0]; _next[0] += 1
    rows.append(dict(zip(COLS, [
        nid, type, parent, level,
        round(t3[0], 6), round(t3[1], 6), round(t3[2], 6), 0, 0, 0,
        round(sc[0], 6), round(sc[1], 6), round(sc[2], 6),
        rgb[0], rgb[1], rgb[2], a, geo, 0, topo, ratio, facet, cidx, pal,
        ch, rrz, "".join(c for c in text if c.isprintable())])))
    return nid

def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))

# channel/track registries
tracks, chmap_rows = {}, []
_ch, _tr = [0], [0]
def new_channel():
    _ch[0] += 1; return _ch[0]
def new_track(values):
    _tr[0] += 1; tracks[_tr[0]] = values; return _tr[0]
def bind(ch, attr, tr):
    chmap_rows.append([len(chmap_rows) + 1, ch, tr, attr, 0, 0, 0])

def step_alpha(k, a=255):                    # 0 until step k, then a
    return [a if (st + 1) >= k else 0 for st in range(NSTEP)]

node(type=0, rgb=(8, 10, 20), geo=0)         # World

for pid, pname, px in PLAYERS:
    g = s[s.playerID == pid]
    agg = g.groupby("year").agg(G=("G", "sum"), A=("A", "sum"),
                                Pts=("Pts", "sum"), PIM=("PIM", "sum"),
                                PM=("+/-", "sum")).reset_index()
    prim = g.sort_values("GP", ascending=False).groupby("year")["tmID"] \
            .first().to_dict()
    tmlist = g.sort_values(["year", "stint"]).groupby("year")["tmID"] \
              .apply(lambda x: "/".join(dict.fromkeys(x))).to_dict()
    awards = ap[ap.playerID == pid].groupby("year")["award"].apply(list).to_dict()
    ty = set(zip(g.tmID, g.year))
    cups = {int(r.year) for r in scf.itertuples() if (r.tmIDWinner, r.year) in ty}
    debut = int(agg.year.min())
    span = int(agg.year.max()) - debut + 1
    step_deg = 320.0 / (span - 1)
    tot = int(agg.Pts.sum())

    hub = node(parent=0, t3=(px, 0, 0), sc=(2.2, 2.2, 2.2),
               rgb=(198, 204, 214), geo=7, topo=3, ratio=0.18, cidx=15,
               rrz=0.02, text=(f"{pname} - {tot:,} points, "
                               f"{len(agg)} seasons over {span} years"))

    for _, r in agg.iterrows():
        y = int(r.year); k = y - debut + 1
        ang = 250.0 - (k - 1) * step_deg
        rgb, cidx = TEAM_COLOR[prim[y]]
        pn = r.Pts / MAXPTS
        ssc = 0.35 + 0.35 * pn
        # season channel: alpha step + scale flare-and-settle
        ch_season = new_channel()
        bind(ch_season, "color_a", new_track(step_alpha(k)))
        flare = [round(ssc * (1.25 if (st + 1) == k and k < NSTEP else 1.0), 4)
                 for st in range(NSTEP)]
        tr_f = new_track(flare)
        for ax in ("scale_x", "scale_y", "scale_z"):
            bind(ch_season, ax, tr_f)
        # aux channel: everything born with this season
        ch_aux = new_channel()
        bind(ch_aux, "color_a", new_track(step_alpha(k)))

        season = node(parent=hub, level=1, t3=(ang, 0, 1.6),
                      sc=(ssc, ssc, ssc), rgb=rgb, geo=3, topo=1,
                      cidx=cidx, ch=ch_season,
                      text=(f"{y}-{str(y + 1)[2:]} - {tmlist[y]} - "
                            f"{int(r.Pts)} Pts ({int(r.G)}G {int(r.A)}A)"))
        stats = [
            (r.G / MAXG, (255, 60, 60), 5, 1, 2, f"{int(r.G)} G"),
            (r.A / MAXA, (0, 152, 255), 3, 2, 12, f"{int(r.A)} A"),
            (r.PIM / MAXPIM, (255, 168, 0), 1, 3, 6, f"{int(r.PIM)} PIM"),
        ]
        for nrm, srgb, geo, fct, ci, txt in stats:
            sc = 0.3 + 0.5 * min(nrm, 1.0)
            node(parent=season, level=2, t3=(0, 0, 0.15), sc=(sc, sc, sc),
                 rgb=srgb, geo=geo, facet=fct, cidx=ci, ch=ch_aux, text=txt)
        pm = r.PM
        pmc, pmi = ((0, 200, 80), 9) if pm >= 0 else ((220, 40, 40), 14)
        sc = 0.3 + 0.5 * min(abs(pm) / MAXPM, 1.0)
        node(parent=season, level=2, t3=(0, 0, 0.15), sc=(sc, sc, sc),
             rgb=pmc, geo=11, facet=4, cidx=pmi, ch=ch_aux,
             text=f"{'+' if pm >= 0 else ''}{int(pm)}")
        alist = sorted(awards.get(y, []), key=lambda nm: AWARD_RANK.get(nm, 99))
        for j, nm in enumerate(alist):
            argb, ageo, aci = AWARD_STYLE.get(nm, ((190, 195, 205), 11, 15))
            node(parent=season, level=2, t3=(0, 0, 0.35 + j * 0.75),
                 sc=(0.3, 0.3, 0.3), rgb=argb, geo=ageo, facet=5, cidx=aci,
                 ch=ch_aux, text=f"{nm} {y}-{str(y + 1)[2:]}")
        if y in cups:
            node(parent=season, level=2, t3=(0, 0, 0.35),
                 sc=(0.45, 0.45, 0.45), rgb=(255, 215, 0), geo=6, facet=6,
                 cidx=4, ch=ch_aux, text=f"Stanley Cup {y + 1}")

    # HOF at the REAL induction year (mid-career for Howe and Lemieux)
    hy = int(hof[hof.hofID == pid + "h"].year.iloc[0])
    k_hof = min(max(hy - debut + 1, 1), NSTEP)
    ch_hof = new_channel()
    bind(ch_hof, "color_a", new_track(step_alpha(k_hof)))
    node(parent=hub, level=1, t3=(270, 0, 1.6), sc=(0.5, 0.5, 0.5),
         rgb=(255, 215, 0), geo=15, cidx=4, ch=ch_hof,
         text=f"Hockey Hall of Fame - Class of {hy}")

    # points-curve plot ring (verts share each season's aux? separate simple)
    puck = node(parent=0, t3=(px, 0, 0), sc=(0.5, 0.5, 0.5),
                rgb=(20, 20, 24), geo=19, topo=16, ratio=0.15, cidx=18,
                text=f"{pname} - points per season")
    for _, r in agg.iterrows():
        y = int(r.year); k = y - debut + 1
        ang = math.radians(250.0 - (k - 1) * step_deg)
        pn = r.Pts / MAXPTS
        lr, lz = 13.8, 1.2 + 6.8 * pn
        ch_v = new_channel()
        bind(ch_v, "color_a", new_track(step_alpha(k)))
        node(parent=puck, level=1,
             t3=(lr * math.cos(ang), lr * math.sin(ang), lz),
             sc=(0.5, 0.5, 0.5), rgb=lerp((152, 0, 255), (255, 255, 0), pn),
             geo=22, ratio=0.12, cidx=round(127 * pn), pal=10, ch=ch_v,
             text=f"{y}-{str(y + 1)[2:]}: {int(r.Pts)}")

# ---- write ----
with open(f"{OD}/duel_of_dynasties_gv_node.csv", "w", newline="",
          encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=COLS, lineterminator="\r\n")
    w.writeheader(); w.writerows(rows)
with open(f"{OD}/duel_of_dynasties_gv_ch-map.csv", "w", newline="",
          encoding="utf-8") as fh:
    w = csv.writer(fh, lineterminator="\r\n")
    w.writerow(["id", "channel_id", "track_id", "attribute",
                "track_table_id", "ch_map_table_id", "record_id"])
    w.writerows(chmap_rows)
ntr = max(tracks)
with open(f"{OD}/duel_of_dynasties_gv_ch-tracks.csv", "w", newline="",
          encoding="utf-8") as fh:
    w = csv.writer(fh, lineterminator="\r\n")
    w.writerow(["cyclecount"] + [f"ch{k}" for k in range(1, ntr + 1)])
    for st in range(NSTEP):
        w.writerow([st + 1] + [tracks[k][st] for k in range(1, ntr + 1)])
print(f"nodes: {len(rows)} | channels: {_ch[0]} | tracks: {ntr} | "
      f"steps: {NSTEP} | ch-map rows: {len(chmap_rows)}")
