#!/usr/bin/env python3
"""
skymap.py — 2MRS from a catalogue of angles into a box of galaxies.

Shared by `build_cosmic_scenes.py`, `verify_astro.py` and `verify_scenes.py`
so the builder and its checkers use one definition of where a galaxy is.

Three steps, none of them optional if the picture is to be honest:

1. **Velocity to the CMB frame.**  A catalogue records the velocity measured
   from here, and here is moving: the Sun runs at 369.82 km/s toward galactic
   (264.021, +48.253) relative to the microwave background.  Left
   uncorrected, that dipole tilts every distance in the sky by up to
   +/-370 km/s, which at these depths is a systematic error of several Mpc
   that rotates with direction.

2. **Velocity to distance.**  d = v_CMB / H0 with H0 = 70 km/s/Mpc.  This is
   a *redshift* distance and it is not the true one: a galaxy's own motion
   inside a cluster adds to its redshift, so clusters come out smeared along
   the line of sight into the radial spikes known as fingers of God.  They
   are an artefact of the method, they are visible in the finished scene, and
   they all point at the observer, which is how you recognise them.

3. **Galactic to supergalactic coordinates.**  The local universe is
   flattened, and the plane it is flattened into is not the Milky Way's.  De
   Vaucouleurs' supergalactic frame puts that structure in the SGX-SGY plane,
   so the Local Supercluster lies flat instead of cutting across the box at
   an angle.  The frame is defined by its north pole at galactic
   (47.37, +6.32) and its zero of longitude at galactic (137.37, 0).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "2mrs.csv.gz"

H0 = 70.0                     # km/s/Mpc
C_KMS = 299792.458

# Solar motion with respect to the CMB (Planck 2018 dipole).
CMB_APEX_L, CMB_APEX_B = 264.021, 48.253
CMB_APEX_V = 369.82           # km/s

# De Vaucouleurs supergalactic frame, in galactic coordinates.
SG_POLE_L, SG_POLE_B = 47.37, 6.32
SG_ORIGIN_L, SG_ORIGIN_B = 137.37, 0.0

# 2MRS is complete to this total K_s magnitude (Huchra et al. 2012).
K_COMPLETE = 11.75

# Redshift distance is meaningless where peculiar motion dominates, and the
# catalogue's few negative velocities are genuinely blueshifted neighbours.
V_MIN = 500.0                 # km/s, CMB frame
V_MAX = 30000.0               # km/s -> 428 Mpc


def unit_vectors(lon_deg, lat_deg) -> np.ndarray:
    """(N, 3) unit vectors from spherical degrees."""
    lon = np.radians(np.asarray(lon_deg, dtype=float))
    lat = np.radians(np.asarray(lat_deg, dtype=float))
    return np.stack([np.cos(lat) * np.cos(lon),
                     np.cos(lat) * np.sin(lon),
                     np.sin(lat)], axis=-1)


def supergalactic_basis() -> np.ndarray:
    """Rows are the supergalactic axes expressed in galactic coordinates.

    Built from the two published directions rather than from a copied matrix,
    so the frame can be checked: `verify_astro.py` asserts the result is
    orthonormal and right-handed.
    """
    z = unit_vectors(SG_POLE_L, SG_POLE_B)
    x = unit_vectors(SG_ORIGIN_L, SG_ORIGIN_B)
    # The published pole and origin are quoted to 0.01 degrees, so they are
    # very nearly but not exactly perpendicular; project the residual out.
    x = x - z * float(np.dot(x, z))
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return np.stack([x, y, z])


SG_BASIS = supergalactic_basis()


def cmb_frame(v_helio, glon, glat) -> np.ndarray:
    """Heliocentric velocity -> CMB-frame velocity, km/s."""
    n = unit_vectors(glon, glat)
    apex = unit_vectors(CMB_APEX_L, CMB_APEX_B)
    return np.asarray(v_helio, dtype=float) + CMB_APEX_V * (n @ apex)


def supergalactic_xyz(glon, glat, dist_mpc) -> np.ndarray:
    """(N, 3) supergalactic Cartesian positions in Mpc."""
    n = unit_vectors(glon, glat)
    return (n @ SG_BASIS.T) * np.asarray(dist_mpc, dtype=float)[:, None]


def abs_mag(k_mag, dist_mpc) -> np.ndarray:
    """Absolute K_s magnitude.  No k-correction or extinction term: at these
    redshifts both are small compared with the scatter, and the value is used
    only to define a volume-limited cut and to size a glyph."""
    d = np.asarray(dist_mpc, dtype=float)
    return np.asarray(k_mag, dtype=float) - (5.0 * np.log10(d) + 25.0)


@dataclass
class Catalogue:
    df: pd.DataFrame          # one row per galaxy, with derived columns

    def __len__(self) -> int:
        return len(self.df)

    @property
    def xyz(self) -> np.ndarray:
        return self.df[["sgx", "sgy", "sgz"]].to_numpy()

    def volume_limited(self, d_max: float) -> pd.DataFrame:
        """The subsample within `d_max` Mpc that the survey could see all the
        way out to `d_max`.

        A magnitude-limited catalogue thins out with distance simply because
        faint galaxies drop below the flux limit, so any grouping run on the
        raw sample finds "richer" structures nearby purely as an artefact.
        Cutting to galaxies brighter than the limiting absolute magnitude at
        `d_max` removes that gradient: every galaxy in the subsample would
        have been detected anywhere inside the volume.
        """
        m_lim = K_COMPLETE - (5.0 * np.log10(d_max) + 25.0)
        sel = (self.df.dist <= d_max) & (self.df.abs_k <= m_lim)
        out = self.df[sel].copy()
        out.attrs["m_lim"] = m_lim
        out.attrs["d_max"] = d_max
        return out


def load(path: Path | str = DATA) -> Catalogue:
    """Read 2MRS and attach CMB velocity, distance, supergalactic position."""
    df = pd.read_csv(path, encoding="utf-8")
    df = df[df.cz.notna() & df.k_mag.notna()].copy()

    df["v_cmb"] = cmb_frame(df.cz.to_numpy(), df.glon.to_numpy(),
                            df.glat.to_numpy())
    df = df[(df.v_cmb > V_MIN) & (df.v_cmb < V_MAX)].copy()
    df["dist"] = df.v_cmb / H0

    xyz = supergalactic_xyz(df.glon.to_numpy(), df.glat.to_numpy(),
                            df.dist.to_numpy())
    df["sgx"], df["sgy"], df["sgz"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    df["abs_k"] = abs_mag(df.k_mag.to_numpy(), df.dist.to_numpy())
    return Catalogue(df.reset_index(drop=True))


# ---------------------------------------------------------------------------
# Local density
# ---------------------------------------------------------------------------
def knn_density(xyz: np.ndarray, k: int = 6) -> np.ndarray:
    """Log10 of the k-nearest-neighbour density estimate, in galaxies/Mpc^3.

    Colour has to carry the web or a point cloud is a fog, and the quantity
    that makes filaments and voids visible is how crowded a galaxy's own
    neighbourhood is.  The estimator is the standard one: with r_k the
    distance to the kth neighbour, n = k / (4/3 pi r_k^3).

    It is computed in redshift space, so a finger of God reads as dense along
    its whole length.  That is a property of the data, not of the estimator.
    """
    from scipy.spatial import cKDTree
    tree = cKDTree(xyz)
    d, _ = tree.query(xyz, k=k + 1)          # column 0 is the point itself
    r_k = np.maximum(d[:, k], 1e-3)
    return np.log10(k / ((4.0 / 3.0) * np.pi * r_k ** 3))


# ---------------------------------------------------------------------------
# Friends of friends
# ---------------------------------------------------------------------------
def friends_of_friends(xyz: np.ndarray, b_perp: float, b_par: float
                       ) -> np.ndarray:
    """Percolation grouping with a line-of-sight stretch; returns group ids.

    Two galaxies are friends when their separation fits inside a cylinder
    `b_perp` in radius and `b_par` half-length, with the cylinder's long axis
    pointing at the observer.  The stretch is what keeps a cluster from being
    shattered by its own fingers of God: real clusters are elongated radially
    by several Mpc in redshift space, so an isotropic linking length large
    enough to hold one together would bridge unrelated structures sideways.

    Galaxies in no group at all get id -1.
    """
    from scipy.spatial import cKDTree

    tree = cKDTree(xyz)
    pairs = np.array(sorted(tree.query_pairs(r=b_par)), dtype=np.int64)
    if len(pairs) == 0:
        return np.full(len(xyz), -1, dtype=np.int64)

    a, b = xyz[pairs[:, 0]], xyz[pairs[:, 1]]
    # Split each separation about the bisector of the two lines of sight,
    # which is the observer direction for the pair.
    mid = (a + b) / 2.0
    los = mid / np.linalg.norm(mid, axis=1, keepdims=True)
    sep = a - b
    d_par = np.abs(np.einsum("ij,ij->i", sep, los))
    d_perp = np.sqrt(np.maximum(np.einsum("ij,ij->i", sep, sep) - d_par ** 2,
                                0.0))
    keep = pairs[(d_perp <= b_perp) & (d_par <= b_par)]

    # Union-find over the surviving pairs.
    parent = np.arange(len(xyz), dtype=np.int64)

    def find(i: int) -> int:
        root = i
        while parent[root] != root:
            root = parent[root]
        while parent[i] != root:            # path compression
            parent[i], i = root, parent[i]
        return root

    for i, j in keep:
        ri, rj = find(int(i)), find(int(j))
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    roots = np.array([find(i) for i in range(len(xyz))], dtype=np.int64)
    counts = np.bincount(roots)
    out = np.full(len(xyz), -1, dtype=np.int64)
    real = np.where(counts >= 2)[0]
    remap = {int(r): n for n, r in enumerate(real)}
    for i, r in enumerate(roots):
        if counts[r] >= 2:
            out[i] = remap[int(r)]
    return out


# ---------------------------------------------------------------------------
# Landmarks
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Landmark:
    name: str
    ra: float                 # J2000 degrees
    dec: float
    cz: float                 # km/s, heliocentric; ignored when dist is set
    dist: float | None = None  # Mpc, when a direct distance is the better one
    note: str = ""


#: Structures famous enough to be worth naming in the scene.  Positions are
#: from the literature, but nothing here is taken on trust: `verify_astro.py`
#: counts 2MRS galaxies around each one and fails the build unless the marker
#: sits on a genuine overdensity, which is a strong check on both the
#: coordinates and the whole coordinate pipeline.
LANDMARKS: tuple[Landmark, ...] = (
    Landmark("Virgo Cluster", 187.706, 12.391, 1050, dist=16.5,
             note="M87; redshift distance fails this close, so 16.5 Mpc "
                  "is the Cepheid/SBF value"),
    Landmark("Fornax Cluster", 54.621, -35.451, 1425, dist=19.0,
             note="NGC 1399"),
    Landmark("Centaurus Cluster", 192.204, -41.311, 3400),
    Landmark("Hydra Cluster", 159.178, -27.528, 3683),
    Landmark("Norma Cluster", 243.554, -60.834, 4871,
             note="Abell 3627, the core of the Great Attractor"),
    Landmark("Perseus Cluster", 49.951, 41.512, 5366, note="Abell 426"),
    Landmark("Coma Cluster", 194.953, 27.981, 6925, note="Abell 1656"),
    Landmark("Hercules Supercluster", 241.299, 17.721, 11000,
             note="Abell 2151"),
    Landmark("Shapley Supercluster", 201.987, -31.505, 14480,
             note="Abell 3558, the richest concentration within 300 Mpc"),
)


def equatorial_to_galactic(ra, dec) -> tuple[np.ndarray, np.ndarray]:
    """J2000 equatorial degrees -> galactic degrees.

    The galactic frame's pole and origin, like the supergalactic ones above,
    are built from published directions rather than a copied matrix.
    """
    pole = unit_vectors(192.85948, 27.12825)      # galactic north, J2000
    lon0 = unit_vectors(266.40510, -28.93617)     # galactic centre, J2000
    x = lon0 - pole * float(np.dot(lon0, pole))
    x /= np.linalg.norm(x)
    y = np.cross(pole, x)
    basis = np.stack([x, y, pole])

    n = unit_vectors(ra, dec) @ basis.T
    n = np.atleast_2d(n)
    lon = np.degrees(np.arctan2(n[:, 1], n[:, 0])) % 360.0
    lat = np.degrees(np.arcsin(np.clip(n[:, 2], -1.0, 1.0)))
    return lon, lat


def landmark_xyz(lm: Landmark) -> np.ndarray:
    """A landmark's supergalactic position, through the same pipeline as the
    galaxies — including the CMB correction, when it uses a redshift."""
    glon, glat = equatorial_to_galactic(lm.ra, lm.dec)
    if lm.dist is not None:
        d = np.array([lm.dist])
    else:
        d = cmb_frame(np.array([lm.cz]), glon, glat) / H0
    return supergalactic_xyz(glon, glat, d)[0]
