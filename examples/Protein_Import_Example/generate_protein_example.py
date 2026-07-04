"""
Generate a small synthetic alpha-helix backbone (polyglycine, N/CA/C/O per
residue) as a standalone .pdb file, for examples/Protein_Import_Example/.

Built from first principles rather than a downloaded PDB entry: idealized
bond lengths/angles (Engh & Huber values) and idealized right-handed
alpha-helix backbone dihedrals (phi=-57, psi=-47, omega=180), placed via NeRF
(Parsons et al. 2005) -- the standard algorithm for building Cartesian
coordinates from internal (bond length/angle/dihedral) coordinates.
"""
import math
import numpy as np

# Idealized backbone bond lengths (Angstroms) and bond angles (degrees).
N_CA = 1.458
CA_C = 1.525
C_N  = 1.329   # peptide bond
C_O  = 1.231

ANG_N_CA_C   = 111.2
ANG_CA_C_N   = 116.2
ANG_C_N_CA   = 121.7
ANG_CA_C_O   = 120.8

PHI, PSI, OMEGA = -57.0, -47.0, 180.0   # ideal right-handed alpha helix
N_RESIDUES = 12


def nerf(a, b, c, length, angle_deg, dihedral_deg):
    """Place a new atom D bonded to C, given the preceding chain atoms A, B, C.
    length = |CD|; angle_deg = angle(B, C, D); dihedral_deg = dihedral(A, B, C, D).
    Standard NeRF placement (Parsons et al., J. Comput. Chem. 2005)."""
    angle = math.radians(angle_deg)
    dihedral = math.radians(dihedral_deg)
    d2 = np.array([
        -length * math.cos(angle),
        length * math.sin(angle) * math.cos(dihedral),
        length * math.sin(angle) * math.sin(dihedral),
    ])
    bc = c - b
    bc_hat = bc / np.linalg.norm(bc)
    n = np.cross(b - a, bc_hat)
    n_hat = n / np.linalg.norm(n)
    m_hat = np.cross(n_hat, bc_hat)
    basis = np.array([bc_hat, m_hat, n_hat]).T
    return c + basis @ d2


def build_backbone(n_residues):
    """Returns list of (resseq, atom_name, element, xyz) for an N/CA/C/O
    polyglycine backbone of n_residues in an idealized alpha-helix."""
    # Bootstrap residue 1 manually (NeRF needs 3 preceding atoms).
    n1 = np.array([0.0, 0.0, 0.0])
    ca1 = n1 + np.array([N_CA, 0.0, 0.0])
    ang = math.radians(180.0 - ANG_N_CA_C)
    c1 = ca1 + CA_C * np.array([math.cos(ang), math.sin(ang), 0.0])

    atoms = []  # (resseq, name, element, xyz)
    N_pos, CA_pos, C_pos = n1, ca1, c1
    atoms.append((1, 'N', 'N', N_pos))
    atoms.append((1, 'CA', 'C', CA_pos))
    atoms.append((1, 'C', 'C', C_pos))

    prev_N, prev_CA, prev_C = N_pos, CA_pos, C_pos

    for resseq in range(1, n_residues + 1):
        O_pos = nerf(prev_N, prev_CA, prev_C, C_O, ANG_CA_C_O, PSI + 180.0)
        atoms.append((resseq, 'O', 'O', O_pos))

        if resseq == n_residues:
            break

        next_N = nerf(prev_N, prev_CA, prev_C, C_N, ANG_CA_C_N, PSI)
        next_CA = nerf(prev_CA, prev_C, next_N, N_CA, ANG_C_N_CA, OMEGA)
        next_C = nerf(prev_C, next_N, next_CA, CA_C, ANG_N_CA_C, PHI)

        atoms.append((resseq + 1, 'N', 'N', next_N))
        atoms.append((resseq + 1, 'CA', 'C', next_CA))
        atoms.append((resseq + 1, 'C', 'C', next_C))

        prev_N, prev_CA, prev_C = next_N, next_CA, next_C

    # Sort so each residue's atoms are grouped N, CA, C, O in resseq order.
    order = {'N': 0, 'CA': 1, 'C': 2, 'O': 3}
    atoms.sort(key=lambda a: (a[0], order[a[1]]))
    return atoms


def atom_line(serial, name, resname, chain, resseq, xyz, element):
    """Fixed-width PDB ATOM record (cols 1-80, per the wwPDB format spec)."""
    x, y, z = xyz
    return (
        f"ATOM  {serial:>5}  {name:<3} {resname:<3} {chain}{resseq:>4}    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}{1.00:6.2f}{0.00:6.2f}"
        f"{'':10}{element:>2}  "
    )


def main(path):
    atoms = build_backbone(N_RESIDUES)
    lines = []
    for i, (resseq, name, element, xyz) in enumerate(atoms, start=1):
        lines.append(atom_line(i, name, 'GLY', 'A', resseq, xyz, element))
    lines.append(f"TER   {len(atoms) + 1:>5}      GLY A{N_RESIDUES:>4}")
    lines.append("END")
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    print(f"Wrote {len(atoms)} atoms, {N_RESIDUES} residues to {path}")


if __name__ == '__main__':
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else 'alpha_helix_example.pdb')
