# -*- coding: utf-8 -*-
"""程序化 PBR 材质库：木纹 / 拉丝钢 / 瓦楞纸 / 布纹 / 水泥地 / 纸灯笼。

全部用噪波节点，不依赖任何贴图文件，也不需要 UV —— 用 Object 坐标，
所以随便改模型尺寸都不会拉伸。

和 build_stall.py 的接口一致：make_all() 返回同名材质的 dict。
"""
import bpy


def _in(bsdf, names, idx, value):
    for n in names:
        if n in bsdf.inputs:
            bsdf.inputs[n].default_value = value
            return True
    try:
        bsdf.inputs[idx].default_value = value
        return True
    except Exception:
        return False


def _fresh(name):
    m = bpy.data.materials.get(name)
    if m is not None:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    return m, nt, bsdf


def _coord(nt, scale=(1.0, 1.0, 1.0), loc=(0.0, 0.0, 0.0)):
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = scale
    mp.inputs["Location"].default_value = loc
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    return mp


def _noise(nt, vec, scale=6.0, detail=8.0, rough=0.55, distortion=0.0):
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = rough
    if "Distortion" in n.inputs:
        n.inputs["Distortion"].default_value = distortion
    nt.links.new(vec, n.inputs["Vector"])
    return n


def _wave(nt, vec, scale=8.0, distortion=2.0, detail=2.0):
    w = nt.nodes.new("ShaderNodeTexWave")
    w.wave_type = "BANDS"
    w.bands_direction = "Z"
    w.inputs["Scale"].default_value = scale
    w.inputs["Distortion"].default_value = distortion
    w.inputs["Detail"].default_value = detail
    nt.links.new(vec, w.inputs["Vector"])
    return w


def _ramp(nt, stops):
    r = nt.nodes.new("ShaderNodeValToRGB")
    el = r.color_ramp.elements
    while len(el) > 1:
        el.remove(el[-1])
    el[0].position = stops[0][0]
    el[0].color = (*stops[0][1], 1.0)
    for pos, col in stops[1:]:
        e = el.new(pos)
        e.color = (*col, 1.0)
    return r


def _bump(nt, height_out, bsdf, strength=0.2, distance=0.02):
    b = nt.nodes.new("ShaderNodeBump")
    b.inputs["Strength"].default_value = strength
    b.inputs["Distance"].default_value = distance
    nt.links.new(height_out, b.inputs["Height"])
    nt.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])
    return b


def _base(bsdf, rgb):
    _in(bsdf, ("Base Color", "基础色"), 0, (*rgb, 1.0))


def _rough(bsdf, v):
    _in(bsdf, ("Roughness", "粗糙度"), 2, v)


def _metal(bsdf, v):
    _in(bsdf, ("Metallic", "金属度"), 1, v)


def _emit(bsdf, rgb, strength):
    _in(bsdf, ("Emission Color", "发光颜色", "Emission"), 26, (*rgb, 1.0))
    _in(bsdf, ("Emission Strength", "发光强度"), 27, strength)


# ---------------------------------------------------------------- 各材质
def wood(name, dark, mid, light, grain_scale=1.0, axis="z"):
    """axis: 木纹走向。'z' = 竖板，'x' = 台面横板。"""
    m, nt, b = _fresh(name)
    if axis == "x":
        big = (0.55 * grain_scale, 3.0 * grain_scale, 3.0 * grain_scale)
        fine = (0.5 * grain_scale, 16.0 * grain_scale, 16.0 * grain_scale)
    else:
        big = (3.0 * grain_scale, 3.0 * grain_scale, 0.55 * grain_scale)
        fine = (16.0 * grain_scale, 16.0 * grain_scale, 0.5 * grain_scale)

    # 底色：大块的深浅变化
    mp = _coord(nt, scale=big)
    n1 = _noise(nt, mp.outputs["Vector"], scale=7.0, detail=8, rough=0.6, distortion=0.35)
    r1 = _ramp(nt, [(0.34, dark), (0.55, mid), (0.74, light)])
    nt.links.new(n1.outputs["Fac"], r1.inputs["Fac"])

    # 细木纹：高频、沿纹理方向拉长
    mp2 = _coord(nt, scale=fine)
    n2 = _noise(nt, mp2.outputs["Vector"], scale=11.0, detail=6, rough=0.55, distortion=0.12)
    r2 = _ramp(nt, [(0.38, (0.0, 0.0, 0.0)), (0.66, (1.0, 1.0, 1.0))])
    nt.links.new(n2.outputs["Fac"], r2.inputs["Fac"])

    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 0.22
    nt.links.new(r1.outputs["Color"], mix.inputs[6])
    nt.links.new(r2.outputs["Color"], mix.inputs[7])
    nt.links.new(mix.outputs[2], b.inputs["Base Color"])

    _bump(nt, n2.outputs["Fac"], b, strength=0.12, distance=0.006)
    r3 = _ramp(nt, [(0.32, (0.52, 0.52, 0.52)), (0.78, (0.88, 0.88, 0.88))])
    nt.links.new(n1.outputs["Fac"], r3.inputs["Fac"])
    nt.links.new(r3.outputs["Color"], b.inputs["Roughness"])
    _metal(b, 0.0)
    return m


def brushed_steel(name="P_steel"):
    m, nt, b = _fresh(name)
    _base(b, (0.60, 0.62, 0.64))
    _metal(b, 1.0)
    mp = _coord(nt, scale=(60.0, 60.0, 3.0))
    n = _noise(nt, mp.outputs["Vector"], scale=6.0, detail=6, rough=0.5)
    r = _ramp(nt, [(0.30, (0.16, 0.16, 0.16)), (0.70, (0.34, 0.34, 0.34))])
    nt.links.new(n.outputs["Fac"], r.inputs["Fac"])
    nt.links.new(r.outputs["Color"], b.inputs["Roughness"])
    _bump(nt, n.outputs["Fac"], b, strength=0.06, distance=0.002)
    return m


def cardboard(name="P_card"):
    m, nt, b = _fresh(name)
    _base(b, (0.30, 0.21, 0.12))
    _rough(b, 0.92)
    mp = _coord(nt, scale=(1.0, 1.0, 1.0))
    n = _noise(nt, mp.outputs["Vector"], scale=26.0, detail=8, rough=0.6)
    r = _ramp(nt, [(0.35, (0.24, 0.165, 0.09)), (0.7, (0.35, 0.25, 0.145))])
    nt.links.new(n.outputs["Fac"], r.inputs["Fac"])
    nt.links.new(r.outputs["Color"], b.inputs["Base Color"])
    w = _wave(nt, mp.outputs["Vector"], scale=55.0, distortion=0.0, detail=1.0)
    _bump(nt, w.outputs["Fac"], b, strength=0.35, distance=0.004)
    return m


def plastic(name="P_blue", rgb=(0.045, 0.14, 0.33)):
    m, nt, b = _fresh(name)
    _base(b, rgb)
    _rough(b, 0.55)
    mp = _coord(nt, scale=(1.0, 1.0, 1.0))
    n = _noise(nt, mp.outputs["Vector"], scale=120.0, detail=3, rough=0.4)
    r = _ramp(nt, [(0.4, (0.45, 0.45, 0.45)), (0.7, (0.62, 0.62, 0.62))])
    nt.links.new(n.outputs["Fac"], r.inputs["Fac"])
    nt.links.new(r.outputs["Color"], b.inputs["Roughness"])
    return m


def cloth(name, rgb, weave=90.0, sheen=0.0):
    m, nt, b = _fresh(name)
    mp = _coord(nt, scale=(1.0, 1.0, 1.0))
    n = _noise(nt, mp.outputs["Vector"], scale=weave, detail=2, rough=0.4)
    lo = tuple(max(0.0, c * 0.72) for c in rgb)
    hi = tuple(min(1.0, c * 1.30 + 0.012) for c in rgb)
    r = _ramp(nt, [(0.25, lo), (0.75, hi)])
    nt.links.new(n.outputs["Fac"], r.inputs["Fac"])
    nt.links.new(r.outputs["Color"], b.inputs["Base Color"])
    _rough(b, 0.94)
    _bump(nt, n.outputs["Fac"], b, strength=0.12, distance=0.002)
    if "Sheen Weight" in b.inputs:
        b.inputs["Sheen Weight"].default_value = sheen
    return m


def concrete(name="ST_floor"):
    m, nt, b = _fresh(name)
    _base(b, (0.17, 0.166, 0.16))
    _rough(b, 0.9)
    mp = _coord(nt, scale=(1.0, 1.0, 1.0))
    n = _noise(nt, mp.outputs["Vector"], scale=2.2, detail=9, rough=0.6)
    r = _ramp(nt, [(0.35, (0.13, 0.128, 0.124)), (0.7, (0.21, 0.205, 0.20))])
    nt.links.new(n.outputs["Fac"], r.inputs["Fac"])
    nt.links.new(r.outputs["Color"], b.inputs["Base Color"])
    n2 = _noise(nt, mp.outputs["Vector"], scale=40.0, detail=6, rough=0.5)
    _bump(nt, n2.outputs["Fac"], b, strength=0.18, distance=0.004)
    return m


def paper_lantern(name="ST_lantern"):
    m, nt, b = _fresh(name)
    _base(b, (0.95, 0.72, 0.42))
    _rough(b, 0.7)
    _emit(b, (1.0, 0.55, 0.20), 1.4)
    mp = _coord(nt, scale=(1.0, 1.0, 1.0))
    n = _noise(nt, mp.outputs["Vector"], scale=70.0, detail=4, rough=0.4)
    r = _ramp(nt, [(0.3, (0.0, 0.0, 0.0)), (0.8, (0.09, 0.09, 0.09))])
    nt.links.new(n.outputs["Fac"], r.inputs["Fac"])
    _bump(nt, n.outputs["Fac"], b, strength=0.25, distance=0.002)
    # 纸的透光：低一点的粗糙 + 轻微次表面感
    if "Subsurface Weight" in b.inputs:
        b.inputs["Subsurface Weight"].default_value = 0.10
    return m


def bottle(name="ST_bottle"):
    """深色玻璃酒瓶：低粗糙 + 一点次表面感的暗绿。"""
    m, nt, b = _fresh(name)
    _base(b, (0.045, 0.070, 0.040))
    _rough(b, 0.16)
    _metal(b, 0.0)
    if "IOR" in b.inputs:
        b.inputs["IOR"].default_value = 1.46
    mp = _coord(nt, scale=(1.0, 1.0, 1.0))
    n = _noise(nt, mp.outputs["Vector"], scale=90.0, detail=3, rough=0.4)
    r = _ramp(nt, [(0.35, (0.10, 0.10, 0.10)), (0.75, (0.24, 0.24, 0.24))])
    nt.links.new(n.outputs["Fac"], r.inputs["Fac"])
    nt.links.new(r.outputs["Color"], b.inputs["Roughness"])
    return m


def ceramic(name="ST_ceramic"):
    m, nt, b = _fresh(name)
    _base(b, (0.80, 0.79, 0.76))
    _rough(b, 0.28)
    mp = _coord(nt, scale=(1.0, 1.0, 1.0))
    n = _noise(nt, mp.outputs["Vector"], scale=60.0, detail=4, rough=0.5)
    r = _ramp(nt, [(0.35, (0.20, 0.20, 0.20)), (0.7, (0.34, 0.34, 0.34))])
    nt.links.new(n.outputs["Fac"], r.inputs["Fac"])
    nt.links.new(r.outputs["Color"], b.inputs["Roughness"])
    _bump(nt, n.outputs["Fac"], b, strength=0.08, distance=0.001)
    return m


def make_all():
    return {
        "wood": wood("ST_wood", (0.085, 0.040, 0.018), (0.150, 0.076, 0.036), (0.215, 0.115, 0.058)),
        "wood_light": wood("ST_wood_light", (0.075, 0.038, 0.017), (0.135, 0.070, 0.033), (0.195, 0.108, 0.055)),
        "wood_top": wood("ST_wood_top", (0.075, 0.038, 0.017), (0.140, 0.073, 0.034), (0.200, 0.110, 0.056), axis="x"),
        "wood_dark": wood("ST_wood_dark", (0.030, 0.015, 0.008), (0.055, 0.028, 0.013), (0.090, 0.048, 0.024)),
        "cloth_red": cloth("ST_cloth_red", (0.30, 0.035, 0.035), 70.0, 0.3),
        "cloth_navy": cloth("ST_cloth_navy", (0.075, 0.085, 0.135), 90.0, 0.25),
        "canopy": cloth("ST_canopy", (0.030, 0.032, 0.040), 40.0, 0.4),
        "floor": concrete(),
        "lantern": paper_lantern(),
        "bottle": bottle(),
        "ceramic": ceramic(),
        "steel": brushed_steel("P_steel"),
        "card": cardboard("P_card"),
        "blue": plastic("P_blue"),
    }
