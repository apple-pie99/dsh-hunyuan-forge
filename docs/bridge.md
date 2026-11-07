# bridge: the 8081 adapter

`bridge/server.py` is a **thin adapter that ships with this repo**. It is not Tencent model
code and contains no credentials.

English · [简体中文](bridge.zh.md)

## What it solves

Hunyuan3D's Gradio interface is a two-stage event stream (submit job → poll result). Blender
and the scripts here want one thing: **a single POST that returns GLB bytes**.

```
DSH / forge.py / any HTTP client
        │  POST http://127.0.0.1:8081/generate   {image: base64, octree_resolution, ...}
        ▼
   bridge/server.py (FastAPI)
        │  gradio_client → api_name="/shape_generation"
        ▼
   Hunyuan3D Gradio (http://127.0.0.1:8080)
        │  local weights
        ▼
   white_mesh.glb  →  binary response
```

## Security boundary

- listens on `127.0.0.1` only (loopback), not exposed to the network
- no API keys, no accounts, no telemetry; makes no outbound requests except to 8080
- `httpx` is forced with `trust_env=False` so a system proxy cannot hijack it
- uploaded images land in a temp file and are deleted when the request ends

## API

```http
POST /generate
{ "image": "<base64>", "octree_resolution": 128, "num_inference_steps": 5,
  "guidance_scale": 5.0, "texture": false, "seed": 1234 }
→ 200  model/gltf-binary   (GLB bytes)
→ 400  texture=true / missing image
→ 502  upstream failure
```

```http
GET /health → {"ok": true, "upstream": "http://127.0.0.1:8080", "default_octree": 128}
```

- `image` is required; a `data:image/...;base64,` prefix is stripped automatically
- `texture` must be `false` (upstream runs with `--disable_tex`)
- `text` is ignored (text-to-3D is not enabled)
- numeric parameters are clamped server-side rather than rejected

## Running it

```bash
# use the bundled interpreter (it has fastapi / uvicorn / gradio_client)
<portable>\python_standalone\python.exe -u server.py
```

Or double-click `start_bridge.bat`. Foreground process; closing it stops the bridge.

## If you don't have this deployment

The bridge is only **protocol translation**. Replace it and nothing else changes:

| Endpoint | Requirement |
|---|---|
| `POST /generate` | accept a base64 image, return `model/gltf-binary` |
| `GET /health` | return `{"ok": true}` |

Options:

- **ComfyUI**: wrap `/prompt` + poll `/history`, read the output GLB
- **Cloud APIs** (Tencent 3D, Meshy, Tripo…): convert the image, wait for the task, download the GLB
- **Talk to Gradio directly**: replace the `gradio_client` block in `server.py`, keep the rest

Then:

```bash
export HY3D_BRIDGE=http://127.0.0.1:8081     # Windows: set HY3D_BRIDGE=...
```

Both `forge.py` and `gen_props.py` read that variable — no code changes.

## Known limits

- **serial**: a single lock, concurrent requests queue
- **temp files**: one temp image per request, removed on both success and failure
- **no validation**: whatever you send is forwarded; the upstream background remover deals with it
