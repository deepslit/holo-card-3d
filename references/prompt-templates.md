# Prompt Templates & Layer Acquisition Guide

Load this reference during **Phase 2** to craft tailored English prompts for Track A (built-in image generation) or Track B (user copy-paste handoff).

---

## 1. Quick Configuration Menus (Phase 1 Choices)

### Recommended Art & Rendering Methods
- **2.5D 厚涂立绘 (Thick-Paint Luxury Anime)**: `2.5D semi-realistic anime illustration, rich impasto brushwork, jewel-like subsurface skin & fabric luminescence, crisp collector TCG key-art polish`
- **赛璐璐日系精修 (Cel-Shaded TCG Key Art)**: `modern Japanese TCG illustration, clean razor-sharp linework, luminous cel shading, dramatic rim lighting`
- **3D 潮玩/雕像质感 (Stylized 3D Figure)**: `stylized 3D collectible figure render, translucent resin & pearlescent lacquer, soft studio rim light`
- **新中式金箔工笔 (Chinese Ink & Gold Leaf)**: `modern Chinese gongbi & ink wash fusion, delicate mineral pigments, gold-leaf accent embroidery`

### `theme_palette` Options (`assets/palettes.json`)
- `"auto"` *(recommended default)*: extracts aura/mist tones from `bg` chromatic peaks and hardware metal tones from `fg`.
- Named presets: `"celestial-gold"`, `"crimson-gold"`, `"sakura-rose"`, `"cyber-neon"`, `"silver-frost"`, `"emerald-jade"`, `"ink-gold"`.

### `holo_pattern` Options
- `"starburst"` *(default)*: 24-ray radial starburst diffraction anchored to background focal center.
- `"prism_grid"`: crossed diamond foil facet grating.
- `"cosmos_waves"`: concentric nebula holographic interference ripples.

### Bundled Fallback Frames (`assets/frames/`)
- `"classic_sar_gold"`: double-beveled champagne gold border with corner concave star medallions.
- `"minimal_platinum"`: brushed silver/platinum museum rim with corner precision tabs.
- `"cyber_hud_frame"`: dark titanium armor corners with cyan-glow micro-ruler bezel.

---

## 2. Layer Prompt Templates (All 3:4 Portrait, `>= 1024x1365`)

Replace bracketed `[SUBJECT]`, `[STYLE]`, `[ART_METHOD]`, `[PALETTE]`, and `[THEME_MOTIFS]` with the confirmed details from Phase 1.

### Layer 1: Foreground Subject (`01_raw_layers/mid.png`)
Keep whole character + props centered with ~6% margin on all sides so nothing clips when tilting `±30°`.

- **Preferred (Native Transparent RGBA PNG)**:
  > Transform the character into a [THEME_STYLE] collector-card centerpiece portrait in [ART_METHOD]. Match facial identity and silhouette carefully. Dynamic three-quarter hero pose, ornate [PALETTE] attire and signature accessories, dramatic rim light. Isolated single character ONLY on a **100% transparent background (RGBA alpha=0)**. No card frame, no text, no scenery behind character, 3:4 portrait aspect ratio, ~6% margin around all limbs and props.
- **Fallback A (Solid Chroma Green `#00FF00` — use when generator lacks true alpha, and subject has no bright green)**:
  > Same as above, ending with: Isolated single character ONLY centered on a completely flat, solid, unlit neon chroma-key green background (`#00FF00`), zero floor shadow or background glow on the green screen, crisp clean silhouette edges, no card frame, no text, 3:4 portrait aspect ratio.
- **Fallback B (Solid Chroma Magenta `#FF00FF` — use when subject contains bright green / emerald tones)**:
  > Same as above, ending with: Isolated single character ONLY centered on a completely flat, solid, unlit magenta chroma-key background (`#FF00FF`), zero floor shadow or magenta cast on the background, crisp silhouette edges, no card frame, no text, 3:4 portrait aspect ratio.

### Layer 2: Deep Atmospheric Background (`01_raw_layers/bg.png`)
- **Full-Bleed Backdrop (No Character, No Frame)**:
  > Pure full-bleed 3:4 collector-card atmospheric background matching [THEME_STYLE] in [ART_METHOD], rich [PALETTE] depth and layered atmospheric glow. Feature a glowing focal emblem / light portal slightly above vertical center (`y ~ 25%–35%`). **NO character, NO figure, NO card border, NO frame, NO text or typography anywhere**, lush depth and empty central breathing room behind the foreground subject.

### Layer 3: Ornate Perimeter Card Frame (`01_raw_layers/fg.png`) *(Skip if using a bundled `assets/frames/*.png`)*
- **Perimeter Border Only (Open Center Window)**:
  > High-craft 3:4 collectible TCG card outer border frame ONLY, matching [THEME_STYLE] and [PALETTE] metallic craftsmanship ([THEME_MOTIFS] motifs woven softly around corners and top/bottom crests). Keep corners rounded-card friendly; frame elements strictly confined to the **outermost 6%–14% perimeter band**. The entire central 75%+ interior window MUST be **100% empty [transparent / solid `#00FF00` / solid `#FF00FF` matching mid]**, with **zero text, numbers, attack stats, or character elements inside**.

### Layer 4 (Optional): Subject Bas-Relief Depth Map (`01_raw_layers/mid_depth.png`)
*(Generate via image-to-image from `02_matted/mid_on_black.png`; omit if using local `--auto-depth`.)*
- **Grayscale Height Map Prompt**:
  > Convert this isolated character silhouette on pure black into a smooth, clean 8-bit grayscale bas-relief depth height map for 3D parallax displacement. Preserve the exact outer silhouette and `#000000` black background with zero gray halo outside the body. Pure black (`#000000`) background = 0; brighter white = closer parts (face, front hand/weapon, chest ornament brightest white; hair back and rear cape darker mid-gray). Smooth sculptural height gradients, **zero anime lineart shading, zero surface texture noise**.

---

## 3. Track B Handoff Checklist (When User Supplies Images)

Tell the user:
1. Exact folder path `<workdir>/01_raw_layers/`.
2. Three valid supply options:
   - **完整 4 图**：`bg.png` + `mid.png` + `fg.png` + `mid_depth.png`（立体浮雕精度最高）
   - **轻量 3 图（自动浮雕）**：`bg.png` + `mid.png` + `fg.png`（本地 `--auto-depth` 自动生成深度）
   - **极速 2 图（内置卡框 + 自动浮雕）**：`bg.png` + `mid.png`（直接套用内置 `classic_sar_gold` / `minimal_platinum` / `cyber_hud_frame` 卡框）
3. Format tips: `3:4` portrait preferred (`>= 1024x1365`); `mid`/`fg` prefer transparent PNG or pure `#00FF00` / `#FF00FF` solid backdrop.

---

## 4. Common Layer Pitfalls
- **Clipped limbs/staff**: Leave ~6% headroom/margin in `mid`; clipped edges become visible when card tilts to `±24°..±30°`.
- **Green clothes on green screen**: Always switch `mid` / `fg` to `#FF00FF` magenta or native RGBA when the character wears green.
- **Over-crowded `fg` frame**: Any ornament extending >18% into the middle risks hiding the face or chest detail.
- **Text inside AI art**: AI card frames often invent gibberish runes/numbers; explicitly forbid all typography and stats.
