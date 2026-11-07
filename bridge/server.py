"""Hunyuan3D local bridge: DSH/Blender 8081 /generate  ->  local Gradio app 8080.

Contract (from dsh_blender_bridge/commands/hunyuan/submit.py:113-158):
  POST /generate  application/json
    {octree_resolution:int, num_inference_steps:int, guidance_scale:float,
     texture:bool, image:"<base64>", text:"<optional>"}
  -> 200 with raw GLB bytes.
"""
import base64
import os
import tempfile
import threading
import time
import traceback
from typing import Optional

import httpx

_orig_init = httpx.Client.__init__


def _init_no_proxy(self, *a, **kw):
    kw["trust_env"] = False
    return _orig_init(self, *a, **kw)


httpx.Client.__init__ = _init_no_proxy

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response
from gradio_client import Client, handle_file
from pydantic import BaseModel

UPSTREAM = os.environ.get("HY3D_UPSTREAM", "http://127.0.0.1:8080")
PORT = int(os.environ.get("HY3D_BRIDGE_PORT", "8081"))
DEFAULT_OCTREE = int(os.environ.get("HY3D_DEFAULT_OCTREE", "128"))

app = FastAPI(title="Hunyuan3D local bridge")
_client = None
_lock = threading.Lock()


def upstream_client():
    global _client
    if _client is None:
        _client = Client(UPSTREAM, verbose=False)
    return _client


class GenerateRequest(BaseModel):
    image: Optional[str] = None
    text: Optional[str] = None
    octree_resolution: int = 128
    num_inference_steps: int = 5
    guidance_scale: float = 5.0
    texture: bool = False
    seed: int = 1234


@app.get("/health")
def health():
    try:
        r = httpx.get(UPSTREAM + "/config", timeout=8)
        return {"ok": r.status_code == 200, "upstream": UPSTREAM,
                "default_octree": DEFAULT_OCTREE}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=503)


@app.post("/generate")
def generate(req: GenerateRequest):
    if req.texture:
        raise HTTPException(400, "texture=false required: this deployment runs with --disable_tex")
    if not req.image:
        raise HTTPException(400, "image is required: local model is image-to-shape only "
                                 "(text-to-3D needs --enable_t23d)")
    raw = req.image.strip()
    if raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        blob = base64.b64decode(raw)
    except Exception:
        raise HTTPException(400, "image is not valid base64")
    if not blob:
        raise HTTPException(400, "image decoded to 0 bytes")

    suffix = ".jpg" if blob[:3] == b"\xff\xd8\xff" else ".png"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as fh:
        fh.write(blob)

    octree = max(16, min(512, int(req.octree_resolution)))
    steps = max(1, min(100, int(req.num_inference_steps)))
    started = time.time()
    try:
        with _lock:
            res = upstream_client().predict(
                caption=req.text or "",
                image=handle_file(tmp_path),
                mv_image_front=None, mv_image_back=None,
                mv_image_left=None, mv_image_right=None,
                steps=int(steps),
                guidance_scale=float(req.guidance_scale),
                seed=int(req.seed),
                octree_resolution=int(octree),
                check_box_rembg=True,
                num_chunks=8000,
                randomize_seed=False,
                api_name="/shape_generation",
            )
        first = res[0]
        if isinstance(first, dict):
            glb_path = first.get("path") or first.get("value")
        else:
            glb_path = str(first)
        if not glb_path:
            raise HTTPException(502, "upstream returned no mesh file (generation may have failed)")
        with open(glb_path, "rb") as fh:
            payload = fh.read()
        elapsed = time.time() - started
        print("[bridge] ok %d bytes in %.1fs (octree=%d steps=%d)"
              % (len(payload), elapsed, octree, steps), flush=True)
        return Response(
            content=payload,
            media_type="model/gltf-binary",
            headers={"X-Gen-Seconds": "%.1f" % elapsed, "X-Octree": str(octree)},
        )
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(502, "upstream generation failed: %s" % exc)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
