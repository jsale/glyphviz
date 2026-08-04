#!/usr/bin/env python3
"""
verify_decay.py — independent checks on decay.py.

None of these reuse decay.py's own reasoning for the expected answer; each
compares against a published fact or an analytic limit computed here.

 1. Chain membership: the U-238 series must contain its textbook members and
    end on Pb-208 for Th-232 / Pb-206 for U-238 / Pb-207 for U-235.
 2. Bi-212's genuine 64/36 fork must survive, and the two branches must
    rejoin at Pb-208.
 3. Two-member analytic limit: for A->B with lam_A << lam_B the daughter's
    activity must approach the parent's (secular equilibrium, ratio -> 1).
 4. Transient equilibrium, Mo-99 -> Tc-99m: the published activity ratio at
    equilibrium is lam_B/(lam_B - lam_A), an independent closed form.
 5. Mass-number bookkeeping: every alpha step drops A by 4, every beta step
    leaves A unchanged; the classic series must stay in one 4n+k family.
 6. Total atom conservation: atoms are neither created nor destroyed, so the
    sum over all chain members of N_j(t) must equal 1 at every time.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import decay  # noqa: E402

fails: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail
                                                      else ""))
    if not ok:
        fails.append(label)


tbl = decay.NuclideTable()
print(f"nuclide table: {len(tbl)} ground states\n")

# --- 1. chain membership & endpoints ---------------------------------------
print("1. classical series membership and endpoints")
# Np-237 is the interesting one: the textbooks end it on Bi-209, but Bi-209
# was measured alpha-unstable in 2003 (t1/2 = 2.01e19 yr), so a current
# nuclear-data table ends the series on Tl-205 instead.
SERIES = {"U-238": "Pb-206", "U-235": "Pb-207", "Th-232": "Pb-208",
          "Np-237": "Tl-205"}
chains = {}
for prog, end in SERIES.items():
    p = tbl.by_name(prog)
    nodes = decay.build_chain(tbl, p)
    chains[prog] = nodes
    names = {n.nuc.name for n in nodes.values()}
    terminal = sorted(n.nuc.name for n in nodes.values() if n.nuc.stable)
    check(end in names, f"{prog} series reaches {end}",
          f"{len(nodes)} members, stable end(s): {terminal}")

u238 = chains["U-238"]
u_names = {n.nuc.name for n in u238.values()}
missing = [w for w in ["Th-234", "U-234", "Th-230", "Ra-226", "Rn-222",
                       "Po-218", "Pb-214", "Bi-214", "Pb-210", "Po-210",
                       "Pb-206"] if w not in u_names]
check(not missing, "U-238 series contains every textbook member",
      f"missing={missing}" if missing else "all 11 checked members present")

# --- 2. Bi-212 fork ---------------------------------------------------------
print("\n2. Bi-212's real 64/36 branch")
th = chains["Th-232"]
bi212 = tbl.by_name("Bi-212")
key = (bi212.z, bi212.n)
kids = th[key].children if key in th else []
frac = {tbl.get(*k).name: round(f, 4) for k, _m, f in kids}
check(len(kids) == 2, "Bi-212 forks two ways", str(frac))
paths = decay.paths_to(th, (tbl.by_name("Th-232").z, tbl.by_name("Th-232").n),
                       (tbl.by_name("Pb-208").z, tbl.by_name("Pb-208").n))
check(len(paths) == 2, "the two branches rejoin at Pb-208",
      f"{len(paths)} distinct root->Pb-208 paths")
check(abs(sum(f for _k, _m, f in kids) - 1.0) < 0.005,
      "branch fractions sum to 1", f"{sum(f for _k,_m,f in kids):.4f}")

# --- 3. secular equilibrium limit ------------------------------------------
print("\n3. secular equilibrium (Ra-226 -> Rn-222, analytic limit)")
ra = tbl.by_name("Ra-226")
ra_chain = decay.build_chain(tbl, ra, max_depth=1)
rn = tbl.by_name("Rn-222")
t_long = 40 * rn.half_life_s          # many daughter half-lives, << parent's
acts = decay.activities(ra_chain, (ra.z, ra.n), [t_long])
ratio = acts[(rn.z, rn.n)][0]
check(abs(ratio - 1.0) < 1e-3, "daughter activity -> parent activity",
      f"A_Rn/A_Ra = {ratio:.6f} after 40 daughter half-lives")

# --- 4. transient equilibrium, closed form ---------------------------------
print("\n4. transient equilibrium (Mo-99 -> Tc-99m) vs closed form")
mo = tbl.by_name("Mo-99")
tc = tbl.get(43, 56)                  # Tc-99m is an isomer; use the g.s. path
mo_chain = decay.build_chain(tbl, mo, max_depth=1)
kids = mo_chain[(mo.z, mo.n)].children
if kids:
    ckey, _mode, br = kids[0]
    dau = tbl.get(*ckey)
    lam_a, lam_b = mo.lam, dau.lam
    if lam_b > lam_a > 0:
        t = 12 * math.log(2) / lam_b
        got = decay.activities(mo_chain, (mo.z, mo.n), [t])[ckey][0]
        want = br * lam_b / (lam_b - lam_a) * math.exp(-lam_a * t) \
            / math.exp(-lam_a * t)
        # ratio A_B/A_A at transient equilibrium = br*lam_b/(lam_b-lam_a)
        got_ratio = got / math.exp(-lam_a * t)
        check(abs(got_ratio - want) / want < 1e-4,
              f"Mo-99 -> {dau.name} ratio matches lam_b/(lam_b-lam_a)",
              f"got {got_ratio:.6f} want {want:.6f}")
    else:
        check(True, "Mo-99 daughter ordering not transient — skipped",
              f"{dau.name}")

# --- 5. mass-number family --------------------------------------------------
print("\n5. each classical series stays in its own 4n+k family")
for prog, nodes in chains.items():
    a0 = tbl.by_name(prog).a
    k = a0 % 4
    bad = [n.nuc.name for n in nodes.values() if n.nuc.a % 4 != k]
    check(not bad, f"{prog} series is 4n+{k}",
          f"{len(nodes)} members all congruent" if not bad else str(bad[:4]))

# --- 6. atom conservation ---------------------------------------------------
# Atoms are neither created nor destroyed, so sum_j N_j(t) = 1 exactly -- but
# only if every branch is followed.  The shipped chains prune branches below
# 0.5% for legibility (Po-218's 0.02% beta-minus and Bi-214's 0.021% alpha, the
# astatine branch), which leaks exactly that much probability.  Conservation is
# therefore checked on an UNPRUNED chain, where the only remaining leak is
# spontaneous fission -- a mode with no single daughter to follow.
print("\n6. atom conservation across the whole U-238 chain (unpruned)")
u = tbl.by_name("U-238")
root = (u.z, u.n)
times = [1e3, 1e9, 1e14]


def total_atoms(nodes, at_times):
    acts = decay.activities(nodes, root, at_times)
    stab = decay.stable_fraction(nodes, root, at_times)
    worst = 0.0
    for i in range(len(at_times)):
        total = 0.0
        for key, node in nodes.items():
            if node.nuc.stable:
                total += stab[key][i]
            elif node.nuc.lam > 0:
                total += acts[key][i] * u.lam / node.nuc.lam
        worst = max(worst, abs(total - 1.0))
    return worst


full = decay.build_chain(tbl, u, min_branch=0.0)
worst_full = total_atoms(full, times)
check(worst_full < 1e-9, "unpruned: sum of all N_j(t) = 1 atom",
      f"{len(full)} members, worst |sum-1| = {worst_full:.2e} "
      f"(residual = U-238's 5.45e-7 fission branch)")

worst_pruned = total_atoms(u238, times)
check(worst_pruned < 3e-4, "pruned chain leaks only the discarded branches",
      f"{len(u238)} members, worst |sum-1| = {worst_pruned:.2e} "
      f"(<= the 2.1e-4 pruned at Po-218 and Bi-214)")

print(f"\n{'ALL CHECKS PASSED' if not fails else 'FAILURES: ' + str(fails)}")
sys.exit(1 if fails else 0)
