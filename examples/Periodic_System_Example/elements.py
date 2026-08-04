#!/usr/bin/env python3
"""
elements.py — the chemistry behind the Periodic System scenes.

Three separate jobs, deliberately kept apart:

1. **Real electron configurations**, parsed from PubChem's own strings
   (noble-gas shorthand expanded), including every experimentally observed
   anomaly — Cr's 3d5 4s1, Cu's 3d10 4s1, Gd's 4f7 5d1, and the rest.
2. **The idealised Madelung order**, computed from the (n+l, n) rule. This
   is what the *layout* uses.
3. **Hund's rule filling**, which decides where each individual electron of
   a subshell goes.

Keeping (1) and (2) apart is the point of the whole example: elements sit
where the idealised rule says they should, but are *drawn* from their real
configuration, so an anomalous element visibly differs from the column it
is standing in.

Data: PubChem Periodic Table of Elements (public domain, NCBI/NLM)
      https://pubchem.ncbi.nlm.nih.gov/rest/pug/periodictable/CSV
      vendored as data/pubchem_periodictable.csv
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent / "data"
CSV = DATA / "pubchem_periodictable.csv"

ORBITALS = "spdf"          # l = 0, 1, 2, 3
NOBLE = {"He": 2, "Ne": 10, "Ar": 18, "Kr": 36, "Xe": 54, "Rn": 86,
         "Og": 118}


# ---------------------------------------------------------------------------
# 1. THE IDEALISED MADELUNG (AUFBAU) ORDER
# ---------------------------------------------------------------------------
def madelung_groups() -> list[list[tuple[int, int, int]]]:
    """Subshells grouped by n+l, each group in filling order.

    The Madelung rule fills in order of increasing n+l, and within equal
    n+l in order of increasing n — which means *decreasing* l. A subshell
    needs l <= n-1, so the group n+l = g contains l = floor((g-1)/2) down
    to 0.

    Returns one list per g, of (n, l, capacity) triples.
    """
    groups = []
    g = 1
    while True:
        block = []
        for l in range((g - 1) // 2, -1, -1):
            n = g - l
            block.append((n, l, 2 * (2 * l + 1)))
        if not block:
            break
        groups.append(block)
        if sum(c for _n, _l, c in groups[-1]) and g >= 8:
            break
        g += 1
    return groups


#: Every group is a *suffix* of the longest one: [s], [s], [p,s], [p,s],
#: [d,p,s], [d,p,s], [f,d,p,s], [f,d,p,s]. That nesting is what lets the
#: helix right-align all eight turns onto one 32-slot angular grid with
#: every block — and therefore every group — in a true vertical column.
SLOTS_PER_TURN = 32


@dataclass(frozen=True)
class Placement:
    turn: int            # 0-based; the Madelung n+l group minus 1
    slot: int            # 0..31, right-aligned on the common angular grid
    block: str           # 's' | 'p' | 'd' | 'f' — the subshell being filled
    n: int               # principal quantum number of that subshell
    l: int


@lru_cache(maxsize=1)
def madelung_layout() -> dict[int, Placement]:
    """Atomic number -> where the idealised rule puts it on the helix."""
    out: dict[int, Placement] = {}
    z = 1
    for t, block in enumerate(madelung_groups()):
        length = sum(c for _n, _l, c in block)
        p = 0
        for (n, l, cap) in block:
            for _ in range(cap):
                if z <= 118:
                    out[z] = Placement(turn=t, slot=SLOTS_PER_TURN - length + p,
                                       block=ORBITALS[l], n=n, l=l)
                z += 1
                p += 1
    return out


# ---------------------------------------------------------------------------
# 2. REAL CONFIGURATIONS, FROM PUBCHEM
# ---------------------------------------------------------------------------
_TOKEN = re.compile(r"(\d+)([spdfg])(\d+)")


def parse_config(text: str, by_symbol: dict[str, str]) -> dict[tuple[int, int], int]:
    """Expand a configuration string into {(n, l): occupancy}.

    Handles the noble-gas shorthand ("[Xe]6s2 4f14 5d10") recursively and
    ignores PubChem's "(predicted)" marker on the superheavy elements.
    """
    text = text.replace("(predicted)", "").strip()
    conf: dict[tuple[int, int], int] = {}
    core = re.match(r"\[([A-Z][a-z]?)\]", text)
    if core:
        sym = core.group(1)
        conf.update(parse_config(by_symbol[sym], by_symbol))
        text = text[core.end():]
    for n, orb, q in _TOKEN.findall(text):
        key = (int(n), ORBITALS.index(orb))
        conf[key] = conf.get(key, 0) + int(q)
    return conf


@dataclass
class Element:
    z: int
    symbol: str
    name: str
    mass: float
    config: dict[tuple[int, int], int]   # (n, l) -> occupancy, REAL
    electronegativity: float | None
    radius_pm: float | None
    ionization_ev: float | None
    group_block: str
    year: int | None
    placement: Placement = field(init=False)

    def __post_init__(self):
        self.placement = madelung_layout()[self.z]

    @property
    def electrons(self) -> int:
        return sum(self.config.values())

    @property
    def is_anomalous(self) -> bool:
        """True when the real configuration differs from what the idealised
        Madelung order predicts for this atomic number."""
        return self.config != ideal_config(self.z)


@lru_cache(maxsize=256)
def ideal_config(z: int) -> dict[tuple[int, int], int]:
    """What strict aufbau filling predicts — no anomalies."""
    conf: dict[tuple[int, int], int] = {}
    left = z
    for block in madelung_groups():
        for (n, l, cap) in block:
            if left <= 0:
                return conf
            take = min(cap, left)
            conf[(n, l)] = take
            left -= take
    return conf


def _num(v):
    try:
        f = float(v)
        return f if f == f else None       # NaN check
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def load_elements(path: str | None = None) -> list[Element]:
    df = pd.read_csv(Path(path) if path else CSV)
    by_symbol = dict(zip(df.Symbol, df.ElectronConfiguration))
    out = []
    for r in df.itertuples(index=False):
        out.append(Element(
            z=int(r.AtomicNumber), symbol=str(r.Symbol), name=str(r.Name),
            mass=_num(r.AtomicMass) or 0.0,
            config=parse_config(str(r.ElectronConfiguration), by_symbol),
            electronegativity=_num(r.Electronegativity),
            radius_pm=_num(r.AtomicRadius),
            ionization_ev=_num(r.IonizationEnergy),
            group_block=str(r.GroupBlock),
            year=int(_num(r.YearDiscovered) or 0) or None))
    return out


# ---------------------------------------------------------------------------
# 3. HUND'S RULE
# ---------------------------------------------------------------------------
def hund_fill(l: int, q: int) -> list[tuple[int, int]]:
    """Distribute q electrons over a subshell's 2l+1 orbitals.

    Hund's first rule: every orbital takes one electron of parallel spin
    before any orbital takes a second. Returns (orbital_index, spin) pairs
    with spin 0 = up, 1 = down — so a half-filled subshell is all spin 0,
    which is why it shows up in the scene as a single hemisphere.
    """
    m = 2 * l + 1
    return [(i % m, i // m) for i in range(min(q, 2 * m))]


def unpaired_electrons(conf: dict[tuple[int, int], int]) -> int:
    """Count of unpaired electrons — the thing that makes an atom magnetic."""
    total = 0
    for (_n, l), q in conf.items():
        m = 2 * l + 1
        total += q if q <= m else 2 * m - q
    return total


def shell_population(conf: dict[tuple[int, int], int]) -> dict[int, int]:
    """Electrons per principal shell n — the old K, L, M, N counts."""
    out: dict[int, int] = {}
    for (n, _l), q in conf.items():
        out[n] = out.get(n, 0) + q
    return out
