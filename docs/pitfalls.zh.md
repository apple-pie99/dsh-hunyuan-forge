# 踩坑清单

Blender 5.2.3 + Windows + Hunyuan3D-2 本地部署，实测踩出来的。按"会浪费你多少时间"排序。

---

### 1. 新建对象后 `matrix_world` 还没求值

`obj.location` 设了，但 `obj.matrix_world` 还是单位矩阵，`bound_box` 读出来在原点。
后果：相机对着空气、渲染出一片灰。

```python
bpy.context.view_layer.update()   # 建完对象、算包围盒之前必须调
```

### 2. 材质按名字缓存，改了不生效

```python
m = bpy.data.materials.get("ST_wood")
if m: return m        # ← 上一轮的材质直接被复用
```

重建场景时不清材质，你会盯着"改了颜色怎么没变"看半小时。
`clear()` 里要：

```python
for m in list(bpy.data.materials):
    if m.name.startswith(("ST_", "P_")):
        bpy.data.materials.remove(m)
```

### 3. 遍历 `view_layer.objects` 会吐出 `None`

删过对象之后，这个集合里会有失效项，`o.select_set(False)` 直接 `AttributeError: 'NoneType'`。

```python
def _deselect_all():
    try: bpy.ops.object.select_all(action="DESELECT")
    except Exception: pass
    for o in bpy.data.objects:
        try: o.select_set(False)
        except Exception: pass
```

### 4. 引擎名在 5.x 是 `BLENDER_EEVEE`

`EEVEE_NEXT` 在某些版本已经改回来，写死会 `TypeError`。用 try 链：

```python
for name in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
    try:
        bpy.context.scene.render.engine = name; break
    except (TypeError, ValueError):
        continue
```

### 5. 世界背景节点按名字找会失败

中文界面下节点名是"背景"，不是 `Background`。按类型找：

```python
bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
```

### 6. 玻璃透明要同时设 Alpha 和渲染方式

只给 `Alpha` 不出效果，EEVEE Next 还要：

```python
mat.surface_render_method = "BLENDED"   # 4.2+
# 老版本: mat.blend_method = "BLEND"
```

### 7. glTF 导入多一层 `world` 空物体

直接 `parent = None` 会丢世界变换。先存矩阵再还原：

```python
mats = {o.name: o.matrix_world.copy() for o in meshes}
for o in meshes:
    o.parent = None
    o.matrix_world = mats[o.name]
```

### 8. 导出 GLB 前必须取消隐藏

`hide_viewport` 的物体会被导出器跳过，得到一个 132 字节的空 GLB。

```python
for o in bpy.data.objects:
    o.select_set(o.type == "MESH" and not o.hide_render)
```

### 9. 程序化材质不进 GLB

three.js 只认贴图。噪波节点连出来的木纹，导出去全变纯色。
要带质感必须烘焙：UV 展开 → Cycles 烘 basecolor/roughness/normal → 重连 image texture。

### 10. 主线程超过 1 秒会卡界面

生成 4 件要 25 秒，放在 Blender 里跑，界面就冻 25 秒。
把生成放到系统 Python（`gen_props.py`），Blender 只负责建/渲/导。

---

## 附：两个非代码的坑

- **别用 256 的 octree**。8GB 卡上从 128 提到 256，时间从 6 秒变成 18 分钟级。
- **别自己猜 gradio_app.py 的启动参数**。整合包用启动器时会设置 `HY3DGEN_MODELS`、
  `HF_ENDPOINT` 这些环境变量；手动起很可能卡在模型加载（表现为：进程活着、CPU 在动、
  内存不涨、端口一直不监听）。
