# -*- coding: utf-8 -*-
"""ramen_stall 摊体结构：程序化搭（不经过混元）。

参考图：日式街头拉面摊 / 屋台。尺寸按真实尺度：宽 3.5m、深 2.3m、总高 2.7m。
道具（锅、灯笼、纸箱、周转筐、炭炉）由 props.json 交给混元，这里只搭结构。

用法（Blender 里）：
    exec(open(r"<repo>/examples/ramen/build_stall.py", encoding="utf-8").read())
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))      # repo 根目录
FORGE = os.path.join(_ROOT, "forge")
if FORGE not in sys.path:
    sys.path.insert(0, FORGE)

OUT = _HERE
COL_NAME = "STALL"

# ---------------------------------------------------------------- 尺寸表
HALF_W = 1.72        # 立柱到中心
Y_FRONT = -1.15      # 前柱
Y_BACK = 1.15        # 后柱
H_POST = 2.46        # 柱高
CTR_H = 0.96         # 台面上表面高度
ROOF_Z = 2.46        # 檐口


# ---------------------------------------------------------------- 材质
def _set(node, names, value):
    for n in names:
        if n in node.inputs:
            node.inputs[n].default_value = value
            return True
    return False


def mat(name, rgb, rough=0.7, metal=0.0, emit=None, strength=0.0, alpha=1.0):
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is not None:
        _set(bsdf, ("Base Color", "基础色"), (*rgb, 1.0))
        _set(bsdf, ("Roughness", "粗糙度"), rough)
        _set(bsdf, ("Metallic", "金属度"), metal)
        if emit:
            _set(bsdf, ("Emission Color", "发光颜色", "Emission"), (*emit, 1.0))
            _set(bsdf, ("Emission Strength", "发光强度"), strength)
        if alpha < 1.0:
            _set(bsdf, ("Alpha", "透明度"), alpha)
            for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
                try:
                    setattr(m, attr, val)
                except Exception:
                    pass
    m.diffuse_color = (*rgb, 1.0)
    return m


def materials():
    d = {
        "wood": mat("ST_wood", (0.140, 0.072, 0.036), 0.80),
        "wood_light": mat("ST_wood_light", (0.190, 0.104, 0.050), 0.74),
        "wood_dark": mat("ST_wood_dark", (0.048, 0.024, 0.012), 0.86),
        "canopy": mat("ST_canopy", (0.030, 0.032, 0.040), 0.92),
        "metal": mat("ST_metal", (0.52, 0.53, 0.55), 0.32, 0.9),
        "cloth_red": mat("ST_cloth_red", (0.30, 0.035, 0.035), 0.88),
        "cloth_navy": mat("ST_cloth_navy", (0.075, 0.085, 0.135), 0.9),
        "paper": mat("ST_paper", (0.86, 0.66, 0.40), 0.65, emit=(1.0, 0.62, 0.26), strength=1.4),
        "glass": mat("ST_glass", (0.30, 0.31, 0.28), 0.18, alpha=0.35),
        "floor": mat("ST_floor", (0.170, 0.166, 0.162), 0.92),
        "dark": mat("ST_dark", (0.02, 0.02, 0.02), 1.0),
        "bottle": mat("ST_bottle", (0.115, 0.062, 0.028), 0.30),
        "warm": mat("ST_warm", (0.9, 0.7, 0.45), 0.5, emit=(1.0, 0.66, 0.34), strength=2.6),
        "ceramic": mat("ST_ceramic", (0.82, 0.81, 0.78), 0.35),
        "lantern": mat("ST_lantern", (0.95, 0.72, 0.42), 0.6, emit=(1.0, 0.55, 0.20), strength=1.1),
    }
    # 程序化材质（木纹/布纹/水泥/纸）在的话就覆盖上面的纯色版本
    try:
        import rich_mats
        d.update(rich_mats.make_all())
    except Exception as exc:
        print("[stall] rich_mats 不可用，退回纯色材质：%s" % exc)
    return d


M = {}


def col():
    c = bpy.data.collections.get(COL_NAME)
    if c is None:
        c = bpy.data.collections.new(COL_NAME)
        bpy.context.scene.collection.children.link(c)
    return c


def _finish(name, me, at, m, rot=(0.0, 0.0, 0.0), bevel=0.004):
    obj = bpy.data.objects.new(name, me)
    col().objects.link(obj)
    if m is not None:
        obj.data.materials.append(m)
    obj.location = at
    obj.rotation_euler = rot
    if bevel:
        bv = obj.modifiers.new("bevel", "BEVEL")
        bv.width = bevel
        bv.segments = 2
        bv.limit_method = "ANGLE"
    return obj


def box(name, size, at, m, rot=(0.0, 0.0, 0.0), bevel=0.004):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= size[0]
        v.co.y *= size[1]
        v.co.z *= size[2]
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return _finish(name, me, at, m, rot, bevel)


def cyl(name, r, h, at, m, segments=24, rot=(0.0, 0.0, 0.0), bevel=0.0):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                          radius1=r, radius2=r, depth=h)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return _finish(name, me, at, m, rot, bevel)


def frustum(name, bottom, top, z0, z1, at, m):
    """四棱台：雨棚用。bottom/top = (宽, 深)。"""
    bw, bd = bottom
    tw, td = top
    verts = [(-bw / 2, -bd / 2, z0), (bw / 2, -bd / 2, z0), (bw / 2, bd / 2, z0), (-bw / 2, bd / 2, z0),
             (-tw / 2, -td / 2, z1), (tw / 2, -td / 2, z1), (tw / 2, td / 2, z1), (-tw / 2, td / 2, z1)]
    faces = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    return _finish(name, me, at, m, bevel=0.0)


# ---------------------------------------------------------------- 结构
def build_posts():
    for sx in (-1, 1):
        for sy, y in ((-1, Y_FRONT), (1, Y_BACK)):
            box("post_%d%d" % (sx, sy), (0.10, 0.10, H_POST + 0.06),
                (sx * HALF_W, y, (H_POST + 0.06) / 2), M["wood_dark"], bevel=0.006)
    # 柱脚铁件
    for sx in (-1, 1):
        for y in (Y_FRONT, Y_BACK):
            box("post_shoe_%d_%d" % (sx, int(y * 10)), (0.14, 0.14, 0.08),
                (sx * HALF_W, y, 0.04), M["metal"], bevel=0.004)


def build_roof():
    # 雨棚：四棱台，前低后高一点点 -> 用两层叠
    frustum("roof_canopy", (4.30, 3.10), (2.55, 1.75), ROOF_Z, ROOF_Z + 0.34,
            (0, 0, 0), M["canopy"])
    # 顶脊小段
    box("roof_ridge", (1.85, 0.26, 0.13), (0, 0.10, ROOF_Z + 0.40), M["canopy"], bevel=0.01)
    # 檐口木梁（前后左右）
    box("fascia_front", (4.30, 0.07, 0.20), (0, -1.50, ROOF_Z - 0.02), M["wood_dark"], bevel=0.006)
    box("fascia_back", (4.30, 0.07, 0.16), (0, 1.50, ROOF_Z - 0.02), M["wood_dark"], bevel=0.006)
    box("fascia_l", (0.07, 3.00, 0.16), (-2.12, 0, ROOF_Z - 0.02), M["wood_dark"], bevel=0.006)
    box("fascia_r", (0.07, 3.00, 0.16), (2.12, 0, ROOF_Z - 0.02), M["wood_dark"], bevel=0.006)
    # 顶梁
    for y in (Y_FRONT, Y_BACK):
        box("beam_top_%d" % int(y * 10), (3.54, 0.09, 0.13), (0, y, ROOF_Z - 0.10),
            M["wood"], bevel=0.005)
    for x in (-HALF_W, HALF_W):
        box("beam_side_%d" % int(x * 10), (0.09, 2.30, 0.13), (x, 0, ROOF_Z - 0.10),
            M["wood"], bevel=0.005)
    # 棚下暖光灯带（细长条，压在檐口内侧）
    box("strip_light", (3.2, 0.05, 0.03), (0, -1.02, ROOF_Z - 0.20), M["warm"], bevel=0.0)


def build_banners():
    """檐口下挂的布幌子：前 5 片 + 右侧 2 片。"""
    xs = [-1.32, -0.66, 0.0, 0.66, 1.32]
    for i, x in enumerate(xs):
        h = 0.38 + (0.03 if i % 2 else 0.0)
        box("banner_%d" % i, (0.50, 0.012, h), (x, -1.44, ROOF_Z - 0.10 - h / 2),
            M["cloth_navy"], rot=(0, math.radians(1.5 * ((-1) ** i)), 0), bevel=0.0)
        box("banner_bar_%d" % i, (0.54, 0.03, 0.03), (x, -1.44, ROOF_Z - 0.07),
            M["wood_dark"], bevel=0.003)
    # 右侧红幔
    for i, y in enumerate((-0.30, 0.30)):
        box("noren_%d" % i, (0.012, 0.54, 1.02), (1.70, y, 1.70), M["cloth_red"], bevel=0.0)
    box("noren_rod", (0.04, 1.32, 0.04), (1.70, 0, 2.24), M["wood_dark"], bevel=0.003)


def build_counter():
    # 台面
    box("counter_top", (3.52, 0.80, 0.07), (0, -0.68, CTR_H - 0.035), M.get("wood_top") or M["wood_light"], bevel=0.008)
    # 前柜体
    box("counter_body", (3.36, 0.66, CTR_H - 0.07), (0, -0.70, (CTR_H - 0.07) / 2),
        M["wood"], bevel=0.006)
    # 前脸竖板（一条条，做出木条感）
    n = 11
    span = 3.20
    w = span / n
    for i in range(n):
        x = -span / 2 + w * (i + 0.5)
        box("plank_%02d" % i, (w - 0.024, 0.028, CTR_H - 0.20),
            (x, -1.035, (CTR_H - 0.20) / 2 + 0.06), M["wood_dark"], bevel=0.003)
    # 台面下沿横档
    box("rail_front", (3.42, 0.05, 0.10), (0, -1.03, CTR_H - 0.12), M["wood_dark"], bevel=0.004)
    # 右侧转角柜
    box("counter_side", (0.62, 1.24, CTR_H - 0.07), (1.46, 0.02, (CTR_H - 0.07) / 2),
        M["wood"], bevel=0.006)
    # 台面右侧补块
    box("counter_top_side", (0.66, 1.20, 0.07), (1.46, 0.02, CTR_H - 0.035),
        M.get("wood_top") or M["wood_light"], bevel=0.008)


def build_back():
    # 背板 + 三层货架（贴住台面后方，摊内进深约 1 米）
    box("back_panel", (3.30, 0.06, 1.46), (0, 0.86, 1.58), M["wood_dark"], bevel=0.004)
    for i, z in enumerate((1.14, 1.52, 1.90)):
        box("shelf_%d" % i, (3.10, 0.28, 0.045), (0, 0.68, z), M["wood_light"], bevel=0.004)
        box("shelf_edge_%d" % i, (3.10, 0.03, 0.05), (0, 0.55, z + 0.03), M["wood_dark"], bevel=0.003)
    # 后柜体
    box("back_cab", (3.30, 0.56, 0.90), (0, 0.58, 0.45), M["wood"], bevel=0.006)

    # 右侧玻璃展示柜
    gx, gy, gz = 1.02, 0.22, CTR_H
    box("case_base", (0.72, 0.46, 0.08), (gx, gy, gz + 0.04), M["wood_dark"], bevel=0.004)
    box("case_glass", (0.68, 0.42, 0.50), (gx, gy, gz + 0.33), M["glass"], bevel=0.0)
    for dx in (-0.34, 0.34):
        for dy in (-0.21, 0.21):
            box("case_post_%d_%d" % (int(dx * 10), int(dy * 10)), (0.025, 0.025, 0.52),
                (gx + dx, gy + dy, gz + 0.33), M["metal"], bevel=0.002)
    box("case_top", (0.72, 0.46, 0.04), (gx, gy, gz + 0.60), M["metal"], bevel=0.004)
    # 柜内两层小架（给玻璃后面一点内容）
    for i, z in enumerate((gz + 0.22, gz + 0.42)):
        box("case_shelf_%d" % i, (0.62, 0.36, 0.012), (gx, gy, z), M["wood_light"], bevel=0.0)


def build_bottles():
    xs = [-1.28, -1.10, -0.86, 0.10, 0.32, 1.24, 1.40]
    for i, x in enumerate(xs):
        z = 1.16 if i % 3 else 1.54
        cyl("bottle_%d" % i, 0.035, 0.20, (x, 0.67, z + 0.10), M["bottle"], segments=16)
        cyl("bottle_neck_%d" % i, 0.014, 0.06, (x, 0.67, z + 0.23), M["bottle"], segments=12)


def build_stools():
    spots = [(-1.58, -1.62, 18), (-1.06, -1.74, -9), (-0.60, -1.55, 32)]
    for i, (x, y, rz) in enumerate(spots):
        base = (x, y, 0)
        cyl("stool_seat_%d" % i, 0.165, 0.035, (x, y, 0.44), M["wood_light"], segments=24)
        cyl("stool_rim_%d" % i, 0.150, 0.05, (x, y, 0.405), M["metal"], segments=24)
        for k in range(4):
            a = math.radians(45 + 90 * k + rz)
            lx, ly = math.cos(a) * 0.115, math.sin(a) * 0.115
            cyl("stool_leg_%d_%d" % (i, k), 0.011, 0.42,
                (x + lx, y + ly, 0.21), M["metal"], segments=10,
                rot=(math.radians(4) * math.sin(a), math.radians(4) * math.cos(a), 0))
        cyl("stool_ring_%d" % i, 0.105, 0.012, (x, y, 0.12), M["metal"], segments=20)


def build_lanterns():
    """灯笼自己做：球身 + 上下木盖 + 吊绳。混元做这种回转体反而糊。"""
    LY = -1.44
    for x in (-1.28, 1.28):
        # 筒身（提灯是「带箍的筒」，不是球）
        cyl("lantern_body_%d" % int(x * 10), 0.115, 0.27, (x, LY, 1.885),
            M["lantern"], segments=32)
        # 只留上下两道箍，中间是纸
        for i, dz in enumerate((-0.100, 0.100)):
            cyl("lantern_rib_%d_%d" % (int(x * 10), i), 0.117, 0.010,
                (x, LY, 1.885 + dz), M["wood_dark"], segments=32)
        cyl("lantern_cap_%d" % int(x * 10), 0.070, 0.032, (x, LY, 2.036),
            M["wood_dark"], segments=16)
        cyl("lantern_cap_b_%d" % int(x * 10), 0.064, 0.028, (x, LY, 1.734),
            M["wood_dark"], segments=16)
        cyl("lantern_cord_%d" % int(x * 10), 0.006, 0.24, (x, LY, 2.18), M["dark"],
            segments=8)


def build_details():
    """台面碗堆这类小件。"""
    # 叠起来的碗
    for i, r in enumerate((0.10, 0.098, 0.096)):
        cyl("bowl_%d" % i, r, 0.032, (-0.86, -0.50, 0.976 + i * 0.028),
            M["ceramic"], segments=20)
    # 筷筒
    cyl("chop_pot", 0.055, 0.16, (0.20, -0.62, 1.04), M["wood_dark"], segments=16)


def build_ceiling_light():
    # 台面上方的暖光筒灯外壳
    for x in (-0.9, 0.35):
        cyl("lamp_can_%d" % int(x * 10), 0.075, 0.10, (x, -0.55, ROOF_Z - 0.34),
            M["wood_dark"], segments=16)
        cyl("lamp_bulb_%d" % int(x * 10), 0.055, 0.02, (x, -0.55, ROOF_Z - 0.40),
            M["paper"], segments=16)


# ---------------------------------------------------------------- 布景
def _aim(obj, target):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def _area(name, loc, target, size, energy, color=(1, 1, 1)):
    data = bpy.data.lights.new(name, "AREA")
    data.shape = "SQUARE"
    data.size = size
    data.energy = energy
    data.color = color
    obj = bpy.data.objects.new(name, data)
    col().objects.link(obj)
    obj.location = loc
    _aim(obj, target)
    return obj


def _point(name, loc, energy, color=(1, 1, 1), radius=0.1):
    data = bpy.data.lights.new(name, "POINT")
    data.energy = energy
    data.color = color
    data.shadow_soft_size = radius
    obj = bpy.data.objects.new(name, data)
    col().objects.link(obj)
    obj.location = loc
    return obj


def studio():
    sc = bpy.context.scene
    w = bpy.data.worlds.get("ST_world") or bpy.data.worlds.new("ST_world")
    w.use_nodes = True
    bg = next((n for n in w.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg is not None:
        bg.inputs[0].default_value = (0.055, 0.065, 0.090, 1.0)
        bg.inputs[1].default_value = 1.0
    sc.world = w

    box("floor", (30, 30, 0.04), (0, 0, -0.02), M["floor"], bevel=0.0)

    _area("key", (4.6, -5.6, 5.2), (0, -0.2, 1.1), 3.2, 430, (0.95, 0.95, 1.0))
    _area("fill", (-5.2, -3.6, 2.6), (0, 0, 1.0), 5.0, 130, (0.70, 0.80, 1.0))
    _area("rim", (-0.6, 5.2, 4.2), (0, 0.4, 1.4), 3.0, 260, (0.80, 0.86, 1.0))

    # 摊内暖光
    _point("warm_l", (-1.28, -1.18, 1.88), 90, (1.0, 0.52, 0.20), 0.14)
    _point("warm_r", (1.28, -1.18, 1.88), 90, (1.0, 0.52, 0.20), 0.14)
    _point("counter_light", (-0.2, -0.55, 2.02), 160, (1.0, 0.70, 0.38), 0.40)
    _point("inner_light", (0.3, 0.55, 2.05), 120, (1.0, 0.74, 0.44), 0.35)

    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = 1600
    sc.render.resolution_y = 900
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    try:
        sc.eevee.taa_render_samples = 64
        sc.eevee.use_raytracing = True
    except Exception:
        pass
    try:
        sc.view_settings.view_transform = "Standard"
        sc.view_settings.look = "None"
        sc.view_settings.exposure = 0.15
    except Exception:
        pass

    cam_data = bpy.data.cameras.new("ST_cam")
    cam_data.lens = 62
    cam = bpy.data.objects.new("ST_cam", cam_data)
    col().objects.link(cam)
    cam.location = (6.35, -8.7, 4.15)
    _aim(cam, (0.05, -0.10, 1.02))
    sc.camera = cam
    return cam


# ---------------------------------------------------------------- 场景
def clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for c in list(bpy.data.collections):
        if c.name != "Collection":
            bpy.data.collections.remove(c)
    # 材质是按名字缓存的，不清掉就会一直用上一轮的颜色
    for m in list(bpy.data.materials):
        if m.name.startswith(("ST_", "P_")):
            bpy.data.materials.remove(m)
    bpy.context.view_layer.update()


def build():
    global M
    M = materials()
    build_posts()
    build_roof()
    build_banners()
    build_counter()
    build_back()
    build_bottles()
    build_stools()
    build_lanterns()
    build_details()
    build_ceiling_light()
    bpy.context.view_layer.update()
    return len(col().objects)


if __name__ == "__main__":
    clear()
    n = build()
    studio()
    print("STALL_BUILT %d objects" % n, flush=True)
