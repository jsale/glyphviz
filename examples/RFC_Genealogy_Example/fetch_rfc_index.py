#!/usr/bin/env python3
"""
fetch_rfc_index.py — download the RFC Editor's index and distil it.

The whole RFC series is published as one XML file, `rfc-index.xml`, about
14 MB.  Everything this example needs is a small fraction of it: number,
title, date, current status, stream, page count, and the four cross-reference
lists (obsoletes / obsoleted-by / updates / updated-by).  This script pulls
the XML, extracts those fields, and writes a 0.6 MB gzipped CSV into `data/`,
which is what ships in the repo and what every other script here reads.

    python fetch_rfc_index.py            # refresh data/rfc_index.csv.gz
    python fetch_rfc_index.py --keep-xml # also leave the raw XML behind

Source: https://www.rfc-editor.org/rfc-index.xml  (RFC Editor, public domain
under the IETF Trust's licence for RFC metadata).

Network note: this uses `curl` rather than `urllib`, matching
`Wind_Rose_Example/fetch_wind.py`.  urllib has stalled indefinitely against
some of these hosts while ignoring its own timeout.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
URL = "https://www.rfc-editor.org/rfc-index.xml"
NS = "{https://www.rfc-editor.org/rfc-index}"

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}


def download(dest: Path) -> None:
    print(f"downloading {URL} ...")
    subprocess.run(["curl", "-sSf", "--max-time", "300", "-o", str(dest), URL],
                   check=True)
    print(f"  {dest.stat().st_size / 1e6:.1f} MB")


def _refs(entry: ET.Element, tag: str) -> str:
    """Space-separated RFC numbers from a cross-reference list."""
    out = []
    for d in entry.findall(f"{NS}{tag}/{NS}doc-id"):
        text = (d.text or "").strip()
        if text.startswith("RFC") and text[3:].isdigit():
            out.append(str(int(text[3:])))
    return " ".join(out)


def distil(xml_path: Path) -> pd.DataFrame:
    root = ET.parse(xml_path).getroot()
    rows = []
    for e in root:
        if e.tag != f"{NS}rfc-entry":
            continue
        doc = (e.findtext(f"{NS}doc-id") or "").strip()
        if not doc.startswith("RFC") or not doc[3:].isdigit():
            continue
        date = e.find(f"{NS}date")
        month = (date.findtext(f"{NS}month") or "").strip() if date is not None else ""
        pages = (e.findtext(f"{NS}page-count") or "").strip()
        rows.append(dict(
            num=int(doc[3:]),
            title=" ".join((e.findtext(f"{NS}title") or "").split()),
            year=int(date.findtext(f"{NS}year")) if date is not None else 0,
            month=MONTHS.get(month, 0),
            status=(e.findtext(f"{NS}current-status") or "UNKNOWN").strip(),
            stream=(e.findtext(f"{NS}stream") or "").strip(),
            pages=int(pages) if pages.isdigit() else 0,
            area=(e.findtext(f"{NS}area") or "").strip(),
            wg=(e.findtext(f"{NS}wg_acronym") or "").strip(),
            obsoletes=_refs(e, "obsoletes"),
            obsoleted_by=_refs(e, "obsoleted-by"),
            updates=_refs(e, "updates"),
            updated_by=_refs(e, "updated-by"),
        ))
    df = pd.DataFrame(rows).sort_values("num").reset_index(drop=True)
    print(f"  {len(df):,} RFCs, {df.year.min()}-{df.year.max()}")
    return df


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-xml", action="store_true")
    args = ap.parse_args()

    DATA.mkdir(exist_ok=True)
    xml_path = DATA / "rfc-index.xml"
    download(xml_path)
    df = distil(xml_path)
    out = DATA / "rfc_index.csv.gz"
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"wrote {out}  ({out.stat().st_size / 1e6:.2f} MB)")
    if not args.keep_xml:
        xml_path.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
