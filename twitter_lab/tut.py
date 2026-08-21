#!/usr/bin/env python3
"""
tut.py -- Twitter/X User Timeline Tower: archive -> GlyphViz scene.

A Timeline Tower turns an account's whole posting history into one hyperglyph.
Every post is a needle radiating from a vertical time axis:

    height  = when it was posted (the account's span, bottom to top)
    bearing = what time of day it was posted (a 24-hour clock face)
    color   = what kind of post it was (original / reply / retweet / quote)

and each needle carries concentric rings of measurement -- likes, reposts,
hashtags, links, shouting, punctuation, keyword hits -- at fixed radii, so a
ring read across the whole tower is one variable read across a whole life.

Three layouts share that mapping and differ only in the shape time is wound
onto (`--layout`):

    tower      The classic form.  A straight vertical axis, needles pointing
               outward.  Read from the outside, like a core sample.

    immersive  The same tower turned inside out: the axis becomes a cylindrical
               wall far out from the origin and the needles hang inward, so the
               viewer stands at the centre of their own history.  Built for VR.

    helix      Time wound as a spiral, one turn per year, so seasons stack
               vertically and the record never doubles back on itself.  Time of
               day survives as the needle's pitch: dawn dips, midnight rises.

This is Phase 1 of the TUT Designer -- the reference implementation whose
output the browser tool must reproduce.  It reads the `data/` folder of an
official X archive ("Download an archive of your data"), which is richer than
the v2 API timeline the original 2018 notebooks consumed: repost counts are
present per post, and the account/profile files supply real identity.

Usage:
    python tut.py --archive path/to/twitter-2026-08-19/data --out DIR
    python tut.py --archive DIR --out DIR --layout helix --keywords data,art

Requires: nothing outside the standard library.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - 3.9+ always has it
    ZoneInfo = None  # type: ignore


# ---------------------------------------------------------------------------
# 1. GEOMETRY -- every number here is a world unit, measured on a scale-1 trunk
# ---------------------------------------------------------------------------
# The trunk of all three layouts is scale 1 and nothing below it is scaled by a
# parent, which is the whole reason the layouts are built the way they are: a
# node's rendered size and the frame its children sit in are the same quantity
# in GlyphViz, so a trunk scaled to tower height would stretch every needle and
# ring by that factor too.  Zcylinder and Spiral both take world units directly
# (verified against compute_world_transforms), so the trunk never has to grow.

TOWER_HEIGHT = 220.0        # bottom to top of the time axis
HUB_RADIUS = 2.0            # where a needle starts, off the axis
NEEDLE_REACH = 22.0         # where a needle ends
NEEDLE_THICKNESS = 0.2      # cross-section; >= 0.2 so the optional size floor
                            # can never alter what the scene encodes
YEAR_MARK_RADIUS = 25.0     # the labelled year ticks, just clear of the rings

IMMERSIVE_WALL = 46.0       # radius of the cylinder the viewer stands inside
HELIX_RADIUS = 38.0         # radius of the winding -- wide enough that a busy
                            # year's posts do not overlap around the turn, and
                            # that a decade of turns still reads as a coil
                            # rather than as a wire
HELIX_RISE_PER_TURN = 17.0  # vertical gap between one year and the next
HELIX_PITCH_MAX = 34.0      # ceiling on the needle tilt that carries time of day
HELIX_PITCH_HEADROOM = 0.45  # of the gap to a neighbouring turn that the tilt
                            # is allowed to consume, each way

SPIRAL_RISE_PER_TURN = 1.0  # what a Spiral parent rises per turn at scale 1;
                            # the rest of the rise is added through translate_y


# ---------------------------------------------------------------------------
# 2. THE ENCODING -- rings, colors, and what each one measures
# ---------------------------------------------------------------------------
# Radii run inward-to-outward in the order of the original Timeline Tower
# legend, with reposts added on the outside (the X archive carries a per-post
# repost count; the v2 API timeline the 2018 notebooks read did not).

KIND_COLORS = {
    "original": (0, 230, 0),        # green
    "reply": (255, 255, 255),       # white
    "retweet": (105, 105, 105),     # dark gray
    "quote": (190, 190, 190),       # light gray
}

KIND_BLURB = {
    "original": "original post",
    "reply": "reply",
    "retweet": "repost",
    "quote": "quote post",
}


@dataclass(frozen=True)
class Ring:
    """One concentric band of measurement riding every needle."""

    key: str
    radius: float
    color: tuple[int, int, int]
    label: str                       # what the ring means, for the tag text


RINGS: tuple[Ring, ...] = (
    Ring("hashtags", 5.5, (255, 255, 0), "hashtags"),
    Ring("specials", 8.0, (255, 0, 255), "% special characters"),
    Ring("urls", 10.5, (0, 255, 255), "links"),
    Ring("keyword", 13.0, (255, 0, 0), "keyword"),      # color overridden per hit
    Ring("uppercase", 15.5, (255, 153, 0), "uppercase characters"),
    Ring("likes", 18.0, (255, 0, 102), "likes"),
    Ring("reposts", 20.5, (150, 60, 255), "reposts"),
)

KEYWORD_COLORS = ((255, 0, 0), (0, 90, 255))    # keyword 1 red, keyword 2 blue

RING_FLATTEN = 0.5          # how much a ring is squashed along the needle, so
                            # it reads as a band rather than as a blob
MIN_RING_SCALE = 0.4        # a ring that exists is always big enough to see
                            # (and to click) -- below this it would read as
                            # "absent" rather than "small".  The value is
                            # 0.2 / RING_FLATTEN, which keeps even the
                            # squashed axis at the 0.2 the optional
                            # minimum-glyph-size clamp would otherwise raise
                            # it to -- a scene must encode the same thing with
                            # that setting on or off.


def ring_scale(key: str, value: float) -> float:
    """Map a measured value onto a ring's rendered size.

    Counts that span orders of magnitude (likes, reposts) are logarithmic so a
    viral post enlarges its ring without erasing every ordinary one; small
    bounded counts are linear.
    """
    if key == "likes":
        return 0.15 + 0.35 * math.log1p(value)
    if key == "reposts":
        return 0.15 + 0.45 * math.log1p(value)
    if key == "hashtags":
        return 0.30 * value
    if key == "urls":
        return 0.35 * value
    if key == "uppercase":
        # Nearly every post has some uppercase, so this ring is almost always
        # lit; it earns its place by how far it swells on a shouted post, not
        # by being present, and a steep coefficient would bury the rings
        # outside it.
        return 0.035 * value
    if key == "specials":
        return 3.0 * value          # value is a fraction 0..1
    if key == "keyword":
        return 1.20                 # a hit is a hit; presence is the signal
    raise KeyError(key)


# ---------------------------------------------------------------------------
# 3. GLYPHVIZ FORMAT CONSTANTS
# ---------------------------------------------------------------------------
TYPE_WORLD, TYPE_GLYPH = 0, 5
TOPO_NONE, TOPO_POINT, TOPO_ZCYLINDER, TOPO_SPIRAL = 0, 7, 12, 14
GEO_CUBE_SOLID, GEO_SPHERE_SOLID, GEO_CYLINDER_SOLID = 1, 3, 19
GEO_POINT, GEO_CIRCLE, GEO_STAR = 22, 24, 26
ROTATION_EULER_XYZ = 0

COLUMNS = [
    "id", "type", "parent_id", "branch_level",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo", "ratio", "rotation_mode", "show_text",
    "text", "link",
    "tag_color_mode", "tag_color_r", "tag_color_g", "tag_color_b",
    "tag_font_size",
]


# ---------------------------------------------------------------------------
# 4. READING THE ARCHIVE
# ---------------------------------------------------------------------------
# Every file in an X archive is JavaScript, not JSON: `window.YTD.<name>.partN
# = [ ... ]`.  Slicing at the first '=' leaves a plain JSON array.

TWITTER_TS = "%a %b %d %H:%M:%S %z %Y"

# Twitter stored a display name for the account's zone rather than an IANA id.
TZ_ALIASES = {
    "Pacific Time (US & Canada)": "America/Los_Angeles",
    "Mountain Time (US & Canada)": "America/Denver",
    "Central Time (US & Canada)": "America/Chicago",
    "Eastern Time (US & Canada)": "America/New_York",
    "Alaska": "America/Anchorage",
    "Hawaii": "Pacific/Honolulu",
    "London": "Europe/London",
    "Dublin": "Europe/Dublin",
    "Edinburgh": "Europe/London",
    "Lisbon": "Europe/Lisbon",
    "Paris": "Europe/Paris",
    "Berlin": "Europe/Berlin",
    "Amsterdam": "Europe/Amsterdam",
    "Madrid": "Europe/Madrid",
    "Rome": "Europe/Rome",
    "Athens": "Europe/Athens",
    "Moscow": "Europe/Moscow",
    "New Delhi": "Asia/Kolkata",
    "Tokyo": "Asia/Tokyo",
    "Seoul": "Asia/Seoul",
    "Beijing": "Asia/Shanghai",
    "Singapore": "Asia/Singapore",
    "Sydney": "Australia/Sydney",
    "Melbourne": "Australia/Melbourne",
    "Auckland": "Pacific/Auckland",
}


def read_ytd(path: Path) -> list:
    """Parse one `window.YTD.*` archive file into its JSON array."""
    raw = path.read_text(encoding="utf-8")
    try:
        start = raw.index("=")
    except ValueError:
        raise ValueError(f"{path.name} is not a window.YTD archive file")
    return json.loads(raw[start + 1:])


def unwrap(rows: list, key: str) -> list[dict]:
    """Archive arrays wrap each record in a single-key object."""
    return [r[key] for r in rows if isinstance(r, dict) and key in r]


@dataclass
class Post:
    """One post, reduced to exactly what the tower draws."""

    id_str: str
    when: datetime                  # in the account's local zone
    kind: str                       # original / reply / retweet / quote
    text: str
    likes: int
    reposts: int
    hashtags: int
    urls: int
    uppercase: int
    specials: float                 # fraction of non-alphanumeric characters
    keyword_hit: int | None = None  # index into the keyword list, if any


@dataclass
class Archive:
    username: str
    display_name: str
    bio: str
    location: str
    tz_name: str
    posts: list[Post] = field(default_factory=list)


_STATUS_URL = re.compile(r"^https?://(?:www\.)?(?:twitter|x)\.com/[^/]+/status/", re.I)


def classify(tweet: dict) -> str:
    """Which of the four kinds a post is.

    The archive has no quote-post flag -- it was never exported -- so a quote is
    inferred the standard way: a post that is not a reply or a repost but whose
    entities carry a link to another post.
    """
    if tweet.get("full_text", "").startswith("RT @"):
        return "retweet"
    if tweet.get("in_reply_to_status_id") or tweet.get("in_reply_to_user_id"):
        return "reply"
    for url in tweet.get("entities", {}).get("urls", []):
        if _STATUS_URL.match(url.get("expanded_url", "")):
            return "quote"
    return "original"


def measure(tweet: dict, tz: timezone | object, keywords: list[str]) -> Post:
    when = datetime.strptime(tweet["created_at"], TWITTER_TS).astimezone(tz)
    text = tweet.get("full_text", "")
    ents = tweet.get("entities", {})

    total = len(text)
    specials = (len(re.findall(r"[^A-Za-z0-9 ]", text)) / total) if total else 0.0

    hit = None
    lowered = text.lower()
    for i, kw in enumerate(keywords[:2]):
        if kw and kw.lower() in lowered:
            hit = i
            break

    return Post(
        id_str=tweet.get("id_str") or tweet.get("id", ""),
        when=when,
        kind=classify(tweet),
        text=text,
        likes=int(tweet.get("favorite_count", 0) or 0),
        reposts=int(tweet.get("retweet_count", 0) or 0),
        hashtags=len(ents.get("hashtags", [])),
        urls=len(ents.get("urls", [])),
        uppercase=sum(1 for c in text if c.isupper()),
        specials=specials,
        keyword_hit=hit,
    )


def load_archive(data_dir: Path, keywords: list[str], utc: bool) -> Archive:
    tweets_js = data_dir / "tweets.js"
    if not tweets_js.exists():
        raise SystemExit(f"No tweets.js in {data_dir} -- point --archive at an "
                         f"X archive's 'data' folder.")

    username, display_name, bio, location = "unknown", "", "", ""
    tz_name = "UTC"

    account_js = data_dir / "account.js"
    if account_js.exists():
        acct = unwrap(read_ytd(account_js), "account")
        if acct:
            username = acct[0].get("username", username)
            display_name = acct[0].get("accountDisplayName", "")

    profile_js = data_dir / "profile.js"
    if profile_js.exists():
        prof = unwrap(read_ytd(profile_js), "profile")
        if prof:
            desc = prof[0].get("description", {})
            bio = desc.get("bio", "")
            location = desc.get("location", "")

    tz: object = timezone.utc
    tzfile = data_dir / "account-timezone.js"
    if not utc and tzfile.exists() and ZoneInfo is not None:
        rows = unwrap(read_ytd(tzfile), "accountTimezone")
        if rows:
            raw_name = rows[0].get("timeZone", "")
            iana = TZ_ALIASES.get(raw_name, raw_name)
            try:
                tz = ZoneInfo(iana)
                tz_name = raw_name or iana
            except Exception:
                tz, tz_name = timezone.utc, "UTC"

    posts = [measure(t, tz, keywords)
             for t in unwrap(read_ytd(tweets_js), "tweet")]
    posts.sort(key=lambda p: p.when)

    return Archive(username=username, display_name=display_name, bio=bio,
                   location=location, tz_name=tz_name, posts=posts)


# ---------------------------------------------------------------------------
# 5. LABELS
# ---------------------------------------------------------------------------
# Every node gets tag text, links included, even where it repeats what a
# neighbour says: the label is what teaches the encoding to someone who opens
# the scene without the legend.  Only a handful are pinned on.

_CTRL = {c: None for c in range(32)}


def clean(s: str, limit: int = 90) -> str:
    """Make arbitrary post text safe for a CSV label.

    One unescaped control character silently drops labels downstream, so they
    are removed rather than escaped, and the text is collapsed to a single line.
    """
    s = unicodedata.normalize("NFC", s or "")
    s = s.translate(_CTRL).replace('"', "'").replace("\t", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return (s[: limit - 1] + "…") if len(s) > limit else s


def clock_label(when: datetime) -> str:
    return when.strftime("%-I:%M %p").lstrip("0") if sys.platform != "win32" \
        else when.strftime("%I:%M %p").lstrip("0")


# ---------------------------------------------------------------------------
# 6. BUILDING THE SCENE
# ---------------------------------------------------------------------------
class SceneBuilder:
    """Accumulates node rows and hands out ids."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self._next = 1

    def add(self, **kw) -> int:
        nid = self._next
        self._next += 1
        row = {c: 0 for c in COLUMNS}
        row.update(
            id=nid, type=TYPE_GLYPH, parent_id=0, branch_level=0,
            scale_x=1.0, scale_y=1.0, scale_z=1.0,
            color_r=200, color_g=200, color_b=200, color_a=255,
            geometry=GEO_CUBE_SOLID, hide=0, topo=TOPO_NONE,
            ratio=0.1, rotation_mode=ROTATION_EULER_XYZ, show_text=0,
            text="", link="",
        )
        row.update(kw)
        row["id"] = nid
        self.rows.append(row)
        return nid

    def world(self, archive: Archive) -> None:
        self.add(
            type=TYPE_WORLD, parent_id=0, branch_level=0,
            color_r=0, color_g=0, color_b=0, color_a=255,
            geometry=0, topo=TOPO_NONE,
            # Each label takes its own node's color, so a ring's tag text is
            # the same color as the ring -- the scene explains its own legend.
            tag_color_mode=1, tag_color_r=255, tag_color_g=255, tag_color_b=200,
            tag_font_size=12,
            text=f"World · Timeline Tower for @{archive.username}",
        )


def day_fraction(when: datetime) -> float:
    """Where in its own day a moment falls, 0.0 at midnight to 1.0 at midnight."""
    return (when.hour * 3600 + when.minute * 60 + when.second) / 86400.0


def clock_bearing(when: datetime) -> float:
    """Time of day as a bearing in degrees, midnight at 0 and rising with the clock."""
    return day_fraction(when) * 360.0


def helix_pitch_limit(rise_per_turn: float) -> float:
    """The largest needle tilt one turn of the helix can carry, in degrees.

    A tilted needle of reach R sweeps R·sin(pitch) vertically, and the turn
    directly above is only `rise_per_turn` away -- so an unbounded tilt puts a
    midnight post from one year at the same height as a noon post from the
    next, which is a collision in the encoding, not just in the picture.  The
    tilt is therefore derived from the gap rather than chosen, and a taller
    helix simply gets a more expressive one.
    """
    room = HELIX_PITCH_HEADROOM * rise_per_turn / NEEDLE_REACH
    return math.degrees(math.asin(min(room, math.sin(math.radians(HELIX_PITCH_MAX)))))


YEAR_SECONDS = 365.2425 * 86400.0


def build(archive: Archive, layout: str, keywords: list[str],
          height: float | None = None) -> list[dict]:
    posts = archive.posts
    if not posts:
        raise SystemExit("archive contains no posts")

    sb = SceneBuilder()
    sb.world(archive)

    t0, t1 = posts[0].when, posts[-1].when
    span = (t1 - t0).total_seconds() or 1.0
    turns = max(span / YEAR_SECONDS, 1e-9)

    # The helix is sized by the gap it needs between one year and the next,
    # not by a fixed overall height: a longer account grows taller rather than
    # winding tighter.  An explicit --height scales that proportionally.
    if height is None:
        height = turns * HELIX_RISE_PER_TURN if layout == "helix" else TOWER_HEIGHT
    elif layout == "helix":
        height = turns * HELIX_RISE_PER_TURN * (height / TOWER_HEIGHT)

    rise_per_turn = height / turns
    pitch_limit = helix_pitch_limit(rise_per_turn)
    inward = layout == "immersive"
    lon = 180.0 if inward else 0.0          # which way a needle reaches
    wall = IMMERSIVE_WALL if inward else 0.0

    zone = "UTC" if archive.tz_name == "UTC" else archive.tz_name
    axis_blurb = {
        "tower": f"height = date, bearing = time of day ({zone})",
        "immersive": f"height = date, bearing = time of day ({zone}) — "
                     f"you are standing at the centre",
        "helix": f"one turn = one year, height = date, "
                 f"needle pitch = time of day ({zone}, ±{pitch_limit:.0f}°)",
    }[layout]

    # -- the trunk: the axis time is wound onto ------------------------------
    trunk_topo = TOPO_SPIRAL if layout == "helix" else TOPO_ZCYLINDER
    trunk = sb.add(
        parent_id=0, branch_level=0, topo=trunk_topo,
        geometry=GEO_POINT, ratio=0.0, hide=1,
        translate_x=0.0, translate_y=0.0, translate_z=0.0,
        color_r=255, color_g=255, color_b=255,
        show_text=1,
        text=f"@{archive.username} · {len(posts):,} posts · "
             f"{t0:%b %Y} – {t1:%b %Y} · {axis_blurb}",
        link=f"https://x.com/{archive.username}",
    )

    # A visible pole for the two layouts that have a centre worth drawing.
    # It is a child, not the trunk itself: the trunk must stay at scale 1 or it
    # would stretch every needle hanging off it.
    if layout == "tower":
        sb.add(
            parent_id=trunk, branch_level=1, topo=TOPO_NONE,
            geometry=GEO_CYLINDER_SOLID,
            translate_x=0.0, translate_y=height / 2.0, translate_z=0.0,
            scale_x=0.35, scale_y=0.35, scale_z=height / 2.0,
            color_r=225, color_g=225, color_b=235, color_a=255,
            text=f"Time axis · {t0:%d %b %Y} at the base to "
                 f"{t1:%d %b %Y} at the top",
        )
    elif layout == "immersive":
        # At the BASE, not at mid-height: the axis is where the viewer stands,
        # so a marker halfway up sits inside their head in VR.  On the floor it
        # marks where the account starts and where the climb begins.
        sb.add(
            parent_id=trunk, branch_level=1, topo=TOPO_NONE,
            geometry=GEO_SPHERE_SOLID,
            translate_x=0.0, translate_y=0.0, translate_z=0.0,
            scale_x=1.2, scale_y=1.2, scale_z=1.2,
            color_r=255, color_g=210, color_b=90, color_a=255,
            show_text=1,
            text=f"Start here · @{archive.username} · {t0:%b %Y} · "
                 f"look outward, then climb: the wall is {len(posts):,} posts",
        )

    def place(p: Post) -> tuple[float, float, float, float]:
        """(translate_x, translate_y, translate_z, pitch) for one post's anchor."""
        frac = (p.when - t0).total_seconds() / span
        if layout == "helix":
            # One turn per year, continuous, so seasons stack vertically.  The
            # angle keeps counting past 360 -- that is what a Spiral parent
            # wants.  A Spiral rises SPIRAL_RISE_PER_TURN per turn at scale 1,
            # so translate_y supplies whatever rise is still owed.
            years = (p.when - t0).total_seconds() / YEAR_SECONDS
            tx = years * 360.0
            ty = years * (rise_per_turn - SPIRAL_RISE_PER_TURN)
            tz = HELIX_RADIUS - 1.0     # Spiral's radius is 1 + translate_z
            pitch = (day_fraction(p.when) - 0.5) * 2.0 * pitch_limit
            return tx, ty, tz, pitch
        # tower and immersive: Zcylinder takes world units straight through.
        return clock_bearing(p.when), frac * height, wall, 0.0

    needle_half = (NEEDLE_REACH - HUB_RADIUS) / 2.0
    needle_centre = HUB_RADIUS + needle_half

    for p in posts:
        tx, ty, tz, pitch = place(p)
        color = KIND_COLORS[p.kind]
        stamp = f"{p.when:%Y-%m-%d} {clock_label(p.when)}"

        # The anchor carries the post's place in time and nothing else.  It is
        # topo Point, so everything hanging off it at longitude `lon` reaches
        # straight out (or straight in) along one radial line, and every child
        # is aimed down that line by the topology rather than by a rotation.
        anchor = sb.add(
            parent_id=trunk, branch_level=1, topo=TOPO_POINT,
            geometry=GEO_POINT, ratio=0.0, hide=1,
            translate_x=tx, translate_y=ty, translate_z=tz,
            rotate_y=pitch, rotation_mode=ROTATION_EULER_XYZ,
            color_r=color[0], color_g=color[1], color_b=color[2],
            text=f"{stamp} · {KIND_BLURB[p.kind]} · anchor",
            link=f"https://x.com/{archive.username}/status/{p.id_str}",
        )

        # The needle itself.  Point topology aims a child's +Z down its own
        # offset direction, and +Z is a Cylinder glyph's long axis, so the
        # needle lies exactly along the radial with no rotation at all.
        sb.add(
            parent_id=anchor, branch_level=2, topo=TOPO_NONE,
            geometry=GEO_CYLINDER_SOLID,
            translate_x=lon, translate_y=0.0, translate_z=needle_centre,
            scale_x=NEEDLE_THICKNESS, scale_y=NEEDLE_THICKNESS,
            scale_z=needle_half,
            color_r=color[0], color_g=color[1], color_b=color[2], color_a=255,
            text=f"{stamp} · {KIND_BLURB[p.kind]} · "
                 f"{p.likes} likes, {p.reposts} reposts · {clean(p.text)}",
            link=f"https://x.com/{archive.username}/status/{p.id_str}",
        )

        # The rings.  A ring is emitted only when it has something to measure --
        # an absent ring reads as a zero, which is what it is.
        values = {
            "hashtags": float(p.hashtags),
            "specials": p.specials,
            "urls": float(p.urls),
            "keyword": 1.0 if p.keyword_hit is not None else 0.0,
            "uppercase": float(p.uppercase),
            "likes": float(p.likes),
            "reposts": float(p.reposts),
        }
        readable = {
            "hashtags": f"{p.hashtags} hashtags",
            "specials": f"{p.specials * 100:.0f}% special characters",
            "urls": f"{p.urls} links",
            "keyword": (f'keyword "{keywords[p.keyword_hit]}"'
                        if p.keyword_hit is not None else ""),
            "uppercase": f"{p.uppercase} uppercase characters",
            "likes": f"{p.likes} likes",
            "reposts": f"{p.reposts} reposts",
        }

        for ring in RINGS:
            v = values[ring.key]
            if v <= 0:
                continue
            m = max(MIN_RING_SCALE, ring_scale(ring.key, v))
            rgb = ring.color
            if ring.key == "keyword" and p.keyword_hit is not None:
                rgb = KEYWORD_COLORS[p.keyword_hit]
            sb.add(
                parent_id=anchor, branch_level=2, topo=TOPO_NONE,
                geometry=GEO_CUBE_SOLID,
                translate_x=lon, translate_y=0.0, translate_z=ring.radius,
                # +Z is radial here, so flattening Z squashes the ring against
                # the needle rather than along it.
                scale_x=m, scale_y=m, scale_z=RING_FLATTEN * m,
                color_r=rgb[0], color_g=rgb[1], color_b=rgb[2], color_a=255,
                text=f"{readable[ring.key]} · ring {ring.radius:g} "
                     f"({ring.label}) · {stamp}",
                link=f"https://x.com/{archive.username}/status/{p.id_str}",
            )

    add_year_marks(sb, trunk, layout, t0, t1, span, height, rise_per_turn)
    return sb.rows


def add_year_marks(sb: SceneBuilder, trunk: int, layout: str,
                   t0: datetime, t1: datetime, span: float, height: float,
                   rise_per_turn: float) -> None:
    """A labelled tick at each new year, so the height axis can be read."""
    inward = layout == "immersive"
    lon = 180.0 if inward else 0.0
    year = t0.year + 1
    while year <= t1.year:
        moment = t0.replace(year=year, month=1, day=1, hour=0, minute=0,
                            second=0, microsecond=0)
        if not (t0 <= moment <= t1):
            year += 1
            continue

        if layout == "helix":
            years = (moment - t0).total_seconds() / YEAR_SECONDS
            tx = years * 360.0
            ty = years * (rise_per_turn - SPIRAL_RISE_PER_TURN)
            tz = HELIX_RADIUS - 1.0
        else:
            tx = 0.0
            ty = (moment - t0).total_seconds() / span * height
            tz = IMMERSIVE_WALL if inward else 0.0

        mark = sb.add(
            parent_id=trunk, branch_level=1, topo=TOPO_POINT,
            geometry=GEO_POINT, ratio=0.0, hide=1,
            translate_x=tx, translate_y=ty, translate_z=tz,
            text=f"{year} · year mark anchor",
        )
        sb.add(
            parent_id=mark, branch_level=2, topo=TOPO_NONE,
            geometry=GEO_STAR,
            translate_x=lon, translate_y=0.0, translate_z=YEAR_MARK_RADIUS,
            scale_x=1.6, scale_y=1.6, scale_z=1.6,
            color_r=255, color_g=225, color_b=140, color_a=255,
            show_text=1,
            text=str(year),
        )
        year += 1


# ---------------------------------------------------------------------------
# 7. WRITING
# ---------------------------------------------------------------------------
def write_scene(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\r\n")
        w.writeheader()
        for r in rows:
            out = dict(r)
            for k, v in out.items():
                if isinstance(v, float):
                    out[k] = f"{v:.6f}"
            w.writerow(out)


LAYOUTS = ("tower", "immersive", "helix")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archive", required=True, type=Path,
                    help="the 'data' folder of an unpacked X archive")
    ap.add_argument("--out", required=True, type=Path,
                    help="directory to write scene folders into")
    ap.add_argument("--layout", default="all", choices=LAYOUTS + ("all",))
    ap.add_argument("--keywords", default="",
                    help="up to two comma-separated keywords to highlight")
    ap.add_argument("--height", type=float, default=None,
                    help=f"overall height in world units (default {TOWER_HEIGHT:g}; "
                         f"the helix is sized per year and scales proportionally)")
    ap.add_argument("--utc", action="store_true",
                    help="clock the tower in UTC instead of the account's zone")
    args = ap.parse_args(argv)

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()][:2]
    archive = load_archive(args.archive, keywords, args.utc)

    print(f"@{archive.username} ({archive.display_name}) — "
          f"{len(archive.posts):,} posts, "
          f"{archive.posts[0].when:%Y-%m-%d} to {archive.posts[-1].when:%Y-%m-%d}, "
          f"clocked in {archive.tz_name}")
    kinds: dict[str, int] = {}
    for p in archive.posts:
        kinds[p.kind] = kinds.get(p.kind, 0) + 1
    print("  " + ", ".join(f"{v:,} {k}" for k, v in sorted(kinds.items())))
    if keywords:
        hits = sum(1 for p in archive.posts if p.keyword_hit is not None)
        print(f"  keywords {keywords}: {hits:,} posts matched")

    wanted = LAYOUTS if args.layout == "all" else (args.layout,)
    for layout in wanted:
        rows = build(archive, layout, keywords, height=args.height)
        name = f"TUT_{archive.username}_{layout}"
        path = args.out / name / f"{name}_gv_node.csv"
        write_scene(rows, path)
        print(f"  {layout:10} {len(rows):>7,} nodes  ->  {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
