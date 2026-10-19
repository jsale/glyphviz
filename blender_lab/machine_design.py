"""The clockwork marble machine.  Run INSIDE Blender (python bl.py run machine_design.py).

A wall-mounted contraption in the XZ plane, viewed from -Y.  One loop = 360
frames = 12 s @ 30 fps; every angle below is a closed-form function of the loop
phase u in [0,1) so frame 361 == frame 1 exactly.

  G1 (30T) --meshes--> G2 (15T) --meshes--> G3 (60T, the lift wheel)
       |  eccentric cam -> follower -> strikes a gong      (2 strikes/loop)
       |                   G2 crank pin -> con-rod -> piston  (4 strokes/loop)
       |                   G3 carries six gondola cups that lift six marbles
  pendulum swings 6x/loop.

Marbles are scripted kinematically (a rigid-body bake would not loop): carried
by a gondola, poured onto rail F1, through a portal ring, along F2 (past a
colour prism), down F3, and dropped into their own gondola again.
"""
import importlib
import math
import sys

HERE = r"C:\Users\jsale\source\repos\glyphviz\blender_lab"
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import machine_lib as L
import export_for_glyphviz as X
importlib.reload(L)
importlib.reload(X)
import bpy
import colorsys

TAU = math.tau
N = 360
FR = range(1, N + 1)
OUT = HERE + r"\out\machine"


def U(f):
    return (f - 1) / N


def smooth(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return a + (b - a) * t


# ------------------------------------------------------------------ layout
M = 0.1
T1, T2, T3 = 30, 15, 60
C1 = (-5.5, 4.5)
PHI12, PHI23 = 0.0, math.radians(-35.0)
C2 = (C1[0] + L.centre_distance(T1, T2, M), C1[1])
D23 = L.centre_distance(T2, T3, M)
C3 = (C2[0] + D23 * math.cos(PHI23), C2[1] + D23 * math.sin(PHI23))


def th1(u): return TAU * 2.0 * u                      # +2 rev / loop
def th2(u): return L.follow(th1(u), T1, T2, PHI12)    # -4 rev
def th3(u): return L.follow(th2(u), T2, T3, PHI23)    # +1 rev


MARBLE_R = 0.20
CUP_RIN, CUP_ROUT, CUP_HALF_W = 0.25, 0.32, 0.15
SIT = CUP_RIN - MARBLE_R - 0.005       # a resting marble's centre sits this far below the cup's centre

Y_RAIL = -0.95            # marbles on the rails
Y_CUP = -0.40             # gondola cups
Y_MCUP = -0.46            # a marble sits slightly proud of the cup's back brace
R_PIV = 2.6               # gondola pivot radius on the wheel
CUP_DROP = 0.80           # pivot -> cup centre
N_BUCKET = 6
PSI_REL, PSI_LOAD = 36.0, -60.0      # wheel angle (deg) where a marble is poured / loaded
S_LAND = ((PSI_LOAD - PSI_REL) % 360.0) / 360.0     # fraction of a loop spent running

F1 = ((2.55, 3.00), (8.10, 2.20))
F2 = ((3.40, 1.87), (8.10, 1.21))       # 0.2 lower than F1's mirror so the exit ring clears F1's plank
F3 = ((8.80, 0.50), (2.30, 0.00))      # starts right of / well below F2's end (the hop is a plain arc), and
                                       # runs UNDER F2, which slopes toward it: needs >= 0.55 m centre-line gap
PRISM_X = 5.6
RING1_X = 8.62
RING2_X = 3.18

# seg weights of the run: release, F1, portal(hidden), F2, drop, F3, landing
SEG_W = [0.04, 0.24, 0.08, 0.20, 0.04, 0.32, 0.08]
SEG_B = [sum(SEG_W[:i]) for i in range(len(SEG_W) + 1)]


def line_z(fl, x):
    (x0, z0), (x1, z1) = fl
    return z0 + (z1 - z0) * (x - x0) / (x1 - x0)


def pivot(k, u):
    psi = math.radians(60.0 * k) + (th3(u) - th3(0.0))
    return (C3[0] + R_PIV * math.cos(psi), C3[1] + R_PIV * math.sin(psi)), math.degrees(psi)


def tilt_deg(psi_deg):
    p = (psi_deg + 180.0) % 360.0 - 180.0
    if 10.0 <= p <= 70.0:
        return 74.0 * math.sin(math.pi * (p - 10.0) / 60.0) ** 2
    return 0.0


def cup_centre(k, u):
    (px, pz), _ = pivot(k, u)
    return (px, pz - CUP_DROP)


def marble_phase_s(k, u):
    _, psi = pivot(k, u)
    return ((psi - PSI_REL) % 360.0) / 360.0


P_REL = None      # filled from the geometry (marble centre at the instant of release)
P_LAND = None


def _fixed_points():
    global P_REL, P_LAND
    # at release / landing the wheel angle is fixed, so the gondola position is too
    px = C3[0] + R_PIV * math.cos(math.radians(PSI_REL))
    pz = C3[1] + R_PIV * math.sin(math.radians(PSI_REL))
    P_REL = (px, pz - CUP_DROP - SIT)
    px = C3[0] + R_PIV * math.cos(math.radians(PSI_LOAD))
    pz = C3[1] + R_PIV * math.sin(math.radians(PSI_LOAD))
    P_LAND = (px, pz - CUP_DROP - SIT)


_fixed_points()


def hue_rgb(h):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, 0.82, 1.0)
    return (r * 255.0, g * 255.0, b * 255.0)


WHITE = (236.0, 236.0, 240.0)
PRISM_HALF = 0.28


def _inv_acc(frac):
    """Invert the rolling profile a(t) = t/2 + t^2/2 (distance fraction -> time fraction)."""
    return -0.5 + math.sqrt(0.25 + 2.0 * frac)


# the hue sweep begins as the marble LEAVES the prism; inside it, white blends to the first hue
R_EXIT = SEG_B[3] + SEG_W[3] * _inv_acc((PRISM_X + PRISM_HALF - F2[0][0]) / (F2[1][0] - F2[0][0]))
S_PRISM = R_EXIT * S_LAND
S_IN = SEG_B[2] * S_LAND            # the instant the marble enters portal 1


def marble_state(k, u):
    """(x, y, z, (r,g,b), hide) for marble k at loop phase u."""
    s = marble_phase_s(k, u)
    # ---- colour: white until the prism, then a spectrum sweep until portal 1
    q = (s - S_PRISM) % 1.0
    q_end = (S_IN - S_PRISM) % 1.0
    col = hue_rgb(0.85 * q / q_end) if q <= q_end else WHITE
    hide = 0
    if s >= S_LAND:                                  # carried in gondola k
        cx, cz = cup_centre(k, u)
        return (cx, Y_MCUP, cz - SIT, col, 0)
    r = s / S_LAND
    seg = max(i for i in range(7) if SEG_B[i] <= r + 1e-12)
    seg = min(seg, 6)
    w = (r - SEG_B[seg]) / SEG_W[seg]
    acc = lambda t: 0.5 * t + 0.5 * t * t            # rolling downhill: speeds up
    if seg == 0:                                     # pour out of the cup onto F1
        x = lerp(P_REL[0], F1[0][0], w)
        z = lerp(P_REL[1], F1[0][1], w * w)
        y = lerp(Y_MCUP, Y_RAIL, smooth(w))
    elif seg == 1:
        a = acc(w)
        x = lerp(F1[0][0], F1[1][0], a)
        z = line_z(F1, x)
        y = Y_RAIL
    elif seg == 2:                                   # inside the portal: hidden
        hide = 1
        col = WHITE
        if w < 0.5:
            x, z = F1[1][0] + 0.4, line_z(F1, F1[1][0] + 0.4)
        else:
            x, z = F2[0][0] - 0.2, line_z(F2, F2[0][0] - 0.2)
        y = Y_RAIL
    elif seg == 3:
        a = acc(w)
        x = lerp(F2[0][0], F2[1][0], a)
        z = line_z(F2, x)
        y = Y_RAIL
        if x < PRISM_X + PRISM_HALF:                 # inside / approaching the prism: white -> first hue
            b = smooth((x - (PRISM_X - PRISM_HALF)) / (2.0 * PRISM_HALF))
            h0 = hue_rgb(0.0)
            col = tuple(lerp(WHITE[i], h0[i], b) for i in range(3))
    elif seg == 4:                                   # hop from F2's end onto F3
        x = lerp(F2[1][0], F3[0][0], w)                # carries on right at F2's exit speed...
        z = lerp(F2[1][1], F3[0][1], w * w)            # ...while gravity takes it down: a parabola
        y = Y_RAIL
    elif seg == 5:
        a = acc(w)
        x = lerp(F3[0][0], F3[1][0], a)
        z = line_z(F3, x)
        y = Y_RAIL
    else:                                            # fall into the gondola
        x = lerp(F3[1][0], P_LAND[0], w)
        z = lerp(F3[1][1], P_LAND[1], w * w)
        y = lerp(Y_RAIL, Y_MCUP, smooth(w))
    return (x, y, z, col, hide)


def pulse_events(u, event_s, width):
    """Sum over marbles of a bump centred on each marble's crossing of `event_s`."""
    tot = 0.0
    for k in range(N_BUCKET):
        d = (marble_phase_s(k, u) - event_s + 0.5) % 1.0 - 0.5
        tot += math.exp(-(d / width) ** 2)
    return min(1.0, tot)


# ------------------------------------------------------------------ build
L.clear_scene()
scn = bpy.context.scene
scn.frame_start, scn.frame_end = 1, N
scn.render.fps = 30

STEEL = (150, 158, 176)
DARK = (82, 90, 112)

# --- gear train
G1 = L.make_gear("G1_gear30", T1, M, 0.25, spokes=5)
G2 = L.make_gear("G2_gear15", T2, M, 0.25, stud=(0.45, 0.075, -0.56))
G3 = L.make_gear("G3_wheel60", T3, M, 0.25, spokes=8)
L.mark(G1, (214, 168, 64), label="G1 - drive gear, 30 teeth (2 turns per loop)")
L.mark(G2, (96, 170, 220), label="G2 - pinion, 15 teeth (reverses, 4 turns)")
L.mark(G3, (205, 112, 70), label="G3 - lift wheel, 60 teeth (1 turn)")
L.set_pose(G1, C1[0], 0, C1[1]); L.set_pose(G2, C2[0], 0, C2[1]); L.set_pose(G3, C3[0], 0, C3[1])
L.key_rot_y(G1, lambda f: th1(U(f)), FR)
L.key_rot_y(G2, lambda f: th2(U(f)), FR)
L.key_rot_y(G3, lambda f: th3(U(f)), FR)

# --- crank / con-rod / piston (on G2)
ROD_L, CRANK_E, Y_LINK = 2.2, 0.45, -0.42
rod = L.make_bar("P1_conrod", ROD_L, 0.13, 0.09, 0.13)
L.mark(rod, (226, 228, 236), label="Connecting rod")
piston = L.make_block("P2_piston", 0.5, 0.2, 0.5)
L.mark(piston, (170, 176, 196), label="Piston")
L.set_pose(rod, C2[0], Y_LINK, C2[1]); L.set_pose(piston, C2[0], Y_LINK, 6.5)


def crank(u):
    a = th2(u)
    px, pz = C2[0] + CRANK_E * math.cos(a), C2[1] + CRANK_E * math.sin(a)
    zs = pz + math.sqrt(ROD_L ** 2 - (C2[0] - px) ** 2)
    return px, pz, zs, math.atan2(zs - pz, C2[0] - px)


for f in FR:
    px, pz, zs, beta = crank(U(f))
    rod.location = (px, Y_LINK, pz); rod.rotation_euler = (0.0, -beta, 0.0)
    rod.keyframe_insert("location", frame=f); rod.keyframe_insert("rotation_euler", index=1, frame=f)
    piston.location = (C2[0], Y_LINK, zs + 0.0)
    piston.keyframe_insert("location", frame=f)
L._linear(rod); L._linear(piston)

# --- cam, follower, gong
CAM_R, CAM_E, Y_CAM = 0.7, 0.35, -0.35
cam = L.make_cylinder("C1_cam", CAM_R, 0.12)
L.mark(cam, (168, 206, 108), label="Eccentric cam (on G1's shaft)")
fol = L.Static()
fol.box(0, 0, 0, 0.5, 0.07, 0.05)                       # flat follower plate
fol.box(0, 0, 0.75, 0.05, 0.05, 0.75)                   # rod
fol.cyl(0, 1.5, 0.14, -0.05, 0.05, n=16)                # hammer head (axis along Y)
follower = fol.build("C2_follower")
L.mark(follower, (206, 208, 220), label="Cam follower + hammer")
for f in FR:
    a = th1(U(f))
    cam.location = (C1[0] + CAM_E * math.cos(a), Y_CAM, C1[1] + CAM_E * math.sin(a))
    cam.keyframe_insert("location", frame=f)
    follower.location = (C1[0], Y_CAM, C1[1] + CAM_E * math.sin(a) + CAM_R + 0.05)
    follower.keyframe_insert("location", frame=f)
L._linear(cam); L._linear(follower)

GONG_Z = C1[1] + CAM_E + CAM_R + 0.05 + 1.5 + 0.14 + 0.5          # lowest edge touches the hammer at top of stroke
gong = L.make_cylinder("C3_gong", 0.5, 0.12)
L.mark(gong, (212, 160, 64), label="Gong")
L.set_pose(gong, C1[0], Y_CAM, GONG_Z)
STRIKE_U = [(0.25 + j) / 2.0 for j in range(2)]                    # th1 = 90 deg at u=.125,.625


def gong_glow(u):
    best = 0.0
    for us in (0.125, 0.625):
        d = (u - us) % 0.5
        best = max(best, math.exp(-d / 0.035))
    return best


for f in FR:
    g = gong_glow(U(f))
    base, hot = (212, 160, 64), (255, 245, 170)
    gong["gv_r"], gong["gv_g"], gong["gv_b"] = [lerp(b, h, g) for b, h in zip(base, hot)]
    for p in ("gv_r", "gv_g", "gv_b"):
        gong.keyframe_insert('["%s"]' % p, frame=f)
L._linear(gong)

# --- pendulum
PEND_P = (-5.5, 2.45)
PEND_L, PEND_A = 2.9, math.radians(10.0)    # 10 deg: the widest swing the anchor can follow without
PEND_K = 6                                  # fouling the escape wheel (found by scan_escapement.py)
pn = L.Static()
pn.cyl(0, 0, 0.13, -0.05, 0.05, n=16)
pn.box(0, 0, -PEND_L / 2, 0.035, 0.035, PEND_L / 2)
pn.cyl(0, -PEND_L, 0.42, -0.09, 0.09, n=28)
pend = pn.build("K1_pendulum")
L.mark(pend, (214, 168, 64), label="Pendulum (6 swings per loop)")
L.set_pose(pend, PEND_P[0], -0.3, PEND_P[1])
def pend_angle(u):
    return PEND_A * math.sin(TAU * PEND_K * u)


for f in FR:
    pend.location = (PEND_P[0], -0.3, PEND_P[1]); pend.rotation_euler = (0.0, -pend_angle(U(f)), 0.0)
    pend.keyframe_insert("rotation_euler", index=1, frame=f)
L._linear(pend)

# --- escapement: the anchor rides the pendulum; the escape wheel advances half a tooth at each zero
# crossing, when both pallets are momentarily clear.  Pallets straddle ~2.5 pitches so one rests in a
# gap while the other is lifted.  Numbers from scan_escapement.py (zero collisions + real engagement).
ESC_TEETH, ESC_M, ESC_Z, ESC_AX = 12, 0.14, 0.96, 0.74
ESC_PITCH = TAU / ESC_TEETH
esc = L.make_gear("K2_escape12", ESC_TEETH, ESC_M, 0.12)
anchor = L.make_anchor("K3_anchor", ax=ESC_AX, az=0.5)
L.mark(esc, (96, 170, 220), label="Escape wheel (advances half a tooth per tick)")
L.mark(anchor, (240, 232, 200), label="Anchor (rocks with the pendulum)")
L.set_pose(esc, PEND_P[0], 0, ESC_Z); L.set_pose(anchor, PEND_P[0], 0, PEND_P[1])


def esc_steps(u, width=0.45):
    """Half-swings completed: each step is a smoothstep centred on a pendulum zero crossing."""
    t = u * 2.0 * PEND_K
    n = math.floor(t)
    return n + smooth((t - n - (0.5 - width / 2.0)) / width)


def esc_angle(u):
    return -0.5 * ESC_PITCH * esc_steps(u)           # clockwise ticks


for f in FR:
    anchor.location = (PEND_P[0], 0.0, PEND_P[1]); anchor.rotation_euler = (0.0, -pend_angle(U(f)), 0.0)
    anchor.keyframe_insert("rotation_euler", index=1, frame=f)
L._linear(anchor)
L.key_rot_y(esc, lambda f: esc_angle(U(f)), FR)

# --- gondolas + marbles
cups, stems, marbles = [], [], []
for k in range(N_BUCKET):
    c = L.make_cup("B%d_cup" % k, r_in=CUP_RIN, r_out=CUP_ROUT, a1=335.0, half_w=CUP_HALF_W)
    L.mark(c, (96, 196, 176), label="Gondola %d" % (k + 1))
    st = L.make_stem("B%d_stem" % k, CUP_DROP - 0.06)       # down to the cup's back brace
    L.mark(st, (122, 134, 156))
    mb = L.make_sphere("M%d_marble" % k, MARBLE_R)
    L.mark(mb, (236, 236, 240), label="Marble %d" % (k + 1))
    cups.append(c); stems.append(st); marbles.append(mb)
for f in FR:
    u = U(f)
    for k in range(N_BUCKET):
        (px, pz), psi = pivot(k, u)
        stems[k].location = (px, -0.128, pz)       # pin tip just inside the wheel's -Y face
        stems[k].keyframe_insert("location", frame=f)
        cx, cz = px, pz - CUP_DROP
        cups[k].location = (cx, Y_CUP, cz)
        cups[k].rotation_euler = (0.0, math.radians(tilt_deg(psi)), 0.0)   # CW on screen = +Y rotation
        cups[k].keyframe_insert("location", frame=f)
        cups[k].keyframe_insert("rotation_euler", index=1, frame=f)
        x, y, z, col, hide = marble_state(k, u)
        mb = marbles[k]
        mb.location = (x, y, z)
        mb.keyframe_insert("location", frame=f)
        mb["gv_r"], mb["gv_g"], mb["gv_b"], mb["gv_hide"] = col[0], col[1], col[2], float(hide)
        for p in ("gv_r", "gv_g", "gv_b", "gv_hide"):
            mb.keyframe_insert('["%s"]' % p, frame=f)
for ob in cups + stems + marbles:
    L._linear(ob)

# --- portal rings + prism (the rings glow as marbles cross them)
slope = lambda fl: math.atan2(fl[1][1] - fl[0][1], fl[1][0] - fl[0][0])
ring1 = L.make_torus_x("R1_portal_in", 0.52, 0.065)
ring2 = L.make_torus_x("R2_portal_out", 0.52, 0.065)
L.mark(ring1, (120, 90, 200), label="Portal (entry)")
L.mark(ring2, (120, 90, 200), label="Portal (exit)")
L.set_pose(ring1, RING1_X, Y_RAIL, line_z(F1, RING1_X), slope(F1))
L.set_pose(ring2, RING2_X, Y_RAIL, line_z(F2, RING2_X), slope(F2))
for ring, ev in ((ring1, SEG_B[2] * S_LAND), (ring2, SEG_B[3] * S_LAND)):
    for f in FR:
        g = pulse_events(U(f), ev, 0.012)
        for p, (b, h) in zip(("gv_r", "gv_g", "gv_b"), zip((120, 90, 200), (255, 230, 255))):
            ring[p] = lerp(b, h, g)
            ring.keyframe_insert('["%s"]' % p, frame=f)
    L._linear(ring)

pz = line_z(F2, PRISM_X) + 0.02
prism = L.Static().prism_x(PRISM_X - 0.28, PRISM_X + 0.28,
                           [(Y_RAIL - 0.52, pz - 0.38), (Y_RAIL + 0.52, pz - 0.38), (Y_RAIL, pz + 0.55)]).build("R3_prism")
L.mark(prism, (170, 225, 255), alpha=110, label="Colour prism")

# --- static structure
wall = L.Static().box(0.65, 0.30, 3.0, 9.0, 0.05, 6.0)
wall.box(0.65, -0.55, -3.05, 9.0, 0.95, 0.10)                      # base shelf
wall_ob = wall.build("W1_wall")
L.mark(wall_ob, (30, 38, 62), label="Back wall")

rails = L.Static()
T_RAIL, W_RAIL = 0.10, 0.40
OFF = MARBLE_R + 0.015 + T_RAIL / 2.0       # plank top sits 15 mm under a resting marble
# (flight, overhang past start, overhang past end, rib x positions).  A flight whose marble must
# FALL away from its end (F3 into the gondola) gets no end overhang or the marble clips the corner;
# F2's far rib sits at 7.1 because at 7.7 it hangs right above the marble's F3 path.
for a, ext, ribs in ((F1, (0.2, 0.1), (3.6, 5.6, 7.7)),
                     (F2, (0.1, 0.0), (3.6, 5.6, 7.1)),      # starts just clear of the exit ring (x=3.18)
                     (F3, (0.35, 0.0), (3.6, 5.6, 7.7))):
    (x0, z0), (x1, z1) = a
    sgn = 1 if x1 > x0 else -1
    xa, xb = x0 - sgn * ext[0], x1 + sgn * ext[1]
    rails.plank((xa, line_z(a, xa) - OFF), (xb, line_z(a, xb) - OFF), T_RAIL, W_RAIL, Y_RAIL)
    for x in ribs:                                                # ribs from the wall to the rail
        if min(xa, xb) <= x <= max(xa, xb):
            zt = line_z(a, x) - OFF - 0.05
            rails.box(x, (0.25 + Y_RAIL - W_RAIL / 2) / 2, zt - 0.05, 0.05, (0.25 - Y_RAIL + W_RAIL / 2) / 2, 0.05)
rails_ob = rails.build("W2_rails")
L.mark(rails_ob, (150, 160, 182), label="Marble rails")

hous = L.Static()                                                  # piston guides
for dx in (-0.34, 0.34):
    hous.box(C2[0] + dx, Y_LINK, 6.75, 0.035, 0.12, 0.95)
hous.box(C2[0], Y_LINK, 7.75, 0.45, 0.12, 0.06)
for dx in (-0.34, 0.34):                                           # arms tie each guide to the wall,
    hous.box(C2[0] + dx, -0.145, 6.75, 0.035, 0.395, 0.06)         # OUTSIDE the piston's path
# gong hanger + follower guide
hous.box(C1[0], 0.0, 8.45, 0.06, 0.35, 0.06)                       # arm from the wall
for dx in (-0.35, 0.35):
    hous.box(C1[0] + dx, Y_CAM, (8.45 + GONG_Z + 0.5) / 2, 0.015, 0.03, (8.45 - GONG_Z - 0.5) / 2)
for dx in (-0.22, 0.22):                                           # clear of the 0.14-radius hammer head
    hous.box(C1[0] + dx, (0.25 - 0.45) / 2, 6.55, 0.035, 0.35, 0.1)
hous_ob = hous.build("W3_brackets")
L.mark(hous_ob, (110, 120, 142), label="Guides and brackets")

print("layout: C2=%s C3=%s S_LAND=%.4f P_REL=%s P_LAND=%s" % (C2, C3, S_LAND, P_REL, P_LAND))

checks = L.interference([("G1_gear30", "G2_gear15"), ("G2_gear15", "G3_wheel60"),
                         ("K2_escape12", "K3_anchor")], FR)
print("gear interference:", checks)
print(X.bake(OUT, 1, N))
