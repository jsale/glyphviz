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
        # a Plot whose vertices are alpha 0: a reveal animation's rest state,
        # exempt from the carrier fault
        "8,5,0,0,-200,0,0,0,0,0,1,1,1,200,200,200,0,22,0,16,0.1,0,0",
        "9,5,8,1,0,0,0,0,0,0,0,0,0,200,200,200,0,1,0,0,0.1,0,0",
        "10,5,8,1,1,0,0,0,0,0,0,0,0,200,200,200,0,1,0,0,0.1,0,0",
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
    assert r["dark_surfaces"] == []           # no textured Surface in this scene

    text = gx.report(r)
    assert "buried" not in text.lower() or "cannot be seen" in text
    assert text.isascii(), "the report must stay ASCII so it prints on any console"


def test_gv_extents_seats_ring_children_on_the_tube(tmp_path):
    """A torus or Flat Ring has a hole: children are measured from its tube.

    Against the outer silhouette, a bead riding the tube (tube angle 90) read
    as 97% of the way out of a solid disc. Found by Dave Warner, 2026-10-21.
    """
    hdr = ("id,type,parent_id,branch_level,translate_x,translate_y,translate_z,"
           "rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,"
           "color_r,color_g,color_b,color_a,geometry,hide,topo,ratio,rotation_mode")
    bead = "{id},5,{p},1,{tx},{ty},{tz},0,0,0,0.05,0.05,0.05,200,200,200,255,3,0,0,0.1,0"
    rows = []
    for parent, geo in ((1, 7), (10, 33)):            # Torus, Flat Ring
        rows.append(f"{parent},5,0,0,{parent * 20},0,0,0,0,0,3,3,3,"
                    f"200,200,200,255,{geo},0,3,0.1,0")
        rows += [
            bead.format(id=parent + 1, p=parent, tx=0, ty=90, tz=0.2),   # clears the tube
            bead.format(id=parent + 2, p=parent, tx=45, ty=0, tz=-0.1),  # on its centreline
            bead.format(id=parent + 3, p=parent, tx=0, ty=180, tz=0.8),  # in the hole
        ]
    p = tmp_path / "rings_gv_node.csv"
    p.write_text(hdr + "\r\n" + "\r\n".join(rows) + "\r\n", encoding="utf-8", newline="")

    gx = _load("gv_extents_rings", CODE / "gv_extents.py")
    r = gx.analyse(str(p), 1.0)
    assert sorted((b[0].id, b[5]) for b in r["buried"]) == [
        (3, "swallowed"), (12, "swallowed")]
    assert all("tube" in b[6] for b in r["buried"])


def test_gv_extents_root_sweep_matches_all_pairs():
    """The x-sweep over root spheres must find exactly what all-pairs finds."""
    gx = _load("gv_extents_sweep", CODE / "gv_extents.py")
    rng = np.random.default_rng(7)
    n = 300
    centres = rng.uniform(-40, 40, size=(n, 3))
    radii = rng.uniform(0.2, 6.0, size=n)
    spheres = [(i, centres[i], float(radii[i]), 1) for i in range(n)]

    want, want_touch = [], 0
    for i in range(n):
        for j in range(i + 1, n):
            gap = float(np.linalg.norm(centres[i] - centres[j])) - radii[i] - radii[j]
            if gap < -min(radii[i], radii[j]):
                want.append((i, j, gap))
            elif gap < 0:
                want_touch += 1
    got, got_touch = gx._root_contacts(spheres)
    assert got_touch == want_touch
    assert sorted((a, b) for a, b, _ in got) == sorted((a, b) for a, b, _ in want)
    assert want, "the random scene should contain some overlaps to compare"


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
                + len(r["alpha_carriers"]) + len(r["dead_links"])
                + len(r["dark_surfaces"])
                + len(r["aim_fan"]))
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


# ---------------------------------------------------------------------------
# Aim. Which way a glyph POINTS is decided by placement, not rotate_*, and a
# position check cannot see it get this wrong: correctly placed rods can still
# be aimed into a flat fan. The checker's AIM section exists so a session with
# no render can answer the direction question with a number, and these pin the
# two halves of that -- the aim table it rests on, and the one fault it claims.
# ---------------------------------------------------------------------------

_AIM_HDR = ("id,type,parent_id,branch_level,translate_x,translate_y,translate_z,"
            "rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,"
            "color_r,color_g,color_b,color_a,geometry,hide,topo,ratio,"
            "rotation_mode\n")


def _spokes(tmp, topo, rot=(0.0, 0.0, 0.0), n=12, cartesian_positions=False):
    """n cylinder rods around one hub, written to a real CSV."""
    import math
    rows = [f"1,5,0,0,0,0,0,0,0,0,1,1,1,255,255,255,255,3,0,{topo},0.1,0"]
    for i in range(n):
        if cartesian_positions:
            a = math.radians(i * 360.0 / n)
            tx, ty, tz = 3 * math.cos(a), 3 * math.sin(a), 0.0
        else:
            tx, ty, tz = i * 360.0 / n, 0.0, 2.0
        rx, ry, rz = rot[0], rot[1], (rot[2] + i * 360.0 / n if rot[2] else rot[2])
        rows.append(f"{2 + i},5,1,1,{tx},{ty},{tz},{rx},{ry},{rz},"
                    f"0.2,0.2,2,110,160,220,255,19,0,0,0.1,0")
    p = tmp / "spokes_gv_node.csv"
    p.write_text(_AIM_HDR + "\n".join(rows) + "\n", encoding="utf-8")
    return p


def test_aiming_topologies_turn_a_childs_z_outward(tmp_path):
    """SKILL.md rule 12's central claim, measured: a Cylinder child of a Sphere
    or Point parent with every rotate field 0 points straight out."""
    gx = _load("gv_extents_aim", CODE / "gv_extents.py")
    for topo in (2, 7):                       # Sphere, Point
        r = gx.analyse(str(_spokes(tmp_path, topo)), 1.0)
        assert not r["aim_fan"], topo
        assert len(r["aim"]) == 12, topo
        tr = r["tr"]
        hub = tr.world_pos[tr.row_of_id[1]]
        for n, parent, z, dev, aims in r["aim"]:
            assert aims, f"topo {topo} should aim its children"
            assert dev == pytest.approx(0.0, abs=1e-9), "no rotation, no deviation"
            radial = tr.world_pos[tr.row_of_id[n.id]] - hub
            radial = radial / np.linalg.norm(radial)
            assert float(z @ radial) == pytest.approx(1.0, abs=1e-12), (
                f"topo {topo} node {n.id}: +Z is not the outward radial")


def test_zsphere_does_not_aim_and_the_table_says_so(tmp_path):
    """The exception that makes the table worth having: Zsphere pulls children
    to the centre and leaves their +Z alone."""
    gx = _load("gv_extents_zsphere", CODE / "gv_extents.py")
    assert 10 not in gx.AIMING_TOPOS
    r = gx.analyse(str(_spokes(tmp_path, 10)), 1.0)
    for _n, _p, z, _dev, aims in r["aim"]:
        assert not aims
        assert np.allclose(z, [0.0, 0.0, 1.0], atol=1e-9)


def test_hand_aimed_fan_is_reported(tmp_path):
    """The reported bug: positions computed by hand around a Cartesian parent,
    aim supplied by rotate_*, and every rod ends up parallel."""
    gx = _load("gv_extents_fan", CODE / "gv_extents.py")
    p = _spokes(tmp_path, 0, rot=(90.0, 0.0, 30.0), cartesian_positions=True)
    r = gx.analyse(str(p), 1.0)
    assert len(r["aim_fan"]) == 1, "the flat stacked fan must be caught"
    parent, count, spread, _z = r["aim_fan"][0]
    assert parent.id == 1 and count == 12 and spread > 45.0
    text = gx.report(r)
    assert "pointing the same way" in text
    assert text.isascii()


def test_upright_forest_is_not_a_fan(tmp_path):
    """The discriminator. Trees standing up, spread on the ground, all +Z up:
    identical to the fan in every way except that no sibling lies ALONG the
    shared direction. This must stay quiet or the check is worthless."""
    import math
    gx = _load("gv_extents_forest", CODE / "gv_extents.py")
    rows = ["1,5,0,0,0,0,0,0,0,0,1,1,1,255,255,255,255,3,0,0,0.1,0"]
    for i in range(12):
        a = math.radians(i * 30)
        rows.append(f"{2 + i},5,1,1,{6 * math.cos(a):.4f},{6 * math.sin(a):.4f},1,"
                    f"0,0,45,0.3,0.3,1,90,150,90,255,19,0,0,0.1,0")
    p = tmp_path / "forest_gv_node.csv"
    p.write_text(_AIM_HDR + "\n".join(rows) + "\n", encoding="utf-8")
    r = gx.analyse(str(p), 1.0)
    assert not r["aim_fan"], "an upright forest is not a mis-aimed fan"


def test_a_deliberate_lean_is_reported_but_not_called_a_fault(tmp_path):
    """Measured across the example gallery, "rotated off the placed aim" is
    indistinguishable from a deliberate lean -- Armillary_World lays its pins
    along their rings at rotate_x = -90 on purpose. So it is stated in the AIM
    section and must never be counted as a problem."""
    gx = _load("gv_extents_lean", CODE / "gv_extents.py")
    r = gx.analyse(str(_spokes(tmp_path, 2, rot=(90.0, 0.0, 0.0))), 1.0)
    assert len(r["fighting_aim"]) == 12, "the deflection should be measured"
    assert not r["aim_fan"], "and it must not be reported as a fault"
    text = gx.report(r)
    assert "no hand-aimed fans" in text, "PROBLEMS must stay clean"
    assert "turns them off that aim" in text, "but AIM must say what happened"


def test_radial_spokes_example_is_the_known_good_scene():
    """The example exists to be calibrated against, so its numbers are pinned
    here too: this is the scene SKILL.md rule 12 points a reader at."""
    gx = _load("gv_extents_example", CODE / "gv_extents.py")
    scene = CODE.parent / "examples" / "Radial_Spokes" / "radial_spokes_gv_node.csv"
    assert scene.exists(), "the known-good spokes scene is missing"
    r = gx.analyse(str(scene), 1.0)
    assert not r["aim_fan"] and not r["fighting_aim"]
    assert all(n.rotate_x == n.rotate_y == n.rotate_z == 0.0
               for n in r["nodes"]), "this scene must carry no rotations at all"
    aimed = [a for a in r["aim"] if a[4]]
    assert len(aimed) == 30, f"expected 30 aimed rods, got {len(aimed)}"
    assert (CODE.parent / "examples" / "Radial_Spokes" / "aim_report.txt").exists()


def test_gv_extents_flags_a_textured_surface_at_alpha_zero(tmp_path):
    """A textured Surface is drawn with its PARENT's alpha, so color_a = 0 on
    that parent makes the whole mesh invisible (measured through the real
    renderer: 141,376 px at 255, 0 at 0). An untextured one uses its vertices'
    colours instead, so the same alpha on its hub is harmless."""
    hdr = ("id,type,parent_id,branch_level,translate_x,translate_y,translate_z,"
           "rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,"
           "color_r,color_g,color_b,color_a,geometry,hide,topo,ratio,texture_id")
    rows = []
    nid = 1
    for hub_x, tex in ((0, 1), (100, 0)):
        hub = nid
        rows.append(f"{hub},5,0,0,{hub_x},0,0,0,0,0,1,1,1,255,255,255,0,22,0,17,0.1,{tex}")
        nid += 1
        for j in range(2):
            for i in range(2):
                rows.append(f"{nid},5,{hub},1,{i},{j},0,0,0,0,0,0,0,200,200,200,255,1,0,0,0.1,0")
                nid += 1
    p = tmp_path / "surf_gv_node.csv"
    p.write_text(hdr + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    gx = _load("gv_extents_surface", CODE / "gv_extents.py")
    r = gx.analyse(str(p), 1.0)
    assert [n.id for n in r["dark_surfaces"]] == [1]
    assert "whole mesh is invisible" in gx.report(r)
