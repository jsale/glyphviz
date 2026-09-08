# Rooted_Bars — four ways to draw a bar, measured

**What it teaches:** a length that carries data belongs in *position* space, not
*scale* space — and, underneath that, what a `scale` number actually means.
Fourteen values, drawn four times, so the difference between the recipes is
something you can look at rather than something you have to be told.

Open `rooted_bars_gv_node.csv`, then drag Properties → Global Scale from 1 to 3
and watch which rows survive.

| | |
|---|---|
| `rooted_bars_gv_node.csv` | 91 rows: four rows of 14 bars, a World Grid baseline, five captions |
| `build_rooted_bars.py` | the generator, and the measurement — see below |
| `data/u238_chain.csv` | 14 rows, extracted from the IAEA ground-state table bundled with `Decay_Chain/` |

## The four recipes

`H` is the height the bar is supposed to have, standing on `z = 0`.

| row | authored | at Global Scale 1 | at Global Scale 3 |
|---|---|---|---|
| **A** | cube, `scale_z = H` | −0.58H…0.58H | −1.73H…1.73H |
| **B** | cube, `scale_z = H/1.155`, `translate_z = H/2` | 0…H | −H…2H |
| **C** | Pin, `scale_z = H/1.1` | 0…H | 0…3H |
| **D** | Link, hidden base at 0 → hidden tip at H | 0…H | **0…H** |

Every number in that table is re-measured through the app's own placement
engine by `verify()` before the CSV is written, at both Global Scale settings.
If the code and the table ever disagree, the generator refuses to emit a file.

**Row A is wrong twice.** Half the bar is underground, which is the familiar
half of the problem. The other half is quieter: a cube is inscribed in the unit
sphere, so its faces reach only `1/√3 = 0.577` of its scale. `scale_z = H` draws
a bar of total height 1.15H, of which 0.58H is above ground — so the naive
recipe encodes the *wrong number* as well as putting it in the wrong place.

**Row B is exact, and only at one setting.** Dividing the geometry factor out
and lifting by `H/2` puts the base on the baseline. But Global Scale multiplies
rendered size and does *not* move a root's coordinates, so at GS 3 the bar is
three times as tall around a lift that did not change, and the base sinks to
−H. Anything corrected by an offset comes apart the moment the viewer zooms.

**Row C holds its base** because a Pin is the one geometry that stands *on* its
origin (it spans 0…1.1). Only the height rides Global Scale. Note the width:
a Pin is a needle 0.1 wide, so its `scale_x/y` is **ten times** a cube's for the
same rendered thickness — 5.5 against 0.95 here. That is not a fudge factor,
it is the geometry's own size, and it comes out of `gv_extents.local_box()`.
Note also what a Pin *looks* like: a cone standing on its apex, widening
upward, with a small dome on top. The base is exactly right and the silhouette
is a spike rather than a column — a second reason to prefer D when the bar is
meant to read as a bar.

**Row D is invariant** because both ends are coordinates. The bar is a Link
whose A-end is a hidden node at `z = 0` and whose B-end is a hidden node at
`z = H`; `geometry` = Cylinder and `ratio` is the thickness. Nothing the viewer
does can move either end, and `H` can be read straight back out of the CSV.
This generalises well past bar charts — it is the answer whenever a part's
*length*, rather than its *size*, is the measurement.

## The data, and the clamp

The 14 unstable members of the uranium-238 decay chain, in decay order, with
half-lives from the IAEA table. Bar height is **decades of half-life above the
shortest-lived member** — Po-214, at 164 µs — which spans 20.9 orders of
magnitude between Po-214 and U-238's 4.5 billion years.

That domain is exactly the kind that has to be clamped before it is drawn:

```
variable   half-life                        channel  bar height
domain     164 us .. 4.5 Gy = 20.9 decades  range    0.44 .. 5.40
```

The floor does real work. Po-214 sits at 0 decades and would otherwise be a bar
of height zero — invisible, unclickable, and with no way to read its label.
0.44 also keeps every recipe's authored `scale_z` above 0.2, so the scene reads
the same whether or not the viewer has View → Enforce Minimum Glyph Size on.
The ceiling never binds on this data; it is there for the next dataset.

## Reading the checker's crowding line

`python ../../code/gv_extents.py rooted_bars_gv_node.csv` reports no problems,
and then says this:

```
crowding     10 root pairs have interpenetrating bounding spheres,
             worst roots 8 and 9 by 5.21.
```

That is correct arithmetic and not a defect, which is why it sits under SCENE
rather than under PROBLEMS. A tall thin bar has a bounding sphere as wide as it
is tall, so adjacent bars in any bar chart will always "interpenetrate" by that
measure. Treat the crowding line as a hint to go and look, not as a failure —
the same way you would treat a linter warning on a deliberate idiom.

## Why a bar chart is in this skill at all

Because it is the shape people ask for first, and because the mistake it invites
— write the value into `scale_z`, look at the result, adjust by eye — is the
same mistake that later breaks a hyperglyph. Rules 2 and 5 in `SKILL.md` are
both visible in one screenshot here.

Regenerate with `python build_rooted_bars.py`. Never hand-edit the CSV.
