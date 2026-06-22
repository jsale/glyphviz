"""GL drawing helpers for the OpenXR renderer — fixed-function GL state setup
and the diorama/controller-marker draw calls, reusing glyphviz_gl.geometry.GeoRenderer
exactly as the desktop viewport does."""
import numpy as np

from glyphviz_core.geometry_data import GEO_CUBE_WIRE, GEO_SPHERE
from glyphviz_core.node import NODE_TYPE_LINK, NON_VISUAL_TYPES
from glyphviz_core.scene import Scene, node_world_matrix
from glyphviz_gl.geometry import GeoRenderer

from .text_billboard import draw_label
from .transforms import gl_col_major


def init_gl_state():
    """Mirrors glyphviz_gl.viewport.Viewport.initializeGL's fixed-function setup."""
    from OpenGL.GL import (
        glClearColor, glEnable, glLightfv,
        glColorMaterial, glShadeModel, glBlendFunc, glCullFace,
        GL_DEPTH_TEST, GL_LIGHTING, GL_LIGHT0, GL_DIFFUSE,
        GL_AMBIENT, GL_SPECULAR, GL_POSITION, GL_COLOR_MATERIAL,
        GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE, GL_SMOOTH, GL_BLEND,
        GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_CULL_FACE, GL_BACK,
    )
    glClearColor(0.08, 0.08, 0.12, 1.0)
    glEnable(GL_DEPTH_TEST)
    # xr.utils.projection_from_fovf()'s docstring claims an "infinite
    # reverse-Z projection," which led to an earlier (wrong) fix here adding
    # glDepthFunc(GL_GREATER)/glClearDepth(0.0). Verified numerically
    # 2026-06-18: feeding real eye-space points through the actual matrix
    # this function returns gives depth-buffer values that *increase* with
    # distance (near=0.33, far=0.50 at z=-1m/-50m) — i.e. standard
    # near-is-small convention, the opposite of what the docstring claims.
    # The GL_GREATER fix was therefore backwards, telling GL to let farther
    # fragments win — exactly the "distant objects render in front of
    # closer ones" symptom reported on the SineWave scene. Plain GL
    # defaults (GL_LESS, clear-to-1.0, both implicit below) are correct.
    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)
    glLightfv(GL_LIGHT0, GL_DIFFUSE, [1.0, 1.0, 1.0, 1.0])
    glLightfv(GL_LIGHT0, GL_AMBIENT, [0.3, 0.3, 0.3, 1.0])
    glLightfv(GL_LIGHT0, GL_SPECULAR, [0.5, 0.5, 0.5, 1.0])
    glLightfv(GL_LIGHT0, GL_POSITION, [1.0, 2.0, 1.0, 0.0])
    glEnable(GL_COLOR_MATERIAL)
    glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
    glShadeModel(GL_SMOOTH)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glEnable(GL_CULL_FACE)
    glCullFace(GL_BACK)


def draw_scene(scene: Scene, geo: GeoRenderer, scale: float, forward: float, down: float,
                selected_node=None, tex_mgr=None):
    """Diorama-first placement: shrink the GlyphViz (Z-up) scene to roughly
    tabletop size, rotate Z-up into OpenXR's Y-up, and anchor it a fixed
    distance in front of / below wherever the LOCAL reference space origin
    is (i.e. where the headset was when Link/the app started) — not a
    room-scale, world-locked placement."""
    from OpenGL.GL import (
        glPushMatrix, glPopMatrix, glTranslatef, glRotatef, glScalef,
        glMultMatrixf, glColor4f, glDisable, glEnable, GL_LIGHTING, glLineWidth,
    )
    glTranslatef(0.0, -down, -forward)
    glRotatef(-90.0, 1.0, 0.0, 0.0)  # GlyphViz +Z (up) -> OpenXR +Y (up)
    glScalef(scale, scale, scale)

    for node in scene.nodes:
        if node.type in NON_VISUAL_TYPES or node.type == NODE_TYPE_LINK:
            continue
        M = node_world_matrix(node, scene)
        glPushMatrix()
        glMultMatrixf(gl_col_major(M))
        glColor4f(
            node.color_r / 255.0, node.color_g / 255.0,
            node.color_b / 255.0, node.color_a / 255.0,
        )
        gl_tex = tex_mgr.get_gl_name(node.texture_id) if tex_mgr and node.texture_id else 0
        geo.draw(node.geometry, 1.0, 1.0, 1.0, ratio=node.ratio, gl_tex_name=gl_tex)
        glPopMatrix()

        if node is selected_node:
            glPushMatrix()
            glMultMatrixf(gl_col_major(M))
            glDisable(GL_LIGHTING)
            glColor4f(1.0, 1.0, 0.2, 1.0)
            glLineWidth(2.0)
            geo.draw(GEO_CUBE_WIRE, 1.3, 1.3, 1.3)
            glEnable(GL_LIGHTING)
            glPopMatrix()

            # Label anchored at the node's plain world position (not inside
            # the node's own R*S above) so the billboard lifts straight up
            # in the diorama frame regardless of the node's own orientation.
            radius = sum(np.linalg.norm(M[:3, i]) for i in range(3)) / 3.0
            glPushMatrix()
            glTranslatef(float(M[0, 3]), float(M[1, 3]), float(M[2, 3]))
            draw_label(node.text, (0.0, 0.0, radius * 1.3))
            glPopMatrix()


def draw_controller_marker(geo: GeoRenderer, position: np.ndarray, forward_dir: np.ndarray,
                            color: tuple[float, float, float]):
    """Small sphere at a controller's real (untransformed-by-nav) grip
    position, plus a thin pointing ray along its aim direction — drawn before
    the rig transform is applied, so these always show the controller's true
    physical position/orientation regardless of how far the user has
    virtually navigated."""
    from OpenGL.GL import (
        glPushMatrix, glPopMatrix, glTranslatef, glScalef, glColor4f,
        glBegin, glEnd, glVertex3f, glLineWidth, GL_LINES, glDisable, glEnable, GL_LIGHTING,
    )
    glPushMatrix()
    glTranslatef(float(position[0]), float(position[1]), float(position[2]))
    glColor4f(color[0], color[1], color[2], 1.0)
    glScalef(0.02, 0.02, 0.02)
    geo.draw(GEO_SPHERE, 1.0, 1.0, 1.0)
    glPopMatrix()

    ray_end = position + forward_dir * 0.5
    glDisable(GL_LIGHTING)
    glLineWidth(2.0)
    glColor4f(color[0], color[1], color[2], 1.0)
    glBegin(GL_LINES)
    glVertex3f(float(position[0]), float(position[1]), float(position[2]))
    glVertex3f(float(ray_end[0]), float(ray_end[1]), float(ray_end[2]))
    glEnd()
    glEnable(GL_LIGHTING)
