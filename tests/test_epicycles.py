"""Epicycle chains: the harmonic ladder, the two 3-D knobs, and the trail.

Everything here is measured against the REAL engine (Scene / topology /
csv_reader), never against a second copy of the math — the whole point of
glyphviz_core.epicycles is that the trail is sampled from the same code that
renders, so a test that reimplemented the placement would pin the wrong thing.
"""
import math
import os

import numpy as np
import pytest

from glyphviz_core import epicycles as ep
from glyphviz_core.csv_reader import load_node_csv
from glyphviz_core.node import Node, ROTATION_MODE_EULER_XYZ
from glyphviz_core.scene import Scene


# --------------------------------------------------------------------------
# The ladder
# --------------------------------------------------------------------------

def _measured_harmonics(design, frames=1440):
    """Harmonic of each arm, read off the rendered chain.

    Each arm's vector is (child world pos - parent world pos); the complex DFT
    of x+iy separates +h from -h, which is what distinguishes an arm turning
    one way from the other.
    """
    nodes = ep._chain_nodes(design, start_id=1, parent_id=0, base_branch=0,
                            animated=True)
    chain = [n for n in nodes if n.type == ep.TYPE_GLYPH]
    by_id = {n.id: n for n in chain}
    scene = Scene(chain, base_scale=1.0)
    ids = [n.id for n in chain]

    pos = {i: [] for i in ids}
    for f in range(frames):
        t = f * 360.0 / frames
        for arm, nid in zip(design.arms, ids[1:]):
            by_id[nid].translate_x = arm.phase_x + arm.rate_x * t
            by_id[nid].translate_y = arm.phase_y + arm.rate_y * t
        scene.invalidate()
        for i in ids:
            pos[i].append(scene.world_pos(i))

    out = []
    for a, b in zip(ids[:-1], ids[1:]):
        va, vb = np.array(pos[a]), np.array(pos[b])
        d = (vb[:, 0] - va[:, 0]) + 1j * (vb[:, 1] - va[:, 1])
        f = np.fft.fft(d) / frames
        k = int(np.argmax(np.abs(f)))
        out.append(float(k if k <= frames // 2 else k - frames))
    return out


@pytest.mark.parametrize("rates,expected", [
    ((1, -1, 1, -1), [1, 2, 3, 4]),      # Jeff's ANTz original
    ((1, 1, 1, 1), [1, 0, 1, 0]),
    ((1, -2, 3, -4), [1, 3, 6, 10]),
    ((1, -2, 2, -2), [1, 3, 5, 7]),      # the square wave
    ((2, -1, 0, -1), [2, 3, 3, 4]),
    ((1, -3, 3, -3), [1, 4, 7, 10]),
    ((1, 0, 0, 0), [1, 1, 1, 1]),
])
def test_harmonic_ladder_matches_the_engine(rates, expected):
    """h_k = h_{k-1} + (-1)^(k-1) * r_k, predicted AND measured.

    The alternating sign is the whole subtlety: rotate = (90, 90, 0) cancels
    TOPO_TORUS's base rotation and leaves the frame handedness flipped, so the
    rate MAGNITUDES add. Jeff's (+1,-1,+1,-1) climbing to 1,2,3,4 rather than
    collapsing to 1,0,1,0 is that fact.
    """
    design = ep.EpicycleDesign(
        arms=[ep.Arm(length=10.0, rate_x=float(r)) for r in rates])
    assert ep.harmonics_of(rates) == pytest.approx(expected)
    assert _measured_harmonics(design) == pytest.approx(expected)


def test_the_90_90_rotation_is_load_bearing():
    """Without it the chain leaves the plane and the ladder collapses.

    Pinned because it looks like an arbitrary pose and is not: it is what makes
    the construction a Fourier series at all.
    """
    rates = (1.0, -1.0, 1.0, -1.0)
    design = ep.EpicycleDesign(arms=[ep.Arm(length=10.0, rate_x=r) for r in rates])
    good = ep.trace_path(design, 360)
    assert max(abs(p[2]) for p in good) < 1e-9
    assert _measured_harmonics(design) == pytest.approx([1, 2, 3, 4])

    nodes = ep._chain_nodes(design, 1, 0, 0, animated=True)
    chain = [n for n in nodes if n.type == ep.TYPE_GLYPH]
    for n in chain[1:]:
        n.rotate_x = n.rotate_y = 0.0
    by_id = {n.id: n for n in chain}
    scene = Scene(chain, base_scale=1.0)
    worst_z = 0.0
    for f in range(360):
        for arm, node in zip(design.arms, chain[1:]):
            by_id[node.id].translate_x = arm.rate_x * f
        scene.invalidate()
        worst_z = max(worst_z, abs(scene.world_pos(chain[-1].id)[2]))
    assert worst_z > 10.0, "without (90,90,0) the chain should corkscrew away"


# --------------------------------------------------------------------------
# The two 3-D knobs
# --------------------------------------------------------------------------

def test_tilt_leans_the_orbit_plane_by_exactly_that_many_degrees():
    """Arm.tilt is written as the PARENT's rotate_y, and rotate_y is the field
    that tips a ring plane — rotate_x and rotate_z do not, at this base pose."""
    for tilt in (0.0, 15.0, 30.0, 60.0, 90.0):
        design = ep.EpicycleDesign(arms=[
            ep.Arm(length=10.0, rate_x=1.0),
            ep.Arm(length=5.0, rate_x=1.0, tilt=tilt),
        ])
        nodes = ep._chain_nodes(design, 1, 0, 0, animated=True)
        chain = [n for n in nodes if n.type == ep.TYPE_GLYPH]
        scene = Scene(chain, base_scale=1.0)
        basis = np.asarray(scene.basis_matrices(chain[1].id)[0])
        normal = basis[:3, 2]
        normal = normal / np.linalg.norm(normal)
        got = math.degrees(math.acos(min(1.0, abs(float(normal[2])))))
        assert got == pytest.approx(tilt, abs=1e-6), f"tilt {tilt} -> {got}"


def test_tube_generates_sidebands_and_out_of_plane_motion():
    """An arm at harmonic h with tube rate r contributes h, h-r and h+r in the
    plane, and pure out-of-plane motion at r. That is the whole reason the tube
    is exposed: it is a spectrum knob, not just a wobble."""
    design = ep.EpicycleDesign(arms=[
        ep.Arm(length=10.0, rate_x=1.0),
        ep.Arm(length=10.0, rate_x=-1.0, tube=5.0, rate_y=3.0),
    ])
    # Traced over four full periods on purpose: spectrum() reports harmonics in
    # rate_x units (turns per 360 frames), so the answer must not depend on how
    # many periods were sampled.
    for frames in (360, 1440):
        path = ep.trace_path(design, frames)
        got = {h for h, _a in ep.spectrum(path, top=12, floor=1e-3)}
        assert {1.0, 2.0, 5.0, -1.0} <= got, (frames, got)
        assert max(abs(p[2]) for p in path) > 4.0

    flat = ep.EpicycleDesign(arms=[
        ep.Arm(length=10.0, rate_x=1.0), ep.Arm(length=10.0, rate_x=-1.0)])
    assert max(abs(p[2]) for p in ep.trace_path(flat, 360)) < 1e-9


def test_tube_is_carved_out_of_the_arm_not_added_to_it():
    """`length` stays the true arm length at phase_y 0 even with a fat tube,
    and the parent's DRAWN ring is the circle the child rides.

    The obvious alternative — the child's translate_z — also works but draws
    nothing and pushes the arm longer than its authored length, which made a
    tube design impossible to read and impossible to size.
    """
    design = ep.EpicycleDesign(arms=[
        ep.Arm(length=12.0, rate_x=1.0),
        ep.Arm(length=6.0, rate_x=1.0, tube=3.0, rate_y=4.0),
    ])
    nodes = ep._chain_nodes(design, 1, 0, 0, animated=True)
    chain = [n for n in nodes if n.type == ep.TYPE_GLYPH]
    scene = Scene(chain, base_scale=1.0)

    # phase_y = 0 puts the child at the tube's outer equator: exactly `length`.
    assert math.dist(scene.world_pos(chain[1].id),
                     scene.world_pos(chain[2].id)) == pytest.approx(6.0, rel=1e-9)
    # The parent wears that tube as its own ring thickness.
    assert chain[1].ratio == pytest.approx(3.0 / 6.0)
    # Half a tube turn later the child is at length - 2*tube.
    chain[2].translate_y = 180.0
    scene.invalidate()
    assert math.dist(scene.world_pos(chain[1].id),
                     scene.world_pos(chain[2].id)) == pytest.approx(0.0, abs=1e-9)


def test_tube_cannot_swallow_its_own_orbit():
    """Ratio 1 degenerates the torus to a sphere, so the fraction is capped."""
    design = ep.EpicycleDesign(arms=[
        ep.Arm(length=10.0, rate_x=1.0),
        ep.Arm(length=4.0, rate_x=1.0, tube=99.0),
    ])
    chain = [n for n in ep._chain_nodes(design, 1, 0, 0, animated=True)
             if n.type == ep.TYPE_GLYPH]
    assert chain[1].ratio == pytest.approx(ep.MAX_TUBE_FRACTION)


def test_arm_length_is_world_units_and_telescopes():
    """`length` is authored in world units at every depth, which only works
    because the builder divides consecutive lengths into each node's scale — a
    node's cumulative scale IS the radius of the circle its child rides."""
    lengths = [12.0, 7.0, 4.5, 1.5]
    design = ep.EpicycleDesign(
        arms=[ep.Arm(length=v, rate_x=1.0) for v in lengths])
    nodes = ep._chain_nodes(design, 1, 0, 0, animated=True)
    chain = [n for n in nodes if n.type == ep.TYPE_GLYPH]
    scene = Scene(chain, base_scale=1.0)
    for k, (a, b) in enumerate(zip(chain[:-1], chain[1:])):
        got = math.dist(scene.world_pos(a.id), scene.world_pos(b.id))
        assert got == pytest.approx(lengths[k], rel=1e-9)


# --------------------------------------------------------------------------
# Closure
# --------------------------------------------------------------------------

@pytest.mark.parametrize("rates,expected", [
    ((1.0, -1.0), 360),
    ((2.0, 3.0), 360),
    ((0.5, 1.0), 720),
    ((1.0 / 3.0, 1.0), 1080),
    ((0.0, 0.0), None),
])
def test_closure_frames(rates, expected):
    design = ep.EpicycleDesign(
        arms=[ep.Arm(length=10.0, rate_x=r) for r in rates])
    assert ep.closure_frames(design) == expected


def test_closure_actually_closes():
    """The claim is geometric, not arithmetic: at the reported frame the pen is
    back where it started."""
    for label in ep.PRESETS:
        design = ep.preset(label)
        n = ep.closure_frames(design)
        assert n, label
        path = ep.trace_path(design, n + 1)
        assert math.dist(path[0], path[n]) < 1e-9, label


# --------------------------------------------------------------------------
# The trail, through a real round trip
# --------------------------------------------------------------------------

@pytest.mark.parametrize("label", list(ep.PRESETS))
def test_every_preset_round_trips_with_its_trail_on_the_curve(label, tmp_path):
    """Write, reload from disk, re-run the chain, and check bead f is where the
    pen is at frame f. This is the one test that would catch a units bug, a
    sampling-step mismatch, or a tag file that did not load."""
    design = ep.preset(label)
    paths = ep.write_scene(design, str(tmp_path), "scene")

    nodes = load_node_csv(paths["node"])
    by_id = {n.id: n for n in nodes}
    chain = [n for n in nodes
             if n.type == ep.TYPE_GLYPH and n.topo == ep.T_TORUS]
    plot = next(n for n in nodes if n.topo == ep.T_PLOT)
    beads = [n for n in nodes if n.parent_id == plot.id]
    assert len(chain) == design.n_arms + 1

    frames = ep.frame_count(design)
    step, n_beads = ep.trail_sampling(design, frames)
    assert len(beads) == n_beads

    scene = Scene(nodes, base_scale=1.0)
    worst = 0.0
    for i, bead in enumerate(beads):
        f = i * step
        for arm, node in zip(design.arms, chain[1:]):
            by_id[node.id].translate_x = arm.phase_x + arm.rate_x * f
            by_id[node.id].translate_y = arm.phase_y + arm.rate_y * f
        scene.invalidate()
        worst = max(worst, math.dist(scene.world_pos(chain[-1].id),
                                     scene.world_pos(bead.id)))
    # The floor is the node CSV's own 6-decimal write precision, amplified by
    # the parent scales the offsets pass through.
    assert worst < 1e-4, f"{label}: trail is {worst} off the pen's path"

    # The tag file is found by NAME CONVENTION alone, so a rename costs every
    # label silently. Check the labels actually arrived.
    bead_ids = {b.id for b in beads}
    assert all(n.text for n in nodes if n.id not in bead_ids)


def test_plot_parent_is_transparent_not_hidden():
    """A hidden Plot parent suppresses the polyline entirely
    (viewport._draw_topology_overlays skips hidden plot nodes), so the trail
    parent must be alpha 0 instead. Easy to "tidy up" into hide=1 later."""
    nodes = ep.build_nodes(ep.preset("Cardioid (2 terms)"))
    plot = next(n for n in nodes if n.topo == ep.T_PLOT)
    assert plot.hide == 0
    assert plot.color_a == 0


def test_trail_sampling_is_shared_by_nodes_and_channels():
    """The bead->frame mapping must be identical on both sides or the alpha
    steps light at the wrong moment. They are derived from one function."""
    design = ep.preset("Jeff's ANTz original")
    design.self_drawing = True
    design.trail_points = 137           # deliberately not a divisor of 360
    frames = ep.frame_count(design)
    step, n_beads = ep.trail_sampling(design, frames)

    nodes = ep.build_nodes(design, include_world=True)
    plot = next(n for n in nodes if n.topo == ep.T_PLOT)
    beads = [n for n in nodes if n.parent_id == plot.id]
    assert len(beads) == n_beads

    chmap, tracks = ep.build_channels(design, frames)
    alpha_rows = [r for r in chmap if r[2] == "color_a"]
    assert len(alpha_rows) == (n_beads + design.bead_group - 1) // design.bead_group
    # Every bead's channel exists in the map.
    bead_channels = {int(b.extras["ch_input_id"]) for b in beads}
    assert bead_channels <= {r[0] for r in alpha_rows}


def test_self_drawing_trail_never_runs_ahead_of_the_pen():
    """A line drawing a curve the pen has not travelled yet would be a lie. The
    grouping lights a group when its LAST bead is reached, so it lags instead."""
    design = ep.preset("Jeff's ANTz original")
    design.self_drawing = True
    frames = ep.frame_count(design)
    step, n_beads = ep.trail_sampling(design, frames)
    chmap, tracks = ep.build_channels(design, frames)

    by_channel = {ch: tracks[tid] for ch, tid, attr in chmap if attr == "color_a"}
    for gidx, (ch, col) in enumerate(sorted(by_channel.items())):
        on = next(f for f, v in enumerate(col) if v > 0)
        first_bead = gidx * design.bead_group
        assert on >= first_bead * step, (
            f"group {gidx} lights at frame {on}, before bead {first_bead} "
            f"is reached at {first_bead * step}")


def test_channel_playback_puts_the_pen_on_the_trail(tmp_path):
    """End to end through the real ChannelEngine and the real track files."""
    from glyphviz_core.channel_loader import (find_channel_files, load_ch_map,
                                              load_ch_tracks)
    from glyphviz_core.channel_engine import ChannelEngine

    design = ep.preset("Rose in space")
    design.self_drawing = True
    paths = ep.write_scene(design, str(tmp_path), "scene")
    assert "map" in paths and "tracks" in paths

    nodes = load_node_csv(paths["node"])
    map_path, tracks_path = find_channel_files(paths["node"])
    engine = ChannelEngine()
    tracks, id_to_col = load_ch_tracks(tracks_path)
    engine.load(load_ch_map(map_path), tracks, id_to_col, nodes)
    assert engine.has_bindings

    plot = next(n for n in nodes if n.topo == ep.T_PLOT)
    beads = [n for n in nodes if n.parent_id == plot.id]
    chain = [n for n in nodes
             if n.type == ep.TYPE_GLYPH and n.topo == ep.T_TORUS]
    scene = Scene(nodes, base_scale=1.0)

    frames = ep.frame_count(design)
    step, _ = ep.trail_sampling(design, frames)
    worst = 0.0
    for i, bead in enumerate(beads):
        engine.apply_frame(i * step)
        scene.invalidate()
        worst = max(worst, math.dist(scene.world_pos(chain[-1].id),
                                     scene.world_pos(bead.id)))
    assert worst < 1e-4


# --------------------------------------------------------------------------
# Design model housekeeping
# --------------------------------------------------------------------------

def test_design_round_trips_through_dict():
    design = ep.preset("Deep chain (6 arms)")
    again = ep.EpicycleDesign.from_dict(design.to_dict())
    assert again.to_dict() == design.to_dict()


def test_preset_returns_a_copy():
    a = ep.preset("Cardioid (2 terms)")
    a.arms[0].length = 999.0
    assert ep.preset("Cardioid (2 terms)").arms[0].length != 999.0


def test_random_designs_are_deterministic_and_sane():
    import random as _r
    for seed in (1, 7, 12345):
        one = ep.random_design(_r.Random(seed))
        two = ep.random_design(_r.Random(seed))
        assert one.to_dict() == two.to_dict()
        assert ep.MIN_ARMS <= one.n_arms <= ep.MAX_ARMS
        # Small whole-number rates, so a random design still closes.
        assert ep.closure_frames(one) is not None


def test_ids_are_contiguous_from_start_id():
    """Insert into Scene allocates from max(existing)+1, so a gap or a repeat
    would collide with the live scene."""
    design = ep.preset("Inclined orrery (tilt)")
    nodes = ep.build_nodes(design, start_id=500, include_world=False)
    ids = [n.id for n in nodes]
    assert ids == list(range(500, 500 + len(nodes)))
    known = set(ids) | {0}
    for n in nodes:
        assert n.parent_id in known
        assert int(n.extras.get("child_id", 0) or 0) in known
