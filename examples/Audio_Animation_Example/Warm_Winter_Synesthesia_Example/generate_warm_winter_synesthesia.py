#!/usr/bin/env python3
"""
generate_warm_winter_synesthesia.py
====================================
GlyphViz music synesthesia — "Warm Winter" (Jeff Sale), from its SEVEN
separate Garage Band tracks.

Where Cat_Scan_Synesthesia_Example built ONE hyperglyph from a finished stereo
mix — 64 frequency bands of everything at once — this scene has the luxury of
the multitrack session.  Each of the seven keyboard tracks gets a hyperglyph of
its own, so an instrument's shape, colour and motion belong to *that
instrument* rather than to a slice of the combined spectrum.

The song's form is the composition
---------------------------------
Every track runs the full 3:47 file, but each one enters a few measures after
the previous and leaves a few measures before it — measured from the stems
themselves (-34 dB gate):

    track 1   0:00 - 3:45    track 5   1:09 - 2:38
    track 2   0:17 - 3:30    track 6   1:27 - 2:19
    track 3   0:34 - 3:12    track 7   1:44 - 2:02
    track 4   0:52 - 2:54

A perfectly nested set: ~17.4 s of stagger on each side, the climax centred at
1:53.  The scene reads that shape three ways over —

  * the seven glyphs stack straight up +Z, in playing order, all on x = y = 0;
  * each glyph's whole size is bound to its own track's loudness, so a glyph
    sits as a small dormant seed (38% size) until its instrument enters,
    blooms open while it plays, and folds back down when it drops out;
  * the WORLD itself is on a channel — background colour and fog open from a
    near-black, close winter night at the start to a pale warm dusk at the
    climax, then settle at a middle intensity for the fade-out (see
    WORLD_COLOR_RAMP: the ending is deliberately not as dark as the opening,
    because the ramp that lifts the floor only starts climbing after the
    measured peak).

Watch the column light up from the bottom, crest at track 7, and go dark again
in the same order while the sky comes back down with it.  The glyphs DO grow
into each other once the music is running; that is Jeff's call and the point —
the instruments are not isolated in the audio either.  See Z_RISE.

One glyph per track
-------------------
Each hyperglyph is Cat Scan's design — a master root whose children are
frequency bands, each band a 3-level tree with a zone personality — but the
BRANCH 0 and BRANCH 1 topologies change from track to track, which is what
makes seven copies of one recipe read as seven different instruments:

    track   branch 0    branch 1   colour            reads as
    1       Plane       Plane      pale ice blue     a flat blanket of pads
    2       Plane       Sphere     pale periwinkle   orbs laid out on a grid
    3       Sphere      Sphere     pale violet       a shell of orbs
    4       Spiral      Spiral     amber gold        a helix of helices
    5       Plane       Rod        warm orange       rods standing in a grid
    6       Rod         Zrod       scarlet           one dominating rod trunk
    7       Pin         Pin        magenta           a tapering spire

Two of those need a word.  A node whose topo is ROD is not merely a *placement*
rule — glyphviz_core/scene.py draws it 0.25x wide, 5x tall and bottom-capped,
ANTz-style, so the node literally becomes the rod its children are threaded
along.  That is why Rod appears at exactly one level per glyph: nesting Rod
inside Rod multiplies the 5x stretch at every level and the glyph collapses
into a smear of needles.  Track 5 puts it at branch 1 (each grid cell grows a
rod); track 6 puts it at branch 0 (one trunk carries all twelve bands) and
gives the bands ZROD, the rod family's centred variant, which places children
in a ring without restyling the node.

Colour follows the title.  Tracks 1-3 are pastel and cool — winter — and
saturation climbs track by track into gold, orange, scarlet and magenta for
4-7 — warm.  Branch 2 is always Sphere topology, so the leaf clusters stay
compact orbs whatever the trunk is doing.

Tracks 1 and 2 additionally carry a topo_scale (see TRACK_STYLES): track 1's
spreads its blanket ~9x wide into the floor the whole column stands on, and
track 2's opens its grid of orbs out to 3x so the spheres stop crowding each
other.  Nothing is pinned: every node carries a label in the tag CSV, and T
shows the ones you select.

The whole scene is written with the app's Global Scale baked in at 3.0, so it
opens correct at GlyphViz's own default of 1.0 — see GLOBAL_SCALE, which is
also the note to read before tuning this scene in the app again.

Per-track frequency windows
---------------------------
A single 20 Hz - 16 kHz window would leave the bass track lighting three bands
and the rest dead.  Each stem is measured for its own 5%/95% spectral rolloff
and given a window an octave wider on each side, so all 12 of a glyph's bands
are in play and the fan shows where THAT instrument lives.  The windows are
printed at generation time and listed in the README.

Structure of one glyph (715 nodes)
----------------------------------
  branch 0   master root — a wire form naming its own topology (ring for Plane,
             sphere for Sphere, torus for Spiral, cylinder for Rod, pin for
             Pin).  Its topology governs how the 12 band roots distribute.
  branch 1   12 band roots, log-spaced across that track's window
  branch 2   5-8 children per band root
  branch 3   8 children per branch-2 node

Frequency zones (3 bands each, as in Cat Scan)
----------------------------------------------
  DEEP   solid spheres + fat toruses, heavy slow scale-breathing, lazy orbits
  FLOW   dodecahedra + cylinders + cubes
  SHINE  octahedra + icosahedra, faster pinwheels
  SPARK  wire icosahedra + pins + tetras, snappiest envelopes, fastest orbits

Channel animation (4 tracks per band, 1 per glyph, 5 for the world)
-------------------------------------------------------------------
  band root   scale_x/y/z   <- envelope-followed band power (instant attack,
                               zone-tuned decay).  Scale cascades, so the whole
                               band hyperglyph breathes as one.
  branch 2    <pop axis>    <- altitude pop away from the band root.  WHICH
                               axis that is depends on the band root's
                               topology (translate_x is height under a Pin,
                               translate_z is radial/up under the rest) — see
                               ALT_AXIS.
              rotate_rate_z <- pinwheel spin speed
  branch 3    translate_rate_x <- orbital speed around its (Sphere-topology)
                               parent.  Longitude is periodic, so orbiting
                               children never fly off — loud passages just
                               orbit faster.
              rotate_rate_z <- same spin signal as branch 2
  master root scale_x/y/z   <- that track's presence: 38% dormant -> 100% at
                               that track's own loudest moment.  The file is
                               written at that 100%, which is why it opens
                               LARGER than any frame of the playback; the scene
                               is sized so a PLAYING glyph is the right size —
                               see PLAYBACK_FIT.
  world row   color_r/g/b   <- the sky, from the seven presences combined
              fog_start/end <- the mist, opening and closing with it

Only *angular* axes ever get a translate_rate: a rate on a linear axis would
integrate forever and throw the children out of the scene.

Output files (written to --out, default: this folder)
------------------------------------------------------
  Warm_Winter_Synesthesia_Example_gv_node.csv       5,006 nodes
  Warm_Winter_Synesthesia_Example_gv_tag.csv        a label on every node
  Warm_Winter_Synesthesia_Example_gv_ch-map.csv     channel -> attribute
  Warm_Winter_Synesthesia_Example_gv_ch-tracks.csv  348 tracks x ~6,800 frames
  Warm_Winter_Synesthesia_Example_gv_audio.txt      -> media/warm_winter_all.m4a

Usage
-----
  python generate_warm_winter_synesthesia.py --stems <folder with track1..7>

The stems may be .wav or .m4a (ffmpeg is used to decode .m4a into a temp WAV).
They are NOT shipped with the example — only the mixdown that plays back is.

Load in GlyphViz: File > Open Node CSV -> ..._gv_node.csv
Press Play in the Channels panel — the full mix plays in sync automatically.
"""

import argparse
import colorsys
import csv
import math
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audio_analysis import analyze, load_wav_mono   # vendored — see that file

# ===========================================================================
# Parameters
# ===========================================================================

OUTPUT_DIR = Path(__file__).parent
PREFIX     = "Warm_Winter_Synesthesia_Example"
MIX_AUDIO  = OUTPUT_DIR / "media" / "warm_winter_all.m4a"

N_TRACKS = 7
N_BANDS  = 12          # per glyph: 4 zones x 3 bands
FPS      = 30.0

# Global motion multiplier on every animated signal's amplitude (scale swell,
# altitude pop, spin, orbit) — NOT on rest sizes, which the tracks carry as
# absolute values.  Cat Scan settled at 4.0; 3.0 here because seven glyphs
# share one scene and each still has to stay recognizable at its peak.
EXAGGERATION = 3.0

# Global Scale, baked in
# ----------------------
# Jeff tunes this scene with the app's Global Scale slider at 3.0, not at its
# 1.0 default, and nothing in a node CSV records which setting a scene was
# authored against.  Rather than ship a file that only looks right with a
# slider moved by hand, the generator bakes that setting into the numbers, so
# the example opens correct at GlyphViz's own default.
#
# Global Scale (glyphviz_core/scene.py's base_scale) does exactly two things,
# and it is the SECOND one that makes this more than a size multiplier:
#
#   1. every glyph renders base_scale times larger (scale x base_scale, once
#      per node, in the draw matrix only);
#   2. it IS the parent radius term in every topology's placement formula —
#      a Sphere parent puts a child at (base_scale + translate_z), a Pin at
#      (base_scale + translate_x) up the spike, a Rod's length scales with it.
#      Purely Cartesian parents (Plane, None) have no such term at all.
#
# So Global Scale 3.0 is NOT a uniform 3x zoom: glyphs grow 3x while a Plane
# parent's children stay exactly where they were, and the seven root positions
# (a root's translate IS its world position) do not move either.  That change
# of proportion is the thing being preserved here.
#
# The exact equivalent, at base_scale = 1, is:
#
#   * multiply each ROOT's scale by GLOBAL_SCALE.  Every scale in this scene is
#     a ratio to its parent's (a band root is w_root / root_scale of its root,
#     and so on down), so one multiplication at the root makes every node in
#     the glyph render GLOBAL_SCALE times larger — exactly what base_scale did.
#   * divide every node's topo_scale by GLOBAL_SCALE.  Node.topo_scale
#     multiplies precisely the translate axes a topology reads as a DISTANCE
#     (LINEAR_AXES below), and dividing those by S is what turns f(t; S) into
#     S * f(t; 1) for every one of the offset formulas:
#         Sphere  (S + tz) . dir      -> S . (1 + tz/S) . dir
#         Pin     (ty, tz, S + tx)    -> S . (ty/S, tz/S, 1 + tx/S)
#         Spiral  (S + tz), tx.S/360  -> S . (1 + tz/S), tx/360
#         Rod     tx/180 . 2 . S . H  -> S . tx/180 . 2 . H
#         Plane   (tx, ty, tz)        -> S . (tx/S, ty/S, tz/S)
#     while angular axes (longitude, latitude, sweep) are left alone, as they
#     must be.  The root's scale, now S times larger, supplies the S outside.
#
# Dividing topo_scale rather than the translate values is also what keeps the
# CHANNEL-driven translates right for free: the altitude pops in build_tracks
# are written into translate axes that topo_scale multiplies at placement time,
# so they scale with everything else and the animation needs no change.
#
# Verified node-for-node against the real engine: the baked scene at
# base_scale = 1 reproduces the unbaked scene at base_scale = 3 to 1e-9 in both
# world position and draw matrix, for all 5,006 nodes.
#
# Consequence worth knowing: the Topo Scale the Properties panel now shows for
# a root is a THIRD of the number set on the slider (Track 1 reads 2.9708, not
# 8.9125).  The file is authored for Global Scale 1.0 — put the slider back
# there before tuning this scene again, or the bake compounds.
GLOBAL_SCALE = 3.0

# Sized for playback, not for the file's rest state
# --------------------------------------------------
# Every root is written at its own PEAK presence, because that is what the
# presence channel's top of range means — and that is a state PLAYBACK NEVER
# REACHES, since the seven tracks peak at different times.  A dormant glyph
# plays at PRESENCE_REST (38%) of it, and at frame 0 all seven are dormant, so
# pressing Play collapsed the scene to 62% of the size it opened at (Jeff's
# 2026-09-20 report: "when I click Play, they shrink back down to 1/3 their
# size").  Measured over the whole piece, a glyph holds 0.70 of its written
# peak while its own instrument is actually playing.
#
# So the scene is restated at the size a PLAYING glyph has: what you tune in
# the app is then what you watch, and the file's own rest state is the outlier
# rather than the reference.  The file therefore opens ~1.4x larger than a
# playing frame, and Stop restores that larger look.
#
# This is a multiplier on the ROOT scales only.  A root's scale carries its
# whole glyph — its own drawn size, and, through world_basis, every
# descendant's position and size — so multiplying it is a uniform zoom of that
# glyph with every internal proportion untouched.  Raising GLOBAL_SCALE would
# NOT do this: that divides topo_scale too, which grows the glyphs without
# growing their spread and packs the children tighter.  Dividing Z_RISE by the
# same factor is the exact equivalent (only the glyph-to-column ratio matters,
# the rest is camera distance); the roots carry it instead, because the column
# spacing is Jeff's own design and this is not a re-spacing.
PLAYING_FRACTION = 0.70   # measured; see build_tracks
PLAYBACK_FIT = 1.0 / PLAYING_FRACTION

# geometry ids — glyphviz_core/geometry_data.py
GEO_CUBE, GEO_SPHERE_WIRE, GEO_SPHERE   = 1, 2, 3
GEO_TORUS_WIRE, GEO_TORUS, GEO_DODECA   = 6, 7, 9
GEO_OCTA, GEO_TETRA, GEO_ICOSA_WIRE     = 11, 13, 14
GEO_ICOSA, GEO_PIN, GEO_PIN_WIRE        = 15, 16, 17
GEO_CYLINDER_WIRE, GEO_CYLINDER         = 18, 19
GEO_RING_WIRE                           = 34

# topology ids — glyphviz_core/topology.py
TOPO_SPHERE, TOPO_PIN, TOPO_ROD, TOPO_PLANE = 2, 5, 6, 8
TOPO_ZROD, TOPO_SPIRAL = 13, 14

NODE_TYPE_WORLD, NODE_TYPE_GLYPH = 0, 5

ROOT_WORLD_LO, ROOT_WORLD_HI = 0.68, 0.44   # band-root world radius, bass -> treble

# Presence: a glyph's root scale swings between these fractions of its own
# root_scale as its track fades in and out.  Cascades, so the glyph blooms.
PRESENCE_REST, PRESENCE_TAU = 0.38, 1.20

# --- the world itself is animated -------------------------------------------
# Background colour and fog follow the song's ARC, not its beat: dark and close
# while the piece is still gathering, open and pale at the climax, settled at a
# middle intensity for the long fade-out.  The asymmetry (a quiet ending is not
# as dark as the quiet opening) comes from a one-way ramp that only starts
# climbing after the measured loudest moment, so the world keeps some of the
# warmth the climax gave it.
WORLD_BASE_AFTER = 0.34   # how far that ramp lifts the floor once the peak passes
WORLD_GAIN       = 0.66   # how much the seven tracks' combined presence adds
# level -> background RGB.  Fog takes the same colour (viewport.py sets
# GL_FOG_COLOR from the World row), so the mist always matches the sky.
# The top of this ramp is deliberately restrained.  A genuinely pale sky reads
# as "lighter" for about two seconds and then costs the whole scene: tracks 1-3
# are near-white pastels by design, and against a light background they stop
# being glyphs and become smudges.  Rendered and compared — this ramp lifts the
# sky by ~5x in luminance across the song and still leaves every glyph legible.
WORLD_COLOR_RAMP = [
    (0.00, (4,  6,  14)),        # near-black winter night
    (0.35, (20, 24, 42)),        # cold twilight
    (0.70, (52, 50, 78)),        # dusk, warming
    (1.00, (86, 78, 100)),
]
# Fog is LINEAR in eye distance.  The static values — what the file opens at,
# and what Stop restores — are deliberately mild: a scene that renders as an
# empty fog bank when you first open it is a bug, not an atmosphere.
FOG_START_REST, FOG_END_REST = 300.0, 1000.0
FOG_START_RANGE, FOG_END_RANGE = (120.0, 320.0), (420.0, 1200.0)

# Scene layout: the seven glyphs stack straight up the Z axis, all seven roots
# on x = y = 0, Z_RISE apart, in playing order.
#
# The first pass spread them along an arc wide enough that no two glyphs ever
# touched.  Jeff replaced it with this column after living with it: the glyphs
# DO overlap once the music is running, "but that's the way music is — the
# instruments are not isolated from each other in the audio, they are all
# overlapping," and the column is what he actually sees in his synesthesia
# image.  So overlap here is the finding, not a defect to space away.
Z_RISE = 8.0
# What "loud" means for the printed extent report: at full band power a
# hyperglyph reaches ~3.7x its rest size, which no glyph holds for long.
LAYOUT_SWELL_FRACTION = 0.45

GOLDEN_ANGLE = 137.50776405


@dataclass(frozen=True)
class Zone:
    """One frequency zone's personality — 3 consecutive bands of every glyph."""
    name: str
    geo_l1: int; geo_l2: int; geo_l3: int
    n2: int; n3: int              # children per band root / per branch-2 node
    l2_world: float               # branch-2 world radius
    l3_world: float               # branch-3 world radius
    l2_lat: float                 # |latitude| of alternating rings (Sphere parents)
    scale_gain: float             # band-root scale swells by (1 + gain*env)
    tau_scale: float              # envelope decay (s) for that swell
    alt_peak: float               # branch-2 pop at full band power
    spin_peak: float              # rotate_rate_z deg/cycle (60 cyc/s) at full power
    orbit_peak: float             # translate_rate_x deg/cycle at full power
    ratio: float                  # geometry ratio (torus tube fatness etc.)


# Cat Scan's four zones, with its cones replaced (Jeff dislikes the cone glyph):
# SHINE's branch-2 cone -> icosahedron, its branch-3 cone -> octahedron.
ZONES = [
    Zone("DEEP",  GEO_SPHERE,     GEO_TORUS,    GEO_SPHERE, 5, 8, 0.40, 0.26,
         0.0,  0.90, 0.50, 0.70, 0.6, 0.30, 0.32),
    Zone("FLOW",  GEO_DODECA,     GEO_CYLINDER, GEO_CUBE,   6, 8, 0.37, 0.25,
         18.0, 0.75, 0.32, 0.85, 1.2, 0.70, 0.22),
    Zone("SHINE", GEO_OCTA,       GEO_ICOSA,    GEO_OCTA,   7, 8, 0.33, 0.23,
         32.0, 0.62, 0.20, 1.00, 2.2, 1.30, 0.18),
    Zone("SPARK", GEO_ICOSA_WIRE, GEO_PIN,      GEO_TETRA,  8, 8, 0.29, 0.21,
         48.0, 0.50, 0.12, 1.20, 3.5, 2.40, 0.14),
]
BANDS_PER_ZONE = N_BANDS // len(ZONES)


@dataclass(frozen=True)
class TrackStyle:
    """One track's identity: the two topologies of its trunk, and its colour."""
    name: str
    topo0: int                    # branch 0 — distributes the 12 band roots
    topo1: int                    # branch 1 — distributes each band's children
    root_geo: int                 # wire form naming the branch-0 topology
    root_scale: float             # the root's world radius = 1 root-local unit
    band_scale: float             # multiplies every band root's world radius
    topo_scale: float             # spreads the band roots along the root's
                                  # LINEAR axes only (Node.topo_scale)
    hue: float                    # base hue; slides +/- HUE_SPREAD across bands
    sat: float
    val: float


# Pastel and cool for the tracks that open and close the piece; saturated and
# warm for the ones that build the middle.  ("Warm Winter", both halves of it.)
#
# Rod appears at ONE level per glyph and never two — see the module docstring.
# root_scale is set by what the branch-0 geometry does with it: a Rod node
# renders 10x its scale tall, so track 6's is small; a Pin renders only 1.1x
# tall and its band roots have to ride that shaft, so track 7's is large.
# Tracks 6 and 7 string their bands along a line rather than spreading them
# over a surface, which makes a thin glyph — band_scale gives the two climax
# tracks back the visual weight that costs them.
#                                                                     root  band  topo
#                                                                     scale scale scale   hue   sat   val
TRACK_STYLES = [
    TrackStyle("Track 1", TOPO_PLANE,  TOPO_PLANE,  GEO_RING_WIRE,     2.5, 1.00, 8.912509381, 0.550, 0.28, 0.93),
    TrackStyle("Track 2", TOPO_PLANE,  TOPO_SPHERE, GEO_RING_WIRE,     2.5, 1.00, 3.000000000, 0.680, 0.34, 0.90),
    TrackStyle("Track 3", TOPO_SPHERE, TOPO_SPHERE, GEO_SPHERE_WIRE,   2.5, 1.00, 1.000000000, 0.800, 0.40, 0.92),
    TrackStyle("Track 4", TOPO_SPIRAL, TOPO_SPIRAL, GEO_TORUS_WIRE,    2.5, 1.00, 1.000000000, 0.125, 0.74, 1.00),
    TrackStyle("Track 5", TOPO_PLANE,  TOPO_ROD,    GEO_RING_WIRE,     2.5, 1.00, 1.000000000, 0.070, 0.86, 1.00),
    TrackStyle("Track 6", TOPO_ROD,    TOPO_ZROD,   GEO_CYLINDER_WIRE, 1.9, 1.30, 1.000000000, 0.010, 0.93, 1.00),
    TrackStyle("Track 7", TOPO_PIN,    TOPO_PIN,    GEO_PIN_WIRE,      9.0, 1.30, 1.000000000, 0.905, 1.00, 1.00),
]
# The two topo_scales are Jeff's, set on the Topo Scale log slider in the
# Properties panel.  Plane reads all three translate axes as distances, so
# track 1's spreads that glyph's 4x3 blanket ~9x wide — the pad that holds the
# whole song becomes the floor the column stands on — and track 2's opens its
# grid of orbs out to 3x, which is what stops them crowding once Global Scale
# has grown every sphere.  These are the numbers AS SET ON THE SLIDER; each is
# divided by GLOBAL_SCALE on its way into the file.
HUE_SPREAD = 0.045    # hue slide from the glyph's lowest band to its highest

TOPO_LABELS = {TOPO_PLANE: "Plane", TOPO_SPHERE: "Sphere", TOPO_SPIRAL: "Spiral",
               TOPO_ROD: "Rod", TOPO_ZROD: "Zrod", TOPO_PIN: "Pin"}


# ===========================================================================
# Placement — the one place per-topology layout lives
# ===========================================================================
#
# Every offset below is in the PARENT's own local units, which is exactly what
# glyphviz_core/topology.py's offset functions consume: their placement radius
# term is the global base_scale (1.0), and the parent's world scale is applied
# afterwards by its world_basis.  So "1.0" means "one parent radius", whatever
# the parent's actual size.
#
# level1(topo, n)      — where a root of that topology puts its 12 band roots
# level2(topo, n, lat) — where a band root of that topology puts its children
#
# ALT_AXIS names the axis a branch-2 child pops along when its band gets loud,
# and its resting value.  The axis has to MEAN "away from the parent" under
# that topology: translate_z is radial (Sphere/Spiral/Rod/Zrod) or up (Plane),
# but under a Pin the height axis is translate_x and translate_z is lateral.
# The rest value must be the SAME for every branch-2 node of a band, because
# they all share one channel.

# Which translate axes each topology reads as a DISTANCE rather than an angle —
# i.e. the ones a parent's topo_scale multiplies.  Mirrors
# glyphviz_core/topology.py's LINEAR_PLACEMENT_AXES for the six topologies this
# scene uses; kept here so the generator stays standalone.
LINEAR_AXES: dict[int, tuple[bool, bool, bool]] = {
    TOPO_PLANE:  (True,  True,  True),     # all three are plain offsets
    TOPO_SPHERE: (False, False, True),     # lon, lat, altitude
    TOPO_SPIRAL: (False, True,  True),     # helix angle, rise, radial
    TOPO_ROD:    (False, False, True),     # length fraction, angle, radial
    TOPO_ZROD:   (False, True,  True),     # angle, height, radial
    TOPO_PIN:    (True,  True,  True),     # height and two lateral offsets
}

ALT_AXIS: dict[int, tuple[str, float]] = {
    TOPO_PLANE:  ("translate_z", 0.00),
    TOPO_SPHERE: ("translate_z", 0.00),
    TOPO_SPIRAL: ("translate_z", 0.55),
    TOPO_ROD:    ("translate_z", 0.55),    # radial distance from the rod's axis
    TOPO_ZROD:   ("translate_z", 1.35),
    TOPO_PIN:    ("translate_x", -0.30),   # height along the spike
}


def level1(topo: int, n: int) -> list[tuple[float, float, float]]:
    """Where a glyph root of *topo* places its n band roots."""
    if topo == TOPO_PLANE:
        step = 1.25                                   # a flat 4 x 3 blanket
        return [(((i % 4) - 1.5) * step, (1 - i // 4) * step, 0.0) for i in range(n)]
    if topo == TOPO_SPHERE:
        return [((i * GOLDEN_ANGLE) % 360.0,
                 math.degrees(math.asin(2.0 * (i + 0.5) / n - 1.0)), 0.85)
                for i in range(n)]                    # Fibonacci shell, bass at the pole
    if topo == TOPO_SPIRAL:
        turn = 88.0
        centre = (n - 1) * turn / 360.0 / 2.0         # translate_x is sweep AND rise
        return [(i * turn, -centre, 0.75) for i in range(n)]
    if topo == TOPO_ROD:
        # translate_x runs the rod's length: 0..180 maps to the whole rendered
        # rod, which is bottom-capped at the node's own position.
        return [(8.0 + i * (164.0 / (n - 1)), (i * GOLDEN_ANGLE) % 360.0, 0.60)
                for i in range(n)]
    if topo == TOPO_PIN:
        # A child sits at (1 + translate_x) up the spike, so tx in [-0.9, 0.1]
        # rides the shaft; the ring tapers so the glyph comes to a point.
        out = []
        for i in range(n):
            r = 0.45 - i * (0.43 / (n - 1))
            a = math.radians((i * GOLDEN_ANGLE) % 360.0)
            out.append((-0.92 + i * (0.98 / (n - 1)), r * math.cos(a), r * math.sin(a)))
        return out
    raise ValueError(f"no level-1 placement for topo {topo}")


def level2(topo: int, n: int, lat: float) -> list[tuple[float, float, float]]:
    """Where a band root of *topo* places its branch-2 children."""
    if topo == TOPO_PLANE:
        return [(1.55 * math.cos(math.radians(j * 360.0 / n)),
                 1.55 * math.sin(math.radians(j * 360.0 / n)), 0.0) for j in range(n)]
    if topo == TOPO_SPHERE:
        return [(j * 360.0 / n, lat * (1 if j % 2 == 0 else -1), 0.0) for j in range(n)]
    if topo == TOPO_SPIRAL:
        return [(j * 360.0 / n, -0.5, 0.55) for j in range(n)]
    if topo == TOPO_ROD:
        return [(12.0 + j * (156.0 / max(n - 1, 1)), j * 360.0 / n, 0.55)
                for j in range(n)]                    # beads threaded up the rod
    if topo == TOPO_ZROD:
        return [(j * 360.0 / n, 0.0, 1.35) for j in range(n)]   # angle, height, radius
    if topo == TOPO_PIN:
        return [(-0.30, 1.40 * math.cos(math.radians(j * 360.0 / n)),
                 1.40 * math.sin(math.radians(j * 360.0 / n))) for j in range(n)]
    raise ValueError(f"no level-2 placement for topo {topo}")


def level3(z: Zone) -> list[tuple[float, float, float]]:
    """Branch-3 children sit on their branch-2 parent's unit sphere (branch 2
    is always Sphere topology, whatever the trunk is doing)."""
    return [(k * 360.0 / z.n3,
             12.0 * (1 if k % 2 == 0 else -1) if z.l2_lat > 20 else 0.0,
             0.0) for k in range(z.n3)]


def topo_offset(topo: int, tx: float, ty: float, tz: float) -> tuple[float, float, float]:
    """The parent-local offset glyphviz_core/topology.py computes for a child at
    (tx, ty, tz) under a parent of this topology, with base_scale = 1.

    Mirrors _batched_topo_offsets for the six topologies this scene uses; kept
    here so the generator stays standalone (no glyphviz_core import).
    """
    if topo == TOPO_SPHERE:
        lon, lat, r = math.radians(tx), math.radians(ty), 1.0 + tz
        return (r * math.cos(lat) * math.cos(lon), r * math.cos(lat) * math.sin(lon),
                r * math.sin(lat))
    if topo == TOPO_ROD:
        a = math.radians(ty)
        return (tz * math.cos(a), tz * math.sin(a), (tx / 180.0) * 2.0 * 5.0)
    if topo == TOPO_ZROD:
        a = math.radians(tx)
        return (tz * math.cos(a), tz * math.sin(a), ty)
    if topo == TOPO_PIN:
        return (ty, tz, 1.0 + tx)
    if topo == TOPO_SPIRAL:
        th, r = math.radians(tx), 1.0 + tz
        return (r * math.cos(th), r * math.sin(th), tx / 360.0 + ty)
    return (tx, ty, tz)          # Plane / None — Cartesian


# Channel / track id scheme (1-indexed, glyph t = 0..6):
#   channels  t*37 + 3i+1 (band root scale), +2 (branch 2), +3 (branch 3)
#             t*37 + 37   (glyph presence);  7*37 + 1 = 260  (the world)
#   tracks    t*49 + 4i+1 (scale), +2 (pop), +3 (spin), +4 (orbit)
#             t*49 + 49   (presence);  7*49 + 1..5 = 344..348  (the world)
CH_PER_GLYPH, TRK_PER_GLYPH = 3 * N_BANDS + 1, 4 * N_BANDS + 1
CH_WORLD = N_TRACKS * CH_PER_GLYPH + 1
TRK_WORLD = N_TRACKS * TRK_PER_GLYPH + 1          # first of five
N_TRACKS_TOTAL = TRK_WORLD + 4


# ===========================================================================
# Signal shaping
# ===========================================================================

def envelope(p: np.ndarray, fps: float, tau: float) -> np.ndarray:
    """Peak-follower: instant attack, exponential decay over tau seconds."""
    decay = math.exp(-1.0 / (fps * tau))
    env = np.empty_like(p)
    e = 0.0
    for t in range(len(p)):
        e = max(float(p[t]), e * decay)
        env[t] = e
    return env


def zone_of_band(i: int) -> Zone:
    return ZONES[min(i // BANDS_PER_ZONE, len(ZONES) - 1)]


def band_root_world(style: TrackStyle, i: int) -> float:
    """Band root i's world radius — bass bulky, treble small."""
    return (ROOT_WORLD_LO + (ROOT_WORLD_HI - ROOT_WORLD_LO) * (i / (N_BANDS - 1))
            ) * style.band_scale


def root_scale_written(style: TrackStyle) -> float:
    """The scale a glyph root is actually written with.

    style.root_scale stays the scene's design number — "this root is one
    root-local unit, and its world radius" — because every scale below it is a
    ratio measured against it (band roots divide by it, and the presence
    channel is expressed in it).  Both whole-scene multipliers are applied
    here, at the one node per glyph where multiplying makes the whole glyph
    render larger without touching a single ratio: the Global Scale bake
    (GLOBAL_SCALE) and the playback fit (PLAYBACK_FIT).
    """
    return style.root_scale * GLOBAL_SCALE * PLAYBACK_FIT


def linear_scaled(topo: int, t: tuple[float, float, float], k: float
                  ) -> tuple[float, float, float]:
    """Multiply only the axes *topo* reads as a distance, leaving angles alone
    — what a parent's Node.topo_scale does at placement time.  Mirrors
    glyphviz_core/topology.py's scale_linear_axes; see LINEAR_AXES."""
    ax, ay, az = LINEAR_AXES[topo]
    return (t[0] * k if ax else t[0],
            t[1] * k if ay else t[1],
            t[2] * k if az else t[2])


def band_colors(style: TrackStyle, i: int) -> tuple[tuple[int, int, int], ...]:
    """(branch1, branch2, branch3) RGB for band i of this track: the track's own
    hue slides slightly with frequency, value deepens toward the core and
    brightens/desaturates at the tips."""
    f = i / (N_BANDS - 1)
    hue = (style.hue - HUE_SPREAD + 2 * HUE_SPREAD * f) % 1.0
    levels = [
        (hue, style.sat,        min(1.0, style.val * 0.78)),
        (hue, style.sat,        style.val),
        (hue, style.sat * 0.45, min(1.0, style.val + 0.22)),
    ]
    return tuple(tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h, s, v))
                 for h, s, v in levels)


def world_color(level: float) -> tuple[float, float, float]:
    """Background (and fog) colour for a world intensity in [0, 1]."""
    level = min(max(level, 0.0), 1.0)
    for (a, ca), (b, cb) in zip(WORLD_COLOR_RAMP, WORLD_COLOR_RAMP[1:]):
        if level <= b:
            f = 0.0 if b == a else (level - a) / (b - a)
            return tuple(ca[k] + (cb[k] - ca[k]) * f for k in range(3))
    return tuple(float(c) for c in WORLD_COLOR_RAMP[-1][1])


# ===========================================================================
# Audio
# ===========================================================================

def to_wav(path: Path, tmpdir: Path) -> Path:
    """Return a WAV for *path*, decoding through ffmpeg if it isn't one."""
    try:
        with wave.open(str(path), 'rb'):
            return path
    except Exception:
        pass
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit(f"{path.name} is not a WAV and ffmpeg is not on PATH.")
    out = tmpdir / (path.stem + ".wav")
    subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(path), "-vn",
                    "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", str(out)],
                   check=True)
    return out


def find_stems(folder: Path) -> list[Path]:
    stems = []
    for i in range(1, N_TRACKS + 1):
        hit = [p for ext in (".wav", ".m4a", ".mp3", ".aif", ".aiff", ".flac")
               for p in (folder / f"track{i}{ext}",) if p.is_file()]
        if not hit:
            raise SystemExit(f"No track{i}.* found in {folder}")
        stems.append(hit[0])
    return stems


def stem_profile(wav: Path) -> tuple[float, float, float, float, float]:
    """(f_lo, f_hi, centroid, enter_s, exit_s) for one stem.

    The window is that stem's own 5%/95% spectral rolloff widened an octave each
    way — so all 12 of its glyph's bands carry signal, instead of most of them
    sitting dead below a bass part or above a mid one.
    """
    x, sr = load_wav_mono(wav)
    hop = sr // 10
    n = len(x) // hop
    e = np.array([np.sqrt(np.mean(x[k * hop:(k + 1) * hop] ** 2)) for k in range(n)])
    on = np.where(e > e.max() * 0.02)[0]        # -34 dB relative to this stem
    enter_s = on[0] / 10.0 if len(on) else 0.0
    exit_s = (on[-1] + 1) / 10.0 if len(on) else len(x) / sr

    seg = x[on[0] * hop: min(len(x), (on[-1] + 1) * hop)] if len(on) else x
    win = 8192
    cent, lo, hi = [], [], []
    for s in range(0, max(1, len(seg) - win), win * 8):
        spec = np.abs(np.fft.rfft(seg[s:s + win] * np.hanning(win)))
        if spec.sum() <= 0:
            continue
        freqs = np.fft.rfftfreq(win, 1.0 / sr)
        cent.append((spec * freqs).sum() / spec.sum())
        c = np.cumsum(spec ** 2)
        c /= c[-1]
        lo.append(freqs[np.searchsorted(c, 0.05)])
        hi.append(freqs[np.searchsorted(c, 0.95)])
    f_lo = max(30.0, float(np.median(lo)) / 2.0) if lo else 40.0
    f_hi = min(16000.0, float(np.median(hi)) * 2.0) if hi else 8000.0
    f_hi = max(f_hi, f_lo * 16.0)               # never narrower than 4 octaves
    return f_lo, f_hi, float(np.median(cent)) if cent else 0.0, enter_s, exit_s


# ===========================================================================
# Layout — how far apart the seven glyphs have to stand
# ===========================================================================

def glyph_extent(style: TrackStyle) -> tuple[float, float, float]:
    """(horizontal radius, min z, max z) of one glyph in world units, at a
    loud-but-not-peak frame (see LAYOUT_SWELL_FRACTION).

    Bounds the real cascade rather than guessing it: a branch-2 child sits
    `band-root world radius x |offset|` from its band root, its own radius is
    l2_world x swell, and its branch-3 children add one more of each.  Per
    axis, not as one magnitude — a Rod band root is a tall thin needle whose
    children reach ~9 parent-radii along Z and half a radius across.

    Nothing is placed from this any more (the glyphs stack on one axis); it is
    the generator's own report of how much room each glyph asks for, which is
    the number to look at when a topology or a topo_scale changes.

    Reported in the units the file is written in, i.e. with the Global Scale
    bake applied: sizes carry GLOBAL_SCALE, the linear placement axes carry its
    reciprocal (see GLOBAL_SCALE).  Compare these numbers against Z_RISE, which
    the bake does NOT touch — a root's translate is its world position.
    """
    alt_attr, _rest = ALT_AXIS[style.topo1]
    root_s = root_scale_written(style)
    k1 = style.topo_scale / GLOBAL_SCALE      # the root's written topo_scale
    k2 = 1.0 / GLOBAL_SCALE                   # every band root's
    radial, z_lo, z_hi = 0.0, 0.0, 0.0
    for i, off1 in enumerate(level1(style.topo0, N_BANDS)):
        z = zone_of_band(i)
        swell = 1.0 + LAYOUT_SWELL_FRACTION * EXAGGERATION * z.scale_gain
        cx, cy, cz = (c * root_s for c in topo_offset(
            style.topo0, *linear_scaled(style.topo0, off1, k1)))

        w_root = band_root_world(style, i) * GLOBAL_SCALE * swell
        pop = LAYOUT_SWELL_FRACTION * EXAGGERATION * z.alt_peak
        d_xy = d_z = 0.0
        for (ax, ay, az) in level2(style.topo1, z.n2, z.l2_lat):
            if alt_attr == "translate_x":
                ax += pop
            else:
                az += pop
            ox, oy, oz = topo_offset(
                style.topo1, *linear_scaled(style.topo1, (ax, ay, az), k2))
            d_xy = max(d_xy, math.hypot(ox, oy))
            d_z = max(d_z, abs(oz))
        tips = (z.l2_world + 2.0 * z.l3_world) * GLOBAL_SCALE * swell
        radial = max(radial, math.hypot(cx, cy) + w_root * d_xy + tips)
        z_lo = min(z_lo, cz - w_root * d_z - tips)
        z_hi = max(z_hi, cz + w_root * d_z + tips)
    return radial, z_lo, z_hi


def glyph_positions() -> list[tuple[float, float, float]]:
    """World positions for the seven glyph roots: a column on x = y = 0,
    Z_RISE apart, centred on the origin — see Z_RISE for why they stack."""
    mid = (N_TRACKS - 1) / 2.0
    return [(0.0, 0.0, (k - mid) * Z_RISE) for k in range(N_TRACKS)]


# ===========================================================================
# File writers
# ===========================================================================

NODE_FIELDS = [
    "id", "type", "parent_id", "branch_level",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo", "topo_scale", "ratio", "ch_input_id",
    "fog_enabled", "fog_start", "fog_end",
]
# No show_text column: nothing is pinned.  Every node still carries a label in
# the companion tag CSV — press T, or "Show Tag Labels of Selected", to read
# them.  Seven always-on root labels were pinned in the first pass and Jeff
# turned them off; a pin cannot be cleared from the viewport, only from the file.


def _row(node_id, parent_id, level, t, scale, color, alpha, geometry, topo,
         ratio, ch_input_id, topo_scale=1.0, node_type=NODE_TYPE_GLYPH, fog=None):
    r, g, b = color
    fog_on, fog_a, fog_b = fog if fog else (0, 0.0, 0.0)
    return {
        "id": node_id, "type": node_type, "parent_id": parent_id,
        "branch_level": level,
        "translate_x": round(t[0], 4), "translate_y": round(t[1], 4),
        "translate_z": round(t[2], 4),
        "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
        "scale_x": round(scale, 5), "scale_y": round(scale, 5),
        "scale_z": round(scale, 5),
        "color_r": int(r), "color_g": int(g), "color_b": int(b), "color_a": alpha,
        "geometry": geometry, "hide": 0, "topo": topo,
        # topo_scale carries the Global Scale bake for the whole file — see
        # GLOBAL_SCALE.  A node's own value is "how far one translate unit
        # reaches on the axes my topology reads as a distance", and a parent
        # radius that just grew GLOBAL_SCALE times over is exactly what makes
        # one unit reach GLOBAL_SCALE times less far.
        "topo_scale": round(topo_scale / GLOBAL_SCALE, 9), "ratio": ratio,
        "ch_input_id": ch_input_id,
        "fog_enabled": fog_on, "fog_start": fog_a, "fog_end": fog_b,
    }


def fmt_time(s: float) -> str:
    return f"{int(s) // 60}:{int(s) % 60:02d}"


def build_nodes(windows) -> tuple[list[dict], list[dict]]:
    """Returns (node rows, tag rows) — every node gets a label, per house style."""
    rows = [_row(1, 0, 0, (0.0, 0.0, 0.0), 1.0, world_color(0.0), 255, 0, 0, 0.1,
                 CH_WORLD, node_type=NODE_TYPE_WORLD,
                 fog=(1, FOG_START_REST, FOG_END_REST))]
    tags = [{"id": 0, "table_id": 0, "record_id": 1,
             "title": "Warm Winter — world: background colour and fog, both animated"}]
    positions = glyph_positions()
    next_id = 2

    for t, style in enumerate(TRACK_STYLES):
        f_lo, f_hi, freqs, enter_s, exit_s = windows[t]
        base_ch = t * CH_PER_GLYPH

        root_id = next_id
        next_id += 1
        root_rgb = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(
            style.hue, style.sat * 0.6, style.val * 0.55))
        rows.append(_row(root_id, 0, 0, positions[t], root_scale_written(style), root_rgb,
                         70, style.root_geo, style.topo0, 0.1,
                         base_ch + CH_PER_GLYPH, topo_scale=style.topo_scale))
        tags.append({"id": len(tags), "table_id": 0, "record_id": root_id,
                     "title": f"{style.name} — {TOPO_LABELS[style.topo0]} of "
                              f"{TOPO_LABELS[style.topo1]} — {f_lo:.0f}-{f_hi:.0f} Hz "
                              f"— plays {fmt_time(enter_s)}–{fmt_time(exit_s)}"})

        band_offsets = level1(style.topo0, N_BANDS)
        for i in range(N_BANDS):
            z = zone_of_band(i)
            c1, c2, c3 = band_colors(style, i)
            w_root = band_root_world(style, i)
            ch_root = base_ch + 3 * i + 1
            ch_l2, ch_l3 = ch_root + 1, ch_root + 2
            band_label = f"{style.name} b{i:02d} · {freqs[i]:.0f} Hz · {z.name}"

            band_id = next_id
            next_id += 1
            rows.append(_row(band_id, root_id, 1, band_offsets[i],
                             w_root / style.root_scale, c1, 255, z.geo_l1,
                             style.topo1, z.ratio, ch_root))
            tags.append({"id": len(tags), "table_id": 0, "record_id": band_id,
                         "title": band_label})

            for j, off2 in enumerate(level2(style.topo1, z.n2, z.l2_lat)):
                l2_id = next_id
                next_id += 1
                rows.append(_row(l2_id, band_id, 2, off2, z.l2_world / w_root,
                                 c2, 255, z.geo_l2, TOPO_SPHERE, z.ratio, ch_l2))
                tags.append({"id": len(tags), "table_id": 0, "record_id": l2_id,
                             "title": f"{band_label} · arm {j + 1}"})

                for k, off3 in enumerate(level3(z)):
                    l3_id = next_id
                    next_id += 1
                    rows.append(_row(l3_id, l2_id, 3, off3,
                                     z.l3_world / z.l2_world, c3, 255,
                                     z.geo_l3, 0, z.ratio, ch_l3))
                    tags.append({"id": len(tags), "table_id": 0, "record_id": l3_id,
                                 "title": f"{band_label} · arm {j + 1} · {k + 1}"})
    return rows, tags


def build_ch_map() -> list[dict]:
    rows, rid = [], 0

    def add(ch, track, attr):
        nonlocal rid
        rows.append({"id": rid, "channel_id": ch, "track_id": track,
                     "attribute": attr, "track_table_id": 0,
                     "ch_map_table_id": 0, "record_id": 0})
        rid += 1

    for t, style in enumerate(TRACK_STYLES):
        alt_attr, _rest = ALT_AXIS[style.topo1]
        base_ch, base_tr = t * CH_PER_GLYPH, t * TRK_PER_GLYPH
        for i in range(N_BANDS):
            t_scale, t_alt = base_tr + 4 * i + 1, base_tr + 4 * i + 2
            t_spin, t_orbit = base_tr + 4 * i + 3, base_tr + 4 * i + 4
            for attr in ("scale_x", "scale_y", "scale_z"):
                add(base_ch + 3 * i + 1, t_scale, attr)
            add(base_ch + 3 * i + 2, t_alt, alt_attr)
            add(base_ch + 3 * i + 2, t_spin, "rotate_rate_z")
            add(base_ch + 3 * i + 3, t_orbit, "translate_rate_x")
            add(base_ch + 3 * i + 3, t_spin, "rotate_rate_z")
        for attr in ("scale_x", "scale_y", "scale_z"):
            add(base_ch + CH_PER_GLYPH, base_tr + TRK_PER_GLYPH, attr)

    for k, attr in enumerate(("color_r", "color_g", "color_b",
                              "fog_start", "fog_end")):
        add(CH_WORLD, TRK_WORLD + k, attr)
    return rows


def build_tracks(per_track_bands: list[np.ndarray]) -> tuple[np.ndarray, float]:
    """Returns (track values, seconds at which the world reaches its peak)."""
    n_frames = min(a.shape[0] for a in per_track_bands)
    out = np.zeros((n_frames, N_TRACKS_TOTAL), dtype=np.float64)
    presences = []
    for t, style in enumerate(TRACK_STYLES):
        _alt_attr, alt_rest = ALT_AXIS[style.topo1]
        bands = per_track_bands[t][:n_frames]
        base_tr = t * TRK_PER_GLYPH
        for i in range(N_BANDS):
            z = zone_of_band(i)
            p = bands[:, i]
            env_scale = envelope(p, FPS, z.tau_scale)
            env_alt = envelope(p, FPS, max(0.08, z.tau_scale * 0.5))
            rest = band_root_world(style, i) / style.root_scale
            out[:, base_tr + 4 * i + 0] = rest * (1.0 + EXAGGERATION * z.scale_gain * env_scale)
            out[:, base_tr + 4 * i + 1] = alt_rest + EXAGGERATION * z.alt_peak * env_alt
            out[:, base_tr + 4 * i + 2] = EXAGGERATION * z.spin_peak * p
            out[:, base_tr + 4 * i + 3] = EXAGGERATION * z.orbit_peak * p
        loud = bands.mean(axis=1)
        if loud.max() > 0:
            loud = loud / loud.max()
        presence = envelope(loud, FPS, PRESENCE_TAU)
        presences.append(presence)
        out[:, base_tr + TRK_PER_GLYPH - 1] = root_scale_written(style) * (
            PRESENCE_REST + (1.0 - PRESENCE_REST) * presence)

    # --- the world: dark -> pale at the peak -> a settled middle ------------
    intensity = np.mean(presences, axis=0)
    if intensity.max() > 0:
        intensity = intensity / intensity.max()
    peak = int(np.argmax(intensity))
    tail = max(1, n_frames - 1 - peak)
    ramp = np.clip((np.arange(n_frames) - peak) / tail, 0.0, 1.0)
    level = np.clip(WORLD_BASE_AFTER * ramp + WORLD_GAIN * intensity, 0.0, 1.0)
    rgb = np.array([world_color(v) for v in level])
    out[:, TRK_WORLD - 1:TRK_WORLD + 2] = rgb
    out[:, TRK_WORLD + 2] = FOG_START_RANGE[0] + level * (FOG_START_RANGE[1] - FOG_START_RANGE[0])
    out[:, TRK_WORLD + 3] = FOG_END_RANGE[0] + level * (FOG_END_RANGE[1] - FOG_END_RANGE[0])
    return out, peak / FPS


def write_csv(path: Path, fields: list[str], rows: list[dict], note: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: {note}")


def write_ch_tracks(path: Path, out: np.ndarray) -> None:
    n_frames, n_tracks = out.shape
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cyclecount"] + [f"ch{i + 1}" for i in range(n_tracks)])
        for j in range(n_frames):
            w.writerow([j] + [f"{v:.4f}" for v in out[j]])
    print(f"  {path.name}: {n_frames} frames x {n_tracks} tracks")


def write_audio_manifest(path: Path, wav_path: Path, out_dir: Path) -> None:
    rel = os.path.relpath(wav_path.resolve(), out_dir.resolve())
    path.write_text(rel.replace("\\", "/") + "\n", encoding="utf-8")
    print(f"  {path.name}: -> {rel}")


# ===========================================================================
# Pipeline
# ===========================================================================

def generate(stems_dir: Path, out_dir: Path, mix_wav: Path):
    stems = find_stems(stems_dir)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        wavs = [to_wav(p, tmp) for p in stems]

        print(f"Profiling {N_TRACKS} stems from {stems_dir}\n")
        print(f"  {'stem':10} {'window':>16} {'centroid':>9} {'plays':>14}")
        windows, per_track = [], []
        for t, w in enumerate(wavs):
            f_lo, f_hi, centroid, enter_s, exit_s = stem_profile(w)
            bands, freqs, dur = analyze(w, n_bands=N_BANDS, fps=FPS,
                                        f_lo=f_lo, f_hi=f_hi)
            windows.append((f_lo, f_hi, freqs, enter_s, exit_s))
            per_track.append(bands)
            print(f"  {stems[t].stem:10} {f_lo:6.0f}-{f_hi:<7.0f} Hz {centroid:8.0f} Hz "
                  f"{fmt_time(enter_s):>6}-{fmt_time(exit_s):<6}  {bands.shape[0]} frames")

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nWriting {PREFIX} to {out_dir}/\n")
    node_rows, tag_rows = build_nodes(windows)
    write_csv(out_dir / f"{PREFIX}_gv_node.csv", NODE_FIELDS, node_rows,
              f"{len(node_rows)} nodes (1 world + {N_TRACKS} glyphs of "
              f"{(len(node_rows) - 1) // N_TRACKS} objects)")
    write_csv(out_dir / f"{PREFIX}_gv_tag.csv",
              ["id", "table_id", "record_id", "title"], tag_rows,
              f"{len(tag_rows)} labels (one per node)")
    write_csv(out_dir / f"{PREFIX}_gv_ch-map.csv",
              ["id", "channel_id", "track_id", "attribute", "track_table_id",
               "ch_map_table_id", "record_id"], build_ch_map(),
              f"{CH_WORLD} channels ({N_TRACKS} glyphs + the world)")
    values, peak_s = build_tracks(per_track)
    write_ch_tracks(out_dir / f"{PREFIX}_gv_ch-tracks.csv", values)
    write_audio_manifest(out_dir / f"{PREFIX}_gv_audio.txt", mix_wav, out_dir)

    print(f"\nWorld peaks at {fmt_time(peak_s)}; sky runs "
          f"{tuple(int(c) for c in world_color(0.0))} -> "
          f"{tuple(int(c) for c in world_color(WORLD_GAIN))} -> "
          f"{tuple(int(c) for c in world_color(WORLD_BASE_AFTER))}")
    print("\nGlyph layout (world):")
    for style, pos in zip(TRACK_STYLES, glyph_positions()):
        r, z_lo, z_hi = glyph_extent(style)
        print(f"  {style.name}  {TOPO_LABELS[style.topo0]:6}/{TOPO_LABELS[style.topo1]:6} at "
              f"({pos[0]:7.1f},{pos[1]:7.1f},{pos[2]:7.1f})  "
              f"radius {r:5.1f}  z {z_lo:6.1f}..{z_hi:5.1f}")
    return windows


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Warm Winter multitrack synesthesia")
    ap.add_argument("--stems", type=Path, default=OUTPUT_DIR / "stems",
                    help="folder holding track1..track7 (.wav or .m4a)")
    ap.add_argument("--out", type=Path, default=OUTPUT_DIR)
    ap.add_argument("--mix", type=Path, default=MIX_AUDIO,
                    help="the full mixdown that plays back in sync")
    args = ap.parse_args()

    generate(args.stems, args.out, args.mix)

    print(f"\nDone.  Open GlyphViz, then:")
    print(f"  File > Open Node CSV -> {PREFIX}_gv_node.csv")
    print(f"  Press Play — the full mix plays in sync while each glyph blooms")
    print(f"  open as its own track enters and the sky opens with them.")
