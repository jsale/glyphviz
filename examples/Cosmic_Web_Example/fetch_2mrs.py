#!/usr/bin/env python3
"""
fetch_2mrs.py — download the 2MASS Redshift Survey from VizieR.

2MRS (Huchra et al. 2012, ApJS 199, 26) is the all-sky redshift catalogue:
44,599 galaxies selected in the near infrared, 43,533 of them with a measured
recession velocity.  Near-infrared selection is the point — dust in the plane
of the Milky Way, which blanks out optical surveys in a broad "Zone of
Avoidance", is far less of an obstacle at 2.2 microns, so this is the only
survey that maps the local universe in every direction at once.

The catalogue is served by VizieR's TAP endpoint as ADQL over HTTP, no key
and no account.  This script pulls the nine columns the example needs and
writes a 1.3 MB gzipped CSV into `data/`, which is what ships in the repo.

    python fetch_2mrs.py

Source: VizieR catalogue J/ApJS/199/26, table3.  Please cite Huchra et al.
(2012) if you use the data for anything beyond looking at it.

Network note: this uses `curl` rather than `urllib`, matching
`Wind_Rose_Example/fetch_wind.py` — urllib has stalled indefinitely against
some astronomy hosts while ignoring its own timeout.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
TAP = "https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync"
ADQL = ('SELECT ID, RAJ2000, DEJ2000, GLON, GLAT, Ktmag, type, cz, CAT '
        'FROM "J/ApJS/199/26/table3"')


def main() -> int:
    DATA.mkdir(exist_ok=True)
    raw = DATA / "2mrs_raw.csv"
    print(f"querying {TAP} ...")
    subprocess.run([
        "curl", "-sSf", "--max-time", "600", "-o", str(raw), "-G", TAP,
        "--data-urlencode", "REQUEST=doQuery",
        "--data-urlencode", "LANG=ADQL",
        "--data-urlencode", "FORMAT=csv",
        "--data-urlencode", "MAXREC=100000",
        "--data-urlencode", f"QUERY={ADQL}",
    ], check=True)

    df = pd.read_csv(raw)
    print(f"  {len(df):,} rows, {df.cz.notna().sum():,} with a velocity")
    df = df.rename(columns={"RAJ2000": "ra", "DEJ2000": "dec",
                            "GLON": "glon", "GLAT": "glat",
                            "Ktmag": "k_mag", "type": "morph"})
    df = df[["ID", "ra", "dec", "glon", "glat", "k_mag", "morph", "cz"]]
    out = DATA / "2mrs.csv.gz"
    df.to_csv(out, index=False, encoding="utf-8")
    raw.unlink()
    print(f"wrote {out}  ({out.stat().st_size / 1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
