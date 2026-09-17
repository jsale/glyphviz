"""
Mirror symmetry in the mesh authoring toolkit (2026-09-17).

The bug this guards against shipped in two scenes and survived several
renders before a top-down screenshot caught it. Both the jet and the whale
placed their left/right pairs with `rot_z(-90 * side)` — which ROTATES the
left copy 180 degrees about the vertical rather than REFLECTING it. Anything
fore-and-aft asymmetric then points the wrong way: a swept wing sweeps forward
on one side, an aerofoil trails its round leading edge. The result is
rotationally symmetric, not mirror symmetric, and from most viewing angles it
reads as merely "a bit off" rather than as obviously broken — which is exactly
why it needs a test rather than an eye.

Two things are pinned:

  * `mirror_pair()` really does produce a reflection (the vertex set is
    invariant under x -> -x), and reverses winding while doing it — a
    reflection flips face normals, and the importer's crease pass reads a face
    normal from its winding, so a verbatim copy would shade as a dark hole
    beside its correctly-lit twin;
  * the two lab models that had the bug are symmetric as built.

The toolkit lives in mesh_creation_lab/ rather than tools/, so it is imported
by path here.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
LAB = REPO / 'mesh_creation_lab'

if LAB.is_dir() and str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))

pytestmark = pytest.mark.skipif(not LAB.is_dir(),
                                reason='mesh_creation_lab/ not present')

mk = pytest.importorskip('meshkit')


def _vertex_key(v, digits=4):
    return {tuple(row) for row in np.round(np.asarray(v, dtype=float), digits)}


def _is_mirror_symmetric(mesh) -> bool:
    v = np.asarray(mesh.vertices, dtype=float)
    if len(v) == 0:
        return True
    return _vertex_key(v) == _vertex_key(v * np.array([-1.0, 1.0, 1.0]))


# --- the helper itself ------------------------------------------------------

def _wedge() -> mk.Mesh:
    """A deliberately fore-and-aft asymmetric part sitting off-centre: the
    shape that makes a rotation and a reflection give different answers."""
    m = mk.Mesh('wedge')
    m.add_quad((1, 0, 0), (3, 0, 0), (2.5, 2, 0), (1.5, 1, 0))
    return m


def test_mirror_pair_is_a_reflection():
    out = mk.Mesh('out')
    mk.mirror_pair(out, _wedge(), mk.identity())
    assert _is_mirror_symmetric(out)


def test_a_negated_rotation_is_not_a_mirror():
    """The control: the technique that shipped the bug, shown failing. Without
    this the test above could pass for the wrong reason."""
    out = mk.Mesh('out')
    part = _wedge()
    for side in (-1, 1):
        out.extend(part, mk.rot_z(180 if side < 0 else 0))
    assert not _is_mirror_symmetric(out)


def test_mirror_reverses_winding():
    """A reflection flips face normals, so the copy must be re-wound or it
    shades inside-out next to its twin."""
    src = mk.Mesh('src')
    src.tri(src.vert((1, 0, 0)), src.vert((2, 0, 0)), src.vert((1, 1, 0)))

    out = mk.Mesh('out')
    out.extend(src)                     # untransformed: winding unchanged
    out.extend(src, mk.mirror_x())      # reflected: winding reversed

    v = out.vertices
    normals = []
    for a, b, c in out.faces:
        n = np.cross(v[b] - v[a], v[c] - v[a])
        normals.append(n / np.linalg.norm(n))
    # Both triangles face the same way; a verbatim copy would face opposite.
    assert np.allclose(normals[0], normals[1]), "mirrored winding not reversed"


def test_a_plain_rotation_keeps_winding():
    """Only NEGATIVE-determinant matrices flip; an ordinary rotation must not,
    or every rotated part would shade inside-out."""
    src = mk.Mesh('src')
    src.tri(src.vert((1, 0, 0)), src.vert((2, 0, 0)), src.vert((1, 1, 0)))
    out = mk.Mesh('out')
    out.extend(src, mk.rot_z(37))
    assert [tuple(f) for f in out.faces] == [(0, 1, 2)]


# --- the models that had the bug -------------------------------------------

@pytest.mark.parametrize('module,builder,parts', [
    ('build_jet', 'build_jet', None),
    ('build_whale', 'build_whale', ('fins', 'tail', 'belly')),
])
def test_lab_models_are_symmetric(module, builder, parts):
    """The jet whole, and the whale's fins/flukes/throat.

    The whale's BODY is deliberately excluded: it carries a slight swim curve
    (`_section(..., flex=...)`), so it is asymmetric on purpose. Every part
    that is supposed to be a mirrored pair is checked.
    """
    name = {'build_jet': 'Jet', 'build_whale': 'Whale'}[module]
    sys.path.insert(0, str(LAB / name))
    try:
        mod = pytest.importorskip(module)
        model = getattr(mod, builder)()
    finally:
        sys.path.remove(str(LAB / name))

    keys = parts if parts is not None else tuple(model.parts)
    for key in keys:
        mesh = model.parts.get(key)
        if mesh is None or not len(mesh):
            continue
        assert _is_mirror_symmetric(mesh), f'{module}:{key} is not mirror symmetric'
