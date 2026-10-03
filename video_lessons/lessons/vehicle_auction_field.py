"""Example explainer: Vehicle Sales, Raw Auction Field.

Screenplay follows the gallery page glyphviz-docs/docs/examples/vehicle-raw-
auction-field.md: no aggregation -> the axes -> the scene's own legend and
one glyph read part by part -> tag queries -> the three results the page
reverse-engineers, the third because the picture can't show it.

Every query runs through the app's own Select By handlers
(MainWindow._on_select_by, _on_select_by_tag) and Show Only Selected
(_isolate_selected), in the order the page recommends: Branch Level 9 first
so the axes stay, then "Add to current selection", then the token.
Nothing is saved; a filmed scene_csv is never written back.

Numbers spoken are the page's (checked 2026-10-03). Landmarks, by label:
axis titles 10 / 21 / 30, month labels 2..9 (Apr = 6), the 14x legend glyph
32 with parts 33..36, the Lexus pair 61114 (cond 44/49) and 91859
(cond 4/49), whose +Z condition octahedra are 61116 and 91861.
Measured on the scene: #ATBOOK roots' 90th-percentile height is 39 units
(~98k mi) against 61 for #UNDER (~153k mi); #COARSE median height 15
(~38k mi), median model year 2012.
NOT a "flat sheet": the gallery page says the coarse cohort is one, but in
the shipped scene its heights match the rest (24% above 100k mi vs 22.5% of
#FINE; 90th percentile 147k vs 137k mi), so the video says what the picture
shows instead: ordinary cars, spread like the rest, wearing the wrong badge. The scene is 100,083 nodes, so this lesson renders slowly.
"""
from pathlib import Path

from lessonkit import (Callout, Key, Lesson, Shot, text_card, AMBER, CHALK, CORAL,
                       TEAL)

REPO = Path(__file__).resolve().parents[2]
SCENE = (REPO / "examples" / "Vehicle_Sales_Example" / "Raw_Auction_Field"
         / "RawAuctionField_gv_node.csv")

X_TITLE, Y_TITLE, Z_TITLE, APRIL = 10, 21, 30, 6
LEG_GLYPH, LEG_INSIDE, LEG_Z, LEG_X, LEG_Y = 32, 33, 34, 35, 36
LEG_POS = (-395.0, -20.0, 64.0)
LEXUS_FINE, LEXUS_COARSE = 61114, 91859
OCTA_FINE, OCTA_COARSE = 61116, 91861
PAIR_MID = (337.8, 176.0, 14.4)
FIELD = (210.0, 96.0, 45.0)
RED, GREEN, BLUE = (240, 80, 70), (90, 210, 110), (90, 140, 255)
GOLD = (230, 190, 70)


def bigger_labels(L):
    # Viewer-side Tag Text Size for video legibility; never saved. This scene
    # ships no World row, so there is nowhere to set it: labels stay at the
    # app's default 11 pt, which is what a viewer opening it will see.
    world = L.vp._scene.world_node()
    if world is not None:
        world.tag_font_size = 13
        L.vp.tags_touch()


def query(token):
    """Isolate one token's cohort exactly as the page says to: Branch Level 9
    (the axes and legend), then Add to current selection, then Tag contains,
    then Show Only Selected. The selection box is turned off afterwards, a
    viewer-side display choice: 10,000 yellow boxes would hide the cohort."""
    def act(L):
        w = L.win
        w._show_all()
        w._sel_cumulative.setChecked(False)
        w._sel_criterion.setCurrentText("Branch Level")
        w._update_sel_values()
        w._sel_value.setCurrentIndex(w._sel_value.findData(9))
        w._on_select_by()
        w._sel_cumulative.setChecked(True)
        w._sel_tag_keyword.setText(token)
        w._on_select_by_tag()
        w._isolate_selected()
        w._table.select_by_ids(set())
        L.vp.tags_touch()
    return act


def show_all(L):
    L.win._show_all()
    L.win._table.select_by_ids(set())
    L.vp.tags_touch()


def isolate_ids(ids):
    def act(L):
        w = L.win
        w._show_all()
        kids = {n.id for n in w.nodes if n.parent_id in ids}
        w._table.select_by_ids(set(ids) | kids)
        w._isolate_selected()
        w._table.select_by_ids(set())
        L.vp.tags_touch()
    return act


def panel(lines):
    return lambda L, u: "\n".join(lines) if u > 0.08 else None


CONDITION = text_card(
    "The condition column", [
        "values present:   1  2  3  4  5",
        "                  11 ... 19",
        "                  21 ... 29",
        "                  31 ... 39",
        "                  41 ... 49",
        "",
        "never present:    6  7  8  9  10, or any multiple of ten",
    ], color=AMBER, sub="558,837 auction records",
    footer="88% store a 1.1-4.9 grade times ten.  12% store the same grade as 1-5.")

SEASON = text_card(
    "A real result the picture won't show", [
        "                   Dec    Jan    Feb    Mar",
        "#UNDER share      35.9%                27.5%",
        "",
        "like-for-like residual:",
        "                  -0.31% -0.24% +0.23% +0.62%",
    ], color=CORAL, sub="tax-refund season lifts prices, then resets",
    footer="An 8-point change in density along a long axis is not something eyes read.")


def build() -> Lesson:
    ov = dict(target=FIELD, dist=560, az=232, el=24)
    shots = [
        Shot(title="Vehicle Sales: Raw Auction Field",
             heading="An Examples Gallery scene",
             say="Twenty thousand used car auction sales, sampled from more than "
                 "half a million. No aggregation: every sale is its own five part "
                 "glyph, about a hundred thousand nodes in all.",
             keys=[Key(0, az=220, el=28, dist=640, target=FIELD),
                   Key(1, az=ov["az"], el=ov["el"], dist=ov["dist"])],
             select=set(), events=[(0.0, bigger_labels)],
             state=dict(show_tags=True, show_tags_selected_only=True,
                        show_selection_box=True)),
        Shot(heading="Three axes",
             say="Three rails give the axes, coloured like GlyphViz's own transform "
                 "handles. Red X is the sale date, from December 2014 to July 2015. "
                 "Green Y is the model year. Blue Z, the height, is the odometer.",
             keys=[Key(0, az=ov["az"], el=ov["el"], dist=ov["dist"], target=FIELD),
                   Key(1, az=240, el=20, dist=600, target=(200, 96, 50))],
             callouts=[Callout(X_TITLE, "sale date", 0.25, 0.97, offset=(-40, 70),
                               ring=False, color=RED),
                       Callout(Y_TITLE, "model year", 0.45, 0.97, offset=(-60, -70),
                               ring=False, color=GREEN),
                       Callout(Z_TITLE, "odometer", 0.65, 0.97, offset=(-60, -60),
                               ring=False, color=BLUE)]),
        Shot(heading="Two selling seasons",
             say="Along the date axis, the field splits in two: the December to "
                 "March selling season, and May and June, with April nearly empty "
                 "between them. The rows inside are model years.",
             keys=[Key(0, az=240, el=20, dist=600, target=(200, 96, 50)),
                   Key(1, az=262, el=34, dist=470, target=(210, 110, 20))],
             callouts=[Callout(APRIL, "April: nearly empty", 0.4, 0.97, offset=(30, -190),
                               ring=False, color=AMBER)]),
        Shot(heading="The scene's own legend",
             say="The scene carries its own legend, parked beyond the start of the "
                 "time axis. It explains one sale, drawn fourteen times larger, and "
                 "what every part of it means.",
             keys=[Key(0, az=262, el=34, dist=470, target=(210, 110, 20)),
                   Key(0.6, az=270, el=8, dist=330, target=(-260, -20, 80)),
                   Key(1, az=272, el=8, dist=315)]),
        Shot(heading="The cube is the sale",
             say="The wire cube is the sale itself. Its colour is the car's paint, "
                 "and its size is the wholesale book value.",
             keys=[Key(0, az=272, el=8, dist=315, target=(-260, -20, 80)),
                   Key(0.5, az=300, el=18, dist=62, target=LEG_POS),
                   Key(1, az=306, el=18, dist=58)],
             callouts=[Callout(LEG_GLYPH, "one sale", 0.5, 0.97, offset=(-170, -70),
                               ring=False, color=CHALK)]),
        Shot(heading="Inside: the body class",
             say="Inside, the shape is the body class: a sedan is a sphere, an S U V "
                 "a cube, a truck a cylinder. Its colour is the interior trim.",
             keys=[Key(0, az=306, el=18, dist=58, target=LEG_POS),
                   Key(1, az=312, el=16, dist=52)],
             callouts=[Callout(LEG_INSIDE, "body class", 0.15, 0.97,
                               offset=(-170, 60), color=TEAL)]),
        Shot(heading="Three facets",
             say="On top, an octahedron is the condition grade. On the side, a "
                 "dodecahedron compares the price with book: blue under, white at it, "
                 "red over. And a gold tetrahedron means a manual gearbox.",
             keys=[Key(0, az=312, el=16, dist=52, target=LEG_POS),
                   Key(1, az=322, el=20, dist=50)],
             callouts=[Callout(LEG_Z, "condition", 0.05, 0.97, offset=(-150, -70),
                               color=AMBER),
                       Callout(LEG_X, "price vs book", 0.35, 0.97, offset=(140, -40),
                               color=CORAL),
                       Callout(LEG_Y, "gearbox", 0.7, 0.97, offset=(140, 60),
                               color=GOLD)]),
        Shot(heading="Every glyph carries tokens",
             say="Every part of every glyph also carries search tokens in its label. "
                 "Type one into Select By, Tag contains, and you select whole sales.",
             keys=[Key(0, az=322, el=20, dist=50, target=LEG_POS),
                   Key(1, az=272, el=6, dist=150, target=(-300, -20, 40))],
             readout=panel(["#COARSE  #FINE        condition scale",
                            "#RENTAL  #FLEET  #LEASE  #DEALER",
                            "#OVER  #ATBOOK  #UNDER   vs book",
                            "#LIGHT  #NORMAL  #HARD   miles/yr",
                            "#MANUAL                  gearbox"])),
        # ---- result 1
        Shot(heading="One column, two rulers",
             say="This scene was built first, with no finding in mind. The analysis "
                 "came after, and the first result is about the condition column. "
                 "It holds one to five, and eleven to forty nine, but never six to "
                 "ten. That's two scales in one column.",
             keys=[Key(0, az=272, el=6, dist=150, target=(-300, -20, 40)),
                   Key(1, az=250, el=20, dist=560, target=FIELD)],
             card=CONDITION),
        Shot(heading="#COARSE: really 4 of 5",
             say="The scene draws the column as published, so a car graded four out "
                 "of five on the short scale wears a tiny, dark badge. Isolate the "
                 "coarse cohort, and these supposed wrecks are ordinary cars: a "
                 "median model year of 2012, under forty thousand miles, spread "
                 "through the field like all the rest. The badge is wrong, not the car.",
             keys=[Key(0, az=250, el=20, dist=560, target=FIELD),
                   Key(1, az=262, el=10, dist=520, target=(210, 96, 40))],
             events=[(0.35, query("#COARSE"))],
             readout=lambda L, u: (None if u < 0.3 else
                                   "Select By > Branch Level 9\n"
                                   "+ Tag contains  #COARSE\n"
                                   "Show Only Selected   [I]")),
        Shot(heading="The same car, twice",
             say="Here are two of them: the same 2013 Lexus, the same mileage, the "
                 "same money. One is graded forty four. The other is graded four.",
             keys=[Key(0, az=262, el=10, dist=520, target=(210, 96, 40)),
                   Key(0.45, az=0, el=55, dist=12, target=PAIR_MID),
                   Key(1, az=10, el=50, dist=11)],
             events=[(0.3, isolate_ids({LEXUS_FINE, LEXUS_COARSE}))],
             callouts=[Callout(OCTA_FINE, "cond 44/49", 0.5, 0.97, offset=(-140, -60),
                               color=AMBER),
                       Callout(OCTA_COARSE, "cond 4/49", 0.6, 0.97, offset=(140, 60),
                               color=BLUE)],
             readout=lambda L, u: (None if u < 0.5 else
                                   "2013 Lexus RX 350  36k mi\n"
                                   "  sold $31.5k  book $30.2k  cond 44/49\n"
                                   "2013 Lexus RX 350  34k mi\n"
                                   "  sold $32.3k  book $31.1k  cond 4/49")),
        Shot(heading="It follows the seller",
             say="It isn't random. Seven big sellers, five of them rental fleets, "
                 "report nearly every car on the short scale. Pool the two, and "
                 "any analysis that uses condition is measuring a blend of two "
                 "rulers.",
             keys=[Key(0, az=10, el=50, dist=11, target=PAIR_MID),
                   Key(1, az=240, el=22, dist=560, target=FIELD)],
             events=[(0.25, show_all)]),
        # ---- result 2
        Shot(heading="Book value: sharp, then rough",
             say="The second result: the book value is a sharp estimate for low "
                 "mileage cars, and a rough guess for high mileage ones. Sales within "
                 "five percent of book form a low, dense slab.",
             keys=[Key(0, az=240, el=22, dist=560, target=FIELD),
                   Key(1, az=270, el=2, dist=500, target=(210, 96, 40))],
             events=[(0.3, query("#ATBOOK"))],
             readout=lambda L, u: None if u < 0.3 else "Tag contains  #ATBOOK"),
        Shot(heading="#UNDER climbs",
             say="Sales under book climb high, and so do sales over it. Height is "
                 "the odometer here, so the book value's growing error shows up as "
                 "height.",
             keys=[Key(0, az=270, el=2, dist=500, target=(210, 96, 40)),
                   Key(1, az=268, el=2, dist=490)],
             events=[(0.1, query("#UNDER"))],
             readout=lambda L, u: None if u < 0.1 else "Tag contains  #UNDER"),
        # ---- result 3
        Shot(heading="The one the picture won't show",
             say="The third result is real, but you can't see it. Prices lift through "
                 "tax refund season, so the share of sales under book falls from "
                 "thirty six percent in December to twenty seven and a half in March. "
                 "Isolate "
                 "the cohort, and your eyes can't read that change.",
             keys=[Key(0, az=268, el=2, dist=490, target=(210, 96, 40)),
                   Key(1, az=250, el=22, dist=560, target=FIELD)],
             card=SEASON),
        Shot(heading="Structure, not rates",
             say="That's worth knowing. Selection shows where a group sits and what "
                 "shape it takes. When the answer is a rate that changes slowly, go "
                 "back to the numbers.",
             keys=[Key(0, az=250, el=22, dist=560, target=FIELD),
                   Key(1, az=236, el=24, dist=560)],
             events=[(0.05, show_all)]),
        Shot(heading="Try it",
             say="Open it from the Examples Gallery, and try a token of your own. "
                 "Keep the hash: a bare OVER also matches every Land Rover.",
             keys=[Key(0, az=236, el=24, dist=560, target=FIELD),
                   Key(1, az=226, el=26, dist=600)]),
        Shot(heading="Recap",
             say="That's the Raw Auction Field.",
             keys=[Key(0, az=226, el=26, dist=600, target=FIELD),
                   Key(1, az=220, el=26, dist=600)],
             min_dur=7,
             summary=["One 5-part glyph per sale: 20,000 sales",
                      "Axes: sale date, model year, odometer",
                      "Tag tokens + Show Only Selected = a query",
                      "Two results you can see, one you can't",
                      "Examples Gallery: Vehicle Sales, Raw Auction Field"]),
    ]
    return Lesson(name="vehicle_auction_field", title="Raw Auction Field", nodes=[],
                  shots=shots, use_window=True, scene_csv=str(SCENE),
                  voice="af_heart")
