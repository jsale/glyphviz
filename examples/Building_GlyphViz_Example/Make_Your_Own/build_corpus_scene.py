"""Step 3a: every session in one scene -- the full "forest" of columns.

    python build_corpus_scene.py              # -> out/Session_Corpus/gv_node.csv
    python build_corpus_scene.py --public     # scrubbed copy, safe to share
    python build_corpus_scene.py --report     # also print layout statistics

LAYOUT
------
    X = project BANK, then archetype lane within it. One bank per entry in
        config.PROJECTS, left to right in the order listed; five lanes per
        bank, in the order work usually moves: design talk -> quick fix ->
        feature build -> example authoring -> docs & release.
    Y = calendar date, shared by every bank, so quiet days are real gaps, busy
        days are real clusters, and a look across the banks shows what each
        project was doing that same week.
    Z = the column: height = how much work happened (see glyph_kit.py).

An empty lane keeps its nameplate ("0 sessions"): a missing lane would just
look like a narrower bank, where the empty one says something true.

Several sessions of one kind on one day fan out ACROSS their lane, never
along it, since Y means the calendar.
"""
from __future__ import annotations

import argparse
import collections
import math
import os
from datetime import date

import archetypes as AR
import config
import glyph_kit as K

LANES = ["design talk", "quick fix", "feature build", "example authoring",
         "docs & release"]
LANE_PITCH = 18.0        # world units between lane centres
BANK_GAP = 30.0          # clear space between neighbouring banks
DAY_PITCH = 3.0          # world units per calendar day
FAN = 3.2                # spacing between same-lane, same-day sessions; must
                         # clear a column's widest part, its commit band
MONTHS = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY",
          "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"]

BANK_SPAN = (len(LANES) - 1) * LANE_PITCH          # lane centre to lane centre
BANK_PITCH = BANK_SPAN + BANK_GAP                  # bank centre to bank centre


def lane_x(name, bank, n_banks):
    bank_c = (bank - (n_banks - 1) / 2.0) * BANK_PITCH
    return bank_c + (LANES.index(name) - (len(LANES) - 1) / 2.0) * LANE_PITCH


def plan_layout(sessions, banks):
    """Every session -> (session, x, y): bank by project, lane by archetype,
    day by date, fanned across the lane when a lane-day holds several."""
    day0 = date.fromisoformat(min(s["date"] for s in sessions))
    cell = collections.defaultdict(list)
    for s in sessions:
        cell[(s["project"], s["archetype"], s["date"])].append(s)
    placed = []
    for (proj, arch, d), group in cell.items():
        group.sort(key=lambda s: s["start"])
        cx = lane_x(arch, banks.index(proj), len(banks))
        cy = (date.fromisoformat(d) - day0).days * DAY_PITCH
        for k, s in enumerate(group):
            placed.append((s, cx + (k - (len(group) - 1) / 2.0) * FAN, cy))
    placed.sort(key=lambda t: t[0]["start"])
    return placed, day0


def build():
    b = K.Builder()
    sessions, _ = AR.build()
    turns_by, events_by = K.load_side_tables()
    banks = [p["key"] for p in config.PROJECTS if any(s["project"] == p["key"] for s in sessions)]
    nb = len(banks)
    counts = collections.Counter((s["project"], s["archetype"]) for s in sessions)
    b.world(text="%s - scene settings" % config.CORPUS_TITLE)

    placed, day0 = plan_layout(sessions, banks)
    y_end = max(y for _, _, y in placed)
    heights = []
    for s, x, y in placed:
        p = K.PROJECT[s["project"]]
        _, h, _ = K.build_column(
            b, x, y, s, turns_by.get(s["session"], []), events_by, K.COMPACT,
            K.ARCH_COLOR[s["archetype"]],
            pedestal_color=p["color"], pedestal_note=" - %s" % p["short"],
            root_text=("%s  “%s”  -  %s - %s - %d prompts - %d tool calls"
                       " - %.0f min - %d files - %d commits"
                       % (s["date"], K.short(s["title"] or "(untitled)", 80),
                          p["short"], s["archetype"], s["prompts"], s["tools"],
                          s["active_min"], s["files_edited"], s["commits"])))
        heights.append(h)
    tallest = max(heights)

    # ---- lane nameplates at both ends of every bank, stepped in Z so five
    # plates far down the avenue don't land on one another ----
    for bi, proj in enumerate(banks):
        for i, name in enumerate(LANES):
            n = counts[(proj, name)]
            col = K.ARCH_COLOR[name] if n else tuple(int(c * 0.42) for c in K.ARCH_COLOR[name])
            for yy in (-5.0, y_end + 5.0):
                b.glyph(0, 0, (lane_x(name, bi, nb), yy, 1.5 + i * 2.8), 1.0, col,
                        K.GEO_POINT, ratio=0.24, pin=1,
                        text="%s - %s" % (name.upper(), K.plural(n, "session")))

    # ---- bank nameplates, and a rail down each bank's outer edges: the rails
    # say which project you are in from inside the scene ----
    for bi, proj in enumerate(banks):
        p = K.PROJECT[proj]
        g = [s for s in sessions if s["project"] == proj]
        centre = (bi - (nb - 1) / 2.0) * BANK_PITCH
        full = ("%s  -  %s, %s, %d tool calls, %d commits, first %s"
                % (p["label"], K.plural(len(g), "session"),
                   K.plural(sum(s["prompts"] for s in g), "prompt"),
                   sum(s["tools"] for s in g), sum(s["commits"] for s in g),
                   min(s["date"] for s in g)))
        for yy, plate in ((-9.0, full), (y_end + 9.0, p["short"].upper())):
            b.glyph(0, 0, (centre, yy, 1.5 + len(LANES) * 2.8), 1.0, p["color"],
                    K.GEO_POINT, ratio=0.34, pin=1, text=plate)
        for side in (-1, 1):
            rx = centre + side * (BANK_SPAN / 2.0 + 9.0)
            a = b.glyph(0, 0, (rx, -6.0, 0.02), 1.0, p["color"], K.GEO_POINT,
                        ratio=0.05, text="%s bank edge" % p["short"])
            z = b.glyph(0, 0, (rx, y_end + 6.0, 0.02), 1.0, p["color"], K.GEO_POINT,
                        ratio=0.05, text="%s bank edge" % p["short"])
            b.glyph(a, 0, (0.0, 0.0, 0.0), 1.0, p["color"], K.GEO_LINE, ratio=0.04,
                    ntype=K.TYPE_LINK, child_id=z,
                    text="%s - %s" % (p["short"], K.plural(len(g), "session")))

    # ---- month markers: a pinned label and a line ruled across every bank --
    x_lo = lane_x(LANES[0], 0, nb) - 11.0
    x_hi = lane_x(LANES[-1], nb - 1, nb) + 11.0
    months = sorted({tuple(map(int, s["date"][:7].split("-"))) for s in sessions})
    for year, mon in months:
        ym = max(-3.0, (date(year, mon, 1) - day0).days * DAY_PITCH)
        label = "%s %d" % (MONTHS[mon - 1], year)
        a = b.glyph(0, 0, (x_lo, ym, 0.05), 1.0, (150, 150, 175), K.GEO_POINT,
                    ratio=0.26, pin=1, text=label)
        z = b.glyph(0, 0, (x_hi, ym, 0.05), 1.0, (150, 150, 175), K.GEO_POINT,
                    ratio=0.26, text=label + " - far end")
        b.glyph(a, 0, (0.0, 0.0, 0.0), 1.0, (86, 88, 110), K.GEO_LINE, ratio=0.05,
                ntype=K.TYPE_LINK, child_id=z, text="start of " + label)

    # ---- title and legend, off the near end ----
    b.glyph(0, 0, (0.0, -24.0, tallest * 0.80), 1.0, (255, 255, 255), K.GEO_POINT,
            ratio=0.3, pin=1,
            text=("%s - %s%s, %.0f active hours, %d prompts, %d tool calls, "
                  "%d commits, %s to %s"
                  % (config.CORPUS_TITLE, K.plural(len(sessions), "session"),
                     " across %d projects" % nb if nb > 1 else "",
                     sum(s["active_min"] for s in sessions) / 60.0,
                     sum(s["prompts"] for s in sessions),
                     sum(s["tools"] for s in sessions),
                     sum(s["commits"] for s in sessions),
                     sessions[0]["date"], sessions[-1]["date"])))
    legend = list(K.LEGEND) + [
        (K.GEO_RING, K.PROJECT[proj]["color"], (0.62, 0.62, 0.06),
         "pedestal colour - a %s session" % K.PROJECT[proj]["short"])
        for proj in banks]
    for k, (geo, col, sc, label) in enumerate(legend):
        b.glyph(0, 0, (x_lo - 9.0, -6.0, 12.0 - k * 0.95), sc, col, geo, ratio=0.1,
                pin=1, text=label)
    return b, placed, heights, banks


def report(placed, heights, banks):
    xs = [x for _, x, _ in placed]
    ys = [y for _, _, y in placed]
    print("\nextents  x %.0f..%.0f   y %.0f..%.0f   z 0..%.1f"
          % (min(xs), max(xs), min(ys), max(ys), max(heights)))
    for proj in banks:
        print("  %-10s %d columns" % (proj, sum(1 for s, _, _ in placed if s["project"] == proj)))
    order = sorted(heights)
    top = placed[heights.index(max(heights))][0]
    print("height   median %.1f   max %.1f (%s “%s”)"
          % (order[len(order) // 2], max(heights), top["date"], top["title"]))
    fan = collections.Counter((s["project"], s["archetype"], s["date"]) for s, _, _ in placed)
    (proj, arch, d), n = fan.most_common(1)[0]
    print("busiest lane-day: %d sessions (%s %s, %s)" % (n, proj, arch, d))
    # A fan's outer columns sit (n-1)*FAN/2 from the lane centre, plus a
    # commit band's radius; past half a lane they can touch the next lane's.
    need = (n - 1) * FAN + 2 * K.COMPACT.ring_r
    if need > LANE_PITCH:
        print("  note: a fan that wide can touch a busy neighbouring lane on the "
              "same day; LANE_PITCH %.0f or more keeps them apart" % math.ceil(need))
    close = min((math.dist(a[1:], c[1:]) for i, a in enumerate(placed)
                 for c in placed[i + 1:]), default=0.0)
    print("closest pair of columns: %.2f units apart" % close)
    # Camera hints for tools/export_frame.py or the app's own camera.
    print("\ncamera: down the avenue  --azimuth 270 --elevation 16 --distance %.0f "
          "--target 0 %.0f 12" % (max(ys) * 1.1 + 40, max(ys) / 2))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--public", action="store_true",
                    help="scrub private paths and names so the scene can be shared")
    ap.add_argument("--report", action="store_true", help="print layout statistics")
    ap.add_argument("--out", help="output folder (default out/Session_Corpus[_public])")
    args = ap.parse_args()
    K.PUBLIC = args.public
    out = args.out or os.path.join(config.OUT_DIR, "Session_Corpus" + ("_public" if args.public else ""))
    b, placed, heights, banks = build()
    path = os.path.join(out, "gv_node.csv")
    n = b.write(path)
    print("wrote %s  (%d nodes, %.1f MB)" % (path, n, os.path.getsize(path) / 1e6))
    if args.report:
        report(placed, heights, banks)


if __name__ == "__main__":
    main()
