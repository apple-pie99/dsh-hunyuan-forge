# -*- coding: utf-8 -*-
"""第三步（Blender 内）：归位 → 套材质 → 渲染 → 导出 GLB。

    blender -b stall_base.blend -P run_place.py

前提：已经跑过 run_build.py 和 gen_props.py（glb/ 里有文件）。
产物：stall.blend / stall.glb / render.png
"""
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (os.path.join(ROOT, "forge"), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import forge  # noqa: E402
import rich_mats  # noqa: E402
import scene_spec  # noqa: E402


def dress():
    """按 forge_id 前缀给混元件套材质（它们导入进来是白模）。"""
    steel = rich_mats.brushed_steel("P_steel")
    card = rich_mats.cardboard("P_card")
    blue = rich_mats.plastic("P_blue")
    look = {"pot": steel, "crate_card": card, "crate_blue": blue}
    for o in bpy.data.collections.get("ASSETS", bpy.data.collections.new("ASSETS")).objects:
        if o.type != "MESH":
            continue
        fid = str(o.get("forge_id") or o.name)
        for prefix, mat in look.items():
            if fid.startswith(prefix):
                o.data.materials.clear()
                o.data.materials.append(mat)
                break


def main():
    spec = scene_spec.resolve(scene_spec.load(os.path.join(HERE, "props.json")))
    rows = forge.stage_place(spec, out=HERE)
    ok = [r for r in rows if r.get("status") == "ok"]
    print("placed %d/%d" % (len(ok), len(rows)))
    if not ok:
        print("没有可归位的 GLB，先跑 gen_props.py")
        return

    dress()

    sc = bpy.context.scene
    sc.render.resolution_x = 1600
    sc.render.resolution_y = 900
    sc.render.filepath = os.path.join(HERE, "render.png")
    bpy.ops.render.render(write_still=True)

    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "stall.blend"))
    for o in bpy.data.objects:
        o.select_set(o.type == "MESH" and not o.hide_render)
    bpy.ops.export_scene.gltf(filepath=os.path.join(HERE, "stall.glb"),
                              export_format="GLB", use_selection=True)
    print("PLACE_DONE  render.png / stall.glb 已生成")


if __name__ == "__main__":
    main()
