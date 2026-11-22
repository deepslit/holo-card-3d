---
name: holo-card-3d
description: >-
  Create 3D holographic and flowing-quicksand (流麻) collector cards from a reference
  image via zero-image-gen local matting or AI layer redraw, exporting a 3-deliverable
  bundle (60fps offline WebGL2 HTML, ~16.7fps 690x960 zero-ghosting transparent WebP,
  and ~16.7fps 460x640 GIF). Use when the user asks to turn an image or character into
  a 3D holo card, SAR/UR collector card, or interactive quicksand card. Not for general
  2D photo editing or video generation.
metadata:
  short-description: Turn images into 3D holo quicksand HTML, WebP, and GIF cards
  version: "2.2"
  compatibility: Portable across any SKILL.md-compatible agent harness (Claude Code, Codex, Antigravity, Cursor, Windsurf, Gemini CLI, OpenCode, Cline, GitHub Copilot, etc.) or standalone CLI; requires Python 3.10+ with numpy, Pillow, and opencv-python.
---

# 3D Holo Quicksand Collector Card (`holo-card-3d` · v2.2)

Turn a user-provided image into a standardized 3-layer + relief-depth 3D SAR/UR collector card with holographic foil, flowing quicksand + 3D micro-sequins, metallic bevel frames, optional **1 surgical prop light sweep + 1 analytical SDF motion motif**, and a 3-file deliverable bundle.

## Workflow

### Phase 0: Environment Preflight

Before running pipeline scripts, verify a real Python 3.10+ interpreter (avoid Windows Store `WindowsApps` aliases) and dependencies (`numpy`, `Pillow` with `webp_anim`, `opencv-python`) using [scripts/check_env.py](./scripts/check_env.py):

```bash
python scripts/check_env.py --workdir <workdir>
```

If `status != "OK"`, follow the printed `recommended_commands` (`pip install -r requirements.txt` or isolated `.venv`) before continuing.

### Phase 1: Inspect Input & Propose Default Plan

1. Inspect the user's reference image first (aspect ratio, backdrop type, whether the subject is already polished art, and whether a distinct hero prop exists).
2. Classify the user's intent into one of **3 explicit routes** (never silently call AI image-gen to redraw a character when the user asked to keep the original artwork):
   - **Route 1 — Keep Original Artwork (Zero Image Gen)**: Pixel-faithful local cutout via [scripts/matte_layers.py](./scripts/matte_layers.py) (`rgba` / `green` / `magenta` / `blue` / `solid` / `grabcut` / `none`) + procedural atmospheric backdrop (auto-synthesized if `01_raw_layers/bg.*` is omitted) + built-in frame (`assets/frames/*.png`) + `--auto-depth`. Works from **1 single image**.
   - **Route 2 — Hybrid (Keep Original Subject + Custom BG/Frame, or vice versa)**: Local pixel cutout for kept layers; generate or accept user-supplied assets only for layers the user wants replaced.
   - **Route 3 — Reference-Based AI Redraw**: Full style transfer, pose redesign, or TCG re-illustration via Track A (built-in imagegen) or Track B (copy-ready prompt pack).
3. **Propose-Default-First (Low Friction)**: Do not interrogate the user with a long questionnaire. Infer a sensible default package from the image and present **one concise confirmation block** covering only impactful choices (skip confirmation if the user already specified preferences or asked you to decide):
   - **Route**: Route 1 (keep original pixels), Route 2 (hybrid), or Route 3 (AI redraw + art style).
   - **Theme, Palette & Frame**: `theme_palette` (`auto` or preset in `assets/palettes.json`) + bundled frame (`classic_sar_gold`, `minimal_platinum`, `cyber_hud_frame`) or custom `fg`.
   - **Card Label Visibility (`label_mode`)**: `"page_only"` *(default: clean art-first card face; title/badge in HTML HUD)*, `"on_card"` *(engraved metallic bottom nameplate visible on HTML, WebP, and GIF)*, or `"hidden"`.
   - **Optional Polish**: `motion_motif` (`feathers_bubbles`, `cyber_stars`, `petals`, `embers`, `snowflakes`, or `none`) and `prop_fx` (**optional** — propose ONLY when a clear hero prop such as a staff, sword, skateboard, lantern, or instrument exists).

### Phase 2: Acquire Source Layers (`<workdir>/01_raw_layers/`)

Initialize `<workdir>/card_config.json` (adapted from [assets/card_config.example.json](./assets/card_config.example.json)) and `<workdir>/01_raw_layers/`.

- **Route 1 (Zero Image Gen)**: Copy the original image directly to `01_raw_layers/mid.<ext>`. Omit `bg`, `fg`, and `mid_depth` unless the user supplies them — `prepare_assets.py` auto-synthesizes the atmospheric backdrop and relief depth and applies `fallback_frame`.
- **Route 2 / Route 3**: Read [references/prompt-templates.md](./references/prompt-templates.md) before generating or handing off prompts.
  - **Track A (Built-in Image Gen)**: Generate requested layers (`3:4`, `>= 1024x1365`; native RGBA preferred, else `#00FF00` green or `#FF00FF` magenta when subject contains green). Remember: AI image-gen **redraws** pixels; use local `matte_layers.py` whenever pixel preservation is required.
  - **Track B (No Image Gen)**: Deliver tailored copy-ready prompts (1-image zero-gen, 2-image fast, 3-image auto-depth, or 4-image full) with exact target path `<workdir>/01_raw_layers/`, then **stop and wait** for files.

### Phase 3: Matte, Asset Lint & Fast Preview Gate (Before Slow Render)

Run matting, asset preparation, and the **~3-second 2-angle composite preview** BEFORE running the multi-minute 84-frame WebP/GIF encode:

```bash
python scripts/run_pipeline.py --workdir <workdir> --stage matte
python scripts/run_pipeline.py --workdir <workdir> --stage prepare
python scripts/run_pipeline.py --workdir <workdir> --stage preview
```

Inspect all pre-render gates and address any `LINT WARNING` printed by `prepare_assets.py`:
1. **`03_processed/cutout_check.png`**: Verify clean edges and zero green/magenta/white fringe. If `mid_mode == grabcut` on a busy photo shows artifacts, ask the user for a clean RGBA cutout or switch to Route 3 with consent.
2. **`03_processed/align_check.png` & `asset_lint`**: Check for `EDGE_CLIPPING_TOP/SIDE` (clipped ears, head, or props — `mid_fit: "auto"` switches non-3:4 inputs to `contain_safe` automatically, or adjust source headroom), face-box placement, and relief depth contour.
3. **`03_processed/preview_composite.png`**: Shows `0°` front + tilted holo + transparent checkerboard in ~3s. Confirm framing, palette, and `on_card` nameplate legibility (show preview to the user before full animation render when visual sign-off matters).

### Phase 3.5: Optional Surgical `prop_fx` ("1+1 Restraint Rule")

Only run when `prop_fx.enabled` is desired for a hero prop (never add outer card shells, background energy veins, hair UV wobble, or circular flashbangs):
1. Export labeled `0.05` UV coordinate rulers (`--crop U0 V0 U1 V1` optional):
   ```bash
   python scripts/run_pipeline.py --workdir <workdir> --stage prop-grid
   ```
2. Record tight `mask_polygons`, finger `exclude_polygons`, `start_uv`, and `tip_uv` in `card_config.json`, then rebuild mask and inspect `03_processed/prop_mask_qa.png` until zero bleed touches skin/face/hair:
   ```bash
   python scripts/run_pipeline.py --workdir <workdir> --stage prop-mask
   ```

### Phase 4: Full Build, Render & Separated Technical / Visual QA

```bash
python scripts/run_pipeline.py --workdir <workdir> --stage html
python scripts/run_pipeline.py --workdir <workdir> --stage render
python scripts/run_pipeline.py --workdir <workdir> --stage verify
```

Always separate **Technical Verification** from **Visual QA** in your delivery report:
- **Technical Verification (`scripts/verify_outputs.py`)**: Confirm exit code `0` and `"technical_status": "PASS"` (validates HTML WebGL2 bundle, WebP `690x960` / `84f` / `60ms` / `dispose=1, no_blend=1` / transparent corners, GIF `460x640` / `84f` / `60ms`).
- **Visual QA (Manual/Agent Inspection)**: Inspect `03_processed/qa_keyframes.png` (and `cutout_check.png` / `prop_mask_qa.png`) and explicitly report visual checks (`cutout edges`, `no ear/limb clipping`, `contrast/lighting`, `on_card text readability` if enabled) plus any `asset_lint_warnings` or items not visually checked.

### Phase 5: Deliver 3-File Bundle (`<workdir>/output/`)

State accurate per-format frame rates explicitly on delivery:
1. `holographic_card.html` — Offline single-file **`60 fps`** WebGL2 interactive 3D card (`5.2s` auto-orbit, `±30°/±19°` drag & gyro, `流畅`/`高清` toggle).
2. `holographic_card.webp` — `690x960` transparent RGBA animated WebP (**`84` frames @ `60 ms/frame` ≈ `16.7 fps`, `5.04s`**, zero-ghosting `dispose=1, no_blend=1`).
3. `holographic_card.gif` — `460x640` themed studio-backdrop GIF (**`84` frames @ `60 ms/frame` ≈ `16.7 fps`, `5.04s`**, 256-color Median Cut + Floyd–Steinberg).

## Bundled Files & References

- **Scripts** (`scripts/`): `check_env.py`, `run_pipeline.py`, `matte_layers.py`, `build_prop_mask.py`, `prepare_assets.py`, `build_html_card.py`, `render_card.py`, `verify_outputs.py`.
- **Assets** (`assets/`): `palettes.json`, `card_config.example.json`, `frames/{classic_sar_gold,minimal_platinum,cyber_hud_frame}.png`; pinned deps in [requirements.txt](./requirements.txt).
- **References** (load on demand):
  - [references/prompt-templates.md](./references/prompt-templates.md) — Route 2/3 prompt templates & cutout-vs-redraw rules.
  - [references/standard-spec.md](./references/standard-spec.md) — Optical/motion specs, `card_config.json` schema, lint thresholds, and QA invariants.
