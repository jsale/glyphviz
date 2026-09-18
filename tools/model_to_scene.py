"""Turn a multi-material 3D model into a ready-to-open GlyphViz scene folder.

A downloaded OBJ is usually one file carrying a dozen materials, each with its
own texture. GlyphViz renders one geometry and one texture per node, so the
useful shape for such a model is not one node but a small hierarchy: a hidden
rig node holding the model's position and size, with one visible child per
material wearing its own mesh and its own image.

That is what this writes:

    <out>/
        <stem>_gv_node.csv     rig + one node per material
        meshes/                one OBJ per material, numbered so mesh_id is stable
        media/                 the diffuse images those nodes point at

Open the CSV in GlyphViz and the meshes/ and media/ folders are picked up
automatically, so the scene reopens and ships intact -- which a hand-imported
model does not.

The app can do this too (Meshes > Import Model with Materials...). This exists
for the case the app cannot cover: a model whose .mtl lost its textures, which
needs a second source to recover them from. See --maya-scene below.

Where the textures come from
----------------------------
In a well-formed model the .mtl says, per material, "map_Kd hull.png", and
that is all this needs. Real exports are frequently not well formed: a V-Ray
or Arnold scene keeps its shading in a node graph the .mtl format cannot
carry, so the exported .mtl arrives with no map_Kd at all and Kd 0 0 0 on
every material. The model is fine; only the material file is lossy.

Two recoveries are offered for that case, in order of authority:

  --maya-scene FILE   Read the .ma directly. Maya names each exported material
                      after its shadingEngine, which is exactly the usemtl
                      name in the OBJ, so the graph
                          file<N>.ftn -> file<N>.oc -> <shader>.dc -> <SG>.ss
                      recovers the true material-to-image assignment. It also
                      recovers flat colours, including VRayLightMtl's light
                      colour -- the glowing parts of the model.

  --textures DIR      Match on name: a material (or its shader) called
                      ShipMain takes a texture whose stem contains ShipMain
                      and reads as a colour map. Good enough when an author
                      names files after materials, which is common. It is a
                      guess, and the report says so per part.

Usage
-----
    python tools/model_to_scene.py MODEL.obj --out SCENE_DIR
        [--textures DIR] [--maya-scene FILE] [--name STEM] [--scale N]
        [--crease DEG] [--up-axis y|z] [--keep-overlaps] [--dry-run]

Overlapping copies
------------------
The same export habit that loses textures also tends to write the model out
more than once -- an object-level material assignment plus per-face-set ones
produces several coincident copies, which z-fight into a dense rib pattern and
bury the correctly-textured copy under a single wrong image. Those are removed
by default, keeping each surface once and reporting the count.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from glyphviz_core.csv_reader import save_node_csv                  # noqa: E402
from glyphviz_core.mesh_loader import (                             # noqa: E402
    DEFAULT_CREASE_ANGLE, load_mesh_parts,
)
from glyphviz_core.model_import import (                            # noqa: E402
    IMAGE_EXTS, build_nodes, folder_ids, index_textures, plan_model,
    safe_name, write_assets,
)


# --- Maya ASCII recovery ---------------------------------------------------

def maya_material_map(ma_path) -> dict[str, dict]:
    """{shadingEngine name: {shader, diffuse, color, emissive}} from a .ma.

    shadingEngine names are what Maya's OBJ exporter writes as usemtl, so this
    keys straight onto the parts load_mesh_parts returns.

    `diffuse` is the texture file name feeding the shader's colour input, when
    there is one; `color` is a flat RGB float triple for a shader that has
    none -- including VRayLightMtl, whose .cl is the light colour.
    """
    text = Path(ma_path).read_text(encoding='utf-8', errors='replace')

    # file node -> texture path as recorded on the author's machine
    file_tex: dict[str, str] = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r'createNode file -n "([^"]+)"', line)
        if m:
            cur = m.group(1)
            continue
        if cur:
            m = re.search(r'setAttr "\.ftn" -type "string" "([^"]+)"', line)
            if m:
                file_tex[cur] = m.group(1)
                cur = None

    # flat colour attributes per shader node: .dc (VRayMtl diffuse),
    # .cl (VRayLightMtl light colour), .c (lambert/blinn colour)
    node_color: dict[str, dict[str, tuple]] = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r'createNode (\w+) -n "([^"]+)"', line)
        if m:
            cur = m.group(2)
            node_color.setdefault(cur, {})
            continue
        if cur:
            m = re.search(r'setAttr "\.(dc|cl|c)" -type "float3" '
                          r'([-\d.e]+) ([-\d.e]+) ([-\d.e]+)', line)
            if m:
                node_color[cur][m.group(1)] = tuple(
                    float(m.group(i)) for i in (2, 3, 4))

    shader_in: dict[tuple, str] = {}
    sg_shader: dict[str, str] = {}
    for src, dst in re.findall(r'connectAttr "([^"]+)" "([^"]+)"', text):
        s_node = src.partition('.')[0]
        d_node, _, d_attr = dst.partition('.')
        if s_node in file_tex:
            shader_in[(d_node, d_attr)] = s_node
        if d_attr == 'ss':
            sg_shader[d_node] = s_node

    out: dict[str, dict] = {}
    for sg, shader in sg_shader.items():
        tex = None
        for attr in ('dc', 'c', 'color', 'diffuseColor'):
            f = shader_in.get((shader, attr))
            if f:
                tex = Path(file_tex[f].replace(chr(92), '/')).name
                break
        cols = node_color.get(shader, {})
        out[sg] = {
            'shader': shader,
            'diffuse': tex,
            'color': cols.get('dc') or cols.get('cl') or cols.get('c'),
            'emissive': 'cl' in cols,
        }
    return out


# --- main ------------------------------------------------------------------

def build(model: Path, out: Path, textures_dir: Path | None,
          maya_scene: Path | None, stem: str, rig_scale: float,
          crease: float, up_axis: str, keep_overlaps: bool,
          dry_run: bool) -> int:
    parts = load_mesh_parts(model, crease_angle=crease,
                            dedupe=not keep_overlaps)
    if not parts:
        print(f"{model.name}: no material split found -- this is a "
              f"single-material model, import it normally.")
        return 1

    overrides = maya_material_map(maya_scene) if maya_scene else {}
    textures = index_textures(textures_dir) if textures_dir else []
    if textures_dir:
        print(f"texture pool: {len(textures)} images under {textures_dir}")

    plan = plan_model(parts, model, textures, overrides)

    print()
    print(f"{'material':22s} {'faces':>7s} {'via':>9s}  texture / flat colour")
    for pp in plan.parts:
        shown = pp.texture.name if pp.texture is not None else f"-- {pp.color}"
        print(f"{pp.part.material:22s} {pp.part.face_count:7d} "
              f"{pp.via:>9s}  {shown}")
    print(f"\n{len(plan.parts)} parts, {plan.textured} textured, "
          f"{len(plan.images)} distinct images")

    dropped = sum(p.dropped_faces for p in parts)
    if dropped:
        kept = sum(p.face_count for p in parts)
        print(f"\noverlapping copies removed: {dropped:,} of {kept + dropped:,} "
              f"triangles drew a surface another material had already drawn "
              f"({kept:,} kept). Pass --keep-overlaps to import the file "
              f"exactly as authored.")
    if dry_run:
        return 0

    mesh_dir, media_dir = out / 'meshes', out / 'media'
    write_assets(plan, mesh_dir, media_dir)

    nodes = build_nodes(
        plan, first_id=1,
        mesh_ids=folder_ids(mesh_dir),
        texture_ids=folder_ids(media_dir, IMAGE_EXTS),
        rig_scale=rig_scale, up_axis=up_axis, label=model.stem,
    )

    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / f"{stem}_gv_node.csv"
    save_node_csv(nodes, str(csv_path))

    print(f"\nwrote {csv_path}")
    print(f"      {len(plan.parts)} meshes, {len(plan.images)} textures")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('model', type=Path, help='OBJ (or other supported model)')
    ap.add_argument('--out', type=Path, required=True, help='scene folder to write')
    ap.add_argument('--textures', type=Path, default=None,
                    help='folder of texture images (searched recursively)')
    ap.add_argument('--maya-scene', type=Path, default=None,
                    help='.ma file to recover material->texture assignment from')
    ap.add_argument('--name', default=None, help='CSV stem (default: model stem)')
    ap.add_argument('--scale', type=float, default=10.0, help='rig scale')
    ap.add_argument('--crease', type=float, default=DEFAULT_CREASE_ANGLE,
                    help='crease angle in degrees')
    ap.add_argument('--up-axis', choices=('y', 'z'), default='y',
                    help="the model's up axis (default y, as most DCC tools "
                         "export); GlyphViz is z-up, so y rotates the rig 90 "
                         "degrees about X")
    ap.add_argument('--keep-overlaps', action='store_true',
                    help='keep surfaces that several materials each draw; '
                         'by default the copy from the most specific '
                         'material is kept and the rest dropped, since '
                         'overlapping copies z-fight into a rib pattern')
    ap.add_argument('--dry-run', action='store_true',
                    help='report the material/texture match and write nothing')
    a = ap.parse_args(argv)

    if not a.model.is_file():
        print(f"no such model: {a.model}")
        return 2
    stem = a.name or safe_name(a.model.stem).lower()
    return build(a.model, a.out, a.textures, a.maya_scene, stem,
                 a.scale, a.crease, a.up_axis, a.keep_overlaps, a.dry_run)


if __name__ == '__main__':
    raise SystemExit(main())
