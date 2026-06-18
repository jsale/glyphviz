"""Pure-math (numpy-only) transforms for the OpenXR renderer.

No GL or XR imports here except the one lazy `xr.utils.rotation_from_quaternionf`
call inside view_matrix(), which is XR-specific math, not a rendering call —
kept lazy so this module stays importable without the xr package installed.
"""
from math import radians

import numpy as np


def gl_col_major(M: np.ndarray) -> np.ndarray:
    """Row-major 4x4 -> flat column-major float32, for glLoadMatrixf/glMultMatrixf
    (mirrors glyphviz_gl.viewport._gl_col_major; duplicated to keep this
    package independent of the Qt-importing viewport module)."""
    return M.astype(np.float32).T.flatten()


def toe_yaw_matrix(angle_rad: float) -> np.ndarray:
    """Extra yaw (around the local +Y/up axis) applied in eye space, for manual
    convergence tuning independent of whatever the runtime's own eye poses/FOV
    give us (see --toe-deg)."""
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    M = np.identity(4)
    M[0, 0] = c
    M[0, 2] = s
    M[2, 0] = -s
    M[2, 2] = c
    return M


def view_matrix(pose, toe_rad: float = 0.0) -> np.ndarray:
    """Correct world-to-eye view matrix from an OpenXR pose.

    xr.utils.view_matrix_from_posef() has a bug: xr.utils.rotation_from_quaternionf()
    already returns the inverse (world-to-local) rotation, but view_matrix_from_posef
    transposes it *again* before use, embedding the forward (local-to-world) rotation
    in the view matrix instead. That makes the rendered scene rotate the same
    direction as the headset instead of counter-rotating. Built directly here from
    the (correctly inverse) rotation_from_quaternionf output, with no extra transpose.

    `toe_rad` adds a manual outward-toe yaw on top of the runtime-reported
    orientation (positive turns the view further toward +X in its own local
    frame) — a stopgap for dialing in convergence/overlap independent of
    whatever the runtime's per-eye FOV asymmetry is actually doing."""
    from xr.utils import rotation_from_quaternionf
    r_inv = np.asarray(rotation_from_quaternionf(pose.orientation), dtype=np.float64)
    position = np.array([pose.position.x, pose.position.y, pose.position.z])
    view = np.identity(4, dtype=np.float32)
    view[:3, :3] = r_inv
    view[:3, 3] = -(r_inv @ position)
    if toe_rad != 0.0:
        view = (toe_yaw_matrix(toe_rad) @ view).astype(np.float32)
    return view


def diorama_transform_matrix(scale: float, forward: float, down: float) -> np.ndarray:
    """CPU-side (numpy) equivalent of render.draw_scene's GL calls —
    Translate(0, -down, -forward) @ RotateX(-90) @ Scale(scale) — used by
    ControllerNav's picking ray test, which needs this transform without
    touching the GL matrix stack."""
    t = np.identity(4)
    t[:3, 3] = [0.0, -down, -forward]
    a = radians(-90.0)
    c, s = np.cos(a), np.sin(a)
    r = np.identity(4)
    r[1, 1] = c
    r[1, 2] = -s
    r[2, 1] = s
    r[2, 2] = c
    sc = np.diag([scale, scale, scale, 1.0])
    return t @ r @ sc


def rig_inverse_matrix(nav_position: np.ndarray, nav_yaw: float) -> np.ndarray:
    """Inverse of Translate(nav_position) @ RotateY(nav_yaw) — the virtual
    "locomotion rig" transform accumulated from controller input. Multiplying
    this into MODELVIEW right after the (real, tracked) per-eye view matrix
    makes the world appear to move/turn as if the user's rig had moved by
    nav_position/nav_yaw, independent of their real physical position in the
    room. See ControllerNav for how nav_position/nav_yaw accumulate."""
    c, s = np.cos(-nav_yaw), np.sin(-nav_yaw)
    rot_inv = np.identity(4)
    rot_inv[0, 0] = c
    rot_inv[0, 2] = s
    rot_inv[2, 0] = -s
    rot_inv[2, 2] = c
    trans_inv = np.identity(4)
    trans_inv[:3, 3] = -nav_position
    return rot_inv @ trans_inv
