#!/usr/bin/env python
"""Orbital Shells — the architecture of near-Earth space, turning by itself.

The other two scenes are geographic: satellites over a map, placed by latitude
and longitude.  This one drops the map and shows the *structure* — the orbital
planes themselves, in the inertial frame where they are fixed and the Earth is
the thing that spins.

Constellations are not clouds.  GPS is six planes of four; Galileo is three of
eight; GLONASS is three at a steeper tilt; Iridium is six near-polar planes;
and the geostationary belt is a single crowded ring in the equatorial plane.
Seen from a map, all of that is scattered dots.  Seen as planes, it is
obviously engineering — and you can see what each design is for.

Nothing is animated by Channels here.  Every ring carries `rotate_rate_z` set
to its own orbital angular rate, so the whole scene turns the moment it loads,
each constellation at its true speed relative to the others and to the Earth
underneath.  There is no clock to press and nothing to play.

Usage
-----
    python build_orbital_shells.py
    python build_orbital_shells.py --time-scale 600   # faster
    python build_orbital_shells.py --no-geo           # drop the GEO belt
    python build_orbital_shells.py --fetch            # refresh elements

The transform convention every ring depends on is established, against the
real engine, by `probe_torus.py`.  Read that first if you touch the geometry.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import os
import shutil
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import orbits  # noqa: E402
from build_live_sky import (KM_PER_UNIT, TAG_FONT_PT, dim,  # noqa: E402
                            glyph_scale, load_satcat, parse_csv, sanitize)

# ---------------------------------------------------------------------------
# 1. Constants
# ---------------------------------------------------------------------------
OUT_DIR = os.path.join(HERE, "Orbital_Shells")
STEM = "orbital_shells_gv"

# probe_torus.py, finding 1: a torus parent puts its children at
#     radius = base_scale x parent scale
# and `Scene(base_scale=...)` defaults to 3.0 — the app's Global Scale.  So a
# ring of radius R world units needs scale = R / 3.  A plain Sphere glyph obeys
# the same rule (finding 5), which is why Earth is drawn as one here rather
# than as a World Grid: grids are exempt from Global Scale, so a grid Earth
# would drift out of step with the rings the moment anyone touched that slider.
BASE_SCALE = 3.0

R_EARTH_UNITS = orbits.R_EARTH_EQ / KM_PER_UNIT       # 57.2958
SIDEREAL_DEG_PER_S = 360.0 / 86164.0905
RATE_CYCLES_PER_S = 60.0                              # ANTz rate convention

BG = (5, 6, 14, 255)

GEO_SPHERE, GEO_TORUS_WIRE, GEO_OCTA, GEO_LINE = 3, 6, 11, 27
GEO_BY_TYPE = {"PAY": 11, "R/B": 19, "DEB": 13}
GEO_UNKNOWN = 1

# The constellations worth showing as *planes*, in draw order.
CONSTELLATIONS = [
    # key            group          label                              rgb
    ("iridium",  "iridium-NEXT", "Iridium NEXT  6 planes, 86.4 deg",
     (90, 220, 255)),
    ("glonass",  "glo-ops",      "GLONASS  3 planes, 64.8 deg",
     (255, 130, 130)),
    ("galileo",  "galileo",      "Galileo  3 planes, 56 deg",
     (140, 170, 255)),
    ("gps",      "gps-ops",      "GPS  6 planes, 55 deg",
     (255, 196, 92)),
    ("beidou",   "beidou",       "BeiDou  mixed MEO / IGSO / GEO",
     (150, 235, 150)),
    ("geo",      "geo",          "the geostationary belt  one ring, 0 deg",
     (255, 120, 190)),
]
RING_ALPHA = 70            # many overlapping rings; keep bundles legible
RING_RATIO = 0.01          # the renderer quantises torus ratio to 1% steps
PLANE_GAP_DEG = 18.0        # RAAN gap that separates one plane from the next
INC_GAP_DEG = 8.0           # inclination gap that separates two orbit types
RADIUS_GAP_UNITS = 25.0     # ~2,800 km: IGSO and MEO must not share a ring
MIN_RING_MEMBERS = 3        # below this, don't claim a plane exists

COLUMNS = [
    "id", "type", "parent_id", "branch_level", "child_id",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "rotate_rate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo", "ratio", "texture_id",
    "segments_x", "segments_y",
    "show_text", "rotation_mode", "tag_color_mode", "tag_font_size",
    "ref_grid_color_r", "ref_grid_color_g", "ref_grid_color_b",
    "text", "link",
]
DEFAULTS = {c: 0 for c in COLUMNS}
DEFAULTS.update(scale_x=1.0, scale_y=1.0, scale_z=1.0, color_a=255,
                ratio=0.1, text="", link="")

# A few unmistakable places, so the Earth's orientation is readable and the
# sphere's own lon/lat convention is visible rather than assumed.
LANDMARKS = [
    ("Greenwich", 51.478, -0.001),
    ("Quito", -0.180, -78.467),
    ("Singapore", 1.352, 103.820),
    ("Cape Horn", -55.976, -67.266),
    ("Anchorage", 61.218, -149.900),
]


# ---------------------------------------------------------------------------
# 2. Orbital geometry
# ---------------------------------------------------------------------------
def osculating_plane(r_vec, v_vec):
    """(RAAN, inclination, argument of latitude, radius) from a state vector.

    Taken from the instantaneous position and velocity rather than from the
    element set's mean elements, so the reconstruction

        r = radius . Rz(RAAN) . Rx(inc) . (cos u, sin u, 0)

    reproduces the propagated position *exactly*, eccentricity and all — the
    ring a satellite rides is a circle through where it actually is, not an
    idealisation of where it ought to be.
    """
    r = np.asarray(r_vec, dtype=float)
    v = np.asarray(v_vec, dtype=float)
    h = np.cross(r, v)
    h_norm = float(np.linalg.norm(h))
    radius = float(np.linalg.norm(r))
    inc = math.degrees(math.acos(max(-1.0, min(1.0, h[2] / h_norm))))
    # Line of nodes = z_hat x h
    n = np.array([-h[1], h[0], 0.0])
    n_norm = float(np.linalg.norm(n))
    if n_norm < 1e-9:                      # equatorial: nodes undefined
        raan = 0.0
        u = math.degrees(math.atan2(r[1], r[0]))
    else:
        n = n / n_norm
        raan = math.degrees(math.atan2(n[1], n[0]))
        # Argument of latitude: angle from the node to r, in the orbit plane.
        m = np.cross(h / h_norm, n)        # completes the right-handed frame
        u = math.degrees(math.atan2(float(r @ m), float(r @ n)))
    return raan % 360.0, inc, u % 360.0, radius


def _split_linear(idx, value_of, gap):
    """Split indices into runs separated by gaps larger than `gap`."""
    order = sorted(idx, key=value_of)
    out, cur = [], [order[0]]
    for i in order[1:]:
        if value_of(i) - value_of(cur[-1]) > gap:
            out.append(cur)
            cur = [i]
        else:
            cur.append(i)
    out.append(cur)
    return out


def _split_circular(idx, value_of, gap):
    """Same, on a circle: RAAN 359 and RAAN 1 are one degree apart.

    A naive sort would split a plane that happens to straddle 0 degrees.
    Rotating the origin into the widest empty gap first makes the circle
    behave like a line.
    """
    if len(idx) < 2:
        return [list(idx)]
    order = sorted(idx, key=value_of)
    gaps = [(value_of(order[(k + 1) % len(order)]) - value_of(order[k])) % 360.0
            for k in range(len(order))]
    start = (int(np.argmax(gaps)) + 1) % len(order)
    rotated = order[start:] + order[:start]
    base = value_of(rotated[0])

    out, cur = [], [rotated[0]]
    for i in rotated[1:]:
        prev = (value_of(cur[-1]) - base) % 360.0
        here = (value_of(i) - base) % 360.0
        if here - prev > gap:
            out.append(cur)
            cur = [i]
        else:
            cur.append(i)
    out.append(cur)
    return out


def cluster_planes(idx, elems, gap_deg=PLANE_GAP_DEG,
                   inc_gap=INC_GAP_DEG, radius_gap_units=RADIUS_GAP_UNITS):
    """Group satellites into orbital planes.

    Clustering on RAAN alone is wrong for a mixed constellation.  BeiDou flies
    MEO, inclined-geosynchronous and geostationary satellites at once; a
    RAAN-only cluster happily averages an equatorial GEO with a 55-degree MEO
    and produces a ring in a plane that neither of them is in.  So split on
    inclination first, then on orbit radius (IGSO and MEO can share a RAAN and
    be 14,000 km apart), and only then on RAAN.
    """
    if not idx:
        return []
    groups = [list(idx)]
    for key, gap, circular in (
            (lambda i: elems[i][1], inc_gap, False),          # inclination
            (lambda i: elems[i][3], radius_gap_units, False),  # radius
            (lambda i: elems[i][0], gap_deg, True)):           # RAAN
        nxt = []
        for g in groups:
            split = _split_circular(g, key, gap) if circular \
                else _split_linear(g, key, gap)
            nxt.extend(split)
        groups = nxt
    return groups


def circular_mean(deg):
    a = np.radians(np.asarray(deg, dtype=float))
    return float(np.degrees(math.atan2(float(np.sin(a).mean()),
                                       float(np.cos(a).mean()))) % 360.0)


# ---------------------------------------------------------------------------
# 3. Scene assembly
# ---------------------------------------------------------------------------
class ShellScene:
    def __init__(self):
        self.rows: list[dict] = []
        self.next_id = 1

    def add(self, **kw) -> int:
        row = dict(DEFAULTS)
        row.update(kw)
        row.setdefault("id", self.next_id)
        if "id" not in kw:
            row["id"] = self.next_id
        self.next_id = max(self.next_id, row["id"] + 1)
        self.rows.append(row)
        return row["id"]

    def _raan_node(self, raan, level=0, parent=0):
        """The outer half of an orbital plane: rotation about the polar axis.

        probe_torus.py, findings 2-4: the engine composes a single node's
        rotations as Rx . Ry . Rz — X outermost.  An orbit needs
        Rz(RAAN) . Rx(inc) — Z outermost — so no single node can express one
        by writing inc and RAAN into its own fields.  Nesting fixes it:
        transforms compose down the hierarchy, so an outer node carrying RAAN
        and an inner torus carrying inclination give exactly Rz(RAAN).Rx(inc)
        whatever the single-node convention happens to be.  Verified against
        the engine to 3.7e-15 world units.
        """
        return self.add(type=5, parent_id=parent, branch_level=level,
                        topo=0, geometry=GEO_OCTA, rotate_z=round(raan, 6),
                        rotation_mode=0, hide=1,
                        scale_x=1.0, scale_y=1.0, scale_z=1.0)

    def orbit_ring(self, raan, inc, radius_units, rate_z, rgb, level=0,
                   segments=64, draw=True):
        """One satellite's own orbit, drawn — and the thing it rides.

        The first version drew one ring per *cluster*, at the cluster's mean
        elements, and hung each satellite on its own separate invisible ring
        at its own exact elements.  Both were correct and the combination was
        misleading: the visible circles were not the paths the satellites were
        on, and measured across the scene the satellites sat a median of
        450 km — and up to 9,700 km — away from the nearest drawn ring.  It
        read exactly as it was: paths with nothing following them.

        So the ring a satellite rides is now the ring you see.  They cannot
        disagree, because they are the same node.  The designed structure
        still emerges — GPS's six planes show up as six tight bundles of
        near-identical circles — and the drift of each satellite from its
        plane is now visible instead of hidden.
        """
        node = self._raan_node(raan, level)
        s = radius_units / BASE_SCALE
        return self.add(type=5, parent_id=node, branch_level=level + 1,
                        topo=3, geometry=GEO_TORUS_WIRE,
                        rotate_x=round(inc, 6), rotation_mode=0,
                        rotate_rate_z=rate_z,
                        scale_x=s, scale_y=s, scale_z=s,
                        # RING_RATIO, not something smaller: the renderer
                        # quantises a torus ratio to 1% steps, so anything
                        # under 0.005 collapses to a zero-thickness tube —
                        # which still draws as wires but has no solid
                        # silhouette, and picking renders the SOLID form of a
                        # wireframe. A thinner ring is an unclickable ring.
                        ratio=RING_RATIO,
                        segments_x=segments, segments_y=6,
                        color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                        color_a=RING_ALPHA, hide=0 if draw else 1)

    def placement_chain(self, raan, inc, rate_z, level=0):
        """A hidden, UNSCALED ring a satellite hangs on.

        The obvious construction — a torus scaled to the orbit radius, with the
        satellite as its child — is wrong, and wrong in a way that is invisible
        in the CSV.  A torus parent's scale multiplies its children's *rendered
        size*, not just their positions (probe_torus.py finding 8), so a
        1.5-unit glyph under a GEO-sized torus draws at 190 units: bigger than
        the Earth.  World Grid globes are exempt from that, which is why
        scenes 1 and 2 never met it.

        So the placement torus stays at scale 1 and the orbit radius rides in
        the satellite's own `translate_z` instead — a torus child sits at
        radius `base_scale + translate_z`, whatever the ratio.  The satellite
        then renders at exactly the size it was authored at.
        """
        node = self._raan_node(raan, level)
        return self.add(type=5, parent_id=node, branch_level=level + 1,
                        topo=3, geometry=GEO_TORUS_WIRE,
                        rotate_x=round(inc, 6), rotation_mode=0,
                        rotate_rate_z=rate_z, ratio=0.01,
                        scale_x=1.0, scale_y=1.0, scale_z=1.0, hide=1)

    def plane_ring(self, raan, inc, radius_units, rgb, *, level=0,
                   ratio=0.0035, segments=96):
        """A visible nominal plane. Deliberately childless.

        This one *is* scaled to the orbit radius, which is safe precisely
        because nothing hangs off it to inherit that scale.
        """
        node = self._raan_node(raan, level)
        s = radius_units / BASE_SCALE
        return self.add(type=5, parent_id=node, branch_level=level + 1,
                        topo=3, geometry=GEO_TORUS_WIRE,
                        rotate_x=round(inc, 6), rotation_mode=0,
                        scale_x=s, scale_y=s, scale_z=s,
                        ratio=ratio, segments_x=segments, segments_y=6,
                        color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                        color_a=RING_ALPHA)

    def ring_label(self, raan, inc, radius_units, rgb, text, level=0):
        """A label out on the ring itself.

        A torus node sits at the origin, so putting `show_text` on the ring
        stacks every constellation's caption in one illegible pile at the
        centre of the scene — which is exactly what the first build did.
        """
        node = self._raan_node(raan, level)
        torus = self.add(type=5, parent_id=node, branch_level=level + 1,
                         topo=3, geometry=GEO_TORUS_WIRE,
                         rotate_x=round(inc, 6), rotation_mode=0,
                         ratio=0.01, scale_x=1.0, scale_y=1.0, scale_z=1.0,
                         hide=1)
        return self.add(type=5, parent_id=torus, branch_level=level + 2,
                        translate_x=90.0, translate_y=0.0,
                        translate_z=round(radius_units - BASE_SCALE, 6),
                        scale_x=2.2, scale_y=2.2, scale_z=2.2,
                        geometry=GEO_OCTA,
                        color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                        color_a=255, show_text=1, text=sanitize(text))


def build(sats, meta, args, log):
    t0 = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    jd, fr = orbits.julian(t0)
    theta = orbits.gmst_rad(jd, fr)

    ok, r_teme, v_teme, lat, lon, alt, _ = orbits.propagate(sats, t0)
    sc = ShellScene()

    # -- world + Earth ------------------------------------------------------
    sc.add(type=0, parent_id=0, branch_level=0, geometry=0,
           color_r=BG[0], color_g=BG[1], color_b=BG[2], color_a=BG[3],
           tag_color_mode=1, tag_font_size=TAG_FONT_PT,
           # No World Grid in this scene, so the viewport draws its own
           # reference lattice. Sink it into the background.
           ref_grid_color_r=14, ref_grid_color_g=15, ref_grid_color_b=26)

    # Earth spins; the orbit planes do not. Setting rotate_z to GMST puts the
    # prime meridian at its true right ascension, so the sphere's orientation
    # relative to the rings is the real one at t0 rather than a guess.
    earth_scale = R_EARTH_UNITS / BASE_SCALE
    earth_spin = SIDEREAL_DEG_PER_S * args.time_scale / RATE_CYCLES_PER_S
    earth = sc.add(type=5, parent_id=0, branch_level=0, topo=2,
                   geometry=GEO_SPHERE, texture_id=1,
                   rotate_z=round(math.degrees(theta) % 360.0, 6),
                   rotation_mode=0, rotate_rate_z=round(earth_spin, 9),
                   scale_x=earth_scale, scale_y=earth_scale, scale_z=earth_scale,
                   color_r=150, color_g=180, color_b=210, color_a=255,
                   segments_x=48, segments_y=24, show_text=0,
                   text=sanitize(
                       # To the second: verify_shells.py recovers the epoch
                       # from this label, and a minute of slop is 330 km of
                       # Iridium. Not pinned: it would sit at the origin,
                       # under everything.
                       f"Earth — inertial frame, {t0:%Y-%m-%d %H:%M:%S} "
                       f"UTC, spinning at {args.time_scale:g}x"))
    # A topology child's translate_z is an altitude in the parent's *local*
    # units, so the parent's scale multiplies it. Asking for "0.6 world units
    # above the surface" on a scale-19 Earth without dividing puts the marker
    # 11.5 units — 1,275 km — up, as a halo rather than a pin. The torus
    # satellites escape this only because their tz is zero.
    pin_tz = round(0.6 / earth_scale, 6)
    # ...and its *scale* is inherited from the parent too, so a landmark
    # authored at 0.9 under a scale-19 Earth draws at a radius of 51 world
    # units — very nearly the size of the planet it is supposed to be a pin
    # on. Divide, exactly as with translate_z. The optional minimum-glyph-size
    # clamp is measured against the RENDERED scale, not this authored one, so
    # a small number here is safe (probe_torus.py, finding 8).
    pin_scale = round(0.85 / earth_scale, 6)
    for name, la, lo in LANDMARKS:
        sc.add(type=5, parent_id=earth, branch_level=1,
               translate_x=lo, translate_y=la, translate_z=pin_tz,
               scale_x=pin_scale, scale_y=pin_scale, scale_z=pin_scale,
               geometry=GEO_OCTA,
               color_r=255, color_g=255, color_b=255, color_a=230,
               show_text=0, text=sanitize(name))

    # -- the constellations -------------------------------------------------
    by_group = defaultdict(list)
    for i, s in enumerate(sats):
        if ok[i]:
            by_group[s.group].append(i)

    summary = []
    for key, group, label, rgb in CONSTELLATIONS:
        idx = by_group.get(group, [])
        if not idx or (key == "geo" and args.no_geo):
            continue

        elems = {}
        for i in idx:
            raan, inc, u, radius = osculating_plane(r_teme[i], v_teme[i])
            elems[i] = (raan, inc, u, radius / KM_PER_UNIT)

        # Draw a ring per *distinct* orbit, not per satellite. Every satellite
        # still hangs on its own exact ring node — placement is untouched —
        # but a ring whose plane and radius already match one being drawn is
        # simply not drawn. The GEO belt is 548 orbits within 15 degrees of
        # each other; drawing all of them produced a solid pink wall that hid
        # the structure it was supposed to show. At the default tolerance the
        # deviation between a satellite and the ring it visually sits on is
        # smaller than the satellite's own glyph, so nothing reads as off its
        # path — which was the whole complaint.
        drawn_rings: list[tuple[np.ndarray, float]] = []

        def ring_is_redundant(raan, inc, radius_u):
            """Share a drawn ring only when the two orbits are closer together
            than a satellite glyph is wide.

            The tolerance is a *distance*, not an angle, and the angle it
            allows is derived per ring: `asin(tol / radius)`. A fixed angular
            tolerance would be far too loose out at GEO — half a degree there
            is 3,300 km — and needlessly tight down at Iridium's 767 km, where
            the six planes are 31 degrees apart. Working in world units means
            the guarantee is the one that matters visually: a satellite is
            never drawn further from the ring it appears to ride than the size
            of its own glyph.
            """
            a, b = math.radians(raan), math.radians(inc)
            n = np.array([math.sin(b) * math.sin(a),
                          -math.sin(b) * math.cos(a), math.cos(b)])
            tol = args.ring_tol_units
            for n0, r0 in drawn_rings:
                if abs(radius_u - r0) > tol:
                    continue
                cos = abs(float(n @ n0))
                sep = max(radius_u, r0) * math.sin(
                    math.acos(max(-1.0, min(1.0, cos))))
                if sep <= tol:
                    return True
            drawn_rings.append((n, radius_u))
            return False

        for i in idx:
            raan, inc, u, radius_u = elems[i]
            rate = (sats[i].mean_motion * 360.0 / 86400.0
                    * args.time_scale / RATE_CYCLES_PER_S)
            torus = sc.orbit_ring(raan, inc, radius_u, round(rate, 9), rgb,
                                  draw=not ring_is_redundant(raan, inc,
                                                             radius_u))
            m = meta[i]
            # The ring's scale reaches the satellite too (probe finding 8), so
            # divide it back out: a glyph of rendered radius T on a ring of
            # radius R is authored at T / R.
            gs = round(m["scale"] * args.glyph_scale / radius_u, 8)
            sc.add(type=5, parent_id=torus, branch_level=2,
                   translate_x=round(u, 5), translate_y=0.0, translate_z=0.0,
                   scale_x=gs, scale_y=gs, scale_z=gs,
                   geometry=m["geometry"],
                   color_r=rgb[0], color_g=rgb[1], color_b=rgb[2], color_a=255,
                   text=sanitize(
                       f"{sats[i].name}  |  {sats[i].norad}  |  "
                       f"{radius_u * KM_PER_UNIT - orbits.R_EARTH_EQ:,.0f} km  |  "
                       f"inc {inc:.1f} deg  |  RAAN {raan:.1f} deg  |  "
                       f"{sats[i].period_min / 60:.2f} h"),
                   link=f"https://celestrak.org/satcat/table-satcat.php"
                        f"?CATNR={sats[i].norad}")

        # Cluster into planes anyway — not to draw them, but to name them
        # and to let verify_shells.py assert that the published architecture
        # is recoverable from live data.
        groups = sorted(cluster_planes(idx, elems), key=len, reverse=True)
        drawn = sum(1 for g in groups if len(g) >= MIN_RING_MEMBERS)
        big = groups[0]
        sc.ring_label(circular_mean([elems[i][0] for i in big]),
                      float(np.mean([elems[i][1] for i in big])),
                      float(np.mean([elems[i][3] for i in big])), rgb,
                      f"{label}  —  {len(idx)} objects")
        summary.append((label, len(idx), drawn,
                        float(np.mean([elems[i][1] for i in idx])),
                        float(np.mean([elems[i][3] for i in idx]))
                        * KM_PER_UNIT - orbits.R_EARTH_EQ))
        log(f"  {label:44s} {len(idx):4d} objects, {drawn:2d} plane(s)"
            f" of {len(groups):2d} cluster(s)")

    return sc, t0, summary


# ---------------------------------------------------------------------------
# 4. Validation
# ---------------------------------------------------------------------------
def rendered_scale(row, by_id):
    """The scale a glyph actually draws at: its own, times every ancestor's.

    The authoring guidance "keep visible glyphs at scale >= 0.2" is about the
    size on screen, and the viewer's optional minimum-glyph-size clamp is
    measured against this composed value, not against the number in the row.
    For a root node or a World Grid child (grids are exempt from passing their
    scale down) the two are the same, which is why scenes 1 and 2 could check
    the raw field and be right. Here they are emphatically not the same: a
    landmark authored at 0.045 under a scale-19 Earth draws at 0.85, and one
    authored at 0.9 draws at 17 — nearly the size of the planet.
    """
    s = min(row["scale_x"], row["scale_y"], row["scale_z"])
    pid = row["parent_id"]
    seen = set()
    while pid and pid in by_id and pid not in seen:
        seen.add(pid)
        p = by_id[pid]
        s *= min(p["scale_x"], p["scale_y"], p["scale_z"])
        pid = p["parent_id"]
    return s


def validate(rows):
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate node ids")
    known = set(ids)
    by_id = {r["id"]: r for r in rows}
    for r in rows:
        if r["parent_id"] and r["parent_id"] not in known:
            raise SystemExit(f"node {r['id']}: dangling parent")
        for c in ("color_r", "color_g", "color_b", "color_a"):
            if not 0 <= r[c] <= 255:
                raise SystemExit(f"node {r['id']}: {c} = {r[c]}")
        if not r["hide"] and r["type"] == 5:
            rs = rendered_scale(r, by_id)
            if rs < 0.2:
                raise SystemExit(f"node {r['id']}: renders at {rs:.4f}, "
                                 f"below the 0.2 floor")
            # The other end of the same rule. Two things are meant to be big:
            # a torus ring, sized to the orbit it draws, and the Earth. A
            # marker that large has inherited a parent's scale.
            structural = (r["topo"] == 3 and r["geometry"] in (6, 7)) \
                or r["topo"] == 2
            if rs > 4.0 and not structural:
                raise SystemExit(
                    f"node {r['id']}: renders at {rs:.2f} "
                    f"({BASE_SCALE * rs:.1f} world units across) — a marker "
                    f"this big means it inherited a parent's scale")
        if r["topo"] == 3 and not r["hide"]:
            # Picking renders the SOLID form of a wireframe, and the torus
            # mesh is cached per ratio rounded to 2 decimals. Under 0.005 the
            # tube quantises to zero thickness: it still draws as wires, but
            # has no silhouette, so neither a click nor a rubber-band region
            # can ever select it. A ring you cannot pick is a ring you cannot
            # inspect, which is most of what a ring is for.
            if round(r["ratio"], 2) <= 0.0:
                raise SystemExit(
                    f"node {r['id']}: ratio {r['ratio']} quantises to 0 at "
                    f"2 dp — the ring would draw but be unpickable")
        if not 0 <= r["geometry"] <= 28:
            raise SystemExit(f"node {r['id']}: geometry {r['geometry']}")
        if r["rotate_rate_z"] and r["rotation_mode"] != 0:
            raise SystemExit(f"node {r['id']}: spinning node must pin "
                             f"rotation_mode=0")


def write_atomic(rows, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# 5. Main
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Build the Orbital Shells scene (self-animating rings).")
    ap.add_argument("--time-scale", type=float, default=300.0,
                    help="how much faster than real time the scene turns "
                         "(default 300: an Iridium orbit in ~20 s, a day in "
                         "~5 min, GPS in ~2.4 min)")
    ap.add_argument("--glyph-scale", type=float, default=3.0)
    ap.add_argument("--ring-tol-units", type=float, default=3.0,
                    help="two orbits closer than this anywhere around the "
                         "ring share one drawn circle, in world units "
                         "(1 unit = 111 km; 3 is about one glyph). Placement "
                         "is never shared: every satellite keeps its own "
                         "exact ring node. 0 draws all 773.")
    ap.add_argument("--no-geo", action="store_true",
                    help="drop the geostationary belt and its 568 objects")
    ap.add_argument("--fetch", action="store_true",
                    help="refresh element sets (respects the 2 h limit)")
    ap.add_argument("--out-dir", default=OUT_DIR)
    args = ap.parse_args(argv)

    log = print
    log("Orbital Shells - the architecture of near-Earth space\n")

    cache = os.path.join(HERE, "data", "gp_cache")
    rows = []
    groups = [g for _, g, _, _ in CONSTELLATIONS]
    for g in groups:
        try:
            rows += [(g, r) for r in parse_csv(
                orbits.fetch_group(g, cache, offline=not args.fetch, log=log))]
        except Exception as e:
            log(f"  ! {g}: {e} - skipped")
    seen, uniq = set(), []
    for g, r in rows:
        if r.get("NORAD_CAT_ID") and r["NORAD_CAT_ID"] not in seen:
            seen.add(r["NORAD_CAT_ID"])
            uniq.append((g, r))
    if not uniq:
        raise SystemExit("no element sets available")

    satcat = load_satcat(os.path.join(HERE, "data", "satcat.csv"),
                         offline=not args.fetch, log=log)
    sats, bad = orbits.build_sats(uniq)
    sats.sort(key=lambda s: s.norad)
    meta = []
    for s in sats:
        info = satcat.get(s.norad, {})
        meta.append({
            "owner": info.get("owner", "?"),
            "geometry": GEO_BY_TYPE.get(info.get("type", ""), GEO_UNKNOWN),
            "scale": glyph_scale(info.get("rcs"), 1.0),
        })
    log(f"{len(sats)} element sets loaded"
        + (f", {bad} rejected" if bad else "") + "\n")

    log("Constellations:")
    sc, t0, summary = build(sats, meta, args, log)
    validate(sc.rows)

    os.makedirs(os.path.join(args.out_dir, "media"), exist_ok=True)
    node_path = os.path.join(args.out_dir, f"{STEM}_node.csv")
    write_atomic(sc.rows, node_path)

    media = os.path.join(args.out_dir, "media", "01_bluemarble.png")
    if not os.path.exists(media):
        src = os.path.join(HERE, "Live_Sky", "media", "01_bluemarble.png")
        if os.path.exists(src):
            shutil.copy2(src, media)

    n_rings = sum(1 for r in sc.rows if r["topo"] == 3 and not r["hide"])
    n_sats = sum(1 for r in sc.rows if r["link"])
    log(f"\n{len(sc.rows):,} nodes: {n_sats} satellites, each on its own "
        f"exact orbit ring;\n{n_rings} of those rings drawn "
        f"({n_sats - n_rings} suppressed, indistinguishable within "
        f"{args.ring_tol_units:g} world units of another), "
        f"{len(LANDMARKS)} landmarks, 1 Earth.")
    log(f"time scale {args.time_scale:g}x — the scene turns on load; "
        f"no Channels, nothing to press.")
    log(f"\nOpen {node_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
