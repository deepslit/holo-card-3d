# Standard Specification (`holo-card-3d` · v2.1)

Every execution must conform to these verified quality, optical, motion, and verification standards unless the user explicitly overrides a parameter.

---

## 1. Deliverables & Verified Targets (`<workdir>/output/`)

| File | Resolution | Timing / Cycle | Key Technical Spec |
| :--- | :--- | :--- | :--- |
| `holographic_card.html` | Responsive (`900px` max default `流畅` / `1440px` `高清`) | **5.2s** auto-orbit loop | Single-file offline WebGL2 shader, `768×1024` embedded WebP/PNG textures (plus `propMask` when enabled), zero external CDN dependencies |
| `holographic_card.webp` | **`690 × 960`** RGBA | **`84` frames · `60 ms/frame` · `5.04s`** (`~16.67 fps`) | `loop=0`, `quality=88`, independent keyframes (`kmin=1, kmax=1`), RIFF `ANMF` patched to `dispose=1, no_blend=1` (`0x03`) |
| `holographic_card.gif` | **`460 × 640`** RGB | **`84` frames · `60 ms/frame` · `5.04s`** | Studio backdrop composited, shared 256-color Median Cut palette + Floyd–Steinberg dithering, `loop=0` |

---

## 2. Motion & Tilt Bounds

- **WebP & GIF deterministic seamless cycle**:
  - `t = f_idx / num_frames`, `ang = 2π * t`
  - `yaw = 24.0° * sin(ang)`
  - `pitch = 11.5° * sin(2 * ang)`
  - `roll = 1.6° * sin(ang)`
  - `hover_y = -0.013 * H * sin(ang)`
- **HTML interactive WebGL2**:
  - Auto-orbit matches `±24° yaw`, `±11.5° pitch`, `±1.6° roll` over **`5.2s`**.
  - Manual pointer drag & mobile gyroscope support up to **`±30° yaw` / `±19° pitch`** without frame separation or edge streaking.

---

## 3. Anti-Glitch, Optics & `v2.1` ("1+1") Polish Invariants

### Multi-Layer Optical Stack
- Normalized master canvas: `1200 × 1600` (`3:4`), card ratio `CW:CH = 3:4`, rounded corner `r = 0.045 * CW`, camera distance `D_cam = 3.8 * CW`.
- **Deep Background (`z = -0.082 * CW`)**: **`1.07×` UV overscan** prevents border clamping artifacts at wide tilt; radial/prism/cosmos SAR holographic spectrum gated by `masks.r`.
- **Quicksand Interlayer (`z = -0.058`, `-0.036 * CW`)**: 2 gravity-reactive silk pigment streams + ~300 3D oriented specular sequins + subject cast shadow (`0.44` attenuation).
- **Midground Subject (`z = [-0.012, +0.052] * CW`)**:
  - Aligned via bbox-initialized ECC affine transform (or `--auto-depth` distance-transform + luminance relief when `mid_depth` is absent) + Voronoi edge extrapolation + bilateral filter + inner pillowing (`+0.07`).
  - Ray-marched via Alpha-Gated Perspective Relief Mapping (`18+4` steps CPU / `11+3` WebGL2), clamped-slope normals (`±0.58`), luminous Half-Lambert floor (`0.90 + 0.16 * HL`), metallic hardware specular, SAR ink micro-embossing, highlight roll-off above `0.85`.
- **Foreground Card Rim (`z = +0.005..+0.012 * CW`)**: Flush multi-slice bevel emboss so `±30°` shows zero gap between frame and card slab; brushed multi-slice card thickness edge (`0.036 * CW`).
- **4-Point Cross-Star Glints (`<= 15`)**: Peak-picked on frame hardware, subject metal, and background stars while strictly avoiding `face_box`; gently throttled when `prop_fx.enabled` is active so the hero prop glint leads visual focus.

### v2.1 Effect #1 — Pixel-Exact Prop Light Sweep (`prop_fx`)
- `03_processed/prop_mask.png` (`1200×1600` grayscale `L` PNG, feather `1.6px` AA edge) is rasterized from `prop_fx.mask_polygons`, subtracts `prop_fx.exclude_polygons` (optionally skin-only within hand boxes so dark prop surfaces between fingers stay intact), and intersects `master_mid.png` alpha.
- Both WebGL2 and CPU renderers preserve dark ink lineart (`smoothstep(0.05, 0.26, luma + 0.12 * metal)`) so contours stay sharp inside the gleaming prop.
- **Timing (strictly once per `2π` / `5.04s–5.2s` cycle)**:
  - Directional prism/specular gleam travels `start_uv -> tip_uv` across `cyc ∈ [0.18, 0.50]` strictly inside `prop_mask`.
  - Single hairline expanding ring (`~1.3px` stroke) + razor diffraction cross star fires at `tip_uv` (`z = +0.018 * CW`) across `cyc ∈ [0.43, 0.65]`.

### v2.1 Effect #2 — 1 Analytical SDF Motion Motif (`motion_motif`)
- Supported presets (`kind`): `"feathers_bubbles"` (`0`), `"cyber_stars"` (`1`), `"petals"` (`2`), `"embers"` (`3`), `"snowflakes"` (`4`), or `"none"` (`-1`).
- Spawns `2` slow drifting shapes on deep plane (`z = -0.044 * CW`) + `4` shapes on foreground plane (`z = +0.022 * CW`), gently faded to `14%` opacity when crossing `face_box`, safely padded at least `14px` inside canvas edges (preserving zero corner alpha), and alpha-over composited cleanly in both WebGL2 and WebP/GIF pipelines.
- When `motion_motif.kind == "none"`, classic `v1.0` floating bokeh particles remain active.

### WebP Zero-Ghosting Five-Point Rule
All five conditions are mandatory in `scripts/render_card.py`:
1. Hard alpha cutoff `< 0.015 -> 0.0` before premultiplied-to-straight un-multiplication (no 1-bit haze across transparent canvas, and foreground SDF particles clamped inside margin `[14..W-14, 14..H-14]`).
2. `background=(0, 0, 0, 0)`.
3. `minimize_size=False`.
4. `kmin=1, kmax=1` (every frame encoded as independent keyframe).
5. Post-process every RIFF `ANMF` chunk byte `+23` (`(byte & ~0x03) | 0x03`) so `dispose=1, no_blend=1`.

---

## 4. Workspace & `card_config.json` Schema

```text
<workdir>/
├── card_config.json        # Card title, badge, palette, prop_fx, motion_motif
├── 01_raw_layers/          # Input images (mid, bg, optional fg, mid_depth, prop_mask)
├── 02_matted/              # Auto-generated RGBA cutouts + mid_on_black.png
├── 03_processed/           # 1200x1600 masters, depth maps, prop_mask.png, scene_meta.json, QA images
└── output/                 # Final 3 standard deliverables
```

Key `card_config.json` fields:
- `title`, `badge`, `subtitle`, `studio_bg_label`, `seed`.
- `theme_palette`: `"auto"` or palette key (`"celestial-gold"`, `"crimson-gold"`, `"sakura-rose"`, `"cyber-neon"`, `"silver-frost"`, `"emerald-jade"`, `"ink-gold"`) or custom RGB dict.
- `holo_pattern`: `"starburst"` | `"prism_grid"` | `"cosmos_waves"`.
- `fallback_frame`: `null` | `"classic_sar_gold"` | `"minimal_platinum"` | `"cyber_hud_frame"`.
- `face_box`: `"auto"` | `null` | `[x0, y0, x1, y1]`.
- `key_color`: `"auto"` | `"rgba"` | `"green"` | `"magenta"` | `"blue"`.
- `prop_fx`: `{"enabled": bool, "start_uv": [u, v], "tip_uv": [u, v], "tint": "auto" | [r,g,b], "gain": 0.90, "feather_sigma": 1.6, "exclude_skin_in_exclude_zones": true, "mask_polygons": [[[u,v], ...]], "exclude_polygons": [[[u,v], ...]]}`.
- `motion_motif`: `{"kind": "none"|"feathers_bubbles"|"cyber_stars"|"petals"|"embers"|"snowflakes", "color1": "auto"|[r,g,b], "color2": "auto"|[r,g,b]}` (or bare string).

---

## 5. Mandatory QA Gates

1. `03_processed/cutout_check.png`: Clean checkerboard cutout edges; no green/magenta fringes.
2. `03_processed/align_check.png`: Depth silhouette aligns with `master_mid.png`; `face_box` protects human faces.
3. `03_processed/prop_mask_qa.png` (when `prop_fx.enabled`): Cyan prop mask tightly hugs ONLY the hero prop with zero face/finger/hair bleed.
4. `03_processed/qa_keyframes.png`: Clean `f0`, prop gleam frame, peak hairline tip flare + SDF motif frame, opposite tilt, loop end, and checkerboard transparent WebP panel with rich contrast.
5. `scripts/verify_outputs.py`: Exits `0` with `"status": "PASS"` across HTML, WebP (`690×960`, `flags=[[1,1]]`, `corners=[0,0,0,0]`), and GIF (`460×640`).
