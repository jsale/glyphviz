#!/usr/bin/env python3
"""
capture_example_shots.py
========================
Generate one screenshot per shipped example for the docs Examples Gallery
(glyphviz-docs/docs/examples/), by loading each scene through the real
MainWindow loader (File > Open / Import PDB code paths — companion tag,
channel, and media files come along exactly as they do for a user) and
grabbing the auto-framed viewport.

Shares the Capture window helper with capture_tour_shots.py. Like that
script, running this briefly opens a real window on the desktop; it drives
no input.

Usage:
    python tools/capture_example_shots.py                 # everything
    python tools/capture_example_shots.py --only rss-news topology
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtWidgets import QApplication

from capture_tour_shots import Capture, pump   # noqa: E402  (same folder)

OUT_DIR = REPO_ROOT / "glyphviz-docs" / "docs" / "assets" / "examples"
EX = REPO_ROOT / "examples"
# The 5-D Lorenz scenes live in their lab folder, not under examples/; their
# scene folders are gitignored and regenerate with the lab's generate_*.py.
L5 = REPO_ROOT / "lorenz5d_feedback_lab"
# Likewise the tensor lab (regenerate with tensor_lab/generate_*.py).
TL = REPO_ROOT / "tensor_lab"

# (slug, scene folder, explicit file or None). None -> the folder's single
# *node*.csv. A .pdb file goes through the PDB import path instead.
MANIFEST = [
    ("topology", EX / "Topology_Example", None),
    ("channel-parameters", EX / "Channel_Parameters_Example", None),
    ("palette", EX / "Palette_Example", None),
    ("sine-wave", EX / "SineWave_Example", None),
    ("rotation-convention", EX / "Rotation_Convention_Example", None),
    ("texture-animation", EX / "Texture_Animation_Example", None),
    ("mood-background", EX / "Mood_Background_Example", None),
    ("bird-song-surface", EX / "Bird_Song_Surface_Topology_Example", None),
    ("audio-cat-scan-synesthesia",
     EX / "Audio_Animation_Example" / "Cat_Scan_Synesthesia_Example", None),
    ("audio-four-instruments",
     EX / "Audio_Animation_Example" / "Four_Instruments_C_Major_Example", None),
    # Unlike the scenes below whose static pose IS the hero, this one opens on
    # every root at its own peak presence — a state the playback never reaches,
    # under the near-black sky the piece starts at. Its hero is a frame, not
    # the rest state: see FRAME.
    ("audio-warm-winter",
     EX / "Audio_Animation_Example" / "Warm_Winter_Synesthesia_Example", None),
    ("surface-cowles", EX / "Surface_Example", None),
    ("multi-hike-race", EX / "Multi_Hike_Race_Example", None),
    ("sd-seismicity", EX / "SD_Seismicity_Example", None),
    ("rss-news", EX / "RSS_News_Example", None),
    ("calstate-testing", EX / "CalStateTesting_Example", None),
    ("ses-achievement-gap-terrain", EX / "SES_Achievement_Gap_Terrain_Example", None),
    ("district-heatmap", EX / "District_Heatmap_Example", None),
    ("gtdb-organization-profiles",
     EX / "Global_Terrorism_Example" / "Organization_Profiles", None),
    ("gtdb-event-cloud", EX / "Global_Terrorism_Example" / "Event_Cloud", None),
    ("gtdb-org-event-network",
     EX / "Global_Terrorism_Example" / "Org_Event_Network", None),
    ("gtdb-time-replay", EX / "Global_Terrorism_Example" / "Time_Replay", None),
    ("gtdb-campaign-pulse", EX / "Global_Terrorism_Example" / "Campaign_Pulse", None),
    ("vehicle-market-galaxy", EX / "Vehicle_Sales_Example" / "Market_Galaxy", None),
    ("vehicle-depreciation-grid",
     EX / "Vehicle_Sales_Example" / "Depreciation_Grid", None),
    ("vehicle-raw-auction-field",
     EX / "Vehicle_Sales_Example" / "Raw_Auction_Field", None),
    ("breathing-century", EX / "Breathing_Century_Example", None),
    ("century-swarm", EX / "Century_Swarm_Example", None),
    ("duel-of-dynasties", EX / "Duel_Of_Dynasties_Example", None),
    ("ybco-superconductor", EX / "YBCO_Superconductor_Example", None),
    ("protein-import", EX / "Protein_Import_Example", "alpha_helix_example.pdb"),
    ("flocking", EX / "Flocking_Example", None),
    ("autosleep-2025", EX / "AutoSleep_2025_Example", None),
    ("hacking-creativity-glyph", EX / "Hacking_Creativity_Glyph_Example",
     "Hacking_Creativity_Glyph_Example_gv_node.csv"),
    # Each of the five below ships 2-3 scenes; the gallery page carries one
    # hero shot, so the scene named here is the one that reads whole at
    # frame 0 (the animated siblings start dark or near-empty by design).
    ("tropical-cyclones", EX / "Tropical_Cyclone_Example" / "Global_Tracks", None),
    ("geomagnetic-field", EX / "Geomagnetic_Field_Example" / "Field_And_Poles", None),
    ("wind-rose", EX / "Wind_Rose_Example" / "Rose_Anatomy", None),
    ("decay-chains", EX / "Decay_Chain_Example" / "Chain_Forest", None),
    ("periodic-system", EX / "Periodic_System_Example" / "Madelung_Helix", None),
    # Orbital Traffic ships three scenes and the gallery gives each its own
    # page, so each gets its own shot rather than one hero for the set.
    ("orbital-live-sky", EX / "Orbital_Traffic_Example" / "Live_Sky", None),
    ("orbital-one-orbit", EX / "Orbital_Traffic_Example" / "One_Orbit", None),
    ("orbital-shells", EX / "Orbital_Traffic_Example" / "Orbital_Shells", None),
    # The Armillary World gets three shots off one scene: the gallery hero, a
    # close-up of the graduated instrument at the centre, and the whole world.
    # A slug is just an output filename, so repeating the folder is how a page
    # gets more than one view.
    ("armillary-world", EX / "Armillary_World_Example" / "Armillary_World", None),
    ("armillary-world-instrument",
     EX / "Armillary_World_Example" / "Armillary_World", None),
    ("armillary-world-overview",
     EX / "Armillary_World_Example" / "Armillary_World", None),
    # Static (Channels stopped) is the scene's last token -- the answer -- so
    # frame 0 is the right hero, unlike most animated scenes.
    ("ai-observatory-gpt2", EX / "AI_Observatory_GPT2_Example", None),
    # Same: static is the newline after "model", where Gemma decides to say "I".
    ("ai-observatory-gemma", EX / "AI_Observatory_Gemma_Example", None),
    # Static (Channels stopped) is the month's signature frame, 19 Dec 2012
    # 15:50 -- the Santa Ana at its peak -- authored into the node CSV.
    ("santa-ana-wind", EX / "Santa_Ana_Wind_Example", None),
    ("sd-river-watershed", EX / "San_Diego_River_Watershed_Example", None),
    # Static is January 1993, the resting pose the generator authors: the
    # highest combined flow among months when every gauge reported.
    ("sd-river-pulse", EX / "San_Diego_River_Pulse_Example", None),
    # Static is 21 February 2005, the resting pose the generator authors: wet
    # across the rain field and high on the river at once.
    ("sd-river-storm-2005", EX / "San_Diego_River_Storm_Example", None),
    # Static is 14 May 2014 11:00 PDT, the ten minutes with the most stations
    # in fire alert, with the now plane and its wind cones parked there.
    ("sd-fire-siege-2014", EX / "San_Diego_Fire_Siege_Example", None),
    # Static is 2025, the end of the record: every tile in its era colour. The
    # scene folder is gitignored; build_fire_history_scene.py regenerates it.
    ("sd-fire-history", EX / "San_Diego_Fire_History_Example" / "Burn_Record", None),
    # Static is the last month, September 2025: every storm on both slabs.
    ("sd-cedar-runoff", EX / "San_Diego_Cedar_Fire_Runoff_Example", None),
    # Building GlyphViz: one scene, three views of it, plus the five medoids.
    # City Climate Rings: the whole globe, then two cities turned to the top
    # of it (see "globe_to" in CAMERA) so their bars stand upright.
    ("city-climate-rings", EX / "City_Climate_Rings_Example", None),
    ("city-climate-rings-mumbai", EX / "City_Climate_Rings_Example", None),
    ("city-climate-rings-moscow", EX / "City_Climate_Rings_Example", None),
    # MLB Batting History: the bird's-eye view the original ANTz screenshots
    # were taken from, the labelled example glyph, and a close look at one
    # stretch of columns.
    ("mlb-batting-history", EX / "MLB_Batting_History_Example", None),
    ("mlb-batting-history-glyph", EX / "MLB_Batting_History_Example", None),
    ("mlb-batting-history-columns", EX / "MLB_Batting_History_Example", None),
    ("building-glyphviz", EX / "Building_GlyphViz_Example", None),
    ("building-glyphviz-gap", EX / "Building_GlyphViz_Example", None),
    ("building-glyphviz-spiral", EX / "Building_GlyphViz_Example", None),
    ("building-glyphviz-archetypes",
     EX / "Building_GlyphViz_Example" / "Five_Archetypes", None),
    # Nonlinear Feedback in a 5-D Lorenz Model: four scenes on one page, each
    # with a whole view and a close-up. All four boards are centred on world
    # (0, 0, 30), facing the default camera (azimuth 45, elevation 25).
    ("lorenz5d-loop", L5 / "Feedback_Loop", None),
    ("lorenz5d-loop-hcs", L5 / "Feedback_Loop", None),
    ("lorenz5d-cells", L5 / "Convection_Cells", None),
    ("lorenz5d-cells-close", L5 / "Convection_Cells", None),
    ("lorenz5d-tower", L5 / "R_Sweep_Tower", None),
    ("lorenz5d-tower-orbit", L5 / "R_Sweep_Tower", None),
    ("lorenz5d-landscape", L5 / "Stability_Landscape", None),
    ("lorenz5d-fig10a", L5 / "Stability_Landscape", None),
    ("lorenz5d-landscape-close", L5 / "Stability_Landscape", None),
    # Tensors, from the Arrow Up: three scenes on one page.
    ("tensors-vectors", TL / "Vectors_and_Bases", None),
    ("tensors-vectors-stage", TL / "Vectors_and_Bases", None),
    ("tensors-machine", TL / "Vector_to_Tensor", None),
    ("tensors-grid", TL / "Vector_to_Tensor", None),
    ("tensors-scope", TL / "Vector_to_Tensor", None),
    ("tensors-principal", TL / "Vector_to_Tensor", None),
    ("tensors-book", TL / "Spinning_Book", None),
    ("tensors-book-flip", TL / "Spinning_Book", None),
    ("tensors-lsphere", TL / "Spinning_Book", None),
    ("tensors-crystal-2d", TL / "Current_Across_the_Grain", None),
    ("tensors-crystal-3d", TL / "Current_Across_the_Grain", None),
    ("tensors-crystal-4d", TL / "Current_Across_the_Grain", None),
    ("tensors-metric-stretch", TL / "Slanted_Rulers", None),
    ("tensors-metric-dual", TL / "Slanted_Rulers", None),
    ("tensors-cut-mohr", TL / "The_Cut", None),
    ("tensors-cut-arbelos", TL / "The_Cut", None),
    ("tensors-field-dye", TL / "A_Field_of_Machines", None),
    ("tensors-field-tracks", TL / "A_Field_of_Machines", None),
]


# Channels frame to scrub to before grabbing, for a scene whose story is a
# moment of its animation rather than its rest state. Applied after the load
# (and so after auto-framing, which fits the rest state — use a CAMERA zoom if
# the frame is smaller). Loading a scene folder brings its ch-map/ch-tracks
# along exactly as it does for a user, so this is just the transport slider.
FRAME = {
    # 1:53 at 30 fps — the climax the whole piece is built around, all seven
    # instruments in, and the sky at its warmest.
    "audio-warm-winter": 3390,
    # 5-D Lorenz: tau = 17.5 has the 4DLM escaped, the 5DLM at r = 25 parked on
    # its quarter turns and both chaotic rows mid-flight; tau = 30 has the 3DLM
    # rolls mid-reversal beside the settled 5DLM cells and every tower bead
    # where its slice ends up.
    "lorenz5d-loop": 700,
    "lorenz5d-loop-hcs": 700,
    "lorenz5d-cells": 1200,
    "lorenz5d-cells-close": 1200,
    "lorenz5d-tower": 1200,
    "lorenz5d-tower-orbit": 1200,
    # Tensors: Act 2 of the basis tour; the end of Act 1 (every leg and
    # shadow drawn); the probe's painted ellipsoid; the tour in Scene 2; the
    # Act 4 turn; Act 5 settled on the principal axes; book 2 mid-flip
    # (5.2 s, its first crossing); the L-sphere with nearly a minute of trails.
    "tensors-vectors": 900,
    "tensors-vectors-stage": 300,
    "tensors-machine": 420,
    "tensors-grid": 1300,
    "tensors-scope": 2200,
    "tensors-principal": 3100,
    "tensors-book": 157,
    "tensors-book-flip": 157,
    "tensors-lsphere": 1790,
    # Tensors, round 2: the 2-D sweep with J's ellipse half drawn; E along y
    # filling the 3x3 grid's middle column; the 4-D hypercrystal and the
    # N-ladder; e1 stretched; the dual basis; the 2-D cut at 138 deg, where its
    # four tip labels sit furthest apart; the 3-D arbelos filling; the dye
    # drop at full spread; the tracks, one taking its wrong turn.
    "tensors-crystal-2d": 500,
    "tensors-crystal-3d": 1200,
    "tensors-crystal-4d": 2300,
    "tensors-metric-stretch": 700,
    "tensors-metric-dual": 2900,
    "tensors-cut-mohr": 940,
    "tensors-cut-arbelos": 2200,
    "tensors-field-dye": 560,
    "tensors-field-tracks": 2700,
}

# Auto-framing fits the bounding box of everything in the scene, title and
# legend nodes included, so a scene whose caption floats off to one side gets
# framed around empty space. These overrides run after the load:
#   zoom       multiplies the fitted camera distance
#   distance   sets the camera distance outright, ignoring the fit (and zoom)
#   origin     re-aim at the world origin instead of the bbox centre
#   target     re-aim at an explicit (x, y, z) — for scenes whose data sits
#              off-origin AND off the bbox centre, i.e. anything with a big
#              legend panel parked to one side
#   azimuth    orbit angle in degrees (default 45)
#   elevation  degrees above the horizon (default 25; 90 looks straight down)
#   hide_grid  turn the ground grid and axes off for this shot (restored after)
CAMERA = {
    "protein-import": {"zoom": 0.35},
    # Globe scenes: the caption sits well off the sphere, so aim at the
    # globe itself and size the distance off its radius rather than the bbox.
    "tropical-cyclones": {"origin": True, "zoom": 0.80, "elevation": 18},
    "geomagnetic-field": {"origin": True, "zoom": 0.78, "elevation": 18},
    # The rose anatomy plate reads as a plate, from fairly high up.
    "wind-rose": {"zoom": 0.72, "elevation": 45},
    # The forest is a skyline: low angle, and nearly square-on to the row of
    # chains (they march along +Y, so the eye swings toward +X). Not dead-on —
    # a few degrees of obliquity separates the per-chain labels.
    "decay-chains": {"zoom": 0.55, "azimuth": 22, "elevation": 12},
    # The Raw Auction Field parks its glyph legend out at x=-395, well clear
    # of the data (x 0..420) so 100k glyphs don't render through the captions
    # — which puts the bbox centre in empty space between the two. Aim at the
    # middle of the field itself, and pick the orbit that shows all three
    # labelled axis rails plus the December-March and May-June sales bursts.
    "vehicle-raw-auction-field": {"target": (250, 96, 42), "distance": 520,
                                  "azimuth": 120, "elevation": 24},
    # Down the helix axis: every group becomes a radial spoke (see README).
    "periodic-system": {"origin": True, "zoom": 0.97, "elevation": 89},
    # Orbital Traffic: all three are Earth-centred, and all three carry a
    # caption and legend well off to one side, so aim at the origin. Live_Sky
    # is the extreme case — its bounding box reaches the GEO belt at 321 units
    # against a 57-unit globe, so the fitted distance leaves Earth a dot.
    "orbital-live-sky": {"origin": True, "zoom": 0.34, "elevation": 20},
    "orbital-one-orbit": {"origin": True, "zoom": 0.85, "elevation": 18},
    "orbital-shells": {"origin": True, "zoom": 0.58, "elevation": 20},
    # Armillary World. Distances are absolute here rather than fractions of the
    # fit, because the scene is nested over two orders of magnitude (a 635-unit
    # world around a 12-unit instrument) and the interesting radii are the
    # instrument's, not the bounding box's. The hero stands just inside Zone 1
    # so one zone band reads at full size with the instrument behind it; the
    # second goes in to the graduated dials; the third pulls out to the whole
    # world, from well above, since at a low angle the eight zone rings
    # collapse into each other.
    "armillary-world": {"origin": True, "distance": 170, "azimuth": 35,
                        "elevation": 22},
    "armillary-world-instrument": {"origin": True, "distance": 110,
                                   "azimuth": 35, "elevation": 22},
    "armillary-world-overview": {"origin": True, "zoom": 0.72, "azimuth": 35,
                                 "elevation": 58},
    # AI Observatory: a 180-unit tower of 12 layer rings with the prompt row in
    # front. The pinned feature labels run off to the right of the tower, so aim
    # right of centre to leave them room. Tag text is a fixed pixel size, so the
    # capture window's short viewport needs a closer camera than export_frame's
    # 1000 px renders did, or the prompt-row tokens run together.
    # The shot has to span the prompt row (z 0) to the prediction label (z ~196):
    # 450 kept the tokens apart but cropped the answer; 540 is the compromise.
    "ai-observatory-gpt2": {"target": (55, -30, 100), "distance": 540,
                            "azimuth": -90, "elevation": 10},
    # Gemma's tower is 26 rings (364 units), too tall to show whole with
    # readable labels in this window. The story is the contrast labels from
    # layer 7 up, so frame those and the prediction; the prompt row drops out.
    "ai-observatory-gemma": {"target": (260, -30, 420), "distance": 600,
                             "azimuth": -90, "elevation": 10},
    # From over the Pacific looking up the valley: the mouth in the foreground,
    # the mountains behind, the Strahler legend in the empty space to the north.
    # From over the coast looking inland: the humidity legend on the left, the
    # December timeline and its running clock along the right.
    "santa-ana-wind": {"target": (-45, -15, 25), "distance": 400,
                       "azimuth": 225, "elevation": 28},
    "sd-river-watershed": {"target": (10, 20, 0), "distance": 430,
                           "azimuth": 180, "elevation": 32},    # Pulled back and swung south so the river mouth, the legend and the whole
    # two-strip panel (and its month/year readout) all fit.
    "sd-river-pulse": {"target": (70, -25, 120), "distance": 640,
                       "azimuth": 194, "elevation": 14},
    # Close on the map, not the panel: this scene's story is the rain field
    # standing over the county, and the panel reads better on its own page
    # image than squeezed into a wide gallery frame.
    "sd-river-storm-2005": {"target": (-40, -30, 10), "distance": 330,
                            "azimuth": 215, "elevation": 35},
    # The whole cube from the south-west, the legend above its east side.
    "sd-fire-siege-2014": {"target": (60, -30, 112), "distance": 640,
                           "azimuth": 215, "elevation": 18},
    # From the south: the ledger stands behind the county, the legend over
    # the Pacific on the left.
    "sd-fire-history": {"target": (-10, 10, 10), "distance": 340,
                        "azimuth": 270, "elevation": 36},
    # Warm Winter: a seven-glyph totem on one vertical axis, 106 units tall at
    # the climax, in a wide frame. Aim at the middle of the column and stand
    # low, so the stack fills the height and track 1's pale floor still reads
    # underneath it.
    "audio-warm-winter": {"target": (0, 0, 14), "distance": 165,
                          "azimuth": 35, "elevation": 7},
    # From the south-west: the map in front, both storm slabs behind it.
    "sd-cedar-runoff": {"target": (20, 110, 85), "distance": 560,
                        "azimuth": 250, "elevation": 24},
    # Building GlyphViz. Azimuth 270, never 90: at 90 the web bank renders on
    # the LEFT, backwards against the lane order and the projects' start order.
    # Down the avenue from the June end: both banks run away up the calendar.
    # "globe_to": (lat, lon) turns the scene's World Grid (Euler XYZ
    # (0, -(90 - lat), -lon), measured through the engine) so that point is on
    # top of the globe. The orbit camera's up is always world +Z, so this is
    # the only way to show a ring on a globe with its bars standing upright;
    # from azimuth 0 it reads north up, east right.
    "city-climate-rings": {"origin": True, "distance": 520,
                           "azimuth": 55, "elevation": 22},
    "city-climate-rings-mumbai": {"globe_to": (19.08, 72.88),
                                  "target": (0, 0, 184), "distance": 66,
                                  "azimuth": -6, "elevation": 28},
    "city-climate-rings-moscow": {"globe_to": (55.76, 37.62),
                                  "target": (0, 0, 180), "distance": 58,
                                  "azimuth": 8, "elevation": 34},
    # MLB Batting History. Azimuth 270 at elevation 89 puts +x (players) to the
    # right and +y (teams) up, so the American League sits left of the National
    # League exactly as in the original ANTz bird's-eye view.
    "mlb-batting-history": {"target": (326, 35, 0), "distance": 800,
                            "azimuth": 270, "elevation": 89},
    "mlb-batting-history-glyph": {"target": (297, -372, 40), "distance": 330,
                                  "azimuth": 270, "elevation": 89},
    "mlb-batting-history-columns": {"target": (-60, -60, 100), "distance": 60,
                                    "azimuth": 300, "elevation": 20},
    "building-glyphviz": {"target": (0, 120, 10), "distance": 230,
                          "azimuth": 270, "elevation": 20},
    # Standing in the 30-unit gap: desktop rising left, web right.
    "building-glyphviz-gap": {"target": (0, 150, 9), "distance": 60,
                              "azimuth": 270, "elevation": 10},
    # Straight down 2026-06-22 "Add audio support", the tallest column:
    # thinking collects in the middle, tool calls ring the outside.
    "building-glyphviz-spiral": {"target": (-49.4, 48.0, 27), "distance": 34,
                                 "azimuth": 0, "elevation": 89},
    "building-glyphviz-archetypes": {"target": (0, 0, 9), "distance": 58,
                                     "azimuth": 92, "elevation": 10},
    # 5-D Lorenz. Every board faces azimuth 45 / elevation 25, so the square-on
    # shots pass those explicitly (the auto-fit's own angles skew the board).
    # The capture window is short and wide, and tag text is a fixed pixel
    # size, so each square-on shot frames the part of the board that tells
    # its story rather than the whole board. Targets measured through the
    # engine from the generated scenes.
    # The 4DLM and steady 5DLM rows: the loop on the left, the HCS on the right.
    "lorenz5d-loop": {"target": (-2.23, 1.58, 30.98), "distance": 23,
                      "azimuth": 45, "elevation": 25, "hide_grid": True},
    # The same two hyperglyphs up close: the 4DLM at infinity, the 5DLM parked.
    "lorenz5d-loop-hcs": {"target": (-10.0, 9.35, 30.98), "distance": 16,
                          "azimuth": 35, "elevation": 22, "hide_grid": True},
    # The r = 25 group: both cells, their budgets and the shared phase panel.
    "lorenz5d-cells": {"target": (-3.01, -3.01, 39.13), "distance": 24,
                       "azimuth": 45, "elevation": 25, "hide_grid": True},
    "lorenz5d-cells-close": {"target": (8.95, -12.47, 35.34), "distance": 12,
                             "azimuth": 45, "elevation": 25, "hide_grid": True},
    "lorenz5d-tower": {"target": (0, 0, 31), "distance": 38,
                       "azimuth": 45, "elevation": 25, "hide_grid": True},
    # Down onto the 5DLM tower: the needle, the transient cone, the bloom.
    "lorenz5d-tower-orbit": {"target": (-8.74, 11.62, 36.97), "distance": 26,
                             "azimuth": 10, "elevation": 55, "hide_grid": True},
    # The three relief panels, then the flat Fig. 10a panel on its own.
    "lorenz5d-landscape": {"target": (-4.2, -2.6, 40.33), "distance": 34,
                           "azimuth": 45, "elevation": 25, "hide_grid": True},
    "lorenz5d-fig10a": {"target": (2.22, 1.37, 24.56), "distance": 17,
                        "azimuth": 45, "elevation": 25, "hide_grid": True},
    "lorenz5d-landscape-close": {"target": (-21.33, 8.37, 37.11), "distance": 26,
                                 "azimuth": 30, "elevation": 35, "hide_grid": True},
    # Tensors. Same wall-board convention (azimuth 45 / elevation 25); targets
    # measured through the engine from the generated scenes.
    "tensors-vectors": {"target": (1.75, -0.85, 9.5), "distance": 34,
                        "azimuth": 45, "elevation": 25, "hide_grid": True},
    "tensors-vectors-stage": {"target": (7.4, -7.4, 8.3), "distance": 21,
                              "azimuth": 45, "elevation": 25, "hide_grid": True},
    "tensors-machine": {"target": (8.48, -8.48, 9.0), "distance": 24,
                        "azimuth": 45, "elevation": 25, "hide_grid": True},
    "tensors-grid": {"target": (3.09, -0.88, 10.0), "distance": 37,
                     "azimuth": 45, "elevation": 25, "hide_grid": True},
    "tensors-scope": {"target": (-1.6, 2.6, 7.0), "distance": 28,
                      "azimuth": 45, "elevation": 25, "hide_grid": True},
    "tensors-principal": {"target": (5.0, -5.0, 10.5), "distance": 30,
                          "azimuth": 45, "elevation": 25, "hide_grid": True},
    "tensors-book": {"target": (-0.5, 0.1, 8.0), "distance": 46,
                     "azimuth": 45, "elevation": 25, "hide_grid": True},
    "tensors-book-flip": {"target": (5.66, -5.66, 7.5), "distance": 17,
                          "azimuth": 45, "elevation": 25, "hide_grid": True},
    "tensors-lsphere": {"target": (-13.8, 13.8, 7.0), "distance": 17,
                        "azimuth": 45, "elevation": 25, "hide_grid": True},
    "tensors-crystal-2d": {"zoom": 0.72, "hide_grid": True},
    "tensors-crystal-3d": {"zoom": 0.72, "hide_grid": True},
    "tensors-crystal-4d": {"zoom": 0.72, "hide_grid": True},
    "tensors-metric-stretch": {"zoom": 0.72, "hide_grid": True},
    "tensors-metric-dual": {"zoom": 0.72, "hide_grid": True},
    "tensors-cut-mohr": {"target": (-1.0, 1.0, 10.3), "distance": 30,
                         "azimuth": 45, "elevation": 25, "hide_grid": True},
    "tensors-cut-arbelos": {"zoom": 0.72, "hide_grid": True},
    "tensors-field-dye": {"target": (7.7, -6.4, 8.6), "distance": 21,
                          "azimuth": 45, "elevation": 25, "hide_grid": True},
    "tensors-field-tracks": {"zoom": 0.72, "hide_grid": True},
}


def scene_file(folder: Path, explicit: str | None) -> Path | None:
    if explicit:
        return folder / explicit
    csvs = sorted(folder.glob("*node*.csv"), key=lambda p: len(p.name))
    return csvs[0] if csvs else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", default=None,
                        help="Slugs to (re)capture.")
    args = parser.parse_args()
    wanted = set(args.only) if args.only else None

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841

    cap = Capture()
    failed = []
    try:
        for slug, folder, explicit in MANIFEST:
            if wanted is not None and slug not in wanted:
                continue
            path = scene_file(folder, explicit)
            if path is None or not path.exists():
                print(f"  !! {slug}: no scene file in {folder}")
                failed.append(slug)
                continue
            if path.suffix.lower() == ".pdb":
                ok = cap.win._load_pdb_path(str(path))
            else:
                ok = cap.win._load_csv_path(str(path))
            if not ok:
                print(f"  !! {slug}: load failed for {path.name}")
                failed.append(slug)
                continue
            pump(0.4)   # texture uploads / first frame of a big scene
            if slug in CAMERA:
                cam = CAMERA[slug]
                if "globe_to" in cam:
                    from glyphviz_core.node import ROTATION_MODE_EULER_XYZ
                    lat, lon = cam["globe_to"]
                    grid = next(n for n in cap.win.nodes if n.type == 6)
                    grid.rotation_mode = ROTATION_MODE_EULER_XYZ
                    grid.rotate_x, grid.rotate_y, grid.rotate_z = (
                        0.0, -(90.0 - lat), -lon)
                    cap.vp.scene_invalidate()
                if cam.get("origin"):
                    cap.vp._cam_target = [0.0, 0.0, 0.0]
                elif "target" in cam:
                    cap.vp._cam_target = [float(v) for v in cam["target"]]
                if "azimuth" in cam:
                    cap.vp._cam_azimuth = cam["azimuth"]
                if "elevation" in cam:
                    cap.vp._cam_elevation = cam["elevation"]
                if "distance" in cam:
                    cap.vp._cam_distance = cam["distance"]
                else:
                    cap.vp._cam_distance *= cam.get("zoom", 1.0)
                if cam.get("hide_grid"):
                    cap.win._set_grid(False)
                    cap.win._set_axes(False)
                cap.vp.update()
                pump(0.1)
            if slug in FRAME:
                if cap.win._ch_engine is None:
                    print(f"  !! {slug}: no channel file loaded, cannot scrub")
                    failed.append(slug)
                    continue
                cap.win._ch_frame = FRAME[slug]
                cap.win._ch_apply_and_show_frame(FRAME[slug])
                pump(0.2)
            cap.viewport_png(OUT_DIR / f"{slug}.png")
            if CAMERA.get(slug, {}).get("hide_grid"):
                cap.win._set_grid(True)
                cap.win._set_axes(True)
            print(f"  ok {slug}  ({path.name})")
    finally:
        cap.close()

    if failed:
        print(f"{len(failed)} failed: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
