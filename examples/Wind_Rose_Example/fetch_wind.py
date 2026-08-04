#!/usr/bin/env python3
"""
fetch_wind.py — build a compact global wind-rose climatology from NOAA ISD-Lite.

Selects a globally distributed set of long-record stations, downloads their
hourly observations, and aggregates them into one small vendored summary:
per station, per calendar month, a 16-sector x 5-speed-bin frequency table
plus calm fraction and the vector-mean (resultant) wind.

Diurnal sampling correction: stations differ in how often they report, and
some report only in daylight, which would bias a raw frequency count toward
whatever regime blows during the reporting hours.  Each observation is
therefore weighted by the inverse of how often that station-month reports in
that hour of day, so every hour of the clock carries equal weight.

Output: wind_roses.csv  (one row per station-month) + stations.csv
"""
from __future__ import annotations

import argparse
import gzip
import io
import sys
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
CACHE = DATA / "isd_cache"
BASE = "https://www.ncei.noaa.gov/pub/data/noaa/isd-lite"

YEARS = list(range(2019, 2024))            # 5 full years
N_SECTORS = 16
SECTOR_DEG = 360.0 / N_SECTORS

# Speed bins in m/s.  Below CALM_MAX is counted as calm, not given a direction.
CALM_MAX = 0.5
BIN_EDGES = [0.5, 2.0, 4.0, 6.0, 9.0, np.inf]
BIN_LABELS = ["0.5-2", "2-4", "4-6", "6-9", "9+"]
N_BINS = len(BIN_LABELS)

MIN_OBS_PER_MONTH = 150                    # across all 5 years
MIN_MONTHS = 12                            # need the full annual cycle


# ---------------------------------------------------------------------------
# station selection
# ---------------------------------------------------------------------------
def select_stations(lon_step: float, lat_step: float,
                    extra_icao: list[str]) -> pd.DataFrame:
    hist = pd.read_csv(DATA / "isd-history.csv", dtype=str)
    hist.columns = [c.strip().strip('"') for c in hist.columns]
    hist = hist.rename(columns={"STATION NAME": "NAME", "ELEV(M)": "ELEV"})
    for c in ("LAT", "LON", "ELEV"):
        hist[c] = pd.to_numeric(hist[c], errors="coerce")
    hist["BEGIN"] = pd.to_numeric(hist["BEGIN"], errors="coerce")
    hist["END"] = pd.to_numeric(hist["END"], errors="coerce")

    ok = hist.dropna(subset=["LAT", "LON", "BEGIN", "END"]).copy()
    ok = ok[(ok.LAT.abs() > 0.02) | (ok.LON.abs() > 0.02)]     # drop 0,0
    # a compass rose is meaningless within a few degrees of the pole,
    # where the local north direction depends on which meridian you pick
    ok = ok[ok.LAT.between(-85, 85) & ok.LON.between(-180, 180)]
    ok = ok[(ok.END >= 20240101) & (ok.BEGIN <= 20160101)]
    ok = ok[ok.WBAN.notna() & ok.USAF.notna()]
    ok = ok[ok.USAF != "999999"]
    ok["span"] = ok.END - ok.BEGIN

    # one station per global cell — prefer the longest record
    ok["cell"] = (np.floor(ok.LON / lon_step).astype(int).astype(str) + "_"
                  + np.floor(ok.LAT / lat_step).astype(int).astype(str))
    picked = (ok.sort_values("span", ascending=False)
                .groupby("cell", as_index=False)
                .first())

    if extra_icao:
        want = ok[ok.ICAO.isin(extra_icao)].sort_values("span",
                                                        ascending=False)
        want = want.groupby("ICAO", as_index=False).first()
        picked = pd.concat([picked, want]).drop_duplicates(
            subset=["USAF", "WBAN"])

    picked["sid"] = picked.USAF.str.zfill(6) + "-" + picked.WBAN.str.zfill(5)
    return picked.reset_index(drop=True)


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------
def fetch_batch(jobs: list[tuple[str, int]], workers: int) -> None:
    """Download every missing (sid, year) with one parallel curl invocation.

    curl rather than urllib: urllib.request stalls indefinitely against
    ncei.noaa.gov from some network environments, ignoring its own timeout.
    curl is present on Windows 10+, macOS, and every Linux we care about.
    """
    todo = [(s, y) for s, y in jobs if not (CACHE / f"{s}-{y}.gz").exists()]
    if not todo:
        return
    for start in range(0, len(todo), 400):
        chunk = todo[start:start + 400]
        cfg = CACHE / "_curl.txt"
        with cfg.open("w", encoding="utf-8") as fh:
            for sid, year in chunk:
                fh.write(f'url = "{BASE}/{year}/{sid}-{year}.gz"\n')
                fh.write(f'output = "{(CACHE / f"{sid}-{year}.gz").as_posix()}"\n')
        subprocess.run(
            ["curl", "--parallel", "--parallel-max", str(workers),
             "--silent", "--show-error", "--fail", "--max-time", "60",
             "--retry", "1", "--remove-on-error", "-K", str(cfg)],
            check=False, capture_output=True, text=True)
        print(f"  fetched {min(start + 400, len(todo))}/{len(todo)}",
              flush=True)
    cfg.unlink(missing_ok=True)


def read_cached(sid: str, year: int) -> bytes | None:
    p = CACHE / f"{sid}-{year}.gz"
    if not p.exists():
        return None
    blob = p.read_bytes()
    return blob if len(blob) > 200 else None


def parse(blob: bytes) -> pd.DataFrame | None:
    try:
        txt = gzip.decompress(blob).decode("ascii", "replace")
    except OSError:
        return None
    arr = np.genfromtxt(io.StringIO(txt), dtype=float, usecols=(1, 3, 7, 8),
                        invalid_raise=False)
    if arr.ndim != 2 or len(arr) == 0:
        return None
    df = pd.DataFrame(arr, columns=["month", "hour", "wdir", "wspd"])
    df = df[(df.wspd > -9000)]
    df["wspd"] = df.wspd / 10.0
    df = df[df.wspd.between(0.0, 75.0)]
    return df


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------
def rose_for_station(df: pd.DataFrame) -> list[dict]:
    """One row per calendar month with weighted sector/bin frequencies."""
    out: list[dict] = []
    for month, g in df.groupby("month"):
        g = g.copy()
        if len(g) < MIN_OBS_PER_MONTH:
            continue
        # diurnal weight: equalise the hours of the day
        counts = g.hour.value_counts()
        g["w"] = 1.0 / g.hour.map(counts).astype(float)
        g["w"] *= len(g) / g["w"].sum()

        # An observation only counts toward the rose if it carries direction
        # information: calm (no direction by definition) or a valid bearing.
        # Speed-without-bearing reports are excluded from the DENOMINATOR too,
        # otherwise the sector frequencies + calm would not close to 1.
        calm = g[g.wspd < CALM_MAX]
        moving = g[(g.wspd >= CALM_MAX) & g.wdir.between(0.0, 360.0)]
        all_w = float(g["w"].sum())
        total_w = float(calm["w"].sum() + moving["w"].sum())
        if total_w <= 0 or len(moving) < MIN_OBS_PER_MONTH * 0.5:
            continue

        # sector 0 is centred on north, so shift by half a sector before floor
        sec = (np.floor(((moving.wdir.values % 360.0) + SECTOR_DEG / 2.0)
                        / SECTOR_DEG).astype(int) % N_SECTORS)
        b = np.clip(np.digitize(moving.wspd.values, BIN_EDGES) - 1,
                    0, N_BINS - 1)
        w = moving["w"].values

        table = np.zeros((N_SECTORS, N_BINS))
        np.add.at(table, (sec, b), w)
        table /= total_w                                  # fraction of all obs

        # resultant (vector-mean) wind — direction the wind comes FROM
        th = np.radians(moving.wdir.values)
        u = float(np.sum(w * moving.wspd.values * np.sin(th)) / total_w)
        v = float(np.sum(w * moving.wspd.values * np.cos(th)) / total_w)
        scalar_mean = float(np.sum(w * moving.wspd.values) / total_w)
        resultant = float(np.hypot(u, v))
        rec = dict(
            month=int(month),
            n_obs=int(len(g)),
            calm_frac=round(float(calm["w"].sum() / total_w), 5),
            mean_speed=round(scalar_mean, 3),
            resultant_speed=round(resultant, 3),
            resultant_dir=round(float(np.degrees(np.arctan2(u, v)) % 360.0), 2),
            constancy=round(resultant / scalar_mean if scalar_mean > 0 else 0.0,
                            4),
            dir_missing_frac=round(1.0 - total_w / all_w if all_w > 0 else 0.0,
                                   5),
        )
        for s in range(N_SECTORS):
            for k in range(N_BINS):
                rec[f"s{s:02d}b{k}"] = round(float(table[s, k]), 6)
        out.append(rec)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lon-step", type=float, default=15.0)
    ap.add_argument("--lat-step", type=float, default=13.0)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)

    archetypes = ["TJSJ", "VABB", "VECC", "WSSS", "EINN", "NZWN", "PABR",
                  "HKJK", "KDEN", "ZMUB", "LFML", "KPMD", "FACT", "SBGL",
                  "YPPH", "RJTT", "OMDB", "SAWH", "BGTL", "GVAC"]
    st = select_stations(args.lon_step, args.lat_step, archetypes)
    if args.limit:
        st = st.head(args.limit)
    print(f"selected {len(st)} candidate stations", flush=True)

    jobs = [(row.sid, y) for row in st.itertuples() for y in YEARS]
    fetch_batch(jobs, args.workers)
    have = {s for s, y in jobs if (CACHE / f"{s}-{y}.gz").exists()}
    print(f"downloaded data for {len(have)} stations", flush=True)

    rows, keep = [], []
    for row in st.itertuples():
        blobs = [b for b in (read_cached(row.sid, y) for y in YEARS) if b]
        parts = [parse(b) for b in blobs]
        parts = [p for p in parts if p is not None and len(p)]
        if not parts:
            continue
        df = pd.concat(parts, ignore_index=True)
        recs = rose_for_station(df)
        if len(recs) < MIN_MONTHS:
            continue
        for r in recs:
            r["sid"] = row.sid
            rows.append(r)
        keep.append(dict(sid=row.sid, name=str(row.NAME).strip(),
                         ctry=str(row.CTRY).strip(), icao=str(row.ICAO).strip(),
                         lat=float(row.LAT), lon=float(row.LON),
                         elev=float(row.ELEV) if row.ELEV == row.ELEV else 0.0))

    roses = pd.DataFrame(rows)
    stations = pd.DataFrame(keep)
    front = ["sid", "month", "n_obs", "calm_frac", "mean_speed",
             "resultant_speed", "resultant_dir", "constancy",
             "dir_missing_frac"]
    roses = roses[front + [c for c in roses.columns if c not in front]]

    roses.to_csv(DATA / "wind_roses.csv", index=False, encoding="utf-8")
    stations.to_csv(DATA / "wind_stations.csv", index=False, encoding="utf-8")
    print(f"\n{len(stations)} stations x {len(roses)} station-months")
    print(f"wind_roses.csv   {(DATA / 'wind_roses.csv').stat().st_size/1e6:.2f} MB")
    print(f"lat range {stations.lat.min():.1f}..{stations.lat.max():.1f}  "
          f"lon range {stations.lon.min():.1f}..{stations.lon.max():.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
