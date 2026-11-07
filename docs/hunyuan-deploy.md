# Hunyuan3D 本地部署（本仓库验证过的版本）

本仓库**不附带**任何模型或整合包。下面是验证环境，照着准备即可复现。

---

## 1. 验证过的部署形态

| 项 | 值 |
|---|---|
| 形态 | Windows 便携整合包（WinPortable，cu129），解压即用，约 **15 GB** |
| 代码版本 | [Hunyuan3D-2](https://github.com/Tencent-Hunyuan/Hunyuan3D-2)（腾讯官方，整合包内是带 mmgp 显存优化的 fork） |
| 模型 | `tencent/Hunyuan3D-2mini`，**mini + turbo** 权重 |
| 权重体积 | DiT `hunyuan3d-dit-v2-mini-turbo` 3.82 GB + VAE `hunyuan3d-vae-v2-mini-turbo` 0.39 GB，合计 **4.24 GB** |
| Python | 整合包自带 `python_standalone`（torch 2.8.0+cu129） |
| 服务端口 | **8080**（Gradio WebUI + API） |

> 整合包是第三方重打包（不是腾讯官方发布物）。商用前请自行核对包的来源与完整性；
> 官方代码与权重许可以腾讯仓库为准。

## 2. 启动

```text
Hunyuan3D2_WinPortable\启动.bat  →  点底部「保存并启动」
```

等日志出现：

```text
Uvicorn running on http://0.0.0.0:8080
```

启动器会记住配置，**不用每次重填**。它实际等价于：

```bat
set HF_HUB_CACHE=<root>\HuggingFaceHub
set HY3DGEN_MODELS=<root>\HuggingFaceHub      :: 关键：本地权重优先，不联网
python -s Hunyuan3D-2\gradio_app.py --mini --turbo --disable_tex --profile 4 --port 8080
```

**建议用启动器，不要手搓命令行。** 少了 `HY3DGEN_MODELS`，模型会去 HuggingFace 下载，
在国内表现为"进程活着、CPU 在动、内存不涨、端口一直不监听"——看起来像卡死，其实在等网络。

## 3. 参数限制（都是硬限制）

| 参数 | 范围 / 取值 | 说明 |
|---|---|---|
| octree_resolution | **128–512** | 128 是甜点；256 在 8GB 卡上 18 分钟级，别碰 |
| num_inference_steps | 1–100（API 直调） | turbo 模型 **5 步**就够；Blender 插件 UI 锁死 ≥20 |
| guidance_scale | 1.0–10.0 | 5.0 |
| texture | **只能 false** | 部署时带 `--disable_tex`，开纹理需要额外编译 DISO + 更多显存 |
| 文生 3D | **不可用** | 需 `--enable_t23d`，要再下一套 HunyuanDiT 权重（几个 GB）并和 shape 模型抢显存 |
| 多视图 | 需重启换 `--mv` | 默认单图 |

## 4. 性能（RTX 5060 Laptop 8GB / 24GB RAM）

| 通道 | octree | steps | 耗时 | 输出 |
|---|---|---|---|---|
| API 直调（本仓库走这条） | 128 | 5 | **6–10 s/件** | 2–6 MB GLB |
| Blender 插件全链路 | 128 | 20 | ~15 s/件 | ~10 万面 |

显存：空闲 2.4 GB，峰值 5.7–6.3 GB（总 8.15 GB）。
串行服务，一次一件；批量就排队。

## 5. 自检

```bash
curl http://127.0.0.1:8080/config          # 200 即服务活着
curl http://127.0.0.1:8081/health          # {"ok": true, ...} 即桥接通了
```

桥接的部署见 [bridge.md](bridge.md)。

## 6. 许可

[TENCENT HUNYUAN 3D 2.0 COMMUNITY LICENSE](https://github.com/Tencent-Hunyuan/Hunyuan3D-2)：

- 个人与商用**免版税**
- **欧盟、英国、韩国不在授权范围内**
- 月活用户 > 100 万需向腾讯单独申请
- 生成物归属：许可明确 `Outputs by themselves are not deemed Model Derivatives`，输出归使用者
- 不得使用腾讯商标

本仓库只调用你本地的服务，不重新分发权重；你在部署与使用时的合规责任自负。
