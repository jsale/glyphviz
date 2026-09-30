"""Step 3b: five large columns, one real session per archetype.

    python build_archetype_scene.py            # -> out/Session_Archetypes/gv_node.csv
    python build_archetype_scene.py --public   # scrubbed copy, safe to share

Each specimen is the archetype's MEDOID (see archetypes.py): a session that
actually happened, not an average. The group's median numbers hang under the
pedestal, so the exemplar can be checked against what it stands for. This is
the easier scene to learn to read a column in before opening the full corpus.
"""
from __future__ import annotations

import argparse
import os

import archetypes as AR
import config
import glyph_kit as K

SPACING = 10.0              # world units between specimen axes


def build():
    b = K.Builder()
    sessions, arch = AR.build()
    turns_by, events_by = K.load_side_tables()
    b.world(text="%s - scene settings" % config.ARCHETYPE_TITLE)

    order = sorted(arch.values(),
                   key=lambda a: a["exemplar"]["tools"] + a["exemplar"]["prompts"])
    x0 = -SPACING * (len(order) - 1) / 2.0
    tallest = 0.0
    projects_shown = []
    for i, a in enumerate(order):
        ex, med, name = a["exemplar"], a["median"], a["name"]
        col = K.ARCH_COLOR[name]
        p = K.PROJECT[ex["project"]]
        if ex["project"] not in projects_shown:
            projects_shown.append(ex["project"])
        headline = "%s  -  %d of %d sessions" % (name.upper(), a["n"], len(sessions))
        root, height, _ = K.build_column(
            b, x0 + i * SPACING, 0.0, ex, turns_by.get(ex["session"], []),
            events_by, K.ColumnStyle(), col, root_text=headline,
            pedestal_color=p["color"], pedestal_note=" - %s" % p["short"])
        tallest = max(tallest, height)

        # Detail lines hang below the pedestal, NOT pinned: five bases at one
        # height would stack their labels. Click a pedestal to read them.
        dim = tuple(int(c * 0.72) for c in col)
        b.glyph(root, 1, (0.0, -0.85, -1.0), 1.0, dim, K.GEO_POINT, ratio=0.05,
                text=("group median: %.0f min - %.0f prompts - %.0f tools - "
                      "%.0f files - %.0f thinking blocks - %.0f commits"
                      % (med["active_min"], med["prompts"], med["tools"],
                         med["files_edited"], med["think_blocks"], med["commits"])))
        b.glyph(root, 1, (0.0, -1.65, -1.0), 1.0, dim, K.GEO_POINT, ratio=0.05,
                text=("shown: %s  “%s”  -  %s - %d prompts, %d tool calls, %.0f min"
                      % (ex["date"], K.short(ex["title"] or "(untitled)", 46),
                         p["short"], ex["prompts"], ex["tools"], ex["active_min"])))
        # One pinned label per specimen, above its cap, lifted a little more
        # per column so two columns of similar height don't collide.
        b.glyph(root, 1, (0.0, height + 1.2 + i * 0.9, -1.0), 1.0, col,
                K.GEO_POINT, ratio=0.05, pin=1, text=headline)

    b.glyph(0, 0, (0.0, 0.0, tallest + 6.5), 1.0, (255, 255, 255), K.GEO_POINT,
            ratio=0.3, pin=1,
            text=("%s: %s, %.0f active hours, %d prompts, %d tool calls, %s to %s"
                  % (config.ARCHETYPE_TITLE, K.plural(len(sessions), "session"),
                     sum(s["active_min"] for s in sessions) / 60.0,
                     sum(s["prompts"] for s in sessions),
                     sum(s["tools"] for s in sessions),
                     sessions[0]["date"], sessions[-1]["date"])))

    # The legend stands off the short end of the row, clear of every coil.
    legend = list(K.LEGEND)
    if len(config.PROJECTS) > 1:
        legend += [(K.GEO_RING, K.PROJECT[k]["color"], (0.62, 0.62, 0.06),
                    "pedestal colour - the exemplar is a %s session" % K.PROJECT[k]["short"])
                   for k in projects_shown]
    for k, (geo, col, sc, label) in enumerate(legend):
        b.glyph(0, 0, (x0 - 12.0, 0.0, 14.0 - k * 0.95), sc, col, geo, ratio=0.1,
                pin=1, text=label)
    return b


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--public", action="store_true",
                    help="scrub private paths and names so the scene can be shared")
    ap.add_argument("--out", help="output folder (default out/Session_Archetypes[_public])")
    args = ap.parse_args()
    K.PUBLIC = args.public
    out = args.out or os.path.join(config.OUT_DIR, "Session_Archetypes" + ("_public" if args.public else ""))
    b = build()
    path = os.path.join(out, "gv_node.csv")
    print("wrote %s  (%d nodes)" % (path, b.write(path)))


if __name__ == "__main__":
    main()
