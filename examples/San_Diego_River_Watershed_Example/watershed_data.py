"""
watershed_data.py — the public data behind the San Diego River Watershed scene
==============================================================================

Fetches, caches and shapes every public dataset the Phase 1 scene uses. Kept
apart from the scene builder so later Atlas phases (hydrographs, fire
perimeters, the storm scenes) can import the same frame without re-deriving it.

All sources are free, keyless US federal services, queried live and cached as
small JSON files under data/ so a rebuild works offline and is reproducible.
Pass refresh=True (build script: --refresh) to re-download.

  Watershed outline   USGS Watershed Boundary Dataset, three HUC-10 units:
                      1807030405 Upper San Diego River, 1807030406 San Vicente
                      Creek, 1807030407 Lower San Diego River. Together
                      1,120.8 km² = 432.8 sq mi. NOTE the HUC-8 that contains
                      them, 18070304 "San Diego", is 1,553 sq mi and also
                      takes in the Sweetwater, Otay and San Diego Bay basins.
  River network       NHDPlus V2 flowlines upstream of the river's terminal
                      reach (comid 20331522), via the USGS NLDI, with
                      attributes (Strahler order, name, level path, drainage
                      area) from the USGS water-data GeoServer.
  Stream gauges       USGS NWIS site service.
  Rain stations       NOAA GHCN-Daily station metadata via RCC-ACIS.
  Place names         USGS National Map Gazetteer (GNIS).
  Monthly flow        USGS NWIS daily values, averaged per month (Phase 2).
  Monthly rainfall    NOAA GHCN-Daily monthly totals via RCC-ACIS (Phase 2).
"""

from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
USER_AGENT = "GlyphViz/1.0 (desktop data-visualization app; example build)"

HUC10 = {
    "1807030405": "Upper San Diego River",
    "1807030406": "San Vicente Creek",
    "1807030407": "Lower San Diego River",
}
TERMINAL_COMID = 20331522          # NHDPlus V2: the reach that meets the Pacific

GAUGES = ["11022480", "11023000", "11022200"]
RAIN_STATIONS = ["USC00042239", "USC00044412", "USC00044710", "USC00042406"]

# Names looked up in GNIS, with the gazetteer layer to search and the feature
# class expected — the class check stops "Santee" matching a school.
#   3 = Populated Places, 5 = Landforms, 7 = Other Hydrographic Features
# Spellings are GNIS's own, checked against the service: it is "Volcan
# Mountains" (a Range) and "Lake Cuyamaca". A Range or Valley is stored as
# several points; the first is GNIS's primary point (a valley's mouth).
# El Capitan Reservoir is NOT in this gazetteer layer at all — it comes from
# the NHDPlus waterbody instead (see fetch_reservoirs).
PLACES = [
    ("Volcan Mountains", 5, "Range"),
    ("Cuyamaca Peak", 5, "Summit"),
    ("Lake Cuyamaca", 7, "Reservoir"),
    ("San Vicente Reservoir", 7, "Reservoir"),
    ("Lake Jennings", 7, "Reservoir"),
    ("Lakeside", 3, "Populated Place"),
    ("Santee", 3, "Populated Place"),
    ("Cowles Mountain", 5, "Summit"),
    ("Mission Gorge", 5, "Valley"),
    ("Mission Valley", 5, "Valley"),
    ("Ocean Beach", 3, "Populated Place"),
]


# ---------------------------------------------------------------------------
# HTTP + cache
# ---------------------------------------------------------------------------

def _get(url: str, params: dict | None = None, body: dict | None = None) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    data = None
    headers = {"User-Agent": USER_AGENT}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    # The National Map's gazetteer resets connections and returns empty
    # bodies intermittently; a few spaced retries clear it in practice.
    last: Exception | None = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
            if body.strip():
                return body
            last = OSError(f"empty response from {url}")
        except OSError as exc:
            last = exc
        time.sleep(4.0 * (attempt + 1))
    raise last


def _cached(name: str, refresh: bool, fetch):
    path = DATA / name
    if path.is_file() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    DATA.mkdir(parents=True, exist_ok=True)
    obj = fetch()
    path.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")
    return obj


# ---------------------------------------------------------------------------
# Watershed outline
# ---------------------------------------------------------------------------

def fetch_huc10(refresh=False) -> dict:
    def fetch():
        ids = ",".join(f"'{h}'" for h in HUC10)
        return json.loads(_get(
            "https://hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer/5/query",
            {"where": f"huc10 in ({ids})", "outFields": "huc10,name,areasqkm",
             "returnGeometry": "true", "outSR": "4326", "f": "geojson"}))
    return _cached("huc10.geojson", refresh, fetch)


def _key(p) -> tuple[float, float]:
    return (round(p[0], 7), round(p[1], 7))


def dissolve(geojson: dict) -> tuple[list[list], list[list], float]:
    """-> (outer boundary rings, internal divide polylines, total km²).

    No shapely in the env, and none needed: the three units come from one
    dataset and share their common borders vertex for vertex, so an edge that
    appears in two rings is an internal divide and an edge that appears once
    is on the outside. Chaining each set of edges back into lines gives both.
    """
    count: dict[tuple, int] = {}
    area = 0.0
    for f in geojson["features"]:
        area += float(f["properties"]["areasqkm"])
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for poly in polys:
            for ring in poly:
                for a, b in zip(ring, ring[1:]):
                    ka, kb = _key(a), _key(b)
                    if ka == kb:
                        continue
                    e = (ka, kb) if ka < kb else (kb, ka)
                    count[e] = count.get(e, 0) + 1
    outer = [e for e, c in count.items() if c == 1]
    inner = [e for e, c in count.items() if c >= 2]
    return _chain(outer), _chain(inner), area


def _chain(edges) -> list[list]:
    """Join undirected edges into maximal polylines (closed ones repeat their
    first point at the end)."""
    adj: dict[tuple, list[tuple]] = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    used: set[tuple] = set()
    lines: list[list] = []

    def edge(a, b):
        return (a, b) if a < b else (b, a)

    # Start from dead ends / junctions first so open lines are not split.
    starts = [v for v, n in adj.items() if len(n) != 2] + list(adj)
    for s in starts:
        for nxt in adj[s]:
            if edge(s, nxt) in used:
                continue
            line = [s, nxt]
            used.add(edge(s, nxt))
            cur, prev = nxt, s
            while len(adj[cur]) == 2:
                cand = [v for v in adj[cur] if edge(cur, v) not in used]
                if not cand:
                    break
                prev, cur = cur, cand[0]
                used.add(edge(prev, cur))
                line.append(cur)
            lines.append([list(p) for p in line])
    return lines


def point_in_rings(lon: float, lat: float, rings: list[list]) -> bool:
    inside = False
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            if (y1 > lat) != (y2 > lat):
                x = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
                if x > lon:
                    inside = not inside
    return inside


# ---------------------------------------------------------------------------
# River network
# ---------------------------------------------------------------------------

def fetch_network(refresh=False) -> dict:
    def fetch():
        geo = json.loads(_get(
            f"https://api.water.usgs.gov/nldi/linked-data/comid/{TERMINAL_COMID}"
            f"/navigation/UT/flowlines", {"distance": "2000"}))
        comids = [f["properties"]["nhdplus_comid"] for f in geo["features"]]
        attrs: dict[str, dict] = {}
        props = ("comid,gnis_name,streamorde,lengthkm,totdasqkm,hydroseq,"
                 "dnhydroseq,levelpathi,terminalfl,ftype")
        for i in range(0, len(comids), 80):
            chunk = ",".join(str(c) for c in comids[i:i + 80])
            page = json.loads(_get(
                "https://api.water.usgs.gov/geoserver/wmadata/ows",
                {"service": "WFS", "version": "1.0.0", "request": "GetFeature",
                 "typeName": "wmadata:nhdflowline_network",
                 "outputFormat": "application/json",
                 "cql_filter": f"comid IN ({chunk})", "propertyName": props}))
            for f in page["features"]:
                attrs[str(f["properties"]["comid"])] = f["properties"]
        for f in geo["features"]:
            f["properties"].update(attrs.get(str(f["properties"]["nhdplus_comid"]), {}))
        return geo
    return _cached("nhdplus_network.geojson", refresh, fetch)


@dataclass
class Stream:
    """One run of constant Strahler order along one NHDPlus level path,
    ordered upstream -> downstream."""
    name: str
    order: int
    levelpath: int
    coords: list[list[float]]
    length_km: float
    drainage_km2: float          # at the downstream end
    mainstem: bool = False
    comids: list[int] = field(default_factory=list)


def build_streams(geo: dict) -> list[Stream]:
    """Group flowlines into Strahler-order runs along each level path.

    A level path is NHDPlus's headwater-to-confluence identity for one stream,
    so it is what a person means by "Boulder Creek". Splitting it where the
    order changes lets line width follow Strahler order exactly, the way a
    stream actually grows as tributaries join it.
    """
    rows = []
    for f in geo["features"]:
        p = f["properties"]
        if p.get("streamorde") is None or p.get("hydroseq") is None:
            continue
        g = f["geometry"]
        parts = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        coords = [pt for part in parts for pt in part]
        rows.append((p, coords))

    mouth_path = next((p["levelpathi"] for p, _ in rows
                       if p["comid"] == TERMINAL_COMID), None)

    by_path: dict[int, list] = {}
    for p, coords in rows:
        by_path.setdefault(int(p["levelpathi"]), []).append((p, coords))

    streams: list[Stream] = []
    for lp, members in by_path.items():
        members.sort(key=lambda r: -r[0]["hydroseq"])      # upstream first
        run: list = []
        for p, coords in members + [(None, None)]:
            if run and (p is None or p["streamorde"] != run[-1][0]["streamorde"]):
                first = run[0][0]
                last = run[-1][0]
                pts: list[list[float]] = []
                for _rp, c in run:
                    if pts and _key(pts[-1]) == _key(c[0]):
                        pts.extend(c[1:])
                    else:
                        pts.extend(c)
                streams.append(Stream(
                    name=first.get("gnis_name") or "",
                    order=int(first["streamorde"]),
                    levelpath=lp,
                    coords=pts,
                    length_km=sum(float(rp["lengthkm"]) for rp, _ in run),
                    drainage_km2=float(last["totdasqkm"]),
                    mainstem=(lp == mouth_path),
                    comids=[int(rp["comid"]) for rp, _ in run]))
                run = []
            if p is not None:
                run.append((p, coords))

    # A run's downstream end should meet the next run (or the stream it joins)
    # exactly; NHDPlus flowlines already share their end vertices, so this is a
    # check rather than a fix.
    return streams


def km_of(coords) -> float:
    total = 0.0
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        la = math.radians((y1 + y2) / 2)
        total += 6371.0 * math.hypot(math.radians(x2 - x1) * math.cos(la),
                                     math.radians(y2 - y1))
    return total


# ---------------------------------------------------------------------------
# Gauges, rain stations, places
# ---------------------------------------------------------------------------

def fetch_gauges(refresh=False) -> list[dict]:
    def fetch():
        txt = _get("https://waterservices.usgs.gov/nwis/site/",
                   {"format": "rdb", "sites": ",".join(GAUGES),
                    "siteOutput": "expanded"}).decode()
        lines = [l for l in txt.splitlines() if l and not l.startswith("#")]
        head = lines[0].split("\t")
        out = []
        for l in lines[2:]:
            r = dict(zip(head, l.split("\t")))
            out.append(dict(site=r["site_no"], name=r["station_nm"],
                            lat=float(r["dec_lat_va"]), lon=float(r["dec_long_va"]),
                            drain_sq_mi=float(r["drain_area_va"] or "nan")))
        return out
    return _cached("usgs_gauges.json", refresh, fetch)


def fetch_rain_stations(refresh=False) -> list[dict]:
    def fetch():
        meta = json.loads(_get("https://data.rcc-acis.org/StnMeta", body={
            "sids": ",".join(RAIN_STATIONS), "meta": "name,ll,elev,sids,valid_daterange",
            "elems": "pcpn"}))["meta"]
        out = []
        for m in meta:
            ghcn = next(s.split()[0] for s in m["sids"] if s.startswith("USC"))
            span = (m.get("valid_daterange") or [[None, None]])[0]
            out.append(dict(ghcn=ghcn, name=m["name"].title(), lon=m["ll"][0],
                            lat=m["ll"][1], elev_ft=m["elev"],
                            first=span[0], last=span[1]))
        return out
    return _cached("ghcn_rain_stations.json", refresh, fetch)


def fetch_places(refresh=False) -> list[dict]:
    def fetch():
        out = []
        for name, layer, fclass in PLACES:
            time.sleep(1.0)                   # be gentle with a flaky service
            res = json.loads(_get(
                f"https://carto.nationalmap.gov/arcgis/rest/services/geonames/"
                f"MapServer/{layer}/query",
                {"where": f"gaz_name = '{name}' AND state_alpha = 'CA' "
                          f"AND county_name = 'San Diego'",
                 "outFields": "gaz_id,gaz_name,gaz_featureclass",
                 "returnGeometry": "true", "outSR": "4326", "f": "json"}))
            hits = [f for f in res.get("features", [])
                    if f["attributes"]["gaz_featureclass"] == fclass]
            if len(hits) != 1:
                raise SystemExit(f"GNIS: expected one {fclass} named {name!r}, "
                                 f"found {len(hits)}")
            a, g = hits[0]["attributes"], hits[0]["geometry"]
            pts = g["points"] if "points" in g else [[g["x"], g["y"]]]
            out.append(dict(name=a["gaz_name"], gnis_id=a["gaz_id"],
                            feature_class=a["gaz_featureclass"],
                            lon=pts[0][0], lat=pts[0][1], points=pts))
        return out
    return _cached("gnis_places.json", refresh, fetch)


def fetch_reservoirs(refresh=False) -> dict:
    """The named NHDPlus waterbodies the river network flows through, with
    their shorelines.

    Found through the network rather than by name: an ArtificialPath
    flowline carries the comid of the waterbody it crosses (wbareacomi). The
    GeoServer's firewall rejects quoted strings in a filter, so a by-name
    query 403s, while a numeric comid IN (...) filter is accepted.
    """
    def fetch():
        geo = fetch_network()
        art = [f["properties"]["nhdplus_comid"] for f in geo["features"]
               if f["properties"].get("ftype") == "ArtificialPath"]
        wfs = "https://api.water.usgs.gov/geoserver/wmadata/ows"
        base = {"service": "WFS", "version": "1.0.0", "request": "GetFeature",
                "outputFormat": "application/json"}
        fl = json.loads(_get(wfs, {**base, "typeName": "wmadata:nhdflowline_network",
                                   "cql_filter": f"comid IN ({','.join(map(str, art))})",
                                   "propertyName": "comid,wbareacomi"}))
        wbs = sorted({f["properties"]["wbareacomi"] for f in fl["features"]
                      if f["properties"].get("wbareacomi")})
        wb = json.loads(_get(wfs, {**base, "typeName": "wmadata:nhdwaterbody",
                                   "cql_filter": f"comid IN ({','.join(map(str, wbs))})",
                                   "propertyName": "comid,gnis_name,areasqkm,ftype,the_geom"}))
        wb["features"] = [f for f in wb["features"]
                          if (f["properties"].get("gnis_name") or "").strip()]
        return wb
    return _cached("nhd_reservoirs.geojson", refresh, fetch)


# ---------------------------------------------------------------------------
# Time series (Phase 2, "The Pulse"): monthly river flow and monthly rainfall
# ---------------------------------------------------------------------------

def _month_keys(first: str, last: str) -> list[str]:
    y, m = int(first[:4]), int(first[5:7])
    ly, lm = int(last[:4]), int(last[5:7])
    out = []
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def fetch_monthly_flow(site: str, refresh=False) -> dict:
    """Monthly mean discharge (cfs) for one USGS gauge, from its DAILY values.

    -> {"site", "first_day", "last_day", "months": {"YYYY-MM": {"cfs", "days",
    "of", "provisional", "estimated"}}}. Months with no daily value at all are
    absent — they are gaps in the record, not zero flow, and the scene draws
    them as gaps. A month missing a few days keeps the mean of the days it has
    ("days" of "of"); callers decide how complete is complete enough.

    Built from the daily values rather than taken from NWIS's monthly
    statistics service so the completeness of every month is known and
    reported. Only the monthly result is cached (small, and all Phase 2
    needs); the storm scene will fetch its own daily window.

    USGS is moving these services to api.waterdata.usgs.gov. The cache under
    data/ means a rebuild never depends on this endpoint staying up.
    """
    def fetch():
        import calendar
        txt = _get("https://waterservices.usgs.gov/nwis/dv/",
                   {"format": "rdb", "sites": site, "parameterCd": "00060",
                    "statCd": "00003", "startDT": "1900-01-01"}).decode()
        lines = [l.split("\t") for l in txt.splitlines()
                 if l and not l.startswith("#")]
        head = lines[0]
        vcol = next(i for i, h in enumerate(head) if h.endswith("_00060_00003"))
        ccol = vcol + 1
        acc: dict[str, list] = {}
        days = []
        for row in lines[2:]:
            if len(row) <= vcol or not row[vcol].strip():
                continue
            try:
                q = float(row[vcol])
            except ValueError:            # "Ice", "Eqp", "Dis" and friends
                continue
            code = row[ccol] if len(row) > ccol else ""
            day = row[head.index("datetime")]
            days.append(day)
            a = acc.setdefault(day[:7], [0.0, 0, False, False])
            a[0] += q
            a[1] += 1
            a[2] |= "P" in code
            a[3] |= "e" in code
        months = {}
        for k, (tot, n, prov, est) in sorted(acc.items()):
            months[k] = dict(cfs=round(tot / n, 4), days=n,
                             of=calendar.monthrange(int(k[:4]), int(k[5:]))[1],
                             provisional=prov, estimated=est)
        return dict(site=site, first_day=min(days), last_day=max(days),
                    months=months)
    return _cached(f"flow_monthly_{site}.json", refresh, fetch)


def fetch_monthly_rain(ghcn: str, refresh=False) -> dict:
    """Monthly precipitation totals (inches) for one GHCN-Daily station via
    RCC-ACIS. -> {"station", "months": {"YYYY-MM": inches | None}}.

    ACIS sums the daily values itself and returns "M" when more than
    MAX_MISSING_DAYS days of the month are missing, which becomes None here.
    A trace ("T") is a real observation of almost nothing and becomes 0.
    """
    MAX_MISSING_DAYS = 3

    def fetch():
        res = json.loads(_get("https://data.rcc-acis.org/StnData", body={
            "sid": ghcn, "sdate": "1899-01", "edate": "por",
            "elems": [{"name": "pcpn", "interval": "mly", "duration": "mly",
                       "reduce": "sum", "maxmissing": MAX_MISSING_DAYS}]}))
        months = {}
        for k, v in res["data"]:
            months[k] = (None if v == "M" else 0.0 if v == "T"
                         else float(v.rstrip("A")))
        return dict(station=ghcn, name=res["meta"]["name"].title(),
                    max_missing_days=MAX_MISSING_DAYS, months=months)
    return _cached(f"rain_monthly_{ghcn}.json", refresh, fetch)


def fetch_daily_flow(site: str, refresh=False) -> dict:
    """A gauge's whole daily record: {"site", "first_day", "cfs": [...]}, one
    entry per calendar day from first_day, None where the record has no value.
    Stored as a flat list so the century of days caches compactly."""
    def fetch():
        import datetime as dt
        txt = _get("https://waterservices.usgs.gov/nwis/dv/",
                   {"format": "rdb", "sites": site, "parameterCd": "00060",
                    "statCd": "00003", "startDT": "1900-01-01"}).decode()
        lines = [l.split("\t") for l in txt.splitlines()
                 if l and not l.startswith("#")]
        head = lines[0]
        vcol = next(i for i, h in enumerate(head) if h.endswith("_00060_00003"))
        dcol = head.index("datetime")
        got = {}
        for row in lines[2:]:
            try:
                got[row[dcol]] = float(row[vcol])
            except (ValueError, IndexError):
                continue
        first = dt.date.fromisoformat(min(got))
        last = dt.date.fromisoformat(max(got))
        n = (last - first).days + 1
        vals = [got.get((first + dt.timedelta(days=i)).isoformat()) for i in range(n)]
        return dict(site=site, first_day=first.isoformat(), cfs=vals)
    return _cached(f"flow_daily_{site}.json", refresh, fetch)


def fetch_daily_rain_field(bbox: tuple[float, float, float, float], sdate: str,
                           edate: str, refresh=False) -> list[dict]:
    """Every GHCN-Daily station ACIS has precipitation for inside *bbox*
    (lon_min, lat_min, lon_max, lat_max) between *sdate* and *edate*.

    -> [{"name", "sids", "lon", "lat", "elev_ft", "days": [[inches|None, flag]]}]
    with one entry per day. Flags, kept rather than smoothed over:
      ""   an ordinary daily total          "T"  trace, stored as 0.0
      "M"  missing                          "S"  folded into a later "A" total
      "A"  a total ACCUMULATED over this day and the "S" days before it
    """
    def fetch():
        import re
        res = json.loads(_get("https://data.rcc-acis.org/MultiStnData", body={
            "bbox": ",".join(f"{v:g}" for v in bbox), "sdate": sdate, "edate": edate,
            "elems": [{"name": "pcpn"}], "meta": "name,ll,elev,sids"}))
        out = []
        for r in res["data"]:
            m = r["meta"]
            if not m.get("ll"):
                continue
            days = []
            for (raw,) in r["data"]:
                raw = raw or "M"
                if raw in ("M", "S"):
                    days.append([None, raw])
                elif raw == "T":
                    days.append([0.0, "T"])
                else:
                    num = re.match(r"^[0-9.]+", raw)
                    flag = re.sub(r"[0-9.]", "", raw)
                    days.append([float(num.group()) if num else None,
                                 flag if num else "M"])
            out.append(dict(name=m["name"].title(), sids=m.get("sids", []),
                            lon=m["ll"][0], lat=m["ll"][1], elev_ft=m.get("elev"),
                            days=days))
        return out
    key = f"{sdate}_{edate}"
    return _cached(f"rain_daily_field_{key}.json", refresh, fetch)


def reservoir_shorelines(wb: dict) -> list[dict]:
    """-> [{name, area_km2, ring}] using each waterbody's largest outer ring."""
    out = []
    for f in wb["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        ring = max((poly[0] for poly in polys), key=len)
        out.append(dict(name=f["properties"]["gnis_name"].strip(),
                        area_km2=float(f["properties"]["areasqkm"]),
                        ring=[list(p[:2]) for p in ring]))
    return out
