# Designing a hyperglyph someone can actually read

A **hyperglyph** is one composite glyph whose internal structure carries several
variables at once, repeated across many records. `SKILL.md`'s hard rules tell
you what the engine does. This tells you how to build a glyph a person can
decode, and how to keep it working when real data replaces your sample.

Most of what follows was learned the expensive way, from real sessions where a
design that looked right fell apart on contact with data. Where a rule has an
engine fact behind it, that fact is stated and has been measured; where it is a
design judgement, it says so.

The single most useful habit: **run `code/gv_extents.py` on the scene before you
hand it over.** Most of the failures below are things it names for you.

---

## 1. Anatomy

**The root is a handle, and it belongs on the ground.** Make the root a small,
visible, grabbable glyph — a cube is conventional — sitting on the world plane
as the lowest point of the whole assembly, with everything else parented beneath
it. Then one drag moves the entire hyperglyph, and a field of them can be
rearranged by hand. A root that is invisible, buried inside the body, or floating
mid-structure cannot be grabbed, and a user who cannot move your glyph cannot
work with it.

**Build a real parent chain, not a pile of siblings.** Root → trunk → limb →
leaves, each a genuine `parent_id` link. If the leaves are siblings of the limb
rather than its children, they will not follow it, and the first time you move
or scale anything the glyph comes apart. This sounds obvious and is one of the
most common structural mistakes.

**Parts should touch, or nearly touch.** A hyperglyph reads as one entity when
its components are in contact and as scattered debris when they are not. Gaps
between a limb and the beads on it are the difference between a plant and a
cloud of dots. Seat children so their near face just clears the parent's
surface (rule 3) — clearing it by a small gap, not floating a diameter away.

**Information volume must justify spatial volume.** If a component occupies a
quarter of the glyph's bounding box it should be carrying roughly a quarter of
the meaning. A vast empty hub with three tiny beads on it wastes the reader's
attention and, when you pack a field of these, wastes the screen. This is Dave
Warner's phrasing and it is the fastest test for whether a design is padded.

---

## 2. Getting parts where you meant them

Read `SKILL.md` rules 2 and 3 first — they carry the extent law and the seating
table. Three consequences matter most in practice.

**A child seated exactly at the parent's surface is half buried,** because the
child has its own half-extent. Clearing it means
`translate magnitude = 1 + (child_radius + gap) / parent_scale` under a
Cartesian parent, and the equivalent in whatever units the parent's topology
reads. `gv_extents.py` prints the exact distance that clears each offender.

**A child inherits its parent's scale, so it is bigger than you authored.** A
child authored at `scale 0.3` under a `scale 3` parent renders at 0.9. This is
why "seat it at the surface plus its own small radius" so often still buries
things: the radius you must clear is the *rendered* one.

**Some parents are not surfaces at all.** A Rod parent threads its children
along its own axis; the Z-variants place children at the centre or axis on
purpose. Children inside those parents are correct, not buried, and the checker
knows the difference.

---

## 3. Uniform carriers, and when to counter-scale

A non-uniformly scaled parent distorts everything beneath it: a sphere becomes
an ellipsoid, and a *rotated* child shears outright (rule 4). There are two ways
to deal with that, and the order matters.

**First choice: hang the part on a uniformly-scaled carrier.** A carrier is a
node with `hide = 1` and uniform `scale 1` that exists only to position things.
Both the render and the pick pass skip it, its children are unaffected, and
because its scale is uniform nothing beneath it distorts. Build the stretched
rod as a *sibling* for looks, and hang the beads on the carrier.

Three things that look like carriers and are not, all seen in real sessions:

| Looks like a carrier | What actually happens |
|---|---|
| `color_a = 0` | still drawn, and still takes clicks — it silently steals selections |
| `scale = 0.001` | not hidden at all; it shrinks the entire subtree by a thousand |
| a long thin rod | shears and distorts everything hung on it |

The one exception to the alpha rule: a **Plot or Surface** overlay is drawn
*from* its children, so an alpha-0 vertex — or an alpha-0 hub carrying the
polyline — is the correct idiom there. `hide = 1` would drop the node from the
overlay as well.

**Second choice: counter-scale the child** so it renders round despite the
parent, by dividing out the parent's per-axis scale. This is legitimate and
sometimes necessary, but it costs you two things. The authored numbers stop
being readable by a human editing the CSV. And it is **incompatible with View >
Enforce Minimum Glyph Size**, which lifts each node's own scale and so turns a
counter-scaled child into an ellipsoid (rule 6). Prefer a carrier; reach for
counter-scaling when the design genuinely requires a round part on a stretched
parent, and say so in the scene's notes.

---

## 4. The design envelope — surviving real data

This is the failure Dave Warner reports most often: a glyph is dialled in on
sample data, real data goes in, and the parts fly apart, collapse, or intersect.
It happens because a design implicitly assumes a range the data does not respect.

**Declare a budget per variable, before generating anything:**

| | |
|---|---|
| variable | the column |
| channel | what it drives — length, radius, angle, colour, count |
| domain | the real min and max **in the data**, not the sample |
| range | the rendered values it may produce, **clamped at both ends** |

Normalise into the clamped range before writing the CSV. Then no data value —
including the outlier you have not seen yet — can push a part outside the room
the design allotted it. An unclamped `radius = value / 10` is a bug waiting for
a big number.

**Then check the extremes before generating all N.** Build the glyph at the
data's minimum, median and maximum, run `gv_extents.py` on those three, and look
at one. Three glyphs will tell you what a thousand would, in a fraction of the
time, and this is the step that catches "the biggest record's crown swallows its
own stem".

**Watch the direction of the encoding.** If a low score produces a *bigger*
glyph, the field will read backwards at a glance. A struggling record should not
be the largest thing on screen unless you mean it to be.

---

## 5. Readability

These are design judgements, informed by what has actually confused readers.

**Put the same datum in the same place on every glyph.** Fixed slots are what
make a field comparable: if the third bead is always the same test, the eye can
scan across records. A layout that reorders itself per record cannot be read
comparatively at all, however pretty each instance is.

**Encode important things twice.** Position *and* colour, or length *and* angle.
Redundancy survives a bad viewing angle, and it lets a reader confirm what they
think they are seeing.

**Give deviation a visible zero.** "Up is above average, down is below" only
works if the reader can see where average is. Draw the reference plane, ring or
baseline. Without it the encoding is unreadable in isolation, because there is
nothing to compare against.

**Rank by visibility, not just by size.** The most important marker belongs
where nothing occludes it — the top pole is usually free — and position matters
more than size for catching the eye. Reserve one colour for alerts and do not
use it anywhere else; if the body can be red, a red alert cap stops meaning
anything.

**Render a placeholder when data is missing.** A component that vanishes makes
the glyph read as a *different kind* of glyph. Draw it in neutral dark grey at
low alpha instead, so "absent" is visibly distinct from "small" and the anatomy
stays constant across the field.

**Every node should earn its place, and say what it is.** No decorative nodes:
if something is there for structure rather than data, note that in the scene's
documentation. And give every node a `text` label naming what it is and its
value, so a reader can click any part and learn what it encodes. A scene that
can be interrogated is worth far more than one that has to be decoded.

**Spin is invisible on a radially symmetric shape.** A rotating sphere, cone,
cylinder or torus reads as static. If rotation carries data, put it on an
asymmetric geometry, or give the part an off-axis child to act as a hand.

---

## 6. Occlusion is a design constraint, not a bug to patch

Two different things get called occlusion, and only one is a defect.

**Structural** — a component physically inside another. Always a defect when
the component is meant to be seen, always detectable at author time.
`gv_extents.py` reports it.

**Projective** — components at valid, distinct positions that line up along the
camera ray. Inherent to drawing 3D on a 2D screen. **No layout removes it** for
a dense glyph, and chasing it with small position nudges is wasted effort.

The lever that actually works is the glyph's own complexity budget. Occlusion
rises with **depth × branching factor** — total parts packed into one volume —
far more than with the choice of topology. A glyph that is four wide and three
deep puts roughly eighty parts in one region, and no single viewpoint shows them
all. Two structural notes: a **Cube** parent's children sit on its six faces,
which are exactly the six axes a camera naturally aligns to, so a cube's
occlusion cannot be tuned away by repositioning; and a **Pin** stack self-
eclipses along its own axis.

So: keep safety-critical or must-see components shallow and few, reserve deep
nesting for data the viewer will orbit, and **declare what cannot be seen from
the default view** rather than pretending it is visible. For anything where a
missed component has real consequences, that declaration is the safety net —
layout is not.

---

## 7. Laying out a field of glyphs

**Measure each glyph's real footprint after building it, then space from that.**
Estimating footprints from the design is unreliable, because tails, spokes and
crowns reach further than you think — one real case had a marker flung fourteen
units out, inflating the glyph's footprint from four to fifteen. `gv_extents.py`
reports each root's true bounding radius. Drive the layout's pitch from those
numbers, not from a guess.

**When a layout is data-driven, de-collide in two phases.** Records that are
close in the data land close in space, however generous your pitch is. So:
record every intended position first, push apart any that are closer than their
combined radii, and only then build the glyphs at the corrected positions. That
guarantees separation regardless of how the data clusters, and it is far more
reliable than tuning a spacing multiplier until it happens to work. This
technique is Dave Warner's; on a real catalogue it took overlapping pairs from
301 to 2, and the two that remained were genuine geographic coincidence that
should not have been moved.

**Scale the glyph, not the spacing, when a field reads too small.** Size travels
with the glyph into every future layout; a spacing tweak has to be redone for
each one. Because a hyperglyph resizes correctly from its root (rule 4), one
number at the root is enough.

---

## 8. Patterns that work

**The necklace.** Instead of several concentric rings at different heights —
which crowd each other and produce cross-ring collisions — put every satellite
on **one** ring, and distinguish data types by giving each its own geometry
*and* colour: spheres for one variable, cubes for another, octahedra for a
third. Group each type into a contiguous arc so counts can be read at a glance.
Keep the beads small; they carry more information than their size suggests.
Reserving the 12 and 6 o'clock positions for on-axis markers keeps those lanes
clear, and giving each type a different angular phase stops satellites lining up
radially and merging.

**`ratio` is a channel that moves nothing.** On a **Torus** parent, `ratio` sets
the tube's thickness while children on the tube stay exactly where they are —
measured: children sit at radius 2.0 under a scale-2 torus at every ratio from
0.05 to 0.4. So a torus can encode a value in its thickness without disturbing
anything mounted on it. **This is not true of Ztorus**, whose children ride the
tube's centreline and therefore move as `ratio` changes: the same test gives 1.9,
1.8, 1.5 and 1.2. Alpha is a second such channel — free to vary, moves nothing.

**Rings that carry information should not be faint.** Make scaffolding rings
thin and low-alpha so they read as structure, but if a ring's alpha or thickness
*is* the encoding, let it vary across its full range and give it enough presence
to be seen. Do not apply a uniform "make all rings faint" rule to a ring whose
visibility is the data.

**Bead chains: tie spacing to radius.** To draw a limb as a chain of overlapping
beads, set the spacing from the bead radius — roughly `1.2 × radius` — rather
than choosing a spacing independently. Otherwise thick parts overlap correctly
while thin ones dot into disconnected specks, giving the characteristic
"connected trunk, floating branches" look. Derive the bead *count* from the
limb's length divided by that spacing.

**Containers you can see into.** A wireframe hull is a click shield: wire ids
pick as their solid counterpart, so a wire sphere blocks selection of everything
inside it. To draw a container the user can reach through, build its outline
from **Plot-topology (16)** line children — latitude and longitude rings for a
sphere, edges for a box. Wrap the whole outline under one root so it moves and
scales as a single object, and if data glyphs are meant to sit on that surface,
make them children of the same root so they share its frame and cannot drift out
of register with it.

---

## 9. Working with someone who can see the render

You cannot see the scene; the user can. That asymmetry has its own discipline.

**Read the component spec back before building.** Spatial descriptions are
genuinely ambiguous in linear text. "A sphere 50% the size of the sphere at the
end" parses two ways, and the wrong reading costs a full build cycle. List each
part with its name, parent, geometry, size *reference* and position *reference*,
and let the user correct the list rather than the result.

**Express a hand-correction as a formula, never as the corrected number.** When
a user fixes a glyph by hand and shows you the file, the temptation is to copy
the value they typed. That value is only right for that one node. Work out the
*relationship* it encodes — `translate_z := scale_z`, not `translate_z = 3` —
and then verify it against a second corrected node before applying it to the
rest. A magic number that happens to work on one glyph is how a fix becomes a
new bug at the next scale.

**Warn, then do as asked.** If a request will produce something that overlaps,
occludes or reads badly, say so in a sentence and build it anyway. The user may
want exactly that, and may be testing what it looks like. Silently "fixing" the
request wastes the round trip and hides the lesson.

**Give every file a unique name.** Two scenes with the same filename in
different folders will overwrite each other the moment they land in the same
downloads directory. Put a version or a descriptor in the filename itself. Note
that Channels files pair with a node CSV by folder, so unique names and
one-scene-per-folder have to coexist.

**Ship a cheat sheet, and make it self-contained.** Every scene should come with
a note saying what each glyph, colour, size and motion means, why each channel
was chosen, and the exact format of each node's click label. Do not
cross-reference another scene's sheet: the reader will have this one open and
nothing else.

---

## See also

- `SKILL.md` rules 2–6 and 13 — the engine facts this doctrine rests on.
- `code/README.md` — running the checker that catches most of section 2.
- `references/topologies.md` — placement math, aiming, and the branching recipe.
- `references/troubleshooting.md` — symptom index for a scene that loads and
  still looks wrong.
- `examples/Wind_Rose/` and `examples/Decay_Chain/` — two worked hyperglyphs,
  each shipping a small teach-the-form scene beside a large one that puts it to
  work.
