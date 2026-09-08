# Note for Dave — what changed in the GlyphViz skill, and one thing to delete

*Draft for Jeff to send with the Round 7 skill zip. Written 2026-09-08.*

---

Dave — the GlyphViz skill has had a large pass, built almost entirely from the
eight session transcripts you shared. Nearly everything in it is an answer to
something one of those sessions had to re-derive. Three things are worth your
time before you run it again.

## 1. Delete the scale-floor rule from your `scaling-rules` doc

This is the one concrete ask. Your doc says something close to:

> the renderer floors rendered scale at 0.2 per axis; if local scale < 0.2 it
> floors UP, distorting

**Measured against the app: that clamp is OFF by default**, and when a user does
switch it on (View → Enforce Minimum Glyph Size) it lifts each node's *own*
`scale × Global Scale` and **ignores every ancestor**. So it does not protect a
counter-scaled child — it destroys one. A bead authored `(5.0, 5.0, 0.073)` to
render round on a thin tall mast measures 0.500 / 0.500 / 0.500 with the clamp
off, and 0.500 / 0.500 / 1.378 — a 2.8 : 1 ellipsoid — with it on.

Your most recent session spent the majority of its turns restructuring five
glyph designs to satisfy that rule, and reported "zero sphere floor violations
across 25 scenes" as the win. That was work done for a constraint that does not
exist. The rule is now stated correctly in `SKILL.md` as hard rule 6, so leaving
the old sentence in your own doc will just make the two disagree — and the
document that gets read at design time is the one that wins.

**`CompScene` stays.** It is a good implementation of counter-scaling. Only its
premise changes: counter-scaling is the *fallback*, a uniform `hide = 1` carrier
is the primary answer, and counter-scaling and the clamp option are mutually
exclusive by construction.

## 2. There is now a checker, and it is the app's own math

`code/` in the zip holds two things:

- **`gv_kernel/`** — byte-identical copies of GlyphViz's `node.py`,
  `geometry_data.py`, `topology.py`, `link_geometry.py`, `csv_reader.py` and
  `scene.py`. numpy and pandas only, no GlyphViz install needed. A test in the
  repo fails if they ever drift from the app.
- **`gv_extents.py`** — reads a node CSV and tells you what it will actually
  render as, and what is wrong with it: children buried inside their parent,
  children flung far outside their parent's layout (with a hint when the numbers
  look like degrees written into a Cartesian slot), glyphs that will shear,
  `color_a = 0` nodes used as carriers, links with an unresolvable end, and
  anything whose proportions would change if that clamp were switched on.

```
python code/gv_extents.py my_scene_gv_node.csv
```

It is importable too (`analyse()` / `report()`), which is usually what you want
mid-build.

**This is the replacement for your thumbnail previewer.** The previewer sizes
each node by the *mean* of its basis columns, so a `0.10 / 0.10 / 11` carrier
draws as a radius-3.7 disc — that is where the three false bug reports in the
last session came from. `gv_extents` uses per-geometry silhouettes and the real
draw matrix, so it cannot make that mistake. You wrote "trust the tool, not my
thumbnail" and then acted on the thumbnail, because there was no tool. Now
there is one.

## 3. A number that was wrong in the skill itself, and is now right

The skill used to say *every geometry spans −1…+1 per axis*. It does not. Every
geometry is built to fit inside **radius 1**, which is a different statement:

| geometry | x, y half-extent | z |
|---|---|---|
| Sphere, Cone, Cylinder, Octahedron | 1 | −1…+1 |
| **Cube** | **0.577** | ±0.577 |
| Icosahedron | 0.851 | ±0.851 |
| Dodecahedron | 0.934 | ±0.934 |
| Tetrahedron | 0.943 / 0.816 | −0.333…+1 |
| **Pin** | **0.1** | 0…1.1 |
| Square ("Grid") | 0.707 | flat |
| Torus, Flat Ring | 1 | ±`ratio` |

Two consequences worth knowing, both measured:

- A bar built as a cube at `scale_z = H` is **0.58H above ground**, not H. It
  encodes the wrong number as well as sinking half of itself.
- A Pin at the same `scale_x/y` as a cube is **ten times thinner**. If a rod or
  pin in one of your glyphs has ever looked like a hair, this is why.

And the placement side, which is *not* affected: a topology always seats
children on the parent's circumscribed sphere, whatever geometry it wears. So a
child on a scale-2 Cube facet lands at 2.000 while the drawn face is at 1.155 —
it floats 0.845 above it, by design. Cube, Pin, Icosahedron and flat-square
parents will always look like their children are hovering.

`gv_extents.local_box(geometry, ratio)` returns that table, so nothing has to
re-derive it.

## 4. Two of your inventions are now in the skill, credited

- **Measure each glyph's true footprint after building and drive layout spacing
  from it**, rather than guessing a pitch.
- **The two-phase record → de-collide → build pass** that took your overlaps
  from 301 to 2.

Both are in `references/hyperglyph-design.md` §7, with your name on them. So are
your troubleshooting reports, in your own words, as entries 18–22 of
`references/troubleshooting.md`.

## 5. Two new examples, both small

- **`examples/Rooted_Bars/`** — the four ways to draw a bar, side by side over
  one dataset, measured at Global Scale 1 and 3. The generator re-derives its
  own documentation through the placement engine and refuses to write the CSV if
  the table and the code disagree.
- **`examples/Glyph_Envelope/`** — your palm glyph, generated at the minimum,
  median and maximum of every variable, with the variable → channel → domain →
  clamped-range budget written down and enforced, and its extent report
  committed beside it. The design is credited to you; **the data in it is
  synthetic**, generated from a seeded RNG, so nothing of your cohort is in the
  zip.

That example is also the clearest demonstration of the discipline: the palm
grew a bare lower stem, carrying no data at all, purely because the worst
record's branch droop otherwise went through the floor. The envelope changed the
design, which is what it is for.

## What would help most, if you have it

1. **The `med_bakeoff2` node CSV** behind the screenshot in the last session.
   Running the checker over a real file of yours is the fastest way to find the
   next class of false positive — the last tuning pass found five, each of which
   was a genuine lesson.
2. **One file you hand-corrected, plus its original.** The most valuable thing a
   skill can carry is a worked "here is what was wrong, here is the formula that
   fixes it in the generator rather than by hand" — and that needs a real
   before-and-after, not an invented one.
3. **Whether `gv_extents.py` actually gets run.** That is the honest open
   question. Rounds 3 through 7 have all shared one failure mode: the right
   answer existed and was not the document that got read. If your own skills
   open first and the GlyphViz skill never does, the checker will not help, and
   the fix is in how the skills are ordered rather than in anything the skill
   says. `SKILL.md` now has a short section, *Writing a skill on top of this
   one*, aimed exactly at that.
