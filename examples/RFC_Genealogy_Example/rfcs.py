#!/usr/bin/env python3
"""
rfcs.py — the RFC series as data: records, statuses, and the lineage forest.

Shared by `build_rfc_scenes.py`, `verify_rfc.py` and `verify_scenes.py` so
that the scene builder and its checkers cannot drift apart on what a lineage
*is*.

Two relations live in the index and they are not the same thing:

  obsoletes   A replaces B outright.  B is dead.  This is descent, and it is
              what "genealogy" means here.
  updates     A amends B.  B stays alive and you now have to read both.

The obsoletes relation, followed backwards from documents nobody has yet
replaced, is a forest: root = a specification in force today, children = the
documents it retired, grandchildren = the documents *those* retired.  Depth is
therefore the number of times a specification has been rewritten, which is a
measurement and not a layout choice.

It is not quite a tree.  109 RFCs are obsoleted by more than one successor
(RFC 2616, the old HTTP/1.1, was split across six documents), so those appear
in more than one lineage.  `lineage_forest()` materialises each occurrence as
its own node and reports the duplication rather than hiding it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "rfc_index.csv.gz"

# Status colours.  Ordered from "this is load-bearing" to "this is history".
STATUS_STYLE: dict[str, tuple[int, int, int]] = {
    "INTERNET STANDARD":     (255, 214,  92),   # gold
    "BEST CURRENT PRACTICE": (120, 210, 140),   # green
    "DRAFT STANDARD":        (110, 205, 205),   # teal
    "PROPOSED STANDARD":     ( 95, 150, 235),   # blue
    "EXPERIMENTAL":          (185, 130, 235),   # violet
    "INFORMATIONAL":         (170, 175, 190),   # grey
    "HISTORIC":              (200,  90,  85),   # red
    "UNKNOWN":               (130, 115,  95),   # brown
}
STATUS_ORDER = list(STATUS_STYLE)
DEFAULT_RGB = (130, 115, 95)


@dataclass
class Rfc:
    num: int
    title: str
    year: int
    month: int          # 1-12, or 0 when the index gives no month
    status: str
    stream: str
    pages: int
    area: str
    wg: str
    obsoletes: tuple[int, ...]
    obsoleted_by: tuple[int, ...]
    updates: tuple[int, ...]
    updated_by: tuple[int, ...]

    @property
    def doc(self) -> str:
        return f"RFC {self.num}"

    @property
    def when(self) -> float:
        """Publication date as a fractional year.

        The index records month precision only — there is no day field — so
        this is `year + (month-1)/12`, with a missing month treated as
        mid-year.
        """
        if self.month <= 0:
            return self.year + 0.5
        return self.year + (self.month - 1) / 12.0

    @property
    def rgb(self) -> tuple[int, int, int]:
        return STATUS_STYLE.get(self.status, DEFAULT_RGB)

    @property
    def url(self) -> str:
        return f"https://www.rfc-editor.org/rfc/rfc{self.num}"


def _ints(cell) -> tuple[int, ...]:
    if not isinstance(cell, str) or not cell.strip():
        return ()
    return tuple(int(x) for x in cell.split())


def load(path: Path | str = DATA) -> dict[int, Rfc]:
    """Read the distilled index into `{number: Rfc}`."""
    df = pd.read_csv(path, encoding="utf-8", keep_default_na=False)
    out: dict[int, Rfc] = {}
    for r in df.itertuples(index=False):
        out[int(r.num)] = Rfc(
            num=int(r.num), title=str(r.title), year=int(r.year),
            month=int(r.month), status=str(r.status) or "UNKNOWN",
            stream=str(r.stream), pages=int(r.pages),
            area=str(r.area), wg=str(r.wg),
            obsoletes=_ints(r.obsoletes), obsoleted_by=_ints(r.obsoleted_by),
            updates=_ints(r.updates), updated_by=_ints(r.updated_by))
    return out


# ---------------------------------------------------------------------------
# The lineage forest
# ---------------------------------------------------------------------------
@dataclass
class Lineage:
    """One ancestry tree, rooted at a document still in force."""
    root: int
    #: (rfc number, depth, parent index in `self.nodes`, sibling index,
    #:  sibling count).  Index 0 is the root, parent -1.
    nodes: list[tuple[int, int, int, int, int]] = field(default_factory=list)

    @property
    def depth(self) -> int:
        return max(n[1] for n in self.nodes)

    @property
    def size(self) -> int:
        return len(self.nodes)


def lineage_forest(recs: dict[int, Rfc]) -> list[Lineage]:
    """Every ancestry tree, deepest first.

    A root is an RFC that (a) nothing has obsoleted and (b) obsoletes at
    least one RFC that is itself in the index.  Documents with no ancestry
    at all are not lineages and are handled separately by the scene builder.

    Repeated visits along one path (which the index does not contain, but
    which a malformed future index could) are cut, so this always terminates.
    """
    forest: list[Lineage] = []
    for num, rec in recs.items():
        if rec.obsoleted_by:
            continue
        kids = [o for o in rec.obsoletes if o in recs]
        if not kids:
            continue
        lin = Lineage(root=num)
        # Iterative pre-order walk carrying the path, so a cycle cannot hang.
        stack = [(num, 0, -1, 0, 1, (num,))]
        while stack:
            n, d, parent, sib, nsib, path = stack.pop()
            here = len(lin.nodes)
            lin.nodes.append((n, d, parent, sib, nsib))
            children = [o for o in recs[n].obsoletes
                        if o in recs and o not in path]
            for i, c in enumerate(reversed(children)):
                stack.append((c, d + 1, here, len(children) - 1 - i,
                              len(children), path + (c,)))
        forest.append(lin)
    forest.sort(key=lambda l: (-l.depth, -l.size, l.root))
    return forest


def duplicated_members(forest: list[Lineage]) -> dict[int, int]:
    """`{rfc: how many lineage slots it occupies}` for anything counted more
    than once — the price of drawing a DAG as a forest of trees."""
    seen: dict[int, int] = {}
    for lin in forest:
        for num, *_ in lin.nodes:
            seen[num] = seen.get(num, 0) + 1
    return {k: v for k, v in seen.items() if v > 1}


def standing_stones(recs: dict[int, Rfc]) -> list[Rfc]:
    """Full Internet Standards that were never obsoleted and never obsoleted
    anything — specifications that were got right the first time and have
    been left alone ever since.  Oldest first."""
    out = [r for r in recs.values()
           if r.status == "INTERNET STANDARD"
           and not r.obsoleted_by
           and not [o for o in r.obsoletes if o in recs]]
    out.sort(key=lambda r: (r.when, r.num))
    return out
