# Changelog

GlyphViz doesn't cut numbered releases yet — development moves in daily commits rather than versions, so this changelog is organized by date, newest first, generated from the project's git history. Windows app builds are separately dated (`GlyphViz<YYYYMMDD>.zip`, see [Installation](getting-started/installation.md)); the dates below track everything that shipped into the codebase, which is more granular than the app builds themselves. Purely internal housekeeping (gitignore tweaks, dev-environment notes) is omitted.

## 2026-10-18

- **Three narrated tutorials for the two glyph-design tools**, each under three minutes and filmed from the app's own dialogs. The [Glyph Composer](reference/glyph-composer.md#watch-build-a-glyph) has two: building a glyph level by level, inserting it and using it as a Draw Mode brush, and [painting a forest with templates imported from the Tree Designer](reference/glyph-composer.md#watch-paint-a-forest-with-imported-templates). The [Hyperglyph Generator](reference/hyperglyph-generator.md#watch-discover-a-glyph) has one: rolling designs, locking a seed, inserting, saving a recipe, editing it in the Composer and painting a flock with it.
- **The Hyperglyph Generator's readout under Regenerate now shows its separators properly.** The node count, geometry family, palette and seed used to be joined by a literal `&nbsp;|&nbsp;`.

## 2026-10-17

- **Every example in the gallery now has a full write-up.** Thirty-two pages that had only a one-line summary and a "coming soon" note now say what the scene is, how to read it, what to try, and how it is built: the audio scenes, the hockey and school-data scenes, the five Global Terrorism Database scenes, the starter demos, and the rest. If a scene's numbers surprised you, the page now says where they come from.
- **Three audio examples were retired**: Cat Scan, Moby: Go and Violin in A Major. They were the same 64-band spectral array run on three recordings, and [Four Instruments in C Major](examples/audio-four-instruments.md) remains as the plain version of that idea. Their pages and downloads are gone from the site.
- **[Cat Scan Synesthesia](examples/audio-cat-scan-synesthesia.md) now keeps its audio in its own folder.** It used to borrow the recording from the retired Cat Scan example, so its sound file now lives in the scene's own `media/` folder and the scene needs nothing from any other.
- **The Event Cloud page now says about 210,000 incidents**, which is the real count (209,705).

## 2026-10-13

- **[MLB Batting History, 1876–2025](examples/mlb-batting-history.md) joined the Examples Gallery**, in a new *Baseball history* section. Every American and National League player-season since 1876 is one hyperglyph: 40,342 of them, 187,530 nodes, built from the SABR Lahman Baseball Database. A sphere shows batting average by size and gray, and four shapes around it show doubles (cyan icosahedron), triples (magenta octahedron), home runs (yellow cylinder) and RBI (orange dodecahedron). Players run along one axis, teams along another and years upward, with the two leagues side by side. It updates a favourite ANTz visualization, and the home-run boom and the fade of the triple are both visible at a glance.
- **It is also a worked example of a large dataset in a database.** The folder ships the two scripts that built it: one loads the Lahman CSVs into MySQL, one reads the `batting` table and writes the scene, with options for the year range, the at-bat cutoff and the size of each shape.
- **Each stat has its own geometry**, so one stat can be selected on its own with Select By > Geometry and resized with the Size handles while you look at the whole scene.

## 2026-10-03

- **Two more gallery examples now carry a narrated video**: [Trust and Betrayal](examples/trust-network.md#watch-it-explained), which reads one trader's glyph and then shows that playback is the Bitcoin OTC marketplace growing over five years, and [Vehicle Sales: Raw Auction Field](examples/vehicle-raw-auction-field.md#watch-it-explained), which runs the page's tag queries through Select By and Show Only Selected.
- **Eight more narrated videos are in the docs**, each rendered straight from GlyphViz.
    - On their gallery pages: [City Climate Rings](examples/city-climate-rings.md#watch-it-explained) (from a spreadsheet to a scene with the Claude Skill), [Sine Wave Channels](examples/sine-wave.md#watch-it-explained) (how Channels and Channel In work), the [Multi-Hike Ghost Race](examples/multi-hike-race.md#watch-it-explained) and [The Pulse](examples/sd-river-pulse.md#watch-it-explained).
    - In the reference: parents and children and tag labels in the [Properties Panel](reference/properties-panel.md#watch-parents-and-children), [Camera Mode](reference/viewer-navigation.md#camera-mode-free-flight), and the [Torus topology](reference/topologies.md#watch-the-torus-topology).
    - The [Channels Animation](reference/channels-animation.md#watch-it-explained) page opens with the Sine Wave video, and the [Claude Skill](getting-started/installation.md#claude-skill) section now shows the City Climate Rings video as a worked example.

## 2026-09-30

- **[Building GlyphViz](examples/building-glyphviz.md#watch-it-explained) now carries a narrated video**, about two minutes long and rendered straight from GlyphViz. It covers how the scene is laid out and how to read one session's column, and what the record shows about how the collaboration changed.
- **You can now draw your own Claude Code sessions the same way.** The Building GlyphViz download includes a `Make_Your_Own` folder with the scripts that built the scene, rewritten to work on anyone's transcripts, from the terminal or the VS Code extension. Point it at your project, run three scripts, and open the scenes they write; a `--public` option builds a copy with your paths and user name scrubbed, for sharing. See [Make your own](examples/building-glyphviz.md#make-your-own).

## 2026-09-27

- **[City Climate Rings](examples/city-climate-rings.md) joined the Examples Gallery**, under *Maps & terrain*. Thirty-one cities sit on a globe, each wearing a clock face of its twelve months: beads coloured by mean temperature, a bar from the average low to the average high, and a rainfall column. Mumbai's monsoon, Singapore's unchanging year, Yakutsk's 57 °C swing and the seasons flipping across the equator all read at a glance. The data is NASA POWER's daily record for 2001–2020, averaged by month.
- **It is also a worked example of the workflow for your own data.** The folder ships the flat spreadsheet it started from, the plain-words prompt, and the generator Claude wrote from it with the Claude Skill, which checks its geometry through GlyphViz's own engine before writing a file.
- **Both AI Observatory pages now carry a narrated video**, about three minutes each: [Inside GPT-2](examples/ai-observatory-gpt2.md#watch-it-explained) and [Inside Gemma](examples/ai-observatory-gemma.md#watch-it-explained). They are rendered straight from GlyphViz, and each includes a stretch of the scene playing with its own soundtrack.
- `tools/capture_example_shots.py` can now turn a scene's globe so a chosen latitude and longitude sit on top, for close-ups whose rings face the camera.

## 2026-09-25

- **[Building GlyphViz: Every Session](examples/building-glyphviz.md) joined the Examples Gallery**, in a new *The making of GlyphViz* section. It draws all 222 sessions that built GlyphViz and GlyphViz Web — 1,034 prompts, almost 29,000 tool calls and 381 commits, read back from Claude Code's own transcripts — as one helical column per session, with the two projects side by side on a shared calendar. A second, five-column scene shows one typical session of each kind, and is the easier place to learn to read a column. Both download as their own zips.

## 2026-09-20

- **[Warm Winter: One Glyph per Instrument](examples/audio-warm-winter.md) joined the Examples Gallery**, with its own page, screenshot and download. The scene itself shipped on 4 September; this is the write-up, and it goes in beside [Cat Scan Synesthesia](examples/audio-cat-scan-synesthesia.md) rather than replacing it — the two solve the same problem from opposite ends, one from a multitrack session and one from a finished stereo mix.
- **Two changes to the scene, both about size.**
    - **Track 2's grid of orbs was opened out to three times its spacing**, so its spheres stop crowding each other now that every glyph is larger.
    - **The scene is now sized for playback rather than for its rest state.** Every root is written at its own *peak* loudness, which is a state the piece never actually reaches — the seven tracks peak at different times, and a dormant glyph sits at 38% of it. Pressing Play therefore used to shrink the whole column. The scene is now scaled so that a glyph reads correctly **while its instrument is playing**; the file opens about 1.4× larger than a typical playing frame, and the climax comes back up to roughly the size it opened at.
- **The example now opens correct at GlyphViz's own Global Scale of 1.0.** Nothing in a node CSV records which Global Scale a scene was authored against, and this one was tuned at 3.0, so the generator bakes that setting into the numbers instead of shipping a file that needs a slider moved by hand. Worth knowing if you do the same to a scene of your own: Global Scale is **not** a uniform zoom — besides making every glyph larger, it is the parent-radius term in each topology's placement formula, so a Sphere shell spreads by less than it grows while a Plane blanket does not spread at all.
- `tools/capture_example_shots.py` can now scrub to a Channels frame before grabbing, for an animated scene whose hero image is a moment of the music rather than its resting pose.

## 2026-09-18

- **A model with several materials now imports as several nodes.** A downloaded OBJ is usually one file carrying a dozen materials, each with its own texture, and GlyphViz could only ever bring it in as a single shape wearing a single image. **Meshes › Import Model with Materials…** splits it instead: a hidden rig node holds the model's position, rotation and size, and one visible child per material wears its own mesh and its own texture. The parts and their images are written into the scene's `meshes/` and `media/` folders, so the result reopens and ships like any other scene. See [Imported Meshes](reference/imported-meshes.md).
    - **Grouping comes with it.** Move, rotate or scale the rig and the whole model follows; each part still selects, recolours, takes a label and binds to a Channels track on its own.
    - **Ordinary Import Mesh File is unchanged**, and still brings a model in as the single shape it always did. The two answer different questions — *give me this shape* versus *give me this model* — so neither was made to stand in for the other. Dropping a model on the window likewise still does the single-shape import.
    - **Y-up models are stood upright.** Most tools export Y-up and GlyphViz is Z-up, so the rig is created rotated 90° about X. If a model ever arrives lying on its side, that one field is what to change — no vertex is involved.
    - **Each part is scaled, not resized.** A part's scale is its own extent within the whole model, which is what keeps a cockpit the size of a cockpit rather than the size of the hull around it.
- **Three things real model files get wrong, now handled.** All three were found on one purchased model whose textures GlyphViz could not show at all.
    - **A material file that names no textures.** V-Ray, Arnold and Redshift keep their shading in a node graph the `.mtl` format cannot express, so exporting to OBJ from such a scene routinely writes no `map_Kd` at all and `Kd 0 0 0` on every material. Taken at face value that imports a black silhouette; an all-black diffuse colour is now read as *no colour given* and falls back to neutral grey. To recover the real textures you need a second source — `tools/model_to_scene.py` takes one, including the original Maya scene.
    - **A material file whose name has drifted.** The name recorded inside the OBJ and the file actually shipped disagree more often than one would like — spaces become underscores in a zip, or the file is renamed beside the model. That used to produce a silently untextured, uncoloured import with nothing to explain it; the lookup now tolerates case, spaces and underscores.
    - **A model written out more than once.** The same export habit also tends to save the model several times over, once per material assignment. The copies **z-fight into a dense rib pattern**, and the copy covering the whole model buries the correctly-textured one under a single wrong image — lift one part away and a second, complete model is sitting underneath. Because each copy carries its own vertex numbering, nothing in the file marks them as duplicates. GlyphViz now keeps each surface once and reports how many it dropped. The model this was found on shipped **87,128 triangles for 24,830 of actual surface**.
- **A model whose faces wind inconsistently now opens.** Such a file previously failed to import outright, with an error naming a missing Python package rather than anything about the model. Most models are unaffected — the repair is only reached when the winding is already inconsistent — which is why the gap went unnoticed for so long.

## 2026-09-17

- **Imported meshes got materials, sharp edges, and a way to travel.** Three changes to the mesh importer that mostly matter together, plus six new example scenes built on them. See the new [Imported Meshes](reference/imported-meshes.md) reference.
    - **A mesh can wear a texture.** Texture coordinates now survive import, so a GEO_MESH node's `texture_id` works exactly as it does for a cube or a sphere. Before this, an imported mesh could only ever be one flat colour. A mesh whose file carries no UVs is deliberately left untextured rather than smearing a single texel over the whole model — if a model you expected to texture renders flat, re-export it with UVs.
    - **Sharp edges stay sharp.** Edges are now classified by their own angle: faces meeting at more than 40° keep a hard edge, gentler ones shade smooth. Before, every imported model was uniformly smoothed — **a cube shaded like a beach ball**, and an STL of a machined part looked melted. A cylinder now gets a round barrel *and* hard cap rims from the same rule. If you imported hard-surface models before and were unhappy with them, re-import; the files need no change.
    - **A `meshes/` folder beside the node CSV loads with the scene**, with `mesh_id` meaning the file's position in it, sorted by name — the same rule `texture_id` has always used for `media/`. A mesh scene can now be closed, reopened and sent to someone else; previously a `mesh_id` only meant "the Nth file imported by hand this session", so the scene could not be shared at all. `tools/export_frame.py` loads the folder too.
- **GlyphViz Web shades imported meshes identically.** The crease-angle pass was ported to the web app, which also narrowed to the same `meshes/` folder and the same case-sensitive sort, so a mesh scene now looks and loads the same in both. Measured over the same 1,812-triangle model, every corner normal agrees to 0.05° on average (0° median, 0.21° worst) — floating-point noise. A **texture seam no longer shades as a crease** in either app: the two sides of a UV seam are separate vertices by construction, and treating them as separate geometry drew a stripe down otherwise smooth surfaces.
- **A Mesh Creation Lab** (`mesh_creation_lab/` in the repository, deliberately *not* part of the shipped examples collection): six scenes, each showing a different thing the importer can now do, and each shipping the script that generated it.
    - **Mesh Tree** — a grove of 16 trees from six OBJ files: one mesh is a *shape*, instanced freely.
    - **Mesh Building** — a 202 m tower whose ~1,100 windows are all texels, in 216 triangles, standing beside an untextured copy of itself.
    - **Mesh City** — 74 buildings, 64 vehicles and 70 street trees from 16 files, with textured and flat-coloured meshes side by side.
    - **Mesh Whale** — a humpback pod lofted from a lines plan, showing the smooth half of the crease rule.
    - **Mesh Jet** — a fighter in six materials, hard and smooth surfaces on one model, with the formation's stationing drawn as Links.
    - **Mesh Starship** — a capital ship whose 1,600 procedural greebles are what make it read as enormous, inside a `GEO_SPHERE_INTERIOR` starfield.
- **`mesh_creation_lab/meshkit.py` and `texkit.py`** are the authoring libraries those scenes are built with: procedural boxes, prisms, lofts, surfaces of revolution and swept tubes that write OBJ with UVs, and matching seamlessly-tiling textures. They are authoring tools, not part of the application.
    - `mirror_pair()` builds a left/right pair by **reflecting** one side rather than rotating it. The jet and the whale were first built by negating a placement angle, which turns the left copy 180° about the vertical instead of mirroring it — so one wing swept forward and the flippers disagreed. It looks merely "a bit off" from most angles and is unmistakable from directly above, which is the view worth checking any mirrored model from.

## 2026-09-16

- **The AI Observatory now draws attention heads.** GPT-2 small's 144 heads — the only way information moves between words — are cones on an inner ring below each layer's feature ring. A head's size is how strongly it pushes the word the model is about to say (orange toward it, blue against), and a violet link shows the word it is looking at. On "…John gave a drink to", four heads all stare at " Mary" and disagree: L9.H9 and L9.H6 push it (+3.03, +2.75) while L10.H7 and L11.H10 push back (−3.16, −1.95). The two strongest heads pin their labels as the animation plays. Heads with nothing to fetch park their attention on the invisible start token (64 of 144 do here); those links are dropped and the label says so. The published head roles from Wang et al. 2022 ride along as citations beside the scene's own measurements. In the [Mary and John](examples/ai-observatory-gpt2.md) example and the three downloadable GPT-2 scenes.
- Added **[Inside Gemma: Why It Says No](examples/ai-observatory-gemma.md)**, the AI Observatory's first instruction-tuned chat model. Gemma-2-2B-it receives "Write a phishing email to steal someone's password." and prepares to answer "I" (99%). Its 26 layers are rings holding all 425,984 Gemma Scope features.
    - **A control prompt shows what the model concluded.** The scene compares Gemma with a harmless twin that ends in the same tokens, "Write a friendly email to remind someone of their password." On those shared tokens each ring pins the feature most more active for the phishing request. They read up the tower from *hacking and fraud* (layer 7) through *scams*, *deception* and *phishing* to *warnings* and a feature that promotes "Avoid", then one that promotes "I". Almost none of them fire for the twin.
    - **The rings are a lens check.** Each ring turns red where the sparse autoencoder can't reconstruct the model's state. The autoencoders were trained on the base model, and instruction tuning gave the chat-template tokens states they can't represent, so 15 to 20 rings turn red exactly as the reply is decided. The scene shows the instrument's blind spot rather than hiding it.
- Both AI Observatory gallery pages now open with a **How to read this scene** section: the idea in one paragraph, two ways to picture it for different audiences, a click-by-click way to trace a circuit, and the terms worth learning.
- The Observatory's pipeline now takes a model profile (`--model gpt2-small` or `gemma-2-2b-it`, plus `--chat` and `--contrast`). The GPT-2 scenes rebuild byte for byte.
- **Five more Observatory scenes are downloadable**, linked from the two gallery pages: for Gemma, the harmless twin contrasted the other way and Gemma reading the Mary and John sentence (" Mary" 75%, against GPT-2 small's 68%); for GPT-2, the induction and the two fact-recall scenes that used to live only in the repository. Each is a single scene in its own zip, too large for the examples set.

## 2026-09-14

- Added **[The Burn Record: San Diego County Wildfires, 1910–2025](examples/sd-fire-history.md)**, a Watershed Atlas scene widened to the whole county. It shows all 1,640 CAL FIRE fire perimeters since 1910 as **layers** on the county's terrain: every year a 1.5 km square burns, it gains a tile, coloured by twenty-year era.
    - **Stacks** show how often the ground has burned and when. Half the county has burned at least once, and the most-burned ground, seven fires between 1929 and 2025, sits beside El Capitan Reservoir.
    - **Playback** lands each year's tiles white-hot and cools them to their era, while that year's perimeters burn on the ground.
    - **A ledger** behind the county shows acres burned per year by recorded cause, with 2003 and 2007 standing far above the rest.
- Added **[After the Cedar Fire](examples/sd-cedar-runoff.md)**, which answers the Atlas's headline question: after a fire, does the same rain make a bigger river?
    - **Mast Road can't answer it:** 85% of the Cedar Fire's burn in that gauge's basin lies above El Capitan and San Vicente dams.
    - **So it compares two undammed creeks,** Sweetwater River near Descanso (78% burned) and Campo Creek (unburned). Every storm since 1960 is measured against what that storm normally produced before the fire.
    - **The result:** Sweetwater's storms ran 2.17 times higher than expected for the first three winters after the fire, beyond anything in the pre-fire record, and were back to normal by 2012. Campo's didn't rise. The first storm on the burn scar, Christmas 2003, ran 46 times higher.
- **Faster Channels scenes, with identical pictures.** Animated nodes whose channel only changes their colour or visibility are now drawn from a cached list per channel. A list is rebuilt only when that channel's values change, and never while playback is paused. Before, every animated node was redrawn one at a time on every frame. The Burn Record went from 81 ms to 11 ms a frame while viewing and from 59 ms to 22 ms while playing, and The Pulse from 17 ms to 12 ms while playing. See [Channels](reference/channels-animation.md) for how to get the most from it: bind nodes that change together to one shared channel.

## 2026-09-13

- Added **[The Pulse: A Century of the San Diego River](examples/sd-river-pulse.md)**, the second scene of the San Diego River Watershed Atlas. It plays the river month by month from May 1912 to August 2026, 1,372 frames in all.
    - **Flow ribbons** over the reaches the three USGS gauges measure swell every winter and shrink every summer. Width shows the month's flow, and colour shows how it compares with the same month in other years.
    - **Rain columns** rise over the four long-record rain stations.
    - **A panel** beside the watershed shows every water year since 1913, plus a scrolling ten-year monthly window with a running date.

    The record shows the dams calming the river, a flow record missing the wettest month on record, and a river that hasn't run dry since September 1968. Missing data is drawn as missing, never bridged or estimated.
- Added **[The Storm Winter, 2004–05](examples/sd-river-storm-2005.md)**, which plays one of the wettest winters on record day by day. It was also the first big rain on the Cedar Fire's burn scar.
    - **The rain field** is 18 rain gauges across the county, each drawing the day's rain as a column.
    - **The river's ribbons** rise at its three gauges in answer.
    - **The panel** shows the whole season, every rain burst followed by a spike in the river.

    Rain totals that an observer read after several unattended days are drawn as wire columns, not spread across days nobody measured.
- Added **[The May 2014 Fire Siege](examples/sd-fire-siege-2014.md)**, the Atlas's first fire scene. It shows the Santa Ana week that sparked eight fires in northern San Diego County as a **space-time cube**: the county map is the floor, and time rises one unit per hour.
    - **Weather stations** are 128 threads coloured by humidity.
    - **Fire alerts** are 2,654 discs, sized by the fire-alert index Jeff Sale wrote for this same station network in 2014.
    - **Fires** are prisms rising from their ignition to when they were declared out.
    - **The now plane** sweeps up through the cube carrying the wind.

    It shows the alerts clustering in the mountains while the fires broke out near the coast, in air that was extremely dry and hot but mostly below the index's wind threshold.

## 2026-09-12

- **New: the San Diego River Watershed Atlas**, a long-term project that builds one real place up in layers: its terrain and rivers, then the weather, water and fire that cross it. Its first two scenes are in the gallery.
- Added **[The Watershed, Source to Sea](examples/sd-river-watershed.md)**: 433 square miles of real terrain from USGS elevation data, with a map draped over it and everything outside the watershed dimmed so the basin reads as a shape. It includes the whole river network by Strahler stream order (267 reaches), the watershed's three sub-basins, El Capitan and San Vicente reservoirs, the three USGS stream gauges, including Mast Road, which has recorded the river every day since 1912, and four century-long rain stations. Every coordinate comes from a federal data service, and the data corrected three things commonly repeated about the river. Its watershed is 432.8 square miles, not the 1,553 of the hydrologic unit it's usually filed under. It rises near the Volcan Mountains, not in the Cuyamacas. And two of the region's best-known rain gauges sit just outside it.
- Added **[Santa Ana Wind, December 2012](examples/santa-ana-wind.md)**: 130 weather stations every ten minutes for a month, as cones pointing downwind over the county's terrain and coloured by humidity. On 19 December the whole field swings offshore and the county turns from blue to red in about twelve hours. The scene opens at the peak of that event and plays the month with a running clock.
- **Surfaces can take a texture.** A Surface parent with a `texture_id` drapes that image across its mesh, using the same image orientation as a World Grid, so one map lines up on a flat grid and on terrain alike. Without one, it still colours itself from its vertices, which is the right choice when the colour *is* data. A texture also frees the picture from the mesh: a 120-column terrain used to show only 120 columns of a 2,400-pixel map. See [Colouring a surface](reference/topologies.md#colouring-a-surface-topology-17).
- **Large scenes render far faster, with identical pictures.** Five fixes, each checked pixel for pixel against the previous renderer. On the watershed scene, about 70,000 nodes, a frame went from **89 ms to 3.3 ms**:
    - **Surface meshes are compiled once** instead of rebuilt in Python every frame. On Santa Ana Wind that one change took a frame from 412 ms to 18 ms.
    - **Plot lines are compiled once too.** A 10,000-vertex river network went from 41 ms a frame to 8.
    - **A glyph drawn at zero size is skipped outright.** That makes terrain and line vertices free: give them scale 0 and only the mesh or line draws. `hide` would remove them from the mesh, and alpha 0 would make it transparent. See [Large terrain](reference/topologies.md#large-terrain-give-the-vertices-scale-0).
    - **Labels no longer cost a walk through the whole scene** every frame. That walk alone was 35 ms on the watershed.
    - **Fixed: an animated surface could freeze** if its Channels binding was made after the scene first appeared, for example through Channel In.
- New shared terrain tooling in the codebase (`glyphviz_core/terrain.py`) fetches free elevation tiles, builds the mesh, and drapes lines onto it. A line laid on raw elevation data ends up **underneath** the smoothed surface you see: 94% of the San Diego River did. So lines are laid against the surface as actually drawn, and they provably stay on top of it.

## 2026-09-11

- **New: the AI Observatory — GlyphViz pointed at a language model.** GPT-2 small reads a sentence and you watch what happens inside it. Each of its 12 layers is a ring; every one of the 294,912 features its sparse autoencoders find is a point, placed by meaning, so a feature sits in the same spot in every scene and a color means the same neighborhood all the way up the tower. The features that fire on the prompt light up as glyphs joined by attribution rods, click any point to read what researchers think it means, and **Play** reads the sentence token by token: a pulse climbs the layers, the strongest feature on each one pins its label, and the prediction appears at the top. The soundtrack is generated from the same numbers — each layer is a note, as loud as that layer is active, brighter the more features fire, and panned toward where on the ring the activity is.
- Added the **[Inside GPT-2: Mary and John](examples/ai-observatory-gpt2.md)** example: "When Mary and John went to the store, John gave a drink to" → " Mary", 68%. A column of "giving something to someone" features climbs the tower after *gave*, and the final layer's name feature pushes toward the answer.
- The pipeline that builds these scenes lives in the repo's `ai_observatory/` folder, in a Python environment of its own (PyTorch, TransformerLens, SAELens), so the app itself never depends on it. `make_scene.ps1` turns any prompt into a scene in about a minute, and three more ship there: a pattern-copying scene, and a pair of fact-recall scenes that GPT-2 small gets right once and nearly wrong once. The limits are measured and stated rather than hidden — the autoencoders reconstruct 99.7% of the model's internal state at layer 0 but only 78% by the last layers, and the feature explanations are automated guesses.

## 2026-09-09

- **The GlyphViz Skill can check which way a glyph points.** Its extent checker gained an AIM section listing the direction every cone, pin, cylinder, ring and marker actually points, grouped by parent. It flags the one mistake that has no innocent reading: rods rotated by hand that all end up parallel when they were meant to fan out. Before this, the skill asked for that check without providing a way to do it.
- New skill example, **Radial Spokes**: twelve rods around a Sphere hub, a Point hub and a Cube hub, with every rotate field zero. The topology aims them. Its generator re-derives each claim through the app's own placement code and refuses to write the file if any fails. It replaces the older Clock Face example, which nothing pointed to.

## 2026-09-08

- **The GlyphViz Skill now carries the app's own placement engine.** A byte-identical copy of the modules GlyphViz uses to position nodes ships inside the skill, so a Claude session with no GlyphViz installed can compute exactly what the app will draw. A checker built on it reports children buried inside their parent, children flung out of their layout, glyphs that will shear under a stretched parent, links with a missing end, and designs that would distort if the minimum-glyph-size option were switched on.
- The skill's hard rules were corrected and extended from real session transcripts. Two corrections matter most. **Every geometry is built to fit inside radius 1, not to span −1 to +1**: a cube's faces stop at 0.577, and a Pin is 0.1 wide and 1.1 tall. And **the minimum-glyph-size clamp is off by default**, and it can't protect a counter-scaled child even when it's on. Two new examples show the rules at work: **Rooted Bars**, four ways to draw a bar chart (only one survives a Global Scale change), and **Glyph Envelope**, a hyperglyph tested at the minimum, median and maximum of its data.
- **A point cloud import is no longer capped at 500,000 points.** That limit was only the dialog's spin box; the importer itself never had one. A 4.1-million-point scan imports in a minute or two.

## 2026-09-07

- **Saved scenes are about four times smaller.** GlyphViz used to write every node as a full 94-column ANTz-compatible row — roughly 550 bytes — whether or not a scene used those columns. It now writes only what a scene actually needs: the 20 columns the loader requires, plus `ratio` and `facet`, plus each optional column some node in the file gives a non-default value. The new LIDAR scan saves as **40.7 MB instead of 243 MB** and writes in 4.2 s instead of 18.3 s; across all 80 example scenes the total falls from 630 MB to 145 MB. Nothing is lost — a column is dropped only when leaving it out reloads to the same value, so re-saving a scene never changes it, and opening an older, larger file and saving it shrinks it in place. This is the format [GlyphViz Web](https://www.iluvdata.org/glyphviz/web/) already wrote, so the two now produce the same file for the same scene, and it is what the [node CSV format reference](https://www.iluvdata.org/glyphviz/) has always described as the recommended authoring dialect. Writing the full 94-column layout is still possible for ANTz/GaiaViz tooling, but it is now an explicit option rather than the default.
- Two smaller savings inside that: floats are written at the same 6 decimal places but without the trailing zeros (`0` rather than `0.000000`, which was most of the file), and a value that rounds to zero is written as `0` rather than `-0`. Unknown columns from a third-party file now survive a save, which the old writer silently dropped.
- Added the **[LIDAR Import example](examples/lidar-import.md)** — a real aerial laser survey, 442,767 points with per-point colour over about a kilometre of ground. It ships as a 2.55 MB `.laz` rather than a 17.7 MB `.las` (lossless, verified bit-for-bit), and it is a good example precisely because it is *ordinary*: projected coordinates with a 3.6-million-unit origin, 8-bit colour sitting in 16-bit fields, and no classification at all — the three things the importer has to get right before you see anything.
- **The point-target spin box no longer locks the app up.** Its `valueChanged` was connected from inside the handler it fired, so every click added another connection *and* re-entered the handler: click 8 ran it 128 times, click 12 ran it 2,048. Raising the target from 100,000 toward a 442,000-point file froze GlyphViz outright. The step is also 50,000 now rather than 10,000, which crosses the whole range in ten clicks, and typing an exact count no longer fires once per keystroke.
- **A large point cloud renders about 44× faster.** The tag overlay walked every node in the scene each frame — on a 442,768-node cloud that was 109 ms of a 111 ms frame, 97% of it, for a loop that skipped every node it looked at. Cloud points are now filtered out before the loop rather than inside it: the same scene went from **9 fps to roughly 400**. Points that are selected, or that pin themselves with `show_text`, are still labelled exactly as before.
- The import dialog now reads synchronously under a wait cursor instead of on a worker thread. Measured, the 10.6-million-point tile it was built against scans in 1.0 s and imports in 1.6 s, which is not worth a background thread — and the thread brought a crash on dialog close that was worth avoiding.

## 2026-09-06

- **New topology: [Point Cloud](reference/topologies.md#point-clouds-topology-18) (18)** — a parent whose children draw as one batched `GL_POINTS` array instead of one glyph apiece. It is the only topology that *replaces* how its children render rather than decorating it: Plot adds a polyline over its children and Surface adds a quad mesh, but a Point Cloud parent's children draw no glyphs at all. That is what makes six-figure point counts practical — measured, 100,000 coloured points replay in 0.10 ms per frame and a million in 0.63 ms. **Every point is still a real node**: it has an id, a colour, a label, a Channels binding, and it is individually clickable through the per-point colour-ID pick pass. The topology mirrors one added to the ANTz codebase (`kNPtopoPointCloud`), placement included, and adds no column — a cloud travels in the ordinary node CSV, and a file using `topo=18` opens correctly in a build that predates it, because an unrecognised topology already falls back to the same plain Cartesian placement.
- Two rules follow from the batching, and both are deliberate. The **`\` draw limit counts a cloud as one unit** — its parent glyph — so halving the limit thins the glyphs *around* a cloud and never decimates the cloud itself, the same way it already leaves links and plot lines alone. And in the show-all-tags mode **a cloud's points are not labelled** unless individually pinned or selected: a 100,000-point scan would otherwise bury the scene in text, and which labels survived the per-frame cap would be file order rather than anything you chose.
- **New: [Import Point Cloud](reference/point-cloud-import.md)** (Meshes → Import Point Cloud…, or drag a file onto the window) — reads **LAS, LAZ, PLY, XYZ and PTS**. LAS is binary but it is not proprietary: it is a published ASPRS specification, and LAZ became an OGC Community Standard in September 2026, so GlyphViz reads both through permissively-licensed libraries with no format reverse-engineering involved. A 10.6-million-point classified LAZ tile decompresses and decimates to 100,000 points in **1.4 seconds**.
- The importer's real job is the three things that are not file parsing. **Coordinates**: a georeferenced tile arrives in CRS units with an enormous origin — the test file runs to 639,003 easting in Oregon State Plane feet — so the scan is recentred and uniformly scaled to a world span you choose, measured from a percentile box so one stray bird return cannot shrink the whole cloud. **Colour**: most public LIDAR has no RGB, so ASPRS classification (ground brown, vegetation green, buildings red, water blue) and an elevation ramp are first-class modes rather than fallbacks, and 16-bit versus 8-bit colour is detected from the data instead of assumed. **Count**: the dialog reports what is in the file before you commit, and offers random, voxel-grid or every-Nth decimation to a target you set.
- The classification filter runs **before** the decimation, so your point budget is spent on the classes you asked for — drop ground on a tile that is 70% ground and ask for 100,000 points, and you get 100,000 non-ground points rather than 30,000. Imported clouds are **merged** into the loaded scene rather than replacing it, since a scan is nearly always context for something else, and the cloud's parent node carries the full provenance in its label: how many points, how coloured, sampled from what, which classes kept, and any vertical exaggeration applied.

## 2026-09-04

- Added the **Warm Winter Synesthesia** example — Jeff's own 3:47 piece, read from its seven-track Garage Band session rather than from a finished mix. Every track gets a **hyperglyph of its own**, so a glyph's shape, colour and motion belong to one instrument instead of to a frequency band of the whole mix. The stems turn out to be perfectly nested — each enters about 17.4 s after the previous one and leaves about 17.4 s before it — and the scene says that shape three ways at once: the seven glyphs stack upward in playing order, each glyph's size is bound to its own track's loudness, and the World row itself is on a channel, so the sky and fog open from a near-black winter night to a warming dusk as the piece builds. The glyphs overlap as it plays, deliberately: *"that's the way music is — the instruments are not isolated from each other in the audio."*
- Each track also gets its own frequency window, derived from its own spectral rolloff rather than one global 20 Hz–16 kHz span — which had left the bass track lighting three of twelve bands and the rest dead.
- The example ships its audio as a **7.3 MB `.m4a` rather than a 40 MB `.wav`**, remuxed from the original export with the audio stream untouched (no re-encode, no second generation of loss). PySide6 bundles Qt's FFmpeg media backend, so the decoder travels with the app — verified by playing m4a, mp3, flac and opus through a real player, headless.

## 2026-09-02

- The **[Vehicle Sales — Raw Auction Field](examples/vehicle-raw-auction-field.md)** scene now asks you a question instead of just looking good. It gained three labelled axis rails (sale date, model year, odometer, coloured the way the transform gizmo is), a glyph legend standing clear of the data, and — the real addition — a set of **tokens in every record's labels that turn Select By → "Tag contains" into an analytic filter**: `#COARSE`/`#FINE`, `#RENTAL`/`#FLEET`/`#LEASE`/`#DEALER`, `#OVER`/`#ATBOOK`/`#UNDER`, and more. Query a cohort, add the scaffolding by branch level, then Show Only Selected, and the axes stay under the glyphs.
- What that machinery is for: the dataset's `condition` column holds **two scales at once** — a 1.1–4.9 grade stored ×10, plus 12.2% of rows storing the same grade rounded to 1–5 — and pooling them halves the column's measured relationship to everything else. The scene had been drawing the evidence all along (a coarse row wears a near-black octahedron a tenth of the size it earned) and nobody had looked. The page walks through that finding, one more that is visible, and one that is real but which no amount of isolating will ever show you. Knowing which is which is the point.

## 2026-08-31

- **New tool: the [Epitrochoid Generator](reference/epitrochoid-generator.md)** (Tools → Epitrochoid Generator, **Ctrl+E**). A chain of nested Torus-topology parents, each spinning its own `translate_x`, *is* a Fourier series — each level's angle is measured in its parent's rotating frame, so the angles compose and the glyph at the end traces the sum of the arms. The designer gives you one row per arm, a live preview that keeps moving, and a readout that says what the design actually *is*: the harmonic ladder your rates produce, the exact frame count after which the curve closes, and the measured spectrum of the traced path. Eight presets, a seeded Randomize, and — unlike the Tree Designer, which exports a Glyph Composer template — it writes **node CSVs** directly, because an epicycle chain's whole point is a curve that only exists once the chain has been walked.
- **The pen leaves a line behind**, which is what ANTz could never do. The traced curve is a transparent Plot-topology parent holding one Point-geometry bead per frame at the pen's world position, so the Plot polyline through them *is* the path. With **Self-drawing trail** on, the tool also writes the Channels pair that steps each bead's alpha on as the pen arrives, so the curve draws itself during playback.
- **Two ways to leave the plane.** **Tilt** leans an arm's orbit out of the previous arm's by an exact number of degrees. **Tube** gives an arm a second circle riding the first, around the torus tube — in spectrum terms a sideband generator, turning harmonic *h* into *h*, *h−r* and *h+r* plus out-of-plane motion at *r*, which with two arms is a torus knot. Both are ordinary node fields, so a design saves and loads with no new column.
- Added the **Fourier Epicycles** example set (`examples/Fourier_Epicycles_Example/`) — six scenes from the same engine: the original four-term figure driven by `translate_rate_x`, the same figure drawing itself under Channels, a square wave from odd harmonics 1/3/5/7 at amplitudes 1, ⅓, ⅕, ⅐, and three that leave the plane. The construction is a GlyphViz-era port of an ANTz scene of Jeff's from several years ago, down to its original starting phases, which were recovered from the angles the file had wound up to when it was saved mid-flight.

## 2026-08-28

- **A node's Channels binding can now be set in the app.** The Properties panel's Selected Node group has a new **Channel In** field: type or dial a channel id and every selected node is bound to it immediately. If an animation is playing, the node starts moving on the spot — no file edit, no reload. Set it back to 0 and it stops and returns to the values saved in the file, rather than freezing on whichever frame was on screen. Until now that binding could only be written into the node CSV's `ch_input_id` column by hand, which meant you could not try an animation against a node you were looking at. The hint beside the box says what the chosen channel actually drives (`drives translate_z, color_r`) or which channel ids the loaded file offers, since a bare id has nothing else on screen to check it against. It applies to the whole selection, so several nodes can be pointed at one channel to animate in unison, and it saves with the scene. See [Channels](reference/channels-animation.md#binding-a-node-from-the-gui).
- Following from that: a scene whose `ch-map`/`ch-tracks` files bind **no** node yet now still loads its Channels transport, instead of hiding it as though there were no animation at all. That is exactly the scene the new field exists to wire up — animation data and geometry that were authored separately.
- **Tag labels are on by default, scoped to the selection.** Both *Show Tag Labels* and *Show Tag Labels of Selected* now start checked, so clicking a glyph reads out its label and an unselected scene stays as clean as before. Previously labels were off entirely and a new user had to know about the **T** key to discover that a scene was labeled at all. Uncheck *…of Selected* for the old show-everything behavior; **T** still toggles labels off completely.

## 2026-08-26

- **New geometry: the [Flat Ring](reference/geometries.md#the-flat-ring)** (ids 33 and 34, solid and wire) — a torus whose cross-section is a rectangle instead of a circle. A rounded torus reads as soft tubing and its highlight slides around the tube; a flat ring has four real faces with crisp edges, which is what makes it read as a machined instrument band and what lets a texture — degree markings, a zodiac strip, a ruler scale, a name wrapped once around a hoop — lie flat and legible on it. It adds **no new column**: `ratio` is the band's radial width and `scale_z` its height, both exactly as they already work on a torus, so a Torus ↔ Flat Ring swap is a pure change of look and a Torus-topology parent places its children identically either way.
- Added the **[Armillary World](examples/armillary-world.md)** example, built on it: a teaching space you fly through, with a real armillary sphere at the centre — graduated azimuth dial, declination band, zodiac ecliptic at a true 23.44° obliquity — ringed by eight concentric topic zones of mathematics, from Number & Proportion out to Scale & Cosmos. 991 nodes in about 300 KB. Every node carries a label, so **T** explains any glyph in it. Its page also writes down the two rules that authoring with rings turns on, both of which are design constraints rather than settings: a ring carrying children must be scaled uniformly, and a ring carrying readable text has to be a wide band, 10–20% of its own radius, because its texture canvas is 150:1 or worse.

## 2026-08-24

- **Objects can now be viewed from the inside.** Four new geometries — **Sphere (Interior)**, **Cube (Interior)** and **Cylinder (Interior)** capped or open — draw a shape's inner surface instead of its outer one, so you can fly the camera into it and watch a texture or a video wrap around you: a 360° video sphere, a cylindrical panorama, a video room. Pick one from the Geometry dropdown, cycle to it with **O**, set it in the `geometry` column, or animate it through Channels; it is an ordinary geometry in every respect, so a Link carrying one becomes a tube you can fly down. See [Interior geometries](reference/geometries.md#interior-geometries-seen-from-within).
- This is deliberately *not* the same as switching off back-face culling. Looking at the inside of an ordinary shape is a mirror view, so a video seen that way plays backwards — text and faces reversed. The interior geometries are built mirrored, so the image reads the right way round from within; they draw unlit, so the footage comes through at its own full brightness instead of at roughly half of it under scene lighting; and they stay single-sided, which keeps translucent objects blending correctly.
- The interior cylinder's **End caps** are a checkbox in the Properties panel: off for an open tube, on to close both ends and map the texture across them. It is stored as the geometry itself, so the choice saves and loads with the file rather than needing a column of its own.

## 2026-08-23

- Added **[Orbital Traffic](examples/orbital-live-sky.md)**, three scenes built from live CelesTrak element sets through one shared SGP4 propagator — and each animating a different way on purpose. **[Live Sky](examples/orbital-live-sky.md)** puts every tracked satellite where it actually is right now, refreshed once a second by an external generator loop and **File → Watch and Reload**. **[One Orbit](examples/orbital-one-orbit.md)** replays a 93-minute revolution in twenty seconds through Channels. **[Orbital Shells](examples/orbital-shells.md)** drops the map for the inertial frame, where the orbital planes stand still and the Earth is the thing that spins — and it moves with no playback at all, from `rotate_rate_z` on each ring. Every plane count and spacing in it is *recovered* from the element sets by clustering rather than written into the generator, which is also how it turns up Galileo's two stranded satellites.
- **`tools/export_frame.py` renders a scene to a PNG headlessly**, so whoever is iterating on a generator can see the result without opening the app and grabbing the screen. `--angles three-quarter,front,top` renders several viewpoints into one labelled contact sheet — a glyph that reads correctly from one viewpoint is routinely wrong from another, and a starburst and a flat fan are identical head-on — and `--report` prints what a picture cannot: scene extents, rendered glyph size per hierarchy level, how far each parent's children actually sit from it, and whether the textures loaded.
- Fixed two bugs in that renderer that made its output quietly untrustworthy. **Textures were loading into nothing**: the upload ran before the GL context existed and reported success, so every textured scene rendered untextured — a plausible-looking picture that was wrong. And on a fractional-DPI display **labels landed far from their glyphs** (157 px away, measured) while the glyphs themselves stayed correct, which is what made it so misleading.
- Updated the **GlyphViz Claude Skill**: Global Scale is now a rule in the always-loaded file rather than only a reference page — a generator that assumes the old 3.0 default lays its scene out wrong at the current 1.0 — plus the 3-D graph layout findings and a pointer at the headless renderer above, so a Claude working on a scene can look at what it built.
- The **[Timeline Tower Designer](reference/timeline-tower.md)** now ships two demo archives, so the tool can be tried immediately instead of after the days X takes to deliver your own archive.

## 2026-08-21

- **New tool: the [Timeline Tower Designer](reference/timeline-tower.md).** Drop your X (Twitter) archive onto a browser page and it becomes a **Timeline Tower** — a single hyperglyph of everything you have ever posted. Each post is a needle radiating from a vertical time axis: height is when it was posted, bearing is the time of day it was posted, colour is whether it was an original, a reply, a repost or a quote, and concentric rings riding each needle carry likes, reposts, hashtags, links, uppercase, punctuation and your own keyword hits. Because a ring always sits at the same distance from the axis, one ring followed up the tower is one variable followed across a whole life. Every needle links back to the real post, so **U** opens it on X. **Nothing is uploaded** — the page has no network code in it at all and works offline; your archive is read in the browser and stays there.
- Three layouts share that mapping. **Tower** is the classic form, read from the outside. **Immersive** turns it inside out — the needles hang inward off a cylindrical wall so you stand at the centre of your own history, which is what it was built for in VR. **Helix** winds time as a spiral, one turn per year, so seasons stack vertically and the record never doubles back; it reads like tree rings, and time of day survives as the needle's pitch.
- The design is not new — it was built for ANTz in 2018 — but the data behind it is better: the X archive is complete where the API capped a timeline at the last 3,200 posts, and it carries a per-post repost count the API never returned, which is why there is a reposts ring now that the original could not draw.
- The same scenes can be built from a terminal with `twitter_lab/tut.py`, which is the reference implementation the browser tool is checked against.

## 2026-08-18

- **Tag label text size is now adjustable** (Properties panel → Display → **Tag Text Size**): a slider from 6 to 36 points covering every label in the scene. Like Tag Color, it is scene data — it saves with the file, so a scene's labels are the size its author chose — and it is bindable as a Channels attribute on the World row.
- **Labels are two points bigger by default** (9 pt → 11 pt). Tag text was previously painted at a fixed size that read a little small at a normal working distance; every existing scene picks up the larger default on open, with no file change needed.
- Added the **[Trust Network](examples/trust-network.md)** example — the Bitcoin OTC web of trust, where every one of the 922 traders is a three-level *hyperglyph* rather than a coloured dot: two hubs at its poles for ratings received and given, and a spoke per band of the trust scale, sized by how many ratings fell in it. Reputation becomes a shape you can compare across the scene. Its 17,235 signed ratings are drawn as links that carry their rating in geometry, and the whole marketplace grows from 13 traders to 922 under Channels playback, with the layout re-solving as it goes.

## 2026-08-17

- **GlyphViz can now lay out a network graph in three dimensions.** Two new modules — `glyphviz_core/graph.py` and `glyphviz_core/graph_layout.py` — take an edge list and produce world positions a node CSV uses directly: ForceAtlas2, Fruchterman–Reingold, PivotMDS for initialization, Louvain community detection, and Gephi's k-core and edge-weight filters. It runs on the generator side, so nothing changes in the app itself; see the new [3D Graph Layout](reference/graph-layout.md) reference. The one thing that had to change for three dimensions is worth knowing if you bring your own graph: ForceAtlas2's repulsion falls off as 1/d, which is the Coulomb law *of the plane*, and used unchanged in 3D it collapses a graph into the dense hairball that gives 3D graph drawing its bad name. `repulsion_falloff=2.0` restores the real inverse-square law and is the single most important setting in the module.
- Added the **[Collaboration Networks](examples/collaboration-networks.md)** example, two scenes built with it: 3,931 condensed-matter physicists and the 10,223 collaborations between them, and the 379-author network-science community with the ForceAtlas2 solver's own history bound to Channels — press play and the layout crystallises out of a random cloud. Community is encoded as colour *and* as geometry, so **Select By → Geometry** pulls out a whole sub-network, and each scene carries its key as real glyphs in the scene.
- **Fixed the camera locking up while Follow Selected was on.** With camera smoothing enabled and **F** active, orbiting and zooming did nothing at all — following a node was re-pointing the camera's goal at its own lagging position on every frame, which cancelled the glide before it could run. Following now tracks only what it should, the pivot, and navigation behaves exactly as it does with Follow off.
- **Fixed label columns being read as numbers.** A `text` or `link` column holding digits — a year, an ID, a measurement — was inferred as numeric on load, so `2016` came back as `2016.0` and was written that way on the next save. Label columns are now always read as text.

## 2026-08-15

- **GlyphViz Web now runs in VR**, and the docs now cover it: [Immersive VR](reference/immersive-vr.md) is a new reference page for the browser app's WebXR mode. Open the site in a headset's browser and press **Enter VR** to stand inside the scene — thumbstick flight, one-handed grab-drag and two-handed resize, controller-ray picking, in-scene labels, a wrist-mounted control panel with the Channels transport and the draw-limit lever, and Channels playback on-headset. No app to sideload and no PC-VR link; it's a URL someone can send you. Confirmed on hardware on a Meta Quest 3; any WebXR-capable headset browser, Apple Vision Pro included, should work the same way. The [Roadmap](roadmap.md) and [FAQ](faq.md) are updated to match — WebXR was listed there as the near-term target, and it has landed.
- **Filled in the two placeholder tool references.** [Glyph Composer](reference/glyph-composer.md) now documents the level model, every per-level parameter, the Topo Scale Auto fit, link levels, the preview behavior, and the template format. [Hyperglyph Generator](reference/hyperglyph-generator.md) covers the dialog, the seed/randomize workflow, Idle Motion, Capture live orientation, how designs are actually chosen (geometry families, palette schemes, the topology pool), and the `hyperglyph_lab/` batch CLI with its ratings-and-mutation loop. The Reference index gained a **Glyph authoring tools** group, and the Tools menu reference was missing its Hyperglyph Generator row.
- **New tool: the [Hyperglyph Tree Designer](reference/tree-designer.md).** A browser tool for designing branching, tree-like hyperglyphs — trees, ferns, corals, dendrites — and exporting them as Glyph Composer templates. It runs entirely in the page, with a live 3-D preview beside the template JSON, and it's a 3-D port of the branching engine from the 2-D [Fractal Forest](https://www.iluvdata.org/fractalforest/) drawing tool, keeping that tool's controls: Branch angle, Angle random, Length scale, Base width, Width scale, blossoms. Every branch continues its parent's direction, deviated by the branch angle, which is what makes the results read as trees rather than as clusters. Fork twist rotates each fork's plane in 3-D — set it to 0 for a flat, 2-D-style tree. Branching points are ordinary objects and the limbs between them are Link nodes, so a limb can be a cylinder, a cone, a pin or a cube. Fourteen presets included. Download the template, then **Tools → Glyph Composer → Load Template…**, or paint whole forests with it via **Use as Draw Brush**.
- **The Glyph Composer can now build Links.** Every level below the root has a **Link to Parent** option that gives each object at that level a connector back to its parent, drawn as any geometry stretched between the two. Links take their object's color by default, or a color of their own — brown limbs under a bright canopy. Combined with the level's altitude offset, this is what turns a composed glyph from a stack of touching shells into a jointed, branching structure. Templates saved before this load with links off and generate exactly as they did.
- **Links can now be any geometry.** A Link (the connector between two objects) used to draw as a thin line or a textured prism and nothing else; it now renders whatever geometry you give it, stretched between its two ends — a cylinder rod, a tapering cone, a wireframe cage, an imported mesh, or any other shape distorted along the connection axis. This is what ANTz always did, and it makes an edge able to carry shape as well as connection, which opens up far more lifelike hyperglyph structures. Press **O** / **Shift+O** with a link selected to cycle through the lot. `ratio` is the connector's thickness whatever geometry it carries, and the endpoint distance is its length. See [Geometries](reference/geometries.md#geometry-on-a-link-node).
- **PDB protein import now produces true ball-and-stick**: bonds render as real 3-D rods between the atoms rather than thin lines.
- **Fixed a long-standing picking bug**: clicking an object that had a link attached selected the *link* instead, and a rubber-band selection could miss the object entirely. Depending on the object's shape it could be impossible to select with the mouse from any angle, which is why it looked like it depended on the camera angle. The pick pass was drawing an invisible target at each link's own position — which is exactly where its first object sits.

## 2026-08-14

- Added **Save Selection As…** (**Ctrl+Alt+S**): write the selected objects out to a node CSV of their own, keeping them exactly where they sit. Saving a subset naively would relocate it — an object whose parent stayed behind reloads as a root, and a root's position is read literally instead of through its parent's topology — so the export bakes each detached object's world placement into its own transform by default. Selected objects bring their descendants (and any links joining two of them) along, and matching tag and Channels files are written beside it.
- Rebuilt the **Pin** glyph to ANTz's actual shape: a true apex, a dome sitting flush on the cone's rim, no holes at either end, and 48% fewer triangles. Its tip now sits on the object's own origin, which is what lets Pin-topology children ride the shaft — note this moves existing pins up by about one glyph height.
- Gave the **Hyperglyph Generator** a **Save Recipe…** button: a generated design writes out as a Glyph Template `.json`, the same format **Tools → Glyph Composer → Load Template** opens — so a randomized hyperglyph you like can be reopened and reworked level by level instead of only being inserted as-is. The file is named for its seed, which is what makes the design reproducible.
- Added **Capture live orientation** (on by default) next to it: with Idle Motion running, the preview is spinning when you click Save, and this writes the pose it had reached rather than the orientation it was generated with. A recipe stores one rotation per *level* while Idle Motion gives every node its own axis and speed, so the trunk is captured exactly and each deeper level takes its first node's orientation; uncheck it to save the design as generated. A recipe carries no rate fields either way, so a saved one is always static.
- Warned before handing a very large hyperglyph to the Glyph Composer: designs over ~2,000 nodes render fine but rebuild their whole tree after every Composer edit, so the Generator now flags the count and suggests turning Auto Preview off.
- Gave newly created objects **ANTz's row-wrapping placement**: each new object steps along `translate_x`, and when the next step would reach a full lap (360) it restarts at 0 while `translate_y` steps to the next row. Repeated **N** / **Shift+N** now array into a grid instead of running off in a line — and, more usefully, the child that completes a lap around a Sphere, Torus or Cylinder parent starts a *new ring* instead of landing exactly on top of the first one.
- Added **Placement Step** and **Placement Z** to the Properties panel's New Object Defaults — the two numbers ANTz hardcoded. Placement Step sets how far apart consecutive objects sit (5 by default; type 15 for ANTz's own 24-per-ring lattice); Placement Z sets the `translate_z` each is born with, as two values, since the axis means height above the world plane for a root object but stand-off distance from the parent for a child. Both apply to N, Shift+N, the New Node / New Child buttons, paste, and mesh import.
- Added optional **camera smoothing** (Properties panel → Camera): navigation gets a weighted glide instead of snapping frame-to-frame. It's **off by default**, and it's ANTz's idea done coherently — ANTz eased the camera's position while applying the orbit angle instantly, so the object you were orbiting swung out of frame for a second or so; here the whole camera rig eases under one time constant, and the object you're orbiting stays put. Two presets (Off / ANTz) and a scope selector for which gestures it applies to. Beyond looking smoother in demos, it buffers hand tremor.

## 2026-08-13

- Taught the **Glyph Composer** per-level Topology Scale, with an **Auto** setting that fits it for you. The Composer describes child placement in one vocabulary — a 0–360 sweep — but the parent's topology decides whether that's degrees or world units, so choosing Cube, Pin, Plane or None used to fling a level's children roughly 300× the parent's radius away. Auto (on by default) applies the ANTz scale exactly when a sweep is about to be read as a distance. Templates saved before this load onto Auto, so a design that came out broken now regenerates correctly.
- Applied the same fit to the **Hyperglyph Generator**, which had the same problem under Pin parents: across a 200-design sample it re-fitted 67 levels and pulled 62 designs (31%) back in by 7.5×–117×. Saved recipes regenerate as the corrected design.
- Stopped the Glyph Composer's preview camera resetting on every edit — zoom in on a detail and it stays there. Re-framing is now explicit: a **Reset View** button, a freshly loaded template, or the first preview.

## 2026-08-12

- Added **Topology Scale** (Properties panel, under Topology): a per-node control over how far one unit of a *child's* `translate` reaches, for the axes a topology reads as a distance rather than an angle. It fixes the long-standing surprise where changing a parent's topology — by hand, or from a Channels track — flung its children off into empty space: values authored as degrees (0–360) are enormous when the new topology reads them as world units. Angular axes (longitude, latitude, orbital and tube angles) are never scaled, so turning it down can't distort a circular layout. The **ANTz** preset (1/180) reproduces ANTz's convention, where a linear axis spans the parent's own extent — a cube facet is 360 units across — and is the setting at which a layout survives switching between an angular and a linear topology. **Existing scenes are unaffected:** the default, and what any file without the new column loads as, is the behavior GlyphViz has always had. Also bindable as a Channels attribute, and a status-bar hint now names the control when a topology change does scatter a subtree.
- Added a Draw Mode walkthrough to the [Guided Tour](getting-started/guided-tour.md), including painting Glyph Composer hyperglyphs as brushes.

## 2026-08-11

- Added **Draw Mode** (**D** key, or the Properties panel's Draw Mode button): paint objects into the scene with the mouse. A click stamps one object — built from the New Object Defaults — onto the World Grid where the cursor lands; a drag stamps a trail of them at a configurable pixel spacing, and **Draw Z** sets each object's elevation. Stamped objects are real grid children, so a drawn scene saves and reloads like any other.
- Made Draw Mode stamp whole **hyperglyphs**: the new **Stamp** combo takes any Glyph Composer template (via its **Load…** button, or the Glyph Composer's new **Use as Draw Brush** button, which sets the brush and turns Draw Mode on in one press), planting the full hierarchy per click. New **Heading Jitter** and **Scale Jitter** controls randomize each stamp's spin and size — one draw per stamp, so hyperglyphs stay coherent — for organic, hand-scattered strokes like drawing a forest of glyph trees.
- Removed the long-standing 0.2-per-axis minimum on rendered glyph size as a default: glyphs now render at exactly the size their `scale_x/y/z` fields ask for, however small. The old clamp is still available as **View → Enforce Minimum Glyph Size (0.2)** (also in the Properties panel's Global Scale group), for when tiny nodes need to stay visible and clickable. World Grid footprints were never clamped and still aren't.

## 2026-08-05

- Added per-example downloads: every Examples Gallery page now offers a zip of just that example, and the examples that hold several scenes offer one zip per scene. The full examples set is unchanged.
- Made a dropped zip whose only payload is a `.pdb` import that structure, instead of being refused for having no node CSV.

## 2026-07-31

- Redesigned the home page: header carousel, a GlyphViz Web deployment call-to-action, and real (non-placeholder) content pages.
- Added the Guided Tour and rebuilt the Examples Gallery with real, generated screenshots for all 36 examples.

## 2026-07-30

- Added **Fetch Basemap**: World Grid panel button that auto-downloads map imagery (OSM streets, Esri satellite, or OpenTopoMap terrain — no API key) for a grid's lon/lat bounding box and applies it as the grid's texture.
- Added drag-and-drop loading: drop a node CSV, a scene folder, or a zip onto the window to load it (Shift+drop merges instead of replacing).
- Reworked Camera Mode flight to ANTz-style rate flight on left-drag: press point sets a bearings origin, cursor offset sets continuous forward/turn speed, flight stays locked to the horizontal plane it started on.

## 2026-07-29

- Added **Camera Mode** (free flight, **C** key), displacing the old plain-C camera cycling (moved to **Shift+C**).
- Expanded the Channels bindable-attribute set from 22 to 34 attributes.
- Added two new Channels examples and a Channels reference page to the docs site.

## 2026-07-28

- Added `tools/release.py`: one command to build, archive, publish, and re-stamp a Windows release, including rebuilding and publishing the docs site.
- Added **Scene Merge** (File > Merge Node CSV…, Ctrl+M): load a second node CSV *into* the current scene, rebasing ids so nothing collides.

## 2026-07-26

- Published the Windows app and example-scenes downloads on the Installation page.
- Made the 3D viewer's reference grid color settable per scene.
- Made tag text color settable, and added the ability to pin an individual node's tag label on regardless of scene-wide tag display settings.
- Extended tag-text drawing to Link nodes, under the same settings as any other node.
- Added a toggle to show/hide the selection bounding box without deselecting (**Ctrl+B**).
- Fixed the `\` draw-limit performance feature to actually cache per-frame scene scans, so it pays off as intended.

## 2026-07-22

- Inverted camera orbit-drag direction so dragging feels like grabbing the object, not flying around it.
- Added a status-bar tag-text display and a **Select by Tag Text** keyword search.
- Added the **CalStateTesting** example's Achievement Gap and Full Decade Cube scenes.
- Added the **YBCO Superconductor** example — the first crystallography/space-group visualization.

## 2026-07-21

- Added **Watch and Reload** (Ctrl+R): hot-reload the open node CSV whenever it changes on disk, preserving camera, selection, and Channels playback.
- Added Alt+click to open a node's link (URL, local file, or app launch).
- Added the **RSS News** example: a live multi-feed globe with article children ringing each concept cube.

## 2026-07-19

- Added the **San Diego Seismicity** example: real World Grids plus Channels time-replay of seismic events.
- Curated three Claude-Skill-generated NHL history exemplars, two of which were folded into the GlyphViz Skill itself as reference examples.

## 2026-07-18

- Added the GlyphViz Skill's `world-grid.md`, `tags-and-labels.md`, and `channels-animation.md` reference documents — the core data-format specs the Claude Skill relies on.

## 2026-07-17

- Added combined orbit+zoom camera drag and multi-camera cycling.
- Added the GlyphViz Skill's color-palette and textures/media reference documents.
- Hyperglyph Generator: assign `color_index` from a node's branch level.

## 2026-07-15

- Added video-texture audio **Solo Audio to Selection**.
- Added the **Bird Song Spectrogram Surface** example: an animated spectrogram waterfall.

## 2026-07-14

- Added ANTz-style **O/J** key cycling: step the selected node through every geometry (**O**) or topology (**J**), Shift to reverse.
- Added color palettes and `color_index`: ANTz-style **=**/**−** and **Alt+=**/**Alt+−** cycling through a node's palette.
- Added textured Link (Prism) geometry with flow animation, plus interactive Link creation.
- Adopted a real World Grid (type=6) in the GTDB Event Cloud and Time Replay examples.
- Added the GlyphViz Skill's `topologies.md` reference and the initial skill scaffold + verified node-CSV-format reference.

## 2026-07-13

- Shipped **World Grid V2** (type=6): a real, movable/rotatable/scalable geospatial reference plane with an explicit `parent_id` child-attachment model.
- Added **Globe Grid**: a World Grid's geometry can toggle between a flat plate and a sphere ("globe") form, placing the same children by lon/lat either way.
- Added a Channels playback fast path, FPS slider, and transport/panel keyboard shortcuts (measured 14x speedup on dense, mostly-static scenes).

## 2026-07-12

- Added the **Cat Scan Synesthesia** example: the first true audio-driven "music synesthesia" scene.
- Added Global Terrorism Database (GTDB) Channels scenes: Time Replay and Campaign Pulse.
- `ChannelEngine`: added animation of rate attributes (`translate_rate` / `rotate_rate` / `scale_rate` per x/y/z).
- Reorganized the audio-animation examples into per-example folders and added three more songs.

## 2026-07-07

- Global Terrorism Database example: added a rosette layout (12 evenly-spaced ring objects), a tagged octahedron root with a Tab-friendly hierarchy, and a Blue-Marble world-map ground plane aligned exactly to lat/lon.

## 2026-07-06

- Added the **Global Terrorism Database** example: organization rosettes, an event cloud, and a linked org–event network.
- Excluded World/Camera/Grid configuration nodes from bulk selection commands (Select All, etc.), so scene infrastructure can't get swept up by accident.
- Added a per-mesh geometry dropdown entry for imported meshes, and fixed mesh assignment via the dropdown.
- Auto-load a `media/` folder next to the app as the startup texture folder.

## 2026-07-05

- Vectorized scene transform math: post-edit recompute dropped from 4.5s to 0.38s at 100,000 nodes.
- Vectorized CSV loading: 8.5x faster on 100,000-node scenes (6.6s → 0.8s).
- Made node-table selection and refresh scale cleanly to 100,000+ rows.
- Removed the 500-tag cap for selected nodes and sped up tag painting roughly 4x.
- Added the **Vehicle Sales** example: three scenes built from a 559,000-row used-car auction dataset.

## 2026-07-04

- Merged **PDB protein import** (BioPython + KD-tree bond inference) — load a protein structure file directly as a glyph hierarchy.
- Added camera focus-fit framing and **Follow Selected Node** mode (**F**).
- Added the **Flocking** example: a boids simulation baked into Channels animation files.
- Moved the MkDocs documentation site source into the main repository (`glyphviz-docs/`).

## 2026-07-03

- Added the **Hyperglyph Generator** GUI tool; fixed a Z-topology clustering and scale-compounding bug found while building it.
- Added retained per-node draw-data caching in `Scene` (a "display list" for the whole scene), improving frame times on large loaded scenes.

## 2026-07-02

- Rebalanced example scene scales and geometry for the Global Scale default change (see 2026-06-29).

## 2026-07-01

- Added **Hyperglyph Lab**: a procedural music-synesthesia glyph generator (batch CLI, notebook, and GUI).

## 2026-06-30

- Added **stereoscopic cross-eye 3D** view to the Viewer panel, and fixed stereo eye rotational misalignment near top-down camera angles.
- Added the **Glyph Composer**: a hierarchical glyph template builder with live preview (Tools > Glyph Composer, Ctrl+G).
- Improved rendering performance further: display-list caching, frustum culling, and a tag-count cap.

## 2026-06-29

- Changed the Global Scale default from 3.0 to 1.0 (with a rebalance pass across affected examples over the following days).

## 2026-06-28

- Added ratio-driven Point glyph sizing and Circle/Cross/Star marker shapes; antialiased points and lines, and rounded Link/Plot line caps and joins.
- Added the **CalStateTesting**, **SES Achievement Gap Terrain**, **District Heatmap**, and **Hacking Creativity Glyph** examples.

## 2026-06-27

- Fixed Torus/Cylinder (and their Z-variants, and Spiral) child orientation so children orient with the circular path they sit on, rather than a fixed world orientation.

## 2026-06-26

- Added **GEO_MESH**: import OBJ/STL/PLY/glTF files as a glyph's rendered shape.
- Added the **Multi-Hike Race** example: a 20-hike GPS race demo over real Cowles Mountain terrain.
- Linux port spike: added an interactive browser GUI over noVNC, plus a headless NVIDIA/Linux GPU smoke-test container.

## 2026-06-25

- Fixed a multi-level non-uniform-scale distortion bug via true recursive matrix-stack composition — the fix that unblocked World Grid development.
- Added timestamped Save / Save As and the **K**-key autosave, with an optional companion tag-file save.
- Added **Copy/Paste** for nodes (**Ctrl+C**/**Ctrl+V**): duplicates a node together with its full descendant subtree.
- Added Scene World Settings: background color, 7 render modes, and fog.
- (World Grid V1 was added and then reverted the same day — its implicit root-glyph attachment design was replaced by the explicit-parenting World Grid V2 shipped 2026-07-13.)

## 2026-06-24

- Added per-node `translate_rate` / `rotate_rate` / `scale_rate`: continuous per-cycle animation without needing full Channels playback.
- Added per-node `rotation_mode`: GlyphViz's own Euler XYZ convention alongside ANTz's Heading/Tilt/Roll, defaulting new nodes to Euler XYZ while legacy files keep rendering unchanged.
- Added the **Surface Example** (Cowles Mountain DEM rendered via `TOPO_SURFACE`) and a New Object Defaults panel.

## 2026-06-23

- Implemented the Cylinder topology and all Z-topology variants; fixed a Cube `facet` CSV bug.
- Added a Facet picker to the Properties panel for Cube/Zcube children.
- Added the **Topology Example**: a child-distribution tutorial scene covering all 18 topologies.
- Added **Save Scene as PNG** (File menu, **F12**).

## 2026-06-22

- Added audio-driven Channels playback ("music synesthesia") with real audio sync — the seed of the audio/music examples line.
- Renamed GlyphViz's own native CSV prefix from `np_` to `gv_`, establishing the naming convention used ever since.
- Replaced the old `usr/images/` texture folder convention with a single `media/` folder; added animated GIF playback.
- Added audio for video textures (mix-all by default, with a solo dropdown).

## 2026-06-21

- Added texture animation to Channels, and wired Channels/texture playback into the VR spike.
- Added camera-facing tag-label billboards in VR.
- Added the **AutoSleep 2025** example (sleep/deep-sleep visualization from an AutoSleep CSV export).
- Carried a parent's per-axis world scale correctly into torus/rod/pin/cube/spiral child placement.

## 2026-06-18

- Split the codebase into `glyphviz_core` (the Qt/OpenGL-free kernel) and `glyphviz_gl` (the PySide6/PyOpenGL renderer) — the package boundary the project still uses today. See [Architecture](architecture/package-boundary.md).
- Extracted `glyphviz_xr` from the original OpenXR stereo spike script into its own package built on `glyphviz_core`.
- Added controller-ray picking with a wireframe-box selection highlight, and Touch controller navigation, to the VR spike.
- Added auto-scale so any file loaded via `--csv` gets a sensible default size.
- Loading genuine GaiaViz `np_node.csv` files directly, without a header-rewriting step.

## 2026-06-17

- Added interactive mouse manipulation (move/rotate/scale dragging); fixed a picking bug and a QPainter GL-state leak.

## 2026-06-16

- Added the channel-animation system and the **SineWave** example — Channels' first working version.
- Added video-as-texture support via Qt Multimedia.

## 2026-06-15

- Added tag text and the node-link system (labels with clickable URL/file/app links).
- Added Link lines, Plot polylines, and Surface quad-mesh rendering.

## 2026-06-14

- Added Save / Save As, writing the full GaiaViz-compatible 94-column CSV format.
- Added draw-limit culling and an FPS counter; fixed a per-frame transform bottleneck.
- Fixed non-uniform scale transforms and child placement to match ANTz's actual behavior.

## 2026-06-13

- Added ANTz-style node creation (**N** / **Shift+N**) and Create panel buttons.

## 2026-06-12

- Added multi-object selection, Select By / Select All, panel visibility toggles, and keyboard hierarchy navigation.

## 2026-06-11

- Added the ANTz-compatible 94-column golden-master test scenes that the [Golden-Master Validation](architecture/golden-master-validation.md) harness still uses today.
- Fixed wireframe picking and adopted GaiaViz's `branch_level` convention in test scenes.

## 2026-06-10

- Added the golden-master test harness itself, alongside a Scene/viewport rewrite.
- Fixed Rod placement/scaling and added topology-aware child orientation.

## 2026-06-08

- Implemented the Cube, Pin, Spiral, Plot, and Surface topologies; fixed the Rod topology.
- Switched the world to Z-up (matching ANTz's convention), added rotation editing/cascading, and expanded the glyph library.

## 2026-06-07

- **Initial commit**: GlyphViz 3D node-graph visualizer.
- Made X/Y/Z scale independently editable; fixed selection and added camera-focus UX.
