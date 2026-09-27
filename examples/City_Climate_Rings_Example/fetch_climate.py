#!/usr/bin/env python3
"""
fetch_climate.py
================
Build city_climate.csv: a flat, spreadsheet-shaped table of monthly climate
normals for 31 cities, one row per city per month (372 rows). This is the
"data you already have" the Climate Rings lesson starts from.

Source: NASA POWER daily point API (power.larc.nasa.gov), public domain, no
key: every day of January 2001 - December 2020 on the MERRA-2 grid (about
50 km cells), averaged here per calendar month. So each value describes the
grid cell a city sits in, not a weather station inside it; a coastal city's
cell often reaches inland, with hotter summers than its airport records.

    high_c, low_c, mean_c   mean of the daily T2M_MAX / T2M_MIN / T2M, deg C
    precip_mm               PRECTOTCORR summed per month, averaged over years

(POWER's own climatology endpoint is not used: its T2M_MAX/T2M_MIN are the
month's EXTREMES, e.g. a 27.6 C January "high" for San Diego.)

    python fetch_climate.py            # writes city_climate.csv beside itself
"""
import calendar
import csv
import json
import time
import urllib.request
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "city_climate.csv"
API = ("https://power.larc.nasa.gov/api/temporal/daily/point"
       "?parameters=T2M_MAX,T2M_MIN,T2M,PRECTOTCORR&community=AG"
       "&longitude={lon}&latitude={lat}&start=20010101&end=20201231&format=JSON")

# (city, country, lat, lon): a spread of climates on every continent.
CITIES = [
    ("San Diego", "USA", 32.72, -117.16),
    ("Seattle", "USA", 47.61, -122.33),
    ("Anchorage", "USA", 61.22, -149.90),
    ("Honolulu", "USA", 21.31, -157.86),
    ("Chicago", "USA", 41.88, -87.63),
    ("Miami", "USA", 25.76, -80.19),
    ("Mexico City", "Mexico", 19.43, -99.13),
    ("Bogota", "Colombia", 4.71, -74.07),
    ("Lima", "Peru", -12.05, -77.04),
    ("Manaus", "Brazil", -3.12, -60.02),
    ("Rio de Janeiro", "Brazil", -22.91, -43.17),
    ("Buenos Aires", "Argentina", -34.60, -58.38),
    ("Reykjavik", "Iceland", 64.15, -21.94),
    ("London", "UK", 51.51, -0.13),
    ("Moscow", "Russia", 55.76, 37.62),
    ("Cairo", "Egypt", 30.04, 31.24),
    ("Lagos", "Nigeria", 6.52, 3.38),
    ("Nairobi", "Kenya", -1.29, 36.82),
    ("Johannesburg", "South Africa", -26.20, 28.05),
    ("Cape Town", "South Africa", -33.92, 18.42),
    ("Dubai", "UAE", 25.20, 55.27),
    ("Mumbai", "India", 19.08, 72.88),
    ("Delhi", "India", 28.61, 77.21),
    ("Yakutsk", "Russia", 62.03, 129.73),
    ("Ulaanbaatar", "Mongolia", 47.89, 106.91),
    ("Beijing", "China", 39.90, 116.41),
    ("Tokyo", "Japan", 35.68, 139.69),
    ("Singapore", "Singapore", 1.35, 103.82),
    ("Perth", "Australia", -31.95, 115.86),
    ("Sydney", "Australia", -33.87, 151.21),
    ("Auckland", "New Zealand", -36.85, 174.76),
]


def fetch(lat, lon, tries=5):
    # POWER drops the odd connection under load; back off and retry.
    for k in range(tries):
        try:
            with urllib.request.urlopen(API.format(lat=lat, lon=lon), timeout=60) as r:
                return json.load(r)["properties"]["parameter"]
        except (OSError, ValueError):
            if k == tries - 1:
                raise
            time.sleep(3 * (k + 1))


def main():
    rows = []
    for city, country, lat, lon in CITIES:
        d = pd.DataFrame(fetch(lat, lon)).replace(-999.0, float("nan"))
        d.index = pd.to_datetime(d.index, format="%Y%m%d")
        by_month = d.groupby(d.index.month)
        mean = by_month.mean()
        rain = (d["PRECTOTCORR"].groupby([d.index.year, d.index.month]).sum()
                .groupby(level=1).mean())
        for m in range(1, 13):
            rows.append(dict(
                city=city, country=country, lat=lat, lon=lon,
                month=calendar.month_abbr[m],
                high_c=round(mean.loc[m, "T2M_MAX"], 1),
                low_c=round(mean.loc[m, "T2M_MIN"], 1),
                mean_c=round(mean.loc[m, "T2M"], 1),
                precip_mm=int(round(rain.loc[m]))))
        print(f"{city:<16} ok")
        time.sleep(0.5)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()
