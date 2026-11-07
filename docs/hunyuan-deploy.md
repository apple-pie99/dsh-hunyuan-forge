# Local Hunyuan3D deployment (the configuration this repo was verified on)

This repository **ships no weights**. Below is the environment that was tested; reproduce it
and the examples should run.

English · [简体中文](hunyuan-deploy.zh.md)

---

## 1. Verified configuration

| Item | Value |
|---|---|
| Form | Windows portable bundle (WinPortable, cu129), unzip and run, ~**15 GB** |
| Code | [Hunyuan3D-2](https://github.com/Tencent-Hunyuan/Hunyuan3D-2) (the bundle carries a fork with mmgp VRAM optimisation) |
| Model | `tencent/Hunyuan3D-2mini`, **mini + turbo** weights |
| Weights | DiT `hunyuan3d-dit-v2-mini-turbo` 3.82 GB + VAE `hunyuan3d-vae-v2-mini-turbo` 0.39 GB = **4.24 GB** |
| Python | bundled `python_standalone` (torch 2.8.0+cu129) |
| Port | **8080** (Gradio UI + API) |

> The portable bundle is a third-party repack, not an official Tencent release. Verify its
> provenance before commercial use; the licence terms come from the official repository.

## 2. Starting it

```text
Hunyuan3D2_WinPortable\启动.bat  →  「保存并启动」
```

Wait for:

```text
Uvicorn running on http://0.0.0.0:8080
```

The launcher remembers its settings. It is effectively running:

```bat
set HF_HUB_CACHE=<root>\HuggingFaceHub
set HY3DGEN_MODELS=<root>\HuggingFaceHub      :: local weights first, no downloads
python -s Hunyuan3D-2\gradio_app.py --mini --turbo --disable_tex --profile 4 --port 8080
```

**Use the launcher, don't hand-roll the command.** Without `HY3DGEN_MODELS` the process tries
to reach HuggingFace; on a restricted network it looks hung (alive, busy CPU, flat memory,
no listening port).

## 3. Hard limits

| Parameter | Range | Notes |
|---|---|---|
| octree_resolution | **128–512** | 128 is the sweet spot; 256 is ~18 min on 8 GB |
| num_inference_steps | 1–100 (direct API) | 5 is enough for turbo; the Blender addon UI enforces ≥20 |
| guidance_scale | 1.0–10.0 | 5.0 |
| texture | **must be false** | deployed with `--disable_tex`; textures need DISO + more VRAM |
| text-to-3D | **unavailable** | needs `--enable_t23d` plus a HunyuanDiT checkpoint |
| multi-view | restart with `--mv` | single-image mode by default |

## 4. Performance (RTX 5060 Laptop, 8 GB / 24 GB RAM)

| Path | octree | steps | Time | Output |
|---|---|---|---|---|
| Direct API (this repo) | 128 | 5 | **6–10 s per part** | 2–6 MB GLB |
| Blender addon | 128 | 20 | ~15 s per part | ~100k faces |

VRAM: 2.4 GB idle, 5.7–6.3 GB peak. Serial service — one part at a time.

## 5. Health check

```bash
curl http://127.0.0.1:8080/config          # 200 = inference alive
curl http://127.0.0.1:8081/health          # {"ok": true, ...} = bridge alive
```

Bridge deployment: see [bridge.md](bridge.md).

## 6. Licence

[TENCENT HUNYUAN 3D 2.0 COMMUNITY LICENSE](https://github.com/Tencent-Hunyuan/Hunyuan3D-2):

- royalty-free for personal and commercial use
- **not licensed in the EU, the UK, or South Korea**
- >1M monthly active users requires separate permission from Tencent
- outputs are not deemed model derivatives — they belong to the user
- no Tencent trademarks

This repo only calls a service you run locally and redistributes no weights; compliance with
the model licence is your responsibility.
