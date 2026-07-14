"""
Built-in color palettes + resolution for Node.palette_id/color_index -- no
OpenGL/Qt dependency, like geometry_data.py/topology.py, so this is safe to
import from anything.

ANTz's model: a node's rendered color_r/g/b is a literal RGB value; palette_id
+ color_index are a convenience that RESOLVE into that literal RGB only when
the user steps through them with the =/-/Alt+=/Alt+- keys (see
glyphviz_gl.main_window's _cycle_selected_color_index/_cycle_selected_palette).
color_a (alpha) is never touched by palette resolution.

Palette IDs and the literal 20-color table below match ANTz's own documented
defaults (gaiaviz-skill/references/structure/Node-Field-Descriptions.md,
"np_palette_id"/"np_color_id" sections) -- palette 0, index 0 ("Caribbean
current") is ANTz's real documented default. IDs 2-25 are gradients (0-127
index range) generated from a couple of endpoint colors rather than hand-typed
as 128 RGB triples each; only the rainbow heatmap needs a non-linear (HSV)
sweep.
"""
import colorsys

PALETTE_20              = 0
PALETTE_20_INV          = 1
PALETTE_RAINBOW         = 2
PALETTE_RAINBOW_INV     = 3
PALETTE_BLUE_GREEN      = 4
PALETTE_BLUE_GREEN_INV  = 5
PALETTE_GREEN_RED       = 6
PALETTE_GREEN_RED_INV   = 7
PALETTE_BLUE_RED        = 8
PALETTE_BLUE_RED_INV    = 9
PALETTE_PURPLE_YELLOW     = 10
PALETTE_PURPLE_YELLOW_INV = 11
PALETTE_BLACK_RED        = 12
PALETTE_BLACK_RED_INV    = 13
PALETTE_BLACK_GREEN      = 14
PALETTE_BLACK_GREEN_INV  = 15
PALETTE_BLACK_BLUE       = 16
PALETTE_BLACK_BLUE_INV   = 17
PALETTE_WHITE_RED        = 18
PALETTE_WHITE_RED_INV    = 19
PALETTE_WHITE_GREEN      = 20
PALETTE_WHITE_GREEN_INV  = 21
PALETTE_WHITE_BLUE       = 22
PALETTE_WHITE_BLUE_INV   = 23
PALETTE_GREYSCALE        = 24
PALETTE_GREYSCALE_INV    = 25

PALETTE_COUNT   = 26
PALETTE_DEFAULT = PALETTE_20

PALETTE_NAMES = {
    PALETTE_20:               "20 Distinct Colors",
    PALETTE_20_INV:           "20 Distinct Colors (Inverted)",
    PALETTE_RAINBOW:          "Rainbow Heatmap",
    PALETTE_RAINBOW_INV:      "Rainbow Heatmap (Inverted)",
    PALETTE_BLUE_GREEN:       "Blue → Green",
    PALETTE_BLUE_GREEN_INV:   "Blue → Green (Inverted)",
    PALETTE_GREEN_RED:        "Green → Red",
    PALETTE_GREEN_RED_INV:    "Green → Red (Inverted)",
    PALETTE_BLUE_RED:         "Blue → Red",
    PALETTE_BLUE_RED_INV:     "Blue → Red (Inverted)",
    PALETTE_PURPLE_YELLOW:     "Purple → Yellow",
    PALETTE_PURPLE_YELLOW_INV: "Purple → Yellow (Inverted)",
    PALETTE_BLACK_RED:        "Black → Red",
    PALETTE_BLACK_RED_INV:    "Black → Red (Inverted)",
    PALETTE_BLACK_GREEN:      "Black → Green",
    PALETTE_BLACK_GREEN_INV:  "Black → Green (Inverted)",
    PALETTE_BLACK_BLUE:       "Black → Blue",
    PALETTE_BLACK_BLUE_INV:   "Black → Blue (Inverted)",
    PALETTE_WHITE_RED:        "White → Red",
    PALETTE_WHITE_RED_INV:    "White → Red (Inverted)",
    PALETTE_WHITE_GREEN:      "White → Green",
    PALETTE_WHITE_GREEN_INV:  "White → Green (Inverted)",
    PALETTE_WHITE_BLUE:       "White → Blue",
    PALETTE_WHITE_BLUE_INV:   "White → Blue (Inverted)",
    PALETTE_GREYSCALE:        "Greyscale",
    PALETTE_GREYSCALE_INV:    "Greyscale (Inverted)",
}

# Literal 20-color table (palette 0), in id order -- id 0 is ANTz's documented
# default. Names are for tooltips only, not written to CSV.
_PALETTE_20_RGB = [
    (50, 101, 101),    # 0  Caribbean current (default)
    (0, 255, 0),       # 1  Green
    (255, 0, 0),       # 2  Red
    (0, 0, 255),       # 3  Blue
    (255, 255, 0),     # 4  Yellow
    (152, 0, 255),     # 5  Electric violet
    (255, 168, 0),     # 6  Orange
    (0, 255, 255),     # 7  Cyan
    (255, 0, 255),     # 8  Fuchsia
    (0, 153, 0),       # 9  Forest green
    (185, 153, 102),   # 10 Lion (gold)
    (255, 180, 255),   # 11 Mauve
    (0, 152, 255),     # 12 Dodgers blue
    (185, 255, 0),     # 13 Lime
    (152, 0, 0),       # 14 Penn red
    (127, 127, 127),   # 15 Gray
    (127, 127, 255),   # 16 Tropical indigo
    (197, 82, 0),      # 17 Tawny
    (0, 0, 0),         # 18 Black
    (255, 255, 255),   # 19 White
]

_PALETTE_20_NAMES = [
    "Caribbean current", "Green", "Red", "Blue", "Yellow", "Electric violet",
    "Orange", "Cyan", "Fuchsia", "Forest green", "Lion", "Mauve",
    "Dodgers blue", "Lime", "Penn red", "Gray", "Tropical indigo", "Tawny",
    "Black", "White",
]

# Non-inverted (even) gradient palette id -> (start_rgb, end_rgb) endpoints,
# linearly interpolated across color_index 0-127. Rainbow is handled
# separately (HSV sweep, not a 2-color lerp).
_GRADIENT_ENDPOINTS = {
    PALETTE_BLUE_GREEN:      ((0, 0, 255), (0, 255, 0)),
    PALETTE_GREEN_RED:       ((0, 255, 0), (255, 0, 0)),
    PALETTE_BLUE_RED:        ((0, 0, 255), (255, 0, 0)),
    PALETTE_PURPLE_YELLOW:   ((152, 0, 255), (255, 255, 0)),
    PALETTE_BLACK_RED:       ((0, 0, 0), (255, 0, 0)),
    PALETTE_BLACK_GREEN:     ((0, 0, 0), (0, 255, 0)),
    PALETTE_BLACK_BLUE:      ((0, 0, 0), (0, 0, 255)),
    PALETTE_WHITE_RED:       ((255, 255, 255), (255, 0, 0)),
    PALETTE_WHITE_GREEN:     ((255, 255, 255), (0, 255, 0)),
    PALETTE_WHITE_BLUE:      ((255, 255, 255), (0, 0, 255)),
    PALETTE_GREYSCALE:       ((0, 0, 0), (255, 255, 255)),
}


def _lerp_rgb(c0, c1, t):
    return tuple(round(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))


def _rainbow_heatmap(t):
    r, g, b = colorsys.hsv_to_rgb(t, 1.0, 1.0)
    return (round(r * 255), round(g * 255), round(b * 255))


def _invert(rgb):
    return tuple(255 - c for c in rgb)


def palette_index_count(palette_id: int) -> int:
    """Number of valid color_index values for a palette: 20 for the distinct-
    color palettes (0/1), 128 for every gradient (2-25). Sizes the Inspector's
    Color Index spinner and the =/- cycle keys' wraparound."""
    return 20 if palette_id in (PALETTE_20, PALETTE_20_INV) else 128


def resolve_palette_color(palette_id: int, color_index: int) -> tuple[int, int, int]:
    """(palette_id, color_index) -> literal (r, g, b), per ANTz's documented
    palette table. color_index wraps to the palette's own valid range."""
    if palette_id in (PALETTE_20, PALETTE_20_INV):
        rgb = _PALETTE_20_RGB[color_index % 20]
    else:
        base_id = palette_id - (palette_id % 2)
        t = (color_index % 128) / 127.0
        if base_id == PALETTE_RAINBOW:
            rgb = _rainbow_heatmap(t)
        else:
            rgb = _lerp_rgb(*_GRADIENT_ENDPOINTS[base_id], t)
    return _invert(rgb) if palette_id % 2 == 1 else rgb
