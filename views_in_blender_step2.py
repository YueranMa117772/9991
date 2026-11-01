# Tuning:
#   Background grey: BG_COLOR (1.0 = white, 0.9 = light grey, 0.5 = mid grey)
#   Output folder:   OUTPUT_DIR (each run saves to a new run_ sub-folder)
import bpy
import math
import os
import time
import numpy as np
from mathutils import Vector

OUTPUT_DIR = r"C:\Users\boxca\Documents\hy_views"
BG_COLOR = (1.0, 1.0, 1.0)
HIDE_OTHERS = True

VIEWS = {
    "front": 0,
    "left_front": -45,
    "left": -90,
    "back": 180,
    "right": 90,
    "right_front": 45,
}

scene = bpy.context.scene
cam = bpy.data.objects.get("HY_ViewCam")
if cam is None or "hy_center" not in cam:
    raise RuntimeError("Run hy_1_setup_lighting.py first.")

center = Vector(cam["hy_center"])
dist = float(cam["hy_dist"])
front_offset = float(cam["hy_front_offset"])
model_names = {n for n in str(cam["hy_objects"]).split(",") if n}
keep = model_names | {"HY_ViewCam", "HY_Key", "HY_Fill"}

out_dir = os.path.join(OUTPUT_DIR, time.strftime("run_%Y%m%d_%H%M%S"))
os.makedirs(out_dir, exist_ok=True)

r = scene.render
old_path = r.filepath
old_camera = scene.camera
scene.camera = cam
r.film_transparent = True
r.image_settings.file_format = "PNG"
r.image_settings.color_mode = "RGBA"

hidden = []
if HIDE_OTHERS:
    for o in scene.objects:
        if o.name not in keep and not o.hide_render and o.type in {
                "MESH", "CURVE", "SURFACE", "META", "FONT", "LIGHT"}:
            o.hide_render = True
            hidden.append(o.name)


def flatten_on_bg(path):
    img = bpy.data.images.load(path, check_existing=False)
    px = np.empty(len(img.pixels), dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(-1, 4)
    a = px[:, 3:4]
    px[:, :3] = px[:, :3] * a + np.array(BG_COLOR, dtype=np.float32) * (1 - a)
    px[:, 3] = 1.0
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def place_cam(angle_deg):
    t = math.radians(angle_deg + front_offset)
    cam.location = center + Vector((dist * math.sin(t), -dist * math.cos(t), 0))
    cam.rotation_euler = (math.pi / 2, 0, t)


try:
    for name, ang in VIEWS.items():
        place_cam(ang)
        path = os.path.join(out_dir, f"{name}.png")
        r.filepath = path
        bpy.ops.render.render(write_still=True)
        flatten_on_bg(path)
finally:
    place_cam(0)
    r.filepath = old_path
    scene.camera = old_camera if old_camera else cam
    for n in hidden:
        o = bpy.data.objects.get(n)
        if o:
            o.hide_render = False
