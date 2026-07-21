#!/usr/bin/env python3
"""
build_rss_news_scene.py — GlyphViz international news visualization
===================================================================

A GlyphViz take on GaiaViz's "RSS Viz": poll the world's news feeds, count
concept mentions in each language, and render the result as concept towers
rising from a textured globe — with a Channels time replay of the last few
days of coverage and clickable headline glyphs.

Scene structure:

  * A globe World Grid (type=6, geometry=Sphere) textured with the NASA
    Blue Marble equirectangular image (media/01_bluemarble.png).
  * One news source per city, a cylinder pad placed by lon/lat on the
    globe surface. `link` = the outlet's homepage (U key / Alt+click).
  * Above each source, a CONCEPT TOWER: one cube per tracked concept at a
    fixed altitude slot (war lowest, sports highest — the same concept
    sits at the same height on every tower, so cross-outlet comparison is
    a glance). Cube size encodes how many of the outlet's articles
    mention the concept; cube color identifies the concept (legend
    column floats west of the globe). Concepts an outlet never mentioned
    leave a visible gap in its tower.
  * At each tower's top, a spinning amber octahedron carrying the
    outlet's LATEST HEADLINE as its text label and the article URL as
    its `link` — select it and press U, or Alt+click it, to read the
    story in your browser.
  * CHANNELS TIME REPLAY — one frame per BUCKET_HOURS of wall-clock
    time across the last --hours hours. During playback every concept
    cube dims to a faint baseline and flashes bright in the buckets
    where articles mentioning it were published; a cursor sweeps a
    UTC timeline bar south of the globe. Playback OFF shows the static
    all-time totals (the channel files only ever *animate* CSV values).

Term matching is concept-based and multilingual (data/terms.csv): each
concept lists per-language search terms, so a war spike is comparable
between BBC (en), TASS (ru), and NHK (ja) — you can see patterns in
languages you don't read. Matching is case-insensitive; for alphabetic
scripts terms match at word starts ("election" also hits "elections",
"вакцин" hits "вакцина"), with a trailing boundary added for very short
terms so "gas" cannot hit "Gaslight"; CJK terms match as substrings.
Counts are per-article (an article mentioning "war" five times counts
once).

Data flow (the near-real-time loop):
    fetch feeds -> merge into data/rss_items.csv (dedup by link, so the
    snapshot's time window grows across runs) -> count/bucket -> write
    gv CSVs (atomically: temp file + os.replace, channels first, node
    CSV last). With --watch N the script repeats every N seconds —
    leave it running and turn on File > Watch and Reload in GlyphViz
    for a live-updating scene.

Feeds are fetched with stdlib urllib + xml.etree only (RSS 2.0, Atom,
and RDF/RSS 1.0) — no external dependencies beyond pandas. Individual
feed failures are tolerated and reported.

Usage:
    python build_rss_news_scene.py                 # live fetch + build
    python build_rss_news_scene.py --offline       # rebuild from snapshot
    python build_rss_news_scene.py --hours 48 --bucket-hours 2
    python build_rss_news_scene.py --watch 300     # refresh every 5 min

Then File > Open rss_news_gv_node.csv in GlyphViz (media/ auto-loads,
ch files auto-load; Space plays; T shows labels; U/Alt+click opens links).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
SNAPSHOT = DATA_DIR / "rss_items.csv"

# ---------------------------------------------------------------------------
# 1. SCENE LAYOUT CONSTANTS (the knobs)
# ---------------------------------------------------------------------------
GLOBE_SCALE = 0.8               # globe radius = 180/pi * this ~= 45.8 units
GLOBE_RADIUS = 180.0 / 3.141592653589793 * GLOBE_SCALE
SRC_PAD_Z = 1.2                 # cylinder pad altitude above the surface
TOWER_BASE_Z = 5.0              # first concept slot altitude (child coords)
TOWER_STEP_Z = 4.2              # altitude between concept slots
HEADLINE_GAP_Z = 4.5            # headline octa floats this far above the top
CUBE_MIN, CUBE_MAX = 0.35, 1.6  # concept cube scale range (>= 0.2 floor)
AMBER = (255, 179, 64)          # headline / timeline accent color
BG_COLOR = (8, 10, 24, 255)     # World-row background (deep space blue)

# Channels time replay -------------------------------------------------------
STATIC_ALPHA = 235              # concept cube alpha with playback off
DIM_ALPHA = 40                  # playback baseline (concept not mentioned)
PULSE_LO, PULSE_HI = 110, 255   # active-bucket alpha ramp endpoints
HOLD_FRAMES = 12                # frames appended after the last bucket
RELIGHT_FRAMES = 8              # tail of the hold: ramp back to STATIC_ALPHA
CURSOR_CHANNEL = 900            # channel id for the timeline cursor

# Timeline bar (south of the globe, in world coordinates) --------------------
TL_Y = -(GLOBE_RADIUS + 16.0)
TL_X_MAX = GLOBE_RADIUS
TL_X_MIN = -GLOBE_RADIUS
LEGEND_X = -(GLOBE_RADIUS + 26.0)   # legend column west of the globe

# Concept slot order (tower bottom -> top) and identity colors ---------------
CONCEPTS: list[tuple[str, tuple[int, int, int]]] = [
    ("war",        (230, 40, 40)),
    ("election",   (120, 110, 220)),
    ("economy",    (200, 160, 30)),
    ("climate",    (90, 180, 70)),
    ("energy",     (255, 140, 0)),
    ("health",     (0, 190, 170)),
    ("technology", (50, 140, 240)),
    ("ai",         (230, 60, 180)),
    ("protest",    (250, 220, 60)),
    ("disaster",   (150, 75, 20)),
    ("migration",  (170, 170, 170)),
    ("sports",     (140, 220, 255)),
]
CONCEPT_ORDER = [c for c, _ in CONCEPTS]
CONCEPT_COLOR = dict(CONCEPTS)

USER_AGENT = "GlyphViz-RSS-News-example/1.0 (data visualization demo)"
FETCH_TIMEOUT = 25              # per-feed seconds
SNAPSHOT_MAX_AGE_DAYS = 14      # prune merged snapshot items older than this
HEADLINE_MAX_CHARS = 60

# CJK-script languages: terms match as plain substrings (no word boundaries).
SUBSTRING_LANGS = {"ja", "zh", "ko"}


# ---------------------------------------------------------------------------
# 2. FEED FETCHING (stdlib RSS 2.0 / Atom / RDF parser)
# ---------------------------------------------------------------------------
def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _first_text(elem: ET.Element, names: set[str]) -> str:
    for child in elem:
        if _strip_ns(child.tag) in names and child.text:
            return child.text.strip()
    return ""


def _atom_link(entry: ET.Element) -> str:
    fallback = ""
    for child in entry:
        if _strip_ns(child.tag) == "link":
            href = child.get("href", "")
            if not href:
                continue
            if child.get("rel", "alternate") == "alternate":
                return href
            fallback = fallback or href
    return fallback


def parse_feed_xml(raw: bytes) -> list[dict]:
    """Parse RSS 2.0 <item>, Atom <entry>, or RDF/RSS 1.0 <item> elements
    into [{title, link, summary, published}] (published = raw string)."""
    root = ET.fromstring(raw)
    items = []
    for elem in root.iter():
        kind = _strip_ns(elem.tag)
        if kind == "item":                       # RSS 2.0 / RDF
            title = _first_text(elem, {"title"})
            link = _first_text(elem, {"link"})
            summary = _first_text(elem, {"description", "summary"})
            published = _first_text(elem, {"pubdate", "date", "published"})
        elif kind == "entry":                    # Atom
            title = _first_text(elem, {"title"})
            link = _atom_link(elem)
            summary = _first_text(elem, {"summary", "content"})
            published = _first_text(elem, {"published", "updated"})
        else:
            continue
        if title and link:
            items.append(dict(title=title, link=link, summary=summary,
                              published=published))
    return items


def parse_when(raw: str) -> datetime | None:
    """RFC-822 or ISO-8601 timestamp -> aware UTC datetime (None if absent
    or unparseable)."""
    raw = (raw or "").strip()
    if not raw:
        return None
    for parser in (parsedate_to_datetime,
                   lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))):
        try:
            dt = parser(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


_HTML_TAG = re.compile(r"<[^>]+>")


def sanitize(text: str) -> str:
    """Strip markup and control characters — one bad byte can kill all
    tags (see CSV UTF-8 gotcha in the repo history)."""
    text = _HTML_TAG.sub(" ", str(text))
    return "".join(c for c in text
                   if unicodedata.category(c)[0] != "C").strip()


def fetch_feeds(feeds: pd.DataFrame) -> pd.DataFrame:
    """Fetch every feed, tolerating individual failures. Returns the item
    table (source, lang, title, link, summary, published_utc)."""
    rows = []
    for f in feeds.itertuples(index=False):
        try:
            req = urllib.request.Request(f.feed_url,
                                         headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
                raw = resp.read()
            items = parse_feed_xml(raw)
            for it in items:
                when = parse_when(it["published"])
                rows.append(dict(
                    source=f.source, lang=f.lang,
                    title=sanitize(it["title"]),
                    link=str(it["link"]).strip(),
                    summary=sanitize(it["summary"])[:500],
                    published_utc=when.isoformat() if when else "",
                ))
            print(f"  {f.source:<18} {len(items):>4} items")
        except Exception as exc:                 # noqa: BLE001 - keep going
            print(f"  {f.source:<18} FAILED ({exc})", file=sys.stderr)
    return pd.DataFrame(rows, columns=["source", "lang", "title", "link",
                                       "summary", "published_utc"])


def merge_snapshot(fresh: pd.DataFrame) -> pd.DataFrame:
    """Merge newly fetched items into the on-disk snapshot (dedup by
    source+link, newest fetch wins) and prune stale rows, so repeated
    --watch cycles accumulate a longer replay window than any single
    fetch provides."""
    if SNAPSHOT.exists():
        try:
            old = pd.read_csv(SNAPSHOT, encoding="utf-8").fillna("")
            fresh = pd.concat([old, fresh], ignore_index=True)
        except Exception as exc:                 # noqa: BLE001
            print(f"  snapshot unreadable, starting fresh ({exc})",
                  file=sys.stderr)
    fresh = fresh.drop_duplicates(subset=["source", "link"], keep="last")
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=SNAPSHOT_MAX_AGE_DAYS)).isoformat()
    when = fresh["published_utc"].fillna("")
    fresh = fresh[(when == "") | (when >= cutoff)]
    fresh = fresh.reset_index(drop=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fresh.to_csv(SNAPSHOT, index=False, encoding="utf-8")
    return fresh


# ---------------------------------------------------------------------------
# 3. TERM COUNTING
# ---------------------------------------------------------------------------
def load_term_matchers(terms_path: Path) -> dict[str, dict[str, list]]:
    """terms.csv -> {lang: {concept: [compiled matchers]}}.

    Alphabetic terms compile to word-start regexes (trailing boundary too
    for terms of <= 3 letters, so short terms can't hit inside longer
    words); CJK terms match as literal substrings (marked by None)."""
    df = pd.read_csv(terms_path, encoding="utf-8")
    out: dict[str, dict[str, list]] = {}
    for row in df.itertuples(index=False):
        lang = str(row.lang).strip()
        concept = str(row.concept).strip()
        for term in str(row.terms).split(";"):
            term = term.strip().lower()
            if not term:
                continue
            if lang in SUBSTRING_LANGS:
                matcher = (term, None)
            else:
                pattern = r"\b" + re.escape(term)
                if len(term) <= 3:
                    pattern += r"\b"
                matcher = (term, re.compile(pattern, re.IGNORECASE))
            out.setdefault(lang, {}).setdefault(concept, []).append(matcher)
    return out


def item_concepts(text: str, lang: str,
                  matchers: dict[str, dict[str, list]]) -> set[str]:
    """Concepts mentioned in one article (title+summary). Terms for the
    feed's language plus English are checked — non-English outlets often
    quote English names verbatim."""
    text_l = text.lower()
    hit = set()
    langs = [lang] + (["en"] if lang != "en" else [])
    for lg in langs:
        for concept, terms in matchers.get(lg, {}).items():
            if concept in hit:
                continue
            for term, rx in terms:
                if (rx.search(text_l) if rx else term in text_l):
                    hit.add(concept)
                    break
    return hit


def count_items(items: pd.DataFrame, matchers) -> pd.DataFrame:
    """Tag every item with its concept hits; returns the item table with
    a `concepts` column (semicolon-joined)."""
    concepts = []
    for it in items.itertuples(index=False):
        text = f"{it.title} {it.summary}"
        concepts.append(";".join(sorted(
            item_concepts(text, str(it.lang), matchers))))
    items = items.copy()
    items["concepts"] = concepts
    return items


# ---------------------------------------------------------------------------
# 4. SCENE BUILDER (94-column subset, same pattern as the SD exemplar)
# ---------------------------------------------------------------------------
COLUMNS = ["id", "type", "parent_id", "branch_level", "child_id",
           "translate_x", "translate_y", "translate_z",
           "rotate_x", "rotate_y", "rotate_z",
           "scale_x", "scale_y", "scale_z",
           "color_r", "color_g", "color_b", "color_a", "color_index",
           "geometry", "hide", "topo", "ratio", "texture_id",
           "ch_input_id", "rotate_rate_z",
           "trigger_lo_x", "trigger_hi_x", "trigger_lo_y", "trigger_hi_y",
           "segments_x", "segments_y", "text", "link"]

DEFAULTS = dict(child_id=0, translate_x=0.0, translate_y=0.0, translate_z=0.0,
                rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_r=255, color_g=255, color_b=255, color_a=255,
                color_index=0, geometry=3, hide=0, topo=0, ratio=0.1,
                texture_id=0, ch_input_id=0, rotate_rate_z=0.0,
                trigger_lo_x=0, trigger_hi_x=0, trigger_lo_y=0,
                trigger_hi_y=0, segments_x=16, segments_y=16,
                text="", link="")

GEO_CUBE, GEO_SPHERE, GEO_OCTA, GEO_CYLINDER, GEO_LINE_PRISM = 1, 3, 11, 19, 27


@dataclass
class SceneBuilder:
    rows: list[dict] = field(default_factory=list)
    next_id: int = 1

    def add(self, **kw) -> int:
        row = {**DEFAULTS, "id": self.next_id, **kw}
        self.rows.append(row)
        self.next_id += 1
        return row["id"]

    def build_structure(self) -> int:
        """World row + the globe grid. Returns the globe's node id."""
        self.add(type=0, parent_id=0, branch_level=0,
                 color_r=BG_COLOR[0], color_g=BG_COLOR[1],
                 color_b=BG_COLOR[2], color_a=BG_COLOR[3], geometry=0)
        return self.add(
            type=6, parent_id=0, branch_level=0, geometry=GEO_SPHERE,
            scale_x=GLOBE_SCALE, scale_y=GLOBE_SCALE, scale_z=GLOBE_SCALE,
            texture_id=1,
            trigger_lo_x=-180, trigger_hi_x=180,
            trigger_lo_y=-90, trigger_hi_y=90,
            segments_x=36, segments_y=18,
            text="World news globe (Blue Marble)")

    def build_legend(self) -> None:
        """Concept color key: a column of cubes west of the globe, slot
        order matching the towers (bottom -> top)."""
        for i, concept in enumerate(CONCEPT_ORDER):
            r, g, b = CONCEPT_COLOR[concept]
            self.add(type=5, parent_id=0, branch_level=0,
                     translate_x=LEGEND_X, translate_y=0.0,
                     translate_z=round(-22.0 + i * 4.0, 3),
                     scale_x=0.9, scale_y=0.9, scale_z=0.9,
                     geometry=GEO_CUBE, color_r=r, color_g=g, color_b=b,
                     color_a=255, text=concept)

    def build_timeline(self, t0: datetime, n_buckets: int,
                       bucket_hours: int) -> None:
        """UTC timeline bar south of the globe + the channel-driven cursor."""
        def x_of(idx: float) -> float:
            f = idx / max(n_buckets - 1, 1)
            return round(TL_X_MIN + (TL_X_MAX - TL_X_MIN) * f, 3)

        left = self.add(type=5, parent_id=0, branch_level=0,
                        translate_x=TL_X_MIN, translate_y=TL_Y,
                        scale_x=0.7, scale_y=0.7, scale_z=0.7,
                        geometry=GEO_CUBE, color_r=AMBER[0], color_g=AMBER[1],
                        color_b=AMBER[2], color_a=255,
                        text=t0.strftime("%b %d %H:%M UTC"))
        end = t0 + timedelta(hours=n_buckets * bucket_hours)
        right = self.add(type=5, parent_id=0, branch_level=0,
                         translate_x=TL_X_MAX, translate_y=TL_Y,
                         scale_x=0.7, scale_y=0.7, scale_z=0.7,
                         geometry=GEO_CUBE, color_r=AMBER[0], color_g=AMBER[1],
                         color_b=AMBER[2], color_a=255,
                         text=end.strftime("%b %d %H:%M UTC"))
        self.add(type=7, parent_id=left, child_id=right, branch_level=1,
                 geometry=GEO_LINE_PRISM, color_r=AMBER[0], color_g=AMBER[1],
                 color_b=AMBER[2], color_a=180)

        # Day ticks at UTC midnights inside the window.
        tick = t0.replace(hour=0, minute=0, second=0, microsecond=0)
        if tick < t0:
            tick += timedelta(days=1)
        while tick < end:
            idx = (tick - t0).total_seconds() / (bucket_hours * 3600.0)
            self.add(type=5, parent_id=0, branch_level=0,
                     translate_x=x_of(idx), translate_y=TL_Y,
                     translate_z=1.0, scale_x=0.6, scale_y=0.6, scale_z=1.8,
                     geometry=GEO_CUBE, color_r=AMBER[0], color_g=AMBER[1],
                     color_b=AMBER[2], color_a=220,
                     text=tick.strftime("%b %d"))
            tick += timedelta(days=1)

        self.add(type=5, parent_id=0, branch_level=0,
                 translate_x=TL_X_MIN, translate_y=TL_Y, translate_z=3.2,
                 scale_x=2.8, scale_y=2.8, scale_z=2.8, geometry=GEO_OCTA,
                 rotate_rate_z=0.6, color_r=255, color_g=220, color_b=120,
                 color_a=255, ch_input_id=CURSOR_CHANNEL, text="now")

    def add_source(self, src, totals: dict[str, int], max_total: int,
                   headline: tuple[str, str] | None,
                   channel_of: dict[tuple[str, str], int]) -> None:
        """One outlet: surface pad + concept tower + headline octa."""
        lon, lat = float(src.lon), float(src.lat)
        n_articles = sum(totals.values())
        self.add(type=5, parent_id=self.globe_id, branch_level=1,
                 translate_x=lon, translate_y=lat, translate_z=SRC_PAD_Z,
                 scale_x=1.3, scale_y=1.3, scale_z=0.35,
                 geometry=GEO_CYLINDER, ratio=0.1,
                 color_r=235, color_g=235, color_b=235, color_a=255,
                 text=str(src.source), link=str(src.homepage))
        for i, concept in enumerate(CONCEPT_ORDER):
            count = totals.get(concept, 0)
            if count == 0:
                continue                        # gap = never mentioned
            r, g, b = CONCEPT_COLOR[concept]
            s = CUBE_MIN + (CUBE_MAX - CUBE_MIN) * \
                (count / max_total) ** 0.5
            self.add(type=5, parent_id=self.globe_id, branch_level=1,
                     translate_x=lon, translate_y=lat,
                     translate_z=round(TOWER_BASE_Z + i * TOWER_STEP_Z, 3),
                     scale_x=round(s, 3), scale_y=round(s, 3),
                     scale_z=round(s, 3), geometry=GEO_CUBE,
                     color_r=r, color_g=g, color_b=b, color_a=STATIC_ALPHA,
                     ch_input_id=channel_of.get((str(src.source), concept), 0),
                     text=f"{concept} {count}")
        if headline is not None:
            title, url = headline
            top_z = TOWER_BASE_Z + len(CONCEPT_ORDER) * TOWER_STEP_Z \
                + HEADLINE_GAP_Z
            self.add(type=5, parent_id=self.globe_id, branch_level=1,
                     translate_x=lon, translate_y=lat,
                     translate_z=round(top_z, 3),
                     scale_x=1.5, scale_y=1.5, scale_z=1.5,
                     geometry=GEO_OCTA, rotate_rate_z=0.8,
                     color_r=AMBER[0], color_g=AMBER[1], color_b=AMBER[2],
                     color_a=255, text=title, link=url)

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=COLUMNS)


# ---------------------------------------------------------------------------
# 5. CHANNELS BUILDER
# ---------------------------------------------------------------------------
def bucket_items(items: pd.DataFrame, hours: int, bucket_hours: int
                 ) -> tuple[dict[tuple[str, str], list[int]], datetime, int]:
    """Per (source, concept), articles per time bucket over the replay
    window ending now. Returns (buckets, window_start, n_buckets)."""
    n_buckets = max(hours // bucket_hours, 1)
    end = datetime.now(timezone.utc).replace(minute=0, second=0,
                                             microsecond=0) \
        + timedelta(hours=1)
    start = end - timedelta(hours=n_buckets * bucket_hours)
    counts: dict[tuple[str, str], list[int]] = {}
    for it in items.itertuples(index=False):
        if not it.concepts:
            continue
        when = parse_when(str(it.published_utc))
        if when is None or not (start <= when < end):
            continue
        idx = int((when - start).total_seconds() // (bucket_hours * 3600))
        idx = min(idx, n_buckets - 1)
        for concept in str(it.concepts).split(";"):
            key = (str(it.source), concept)
            counts.setdefault(key, [0] * n_buckets)[idx] += 1
    return counts, start, n_buckets


def build_channel_files(buckets: dict[tuple[str, str], list[int]],
                        source_concepts: set[tuple[str, str]],
                        n_buckets: int
                        ) -> tuple[pd.DataFrame, pd.DataFrame,
                                   dict[tuple[str, str], int]]:
    """One color_a channel per rendered (source, concept) cube, plus the
    cursor's translate_x channel. Frames = n_buckets + HOLD_FRAMES."""
    total = n_buckets + HOLD_FRAMES
    channel_of = {key: i + 1
                  for i, key in enumerate(sorted(source_concepts))}
    gmax = max((max(v) for v in buckets.values()), default=1) or 1

    def alpha_track(counts: list[int]) -> list[int]:
        vals = []
        for f in range(total):
            c = counts[f] if f < n_buckets else 0
            a = DIM_ALPHA if c == 0 else int(round(
                PULSE_LO + (PULSE_HI - PULSE_LO) * min(c / gmax, 1.0)))
            ramp_start = total - RELIGHT_FRAMES
            if f >= ramp_start:
                t = (f - ramp_start) / max(RELIGHT_FRAMES - 1, 1)
                a = max(a, int(round(DIM_ALPHA
                                     + (STATIC_ALPHA - DIM_ALPHA) * t)))
            vals.append(a)
        return vals

    map_rows = [dict(id=i + 1, channel_id=ch, track_id=ch,
                     attribute="color_a", track_table_id=0,
                     ch_map_table_id=0, record_id=0)
                for i, (_k, ch) in enumerate(sorted(channel_of.items(),
                                                    key=lambda kv: kv[1]))]
    map_rows.append(dict(id=len(map_rows) + 1, channel_id=CURSOR_CHANNEL,
                         track_id=CURSOR_CHANNEL, attribute="translate_x",
                         track_table_id=0, ch_map_table_id=0, record_id=0))
    ch_map_df = pd.DataFrame(map_rows)

    data: dict[str, list] = {"cyclecount": list(range(1, total + 1))}
    for key, ch in sorted(channel_of.items(), key=lambda kv: kv[1]):
        data[f"ch{ch}"] = alpha_track(buckets.get(key, [0] * n_buckets))
    span = TL_X_MAX - TL_X_MIN
    data[f"ch{CURSOR_CHANNEL}"] = [
        round(TL_X_MIN + span * min(f, n_buckets - 1)
              / max(n_buckets - 1, 1), 3)
        for f in range(total)]
    return ch_map_df, pd.DataFrame(data), channel_of


# ---------------------------------------------------------------------------
# 6. VALIDATION (same three-way checks as the SD exemplar)
# ---------------------------------------------------------------------------
def validate(df: pd.DataFrame) -> list[str]:
    problems = []
    if df["id"].duplicated().any():
        problems.append("duplicate ids")
    known = set(df["id"])
    bad_parents = df[(df.parent_id != 0) & (~df.parent_id.isin(known))]
    if len(bad_parents):
        problems.append(f"{len(bad_parents)} rows with unknown parent_id")
    links = df[df.type == 7]
    if len(links) and (~links.child_id.isin(known)).any():
        problems.append("link child_id references a missing node")
    for c in ("color_r", "color_g", "color_b", "color_a"):
        if ((df[c] < 0) | (df[c] > 255)).any():
            problems.append(f"{c} out of 0..255")
    vis = df[(df.hide == 0) & (df.type.isin([5, 7]))]
    if ((vis[["scale_x", "scale_y", "scale_z"]] < 0.2).any(axis=None)):
        problems.append("visible glyph with raw scale < 0.2")
    return problems


def validate_channels(df, ch_map_df, ch_tracks_df) -> list[str]:
    problems = []
    channels = set(ch_map_df["channel_id"])
    used = set(df.loc[df.ch_input_id != 0, "ch_input_id"])
    if used - channels:
        problems.append(f"ch_input_id with no map row: "
                        f"{sorted(used - channels)}")
    if channels - used:
        problems.append(f"map channel with no node: "
                        f"{sorted(channels - used)}")
    track_cols = {int(c[2:]) for c in ch_tracks_df.columns
                  if c.startswith("ch") and c[2:].isdigit()}
    missing = set(ch_map_df["track_id"]) - track_cols
    if missing:
        problems.append(f"map track_id with no ch<id> column: "
                        f"{sorted(missing)}")
    alpha_cols = [f"ch{t}" for t in
                  ch_map_df.loc[ch_map_df.attribute == "color_a", "track_id"]]
    for c in alpha_cols:
        if ((ch_tracks_df[c] < 0) | (ch_tracks_df[c] > 255)).any():
            problems.append(f"tracks column {c}: alpha out of 0..255")
    return problems


# ---------------------------------------------------------------------------
# 7. OUTPUT (atomic writes so File > Watch and Reload never sees a torn file)
# ---------------------------------------------------------------------------
def write_csv_atomic(df: pd.DataFrame, path: str) -> None:
    tmp = f"{path}.tmp"
    df.to_csv(tmp, index=False, encoding="utf-8", lineterminator="\r\n")
    back = pd.read_csv(tmp, encoding="utf-8")
    assert len(back) == len(df), f"round-trip row-count mismatch: {path}"
    os.replace(tmp, path)


def channel_paths(node_out: str) -> tuple[str, str]:
    p = Path(node_out)
    base = p.stem[:-len("node")] if p.stem.endswith("node") else p.stem + "_"
    return (str(p.with_name(f"{base}ch-map{p.suffix}")),
            str(p.with_name(f"{base}ch-tracks{p.suffix}")))


# ---------------------------------------------------------------------------
# 8. BUILD CYCLE + MAIN
# ---------------------------------------------------------------------------
def build_once(args, feeds: pd.DataFrame, matchers) -> None:
    if args.offline:
        if not SNAPSHOT.exists():
            raise RuntimeError(f"--offline needs a snapshot at {SNAPSHOT}")
        print(f"Loading snapshot: {SNAPSHOT}")
        items = pd.read_csv(SNAPSHOT, encoding="utf-8").fillna("")
    else:
        print(f"Fetching {len(feeds)} feeds…")
        fresh = fetch_feeds(feeds)
        if fresh.empty and not SNAPSHOT.exists():
            raise RuntimeError("every feed failed and no snapshot exists")
        items = merge_snapshot(fresh)
    items = items[items["source"].isin(set(feeds["source"]))]
    print(f"  {len(items)} items in working set")

    items = count_items(items, matchers)
    tagged = int((items["concepts"] != "").sum())
    print(f"  {tagged} items mention at least one tracked concept")

    # Static totals per (source, concept) over the whole working set.
    totals: dict[str, dict[str, int]] = {}
    for it in items.itertuples(index=False):
        for concept in str(it.concepts).split(";"):
            if concept:
                totals.setdefault(str(it.source), {})
                totals[str(it.source)][concept] = \
                    totals[str(it.source)].get(concept, 0) + 1
    max_total = max((c for per in totals.values() for c in per.values()),
                    default=1)

    # Latest headline per source (parseable date required).
    headlines: dict[str, tuple[str, str]] = {}
    for it in items.itertuples(index=False):
        when = parse_when(str(it.published_utc))
        if when is None or not str(it.title):
            continue
        prev = headlines.get(str(it.source))
        if prev is None or when > prev[2]:
            title = str(it.title)
            if len(title) > HEADLINE_MAX_CHARS:
                title = title[:HEADLINE_MAX_CHARS - 1] + "…"
            headlines[str(it.source)] = (title, str(it.link), when)

    buckets, window_start, n_buckets = bucket_items(
        items, args.hours, args.bucket_hours)
    source_concepts = {(s, c) for s, per in totals.items() for c in per}
    ch_map_df, ch_tracks_df, channel_of = build_channel_files(
        buckets, source_concepts, n_buckets)
    active = sum(1 for v in buckets.values() if any(v))
    print(f"  Channels: {n_buckets} buckets x {args.bucket_hours}h "
          f"+ {HOLD_FRAMES} hold frames, {len(channel_of)} cube channels "
          f"({active} active in window) + cursor")

    sb = SceneBuilder()
    sb.globe_id = sb.build_structure()
    sb.build_legend()
    sb.build_timeline(window_start, n_buckets, args.bucket_hours)
    for src in feeds.itertuples(index=False):
        per = totals.get(str(src.source), {})
        hl = headlines.get(str(src.source))
        sb.add_source(src, per, max_total,
                      (hl[0], hl[1]) if hl else None, channel_of)

    df = sb.to_dataframe()
    problems = validate(df) + validate_channels(df, ch_map_df, ch_tracks_df)
    if problems:
        raise RuntimeError("; ".join(problems))

    # Channels first, node CSV last: the app watches the node file, so by
    # the time a reload triggers, the companion files are already in place.
    map_path, tracks_path = channel_paths(args.out)
    write_csv_atomic(ch_map_df, map_path)
    write_csv_atomic(ch_tracks_df, tracks_path)
    write_csv_atomic(df, args.out)
    print(f"Wrote {args.out}: {len(df)} rows "
          f"({len(feeds)} sources, {len(channel_of)} concept cubes). "
          "Validation clean.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--offline", action="store_true",
                    help="rebuild from data/rss_items.csv, no network")
    ap.add_argument("--hours", type=int, default=72,
                    help="replay window length (default 72)")
    ap.add_argument("--bucket-hours", type=int, default=3,
                    help="hours per animation frame (default 3)")
    ap.add_argument("--watch", type=int, metavar="SECONDS",
                    help="refresh forever every N seconds (Ctrl+C stops)")
    ap.add_argument("--feeds", default=str(DATA_DIR / "feeds.csv"))
    ap.add_argument("--terms", default=str(DATA_DIR / "terms.csv"))
    ap.add_argument("--out", default=str(HERE / "rss_news_gv_node.csv"),
                    help="output node CSV path")
    args = ap.parse_args()

    feeds = pd.read_csv(args.feeds, encoding="utf-8")
    matchers = load_term_matchers(Path(args.terms))

    while True:
        started = time.monotonic()
        try:
            build_once(args, feeds, matchers)
        except Exception as exc:                 # noqa: BLE001
            if not args.watch:
                print(f"BUILD FAILED: {exc}", file=sys.stderr)
                return 1
            print(f"cycle failed, keeping previous output: {exc}",
                  file=sys.stderr)
        print(f"  cycle took {time.monotonic() - started:.1f}s")
        if not args.watch:
            return 0
        print(f"— next refresh in {args.watch}s (Ctrl+C to stop) —")
        try:
            time.sleep(args.watch)
        except KeyboardInterrupt:
            print("stopped.")
            return 0


if __name__ == "__main__":
    sys.exit(main())
