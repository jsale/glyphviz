"""
Importer for .pdb protein-structure files (see examples/Protein_Import_Example/).
Converts ATOM/HETATM records into ordinary GEO_SPHERE/TOPO_NONE atom nodes and
distance-inferred bonds into ordinary NODE_TYPE_LINK (type=7) nodes carrying
GEO_CYLINDER, which a Link renders as a rod spanning the two atoms -- so the
result is a true ball-and-stick scene. Both node shapes are already fully
supported by topology.py and viewport.py, so no new geometry/topology/rendering
code is needed. Pure data/numpy (plus
Bio.PDB/scipy) -- no OpenGL/Qt dependency, so this module is safe to import
from anything, including a future non-GL presentation layer.

Bio.PDB.PDBParser doesn't surface CONECT records, so bonds are always
distance-inferred: a KD-tree (scipy, already a project dependency) finds
candidate atom pairs within a generous cutoff in near-linear time, and each
candidate is kept only if its distance is within a per-element covalent-radius
tolerance -- the standard heuristic molecular viewers use when CONECT is
absent.
"""
from dataclasses import dataclass

import numpy as np
from Bio.PDB import PDBParser
from scipy.spatial import cKDTree

from .geometry_data import GEO_CYLINDER, GEO_POINT, GEO_SPHERE
from .node import Node, NODE_TYPE_LINK
from .topology import TOPO_NONE

# Covalent radii in Angstroms (Cordero et al. 2008), for elements commonly
# found in proteins/nucleic acids/common ligands. Unlisted elements fall back
# to a carbon-like default.
_COVALENT_RADIUS = {
    'H': 0.31, 'C': 0.76, 'N': 0.71, 'O': 0.66, 'S': 1.05,
    'P': 1.07, 'F': 0.57, 'CL': 1.02, 'BR': 1.20, 'I': 1.39,
    'FE': 1.32, 'ZN': 1.22, 'MG': 1.41, 'CA': 1.76, 'NA': 1.66, 'K': 2.03,
}
_DEFAULT_COVALENT_RADIUS = 0.77

# CPK element coloring (0-255), the near-universal molecular-viewer convention.
_CPK_COLOR = {
    'H': (255, 255, 255), 'C': (144, 144, 144), 'N': (48, 80, 248),
    'O': (255, 13, 13), 'S': (255, 255, 48), 'P': (255, 128, 0),
    'F': (144, 224, 80), 'CL': (31, 240, 31), 'BR': (166, 41, 41),
    'I': (148, 0, 148), 'FE': (224, 102, 51), 'ZN': (125, 128, 176),
    'MG': (138, 255, 0), 'CA': (61, 255, 0), 'NA': (171, 92, 242), 'K': (143, 64, 212),
}
_DEFAULT_CPK_COLOR = (255, 20, 147)

_ATOM_RADIUS_SCALE = 0.4   # ball-and-stick style: shrink covalent radius so bonds stay visible
_BOND_TOLERANCE = 1.2      # distance <= tolerance * (radius_a + radius_b) counts as bonded
_BOND_SEARCH_RADIUS = 3.0  # generous KD-tree cutoff (Angstroms); the tolerance test above is tighter


@dataclass
class PdbImportResult:
    nodes: list[Node]
    atom_count: int
    bond_count: int
    chain_count: int


def _element_of(atom) -> str:
    return (atom.element or atom.name[0]).strip().upper()


def load_pdb_file(path: str) -> PdbImportResult:
    """Parse *path* (first MODEL only -- multi-MODEL trajectories are a
    follow-on) into a root node plus one GEO_SPHERE atom node per ATOM/HETATM
    and one NODE_TYPE_LINK bond node per inferred bond."""
    parser = PDBParser(QUIET=True)
    structure = parser.get_structure('pdb', path)
    model = next(iter(structure), None)
    if model is None:
        raise ValueError(f"No MODEL/atoms found in {path!r}")

    atoms = [atom for chain in model for residue in chain for atom in residue]
    if not atoms:
        raise ValueError(f"No atoms found in {path!r}")

    coords = np.array([atom.coord for atom in atoms], dtype=np.float64)
    coords -= coords.mean(axis=0)   # center on the structure's centroid, like every other import

    next_id = 1
    root_id = next_id
    next_id += 1
    nodes = [Node(
        id=root_id, type=5, parent_id=0, branch_level=0,
        translate_x=0.0, translate_y=0.0, translate_z=0.0,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=200, color_g=200, color_b=200, color_a=255,
        geometry=GEO_POINT, hide=1, topo=TOPO_NONE,
    )]

    atom_id_of = {}
    for i, (atom, pos) in enumerate(zip(atoms, coords)):
        element = _element_of(atom)
        radius = _COVALENT_RADIUS.get(element, _DEFAULT_COVALENT_RADIUS)
        color = _CPK_COLOR.get(element, _DEFAULT_CPK_COLOR)
        residue = atom.get_parent()
        chain = residue.get_parent()
        atom_id = next_id
        next_id += 1
        atom_id_of[i] = atom_id
        nodes.append(Node(
            id=atom_id, type=5, parent_id=root_id, branch_level=1,
            translate_x=float(pos[0]), translate_y=float(pos[1]), translate_z=float(pos[2]),
            rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
            scale_x=radius * _ATOM_RADIUS_SCALE,
            scale_y=radius * _ATOM_RADIUS_SCALE,
            scale_z=radius * _ATOM_RADIUS_SCALE,
            color_r=color[0], color_g=color[1], color_b=color[2], color_a=255,
            geometry=GEO_SPHERE, hide=0, topo=TOPO_NONE,
            text=f"{chain.id}:{residue.resname}{residue.id[1]} {atom.name}",
        ))

    tree = cKDTree(coords)
    bond_count = 0
    for i, j in tree.query_pairs(r=_BOND_SEARCH_RADIUS):
        r_i = _COVALENT_RADIUS.get(_element_of(atoms[i]), _DEFAULT_COVALENT_RADIUS)
        r_j = _COVALENT_RADIUS.get(_element_of(atoms[j]), _DEFAULT_COVALENT_RADIUS)
        dist = float(np.linalg.norm(coords[i] - coords[j]))
        if dist > _BOND_TOLERANCE * (r_i + r_j):
            continue
        bond_id = next_id
        next_id += 1
        nodes.append(Node(
            id=bond_id, type=NODE_TYPE_LINK, parent_id=atom_id_of[i], branch_level=1,
            translate_x=0.0, translate_y=0.0, translate_z=0.0,
            rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
            scale_x=1.0, scale_y=1.0, scale_z=1.0,
            color_r=220, color_g=220, color_b=220, color_a=255,
            # True ball-and-stick: a Link renders its geometry stretched
            # between its two ends (link_geometry.py), so a Cylinder bond is a
            # real 3-D rod running atom to atom, with `ratio` as its radius on
            # both cross-axes. This said GEO_SPHERE until 2026-08-15, which
            # meant nothing back when every non-Line id fell through to the
            # line renderer -- bonds drew as 1px lines. Set GEO_LINE here to go
            # back to those.
            geometry=GEO_CYLINDER, hide=0, topo=TOPO_NONE, ratio=0.05,
            extras={'child_id': atom_id_of[j]},
        ))
        bond_count += 1

    return PdbImportResult(
        nodes=nodes,
        atom_count=len(atoms),
        bond_count=bond_count,
        chain_count=len({chain.id for chain in model}),
    )
