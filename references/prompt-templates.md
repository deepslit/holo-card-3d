# Prompt Templates & Layer Acquisition Guide (`v2.4`)

Load this reference during **Phase 2** when running **Route 2 (Hybrid)** or **Route 3 (Reference-Based AI Redraw)**.

> **Important Distinction — Local Cutout vs. AI Redraw**
> - If the user wants to **keep their original image pixels unchanged** (**Route 1**), do **NOT** call an image generator to "remove the background" — image-gen models redraw characters and alter details. Copy the image straight to `01_raw_layers/mid.<ext>` and run `scripts/matte_layers.py` (`rgba` / `green` / `magenta` / `blue` / `solid` / `grabcut`).
> - Only use the prompts below when the user explicitly wants **AI generation or redrawing** of one or more layers.

---

## 1. Quick Configuration Menus

### Recommended Art & Rendering Methods (Route 3)
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
- `"cracked_ice"`, `"diagonal_foil"`, `"diamond_lattice"`: shattered-ice facets, classic diagonal foil bands, fine diamond lattice.

### Bundled Instant Frames (`assets/frames/`)
- `"classic_sar_gold"`: double-beveled champagne gold border with corner concave star medallions.
- `"minimal_platinum"`: brushed silver/platinum museum rim with corner precision tabs.
- `"cyber_hud_frame"`: dark titanium armor corners with cyan-glow micro-ruler bezel.
- `"full_art_glass"`, `"baroque_arch"`, `"eastern_ink"`, `"y2k_polaroid"`, `"gothic_spire"`: thin glass rim, baroque arch, Chinese ink border, Y2K instant-photo, gothic spire.

### Chroma-Key Colour — Pick by Contrast Before Writing Any Prompt
Look at the subject's colours first, then use the **same** key for `mid` and `fg`:
- No green on the subject → `#00FF00` green (default).
- Green hair / eyes / leaves / clothes → `#FF00FF` magenta.
- Both green and pink / magenta present → `#0000FF` blue.
Also tell the generator that the subject must not contain the key colour, and that petals, ribbons, sparks, and other effects must be **opaque solid shapes** (semi-transparent glows cannot be keyed cleanly).

---

## 2. Layer Prompt Templates (All 3:4 Portrait, `>= 1024x1365`)

Replace bracketed `[SUBJECT]`, `[STYLE]`, `[ART_METHOD]`, `[PALETTE]`, and `[THEME_MOTIFS]` with the confirmed details from Phase 1.

### Layer 1: Foreground Subject (`01_raw_layers/mid.png`) *(Route 3 Redraw Only)*
Compose it as **card key art, not a character sheet**: a knee-up or half-body crop in which the subject fills about 80% of the canvas height, the face is large and clearly readable, and the body turns toward the viewer with one hero prop. The lower body may run off the bottom edge (only top and side clipping is linted). Keep **~8% headroom and ~5% side margin**. A small full-body figure with empty margins looks weak on a card. If the head still ends up behind the frame, enable `breakout` (see §4) instead of regenerating.

- **Preferred (Native Transparent RGBA PNG)**:
  > Transform the character into a [THEME_STYLE] collector-card centerpiece portrait in [ART_METHOD]. Match facial identity and silhouette carefully. Dynamic three-quarter hero pose, ornate [PALETTE] attire and signature accessories, dramatic rim light. Isolated single character ONLY on a **100% transparent background (RGBA alpha=0)**. No card frame, no text, no scenery behind character, 3:4 portrait aspect ratio, **a knee-up or half-body key-art crop: the subject fills about 80% of the canvas height with a large, clearly readable face, the lower body may run off the bottom edge, ~8% headroom above ears/hair/hat and ~5% at the sides**.
- **Fallback A (Solid Chroma Green `#00FF00` — use when generator lacks true alpha, and subject has no bright green)**:
  > Same as above, ending with: Isolated single character ONLY centered on a completely flat, solid, unlit neon chroma-key green background (`#00FF00`), zero floor shadow or background glow on the green screen, crisp clean silhouette edges, no card frame, no text, 3:4 portrait aspect ratio, knee-up or half-body crop filling about 80% of the canvas height (the lower body may run off the bottom edge), ~8% headroom above ears/hair and ~5% margin on left and right sides.
- **Fallback C (Solid Chroma Blue `#0000FF` — use when the subject contains both green and pink / magenta)**: same wording as Fallback A with `blue chroma-key background (#0000FF)`.
- **Fallback B (Solid Chroma Magenta `#FF00FF` — use when subject contains bright green / emerald tones)**:
  > Same as above, ending with: Isolated single character ONLY centered on a completely flat, solid, unlit magenta chroma-key background (`#FF00FF`), zero floor shadow or magenta cast on the background, crisp clean silhouette edges, no card frame, no text, 3:4 portrait aspect ratio, knee-up or half-body crop filling about 80% of the canvas height (the lower body may run off the bottom edge), ~8% headroom above ears/hair and ~5% margin on left and right sides.

### Layer 2: Deep Atmospheric Background (`01_raw_layers/bg.png`) *(Optional — omit to auto-synthesize procedural backdrop)*
- **Full-Bleed Backdrop (No Character, No Frame)**:
  > Pure full-bleed 3:4 collector-card atmospheric background matching [THEME_STYLE] in [ART_METHOD], rich [PALETTE] depth and layered atmospheric glow. Feature a glowing focal emblem / light portal slightly above vertical center (`y ~ 25%–35%`). **NO character, NO figure, NO card border, NO frame, NO text or typography anywhere**, lush depth and empty central breathing room behind the foreground subject. **Keep it darker than the subject and in a clearly different dominant hue** (crimson subject → deep indigo / teal / near-black backdrop; pale or white subject → dark backdrop), otherwise the silhouette dissolves into the background.

### Layer 3: Ornate Perimeter Card Frame (`01_raw_layers/fg.png`) *(Optional — omit to use bundled `assets/frames/*.png`)*
- **Perimeter Border Only (Open Center Window)**:
  > High-craft 3:4 collectible TCG card outer border frame ONLY, matching [THEME_STYLE] and [PALETTE] metallic craftsmanship ([THEME_MOTIFS] motifs woven softly around corners and top/bottom crests). Keep corners rounded-card friendly; frame elements strictly confined to the **outermost 6%–14% perimeter band**. The entire central 75%+ interior window MUST be **100% empty [transparent / solid `#00FF00` / solid `#FF00FF` matching mid]**, with **zero text, numbers, attack stats, or character elements inside**. No crest, medallion, or ornament may reach further than 14% into the canvas — especially at the top centre, where the subject's head sits.

### Layer 4 (Optional): Subject Bas-Relief Depth Map (`01_raw_layers/mid_depth.png`)
*(Generate via image-to-image from `02_matted/mid_on_black.png`; omit to use local `--auto-depth`.)*
- **Grayscale Height Map Prompt**:
  > Convert this isolated character silhouette on pure black into a smooth, clean 8-bit grayscale bas-relief depth height map for 3D parallax displacement. Preserve the exact outer silhouette and `#000000` black background with zero gray halo outside the body. Pure black (`#000000`) background = 0; brighter white = closer parts (face, front hand/weapon, chest ornament brightest white; hair back and rear cape darker mid-gray). Smooth sculptural height gradients, **zero anime lineart shading, zero surface texture noise**.

---

## 3. Track B Handoff Checklist (When User Supplies Images)

Tell the user:
1. Exact folder path `<workdir>/01_raw_layers/`.
2. Four valid supply options:
   - **零生图单图模式（保留原图）**：仅放 1 张 `mid.png`（透明底、纯色底、绿/品红幕或普通图均可，本地自动抠图 + 程序氛围背景 + 内置卡框 + 自动浮雕）。
   - **极速 2 图（内置卡框 + 自动浮雕）**：`bg.png` + `mid.png`（套用内置 `classic_sar_gold` / `minimal_platinum` / `cyber_hud_frame` 卡框）。
   - **轻量 3 图（自动浮雕）**：`bg.png` + `mid.png` + `fg.png`（本地 `--auto-depth` 自动生成深度）。
   - **完整 4 图**：`bg.png` + `mid.png` + `fg.png` + `mid_depth.png`（立体浮雕精度最高）。
3. Format tips: `3:4` portrait preferred (`>= 1024x1365`); prefer a knee-up or half-body crop that fills ~80% of the height (the bottom may bleed off); leave ~8% headroom above ears/hair and ~5% side margin. Non-3:4 `mid` inputs are automatically fitted with safe margins (`mid_fit: "auto"`) so edges aren't accidentally cropped.

---

### Copy-Ready Single-Image Prompt (give this to users whose agent has no image tool)
Fill in the subject and style, swap the key colour by the contrast rule above, and tell the user to paste it into any image generator, then save the result as `<workdir>/01_raw_layers/mid.png`:

> 请直接生成一张图片。主体：[主体描述]。画风：[画风描述]。竖版 3:4 比例，只画一个主体，采用膝上或半身特写：主体占画面高度约 80%，脸要大而清晰，身体朝向镜头，下半身可以从画面底部出画；头顶留出约 8% 的空隙、左右约 5%。背景必须是完全均匀的纯色 [#00FF00 绿幕 / #FF00FF 洋红幕 / #0000FF 蓝幕]：没有渐变、阴影、地面、光晕或其他元素。主体身上不要出现背景色，花瓣、丝带、光效等都画成不透明的实体，边缘清晰干净。不要文字、数字、Logo、水印、边框或卡牌框。

---

## 4. Common Layer Pitfalls & Auto-Lint Checks
- **Clipped ears/limbs/staff**: `prepare_assets.py` automatically checks top/left/right border opacity (`EDGE_CLIPPING_TOP/SIDE`). If flagged, re-generate with wider headroom or adjust source padding BEFORE running `--stage render`.
- **Green clothes on green screen**: Switch `mid` / `fg` to `#FF00FF` magenta or native RGBA when the character wears green.
- **Subject hidden behind the frame** (`SUBJECT_UNDER_FRAME`): the frame covers part of the head, weapon, or hair. Set `"breakout": {"enabled": true}` in `card_config.json` and re-run `prepare` — the upper body is drawn over the frame (`"mode": "all"` for the whole subject, or paint `01_raw_layers/breakout_mask.png`). Prefer this to regenerating.
- **Subject and backdrop in the same hue**: nothing lints this — look at `preview_composite.png`; if the silhouette is hard to read, regenerate `bg` in a contrasting, darker hue or switch `bg_preset`.
- **Over-crowded `fg` frame**: Any ornament extending >18% into the middle triggers `CROWDED_FRAME` lint warnings.
- **Text inside AI art**: Forbid gibberish AI typography inside `fg`/`bg`; use `label_mode: "on_card"` in `card_config.json` when you want clean, readable title & rarity text on the card face.
