#!/usr/bin/env python3
"""
decay.py — nuclide table, decay-chain DAG construction, and Bateman activities.

Data: IAEA Nuclear Data Services "ground_states" export (NUBASE/ENSDF-derived),
vendored in data/iaea_ground_states.csv.  Nothing here needs the network.

The three things this module provides:

  NuclideTable   half-life, decay modes and branching ratios for 3386 ground
                 states, keyed by (Z, N).

  build_chain()  walks the decay modes recursively from a progenitor and
                 returns the chain as a DAG.  It is a DAG rather than a list
                 because real chains fork: Bi-212 goes beta-minus 64% of the
                 time and alpha the other 36%, and the two branches rejoin at
                 Pb-208.  Mass number never rises, so the graph is acyclic.

  activities()   solves the Bateman equations on that DAG by enumerating every
                 root->node path and summing the path contributions, each
                 weighted by the product of its branching ratios.  Exact for an
                 acyclic graph.

Why Decimal and not floats: decay constants in one chain span 25 orders of
magnitude (Po-214 at 4.2e3 /s, U-238 at 4.9e-18 /s).  The Bateman sum is an
alternating series whose individual terms are astronomically larger than their
total, so in float64 it is pure cancellation noise.  120 decimal digits makes
it exact for the chain lengths we care about, with no extra dependency.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from pathlib import Path

import pandas as pd

getcontext().prec = 120


def _D(x) -> Decimal:
    """Decimal from any float-like.  numpy 2.x repr()s a float64 as
    "np.float64(1.0)", which Decimal cannot parse, so coerce first."""
    return Decimal(repr(float(x)))

HERE = Path(__file__).resolve().parent

# Change in (Z, N) for each decay mode string the IAEA export uses.
# None = the mode destroys the nucleus (fission) or leaves it unchanged, so the
# chain stops there.
MODE_DELTA: dict[str, tuple[int, int] | None] = {
    "A":     (-2, -2),
    "B-":    (+1, -1),
    "B+":    (-1, +1),
    "EC":    (-1, +1),
    "EC+B+": (-1, +1),
    "2B-":   (+2, -2),
    "2B+":   (-2, +2),
    "2EC":   (-2, +2),
    "P":     (-1, 0),
    "2P":    (-2, 0),
    "N":     (0, -1),
    "2N":    (0, -2),
    "3N":    (0, -3),
    "4N":    (0, -4),
    "B-N":   (+1, -2),
    "B-2N":  (+1, -3),
    "B-3N":  (+1, -4),
    "B-A":   (-1, -3),
    "B-P":   (0, -1),
    "ECP":   (-2, +1),
    "B+P":   (-2, +1),
    "ECA":   (-3, -1),
    "B+A":   (-3, -1),
    "EC2P":  (-3, +1),
    "14C":   (-6, -8),
    "12C":   (-6, -6),
    "20O":   (-8, -12),
    "24NE":  (-10, -14),
    "28MG":  (-12, -16),
    "SF":    None,
    "ECSF":  None,
    "IT":    None,
}

ELEMENTS = (
    "n H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co "
    "Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te "
    "I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir "
    "Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No "
    "Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og"
).split()


@dataclass(frozen=True)
class Nuclide:
    z: int
    n: int
    symbol: str
    half_life_s: float | None          # None = stable
    stable: bool
    abundance: float                   # natural abundance %, 0 if none
    modes: tuple[tuple[str, float], ...]   # (mode, branching fraction 0-1)
    q_alpha: float
    q_beta: float

    @property
    def a(self) -> int:
        return self.z + self.n

    @property
    def name(self) -> str:
        return f"{self.symbol}-{self.a}"

    @property
    def lam(self) -> float:
        """Decay constant, 1/s.  0 for stable."""
        if self.stable or not self.half_life_s:
            return 0.0
        return math.log(2.0) / self.half_life_s


class NuclideTable:
    def __init__(self, csv_path: Path | None = None):
        path = csv_path or (HERE / "data" / "iaea_ground_states.csv")
        df = pd.read_csv(path, low_memory=False)
        self._by_zn: dict[tuple[int, int], Nuclide] = {}
        self._by_name: dict[str, Nuclide] = {}

        def num(v, default=0.0):
            return float(v) if v == v and v is not None else default

        for r in df.to_dict("records"):
            try:
                z, n = int(r["z"]), int(r["n"])
            except (TypeError, ValueError):
                continue
            stable = str(r.get("half_life", "")).strip().upper() == "STABLE"
            hl_raw = r.get("half_life_sec")
            hl = float(hl_raw) if hl_raw == hl_raw and hl_raw is not None \
                else None
            modes: list[tuple[str, float]] = []
            for k in (1, 2, 3):
                m, pct = r.get(f"decay_{k}"), r.get(f"decay_{k}_%")
                if isinstance(m, str) and m.strip() and pct == pct \
                        and pct is not None:
                    modes.append((m.strip().upper(), float(pct) / 100.0))
            # Each mode's percentage is rounded independently in the evaluated
            # data, so the published set does not always close: Bi-214 sums to
            # 100.003%, Tl-210 to 100.007%.  Renormalise so branching is a
            # genuine probability distribution -- otherwise the Bateman
            # solution quietly creates or destroys atoms at the 1e-5 level.
            tot = sum(f for _m, f in modes)
            if tot > 0 and abs(tot - 1.0) > 1e-12:
                modes = [(m, f / tot) for m, f in modes]
            sym = str(r.get("symbol", "")).strip()
            if not sym or sym.lower() == "nan":
                sym = ELEMENTS[z] if z < len(ELEMENTS) else f"Z{z}"
            nuc = Nuclide(
                z=z, n=n, symbol=sym, half_life_s=hl, stable=stable,
                abundance=num(r.get("abundance")), modes=tuple(modes),
                q_alpha=num(r.get("qa")), q_beta=num(r.get("qbm")),
            )
            self._by_zn[(z, n)] = nuc
            self._by_name[f"{sym.lower()}{z + n}"] = nuc

    def get(self, z: int, n: int) -> Nuclide | None:
        return self._by_zn.get((z, n))

    def by_name(self, name: str) -> Nuclide | None:
        """'U-238' / 'U238' / 'Pb-208' -> Nuclide."""
        return self._by_name.get(name.replace("-", "").lower())

    def __len__(self) -> int:
        return len(self._by_zn)

    def all(self):
        return self._by_zn.values()


# ---------------------------------------------------------------------------
# chain construction
# ---------------------------------------------------------------------------
@dataclass
class ChainNode:
    nuc: Nuclide
    key: tuple[int, int]
    depth: int                                   # decay steps from progenitor
    parents: list[tuple[tuple[int, int], str, float]] = field(
        default_factory=list)                    # (parent key, mode, branch)
    children: list[tuple[tuple[int, int], str, float]] = field(
        default_factory=list)                    # (child key, mode, branch)


def build_chain(table: NuclideTable, progenitor: Nuclide,
                min_branch: float = 0.005,
                max_depth: int = 40) -> dict[tuple[int, int], ChainNode]:
    """Walk decay modes from `progenitor` down to stability.

    min_branch drops negligible side channels — at the 0.5% default this keeps
    Bi-212's genuine 64/36 fork and discards U-238's 5e-5% spontaneous-fission
    branch, which would otherwise hang a dead stub off the trunk.
    """
    root_key = (progenitor.z, progenitor.n)
    nodes: dict[tuple[int, int], ChainNode] = {
        root_key: ChainNode(progenitor, root_key, 0)}
    queue = [root_key]
    while queue:
        key = queue.pop(0)
        node = nodes[key]
        if node.depth >= max_depth or node.nuc.stable:
            continue
        for mode, frac in node.nuc.modes:
            if frac < min_branch:
                continue
            delta = MODE_DELTA.get(mode)
            if delta is None:
                continue
            dz, dn = delta
            child = table.get(node.nuc.z + dz, node.nuc.n + dn)
            if child is None:
                continue
            ckey = (child.z, child.n)
            if ckey == key:
                continue
            if ckey not in nodes:
                nodes[ckey] = ChainNode(child, ckey, node.depth + 1)
                queue.append(ckey)
            else:
                nodes[ckey].depth = max(nodes[ckey].depth, node.depth + 1)
            node.children.append((ckey, mode, frac))
            nodes[ckey].parents.append((key, mode, frac))
    return nodes


def paths_to(nodes: dict[tuple[int, int], ChainNode], root: tuple[int, int],
             target: tuple[int, int]) -> list[list[tuple[int, int]]]:
    """Every distinct root->target path through the DAG (with its branchings)."""
    out: list[list[tuple[int, int]]] = []

    def walk(key, acc):
        if key == target:
            out.append(list(acc))
            return
        for ckey, _mode, _frac in nodes[key].children:
            if ckey in acc:
                continue
            acc.append(ckey)
            walk(ckey, acc)
            acc.pop()

    walk(root, [root])
    return out


def branch_product(nodes, path: list[tuple[int, int]]) -> float:
    p = 1.0
    for a, b in zip(path, path[1:]):
        p *= max((f for k, _m, f in nodes[a].children if k == b), default=0.0)
    return p


# ---------------------------------------------------------------------------
# Bateman
# ---------------------------------------------------------------------------
def _bateman_path(lams: list[Decimal], t: Decimal) -> Decimal:
    """sum_i exp(-l_i t) / prod_{j!=i} (l_j - l_i)   for one path's constants."""
    k = len(lams)
    total = Decimal(0)
    for i in range(k):
        denom = Decimal(1)
        ok = True
        for j in range(k):
            if j == i:
                continue
            d = lams[j] - lams[i]
            if d == 0:
                ok = False
                break
            denom *= d
        if not ok:
            continue
        arg = -lams[i] * t
        if arg < Decimal(-800):
            ex = Decimal(0)
        else:
            ex = arg.exp()
        total += ex / denom
    return total


def _dedupe(lams: list[Decimal]) -> list[Decimal]:
    """Nudge exactly-equal decay constants apart (Bateman is singular there)."""
    out: list[Decimal] = []
    for v in lams:
        while any(v == w for w in out):
            v = v * (Decimal(1) + Decimal("1e-30")) + Decimal("1e-300")
        out.append(v)
    return out


def activities(nodes: dict[tuple[int, int], ChainNode],
               root: tuple[int, int],
               times_s: list[float]) -> dict[tuple[int, int], list[float]]:
    """Activity of every chain member vs time, per unit initial parent activity.

    Starts from a pure sample of the progenitor.  Returned values are
    A_j(t) / A_root(0), so secular equilibrium reads as 1.0 and the classic
    ingrowth curves are directly comparable between chains.  Stable end
    members have zero activity by definition and are reported as their
    accumulated atom fraction instead (see `stable_fraction`).
    """
    root_lam = nodes[root].nuc.lam
    out: dict[tuple[int, int], list[float]] = {}
    for key, node in nodes.items():
        lam_j = _D(node.nuc.lam)
        series: list[float] = []
        all_paths = paths_to(nodes, root, key)
        for t_f in times_s:
            t = _D(t_f)
            n_atoms = Decimal(0)
            for path in all_paths:
                lams = _dedupe([_D(nodes[k].nuc.lam) for k in path])
                bp = _D(branch_product(nodes, path))
                if bp == 0:
                    continue
                prod_lam = Decimal(1)
                for lm in lams[:-1]:
                    prod_lam *= lm
                n_atoms += bp * prod_lam * _bateman_path(lams, t)
            # N_root(0) = 1 atom; A_root(0) = lam_root.  Normalise activity.
            act = lam_j * n_atoms
            if root_lam > 0:
                act = act / _D(root_lam)
            series.append(float(act))
        out[key] = series
    return out


def stable_fraction(nodes, root, times_s) -> dict[tuple[int, int], list[float]]:
    """Accumulated atom fraction for stable members (activity is zero there)."""
    out = {}
    for key, node in nodes.items():
        if not node.nuc.stable:
            continue
        series = []
        all_paths = paths_to(nodes, root, key)
        for t_f in times_s:
            t = _D(t_f)
            n_atoms = Decimal(0)
            for path in all_paths:
                lams = _dedupe([_D(nodes[k].nuc.lam) for k in path])
                bp = _D(branch_product(nodes, path))
                if bp == 0:
                    continue
                prod_lam = Decimal(1)
                for lm in lams[:-1]:
                    prod_lam *= lm
                n_atoms += bp * prod_lam * _bateman_path(lams, t)
            series.append(float(n_atoms))
        out[key] = series
    return out
