"""Timeline Tower Designer — the browser tool in twitter_lab/.

Like the Tree Designer, the tool ships in two places: `twitter_lab/` is the
source of truth and `glyphviz-docs/docs/twitter_lab/` is the copy mkdocs
serves. Nothing in the build copies one to the other, so this test is the only
thing standing between them and silent drift.

It also pins the two claims the docs page makes on the tool's behalf, because
both are promises to a user about their own data:

  * the page is **self-contained** — it has to run from a file:// path and from
    the docs site with no build step;
  * the page makes **no network requests of any kind**, which is the entire
    reason it is safe to drop a personal archive on it.

The encoding itself is pinned on the Python side against `twitter_lab/tut.py`,
which is the reference implementation; `twitter_lab/parity_check.mjs` is what
proves the page agrees with it, and needs node, so it is not run from here.
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "twitter_lab" / "tut_designer.html"
DOCS_COPY = REPO / "glyphviz-docs" / "docs" / "twitter_lab" / "tut_designer.html"
DOCS_PAGE = REPO / "glyphviz-docs" / "docs" / "reference" / "timeline-tower.md"


def test_tool_ships_in_twitter_lab():
    assert TOOL.is_file(), f"{TOOL} is missing"


def test_docs_copy_is_identical():
    """The docs site serves its own copy; if they diverge, the published tool
    silently stops matching the repo's."""
    assert DOCS_COPY.is_file(), (
        f"{DOCS_COPY} is missing — the docs site would 404 on the "
        "Timeline Tower Designer link")
    assert DOCS_COPY.read_bytes() == TOOL.read_bytes(), (
        "twitter_lab/tut_designer.html and the docs copy have drifted. "
        "Copy the twitter_lab/ one over the docs one.")


def test_tool_is_self_contained():
    html = TOOL.read_text(encoding="utf-8")
    for pattern in (r'<script[^>]+src=', r'<link[^>]+stylesheet',
                    r'\bimport\s+.*\bfrom\s+[\'"]'):
        assert not re.search(pattern, html), \
            f"tool pulls in an external resource: {pattern}"


def test_tool_makes_no_network_requests():
    """The privacy claim, checked rather than trusted.

    The page tells the user their archive never leaves the browser, and the
    docs page repeats it. That is only true while the tool has no way to send
    anything anywhere.
    """
    html = TOOL.read_text(encoding="utf-8")
    for api in ("fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon",
                "EventSource", "navigator.connection"):
        assert api not in html, f"tool can reach the network via {api}"

    # The only host named anywhere in the source should be x.com, and only
    # because the tool writes post links INTO the scene as each node's `link`
    # — strings in the CSV, never fetched. (They are template literals, so
    # compare hosts rather than whole URLs.)
    hosts = {m.group(1) for m in re.finditer(r'https?://([^/\s"\'`)$]+)', html)}
    assert hosts <= {"x.com"}, f"unexpected hosts in the tool: {hosts}"


def test_tool_has_no_stray_control_characters():
    """A literal control character in the source breaks the page rather than
    the label it was meant to strip, and is invisible in a diff."""
    text = TOOL.read_text(encoding="utf-8")
    stray = {c for c in text if ord(c) < 32 and c not in "\r\n\t"}
    assert not stray, f"stray control characters in the tool: {stray!r}"


def test_docs_page_links_to_the_tool_and_is_in_the_nav():
    assert DOCS_PAGE.is_file()
    text = DOCS_PAGE.read_text(encoding="utf-8")
    assert "../twitter_lab/tut_designer.html" in text
    nav = (REPO / "glyphviz-docs" / "mkdocs.yml").read_text(encoding="utf-8")
    assert "reference/timeline-tower.md" in nav, "page is not in the nav"


def test_docs_page_images_exist():
    """A docs page that references a missing image builds clean and renders
    broken."""
    text = DOCS_PAGE.read_text(encoding="utf-8")
    refs = re.findall(r'!\[[^\]]*\]\(\.\./([^)]+)\)', text)
    assert refs, "docs page has no images"
    for rel in refs:
        img = REPO / "glyphviz-docs" / "docs" / rel
        assert img.is_file(), f"docs page references missing image {rel}"


# --- the encoding the docs page documents ----------------------------------

def _tut():
    import sys
    sys.path.insert(0, str(REPO / "twitter_lab"))
    import tut
    return tut


def test_ring_table_matches_the_documented_legend():
    """The docs page prints the ring radii and colors as a table a reader will
    trust while looking at their own tower."""
    tut = _tut()
    documented = {
        "hashtags": (5.5, (255, 255, 0)),
        "specials": (8.0, (255, 0, 255)),
        "urls": (10.5, (0, 255, 255)),
        "keyword": (13.0, (255, 0, 0)),
        "uppercase": (15.5, (255, 153, 0)),
        "likes": (18.0, (255, 0, 102)),
        "reposts": (20.5, (150, 60, 255)),
    }
    assert {r.key: (r.radius, r.color) for r in tut.RINGS} == documented

    page = DOCS_PAGE.read_text(encoding="utf-8")
    for ring in tut.RINGS:
        assert f"| {ring.radius} |" in page, \
            f"ring radius {ring.radius} is not in the docs table"


def test_min_ring_scale_keeps_the_squashed_axis_off_the_floor():
    """MIN_RING_SCALE exists so that even a ring's flattened axis clears the
    0.2 the optional minimum-glyph-size clamp would otherwise raise it to — a
    scene has to encode the same thing with that setting on or off."""
    tut = _tut()
    assert tut.MIN_RING_SCALE * tut.RING_FLATTEN == pytest.approx(0.2)


def test_helix_pitch_can_never_reach_the_next_turn():
    """The needle tilt that carries time of day is derived from the gap to the
    turn above, not chosen, so one year's midnight can never land at the next
    year's noon."""
    import math
    tut = _tut()
    for rise in (8.0, 17.0, 26.0, 45.0, 200.0):
        pitch = tut.helix_pitch_limit(rise)
        reach = tut.NEEDLE_REACH * math.sin(math.radians(pitch))
        assert reach < rise / 2, f"tilt at rise {rise} reaches into the next turn"
        assert pitch <= tut.HELIX_PITCH_MAX + 1e-9
