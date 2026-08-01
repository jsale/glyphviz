#!/usr/bin/env python3
"""
capture_tour_shots.py
=====================
Generate the screenshot set for the docs' "A Guided Tour" page
(glyphviz-docs/docs/getting-started/guided-tour.md) by driving the real
MainWindow through the same steps the tour describes — the N/Shift+N
creation handlers, table-driven selection, the geometry/topology fields —
and capturing frames along the way.

Scene-only shots come from Viewport.grabFramebuffer() (the exact pixels the
F12 PNG export produces); full-window shots come from QWidget.grab() with
the GL framebuffer pasted over the viewport rect (QOpenGLWidget content
isn't reliably composited into a widget grab). Composites (side-by-sides,
contact sheets, region-label overlays) are assembled with Pillow.

Running this briefly opens real windows on the desktop — it drives no
mouse or keyboard input, but expect a few seconds of window flashing.

Usage:
    python tools/capture_tour_shots.py                # all shots
    python tools/capture_tour_shots.py --only 05 12   # just tour-05*, tour-12*
    python tools/capture_tour_shots.py --keep-raw     # keep per-frame captures
"""
import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from PIL import Image, ImageDraw, ImageFont

from PySide6.QtCore import QPoint, QSize
from PySide6.QtWidgets import (
    QApplication, QDockWidget, QScrollArea, QToolBar,
)

OUT_DIR = REPO_ROOT / "glyphviz-docs" / "docs" / "assets" / "tour"
RAW_DIR = OUT_DIR / "_raw"

WIN_SIZE = QSize(1600, 1000)

# Geometry ids for the contact sheet + the octahedron default (geometry_data.py)
from glyphviz_core.geometry_data import (
    GEO_CUBE, GEO_SPHERE_WIRE, GEO_TORUS, GEO_DODECA, GEO_TETRA,
    GEO_ICOSA, GEO_PIN, GEO_CYLINDER, GEO_OCTA, GEO_NAMES,
)
from glyphviz_core.topology import (
    TOPO_SPHERE, TOPO_TORUS, TOPO_CYLINDER, TOPO_SPIRAL,
)
from glyphviz_core.geometry_data import GEO_TORUS_WIRE, GEO_CYLINDER_WIRE

CONTACT_GEOS = [GEO_CUBE, GEO_SPHERE_WIRE, GEO_TORUS, GEO_DODECA,
                GEO_TETRA, GEO_ICOSA, GEO_PIN, GEO_CYLINDER]

# (topology, pane label, wire-shell geometry that matches the placement surface)
TOPO_GRID = [(TOPO_SPHERE, "Sphere", GEO_SPHERE_WIRE),
             (TOPO_TORUS, "Torus", GEO_TORUS_WIRE),
             (TOPO_CYLINDER, "Cylinder", GEO_CYLINDER_WIRE),
             (TOPO_SPIRAL, "Spiral", GEO_SPHERE_WIRE)]


def pump(seconds: float = 0.15):
    """Let Qt process paints/layout for a moment (no exec loop here)."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)


def font(size: int = 28) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", size)
    except OSError:
        return ImageFont.load_default()


class Capture:
    """One MainWindow plus the grab/save helpers the shot functions share."""

    def __init__(self):
        from PySide6.QtCore import Qt
        from glyphviz_gl.main_window import MainWindow
        self.win = MainWindow()
        self.win.resize(WIN_SIZE)
        self.win.move(50, 50)
        self.win.show()
        pump(0.6)   # first GL init + dock layout
        # Rebalance the default dock layout for a viewport-dominant shot:
        # Properties narrow on the left, Node Table short at the bottom.
        docks = {d.windowTitle(): d for d in self.win.findChildren(QDockWidget)}
        if "Properties" in docks:
            self.win.resizeDocks([docks["Properties"]], [380],
                                 Qt.Orientation.Horizontal)
        if "Node Table" in docks:
            self.win.resizeDocks([docks["Node Table"]], [230],
                                 Qt.Orientation.Vertical)
        pump(0.2)

    @property
    def vp(self):
        return self.win._viewport

    def close(self):
        self.win.close()
        pump(0.1)

    # --- capture helpers ---

    def viewport_png(self, path: Path):
        pump(0.1)
        img = self.vp.grabFramebuffer()
        img.save(str(path))

    def window_png(self, path: Path):
        """Full-window grab with the GL framebuffer pasted over the viewport
        rect (widget grabs don't reliably include QOpenGLWidget content)."""
        self.win.statusBar().clearMessage()
        pump(0.15)
        pixmap = self.win.grab()
        shot = pixmap.toImage()
        dpr = pixmap.devicePixelRatio()
        gl = self.vp.grabFramebuffer()
        origin = self.vp.mapTo(self.win, QPoint(0, 0))
        tmp_gl = RAW_DIR / "_gl_paste.png"
        tmp_win = RAW_DIR / "_win_base.png"
        gl.save(str(tmp_gl))
        shot.save(str(tmp_win))
        base = Image.open(tmp_win)
        gl_img = Image.open(tmp_gl)
        target = (int(origin.x() * dpr), int(origin.y() * dpr))
        want = (int(self.vp.width() * dpr), int(self.vp.height() * dpr))
        if gl_img.size != want:
            gl_img = gl_img.resize(want)
        base.paste(gl_img, target)
        base.save(path)

    def region_rect(self, widget, dpr: float = 1.0) -> tuple[int, int, int, int]:
        p = widget.mapTo(self.win, QPoint(0, 0))
        return (int(p.x() * dpr), int(p.y() * dpr),
                int((p.x() + widget.width()) * dpr),
                int((p.y() + widget.height()) * dpr))

    # --- scene-building via the real app handlers ---

    def new_root(self):
        self.win._on_create_node()
        pump(0.05)

    def new_child(self):
        self.win._create_child_node()
        pump(0.05)

    def select(self, node_id: int):
        self.win._table.select_by_id(node_id)
        pump(0.05)

    def node(self, node_id: int):
        return next(n for n in self.win.nodes if n.id == node_id)

    def invalidate(self):
        self.vp.scene_invalidate()
        self.vp.update()
        pump(0.05)

    def camera(self, azim_deg: float, elev_deg: float, distance: float,
               target=(0.0, 0.0, 0.0)):
        # Viewport stores azimuth/elevation in degrees (radians at the
        # gluLookAt site only).
        self.vp.set_camera(azimuth=azim_deg, elevation=elev_deg,
                           distance=distance, target=target)
        self.vp.update()
        pump(0.05)


# --- Pillow composites ---

def side_by_side(paths: list[Path], out: Path, labels: list[str] | None = None,
                 gap: int = 6):
    imgs = [Image.open(p) for p in paths]
    h = min(i.height for i in imgs)
    imgs = [i.resize((int(i.width * h / i.height), h)) for i in imgs]
    w = sum(i.width for i in imgs) + gap * (len(imgs) - 1)
    label_h = 44 if labels else 0
    canvas = Image.new("RGB", (w, h + label_h), (24, 24, 28))
    x = 0
    draw = ImageDraw.Draw(canvas)
    f = font(26)
    for idx, img in enumerate(imgs):
        canvas.paste(img, (x, 0))
        if labels:
            draw.text((x + 12, h + 8), labels[idx], fill=(230, 230, 235), font=f)
        x += img.width + gap
    canvas.save(out)


def grid_sheet(paths: list[Path], labels: list[str], out: Path, cols: int,
               gap: int = 6, label_h: int = 40, crop_square: bool = False):
    imgs = [Image.open(p) for p in paths]
    if crop_square:
        # Center square crop (subject is camera-centered), sized off height.
        side = int(imgs[0].height * 0.8)
        imgs = [i.crop(((i.width - side) // 2, (i.height - side) // 2,
                        (i.width + side) // 2, (i.height + side) // 2))
                for i in imgs]
    cw, ch = imgs[0].width, imgs[0].height
    rows = (len(imgs) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * cw + gap * (cols - 1),
                               rows * (ch + label_h) + gap * (rows - 1)),
                       (24, 24, 28))
    draw = ImageDraw.Draw(canvas)
    f = font(26)
    for i, img in enumerate(imgs):
        r, c = divmod(i, cols)
        x = c * (cw + gap)
        y = r * (ch + label_h + gap)
        canvas.paste(img, (x, y))
        draw.text((x + 12, y + ch + 6), labels[i], fill=(230, 230, 235), font=f)
    canvas.save(out)


def annotate_regions(base: Path, out: Path,
                     regions: list[tuple[str, tuple[int, int, int, int], tuple]]):
    img = Image.open(base).convert("RGB")
    draw = ImageDraw.Draw(img)
    f = font(30)
    for label, (x0, y0, x1, y1), color in regions:
        for wpx in range(4):
            draw.rectangle((x0 - wpx, y0 - wpx, x1 + wpx, y1 + wpx), outline=color)
        tw = draw.textlength(label, font=f)
        draw.rectangle((x0, y0, x0 + tw + 20, y0 + 44), fill=color)
        draw.text((x0 + 10, y0 + 4), label, fill=(0, 0, 0), font=f)
    img.save(out)


# --- shot groups ---

def shots_empty_window(only):
    """tour-01 (first launch), tour-02 (region overlay), tour-03 (menus),
    tour-04 (viewer colors) — all from one fresh empty-scene window."""
    if not any(k in only for k in ("01", "02", "03", "04")):
        return
    cap = Capture()
    try:
        cap.camera(45, 25, 500)
        if "01" in only or "02" in only:
            cap.window_png(OUT_DIR / "tour-01-first-launch.png")

        if "02" in only:
            pixmap_dpr = cap.win.grab().devicePixelRatio()
            regions = [("Viewer", cap.region_rect(cap.vp, pixmap_dpr), (120, 200, 255))]
            for dock in cap.win.findChildren(QDockWidget):
                if not dock.isVisible():
                    continue
                title = dock.windowTitle()
                color = (255, 200, 90) if title == "Properties" else (170, 255, 140)
                regions.append((title, cap.region_rect(dock, pixmap_dpr), color))
            bars = [tb for tb in cap.win.findChildren(QToolBar) if tb.isVisible()]
            if bars:
                rects = [cap.region_rect(tb, pixmap_dpr) for tb in bars]
                merged = (min(r[0] for r in rects), min(r[1] for r in rects),
                          max(r[2] for r in rects), max(r[3] for r in rects))
                regions.append(("Manipulate + Camera toolbars", merged, (255, 140, 200)))
            annotate_regions(OUT_DIR / "tour-01-first-launch.png",
                             OUT_DIR / "tour-02-window-regions.png", regions)

        if "03" in only:
            menu_pngs, labels = [], []
            for act in list(cap.win.menuBar().actions()):
                name = act.text().replace("&", "")
                if name not in ("File", "View"):
                    continue
                menu = act.menu()
                if menu is None:
                    continue
                menu.popup(cap.win.mapToGlobal(QPoint(60, 60)))
                pump(0.25)
                pm = menu.grab()
                menu.hide()
                pump(0.1)
                p = RAW_DIR / f"menu_{name.lower()}.png"
                pm.toImage().save(str(p))
                menu_pngs.append(p)
                labels.append(f"{name} menu")
            if menu_pngs:
                side_by_side(menu_pngs, OUT_DIR / "tour-03-menus.png",
                             labels=labels, gap=40)

        if "04" in only:
            cap.camera(45, 25, 420)
            dark = RAW_DIR / "colors_dark.png"
            cap.viewport_png(dark)
            cap.win._on_scene_bg_toggle_bw()      # black -> white (B key path)
            world = cap.win._ensure_world_node()
            world.ref_grid_color_r = 70            # slate blue reference grid
            world.ref_grid_color_g = 110
            world.ref_grid_color_b = 170
            cap.invalidate()
            light = RAW_DIR / "colors_light.png"
            cap.viewport_png(light)
            side_by_side([dark, light], OUT_DIR / "tour-04-viewer-colors.png",
                         labels=["Default: dark background",
                                 "B key + Grid Color: white background, custom grid"])
    finally:
        cap.close()


def shots_build_sequence(only):
    """tour-05 .. tour-11: the tour's cumulative build-up, replayed through
    the same handlers N / Shift+N / Delete drive."""
    if not any(k in only for k in ("05", "06", "07", "08", "09", "10", "11")):
        return
    cap = Capture()
    try:
        # The tour has the reader set New Object Defaults > Topology to None
        # (the panel's Point default places children spherically — angles,
        # not offsets — which is section 12's subject, not section 8's).
        combo = cap.win._new_topo
        combo.setCurrentIndex(max(combo.findData(0), 0))   # TOPO_NONE
        pump(0.05)

        # -- 05: three roots (N, N, N) --
        for _ in range(3):
            cap.new_root()
        cap.select(1)
        cap.camera(70, 18, 32, target=(10.0, 0.0, 1.0))
        if "05" in only:
            cap.viewport_png(OUT_DIR / "tour-05-first-objects.png")

        # -- 06: fly close to node 1, selected, full window with panels --
        cap.select(1)
        cap.vp.focus_on_node(cap.node(1))
        # Scroll the Properties panel to the Selected Node group — that's
        # the part of the panel this tour step is talking about.
        scroll = next((s for s in cap.win.findChildren(QScrollArea)
                       if s.isAncestorOf(cap.win._insp_grp)), None)
        if scroll is not None:
            grp_y = cap.win._insp_grp.mapTo(scroll.widget(), QPoint(0, 0)).y()
            scroll.verticalScrollBar().setValue(max(0, grp_y - 8))
            scroll.horizontalScrollBar().setValue(0)
        pump(0.15)
        if "06" in only:
            cap.window_png(OUT_DIR / "tour-06-selection.png")

        # -- 07: geometry contact sheet on node 1 --
        if "07" in only:
            frames, labels = [], []
            for geo in CONTACT_GEOS:
                cap.node(1).geometry = geo
                cap.invalidate()
                cap.vp.focus_on_node(cap.node(1))
                pump(0.05)
                p = RAW_DIR / f"geo_{geo}.png"
                cap.viewport_png(p)
                frames.append(p)
                labels.append(GEO_NAMES[geo])
            grid_sheet(frames, labels, OUT_DIR / "tour-07-geometry-cycle.png",
                       cols=4, crop_square=True)
        cap.node(1).geometry = GEO_OCTA
        cap.invalidate()

        # -- 08: children of node 1 (Shift+N x5; parent stays selected) --
        cap.select(1)
        for _ in range(5):
            cap.new_child()
        cap.select(1)
        cap.camera(65, 22, 34, target=(10.0, 0.0, 3.0))
        if "08" in only:
            cap.viewport_png(OUT_DIR / "tour-08-children-row.png")

        # -- 09: grandchildren + great-grandchildren --
        first_child = min(n.id for n in cap.win.nodes if n.parent_id == 1)
        cap.select(first_child)
        for _ in range(3):
            cap.new_child()
        gc = min(n.id for n in cap.win.nodes if n.parent_id == first_child)
        cap.select(gc)
        for _ in range(2):
            cap.new_child()
        cap.select(1)
        # The Shift+N tree grows in the x-z plane — view it near side-on so
        # the branch levels stack as visible rows.
        cap.camera(100, 12, 30, target=(8.0, 0.0, 7.0))
        if "09" in only:
            cap.viewport_png(OUT_DIR / "tour-09-branching-tree.png")

        # -- 10: delete the first child's subtree, before/after --
        if "10" in only:
            before = RAW_DIR / "delete_before.png"
            cap.viewport_png(before)
            cap.select(first_child)
            cap.win._delete_selected()
            pump(0.1)
            after = RAW_DIR / "delete_after.png"
            cap.viewport_png(after)
            side_by_side([before, after], OUT_DIR / "tour-10-delete-subtree.png",
                         labels=["Before: mid-level node selected",
                                 "After Delete: node AND its whole subtree gone"])

    finally:
        cap.close()


def shots_transform(only):
    """tour-11: a clean parent + two children, then the parent rotated and
    scaled \u2014 children carried along. Own window so nothing else distracts."""
    if "11" not in only:
        return
    cap = Capture()
    try:
        combo = cap.win._new_topo
        combo.setCurrentIndex(max(combo.findData(0), 0))   # TOPO_NONE
        cap.new_root()
        cap.select(1)
        cap.new_child()
        cap.new_child()
        cap.select(1)
        cap.camera(60, 22, 20, target=(2.0, 0.0, 3.0))
        frame_a = RAW_DIR / "xform_before.png"
        cap.viewport_png(frame_a)
        n1 = cap.node(1)
        n1.rotate_z = 45.0
        n1.scale_x = n1.scale_y = n1.scale_z = 1.6
        cap.invalidate()
        frame_b = RAW_DIR / "xform_after.png"
        cap.viewport_png(frame_b)
        side_by_side([frame_a, frame_b],
                     OUT_DIR / "tour-11-parent-child-transform.png",
                     labels=["Parent + two children at rest",
                             "Parent rotated 45\u00b0 and scaled \u00d71.6 \u2014 children carried along"])
    finally:
        cap.close()


def shots_topology(only):
    """tour-12: one parent, 12 children, four topologies."""
    if "12" not in only:
        return
    cap = Capture()
    try:
        cap.new_root()
        cap.select(1)
        for _ in range(12):
            cap.new_child()
        # Same layout as Channel_Parameters_Example's topo station: a big
        # translucent wire shell with 12 small solid children spread over
        # lon 0..330 at four latitudes — proven to read well on every
        # topology in the cycle.
        parent = cap.node(1)
        parent.scale_x = parent.scale_y = parent.scale_z = 9.0
        parent.color_r, parent.color_g, parent.color_b = 120, 120, 140
        parent.color_a = 70
        kids = [n for n in cap.win.nodes if n.parent_id == 1]
        for i, k in enumerate(kids):
            k.translate_x = i * 30.0
            k.translate_z = 0.0
            k.scale_x = k.scale_y = k.scale_z = 0.28
            k.color_r, k.color_g, k.color_b = 255, 140, 90
            k.geometry = GEO_SPHERE_WIRE + 1        # solid sphere
        frames, labels = [], []
        cap.vp.show_grid = False
        cap.vp.show_axes = False
        for topo, label, shell_geo in TOPO_GRID:
            # translate_y is angular (degrees) on Sphere/Torus but a linear
            # local height on Cylinder/Spiral — keep the latter compact or
            # the parent's x9 scale flings children far off-camera.
            angular = topo in (TOPO_SPHERE, TOPO_TORUS)
            for i, k in enumerate(kids):
                k.translate_y = ((i % 4) * 25.0 - 30.0) if angular \
                    else ((i % 4) * 0.6 - 0.9)
            parent.topo = topo
            parent.geometry = shell_geo
            cap.invalidate()
            cap.camera(55, 22, 47, target=(0.0, 0.0, 0.0))
            p = RAW_DIR / f"topo_{topo}.png"
            cap.viewport_png(p)
            frames.append(p)
            labels.append(label)
        grid_sheet(frames, labels, OUT_DIR / "tour-12-topology-cycle.png",
                   cols=2, crop_square=True)
    finally:
        cap.close()


def shots_topology_example(only):
    """tour-12b: the shipped Topology_Example scene, tags on."""
    if "12b" not in only:
        return
    cap = Capture()
    try:
        csv = REPO_ROOT / "examples" / "Topology_Example" / "topology_example_gv_node.csv"
        if not cap.win._load_csv_path(str(csv)):
            print(f"  !! could not load {csv}")
            return
        cap.vp.show_tags = True
        pump(0.3)
        # Frame a handful of stations (Cube..Pin, x -90..-42 at 12-unit
        # spacing) rather than the whole -102..102 row.
        cap.camera(105, 15, 34, target=(-66.0, 0.0, 2.0))
        cap.viewport_png(OUT_DIR / "tour-12b-topology-example.png")
    finally:
        cap.close()


ALL_KEYS = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11",
            "12", "12b"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", default=None,
                        help="Shot numbers to (re)capture, e.g. --only 05 12b")
    parser.add_argument("--keep-raw", action="store_true",
                        help="Keep the _raw/ per-frame captures for debugging.")
    args = parser.parse_args()
    only = set(args.only) if args.only else set(ALL_KEYS)
    # tour-02 annotates tour-01's capture, so 02 implies 01's grab
    if "02" in only:
        only.add("01")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841

    shots_empty_window(only)
    shots_build_sequence(only)
    shots_transform(only)
    shots_topology(only)
    shots_topology_example(only)

    made = sorted(p.name for p in OUT_DIR.glob("tour-*.png"))
    print(f"Wrote {len(made)} shots to {OUT_DIR}:")
    for name in made:
        print(f"  {name}")
    if not args.keep_raw:
        for p in RAW_DIR.glob("*.png"):
            p.unlink()
        try:
            RAW_DIR.rmdir()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
