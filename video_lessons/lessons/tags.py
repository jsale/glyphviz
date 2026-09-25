"""Lesson: Tag labels — selection-scoped labels, show-all, T, pinning, size."""
from lessonkit import Callout, Key, Lesson, Shot, lerp, ease, TEAL, CORAL
from lessons._common import (G_CONE, G_CUBE, G_ICOSA, G_OCTA, G_SPHERE, G_TORUS,
                             G_CYL, T_SPHERE, glyph, world)

HUB = 2
SENSORS = [  # (id, label, geometry, colour, longitude)
    (3, "Temperature", G_CUBE, (255, 111, 97), 0),
    (4, "Humidity", G_SPHERE, (38, 198, 181), 60),
    (5, "Wind Speed", G_CONE, (167, 139, 250), 120),
    (6, "Rainfall", G_OCTA, (99, 140, 255), 180),
    (7, "Pressure", G_CYL, (255, 193, 7), 240),
    (8, "Sunlight", G_ICOSA, (240, 160, 220), 300),
]
PINNED = 6


def build() -> Lesson:
    nodes = [world(),
             glyph(HUB, 0, 0, scale=1.0, color=(63, 81, 181, 255), geometry=G_SPHERE,
                   topo=T_SPHERE, text="Weather Station")]
    for nid, label, geo, col, lon in SENSORS:
        nodes.append(glyph(nid, HUB, 1, pos=(lon, 0, 2.2), scale=0.5,
                           color=col, geometry=geo, text=label))

    def orbit(a0, a1, el=24, dist=11):
        return [Key(0, az=a0, el=el, dist=dist, target=(0, 0, 0)),
                Key(1, az=a1)]

    def pin(lesson, u):
        lesson.node(PINNED).show_text = 1 if u > 0.18 else 0

    def grow(lesson, u):
        size = round(lerp(11, 22, ease((u - 0.2) / 0.5)))
        lesson.node(1).tag_font_size = size

    def size_readout(lesson, u):
        return f"Tag Text Size: {lesson.node(1).tag_font_size} pt"

    shots = [
        Shot(title="Tag Labels", heading="Text attached to nodes",
             say="A tag is a text label on a node. Every node here has one, "
                 "but when a scene opens, none are showing.",
             keys=orbit(20, 55), select=set(),
             state=dict(show_tags=True, show_tags_selected_only=True)),
        Shot(heading="Labels follow the selection",
             say="Click a node, and its label appears. "
                 "Control click to add more.",
             keys=orbit(55, 80, dist=9.5), select={HUB},
             events=[(0.5, {"select": {HUB, 3}}), (0.7, {"select": {HUB, 3, 8}})],
             keycap=lambda u: (("Click", "select a node") if u < 0.45 else
                               ("Ctrl + Click", "add to the selection")),
             callouts=[Callout(HUB, "selected", 0.08, 0.45, offset=(-170, -120),
                               ring=False)]),
        Shot(heading="Show every label",
             say="To show them all, clear Show Tag Labels of Selected, "
                 "under Properties, Display.",
             keys=orbit(80, 125, el=30, dist=10), select=set(),
             events=[(0.4, {"show_tags_selected_only": False})],
             keycap="Properties  >  Display",
             keycap_note='clear  "Show Tag Labels of Selected"'),
        Shot(heading="The T key",
             say="T hides every label. T again brings them back.",
             keys=orbit(125, 150, el=30, dist=10),
             events=[(0.25, {"show_tags": False}), (0.65, {"show_tags": True})],
             keycap="T", keycap_note="toggle all labels"),
        Shot(heading="Pin one label",
             say="Tick Always Show Text to pin one label on, "
                 "even while the rest are hidden.",
             keys=orbit(150, 205, el=22, dist=9),
             state=dict(show_tags_selected_only=True), select=set(),
             animate=pin,
             keycap="Properties", keycap_note='tick  "Always Show Text"',
             callouts=[Callout(PINNED, "pinned", 0.22, 0.95, offset=(110, -80),
                               color=TEAL)]),
        Shot(heading="Text size",
             say="And Tag Text Size sets the size of every label in the scene.",
             keys=orbit(205, 250, el=28, dist=10.5),
             state=dict(show_tags_selected_only=False),
             animate=grow, readout=size_readout,
             keycap="Properties  >  Display", keycap_note="Tag Text Size"),
        Shot(heading="Recap",
             say="That's tag labels.",
             keys=orbit(250, 280, el=28, dist=10.5), min_dur=5,
             summary=["Click / Ctrl+Click: labels of the selection",
                      "Display: clear 'of Selected' to show all",
                      "T: hide or show every label",
                      "Always Show Text: pin one label"]),
    ]
    return Lesson(name="tags", title="Tag Labels", nodes=nodes, shots=shots,
                  voice="af_heart")
