# The 10-D superstring landscape, through the HCS

A GlyphViz lab on the shapes that superstring theory's six extra dimensions
can curl up into, drawn from two real, public datasets.

Superstrings live in 10 dimensions: our 4 plus 6 curled up into a tiny
**Calabi-Yau** shape, and the shape sets the 4-D physics (how many particle
generations, which forces). A Calabi-Yau threefold's two **Hodge numbers**
h11 and h21 count its size and shape moduli, and its Euler number is
χ = 2 (h11 − h21). **Mirror symmetry** swaps h11 and h21, so χ → −χ.

The lab draws with Jeff Sale's **Hyperdimensional Coordinate System (HCS)**
(on Dr. Art Springer's construction): every dimension is the real line folded
onto a circle, θ = 180 u / (1 + |u|) with u = value / scale, and a torus is
two nested HCS circles. See [`../bosonic_string_lab/`](../bosonic_string_lab/)
for the 26-D bosonic string; this lab shares its `string_kit.py`.

## The scene: Superstring Landscape (static)

| What | Data |
| --- | --- |
| Every glyph | One of the **30,108** distinct (h11, h21) pairs of the 473,800,776 Calabi-Yau hypersurfaces Kreuzer and Skarke built from reflexive 4-polytopes (2000) |
| **HCS torus** (left) | Ring angle = θ(χ; 152), tube angle = θ(h11 + h21; 184), the two medians at 90°. χ = 0 faces you; χ = ±∞ meet at the back |
| **Flat plot** (right) | The same pairs in the classic view: χ across, h11 + h21 up |
| Blue / orange / white | χ < 0 / χ > 0 / χ = 0 |
| **Gold** | \|χ\| = 6: three generations of quarks and leptons in the simplest heterotic models (208 pairs) |
| **Cyan** | The 7,890 CICY manifolds (Candelas et al. 1988): 265 distinct pairs, all with χ ≤ 0 |
| Tian-Yau | CICY (14, 23), χ = −18, divided by a free Z₃ symmetry: (6, 9), χ = −6, one of the first three-generation worlds (1986) |

The torus is CSV-native HCS: each glyph is a child of a Torus-topology node
with `translate_x` = the HCS angle of χ and `translate_y` = the HCS angle of
h11 + h21, so the app itself does the folding. With χ = 0 facing the viewer,
**mirror symmetry is a literal mirror**: the torus's left half is the right
half's reflection, because every pair's mirror is also in the list. The HCS
also holds the whole unbounded range (|χ| up to 960) on one ring.

## Open it

```bash
python landscape_data.py            # download the two datasets into data/ (once) and check them
python generate_landscape.py        # -> Superstring_Landscape/  (~5 s, 61,633 nodes)
python verify_superstring_lab.py    # optional: every check below; --paint also times repaints
```

`data/` and the scene folder are gitignored. Open
`Superstring_Landscape/Superstring_Landscape_gv_node.csv`. Turn off **View >
Show Grid** for the cleanest view. Hover or click a glyph to read its pair.

## What the checks hold

`verify_superstring_lab.py` loads the scene with the app's loader and
resolves transforms with `compute_world_transforms`:

- **The data**: 30,108 pairs with χ = 2 (h11 − h21), closed under mirror
  symmetry; 7,890 CICYs, every configuration matrix a threefold, the list's
  `Eta` column equal to χ, all χ ≤ 0. The 22 product manifolds (a torus × K3
  and the like) carry no Hodge numbers in the list and are left out.
- **The torus**: all 30,108 glyphs sit at their HCS points, checked against an
  independent torus formula.
- **The mirror**: every glyph is the exact reflection of its mirror pair's
  glyph across the χ = 0 plane.
- **The flat plot** and the gold/cyan highlights match the data.

## Data sources

- Kreuzer-Skarke Hodge data, `alltoric.spec.gz` (30,108 lines of
  `h11 h21 χ`): <http://hep.itp.tuwien.ac.at/~kreuzer/CY/CYcy.html>.
  M. Kreuzer and H. Skarke, *Complete classification of reflexive polyhedra in
  four dimensions*, hep-th/0002240.
- The CICY list, `cicylist.txt` (7,890 entries with configuration matrices):
  <https://www-thphys.physics.ox.ac.uk/projects/CalabiYau/cicylist/>.
  P. Candelas, A. M. Dale, C. A. Lütken, R. Schimmrigk (1988); Hodge numbers
  from P. Green, T. Hübsch, C. A. Lütken, Class. Quant. Grav. 6 (1989) 105.
- Tian-Yau: G. Tian and S.-T. Yau (1986).

## Next-scene ideas

- **Each CICY as a hyperglyph**: the configuration matrix (which projective
  spaces, how many equations) as nested HCS levels, so similar manifolds look
  alike.
- **Kaluza-Klein towers**: curled-up dimensions show up in 4-D as towers of
  heavier copies of familiar particles; Le Yaouanc and Richard
  (arXiv:2610.31458) read CMS four-jet excesses as KK gluons and quarks.
