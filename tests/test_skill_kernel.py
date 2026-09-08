"""The skill's vendored placement kernel must not drift from glyphviz_core.

`glyphviz-skill/code/gv_kernel/` holds byte-identical copies of the app's
placement math so a Claude session with no GlyphViz install can compute the
same answers the app renders. That guarantee is only worth anything if it is
enforced, because the failure mode is silent: the skill keeps returning
confident numbers that the app no longer agrees with.

Re-vendor with the loop at the bottom of this file's docstring:

    for f in node geometry_data topology link_geometry csv_reader scene; do
        cp glyphviz_core/$f.py glyphviz-skill/code/gv_kernel/$f.py
    done
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
CORE = REPO / "glyphviz_core"
KERNEL = REPO / "glyphviz-skill" / "code" / "gv_kernel"
CODE = KERNEL.parent
VENDORED = ["node.py", "geometry_data.py", "topology.py", "link_geometry.py",
            "csv_reader.py", "scene.py"]


@pytest.mark.parametrize("name", VENDORED)
def test_vendored_file_is_byte_identical(name):
    src, dst = CORE / name, KERNEL / name
    assert dst.exists(), f"{name} is missing from the skill kernel"
    assert dst.read_bytes() == src.read_bytes(), (
        f"glyphviz-skill/code/gv_kernel/{name} has drifted from "
        f"glyphviz_core/{name}. Re-copy it; do not hand-edit the vendored copy."
    )


def test_kernel_has_no_extra_python_files():
    """Only the vendored modules plus our own __init__ may live in the package."""
    found = sorted(p.name for p in KERNEL.glob("*.py"))
    assert found == sorted(VENDORED + ["__init__.py"]), found


def test_kernel_imports_without_the_repo_on_sys_path():
    """The skill runs standalone on claude.ai, so the package must not reach
    back into glyphviz_core."""
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, r'%s');"
         "import gv_kernel as k;"
         "assert 'glyphviz_core' not in sys.modules, 'kernel imported the repo package';"
         "print(len(k.__all__))" % CODE],
        capture_output=True, text=True, cwd=str(REPO.parent))
    assert out.returncode == 0, out.stderr
    assert int(out.stdout.strip()) >= 20


def _load(mod_name, path):
    spec = importlib.util.spec_from_file_location(mod_name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = m
    spec.loader.exec_module(m)
    return m


def test_kernel_and_core_agree_numerically(tmp_path):
    """Same scene, both engines, identical world transforms and draw matrices."""
    from glyphviz_core.csv_reader import load_node_csv as core_load
    from glyphviz_core.topology import compute_world_transforms as core_xf
    from glyphviz_core.scene import Scene as CoreScene, node_world_matrix as core_mat

    sys.path.insert(0, str(CODE))
    try:
        import gv_kernel as k
    finally:
        sys.path.remove(str(CODE))

    hdr = ("id,type,parent_id,branch_level,translate_x,translate_y,translate_z,"
           "rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,"
           "color_r,color_g,color_b,color_a,geometry,hide,topo,ratio,rotation_mode")
    rows = [
        "1,5,0,0,0,0,0,0,0,0,2,2,2,200,200,200,255,3,0,2,0.1,0",
        "2,5,1,1,45,30,0.5,0,0,0,0.4,0.4,0.4,200,200,200,255,3,0,3,0.15,0",
        "3,5,2,2,90,0,0,15,0,25,0.3,0.3,0.9,200,200,200,255,19,0,5,0.1,0",
        "4,5,3,3,1,0,0,0,0,0,0.2,0.2,0.2,200,200,200,255,16,0,6,0.1,0",
        "5,5,0,0,20,0,0,0,0,0,1,1,4,200,200,200,255,1,0,14,0.1,0",
    ]
    p = tmp_path / "kernel_check_gv_node.csv"
    p.write_text(hdr + "\r\n" + "\r\n".join(rows) + "\r\n", encoding="utf-8", newline="")

    a, b = core_load(str(p)), k.load_node_csv(str(p))
    assert [n.id for n in a] == [n.id for n in b]

    for base in (1.0, 3.0):
        ta, tb = core_xf(a, base), k.compute_world_transforms(b, base)
        np.testing.assert_allclose(ta.world_pos, tb.world_pos, atol=1e-12)
        np.testing.assert_allclose(ta.world_basis, tb.world_basis, atol=1e-12)
        for floor in (0.0, 0.2):
            sa, sb = CoreScene(a, base, floor), k.Scene(b, base, floor)
            for na, nb in zip(a, b):
                np.testing.assert_allclose(core_mat(na, sa), k.node_world_matrix(nb, sb),
                                           atol=1e-12)


def test_gv_extents_runs_and_finds_planted_faults(tmp_path):
    """The checker must catch the failures it advertises, on one scene."""
    hdr = ("id,type,parent_id,branch_level,translate_x,translate_y,translate_z,"
           "rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,"
           "color_r,color_g,color_b,color_a,geometry,hide,topo,ratio,rotation_mode,child_id")
    rows = [
        # a child fully inside a scale-3 sphere hub
        "1,5,0,0,0,0,0,0,0,0,3,3,3,200,200,200,255,3,0,0,0.1,0,0",
        "2,5,1,1,0.34,0,0.78,0,0,0,0.3,0.3,0.3,200,200,200,255,3,0,0,0.1,0,0",
        # degrees written into a Cartesian slot
        "3,5,0,0,40,0,0,0,0,0,1,1,1,200,200,200,255,3,0,0,0.1,0,0",
        "4,5,3,1,270,0,55,0,0,0,0.2,0.2,0.2,200,200,200,255,3,0,0,0.1,0,0",
        # alpha-0 pretending to be a carrier (parent topo is not an overlay)
        "5,5,0,0,110,0,0,0,0,0,1,1,1,200,200,200,0,3,0,0,0.1,0,0",
        # a link whose B-end does not exist
        "6,7,1,1,0,0,0,0,0,0,1,1,1,200,200,200,255,27,0,0,0.1,0,9999",
        # a small child near the hub's centre: completely swallowed
        "7,5,1,1,0.1,0,0,0,0,0,0.05,0.05,0.05,200,200,200,255,3,0,0,0.1,0,0",
    ]
    p = tmp_path / "faults_gv_node.csv"
    p.write_text(hdr + "\r\n" + "\r\n".join(rows) + "\r\n", encoding="utf-8", newline="")

    gx = _load("gv_extents_under_test", CODE / "gv_extents.py")
    r = gx.analyse(str(p), 1.0)
    # node 7 vanishes entirely; node 2's centre is inside but it still pokes out,
    # because a child inherits its parent's scale and so is bigger than authored.
    assert [b[0].id for b in r["buried"] if b[5] == "swallowed"] == [7]
    assert [b[0].id for b in r["buried"] if b[5] == "centre"] == [2]
    assert [f[0].id for f in r["flung"]] == [4]
    assert [n.id for n in r["degrees"]] == [4]
    assert [n.id for n in r["alpha_carriers"]] == [5]
    assert [n.id for n in r["dead_links"]] == [6]

    text = gx.report(r)
    assert "buried" not in text.lower() or "cannot be seen" in text
    assert text.isascii(), "the report must stay ASCII so it prints on any console"


def test_gv_extents_is_quiet_on_curated_examples():
    """A curated scene must not trip the checker, or the signal is worthless."""
    gx = _load("gv_extents_quiet", CODE / "gv_extents.py")
    scenes = sorted((CODE.parent / "examples").rglob("*_gv_node.csv"))
    assert scenes, "no skill examples found"
    noisy = []
    for s in scenes:
        r = gx.analyse(str(s), 1.0)
        hard = (len([b for b in r["buried"] if b[5] == "swallowed"])
                + len(r["flung"]) + len(r["sheared"])
                + len(r["alpha_carriers"]) + len(r["dead_links"]))
        if hard:
            noisy.append((s.name, hard))
    assert not noisy, f"checker reports problems on curated examples: {noisy}"


# ---------------------------------------------------------------------------
# The geometry table in gv_extents.py is measured, not vendored, so it needs
# its own guard. Every glyph is built to fit inside RADIUS 1, which is not the
# same as spanning -1..+1 per axis: a cube's faces stop at 1/sqrt(3), a Pin is
# a needle 0.1 wide, a flat square reaches 0.707. Getting that wrong makes
# every cube bar 15% too tall and every Pin ten times too thin, which is
# exactly the class of confident-wrong number the skill exists to prevent --
# so the table is re-measured here from the app's own display-list builders.
# ---------------------------------------------------------------------------

class _GLRecorder:
    """Stands in for the GL entry points, logging every call in order.

    Same trick as tests/test_interior_geometry.py: glyphviz_gl.geometry pulls
    the GL names into its own module namespace, so swapping the callables
    captures the exact vertex stream each builder emits, with no GL context.
    """

    def __init__(self):
        self.calls = []

    def install(self, monkeypatch, module):
        for name in dir(module):
            if not name.startswith("gl") or name.startswith("GL"):
                continue
            if not callable(getattr(module, name)):
                continue
            monkeypatch.setattr(module, name, self._stub(name), raising=False)

    def _stub(self, name):
        def fn(*args):
            self.calls.append((name,) + args)
            if name == "glGenLists":
                return 1
            if name == "glIsEnabled":
                return False
            if name == "gluNewQuadric":
                return object()
            return None
        return fn

    def bounds(self):
        v = [c[1:4] for c in self.calls if c[0] == "glVertex3f"]
        assert v, "builder emitted no vertices"
        return (max(abs(p[0]) for p in v), max(abs(p[1]) for p in v),
                min(p[2] for p in v), max(p[2] for p in v))


def test_gv_extents_local_box_matches_the_real_geometry_builders():
    geometry = pytest.importorskip("glyphviz_gl.geometry")
    from _pytest.monkeypatch import MonkeyPatch

    gx = _load("gv_extents_box", CODE / "gv_extents.py")

    # Only the builders that emit explicit vertices can be measured this way;
    # sphere, cone and cylinder are gluQuadric calls with documented radii
    # (r = 1, h = 2), covered by the constants assertion below.
    mp = MonkeyPatch()
    try:
        rec = _GLRecorder()
        rec.install(mp, geometry)
        cases = {
            1: lambda: geometry._draw_cube(True),
            7: lambda: geometry._draw_torus(True),
            9: lambda: geometry._draw_poly_solid(geometry._DODECA_VERTS,
                                                 geometry._DODECA_FACES),
            11: lambda: geometry._draw_tri_solid(geometry._OCTA_VERTS,
                                                 geometry._OCTA_FACES),
            13: lambda: geometry._draw_tri_solid(geometry._TETRA_VERTS,
                                                 geometry._TETRA_FACES),
            15: lambda: geometry._draw_tri_solid(geometry._ICOSA_VERTS,
                                                 geometry._ICOSA_FACES),
            16: lambda: geometry._draw_pin(True),
            21: lambda: geometry._draw_grid_solid(),
            24: lambda: geometry._draw_circle(),
            29: lambda: geometry._draw_cube_interior(),
        }
        for geo_id, build in cases.items():
            rec.calls.clear()
            build()
            hx, hy, zlo, zhi = rec.bounds()
            want = gx.LOCAL_BOX[geo_id]
            # Ratio-shaped glyphs carry their z half-extent in `ratio`; the
            # builder's default ratio is the table's stand-in value.
            if geo_id in gx.RATIO_SHAPED:
                zlo, zhi = want[2], want[3]
            assert np.allclose((hx, hy, zlo, zhi), want, atol=1e-3), (
                f"geometry {geo_id} measures {(hx, hy, zlo, zhi)} but "
                f"gv_extents.LOCAL_BOX says {want}")
    finally:
        mp.undo()

    # The quadric-built shapes, from the constants the builders are called with.
    from glyphviz_core.geometry_data import (
        CYLINDER_RADIUS_RATIO, CYLINDER_HEIGHT_RATIO, PIN_HEIGHT, PIN_RADIUS,
        GRID_HALF_EXTENT,
    )
    assert gx.LOCAL_BOX[3] == (1.0, 1.0, -1.0, 1.0), "sphere is r = 1"
    assert gx.LOCAL_BOX[19] == (CYLINDER_RADIUS_RATIO, CYLINDER_RADIUS_RATIO,
                                -CYLINDER_HEIGHT_RATIO / 2.0,
                                CYLINDER_HEIGHT_RATIO / 2.0)
    assert gx.LOCAL_BOX[16] == (PIN_RADIUS, PIN_RADIUS,
                                0.0, PIN_HEIGHT + PIN_RADIUS)
    assert np.allclose(gx.LOCAL_BOX[21][:2], GRID_HALF_EXTENT)


def test_gv_extents_local_box_covers_every_geometry():
    """A geometry added to the app must be added to the table, not defaulted."""
    from glyphviz_core.geometry_data import GEO_COUNT
    gx = _load("gv_extents_cover", CODE / "gv_extents.py")
    missing = [g for g in range(GEO_COUNT) if g not in gx.LOCAL_BOX]
    assert not missing, (
        f"gv_extents.LOCAL_BOX has no entry for geometry {missing}; add the "
        f"measured half-extents rather than letting it fall back to unit size")


def test_placement_radius_is_one_whatever_the_parent_geometry_draws():
    """The gap a Cube parent leaves under its children is real, and documented.

    A topology seats children on the parent's circumscribed sphere; the drawn
    body is inscribed in it. SKILL.md rule 3 states the 0.42 x parent-scale gap
    a cube leaves, so it has to keep being true.
    """
    from glyphviz_core.csv_reader import load_node_csv
    from glyphviz_core.scene import Scene, node_world_matrix
    from glyphviz_core.topology import compute_world_transforms
    import tempfile
    import math

    hdr = ("id,type,parent_id,branch_level,translate_x,translate_y,translate_z,"
           "rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,"
           "color_r,color_g,color_b,color_a,geometry,hide,topo\n")
    body = ("1,5,0,0,0,0,0,0,0,0,2,2,2,255,255,255,255,1,0,1\n"
            "2,5,1,1,0,0,0,0,0,0,0.3,0.3,0.3,255,0,0,255,3,0,0\n")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "cube_gv_node.csv"
        p.write_text(hdr + body, encoding="utf-8")
        nodes = load_node_csv(str(p))
        tr = compute_world_transforms(nodes, 1.0)
        scene = Scene(nodes, 1.0)
        child = tr.world_pos[tr.row_of_id[2]]
        face = node_world_matrix(nodes[0], scene)[0, 0] / math.sqrt(3.0)

    assert np.allclose(child, [2.0, 0.0, 0.0]), child
    assert np.isclose(face, 2.0 / math.sqrt(3.0))
    assert np.isclose(child[0] - face, 0.845, atol=1e-3)
