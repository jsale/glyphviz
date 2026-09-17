#!/usr/bin/env python3
"""
export_frame.py
================
Render a GlyphViz node CSV to a PNG, headlessly — no window is ever shown.
Built for reproducible tutorial/doc screenshots, visual regression baselines,
and — the reason it grew a contact sheet and a report — letting whoever is
iterating on a scene *see* it without opening the app and grabbing the screen
by hand.

Camera framing defaults to the same bounding-box auto-fit Viewport.set_nodes()
already computes for the desktop app; pass --azimuth/--elevation/--distance/
--target to override any of them individually.

Usage:
    python tools/export_frame.py --csv scene.csv --out frame.png
    python tools/export_frame.py --csv scene.csv --out sheet.png \
        --angles three-quarter,front,top
    python tools/export_frame.py --csv scene.csv --out frame.png --report
    python tools/export_frame.py --csv scene.csv --out frame.png \
        --width 1920 --height 1080 --azimuth 30 --elevation 20 --distance 80

--angles renders several viewpoints into one labelled contact sheet, which is
what makes a single image enough to judge a 3D scene: a glyph that reads fine
from one angle is routinely wrong from another, and one file is one paste.

--report prints what a picture cannot tell you and a number can — scene
extents, rendered-size ranges per hierarchy level, how far each parent's
children actually sit from it, and whether the textures loaded. Most
"I thought this was right and it isn't" gaps show up there first.

WHAT THIS RENDERS, EXACTLY
--------------------------
The real Viewport, so geometry, topology placement, color and textures are
the app's own. Two things are *choices* rather than fidelity, and both match
how the app opens a file: tags are off unless you pass --tags (the app starts
with labels hidden and T toggles them; nodes with show_text=1 pin themselves
on either way), and Global Scale is 1.0 unless you pass --base-scale.
"""
import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Force devicePixelRatio 1 for headless rendering, BEFORE Qt is imported —
# these are read once, when QApplication is constructed.
#
# The tag overlay is a QPainter in logical widget coordinates while
# export_png() grabs a DPR-scaled framebuffer, and on a fractional-DPI display
# the two disagree: on a 1.25 display a label anchored beside its glyph landed
# 157 px above it (measured), and long captions went off-screen entirely. The
# glyphs themselves were always in the right place, which is what made it so
# misleading — the picture looked authoritative and the labels lied. With DPR
# pinned to 1 the same label lands 8 px from its glyph, where the app puts it.
#
# Safe to do at import: Qt ignores these once a QApplication exists, and
# nothing in the running application imports this module.
for _var, _val in (("QT_ENABLE_HIGHDPI_SCALING", "0"),
                   ("QT_SCALE_FACTOR", "1"),
                   ("QT_AUTO_SCREEN_SCALE_FACTOR", "0")):
    os.environ.setdefault(_var, _val)

from PySide6.QtWidgets import QApplication

from glyphviz_core.csv_reader import load_node_csv


# (name, azimuth, elevation) — elevation 89 rather than 90 because a camera
# exactly on the pole has no defined up-vector.
ANGLE_PRESETS = {
    "three-quarter": (45.0, 25.0),
    "front": (0.0, 0.0),
    "back": (180.0, 0.0),
    "side": (90.0, 0.0),
    "top": (0.0, 89.0),
    "bottom": (0.0, -89.0),
}


def _build_viewport(csv_path, base_scale, show_grid, show_axes, show_tags,
                    media_folder, width, height):
    """Load the scene into a real (never shown) Viewport, textures included.

    Ordering matters: load_texture_folder() calls makeCurrent(), which is a
    no-op on a QOpenGLWidget whose context does not exist yet, and
    TextureManager.load_folder() then returns 0 *silently*. Grabbing one
    throwaway frame first creates the context, so textures actually upload.
    Without this the whole scene renders untextured and nothing says so —
    which is worse than not rendering at all, because the picture looks
    plausible.
    """
    from glyphviz_gl.viewport import Viewport   # deferred: needs QApplication

    nodes = load_node_csv(csv_path)
    vp = Viewport()
    vp.base_scale = base_scale
    vp.show_grid = show_grid
    vp.show_axes = show_axes
    vp.show_tags = show_tags
    # --tags means every tagged node, not "the selection" — a headless export
    # never has one, and the app's default scopes tags to it.
    vp.show_tags_selected_only = False

    # Size first, so set_nodes() auto-frames against the aspect ratio the
    # image will actually have, then one throwaway grab to create the context.
    vp.resize(max(1, width), max(1, height))
    vp.grabFramebuffer()          # force context creation — see docstring
    media = (Path(media_folder) if media_folder
             else Path(csv_path).resolve().parent / "media")
    textures = vp.load_texture_folder(media) if media.is_dir() else 0

    # Imported models, on the same folder convention the app uses when it
    # opens a scene (MainWindow._load_csv_path). Without this a GEO_MESH scene
    # renders every model as the sphere fallback -- and, exactly like the
    # untextured case above, says nothing about it.
    meshes = Path(csv_path).resolve().parent / "meshes"
    if meshes.is_dir():
        vp.load_mesh_folder(meshes)

    vp.set_nodes(nodes)   # auto-frames the camera from the scene's bounding box
    return vp, nodes, textures, media


def render_frame(
    csv_path: str,
    out_path: str,
    width: int = 1280,
    height: int = 720,
    base_scale: float = 1.0,
    azimuth: float | None = None,
    elevation: float | None = None,
    distance: float | None = None,
    target: tuple[float, float, float] | None = None,
    media_folder: str | None = None,
    show_grid: bool = True,
    show_axes: bool = True,
    show_tags: bool = False,
    angles: list[str] | None = None,
) -> None:
    """Load *csv_path*, frame it, and save a PNG to *out_path*.  Must be
    called with a QApplication already constructed (see main() below).

    With *angles*, saves one labelled contact sheet instead of one view.
    """
    vp, _nodes, _tex, _media = _build_viewport(
        csv_path, base_scale, show_grid, show_axes, show_tags,
        media_folder, width, height)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    if not angles:
        vp.set_camera(azimuth=azimuth, elevation=elevation,
                      distance=distance, target=target)
        vp.export_png(out_path, width, height)
        return

    _render_contact_sheet(vp, out_path, width, height, angles,
                          distance=distance, target=target)


def _render_contact_sheet(vp, out_path, width, height, angles,
                          distance=None, target=None):
    """One PNG holding each named view, captioned, laid out in a grid.

    Every pane keeps the auto-fitted distance unless one was given, so the
    panes are directly comparable — only the viewpoint changes between them.
    """
    from PIL import Image, ImageDraw, ImageFont

    unknown = [a for a in angles if a not in ANGLE_PRESETS]
    if unknown:
        raise SystemExit(
            f"unknown angle(s): {', '.join(unknown)}. "
            f"choose from: {', '.join(ANGLE_PRESETS)}")

    cols = min(len(angles), 3)
    rows = (len(angles) + cols - 1) // cols
    pane_w = max(1, width // cols)
    pane_h = max(1, height // rows)
    caption_h = max(18, pane_h // 22)

    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", caption_h - 6)
    except OSError:
        font = ImageFont.load_default()

    sheet = Image.new("RGB", (pane_w * cols, (pane_h + caption_h) * rows),
                      (12, 12, 18))
    draw = ImageDraw.Draw(sheet)

    tmp = Path(out_path).with_suffix(".pane.png")
    try:
        for i, name in enumerate(angles):
            az, el = ANGLE_PRESETS[name]
            vp.set_camera(azimuth=az, elevation=el,
                          distance=distance, target=target)
            vp.export_png(str(tmp), pane_w, pane_h)
            pane = Image.open(tmp).convert("RGB")
            x = (i % cols) * pane_w
            y = (i // cols) * (pane_h + caption_h)
            sheet.paste(pane, (x, y))
            pane.close()
            draw.text((x + 8, y + pane_h + 3),
                      f"{name}   azimuth {az:g}°, elevation {el:g}°",
                      fill=(190, 190, 205), font=font)
    finally:
        tmp.unlink(missing_ok=True)

    sheet.save(out_path)


# --------------------------------------------------------------- the report

def scene_report(csv_path: str, base_scale: float = 1.0,
                 media_folder: str | None = None) -> str:
    """Numbers a screenshot can't give you, for the scene as it will render.

    Everything here comes from the real transform engine, not from the CSV's
    authored columns — the whole point is that a node's *rendered* size and
    position are products of its whole ancestry, so reading the file back
    tells you what you wrote rather than what you will see.
    """
    import numpy as np

    from glyphviz_core import scene as scene_mod
    from glyphviz_core.node import NODE_TYPE_LINK, NON_VISUAL_TYPES
    from glyphviz_core.topology import TOPO_NAMES

    nodes = load_node_csv(csv_path)
    sc = scene_mod.Scene(nodes, base_scale)
    by_id = {n.id: n for n in nodes}
    lines = []

    def say(s=""):
        lines.append(s)

    visible = [n for n in nodes
               if not n.hide and n.type not in NON_VISUAL_TYPES]
    say(f"scene            {Path(csv_path).name}")
    say(f"nodes            {len(nodes)} total, {len(visible)} visible, "
        f"{sum(1 for n in nodes if n.hide)} hidden")
    kinds = {}
    for n in nodes:
        kinds[n.type] = kinds.get(n.type, 0) + 1
    say("types            " + ", ".join(f"{k}x{v}" for k, v in
                                        sorted(kinds.items())))
    say(f"Global Scale     {base_scale:g}  "
        f"(the app opens at 1.0; nothing in the CSV records this)")

    if visible:
        pts = np.array([sc.world_pos(n.id) for n in visible], dtype=float)
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        say(f"extents          x {lo[0]:.2f}..{hi[0]:.2f}   "
            f"y {lo[1]:.2f}..{hi[1]:.2f}   z {lo[2]:.2f}..{hi[2]:.2f}")
        say(f"                 size {hi[0] - lo[0]:.2f} x {hi[1] - lo[1]:.2f} "
            f"x {hi[2] - lo[2]:.2f}, centre "
            f"({(lo[0] + hi[0]) / 2:.2f}, {(lo[1] + hi[1]) / 2:.2f}, "
            f"{(lo[2] + hi[2]) / 2:.2f})")

        # Rendered size per level: authored scale is not what you see.
        say()
        say("rendered glyph size by branch_level "
            "(scale x every ancestor's scale x Global Scale)")
        say(f"  {'level':>5}  {'count':>6}  {'smallest':>10}  {'median':>10}  "
            f"{'largest':>10}")
        levels = {}
        for n in visible:
            m = np.asarray(scene_mod.node_world_matrix(n, sc))[:3, :3]
            r = float(np.linalg.norm(m, axis=0).max())
            levels.setdefault(n.branch_level, []).append(r)
        for lvl in sorted(levels):
            v = np.array(levels[lvl])
            say(f"  {lvl:>5}  {len(v):>6}  {v.min():>10.3f}  "
                f"{np.median(v):>10.3f}  {v.max():>10.3f}")

    # Topologies actually in use, and how far each kind throws its children.
    say()
    # A Link's parent_id is its A-end, not a hierarchy parent, so links must
    # not make every node they touch look like a parent of children.
    parents = {n.parent_id for n in nodes
               if n.parent_id in by_id and n.type != NODE_TYPE_LINK}
    if parents:
        say("parents, by topology — worst child distance in multiples of the "
            "parent's own radius")
        say("  (about 1 means children ride the parent's surface; a big "
            "number is the classic topo_scale mismatch)")
        by_kind = {}
        for pid in parents:
            p = by_id[pid]
            # A World Grid places children by lon/lat, not by its topo field.
            kind = "World Grid" if p.type == 6 else TOPO_NAMES.get(p.topo,
                                                                   str(p.topo))
            by_kind.setdefault(kind, []).append(pid)
        for kind in sorted(by_kind):
            ratio, worst = sc.worst_child_placement_ratio(by_kind[kind])
            tail = (f"worst {ratio:8.1f}x at node {worst}" if worst >= 0
                    else "no visible children")
            say(f"  {kind:<12} {len(by_kind[kind]):>5} parents   {tail}")

    # Textures: the silent failure this tool used to have itself.
    say()
    media = (Path(media_folder) if media_folder
             else Path(csv_path).resolve().parent / "media")
    wanted = sorted({n.texture_id for n in nodes if n.texture_id})
    if media.is_dir():
        files = sorted(p.name for p in media.iterdir() if p.is_file())
        say(f"media/           {len(files)} file(s): "
            f"{', '.join(files[:6])}{' ...' if len(files) > 6 else ''}")
    else:
        say(f"media/           none found at {media}")
    if wanted:
        say(f"texture_id used  {wanted}  "
            f"(1-based index into media/, images then videos)")
    else:
        say("texture_id used  none")

    pinned = sum(1 for n in nodes if n.show_text)
    labelled = sum(1 for n in nodes if (n.text or "").strip())
    say(f"labels           {labelled} nodes carry text, {pinned} pinned with "
        f"show_text=1 (the rest need T)")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[2])
    parser.add_argument("--csv", required=True, help="Node CSV to load.")
    parser.add_argument("--out", required=True, help="Output PNG path.")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--base-scale", type=float, default=1.0,
                        help="The app's Global Scale. Default 1.0, which is "
                             "what the app opens at.")
    parser.add_argument("--azimuth", type=float, default=None,
                        help="Camera azimuth in degrees. Default: auto bounding-box framing.")
    parser.add_argument("--elevation", type=float, default=None,
                        help="Camera elevation in degrees. Default: auto bounding-box framing.")
    parser.add_argument("--distance", type=float, default=None,
                        help="Camera distance. Default: auto bounding-box framing.")
    parser.add_argument("--target", type=float, nargs=3, default=None, metavar=("X", "Y", "Z"),
                        help="Camera look-at target. Default: auto bounding-box framing.")
    parser.add_argument("--angles", default=None,
                        help="Comma-separated viewpoints rendered into one "
                             "labelled contact sheet, e.g. "
                             "'three-quarter,front,top'. Choices: "
                             + ", ".join(ANGLE_PRESETS) + ".")
    parser.add_argument("--media-folder", default=None,
                        help="Folder of images/videos/GIFs for texture_id. "
                             "Default: auto-detect 'media' next to --csv.")
    parser.add_argument("--report", action="store_true",
                        help="Also print a numeric summary of the scene "
                             "(extents, rendered sizes per level, child "
                             "placement ratios, textures, labels).")
    parser.add_argument("--report-out", default=None,
                        help="Write the --report text to this file as well.")
    parser.add_argument("--no-grid", dest="show_grid", action="store_false")
    parser.add_argument("--no-axes", dest="show_axes", action="store_false")
    parser.add_argument("--tags", dest="show_tags", action="store_true",
                        help="Draw every label, as pressing T in the app does. "
                             "Off by default, matching how the app opens a "
                             "file; show_text=1 nodes pin themselves on "
                             "either way.")
    parser.add_argument("--no-tags", dest="show_tags", action="store_false",
                        help="Accepted for compatibility; this is the default.")
    parser.set_defaults(show_tags=False)
    args = parser.parse_args()

    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    render_frame(
        args.csv, args.out, args.width, args.height, args.base_scale,
        args.azimuth, args.elevation, args.distance,
        tuple(args.target) if args.target else None,
        args.media_folder, args.show_grid, args.show_axes, args.show_tags,
        [a.strip() for a in args.angles.split(",")] if args.angles else None,
    )
    print(f"Wrote {args.out}")

    if args.report or args.report_out:
        text = scene_report(args.csv, args.base_scale, args.media_folder)
        if args.report:
            print()
            print(text)
        if args.report_out:
            Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.report_out).write_text(text + "\n", encoding="utf-8")
            print(f"Wrote {args.report_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
