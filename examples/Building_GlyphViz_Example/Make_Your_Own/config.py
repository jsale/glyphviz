"""The one file you edit: which transcripts to read, and how to label them.

Claude Code (the CLI and the VS Code extension alike) saves every session as a
JSON Lines transcript under

    ~/.claude/projects/<project folder>/<session uuid>.jsonl

where <project folder> is the project's path with every separator turned into
a dash, e.g. a repo at C:\\Users\\<you>\\source\\repos\\myapp becomes
"c--Users-<you>-source-repos-myapp". Run

    python extract_transcripts.py --list

to see the folders on your machine and how many sessions each holds, then put
the ones you want into PROJECTS below. Nothing else needs changing to get a
scene; everything past PROJECTS is optional tuning.
"""
from __future__ import annotations

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

# Where Claude Code keeps its transcripts. Override with the CLAUDE_PROJECTS_DIR
# environment variable if yours live somewhere else.
TRANSCRIPT_ROOT = os.environ.get("CLAUDE_PROJECTS_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude", "projects")

# Where the pipeline writes its tables (data/) and scenes (out/). Defaults to
# this folder; set SESSION_VIZ_WORK to keep generated files somewhere else.
WORK_DIR = os.environ.get("SESSION_VIZ_WORK") or HERE
DATA_DIR = os.path.join(WORK_DIR, "data")
OUT_DIR = os.path.join(WORK_DIR, "out")

# ---------------------------------------------------------------------------
# PROJECTS -- one entry per transcript folder. Each becomes one BANK of the
# corpus scene, left to right in the order listed (list them in the order the
# projects started and the banks read like a timeline).
#
#   folder  the folder name under TRANSCRIPT_ROOT (or an absolute path)
#   key     a short id carried through the tables; letters/digits only
#   label   the long name on the bank's nameplate
#   short   the short name used in column labels
#   color   the bank's pedestal and rail colour, RGB 0-255
#
# Replace the placeholder below with your own folder(s).
# ---------------------------------------------------------------------------
PROJECTS = [
    {"folder": "<your-project-folder>",
     "key": "main",
     "label": "MY PROJECT",
     "short": "My project",
     "color": (120, 230, 210)},
    # A second project gets its own bank beside the first, sharing the
    # calendar -- this is how the gallery scene shows GlyphViz desktop and
    # GlyphViz Web side by side:
    # {"folder": "<another-project-folder>",
    #  "key": "web",
    #  "label": "MY OTHER PROJECT",
    #  "short": "Other project",
    #  "color": (255, 176, 120)},
]

# Scene titles (the pinned line above each scene).
CORPUS_TITLE = "Every Claude Code session"
ARCHETYPE_TITLE = "Session archetypes"

# Who typed the prompts, as the legend and labels should say it.
PROMPT_AUTHOR = "you"

# ---------------------------------------------------------------------------
# Where an edit landed. Every Read/Edit/Write path is sorted into the FIRST
# category whose pattern matches (paths are compared with backslashes, so
# write [\\/] for a separator). The archetype rules below only care which
# AREA a category belongs to, so tailoring this table to your repo's layout is
# the single most useful tweak -- run archetypes.py afterwards and check the
# "EDIT TARGET MIX" table; a large "other" share means a pattern is missing.
# ---------------------------------------------------------------------------
PATH_CATS = [
    # Claude Code's own notes about your project -- bookkeeping, not work.
    ("memory",   re.compile(r"\.claude[\\/]|[\\/]memory[\\/]", re.I)),
    ("scratch",  re.compile(r"appdata[\\/]local[\\/]temp|[\\/]tmp[\\/]"
                            r"|[\\/]scratch", re.I)),
    ("tests",    re.compile(r"[\\/]tests?[\\/]|[\\/]test_[^\\/]*$"
                            r"|\.(test|spec)\.[jt]sx?$|[\\/]fixtures[\\/]", re.I)),
    ("examples", re.compile(r"[\\/](examples?|samples?|demos?)[\\/]", re.I)),
    ("tools",    re.compile(r"[\\/](tools|scripts)[\\/]", re.I)),
    ("docs",     re.compile(r"[\\/]docs?[\\/]|\.(rst|adoc)$", re.I)),
    ("projdoc",  re.compile(r"(claude|readme|changelog|contributing)\.md$", re.I)),
    ("build",    re.compile(r"\.spec$|dockerfile|[\\/]\.github[\\/]|\.ya?ml$"
                            r"|build.*\.(bat|sh|ps1)$|package\.json$"
                            r"|pyproject\.toml$|setup\.(py|cfg)$", re.I)),
    # Anything else that looks like source code.
    ("code",     re.compile(r"\.(py|pyx|ts|tsx|js|jsx|mjs|c|cc|cpp|h|hpp|cs|"
                            r"java|kt|go|rs|rb|php|swift|m|mm|lua|r|jl|scala|"
                            r"glsl|hlsl|wgsl|vert|frag|css|scss|html|vue|svelte)$",
                            re.I)),
]

# Which categories count as which kind of work. `memory` and `scratch` are in
# no area on purpose: a session that only wrote notes should not look like it
# built something.
AREA = {
    "feature": ("code", "tests"),
    "example": ("examples", "tools"),
    "docs":    ("docs", "projdoc", "build"),
}

# ---------------------------------------------------------------------------
# Privacy, for sharing a scene (build_*_scene.py --public). Labels quote the
# first line of your prompts and the files and commands Claude touched, so a
# public build rewrites your home folder to "~", drops links, and refuses to
# write if anything below still matches. Your home folder and user name are
# found automatically; add anything else that must never appear in a shared
# scene (other machine paths, a client's name, an address...).
# ---------------------------------------------------------------------------
EXTRA_PRIVATE_PREFIXES = [
    # r"D:\Work",
]
EXTRA_PRIVATE_PATTERNS = [
    # re.compile(r"(?i)acme corp"),
]
