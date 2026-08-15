"""Hyperglyph Tree Designer — the browser tool in hyperglyph_lab/.

The tool ships in two places: `hyperglyph_lab/` is the source of truth, and
`glyphviz-docs/docs/hyperglyph_lab/` is the copy mkdocs serves so the docs
site can open it. Nothing in the build copies one to the other, so the only
thing standing between them and silent drift is this test.

Also pins the contract the tool depends on from the Python side: it writes
Glyph Composer templates whose non-root levels carry `link_*` keys, so it
cannot outlive the Composer's link levels (see test_glyph_recipe_links.py)
without someone noticing.
"""
import json
import re
from pathlib import Path

import pytest

from glyphviz_core import glyph_recipe as gr

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "hyperglyph_lab" / "hyperglyph_tree_designer.html"
DOCS_COPY = (REPO / "glyphviz-docs" / "docs" / "hyperglyph_lab"
             / "hyperglyph_tree_designer.html")


def test_tool_ships_in_hyperglyph_lab():
    assert TOOL.is_file(), f"{TOOL} is missing"


def test_docs_copy_is_identical():
    """The docs site serves its own copy; if they diverge, the published tool
    silently stops matching the repo's."""
    assert DOCS_COPY.is_file(), (
        f"{DOCS_COPY} is missing — the docs site would 404 on the "
        "Tree Designer link")
    assert DOCS_COPY.read_bytes() == TOOL.read_bytes(), (
        "hyperglyph_lab/hyperglyph_tree_designer.html and the docs copy have "
        "drifted. Copy the hyperglyph_lab/ one over the docs one.")


def test_tool_is_self_contained():
    """It has to run from a file:// path and from the docs site with no build
    step, so no external script/style/import references."""
    html = TOOL.read_text(encoding="utf-8")
    for pattern in (r'<script[^>]+src=', r'<link[^>]+stylesheet',
                    r'\bimport\s+.*\bfrom\s+[\'"]'):
        assert not re.search(pattern, html), \
            f"tool pulls in an external resource: {pattern}"


def test_docs_page_links_to_the_tool():
    page = REPO / "glyphviz-docs" / "docs" / "reference" / "tree-designer.md"
    assert page.is_file()
    text = page.read_text(encoding="utf-8")
    assert "../hyperglyph_lab/hyperglyph_tree_designer.html" in text
    nav = (REPO / "glyphviz-docs" / "mkdocs.yml").read_text(encoding="utf-8")
    assert "reference/tree-designer.md" in nav, "page is not in the nav"


# --- the recipe contract the tool writes against ---------------------------

def _levels_from_tool_defaults():
    """A template shaped the way the tool emits one: a root, a trunk, forks
    that link back to their parents, and a blossom level."""
    root = gr.LevelSpec(count=1, dist_mode=gr.DIST_LINEAR, topo=7)
    trunk = gr.LevelSpec(count=1, dist_mode=gr.DIST_ANGULAR, topo=7,
                         dist_tilt=90.0, dist_tz=4.0,
                         link_geo=19, link_ratio=0.4)
    fork = gr.LevelSpec(count=2, dist_mode=gr.DIST_ANGULAR, topo=7,
                        dist_tilt=65.0, dist_tz=3.0,
                        scale_x=0.68, scale_y=0.68, scale_z=0.68,
                        link_geo=19, link_ratio=0.27)
    return gr.GlyphRecipe(name="Tree", levels=[root, trunk, fork])


def test_tool_style_template_round_trips():
    """What the tool downloads is plain Composer JSON — it must load back
    through the real loader with its link settings intact."""
    recipe = _levels_from_tool_defaults()
    back = gr.recipe_from_dict(json.loads(json.dumps(gr.recipe_to_dict(recipe))))
    assert [l.link_geo for l in back.levels] == [None, 19, 19]
    assert back.levels[2].link_ratio == pytest.approx(0.27)
    assert gr.recipe_node_count(back) == len(gr.generate_nodes(back, start_id=1))


def test_branch_angle_is_ninety_minus_tilt():
    """The tool's whole armature: a level authored at dist_tilt = 90 - A puts
    its children A degrees off the parent's heading. Pinned here because the
    tool computes that 90 - A itself and would silently produce wrong-angled
    trees if the convention ever moved."""
    import numpy as np
    from glyphviz_core.scene import Scene

    angle = 35.0
    recipe = _levels_from_tool_defaults()
    recipe.levels[2].dist_tilt = 90.0 - angle
    nodes = gr.generate_nodes(recipe, start_id=1)
    scene = Scene(nodes, 1.0)
    scene._ensure()
    by_id = {n.id: n for n in nodes}

    checked = 0
    for n in nodes:
        if n.type == 7 or n.branch_level != 2:
            continue
        parent = by_id[n.parent_id]
        wb, _, _ = scene.basis_matrices(parent.id)
        heading = np.asarray(wb)[:, 2]
        heading = heading / np.linalg.norm(heading)
        off = (np.asarray(scene.world_pos(n.id))
               - np.asarray(scene.world_pos(parent.id)))
        off = off / np.linalg.norm(off)
        got = np.degrees(np.arccos(np.clip(float(np.dot(off, heading)), -1, 1)))
        assert got == pytest.approx(angle, abs=1e-6)
        checked += 1
    assert checked == 2
