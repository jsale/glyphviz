"""Render preview frames inside Blender (Workbench engine - fast, flat colours).

Set FRAMES / VIEW before running via bl.py:  python bl.py run blender_preview.py
"""
import math
import os

import bpy

OUT = r"C:\Users\jsale\source\repos\glyphviz\blender_lab\out\blender_frames"
FRAMES = [1, 61, 121, 181]
RES = (1280, 720)
os.makedirs(OUT, exist_ok=True)

scn = bpy.context.scene
scn.render.engine = "BLENDER_WORKBENCH"
scn.render.resolution_x, scn.render.resolution_y = RES
scn.render.image_settings.file_format = "PNG"
sh = scn.display.shading
sh.light = "STUDIO"
sh.color_type = "MATERIAL"
sh.show_object_outline = False
scn.world.color = (0.04, 0.05, 0.08)

cam = bpy.data.objects.get("PreviewCam")
if cam is None:
    cam = bpy.data.objects.new("PreviewCam", bpy.data.cameras.new("PreviewCam"))
    scn.collection.objects.link(cam)
cam.data.type = "ORTHO"
cam.data.ortho_scale = 21.0
cam.location = (0.65, -30.0, 2.9)
cam.rotation_euler = (math.radians(90.0), 0.0, 0.0)
scn.camera = cam

for f in FRAMES:
    scn.frame_set(f)
    scn.render.filepath = os.path.join(OUT, "blender_%03d.png" % f)
    bpy.ops.render.render(write_still=True)
print("rendered", FRAMES)
