#!/usr/bin/env python3
"""
verify_elements.py — check the chemistry before any geometry depends on it.

Nothing here uses the scene builder; these are checks against textbook facts
and against PubChem's own data, so a layout bug can never hide behind a
plausible-looking picture.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import elements as E                                              # noqa: E402

fails: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail
                                                      else ""))
    if not ok:
        fails.append(label)


els = E.load_elements()
by_z = {e.z: e for e in els}

# ---------------------------------------------------------------------------
print("\n1. Configurations parsed from PubChem")
# ---------------------------------------------------------------------------
check(len(els) == 118, "118 elements loaded", f"{len(els)}")
bad = [e.z for e in els if e.electrons != e.z]
check(not bad, "every configuration's electrons sum to Z",
      f"offenders: {bad[:8]}")
over = [(e.z, n, l, q) for e in els for (n, l), q in e.config.items()
        if q > 2 * (2 * l + 1)]
check(not over, "no subshell exceeds 2(2l+1)", f"{over[:4]}")
bad_l = [(e.z, n, l) for e in els for (n, l) in e.config if l >= n]
check(not bad_l, "every subshell satisfies l <= n-1", f"{bad_l[:4]}")

# ---------------------------------------------------------------------------
print("\n2. Known configurations, spot-checked against the textbook")
# ---------------------------------------------------------------------------
KNOWN = {
    1:  {(1, 0): 1},                                             # H
    2:  {(1, 0): 2},                                             # He
    10: {(1, 0): 2, (2, 0): 2, (2, 1): 6},                       # Ne
    26: {(1, 0): 2, (2, 0): 2, (2, 1): 6, (3, 0): 2, (3, 1): 6,
         (3, 2): 6, (4, 0): 2},                                  # Fe  3d6 4s2
}
for z, want in KNOWN.items():
    check(by_z[z].config == want, f"Z={z} ({by_z[z].symbol}) configuration",
          "" if by_z[z].config == want else f"got {by_z[z].config}")

# The famous anomalies must be present as anomalies.
ANOMALIES = {24: "Cr", 29: "Cu", 41: "Nb", 42: "Mo", 44: "Ru", 45: "Rh",
             46: "Pd", 47: "Ag", 57: "La", 64: "Gd", 78: "Pt", 79: "Au"}
missed = [f"{s}({z})" for z, s in ANOMALIES.items()
          if not by_z[z].is_anomalous]
check(not missed, "textbook aufbau exceptions are flagged as anomalous",
      f"missed: {missed}" if missed else
      f"{sum(1 for e in els if e.is_anomalous)} of 118 differ from ideal")
# ...and elements that obey the rule must NOT be flagged.
obedient = [20, 25, 30, 56]          # Ca, Mn, Zn, Ba
wrong = [by_z[z].symbol for z in obedient if by_z[z].is_anomalous]
check(not wrong, "well-behaved elements are not flagged", f"{wrong}")

# ---------------------------------------------------------------------------
print("\n3. Hund's rule and magnetism")
# ---------------------------------------------------------------------------
# Unpaired-electron counts every chemistry student memorises.
UNPAIRED = {1: 1, 2: 0, 6: 2, 7: 3, 8: 2, 10: 0, 24: 6, 26: 4, 30: 0,
            64: 8}
for z, want in UNPAIRED.items():
    got = E.unpaired_electrons(by_z[z].config)
    check(got == want, f"{by_z[z].symbol} has {want} unpaired electrons",
          "" if got == want else f"got {got}")

# A half-filled subshell must be entirely spin-up (that IS Hund's rule).
half = E.hund_fill(1, 3)                       # p3, e.g. nitrogen
check([s for _o, s in half] == [0, 0, 0], "p3 fills all spin-up",
      f"{half}")
full = E.hund_fill(1, 6)
check(sorted(full) == [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1)],
      "p6 fills three orbitals with paired spins")
check(len(E.hund_fill(3, 14)) == 14 and len(E.hund_fill(2, 10)) == 10,
      "f14 and d10 place every electron")

# ---------------------------------------------------------------------------
print("\n4. The Madelung helix layout")
# ---------------------------------------------------------------------------
lay = E.madelung_layout()
check(len(lay) == 118, "every element placed", f"{len(lay)}")

turn_len = {}
for z, p in lay.items():
    turn_len.setdefault(p.turn, []).append(z)
lengths = [len(turn_len[t]) for t in sorted(turn_len)]
check(lengths == [2, 2, 8, 8, 18, 18, 32, 30],
      "turn lengths follow the 2,2,8,8,18,18,32,32 Madelung pattern",
      f"{lengths} (last turn truncated at Z=118 of 120)")

# The whole point: a group is a column, i.e. one slot across many turns.
COLUMNS = {
    30: ([1, 3, 11, 19, 37, 55, 87], "alkali metals (s1)"),
    31: ([2, 4, 12, 20, 38, 56, 88], "He + alkaline earths (s2)"),
    29: ([10, 18, 36, 54, 86, 118], "noble gases (p6)"),
    28: ([9, 17, 35, 53, 85, 117], "halogens (p5)"),
    23: ([30, 48, 80, 112], "zinc group (d10)"),
    0:  ([57, 89], "first f-block column (f1)"),
}
for slot, (want, label) in COLUMNS.items():
    got = sorted(z for z, p in lay.items() if p.slot == slot)
    check(got == want, f"slot {slot} is exactly the {label}",
          "" if got == want else f"got {got}")

# Blocks must occupy contiguous, correctly sized slot ranges.
RANGES = {"f": (0, 13), "d": (14, 23), "p": (24, 29), "s": (30, 31)}
for blk, (lo, hi) in RANGES.items():
    slots = {p.slot for p in lay.values() if p.block == blk}
    check(slots and min(slots) >= lo and max(slots) <= hi,
          f"{blk}-block occupies slots {lo}..{hi}",
          f"got {min(slots)}..{max(slots)}" if slots else "empty")

# Every COMPLETE turn must be a right-aligned suffix of the 32-slot grid.
turns = sorted(turn_len)
ragged = [t for t in turns[:-1]
          if max(lay[z].slot for z in turn_len[t]) != 31]
check(not ragged, "every complete turn ends flush at slot 31",
      f"turns {ragged}")
# The last turn is the exception, and for a real reason: the 8th Madelung
# group runs to Z=120, so the helix stops two slots short. Those two empty
# slots are 8s1 and 8s2 — elements 119 and 120, undiscovered.
last_slot = max(lay[z].slot for z in turn_len[turns[-1]])
check(last_slot == 29,
      "the final turn stops 2 slots short — 119 and 120 are not discovered",
      f"ends at slot {last_slot} (Z=118, Og, p6)")

# ---------------------------------------------------------------------------
print("\n5. Data coverage (drives the visual encodings)")
# ---------------------------------------------------------------------------
for label, attr in (("electronegativity", "electronegativity"),
                    ("atomic radius", "radius_pm"),
                    ("ionization energy", "ionization_ev")):
    have = [e for e in els if getattr(e, attr) is not None]
    missing = [e.z for e in els if getattr(e, attr) is None]
    print(f"     {label:20s} {len(have):3d}/118   missing Z: "
          f"{missing[:4]}{'...' if len(missing) > 4 else ''}")
check(all(e.radius_pm is not None for e in els if e.z <= 99),
      "atomic radius present for every element up to Z=99")

print("\n" + ("ALL CHECKS PASSED" if not fails
             else f"{len(fails)} CHECK(S) FAILED: {fails}"))
sys.exit(1 if fails else 0)
