# Tuning (all in the settings below):
#   Stronger structure: lower WORLD_STRENGTH / FILL_RATIO, smaller LIGHT_SIZE
#   Softer, flatter:    raise WORLD_STRENGTH / FILL_RATIO, bigger LIGHT_SIZE
#   Overall brightness: KEY_POWER
#   Wrong front angle:  FRONT_OFFSET (90 / 180 / -90)
import bpy
import math
from mathutils import Vector

RES_X, RES_Y = 1024, 1536
FRONT_OFFSET = 0.0
PADDING = 1.08
SAMPLES = 128
WORLD_COLOR = (0.80, 0.80, 0.80)
WORLD_STRENGTH = 0.2
KEY_POWER = 1.2
FILL_RATIO = 0.25
LIGHT_SIZE = 1.0
EXPOSURE = 0.0

ctx = bpy.context
scene = ctx.scene
objs = [o for o in ctx.selected_objects if o.type == "MESH" and not o.name.startswith("HY_")]
if not objs:
    raise RuntimeError("Select the model first.")

for name in ("HY_Key", "HY_Fill", "HY_ViewCam"):
    o = bpy.data.objects.get(name)
    if o:
        data = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if data and data.users == 0:
            if isinstance(data, bpy.types.Camera):
                bpy.data.cameras.remove(data)
            else:
                bpy.data.lights.remove(data)
old_coll = bpy.data.collections.get("HY_Studio")
if old_coll:
    bpy.data.collections.remove(old_coll)
coll = bpy.data.collections.new("HY_Studio")
scene.collection.children.link(coll)

pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center = (mn + mx) / 2
size = mx - mn
height = max(size)
horiz = math.hypot(size.x, size.y)
dist = height * 3 + 1

r, cm = scene.render, scene.view_settings
r.engine = "CYCLES"
scene.cycles.samples = SAMPLES
scene.cycles.use_denoising = True
try:
    prefs = ctx.preferences.addons["cycles"].preferences
    for dev_type in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = dev_type
            prefs.get_devices()
            if any(d.type == dev_type for d in prefs.devices):
                for d in prefs.devices:
                    d.use = True
                scene.cycles.device = "GPU"
                break
        except TypeError:
            continue
except Exception:
    scene.cycles.device = "CPU"
r.resolution_x, r.resolution_y, r.resolution_percentage = RES_X, RES_Y, 100
r.film_transparent = True
r.image_settings.file_format = "PNG"
r.image_settings.color_mode = "RGBA"
cm.view_transform = "Standard"
cm.look = "None"
cm.exposure = EXPOSURE
cm.gamma = 1.0

old_world = bpy.data.worlds.get("HY_StudioWorld")
if old_world:
    old_world.name = "HY_StudioWorld_old"
world = bpy.data.worlds.new("HY_StudioWorld")
world.use_nodes = True
nt = world.node_tree
nt.nodes.clear()
bg = nt.nodes.new("ShaderNodeBackground")
out = nt.nodes.new("ShaderNodeOutputWorld")
nt.links.new(bg.outputs[0], out.inputs[0])
bg.inputs[0].default_value = (*WORLD_COLOR, 1.0)
bg.inputs[1].default_value = WORLD_STRENGTH
scene.world = world
if old_world and old_world.users == 0:
    bpy.data.worlds.remove(old_world)

cam_data = bpy.data.cameras.new("HY_ViewCam")
cam_data.type = "ORTHO"
cam_data.clip_start = 0.01
cam_data.clip_end = dist * 4
cam_data.ortho_scale = max(size.z, horiz / (RES_X / RES_Y)) * PADDING
cam = bpy.data.objects.new("HY_ViewCam", cam_data)
coll.objects.link(cam)
t = math.radians(FRONT_OFFSET)
cam.location = center + Vector((dist * math.sin(t), -dist * math.cos(t), 0))
cam.rotation_euler = (math.pi / 2, 0, t)
scene.camera = cam

cam["hy_center"] = list(center)
cam["hy_dist"] = dist
cam["hy_front_offset"] = FRONT_OFFSET
cam["hy_objects"] = ",".join(o.name for o in objs)

ctx.view_layer.update()
target_local = Vector((0, 0, -dist))
k = height * 1.5
light_size = height * LIGHT_SIZE
base_power = 4.5 * k * k


def make_light(name, offset_dir, power):
    ld = bpy.data.lights.new(name, "AREA")
    ld.shape = "SQUARE"
    ld.size = light_size
    ld.energy = power
    lo = bpy.data.objects.new(name, ld)
    coll.objects.link(lo)
    lo.parent = cam
    pos = target_local + offset_dir.normalized() * k
    lo.location = pos
    lo.rotation_euler = (target_local - pos).to_track_quat("-Z", "Y").to_euler()


make_light("HY_Key", Vector((-0.7, 0.7, 0.8)), base_power * KEY_POWER)
make_light("HY_Fill", Vector((0.9, 0.1, 0.8)), base_power * KEY_POWER * FILL_RATIO)
