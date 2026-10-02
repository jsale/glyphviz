"""
plan_trace — turn Jeff's hand-drawn floor plan into wall, room and roof data.

The school is not modelled from guessed dimensions. Its walls are the ink of
`drawings/banyan_floor_plan.png` itself: every dark stroke long enough to be a
wall is kept, thickened, smoothed, and its outline becomes the faces of a wall
mesh. So the curve of every room, the width of every doorway and the hook of
the courtyard entrance are exactly what was drawn.

What the drawing does not say, this module decides, and each decision is a
named table below rather than a buried constant:

* **Scale.** The Main Hall is drawn about 300 px across. At 0.06 m/px that is
  an 18 m round hall, which is the size a dining room for several families
  needs, and it makes the whole school 57 m x 33 m -- which also matches how
  big the school is drawn on the community plan (see build_banyan_tree.py).
* **Which ink is not wall.** Labels and their underlines are dropped by size;
  the three stair symbols are cut out (their gaps become the doorways the
  stairs pass through) and replaced by real stair meshes.
* **Rooms.** The enclosed spaces between walls, found by flood fill after
  temporarily closing the doorways, each named by the label Jeff wrote in it.

Coordinates: everything here works in PLAN PIXELS (x right, y down), and
`to_world` converts to scene metres (x east, y north, origin at the hearth).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

HERE = Path(__file__).resolve().parent
PLAN_PNG = HERE / "drawings" / "banyan_floor_plan.png"

M_PER_PX = 0.06                 # 300 px Main Hall -> 18 m
HEARTH_PX = (208.0, 175.0)      # the scene origin: the community's hearth


def to_world(px, py):
    """Plan pixels -> scene metres (east, north). Works on scalars or arrays."""
    return ((np.asarray(px, float) - HEARTH_PX[0]) * M_PER_PX,
            -(np.asarray(py, float) - HEARTH_PX[1]) * M_PER_PX)


def to_plan(x, y):
    return (np.asarray(x, float) / M_PER_PX + HEARTH_PX[0],
            -np.asarray(y, float) / M_PER_PX + HEARTH_PX[1])


# Stair symbols, as plan-pixel polygons. Cutting them out of the wall ink
# leaves the gap the stair passes through.
STAIRS = {
    'rear':  [(224, 64), (282, 46), (300, 80), (282, 104), (226, 76)],
    'west':  [(88, 208), (124, 206), (126, 266), (94, 268)],
    'east':  [(731, 90), (770, 90), (770, 160), (731, 160)],
}

# Openings closed ONLY while finding rooms, so the flood fill doesn't leak out
# of a doorway into the outdoors. They are never built.
SEALS = [
    [(598, 446), (690, 452)],          # courtyard entrance, between the hooks
    [(290, 95), (300, 60), (356, 44)],  # rear entrance
    [(888, 138), (912, 150), (895, 178)],   # library / underwater junction
    [(514, 0), (498, 28), (482, 54)],  # storage, dashed (west)
    [(624, 0), (650, 40), (674, 74)],  # storage, dashed (east)
    [(500, 2), (640, 2)],              # storage, open north side
]

# Every room, by a point inside it (near where its label is written).
ROOMS = {
    'main_hall':   (190, 180),
    'indoor_rec':  (420, 260),
    'lab':         (640, 190),
    'lobby':       (645, 272),
    'courtyard':   (640, 375),
    'admin':       (510, 372),
    'library':     (820, 260),
    'rest_west':   (412, 120),
    'rest_east':   (700, 80),
    'underwater':  (860, 120),
    'storage':     (560, 40),
    'gallery':     (620, 135),
}

ROOM_TITLES = {
    'main_hall':  "Main Hall — upper level kitchen & dining, lower level "
                  "communal gatherings around the hearth",
    'indoor_rec': "Indoor Recreation",
    'lab':        "Lab — science benches and computers",
    'lobby':      "Lobby / Foyer — a tree-of-life mosaic in the floor",
    'courtyard':  "Entrance Courtyard — open to the sky",
    'admin':      "Admin Office",
    'library':    "Study, Museum, Library",
    'rest_west':  "Rest Room",
    'rest_east':  "Rest Room",
    'underwater': "Underwater Observation Area — windows into the pond",
    'storage':    "Storage",
    'gallery':    "North gallery — the children's cubbies",
}

OPEN_TO_SKY = {'courtyard'}


def _poly_mask(shape, poly, width=0):
    img = Image.new('L', (shape[1], shape[0]), 0)
    d = ImageDraw.Draw(img)
    if width:
        d.line([tuple(p) for p in poly], fill=255, width=width)
    else:
        d.polygon([tuple(p) for p in poly], fill=255)
    return np.asarray(img) > 0


def _disk(r):
    y, x = np.mgrid[-r:r + 1, -r:r + 1]
    return x * x + y * y <= r * r


@dataclass
class Plan:
    walls: np.ndarray          # bool, the built wall ink (thickened)
    building: np.ndarray       # bool, walls + every room = the roofed outline
    rooms: np.ndarray          # int, 0 = outside, k = index into room_names
    room_names: list
    stairs: dict

    @property
    def shape(self):
        return self.walls.shape


def trace(debug_png=None) -> Plan:
    g = np.asarray(Image.open(PLAN_PNG).convert('L')).astype(float) / 255.0
    dark = g < 0.55
    lab, n = ndi.label(dark, structure=np.ones((3, 3)))
    keep = np.zeros(n + 1, bool)
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        h = sl[0].stop - sl[0].start
        w = sl[1].stop - sl[1].start
        # Walls are long; text is small; an underline is long but flat. The
        # title ("Top View") sits below y=535.
        if max(h, w) > 60 and min(h, w) > 16 and sl[0].start < 535:
            keep[i] = True
    ink = keep[lab]
    for poly in STAIRS.values():
        ink &= ~_poly_mask(ink.shape, poly)

    # Double-line walls (the drawing's way of showing a thick wall with
    # window gaps) merge into one solid wall at a 3 px dilation, ~0.4 m.
    walls = ndi.binary_dilation(ink, _disk(3))

    sealed = walls.copy()
    for line in SEALS:
        sealed |= _poly_mask(walls.shape, line, width=9)
    for poly in STAIRS.values():
        sealed |= _poly_mask(walls.shape, poly)
    sealed = ndi.binary_dilation(sealed, _disk(5))     # close small doorways

    space, m = ndi.label(~sealed)
    border = set(np.unique(np.concatenate([space[0], space[-1],
                                           space[:, 0], space[:, -1]])))
    # Seeds that share one flood-fill component (rooms joined by a wide
    # doorway, like Lab / Lobby / Courtyard) split it by nearest seed.
    names, seeds = [], []
    for key, (x, y) in ROOMS.items():
        k = space[int(y), int(x)]
        if k == 0 or k in border:
            print(f"  plan_trace: room '{key}' is not enclosed (k={k})")
            continue
        names.append(key)
        seeds.append((x, y, k))
    yy, xx = np.mgrid[0:walls.shape[0], 0:walls.shape[1]]
    best = np.full(walls.shape, np.inf)
    rooms = np.zeros(walls.shape, int)
    for idx, (x, y, k) in enumerate(seeds, 1):
        d = np.hypot(xx - x, yy - y)
        win = (space == k) & (d < best)
        rooms[win] = idx
        best[win] = d[win]

    # Give the closed doorways back to the rooms on either side of them: grow
    # each room into the sealed-but-not-wall band, nearest room wins.
    inside = rooms > 0
    _, (iy, ix) = ndi.distance_transform_edt(~inside, return_indices=True)
    grown = rooms[iy, ix]
    reach = ndi.binary_dilation(inside, _disk(9)) & ~walls
    rooms = np.where(reach, grown, 0)

    building = ndi.binary_closing(rooms > 0, _disk(6)) | (
        ndi.binary_dilation(rooms > 0, _disk(6)) & walls)
    building = ndi.binary_fill_holes(building)

    plan = Plan(walls=walls, building=building, rooms=rooms,
                room_names=names, stairs=STAIRS)
    if debug_png:
        _debug(plan, g, debug_png)
    return plan


def _debug(plan, g, path):
    rng = np.random.default_rng(3)
    pal = rng.integers(90, 240, (len(plan.room_names) + 1, 3))
    rgb = np.full(plan.shape + (3,), 255, np.uint8)
    rgb[plan.building] = (235, 235, 210)
    for k in range(1, len(plan.room_names) + 1):
        rgb[plan.rooms == k] = pal[k]
    rgb[plan.walls] = (30, 30, 30)
    rgb[g < 0.55] = (rgb[g < 0.55] * 0.5).astype(np.uint8)
    img = Image.fromarray(rgb)
    d = ImageDraw.Draw(img)
    for key, (x, y) in ROOMS.items():
        d.text((x - 20, y - 5), key, fill=(200, 0, 0))
    img.save(path)
