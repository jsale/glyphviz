"""
gvscene — a thin scene builder for script-authored GlyphViz examples.

Wraps glyphviz_core's Node/save_node_csv with the bookkeeping every generator
would otherwise repeat: id allocation, parent/branch_level tracking, the World
row, and the two folder conventions a mesh scene depends on.

Those conventions are the reason this module exists rather than a pile of
dict literals. A scene folder looks like:

    My_Example/
        my_example_gv_node.csv
        my_example_gv_tag.csv      (written automatically when nodes have text)
        media/                     texture_id = 1-based index, sorted by name
        meshes/                    mesh_id    = 1-based index, sorted by name

Both indices are positional, so **the order files sort in is part of the
scene**. `SceneBuilder.register_mesh`/`register_texture` hand back the id a
name will get, and `finish()` checks the folder actually matches what the CSV
claims — an off-by-one here silently swaps a jet's wing for its canopy, which
is not a thing anyone enjoys debugging by eye.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # mesh_creation_lab/ -> repo root
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from glyphviz_core.csv_reader import save_node_csv          # noqa: E402
from glyphviz_core.geometry_data import GEO_MESH            # noqa: E402
from glyphviz_core.mesh_loader import SUPPORTED_EXTENSIONS  # noqa: E402
from glyphviz_core.node import (                            # noqa: E402
    NODE_TYPE_LINK, NODE_TYPE_WORLD, Node,
)

# The `type` an ordinary visible glyph carries. It is a CONVENTION, not an
# enum value with a name in node.py: types 0/1/6/7 are World/Camera/Grid/Link
# and everything else renders as a glyph, but every GlyphViz and ANTz example
# writes 5, so a script that writes anything else produces a file that looks
# subtly unlike the rest of the corpus. Writing 0 by mistake is worse than
# subtle -- NON_VISUAL_TYPES contains it, so the whole scene silently renders
# empty.
NODE_TYPE_GLYPH = 5

IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tga')


class SceneBuilder:
    """Accumulates Nodes, then writes the scene folder."""

    def __init__(self, folder, stem: str, *,
                 background=(8, 10, 16), tag_font_size: int = 11,
                 tag_rgb=(235, 240, 250), fog=None):
        self.folder = Path(folder)
        self.stem = stem
        self._nodes: list[Node] = []
        self._next_id = 1
        self._level: dict[int, int] = {}
        self._mesh_names: list[str] = []
        self._tex_names: list[str] = []
        self._pending_label: dict[int, tuple[str, bool]] = {}

        world = Node(
            id=0, type=NODE_TYPE_WORLD, parent_id=0, branch_level=0,
            translate_x=0.0, translate_y=0.0, translate_z=0.0,
            rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
            scale_x=1.0, scale_y=1.0, scale_z=1.0,
            color_r=background[0], color_g=background[1], color_b=background[2],
            color_a=255, geometry=0, hide=0, topo=0,
            tag_font_size=tag_font_size,
            tag_color_r=tag_rgb[0], tag_color_g=tag_rgb[1], tag_color_b=tag_rgb[2],
        )
        if fog:
            world.fog_enabled = 1
            world.fog_start, world.fog_end = float(fog[0]), float(fog[1])
        self._nodes.append(world)

    # -- asset ids ---------------------------------------------------------

    def register_mesh(self, filename: str) -> int:
        """Reserve *filename* in meshes/ and return the mesh_id it will load
        as. Names are kept and re-sorted at write time, so generators may
        register in whatever order suits them."""
        if filename not in self._mesh_names:
            self._mesh_names.append(filename)
        return sorted(self._mesh_names).index(filename) + 1

    def register_texture(self, filename: str) -> int:
        if filename not in self._tex_names:
            self._tex_names.append(filename)
        return sorted(self._tex_names).index(filename) + 1

    def mesh_id(self, filename: str) -> int:
        """The id *filename* will have — valid only once every mesh is
        registered, which is why generators call this at node-build time and
        register at the top."""
        return sorted(self._mesh_names).index(filename) + 1

    def texture_id(self, filename: str) -> int:
        return sorted(self._tex_names).index(filename) + 1

    # -- nodes -------------------------------------------------------------

    def add(self, *, parent=0, pos=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0),
            scale=1.0, color=(200, 200, 200), alpha=255, geometry=1,
            topo=0, mesh=None, texture=0, text="", pin_text=False,
            ratio=0.1, topo_scale=1.0, hide=0, node_type=None,
            rates=None, link="") -> Node:
        """Add one node. `mesh` may be a filename (resolved through the mesh
        folder index) or an int id; passing one sets geometry to GEO_MESH."""
        if isinstance(scale, (int, float)):
            scale = (scale, scale, scale)
        if isinstance(mesh, str):
            mesh_id, geometry = self.mesh_id(mesh), GEO_MESH
        elif isinstance(mesh, int):
            mesh_id, geometry = mesh, GEO_MESH
        else:
            mesh_id = 0
        if isinstance(texture, str):
            texture = self.texture_id(texture)

        nid = self._next_id
        self._next_id += 1
        level = 0 if parent == 0 else self._level.get(parent, 0) + 1
        self._level[nid] = level

        n = Node(
            id=nid,
            type=NODE_TYPE_GLYPH if node_type is None else int(node_type),
            parent_id=parent, branch_level=level,
            translate_x=float(pos[0]), translate_y=float(pos[1]),
            translate_z=float(pos[2]),
            rotate_x=float(rot[0]), rotate_y=float(rot[1]), rotate_z=float(rot[2]),
            scale_x=float(scale[0]), scale_y=float(scale[1]), scale_z=float(scale[2]),
            color_r=int(color[0]), color_g=int(color[1]), color_b=int(color[2]),
            color_a=int(alpha), geometry=int(geometry), hide=int(hide),
            topo=int(topo), ratio=float(ratio), topo_scale=float(topo_scale),
            texture_id=int(texture), mesh_id=int(mesh_id),
            text=text, link=link, show_text=1 if pin_text else 0,
        )
        if rates:
            for k, v in rates.items():
                setattr(n, k, float(v))
        # Inherit a label its (hidden) rig could not display — see rig().
        if not text and not hide and parent in self._pending_label:
            n.text, pinned = self._pending_label.pop(parent)
            n.show_text = 1 if pinned else 0
        self._nodes.append(n)
        return n

    def rig(self, *, pos=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0), scale=1.0,
            text="", pin_text=False) -> Node:
        """A hidden parent node carrying one model instance's position,
        rotation and size, with its `Model.assembly()` parts added under it.

        **`text` is deliberately not kept on this node.** A hidden node draws
        nothing, and the tag pass only labels nodes it draws — so a label
        written here is silently invisible, which cost an hour the first time.
        It is handed to the first visible child added under this rig instead,
        which puts it on the model where a reader expects it.
        """
        n = self.add(pos=pos, rot=rot, scale=scale, hide=1, geometry=0,
                     color=(96, 96, 96))
        if text:
            self._pending_label[n.id] = (text, pin_text)
        return n

    def link(self, a: Node | int, b: Node | int, *, color=(120, 140, 170),
             alpha=255, ratio=0.02, geometry=27, text="") -> Node:
        """A Link node (type 7) from A to B. A link's parent IS its A-end."""
        aid = a.id if isinstance(a, Node) else a
        bid = b.id if isinstance(b, Node) else b
        n = self.add(parent=aid, node_type=NODE_TYPE_LINK, color=color,
                     alpha=alpha, ratio=ratio, geometry=geometry, text=text)
        n.extras['child_id'] = bid
        return n

    # -- output ------------------------------------------------------------

    def finish(self, *, verbose=True) -> Path:
        """Write the node CSV and check the asset folders line up with it."""
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"{self.stem}_gv_node.csv"
        save_node_csv(self._nodes, str(path))

        self._verify('meshes', self._mesh_names, SUPPORTED_EXTENSIONS)
        self._verify('media', self._tex_names, IMAGE_EXTS)

        if verbose:
            glyphs = sum(1 for n in self._nodes if n.type == NODE_TYPE_GLYPH)
            links = sum(1 for n in self._nodes if n.type == NODE_TYPE_LINK)
            print(f"  {path.name}: {glyphs} glyphs, {links} links, "
                  f"{len(self._mesh_names)} meshes, {len(self._tex_names)} textures")
        return path

    def _verify(self, sub: str, expected: list[str], exts) -> None:
        """Assert the on-disk folder yields exactly the ids the CSV assumes.

        Positional ids are unforgiving: one stray file sorting early shifts
        every id after it, and the scene still opens -- wearing the wrong
        shapes. Better to fail here, next to the generator that can fix it."""
        if not expected:
            return
        folder = self.folder / sub
        if not folder.is_dir():
            raise FileNotFoundError(
                f"{self.stem}: {sub}/ is missing but the scene names "
                f"{len(expected)} file(s) in it")
        on_disk = sorted(p.name for p in folder.iterdir()
                         if p.is_file() and p.suffix.lower() in exts)
        want = sorted(expected)
        if on_disk != want:
            extra = [n for n in on_disk if n not in want]
            missing = [n for n in want if n not in on_disk]
            raise AssertionError(
                f"{self.stem}: {sub}/ does not match the scene.\n"
                f"  missing: {missing or 'none'}\n"
                f"  unexpected: {extra or 'none'}\n"
                f"  (ids are positional, so an extra file shifts every id after it)")
