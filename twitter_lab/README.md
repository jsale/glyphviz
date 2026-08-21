# Twitter/X Timeline Tower

A **Timeline Tower** turns an account's whole posting history into one
hyperglyph. Every post is a needle radiating from a vertical time axis:

| Channel | Meaning |
|---|---|
| **height** | when it was posted, oldest at the base |
| **bearing** | what time of day it was posted, as a 24-hour clock face |
| **needle color** | what kind of post it was |

and each needle carries concentric **rings** of measurement at fixed radii, so
one ring read across the whole tower is one variable read across a whole life.

The design is Jeff Sale's, first built for ANTz in 2018 against the Twitter v2
API. `tut.py` is its native GlyphViz reimplementation, and the reference
implementation the browser-based TUT Designer (Phase 2) must reproduce.

## Getting the data

Ask X for your archive — *Settings → Your account → Download an archive of your
data*. It arrives as a zip; unpack it and point `--archive` at the `data`
folder inside. Everything the tower needs is `tweets.js`, with
`account.js`, `profile.js` and `account-timezone.js` used when present to name
the account and clock it in its own zone.

The X archive is **richer than the v2 API timeline** the original notebooks
read: it carries a repost count per post, which the API did not, so the tower
has a reposts ring the 2018 version could not draw. It is also complete —
the API capped a timeline at the last 3,200 posts.

## Running it

```
python tut.py --archive path/to/twitter-2026-08-19/data --out DIR
python tut.py --archive DIR --out DIR --layout helix --keywords data,art
```

| Option | |
|---|---|
| `--layout` | `tower`, `immersive`, `helix`, or `all` (default) |
| `--keywords` | up to two comma-separated words to light up on the keyword ring |
| `--height` | overall height in world units (default 220) |
| `--utc` | clock the tower in UTC instead of the account's own zone |

No dependencies outside the standard library. Each layout is written as its
own scene folder holding one `_gv_node.csv` with inline `text`/`link` columns,
so it drag-and-drops straight onto GlyphViz or loads in GlyphViz Web. Every
node — needle and ring alike — carries a label naming what it encodes, and a
`link` back to the post itself, so **U** or **Alt+click** opens the real post
in a browser.

## The three layouts

All three share the same time mapping and differ only in the shape time is
wound onto.

**`tower`** — the classic form. A straight vertical axis with the needles
pointing outward, read from the outside like a core sample. This is the one
that photographs well.

**`immersive`** — the same tower turned inside out. The axis becomes a
cylindrical wall out at `IMMERSIVE_WALL` and the needles hang inward, so the
viewer stands at the centre of their own history and the record surrounds them.
Built for VR; a marker on the floor names where the account starts.

**`helix`** — time wound as a spiral, one turn per year, so seasons stack
vertically and the record never doubles back on itself. Time of day survives as
the needle's **pitch**: dawn dips, midnight rises.

## The encoding

Needle color, from the original legend:

| Color | Kind |
|---|---|
| green | original post |
| white | reply |
| dark gray | repost |
| light gray | quote post |

The archive has no quote-post flag — it was never exported — so a quote is
inferred the standard way: a post that is not a reply or a repost but whose
entities carry a link to another post.

Rings, innermost to outermost:

| Radius | Color | Measures |
|---|---|---|
| 5.5 | yellow | hashtags |
| 8.0 | magenta | % special characters |
| 10.5 | cyan | links |
| 13.0 | red / blue | keyword 1 / keyword 2 hit |
| 15.5 | orange | uppercase characters |
| 18.0 | pink | likes |
| 20.5 | violet | reposts |

A ring is emitted only when it has something to measure — an absent ring reads
as a zero, which is what it is. Counts that span orders of magnitude (likes,
reposts) are logarithmic so a viral post enlarges its ring without erasing
every ordinary one; small bounded counts are linear.

The scene sets `tag_color_mode = 1`, so every label is drawn in its own node's
color: a ring's tag text is the same color as the ring, and the scene explains
its own legend.

## Two things that are load-bearing, if you change this

**The trunk must stay at scale 1.** A node's rendered size and the frame its
children sit in are the same quantity in GlyphViz, so a trunk scaled to tower
height would stretch every needle and ring by that factor — a `scale_z = 20`
Rod trunk makes its descendants 20× too tall. Zcylinder and Spiral both take
world units straight through, which is why they are the trunks here and Rod
(the obvious choice, and the one ANTz used) is not.

**Nothing is aimed by a rotation.** Each post gets a hidden **anchor** carrying
its place in time, with `topo = Point`; everything hanging off that anchor at
one longitude reaches straight out along a single radial line, aimed by the
topology. That is what makes `lon = 0` versus `lon = 180` the entire difference
between the tower and the immersive layout, and it is why the needle — a
Cylinder glyph, whose long axis is its +Z — lies exactly along the radial with
`rotate_x/y/z` all zero. See `glyphviz-skill/references/topologies.md`,
"Pointing a glyph: use placement, not rotation".

The one deliberate rotation in the whole generator is the helix's needle pitch,
and it is **derived, not chosen**: a tilted needle of reach *R* sweeps
*R*·sin(pitch) vertically while the turn above is only `rise_per_turn` away, so
an unbounded tilt would put a midnight post from one year at the same height as
a noon post from the next. `helix_pitch_limit()` takes the tilt from the gap,
so a taller helix simply gets a more expressive one and a collision is
impossible by construction.

## Privacy

`tut.py` reads local files and writes local files. It makes no network
requests, and it deliberately ignores the parts of an X archive that a shared
scene should not carry — direct messages, ad and device data, deleted posts.
Generated scenes contain post text, so treat one as being as public as the
account it came from.
