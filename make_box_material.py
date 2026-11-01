# Bought PBR (box projection, no UV) x Hunyuan base map -> one material on the selected object
# Use: set TEX_DIR and HY_BASEMAP, select the high poly, Alt+P
# Tuning:
#   Texture size:     REPEATS (higher = smaller grain)
#   Bone colour:      COLOR_VALUE (brightness), COLOR_SAT (yellower / more aged)
#   Hunyuan amount:   HY_MIX (0 = off, 1 = full)
#   Surface relief:   BUMP_STRENGTH, NORMAL_STRENGTH
#   Shininess:        ROUGH_OUT (e.g. (0.4, 0.9) = less shiny)
#   Worn edges:       EDGE_WEAR (0 = off), EDGE_RANGE (lower first number = more edge)
#   Dirty crevices:   CAVITY_DIRT (0 = off)
import bpy
import bmesh
import os

TEX_DIR = r"C:\path\to\bone_textures"
HY_BASEMAP = r"C:\Users\boxca\Documents\ND\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable\ComfyUI\output\HY3D_TexMV_1504791403933679616\e38e705a-38d9-41a0-9513-f1334146be3d_texture.png"
MAT_NAME = "Bone_Box"

REPEATS = 5.0
BOX_BLEND = 0.2
APPLY_SCALE = True
HY_MIX = 1.0
COLOR_VALUE = 1.0
COLOR_SAT = 1.0
USE_AO = True
ROUGH_OUT = (0.0, 1.0)
BUMP_STRENGTH = 1.0
BUMP_DISTANCE = 0.002
HEIGHT_RANGE = (0.44, 0.50)
USE_NORMAL_MAP = True
NORMAL_STRENGTH = 1.0
TANGENT_UV = "Tangent"
EDGE_WEAR = 0.6
EDGE_COLOR = (0.93, 0.89, 0.80)
EDGE_RANGE = (0.52, 0.58)
EDGE_ROUGH = 0.35
CAVITY_DIRT = 0.5
CAVITY_DIST = 0.01

KEYS = {
    "normal": ("normal", "nrm", "_nor", "norm"),
    "height": ("height", "displacement", "disp", "bump"),
    "ao": ("ambientocclusion", "ambient_occlusion", "_ao", "-ao", " ao", "occlusion"),
    "metal": ("metallic", "metalness", "metal"),
    "gloss": ("gloss",),
    "rough": ("roughness", "rough"),
    "basecolor": ("basecolor", "base_color", "albedo", "diffuse", "diff", "color", "colour", "_col"),
}

files = [f for f in os.listdir(TEX_DIR)
         if f.lower().endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr"))]
maps = {}
for f in sorted(files):
    low = "_" + f.lower()
    for kind, words in KEYS.items():
        if kind not in maps and any(w in low for w in words):
            maps[kind] = os.path.join(TEX_DIR, f)
            break
if "basecolor" not in maps:
    raise RuntimeError("No base colour map in TEX_DIR.")

objs = [o for o in bpy.context.selected_objects if o.type == "MESH"]
if not objs:
    raise RuntimeError("Select the high poly first.")

if APPLY_SCALE:
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in objs:
        if any(abs(v - 1.0) > 1e-6 for v in o.scale):
            if o.data.users > 1:
                o.data = o.data.copy()
            bpy.ops.object.select_all(action="DESELECT")
            o.select_set(True)
            bpy.context.view_layer.objects.active = o
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for o in objs:
        o.select_set(True)

old = bpy.data.materials.get(MAT_NAME)
if old:
    bpy.data.materials.remove(old)
mat = bpy.data.materials.new(MAT_NAME)
mat.use_nodes = True
nt = mat.node_tree
nodes, links = nt.nodes, nt.links
nodes.clear()

out = nodes.new("ShaderNodeOutputMaterial")
out.location = (900, 0)
bsdf = nodes.new("ShaderNodeBsdfPrincipled")
bsdf.location = (550, 0)
links.new(bsdf.outputs[0], out.inputs["Surface"])
bsdf.inputs["Metallic"].default_value = 0.0

tc = nodes.new("ShaderNodeTexCoord")
tc.location = (-1100, 0)
mp = nodes.new("ShaderNodeMapping")
mp.location = (-900, 0)
local_size = max(max(c[i] for c in objs[0].bound_box) - min(c[i] for c in objs[0].bound_box)
                 for i in range(3))
scale = REPEATS / local_size
mp.inputs["Scale"].default_value = (scale, scale, scale)
links.new(tc.outputs["Object"], mp.inputs["Vector"])

y = 400


def tex(kind, non_color):
    global y
    n = nodes.new("ShaderNodeTexImage")
    n.location = (-600, y)
    y -= 300
    n.label = kind
    n.image = bpy.data.images.load(maps[kind], check_existing=True)
    if n.image.source != "FILE":
        n.image.source = "FILE"
        n.image.reload()
    n.image.colorspace_settings.name = "Non-Color" if non_color else "sRGB"
    n.projection = "BOX"
    n.projection_blend = BOX_BLEND
    links.new(mp.outputs["Vector"], n.inputs["Vector"])
    return n


col_img = tex("basecolor", False)
hsv = nodes.new("ShaderNodeHueSaturation")
hsv.location = (-350, 600)
hsv.inputs["Saturation"].default_value = COLOR_SAT
hsv.inputs["Value"].default_value = COLOR_VALUE
links.new(col_img.outputs["Color"], hsv.inputs["Color"])
col_out = hsv.outputs["Color"]

if USE_AO and "ao" in maps:
    ao = tex("ao", True)
    mix = nodes.new("ShaderNodeMix")
    mix.location = (-250, 400)
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    links.new(col_out, mix.inputs[6])
    links.new(ao.outputs["Color"], mix.inputs[7])
    links.new(mix.outputs[2], bsdf.inputs["Base Color"])
else:
    links.new(col_out, bsdf.inputs["Base Color"])

if HY_BASEMAP:
    if not objs[0].data.uv_layers:
        raise RuntimeError("HY_BASEMAP is set but the object has no UV map.")
    uv = nodes.new("ShaderNodeUVMap")
    uv.location = (-900, 800)
    uv.uv_map = objs[0].data.uv_layers[0].name
    hy = nodes.new("ShaderNodeTexImage")
    hy.location = (-600, 800)
    hy.label = "hunyuan basemap"
    hy.image = bpy.data.images.load(HY_BASEMAP, check_existing=True)
    hy.image.colorspace_settings.name = "sRGB"
    links.new(uv.outputs["UV"], hy.inputs["Vector"])
    cur = bsdf.inputs["Base Color"].links[0].from_socket
    mixhy = nodes.new("ShaderNodeMix")
    mixhy.location = (250, 500)
    mixhy.data_type = "RGBA"
    mixhy.blend_type = "MULTIPLY"
    mixhy.inputs["Factor"].default_value = HY_MIX
    links.new(cur, mixhy.inputs[6])
    links.new(hy.outputs["Color"], mixhy.inputs[7])
    links.new(mixhy.outputs[2], bsdf.inputs["Base Color"])

if "rough" in maps:
    r = tex("rough", True)
    rr = nodes.new("ShaderNodeMapRange")
    rr.location = (-250, 0)
    rr.inputs["To Min"].default_value = ROUGH_OUT[0]
    rr.inputs["To Max"].default_value = ROUGH_OUT[1]
    links.new(r.outputs["Color"], rr.inputs["Value"])
    links.new(rr.outputs["Result"], bsdf.inputs["Roughness"])
elif "gloss" in maps:
    g = tex("gloss", True)
    inv = nodes.new("ShaderNodeInvert")
    inv.location = (-250, y + 300)
    links.new(g.outputs["Color"], inv.inputs["Color"])
    links.new(inv.outputs["Color"], bsdf.inputs["Roughness"])


def make_tangent_uv(me):
    hy_uv = me.uv_layers[0].name if me.uv_layers else None
    me.uv_layers.new(name=TANGENT_UV, do_init=False)
    bm = bmesh.new()
    bm.from_mesh(me)
    lay = bm.loops.layers.uv[TANGENT_UV]
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        a, b = [(1, 2), (0, 2), (0, 1)][ax]
        for l in f.loops:
            co = l.vert.co
            l[lay].uv = (co[a], co[b])
    bm.to_mesh(me)
    bm.free()
    if hy_uv:
        me.uv_layers.active = me.uv_layers[hy_uv]
        me.uv_layers[hy_uv].active_render = True


nmap = None
if USE_NORMAL_MAP and "normal" in maps:
    for o in objs:
        if TANGENT_UV not in [u.name for u in o.data.uv_layers]:
            make_tangent_uv(o.data)
    if TANGENT_UV in [u.name for u in objs[0].data.uv_layers]:
        nt_img = tex("normal", True)
        nmap = nodes.new("ShaderNodeNormalMap")
        nmap.location = (0, -800)
        nmap.space = "TANGENT"
        nmap.uv_map = TANGENT_UV
        nmap.inputs["Strength"].default_value = NORMAL_STRENGTH
        links.new(nt_img.outputs["Color"], nmap.inputs["Color"])
        links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])

if "height" in maps:
    h = tex("height", True)
    rng = nodes.new("ShaderNodeMapRange")
    rng.location = (0, -400)
    rng.inputs["From Min"].default_value = HEIGHT_RANGE[0]
    rng.inputs["From Max"].default_value = HEIGHT_RANGE[1]
    bump = nodes.new("ShaderNodeBump")
    bump.location = (250, -400)
    bump.inputs["Strength"].default_value = BUMP_STRENGTH
    bump.inputs["Distance"].default_value = BUMP_DISTANCE
    links.new(h.outputs["Color"], rng.inputs["Value"])
    links.new(rng.outputs["Result"], bump.inputs["Height"])
    if nmap:
        links.new(nmap.outputs["Normal"], bump.inputs["Normal"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

if EDGE_WEAR > 0 or CAVITY_DIRT > 0:
    base_src = bsdf.inputs["Base Color"].links[0].from_socket
    if CAVITY_DIRT > 0:
        aon = nodes.new("ShaderNodeAmbientOcclusion")
        aon.location = (300, 900)
        aon.inputs["Distance"].default_value = CAVITY_DIST * local_size
        aon.samples = 16
        cav = nodes.new("ShaderNodeMix")
        cav.location = (500, 800)
        cav.data_type = "RGBA"
        cav.blend_type = "MULTIPLY"
        cav.inputs["Factor"].default_value = CAVITY_DIRT
        links.new(base_src, cav.inputs[6])
        links.new(aon.outputs["AO"], cav.inputs[7])
        base_src = cav.outputs[2]
    if EDGE_WEAR > 0:
        geo = nodes.new("ShaderNodeNewGeometry")
        geo.location = (100, 1150)
        er = nodes.new("ShaderNodeMapRange")
        er.location = (300, 1150)
        er.label = "edge mask"
        er.inputs["From Min"].default_value = EDGE_RANGE[0]
        er.inputs["From Max"].default_value = EDGE_RANGE[1]
        links.new(geo.outputs["Pointiness"], er.inputs["Value"])
        ew = nodes.new("ShaderNodeMath")
        ew.location = (500, 1150)
        ew.operation = "MULTIPLY"
        ew.inputs[1].default_value = EDGE_WEAR
        links.new(er.outputs["Result"], ew.inputs[0])
        edge = nodes.new("ShaderNodeMix")
        edge.location = (700, 900)
        edge.label = "edge wear colour"
        edge.data_type = "RGBA"
        edge.blend_type = "MIX"
        edge.inputs[7].default_value = (*EDGE_COLOR, 1.0)
        links.new(ew.outputs[0], edge.inputs["Factor"])
        links.new(base_src, edge.inputs[6])
        base_src = edge.outputs[2]
        r_src = bsdf.inputs["Roughness"].links[0].from_socket if bsdf.inputs["Roughness"].is_linked else None
        er2 = nodes.new("ShaderNodeMix")
        er2.location = (700, 200)
        er2.label = "edge wear roughness"
        er2.data_type = "FLOAT"
        er2.inputs[3].default_value = EDGE_ROUGH
        if r_src:
            links.new(r_src, er2.inputs[2])
        else:
            er2.inputs[2].default_value = bsdf.inputs["Roughness"].default_value
        links.new(ew.outputs[0], er2.inputs[0])
        links.new(er2.outputs[0], bsdf.inputs["Roughness"])
    links.new(base_src, bsdf.inputs["Base Color"])

for o in objs:
    o.data.materials.clear()
    o.data.materials.append(mat)
