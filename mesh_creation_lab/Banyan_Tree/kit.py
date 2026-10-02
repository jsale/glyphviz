"""
kit — deferred scene assembly for the Banyan Tree generator.

`SceneBuilder` hands out a mesh_id only once every mesh file is registered,
because ids are positions in the sorted meshes/ folder. A scene this size is
far easier to write as "build a thing, place it, move on", so `Kit` records
every placement as a spec and writes the nodes in one pass at the end, after
all files exist.

It also owns the two placement rules the mesh importer forces on a generator:

* a mesh built in WORLD coordinates (the school's walls, the terrain) becomes
  a node at its own bounding-box centre with scale = its radius, which puts it
  back exactly where it was built;
* a mesh built in LOCAL coordinates (a chair, origin at its footprint) is
  placed by `place(pos, yaw)`, which offsets the node by the rotated
  bounding-box centre so the piece's origin lands on `pos`.

And one rendering rule: specs marked `translucent` (roof, glass, water) are
written AFTER every opaque node. GlyphViz draws in file order with depth
writes on and no sorting, so a translucent surface drawn first would hide
everything behind it rather than letting it show through.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import meshkit as mk


def _yaw(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


@dataclass
class Spec:
    key: int
    parent: int | None
    kwargs: dict
    translucent: bool = False


class Kit:
    def __init__(self, mesh_dir: Path):
        self.mesh_dir = Path(mesh_dir)
        self.meshes: dict[str, mk.Mesh] = {}
        self.placements: dict[str, mk.Placement] = {}
        self.textures: set[str] = set()
        self.specs: list[Spec] = []
        self.tris = 0

    # -- meshes ------------------------------------------------------------

    def mesh(self, fname: str, mesh: mk.Mesh) -> str:
        """Register a mesh file (written immediately). Returns the name."""
        if fname in self.meshes:
            return fname
        if len(mesh) == 0:
            raise ValueError(f"{fname}: empty mesh")
        mesh.save_obj(self.mesh_dir / fname)
        self.meshes[fname] = mesh
        self.placements[fname] = mesh.placement()
        self.tris += len(mesh)
        return fname

    def _spec(self, parent, translucent=False, **kw) -> int:
        if isinstance(kw.get('texture'), str):
            self.textures.add(kw['texture'])
        k = len(self.specs)
        self.specs.append(Spec(k, parent, kw, translucent))
        return k

    # -- placement ---------------------------------------------------------

    def world(self, fname, mesh=None, *, color=(220, 220, 220), texture=0,
              alpha=255, text="", pin=False, translucent=None, hide=0):
        """A mesh built in scene metres, put back where it was built."""
        if mesh is not None:
            self.mesh(fname, mesh)
        pl = self.placements[fname]
        tr = alpha < 255 if translucent is None else translucent
        return self._spec(None, tr, pos=tuple(pl.center), scale=pl.radius,
                          mesh=fname, color=color, texture=texture, alpha=alpha,
                          text=text, pin_text=pin, hide=hide)

    def place(self, fname, pos, yaw=0.0, s=1.0, *, color=(200, 200, 200),
              texture=0, alpha=255, text="", pin=False, parent=None,
              translucent=None):
        """A local-coordinate mesh, its origin set on *pos*, turned by *yaw*.

        `s` may be a number or (sx, sy, sz) in the piece's own axes; node
        scale is then per axis, which the importer's single radius divisor
        accommodates because it is applied uniformly before the node's scale.
        """
        pl = self.placements[fname]
        sv = np.array([s, s, s] if np.isscalar(s) else s, float)
        off = _yaw(yaw) @ (pl.center * sv)
        p = np.asarray(pos, float) + off
        tr = alpha < 255 if translucent is None else translucent
        return self._spec(parent, tr, pos=tuple(p), rot=(0.0, 0.0, float(yaw)),
                          scale=tuple(sv * pl.radius), mesh=fname, color=color,
                          texture=texture, alpha=alpha, text=text, pin_text=pin)

    def rig(self, pos, yaw=0.0, s=1.0, *, text="", pin=False):
        """Hidden parent. Children use `place(..., parent=rig)` with pos in
        the rig's local metres (the rig's scale multiplies them)."""
        return self._spec(None, False, pos=tuple(pos), rot=(0.0, 0.0, float(yaw)),
                          scale=s, hide=1, geometry=0, color=(96, 96, 96),
                          text=text, pin_text=pin, _rig=True)

    # -- output ------------------------------------------------------------

    def emit(self, sb):
        """Write every spec through the SceneBuilder: opaque first."""
        for f in self.meshes:
            sb.register_mesh(f)
        for t in sorted(self.textures):
            sb.register_texture(t)
        ids: dict[int, int] = {}
        order = ([s for s in self.specs if not s.translucent]
                 + [s for s in self.specs if s.translucent])
        for s in order:
            kw = dict(s.kwargs)
            parent = ids[s.parent] if s.parent is not None else 0
            if kw.pop('_rig', False):
                node = sb.rig(pos=kw['pos'], rot=kw['rot'], scale=kw['scale'],
                              text=kw.get('text', ''), pin_text=kw.get('pin_text', False))
            else:
                node = sb.add(parent=parent, **kw)
            ids[s.key] = node.id
        return ids
