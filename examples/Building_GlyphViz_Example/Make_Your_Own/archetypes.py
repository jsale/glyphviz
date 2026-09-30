"""Step 2: sort every session into one of five archetypes and pick exemplars.

Run it directly for a text report -- it is the quickest way to check that
config.PATH_CATS fits your repo before building a scene:

    python archetypes.py

The taxonomy is rule-based rather than k-means on purpose: every session's
label can be explained in one sentence, and the rules read off what the
transcripts actually show (how much action a prompt produced, and which kind
of file the edits landed in).

The exemplar of each archetype is its MEDOID -- the real session closest to
the group's median profile -- not a synthetic average. An averaged session
would have perfectly regular turns and lose the thing worth looking at: the
real texture of a real tool sequence, its pauses, and where it went wrong.
"""
from __future__ import annotations

import collections
import math
import os
import statistics

import config
from glyph_kit import load_csv

ARCHETYPES = ["feature build", "example authoring", "docs & release",
              "quick fix", "design talk"]

# Feature vector used for medoid selection.
PROFILE = ["active_min", "prompts", "prompt_words", "tools", "files_edited",
           "think_blocks", "asst_words", "commits", "tests", "errors",
           "asst_msgs", "images"]


def classify(s):
    """One session -> one archetype, first matching rule wins."""
    edits = {k: sum(s.get(f"cat_{c}", 0) for c in cats)
             for k, cats in config.AREA.items()}
    action = s["tools"] / max(s["prompts"], 1)

    # Talk, not work: the prompts produced almost no tool use.
    if action < 6 or (s["tools"] < 25 and s["files_edited"] <= 2):
        return "design talk"
    # Short, single-target session.
    if s["active_min"] < 16 and s["tools"] < 90:
        return "quick fix"
    if sum(edits.values()) == 0:
        return "design talk"
    top = max(edits, key=lambda k: edits[k])
    return {"feature": "feature build", "example": "example authoring",
            "docs": "docs & release"}[top]


def medoid(group, stats):
    """The real session closest to the group's median vector, in z-space."""
    med = {k: statistics.median([r[k] for r in group]) for k in PROFILE}
    best, bestd = None, None
    for r in group:
        d = math.sqrt(sum(((r[k] - med[k]) / stats[k]) ** 2 for k in PROFILE))
        if bestd is None or d < bestd:
            best, bestd = r, d
    return best, med, bestd


def build():
    sessions = load_csv(os.path.join(config.DATA_DIR, "sessions.csv"))
    for s in sessions:
        s["archetype"] = classify(s)
    stats = {k: statistics.pstdev([r[k] for r in sessions]) or 1.0 for k in PROFILE}

    groups = collections.OrderedDict((a, []) for a in ARCHETYPES)
    for s in sessions:
        groups[s["archetype"]].append(s)
    out = collections.OrderedDict()
    for name, group in groups.items():
        if group:
            ex, med, dist = medoid(group, stats)
            out[name] = {"name": name, "n": len(group), "group": group,
                         "median": med, "exemplar": ex, "dist": dist}
    return sessions, out


def _fmt(v):
    return f"{v:,.0f}" if abs(v) >= 10 else f"{v:,.1f}"


def report():
    sessions, arch = build()
    total_min = sum(s["active_min"] for s in sessions)
    print(f"{len(sessions)} sessions  {total_min / 60:.1f} h active  "
          f"{sessions[0]['date']} -> {sessions[-1]['date']}\n")

    print("%-18s %4s %6s %5s %6s %5s %6s %5s %5s %5s" % (
        "archetype", "n", "min", "prm", "tool", "edit", "thnk", "cmt", "test", "err"))
    for a in arch.values():
        m = a["median"]
        print("%-18s %4d %6s %5s %6s %5s %6s %5s %5s %5s" % (
            a["name"], a["n"], _fmt(m["active_min"]), _fmt(m["prompts"]),
            _fmt(m["tools"]), _fmt(m["files_edited"]), _fmt(m["think_blocks"]),
            _fmt(m["commits"]), _fmt(m["tests"]), _fmt(m["errors"])))

    print("\nEXEMPLARS (medoid session per archetype)")
    for a in arch.values():
        e = a["exemplar"]
        print("  %-18s %s  %-44s  %.0f min, %d prompts, %d tools" % (
            a["name"], e["date"], (e["title"] or "(untitled)")[:44],
            e["active_min"], e["prompts"], e["tools"]))

    print("\nEDIT TARGET MIX per archetype (share of Edit/Write calls)")
    print("  -- a big 'other' share means config.PATH_CATS is missing a pattern")
    for a in arch.values():
        agg = collections.Counter()
        for s in a["group"]:
            for k, v in s.items():
                if k.startswith("cat_") and v:
                    agg[k[4:]] += v
        tot = sum(agg.values()) or 1
        print("  %-18s %s" % (a["name"], "  ".join(
            f"{k} {100 * v / tot:.0f}%" for k, v in agg.most_common(6))))

    keys = [p["key"] for p in config.PROJECTS]
    if len({s["project"] for s in sessions}) > 1:
        print("\nARCHETYPE BY PROJECT (sessions)")
        print("  %-18s %s" % ("", "  ".join("%8s" % k for k in keys)))
        for a in arch.values():
            print("  %-18s %s" % (a["name"], "  ".join(
                "%8d" % sum(1 for s in a["group"] if s["project"] == k) for k in keys)))

    print("\nARCHETYPE OVER TIME (sessions per month)")
    months = sorted({s["date"][:7] for s in sessions})
    print("  %-18s %s" % ("", "  ".join(months)))
    for a in arch.values():
        c = collections.Counter(s["date"][:7] for s in a["group"])
        print("  %-18s %s" % (a["name"], "  ".join(f"{c.get(m, 0):7d}" for m in months)))


if __name__ == "__main__":
    report()
