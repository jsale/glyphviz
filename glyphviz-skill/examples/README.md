# Examples — curation plan

The skill will ship a small set of **self-contained** examples (generator
script + output CSVs + one screenshot each), curated from the repo's
`examples/` directory rather than written fresh. Candidates, in rough order of
instructional value:

1. **Topology_Example** — all 18 topologies side by side; the canonical
   "what does topo N look like" reference. Small, synthetic, ideal first copy.
2. **Rotation_Convention_Example** — Heading/Tilt/Roll vs Euler XYZ,
   numerically verified; pairs with the `rotation_mode` rules in SKILL.md.
3. **A Channels example** — smallest good one (SineWave_Example or a trimmed
   Flocking_Example) once `channels-animation.md` exists.
4. **A World Grid / geographic example** — a trimmed Global_Terrorism_Example
   scene (Event_Cloud) once `world-grid.md` exists.
5. **Palette_Example** — pairs with `color-palettes.md`.

Rules for copying an example in:
- Trim to the minimum that demonstrates the concept (skill zips should stay
  small; no large media/textures).
- Each example gets its own README stating what it demonstrates and which
  reference doc it pairs with.
- Regenerate outputs with the repo's real generator + verify with the real
  loader before committing the copy — never hand-edit the CSVs.
