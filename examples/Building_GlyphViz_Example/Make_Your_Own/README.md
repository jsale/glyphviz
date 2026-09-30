# Make your own: visualize your Claude Code sessions

This folder holds the pipeline that built the *Building GlyphViz* scene. It
works on your own sessions, too. Claude Code saves every session as a
transcript, both in the terminal and in the VS Code extension. These scripts
read those transcripts and write two GlyphViz scenes in the same glyph
language:

| Scene | What it shows |
|---|---|
| `out/Session_Corpus/gv_node.csv` | every session as one helical column, in lanes by kind of work, along a calendar; one bank per project |
| `out/Session_Archetypes/gv_node.csv` | five large columns, one real session per kind of work: the easier place to learn to read a column |

Only the Python standard library is needed (Python 3.9 or later). Nothing is
uploaded anywhere; the scripts read files on your machine and write CSVs next
to them.

## Quick start

```
python extract_transcripts.py --list
```

This lists the transcript folders Claude Code has saved on your machine, with
the session count of each. They live under `~/.claude/projects/`, and each
folder's name is its project's path with the separators turned into dashes.

Open `config.py` and replace `<your-project-folder>` in `PROJECTS` with the
folder you want. Add a second entry to put another project in its own bank
beside the first. Then:

```
python extract_transcripts.py      # transcripts -> data/*.csv
python archetypes.py               # optional: a text report, to check the rules
python build_corpus_scene.py       # -> out/Session_Corpus/gv_node.csv
python build_archetype_scene.py    # -> out/Session_Archetypes/gv_node.csv
```

Open either `gv_node.csv` in GlyphViz (File > Open, or drag it onto the
window). In the corpus scene, press **C** for Camera Mode and left-drag forward
to fly down the calendar.

## Reading a column

A column is one session, read from the bottom up. Every event advances the
coil by a fixed angle, so **height is how much happened, not how long it
took**. One winding is 18 tool calls' worth of arc.

| Glyph | Meaning |
|---|---|
| warm-white sphere | a prompt, sized by word count; its label is the prompt's first line |
| violet wire sphere | the thinking before Claude acted, sized by the number of thinking blocks |
| blue octahedron | explore: Read, Grep, Glob, web |
| green cube | edit: Edit, Write |
| orange tetrahedron | run: Bash, PowerShell |
| magenta dodecahedron | meta: to-do lists, sub-agents, questions |
| red cone | a tool call that returned an error |
| gold ring around the axis | a git commit |
| cyan icosahedron outside the coil | an image or file pasted with a prompt |
| pedestal colour | which project (the `color` in `config.PROJECTS`) |

Click any glyph to read its label; a column's root label carries the
session's title and totals.

## The five kinds of session

`archetypes.py` sorts every session by rule, first match wins:

- **design talk**: the prompts produced almost no tool use (fewer than 6 tool
  calls per prompt, or under 25 calls and at most 2 files edited)
- **quick fix**: under 16 active minutes and under 90 tool calls
- otherwise, by where most of the edits landed: **feature build** (source
  code, tests), **example authoring** (examples, tools/scripts), or **docs &
  release** (docs, README/CHANGELOG, build files)

"Where the edits landed" comes from `PATH_CATS` in `config.py`: a list of
regular expressions matched against each edited file's path. Its defaults
suit a typical repository. Run `archetypes.py` and look at the *EDIT TARGET MIX*
table: a large `other` share means your layout needs a pattern added. That
table is the single most useful thing to tune.

## Sharing a scene

Labels quote the first line of each prompt, and the files and commands Claude
touched, so a scene can hold things you'd rather keep private. Build a
shareable copy with `--public`:

```
python build_corpus_scene.py --public      # -> out/Session_Corpus_public/
python build_archetype_scene.py --public   # -> out/Session_Archetypes_public/
```

The public build rewrites your home folder to `~` in every spelling a
transcript uses, replaces your user name, and removes any latitude/longitude
written in degrees, minutes and seconds. It also refuses to write the file if
anything it should have removed survives. Add other folders or words that must
never appear to `EXTRA_PRIVATE_PREFIXES` and `EXTRA_PRIVATE_PATTERNS` in
`config.py`.

The scrub cannot know what else in your prompts is personal. **Read the labels
before you share**: open the scene, untick *Show Tag Labels of Selected* in
the Properties panel, and press **T** to show every label. Or search the CSV's
`text` column.

## Changing the look

| To change | Edit |
|---|---|
| lane order, spacing, days per unit | the constants at the top of `build_corpus_scene.py` |
| glyph shapes, colours, sizes, coil proportions | `glyph_kit.py`: the palette, `ColumnStyle` and `COMPACT` |
| what counts as which kind of session | `classify()` in `archetypes.py`, and `AREA` in `config.py` |
| how tool names map to the four families | `TOOL_FAMILY` in `extract_transcripts.py` |

The scene files are GlyphViz's native `gv_node.csv` format; `glyph_kit.py`'s
`Builder` writes them, one row per node. The *GlyphViz Claude Skill* covers
the format in full if you want to add glyphs of your own.

## Notes on the transcripts

- **Active time, not clock time.** A session left open overnight or resumed
  days later would look enormous, so durations count only gaps of five minutes
  or less between records.
- **Thinking is counted, not read.** Most models store that a thinking block
  happened but not its text, so the violet spheres encode how many blocks
  there were, and their labels carry no thinking text.
- **Only surviving transcripts can be drawn.** By default Claude Code deletes
  transcripts after 30 days. To keep a longer history, raise
  `cleanupPeriodDays` in your Claude Code `settings.json`.
- Set `CLAUDE_PROJECTS_DIR` if your transcripts live somewhere other than
  `~/.claude/projects`, and `SESSION_VIZ_WORK` to write `data/` and `out/`
  somewhere other than this folder.
- The transcript format is Claude Code's own and not a published contract; these
  scripts were written against Claude Code 2.1. If a future version changes it,
  `extract_transcripts.py` is the one file to adjust.
