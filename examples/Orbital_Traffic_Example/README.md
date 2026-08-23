# Orbital Traffic

Three scenes built from live CelesTrak orbital data, sharing one propagator.

| Scene | What it is |
|---|---|
| **1 · `Live_Sky/`** | Every tracked satellite where it is *right now*, rewritten once a second |
| **2 · `One_Orbit/`** | A full 93-minute revolution precomputed into Channels, replayable in twenty seconds |
| **3 · `Orbital_Shells/`** | The orbital planes themselves, in the inertial frame — turning by itself the moment it loads |

Nothing here is a simulation. The element sets are the ones the US Space
Surveillance Network published this morning, propagated with the standard SGP4
model.

Each scene animates a different way on purpose: scene 1 by an external
generator loop and File > Watch and Reload, scene 2 by Channels playback, and
scene 3 by nothing at all — `rotate_rate_z` on each ring, integrated by the
viewport, with no clock to press.

---

# Scene 1 — Live Sky

Every tracked satellite on a Blue Marble globe, at its true sub-satellite
point and its true altitude, **updating once a second**. Hue says which
orbital regime an object is in; brightness says whether the Sun is currently
shining on it. Edges run from ten real ground stations to whatever is above
their horizon right now.

---

## What you're looking at

| Element | Meaning |
|---|---|
| Globe | World Grid (type 6) in globe form, NASA Blue Marble texture |
| Small glyphs above it | One per catalogued object, at its real lon/lat/altitude this second |
| Glyph **hue** | Orbit regime — cyan LEO, amber MEO, rose GEO, green HEO (legend to the west) |
| Glyph **brightness** | Sunlight: full = lit, half = penumbra, quarter = eclipsed |
| Glyph **shape** | Octahedron = payload, cylinder = rocket body, tetrahedron = debris |
| Glyph **size** | Radar cross section from the SATCAT, log-compressed |
| Amber ring on the surface | The day/night terminator — a real great circle, 90° from the Sun |
| Yellow sphere | The sub-solar point: where the Sun is directly overhead |
| White pins | Ground stations, standing on their real coordinates |
| Green edges | Station → satellite, for the ten highest passes; thicker and brighter with elevation angle |
| Caption overhead | UTC clock, object and illumination tallies, element age |

Alt+click any satellite (or select it and press **U**) to open its CelesTrak
catalogue record in your browser. **T** toggles the full label set — every
object carries name, NORAD id, regime, altitude, speed, illumination state and
owner, which is far too much to show at once.

---

## The scale is honest, and that is the point

A World Grid globe places children on a sphere of radius 180/π ≈ 57.3 world
units, so **one world unit is 111.32 km** — one degree of latitude.

| Orbit | Altitude | Height above the globe |
|---|---|---|
| ISS | 419 km | 3.8 units — 0.07 Earth radii |
| Starlink shell | 550 km | 4.9 units |
| GPS / Galileo | 20,200 km | 181 units — 3.2 R |
| GEO belt | 35,786 km | **321.5 units — 5.6 R** |

Most satellite maps quietly compress that range. This one doesn't, so the
default view is about eleven Earth-diameters across and Earth is a small ball
at the centre of a very large, very empty volume with three distinct
inhabited shells in it: a fuzzy layer clinging to the surface, two GNSS
shells halfway out, and a razor-thin rose ring at the edge. That picture is
the real geometry of near-Earth space and it is worth the zooming.

For the close-up, rebuild with `--max-alt-km 2000` (see below).

---

## Sunlight

Earth's shadow is modelled as a **cone, not a cylinder** — the Sun is an
extended source, so there is a converging umbra ringed by a diverging
penumbra:

```
a_umb = asin((R_sun - R_earth) / d_sun)      shadow radius at distance x
a_pen = asin((R_sun + R_earth) / d_sun)      = R_earth -+ x*tan(a)
```

The umbra tapers to a point about 1.4 million km behind Earth, well past GEO,
so every orbit in the scene can be fully eclipsed. The atmosphere is ignored;
refraction would soften the boundary by a few tens of km.

The solar direction comes from the Astronomical Almanac's low-precision
series — good to about 0.01°, which at 1 AU is 26,000 km of transverse error
and utterly irrelevant to a test that only cares about a direction.

### What to look for

- **The ISS is in the dark for 38.7% of its orbit right now** — 36 of every
  93 minutes. That fraction is not fixed: it tracks the *beta angle* between
  the Sun and the orbit plane over a roughly 60-day cycle, and near the top of
  that cycle the station runs for days without a sunset at all. Watch it cross
  the terminator and dim.
- **A GEO satellite is normally never eclipsed.** The belt sits 11.9° from the
  shadow axis in late August, and the umbra only subtends 8.4° there. GEO
  eclipse season is roughly three weeks either side of each equinox — the
  verifier measures the whole curve (0 min at ±30 days, 32 min at −21 days,
  **68 min on the equinox itself**).
- **Except for the ones that are.** On 21 August 2026 six of 568 GEO objects
  were in shadow: UFO 2, MILSTAR-2 3, USA 170, SKYNET 5B, AEHF-1 and
  SHIYAN-12 01. All six sat within 7.5° of the anti-solar longitude *and* at
  latitudes between −3.6° and −10.4°. They are **inclined** GEO satellites —
  old birds that have given up north–south stationkeeping and now swing above
  and below the equator each day. Their inclination carries them into a shadow
  their well-stationkept neighbours, sitting at latitude 0.0° a few degrees
  away in the same ring, miss entirely. Two satellites side by side in the
  same belt, one lit and one dark, for a reason you can see.

---

## Ground station horizons

Each station's elevation angle to every object is computed from its local
geodetic horizon — the angle an antenna would actually be commanded to. Edges
are drawn to the **ten highest passes**, because an antenna farm tracks a
handful of satellites rather than everything in the sky, and because without
the cap the GEO belt buries every LEO pass under hundreds of near-identical
edges.

That cap is itself informative. Across the ten stations there are **2,065
station–satellite pairs above 5° elevation at once** — an average of 207 per
station, out of 1,045 objects. Restrict the scene to LEO and the same tally
drops to **145 pairs**, about 15 per station. A geostationary satellite is
visible from roughly 42% of the planet at once; a 550 km LEO satellite from
about 3%. Almost everything a station can "see" is something it can see all
day and has no reason to track.

### Why polar stations exist

Averaged over 24 hours, LEO objects above 5° elevation:

| Station | Latitude | In view |
|---|---|---|
| McMurdo | −77.8° | **25.1** |
| Svalbard (SvalSat) | +78.2° | **24.6** |
| Troll | −72.0° | 21.7 |
| Kiruna | +67.9° | 18.8 |
| Poker Flat | +65.1° | 17.5 |
| Madrid | +40.4° | 9.7 |
| Canberra | −35.4° | 9.5 |
| Wallops | +37.9° | 9.5 |
| Goldstone | +35.4° | 9.3 |
| Kourou | +5.3° | 7.6 |

A clean monotonic slide with latitude, and a **3.3× advantage** for the polar
sites. Most LEO satellites are in near-polar orbits, so their ground tracks
converge at high latitude and a polar station sees nearly every pass while an
equatorial one sees a fraction. Svalbard's whole commercial existence is in
that column. Run the scene live for a minute and you can watch it happen.

---

## Going live

```bash
python build_live_sky.py --watch 1
```

Open `Live_Sky/live_sky_gv_node.csv` in GlyphViz and turn on **File > Watch
and Reload** (Ctrl+R). The viewer polls the file's mtime once a second and
hot-reloads in place, preserving camera, selection and playback.

A full frame — propagate 1,045 objects, classify illumination, compute ten
stations' worth of look angles, and write 1,528 nodes — takes **31 ms**. The
generator is nowhere near the bottleneck; the viewer's 1 Hz poll is the limit.

Writes are atomic (temp file + `os.replace`), so a reload never sees a torn
CSV.

### Node ids never move

This matters more than it sounds. Every id comes from a fixed layout computed
once from the configuration, never from the moment being rendered:

```
1  World      2  globe      3  clock      4  sub-solar marker
5..           legend
...           terminator ring, then its edges
...           ground stations
...           satellites, sorted by NORAD id
...           the station-link pool
```

Objects that fail to propagate, or that an altitude filter excludes, are
written as **hidden rows rather than dropped**. The station-link pool is a
fixed `stations × links-per-station` block whose unused slots are hidden
self-links. So the set of visible edges churns completely every second while
the file's shape never changes — which is what lets you keep a satellite
selected and watch its properties update live.

---

## Rebuilding

```bash
python build_live_sky.py                    # fetch politely, build once
python build_live_sky.py --offline          # rebuild from the bundled cache
python build_live_sky.py --watch 1          # live, 1 Hz
python build_live_sky.py --max-alt-km 2000  # LEO close-up
python build_live_sky.py --groups active    # the whole catalogue (~16,000)
python build_live_sky.py --links-per-station 25 --min-elev 10
python build_live_sky.py --glyph-scale 2.5  # bigger glyphs for a wide shot
```

Default groups are a ~1,045-object mix spanning every regime: `stations`,
`visual`, `science`, `weather`, `iridium-NEXT`, `gps-ops`, `galileo`,
`glo-ops`, `beidou`, `geo`.

### CelesTrak's rate limit — read this before changing the fetch code

CelesTrak refreshes GP data **every 2 hours** and temporarily firewalls IPs
that poll faster. The trap is that a too-soon repeat request does not return
an error status — it returns **HTTP 200** with a plain-text body:

```
GP data has not updated since your last successful
download of GROUP=active at 2026-08-21 21:59:18 UTC.
Data is updated once every 2 hours.
```

A fetcher that trusts the status code parses that as an empty CSV, wipes its
own cache, and keeps hammering until the IP is blocked. `orbits.fetch_group`
sniffs for the `OBJECT_NAME` header, falls back to the on-disk cache when it
is missing, and never re-requests inside the 2-hour window. `--watch` only
ever re-propagates; it does not re-fetch every second.

---

# Scene 2 — One Orbit

Live Sky is honest about time and therefore unwatchable: the ISS takes 93 real
minutes to go round once, so at 1× the orbital motion is invisible. This scene
precomputes that entire revolution into GlyphViz Channels tracks. **Press
Space** and it replays in about twenty seconds — and the motion that was
imperceptible becomes the whole point.

```bash
python build_one_orbit.py
```

Then open `One_Orbit/one_orbit_gv_node.csv`. The Channels panel appears by
itself; Space plays, Shift+Space stops and restores the authored frame.

Three things move together on one clock:

- **The satellites**, along their real SGP4 trajectories — 335 LEO objects,
  558 frames, 10 seconds apart.
- **Their colour**, as each crosses into and out of Earth's shadow. The same
  conical umbra test as Scene 1, re-evaluated every frame.
- **The terminator and sub-solar point**, sliding west while the shell goes
  round. The day/night line is not a backdrop here; it is what the satellites
  are flying through.

Six recognisable objects — ISS, Tiangong, Hubble, Terra, Aqua and NOAA 20 —
carry a static trail marking their full path, so the eye has something to
follow through the swarm.

### What to look for

- **984 illumination transitions** in 93 minutes. 265 of the 335 objects
  change state at least once; watch the shell wink dark as it sweeps into the
  cone behind Earth and brighten as it comes out.
- **70 objects never leave sunlight for the entire orbit.** Those are the
  dawn–dusk sun-synchronous satellites, flying permanently along the
  terminator so their solar panels never lose the Sun and their imagery always
  has the same lighting. They ride the amber ring for the whole replay — the
  scene shows you *why* that orbit is worth having.
- **Earth turns 23.30° beneath the ISS during one revolution.** Play two
  revolutions (`--minutes 186`) and the trail lays down twice, displaced west
  by that much — the reason a ground track is a slowly drifting sinusoid
  rather than a closed loop.
- The sub-solar point sweeps **23.21°** in those 93 minutes. Not the sidereal
  23.31°, because the Sun creeps east along the ecliptic while Earth turns —
  which is exactly why a solar day is four minutes longer than a sidereal one.

### Options

```bash
python build_one_orbit.py --minutes 186     # two revolutions
python build_one_orbit.py --step 5          # smoother, twice the tracks
python build_one_orbit.py --max-alt-km 800  # just the crowded shell
python build_one_orbit.py --max-alt-km 40000  # include MEO and GEO
python build_one_orbit.py --fetch           # refresh elements first
```

### Track economy

The tracks file is the one thing that gets expensive fast — it is 558 rows by
2,004 columns, 7.1 MB. Two things keep it from being much worse:

- **Colour tracks are shared.** A satellite's hue is fixed by its regime and
  only its brightness changes, so any two objects with an identical *shadow
  history* need the same three colour tracks. Among 335 objects there are only
  252 distinct histories — mostly because the 70 permanently-lit ones all
  share a single constant one. That is 756 colour tracks instead of 1,005.
- **The terminator ring animates on longitude and latitude, but nothing else.**

One thing that did *not* work: animating the ring's longitude alone. The
sub-solar longitude sweeps 23° while the declination drifts only 0.02°, so
freezing latitude looks like a free win. It is not — it leaves the ring up to
**0.016° off the true terminator** by the end of the replay. That is 1.8 km on
the ground and completely invisible, but it means the amber circle would no
longer be the day/night circle, and a check that says "the terminator is where
the Sun sets" would have been quietly false. 120 extra tracks fixed it; the
residual is now 1.0 × 10⁻⁴ degrees, which is the CSV's own rounding.

---

# Scene 3 — Orbital Shells

The first two scenes are geographic: satellites over a map, placed by latitude
and longitude. This one drops the map and shows the **structure** — the orbital
planes themselves, in the inertial frame where they stand still and the Earth
is the thing that spins.

```bash
python build_orbital_shells.py
```

Open `Orbital_Shells/orbital_shells_gv_node.csv`. It starts turning
immediately: every ring carries `rotate_rate_z` set to its own orbital angular
rate and the viewport integrates it on a continuous 30 fps timer. There is no
Channels panel, nothing to press, and nothing to keep running in a terminal.

Constellations are not clouds. Seen from a map, GPS is thirty-two scattered
dots. Seen as planes, it is obviously *engineering* — and you can read what
each design is for.

| Constellation | Planes | Inclination | Altitude | Period | One turn at 300× |
|---|---|---|---|---|---|
| Iridium NEXT | **6**, ~31.6° apart | 86.4° | 767 km | 100.1 min | 20 s |
| GPS | **6**, ~60° apart | 55.1° | 20,163 km | 718 min | 144 s |
| GLONASS | **3**, ~120° apart | 64.8° | 19,131 km | 676 min | 135 s |
| Galileo | **3**, ~120° apart | 55.8° | 23,223 km | 840 min | 168 s |
| BeiDou | 7 (mixed MEO/IGSO/GEO) | varies | varies | varies | varies |
| GEO belt | 1 dense ring | ~0° | 35,786 km | 1436 min | 287 s |

Every one of those plane counts and spacings is **recovered from live element
sets by clustering**, not written into the generator. The published designs
are what the clustering finds.

### Every ring is a real orbit, and its satellite is on it

The first build drew one ring per *cluster*, at the cluster's mean elements,
and hung each satellite on its own separate invisible ring at its own exact
elements. Both halves were correct and the combination was misleading: the
visible circles were not the paths the satellites were on. Measured across the
scene, satellites sat a median of **450 km** and up to **9,700 km** from the
nearest drawn ring — 342 of 773 more than 550 km out. It read exactly as it
was: paths with nothing following them.

Now the ring a satellite rides **is** the ring you see — the same node. They
cannot disagree.

A ring is only *drawn*, though, when it is not a duplicate of one already
drawn. Every satellite still keeps its own exact ring node; a ring whose orbit
comes within `--ring-tol-units` (default 3 world units, about one glyph) of an
already-drawn one simply isn't rendered. That tolerance is a **distance, not
an angle**, and the angle it permits is derived per ring as `asin(tol/radius)`:
half a degree is 3,300 km out at GEO and only 7 km down at Iridium, so a fixed
angular tolerance would be wrong at both ends. The guarantee is the one that
matters visually — no satellite is ever further from the ring it appears to
ride than the width of its own glyph. The verifier measures it: worst case
**2.72 world units, 302 km**, inside the glyph.

773 orbits collapse to **170 drawn rings**: 8 for Iridium, 7 for Galileo,
11 for GLONASS, 29 for GPS, 25 for BeiDou — and 90 for the geostationary belt,
which is the interesting number. The GEO "belt" is not a line. Its 548 objects
span 15 degrees of inclination, because satellites that stop north–south
stationkeeping keep drifting, so at glyph resolution it really is ninety
distinct orbits forming a band. Drawing it honestly makes a thick pink wall
that rather dominates the view; `--no-geo` drops it and leaves the GNSS
lattice clean.

### What to look for

- **Iridium's six planes span only ~180° of RAAN**, spaced 31.6° apart with
  one large seam — not 60° apart over the full circle. That is the near-polar
  Walker design: a plane at RAAN Ω and one at Ω+180° are the *same* ring
  travelled the other way, so a polar constellation only has half a circle to
  spread across. The lopsided gap in the scene is the co-rotating seam, and it
  is a real feature of Iridium, not an artefact.
- **GPS at 60° and Galileo at 120°** — six planes of four versus three planes
  of eight, two different answers to the same coverage problem, side by side
  and to scale.
- **The GEO belt is a single wall of satellites** in one plane, while
  everything else is a lattice. Turn the camera edge-on to the equator and the
  belt collapses to a line.
- **Relative speeds are true.** Iridium whips round while GPS crawls and the
  GEO ring keeps perfect pace with the Earth's surface underneath it — that
  last one *is* what geostationary means, and here it is a thing you watch
  rather than a definition you read.

### Galileo's two lost satellites

The plane clustering found something it was not looking for. Galileo has three
nominal planes; the scene finds three clean ones of 11, 10 and 9 satellites at
RAAN 120° apart — plus two satellites that belong to none of them:

| | Nominal Galileo | GSAT0201 / GSAT0202 |
|---|---|---|
| Inclination | 55.8° | **48.8°** |
| Eccentricity | ~0.0002 | **0.168** |
| Altitude | 23,223 km | **18,332 – 25,143 km** |

These are Galileo 5 and 6, launched together on a Soyuz in August 2014 and
stranded in the wrong orbit when a frozen hydrazine line in the Fregat upper
stage froze an attitude-control thruster. They are still up there, still
broadcasting, still on a wrong and eccentric orbit — and they fall out of the
data by themselves the moment you cluster by plane.

The scene deliberately **does not draw a ring for them**. A ring asserts
"these satellites share a circular plane," and for an orbit of eccentricity
0.17 that would be fiction. They get their exact glyph and no claimed plane.
Same rule retires four other small clusters: five groups of abandoned,
high-inclination near-geosynchronous objects that CelesTrak files under `geo`
but which are emphatically not in the geostationary belt.

### Options

```bash
python build_orbital_shells.py --no-geo           # the clean GNSS lattice
python build_orbital_shells.py --time-scale 600   # twice as fast
python build_orbital_shells.py --time-scale 1     # real time (it will look still)
python build_orbital_shells.py --ring-tol-units 0 # draw all 773 orbits
python build_orbital_shells.py --fetch            # refresh elements first
```

---

## The transform convention, and how it was established

Scene 3 is built out of nested rotations, which is the kind of construction
that looks plausible while being wrong. `probe_torus.py` settles the rules
against the real engine before any scene code runs — the same discipline the
Geomagnetic example used for globe children. Run it; it prints its findings.

```bash
python probe_torus.py
```

**1 · A torus parent puts its children at `radius = base_scale × parent
scale`.** `Scene(base_scale=...)` defaults to **3.0** — the app's Global Scale
— so a ring of radius *R* needs `scale = R/3`. The skill reference says this
base defaults to 1.0; the code says 3.0.

**2 · `rotation_mode = 0` composes as Rx · Ry · Rz — X outermost.**

**3 · Therefore a single node cannot express an orbital plane.** The classical
perifocal→ECI transform is

```
r = Rz(RAAN) · Rx(inclination) · (cos u, sin u, 0) · radius
```

which needs **Z** outermost. Writing inclination into `rotate_x` and RAAN into
`rotate_z` on one node produces something quite different — the probe measures
it at 42 world units of error on a radius-30 ring.

**4 · Two nested nodes do express it, exactly.** Transforms compose down the
hierarchy, so an outer node carrying RAAN and an inner torus carrying
inclination give `Rz(RAAN) · Rx(inc)` whatever the single-node convention
happens to be. Verified against the engine at **3.7 × 10⁻¹⁵ world units**.

That is why the hierarchy has a level in it that looks redundant. It is not
stylistic; the geometry does not work without it.

**5 · A Sphere-topology parent obeys the same radius rule**, which is why
Earth here is a plain textured Sphere glyph rather than a World Grid. Grids
are documented as exempt from Global Scale — a grid Earth would drift out of
step with the rings the moment anyone touched that slider.

**7 · A child's `translate_z` is in the parent's LOCAL units.** Asking for
"0.6 world units above the surface" on a scale-19 Earth puts the marker at
**11.46 units — 1,275 km — up**, as a halo rather than a pin. Write
`N / parent_scale`.

**9 · A torus ratio under 0.005 makes an unselectable ring.** The torus mesh
is cached per ratio *rounded to two decimals* (`geometry.py:760`), and picking
renders the **solid** form of a wireframe so the whole silhouette is
clickable. A ratio of 0.0035 therefore draws perfectly well as wires and has
no solid silhouette at all — the ring is visible and cannot be selected, by
click or by rubber-band region. Both the generator and the verifier now refuse
a visible torus whose ratio rounds to zero.

**8 · And a parent's scale multiplies its children's RENDERED SIZE, not just
their positions.** This is the one that shipped a broken scene. A glyph
authored at scale 0.5 under a GEO-sized torus draws **189 world units
across** — three times the diameter of the Earth. Nothing in the CSV looks
wrong; every glyph carries a sane number; every raw-scale assertion passes.

| Parent scale | Child authored 0.5 renders at |
|---|---|
| 1 | 1.5 world units |
| 10 | 15 |
| 126 (GEO) | **189** |
| World Grid globe | 1.5 — grids are exempt |

Scenes 1 and 2 never met this because World Grid globes re-space their
children's positions but never their sizes. Scene 3 hangs everything on torus
and sphere parents and met it immediately.

There are two fixes. Divide the authored scale by the parent's — safe, because
the optional minimum-glyph-size clamp is measured against the *rendered* scale,
so a small authored number is not clamped up (that is what the landmarks do).
Or keep the placement parent at scale 1 and carry the orbit radius in the
child's `translate_z`, since a torus child sits at radius
`base_scale + translate_z` whatever the ratio — that is what the satellites do,
and it is why the placement rings and the drawn rings are separate nodes.

---

## Verifying

Four suites, all worth running.

**`verify_orbits.py`** — 19 checks on the physics, most of which can fail
*without the scene looking wrong*, which is exactly the class of error a
picture cannot catch. Each leans on something outside this code: an
independent implementation, an analytic limit, or a published number.

```
[PASS] 1.  OMM-built Satrec matches TLE-text parser -- 26.1 m apart
[PASS] 2.  vs. skyfield -- 400 sats: |r| 0.00 mm, lat 0.0 m, lon 41.8 m, alt 0.0 m
[PASS] 3.  GEO period == one sidereal day -- median 1436.09 min vs 1436.07
[PASS] 3b. GEO semi-major axis -- 42,165 km, altitude 35,786 km
[PASS] 4.  ISS altitude 418.4 km, ground speed 6.890 km/s
[PASS] 5.  geodetic round-trip is an identity -- worst 2.13e-14 deg
[PASS] 6.  solar declination at solstices/equinoxes -- worst error 0.005 deg
[PASS] 6b. equation of time: all four turning points and four zeros
[PASS] 7.  GEO eclipse peaks at the equinox -- 68 min on 2026-09-23
[PASS] 8.  ISS eclipse fraction matches the beta-angle formula
[PASS] 9.  terminator sits 90 deg from the sub-solar point -- 4.26e-14 deg
```

Three of those are worth singling out:

- **Check 6b** reproduces the equation of time at all four of its annual
  turning points (−14.2 min on 11 Feb, +3.7 in May, −6.4 in July, +16.4 on
  3 Nov) and its four zero crossings. The big pair comes mostly from orbital
  eccentricity and the small pair mostly from obliquity, so it tests the two
  terms of the solar series separately rather than in aggregate.
- **Check 7** measures the GEO eclipse season across a year and finds it where
  published astronomy says it is. Neither the ~70-minute peak nor the
  three-week window appears anywhere in `orbits.py`; they fall out of the
  cone geometry.
- **Check 8** compares the stepped ISS eclipse against the closed-form
  beta-angle formula, `f = arccos(√(h²+2Rh) / ((R+h)cos β)) / π` — different
  mathematics reaching the same physics, never touching `illumination()`.

**`verify_scenes.py`** — 10 checks on the *picture*. It loads the written CSV
through the real `glyphviz_core` transform engine, pulls every node's world
position back out, and asks whether the glyph the viewer draws is where the
satellite actually is.

```
[PASS] 1. globe children land at their written lon/lat/altitude
          1,236 nodes: radius 2.27e-13 world units, bearing 1.71e-06 deg
[PASS] 3. rendered altitude matches the altitude in the label
          worst 504 m over 1,045 satellites (the label rounds to the km)
[PASS] 5. every drawn station edge is genuinely above the horizon
[PASS] 7. terminator ring sits 90 deg from the sub-solar marker
```

Check 1's residual is floating-point noise and check 7's is the CSV's own
4-decimal rounding of longitude. The scene is geometrically exact.

**`verify_replay.py`** — 11 checks on the *animation*. A static scene being
right at frame 0 says nothing about frame 557, so this drives the **real
`ChannelEngine`** — the same object the app's Channels panel drives — through
the replay, pulls each glyph's world position out of the transform engine at
frames spread across the whole span, converts it back to lat/lon/altitude, and
compares against an independent SGP4 propagation to that frame's wall clock.

```
[PASS] 2. the three-way join is complete
          2,253 bindings, 457 channels, 0 driving no node, 0 missing a column
[PASS] 5. animated ground position matches an independent propagation
          worst 7.7 m over 335 satellites x 6 frames (CSV rounding is ~11 m)
[PASS] 6. animated colour tracks the umbra/penumbra test
          1,340 node-frames checked, 0 mismatched
[PASS] 7. terminator stays on the day/night circle for the whole replay
[PASS] 8. the sub-solar point sweeps west at the solar, not sidereal, rate
          23.21 deg; solar 23.25, sidereal 23.31
[PASS] 9. Stop (reset) restores the CSV's own values
```

Check 2 matters more than it looks: the Channels join is three-way
(`node.ch_input_id` → `map.channel_id` → a `ch<id>` tracks column) and **every
link in it fails silently**. A typo'd attribute name, a channel with no node,
a track id with no column — nothing warns, the animation just doesn't happen.

Check 8 is deliberately two-sided: it requires the sweep to match the solar
rate *and* to differ from the sidereal one. A one-sided tolerance would pass
even if the solar model had stopped contributing entirely.

**`verify_shells.py`** — 14 checks on the plane construction. Nested rotations
are easy to get subtly wrong, so this reads the scene back through the
transform engine and asks whether the rings are real planes:

```
[PASS] 2. every glyph sits at its true inertial position
          worst 4.0 m over 773 satellites
[PASS] 4. every drawn ring lies in a real orbit plane of its own constellation
          27/27 rings within 6 deg of a member orbit normal
[PASS] 5. plane counts match the published designs
          gps-ops 6/6, glo-ops 3/3, iridium-NEXT 6/6, galileo 3/3
[PASS] 6. every ring spins at its own true orbital rate
          all 773 rings within 0.0000 of a single shared time scale
[PASS] 7c. Earth's prime meridian is at its true right ascension
[PASS] 9. a landmark's lon/lat lands at its true right ascension
```

Check 5 is the one that matters most: it asserts the scene reproduces
*published* constellation designs from live data. Check 6 is subtle — it does
not test each rate against a fixed number but against that satellite's own
mean motion, so it fails if any ring spins at a rate that merely looks
plausible. Check 4 compares each ring only against its own constellation's
orbit normals; matching against every orbit in the scene would let a ring pass
by coincidentally lining up with something unrelated.

### Seeing the scene without the app

A bug that only a picture can show needs a picture, so `preview_scene.py`
renders any scene straight from the transform engine — world positions *and
world scales* — to a PNG. It is not a renderer: no lighting, no textures, no
depth-correct geometry. It answers one question, which is the question the
CSV cannot: **is anything absurdly the wrong size or in the wrong place?**

```bash
python preview_scene.py                              # all three, side by side
python preview_scene.py Orbital_Shells/orbital_shells_gv_node.csv --out shot.png
python preview_scene.py --elev 8 --azim 40           # look along the belt
```

It reports the rendered size range for each scene as it goes, which is the
number that would have caught finding 8 in seconds.

```bash
python probe_torus.py                                # establish the conventions
python verify_orbits.py                              # the physics
python verify_scenes.py [path/to/scene_gv_node.csv]  # the static picture
python verify_replay.py [path/to/one_orbit_gv_node.csv]   # the animation
python verify_shells.py [path/to/orbital_shells_gv_node.csv]
```

Everything except `verify_orbits.py` needs the GlyphViz package on the path;
set `GLYPHVIZ_PATH` if it is not next to this example.

---

## Files

```
orbits.py                       fetch/cache, SGP4, TEME->ECEF->geodetic, Sun,
                                conical shadow, look angles, classification
build_live_sky.py               scene 1 generator (live, watch-and-reload)
build_one_orbit.py              scene 2 generator (Channels replay)
build_orbital_shells.py         scene 3 generator (self-animating rings)
probe_torus.py                  establishes the torus/rotation/scale conventions
preview_scene.py                renders a scene to PNG from the engine
verify_orbits.py                19 physics checks against independent sources
verify_scenes.py                10 checks that the picture tells the truth
verify_replay.py                11 checks that the animation stays true
verify_shells.py                14 checks that the planes are real planes
data/gp_cache/*.csv             GP element-set snapshots (offline rebuild)
data/satcat.csv                 SATCAT metadata, 70,355 objects
Live_Sky/live_sky_gv_node.csv         1,528 nodes
One_Orbit/one_orbit_gv_node.csv       1,711 nodes
One_Orbit/one_orbit_gv_ch-map.csv     2,253 bindings
One_Orbit/one_orbit_gv_ch-tracks.csv  558 frames x 2,004 tracks
Orbital_Shells/orbital_shells_gv_node.csv  2,344 nodes
*/media/01_bluemarble.png       NASA Blue Marble
PLAN.md                         the wider plan and its feasibility work
```

Each scene lives in its own folder because GlyphViz auto-loads Channels files
by scanning the node CSV's directory and **only** binds them when exactly one
`ch-map` and one `ch-tracks` match. Two candidate map files in a folder
disable Channels entirely, with no warning.

## Data and attribution

Orbital data and satellite catalogue courtesy of **CelesTrak**
(Dr. T. S. Kelso, <https://celestrak.org>), derived from US Space Surveillance
Network observations and freely redistributable. Please respect CelesTrak's
usage policy — in particular the 2-hour GP refresh interval above.

Globe texture: NASA Blue Marble.

## Accuracy

SGP4 is good to roughly a kilometre at epoch, degrading 1–3 km/day for LEO.
With element sets refreshed every 2 hours the displayed positions stay near
the kilometre level. That is right for a visualization and nowhere near good
enough for conjunction assessment — don't fly anything using this.

The TEME→ECEF rotation neglects polar motion and the equation of the
equinoxes, which check 2 measures at 42 m of ground track: three orders of
magnitude inside SGP4's own error.

## Requirements

`sgp4` (a 148 KB pure wheel, no build step), plus `numpy`. `skyfield` is
optional and used only by check 2 of the verifier, which skips itself with a
notice when it is absent.

```bash
pip install sgp4
pip install skyfield     # optional, verifier only
```
