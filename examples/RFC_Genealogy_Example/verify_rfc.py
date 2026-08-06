#!/usr/bin/env python3
"""
verify_rfc.py — check the index and the forest before anything is drawn.

Nothing here touches GlyphViz.  It checks that the distilled index is
internally consistent, that the lineage forest really is a forest, and that
the claims the README makes about the RFC series are recomputed from the data
rather than remembered.

    python verify_rfc.py
"""
from __future__ import annotations

import statistics
import sys
from collections import Counter

import rfcs

FAILS: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILS.append(label)


def main() -> int:
    recs = rfcs.load()

    print("== the index ==")
    check(len(recs) > 9_000, "the whole series is present",
          f"{len(recs):,} RFCs, {min(r.year for r in recs.values())}"
          f"-{max(r.year for r in recs.values())}")
    check(all(1 <= r.month <= 12 for r in recs.values()),
          "every RFC has a publication month")
    gaps = sorted(set(range(1, max(recs) + 1)) - set(recs))
    check(len(gaps) < 250,
          "the numbering has only the known unissued gaps",
          f"{len(gaps)} numbers never issued, e.g. "
          f"{', '.join(str(g) for g in gaps[:5])}")

    # The four cross-reference lists are four views of two relations.  If they
    # disagree, one direction of every lineage is wrong.
    for fwd, back, name in (("obsoletes", "obsoleted_by", "obsoletes"),
                            ("updates", "updated_by", "updates")):
        bad = [(n, o) for n, r in recs.items()
               for o in getattr(r, fwd) if o in recs
               and n not in getattr(recs[o], back)]
        n_edges = sum(1 for r in recs.values()
                      for o in getattr(r, fwd) if o in recs)
        check(not bad, f"every {name} edge is recorded from both ends",
              f"{n_edges:,} edges, {len(bad)} one-sided")

    dangling = {o for r in recs.values() for o in r.obsoletes if o not in recs}
    check(not dangling, "no RFC obsoletes something outside the index",
          f"{len(dangling)} dangling" if dangling else "")

    print("\n== the lineage forest ==")
    forest = rfcs.lineage_forest(recs)
    check(all(not recs[l.root].obsoleted_by for l in forest),
          "every lineage root is a document nothing has replaced")
    check(all(l.size > 1 for l in forest),
          "every lineage has at least one ancestor",
          f"{len(forest)} lineages, {sum(l.size for l in forest):,} slots")

    # Depth must equal the longest chain of obsoletes edges under the root --
    # recomputed here independently of the walk that built the forest.
    def longest(n: int, seen: frozenset[int]) -> int:
        best = 0
        for o in recs[n].obsoletes:
            if o in recs and o not in seen:
                best = max(best, 1 + longest(o, seen | {o}))
        return best

    worst = max((abs(l.depth - longest(l.root, frozenset({l.root}))), l.root)
                for l in forest)
    check(worst[0] == 0,
          "recorded depth is the longest obsoletes chain under the root",
          f"checked all {len(forest)} lineages")

    for lin in forest:
        for _num, depth, parent, _sib, _n in lin.nodes:
            assert parent < 0 or lin.nodes[parent][1] == depth - 1
    check(True, "every child sits exactly one generation below its parent")

    dup = rfcs.duplicated_members(forest)
    check(max(dup.values(), default=0) < 12,
          "the DAG-to-forest duplication stays bounded",
          f"{len(dup)} documents appear in more than one lineage, "
          f"worst RFC {max(dup, key=dup.get)} at {max(dup.values())} slots")

    hist = Counter(l.depth for l in forest)
    deepest = max(forest, key=lambda l: l.depth)
    check(deepest.depth >= 30,
          "the deepest lineage is the standards index rewriting itself",
          f"RFC {deepest.root} ({recs[deepest.root].year}) at depth "
          f"{deepest.depth}: {recs[deepest.root].title[:46]}")
    check(hist[1] / len(forest) > 0.7,
          "...but most specifications have been rewritten exactly once",
          f"{hist[1]} of {len(forest)} lineages are one generation deep "
          f"({100 * hist[1] / len(forest):.0f}%)")

    print("\n== what was never replaced ==")
    stones = rfcs.standing_stones(recs)
    check(all(r.status == "INTERNET STANDARD" and not r.obsoleted_by
              and not [o for o in r.obsoletes if o in recs] for r in stones),
          "the standing stones are full standards with no ancestry and no heir",
          f"{len(stones)} of them, {stones[0].year}-{stones[-1].year}")
    check(stones[0].num == 20 and stones[0].year == 1969,
          "the oldest is RFC 20, the ASCII specification, from 1969",
          f"RFC {stones[0].num} ({stones[0].year}) {stones[0].title}")
    have = {r.num for r in stones}
    check({768, 826} <= have,
          "...and they include UDP and ARP, untouched since 1980 and 1982",
          f"RFC 768 UDP ({recs[768].year}), RFC 826 ARP ({recs[826].year})")

    # IP and ICMP are *not* stones and should not be: each replaced an
    # earlier draft (791 obsoletes 760, 792 obsoletes 777), so each is a
    # one-generation lineage that has then stood untouched for 45 years.
    roots = {l.root: l for l in forest}
    check(791 in roots and roots[791].depth == 1
          and 792 in roots and roots[792].depth == 1,
          "IP and ICMP are one-generation lineages, not stones",
          f"RFC 791 IP ({recs[791].year}) replaced RFC 760 "
          f"({recs[760].year}); RFC 792 ICMP ({recs[792].year}) replaced "
          f"RFC 777 ({recs[777].year})")

    # The two populations must partition cleanly, or the lineage scene is
    # either double-counting documents or dropping them.
    never = {r.num for r in recs.values()
             if r.status == "INTERNET STANDARD" and not r.obsoleted_by}
    check(never == have | (never & set(roots)),
          "every Internet Standard still in force is a stone or a root",
          f"{len(never)} in force = {len(have)} stones + "
          f"{len(never & set(roots))} lineage roots")

    print("\n== how fast the series turns over ==")
    spans = [recs[n].when - recs[o].when
             for n, r in recs.items() for o in r.obsoletes if o in recs]
    check(4.0 <= statistics.median(spans) <= 5.0,
          "a replaced specification had stood for a median of ~4 years",
          f"median {statistics.median(spans):.1f} y, "
          f"90th percentile {sorted(spans)[int(0.9 * len(spans))]:.1f} y, "
          f"longest {max(spans):.1f} y")
    backwards = sum(1 for s in spans if s < 0)
    check(backwards <= 5,
          "hardly any RFC obsoletes something published after it",
          f"{backwards} of {len(spans):,} edges run backwards in time")

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: " + "; ".join(FAILS))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.setrecursionlimit(10_000)
    sys.exit(main())
