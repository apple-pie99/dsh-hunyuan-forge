# -*- coding: utf-8 -*-
"""scene_spec —— 场景清单的纯 Python 层：读取、校验、难度路由、尺寸计算。

这一层**不 import bpy**，可以在任何 Python 3.9+ 下跑：
- 让我在动手前先把「这个资产该自己做还是丢给混元」想清楚并写成数据；
- 让路由/校验逻辑能被单测覆盖，不必开 Blender。

清单（scene.json）的最小形状：

    {
      "name": "夜市面摊",
      "assets": [
        {"id": "stall",  "category": "框架", "size": [3.2, 1.4, 2.4], "at": [0, 0, 0], "rot": 0},
        {"id": "stove",  "category": "道具", "size": [0.9, 0.6, 0.45], "at": [0.8, 0, 0], "rot": 15,
                         "method": "hy3d", "src": "proxy", "octree": 128, "steps": 5}
      ]
    }

约定：
- **单位米**，`at` 是「落地点的底面中心」`[x, y, z]`，不是几何中心 —— 摆场景时这个语义最省事；
- `size` 是目标外接盒 `[dx, dy, dz]`，混元产物会被归一到这个尺度；
- `rot` 是绕 Z 轴的角度（度），0 表示正面朝 -Y。
"""
from __future__ import annotations

import json
import math
import os

METHODS = ("build", "hy3d", "manual")
SOURCES = ("proxy", "ref", "t2i")

# 类别 → 默认做法。判断是**建议**，清单里显式写了 method 就以清单为准。
BUILD_CATEGORIES = {
    "建筑", "结构", "框架", "地形", "地面", "墙", "墙面", "路面", "围栏", "栏杆",
    "管道", "台面", "楼梯", "招牌", "家具", "展台", "平台", "顶棚",
    "building", "structure", "frame", "terrain", "ground", "wall", "floor",
    "rail", "pipe", "counter", "stairs", "sign", "furniture",
}
HY3D_CATEGORIES = {
    "道具", "生物", "人物", "植物", "树", "岩石", "布", "机械", "杂物", "食品",
    "容器", "灯具", "雕塑", "零件", "装备",
    "prop", "creature", "character", "plant", "tree", "rock", "cloth",
    "machine", "clutter", "food", "container", "lamp", "sculpture", "part",
}

# 路由阈值（写在这里，调的时候不用翻代码）
MAX_BUILD_SPAN = 4.0      # 超过 4 米的结构，混元很难守住比例 → 自己做
MIN_HY3D_THICK = 0.02     # 最薄处 < 2cm（板/片/线）→ 混元会做成一坨 → 自己做
PLATE_RATIO = 0.06        # 最薄/最长 < 6% 视为板片


class SpecError(ValueError):
    """清单格式错误（带具体字段位置）。"""


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        spec = json.load(fh)
    return validate(spec)


def _num3(value, where: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise SpecError("%s 必须是 3 个数字的数组，收到 %r" % (where, value))
    out = []
    for v in value:
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise SpecError("%s 含非数字 %r" % (where, v))
        out.append(float(v))
    return out


def _parts(raw) -> list:
    if not raw:
        return []
    if not isinstance(raw, list):
        raise SpecError("parts 必须是数组")
    out = []
    for j, p in enumerate(raw):
        where = "parts[%d]" % j
        if not isinstance(p, dict):
            raise SpecError("%s 必须是对象" % where)
        out.append({
            "shape": str(p.get("shape") or "box").strip().lower(),
            "size": _num3(p.get("size", [1, 1, 1]), where + ".size"),
            "at": _num3(p.get("at", [0, 0, 0]), where + ".at"),
        })
    return out


def validate(spec: dict) -> dict:
    """校验并补全默认值，返回新 dict（不原地改）。"""
    if not isinstance(spec, dict):
        raise SpecError("清单根节点必须是对象")
    assets = spec.get("assets")
    if not isinstance(assets, list) or not assets:
        raise SpecError("assets 必须是非空数组")

    seen = set()
    clean = []
    for i, a in enumerate(assets):
        where = "assets[%d]" % i
        if not isinstance(a, dict):
            raise SpecError("%s 必须是对象" % where)
        aid = str(a.get("id") or "").strip()
        if not aid:
            raise SpecError("%s 缺少 id" % where)
        if aid in seen:
            raise SpecError("id 重复：%s" % aid)
        seen.add(aid)

        size = _num3(a.get("size"), where + ".size")
        if min(size) <= 0:
            raise SpecError("%s.size 三个分量都必须 > 0，收到 %r" % (where, size))
        at = _num3(a.get("at", [0, 0, 0]), where + ".at")
        rot = float(a.get("rot", 0.0))

        method = str(a.get("method") or "").strip().lower()
        if method and method not in METHODS:
            raise SpecError("%s.method 只能是 %s，收到 %r" % (where, "/".join(METHODS), method))
        src = str(a.get("src") or "").strip().lower()
        if src and src not in SOURCES:
            raise SpecError("%s.src 只能是 %s，收到 %r" % (where, "/".join(SOURCES), src))

        item = {
            "id": aid,
            "category": str(a.get("category") or "").strip(),
            "size": size,
            "at": at,
            "rot": rot % 360.0,
            "shape": str(a.get("shape") or "box").strip().lower(),
            "parts": _parts(a.get("parts")),
            "method": method,
            "src": src,
            "note": str(a.get("note") or ""),
            "prompt": str(a.get("prompt") or ""),
            "octree": int(a.get("octree", 128)),
            "steps": int(a.get("steps", 5)),
            "seed": int(a.get("seed", 1234)),
            "faces": int(a.get("faces", 20000)),
            "ref": str(a.get("ref") or ""),
            "texture": bool(a.get("texture", False)),
            "optional": bool(a.get("optional", False)),
        }
        clean.append(item)

    out = {
        "name": str(spec.get("name") or "untitled"),
        "units": "m",
        "assets": clean,
        "notes": str(spec.get("notes") or ""),
    }
    return out


def route(asset: dict) -> dict:
    """给一个资产出「怎么做 / 为什么」。显式 method 优先。"""
    if asset.get("method"):
        return {"method": asset["method"], "why": "清单显式指定"}

    cat = (asset.get("category") or "").strip()
    size = asset["size"]
    span = max(size)
    thin = min(size)

    if cat in BUILD_CATEGORIES:
        return {"method": "build", "why": "类别「%s」属于结构/规则件" % cat}
    if cat in HY3D_CATEGORIES:
        return {"method": "hy3d", "why": "类别「%s」属于形态件，混元合适" % cat}
    if span >= MAX_BUILD_SPAN:
        return {"method": "build", "why": "跨度 %.2fm ≥ %.1fm，混元守不住比例" % (span, MAX_BUILD_SPAN)}
    if thin < MIN_HY3D_THICK:
        return {"method": "build", "why": "最薄处 %.3fm 太薄，混元会糊成一坨" % thin}
    if thin / span < PLATE_RATIO:
        return {"method": "build", "why": "板片形态（%.1f%%），自己做更可控" % (100 * thin / span)}
    return {"method": "hy3d", "why": "中小尺度形态件，混元性价比最高"}


def resolve(spec: dict) -> dict:
    """把 method / src 全部落实成确定值，附路由理由。"""
    for a in spec["assets"]:
        r = route(a)
        a["method"] = r["method"]
        a["why"] = r["why"]
        if a["method"] == "hy3d" and not a["src"]:
            a["src"] = "ref" if a["ref"] else "proxy"
        if not a["src"]:
            a["src"] = "proxy"
    return spec


def scene_bounds(spec: dict) -> dict:
    """所有资产落地盒的并集（给相机取景用）。"""
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    for a in spec["assets"]:
        cx, cy, cz = a["at"]
        dx, dy, dz = a["size"]
        lo = [min(lo[0], cx - dx / 2), min(lo[1], cy - dy / 2), min(lo[2], cz)]
        hi = [max(hi[0], cx + dx / 2), max(hi[1], cy + dy / 2), max(hi[2], cz + dz)]
    if lo[0] is math.inf:
        return {"min": [0, 0, 0], "max": [0, 0, 0], "size": [0, 0, 0]}
    return {"min": lo, "max": hi, "size": [hi[i] - lo[i] for i in range(3)]}


def summary(spec: dict) -> str:
    counts = {}
    for a in spec["assets"]:
        counts[a["method"]] = counts.get(a["method"], 0) + 1
    b = scene_bounds(spec)
    parts = ["%s：%d 件资产" % (spec["name"], len(spec["assets"]))]
    parts.append("build %d / hy3d %d / manual %d" % (
        counts.get("build", 0), counts.get("hy3d", 0), counts.get("manual", 0)))
    parts.append("场景包围盒 %.1f×%.1f×%.1f m" % tuple(b["size"]))
    return " · ".join(parts)


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="校验 scene.json 并打印路由建议")
    p.add_argument("spec")
    p.add_argument("--json", action="store_true", help="输出解析后的清单")
    ns = p.parse_args(argv)
    spec = resolve(load(ns.spec))
    print(summary(spec))
    for a in spec["assets"]:
        print("  %-10s %-5s %-6s %-24s %s" % (
            a["id"], a["method"], a["src"], a["category"] or "-", a["why"]))
    if ns.json:
        print(json.dumps(spec, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
