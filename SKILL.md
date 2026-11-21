---
name: holo-card-3d
description: Create 3D holographic and flowing-quicksand (流麻) collector cards from a reference image, producing a frozen 3-deliverable bundle (60fps offline WebGL2 HTML, 690x960 zero-ghosting transparent animated WebP, and 460x640 GIF). Use when the user asks to turn an image or character into a 3D holo card, SAR/UR collector card, or interactive quicksand card. Not for general 2D photo editing or video generation.
metadata:
  short-description: Turn images into 3D holo quicksand HTML, WebP, and GIF cards
  version: "2.1"
  compatibility: Portable across Antigravity, Codex, and Claude Code (with or without built-in image generation); requires Python 3 with numpy, Pillow, and opencv-python.
---

# 3D Holo Quicksand Collector Card (`holo-card-3d` · v2.1)

Turn a user-provided image into a standardized 3-layer + relief-depth 3D SAR/UR collector card with holographic foil, flowing quicksand + 3D micro-sequins, embossed bevel metallic borders, optional **1 surgical prop light FX + 1 crisp SDF motion motif** (zero extra AI image gen), and the frozen 3-file deliverable bundle.

This skill uses deterministic local scripts and omits external ChatGPT-web or Flow-2K manual multi-app steps.

## Workflow

### Phase 1: Inspect Input & Confirm Style + Art Method

1. Inspect the user's reference image first.
2. Confirm with the user (skip items already explicitly specified):
   - **Theme & Aesthetic** (e.g., 深海星海圣女 / 巴洛克塔罗, 赛博霓虹机能, 樱花和风, 暗夜哥特, 水墨国风).
   - **Art & Rendering Method** (e.g., 2.5D 日系厚涂, 赛璐璐平涂, 写实 3D 盲盒质感, 新中式金箔工笔).
   - **Frame Choice & Title/Badge**: Custom AI-generated `fg` frame vs. one of the bundled instant frames in `assets/frames/` (`classic_sar_gold.png`, `minimal_platinum.png`, `cyber_hud_frame.png`), plus card title, rarity badge (`SAR / UR`), and theme palette (`auto` or a preset from `assets/palettes.json`).
   - **v2.1 "1+1" Bespoke Polish** (zero extra image generation): Identify **1 hero prop** on the subject (weapon, staff, skateboard, spellbook, fan, lantern, instrument) for a pixel-exact single directional light sweep + hairline tip glint, and **1 matching SDF motion motif** (`feathers_bubbles`, `cyber_stars`, `petals`, `embers`, or `snowflakes`; or `none`).
3. **Chroma Check**: If the subject relies heavily on bright green (`#00FF00`-adjacent foliage, slime, green hair/clothes) and native transparent PNG output is unavailable, plan `#FF00FF` magenta backdrop for `mid` instead of green screen.

### Phase 2: Confirm Image-Gen Capability & Acquire Source Layers

Check whether the current harness has an image-generation tool/skill available (e.g., Antigravity `image-generator`, Codex `imagegen`, `openai-image`, or MCP image generation), or ask the user if unsure.

Initialize the project folder first in either track:
- `<workdir>/card_config.json` (copy/adapt from [assets/card_config.example.json](assets/card_config.example.json))
- `<workdir>/01_raw_layers/`

Read [references/prompt-templates.md](references/prompt-templates.md) before generating or handing off prompts.

#### Track A: Harness Has Image Generation

1. Generate `01_raw_layers/mid.png` (3:4 portrait, `>= 1024x1365`, native transparent RGBA PNG preferred; else solid `#00FF00` or `#FF00FF`). Inspect visually for intact pose/props with margin around limbs.
2. Generate `01_raw_layers/bg.png` (3:4 full-bleed atmospheric backdrop, no character, no card border, bright center glow slightly above midpoint). Inspect visually.
3. Unless using a bundled frame in `assets/frames/`, generate `01_raw_layers/fg.png` (3:4 perimeter-only collector frame covering outer 6%–14% rim with solid chroma/transparent inner window `>= 75%`).
4. Optional 4th depth layer: run `--stage matte` to produce `02_matted/mid_on_black.png`, then generate `01_raw_layers/mid_depth.png` via img2img grayscale bas-relief prompt on `#000000`. If img2img is unavailable or skipped, omit `mid_depth` — `prepare_assets.py` automatically synthesizes smooth relief depth (`depth_source: auto_synthesized`).

#### Track B: No Image Generation (e.g., Claude Code / External Gen)

1. Write `<workdir>/card_config.json` and create `<workdir>/01_raw_layers/`.
2. Deliver a tailored copy-ready English prompt pack + brief Chinese instructions from [references/prompt-templates.md](references/prompt-templates.md) supporting any of:
   - **Full 4-image mode**: `mid` + `bg` + `fg` + `mid_depth`
   - **3-image auto-depth mode**: `mid` + `bg` + `fg` (`mid_depth` auto-synthesized locally)
   - **2-image fast mode**: `mid` + `bg` (uses selected `assets/frames/*.png` + `--auto-depth`)
3. Tell the user the exact destination folder `<workdir>/01_raw_layers/` and **stop and wait** for them to supply the images.

### Phase 2.5: Surgical `1 Light FX + 1 Motion Motif` (Zero Extra Image Gen)

Follow the strict **"1+1 Restraint Rule"** so upgrades enhance the prop and atmosphere without ever washing out the original `v1.0` dark contrast or lineart:
- **DO NOT** add outer glowing card shells, background energy veins, UV wind distortion on character hair/clothes, circular gradient blobs, or multi-nova white flashbangs.

Steps:
1. Run matting first if not yet done (`--stage matte`), then export labeled `0.05` UV coordinate rulers on `mid`:
   ```bash
   python scripts/run_pipeline.py --workdir <workdir> --stage prop-grid
   # Optional zoomed crop on the prop region:
   python scripts/run_pipeline.py --workdir <workdir> --stage prop-grid --crop 0.56 0.04 0.98 0.86
   ```
2. Visually inspect `03_processed/uv_grid_mid.png` (and `uv_grid_crop.png`) to record exact normalized `[u, v]` coordinates (`0.0..1.0`):
   - `prop_fx.enabled: true`
   - `prop_fx.mask_polygons`: tight polygon list outlining ONLY the hero prop (zero face/hair/clothing overlap).
   - `prop_fx.exclude_polygons`: loose box(es) over gripping fingers/hands (`exclude_skin_in_exclude_zones: true` automatically strips skin pixels dilated by 2px so dark prop segments between splayed fingers still gleam cleanly).
   - `prop_fx.start_uv` & `prop_fx.tip_uv`: `[u, v]` sweep origin -> tip emblem/crystal where a single hairline ring (`~1.3px`) + needle star fires once per 5s cycle.
   - `prop_fx.tint` / `prop_fx.gain`: `"auto"` tint (follows palette `edge_spec`, or explicit `[r, g, b]`) and scalar gain (default `0.90`; dial down if the card base palette is very bright).
3. Choose **1** analytical SDF motif in `motion_motif.kind` matching the card theme:
   - `"feathers_bubbles"` (deep sea / celestial / angel)
   - `"cyber_stars"` (neon / Y2K / mecha / sci-fi)
   - `"petals"` (floral / Art Nouveau / spring / sakura)
   - `"embers"` (fire / forge / crimson blade)
   - `"snowflakes"` (winter / frost / crystal)
   - `"none"` (disable SDF shapes; keep classic v1.0 particles)
4. Verify mask accuracy before building final outputs:
   ```bash
   python scripts/run_pipeline.py --workdir <workdir> --stage prepare
   ```
   Visually inspect `03_processed/prop_mask_qa.png` (cyan fill, red contour, green start dot, gold tip marker) and refine `mask_polygons` / `exclude_polygons` with `--stage prop-mask` until zero bleed touches skin, face, or hair.

### Phase 3: Build, Render & Visual QA

1. Verify Python dependencies (`cv2`, `numpy`, `PIL`) using the project's Python interpreter:
   ```bash
   python -c "import cv2, numpy, PIL"
   ```
2. Run remaining stages (`--stage prepare` -> `html` -> `render` -> `verify`, or `--stage all` after `card_config.json` is finalized):
   ```bash
   python scripts/run_pipeline.py --workdir <workdir> --stage html
   python scripts/run_pipeline.py --workdir <workdir> --stage render
   python scripts/run_pipeline.py --workdir <workdir> --stage verify
   ```
3. Visually inspect ALL QA gates:
   - `03_processed/cutout_check.png`: clean edges, zero green/magenta fringe.
   - `03_processed/align_check.png`: face exclusion box, focal crosshair, depth map, contour match.
   - `03_processed/prop_mask_qa.png` (when `prop_fx.enabled`): tight prop silhouette, zero finger/face bleed.
   - `03_processed/qa_keyframes.png`: `f0`, prop gleam frame, peak hairline tip flare + SDF motif frame, opposite tilt, loop end, and checkerboard transparent WebP panel with crisp dark contrast (zero wash-out). Confirm `verify_outputs.py` prints `"status": "PASS"` and exits `0`.

### Phase 4: Deliver Standard 3 Outputs

Deliver only verified facts and file paths under `<workdir>/output/`:
1. `holographic_card.html` — offline single-file 60fps WebGL2 interactive 3D card (`5.2s` auto-orbit, `±30°/±19°` drag & gyro, `流畅`/`高清` toggle).
2. `holographic_card.webp` — `690x960` transparent RGBA animated WebP (`84` frames, `60 ms/frame`, `5.04s`, zero-ghosting `dispose=1, no_blend=1`).
3. `holographic_card.gif` — `460x640` themed studio-backdrop GIF (`84` frames, `60 ms/frame`, `5.04s`, 256-color Median Cut + Floyd–Steinberg).

## Bundled Files & Routing

- **Executable scripts** (`scripts/`): `run_pipeline.py`, `matte_layers.py`, `build_prop_mask.py`, `prepare_assets.py`, `render_card.py`, `build_html_card.py`, `verify_outputs.py`. Execute without loading full source unless patching behavior.
- **Bundled assets** (`assets/`):
  - `assets/palettes.json`: 7 curated palettes (`celestial-gold`, `crimson-gold`, `sakura-rose`, `cyber-neon`, `silver-frost`, `emerald-jade`, `ink-gold`).
  - `assets/card_config.example.json`: Config schema starter template including `prop_fx` and `motion_motif`.
  - `assets/frames/*.png`: Ready-to-use `1200x1600` RGBA collector frames (`classic_sar_gold.png`, `minimal_platinum.png`, `cyber_hud_frame.png`).
- **References** (`references/` — load on demand):
  - Read [references/prompt-templates.md](references/prompt-templates.md) when crafting Track A or Track B generation prompts.
  - Read [references/standard-spec.md](references/standard-spec.md) when verifying v2.1 optical/motion specs, prop-mask rules, anti-ghosting requirements, or `card_config.json` fields.
