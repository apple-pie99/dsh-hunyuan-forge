# -*- coding: utf-8 -*-
"""scene_forge —— 把「我搭的框架」变成「混元能吃的图」，再把混元的产物放回框架。

核心思路
--------
混元只会**图生模型**，所以流程图不是「文字 → 模型」，而是：

    清单(scene.json) → 占位体(框架) → 每个占位体渲一张标准参考图
                     → 混元出白模 → 归一化/清理 → 按占位体的位置和朝向摆回去

占位体既是我控制的结构，也是混元的**输入图**。框架的轮廓由我给，
混元只负责把那个轮廓「长肉」——这样既不会粗糙，也不会跑偏。

用法
----
Blender 里（GUI 或脚本）：

    import sys; sys.path.insert(0, r"<repo>/forge")
    import forge
    forge.run(r"<repo>/examples/night_market.json",
              out=r"<repo>/out/night_market")

命令行（无头，推荐批处理）：

    blender -b -P forge.py -- scene.json --out <out> --stage all

阶段
----
frame  建占位体（BO_<id>）+ 地面/相机/灯光
shot   每个占位体渲一张 3/4 参考图（默认 1024²，灰底，无地面）
gen    调 8081 桥接出 GLB（src=proxy/ref/t2i 三条补给线）
place  导入 → 清碎屑 → 减面 → 归一化 → 落地 → 对齐占位体 → 删占位体
all    frame → shot → gen → place → 出图

产物
----
<out>/shots/<id>.png     混元的输入图（也是判据：图不像，模型就不像）
<out>/glb/<id>.glb       混元原始产物
<out>/scene.blend        摆好的场景（stage=all 时保存）
<out>/hero.png           验收预览
<out>/report.md|.json    每件资产的尺寸/面数/耗时/偏差
"""
from __future__ import annotations

import base64
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
import warnings

import bpy
import bmesh
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import scene_spec  # noqa: E402

warnings.filterwarnings("ignore", category=DeprecationWarning)

# ---------------------------------------------------------------- 可调常量
BRIDGE = os.environ.get("HY3D_BRIDGE", "http://127.0.0.1:8081")
CAM_AZ = 25.0        # 参考图方位角（度）：0 = 正前方(-Y)，正值向右偏
CAM_EL = 18.0        # 参考图俯角（度）
SHOT_RES = 1024
BG_GRAY = 0.32
COL_FRAME = "FRAME"
COL_ASSETS = "ASSETS"
COL_RIG = "RIG"

STATS = {"shot": 0, "gen": 0, "gen_seconds": 0.0, "place": 0}


def log(msg):
    print("[forge] %s" % msg, flush=True)


# ---------------------------------------------------------------- 场景基础
def ensure_collection(name, parent=None):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(col)
    return col


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _engine():
    for name in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            bpy.context.scene.render.engine = name
            return name
        except (TypeError, ValueError):
            continue
    bpy.context.scene.render.engine = "CYCLES"
    return "CYCLES"


def setup_render(res=SHOT_RES):
    sc = bpy.context.scene
    eng = _engine()
    sc.render.resolution_x = res
    sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    try:
        sc.view_settings.view_transform = "Standard"
    except Exception:
        pass
    if eng.startswith("BLENDER_EEVEE"):
        try:
            sc.eevee.taa_render_samples = 32
        except Exception:
            pass
    # 灰底世界
    world = bpy.data.worlds.get("FORGE_WORLD") or bpy.data.worlds.new("FORGE_WORLD")
    world.use_nodes = True
    bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg is not None:
        bg.inputs[0].default_value = (BG_GRAY, BG_GRAY, BG_GRAY + 0.02, 1.0)
        bg.inputs[1].default_value = 1.0
    sc.world = world
    return eng


def _sun(name, col, direction, energy, angle_deg=12.0):
    data = bpy.data.lights.new(name, "SUN")
    data.energy = energy
    data.angle = math.radians(angle_deg)
    obj = bpy.data.objects.new(name, data)
    col.objects.link(obj)
    d = Vector(direction).normalized()
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return obj


def setup_lights():
    """三向太阳光：与尺寸无关，一套灯通吃大小物件。"""
    col = ensure_collection(COL_RIG)
    for o in list(col.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    az = math.radians(CAM_AZ + 35.0)
    key_dir = Vector((math.sin(az), -math.cos(az), -0.85))
    fill_dir = Vector((-0.9, -0.5, -0.55))
    rim_dir = Vector((-0.2, 1.0, -0.6))
    _sun("FORGE_key", col, key_dir, 1.0, 18)
    _sun("FORGE_fill", col, fill_dir, 0.3, 40)
    _sun("FORGE_rim", col, rim_dir, 0.6, 10)


def setup_camera():
    col = ensure_collection(COL_RIG)
    cam_data = bpy.data.cameras.get("FORGE_CAM") or bpy.data.cameras.new("FORGE_CAM")
    cam = bpy.data.objects.get("FORGE_CAM")
    if cam is None:
        cam = bpy.data.objects.new("FORGE_CAM", cam_data)
        col.objects.link(cam)
    cam_data.type = "ORTHO"
    bpy.context.scene.camera = cam
    return cam


def world_bbox(obj):
    """世界坐标外接盒 -> (min Vector, max Vector)。"""
    mw = obj.matrix_world
    corners = [mw @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    return lo, hi


def _view_direction(az=CAM_AZ, el=CAM_EL):
    a, e = math.radians(az), math.radians(el)
    return Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))


def aim_camera(cam, center, radius, az=CAM_AZ, el=CAM_EL, fill_points=None):
    d = _view_direction(az, el)
    cam.location = Vector(center) + d * (radius * 3.0 + 1.0)
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()
    scale = radius * 2.3
    if fill_points:
        inv = cam.matrix_world.inverted()
        xs, ys = [], []
        for p in fill_points:
            q = inv @ Vector(p)
            xs.append(q.x)
            ys.append(q.y)
        if xs:
            scale = max(max(xs) - min(xs), max(ys) - min(ys)) * 1.28
    cam.data.ortho_scale = max(scale, 0.01)
    bpy.context.view_layer.update()


# ---------------------------------------------------------------- frame
def build_proxy(asset, col):
    name = "BO_" + asset["id"]
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)

    dx, dy, dz = asset["size"]
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    parts = asset.get("parts") or []
    if parts:
        # 复合占位体：按局部坐标堆基本体（z 从 0 起），合成一个网格
        for part in parts:
            px, py, pz = [float(v) for v in part.get("at", [0, 0, 0])]
            sx, sy, sz = [float(v) for v in part.get("size", [1, 1, 1])]
            shape = str(part.get("shape") or "box").lower()
            mat = Matrix.Translation(Vector((px, py, pz + sz / 2.0))) @ Matrix.Diagonal(
                Vector((sx, sy, sz, 1.0)))
            if shape in ("cyl", "sphere"):
                bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=32,
                                      radius1=0.5, radius2=0.5, depth=1.0, matrix=mat)
            else:
                bmesh.ops.create_cube(bm, size=1.0, matrix=mat)
    elif asset.get("shape") == "cyl":
        r = dx / 2.0
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=32,
                              radius1=r, radius2=r, depth=dz)
        for v in bm.verts:
            v.co.z += dz / 2.0
    else:
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= dx
            v.co.y *= dy
            v.co.z *= dz
        # 原点挪到「底面中心」
        for v in bm.verts:
            v.co.z += dz / 2.0
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    col.objects.link(obj)
    obj.location = Vector(asset["at"])
    obj.rotation_euler = (0.0, 0.0, math.radians(asset["rot"]))
    # 中性陶土材质：亮一点会过曝，暗一点看不出体积
    mat = bpy.data.materials.get("FORGE_clay")
    if mat is None:
        mat = bpy.data.materials.new("FORGE_clay")
        mat.use_nodes = True
        bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is not None:
            bsdf.inputs[0].default_value = (0.42, 0.43, 0.45, 1.0)   # Base Color
            for key in ("Roughness", "粗糙度"):
                if key in bsdf.inputs:
                    bsdf.inputs[key].default_value = 0.55
                    break
    obj.data.materials.append(mat)
    obj["forge_id"] = asset["id"]
    obj["forge_size"] = asset["size"]
    obj["forge_method"] = asset["method"]
    obj.display_type = "WIRE" if asset["method"] == "build" else "SOLID"
    return obj


def stage_frame(spec, reset=False):
    if reset:
        clear_scene()
    eng = setup_render()
    setup_lights()
    setup_camera()
    col = ensure_collection(COL_FRAME)
    if bpy.data.objects.get("FORGE_ground") is None:
        mesh = bpy.data.meshes.new("FORGE_ground")
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=12.0)
        bm.to_mesh(mesh)
        bm.free()
        g = bpy.data.objects.new("FORGE_ground", mesh)
        col.objects.link(g)
        g.hide_render = True          # 参考图不要地面；它只在视口里当地平线
        g.display_type = "WIRE"
    proxies = []
    for a in spec["assets"]:
        proxies.append(build_proxy(a, col))
    # 新建对象后 matrix_world 还没求值（bound_box 会读成原点），必须刷一次
    bpy.context.view_layer.update()
    log("frame: %d 个占位体 · engine=%s" % (len(proxies), eng))
    return proxies


# ---------------------------------------------------------------- shot
def _isolate(target):
    saved = []
    for o in bpy.data.objects:
        if o is target or o.type in ("LIGHT", "CAMERA"):
            continue
        if o.hide_render:
            continue
        o.hide_render = True
        saved.append(o)
    return saved


def shot_proxy(proxy, path, res=SHOT_RES):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.context.view_layer.update()
    cam = bpy.context.scene.camera or setup_camera()
    lo, hi = world_bbox(proxy)
    center = (lo + hi) / 2.0
    radius = max((hi - lo).length / 2.0, 0.05)
    corners = [proxy.matrix_world @ Vector(c) for c in proxy.bound_box]
    aim_camera(cam, center, radius, fill_points=corners)

    saved = _isolate(proxy)
    sc = bpy.context.scene
    sc.render.resolution_x = res
    sc.render.resolution_y = res
    sc.render.filepath = path
    try:
        try:
            bpy.ops.render.render(write_still=True)
        except Exception:
            # 无头没有 GPU 上下文时 EEVEE 会起不来 → 退回 Workbench（纯 clay，不依赖灯光）
            if not sc.render.engine.startswith("BLENDER_EEVEE"):
                raise
            log("EEVEE 渲染失败，退回 Workbench")
            sc.render.engine = "BLENDER_WORKBENCH"
            sc.display.shading.light = "STUDIO"
            sc.display.shading.color_type = "SINGLE"
            sc.display.shading.single_color = (0.62, 0.62, 0.64)
            sc.display.shading.show_shadows = True
            bpy.ops.render.render(write_still=True)
    finally:
        for o in saved:
            o.hide_render = False
    STATS["shot"] += 1
    return path


def stage_shot(spec, out, res=SHOT_RES, only=None):
    shots = {}
    for a in spec["assets"]:
        if a["method"] != "hy3d":
            continue
        if only and a["id"] not in only:
            continue
        proxy = bpy.data.objects.get("BO_" + a["id"])
        if proxy is None:
            log("跳过 %s：没有占位体" % a["id"])
            continue
        p = os.path.join(out, "shots", a["id"] + ".png")
        shot_proxy(proxy, p, res=res)
        shots[a["id"]] = p
        log("shot: %s -> %s" % (a["id"], os.path.basename(p)))
    return shots


# ---------------------------------------------------------------- gen
def _post_json(url, payload, timeout):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), dict(resp.headers)


def bridge_health(timeout=5):
    try:
        with urllib.request.urlopen(BRIDGE + "/health", timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def gen_from_image(png_path, octree=128, steps=5, seed=1234, guidance=5.0, timeout=900):
    with open(png_path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    payload = {
        "image": b64,
        "octree_resolution": int(octree),
        "num_inference_steps": int(steps),
        "guidance_scale": float(guidance),
        "seed": int(seed),
        "texture": False,
    }
    blob, headers = _post_json(BRIDGE + "/generate", payload, timeout)
    if not blob.startswith(b"glTF"):
        raise RuntimeError("桥接返回的不是 GLB（前 4 字节 %r）" % blob[:4])
    return blob, float(headers.get("X-Gen-Seconds") or 0.0)


def fetch_t2i(prompt, path, width=1024, height=1024, timeout=120):
    """免 key 的文生图补给线（Pollinations）。失败就报错，不静默降级。"""
    from urllib.parse import quote
    url = ("https://image.pollinations.ai/prompt/%s?width=%d&height=%d&nologo=true&model=flux"
           % (quote(prompt), width, height))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with urllib.request.urlopen(url, timeout=timeout) as r:
        blob = r.read()
    if len(blob) < 1000:
        raise RuntimeError("文生图返回过小（%d 字节）" % len(blob))
    with open(path, "wb") as fh:
        fh.write(blob)
    return path


def stage_gen(spec, out, only=None):
    os.makedirs(os.path.join(out, "glb"), exist_ok=True)
    health = bridge_health()
    if not health.get("ok"):
        log("桥接不可用：%s（先起 8080 推理 + 8081 桥接）" % health.get("error", health))
        return {}
    log("桥接就绪：上游 %s" % health.get("upstream"))

    made = {}
    for a in spec["assets"]:
        if a["method"] != "hy3d":
            continue
        if only and a["id"] not in only:
            continue
        dst = os.path.join(out, "glb", a["id"] + ".glb")
        try:
            if a["src"] == "ref":
                if not a["ref"] or not os.path.isfile(a["ref"]):
                    raise RuntimeError("ref 图不存在：%s" % a["ref"])
                src_img = a["ref"]
            elif a["src"] == "t2i":
                src_img = os.path.join(out, "shots", a["id"] + "_t2i.png")
                prompt = a.get("prompt") or ("%s, %s, white background, product shot, centered"
                                             % (a["category"], a["note"] or a["id"]))
                fetch_t2i(prompt, src_img)
            else:
                src_img = os.path.join(out, "shots", a["id"] + ".png")
                if not os.path.isfile(src_img):
                    raise RuntimeError("没有参考图，先跑 shot 阶段")
            t0 = time.time()
            blob, secs = gen_from_image(src_img, a["octree"], a["steps"], a["seed"])
            with open(dst, "wb") as fh:
                fh.write(blob)
            STATS["gen"] += 1
            STATS["gen_seconds"] += secs or (time.time() - t0)
            made[a["id"]] = dst
            log("gen: %s -> %.2f MB（%.1fs）" % (a["id"], len(blob) / 1e6, secs))
        except Exception as exc:
            log("gen 失败 %s：%s" % (a["id"], exc))
    return made


# ---------------------------------------------------------------- place
def _new_objects(before):
    return [o for o in bpy.data.objects if o.name not in before]


def _deselect_all():
    try:
        bpy.ops.object.select_all(action="DESELECT")
    except Exception:
        pass
    for o in bpy.data.objects:
        try:
            o.select_set(False)
        except Exception:
            pass


def _join_meshes(objs):
    _deselect_all()
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    return bpy.context.view_layer.objects.active


def _clean_mesh(obj, min_faces=100):
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bm.faces.ensure_lookup_table()
    seen = set()
    islands = []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, island = [f], []
        seen.add(f.index)
        while stack:
            cur = stack.pop()
            island.append(cur)
            for e in cur.edges:
                for nf in e.link_faces:
                    if nf.index not in seen:
                        seen.add(nf.index)
                        stack.append(nf)
        islands.append(island)
    small = [f for isl in islands if len(isl) < min_faces for f in isl]
    if small and len(islands) > 1:
        bmesh.ops.delete(bm, geom=small, context="FACES")
    bm.to_mesh(me)
    bm.free()
    return len(islands), len(small)


def _decimate(obj, target_faces):
    n = len(obj.data.polygons)
    if n <= target_faces or target_faces <= 0:
        return n
    mod = obj.modifiers.new("forge_dec", "DECIMATE")
    mod.ratio = max(0.01, float(target_faces) / float(n))
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return len(obj.data.polygons)


def _apply_all(obj):
    _deselect_all()
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def import_glb(path):
    before = set(bpy.data.objects.keys())
    bpy.ops.import_scene.gltf(filepath=path)
    fresh = _new_objects(before)
    meshes = [o for o in fresh if o.type == "MESH"]
    for o in fresh:
        if o.type != "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
    if not meshes:
        raise RuntimeError("GLB 里没有网格：%s" % path)
    # 断开父级（glTF 会套一层 world 空物体）但保住世界变换
    mats = {o.name: o.matrix_world.copy() for o in meshes}
    for o in meshes:
        o.parent = None
        o.matrix_world = mats[o.name]
    return _join_meshes(meshes)


def normalize_to(obj, target_size, ground=True):
    _apply_all(obj)
    lo, hi = world_bbox(obj)
    dims = hi - lo
    span = max(dims.x, dims.y, dims.z)
    if span <= 1e-6:
        raise RuntimeError("网格尺寸为 0")
    s = max(target_size) / span
    obj.scale = (s, s, s)
    _apply_all(obj)
    lo, hi = world_bbox(obj)
    center = (lo + hi) / 2.0
    dz = -lo.z if ground else -center.z
    for v in obj.data.vertices:
        v.co.x -= center.x
        v.co.y -= center.y
        v.co.z += dz
    obj.location = (0, 0, 0)
    return hi - lo


def place_on_slot(obj, asset):
    rot = math.radians(asset["rot"] - CAM_AZ)
    obj.matrix_world = Matrix.Translation(Vector(asset["at"])) @ Matrix.Rotation(rot, 4, "Z")


def stage_place(spec, out, only=None):
    col = ensure_collection(COL_ASSETS)
    rows = []
    for a in spec["assets"]:
        if a["method"] == "build":
            proxy = bpy.data.objects.get("BO_" + a["id"])
            if proxy is not None:
                proxy.display_type = "TEXTURED"
                proxy["forge_status"] = "kept-as-frame"
                rows.append({"id": a["id"], "method": "build", "status": "kept",
                             "size": a["size"], "faces": len(proxy.data.polygons)})
            continue
        if a["method"] != "hy3d":
            continue
        if only and a["id"] not in only:
            continue
        glb = os.path.join(out, "glb", a["id"] + ".glb")
        if not os.path.isfile(glb):
            log("place 跳过 %s：没有 GLB" % a["id"])
            continue
        t0 = time.time()
        try:
            obj = import_glb(glb)
            obj.name = "AS_" + a["id"]
            islands, dropped = _clean_mesh(obj)
            faces_before = len(obj.data.polygons)
            faces = _decimate(obj, a["faces"])
            dims = normalize_to(obj, a["size"], ground=True)
            place_on_slot(obj, a)
            for c in list(obj.users_collection):
                c.objects.unlink(obj)
            col.objects.link(obj)
            obj["forge_id"] = a["id"]
            obj["forge_src"] = a["src"]
            proxy = bpy.data.objects.get("BO_" + a["id"])
            if proxy is not None:
                bpy.data.objects.remove(proxy, do_unlink=True)
            STATS["place"] += 1
            rows.append({
                "id": a["id"], "method": "hy3d", "status": "ok",
                "size": [round(v, 3) for v in dims],
                "spec_size": a["size"],
                "faces": faces, "faces_before": faces_before,
                "islands": islands, "dropped_faces": dropped,
                "seconds": round(time.time() - t0, 2), "src": a["src"],
            })
            log("place: %s %s 面 尺寸 %.2f×%.2f×%.2f（%.1fs）"
                % (a["id"], faces, dims.x, dims.y, dims.z, time.time() - t0))
        except Exception as exc:
            log("place 失败 %s：%s" % (a["id"], exc))
            rows.append({"id": a["id"], "method": "hy3d", "status": "error", "error": str(exc)})
    return rows


def render_hero(path, res=1280):
    cam = bpy.context.scene.camera or setup_camera()
    pts = []
    for o in bpy.data.objects:
        if o.type == "MESH" and not o.hide_render and o.name != "FORGE_ground":
            lo, hi = world_bbox(o)
            pts.extend([lo, hi])
    if not pts:
        raise RuntimeError("场景里没有可见网格")
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    center = (lo + hi) / 2.0
    radius = max((hi - lo).length / 2.0, 0.5)
    aim_camera(cam, center, radius, az=CAM_AZ + 10, el=16,
               fill_points=[lo, hi, Vector((lo.x, hi.y, hi.z)), Vector((hi.x, lo.y, lo.z))])
    sc = bpy.context.scene
    sc.render.resolution_x = res
    sc.render.resolution_y = int(res * 0.62)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


# ---------------------------------------------------------------- 编排
def _report(out, spec, rows, started):
    md = ["# %s · 场景锻造报告" % spec["name"], ""]
    md.append("生成时间 %.1fs · shot %d · gen %d（%.1fs） · place %d"
              % (time.time() - started, STATS["shot"], STATS["gen"],
                 STATS["gen_seconds"], STATS["place"]))
    md.append("")
    md.append("| 资产 | 方法 | 来源 | 目标尺寸 | 实际尺寸 | 面数 | 状态 |")
    md.append("|---|---|---|---|---|---|---|")
    for r in rows:
        size = "×".join("%.2f" % v for v in r.get("size", [])) if r.get("size") else "-"
        spec_size = "×".join("%.2f" % v for v in r.get("spec_size", [])) if r.get("spec_size") else "-"
        md.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            r["id"], r.get("method", "-"), r.get("src", "-"),
            spec_size, size, r.get("faces", "-"), r.get("status", "-")))
    md.append("")
    md.append("> 图不像，模型就不像。先看 `shots/` 里的参考图，再决定要不要调 octree / 换来源。")
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md))
    with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as fh:
        json.dump({"spec": spec, "rows": rows, "stats": STATS}, fh, ensure_ascii=False, indent=2)


def run(spec_path, out=None, stage="all", only=None, reset=False, hero=True, save=True):
    started = time.time()
    spec = scene_spec.resolve(scene_spec.load(spec_path))
    out = out or os.path.join(HERE, "out", spec["name"])
    only = set(x.strip() for x in only.split(",")) if isinstance(only, str) and only else only
    os.makedirs(out, exist_ok=True)
    log(scene_spec.summary(spec))

    stages = ["frame", "shot", "gen", "place"] if stage == "all" else [stage]
    # 单独跑后续阶段时，如果场景里还没有占位体，先把 frame 补上（CLI 每次都是新进程）
    if stage in ("shot", "gen", "place"):
        first = "BO_" + spec["assets"][0]["id"]
        if bpy.data.objects.get(first) is None:
            log("没有占位体，先补 frame")
            stage_frame(spec, reset=reset)
    for st in stages:
        if st == "frame":
            stage_frame(spec, reset=reset)
        elif st == "shot":
            stage_shot(spec, out, only=only)
        elif st == "gen":
            stage_gen(spec, out, only=only)
        elif st == "place":
            rows = stage_place(spec, out, only=only)
            _report(out, spec, rows, started)
            if hero:
                try:
                    render_hero(os.path.join(out, "hero.png"))
                    log("hero -> %s" % os.path.join(out, "hero.png"))
                except Exception as exc:
                    log("hero 渲染失败：%s" % exc)
        else:
            raise SystemExit("未知阶段：%s" % stage)

    if save and not bpy.data.filepath:
        blend = os.path.join(out, "scene.blend")
        bpy.ops.wm.save_as_mainfile(filepath=blend)
        log("保存 %s" % blend)

    result = {"ok": True, "out": out, "spec": spec_path, "stats": STATS,
              "seconds": round(time.time() - started, 1)}
    print("FORGE_RESULT " + json.dumps(result, ensure_ascii=False), flush=True)
    return result


def _cli():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    import argparse
    p = argparse.ArgumentParser(prog="forge.py")
    p.add_argument("spec")
    p.add_argument("--out", default=None)
    p.add_argument("--stage", default="all",
                   choices=["frame", "shot", "gen", "place", "all"])
    p.add_argument("--only", default=None, help="逗号分隔的资产 id")
    p.add_argument("--reset", action="store_true", help="先清空场景")
    p.add_argument("--no-hero", action="store_true")
    p.add_argument("--no-save", action="store_true")
    ns = p.parse_args(argv)
    return run(ns.spec, out=ns.out, stage=ns.stage, only=ns.only,
               reset=ns.reset, hero=not ns.no_hero, save=not ns.no_save)


if __name__ == "__main__":
    _cli()
