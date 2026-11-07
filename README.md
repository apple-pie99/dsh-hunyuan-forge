# dsh-hunyuan-forge

把「一张参考图 / 一句话需求」变成「一个能渲染、能导 GLB 的 3D 场景」。

核心思路一句话：**自己搭的白模，就是图生 3D 的输入图。** 轮廓和比例由你控制，
AI 只负责在轮廓里"长细节"——所以既不会跑偏，也不会像纯手搭那样平。

![ramen stall](examples/ramen/render.png)

> **状态：实验性 / WIP。** 只在一台 Windows 机器、Blender 5.2.3、一个场景上验证过。
> 代码是原型级，接口会变。别直接拿去当生产工具。

---

## 它解决什么问题

本地跑 Hunyuan3D 时，最常见的尴尬：**它只吃图，不吃文字**。
直接文生 3D 要额外的 T2I 权重（HunyuanDiT，几个 GB），还要和 shape 模型抢显存。

另一条路是：先用手搭的白模把**结构**定死，渲一张标准参考图喂给它，
再把出来的白模**按占位体的位置和尺寸自动摆回去**。这条路人少，但可控、可复现、全离线。

```
参考图 / 需求
   │  ① 拆解：资产清单（尺寸、位置、谁做）
   ▼
参数化结构（自己搭） + 占位体（混元的输入）
   │  ② 每个占位体渲一张标准 3/4 图（灰底、无地面、撑满画幅）
   ▼
Hunyuan3D img2mesh ──► 白模 GLB（只负责"长肉"）
   │  ③ 导入 / 清碎屑 / 减面 / 等比归一 / 落地 / 按 at+rot 对齐
   ▼
摆好的场景 ──► ④ 程序化材质 ──► ⑤ 布光出图 ──► ⑥ 导出 GLB
```

## 和"直接文生 3D"的区别

| | 本仓库 | 纯文生 3D |
|---|---|---|
| 输入 | 你控制的白模渲染图 | 一段文字 |
| 比例/构图 | 精确，按米 | 随机，靠抽卡 |
| 细节 | 由占位体轮廓决定，偏简 | 依赖 T2I 想象 |
| 离线 | ✅ 全本地 | 通常要额外 T2I 权重 |
| 场景拼装 | ✅ 多件自动归位 | 一般只出单件 |

> 想要更丰富的表面细节，社区做法是中间插一步 **depth-ControlNet 文生图**
> （见 [Tenitsky 的指南](https://tenitsky.com/guides/simple-3d-shapes-to-tank-concepts/)）：
> 白模 → 概念图 → img2mesh。本仓库把这一步做成了可选项（`src=t2i`），默认跳过以保持离线。

---

## 依赖

| 组件 | 要求 | 说明 |
|---|---|---|
| **Blender** | 5.2.x（在 5.2.3 验证） | 建结构、渲参考图、归位、出图。4.2+ 应该也能跑，未验证 |
| **Python** | 3.10+ | 只用来跑 `gen_props.py`（需要 `requests`），不占用 Blender |
| **Hunyuan3D** | 本地 Hunyuan3D-2 **mini/turbo** 整合包 | 详见 [docs/hunyuan-deploy.md](docs/hunyuan-deploy.md) |
| **桥接** | 本仓库 `bridge/server.py` | 8081 单次 POST → GLB 字节；见 [docs/bridge.md](docs/bridge.md) |
| 可选 | [DSH](https://github.com/) + `dsh-blender-plugin` | 让 AI agent 直接驱动 Blender；不用也能全程命令行 |

只想要脚本、已经有一套 img2mesh 服务？把 `HY3D_BRIDGE` 指向你自己的 `/generate` 实现即可。

## 快速开始

```bash
git clone <this-repo>
cd dsh-hunyuan-forge/examples/ramen
```

**① 起 Hunyuan（8080）+ 桥接（8081）**，确认：

```bash
curl http://127.0.0.1:8081/health   # {"ok": true, "upstream": "http://127.0.0.1:8080"}
```

**② 搭结构 + 出参考图（Blender）**

```bash
blender -b -P run_build.py
```

产出 `stall_base.blend` 和 `shots/*.png`。**先看 shots/ 里的图**——不像就别往下走。

**③ 生成（系统 Python，后台跑不卡界面）**

```bash
python gen_props.py
```

4 件道具，每件约 6 秒。

**④ 归位 + 材质 + 渲染 + 导出**

```bash
blender -b stall_base.blend -P run_place.py
```

产出 `render.png`、`stall.blend`、`stall.glb`（可直接丢 three.js）。

## 目录

```
forge/                核心库（不依赖示例）
├─ forge.py           建占位体 / 渲参考图 / 调桥接 / 归位
├─ scene_spec.py      清单校验 + 难度路由（纯 Python，可单测）
└─ rich_mats.py       程序化 PBR 材质（木/钢/纸/布/水泥/玻璃/瓷）
bridge/server.py      8081 适配层：REST → Hunyuan Gradio
docs/
├─ workflow.md        六步法（怎么做、怎么判断）
├─ pitfalls.md        Blender/glTF/EEVEE 的 10 个坑
├─ hunyuan-deploy.md  本机部署版本、参数、性能、许可
└─ bridge.md          桥接是什么、为什么需要、怎么替换
examples/ramen/       完整示例：日式拉面摊
```

## 局限（先说清楚）

- **程序化材质不进 GLB**：three.js 只认贴图，要带质感得先烘焙（UV + Cycles）。
- **没有 PBR 法线贴图**：近看纹理有重复。
- **单图没有背面**：生成的模型转一圈会穿帮。
- **只验证过一个场景**：复杂场景（植被、布料、人物）没试过。
- **Windows only**：路径与启动脚本按 Windows 写的。

## 许可与合规

- **代码**：[MIT](LICENSE)。
- **示例场景与渲染图**：CC BY 4.0。
- **本仓库不包含任何模型权重**。Hunyuan3D 由你自己部署，遵循
  [TENCENT HUNYUAN 3D 2.0 COMMUNITY LICENSE](https://github.com/Tencent-Hunyuan/Hunyuan3D-2)：
  个人与商用免版税，但**欧盟、英国、韩国不在授权范围内**；月活 > 100 万需单独申请；不得使用腾讯商标。
- 示例里**没有**任何第三方图片素材，`shots/` 与 `render.png` 全部由脚本生成。
