# Building GlyphViz

Every working session that built GlyphViz and GlyphViz Web, from the first one
on 2026-06-06 to 2026-09-25, drawn as a forest of helical columns. There is one
column per session. Each turn of the coil is a stretch of work: Jeff's prompts,
Claude's thinking, and every tool call Claude Code made in reply.

GlyphViz was written by Jeff Sale working with Claude Code (Anthropic's AI
coding assistant). This scene is that collaboration's own record, read back
through the tool it produced.

| Scene | File | Nodes |
|---|---|---|
| All 222 sessions, both projects | `building_glyphviz_gv_node.csv` (in the full examples set it is zipped, as `Building_GlyphViz_Scene.zip`: drag that onto the GlyphViz window) | 32,374 |
| One typical session of each of the five kinds | `Five_Archetypes/building_glyphviz_archetypes_gv_node.csv` | 538 |

## Layout (the main scene)

- **X: project, then kind of session.** GlyphViz desktop (Python, PySide6,
  OpenGL) on the left, GlyphViz Web (TypeScript, Three.js) on the right, 30
  units apart. Each bank has five lanes: design talk, quick fix, feature build,
  example authoring, docs & release.
- **Y: calendar date,** shared by both banks. Quiet days are real gaps, busy
  days are real clusters.
- **Z: the column.** Height is how much work happened, not how long it took.
  One winding of the coil is 18 tool calls' worth of arc.

## Glyphs

| Glyph | Meaning |
|---|---|
| warm-white sphere | a prompt from Jeff, sized by word count; its label is the prompt's first line |
| violet wire sphere | Claude's thinking before it acted, sized by the number of thinking blocks |
| blue octahedron | explore: Read, Grep, Glob, web |
| green cube | edit: Edit, Write |
| orange tetrahedron | run: Bash, PowerShell |
| magenta dodecahedron | meta: to-do lists, sub-agents, questions |
| red cone | a tool call that returned an error |
| gold ring around the axis | a git commit |
| cyan icosahedron outside the coil | an image or file Jeff pasted in |
| pedestal colour | teal = desktop, amber = web |
| pedestal shape | solid = from the Claude Code transcript; wire hoop = rebuilt from a saved chat copy |

## Where the data came from

Claude Code saves each session as a transcript. The scene was generated from
those transcripts (209 sessions) and from text copies of 13 early sessions
whose transcripts had expired, which is why the June columns with wire
pedestals have tool calls and prompts but no timing or thinking.

For publication, local file paths in the labels were shortened to `~`.
Prompt labels show the first line of each prompt, up to 160 characters.
