# The six steps

This is the operational order, not a concept piece. Each step lists its input, output and
pass criterion.

English · [简体中文](workflow.zh.md)

---

## Step 1 · Decompose (paper only, no software)

Read four things off the reference: **scale, parts, materials, lighting**. Then give every
asset:

| Field | Meaning |
|---|---|
| `id` | unique name; placeholder is `BO_<id>`, result is `AS_<id>` |
| `size` | target bounding box, metres |
| `at` | world position of the **bottom-centre** (not the geometric centre) |
| `rot` | rotation around Z, 0 = front faces -Y |
| `method` | `build` (you) or `hy3d` (the model) |

Send the list for review **before** touching Blender. A wrong list means redoing everything.

Pass criterion: a layperson can count the big objects in the picture; you have at least that many.

## Step 2 · Structure (the part you build)

See `examples/ramen/build_stall.py` — three primitives cover most of it:

- `box(name, size, at, material)` — boards, posts, counter tops
- `cyl(name, r, h, at, material)` — pots, bowls, lanterns, stool seats
- `frustum(name, bottom, top, z0, z1, at, material)` — canopies, tapered volumes

Conventions:

- metres, Z up, front faces **-Y**, ground at `z=0`
- materials named by purpose (`ST_wood`, `P_steel`) — materials are cached by name
- detail comes from addition: plank strips under the counter, shelf edging, post shoes,
  lantern ribs

Pass criterion: with no materials, in wireframe, a stranger can still tell what it is.

## Step 3 · Placeholders + reference renders

```python
import sys; sys.path.insert(0, "<repo>/forge")
import forge, scene_spec
spec = scene_spec.resolve(scene_spec.load("props.json"))
forge.stage_frame(spec, reset=False)   # builds BO_<id>
forge.stage_shot(spec, out=".")        # 1024² reference per part
```

- **one part per image** — two objects, occlusion or a busy background degrade quality fast
- **compound placeholders (`parts`) beat a single box**: a pot = body + lid + two handles
- grey background, no floor, ~85% frame fill, fixed 3/4 view (azimuth 25°, elevation 18°)

Pass criterion: show `shots/xx.png` to someone who never saw the brief — they can name the object.

## Step 4 · Generate

```bash
python gen_props.py            # system Python; 4 parts ≈ 25 s
```

- `octree 128–160`, `steps 5`, `guidance 5.0`, serial
- retry once on failure; if it fails again, change the placeholder, not the knobs

Pass criterion: every file in `glb/` is megabytes (not hundreds of bytes), no FAIL in the log.

## Step 5 · Place

```python
forge.stage_place(spec, out=".")
```

Internally: join → weld → drop shells <100 faces → decimate to 20k → uniform normalise
(largest edge matches `size`) → bottom-centre to origin → position by `at`/`rot` → delete
the placeholder.

Pass criterion: everything stands where it should, nothing sinks or floats, size error < 10%.

## Step 6 · Materials / lighting / output

```python
import rich_mats
M = rich_mats.make_all()
```

- procedural materials use **Object coordinates**: no UVs, no stretching when resized,
  no drift when duplicated
- wood grain direction matters: vertical boards `axis="z"`, counter tops `axis="x"`
- lighting: cool three-point key/fill/rim + warm point lights inside the stall;
  `Standard` view transform
- output: EEVEE, 1600×900

Pass criterion: at 25% zoom, wood reads as wood, steel as steel, cloth as cloth.

---

## When not to use the model

| Situation | Do | Why |
|---|---|---|
| buildings, frames, counters, rails, pipes, boards | build it | parametric is faster and exact |
| longest edge ≥ 4 m | build it | large-scale proportion drifts |
| thinnest part < 2 cm, or thin/long < 6% | build it | plates turn to mush |
| pots, crates, baskets, rocks, plants, machine parts | generate | clear silhouette, irregular form |
| surfaces of revolution (lanterns, bowls, bottles, lids) | build it | generated ones come out crooked |

`scene_spec.route()` gives a first guess, but **the human eye decides**.

## Time budget (8 GB VRAM / 24 GB RAM, measured)

| Step | Time |
|---|---|
| structure + staging | ~1 s |
| reference renders | ~0.2 s each, ~2 s for 10 |
| generation | 6–10 s each |
| placement | 1–2 s each |
| render 1600×900 | 2–4 s |

A 10-part scene: 5–10 minutes end to end, excluding material tweaking.
