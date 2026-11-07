# -*- coding: utf-8 -*-
"""把 shots/*.png 交给 8081 桥接，拿回 GLB。

用**系统 Python** 跑（不是 Blender 的 Python），这样生成期间 Blender 界面不卡。

用法：
    python gen_props.py
    python gen_props.py --only pot_large,pot_small
    python gen_props.py --bridge http://127.0.0.1:8081 --octree 160

产物：
    glb/<id>.glb        混元原始白模
    gen_report.json     每件的耗时与大小（失败也记）
"""
import argparse
import base64
import json
import os
import sys
import time

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(BASE, "shots")
GLB = os.path.join(BASE, "glb")


def main(argv=None):
    ap = argparse.ArgumentParser(description="批量图生 3D（Hunyuan3D 本地桥接）")
    ap.add_argument("--spec", default=os.path.join(BASE, "props.json"))
    ap.add_argument("--bridge", default=os.environ.get("HY3D_BRIDGE", "http://127.0.0.1:8081"))
    ap.add_argument("--only", default="", help="逗号分隔的 id")
    ap.add_argument("--octree", type=int, default=0, help="覆盖清单里的 octree")
    ap.add_argument("--steps", type=int, default=5)
    ap.add_argument("--seed", type=int, default=1234)
    ns = ap.parse_args(argv)

    spec = json.load(open(ns.spec, encoding="utf-8"))
    assets = [a for a in spec["assets"] if a.get("method", "hy3d") == "hy3d"]
    only = set(x.strip() for x in ns.only.split(",") if x.strip())
    if only:
        assets = [a for a in assets if a["id"] in only]
    if not assets:
        print("没有要生成的资产")
        return 1

    os.makedirs(GLB, exist_ok=True)
    try:
        health = requests.get(ns.bridge + "/health", timeout=10).json()
    except Exception as exc:
        print("桥接不可用：%s" % exc)
        print("先起 8080 推理服务和 8081 桥接，见 docs/hunyuan-deploy.md")
        return 2
    print("health", health, flush=True)
    if not health.get("ok"):
        print("BRIDGE_NOT_READY（8080 没起？）")
        return 2

    report = {}
    for a in assets:
        aid = a["id"]
        src = os.path.join(SHOTS, aid + ".png")
        dst = os.path.join(GLB, aid + ".glb")
        if not os.path.isfile(src):
            report[aid] = {"ok": False, "error": "no shot: %s" % src}
            print("%-12s SKIP 没有参考图" % aid, flush=True)
            continue
        b64 = base64.b64encode(open(src, "rb").read()).decode()
        octree = ns.octree or int(a.get("octree", 128))
        t0 = time.time()
        try:
            r = requests.post(
                ns.bridge + "/generate",
                json={"image": b64,
                      "octree_resolution": octree,
                      "num_inference_steps": ns.steps,
                      "guidance_scale": 5.0,
                      "seed": ns.seed},
                timeout=(10, 900))
            el = time.time() - t0
            if r.status_code != 200 or not r.content.startswith(b"glTF"):
                report[aid] = {"ok": False, "status": r.status_code,
                               "head": r.content[:60].decode("utf-8", "replace")}
                print("%-12s FAIL %s %s" % (aid, r.status_code, r.text[:80]), flush=True)
                continue
            open(dst, "wb").write(r.content)
            report[aid] = {"ok": True, "bytes": len(r.content), "sec": round(el, 1),
                           "octree": octree}
            print("%-12s ok %.2fMB %.1fs" % (aid, len(r.content) / 1e6, el), flush=True)
        except Exception as exc:
            report[aid] = {"ok": False, "error": str(exc)}
            print("%-12s ERR %s" % (aid, exc), flush=True)

    with open(os.path.join(BASE, "gen_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    ok = sum(1 for v in report.values() if v.get("ok"))
    print("GEN_DONE %d/%d 成功" % (ok, len(report)), flush=True)
    return 0 if ok == len(report) else 1


if __name__ == "__main__":
    sys.exit(main())
