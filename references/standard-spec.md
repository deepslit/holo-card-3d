# Standard Specification (`holo-card-3d` · v2.4)

Every execution must conform to these verified quality, optical, motion, and verification standards unless the user explicitly overrides a parameter.

---

## 1. Deliverables & Accurate Format Specs (`<workdir>/output/`)

Interactive HTML and pre-rendered animated WebP/GIF use **different frame rates** — always state both accurately:

| File | Resolution | Timing / Frame Rate | Key Technical Spec |
| :--- | :--- | :--- | :--- |
| `holographic_card.html` | Responsive (`900px` max default `流畅` / `1440px` `高清`) | **`60 fps`** target · **5.2s** auto-orbit loop | Single-file offline WebGL2 shader, `768×1024` embedded WebP/PNG textures (plus `propMask` when enabled), zero external CDN dependencies |
| `holographic_card.webp` | **`690 × 960`** RGBA | **`84` frames · `60 ms/frame` · `~16.7 fps` · `5.04s`** | `loop=0`, `quality=88`, independent keyframes (`kmin=1, kmax=1`), RIFF `ANMF` patched to `dispose=1, no_blend=1` (`0x03`) |
| `holographic_card.gif` | **`460 × 640`** RGB | **`84` frames · `60 ms/frame` · `~16.7 fps` · `5.04s`** | Studio backdrop composited, shared 256-color Median Cut palette + Floyd–Steinberg dithering, `loop=0` |

---

## 2. Intent-First 3-Route Architecture

| Route | Use When | `mid` Handling | `bg` Handling | `fg` / `mid_depth` |
| :--- | :--- | :--- | :--- | :--- |
| **Route 1: Keep Original (Zero Image Gen)** | User wants their exact uploaded image kept pixel-faithful | Local matting (`matte_layers.py`: `rgba`, `green`, `magenta`, `blue`, or `solid` cutout; complex/non-uniform full illustrations & photos default to full-bleed opaque `none` — never auto-running `grabcut`) | Auto-synthesized procedural backdrop (`bg_preset`, when subject has transparency) or preserved inside full-bleed `mid` (`none`) | Bundled `assets/frames/*.png` (`frame_tint: "auto"`) + `--auto-depth` |
| **Route 2: Hybrid** | Keep original subject + replace BG/frame (or keep BG + custom subject) | Local cutout for preserved layer | Custom generated/supplied or procedural | Custom or bundled |
| **Route 3: Reference-Based AI Redraw** | Style transfer, pose redesign, or full TCG re-illustration | AI-generated `mid.png` (Track A) or user-supplied (Track B) | AI-generated/supplied `bg.png` | Custom `fg.png` or bundled; optional `mid_depth.png` or `--auto-depth` |

> **Never confuse Local Pixel Cutout with AI Redraw**: Image-generation models always repaint pixels. Only `scripts/matte_layers.py` performs pixel-preserving local matting.

---

## 3. Motion & Tilt Bounds

- **WebP & GIF deterministic seamless cycle**:
  - `t = f_idx / num_frames`, `ang = 2π * t`
  - `yaw = 24.0° * sin(ang)`
  - `pitch = 11.5° * sin(2 * ang)`
  - `roll = 1.6° * sin(ang)`
  - `hover_y = -0.013 * H * sin(ang)`
- **HTML interactive WebGL2 (`60 fps`)**:
  - Auto-orbit matches `±24° yaw`, `±11.5° pitch`, `±1.6° roll` over **`5.2s`**.
  - Manual pointer drag & mobile gyroscope support up to **`±30° yaw` / `±19° pitch`** without frame separation or edge streaking.

---

## 4. Anti-Glitch, Optics & Optional "1+1" Polish Invariants

### Multi-Layer Optical Stack
- Normalized master canvas: `1200 × 1600` (`3:4`), card ratio `CW:CH = 3:4`, rounded corner `r = 0.045 * CW`, camera distance `D_cam = 3.8 * CW`.
- **Deep Background (`z = -0.082 * CW`)**: **`1.07×` UV overscan** prevents border clamping artifacts at wide tilt; radial/prism/cosmos SAR holographic spectrum gated by `masks.r`. When `01_raw_layers/bg.*` is omitted, `prepare_assets.py` synthesizes a rich deep nebula + celestial light-portal backdrop (`bg_source: "procedural_synthesized"`).
- **Quicksand Interlayer (`z = -0.058`, `-0.036 * CW`)**: 2 gravity-reactive silk pigment streams + ~300 3D oriented specular sequins + subject cast shadow (`0.44` attenuation).
- **Midground Subject (`z = [-0.012, +0.052] * CW`)**:
  - Smart aspect-ratio framing (`mid_fit: "auto"` automatically uses `"contain_safe"` with ~5% breathing margins whenever a cover-crop on a non-3:4 image would slice opaque foreground pixels).
  - Aligned via bbox-initialized ECC affine transform (or `--auto-depth` distance-transform + luminance relief when `mid_depth` is absent) + Voronoi edge extrapolation + bilateral filter + inner pillowing (`+0.07`).
  - Ray-marched via Alpha-Gated Perspective Relief Mapping (`18+4` steps CPU / `11+3` WebGL2), clamped-slope normals (`±0.58`), luminous Half-Lambert floor (`0.90 + 0.16 * HL`), metallic hardware specular, SAR ink micro-embossing, highlight roll-off above `0.85`.
- **Foreground Card Rim (`z = +0.005..+0.012 * CW`)**: Flush multi-slice bevel emboss so `±30°` shows zero gap between frame and card slab; brushed multi-slice card thickness edge (`0.036 * CW`). When `label_mode == "on_card"`, an engraved metallic bottom nameplate (`badge` + `title`) is baked onto `master_fg.png` prior to emboss extraction so it receives matching 3D bevel lighting across preview, HTML, WebP, and GIF.
- **4-Point Cross-Star Glints (`<= 15`)**: Peak-picked on frame hardware, subject metal, and background stars while strictly avoiding `face_box`; gently throttled when `prop_fx.enabled` is active.

### Optional FX #1 — Pixel-Exact Prop Light Sweep (`prop_fx`)
- Strictly optional (enable only when a clear hero prop exists on the character).
- `03_processed/prop_mask.png` (`1200×1600` grayscale `L` PNG, feather `1.6px`) rasterized from `prop_fx.mask_polygons`, subtracting `prop_fx.exclude_polygons`, intersected with `master_mid.png` alpha.
- Both WebGL2 and CPU renderers preserve dark ink lineart (`smoothstep(0.05, 0.26, luma + 0.12 * metal)`).
- Timing (once per cycle): directional gleam `cyc ∈ [0.18, 0.50]`, hairline tip ring (`~1.3px`) + needle star `cyc ∈ [0.43, 0.65]`.

### Optional FX #2 — 1 Analytical SDF Motion Motif (`motion_motif`)
- Supported presets (`kind`): `"feathers_bubbles"` (`0`), `"cyber_stars"` (`1`), `"petals"` (`2`), `"embers"` (`3`), `"snowflakes"` (`4`), or `"none"` (`-1`).
- Spawns `2` slow shapes on deep plane (`z = -0.044 * CW`) + `4` shapes on foreground plane (`z = +0.022 * CW`), faded to `14%` across `face_box`, padded `>= 14px` inside canvas edges to preserve zero corner alpha.

### WebP Zero-Ghosting Five-Point Rule
All five conditions are mandatory in `scripts/render_card.py`:
1. Hard alpha cutoff `< 0.015 -> 0.0` before premultiplied-to-straight un-multiplication (and foreground SDF particles clamped inside `[14..W-14, 14..H-14]`).
2. `background=(0, 0, 0, 0)`.
3. `minimize_size=False`.
4. `kmin=1, kmax=1` (independent keyframes).
5. Post-process every RIFF `ANMF` chunk byte `+23` (`(byte & ~0x03) | 0x03`) so `dispose=1, no_blend=1`.

---

## 5. Workspace & `card_config.json` Schema

```text
<workdir>/
├── card_config.json        # Card metadata, label_mode, palette, mid_fit, optional prop_fx & motion_motif
├── 01_raw_layers/          # Input images (mid required; bg, fg, mid_depth all optional)
├── 02_matted/              # Auto-generated RGBA cutouts, mid_on_black.png, matte_meta.json
├── 03_processed/           # 1200x1600 masters, depth maps, scene_meta.json, preview_composite.png, QA sheets
└── output/                 # Final 3 standard deliverables
```

Key `card_config.json` fields:
- `title`, `badge`, `subtitle`, `studio_bg_label`, `seed`.
- `label_mode`: `"page_only"` *(default: HTML HUD only, clean art-first card face)* | `"on_card"` *(engraved metallic bottom nameplate on card face + HTML HUD)* | `"hidden"` *(no HUD pill and no on-card nameplate)*.
- `theme_palette`: `"auto"` or palette key (`"celestial-gold"`, `"crimson-gold"`, `"sakura-rose"`, `"cyber-neon"`, `"silver-frost"`, `"emerald-jade"`, `"ink-gold"`) or custom RGB dict.
- `bg_preset`: Procedural zero-image-gen backdrop when `01_raw_layers/bg.*` is omitted: `"celestial_nebula"` *(default)* | `"stained_glass"` | `"cyber_grid"` | `"ink_wash"` | `"pastel_bokeh"` | `"obsidian_velvet"`.
- `holo_pattern`: `"starburst"` | `"prism_grid"` | `"cosmos_waves"` | `"cracked_ice"` | `"diagonal_foil"` | `"diamond_lattice"`.
- `material_preset`: Dual-end (WebGL2 + CPU WebP/GIF) craft finish: `"sar_quicksand"` *(default)* | `"acrylic_brick"` | `"cracked_ice"` | `"etched_foil"` | `"matte_velvet"` | `"clean_tcg"`.
- `lighting_preset`: Dual-end studio lighting rig: `"gallery_neutral"` *(default)* | `"dramatic_rim"` | `"golden_hour"` | `"moonlit_prism"` | `"soft_pastel"`.
- `fallback_frame`: `null` | `"classic_sar_gold"` | `"minimal_platinum"` | `"cyber_hud_frame"` | `"full_art_glass"` | `"baroque_arch"` | `"eastern_ink"` | `"y2k_polaroid"` | `"gothic_spire"`.
- `frame_tint`: `"auto"` *(default: luminance-preserving palette tint on built-in metallic frames; keeps custom `fg` untouched)* | `"original"` | `[r, g, b]`.
- `mid_fit`: `"auto"` *(default: switches non-3:4 images to `contain_safe` if cover would crop opaque subject)* | `"contain"` | `"cover"`.
- `face_box`: `"auto"` | `null` | `[x0, y0, x1, y1]`.
- `key_color`: `"auto"` *(auto-detects `rgba` / `green` / `magenta` / `blue` / `solid`; defaults to full-bleed opaque `"none"` on complex non-uniform backgrounds)* | `"rgba"` | `"green"` | `"magenta"` | `"blue"` | `"solid"` | `"none"` | `"grabcut"` *(opt-in only)*.
- `prop_fx`: `{"enabled": bool, "start_uv": [u, v], "tip_uv": [u, v], "tint": "auto" | [r,g,b], "gain": 0.90, "feather_sigma": 1.6, "exclude_skin_in_exclude_zones": true, "mask_polygons": [[[u,v], ...]], "exclude_polygons": [[[u,v], ...]]}`.
- `motion_motif`: `{"kind": "none"|"feathers_bubbles"|"cyber_stars"|"petals"|"embers"|"snowflakes", "color1": "auto"|[r,g,b], "color2": "auto"|[r,g,b]}` (or bare string).

---

## 6. Pre-Render Lint & Separated Technical vs Visual QA

### Automated Pre-Render Asset Lint (`prepare_assets.py` -> `scene_meta.json["asset_lint"]`)
Flags objective issues before the multi-minute 84-frame encode:
- `LOW_SUBJECT_COVERAGE` (`< 8%`) / `HIGH_SUBJECT_COVERAGE` (`> 90%` when `key_color != "none"`).
- `EDGE_CLIPPING_TOP` (`> 1.5%` opaque top border) / `EDGE_CLIPPING_SIDE` (`> 2.5%` opaque left/right border).
- `FRINGE_GREEN_SPILL` / `FRINGE_MAGENTA_SPILL` (`> 0.14` mean chroma excess in semi-transparent edge band).
- `CROWDED_FRAME` (`< 62%` open interior window in `fg`).
- `ASPECT_RATIO_MISMATCH` (`|ratio - 0.75| > 0.15`) & `GRABCUT_USED`.

### Fast Preview Gate (`--stage preview`)
- Renders `03_processed/preview_composite.png` (`0°` Studio + tilted Holo Studio + tilted Transparent Checkerboard) in ~2–4 seconds for composition, cutout, and `on_card` nameplate sign-off before `--stage render`.

### Separated Final Verification
1. **Technical Verification (`scripts/verify_outputs.py`)**: Must exit `0` with `"technical_status": "PASS"` (checks HTML structure/tokens, WebP `690×960`, `84f`, `60ms`, `flags=[[1,1]]`, `corners=[0,0,0,0]`, GIF `460×640`, `84f`, `60ms`).
2. **Visual QA (Human/Agent Inspection — Never Auto-Certified by Script)**:
   - `03_processed/cutout_check.png`: natural hair/accessory edges, zero fringe halo.
   - `03_processed/align_check.png` & `preview_composite.png`: intact ears/limbs/props, centered framing, legible `on_card` nameplate (if enabled).
   - `03_processed/prop_mask_qa.png` (when `prop_fx.enabled`): tight prop silhouette, zero finger/face bleed.
   - `03_processed/qa_keyframes.png`: rich contrast, zero wash-out, clean transparent checkerboard panel.
