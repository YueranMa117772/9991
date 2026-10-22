import bpy
import math
import os
import time
from mathutils import Vector

RES_X, RES_Y = 1600, 2000
SAMPLES      = 256
OUT_ROOT     = os.path.join(os.path.expanduser("~"), "Documents", "product_renders")

SHOTS = [
    ("01_hero",        -35, 12, 0.50, 1.12, 85,  None),
    ("02_front",         0,  4, 0.50, 1.10, 85,  None),
    ("03_side",         90,  6, 0.50, 1.10, 85,  None),
    ("04_spine_close", -25, 10, 0.68, 0.32, 100, 2.8),
    ("05_base_detail",  30, -4, 0.14, 0.34, 85,  4.0),
]

scene = bpy.context.scene
cam = bpy.data.objects.get("PR_Cam")
if cam is None or "pr_center" not in cam:
    raise RuntimeError("Run pr_1_setup_lighting.py first.")
mn, mx = Vector(cam["pr_min"]), Vector(cam["pr_max"])
center = Vector(cam["pr_center"])
H = mx.z - mn.z
rot = math.radians(cam["pr_front_angle"])

for o in scene.objects:
    if o.name.lower().endswith("_low"):
        o.hide_render = True

r = scene.render
r.engine = "CYCLES"
scene.cycles.samples = SAMPLES
r.resolution_x, r.resolution_y, r.resolution_percentage = RES_X, RES_Y, 100
r.image_settings.file_format = "PNG"
r.image_settings.color_mode = "RGB"
scene.camera = cam
cd = cam.data
cd.sensor_fit = "VERTICAL"
cd.sensor_height = 24

out_dir = os.path.join(OUT_ROOT, time.strftime("run_%Y%m%d_%H%M%S"))
os.makedirs(out_dir, exist_ok=True)

backdrop = bpy.data.objects.get("PR_Backdrop")
saved = (cam.location.copy(), cam.rotation_euler.copy(), cd.lens, cd.dof.use_dof)
saved_bd = backdrop.rotation_euler.z if backdrop else None

for name, az, el, th, frame_h, lens, fstop in SHOTS:
    target = Vector((center.x, center.y, mn.z + th * H))
    cd.lens = lens
    fov_v = 2 * math.atan(cd.sensor_height / 2 / lens)
    dist = (frame_h * H / 2) / math.tan(fov_v / 2)
    a, e = math.radians(az) + rot, math.radians(el)
    if backdrop:
        backdrop.rotation_euler.z = a
    d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    cam.location = target + d * dist
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    cd.clip_start = 0.001 * H
    cd.clip_end = dist + 20 * H
    if fstop:
        cd.dof.use_dof = True
        cd.dof.focus_distance = dist
        cd.dof.aperture_fstop = fstop
    else:
        cd.dof.use_dof = False
    r.filepath = os.path.join(out_dir, name + ".png")
    t0 = time.time()
    bpy.ops.render.render(write_still=True)

cam.location, cam.rotation_euler, cd.lens, cd.dof.use_dof = saved[0], saved[1], saved[2], saved[3]
if backdrop:
    backdrop.rotation_euler.z = saved_bd
