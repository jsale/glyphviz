# Immersive VR

**[GlyphViz Web](https://www.iluvdata.org/glyphvizweb/)** can put you *inside*
a scene. Open the page in a headset's browser, press **Enter VR**, and the
glyphs are around you at whatever size you choose — from a tabletop model you
lean over to a structure you fly through.

There is nothing to install and no PC-VR link. It is standard
[WebXR](https://www.w3.org/TR/webxr/), so the whole thing is a URL somebody can
send you.

!!! info "Headset support"
    Immersive mode uses the browser's own WebXR `immersive-vr` support, so it
    runs on any headset whose browser provides it.

    It has been **confirmed on hardware on a Meta Quest 3**. Apple Vision Pro
    (Safari on visionOS) provides WebXR and is expected to work, but has not
    been verified here — if you try it, [let us know](../about.md).

    If the browser reports no WebXR support, the **Enter VR** button simply
    doesn't appear.

## Entering and leaving

**Enter VR** lives in the web app's Scene panel, in the world settings group
next to Stereo 3D.

On entry the scene is placed in front of you rather than left wherever the
desktop camera happened to be: sized to about **20 m** across, **15 m** ahead,
and **0.35 m** below eye level, positioned from your actual head pose — so it
lands in front of you whichever way you are facing when you press the button.

Leaving restores the desktop camera exactly as it was.

## Controls

| Input | What it does |
| --- | --- |
| **Left thumbstick** | Fly, at 3 m/s at full deflection, in the direction you are *looking*. Plane-locked, so looking down while flying forward never sinks you into the floor. |
| **Right thumbstick** | Turn (90°/s) and rise/fall. Turning pivots about your head, so you rotate in place rather than being swung sideways through the scene. |
| **Squeeze (one grip)** | Grab the world and drag it. The point you grabbed stays pinned to your hand. |
| **Squeeze (both grips)** | Resize and turn the world about the point between your hands — pull apart to grow, push together to shrink. This is how you get between a tabletop model and a structure you fly through without touching a menu. |
| **Trigger** | Select the node your controller ray is pointing at. A miss clears the selection. |
| **A / X** | Re-fit the scene in front of you — the way out of having flown somewhere you can't see anything from. |
| **B / Y** | Play / pause [Channels](channels-animation.md) playback. |
| **Left X** | Hide / show the wrist panel. |

Flight is suppressed while a hand is grabbing, so a grab-drag is never fighting
a thumbstick.

!!! tip "Scale is honest, not a cheat"
    Resizing scales your interpupillary distance and head motion by the same
    factor as the scene, so the stereo depth stays truthful at any size. A
    "tabletop" glyph really does read as a small object you are leaning over,
    not as a huge one far away.

## The wrist panel

A control panel rides your **left grip** — look at your hand and it is there.
Point the other hand's ray at it and pull the trigger.

It is billboarded toward your head rather than rigidly mounted, so it stays
readable through the poses a wrist actually turns through. The panel takes the
trigger press when your ray is on it, and the pointing laser stops at its
surface, so you never accidentally select a node behind it.

What it carries:

- **Channels transport** — stop, play/pause, and a frame scrubber. A scene with
  no channel data shows no transport at all rather than a dead Play button.
- **Draw limit** — − / + step the same decimation factors the `\` key uses on
  the desktop. This is the frame-rate lever.
- **Scene stepper** — ‹ › walk the built-in example scenes.
- **Room view / Tabletop** — two framings: the 20 m entry size, and a 1.5 m
  model at arm's length.
- **Selection readout** — the inspector reduced to a glance.

Anything that *edits* node data is deliberately left out. Authoring in a
headset is a separate problem, and a wrist panel is a poor place to discover it.

## Labels

The tag-label overlay is a 2D layer stacked over the canvas, so a headset never
sees it. Instead, the **selected** node's label is drawn in the scene as a
billboard that turns to face you.

That is unconditional — the scene-wide Show Tag Labels toggle lives on a key and
a checkbox, neither of which a headset can reach.

## What stands aside during a session

| Feature | In a session |
| --- | --- |
| Cross-eye stereo 3D | Off — the headset compositor owns stereo now |
| Orbit controls / Camera Mode | Stand aside |
| Follow Selected | Inert |
| Transform gizmo | Detaches (it drags from a screen-space pointer, and a headset has none). The armed mode stays sticky, so it returns on exit. |
| Save PNG | Reports itself unavailable rather than silently saving the desktop mirror image |

## Performance

Immersive mode is honest for scenes in the **low thousands of nodes** — a
headset renders two eyes at 72–90 Hz, and the web renderer issues roughly one
draw call per glyph.

Past that, the **draw limit** (the wrist panel's − / +, or `\` on a keyboard) is
the lever: it decimates what is drawn without touching the data. Larger scenes
are a batching problem that would help the flat browser app just as much, and
it isn't solved yet.

## Not the same thing as the desktop XR spike

GlyphViz's desktop repository also contains `glyphviz_xr`, an OpenXR renderer
that runs a scene on a tethered PC-VR headset. It shares the desktop app's
`glyphviz_core` kernel and was where this interaction vocabulary was worked out
— the flight speed, turn rate and grab behavior here are ported from it
directly.

It remains an internal spike: PC-tethered, not packaged, and not maintained
alongside the app. The browser is where immersive GlyphViz is actually usable,
because a headset can open a URL.

## Next step

Return to the [Reference overview](index.md), or see the [Roadmap](../roadmap.md)
for what is planned next in the headset — passthrough AR, hand tracking, comfort
options, and authoring gestures.
