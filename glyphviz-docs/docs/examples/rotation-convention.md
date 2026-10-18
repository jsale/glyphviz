# Rotation Conventions

A side-by-side demonstration of the two `rotation_mode` values: ANTz's legacy Heading/Tilt/Roll (a Z-X-Z sequence) versus GlyphViz's per-axis Euler XYZ. Identical rotation inputs trace visibly different paths — a level circle under one convention, a wobbling one under the other.

![Rotation Conventions loaded in GlyphViz](../assets/examples/rotation-convention.png)

**Try it:** download this example below (or [the full examples set](../getting-started/installation.md#example-scenes)), then open `Rotation_Convention_Example/Rotation_Convention_Example_gv_node.csv` — or just drag its folder onto the GlyphViz window. Press **Space** to start the animation.

[:material-download: Download this example (4 KB)](https://iluvdata.org/glyphviz/zips/Rotation_Convention_Example.zip){ .md-button }

## What it is

Two pins stand side by side. They are given **exactly the same numbers**: a fixed tilt of 30° and a heading that sweeps from 0° to 360° over a four-second loop, driven by one shared channel. Yet they do not move the same way. The left pin's tip sweeps a perfectly level circle. The right pin's tip bobs up and down as it goes round.

The only difference between them is their `rotation_mode`, the setting that tells GlyphViz how to read the three rotation numbers.

| | Left pin | Right pin |
|---|---|---|
| Label | *Heading/Tilt/Roll (ANTz)* | *Euler XYZ* |
| Convention | ANTz's legacy sequence | GlyphViz's own, and the default for new nodes |
| Path of the tip | a level circle at constant elevation | an elevation that wobbles through the sweep |

## Why the two differ

**Heading/Tilt/Roll** is the convention ANTz always used, borrowed from the way KML aims cameras and models. It is a Z-X-Z sequence: `rotate_y` is a heading about the vertical axis, `rotate_x` is a tilt, and `rotate_z` is a roll about the vertical axis again. Heading then tilt is the standard way of describing a direction on a sphere, azimuth and then elevation, the same longitude and latitude idea GlyphViz already uses to place children on a Sphere topology. Hold the tilt fixed and sweep the heading, and you get a lighthouse beam: a level circle.

**Euler XYZ** simply rotates about each named axis in turn: `rotate_x` about X, `rotate_y` about Y, `rotate_z` about Z. That is intuitive when you pose a glyph by hand, but the two angles no longer mean azimuth and elevation. Give it the same fixed `rotate_x` of 30 and a swept `rotate_y`, and the tip's elevation changes as the sweep proceeds.

One tempting explanation is wrong, and the scene is careful not to claim it: it is *not* that one mode can spin in place and the other cannot. `rotate_z` is the innermost rotation in both conventions, so animating only `rotate_z` looks identical in both. The real difference appears when `rotate_x` and `rotate_y` are both non-zero and jointly aim the object.

## What to try

- **Press Space** and watch the two tips. Then orbit to look along the vertical axis: the left tip draws a circle, the right one an uneven loop.
- **Open the Properties panel on each pin** and find its Rotation Mode. Change the right pin to Heading/Tilt/Roll and the two become identical, because only the mode was ever different.
- **Pause and set `rotate_x` to zero** on both: with no tilt, the two conventions agree.

## Why it matters when you write data

Files that predate this setting load as Heading/Tilt/Roll, so every older ANTz, GaiaViz and GlyphViz scene renders exactly as it always did. A node created in GlyphViz itself defaults to Euler XYZ. When you generate scenes, set `rotation_mode` explicitly on any node you rotate. It is the one column whose absence changes what the numbers mean.

The scene is **two nodes and one channel**, and the generator, `generate_rotation_convention_example.py`, is a good minimal model of a Channels animation: one mapping, one 120-frame track, and two nodes sharing it.
