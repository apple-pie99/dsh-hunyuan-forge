# bridge：8081 适配层

`bridge/server.py` 是**本仓库自带的薄适配层**，不是腾讯的模型代码，也不包含任何凭证。

## 它解决什么

Hunyuan3D 的 Gradio 接口是两段式事件流（提交任务 → 轮询结果），
而 Blender 插件和本仓库的脚本只想要一件事：**一次 POST，拿回 GLB 字节**。

```
DSH / forge.py / 任何 HTTP 客户端
        │  POST http://127.0.0.1:8081/generate   {image: base64, octree_resolution, ...}
        ▼
   bridge/server.py（FastAPI）
        │  gradio_client → api_name="/shape_generation"
        ▼
   Hunyuan3D Gradio（http://127.0.0.1:8080）
        │  本地权重推理
        ▼
   white_mesh.glb  →  二进制回传
```

## 安全边界

- 只监听 `127.0.0.1`（回环），不对外网开放
- 无 API key、无账号、无遥测；除了 8080，不发任何外部请求
- `httpx` 显式 `trust_env=False`，防止走到系统代理
- 上传的图只落到系统临时目录，请求结束即删

## 接口

```http
POST /generate
{ "image": "<base64>", "octree_resolution": 128, "num_inference_steps": 5,
  "guidance_scale": 5.0, "texture": false, "seed": 1234 }
→ 200  model/gltf-binary   （GLB 字节）
→ 400  texture=true / 缺 image
→ 502  上游异常
```

```http
GET /health → {"ok": true, "upstream": "http://127.0.0.1:8080", "default_octree": 128}
```

字段说明：

- `image` 必填；`data:image/...;base64,` 前缀会自动剥掉
- `texture` 只能 `false`（上游部署带 `--disable_tex`）
- `text` 当前无效（没有启用文生 3D）
- 参数在服务端会夹到合法区间，越界不报错

## 启动

```bash
# 用整合包自带的 Python（它装了 fastapi / uvicorn / gradio_client）
<portable>\python_standalone\python.exe -u server.py
```

或双击同目录的 `start_bridge.bat`。前台窗口，关掉即停。

## 没有这套部署怎么办

桥接只是**一层协议转换**，完全可以替换。你只需要实现同样两个端点：

| 端点 | 要求 |
|---|---|
| `POST /generate` | 收 base64 图，返回 `model/gltf-binary` |
| `GET /health` | 返回 `{"ok": true}` |

可选实现：

- **ComfyUI**：起一个 `/prompt` + 轮询 `/history` 的包装，把输出 GLB 读回来
- **云 API**（腾讯云 3D、Meshy、Tripo 等）：把图转成它们的格式，等任务完成再下载 GLB
- **直接调 Gradio**：把 `server.py` 里的 `gradio_client` 段落换掉即可，其余逻辑不用动

然后：

```bash
export HY3D_BRIDGE=http://127.0.0.1:8081     # Windows: set HY3D_BRIDGE=...
```

`forge.py` 和 `gen_props.py` 都读这个环境变量，不用改代码。

## 已知限制

- **串行**：服务端一把锁，并发请求会排队
- **临时文件**：每次请求写一个 tmp 图，异常路径也会删
- **不校验图片内容**：传什么都转发，上游 rembg 自己处理背景
