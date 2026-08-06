#!/usr/bin/env python3
"""
verify_astro.py — check the astronomy before anything is drawn.

Nothing here touches GlyphViz.  These are the checks that a coordinate
pipeline is right, and most of them are the kind that fail loudly when a sign
is flipped or a pole is off by a degree — which is exactly the class of bug
that otherwise ships as a picture nobody can tell is wrong.

    python verify_astro.py
"""
from __future__ import annotations

import sys

import numpy as np

import skymap as S

FAILS: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILS.append(label)


def main() -> int:
    print("== frames ==")
    B = S.SG_BASIS
    check(float(np.abs(B @ B.T - np.eye(3)).max()) < 1e-12,
          "supergalactic basis is orthonormal",
          f"max |BB^T - I| = {float(np.abs(B @ B.T - np.eye(3)).max()):.1e}")
    check(abs(float(np.linalg.det(B)) - 1.0) < 1e-12,
          "...and right-handed", f"det = {float(np.linalg.det(B)):.9f}")

    # The 2MRS rows carry galactic coordinates computed by someone else from
    # the same RA/Dec, which makes them an independent test of the equatorial
    # -> galactic rotation this module builds from published pole directions.
    cat = S.load()
    df = cat.df
    glon, glat = S.equatorial_to_galactic(df.ra.to_numpy(), df.dec.to_numpy())
    dlat = np.abs(glat - df.glat.to_numpy())
    dlon = np.abs((glon - df.glon.to_numpy() + 180.0) % 360.0 - 180.0)
    sep = np.degrees(np.arccos(np.clip(np.einsum(
        "ij,ij->i",
        S.unit_vectors(glon, glat),
        S.unit_vectors(df.glon.to_numpy(), df.glat.to_numpy())), -1, 1)))
    check(float(sep.max()) < 0.01,
          "equatorial->galactic reproduces the catalogue's own l,b "
          f"for all {len(df):,} rows",
          f"worst separation {float(sep.max()) * 3600:.2f} arcsec")
    del dlat, dlon

    print("\n== the moving observer ==")
    dv = df.v_cmb.to_numpy() - df.cz.to_numpy()
    check(abs(float(dv.max()) - S.CMB_APEX_V) < 0.5
          and abs(float(dv.min()) + S.CMB_APEX_V) < 0.5,
          "CMB correction spans exactly +/- the dipole amplitude",
          f"{float(dv.min()):.1f} .. {float(dv.max()):.1f} km/s")
    apex = S.unit_vectors(S.CMB_APEX_L, S.CMB_APEX_B)
    n = S.unit_vectors(df.glon.to_numpy(), df.glat.to_numpy())
    towards = n @ apex
    check(float(np.corrcoef(towards, dv)[0, 1]) > 0.9999,
          "...and is largest toward the apex, smallest away from it")

    print("\n== the local universe is flat ==")
    # De Vaucouleurs' whole point: local structure lies in the SGX-SGY plane.
    # If the frame were wrong this number would sit at the isotropic value.
    for r in (40.0, 60.0, 120.0):
        sel = df.dist < r
        sgb = np.degrees(np.arcsin(df.sgz[sel] / df.dist[sel]))
        med = float(np.abs(sgb).median())
        # A uniform sphere gives median |latitude| = 30 degrees exactly.
        check(med < 27.0,
              f"galaxies inside {r:.0f} Mpc concentrate toward SGB = 0",
              f"median |SGB| = {med:.1f} deg vs 30.0 if isotropic "
              f"(n = {int(sel.sum()):,})")

    print("\n== the named structures are really there ==")
    from scipy.spatial import cKDTree
    tree = cKDTree(cat.xyz)
    r_ball = 5.0
    # Expected count for a uniform sample at the landmark's own distance,
    # using the shell density there rather than the global mean: the survey
    # thins with distance, so a global mean would flatter distant landmarks.
    for lm in S.LANDMARKS:
        p = S.landmark_xyz(lm)
        d = float(np.linalg.norm(p))
        shell = df[(df.dist > d * 0.85) & (df.dist < d * 1.15)]
        v_shell = (4.0 / 3.0) * np.pi * ((d * 1.15) ** 3 - (d * 0.85) ** 3)
        expected = len(shell) / v_shell * (4.0 / 3.0) * np.pi * r_ball ** 3
        got = len(tree.query_ball_point(p, r_ball))
        check(got > 6.0 * expected,
              f"{lm.name} sits on an overdensity",
              f"{got} galaxies within {r_ball:.0f} Mpc, "
              f"{expected:.1f} expected -> x{got / max(expected, 1e-9):.0f}")

    print("\n== percolation finds the clusters ==")
    import build_cosmic_scenes as B2
    vl = cat.volume_limited(B2.VL_DEPTH).reset_index(drop=True)
    _gid, groups, mean_sep = B2.find_groups(vl)
    check(len(vl) > 10_000, "volume-limited subsample is usable",
          f"{len(vl):,} galaxies brighter than "
          f"M_K = {vl.attrs['m_lim']:.2f} inside {B2.VL_DEPTH:.0f} Mpc")
    top4 = {g.name for g in groups[:4]}
    check(top4 == {"Perseus Cluster", "Coma Cluster", "Norma Cluster",
                   "Centaurus Cluster"},
          "the four richest groups are Perseus, Coma, Norma and Centaurus",
          ", ".join(f"{g.name or '(unnamed)'} ({len(g.members)})"
                    for g in groups[:4]))
    inside = [lm for lm in S.LANDMARKS
              if float(np.linalg.norm(S.landmark_xyz(lm))) <= B2.VL_DEPTH]
    named = {g.name for g in groups if g.name}
    check(named == {lm.name for lm in inside},
          "every landmark inside the volume claimed exactly one group",
          f"{len(named)} of {len(inside)}")
    biggest = max(len(g.members) for g in groups)
    check(biggest < len(vl) * 0.05,
          "percolation has not run away into one super-group",
          f"largest group holds {biggest} of {len(vl):,} galaxies "
          f"({100 * biggest / len(vl):.1f}%), mean separation "
          f"{mean_sep:.2f} Mpc")

    print("\n== fingers of God point at us ==")
    # The signature artefact of redshift-space distance: cluster members
    # smear along the line of sight, so a rich group is elongated radially
    # and hardly at all across.  If the coordinate pipeline were scrambled,
    # this asymmetry would vanish.
    xyz = vl[["sgx", "sgy", "sgz"]].to_numpy()
    ratios = []
    for g in groups[:40]:
        pts = xyz[g.members]
        c = pts.mean(axis=0)
        los = c / np.linalg.norm(c)
        rel = pts - c
        par = rel @ los
        perp = np.sqrt(np.maximum((rel * rel).sum(axis=1) - par ** 2, 0.0))
        ratios.append(float(par.std() / max(perp.std(), 1e-9)))
    med = float(np.median(ratios))
    check(med > 1.3,
          "the 40 richest groups are stretched along the line of sight",
          f"median radial/transverse spread = {med:.2f}")

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: " + "; ".join(FAILS))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
