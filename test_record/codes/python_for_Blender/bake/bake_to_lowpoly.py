import bpy
import os
import time
import numpy as np

RES            = 1024
MARGIN         = 8
EXTRUSION_REL  = 0.01
MAX_RAY_REL    = 0.03
SAMPLES_NORMAL = 16
SAMPLES_AO     = 32
SAMPLES_EMIT   = 8
MAPS           = ["normal", "ao", "basecolor", "roughness", "metallic"]
UNITY_METALLIC_SMOOTHNESS = True

ctx = bpy.context
scene = ctx.scene

LOW_SUFFIX, HIGH_SUFFIX = "_low", "_high"
meshes = [o for o in scene.objects if o.type == "MESH"]
lows  = [o for o in meshes if o.name.lower().endswith(LOW_SUFFIX)]
highs = [o for o in meshes if o.name.lower().endswith(HIGH_SUFFIX)]
if lows or highs:
    if len(lows) != 1 or not highs:
        raise RuntimeError(f"By-name mode needs exactly ONE '*{LOW_SUFFIX}' object and at least one "
                           f"'*{HIGH_SUFFIX}' object. Found low: {[o.name for o in lows]}, "
                           f"high: {[o.name for o in highs]}")
    lp, hps = lows[0], highs
    if ctx.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in ctx.view_layer.objects:
        o.select_set(False)
    for o in hps + [lp]:
        o.hide_set(False)
        o.select_set(True)
else:
    sel = [o for o in ctx.selected_objects if o.type == "MESH"]
    if len(sel) < 2:
        raise RuntimeError("Name objects *_low / *_high, or select the high polys AND the low poly.")
    lp = min(sel, key=lambda o: len(o.data.polygons))
    hps = [o for o in sel if o is not lp]
if not lp.data.uv_layers:
    raise RuntimeError("The low poly has no UV map.")
if ctx.mode != "OBJECT":
    bpy.ops.object.mode_set(mode="OBJECT")
ctx.view_layer.objects.active = lp

size = max(lp.dimensions)
out_dir = os.path.join(os.path.expanduser("~"), "Documents", "bake_" + bpy.path.clean_name(lp.name))
os.makedirs(out_dir, exist_ok=True)

scene.render.engine = "CYCLES"
b = scene.render.bake
b.use_selected_to_active = True
b.use_cage = False
b.cage_extrusion = EXTRUSION_REL * size
b.max_ray_distance = MAX_RAY_REL * size
b.margin = MARGIN
b.use_clear = True
b.target = "IMAGE_TEXTURES"
b.normal_space = "TANGENT"
b.normal_r, b.normal_g, b.normal_b = "POS_X", "POS_Y", "POS_Z"

bake_mat = bpy.data.materials.get("LP_BakeTarget") or bpy.data.materials.new("LP_BakeTarget")
bake_mat.use_nodes = True
bnodes = bake_mat.node_tree.nodes
bnodes.clear()
bout = bnodes.new("ShaderNodeOutputMaterial")
bbsdf = bnodes.new("ShaderNodeBsdfPrincipled")
bake_mat.node_tree.links.new(bbsdf.outputs[0], bout.inputs["Surface"])
target = bnodes.new("ShaderNodeTexImage")
bnodes.active = target
target.select = True
lp.data.materials.clear()
lp.data.materials.append(bake_mat)

hp_mats = []
for o in hps:
    for s in o.material_slots:
        if s.material and s.material.use_nodes and s.material not in hp_mats:
            hp_mats.append(s.material)

def swap_to_emission(mat, input_name):
    nt = mat.node_tree
    outs = [n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"]
    out = next((n for n in outs if n.is_active_output), outs[0] if outs else None)
    if out is None:
        return None
    orig = out.inputs["Surface"].links[0].from_socket if out.inputs["Surface"].is_linked else None
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.0
    if bsdf:
        inp = bsdf.inputs[input_name]
        if inp.is_linked:
            nt.links.new(inp.links[0].from_socket, em.inputs["Color"])
        else:
            v = inp.default_value
            em.inputs["Color"].default_value = tuple(v) if hasattr(v, "__len__") else (v, v, v, 1.0)
    else:
        em.inputs["Color"].default_value = (0, 0, 0, 1)
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return (nt, out, orig, em)

def restore(state):
    if state is None:
        return
    nt, out, orig, em = state
    nt.nodes.remove(em)
    if orig is not None:
        nt.links.new(orig, out.inputs["Surface"])

def new_image(name, non_color, alpha=False):
    old = bpy.data.images.get(name)
    if old:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, RES, RES, alpha=alpha, float_buffer=False)
    img.colorspace_settings.name = "Non-Color" if non_color else "sRGB"
    return img

def save(img, fname):
    path = os.path.join(out_dir, fname)
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    return path

EMIT_INPUT = {"basecolor": "Base Color", "roughness": "Roughness", "metallic": "Metallic"}
baked = {}
base = bpy.path.clean_name(lp.name)

for kind in MAPS:
    img = new_image(f"{base}_{kind}", non_color=(kind != "basecolor"))
    target.image = img
    bnodes.active = target
    t0 = time.time()
    if kind == "normal":
        scene.cycles.samples = SAMPLES_NORMAL
        bpy.ops.object.bake(type="NORMAL")
    elif kind == "ao":
        scene.cycles.samples = SAMPLES_AO
        bpy.ops.object.bake(type="AO")
    else:
        scene.cycles.samples = SAMPLES_EMIT
        states = [swap_to_emission(m, EMIT_INPUT[kind]) for m in hp_mats]
        try:
            bpy.ops.object.bake(type="EMIT")
        finally:
            for st in states:
                restore(st)
    save(img, f"{base}_{kind}.png")
    baked[kind] = img

if UNITY_METALLIC_SMOOTHNESS and "metallic" in baked and "roughness" in baked:
    n = RES * RES * 4
    met = np.empty(n, np.float32); baked["metallic"].pixels.foreach_get(met)
    rgh = np.empty(n, np.float32); baked["roughness"].pixels.foreach_get(rgh)
    ms = np.zeros((RES * RES, 4), np.float32)
    ms[:, 0] = met.reshape(-1, 4)[:, 0]
    ms[:, 1] = ms[:, 0]
    ms[:, 2] = ms[:, 0]
    ms[:, 3] = 1.0 - rgh.reshape(-1, 4)[:, 0]
    msimg = new_image(f"{base}_MetallicSmoothness", non_color=True, alpha=True)
    msimg.pixels.foreach_set(ms.ravel())
    msimg.alpha_mode = "STRAIGHT"
    save(msimg, f"{base}_MetallicSmoothness.png")

pm = bpy.data.materials.get("LP_Baked")
if pm:
    bpy.data.materials.remove(pm)
pm = bpy.data.materials.new("LP_Baked")
pm.use_nodes = True
pn, pl = pm.node_tree.nodes, pm.node_tree.links
pn.clear()
po = pn.new("ShaderNodeOutputMaterial"); po.location = (600, 0)
pb = pn.new("ShaderNodeBsdfPrincipled"); pb.location = (300, 0)
pl.new(pb.outputs[0], po.inputs["Surface"])

def img_node(kind, y):
    n = pn.new("ShaderNodeTexImage"); n.location = (-300, y); n.image = baked[kind]
    return n

if "basecolor" in baked:
    pl.new(img_node("basecolor", 300).outputs["Color"], pb.inputs["Base Color"])
if "roughness" in baked:
    pl.new(img_node("roughness", 0).outputs["Color"], pb.inputs["Roughness"])
if "metallic" in baked:
    pl.new(img_node("metallic", -300).outputs["Color"], pb.inputs["Metallic"])
if "normal" in baked:
    nm = pn.new("ShaderNodeNormalMap"); nm.location = (0, -600)
    pl.new(img_node("normal", -600).outputs["Color"], nm.inputs["Color"])
    pl.new(nm.outputs["Normal"], pb.inputs["Normal"])

lp.data.materials.clear()
lp.data.materials.append(pm)
bpy.data.materials.remove(bake_mat)
