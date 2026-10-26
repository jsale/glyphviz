# Tensors, from the Arrow Up

Most people who meet vectors in a physics course get comfortable with them: an arrow, a set of perpendicular unit vectors, three components. Then the word **tensor** arrives, usually as a grid of nine numbers with a transformation rule attached, and the picture goes missing. This example is three animated scenes that rebuild the picture one step at a time:

- **Scene 1** asks what a vector's components really are.
- **Scene 2** makes the step from a vector to a tensor.
- **Scene 3** puts a tensor to work in everyday mechanics: why a book thrown spinning about its middle axis flips over.

The idea running through all three is this: **a tensor is a geometric thing that doesn't care about your choice of axes. Its components are the answers it gives when you question it with basis vectors, and its rank is how many basis vectors each question takes.**

![Scene 2 mid-tour: the tensor drawn as an ellipsoid that never moves, the turning basis and the three output arrows T e1, T e2, T e3, beside the 3×3 grid of components, the rank ladder and the scope](../assets/examples/tensors-grid.png)

**Try it:** download the scenes below (or [the full examples set](../getting-started/installation.md#example-scenes)), then open the `*_gv_node.csv` inside, or drag the zip straight onto the GlyphViz window. All three are animated: press **Space** to play, and each loops. Turn off **View > Show Grid** for the cleanest view. The captions sit on a board facing the camera the scene opens with, so they read best from that view.

[:material-download: Vectors_and_Bases (173 KB)](https://iluvdata.org/glyphviz/zips/Tensors_Vectors_and_Bases.zip){ .md-button }
[:material-download: Vector_to_Tensor (369 KB)](https://iluvdata.org/glyphviz/zips/Tensors_Vector_to_Tensor.zip){ .md-button }
[:material-download: Spinning_Book (699 KB)](https://iluvdata.org/glyphviz/zips/Tensors_Spinning_Book.zip){ .md-button }

The colours are the same in every scene. The basis vectors **e1, e2, e3** are **red, green and blue**, the vector **v** is **gold**, and on the boards **warm bars are positive, cool bars negative**.

## Scene 1: One Arrow, Many Shadows

![A gold arrow v with the basis e1, e2, e3; light-coloured legs walk v1 along e1, then v2 along e2, then v3 along e3 to v's tip, and grey drop lines fall from the tip onto each axis](../assets/examples/tensors-vectors-stage.png)

A fixed gold arrow, and a set of three perpendicular unit arrows (an orthonormal **basis**) that turns around it. The scene runs 66 seconds in three acts.

| Act | What happens | What to notice |
| --- | --- | --- |
| 1 | The basis lines up with the room's axes. The arrow is rebuilt one leg at a time. | **v = v1 e1 + v2 e2 + v3 e3.** The components are walking directions: go v1 along e1, then v2 along e2, then v3 along e3, and you arrive at the tip. |
| 2 | The basis turns through a closed loop of rotations. | The gold arrow never moves, but the legs, the drop lines and the bars all change. A component **v_i = v · e_i** is the arrow's shadow on one basis vector, and a shadow depends on where you shine the light from. |
| 3 | The basis holds still and the *arrow* turns the opposite way. | The bars and the history curve repeat Act 2 exactly. The components can't tell which one turned: they only know the arrow *relative to* the basis. |

![The whole first scene in Act 2: the turning basis on the left; the component bars, the stacked bar that never changes height, and the component history on the right](../assets/examples/tensors-vectors.png)

The board on the right shows three things:

- **The three component bars**, changing.
- **A stacked bar of v1², v2² and v3²**. Its colours trade places as the basis turns, but its height never changes: v1² + v2² + v3² = |v|² in every basis. A quantity that comes out the same in every basis is a **scalar**, or rank-0 tensor.
- **The component history** for the whole run, with a time cursor. Acts 2 and 3 trace the same curves.

The caption gives the rule that ties it together. When the basis turns by a rotation matrix R, the new components are v′_i = R_ji v_j, summed over j: **one rotation matrix for the one index.** That single R is what makes a vector a tensor of **rank 1**.

## Scene 2: From Vector to Tensor

The tensor in this scene is a symmetric one with principal values 2.0, 1.2 and 0.5, turned to an arbitrary orientation. The scene runs 105 seconds in five acts.

### Act 1: a tensor is a machine

![A white probe arrow n inside a unit sphere, and the orange output T n, longer and pointing a different way; the path of the output's tip spirals out around the sphere](../assets/examples/tensors-machine.png)

Forget components for a moment. A rank-2 tensor T is a **linear machine**: feed it a direction n, and it hands back a vector T n. A probe (white) sweeps over every direction, and the output (orange) paints a trail as it goes. The trail fills in an **ellipsoid**, and that ellipsoid *is* the tensor, drawn with no basis anywhere.

Notice that T n usually doesn't point along n. It does only along the ellipsoid's three axes, the tensor's **principal axes**.

### Act 2: its components need two basis vectors

To write the machine down as numbers, pick a basis and feed it each basis vector in turn. The three outputs T e1, T e2, T e3 appear in light red, green and blue. Read each output along e1, e2 and e3, and you have the grid:

**T_ij = e_i · (T e_j).** Column j of the grid is T e_j, read along each basis vector.

Drop lines show column 1 being read. Every component uses **two** basis vectors, one fed in and one read out. That's the whole step up from a vector.

### Act 3: turn the basis

The basis tours the same loop as in Scene 1. The ellipsoid never moves, but all nine numbers change. One combination never does: **tr T = T11 + T22 + T33**, the tensor's version of Scene 1's |v|². Scene 1's gold vector rides along so the two can be compared, and the **rank ladder** on the board sets them side by side:

| Rank | Object | Numbers | Rotation matrices in its rule |
| --- | --- | --- | --- |
| 0 | tr T | 1 (never moves) | none |
| 1 | v | 3 | one: v′_i = R_ki v_k |
| 2 | T | 9 | two: T′_ij = R_ki R_lj T_kl |

Count the R's in the rule, and that's the rank.

### Act 4: twice per turn

![The scope: against the angle the basis has turned, tr T is flat, v1′ makes one wave per turn, and T11′ and T12′ make two](../assets/examples/tensors-scope.png)

The basis makes one steady turn about e3, and the **scope** plots components against the angle turned:

- a scalar never waves;
- a vector component waves **once** per turn;
- a tensor component waves **twice** per turn.

Rank shows up as frequency. The reason is visible in the ellipsoid: an arrow has a head, so it takes a full turn to come back to itself, but an ellipsoid has no head and looks the same after half a turn.

### Act 5: the principal axes

![After Act 5: the basis lies along the ellipsoid's own axes, each output arrow T e_j lies along its basis vector, and the grid has bars only on its diagonal: 2.0, 1.2 and 0.5](../assets/examples/tensors-principal.png)

The basis turns onto the ellipsoid's own axes. The off-diagonal bars shrink to zero, and the diagonal ones become **2.0, 1.2 and 0.5**: the ellipsoid's semi-axes. Each output arrow now lies along its own basis vector, T e_i = λ_i e_i.

This is **diagonalization**, and the scene shows what it really is: choosing the basis the tensor agrees with. The tensor itself never changed.

## Scene 3: The Spinning Book

![Three books spinning in free space with their gold L and white ω arrows, their room-basis numbers beneath, and the sphere on the right showing L as each book sees it](../assets/examples/tensors-book.png)

Throw a book in the air spinning about its long axis, or about the axis through its cover, and it spins steadily. Spin it about the remaining middle axis, and it flips over as it goes. This is the **tennis-racket theorem**, or the **Dzhanibekov effect** after the cosmonaut who filmed a wing nut doing it on a space station. It comes from the inertia tensor.

Three identical books (2.4 × 1.5 × 0.36 m, mass 1 kg) float in free space. Each is spun once every 3 seconds about one of its principal axes, with the same 1% nudge off that axis:

| Book | Spin axis | Moment of inertia | Result |
| --- | --- | --- | --- |
| 1 | long axis | smallest, 0.198 kg m² | steady: tilts at most 2.5° |
| 2 | middle axis | middle, 0.491 kg m² | flips, 7 times in 60 seconds |
| 3 | through the cover | largest, 0.668 kg m² | steady: tilts at most 0.6° |

### L = I ω, and I is a tensor

In an introductory course, angular momentum is L = I ω with I a single number, so L and ω always point the same way. For a real body, **I is a rank-2 tensor**: Scene 2's machine again, with angular velocity going in and angular momentum coming out. So L and ω line up only along a principal axis.

With no torque acting, L can't change, and the **gold** arrow holds still in the room. The **white** ω arrow is free to wander. Mid-flip it swings about 30° away from L, and the gauge under each book shows the angle.

![Close on book 2 mid-flip: the gold L arrow points straight up while the white ω arrow has swung well away from it, and the book is tipping over its own middle axis](../assets/examples/tensors-book-flip.png)

### Same tensor, two bases

- **In the book's own basis**, I is diagonal and constant: (I1, I2, I3).
- **In the room's basis**, the grid under each book shows its nine components swinging, twice per turn. That's Scene 2's rank-2 signature again.

Beside the grid, ω's three room components swing too. Yet **L = I ω, their product, never moves.** Two changing things combine into one fixed one.

The wire ellipsoid around each book is its inertia tensor drawn as in Scene 2. It's fattest about the axis through the cover, the axis the mass is spread farthest from.

### Why the middle axis is unstable

![The sphere of angular momentum in the book's own frame: small closed loops around +e1 and +e3, the red separatrix circles crossing at ±e2, and the three books' paths](../assets/examples/tensors-lsphere.png)

The sphere on the right shows L **as the book sees it**, in the book's own frame. Two things are conserved, and each confines L:

- **Its size, |L|.** L stays on a sphere.
- **The kinetic energy**, L1²/2I1 + L2²/2I2 + L3²/2I3. L stays on an ellipsoid.

So L can only ride the curves where the two surfaces meet. Around ±e1 and ±e3, those curves are small closed loops, which is why spin about those axes is stable. Through ±e2 runs the red **separatrix**, a pair of great circles at exactly the energy of a pure middle-axis spin. Book 2 rides near it from +e2 to −e2 and back, and **every crossing is a flip**. Stability is a property of the tensor's geometry.

A real book also loses energy as it flexes. That makes even the long-axis spin unstable in the end, and only the axis with the largest moment survives. That was the lesson of the Explorer 1 satellite in 1958. The scene shows the ideal rigid body.

## How it's built and checked

| Scene | Nodes | Animation |
| --- | --- | --- |
| Vectors and Bases | 1,106 | 88 tracks, 1,980 frames |
| Vector to Tensor | 1,294 | 237 tracks, 3,150 frames |
| Spinning Book | 10,481 | 648 tracks, 1,800 frames |

- **Every arrow is two Link glyphs**: a cylinder for the shaft and a cone for the head, stretched between nodes whose positions are channels.
- **Each basis and each book is a frame node** whose rotation is a channel. Everything inside it rides along.
- **The ellipsoids are wire spheres** scaled along their principal axes. A translucent solid would hide the arrows inside it.
- **The books' motion** solves Euler's equations for a rigid body with a fourth-order Runge–Kutta method, ten steps per frame.

Everything is checked through GlyphViz's own objects: the app's loaders, its playback engine, and its transform code, which says where each thing is drawn.

- **Scene 1:**
    - the drawn basis is the intended rotation;
    - the legs end exactly on the arrow's tip, and every drop line meets its axis at a right angle;
    - the bars are the dot products, and the |v|² stack never changes height;
    - Act 3 replays Act 2's bars exactly.
- **Scene 2:**
    - the ellipsoid is exactly T applied to the unit sphere;
    - every output arrow tip lies on it;
    - the nine bars are Rᵀ T R, and tr T never changes;
    - Act 5 ends exactly diagonal;
    - the scope's dominant frequency is 0, 1 and 2 waves per turn for ranks 0, 1 and 2.
- **Scene 3:**
    - angular momentum and energy are conserved to 10⁻⁹ over the full minute;
    - the drawn books are the computed orientations;
    - the drawn I bars times the drawn ω bars equal the drawn L bars;
    - book 2 flips, and books 1 and 3 don't;
    - every curve on the sphere keeps its energy to 10⁻¹².

The generators and the checks are in the [`tensor_lab`](https://github.com/jsale/glyphviz/tree/master/tensor_lab) folder of the GlyphViz repository.

## Where it could go next

These scenes stay with **Cartesian tensors**: perpendicular unit basis vectors related by rotations. That's all the inertia tensor, the stress tensor or a conductivity tensor needs. Three natural next steps:

- **Skewed bases, and upper and lower indices.** If the basis is allowed to stretch and shear, Scene 1's two pictures of a component come apart: the walking directions (the legs) and the shadows (the drop lines) are no longer the same numbers. These are the *contravariant* and *covariant* components, and the **metric tensor** g_ij = e_i · e_j converts between them. This is the door to general relativity.
- **The stress tensor**, which gave tensors their name (from the Latin *tendere*, to stretch). Cut a loaded block along a plane with normal n, and the force per unit area on the cut is t = σ n. It is generally not along n, so it splits into a pull and a shear. Turning the cut sweeps out Mohr's circle.
- **A tensor field**: one ellipsoid at every point, such as the stress around a hole in a plate or water diffusion in the brain's white matter.

## Credits

This example teaches standard physics rather than one paper. The rigid-body equations are Euler's. The polhode picture of torque-free motion is Poinsot's, as presented in Landau and Lifshitz, *Mechanics*, §37. The tennis-racket theorem is discussed by Ashbaugh, Chicone and Cushman, "The Twisting Tennis Racket," *Journal of Dynamics and Differential Equations* 3 (1991). The scenes, simulations and checks are this example's own, and so are any errors.
