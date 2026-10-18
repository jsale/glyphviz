# GTD — Organization Profiles

A wall of profile-rosette hyperglyphs, one per organization with ten or more attributed attacks, sorted most-active first. Each rosette is a fixed layout — an attack-type clock ring, casualty and reach spheres, an activity sparkline — that you learn once and can then read at a glance on any organization.

![GTD — Organization Profiles loaded in GlyphViz](../assets/examples/gtdb-organization-profiles.png)

*Data: Global Terrorism Database (START, University of Maryland), 1970–2020.*

**Try it:** download this example below (or [the full examples set](../getting-started/installation.md#example-scenes)), then open `Global_Terrorism_Example/Organization_Profiles/OrgProfiles_gv_node.csv` — or just drag its folder onto the GlyphViz window.

[:material-download: Download this example (272 KB)](https://iluvdata.org/glyphviz/zips/Global_Terrorism_Example_Organization_Profiles.zip){ .md-button }

## What it is

The Global Terrorism Database (GTD), compiled by START at the University of Maryland, records about 210,000 incidents from 1970 to 2020. This scene turns it into a **wall of 640 profiles**, one for every organization with ten or more attributed attacks, sorted from the most active (top left) in reading order. Each profile is a small glyph, a *rosette*, built to a fixed layout that you learn once and can then read on any organization.

It is the first of five GTD scenes in the gallery, and the one to start with: the other four use the same colours and the same vocabulary.

## How to read a rosette

| Part | What it shows |
|---|---|
| **Centre octahedron** | the organization. **Size** is the log of its total attacks, and **colour** is its *dominant attack type* |
| **A clock ring** of 12 slots | read clockwise from 12 o'clock. The first nine slots are the nine attack types, in the database's own order; the last three are casualties and reach |
| **Beads on the ring** | each bead's size is the log of how many attacks of that type the organization made. An attack type it never used leaves a gap |
| **Solid red sphere** | total people killed (log scale) |
| **Orange wire sphere** | total people wounded (log scale) |
| **Blue wire sphere** | geographic reach, the log of how many countries it struck |
| **A line beneath the rosette** | activity over time: attacks in each five-year bin from 1970 to 2020, scaled to *that organization's own* peak |

The line beneath is about the *shape* of a campaign, not its size: a rise, a peak, a collapse, a resurgence. Comparing sizes across organizations is the job of the centre and the ring.

The ring runs clockwise from the top through the nine attack types, with these colours, which are used the same way in every GTD scene:

| Slot | Attack type | Colour |
|---|---|---|
| 1 | Assassination | green |
| 2 | Armed assault | blue |
| 3 | Bombing / explosion | cyan |
| 4 | Hijacking | magenta |
| 5 | Hostage taking (barricade) | yellow |
| 6 | Hostage taking (kidnapping) | orange |
| 7 | Facility / infrastructure attack | red-pink |
| 8 | Unarmed assault | sea green |
| 9 | Unknown | grey |

## Things to try

- **Learn one, read them all.** Pick one organization and identify each part, then fly along the wall. A glyph with a big green bead at the top is an organization that assassinated; one dominated by cyan was a bombing campaign.
- **Tab through the wall.** The tagged centre octahedron is the top node of each rosette, so pressing Tab steps from one organization's summary to the next.
- **Read the line against the ring.** Two organizations with similar centres can have very different histories: one that peaked and collapsed, one that has grown steadily.
- **Compare reach.** The blue sphere on the ring is how many countries an organization struck, so a large one marks an organization that operated across borders.

## How it is built

The scene is **13,916 nodes**: 640 rosettes, each with a centre, a ring, up to twelve ring objects and a Plot-topology line of eleven points. The hierarchy is four levels deep, with the tagged centre as the level-0 root so that Tab navigation reads the summaries. Scale cascades down the hierarchy, so the ring is sized in its own units and every ring is the same world size whatever the size of the organization at its centre. The generator is `generate_gtdb_examples.py` in the parent folder, which builds all five GTD scenes from the START spreadsheet and takes options such as the minimum attack count.

**Source:** Global Terrorism Database, National Consortium for the Study of Terrorism and Responses to Terrorism (START), University of Maryland.
