import bpy
import bmesh
import math
from mathutils import Vector

HIGH_SUFFIX     = "_high"
FRONT_ANGLE     = 0.0
BACKDROP_COLOR  = (0.16, 0.15, 0.14)
BACKDROP_ROUGH  = 0.6
WORLD_STRENGTH  = 0.05
KEY_POWER       = 1.0
FILL_POWER      = 1.0
RIM_POWER       = 1.0
TOP_POWER       = 1.0
SAMPLES         = 256

ctx = bpy.context
scene = ctx.scene
highs = [o for o in scene.objects if o.type == "MESH" and o.name.lower().endswith(HIGH_SUFFIX)]
if not highs:
    raise RuntimeError(f"No objects ending with '{HIGH_SUFFIX}' found.")

for o in scene.objects:
    if o.name.lower().endswith("_low"):
        o.hide_render = True
old_hy = bpy.data.collections.get("HY_Studio")
if old_hy:
    for o in old_hy.all_objects:
        o.hide_render = True
for o in highs:
    o.hide_render = False

old = bpy.data.collections.get("PR_Studio")
if old:
    for o in list(old.all_objects):
        data = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if data is not None and data.users == 0:
            for coll in (bpy.data.lights, bpy.data.cameras, bpy.data.meshes):
                if data.name in coll and coll[data.name] == data:
                    coll.remove(data)
                    break
    bpy.data.collections.remove(old)
coll = bpy.data.collections.new("PR_Studio")
scene.collection.children.link(coll)

pts = [o.matrix_world @ Vector(c) for o in highs for c in o.bound_box]
mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center = (mn + mx) / 2
H = mx.z - mn.z

rot = math.radians(FRONT_ANGLE)

def around(az_deg, el_deg, dist, target=center):
    a, e = math.radians(az_deg) + rot, math.radians(el_deg)
    d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    return target + d * dist

def aim(obj, target):
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()

r = scene.render
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
r.film_transparent = False
r.image_settings.file_format = "PNG"
r.image_settings.color_mode = "RGB"
vs = scene.view_settings
try:
    vs.view_transform = "AgX"
    vs.look = "AgX - Medium High Contrast"
except TypeError:
    try:
        vs.view_transform = "Filmic"
        vs.look = "Medium High Contrast"
    except TypeError:
        pass
vs.exposure = 0.0

world = bpy.data.worlds.get("PR_World") or bpy.data.worlds.new("PR_World")
world.use_nodes = True
nt = world.node_tree
bg = next((n for n in nt.nodes if n.type == "BACKGROUND"), None) or nt.nodes.new("ShaderNodeBackground")
out = next((n for n in nt.nodes if n.type == "OUTPUT_WORLD"), None) or nt.nodes.new("ShaderNodeOutputWorld")
for l in list(out.inputs["Surface"].links):
    nt.links.remove(l)
nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
bg.inputs[0].default_value = (0.5, 0.5, 0.5, 1.0)
bg.inputs[1].default_value = WORLD_STRENGTH
scene.world = world

floor_z = mn.z - 0.001 * H
front, back, radius, wall, width = 3.0 * H, 1.6 * H, 1.0 * H, 3.0 * H, 8.0 * H
profile = [(-front, 0.0)]
steps = 16
for i in range(steps + 1):
    t = i / steps * math.pi / 2
    profile.append((back - radius + math.sin(t) * radius, radius - math.cos(t) * radius))
profile.append((back, wall))
bm = bmesh.new()
cols = 8
grid = []
for (py, pz) in profile:
    row = []
    for j in range(cols + 1):
        x = -width / 2 + width * j / cols
        row.append(bm.verts.new((x, py, pz)))
    grid.append(row)
for i in range(len(grid) - 1):
    for j in range(cols):
        bm.faces.new((grid[i][j], grid[i][j + 1], grid[i + 1][j + 1], grid[i + 1][j]))
for f in bm.faces:
    f.smooth = True
bm.normal_update()
me = bpy.data.meshes.new("PR_Backdrop")
bm.to_mesh(me)
bm.free()
backdrop = bpy.data.objects.new("PR_Backdrop", me)
coll.objects.link(backdrop)
backdrop.location = (center.x, center.y, floor_z)
backdrop.rotation_euler = (0, 0, rot)

if me.polygons and me.polygons[0].normal.z < 0:
    me.flip_normals()
bmat = bpy.data.materials.get("PR_BackdropMat") or bpy.data.materials.new("PR_BackdropMat")
bmat.use_nodes = True
bsdf = next(n for n in bmat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
bsdf.inputs["Base Color"].default_value = (*BACKDROP_COLOR, 1.0)
bsdf.inputs["Roughness"].default_value = BACKDROP_ROUGH
me.materials.append(bmat)

def area_light(name, az, el, dist, size, power_e, color, size_y=None, target=center):
    ld = bpy.data.lights.new(name, "AREA")
    if size_y:
        ld.shape = "RECTANGLE"
        ld.size, ld.size_y = size, size_y
    else:
        ld.shape = "DISK"
        ld.size = size
    ld.energy = power_e * math.pi * dist * dist
    ld.color = color
    lo = bpy.data.objects.new(name, ld)
    coll.objects.link(lo)
    lo.location = around(az, el, dist, target)
    aim(lo, target)
    return lo

area_light("PR_Key",  -45, 35, 1.6 * H, 0.9 * H, 3.0 * KEY_POWER,  (1.00, 0.93, 0.84))
area_light("PR_Fill",  60, 10, 1.9 * H, 1.2 * H, 0.8 * FILL_POWER, (0.88, 0.93, 1.00))
area_light("PR_Rim",  150, 25, 1.4 * H, 0.15 * H, 4.0 * RIM_POWER, (1.00, 0.97, 0.92), size_y=1.2 * H)
area_light("PR_Top",    0, 85, 1.3 * H, 0.8 * H, 1.0 * TOP_POWER,  (1.00, 0.98, 0.95))

cd = bpy.data.cameras.new("PR_Cam")
cd.lens = 85
cd.sensor_fit = "VERTICAL"
cd.sensor_height = 24
cd.clip_start = 0.001 * H
cd.clip_end = 50 * H
cam = bpy.data.objects.new("PR_Cam", cd)
coll.objects.link(cam)
fov_v = 2 * math.atan(cd.sensor_height / 2 / cd.lens)
dist = (H * 1.12 / 2) / math.tan(fov_v / 2)
cam.location = around(-30, 12, dist)
aim(cam, center)
scene.camera = cam
r.resolution_x, r.resolution_y, r.resolution_percentage = 1600, 2000, 100

cam["pr_center"] = list(center)
cam["pr_min"] = list(mn)
cam["pr_max"] = list(mx)
cam["pr_front_angle"] = FRONT_ANGLE

