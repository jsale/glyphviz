"""
The superstring landscape's two public datasets: fetch, parse, check.

  * Kreuzer-Skarke (2000): every Calabi-Yau threefold that is a hypersurface
    in a toric variety built from one of the 473,800,776 reflexive
    4-polytopes. Between them they have 30,108 distinct Hodge-number pairs
    (h11, h21); the file lists each pair once with chi = 2 (h11 - h21).
    http://hep.itp.tuwien.ac.at/~kreuzer/CY/CYcy.html  (alltoric.spec.gz)
  * The CICY list (Candelas, Dale, Lutken, Schimmrigk 1988; Hodge numbers by
    Green, Hubsch, Lutken 1989): the 7,890 Complete Intersection Calabi-Yau
    threefolds in products of projective spaces, with configuration matrices.
    https://www-thphys.physics.ox.ac.uk/projects/CalabiYau/cicylist/

    python landscape_data.py           # fetch (if missing) and check
    python landscape_data.py --fetch   # fetch again

The files land in data/ (gitignored), named by this script, never by the
server: alltoric.spec.gz (109 kB) and cicylist.txt (2.3 MB).
"""
import argparse
import gzip
import re
import urllib.request
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
SOURCES = {
    "alltoric.spec.gz": "http://hep.itp.tuwien.ac.at/~kreuzer/pub/misc/alltoric.spec.gz",
    "cicylist.txt": "https://www-thphys.physics.ox.ac.uk/projects/CalabiYau/cicylist/cicylist.txt",
}


def fetch(force=False):
    DATA.mkdir(exist_ok=True)
    for name, url in SOURCES.items():
        out = DATA / name
        if out.exists() and not force:
            continue
        tmp = out.with_suffix(out.suffix + ".part")
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as fh:
            fh.write(r.read())
        tmp.replace(out)
        print(f"fetched {name} ({out.stat().st_size:,} bytes) from {url}")


def kreuzer_skarke():
    """(30108, 3) int array of (h11, h21, chi), one row per distinct pair."""
    rows = []
    with gzip.open(DATA / "alltoric.spec.gz", "rt") as fh:
        for line in fh:
            if line.strip() and not line.startswith("#"):
                rows.append([int(v) for v in line.split()])
    return np.array(rows, dtype=np.int64)


def cicy():
    """The CICY list as a dict of arrays: num, n_ps (projective factors),
    n_pol (equations), h11, h21, chi, and dims (each factor's P^n, from the
    configuration matrix: a row of degrees sums to n + 1 on a Calabi-Yau).
    The 22 product manifolds (block-diagonal: a torus x K3 and the like) are
    listed with h11 = h21 = 0 as placeholders; `product` flags them."""
    text = (DATA / "cicylist.txt").read_text()
    out = {k: [] for k in ("num", "n_ps", "n_pol", "h11", "h21", "chi", "dims", "product")}
    for block in text.split("\n\n"):
        if not block.strip().startswith("Num"):
            continue
        d = dict(re.findall(r"^(\w+)\s*:\s*(.*)$", block, re.M))
        # The matrix rows are the lines after "Redun", one per factor.
        lines = block.splitlines()
        start = next(i for i, ln in enumerate(lines) if ln.startswith("Redun")) + 1
        rows = [list(map(int, re.findall(r"-?\d+", ln))) for ln in lines[start:] if ln.startswith("{")]
        n_ps, n_pol = int(d["NumPs"]), int(d["NumPol"])
        assert len(rows) == n_ps and all(len(r) == n_pol for r in rows), d["Num"]
        dims = [sum(r) - 1 for r in rows]
        out["num"].append(int(d["Num"]))
        out["n_ps"].append(n_ps)
        out["n_pol"].append(n_pol)
        out["h11"].append(int(d["H11"]))
        out["h21"].append(int(d["H21"]))
        out["chi"].append(int(d["Eta"]))
        out["dims"].append(dims)
        out["product"].append(int(d["H11"]) == 0)
    return {k: (v if k == "dims" else np.array(v)) for k, v in out.items()}


def check():
    ks = kreuzer_skarke()
    assert ks.shape == (30108, 3)
    assert np.all(ks[:, 2] == 2 * (ks[:, 0] - ks[:, 1]))
    pairs = {(int(a), int(b)) for a, b, _ in ks}
    assert len(pairs) == 30108
    assert all((b, a) in pairs for a, b in pairs), "the list is not its own mirror"
    assert ks[:, 0].max() == ks[:, 1].max() == 491
    assert abs(ks[:, 2]).max() == 960

    c = cicy()
    assert len(c["num"]) == 7890 and c["num"].tolist() == list(range(1, 7891))
    # Every configuration is a threefold: sum of the P^n dimensions minus
    # the number of equations is 3.
    assert all(sum(d) - n == 3 for d, n in zip(c["dims"], c["n_pol"]))
    # The list's "Eta" column is the Euler number chi = 2 (h11 - h21).
    real = ~c["product"]
    assert np.all(c["chi"][real] == 2 * (c["h11"][real] - c["h21"][real]))
    assert c["product"].sum() == 22 and np.all(c["chi"][c["product"]] == 0)
    assert c["chi"].max() == 0 and c["chi"].min() == -200
    # The Tian-Yau parent: (14, 23), chi = -18, divided by a free Z3 -> (6, 9), chi = -6.
    assert ((c["h11"] == 14) & (c["h21"] == 23)).sum() == 1
    return ks, c


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="download again")
    args = ap.parse_args()
    fetch(force=args.fetch)
    ks, c = check()
    real = ~c["product"]
    cp = {(int(a), int(b)) for a, b in zip(c["h11"][real], c["h21"][real])}
    print(f"Kreuzer-Skarke: {len(ks):,} Hodge pairs, mirror-closed; "
          f"|chi| = 6 (three generations): {(abs(ks[:, 2]) == 6).sum()} pairs")
    print(f"CICY: {len(c['num']):,} manifolds ({c['product'].sum()} products), "
          f"{len(cp)} distinct pairs, {sum(p in {(int(a), int(b)) for a, b, _ in ks} for p in cp)} "
          "of them also Kreuzer-Skarke pairs")
