"""
school — the Banyan Tree school building, from the traced floor plan and the
elevation, with its furnishings.

Read the elevation as the south front: a stone tower at the west end rising
to an observation deck and a telescope, a sculpted roof line, and a run of
oval arches labelled "Walkways". On the plan those arches are the scalloped
arcs that hang off the south side of the building, so each arc becomes a
low fieldstone garden wall with a plaster ribbon soaring over it -- the oval
the elevation draws -- and the walkways pass beneath.

The Main Hall's two levels ("Upper Level: Kitchen & Dining", "Lower Level:
Communal gatherings, Meditations, Relaxation") are read as one round room
with a sunken, stepped gathering floor to the south of the hearth, so the
hearth looks over both: dinner on the upper level, story time on the steps.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage as ndi

import meshkit as mk
import furniture as fu
import organic as og
import plan_trace as pt

GRID = og.Grid(m=pt.M_PER_PX, origin=(-pt.HEARTH_PX[0] * pt.M_PER_PX,
                                      pt.HEARTH_PX[1] * pt.M_PER_PX))

MH_CENTER = tuple(float(v) for v in pt.to_world(192, 177))   # Main Hall
LIB_CENTER = tuple(float(v) for v in pt.to_world(830, 270))
TOWER = (-13.9, 0.6)                 # beside the Nook, as the elevation puts it
WALL_FOOT = -1.6                     # walls run below grade (the floor hides it)

# the Main Hall's lower level: a stepped ellipse south of the hearth
PIT_C, PIT_RX, PIT_RY = (0.7, -4.4), 5.4, 2.8
PIT_STEPS = [(0.0, 0.03), (0.45, -0.30), (0.90, -0.63), (1.35, -0.96)]


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _r(x, y, c):
    return np.hypot(np.asarray(x) - c[0], np.asarray(y) - c[1])


def mh_weight(x, y):
    return 1.0 - smoothstep(10.6, 11.8, _r(x, y, MH_CENTER))


def lib_weight(x, y):
    return 1.0 - smoothstep(7.0, 8.5, _r(x, y, LIB_CENTER))


def wall_top(x, y):
    """Wall height: 3.5 m, the Main Hall 6.4 m (tall enough for its oval
    clerestory windows), the library a little higher, and a gentle undulation
    along every top edge -- a Hubbell wall is shaped, not cut level."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    return (3.5 + 2.9 * mh_weight(x, y) + 0.5 * lib_weight(x, y)
            + 0.22 * np.sin(0.45 * x + 0.8) * np.cos(0.38 * y))


def garden_top(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    return 0.95 + 0.12 * np.sin(0.9 * x) * np.cos(0.7 * y)


def in_pit(x, y, inset=0.0):
    return (((np.asarray(x) - PIT_C[0]) / (PIT_RX - inset)) ** 2
            + ((np.asarray(y) - PIT_C[1]) / (PIT_RY - inset)) ** 2) <= 1.0


class School:
    def __init__(self, plan: pt.Plan):
        self.plan = plan
        p = plan
        rooms_any = p.rooms > 0
        near_rooms = ndi.binary_dilation(rooms_any, iterations=12)
        self.bwalls = p.walls & near_rooms             # building walls
        self.gwalls = p.walls & ~near_rooms            # free-standing garden walls
        # the underwater observation wall is glass
        glass_box = np.zeros_like(p.walls)
        glass_box[52:168, 822:916] = True
        self.glass = self.bwalls & glass_box
        self.bwalls = self.bwalls & ~self.glass
        self.room_ids = {n: k for k, n in enumerate(p.room_names, 1)}

    # ---- helpers ---------------------------------------------------------

    def room_mask(self, name):
        return self.plan.rooms == self.room_ids[name]

    def clearance(self, name):
        """Distance (m) from each pixel to the nearest non-room pixel."""
        return ndi.distance_transform_edt(self.room_mask(name)) * pt.M_PER_PX

    def fits(self, name, x, y, need):
        c, r = pt.to_plan(x, y)
        cl = self.clearance(name)
        ci, ri = int(round(float(c))), int(round(float(r)))
        if not (0 <= ri < cl.shape[0] and 0 <= ci < cl.shape[1]):
            return False
        return cl[ri, ci] >= need

    def wall_point(self, name, origin, angle_deg, back_off=0.5, step=0.05):
        """March from *origin* at *angle* to the room's edge; return the point
        *back_off* metres short of it (for furniture set against a wall)."""
        m = self.room_mask(name)
        a = math.radians(angle_deg)
        d = 0.0
        while d < 40:
            x = origin[0] + math.cos(a) * d
            y = origin[1] + math.sin(a) * d
            c, r = pt.to_plan(x, y)
            ci, ri = int(c), int(r)
            if not (0 <= ri < m.shape[0] and 0 <= ci < m.shape[1]) or not m[ri, ci]:
                break
            d += step
        d = max(d - back_off, 0.0)
        return (origin[0] + math.cos(a) * d, origin[1] + math.sin(a) * d)

    # ---- architecture ----------------------------------------------------

    def build(self, kit, tex):
        p = self.plan
        print("  school: walls")
        walls = og.walls_from_mask(self.bwalls, GRID, WALL_FOOT, wall_top,
                                   uv_scale=0.25, name="walls")
        # wall tops (mostly under the roof, but seen through it)
        walls.extend(og.slab_from_mask(self.bwalls, GRID, wall_top, cell=2,
                                       uv_fn=lambda x, y: (x * 0.25, 0.43)))
        self._uv_v_scale(walls, 0.5)        # texture tile is 4 m wide x 8 m tall
        kit.world("school_walls.obj", walls, color=(255, 252, 245),
                  texture=tex['wall'],
                  text="Walls traced from the floor plan's ink — lime plaster "
                       "on a fieldstone base, redwood-framed windows")

        garden = og.walls_from_mask(self.gwalls, GRID, -0.3, garden_top,
                                    uv_scale=0.5, name="garden_walls")
        garden.extend(og.slab_from_mask(self.gwalls, GRID, garden_top, cell=2,
                                        uv_fn=lambda x, y: (x * 0.5, y * 0.5)))
        kit.world("school_garden_walls.obj", garden, color=(250, 245, 238),
                  texture=tex['stone'],
                  text="Fieldstone garden walls — the plan's free-standing arcs")

        glass = og.walls_from_mask(self.glass, GRID, -1.4, wall_top,
                                   uv_scale=0.25, name="glass")
        kit.world("school_glass.obj", glass, color=(150, 205, 220), alpha=110,
                  text="Underwater Observation Area — glass wall looking "
                       "into the pond")

        print("  school: floor")
        floor_mask = ((p.rooms > 0) | p.walls) & ~in_pit(*GRID.world(
            *np.meshgrid(np.arange(p.shape[1]), np.arange(p.shape[0]))), inset=-0.02)
        H, W = p.shape
        floor = og.slab_from_mask(
            floor_mask, GRID, lambda x, y: np.full(np.shape(x), 0.03), cell=4,
            uv_fn=lambda x, y: ((pt.to_plan(x, y)[0]) / W,
                                1.0 - (pt.to_plan(x, y)[1]) / H))
        kit.world("school_floor.obj", floor, color=(255, 255, 255),
                  texture=tex['floor'],
                  text="Floors, painted room by room: terracotta, maple, "
                       "lab checker, a mosaic, flagstone, oak")
        kit.world("school_lower_level.obj", self._pit(), color=(240, 225, 205),
                  texture=tex['planks'],
                  text="Main Hall lower level — stepped seating for "
                       "communal gatherings, meditations, relaxation")

        print("  school: roof")
        kit.world("school_roof.obj", self._roof(), color=(255, 248, 236),
                  texture=tex['roof'], alpha=105,
                  text="Main Hall & School", pin=True)

        print("  school: arches, tower, hearth, stairs")
        kit.world("school_arches.obj", self._arches(), color=(255, 250, 240),
                  texture=tex['roof'],
                  text="Walkway arches — the ovals of the elevation, swept "
                       "over the plan's scalloped arcs")
        self._tower(kit, tex)
        self._hearth(kit, tex)
        self._stairs(kit, tex)

    @staticmethod
    def _uv_v_scale(mesh, k):
        mesh._uv = [(u, v * k) for (u, v) in mesh._uv]

    def _pit(self):
        """Elliptical stepped bowl, each tread 0.45 m and riser 0.33 m."""
        m = mk.Mesh("pit")
        n = 72
        a = np.linspace(0, 2 * math.pi, n, endpoint=False)
        rings = []
        for inset, z in PIT_STEPS:
            ring = np.stack([PIT_C[0] + (PIT_RX - inset) * np.cos(a),
                             PIT_C[1] + (PIT_RY - inset) * np.sin(a)], 1)
            rings.append((ring, z))
        secs = []
        for k, (ring, z) in enumerate(rings):
            if k:
                secs.append(np.column_stack([ring, np.full(n, rings[k - 1][1])]))
            secs.append(np.column_stack([ring, np.full(n, z)]))
        # treads face up and risers face the middle, as lofted
        body = mk.loft(secs, closed=True, cap_end=True)
        body._uv = [(x * 0.5, y * 0.5) for (x, y, _z) in body._v]
        m.extend(body)
        return m

    def _roof(self):
        p = self.plan
        courtyard = self.room_mask('courtyard')
        roof_mask = p.building & ~ndi.binary_dilation(courtyard, iterations=2)
        interior = roof_mask & ~p.walls
        dist_field = ndi.distance_transform_edt(interior) * pt.M_PER_PX

        def z_fn(x, y):
            c, r = pt.to_plan(x, y)
            dd = ndi.map_coordinates(dist_field, [r, c], order=1, mode='nearest')
            dome = 1.0 - smoothstep(4.0, 10.5, _r(x, y, MH_CENTER))
            amp = 1.4 + 2.2 * dome + 0.7 * lib_weight(x, y)
            L = 2.0 + 1.5 * dome
            return wall_top(x, y) + 0.12 + amp * (1.0 - np.exp(-dd / L))

        return og.slab_from_mask(roof_mask, GRID, z_fn, cell=4,
                                 uv_fn=lambda x, y: (x * 0.25, y * 0.25),
                                 name="roof")

    def _arches(self):
        """A plaster ribbon arching over each long free-standing garden arc."""
        m = mk.Mesh("arches")
        lab, n = ndi.label(self.gwalls)
        for k in range(1, n + 1):
            blob = lab == k
            path = og.centerline(blob, step=5.0)
            if path is None or len(path) < 6:
                continue
            path = og.smooth_path(path, 4)
            x, y = GRID.world(path[:, 0], path[:, 1])
            xy = og.resample(np.stack([x, y], 1), 0.35)
            L = float(np.sum(np.hypot(*np.diff(xy, axis=0).T)))
            # only curve-like blobs (a thin wall's pixel count ~ length x width)
            if L < 6.0 or blob.sum() * pt.M_PER_PX ** 2 > L * 0.75:
                continue
            s = np.linspace(0, 1, len(xy))
            A = min(4.6, 0.30 * L)
            z_lo = A * np.sin(np.pi * s) ** 0.85 + garden_top(xy[:, 0], xy[:, 1]) * (
                1 - np.sin(np.pi * s))
            z_hi = z_lo + 0.55 + 0.25 * np.sin(np.pi * s)
            m.extend(og.ribbon(xy, z_lo, z_hi, thickness=0.28))
        return m

    def _tower(self, kit, tex):
        """Stone tower: banyan-like root buttresses at the foot, a corbelled
        observation deck at 12 m, a domed observatory with its telescope."""
        tx, ty = TOWER
        rng = np.random.default_rng(9)
        prof = [(3.3, -0.5), (3.1, 0.6), (2.75, 2.0), (2.5, 4.5), (2.42, 7.5),
                (2.5, 9.8), (2.8, 11.2), (3.35, 11.95)]
        zs = np.linspace(prof[0][1], prof[-1][1], 34)
        rs = np.interp(zs, [q[1] for q in prof], [q[0] for q in prof])
        n = 40
        secs, uvv = [], []
        for z, r in zip(zs, rs):
            ring = []
            for j in range(n):
                th = 2 * math.pi * j / n
                root = 0.55 * max(0.0, math.cos(5 * th + 0.4)) ** 3 * math.exp(-max(z, 0) / 1.6)
                bump = 0.05 * math.sin(7 * th + z * 1.3) + 0.04 * rng.normal()
                rr = r * (1 + root) + bump
                ring.append((tx + rr * math.cos(th), ty + rr * math.sin(th), z))
            secs.append(ring)
        body = mk.loft(secs, closed=True, cap_end=True, uv_u_repeat=4.0)
        body._uv = [(u, v * (zs[-1] - zs[0]) / 3.0) for (u, v) in body._uv]
        kit.world("tower_stone.obj", body, color=(255, 250, 244), texture=tex['stone'],
                  text="Observatory tower", pin=True)

        deck = mk.revolve([(0.0, 11.95), (4.2, 11.95), (4.2, 12.25), (0.0, 12.25)],
                          segments=40)
        deck._uv = [(x * 0.5, y * 0.5) for (x, y, _z) in deck._v]
        deck.extend(mk.revolve([(1.75, 12.25), (1.85, 12.25), (1.85, 14.6),
                                (1.75, 14.6)], segments=32))
        kit.world("tower_deck.obj", deck.transform(mk.translate(tx, ty, 0)),
                  color=(235, 215, 195), texture=tex['planks'],
                  text="Observation Deck, 12 m up. The tower is fieldstone and "
                       "mortar, buttressed at the foot like a banyan's roots")

        bal = mk.Mesh("balustrade")
        for k in range(44):
            a = 2 * math.pi * k / 44
            bal.extend(fu.blob(0.2, 0.2, 0.24, seg=(7, 5)),
                       mk.translate(tx + 3.95 * math.cos(a), ty + 3.95 * math.sin(a), 12.25))
        ring = [(tx + 3.95 * math.cos(a), ty + 3.95 * math.sin(a), 12.95)
                for a in np.linspace(0, 2 * math.pi, 61)]
        bal.extend(mk.tube(ring, 0.07, segments=6, cap_start=False, cap_end=False))
        kit.world("tower_balustrade.obj", bal, color=(205, 190, 165),
                  text="Balustrade of rounded stones, as drawn in the elevation")

        dome = mk.Mesh("dome")
        dome.extend(mk.revolve([(1.95, 14.55), (1.95, 14.75)] + [
            (1.95 * math.cos(t), 14.75 + 1.95 * math.sin(t))
            for t in np.linspace(0.05, math.pi / 2, 10)], segments=36))
        kit.world("tower_dome.obj", dome.transform(mk.translate(tx, ty, 0)),
                  color=(110, 160, 140),
                  text="Observatory dome — weathered copper")
        scope = mk.revolve([(0.0, -1.3), (0.2, -1.3), (0.2, 1.1), (0.24, 1.2),
                            (0.24, 1.45), (0.0, 1.45)], segments=16)
        kit.world("tower_telescope.obj",
                  scope.transform(mk.compose(mk.rot_y(-38), mk.rot_z(25),
                                             mk.translate(tx + 0.5, ty + 0.3, 16.0))),
                  color=(235, 235, 240), text="Telescope")

    def _hearth(self, kit, tex):
        ring = mk.revolve([(0.55, 0.0), (1.3, 0.0), (1.32, 0.42), (1.15, 0.55),
                           (0.75, 0.55), (0.55, 0.42), (0.55, 0.0)], segments=32)
        ring._uv = [(math.atan2(y, x) * 1.2, z * 2 + math.hypot(x, y))
                    for (x, y, z) in ring._v]
        kit.world("hearth_stone.obj", ring, color=(255, 250, 242), texture=tex['stone'],
                  text="Hearth — the centre of the Main Hall, and the origin "
                       "of this whole scene (0, 0)")
        fire = mk.Mesh("fire")
        rng = np.random.default_rng(3)
        for k in range(6):
            a = k * 2 * math.pi / 6 + rng.uniform(-0.3, 0.3)
            r = rng.uniform(0.05, 0.25)
            h = rng.uniform(0.45, 0.85)
            cone = mk.revolve([(0.0, 0.0), (0.13, 0.0), (0.0, h)], segments=8)
            fire.extend(cone, mk.translate(math.cos(a) * r, math.sin(a) * r, 0.25))
        for k in range(3):
            a = k * math.pi / 3
            fire.extend(mk.tube([(-0.4 * math.cos(a), -0.4 * math.sin(a), 0.22),
                                 (0.4 * math.cos(a), 0.4 * math.sin(a), 0.22)],
                                0.06, segments=6))
        kit.world("hearth_fire.obj", fire, color=(255, 150, 40), text="Fire")
        hood = mk.revolve([(1.5, 3.2), (1.45, 3.35), (0.36, 4.5), (0.32, 4.5),
                           (0.32, 11.6), (0.42, 11.8), (0.0, 11.8)], segments=24)
        kit.world("hearth_hood.obj", hood, color=(196, 120, 66),
                  text="Copper hood and chimney, up through the dome. The roof is "
                       "drawn translucent so the rooms show: select it and set "
                       "alpha 255 for the solid building")

    def _stairs(self, kit, tex):
        flights = mk.Mesh("stairs")
        for key, (p0, p1, w) in {
            # (start, end, width) in plan px; they climb toward the roof deck
            'west': ((106, 266), (106, 210), 26),
            'rear': ((232, 72), (290, 52), 26),
            'east': ((750, 156), (750, 96), 30),
        }.items():
            a = np.array(pt.to_world(*p0)).ravel()
            b = np.array(pt.to_world(*p1)).ravel()
            flights.extend(fu.stair_flight(a, b, w * pt.M_PER_PX, 0.0, 1.25))
        kit.world("school_stairs.obj", flights, color=(225, 205, 180),
                  texture=tex['planks'],
                  text="Stairs, where the plan draws them — up to the roof "
                       "terraces and the tower")

    # ---- furnishings -----------------------------------------------------

    def furnish(self, kit, tex, pieces):
        """Minimal but effective: enough in each room to say what it is for."""
        P = pieces
        wood = (168, 118, 74)
        dark = (110, 72, 44)
        birch = (214, 186, 140)

        # Main Hall: kitchen against the north wall, dining on the upper level
        mh = MH_CENTER
        for ang in range(62, 125, 14):
            x, y = self.wall_point('main_hall', mh, ang, back_off=0.45)
            kit.place(P['counter'], (x, y, 0.03), yaw=ang + 90, color=(206, 180, 140),
                      text="Kitchen — counters along the north wall")
        fx, fy = self.wall_point('main_hall', mh, 132, back_off=0.5)
        kit.place(P['fridge'], (fx, fy, 0.03), yaw=132 + 90, color=(238, 238, 236),
                  text="Kitchen — refrigerator")
        kit.place(P['counter_island'], (-1.2, 3.6, 0.03), yaw=0, color=(150, 108, 70),
                  text="Kitchen island — cooking is shared on a rota")
        for k, (x, y) in enumerate([(-6.2, 2.4), (-4.4, 5.0), (3.4, 4.2), (5.6, 1.3),
                                    (-7.2, -0.9)]):
            kit.place(P['table_round'], (x, y, 0.03), color=wood,
                      text="Dining — round tables, shared dinners")
            for j in range(5):
                a = j * 72 + k * 17
                cx = x + 1.05 * math.cos(math.radians(a))
                cy = y + 1.05 * math.sin(math.radians(a))
                kit.place(P['chair'], (cx, cy, 0.03), yaw=a + 90, color=dark,
                          text="Chair")
        # the Nook: a window seat with cushions and a bookcase
        nx, ny = self.wall_point('main_hall', mh, 180, back_off=0.4)
        kit.place(P['bench'], (nx, ny, 0.03), yaw=90, s=(1.3, 1.4, 1.0),
                  color=birch, text="The Nook — a window seat")
        for dy in (-0.6, 0.0, 0.6):
            kit.place(P['cushion'], (nx, ny + dy, 0.48), color=(186, 70, 54),
                      text="Cushion")
        # lower level: cushions around the steps, a round rug at the bottom
        kit.place(P['rug'], (PIT_C[0], PIT_C[1], -0.95), s=(1.4, 0.9, 1.0),
                  color=(150, 60, 48), text="Lower level — a round rug for "
                  "story time and meditation")
        for k in range(10):
            a = 2 * math.pi * k / 10
            x = PIT_C[0] + (PIT_RX - 0.62) * math.cos(a)
            y = PIT_C[1] + (PIT_RY - 0.62) * math.sin(a)
            if y > PIT_C[1] + 1.9:
                continue
            kit.place(P['cushion'], (x, y, -0.29), color=(200, 140, 60) if k % 2 else (90, 120, 150),
                      text="Floor cushion on the gathering steps")

        # Indoor Recreation
        kit.place(P['pingpong'], (13.5, -3.2, 0.03), yaw=20, color=(40, 96, 70),
                  text="Indoor Recreation — table tennis")
        kit.place(P['piano'], (8.6, 3.4, 0.03), yaw=-12, color=(42, 30, 26),
                  text="Upright piano — music and sing-alongs")
        kit.place(P['rug'], (12.0, -8.4, 0.03), s=(1.5, 1.2, 1.0), color=(196, 150, 70),
                  text="Play rug")
        for k, (x, y) in enumerate([(10.6, -7.6), (12.4, -9.6), (13.6, -7.4), (10.8, -9.8)]):
            kit.place(P['beanbag'], (x, y, 0.05),
                      color=[(200, 70, 60), (60, 120, 180), (230, 180, 60), (90, 160, 90)][k],
                      text="Bean bag")
        kit.place(P['table_rect'], (16.6, 2.0, 0.03), yaw=90, color=birch,
                  text="Craft table — painting, popsicle sticks")
        for k in range(3):
            for side in (-1, 1):
                kit.place(P['stool_low'], (16.6 + side * 0.75, 1.2 + k * 0.8, 0.03),
                          color=[(220, 90, 70), (70, 140, 200), (240, 200, 70)][k],
                          text="Stool")

        # Lab: benches with stools, a row of computers
        for k, y in enumerate((-0.4, -2.3)):
            kit.place(P['lab_bench'], (25.8, y, 0.03), color=(70, 70, 76),
                      text="Lab — science benches (microscopes, chemistry sets, "
                           "spectacular demos)")
            for j in range(4):
                kit.place(P['stool'], (24.3 + j * 1.0, y - 0.65, 0.03), color=(60, 120, 170),
                          text="Lab stool")
        for j in range(4):
            kit.place(P['computer'], (21.4, 0.2 - j * 0.9, 0.93), yaw=-90,
                      color=(46, 48, 54), text="Computers — LEGO Logo, desktop "
                      "publishing, Internet pen-pals")
        kit.place(P['side_bench'], (21.2, -1.15, 0.03), yaw=90, color=(200, 196, 188),
                  text="Computer bench")

        # Lobby / Foyer: benches, plants, and the three original drawings
        for x, y, yaw in ((22.4, -7.4, 90), (30.8, -7.4, -90)):
            kit.place(P['bench'], (x, y, 0.03), yaw=yaw, color=wood, text="Lobby bench")
        for x, y in ((22.0, -4.0), (31.2, -4.0)):
            self._plant(kit, P, x, y)
        # easels: the drawings this model was built from
        for k, (dx, img, aspect, label) in enumerate((
                (-1.9, 'drawing_community', 612 / 792, "The Initial Community"),
                (0.0, 'drawing_elevation', 1064 / 437, "Elevation"),
                (1.9, 'drawing_floor_plan', 1000 / 591, "Top View"))):
            x, y = 26.6 + dx, -7.0
            rig = kit.rig((x, y, 0.03))
            kit.place(P['easel'], (0, 0, 0), parent=rig, color=(150, 110, 70),
                      text=f"Easel — Jeff Sale & Jodi Reed's original drawing: {label}")
            h = 1.0 if aspect < 1.5 else 0.62
            w = h * aspect
            if w > 1.3:
                w, h = 1.3, 1.3 / aspect
            kit.place(P['board'], (0, -0.21, 0.66), s=(w, 1.0, h), parent=rig,
                      color=(255, 255, 255), texture=tex[img],
                      text=f"Original drawing: {label}")

        # Courtyard: a young tree in a round bench
        cx, cy = 26.3, -12.6
        kit.place(P['tree_bench'], (cx, cy, 0.03), color=wood,
                  text="Courtyard — a ring bench round a young tree")
        self.courtyard_tree = (cx, cy)

        # Admin office
        kit.place(P['desk'], (18.4, -11.6, 0.03), yaw=200, color=wood,
                  text="Admin Office — desk")
        kit.place(P['chair'], (18.7, -12.4, 0.03), yaw=20, color=dark, text="Chair")
        kit.place(P['filing'], (17.0, -11.0, 0.03), yaw=200, color=(120, 128, 136),
                  text="Filing cabinet")

        # Library: bookcases round the walls, reading tables, armchairs,
        # museum cases and a globe, the spiral stair to the roof terrace
        lc = (36.6, -6.6)
        for ang in list(range(-150, 181, 24)):
            x, y = self.wall_point('library', lc, ang, back_off=0.32)
            if math.hypot(x - lc[0], y - lc[1]) < 3.0:
                continue
            rig = kit.rig((x, y, 0.03), yaw=ang - 90)
            kit.place(P['bookcase_carcass'], (0, 0, 0), parent=rig, color=dark,
                      text="Bookcases — 'a truly awesome library'")
            kit.place(P['bookcase_front'], (0, 0, 0), parent=rig, color=(255, 255, 255),
                      texture=tex['books'], text="Books")
        for x, y in ((35.4, -5.0), (37.8, -8.2)):
            kit.place(P['table_rect'], (x, y, 0.03), yaw=60, color=wood,
                      text="Reading table")
            for side in (-1, 1):
                a = math.radians(60)
                kit.place(P['chair'], (x + side * 0.65 * math.sin(a), y - side * 0.65 * math.cos(a), 0.03),
                          yaw=60 + (90 if side < 0 else -90) + 180, color=dark, text="Chair")
        for x, y, yaw in ((34.0, -10.6, 30), (35.2, -11.6, 60)):
            kit.place(P['armchair'], (x, y, 0.03), yaw=yaw, color=(120, 50, 40),
                      text="Armchair — quiet time")
        for x, y, yaw in ((38.4, 0.4, 0), (35.6, 1.0, 0)):
            kit.place(P['case_plinth'], (x, y, 0.03), yaw=yaw, color=birch,
                      text="Museum case — fossils, crystals, a bird's nest")
            kit.place(P['case_glass'], (x, y, 0.03), yaw=yaw, color=(200, 230, 240),
                      alpha=70, text="Museum case glass")
        kit.place(P['globe_stand'], (36.8, -2.6, 0.03), color=dark, text="Globe")
        kit.place(P['globe_ball'], (36.8, -2.6, 0.03), color=(70, 130, 190), text="Globe")
        sx, sy = (float(v) for v in pt.to_world(812, 332))
        kit.place(P['spiral_treads'], (sx, sy, 0.03), color=birch,
                  text="Spiral stair, as drawn — up to the roof terrace")
        kit.place(P['spiral_post'], (sx, sy, 0.03), color=(70, 70, 74),
                  text="Spiral stair post and rail")
        # underwater observation: a bench facing the glass, a telescope
        kit.place(P['bench'], (38.6, 3.2, 0.03), yaw=-45, s=(1.5, 1, 1), color=birch,
                  text="Bench facing the underwater windows")
        kit.place(P['bench'], (36.6, 4.6, 0.03), yaw=-25, s=(1.2, 1, 1), color=birch,
                  text="Bench facing the underwater windows")

        # North gallery: the children's cubbies
        for x in (19.5, 22.3, 25.1):
            kit.place(P['cubbies'], (x, 6.3 if x < 24 else 5.9, 0.03), yaw=180,
                      s=(2.6, 1.0, 1.25), color=(255, 255, 255), texture=tex['cubbies'],
                      text="Cubbies — a place for every child's things")
        # storage: shelving and crates
        for x in (12.0, 15.0, 18.0):
            kit.place(P['shelving'], (x, 8.4, 0.03), color=(130, 132, 138),
                      text="Storage shelving")
        for k in range(5):
            kit.place(P['crate'], (13.0 + k * 1.1, 6.8 + (k % 2) * 0.4, 0.03),
                      yaw=k * 13, color=(170, 130, 80), text="Crate")

    def _plant(self, kit, P, x, y):
        rig = kit.rig((x, y, 0.03))
        kit.place(P['pot'], (0, 0, 0), parent=rig, color=(176, 92, 56), text="Potted plant")
        kit.place(P['plant'], (0, 0, 0), parent=rig, color=(70, 130, 60), text="Potted plant")


def furniture_pieces(kit):
    """Model every furnishing once; returns {key: mesh filename}."""
    P = {}

    def reg(key, mesh):
        P[key] = kit.mesh(f"furn_{key}.obj", mesh)

    reg('chair', fu.chair())
    reg('stool', fu.stool())
    reg('stool_low', fu.stool(0.42))
    reg('table_round', fu.table_round())
    reg('table_rect', fu.table_rect())
    reg('lab_bench', fu.table_rect(3.2, 0.8, 0.92, leg=0.07))
    reg('side_bench', fu.table_rect(3.6, 0.7, 0.92, leg=0.06))
    reg('bench', fu.bench())
    reg('counter', fu.counter(2.0))
    reg('counter_island', fu.counter(2.6, 1.0))
    reg('fridge', fu.fridge())
    carcass, front = fu.bookcase_parts()
    reg('bookcase_carcass', carcass)
    reg('bookcase_front', front)
    reg('board', fu.panel(1.0, 1.0, 0.03, name="board"))
    reg('cubbies', fu.panel(1.0, 1.0, 0.40, name="cubbies"))
    reg('easel', fu.easel_frame())
    reg('armchair', fu.armchair())
    reg('beanbag', fu.beanbag())
    reg('cushion', fu.cushion())
    reg('rug', fu.rug())
    reg('piano', fu.piano())
    reg('pingpong', fu.pingpong())
    reg('computer', fu.computer())
    plinth, glass = fu.display_case()
    reg('case_plinth', plinth)
    reg('case_glass', glass)
    reg('globe_stand', fu.globe_stand())
    reg('globe_ball', fu.globe_ball())
    pot, plant = fu.potted_plant()
    reg('pot', pot)
    reg('plant', plant)
    treads, post = fu.spiral_stair()
    reg('spiral_treads', treads)
    reg('spiral_post', post)
    reg('desk', fu.desk())
    reg('filing', fu.filing_cabinet())
    reg('shelving', fu.shelving())
    reg('crate', fu.crate())
    ring = mk.Mesh("tree_bench")
    ring.extend(mk.revolve([(1.1, 0.0), (1.55, 0.0), (1.55, 0.45), (1.1, 0.45),
                            (1.1, 0.0)], segments=28))
    reg('tree_bench', ring)
    reg('log_bench', fu.log_bench())
    return P
