# `holo-card-3d` · 3D Holo Quicksand Collector Card Skill (v2.2)

Turn any character illustration or reference image into a **3D holographic flowing-quicksand (流麻) SAR/UR collector card** with 11+3 perspective relief mapping, metallic embossed bevels, optional pixel-exact prop light sweeps, and analytical SDF motion motifs — exported as an offline **`60 fps` WebGL2 HTML**, **`~16.7 fps` zero-ghosting transparent WebP**, and **`~16.7 fps` GIF** bundle.

Universal **Agent Skill** (`SKILL.md` standard) & standalone CLI pipeline — compatible with **any agent harness or coding CLI** (Claude Code, Codex, Antigravity, Cursor, Windsurf, Gemini CLI, OpenCode, Cline, GitHub Copilot, Trae, etc.).

<p align="center">
  <img src="docs/demo_saintess.gif" width="300" alt="Deep-Sea Saintess · Celestial Staff Gleam & Starlight Feathers" />
  &nbsp;&nbsp;&nbsp;
  <img src="docs/demo_neko.gif" width="300" alt="Neko Y2K · Prism Skateboard Sweep & Cyber Star Shards" />
</p>

---

## Highlights (`v2.2`)

- **3-Route Intent-First Workflow (Zero-Image-Gen Ready)**:
  - **Route 1 (Zero Image Gen — Keep Original Pixels)**: Drop a single image into `01_raw_layers/mid.*` (native RGBA, chroma screen, solid light/dark studio, or local GrabCut) -> local matting + procedural atmospheric backdrop + bundled `1200×1600` collector frame + auto relief depth.
  - **Route 2 (Hybrid)**: Preserve original subject pixels while swapping background/frame (or vice versa).
  - **Route 3 (AI Redraw)**: Full style transfer or TCG re-illustration via built-in imagegen or copy-ready prompt templates (`references/prompt-templates.md`).
- **Pre-Render Asset Lint & Fast 3-Second Preview Gate**:
  - `prepare_assets.py` automatically detects aspect-ratio mismatches (with smart `mid_fit: "auto"` safe framing), top/side edge clipping (e.g., ears/weapons touching canvas edge), chroma fringe spill, and overcrowded frames.
  - `--stage preview` renders `03_processed/preview_composite.png` (`0°` + tilted holo + transparent checkerboard) in ~3 seconds so you approve framing and labels BEFORE the multi-minute 84-frame animation encode.
- **Controllable Card Labels (`label_mode`)**: Choose `"page_only"` *(clean art-first card face + HTML HUD)*, `"on_card"` *(engraved metallic bottom nameplate baked onto the card face for HTML, WebP, and GIF)*, or `"hidden"`.
- **Optional "1+1" Bespoke Polish (Zero Extra AI Image Gen)**:
  1. **Pixel-Exact Prop Light Sweep (`prop_fx`)**: `0.05` UV grid ruler (`--stage prop-grid`) + hand-excluding polygon mask (`prop_mask.png`) for a single directional gleam + hairline tip star.
  2. **Analytical SDF Motion Motif (`motion_motif`)**: Crisp dual-depth drifting shapes with face protection (`feathers_bubbles`, `cyber_stars`, `petals`, `embers`, `snowflakes`, or `none`).
- **Standardized 3-File Deliverable Bundle (`<workdir>/output/`)**:
  - `holographic_card.html` — Single-file offline **`60 fps`** WebGL2 interactive card (`5.2s` auto-orbit, `±30°/±19°` drag & gyro, `流畅`/`高清`, 3 studio modes).
  - `holographic_card.webp` — `690×960` transparent RGBA animated WebP (**`84f @ 60ms` ≈ `16.7 fps`, `5.04s`**, zero-ghosting `dispose=1, no_blend=1`).
  - `holographic_card.gif` — `460×640` themed studio-backdrop GIF (**`84f @ 60ms` ≈ `16.7 fps`, `5.04s`**, shared 256-color Median Cut + Floyd–Steinberg).

---

## Installation & Environment Check

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

## Quick Start (CLI Pipeline)

```bash
# 0. Verify Python & dependencies
python scripts/check_env.py --workdir ./my_card

# 1. Local pixel cutout (supports RGBA, green/magenta/blue chroma, solid studio backdrop, or GrabCut)
python scripts/run_pipeline.py --workdir ./my_card --stage matte

# 2. Align/synthesize depth & procedural bg (if bg omitted), run asset lint, build masks
python scripts/run_pipeline.py --workdir ./my_card --stage prepare

# 3. Fast ~3s 2-angle composite preview (inspect 03_processed/preview_composite.png BEFORE full render)
python scripts/run_pipeline.py --workdir ./my_card --stage preview

# 4. (Optional) Export 0.05 UV grid to trace prop_fx polygons in card_config.json
python scripts/run_pipeline.py --workdir ./my_card --stage prop-grid

# 5. Build 60fps HTML + render 84-frame (~16.7fps) WebP/GIF + verify technical checks
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
├── SKILL.md                  # Universal cross-harness agent instructions (v2.2)
├── README.md                 # Project overview & gallery
├── requirements.txt          # Verified Python dependency ranges
├── LICENSE                   # MIT License
├── agents/openai.yaml        # Optional Codex UI metadata
├── assets/
│   ├── card_config.example.json
│   ├── palettes.json
│   └── frames/               # Built-in 1200x1600 RGBA collector frames
├── docs/                     # README showcase GIFs
├── references/
│   ├── prompt-templates.md   # Route 2/3 layer generation prompts
│   └── standard-spec.md      # Frozen optical, motion, lint & QA invariants
└── scripts/
    ├── check_env.py          # Cross-platform interpreter, deps, disk & RAM preflight
    ├── run_pipeline.py
    ├── matte_layers.py       # RGBA / chroma / solid / GrabCut local pixel matting
    ├── build_prop_mask.py
    ├── prepare_assets.py     # Smart framing, procedural BG, on-card nameplate, asset lint
    ├── build_html_card.py
    ├── render_card.py        # Fast --preview-only & full 84-frame WebP/GIF renderer
    └── verify_outputs.py     # Separated technical PASS & visual QA checklist
```

---

## License

[MIT](LICENSE)
