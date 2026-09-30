"""The shared glyph language: one session -> one helical column.

Both scene builders draw from here, so a column means the same thing in either
scene and in every project bank.

THE ENCODING
------------
A column is one continuous **Spiral** winding, read bottom to top, with one
child per event in the order it happened:

    warm-white SPHERE    a prompt, sized by word count
    violet WIRE SPHERE   that turn's thinking, sized by block count, standing
                         just inside the coil between the prompt and the first
                         tool call -- BESIDE the prompt, never around it
    blue OCTAHEDRON      explore  -- Read, Grep, Glob, Web
    green CUBE           mutate   -- Edit, Write
    orange TETRAHEDRON   execute  -- Bash, PowerShell
    magenta DODECAHEDRON meta     -- TodoWrite, Agent, AskUserQuestion
    red CONE             a tool call that came back an error
    gold RING on the axis   a git commit
    cyan ICOSAHEDRON outside the coil   an image or file pasted with a prompt

    pedestal COLOUR      which project (config.PROJECTS)

The angle advances a fixed step per event, so **column height is how much work
happened**, not how long it took: one winding is 360 / step_tool tool calls of
arc. The four tool families ride four slightly different radii, which makes a
run of one colour read as a thread rather than confetti. Idle time before a
prompt becomes extra blank arc, so the pauses stay visible.

GEOMETRY NOTES (why the numbers are what they are)
--------------------------------------------------
* Spiral places a child at ((B+tz)cos tx, (B+tz)sin tx, (tx/360)B + ty) with
  B = the global base scale (1 by default), and turns it by Rz(tx). So the coil
  radius is 1 + tz, one winding rises 1 unit, and tz = -1 puts a child on the
  axis -- which is how the commit rings, pedestal, cap and axis line are centred.
* Spiral's own pitch is therefore fixed, and at a small coil radius it reads as
  a stack of rings. translate_y is Spiral's "extra height" axis, so adding a
  rise proportional to the angle buys an independent pitch
  (ColumnStyle.pitch = world units per winding).
* Every column root is a Point at scale 1.0. A parent's scale multiplies its
  children's placement, so the root must stay at 1; Point is the one geometry
  whose size comes from `ratio` (pixels) instead of scale, so it can be scale 1
  and still nearly invisible.
* Markers are orientation-tolerant solids (Cone, Icosahedron, Ring): Spiral
  spins every child by Rz(tx), so a flat marker would tumble.
* Nothing is drawn concentric with a glyph you need to click. The thinking
  glyph sits in its own slot beside the prompt; drawn around it, it would seal
  the prompt inside and make it unpickable.
* The thinking glyph's scale runs from 0.05, below the usual 0.2 minimum:
  above it there was too little range left to show a 30x spread in block
  counts. View > Enforce Minimum Glyph Size (off by default) flattens it.
"""
from __future__ import annotations

import csv
import getpass
import os
import re
from dataclasses import dataclass, field
from datetime import datetime

import config

# ---- GlyphViz geometry / topology / node-type ids ---------------------------
GEO_CUBE, GEO_SPHERE_WIRE, GEO_SPHERE = 1, 2, 3
GEO_CONE = 5
GEO_DODECA, GEO_OCTA, GEO_TETRA, GEO_ICOSA = 9, 11, 13, 15
GEO_POINT, GEO_LINE, GEO_RING = 22, 27, 33
TOPO_NONE, TOPO_SPIRAL = 0, 14
TYPE_WORLD, TYPE_GLYPH, TYPE_LINK = 0, 5, 7

# ---- palette ----------------------------------------------------------------
COL_FAMILY = {
    "explore": (74, 168, 255),
    "mutate":  (96, 220, 128),
    "execute": (255, 164, 62),
    "meta":    (208, 122, 255),
}
COL_PROMPT = (255, 242, 214)
COL_THINK = (168, 148, 255)
COL_ERROR = (255, 68, 62)
COL_COMMIT = (255, 214, 92)
COL_ATTACH = (104, 240, 228)
COL_AXIS = (92, 96, 118)

ARCH_COLOR = {
    "design talk":       (188, 180, 255),
    "quick fix":         (255, 158, 198),
    "feature build":     (124, 200, 255),
    "example authoring": (255, 202, 122),
    "docs & release":    (170, 250, 176),
}

GEO_FAMILY = {"explore": GEO_OCTA, "mutate": GEO_CUBE,
              "execute": GEO_TETRA, "meta": GEO_DODECA}
TOOL_VERB = {"explore": "read", "mutate": "write", "execute": "run", "meta": "meta"}

PROJECT = {p["key"]: p for p in config.PROJECTS}

LEGEND = [
    (GEO_SPHERE, COL_PROMPT, 0.34,
     "a prompt from %s (size = word count)" % config.PROMPT_AUTHOR),
    (GEO_SPHERE_WIRE, COL_THINK, 0.42,
     "thinking before acting - inboard of the prompt, size = block count"),
    (GEO_OCTA, COL_FAMILY["explore"], 0.26, "explore - Read, Grep, Glob, Web"),
    (GEO_CUBE, COL_FAMILY["mutate"], 0.26, "mutate - Edit, Write"),
    (GEO_TETRA, COL_FAMILY["execute"], 0.26, "execute - Bash, PowerShell"),
    (GEO_DODECA, COL_FAMILY["meta"], 0.26, "meta - Todo, Agent, Ask"),
    (GEO_CONE, COL_ERROR, 0.30, "a tool call that errored"),
    (GEO_RING, COL_COMMIT, (0.62, 0.62, 0.06), "a git commit"),
    (GEO_ICOSA, COL_ATTACH, 0.26, "an image or file pasted with a prompt"),
]

COLUMNS = [
    "id", "type", "parent_id", "branch_level", "child_id",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo", "ratio", "topo_scale", "rotation_mode",
    "texture_id", "text", "link", "show_text",
    "tag_color_mode", "tag_color_r", "tag_color_g", "tag_color_b",
    "tag_font_size", "ref_grid_color_r", "ref_grid_color_g", "ref_grid_color_b",
]


@dataclass
class ColumnStyle:
    """Everything that differs between the large exemplar columns and the
    compact corpus ones. The encoding is identical; only proportions change."""
    pitch: float = 1.9              # world units of rise per winding
    step_tool: float = 20.0         # degrees per tool call (18 per winding)
    step_prompt: float = 34.0
    gap_prompt: float = 42.0        # blank arc before every prompt
    gap_per_idle_min: float = 4.5   # extra blank arc per idle minute
    gap_idle_cap: float = 24.0      # ... capped, or one overnight gap dwarfs
                                    #     the coil it belongs to
    r_family: dict = field(default_factory=lambda: {
        "explore": 0.45, "mutate": 0.60, "execute": 0.75, "meta": 0.90})
    r_prompt: float = 0.60
    r_attach: float = 1.25
    r_think: float = -0.45          # inboard: coil radius 1 + r_think
    think_angle_frac: float = 0.5   # of step_prompt, past the prompt
    s_tool: float = 0.20
    s_error: float = 0.28
    s_attach: float = 0.24
    s_prompt: tuple = (0.24, 0.40)  # (min, max)
    # Thinking scale is LINEAR, one step per block, the same in both styles so
    # a thinking glyph means the same size in either scene.
    think_scale0: float = 0.05      # one thinking block
    think_scale_step: float = 0.01  # per additional block
    think_scale_max: float = 0.40   # 36+ blocks
    ring_r: float = 2.1             # commit band radius
    pedestal_r: float = 2.5
    label_events: bool = True       # per-event labels (off = a smaller file)


COMPACT = ColumnStyle(
    pitch=1.80, step_tool=20.0, step_prompt=30.0, gap_prompt=34.0,
    gap_per_idle_min=3.0, gap_idle_cap=20.0,
    r_family={"explore": 0.05, "mutate": 0.17, "execute": 0.29, "meta": 0.41},
    r_prompt=0.17, r_attach=0.70,
    s_tool=0.20, s_error=0.26, s_attach=0.22,
    s_prompt=(0.22, 0.34),
    r_think=-0.60,
    ring_r=1.15, pedestal_r=1.40,
)

# Prompt labels carry this many characters of the prompt's FIRST LINE. First
# line only keeps pasted tracebacks and data out of the scene.
PROMPT_LABEL_CHARS = 160


# ---- CSV helpers ------------------------------------------------------------

TEXT_FIELDS = {"session", "project", "title", "start", "date", "model", "ts",
               "prompt_first_line", "tool", "family", "cat", "target",
               "archetype"}


def load_csv(path):
    if not os.path.exists(path):
        raise SystemExit(f"{path} not found -- run extract_transcripts.py first")
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k, v in list(r.items()):
            if k in TEXT_FIELDS:
                continue
            try:
                r[k] = int(v)
            except (TypeError, ValueError):
                try:
                    r[k] = float(v)
                except (TypeError, ValueError):
                    pass
    return rows


def load_side_tables():
    """turns by session, and tool events by (session, turn), both in order."""
    turns_by, events_by = {}, {}
    for r in load_csv(os.path.join(config.DATA_DIR, "turns.csv")):
        turns_by.setdefault(r["session"], []).append(r)
    for v in turns_by.values():
        v.sort(key=lambda r: r["turn"])
    for r in load_csv(os.path.join(config.DATA_DIR, "tool_events.csv")):
        events_by.setdefault((r["session"], r["turn"]), []).append(r)
    for v in events_by.values():
        v.sort(key=lambda r: r["turn_seq"])
    return turns_by, events_by


# ---- public (shareable) build ----------------------------------------------
#
# `--public` rewrites every private path prefix to "~", drops links, and
# refuses to write if a leak survives. The scrub runs INSIDE short(), before
# truncation: scrubbing after would leave a cut prefix like "C:\Users\jo..."
# that no pattern recognises. Builder.write() then re-scrubs every label whole.
PUBLIC = False

_COMMON_NAMES = {"user", "users", "admin", "owner", "home", "dev", "pc", "me"}


def _prefix_patterns(prefix):
    """Regexes for one private path prefix in every spelling a transcript
    uses: either slash, Git Bash's /c/..., Claude Code's dashed project-folder
    slug (c--Users-name-...), and a Windows path whose backslashes a shell
    already ate (C:Usersname...)."""
    parts = [p for p in re.split(r"[\\/]+", prefix) if p]
    if not parts:
        return []
    drive = re.fullmatch(r"([A-Za-z]):", parts[0])
    tail = [re.escape(p) for p in (parts[1:] if drive else parts)]
    end = r"(?=[\\/\"' ]|$)"
    pats = []
    if drive:
        d = drive.group(1)
        pats.append(r"\b%s:[\\/]+%s%s" % (d, r"[\\/]+".join(tail), end))
        pats.append(r"/%s/%s%s" % (d, "/".join(tail), end))
        pats.append(r"\b%s--%s-" % (d, "-".join(tail)))
        pats.append(r"\b%s:%s" % (d, "".join(tail)))
    else:
        pats.append(r"/%s%s" % ("/".join(tail), end))
        pats.append(r"-%s-" % "-".join(tail))
    return [re.compile("(?i)" + p) for p in pats]


_PREFIXES = [os.path.expanduser("~")] + list(config.EXTRA_PRIVATE_PREFIXES)
_PATH_PATTERNS = [p for pre in _PREFIXES for p in _prefix_patterns(pre)]
try:
    _USER = getpass.getuser()
except Exception:
    _USER = os.path.basename(os.path.expanduser("~"))
_BARE_NAME = (re.compile(r"(?i)\b%s\b" % re.escape(_USER))
              if len(_USER) >= 3 and _USER.lower() not in _COMMON_NAMES else None)
# A target cut short at EXTRACTION (commands keep 70 characters) can end
# mid-prefix, "C:/Users/jo" -- nothing complete is left to match.
_CUT_PREFIX = re.compile(r"(?i)(\b[a-z]:[\\/]+|/[a-z]/|\b[a-z]--)"
                         r"(u|us|use|user|users|users[\\/-]+\w*)$")
_DMS = re.compile(r"\d{1,3}\s*°\s*\d{1,2}\s*['′]\s*[\d.]+\s*[\"″]?\s*[NSEW]?")
_REMOVED = "[removed]"


def scrub_public(s):
    if not s:
        return s
    for pat in _PATH_PATTERNS:
        s = pat.sub("~", s)
    s = _CUT_PREFIX.sub("~", s)
    if _BARE_NAME:
        s = _BARE_NAME.sub("user", s)
    s = _DMS.sub(_REMOVED, s)
    for pat in config.EXTRA_PRIVATE_PATTERNS:
        s = pat.sub(_REMOVED, s)
    return s


def public_leaks(s):
    """What a public label must never contain; [] when clean."""
    out = []
    if any(p.search(s) for p in _PATH_PATTERNS):
        out.append("private path")
    if _BARE_NAME and _BARE_NAME.search(s):
        out.append("user name")
    if _DMS.search(s):
        out.append("coordinates")
    if any(p.search(s) for p in config.EXTRA_PRIVATE_PATTERNS):
        out.append("private pattern")
    return out


def short(s, n):
    s = (s or "").strip()
    if PUBLIC:
        s = scrub_public(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def idle_before(turns, i):
    """Wall-clock minutes between the end of turn i-1 and the start of turn i."""
    if i == 0:
        return 0.0
    try:
        prev = datetime.fromisoformat(turns[i - 1]["ts"])
        here = datetime.fromisoformat(turns[i]["ts"])
    except Exception:
        return 0.0
    return max(0.0, (here - prev).total_seconds() / 60.0 - turns[i - 1]["duration_min"])


# ---- the builder ------------------------------------------------------------

class Builder:
    """Accumulates GlyphViz node rows and writes a native gv_node.csv."""

    def __init__(self):
        self.rows = []
        self._id = 0

    def add(self, **kw):
        self._id += 1
        row = {c: 0 for c in COLUMNS}
        row.update({
            "id": self._id, "type": TYPE_GLYPH,
            "scale_x": 1.0, "scale_y": 1.0, "scale_z": 1.0,
            "color_r": 200, "color_g": 200, "color_b": 200, "color_a": 255,
            "geometry": GEO_SPHERE, "topo": TOPO_NONE,
            "ratio": 0.1, "topo_scale": 1.0, "text": "", "link": "",
        })
        row.update(kw)
        self.rows.append(row)
        return row["id"]

    def glyph(self, parent, level, t, scale, color, geometry, text="",
              topo=TOPO_NONE, ratio=0.1, alpha=255, pin=0, ntype=TYPE_GLYPH,
              child_id=0):
        sx, sy, sz = scale if isinstance(scale, tuple) else (scale, scale, scale)
        return self.add(
            type=ntype, parent_id=parent, branch_level=level, child_id=child_id,
            translate_x=t[0], translate_y=t[1], translate_z=t[2],
            scale_x=sx, scale_y=sy, scale_z=sz,
            color_r=color[0], color_g=color[1], color_b=color[2], color_a=alpha,
            geometry=geometry, topo=topo, ratio=ratio, text=text, show_text=pin)

    def world(self, **kw):
        """The scene-settings row: background, tag colours and size."""
        base = dict(type=TYPE_WORLD, geometry=GEO_POINT, hide=1,
                    color_r=16, color_g=17, color_b=26,
                    tag_color_mode=1, tag_color_r=255, tag_color_g=255,
                    tag_color_b=205, tag_font_size=13,
                    ref_grid_color_r=40, ref_grid_color_g=42,
                    ref_grid_color_b=54, text="scene settings")
        base.update(kw)
        return self.add(**base)

    def write(self, path):
        if PUBLIC:
            leaks = []
            for r in self.rows:
                r["link"] = ""
                r["text"] = scrub_public(r["text"])
                if public_leaks(r["text"]):
                    leaks.append((r["id"], public_leaks(r["text"]), r["text"][:120]))
            if leaks:
                raise SystemExit("--public: %d labels still leak, not writing:\n%s"
                                 % (len(leaks), "\n".join(map(str, leaks[:20]))))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(self.rows)
        return len(self.rows)


# ---- one session, one column ------------------------------------------------

def plan_events(sess, turns, events_by, st):
    """Lay a session's prompts and tool calls onto one winding.
    Returns ([(kind, angle, payload)], total angle)."""
    out = []
    angle = 0.0
    for i, t in enumerate(turns):
        angle += st.gap_prompt + min(idle_before(turns, i), st.gap_idle_cap) * st.gap_per_idle_min
        out.append(("prompt", angle, t))
        angle += st.step_prompt
        for e in events_by.get((sess["session"], t["turn"]), []):
            out.append(("tool", angle, e))
            angle += st.step_tool
    return out, angle


def build_column(b, x, y, sess, turns, events_by, st, color,
                 root_text=None, pin_root=0, pedestal_color=None, pedestal_note=""):
    """One session as a helical column standing at world (x, y, 0).

    `pedestal_color` colours the ring the column stands on without touching
    the column itself -- that is how the corpus scene marks the project while
    every glyph stays archetype-coloured. Returns (root_id, height, cap_id)."""
    events, angle = plan_events(sess, turns, events_by, st)
    windings = angle / 360.0
    height = windings * st.pitch

    def rise(a):
        # Spiral's own pitch is 1 unit per winding; translate_y makes up the
        # rest, so a node on the axis lands at z = (a/360) * st.pitch.
        return (a / 360.0) * (st.pitch - 1.0)

    root = b.glyph(0, 0, (x, y, 0.0), 1.0, color, GEO_POINT, ratio=0.22,
                   topo=TOPO_SPIRAL, pin=pin_root,
                   text=root_text or "%s  %s" % (sess["date"], sess["title"] or "(untitled)"))
    # The pedestal: a broad ring (ratio 0.22 -- much thinner and it is a
    # hairline from any distance).
    b.glyph(root, 1, (0.0, 0.0, -1.0), (st.pedestal_r, st.pedestal_r, 0.05),
            pedestal_color or color, GEO_RING, ratio=0.22,
            text="%s - %s%s" % (sess["date"], sess["archetype"], pedestal_note))
    # A winding is a unit of WORK, not of time, and the label says so.
    cap_txt = ("%s - %.1f windings (1 winding = %.0f tool calls of arc), %d tool calls"
               % (sess["date"], windings, 360.0 / st.step_tool, sess["tools"]))
    if sess.get("active_min"):
        cap_txt += ", %.0f active min" % sess["active_min"]
    cap = b.glyph(root, 1, (0.0, height, -1.0), 1.0, color, GEO_POINT, ratio=0.18,
                  text=cap_txt)
    b.glyph(root, 1, (0.0, 0.0, 0.0), 1.0, COL_AXIS, GEO_LINE, ratio=0.05,
            ntype=TYPE_LINK, child_id=cap,
            text="session axis - %s" % short(sess["title"] or sess["date"], 80))

    lab = st.label_events
    smin, smax = st.s_prompt
    for kind, ang, p in events:
        yy = rise(ang)
        if kind == "prompt":
            words = p["prompt_words"]
            s = max(smin, min(smax, smin + (smax - smin) * (words / 260.0) ** (1 / 3)))
            b.glyph(root, 1, (ang, yy, st.r_prompt), s, COL_PROMPT, GEO_SPHERE,
                    text=("prompt %d (%d words): %s"
                          % (p["turn"] + 1, words,
                             short(p["prompt_first_line"], PROMPT_LABEL_CHARS))) if lab else "")
            think = p.get("think_blocks", 0)
            if think:
                sh = min(st.think_scale_max,
                         st.think_scale0 + (think - 1) * st.think_scale_step)
                ta = ang + st.step_prompt * st.think_angle_frac
                b.glyph(root, 1, (ta, rise(ta), st.r_think), sh, COL_THINK,
                        GEO_SPHERE_WIRE, alpha=190,
                        text=("%d thinking blocks before acting" % think) if lab else "")
            n_img = p.get("images", 0)
            for k in range(n_img + p.get("documents", 0)):
                b.glyph(root, 1, (ang + k * 6.0, yy, st.r_attach), st.s_attach,
                        COL_ATTACH, GEO_ICOSA,
                        text=("%s pasted with prompt %d"
                              % ("an image" if k < n_img else "a file", p["turn"] + 1))
                        if lab else "")
        else:
            fam = p["family"]
            r = st.r_family.get(fam, st.r_family["meta"])
            if p["is_error"]:
                b.glyph(root, 1, (ang, yy, r), st.s_error, COL_ERROR, GEO_CONE,
                        text=("%s FAILED: %s" % (p["tool"], short(p["target"], 64)))
                        if lab else "")
            else:
                b.glyph(root, 1, (ang, yy, r), st.s_tool, COL_FAMILY[fam], GEO_FAMILY[fam],
                        text=("%s - %s %s" % (p["tool"], TOOL_VERB[fam],
                                              short(p["target"], 62))) if lab else "")
            if p["cat"] == "commit":
                b.glyph(root, 1, (ang, yy, -1.0), (st.ring_r, st.ring_r, 0.05),
                        COL_COMMIT, GEO_RING, ratio=0.05,
                        text=("git commit - %s" % short(p["target"], 60)) if lab else "")
    return root, height, cap
