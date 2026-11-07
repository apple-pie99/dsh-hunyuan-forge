# -*- coding: utf-8 -*-
"""第一步（Blender 内）：搭结构 → 布景 → 建占位体 → 渲参考图 → 存盘。

    blender -b -P run_build.py

产物：
    stall_base.blend   结构 + 占位体 + 相机灯光
    shots/<id>.png     喂给混元的参考图（先看这个再生成）
"""
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (os.path.join(ROOT, "forge"), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import build_stall  # noqa: E402
import forge  # noqa: E402
import scene_spec  # noqa: E402


def main():
    build_stall.clear()
    build_stall.build()

    spec = scene_spec.resolve(scene_spec.load(os.path.join(HERE, "props.json")))
    forge.stage_frame(spec, reset=False)
    forge.stage_shot(spec, out=HERE)

    # stage_frame/shot 会加临时太阳光和占位相机；展示用布景要收尾重建，
    # 否则渲染时会两套灯叠在一起、相机还对着最后一个占位体。
    for name in ("FORGE_key", "FORGE_fill", "FORGE_rim", "FORGE_CAM", "FORGE_ground"):
        o = bpy.data.objects.get(name)
        if o is not None:
            bpy.data.objects.remove(o, do_unlink=True)
    build_stall.studio()

    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "stall_base.blend"))
    print("BUILD_DONE  下一步：python gen_props.py")


if __name__ == "__main__":
    main()
