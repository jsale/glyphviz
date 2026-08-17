"""Generate a clock-face scene: one sphere hub with 12 radial rods.

Rods are children of the sphere with topo = Sphere (2), so translate_x is
longitude and translate_y is latitude.  Latitude 0 keeps every rod in the
horizontal (XY) plane; longitudes step 30 degrees starting at 0.  A Sphere
parent also gives each child the base rotation Rz(lon)*Ry(90-lat), which aims
the child's local +Z along the outward surface normal -- and a Cylinder glyph's
axis IS its local +Z, so the rods point radially outward with no rotation of
their own.
"""
import csv
import sys

OUT = sys.argv[1]

HUB_ID = 2
B = 1.0            # global scale / parent base radius
ROD_HALF = 2.0     # scale_z: cylinder spans -1..1 in local Z, so length = 2*this
ROD_RADIUS = 0.2   # scale_x/y (>= 0.2 so the optional min-glyph-size clamp is a no-op)
ALTITUDE = ROD_HALF  # translate_z: push the rod's CENTER out so its base sits on the hub

COLS = [
    "id", "type", "parent_id", "branch_level",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo", "ratio", "rotation_mode", "show_text", "text",
]

QUARTER = (255, 190, 60)   # 12, 3, 6, 9
HOUR = (110, 160, 220)


def row(**kw):
    r = {c: 0 for c in COLS}
    r["text"] = ""
    r["color_a"] = 255
    r["ratio"] = 0.1
    r.update(kw)
    return r


rows = []

# Scene settings (never drawn): a dark, slightly blue background.
rows.append(row(id=1, type=0, color_r=12, color_g=12, color_b=24, geometry=0, topo=0))

# The hub.  topo = 2 (Sphere) is what places the rods.
rows.append(row(
    id=HUB_ID, type=5, parent_id=0, branch_level=0,
    scale_x=1.0, scale_y=1.0, scale_z=1.0,
    color_r=225, color_g=228, color_b=238,
    geometry=3, topo=2, rotation_mode=0,
))

# Twelve rods, longitude 0, 30, 60 ... 330.  Longitude runs counter-clockwise
# seen from +Z, so a clock face needs DECREASING longitude: hour h sits at
# (LON_12 - 30h) % 360.  LON_12 = 180 because GlyphViz's overhead "+Z View"
# camera puts -X (longitude 180) at the top of the screen and +Y at the right
# -- so from that view 12 is up, 3 right, 6 down, 9 left.
LON_12 = 180.0
for i in range(12):
    lon = i * 30.0
    hour = int((LON_12 - lon) / 30.0) % 12 or 12
    c = QUARTER if hour % 3 == 0 else HOUR
    rows.append(row(
        id=3 + i, type=5, parent_id=HUB_ID, branch_level=1,
        translate_x=lon, translate_y=0.0, translate_z=ALTITUDE,
        scale_x=ROD_RADIUS, scale_y=ROD_RADIUS, scale_z=ROD_HALF,
        color_r=c[0], color_g=c[1], color_b=c[2],
        geometry=19, topo=0, rotation_mode=0, show_text=1, text=str(hour),
    ))

with open(OUT, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=COLS, lineterminator="\r\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)

print(f"wrote {len(rows)} rows -> {OUT}")
