# Orbital Traffic — plan for a live-satellite GlyphViz example

> **Status, 2026-08-21.** All three scenes — `Live_Sky`, `One_Orbit` and
> `Orbital_Shells` — are **built, verified and documented**. See `README.md`.
> This file is kept as written, for the feasibility record; where the build
> disagreed with the plan, the README wins.
>
> The one thing the plan flagged as uncertain turned out to be real: a single
> node *cannot* express an orbital plane, because the engine composes
> rotations X-outermost while an orbit needs Z-outermost. Two nested nodes do
> it exactly. `probe_torus.py` establishes that and five other conventions.

Draft, 2026-08-21. Feasibility was probed end-to-end before this was written;
every number marked ✅ was measured on this machine today, not estimated.

---

## 1. What access we actually have

### CelesTrak GP (the TLE replacement) — free, no account, current ✅

```
https://celestrak.org/NORAD/elements/gp.php?GROUP=<group>&FORMAT=csv
```

`FORMAT` takes `tle`, `csv`, `json`, `xml` (OMM). **Use `csv`** — it is the
format CelesTrak stores internally, it is the smallest, and it carries more
significant digits than the 69-character TLE text.

Measured today, epoch `2026-08-21T12:47:44Z` — hours old:

| Group | Objects | Group | Objects |
|---|---|---|---|
| `active` | 16,069 | `geo` | 568 |
| `starlink` | 10,744 | `visual` | 157 |
| `stations` | 4 | `weather` | 74 |
| `gps-ops` | 32 | `iridium-NEXT` | 80 |
| `galileo` | 32 | `science` | 48 |
| | | `cosmos-2251-debris` | 591 |

### CelesTrak SATCAT — the metadata join ✅

`https://celestrak.org/pub/satcat.csv` — 6.7 MB, **70,355 cataloged objects**,
34,868 of them still on orbit. Columns worth having:

`OBJECT_NAME, OBJECT_ID, NORAD_CAT_ID, OBJECT_TYPE, OPS_STATUS_CODE, OWNER,
LAUNCH_DATE, LAUNCH_SITE, DECAY_DATE, PERIOD, INCLINATION, APOGEE, PERIGEE, RCS`

On-orbit breakdown: **19,894 payloads · 12,498 debris · 2,422 rocket bodies · 54 unknown**.
Owners: US 18,283 · CIS 6,682 · PRC 6,060 · UK 725 · FR 647. RCS (radar cross
section, m²) present for 14,616 objects — a real size channel, not a made-up one.

On-orbit objects by launch year: 212 (2019) → 470 → 1,092 → 2,478 → 2,376 →
3,233 → **4,510 (2025)** → 2,954 (2026 YTD). The crowding story is in the data.

### The rate limit — the one hard operational constraint ⚠️

CelesTrak's own FAQ (updated 2026-03-26):

> CelesTrak only checks for new GP data once every 2 hours, so there is no need
> for you to check more often. […] we have had to implement limits, which are
> enforced with temporary blocks.

**And it is not a 403.** Requesting a group you already downloaded returns
**HTTP 200 with a plain-text body** — I hit this within one minute today:

```
GP data has not updated since your last successful
download of GROUP=active at 2026-08-21 21:59:18 UTC.
Data is updated once every 2 hours.
```

A naive fetcher parses that as an empty CSV and silently wipes its own cache.
The generator **must** sniff for the `OBJECT_NAME` header, fall back to the
on-disk cache when it is absent, and never re-request inside the 2-hour window.
Getting this wrong is how you end up firewalled.

### Other sources, for the record

| Source | Verdict |
|---|---|
| **Space-Track.org** | The upstream authority; full catalog incl. analyst objects. Needs a free account plus credential handling. **Not a base dependency** — CelesTrak covers the example. |
| **CelesTrak SupGP** | Operator-supplied ephemerides (Starlink/OneWeb), more accurate than GP. Optional accuracy upgrade. |
| **SOCRATES Plus** | Conjunction / close-approach predictions. Would make a spectacular Link-edge scene ("these two pass within 200 m on Thursday"). The public endpoints 404 — it sits behind a search form now. **Verify before committing to it.** |
| **N2YO and friends** | Wrap the same GP data behind an API key. No reason to add a middleman. |

### Licensing

CelesTrak GP/SATCAT derive from US Government SSN data and are freely
redistributable. Credit **CelesTrak (Dr. T.S. Kelso)** and honor the usage
policy. Bundle a snapshot in `data/` for offline rebuild, as the Geomagnetic and
RSS examples already do.

---

## 2. Is "near real-time" actually real? Yes — and better than expected

The thing to be precise about: **element sets refresh every 2 hours, but
positions are propagated locally at any rate you like.** The display is live to
the second. This is exactly what every online tracker does.

Measured today, in the `glyphviz` conda env:

| Step | Cost |
|---|---|
| `sgp4init` 1,013 satellites from OMM CSV | **< 10 ms** ✅ |
| Propagate all 1,013 to *now* (`SatrecArray`, vectorized) | **< 1 ms** ✅ |
| Single-satellite propagation | **0.68 µs** ✅ |
| TEME→ECEF→geodetic for 1,013 (numpy) | sub-ms ✅ |
| Write the 1,014-row `gv_node.csv` | **8 ms**, 103 KB ✅ |

Extrapolated to the full 16,069-object `active` set: roughly 15 ms to propagate,
130 ms to write. **GlyphViz's Watch and Reload polls the node CSV's mtime once a
second** (`main_window.py:221`) and preserves camera, selection, and Channels
playback across the reload. So a 1 Hz live scene is comfortably within budget —
the generator is not the bottleneck.

**The one unmeasured risk:** how smoothly GlyphViz *reloads* several thousand
nodes once a second. Century_Swarm already ships 140,380 static nodes, so
capacity is not in doubt, but per-second reload cost is. **Measure this in the
GUI before locking the default live object count.** Mitigation is simple:
default the live scene to a curated ~800 objects and let `--group` scale up.

### Accuracy

SGP4 is good to roughly 1 km at epoch, degrading 1–3 km/day for LEO. Refreshing
elements every 2 hours keeps it near the kilometer level — right for a
visualization, not for conjunction assessment. Say so in the README.

---

## 3. Does it place correctly on a GlyphViz globe? Verified against the engine

A World Grid globe (`type=6`, `geometry=3`) puts children at
`translate_x = longitude`, `translate_y = latitude`, `translate_z = radial
elevation`, on a sphere of radius **180/π ≈ 57.2958 × scale**.

That fixes the scale: **1 world unit = 111.32 km** (one degree of latitude).

| Orbit | Altitude | `translate_z` | vs. globe radius |
|---|---|---|---|
| ISS | 419 km | 3.8 | 0.07 R |
| Starlink shell | 550 km | 4.9 | 0.09 R |
| GNSS (MEO) | 20,200 km | 181 | 3.2 R |
| GEO belt | 35,786 km | **321.5** | 5.6 R |

The full range is a 5.6-Earth-radii scene. That is the *true* geometry and it is
rarely drawn honestly — worth keeping rather than compressing, at least in one
scene.

**Engine check (already run):** 1,013 satellites written as globe children, then
their world positions pulled back out of the real `glyphviz_core.Scene`
transform engine and compared against the ECEF vectors they came from:

```
worst radius error : 0.000000 world units
worst angular error: 0.000002 deg
ISS world_pos radius -> 419.8 km altitude (CSV said 419.8 km)
```

The pipeline is geometrically exact. This probe becomes `verify_scenes.py`.

### Physics checks (already run)

| Check | Result |
|---|---|
| OMM-initialized `Satrec` vs. classic TLE-text parser, ISS | **44 m** apart — the TLE text's own truncation, not an error |
| GEO altitude, four satellites | 35,769–35,796 km (expect 35,786) ✅ |
| GOES 16 orbital period | **1436.08 min** vs. sidereal day 1436.07 ✅ |
| ISS semi-major axis / mean altitude | 6,796 km / 418 km ✅ |
| ISS ground speed | **6.93 km/s** ✅ |

A nice detail fell out of check 2: TDRS 3, TDRS 5, TDRS 6 and FLTSATCOM 8 sit at
latitudes of ±9° to ±14°, not 0°. These are aging GEO satellites that have given
up north–south stationkeeping and now trace daily figure-eight analemmas.
**That is a story a globe view tells for free and a flat map cannot.**

---

## 4. Proposed example: `Orbital_Traffic_Example`

Three scenes, phased so scene 1 alone is shippable. Structure follows
`Geomagnetic_Field_Example` and `Tropical_Cyclone_Example`.

### Scene 1 — `Live_Sky/` · the headline

Blue Marble World Grid globe, every tracked object at its true sub-satellite
point and true altitude, **updating once a second**.

| Element | Encoding |
|---|---|
| Object glyph | position = real-time sub-satellite lon/lat + altitude |
| Color | orbit regime (LEO / MEO / GEO / HEO) via palette, or owner |
| Size | SATCAT `RCS` (m²), floored at the 0.2 scale rule |
| Shape | `OBJECT_TYPE` — payload / rocket body / debris |
| `text` | name · NORAD ID · altitude · velocity |
| `link` | `celestrak.org/satcat/table-satcat.php?CATNR=<id>` — **Alt+click opens the real catalog record** |

Two additions that lift it above "dots on a globe":

- **Sunlight vs. eclipse.** Compute the sub-solar point and Earth's shadow
  cylinder; color satellites by whether they are lit. Add a terminator arc on
  the surface. This is *why* satellites are visible at dusk — the scene explains
  its own phenomenon.
- **Ground station horizons.** A handful of real stations (Svalbard, Kiruna,
  Goldstone, Canberra, Madrid, McMurdo) as surface glyphs, with **Link edges to
  every satellite currently above their horizon**. The edge set churns live, and
  Svalbard lighting up on nearly every polar pass makes the case for polar
  ground stations visually, in about four seconds of watching.

Generator: `--watch 1` rewrites the node CSV each second (propagate only);
re-fetches GP no more often than every 2 hours, from cache, with the sentinel
guard from §1. Atomic writes (temp file plus `os.replace`), channels first and
node CSV last — the pattern `build_rss_news_scene.py` already proves.

### Scene 3 — `Orbital_Shells/` · the structure  *(built)*

Not a globe. The *architecture* of near-Earth space, which is what GlyphViz's
hierarchy engine is actually for:

```
regime → constellation → orbital plane → satellite
```

Each orbital plane is a **Torus-topology parent** with its satellites as children
spaced by mean anomaly, the plane tilted by inclination and rotated by RAAN.
`rotate_rate_z` makes them genuinely orbit at true relative rates with zero CPU.

GPS's 6 planes, Galileo's 3, Iridium's 6, Starlink's shells, and the GEO belt as
one dense ring — side by side, showing *why* GNSS constellations are built the
way they are.

**Risk:** mapping RAAN and inclination onto the torus parent's rotation
convention needs its own transform probe, the way the Geomagnetic example had to
establish `rotate_x = 90 + I, rotate_y = D − 90` for globe children. Budget for
it; do not assume.

> **As built:** the risk was real. `rotation_mode = 0` composes **Rx · Ry · Rz**
> (X outermost); an orbit needs `Rz(RAAN) · Rx(inc)` (Z outermost), so writing
> the two angles into one node's fields is off by 42 world units on a radius-30
> ring. Nesting an outer RAAN node above the inclination torus reproduces the
> perifocal→ECI transform to 3.7e-15. The hierarchy level that looks redundant
> is load-bearing. A second trap, not anticipated: a child's `translate_z` is
> in the *parent's local* units, so surface markers floated 1,275 km up until
> divided by the parent's scale.

### Scene 2 — `One_Orbit/` · offline Channels replay  *(built)*

The scene that works with no network and no watch loop — and the one people will
screenshot. **90 minutes at 10-second steps = 540 frames** of `translate_x/y/z`
for every LEO object, pre-computed into `gv_ch-tracks.csv`. Press Space and the
whole shell sweeps. Scrubbable, deterministic, reproducible.

Sizing: 540 frames × 3 tracks × N objects. At N = 2,000 that is 3.2 M cells —
large but in Century_Swarm's league. Start at N ≈ 800 (payloads below 2,000 km)
and measure.

> **As built:** 558 frames × 2,004 tracks = 1.1 M cells, 7.1 MB, for 335 LEO
> objects. Six tracks per satellite rather than three — position *and* colour,
> so the shell visibly enters and leaves Earth's shadow during the replay,
> which turned out to be the best thing in the scene. Colour-track sharing
> across identical shadow histories cut 1,005 tracks to 756.

**Stretch alternative** (or a fourth scene): *catalog growth 1957 → 2026* from
SATCAT alone — objects appear at `LAUNCH_DATE`, vanish at `DECAY_DATE`, placed
schematically by altitude and inclination rather than propagated. No SGP4 at
all, and it is the clearest possible telling of the crowding story: 212
still-orbiting objects from 2019's launches against 4,510 from 2025's.

---

## 5. Validation, matching the bar the other examples set

**`verify_orbits.py`** — the physics, against outside sources:

1. vs. **`skyfield`** (independent SGP4 implementation) across many objects and epochs
2. GEO analytic check — altitude 35,786 km, period 1436.07 min ✅ *(already passing)*
3. ISS ground speed and altitude against published values ✅ *(already passing)*
4. OMM-init vs. TLE-text agreement ✅ *(already passing, 44 m)*
5. Round-trip geodetic conversion (lat/lon/alt → ECEF → lat/lon/alt)

**`verify_scenes.py`** — does the picture mean what it claims? Pull every node's
world position back out of the real `Scene` engine, convert to lat/lon/altitude,
compare against the propagator. ✅ *(already prototyped: 2 × 10⁻⁶ deg worst case)*

---

## 6. Dependencies and effort

**New dependency:** `sgp4` (Brandon Rhodes) — 148 KB pure wheel, no build step,
installed cleanly into the `glyphviz` env today ✅. `numpy` 2.4.6 and `pandas`
3.0.5 are already there. `skyfield` optional, verifier only — follow the
Geomagnetic example's pattern of skipping that check with a notice when absent.

**Files:**

```
build_orbital_scenes.py      generator (fetch/cache/propagate/emit)
orbits.py                    SGP4 + TEME->ECEF + geodetic + eclipse geometry
verify_orbits.py             physics vs. independent sources
verify_scenes.py             does the rendered scene tell the truth?
data/gp_cache/*.csv          GP snapshots (offline rebuild)
data/satcat.csv              SATCAT snapshot
data/stations.csv            ground stations: name, lat, lon, operator
Live_Sky/                    + media/01_bluemarble.png
Orbital_Shells/
One_Orbit/                   + gv_ch-map.csv, gv_ch-tracks.csv
README.md
```

**Phasing:**

1. ~~**Scene 1 static**~~ **Done.**
2. ~~**Scene 1 live** — the `--watch 1` loop.~~ **Done**: 600 frames at exactly
   1 Hz, median 38 ms per frame, p95 73 ms — 4% of the budget.
3. ~~**Scene 2 (`One_Orbit`)** — Channels replay.~~ **Done.**
4. ~~**Scene 3 (`Orbital_Shells`)** — the torus/plane transform probe first,
   then the scene.~~ **Done**, probe first exactly as planned.

---

## 7. Recommendation

**Worth building.** The data is free, current, unauthenticated and richly
annotated; the propagation is fast enough that live updates are limited by the
viewer's 1 Hz file poll rather than by anything we compute; and the globe
placement is exact against the real transform engine. Three things make it a
*GlyphViz* example rather than a generic tracker: the honest 5.6-Earth-radii
altitude scale, the ground-station horizon edges, and the constellation → plane
→ satellite hierarchy.

Two things to settle before writing much code: the per-second GUI reload cost
(§2) and the torus rotation convention (§4, scene 2).
