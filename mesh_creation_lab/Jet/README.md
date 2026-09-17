# Mesh Jet

A twin-tail fighter and a four-ship echelon.

Open `mesh_jet_gv_node.csv`.

## What it demonstrates

**Hard and smooth surfaces on the same model.** An aircraft is the awkward
case: a smoothly lofted fuselage, thin wings with knife trailing edges, and a
chine where they meet that has to stay crisp. One crease angle handles all
three — there is no smoothing-group data in an OBJ and none is needed.

**Six materials, six meshes.** Airframe, radome, canopy, intakes, exhaust cans
and stores, because a node paints its mesh in a single colour. That is also
what lets the canopy be translucent (`color_a = 140`) while the airframe
beside it is opaque, and what lets the leader wear a different tint from its
wingmen without a second set of files.

**Build to an axis convention on purpose.** The model is made nose-along-+Y,
so a rig node's `rotate_z` is its heading, `rotate_x` its pitch and
`rotate_y` its bank. A banking echelon is then three numbers per aircraft
instead of a matrix. Deciding this before modelling is worth more than any
amount of fixing up afterwards.

**Links for what links are for.** The formation's stationing — who is flying
on whom — is drawn with Link nodes, not meshes. They are deliberately *not*
called contrails: a contrail trails one aircraft, it does not join two, and
drawing one as a link would be a picture of something untrue.

## Rebuilding it

```
<glyphviz-env>\python.exe mesh_creation_lab/Jet/build_jet.py
```

`wing()` takes span, root and tip chord, sweep, thickness, dihedral and twist,
so the planform is a few numbers away from a delta, a straight wing or a
swing-wing.
