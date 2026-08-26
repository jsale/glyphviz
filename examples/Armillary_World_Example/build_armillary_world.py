"""
The Armillary World — a first pass at a navigable teaching space built out of
nested rings.

The centre is an armillary sphere: horizon, meridian, equator, ecliptic, the
tropics and the polar circles, all of them Flat Rings (geometry 33/34, added
2026-08-26) rather than tori, because an instrument is made of machined bands
with square edges and a torus reads as soft tubing. The graduated ones carry
their scale as a TEXTURE — a strip of degree markings wrapped around the ring —
which is the capability the flat faces exist to make possible.

Around it, eight concentric TOPIC ZONES, each a ring at its own radius and its
own tilt, carrying exhibits that connect a piece of mathematics to something
you can look at.

------------------------------------------------------------------------------
Two authoring rules this file follows, both worth knowing before editing it
------------------------------------------------------------------------------

1.  A ring that CARRIES CHILDREN is scaled UNIFORMLY; a ring that is only
    looked at may be scaled non-uniformly.

    A Flat Ring's radial width is `ratio` and its height is `scale_z`, so a
    wide thin dial needs scale_z != scale_x. But children of any ordinary
    parent inherit its per-axis scale, so a child of a (S, S, Z) ring comes out
    stretched. Hence the split used throughout:

      * RAILS  — uniform scale S, small ratio. The cross-section is square
                 (side 2*ratio*S), which is exactly the thin machined hoop we
                 want anyway, and every exhibit riding it inherits a clean
                 uniform S.
      * BANDS  — wide (large ratio) and thin (small scale_z), textured, and
                 childless.

2.  Sizes are authored in WORLD units and divided down.

    `add()` takes the radius the glyph should actually render at and divides
    out its parent's cumulative scale, so nothing in this file has to reason
    about inherited scale by hand. Rings placed on a TOPO_TORUS parent land at
    exactly the parent's own radius (translate_z pushes them further out as a
    fraction of it) — verified against scene.node_world_matrix.

Run:  python build_armillary_world.py [--out-dir DIR]
"""
from __future__ import annotations

import argparse
import csv
import math
import os
from itertools import count

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Geometry / topology ids (glyphviz_core.geometry_data, glyphviz_core.topology)
# ---------------------------------------------------------------------------
GEO_CUBE_WIRE, GEO_CUBE       = 0, 1
GEO_SPHERE_WIRE, GEO_SPHERE   = 2, 3
GEO_CONE_WIRE, GEO_CONE       = 4, 5
GEO_TORUS_WIRE, GEO_TORUS     = 6, 7
GEO_DODECA_WIRE, GEO_DODECA   = 8, 9
GEO_OCTA_WIRE, GEO_OCTA       = 10, 11
GEO_TETRA_WIRE, GEO_TETRA     = 12, 13
GEO_ICOSA_WIRE, GEO_ICOSA     = 14, 15
GEO_PIN                       = 16
GEO_CYLINDER_WIRE, GEO_CYLINDER = 18, 19
GEO_POINT                     = 22
GEO_CIRCLE, GEO_CROSS, GEO_STAR = 24, 25, 26
GEO_LINE                      = 27
GEO_RING, GEO_RING_WIRE       = 33, 34      # the new flat bands

TOPO_NONE, TOPO_SPHERE, TOPO_TORUS = 0, 2, 3

TYPE_WORLD, TYPE_GLYPH = 0, 5
ROT_EULER_XYZ = 0        # rotate_x/y/z each about their own named axis

STEM = "armillary_world_gv"

# ---------------------------------------------------------------------------
# Scale plan. Global Scale (base_scale) is 1.0, so these are world units.
# ---------------------------------------------------------------------------
R_HORIZON   = 46.0        # the outermost ring of the instrument itself
R_MERIDIAN  = 42.0
R_EQUATOR   = 38.0
R_ECLIPTIC  = 34.0
OBLIQUITY   = 23.44       # degrees — the ecliptic's tilt off the equator
R_EARTH     = 9.0

# The reading face of each graduated ring — the dimension its texture's v axis
# spans. For a flat dial that is the band's radial WIDTH; for a tall hoop read
# on its outer wall it is the band's THICKNESS. strip_size needs the right one.
HORIZON_WIDTH   = 7.5     # a wide, thin dial, read face-on from above
MERIDIAN_WIDTH  = 1.2     # a narrow, tall hoop...
MERIDIAN_HEIGHT = 6.5     # ...read on its outer wall
ECLIPTIC_WIDTH  = 6.2

ZONE_R0, ZONE_DR = 96.0, 34.0     # zone 1 at 96, then every 34 units out
ZONE_TILT_STEP   = 6.0            # each zone opens a little further


def zone_geom(i: int) -> tuple[float, float, float]:
    """(rail radius, band radius, band width) for zone *i*.

    Shared by the texture pass and the scene pass — a band's texture is built
    at the band's own aspect ratio (see strip_size), so the two must agree on
    what those proportions are.

    The band width is what makes the name legible, and it is deliberately
    generous: at 10 + 5% of the radius every zone lands near an aspect of 40:1
    to 70:1, which strip_size can fill at full width without squashing the
    lettering. Narrow it and the names smear.
    """
    r = ZONE_R0 + i * ZONE_DR
    return r, r * 0.955, 10.0 + 0.05 * r

BG = (6, 7, 13, 255)
BRASS       = (214, 172, 84)
BRASS_DEEP  = (176, 132, 56)
BRASS_PALE  = (238, 208, 140)

COLUMNS = [
    "id", "type", "parent_id", "branch_level",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z", "rotate_rate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo", "ratio", "texture_id",
    "rotation_mode", "show_text",
    "tag_color_mode", "tag_color_r", "tag_color_g", "tag_color_b",
    "ref_grid_color_r", "ref_grid_color_g", "ref_grid_color_b", "text",
]
# NB every column listed above is written for EVERY row, defaulting to 0 — so a
# column whose sensible default is not 0 must either be given one in DEFAULTS
# or left out of the list entirely. tag_font_size is left out: writing 0 into
# it would set every node's label to a size the viewport then has to clamp,
# where omitting the column lets the loader supply its real default (11).
DEFAULTS = {c: 0 for c in COLUMNS}
DEFAULTS.update(type=TYPE_GLYPH, scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_a=255, ratio=0.1, rotation_mode=ROT_EULER_XYZ, text="")


# ===========================================================================
# 1.  Node plumbing
# ===========================================================================
class World:
    """Accumulates rows, and remembers each node's cumulative uniform scale so
    sizes can be authored in world units (see rule 2 in the module docstring)."""

    def __init__(self):
        self.rows: list[dict] = []
        self._next = count(1)
        self.cum = {0: 1.0}        # id -> world size of one local unit
        self.level = {0: -1}

    def _row(self, parent: int, **kw) -> int:
        nid = next(self._next)
        row = dict(DEFAULTS)
        row.update(id=nid, parent_id=parent,
                   branch_level=self.level[parent] + 1)
        row.update(kw)
        self.rows.append(row)
        self.level[nid] = row["branch_level"]
        return nid

    def add(self, parent: int, size: float, **kw) -> int:
        """A glyph of world radius *size*, uniformly scaled.

        UNITS, because the two halves differ and it matters when editing:
        *size* is in WORLD units, but any translate_* passed through **kw is in
        the PARENT's own units, where 1.0 is the parent's radius. That is what
        makes an exhibit's internal layout scale with the exhibit — but a
        "1.02x its parent" twin has to be written as `size * 1.02`, not 1.02.
        Use add_at() when an offset is easier to think about in world units.
        """
        s = size / self.cum[parent]
        nid = self._row(parent, scale_x=s, scale_y=s, scale_z=s, **kw)
        self.cum[nid] = size
        return nid

    def add_at(self, parent: int, size: float, offset, **kw) -> int:
        """add(), with *offset* given in world-scale units (still along the
        parent's own axes) rather than in the parent's units."""
        k = self.cum[parent] or 1.0
        return self.add(parent, size, translate_x=offset[0] / k,
                        translate_y=offset[1] / k, translate_z=offset[2] / k,
                        **kw)

    def add_band(self, parent: int, radius: float, width: float,
                 thickness: float, **kw) -> int:
        """A Flat Ring authored the way an instrument maker would describe one:
        outer radius, radial width of the band, thickness through it.

            radial width = 2 * ratio * scale_x      (ratio is a proportion)
            height       = 2 * ratio * scale_z

        so ratio = width / (2*radius) and scale_z = thickness*radius/width.
        Non-uniform, therefore childless — see rule 1.
        """
        s = radius / self.cum[parent]
        ratio = width / (2.0 * radius)
        sz = (thickness * radius / width) / self.cum[parent]
        nid = self._row(parent, scale_x=s, scale_y=s, scale_z=sz,
                        geometry=GEO_RING, ratio=ratio, **kw)
        self.cum[nid] = radius
        return nid

    def write(self, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(self.rows)


def aim_normal(tilt_deg: float, azimuth_deg: float) -> tuple[float, float]:
    """(rotate_x, rotate_y) that tips a flat ring's axis *tilt* degrees off
    vertical, leaning towards *azimuth*.

    EULER_XYZ composes as Rx.Ry.Rz applied to a column vector, i.e. Z turns
    first and X last, so a ring's tilt direction cannot be dialled in with a
    plain "spin it about Z afterwards". Solving Rx(a).Ry(b).(0,0,1) for the
    wanted normal (sin t cos f, sin t sin f, cos t) gives these two angles —
    which is why every tilted ring in this file goes through here rather than
    setting rotate_z and hoping.
    """
    t, f = math.radians(tilt_deg), math.radians(azimuth_deg)
    sb = math.sin(t) * math.cos(f)
    sb = max(-1.0, min(1.0, sb))
    b = math.asin(sb)
    a = math.atan2(-math.sin(t) * math.sin(f), math.cos(t))
    return math.degrees(a), math.degrees(b)


def ring_of(n: int, start: float = 0.0) -> list[float]:
    """n angles evenly spaced around a circle."""
    return [start + 360.0 * i / n for i in range(n)]


def _euler_xyz(rx: float, ry: float):
    """Rx.Ry as a 3x3, matching topology._local_rotation_matrix_euler_xyz with
    rz = 0 — used to find where a point on a tilted ring actually ends up."""
    a, b = math.radians(rx), math.radians(ry)
    ca, sa, cb, sb = math.cos(a), math.sin(a), math.cos(b), math.sin(b)
    return ((cb, 0.0, sb),
            (sa * sb, ca, -sa * cb),
            (-ca * sb, sa, ca * cb))


def point_on_ring(radius: float, rx: float, ry: float,
                  angle: float) -> tuple[float, float, float]:
    """A point at *angle* around a ring of *radius* tilted by (rx, ry).

    A ring node's own position is its CENTRE, so a label pinned to the ring
    itself lands at the middle of the world with every other ring's label —
    which is exactly what the first render of this scene looked like. Markers
    go on the rim instead, where they can also be clicked.
    """
    m = _euler_xyz(rx, ry)
    v = (radius * math.cos(math.radians(angle)),
         radius * math.sin(math.radians(angle)), 0.0)
    return tuple(sum(m[r][c] * v[c] for c in range(3)) for r in range(3))


# ===========================================================================
# 2.  Textures — the reason the rings are flat
# ===========================================================================
def _font(size: int):
    for name in ("arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _text(d, xy, s, font, fill, anchor=None):
    d.text(xy, s, font=font, fill=fill, anchor=anchor)


# ---------------------------------------------------------------------------
# THE ONE RULE THAT DECIDES WHETHER A RING'S TEXTURE IS LEGIBLE
#
# u runs once around the whole circumference and v across the narrow reading
# face, so the canvas a ring hands its texture is enormously wide:
#
#     band aspect = 2*pi*radius / (the reading face's own width)
#
# Two ways to get that wrong, both of which this scene hit on the way here:
#
#   * give the image the wrong aspect (a 12:1 image on a 180:1 band smears
#     every letter sideways by 15x), or
#   * fix the aspect by repeating the content more times, which is right in
#     principle but starves each copy of pixels — 22 copies of a name in a
#     1024-wide image is 46px each, i.e. a solid white streak.
#
# So the image is built AT the band's own aspect ratio, and the number of
# repeats follows from how many legible copies actually fit. The practical
# consequence, and it is a design constraint rather than a coding one: a ring
# that carries readable text has to be a WIDE band, on the order of 10-20% of
# its own radius. Which is exactly what a real armillary's zodiac ring is.
TEX_MAX_W = 4096
TEX_MIN_H = 56


def strip_size(radius: float, face_width: float) -> tuple[int, int]:
    """Image size that maps onto this band without distorting it."""
    aspect = (2.0 * math.pi * radius) / max(face_width, 1e-6)
    h = max(TEX_MIN_H, int(round(TEX_MAX_W / aspect)))
    return min(TEX_MAX_W, int(round(h * aspect))), h


def fitting_repeats(draw, text: str, font, w: int, minimum=2,
                    gap=1.7) -> int:
    """How many copies of *text* fit across *w* at its natural size."""
    span = draw.textlength(text, font=font) * gap
    return max(minimum, int(w // max(span, 1.0)))


def graduated_strip(path: str, labels: list[tuple[float, str]],
                    minor_every: float, total: float,
                    radius: float, face_width: float,
                    ink=BRASS_PALE, tick=BRASS, bg=(20, 17, 11)):
    """A ruler wrapped into a circle.

    v = 0 is the OUTER rim on a top face and the BOTTOM edge on an outer wall
    (glyphviz_gl.geometry._draw_ring), so the graduations go along the bottom
    of the image and the numbers sit inboard of them. u runs once around the
    ring, so one pixel column is one angular step and the strip must tile at
    its own seam.
    """
    w, h = strip_size(radius, face_width)
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    font = _font(int(h * 0.46))
    n_minor = int(round(total / minor_every))
    for i in range(n_minor):
        x = int(w * i / n_minor)
        d.line([(x, h - 1), (x, h - int(h * 0.19))], fill=tick, width=3)
    for value, label in labels:
        x = int(w * value / total)
        d.line([(x, h - 1), (x, h - int(h * 0.36))], fill=ink, width=6)
        _text(d, (x, int(h * 0.06)), label, font, ink, anchor="ma")
    img.save(path)


def name_band(path: str, name: str, rgb, radius: float, face_width: float):
    """A zone's name, repeated around its band. The label IS the ring.

    Lettering goes light on a dark ground rather than the reverse: these bands
    are seen at a glancing angle from most of the world, and a mostly-dark
    texture just reads as a dark ring (which is what the first render gave).
    The zone's own colour carries the rules and the ground tint, so a band is
    identifiable from across the world well before any text is legible.
    """
    w, h = strip_size(radius, face_width)
    tint = tuple(int(c * 0.22) for c in rgb)
    img = Image.new("RGB", (w, h), tint)
    d = ImageDraw.Draw(img)
    font = _font(int(h * 0.46))
    pale = tuple(min(255, int(90 + c * 0.65)) for c in rgb)
    rule = max(3, h // 16)
    d.rectangle([0, 0, w, rule], fill=pale)
    d.rectangle([0, h - rule - 1, w, h], fill=pale)
    repeats = fitting_repeats(d, name, font, w)
    for k in range(repeats):
        cx = int(w * (k + 0.5) / repeats)
        _text(d, (cx, h // 2 + 1), name, font, (255, 252, 244), anchor="mm")
        d.regular_polygon((int(w * k / repeats), h // 2, max(5, h // 8)),
                          4, rotation=0, fill=pale)
    img.save(path)


def zodiac_band(path: str, radius: float, face_width: float):
    """Twelve signs, 30 degrees each — the one band whose repeat count is
    fixed by what it means rather than by what fits."""
    signs = ["ARIES", "TAURUS", "GEMINI", "CANCER", "LEO", "VIRGO",
             "LIBRA", "SCORPIO", "SAGITTARIUS", "CAPRICORN", "AQUARIUS",
             "PISCES"]
    w, h = strip_size(radius, face_width)
    img = Image.new("RGB", (w, h), (24, 19, 10))
    d = ImageDraw.Draw(img)
    small = _font(int(h * 0.22))
    # Sized so the longest sign fits its own 30-degree slot.
    font = _font(int(h * 0.34))
    while (getattr(font, "size", 0) > 12
           and d.textlength("SAGITTARIUS", font=font) > w / 12 * 0.86):
        font = _font(font.size - 2)
    for i, sign in enumerate(signs):
        x0 = int(w * i / 12)
        d.line([(x0, 0), (x0, h)], fill=BRASS, width=4)
        cx = int(w * (i + 0.5) / 12)
        _text(d, (cx, int(h * 0.38)), sign, font, BRASS_PALE, anchor="mm")
        _text(d, (cx, int(h * 0.72)), f"{i * 30} deg", small, BRASS,
              anchor="mm")
    img.save(path)


def build_textures(media: str) -> dict[str, int]:
    """Writes the media folder and returns name -> texture_id.

    TextureManager assigns ids by sorting the folder alphanumerically, 1-based,
    so the numeric prefixes below ARE the ids.
    """
    os.makedirs(media, exist_ok=True)
    graduated_strip(
        os.path.join(media, "01_azimuth_dial.png"),
        [(v, f"{v:g}") for v in range(0, 360, 30)], 5.0, 360.0,
        radius=R_HORIZON, face_width=HORIZON_WIDTH)
    # The meridian is graduated in DECLINATION, which is not linear in the
    # angle around the ring — it runs -90 up to +90 and back down again, so
    # each round value except the poles appears TWICE. Solving for where:
    # a point at ring angle th sits at z = -cos(th) (the ring is aimed by
    # aim_normal(90, 0)), hence dec = asin(-cos th), hence th = acos(-sin dec).
    dec_labels = []
    for dec in (-90, -60, -30, 0, 30, 60, 90):
        th = math.degrees(math.acos(-math.sin(math.radians(dec))))
        dec_labels.append((th, f"{dec:+d}"))
        if 0.5 < th < 179.5:
            dec_labels.append((360.0 - th, f"{dec:+d}"))
    # The meridian is read on its OUTER WALL, so its reading face is the band's
    # thickness, not its radial width.
    graduated_strip(
        os.path.join(media, "02_declination.png"), dec_labels, 10.0, 360.0,
        radius=R_MERIDIAN, face_width=MERIDIAN_HEIGHT,
        ink=(214, 232, 255), tick=(150, 182, 226), bg=(22, 30, 48))
    zodiac_band(os.path.join(media, "03_zodiac.png"),
                radius=R_ECLIPTIC, face_width=ECLIPTIC_WIDTH)
    ids = {"azimuth": 1, "declination": 2, "zodiac": 3}
    for i, z in enumerate(ZONES):
        _rail_r, band_r, band_w = zone_geom(i)
        name_band(os.path.join(media, f"{i + 4:02d}_zone_{z['key']}.png"),
                  z["name"], z["rgb"], radius=band_r, face_width=band_w)
        ids[z["key"]] = i + 4
    return ids


# ===========================================================================
# 3.  The instrument at the centre
# ===========================================================================
def rim_marker(w: World, hub: int, radius: float, rx: float, ry: float,
               angle: float, text: str, rgb, size=1.5,
               geometry=GEO_OCTA, pinned=1) -> int:
    """A labelled cleat on a ring's rim (see point_on_ring)."""
    x, y, z = point_on_ring(radius, rx, ry, angle)
    return w.add(hub, size, translate_x=x, translate_y=y, translate_z=z,
                 geometry=geometry, show_text=pinned, **rgbkw(rgb), text=text)


def build_instrument(w: World, hub: int, tex: dict[str, int]) -> None:
    # -- the globe it is all built around ----------------------------------
    earth = w.add(hub, R_EARTH, geometry=GEO_SPHERE, topo=TOPO_SPHERE,
                  color_r=38, color_g=74, color_b=118,
                  text="Earth - the observer's standpoint")
    # Clear of the solid globe by 2%, not 0.4%: coincident surfaces z-fight,
    # and the wire came through in patches at the tighter offset.
    w.add(earth, R_EARTH * 1.02, geometry=GEO_SPHERE_WIRE,
          color_r=132, color_g=186, color_b=228, color_a=190,
          text="graticule - the globe's own lon/lat mesh")
    for lon, lat, label in (
            (0.0, 51.5, "Greenwich  0 deg"),
            (0.0, 0.0, "the prime meridian meets the equator"),
            (-117.2, 32.7, "San Diego"),
            (135.0, -25.0, "the far side")):
        w.add(earth, R_EARTH * 0.10, translate_x=lon, translate_y=lat,
              geometry=GEO_OCTA, color_r=255, color_g=214, color_b=120,
              text=label)

    # -- horizon: the graduated azimuth dial, read face-on from above ------
    w.add_band(hub, R_HORIZON, width=HORIZON_WIDTH, thickness=0.9,
               color_r=255, color_g=255, color_b=255,
               texture_id=tex["azimuth"],
               text="HORIZON  -  azimuth 0-360 deg, graduated every 5")
    rim_marker(w, hub, R_HORIZON, 0.0, 0.0, 0.0,
               "HORIZON  -  azimuth 0 deg, graduated every 5", BRASS_PALE,
               size=1.8)

    # -- meridian: a tall band standing in the XZ plane --------------------
    rx, ry = aim_normal(90.0, 0.0)
    w.add_band(hub, R_MERIDIAN, width=MERIDIAN_WIDTH,
               thickness=MERIDIAN_HEIGHT,
               rotate_x=rx, rotate_y=ry,
               color_r=255, color_g=255, color_b=255,
               texture_id=tex["declination"],
               text="MERIDIAN  -  declination -90 to +90 deg")
    rim_marker(w, hub, R_MERIDIAN, rx, ry, 20.0,
               "MERIDIAN  -  declination, -90 to +90", (180, 214, 255), size=1.6)

    # -- equator ------------------------------------------------------------
    w.add_band(hub, R_EQUATOR, width=1.6, thickness=1.6,
               color_r=BRASS[0], color_g=BRASS[1], color_b=BRASS[2],
               text="CELESTIAL EQUATOR")
    rim_marker(w, hub, R_EQUATOR, 0.0, 0.0, 205.0,
               "CELESTIAL EQUATOR", BRASS, size=1.4)

    # -- ecliptic: the zodiac band, tilted by the obliquity ----------------
    rx, ry = aim_normal(OBLIQUITY, 90.0)
    w.add_band(hub, R_ECLIPTIC, width=ECLIPTIC_WIDTH, thickness=0.8,
               rotate_x=rx, rotate_y=ry,
               color_r=255, color_g=255, color_b=255,
               texture_id=tex["zodiac"],
               text=f"ECLIPTIC  -  the zodiac, tilted {OBLIQUITY} deg")
    rim_marker(w, hub, R_ECLIPTIC, rx, ry, 250.0,
               f"ECLIPTIC  -  the zodiac, tilted {OBLIQUITY} deg",
               BRASS_PALE, size=1.6)

    # -- the small circles: constant declination, so radius shrinks with the
    #    cosine and the ring lifts with the sine ---------------------------
    for dec, ang, label in ((OBLIQUITY, 120.0, "Tropic of Cancer  +23.44 deg"),
                            (-OBLIQUITY, 120.0, "Tropic of Capricorn  -23.44 deg"),
                            (90.0 - OBLIQUITY, 300.0, "Arctic Circle  +66.56 deg"),
                            (-(90.0 - OBLIQUITY), 300.0,
                             "Antarctic Circle  -66.56 deg")):
        r = R_EQUATOR * math.cos(math.radians(dec))
        z = R_EQUATOR * math.sin(math.radians(dec))
        w.add_band(hub, r, width=0.9, thickness=0.9, translate_z=z,
                   color_r=BRASS_DEEP[0], color_g=BRASS_DEEP[1],
                   color_b=BRASS_DEEP[2], text=label)
        x, y, _ = point_on_ring(r, 0.0, 0.0, ang)
        w.add(hub, 1.1, translate_x=x, translate_y=y, translate_z=z,
              geometry=GEO_OCTA, **rgbkw(BRASS_DEEP), text=label)

    # -- polar axis ---------------------------------------------------------
    axis = w._row(hub, scale_x=0.9, scale_y=0.9, scale_z=R_HORIZON * 0.56,
                  geometry=GEO_CYLINDER, color_r=BRASS[0], color_g=BRASS[1],
                  color_b=BRASS[2], text="POLAR AXIS")
    w.cum[axis] = 0.9
    for sign, label in ((1, "north celestial pole"), (-1, "south celestial pole")):
        w.add(hub, 1.5, translate_z=sign * R_HORIZON * 0.58,
              geometry=GEO_CONE, rotate_x=0.0 if sign > 0 else 180.0,
              color_r=BRASS_PALE[0], color_g=BRASS_PALE[1],
              color_b=BRASS_PALE[2], text=label)


# ===========================================================================
# 4.  The zones
# ===========================================================================
def spectrum_rgb(nm: float) -> tuple[int, int, int]:
    """Approximate sRGB for a wavelength in nm (Bruton's piecewise fit)."""
    if nm < 440:
        r, g, b = -(nm - 440) / 60.0, 0.0, 1.0
    elif nm < 490:
        r, g, b = 0.0, (nm - 440) / 50.0, 1.0
    elif nm < 510:
        r, g, b = 0.0, 1.0, -(nm - 510) / 20.0
    elif nm < 580:
        r, g, b = (nm - 510) / 70.0, 1.0, 0.0
    elif nm < 645:
        r, g, b = 1.0, -(nm - 645) / 65.0, 0.0
    else:
        r, g, b = 1.0, 0.0, 0.0
    if nm > 700:
        f = 0.3 + 0.7 * (780 - nm) / 80.0
    elif nm < 420:
        f = 0.3 + 0.7 * (nm - 380) / 40.0
    else:
        f = 1.0
    return tuple(int(255 * max(0.0, min(1.0, c)) ** 0.8 * f) for c in (r, g, b))


def rgbkw(rgb, alpha=255):
    return dict(color_r=rgb[0], color_g=rgb[1], color_b=rgb[2], color_a=alpha)


# --- the exhibits ----------------------------------------------------------
def z_number(w, rail, R, rgb):
    """Number & proportion."""
    phi = (1 + 5 ** 0.5) / 2

    e = w.add(rail, 2.2, translate_x=0, geometry=GEO_SPHERE, **rgbkw(rgb),
              text="phi = 1.6180339887...  the golden ratio")
    for i in range(22):                      # a golden spiral, r = phi^(th/90)
        th = i * 24.0
        r = 1.0 * phi ** (th / 90.0)
        w.add(e, 0.16 + 0.03 * i,
              translate_x=r * math.cos(math.radians(th)),
              translate_y=r * math.sin(math.radians(th)),
              geometry=GEO_SPHERE, **rgbkw(BRASS_PALE),
              text=f"turn {th:.0f} deg  r = phi^{th / 90:.2f} = {r:.3f}")

    e = w.add(rail, 2.0, translate_x=45, geometry=GEO_CUBE_WIRE, **rgbkw(rgb),
              text="Fibonacci  1 1 2 3 5 8 13 21 34 55")
    fib, a, b = [], 1, 1
    for _ in range(10):
        fib.append(a)
        a, b = b, a + b
    span = sum(fib) or 1
    x = -1.0
    for n in fib:
        s = n / span
        x += s
        w.add(e, max(0.06, s * 0.9), translate_x=x - s / 2, geometry=GEO_CUBE,
              **rgbkw(BRASS), text=f"F = {n}")
        x += s * 0.1

    e = w.add(rail, 2.0, translate_x=90, geometry=GEO_STAR, **rgbkw(rgb),
              text="the primes below 100 - 25 of them, thinning as they climb")
    primes = [p for p in range(2, 100)
              if all(p % q for q in range(2, int(p ** 0.5) + 1))]
    for p in primes:
        w.add(e, 0.10, translate_x=(p / 100.0 - 0.5) * 3.4,
              translate_z=0.4 * math.log(p) / math.log(97) - 0.2,
              geometry=GEO_PIN, **rgbkw(BRASS_PALE), text=f"prime {p}")

    e = w.add(rail, 2.0, translate_x=135, geometry=GEO_CIRCLE, **rgbkw(rgb),
              text="pi = 3.14159...  the first 24 digits, as a colour wheel")
    for i, digit in enumerate("314159265358979323846264"):
        a = 360.0 * i / 24
        shade = 60 + 20 * int(digit)
        w.add(e, 0.16, translate_x=1.2 * math.cos(math.radians(a)),
              translate_y=1.2 * math.sin(math.radians(a)),
              geometry=GEO_SPHERE,
              **rgbkw((shade, 120, 255 - shade)),
              text=f"digit {i + 1} of pi = {digit}")

    e = w.add(rail, 2.0, translate_x=180, geometry=GEO_TETRA, **rgbkw(rgb),
              text="Pascal's triangle - and the binomials hiding in it")
    for r_i in range(7):
        val = 1
        for k in range(r_i + 1):
            w.add(e, 0.08 + 0.10 * math.log1p(val) / math.log(64),
                  translate_x=(k - r_i / 2) * 0.45,
                  translate_z=(3 - r_i) * 0.42,
                  geometry=GEO_SPHERE, **rgbkw(BRASS),
                  text=f"C({r_i},{k}) = {val}")
            val = val * (r_i - k) // (k + 1)

    e = w.add(rail, 2.0, translate_x=225, geometry=GEO_CUBE, **rgbkw(rgb),
              text="the golden rectangle, nested six deep")
    for i in range(6):
        s = phi ** -i
        w.add(e, 1.0, translate_x=0.0, geometry=GEO_CUBE_WIRE,
              **rgbkw(BRASS_PALE, 190),
              text=f"rectangle {i + 1}  ratio 1 : {phi:.3f}")
        w.rows[-1].update(scale_x=s * phi / w.cum[e], scale_y=s / w.cum[e],
                          scale_z=0.02 / w.cum[e])

    e = w.add(rail, 2.0, translate_x=270, geometry=GEO_OCTA, **rgbkw(rgb),
              text="perfect numbers - 6, 28, 496 - equal to the sum of their parts")
    for i, n in enumerate((6, 28, 496)):
        w.add(e, 0.4 + 0.2 * i, translate_x=(i - 1) * 1.6, geometry=GEO_SPHERE,
              **rgbkw(BRASS), text=f"{n} is perfect")

    e = w.add(rail, 2.0, translate_x=315, geometry=GEO_ICOSA, **rgbkw(rgb),
              text="the harmonic mean, the geometric mean, the arithmetic mean")
    for i, (label, val) in enumerate((("harmonic", 0.7), ("geometric", 1.0),
                                      ("arithmetic", 1.3))):
        w.add(e, 0.35, translate_x=(i - 1) * 1.5, translate_z=val - 1.0,
              geometry=GEO_SPHERE, **rgbkw(BRASS_PALE),
              text=f"{label} mean")


def z_form(w, rail, R, rgb):
    """Geometry & form — the five solids, plus the two rings."""
    solids = [
        (GEO_TETRA, GEO_TETRA_WIRE, "Tetrahedron  4 faces  -  fire"),
        (GEO_CUBE, GEO_CUBE_WIRE, "Cube  6 faces  -  earth"),
        (GEO_OCTA, GEO_OCTA_WIRE, "Octahedron  8 faces  -  air"),
        (GEO_DODECA, GEO_DODECA_WIRE, "Dodecahedron  12 faces  -  the cosmos"),
        (GEO_ICOSA, GEO_ICOSA_WIRE, "Icosahedron  20 faces  -  water"),
    ]
    for i, (solid, wire, label) in enumerate(solids):
        a = 360.0 * i / 8
        e = w.add(rail, 2.4, translate_x=a, geometry=solid,
                  **rgbkw(rgb, 210), text=label)
        w.add(e, 2.4 * 1.02, geometry=wire, **rgbkw(BRASS_PALE),
              text=label.split("  ")[0] + " - its edges")

    e = w.add(rail, 2.4, translate_x=225, geometry=GEO_TORUS, ratio=0.28,
              **rgbkw(rgb), text="Torus - one hole, and a rounded section")
    w.add(e, 1.4, translate_z=1.6, geometry=GEO_RING, ratio=0.28,
          **rgbkw(BRASS_PALE),
          text="Flat Ring - the same extents, squared off")

    e = w.add(rail, 2.4, translate_x=270, geometry=GEO_SPHERE,
              **rgbkw(rgb, 120), text="kissing number - twelve spheres touch one")
    for i, a in enumerate(ring_of(6)):
        w.add(e, 0.5, translate_x=1.5 * math.cos(math.radians(a)),
              translate_y=1.5 * math.sin(math.radians(a)),
              geometry=GEO_SPHERE, **rgbkw(BRASS_PALE),
              text=f"neighbour {i + 1} - equator")
    for row, z in ((3, 1.3), (3, -1.3)):
        for i, a in enumerate(ring_of(row, 60.0)):
            w.add(e, 0.5, translate_x=0.87 * math.cos(math.radians(a)),
                  translate_y=0.87 * math.sin(math.radians(a)),
                  translate_z=z, geometry=GEO_SPHERE, **rgbkw(BRASS),
                  text=f"neighbour - {'upper' if z > 0 else 'lower'} cap")

    e = w.add(rail, 2.4, translate_x=315, geometry=GEO_CONE, **rgbkw(rgb),
              text="the conic sections - one cone, four curves")
    for i, (label, tilt) in enumerate((("circle", 0.0), ("ellipse", 20.0),
                                       ("parabola", 45.0), ("hyperbola", 70.0))):
        w.add(e, 1.15, translate_z=(i - 1.5) * 0.75,
              geometry=GEO_RING_WIRE, ratio=0.03,
              rotate_x=tilt, **rgbkw(BRASS_PALE), text=f"{label}  cut at {tilt:g} deg")


def z_wave(w, rail, R, rgb):
    """Wave & harmony."""
    e = w.add(rail, 2.2, translate_x=0, geometry=GEO_SPHERE, **rgbkw(rgb),
              text="the harmonic series  1, 1/2, 1/3, 1/4 ...")
    for n in range(1, 13):
        w.add(e, 0.55 / n, translate_x=(n - 6.5) * 0.55, geometry=GEO_SPHERE,
              **rgbkw(BRASS_PALE), text=f"harmonic {n}  -  1/{n} of the string")

    e = w.add(rail, 2.2, translate_x=51, geometry=GEO_RING_WIRE, ratio=0.05,
              **rgbkw(rgb), text="the octave - every doubling is the same interval")
    for n in range(7):
        w.add(e, 0.28 + 0.22 * n, geometry=GEO_RING_WIRE, ratio=0.04,
              translate_z=(n - 3) * 0.5, **rgbkw(BRASS),
              text=f"octave {n}  -  {2 ** n}x the frequency")

    for i, (num, den, label) in enumerate(((3, 2, "perfect fifth"),
                                           (4, 3, "perfect fourth"),
                                           (5, 4, "major third"))):
        e = w.add(rail, 2.0, translate_x=103 + i * 26, geometry=GEO_CIRCLE,
                  **rgbkw(rgb), text=f"{label}  {num}:{den}")
        for k, r in ((num, 1.0), (den, den / num)):
            w.add(e, r, geometry=GEO_RING, ratio=0.05,
                  translate_z=0.4 if r == 1.0 else -0.4,
                  **rgbkw(BRASS_PALE), text=f"{k} parts")

    e = w.add(rail, 2.2, translate_x=205, geometry=GEO_CYLINDER_WIRE,
              **rgbkw(rgb), text="standing waves - only whole numbers fit")
    for mode in range(1, 6):
        for i in range(25):
            u = i / 24.0
            w.add(e, 0.09, translate_x=(u - 0.5) * 4.0,
                  translate_z=(mode - 3) * 0.8
                              + 0.28 * math.sin(mode * math.pi * u),
                  geometry=GEO_SPHERE, **rgbkw(BRASS_PALE),
                  text=f"mode {mode}, sample {i}")

    e = w.add(rail, 2.2, translate_x=282, geometry=GEO_STAR, **rgbkw(rgb),
              text="beats - two close frequencies, one slow pulse")
    for i in range(40):
        u = i / 39.0
        env = math.cos(math.pi * (u - 0.5))
        w.add(e, 0.10, translate_x=(u - 0.5) * 4.4,
              translate_z=0.9 * env * math.sin(24 * u),
              geometry=GEO_SPHERE, **rgbkw(BRASS), text=f"sample {i}")


def z_symmetry(w, rail, R, rgb):
    """Symmetry & pattern — the rosettes."""
    for i, n in enumerate((3, 4, 5, 6, 8, 12)):
        a = 360.0 * i / 7
        e = w.add(rail, 2.2, translate_x=a, geometry=GEO_RING, ratio=0.10,
                  **rgbkw(rgb), text=f"{n}-fold rotational symmetry")
        for k, ang in enumerate(ring_of(n)):
            w.add(e, 0.34, translate_x=1.35 * math.cos(math.radians(ang)),
                  translate_y=1.35 * math.sin(math.radians(ang)),
                  rotate_z=ang, geometry=GEO_CONE, **rgbkw(BRASS_PALE),
                  text=f"petal {k + 1} of {n}  -  at {ang:.0f} deg")
        w.add(e, 0.4, geometry=GEO_SPHERE, **rgbkw(BRASS),
              text=f"the fixed point - {n} rotations return it to itself")

    e = w.add(rail, 2.2, translate_x=308, geometry=GEO_CUBE_WIRE, **rgbkw(rgb),
              text="reflection - the mirror the cube has nine of")
    for i, (dx, dy) in enumerate(((-1, 0), (1, 0), (0, -1), (0, 1))):
        w.add(e, 0.45, translate_x=dx * 1.3, translate_y=dy * 1.3,
              geometry=GEO_TETRA, rotate_z=90.0 * i,
              **rgbkw(BRASS_PALE), text=f"image {i + 1}")


def z_light(w, rail, R, rgb):
    """Light & colour."""
    e = w.add(rail, 2.4, translate_x=0, geometry=GEO_RING, ratio=0.08,
              **rgbkw(rgb), text="the visible spectrum  380 - 700 nm")
    for i in range(33):
        nm = 380 + i * 10
        a = 360.0 * i / 33
        w.add(e, 0.26, translate_x=1.5 * math.cos(math.radians(a)),
              translate_y=1.5 * math.sin(math.radians(a)),
              geometry=GEO_SPHERE, **rgbkw(spectrum_rgb(nm)),
              text=f"{nm} nm")

    e = w.add(rail, 2.2, translate_x=72, geometry=GEO_SPHERE,
              **rgbkw((250, 250, 250)),
              text="additive primaries - light adds up to white")
    for label, col, a in (("red", (255, 40, 40), 90), ("green", (40, 255, 40), 210),
                          ("blue", (60, 90, 255), 330)):
        w.add(e, 0.85, translate_x=1.0 * math.cos(math.radians(a)),
              translate_y=1.0 * math.sin(math.radians(a)),
              geometry=GEO_SPHERE, **rgbkw(col, 170), text=f"{label} light")

    e = w.add(rail, 2.2, translate_x=144, geometry=GEO_CIRCLE,
              **rgbkw((30, 30, 34)),
              text="subtractive primaries - pigment takes light away")
    for label, col, a in (("cyan", (0, 220, 230), 90), ("magenta", (235, 0, 190), 210),
                          ("yellow", (250, 230, 0), 330)):
        w.add(e, 0.85, translate_x=1.0 * math.cos(math.radians(a)),
              translate_y=1.0 * math.sin(math.radians(a)),
              geometry=GEO_CIRCLE, **rgbkw(col, 170), text=f"{label} ink")

    e = w.add(rail, 2.2, translate_x=216, geometry=GEO_CONE, **rgbkw(rgb),
              text="refraction - one prism, and the spectrum comes apart")
    for i in range(12):
        nm = 400 + i * 25
        w.add(e, 0.14, translate_x=1.0 + i * 0.22,
              translate_z=(5.5 - i) * 0.14, geometry=GEO_CUBE,
              **rgbkw(spectrum_rgb(nm)), text=f"ray at {nm} nm")

    e = w.add(rail, 2.2, translate_x=288, geometry=GEO_RING_WIRE, ratio=0.05,
              **rgbkw(rgb), text="the rainbow - a 42 degree cone, always")
    for i in range(24):
        nm = 400 + i * 12
        a = 180.0 + 180.0 * i / 23
        w.add(e, 0.16, translate_x=1.6 * math.cos(math.radians(a)),
              translate_z=1.6 * math.sin(math.radians(a)),
              geometry=GEO_SPHERE, **rgbkw(spectrum_rgb(nm)),
              text=f"arc at {nm} nm")


def z_growth(w, rail, R, rgb):
    """Growth & life."""
    e = w.add(rail, 2.6, translate_x=0, geometry=GEO_CIRCLE, **rgbkw(rgb),
              text="phyllotaxis - 137.5 deg, the angle a sunflower uses")
    for i in range(89):
        a = i * 137.507764
        r = 0.22 * math.sqrt(i)
        w.add(e, 0.10 + 0.0016 * i, translate_x=r * math.cos(math.radians(a)),
              translate_y=r * math.sin(math.radians(a)),
              geometry=GEO_SPHERE,
              **rgbkw((int(120 + 1.4 * i), int(180 - 0.9 * i), 70)),
              text=f"seed {i + 1}  at  {a % 360:.1f} deg")

    e = w.add(rail, 2.2, translate_x=60, geometry=GEO_POINT, ratio=0.02,
              **rgbkw(rgb, 0),
              text="branching - every fork turns 25 deg and shrinks to 0.72")

    # Worked out in the exhibit's own frame and added as one flat generation
    # of children, rather than by parenting each branch to the last: the
    # cumulative scale would shrink by the segment's own radius at every level
    # and collapse the tree into a speck after two forks.
    def branch(x, z, angle, length, depth):
        tip = (x + length * math.sin(math.radians(angle)),
               z + length * math.cos(math.radians(angle)))
        beads = max(3, int(length * 5))
        for k in range(beads + 1):
            f = k / beads
            w.add_at(e, 0.055 + 0.10 * depth / 4.0,
                     (x + (tip[0] - x) * f, 0.0, z + (tip[1] - z) * f),
                     geometry=GEO_SPHERE,
                     **rgbkw((104 + 20 * depth, 74 + 16 * depth, 48)),
                     text=f"branch, order {5 - depth}")
        if depth > 1:
            for side in (-1, 1):
                branch(tip[0], tip[1], angle + side * 25.0,
                       length * 0.72, depth - 1)

    branch(0.0, -2.4, 0.0, 2.0, 4)

    e = w.add(rail, 2.2, translate_x=120, geometry=GEO_SPHERE, **rgbkw(rgb),
              text="cell division - 1, 2, 4, 8, 16")
    for gen in range(5):
        n = 2 ** gen
        for k in range(n):
            a = 360.0 * k / n
            w.add(e, 0.7 / (gen + 1), translate_x=(gen - 2) * 1.2,
                  translate_y=0.5 * (gen ** 0.5) * math.cos(math.radians(a)),
                  translate_z=0.5 * (gen ** 0.5) * math.sin(math.radians(a)),
                  geometry=GEO_SPHERE, **rgbkw((200, 220, 190)),
                  text=f"generation {gen}  -  cell {k + 1} of {n}")

    e = w.add(rail, 2.2, translate_x=180, geometry=GEO_SPHERE_WIRE, **rgbkw(rgb),
              text="the nautilus - a logarithmic spiral holds its shape as it grows")
    for i in range(46):
        th = i * 16.0
        r = 0.14 * math.exp(0.106 * math.radians(th) * 3)
        if r > 2.2:
            break
        w.add(e, 0.05 + r * 0.16, translate_x=r * math.cos(math.radians(th)),
              translate_y=r * math.sin(math.radians(th)),
              geometry=GEO_SPHERE, **rgbkw(BRASS_PALE),
              text=f"chamber {i + 1}")

    e = w.add(rail, 2.2, translate_x=240, geometry=GEO_ICOSA, **rgbkw(rgb),
              text="the virus - why so many are icosahedral")
    for a in ring_of(12):
        w.add(e, 0.2, translate_x=1.15 * math.cos(math.radians(a)),
              translate_y=1.15 * math.sin(math.radians(a)),
              geometry=GEO_CONE, rotate_z=a, **rgbkw((190, 120, 210)),
              text="capsid spike")

    e = w.add(rail, 2.2, translate_x=300, geometry=GEO_CYLINDER_WIRE,
              **rgbkw(rgb), text="the double helix - two strands, ten rungs a turn")
    for i in range(44):
        th = i * 36.0
        z = (i - 22) * 0.11
        for side in (0.0, 180.0):
            w.add(e, 0.11, translate_x=0.75 * math.cos(math.radians(th + side)),
                  translate_y=0.75 * math.sin(math.radians(th + side)),
                  translate_z=z, geometry=GEO_SPHERE,
                  **rgbkw((90, 200, 235) if side == 0 else (235, 150, 90)),
                  text=f"base pair {i + 1}")


def z_motion(w, rail, R, rgb):
    """Motion & time — a working orrery."""
    e = w.add(rail, 3.0, translate_x=0, geometry=GEO_SPHERE,
              **rgbkw((255, 214, 110)),
              text="a small orrery - the inner planets, to scale in period")
    planets = [
        ("Mercury", 1.0, 88.0, (170, 160, 150)),
        ("Venus", 1.5, 225.0, (222, 190, 130)),
        ("Earth", 2.0, 365.25, (80, 140, 210)),
        ("Mars", 2.6, 687.0, (200, 100, 70)),
    ]
    for name, r, period, col in planets:
        w.add(e, r, geometry=GEO_RING_WIRE, ratio=0.02,
              **rgbkw(BRASS_DEEP, 150),
              text=f"{name}'s orbit  -  {period:g} days")
        arm = w.add(e, r, geometry=GEO_POINT, topo=TOPO_TORUS, ratio=0.02,
                    rotate_rate_z=6.0 / period,
                    **rgbkw(BRASS_DEEP, 0), text=f"{name} - orbital arm")
        w.add(arm, 0.20 + 0.05 * r, geometry=GEO_SPHERE, **rgbkw(col),
              text=f"{name}  -  one lap every {period:g} days")

    e = w.add(rail, 2.2, translate_x=72, geometry=GEO_CONE, **rgbkw(rgb),
              text="the pendulum - period depends on length, not on weight")
    for i, L in enumerate((0.6, 1.0, 1.5, 2.1)):
        w.add(e, 0.28, translate_x=(i - 1.5) * 0.9, translate_z=-L,
              geometry=GEO_SPHERE, **rgbkw(BRASS_PALE),
              text=f"bob {i + 1}  -  length {L:g}, period ~ sqrt(L)")

    e = w.add(rail, 2.2, translate_x=144, geometry=GEO_RING, ratio=0.12,
              rotate_rate_z=0.02, **rgbkw(rgb),
              text="the clock face - twelve hours, and it is turning")
    for h in range(12):
        a = 90.0 - 30.0 * h
        w.add(e, 0.22 if h % 3 else 0.34,
              translate_x=1.35 * math.cos(math.radians(a)),
              translate_y=1.35 * math.sin(math.radians(a)),
              geometry=GEO_CUBE, rotate_z=a, **rgbkw(BRASS_PALE),
              text=f"{12 if h == 0 else h} o'clock")

    e = w.add(rail, 2.2, translate_x=216, geometry=GEO_SPHERE, **rgbkw(rgb),
              text="escape velocity - the speed that never comes back")
    for i in range(18):
        u = i / 17.0
        w.add(e, 0.12, translate_x=(u - 0.5) * 4.0,
              translate_z=1.4 * (1 - (1 - u) ** 0.5) - 0.7,
              geometry=GEO_SPHERE, **rgbkw(BRASS), text=f"trajectory sample {i}")

    e = w.add(rail, 2.2, translate_x=288, geometry=GEO_RING_WIRE, ratio=0.04,
              **rgbkw(rgb), text="Kepler's second law - equal areas, equal times")
    for i in range(16):
        a = 360.0 * i / 16
        r = 1.7 / (1 + 0.55 * math.cos(math.radians(a)))
        w.add(e, 0.13, translate_x=r * math.cos(math.radians(a)),
              translate_y=r * math.sin(math.radians(a)),
              geometry=GEO_SPHERE, **rgbkw(BRASS_PALE),
              text=f"sweep {i + 1}  -  r = {r:.2f}")


def z_cosmos(w, rail, R, rgb):
    """Scale & cosmos — the ladder of magnitudes, which is also the
    navigation problem this world poses."""
    ladder = [
        (-15, "atomic nucleus", (255, 120, 120)),
        (-10, "a hydrogen atom", (255, 170, 110)),
        (-9, "a DNA helix, across", (250, 220, 120)),
        (-6, "a red blood cell", (190, 235, 130)),
        (-3, "a grain of sand", (130, 230, 170)),
        (0, "a person", (120, 220, 230)),
        (3, "a small town", (130, 180, 245)),
        (7, "the Earth", (150, 150, 250)),
        (11, "the Earth's orbit", (190, 140, 240)),
        (16, "the nearest star", (230, 140, 220)),
        (21, "the Milky Way", (245, 150, 180)),
        (26, "the observable universe", (250, 250, 250)),
    ]
    for i, (power, label, col) in enumerate(ladder):
        a = 360.0 * i / len(ladder)
        size = 0.9 + 0.20 * i
        e = w.add(rail, size, translate_x=a, geometry=GEO_SPHERE,
                  **rgbkw(col), text=f"10^{power} m  -  {label}")
        w.add(e, size * 1.3, geometry=GEO_SPHERE_WIRE, **rgbkw(col, 110),
              text=f"10^{power} m  -  each step out is a power of ten")

    e = w.add(rail, 2.4, translate_x=15, geometry=GEO_RING, ratio=0.06,
              **rgbkw(rgb),
              text="a logarithmic ruler - every ring is ten times the last")
    for i in range(8):
        w.add(e, 0.30 + 0.20 * i, geometry=GEO_RING_WIRE, ratio=0.03,
              translate_z=(i - 3.5) * 0.28, **rgbkw(BRASS, 200),
              text=f"x10^{i}")


ZONES = [
    dict(key="number", name="NUMBER & PROPORTION", rgb=(255, 198, 96),
         build=z_number,
         blurb="ratio, sequence and the shapes hiding inside arithmetic"),
    dict(key="form", name="GEOMETRY & FORM", rgb=(120, 226, 236),
         build=z_form,
         blurb="the five solids, and the curves one cone can cut"),
    dict(key="wave", name="WAVE & HARMONY", rgb=(186, 150, 250),
         build=z_wave,
         blurb="why a string divided by whole numbers sounds right"),
    dict(key="symmetry", name="SYMMETRY & PATTERN", rgb=(140, 232, 168),
         build=z_symmetry,
         blurb="what stays the same when everything moves"),
    dict(key="light", name="LIGHT & COLOUR", rgb=(255, 158, 132),
         build=z_light,
         blurb="wavelength becoming colour becoming paint"),
    dict(key="growth", name="GROWTH & LIFE", rgb=(168, 226, 120),
         build=z_growth,
         blurb="the angles and spirals living things keep arriving at"),
    dict(key="motion", name="MOTION & TIME", rgb=(255, 186, 92),
         build=z_motion,
         blurb="orbits, pendulums, and the clocks they became"),
    dict(key="cosmos", name="SCALE & COSMOS", rgb=(150, 178, 255),
         build=z_cosmos,
         blurb="twenty-six powers of ten, end to end"),
]


def build_zones(w: World, hub: int, tex: dict[str, int]) -> None:
    for i, z in enumerate(ZONES):
        R, band_r, band_w = zone_geom(i)
        tilt = ZONE_TILT_STEP * i
        azimuth = 137.5 * i                    # spread the lean around
        rx, ry = aim_normal(tilt, azimuth)

        # The RAIL: uniform scale, so its exhibits inherit cleanly (rule 1).
        rail = w.add(hub, R, geometry=GEO_RING, ratio=0.0042, topo=TOPO_TORUS,
                     rotate_x=rx, rotate_y=ry, rotate_rate_z=0.004 + 0.001 * i,
                     **rgbkw(z["rgb"]),
                     text=f"ZONE {i + 1} rail  -  {z['name']}")

        # The BAND: wide, thin and textured with the zone's own name.
        w.add_band(hub, band_r, width=band_w, thickness=0.7,
                   rotate_x=rx, rotate_y=ry,
                   color_r=255, color_g=255, color_b=255,
                   texture_id=tex[z["key"]],
                   text=f"{z['name']} - the zone's name, wrapped around its band")

        # The GATEWAY: the one pinned label per zone, and the thing you click
        # or press F on to be taken there. It rides the rail like any exhibit,
        # so it stays on the rim wherever the ring is tilted or turned to.
        # Each gateway sits at a different angle on its own ring: at the same
        # angle they project on top of one another from most viewpoints, and
        # eight pinned labels then land in one unreadable stack.
        gate = w.add(rail, 3.2, translate_x=45.0 * i, geometry=GEO_PIN,
                     rotate_x=-90.0, **rgbkw(z["rgb"]), show_text=1,
                     text=f"ZONE {i + 1}   {z['name']}  -  {z['blurb']}")
        w.add(gate, 0.42, translate_z=1.05, geometry=GEO_SPHERE,
              **rgbkw(BRASS_PALE), text=f"zone {i + 1} beacon")

        z["build"](w, rail, R, z["rgb"])


# ===========================================================================
# 5.  Assembly
# ===========================================================================
def build(out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    tex = build_textures(os.path.join(out_dir, "media"))

    w = World()
    # The World row: background, and the look of every label.
    w._row(0, type=TYPE_WORLD, color_r=BG[0], color_g=BG[1], color_b=BG[2],
           tag_color_mode=1, tag_color_r=236, tag_color_g=226, tag_color_b=198,
           ref_grid_color_r=26, ref_grid_color_g=30, ref_grid_color_b=44,
           text="The Armillary World")

    hub = w.add(0, 1.0, geometry=GEO_POINT, ratio=0.10,
                **rgbkw(BRASS_PALE),
                text="THE ARMILLARY WORLD  -  the whole scene hangs off this node")

    build_instrument(w, hub, tex)
    build_zones(w, hub, tex)

    path = os.path.join(out_dir, f"{STEM}_node.csv")
    w.write(path)
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "Armillary_World"))
    args = ap.parse_args()
    path = build(args.out_dir)
    with open(path, encoding="utf-8") as fh:
        n = sum(1 for _ in fh) - 1
    print(f"{path}  ({n} nodes)")


if __name__ == "__main__":
    main()
