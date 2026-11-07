# Pitfalls

Blender 5.2.3 + Windows + local Hunyuan3D-2. Sorted by how much time each one costs.

English · [简体中文](pitfalls.zh.md)

---

### 1. `matrix_world` is not evaluated yet after creating an object

You set `obj.location`, but `obj.matrix_world` is still identity, so `bound_box` reports the
origin. Symptom: the camera aims at nothing and you render an empty grey frame.

```python
bpy.context.view_layer.update()   # required after building, before reading bounds
```

### 2. Materials are cached by name — your edits silently do nothing

```python
m = bpy.data.materials.get("ST_wood")
if m: return m        # ← last build's material, reused as-is
```

When rebuilding a scene you must drop them:

```python
for m in list(bpy.data.materials):
    if m.name.startswith(("ST_", "P_")):
        bpy.data.materials.remove(m)
```

Half an hour of "why didn't the colour change" comes from this.

### 3. Iterating `view_layer.objects` can yield `None`

After removing objects, stale entries remain and `o.select_set(False)` raises
`AttributeError: 'NoneType'`.

```python
def _deselect_all():
    try: bpy.ops.object.select_all(action="DESELECT")
    except Exception: pass
    for o in bpy.data.objects:
        try: o.select_set(False)
        except Exception: pass
```

### 4. In 5.x the engine identifier is `BLENDER_EEVEE`

`EEVEE_NEXT` is not valid everywhere. Use a try chain:

```python
for name in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
    try:
        bpy.context.scene.render.engine = name; break
    except (TypeError, ValueError):
        continue
```

### 5. Looking up the world background by name fails on localised UIs

In a Chinese UI the node is called 背景, not `Background`. Find by type:

```python
bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
```

### 6. Transparent glass needs both Alpha and a render method

`Alpha` alone does nothing in EEVEE Next:

```python
mat.surface_render_method = "BLENDED"   # 4.2+
# older: mat.blend_method = "BLEND"
```

### 7. glTF import adds a `world` empty

Setting `parent = None` loses the world transform. Store and restore the matrix:

```python
mats = {o.name: o.matrix_world.copy() for o in meshes}
for o in meshes:
    o.parent = None
    o.matrix_world = mats[o.name]
```

### 8. Exports skip hidden objects

Objects with `hide_viewport` are skipped, producing a 132-byte GLB.

```python
for o in bpy.data.objects:
    o.select_set(o.type == "MESH" and not o.hide_render)
```

### 9. Procedural materials do not survive GLB export

three.js only reads textures. Noise-node wood grain becomes a flat colour. To keep it you
must bake: UV unwrap → Cycles bake basecolor/roughness/normal → reconnect image textures.

### 10. More than ~1 s on the main thread freezes the UI

Generating 4 parts takes 25 s; run it in Blender and the window is dead for 25 s.
Run generation in system Python (`gen_props.py`); Blender only builds, renders and exports.

---

## Two non-code traps

- **Don't use octree 256.** On an 8 GB card it goes from ~6 s to ~18 min per part.
- **Don't guess `gradio_app.py` flags.** The official launcher sets `HY3DGEN_MODELS` and
  `HF_ENDPOINT`; starting the app yourself typically hangs at model load — the process is
  alive, CPU is busy, memory never grows, and the port never opens.
