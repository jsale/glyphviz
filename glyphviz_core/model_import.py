"""Turning a multi-material model file into GlyphViz scene structure.

mesh_loader.load_mesh_parts does the geometry half -- splitting one file into
one MeshPart per material. This module does the scene half: deciding which
image each part wears, writing the parts and images into the meshes/ and
media/ folders a scene ships with, and building the nodes that put them back
together.

Qt-free and GL-free, so the same code serves the app's importer, the
tools/model_to_scene.py command line, and the tests.

Why a hierarchy rather than one node
------------------------------------
GlyphViz renders one geometry and one texture per node. A model with twelve
materials therefore cannot be one node without throwing eleven of its images
away. Making it a hidden rig node with one visible child per material costs
the renderer nothing -- no new concept, no new column -- and buys the whole
node vocabulary for free: each part selects, recolours, gets a label, binds to
a Channels track and saves like anything else in the scene.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .geometry_data import GEO_MESH
from .mesh_loader import MeshPart
from .node import Node

# A visible, ordinary glyph. Spelled out deliberately: type=0 would land the
# node in NON_VISUAL_TYPES and the whole model would render as nothing.
NODE_TYPE_GLYPH = 5

IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.tga', '.bmp', '.tif', '.tiff')

# Substrings marking a texture as a COLOUR map rather than one of the other
# channels a PBR set ships. GlyphViz's fixed-function renderer samples exactly
# one image per node, so only the colour map has anywhere to go.
DIFFUSE_HINTS = ('diffuse', 'basecolor', 'base_color', 'albedo', 'color', 'col')
NON_DIFFUSE_HINTS = ('normal', 'bump', 'height', 'displace', 'gloss', 'rough',
                     'metal', 'spec', 'reflect', 'ior', 'ao', 'occlusion',
                     'emissive', 'opacity', 'alpha', 'mask')

# A textured node MULTIPLIES its colour into the texture (GL_MODULATE), so a
# faithful texture needs white. Using the material's own Kd here is the
# mistake that renders a bark-textured tree black.
TEXTURED_TINT = (255, 255, 255)

# Fallback for a material with neither a usable texture nor a usable Kd.
NEUTRAL_GREY = (170, 170, 170)

# Most DCC tools (Maya, 3ds Max, Blender's OBJ export) write Y-up; GlyphViz is
# Z-up. Rotating the RIG by this about X stands a Y-up model up without
# touching a vertex, and leaves exactly one node to change if a given file
# turns out to be Z-up already.
Y_UP_RIG_ROTATION = 90.0


@dataclass
class PartPlan:
    """What one part will become: its image, its colour, and where it came from."""
    part: MeshPart
    texture: Path | None = None
    color: tuple[int, int, int] = NEUTRAL_GREY
    via: str = 'none'        # map_Kd | override | name | none
    mesh_file: str = ''      # file name written into meshes/


@dataclass
class ModelPlan:
    parts: list[PartPlan] = field(default_factory=list)

    @property
    def textured(self) -> int:
        return sum(1 for p in self.parts if p.texture is not None)

    @property
    def images(self) -> list[Path]:
        seen: dict[str, Path] = {}
        for p in self.parts:
            if p.texture is not None:
                seen.setdefault(p.texture.name, p.texture)
        return [seen[k] for k in sorted(seen)]


# --- texture matching ------------------------------------------------------

def index_textures(folder, recursive: bool = True) -> list[Path]:
    """Every image under *folder*, skipping dot-folders (tool caches such as
    Maya's .mayaSwatches and V-Ray's .vrayThumbs, which hold same-named
    thumbnails that would otherwise win a name match)."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    it = folder.rglob('*') if recursive else folder.iterdir()
    return sorted(
        p for p in it
        if p.is_file()
        and p.suffix.lower() in IMAGE_EXTS
        and not any(part.startswith('.') for part in p.parts)
    )


def looks_diffuse(path: Path) -> bool:
    stem = path.stem.lower()
    if any(h in stem for h in NON_DIFFUSE_HINTS):
        return False
    return any(h in stem for h in DIFFUSE_HINTS)


def match_by_name(names, textures: list[Path]) -> Path | None:
    """Best colour map for a material, matched on any of *names* in order.

    A guess, and treated as one by callers, but a well-founded one: authors
    overwhelmingly name a texture set after the material it dresses.
    """
    for name in names:
        if not name:
            continue
        key = str(name).lower()
        hits = [p for p in textures if key in p.stem.lower()]
        if not hits:
            continue
        pool = [p for p in hits if looks_diffuse(p)] or hits
        # Shortest stem wins: ShipMain_Diffuse beats ShipMain_Diffuse_old.
        return min(pool, key=lambda p: (len(p.stem), p.name))
    return None


def plan_model(parts: list[MeshPart], model_path,
               textures: list[Path] | None = None,
               overrides: dict | None = None) -> ModelPlan:
    """Decide each part's image and colour.

    Resolution order per part:
      1. the .mtl's own map_Kd, found in the texture pool or beside the model
      2. an explicit override -- {material: {'diffuse': name, 'color': rgb01,
         'emissive': bool, 'shader': name}} -- which is how a caller feeds in
         an assignment recovered from a DCC scene file whose .mtl lost it
      3. a name match against the texture pool

    A part with no image takes a flat colour: its override colour, else its Kd
    when that is not the black a renderer-specific exporter writes for every
    material, else neutral grey.
    """
    model_path = Path(model_path)
    textures = textures or []
    overrides = overrides or {}
    plan = ModelPlan()

    for p in parts:
        info = overrides.get(p.material, {})
        src: Path | None = None
        via = 'none'

        mtl_tex = p.spec.texture if p.spec else None
        if mtl_tex:
            cand = [t for t in textures if t.name.lower() == mtl_tex.lower()]
            if not cand:
                local = model_path.parent / mtl_tex
                cand = [local] if local.is_file() else []
            if cand:
                src, via = cand[0], 'map_Kd'

        if src is None and info.get('diffuse'):
            want = str(info['diffuse']).lower()
            cand = [t for t in textures if t.name.lower() == want]
            if cand:
                src, via = cand[0], 'override'

        if src is None and textures:
            src = match_by_name([info.get('shader', ''), p.material], textures)
            if src is not None:
                via = 'name'

        plan.parts.append(PartPlan(part=p, texture=src, via=via,
                                   color=_part_color(p, src, info)))
    return plan


def _part_color(part: MeshPart, src, info: dict) -> tuple[int, int, int]:
    if src is not None:
        return TEXTURED_TINT
    col = info.get('color')
    if col and max(col) > 0:
        if info.get('emissive'):
            # A light material is an emitter, which GlyphViz has no equivalent
            # for. Its hue at full brightness is the closest honest reading --
            # the glowing parts then read as glowing colour rather than as the
            # near-black paint their raw value would give.
            peak = max(col)
            col = tuple(c / peak for c in col)
        return tuple(int(round(max(0.0, min(1.0, c)) * 255)) for c in col)
    if part.spec and not part.spec.is_black:
        return part.spec.diffuse
    return NEUTRAL_GREY


# --- writing the scene's asset folders -------------------------------------

def safe_name(s: str) -> str:
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', str(s)).strip('_') or 'part'


def write_part_obj(mesh, path: Path) -> None:
    """Write one part as an OBJ carrying positions, UVs and faces.

    Normals are deliberately omitted: GlyphViz recomputes crease-angle normals
    on load (mesh_loader._crease_normals), which is better than whatever the
    source stored, and leaving them out keeps these files small.
    """
    out = [f"# GlyphViz part: {mesh.name}"]
    for v in mesh.vertices:
        out.append(f"v {v[0]:.6g} {v[1]:.6g} {v[2]:.6g}")
    uvs = mesh.uvs
    if uvs is not None:
        for t in uvs:
            out.append(f"vt {t[0]:.6g} {t[1]:.6g}")
    for f in mesh.faces:
        a, b, c = (int(i) + 1 for i in f)
        if uvs is not None:
            out.append(f"f {a}/{a} {b}/{b} {c}/{c}")
        else:
            out.append(f"f {a} {b} {c}")
    path.write_text('\n'.join(out) + '\n', encoding='utf-8')


def write_assets(plan: ModelPlan, mesh_dir: Path, media_dir: Path,
                 prefix: str = '') -> None:
    """Write every part into mesh_dir and copy its image into media_dir.

    Part files are numbered in plan order. That matters: mesh_id is a file's
    1-based position in the sorted folder, so numbering is what makes the ids
    this import writes into the CSV mean the same thing on the next machine
    that opens it.
    """
    mesh_dir.mkdir(parents=True, exist_ok=True)
    media_dir.mkdir(parents=True, exist_ok=True)

    for i, pp in enumerate(plan.parts):
        pp.mesh_file = f"{prefix}{i:02d}_{safe_name(pp.part.material)}.obj"
        write_part_obj(pp.part.mesh, mesh_dir / pp.mesh_file)

    for src in plan.images:
        dst = media_dir / src.name
        if not dst.exists():
            shutil.copy2(src, dst)


def folder_ids(folder: Path, exts=None) -> dict[str, int]:
    """{file name: 1-based id} exactly as the loaders number a folder.

    Read back from the folder as it now stands rather than predicted, because
    an import that inserts files renumbers whatever sorted after them.
    """
    if not folder.is_dir():
        return {}
    names = sorted(q.name for q in folder.iterdir()
                   if q.is_file() and (exts is None or q.suffix.lower() in exts))
    return {n: i + 1 for i, n in enumerate(names)}


def remap_ids(nodes, before: dict[str, int], after: dict[str, int],
              attr: str) -> int:
    """Re-point existing nodes after an asset folder gained files.

    Both mesh_id and texture_id are POSITIONS in a sorted folder, so inserting
    a file shifts every id at or after it -- silently re-skinning the scene or
    swapping its shapes. The file NAME is the stable identity, so ids are
    carried across by name. Returns how many nodes moved.
    """
    id_to_name = {v: k for k, v in before.items()}
    moved = 0
    for n in nodes:
        old = getattr(n, attr, 0)
        if not old:
            continue
        name = id_to_name.get(old)
        if name is None:
            continue
        new = after.get(name, old)
        if new != old:
            setattr(n, attr, new)
            moved += 1
    return moved


# --- nodes -----------------------------------------------------------------

def build_nodes(plan: ModelPlan, first_id: int, mesh_ids: dict[str, int],
                texture_ids: dict[str, int], *,
                position=(0.0, 0.0, 0.0), rig_scale: float = 10.0,
                up_axis: str = 'y', label: str = '',
                parent_id: int = 0, branch_level: int = 0) -> list[Node]:
    """The rig node and one child per part, ready to add to a scene.

    Node ids run from *first_id*. mesh_ids/texture_ids map a file name to the
    id its folder position gives it (see folder_ids).
    """
    nodes: list[Node] = []
    rig_id = first_id
    rig = Node(
        id=rig_id, type=NODE_TYPE_GLYPH, parent_id=parent_id,
        branch_level=branch_level,
        translate_x=float(position[0]), translate_y=float(position[1]),
        translate_z=float(position[2]),
        rotate_x=Y_UP_RIG_ROTATION if up_axis == 'y' else 0.0,
        rotate_y=0.0, rotate_z=0.0,
        scale_x=rig_scale, scale_y=rig_scale, scale_z=rig_scale,
        color_r=96, color_g=96, color_b=96, color_a=255,
        geometry=0, hide=1, topo=0,
    )
    nodes.append(rig)

    pending = label
    for i, pp in enumerate(plan.parts):
        tex = texture_ids.get(pp.texture.name, 0) if pp.texture is not None else 0
        n = Node(
            id=rig_id + 1 + i, type=NODE_TYPE_GLYPH, parent_id=rig_id,
            branch_level=branch_level + 1,
            translate_x=float(pp.part.translate[0]),
            translate_y=float(pp.part.translate[1]),
            translate_z=float(pp.part.translate[2]),
            rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
            # A part written as its own file is reloaded re-normalized onto
            # its OWN bounding box, discarding the shared model scale; the
            # part's radius in model units undoes exactly that. Leave it at 1
            # and every part arrives the same size -- a cockpit as large as
            # the hull around it.
            scale_x=pp.part.radius, scale_y=pp.part.radius, scale_z=pp.part.radius,
            color_r=pp.color[0], color_g=pp.color[1], color_b=pp.color[2],
            color_a=255,
            geometry=GEO_MESH, hide=0, topo=0,
            mesh_id=mesh_ids.get(pp.mesh_file, 0),
            texture_id=tex,
            text=pp.part.material,
        )
        if pending:
            # The rig is hidden, and the tag pass only labels what it draws,
            # so a label put on the rig is silently invisible. It goes on the
            # first part that is actually drawn instead.
            n.text = pending
            pending = ''
        nodes.append(n)

    return nodes
