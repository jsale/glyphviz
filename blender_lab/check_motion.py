"""Continuity audit of a bake: per-frame jumps in position/colour for animated parts.

    python check_motion.py out/machine [part-prefix ...]

A kinematic path can hide a discontinuity that a few stills never show.  This
walks every frame transition (including the wrap 360 -> 1) and reports the
biggest step of each part's world position, ignoring steps where the part is
hidden on either side (a portal teleport is allowed to jump).
"""
import json
import sys
from pathlib import Path

import numpy as np

bake = json.loads((Path(sys.argv[1]) / "bake.json").read_text(encoding="utf-8"))
prefixes = tuple(sys.argv[2:]) or ("M", "B", "G", "P", "C", "K", "R")
rows = []
for nm, rec in sorted(bake["objects"].items()):
    if not nm.startswith(prefixes):
        continue
    M = np.asarray(rec["m"]).reshape(-1, 3, 4)
    P = np.asarray(rec["p"])
    pos = M[:, :, 3]
    hide = P[:, 4] > 0.5
    n = len(pos)
    step = np.linalg.norm(np.roll(pos, -1, axis=0) - pos, axis=1)      # i -> i+1, last wraps to first
    vis = ~(hide | np.roll(hide, -1))
    if not vis.any():
        continue
    s = np.where(vis, step, 0.0)
    i = int(s.argmax())
    col = P[:, :3]
    cstep = np.abs(np.roll(col, -1, axis=0) - col).max(axis=1)
    cstep = np.where(vis, cstep, 0.0)
    j = int(cstep.argmax())
    rows.append((nm, s.max(), i + 1, float(np.median(step)), cstep.max(), j + 1))
print("%-18s %9s %6s %9s   %9s %6s" % ("part", "max step", "@frame", "median", "max dRGB", "@frame"))
for r in rows:
    print("%-18s %9.4f %6d %9.4f   %9.1f %6d" % r)
