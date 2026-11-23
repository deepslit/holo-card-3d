# `holo-card-3d` · 3D Holo Quicksand Collector Card Skill (v2.3)

**English** | **[简体中文](README.zh-CN.md)**

Turn any character illustration or reference image into a **3D holographic flowing-quicksand (流麻) SAR/UR collector card** with 11+3 perspective relief mapping, 8 SDF metallic bevel frames with dynamic palette tinting, 6 craft materials × 5 lighting rigs × 6 holo patterns (face-protected top lamination), optional pixel-exact prop light sweeps, and analytical SDF motion motifs — exported as an offline **`60 fps` WebGL2 HTML (with live Craft Studio & offline GPU WebP/GIF exporter)**, **`~16.7 fps` zero-ghosting transparent WebP**, and **`~16.7 fps` GIF** bundle.

Universal **Agent Skill** (`SKILL.md` standard) & standalone CLI pipeline — works with **any agent harness or coding CLI** (Claude Code, Codex, Antigravity, Cursor, Windsurf, Gemini CLI, OpenCode, Cline, GitHub Copilot, Trae, etc.).

<p align="center">
  <img src="docs/demo_saintess.gif" width="300" alt="Deep-Sea Saintess · Celestial Staff Gleam & Starlight Feathers" />
  &nbsp;&nbsp;&nbsp;
  <img src="docs/demo_neko.gif" width="300" alt="Neko Y2K · Prism Skateboard Sweep & Cyber Star Shards" />
</p>

### Interactive Museum-Vitrine Web UI & Live Craft Studio (`v2.3`)

<p align="center">
  <img src="docs/demo_web_ui.webp" width="760" alt="Museum-Vitrine Web UI · Live Craft Switching (Cracked Ice / Prism Grid / Acrylic Brick), Dark & Light Gallery Themes, Zen Mode & Offline GPU Export" />
  <br />
  <sub>20 fps seamless preview · <a href="docs/demo_web_ui.mp4">Download 30 fps HD MP4 (1040×660)</a></sub>
</p>

---

## ⚡ Quick Start: Just Copy This Prompt to Your Agent

Attach your character/reference image and send this one-liner to **any coding agent or skill-enabled harness**:

```text
Download and install the skill from https://github.com/deepslit/holo-card-3d, then use it to turn this image into a 3D holo quicksand collector card.
```

> - **Already installed?** Just attach an image and say: `Use holo-card-3d to turn this image into a 3D holo quicksand card.`
> - **Users in China (Gitee Mirror):** Replace the URL with `https://gitee.com/deepslit/holo-card-3d` for faster cloning.

---

## Highlights (`v2.3`)

- **Redesigned Museum-Vitrine Web UI + 100% Offline In-Browser GPU Exporter**:
  - Minimal monochrome dark/light adaptive gallery showcase (`Dark Velvet`, `Pitch Obsidian`, `Gallery White`), architectural corner framing, single-row frosted dock, `H` Zen mode, double-click reset, zero-GC 60fps loop, and `visibilitychange` auto-pause.
  - **Live Craft Popover (`工艺`)**: Switch all **6 materials**, **5 lighting rigs**, and **6 holo patterns** in real time at 60fps without re-running Python.
  - **One-Click Offline GPU Export (Non-Overwriting)**: Export your tuned combination directly from the standalone HTML as a `690×960` zero-ghosting transparent animated WebP or `460×640` 256-color Floyd–Steinberg GIF in seconds via WebGL2 FBO + pure-JS RIFF/GIF89a encoders (zero CDN, zero local server, auto-suffixed filenames so original files are never overwritten).
- **6 Craft Materials × 5 Lighting Rigs × 6 Holo Patterns (WebGL2 & CPU 1:1 Synced)**:
  - Face-protected top-coat lamination (`face_box` keeps skin/eyes 100% crisp even on full-art cards):
  - **Materials (`material_preset`)**: `sar_quicksand` (classic SAR holo + silk sand), `acrylic_brick` (1.85× thick crystal acrylic slab + inner prism bevel + front glitter), `cracked_ice` (Voronoi angular crystal shards), `etched_foil` (carved guilloche topographic foil ridges), `matte_velvet` (soft-touch matte paper + 2.55× spot-UV hot foil), `clean_tcg` (pure classic rainbow foil, zero quicksand).
  - **Lighting (`lighting_preset`)**: `gallery_neutral`, `dramatic_rim`, `golden_hour`, `moonlit_prism`, `soft_pastel`.
  - **Holo Patterns (`holo_pattern`)**: `starburst`, `prism_grid`, `cosmos_waves`, `cracked_ice`, `diagonal_foil`, `diamond_lattice`.
- **8 Built-in SDF Collector Frames + Dynamic Metallic Tinting (`frame_tint`)**:
  - `classic_sar_gold`, `minimal_platinum`, `cyber_hud_frame`, `full_art_glass` (ultra-thin acrylic slab edge), `baroque_arch` (Art Nouveau arch), `eastern_ink` (begonia-corner key-fret scroll), `y2k_polaroid` (chrome filmstrip & star studs), `gothic_spire` (pointed cathedral lancet arch).
  - `frame_tint: "auto"` applies luminance-preserving metallic palette tinting to built-in frames (custom `fg` layers remain untouched).
- **6 Pure-Procedural Zero-Image-Gen Backdrops (`bg_preset`)**:
  - `celestial_nebula`, `stained_glass`, `cyber_grid`, `ink_wash`, `pastel_bokeh`, `obsidian_velvet` — synthesized at `1200×1600` with zero AI image-gen.
- **3-Route Intent-First Workflow (Zero-Image-Gen Ready)**:
  - **Route 1 (Zero Image Gen — Keep Original Pixels)**: Drop a single image into `01_raw_layers/mid.*`. Native RGBA, chroma screens (`green`/`magenta`/`blue`), and uniform `solid` backdrops extract cleanly onto procedural `bg_preset` backdrops; **complex full illustrations & photos default straight to full-bleed opaque passthrough (`none`)** (never auto-running GrabCut) so 100% of original art pixels stay crisp under relief depth, frame, and top-coat craft lamination.
  - **Route 2 (Hybrid)**: Preserve original subject pixels while swapping background/frame (or vice versa).
  - **Route 3 (AI Redraw)**: Full style transfer or TCG re-illustration via built-in imagegen or copy-ready prompt templates (`references/prompt-templates.md`).
- **Pre-Render Asset Lint, 3-Second Preview Gate & Optional "1+1" Polish**:
  - Smart `mid_fit: "auto"` framing, edge-clipping/fringe/frame lint checks, `--stage preview` (~3s 2-angle preview), controllable `label_mode` (`page_only` / `on_card` / `hidden`), optional pixel-exact `prop_fx` light sweep, and analytical SDF `motion_motif` (`feathers_bubbles`, `cyber_stars`, `petals`, `embers`, `snowflakes`).
- **Standardized 3-File Deliverable Bundle (`<workdir>/output/`)**:
  - `holographic_card.html` — Single-file offline **`60 fps`** WebGL2 interactive card + Live Craft Studio + Offline GPU Exporter.
  - `holographic_card.webp` — `690×960` transparent RGBA animated WebP (**`84f @ 60ms` ≈ `16.7 fps`, `5.04s`**, zero-ghosting `dispose=1, no_blend=1`).
  - `holographic_card.gif` — `460×640` themed studio-backdrop GIF (**`84f @ 60ms` ≈ `16.7 fps`, `5.04s`**, shared 256-color Median Cut + Floyd–Steinberg).

---

## Manual Installation & Environment Check

### 1. Check Environment & Install Dependencies
```bash
# Pure-stdlib preflight check (detects Windows Store stubs, Python version, packages, disk & RAM)
python scripts/check_env.py

# Install verified dependency ranges
pip install -r requirements.txt
```

### 2. Install as an Agent Skill (Any Harness)
`holo-card-3d` follows the open [`SKILL.md`](SKILL.md) convention with zero harness-specific lock-in, so it works across **any AI coding agent or CLI harness** that supports `SKILL.md` or shell execution.

Clone this repository into your harness's skills directory (or symlink/junction to one shared copy):

```bash
# Universal cross-agent project skills directory (Antigravity, Codex, Gemini CLI, OpenCode, Copilot, etc.)
git clone https://github.com/deepslit/holo-card-3d.git .agents/skills/holo-card-3d

# Or global / tool-specific skills directories (examples):
git clone https://github.com/deepslit/holo-card-3d.git ~/.claude/skills/holo-card-3d   # Claude Code
git clone https://github.com/deepslit/holo-card-3d.git ~/.codex/skills/holo-card-3d    # Codex
git clone https://github.com/deepslit/holo-card-3d.git ~/.cursor/skills/holo-card-3d   # Cursor
```

> **China Mirror & Any-Agent Fallback**: A Gitee mirror auto-syncs at `https://gitee.com/deepslit/holo-card-3d`. Even if your agent does not auto-discover `SKILL.md` folders, clone the repo anywhere and tell the agent to read `SKILL.md` and run `scripts/run_pipeline.py`.

---

## Standalone CLI Pipeline

```bash
# 0. Verify Python & dependencies
python scripts/check_env.py --workdir ./my_card

# 1. Local matting (RGBA / chroma / solid cutout; full-bleed 'none' passthrough on complex art)
python scripts/run_pipeline.py --workdir ./my_card --stage matte

# 2. Align/synthesize depth, procedural bg_preset & dynamic frame_tint, run asset lint, build masks
python scripts/run_pipeline.py --workdir ./my_card --stage prepare

# 3. Fast ~3s 2-angle composite preview (inspect 03_processed/preview_composite.png BEFORE full render)
python scripts/run_pipeline.py --workdir ./my_card --stage preview

# 4. (Optional) Export 0.05 UV grid to trace prop_fx polygons in card_config.json
python scripts/run_pipeline.py --workdir ./my_card --stage prop-grid

# 5. Build 60fps HTML (with live craft studio & offline exporter) + render WebP/GIF + verify specs
python scripts/run_pipeline.py --workdir ./my_card --stage html
python scripts/run_pipeline.py --workdir ./my_card --stage render
python scripts/run_pipeline.py --workdir ./my_card --stage verify
```

Or run the entire pipeline in one command after placing `card_config.json` and `01_raw_layers/`:
```bash
python scripts/run_pipeline.py --workdir ./my_card --stage all
```

---

## Repository Layout

```text
holo-card-3d/
├── SKILL.md                  # Universal cross-harness agent instructions (v2.3)
├── README.md                 # Project overview & gallery (English)
├── README.zh-CN.md           # Project overview & gallery (简体中文)
├── requirements.txt          # Verified Python dependency ranges
├── LICENSE                   # MIT License
├── agents/openai.yaml        # Optional Codex UI metadata
├── assets/
│   ├── card_config.example.json
│   ├── palettes.json
│   └── frames/               # 8 built-in 1200x1600 SDF RGBA collector frames
├── docs/                     # README showcase GIFs (cards & Web UI demo)
├── references/
│   ├── prompt-templates.md   # Route 2/3 layer generation prompts
│   └── standard-spec.md      # Frozen optical, preset, motion, lint & QA invariants
└── scripts/
    ├── check_env.py          # Cross-platform interpreter, deps, disk & RAM preflight
    ├── run_pipeline.py
    ├── generate_builtin_frames.py # Procedural SDF generator for all 8 collector frames
    ├── matte_layers.py       # RGBA / chroma / solid matting & full-bleed 'none' passthrough
    ├── build_prop_mask.py
    ├── prepare_assets.py     # Smart framing, 6 procedural BGs, dynamic frame tint, asset lint
    ├── build_html_card.py    # 60fps WebGL2 gallery UI, live craft popover & offline WebP/GIF export
    ├── render_card.py        # Fast --preview-only & full 84-frame CPU WebP/GIF renderer
    └── verify_outputs.py     # Separated technical PASS & visual QA checklist
```

---

## License

[MIT](LICENSE)
