"""Stage 3A: Align or synthesize relief depth, resolve theme palette, masks, and scene_meta.json."""
import argparse
import json
import math
import sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from build_prop_mask import build_prop_mask_for_workdir

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SKILL_ROOT = Path(__file__).resolve().parent.parent
PALETTES_PATH = SKILL_ROOT / "assets" / "palettes.json"
BUILTIN_FRAMES_DIR = SKILL_ROOT / "assets" / "frames"
IMG_EXTS = (".png", ".webp", ".jpg", ".jpeg")
MASTER_W, MASTER_H = 1200, 1600


def find_layer(folder: Path, stems: list[str]) -> Path | None:
    if not folder.exists():
        return None
    files = {p.name.lower(): p for p in folder.iterdir() if p.is_file()}
    for stem in stems:
        for ext in IMG_EXTS:
            cand = files.get(f"{stem.lower()}{ext}")
            if cand is not None:
                return cand
    return None


def resolve_fallback_frame(fallback_name: str | None) -> Path:
    name = (fallback_name or "classic_sar_gold").strip()
    if name.lower().endswith(".png"):
        name = name[:-4]
    cand = BUILTIN_FRAMES_DIR / f"{name}.png"
    default = BUILTIN_FRAMES_DIR / "classic_sar_gold.png"
    if not cand.exists() and not default.exists():
        # Lite distribution ships without frame PNGs: synthesize all built-in frames once.
        print(f"Built-in frames missing in {BUILTIN_FRAMES_DIR}; generating them once (~1 min)...")
        import generate_builtin_frames
        generate_builtin_frames.main()
    if not cand.exists():
        cand = default
    return cand


def build_breakout_mask(cfg: dict, workdir: Path, mid_rgba: np.ndarray, fg_rgba: np.ndarray) -> tuple[np.ndarray | None, dict]:
    """Break-the-frame mask (mid UV space): where 1, the subject is drawn OVER the frame instead of under it.

    Modes: "top" (default) pops out everything above `until_v` (head, arms, weapon) while the lower
    body stays tucked behind the frame; "all" pops out the whole subject. A user-painted
    01_raw_layers/breakout_mask.png (white = over the frame) overrides both.
    """
    bo_cfg = cfg.get("breakout") or {}
    if isinstance(bo_cfg, bool):
        bo_cfg = {"enabled": bo_cfg}
    mid_a = mid_rgba[..., 3].astype(np.float32) / 255.0
    fg_a = fg_rgba[..., 3].astype(np.float32) / 255.0
    covered_pct = round(float((mid_a * fg_a).sum() / max(float(mid_a.sum()), 1.0)) * 100.0, 2)
    # Full-bleed artwork (mid_mode "none") fills the card; the frame resting on its edge is expected, not a defect.
    info = {"enabled": bool(bo_cfg.get("enabled")), "subject_under_frame_pct": covered_pct, "mid_full_bleed": bool(float(mid_a.mean()) > 0.97)}
    if not info["enabled"]:
        return None, info
    h, w = mid_a.shape
    custom = find_layer(workdir / "01_raw_layers", ["breakout_mask"])
    if custom is not None:
        mask = np.array(Image.open(custom).convert("L").resize((w, h), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0
        info["mode"] = "custom"
    else:
        mode = str(bo_cfg.get("mode", "top")).lower()
        if mode == "all":
            mask = np.ones((h, w), dtype=np.float32)
        else:
            mode = "top"
            until_v = float(bo_cfg.get("until_v", 0.62))
            feather = max(float(bo_cfg.get("feather", 0.05)), 1e-3)
            v = (np.arange(h, dtype=np.float32) + 0.5) / h
            ramp = 1.0 - np.clip((v - until_v) / feather, 0.0, 1.0)
            mask = np.repeat((ramp * ramp * (3.0 - 2.0 * ramp))[:, None], w, axis=1)
            info["until_v"] = until_v
        info["mode"] = mode
    info["popped_out_pct"] = round(float((mid_a * fg_a * mask).sum() / max(float(mid_a.sum()), 1.0)) * 100.0, 2)
    return np.clip(mask * 255.0, 0, 255).astype(np.uint8), info


def resize_exact_3_4(img: Image.Image, mode: str = "cover") -> Image.Image:
    w, h = img.size
    if (w, h) == (MASTER_W, MASTER_H):
        return img
    target_ratio = MASTER_W / MASTER_H
    src_ratio = w / h
    if abs(src_ratio - target_ratio) > 0.015 and mode == "cover":
        if src_ratio > target_ratio:
            nw = int(round(h * target_ratio))
            x0 = (w - nw) // 2
            img = img.crop((x0, 0, x0 + nw, h))
        else:
            nh = int(round(w / target_ratio))
            y0 = (h - nh) // 2
            img = img.crop((0, y0, w, y0 + nh))
    return img.resize((MASTER_W, MASTER_H), Image.Resampling.LANCZOS)


def resize_mid_smart(img: Image.Image, fit_mode: str = "auto") -> tuple[Image.Image, str]:
    """Fit subject RGBA onto 1200x1600 without accidentally slicing limbs/ears on non-3:4 inputs."""
    img = img.convert("RGBA")
    w, h = img.size
    if (w, h) == (MASTER_W, MASTER_H):
        return img, "exact"

    target_ratio = MASTER_W / MASTER_H
    src_ratio = w / h
    ratio_diff = abs(src_ratio - target_ratio) / target_ratio

    mode = fit_mode.lower().strip()
    if mode == "auto":
        if ratio_diff <= 0.025:
            return img.resize((MASTER_W, MASTER_H), Image.Resampling.LANCZOS), "exact_ratio"
        arr = np.array(img)
        alpha = arr[..., 3]
        would_clip = False
        if src_ratio > target_ratio:
            nw = int(round(h * target_ratio))
            x0 = (w - nw) // 2
            if np.any(alpha[:, :x0] > 40) or np.any(alpha[:, x0 + nw :] > 40):
                would_clip = True
        else:
            nh = int(round(w / target_ratio))
            y0 = (h - nh) // 2
            if np.any(alpha[:y0, :] > 40) or np.any(alpha[y0 + nh :, :] > 40):
                would_clip = True
        mode = "contain" if would_clip else "cover"

    if mode == "cover":
        return resize_exact_3_4(img, "cover"), "cover"

    # Contain mode: preserve 100% of subject pixels with clean ~5% breathing margin inside frame rim
    arr = np.array(img)
    bottom_touches = float(np.mean(arr[-max(2, h // 80) :, :, 3] > 60)) > 0.08
    pad_x = int(MASTER_W * 0.05)
    pad_top = int(MASTER_H * 0.055)
    pad_bot = int(MASTER_H * (0.02 if bottom_touches else 0.055))
    avail_w = MASTER_W - 2 * pad_x
    avail_h = MASTER_H - pad_top - pad_bot
    scale = min(avail_w / float(w), avail_h / float(h))
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (MASTER_W, MASTER_H), (0, 0, 0, 0))
    ox = (MASTER_W - nw) // 2
    oy = (MASTER_H - pad_bot - nh) if bottom_touches else (pad_top + (avail_h - nh) // 2)
    canvas.paste(resized, (ox, oy))
    return canvas, "contain_safe"


VALID_BG_PRESETS = (
    "celestial_nebula",
    "stained_glass",
    "cyber_grid",
    "ink_wash",
    "pastel_bokeh",
    "obsidian_velvet",
)
VALID_HOLO_PATTERNS = (
    "starburst",
    "prism_grid",
    "cosmos_waves",
    "cracked_ice",
    "diagonal_foil",
    "diamond_lattice",
)
VALID_MATERIAL_PRESETS = (
    "sar_quicksand",
    "acrylic_brick",
    "cracked_ice",
    "etched_foil",
    "matte_velvet",
    "clean_tcg",
)
VALID_LIGHTING_PRESETS = (
    "gallery_neutral",
    "dramatic_rim",
    "golden_hour",
    "moonlit_prism",
    "soft_pastel",
)


def apply_frame_tint(
    fg_pil: Image.Image,
    is_builtin_frame: bool,
    frame_stem: str,
    frame_tint,
    palette: dict,
) -> Image.Image:
    """Apply luminance-preserving metallic tint to built-in frames (or explicit user tint)."""
    mode = "auto" if frame_tint is None else frame_tint
    if isinstance(mode, str):
        mode_s = mode.lower().strip()
        if mode_s in ("original", "none", "off"):
            return fg_pil
        if mode_s == "auto" and not is_builtin_frame:
            return fg_pil
        # Preserve signature look of classic_sar_gold unless user asks for palette/custom tint
        if mode_s == "auto" and frame_stem == "classic_sar_gold":
            return fg_pil

    arr = np.array(fg_pil.convert("RGBA"), dtype=np.float32) / 255.0
    rgb = arr[..., :3]
    alpha = arr[..., 3:4]

    if isinstance(mode, (list, tuple)) and len(mode) == 3:
        tint_col = np.clip(np.array([float(c) for c in mode], dtype=np.float32), 0.05, 1.0)
        strength = 0.85
    else:
        metal = np.array(palette.get("metal_tint", [0.95, 0.88, 0.65]), dtype=np.float32)
        spec = np.array(palette.get("edge_spec", [1.0, 0.94, 0.78]), dtype=np.float32)
        aura = np.array(palette.get("aura", [0.35, 0.75, 0.98]), dtype=np.float32)
        sand1 = np.array(palette.get("sand1", [0.95, 0.85, 0.55]), dtype=np.float32)

        if frame_stem == "cyber_hud_frame":
            # Keep dark forged armor intact; retint only the bright cyan neon strips/ticks
            cyan_mask = np.clip((rgb[..., 2] - rgb[..., 0]) * 2.2, 0.0, 1.0)[..., None]
            neon_target = np.clip(0.55 * sand1 + 0.45 * aura, 0.15, 1.0)
            luma = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2])[..., None]
            tinted_neon = np.clip(neon_target[None, None, :] * (0.55 + 0.75 * luma), 0.0, 1.0)
            out_rgb = rgb * (1.0 - cyan_mask * 0.88) + tinted_neon * (cyan_mask * 0.88)
            out = np.concatenate([np.clip(out_rgb, 0.0, 1.0), alpha], axis=-1)
            return Image.fromarray((out * 255.0).astype(np.uint8), "RGBA")

        if frame_stem == "full_art_glass":
            tint_col = 0.35 * spec + 0.65 * np.array([0.92, 0.96, 1.0], dtype=np.float32)
            strength = 0.42
        elif frame_stem == "gothic_spire":
            # Forged dark metal retains moody low-key sheen with subtle palette alloy tint
            tint_col = np.clip(0.55 * metal + 0.45 * np.array([0.62, 0.65, 0.74], dtype=np.float32), 0.15, 1.0)
            strength = 0.72
        else:
            tint_col = np.clip(0.72 * metal + 0.28 * spec, 0.15, 1.0)
            strength = 0.82

    luma = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2])[..., None]
    # Preserve bright specular whites while rich midtones take the metallic alloy hue
    spec_keep = np.clip((luma - 0.76) / 0.24, 0.0, 1.0) ** 1.4
    alloy = np.clip(luma * (tint_col[None, None, :] / max(float(np.mean(tint_col)), 0.35)), 0.0, 1.0)
    recolored = alloy * (1.0 - 0.65 * spec_keep) + np.clip(luma * (0.5 + 0.5 * tint_col[None, None, :]), 0.0, 1.0) * (0.65 * spec_keep)
    out_rgb = rgb * (1.0 - strength) + recolored * strength
    out = np.concatenate([np.clip(out_rgb, 0.0, 1.0), alpha], axis=-1)
    return Image.fromarray((out * 255.0).astype(np.uint8), "RGBA")


def _resolve_procedural_colors(mid_rgba: np.ndarray, theme_palette, palettes_db: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return harmonious (aura, accent, secondary) RGB float32 vectors in [0, 1]."""
    if isinstance(theme_palette, dict) and "aura" in theme_palette:
        aura = np.array(theme_palette["aura"], dtype=np.float32)
        accent = np.array(theme_palette.get("sand1", [0.95, 0.84, 0.55]), dtype=np.float32)
        sec = np.array(theme_palette.get("sand2", [0.58, 0.86, 1.00]), dtype=np.float32)
        return aura, accent, sec
    if isinstance(theme_palette, str) and theme_palette in palettes_db:
        pal = palettes_db[theme_palette]
        return (
            np.array(pal["aura"], dtype=np.float32),
            np.array(pal["sand1"], dtype=np.float32),
            np.array(pal["sand2"], dtype=np.float32),
        )
    mid_rgb = mid_rgba[..., :3]
    mid_a = mid_rgba[..., 3] > 128
    hsv = cv2.cvtColor(mid_rgb, cv2.COLOR_RGB2HSV)
    mh = hsv[..., 0].astype(np.float32) * 2.0
    ms = hsv[..., 1].astype(np.float32) / 255.0
    mv = hsv[..., 2].astype(np.float32) / 255.0
    skin = ((mh < 38.0) | (mh > 335.0)) & (ms < 0.48) & (mv > 0.55)
    sel = mid_a & (~skin) & (ms > 0.22) & (mv > 0.22)
    if np.sum(sel) > 300:
        rad = np.radians(mh[sel])
        dom_hue = float(np.degrees(np.arctan2(np.median(np.sin(rad)), np.median(np.cos(rad)))) % 360.0)
        dom_sat = float(np.clip(np.median(ms[sel]), 0.35, 0.72))
    else:
        dom_hue, dom_sat = 218.0, 0.58
    aura = np.array(_hsv_to_rgb01(dom_hue, dom_sat, 0.85), dtype=np.float32)
    accent = np.array(_hsv_to_rgb01(dom_hue + 38.0, float(np.clip(dom_sat * 0.68, 0.25, 0.65)), 0.96), dtype=np.float32)
    sec = np.array(_hsv_to_rgb01(dom_hue - 42.0, float(np.clip(dom_sat * 0.72, 0.25, 0.70)), 0.92), dtype=np.float32)
    return aura, accent, sec


def synthesize_procedural_bg(
    mid_rgba: np.ndarray,
    theme_palette,
    palettes_db: dict,
    seed: int = 20261121,
    bg_preset: str = "celestial_nebula",
) -> Image.Image:
    """Generate a high-craft procedural 1200x1600 collector-card backdrop for zero-image-gen workflows."""
    preset = str(bg_preset or "celestial_nebula").lower().strip()
    if preset not in VALID_BG_PRESETS:
        preset = "celestial_nebula"

    aura, accent, sec = _resolve_procedural_colors(mid_rgba, theme_palette, palettes_db)
    yy, xx = np.mgrid[0:MASTER_H, 0:MASTER_W].astype(np.float32)
    u = xx / float(MASTER_W)
    v = yy / float(MASTER_H)
    rng = np.random.default_rng(int(seed) + 771)

    if preset == "stained_glass":
        # Cathedral stained-glass Voronoi facets + radiant rose apex + god-ray light shafts
        gw, gh = 300, 400
        gy, gx = np.mgrid[0:gh, 0:gw].astype(np.float32)
        gu = gx / float(gw)
        gv = gy / float(gh)
        n_cells = 46
        pts_u = rng.uniform(0.02, 0.98, n_cells).astype(np.float32)
        pts_v = rng.uniform(0.02, 0.98, n_cells).astype(np.float32)
        # Anchor symmetrical cathedral crown points near upper portal
        for k in range(8):
            a = k * math.pi / 4.0
            pts_u[k] = 0.50 + 0.22 * math.cos(a)
            pts_v[k] = 0.28 + 0.16 * math.sin(a)
        d1 = np.full((gh, gw), 1e9, dtype=np.float32)
        d2 = np.full((gh, gw), 1e9, dtype=np.float32)
        cid = np.zeros((gh, gw), dtype=np.int32)
        for idx in range(n_cells):
            dist = np.hypot((gu - pts_u[idx]) * 0.75, gv - pts_v[idx])
            m1 = dist < d1
            d2 = np.where(m1, d1, np.minimum(d2, dist))
            d1 = np.where(m1, dist, d1)
            cid = np.where(m1, idx, cid)
        lead_edge = 1.0 - np.clip((d2 - d1) / 0.0085, 0.0, 1.0)
        pal_cells = np.zeros((n_cells, 3), dtype=np.float32)
        for idx in range(n_cells):
            t_m = float(rng.uniform(0.0, 1.0))
            base_c = aura * (1.0 - t_m) + (accent if idx % 3 == 0 else sec) * t_m
            bright = float(rng.uniform(0.24, 0.62))
            pal_cells[idx] = base_c * bright + np.array([0.04, 0.05, 0.08], dtype=np.float32)
        glass_lo = pal_cells[cid] * (1.0 - 0.78 * lead_edge[..., None])
        glass = cv2.resize(glass_lo, (MASTER_W, MASTER_H), interpolation=cv2.INTER_LINEAR)

        dx, dy = u - 0.50, (v - 0.26) * (MASTER_H / float(MASTER_W))
        rad = np.hypot(dx, dy)
        ang = np.arctan2(dy, dx)
        rose_glow = np.exp(-(rad ** 2) / (2.0 * 0.32 ** 2))
        rays = np.power(0.5 + 0.5 * np.cos(ang * 16.0), 3.0) * np.exp(-rad * 1.65)
        bg = glass * (0.72 + 0.72 * rose_glow[..., None]) + accent * (rays[..., None] * 0.24 + rose_glow[..., None] * 0.16)
        edge_r = np.hypot((u - 0.5) * 1.12, (v - 0.48) * 1.08)
        vig = 1.0 - 0.52 * np.clip((edge_r - 0.36) / 0.54, 0.0, 1.0) ** 1.6
        bg = np.clip(bg * vig[..., None], 0.0, 1.0)
        return Image.fromarray((bg * 255.0).astype(np.uint8), "RGB")

    if preset == "cyber_grid":
        # Retro-futuristic cyber perspective grid + neon horizon glow + clean scanlines
        hor_y = 0.58
        sky_t = np.clip(v / hor_y, 0.0, 1.0)
        sky_top = np.array([0.025, 0.028, 0.062], dtype=np.float32) + aura * 0.08
        sky_hor = np.array([0.05, 0.04, 0.10], dtype=np.float32) + aura * 0.34 + sec * 0.18
        bg = sky_top * (1.0 - sky_t[..., None]) + sky_hor * (sky_t[..., None] ** 1.8)

        # Cyber sun / digital portal ring above horizon
        dx_s, dy_s = u - 0.50, (v - 0.34) * (MASTER_H / float(MASTER_W))
        r_s = np.hypot(dx_s, dy_s)
        sun_disc = (1.0 - np.clip((r_s - 0.22) / 0.008, 0.0, 1.0)) * np.where(v > 0.30, (np.sin(v * 210.0) > -0.35).astype(np.float32), 1.0)
        sun_col = accent * (1.0 - np.clip(v * 1.4, 0.0, 1.0))[..., None] + sec * np.clip(v * 1.4, 0.0, 1.0)[..., None]
        bg += sun_col * (sun_disc[..., None] * 0.46 + np.exp(-(r_s ** 2) / (2.0 * 0.26 ** 2))[..., None] * 0.24)

        # Perspective floor below horizon
        floor_mask = v > hor_y
        dv = np.maximum(v - hor_y, 0.004)
        z_persp = 0.24 / dv
        x_persp = (u - 0.50) * z_persp * 2.6
        gx_line = np.exp(-((np.abs(np.mod(x_persp + 0.5, 1.0) - 0.5)) / 0.032) ** 2)
        gz_line = np.exp(-((np.abs(np.mod(z_persp * 1.6 + 0.5, 1.0) - 0.5)) / 0.042) ** 2)
        grid_str = np.maximum(gx_line, gz_line) * np.clip((v - hor_y) / 0.06, 0.0, 1.0) * np.exp(-dv * 1.2)
        floor_base = np.array([0.02, 0.024, 0.052], dtype=np.float32) + aura * (0.12 * np.exp(-dv * 4.0))[..., None]
        floor_col = floor_base + (0.65 * aura + 0.35 * accent) * grid_str[..., None] * 0.58
        bg = np.where(floor_mask[..., None], floor_col, bg)

        # Crisp neon horizon laser line + subtle CRT scanlines
        hor_glow = np.exp(-((v - hor_y) / 0.016) ** 2)
        bg += (0.55 * accent + 0.45 * aura) * hor_glow[..., None] * 0.55
        scan = 0.94 + 0.06 * np.sin(yy * 1.5708)
        edge_r = np.hypot((u - 0.5) * 1.15, (v - 0.48) * 1.08)
        vig = 1.0 - 0.44 * np.clip((edge_r - 0.38) / 0.54, 0.0, 1.0) ** 1.6
        bg = np.clip(bg * scan[..., None] * vig[..., None], 0.0, 1.0)
        return Image.fromarray((bg * 255.0).astype(np.uint8), "RGB")

    if preset == "ink_wash":
        # Eastern rice-paper wash + misty layered mountains + fine scattered gold leaf flecks
        paper_n = cv2.resize(rng.normal(0.0, 1.0, (MASTER_H // 4, MASTER_W // 4)).astype(np.float32), (MASTER_W, MASTER_H))
        paper_grain = 0.97 + 0.03 * np.clip(paper_n, -1.5, 1.5)
        warm_paper = np.array([0.92, 0.90, 0.85], dtype=np.float32) * 0.86 + aura * 0.10
        sky_fade = np.array([0.82, 0.84, 0.84], dtype=np.float32) * 0.84 + sec * 0.12
        bg = (sky_fade * (1.0 - v[..., None]) + warm_paper * v[..., None]) * paper_grain[..., None]

        # Subtle glowing moon/sun seal in upper third
        r_moon = np.hypot((u - 0.52), (v - 0.25) * (MASTER_H / float(MASTER_W)))
        moon = np.exp(-(r_moon ** 2) / (2.0 * 0.16 ** 2))
        bg = np.clip(bg + accent * moon[..., None] * 0.16, 0.0, 1.0)

        # Three atmospheric misty sumi-ink mountain ridges
        ink_col = np.array([0.11, 0.14, 0.18], dtype=np.float32) * 0.78 + aura * 0.16
        layers = [
            (0.56, 0.075, 4.2, 0.6, 0.24, 0.12),
            (0.68, 0.085, 5.8, 2.1, 0.42, 0.10),
            (0.80, 0.070, 7.1, 4.0, 0.64, 0.08),
        ]
        for base_y, amp, freq, ph, alpha_m, mist in layers:
            ridge = base_y + amp * np.sin(u * freq + ph) + amp * 0.45 * np.cos(u * freq * 2.1 - ph * 0.7)
            m_mask = np.clip((v - ridge) / 0.014, 0.0, 1.0)
            mist_fade = np.exp(-np.maximum(v - ridge, 0.0) / max(mist, 0.02))
            eff = m_mask * alpha_m * (0.35 + 0.65 * mist_fade)
            bg = bg * (1.0 - eff[..., None]) + ink_col[None, None, :] * eff[..., None]

        # Delicate scattered gold-leaf flecks (洒金宣纸)
        gold_c = np.clip(accent * 0.75 + np.array([0.96, 0.82, 0.42], dtype=np.float32) * 0.25, 0.0, 1.0)
        for _ in range(75):
            fx = int(rng.uniform(0.05, 0.95) * MASTER_W)
            fy = int(rng.uniform(0.05, 0.93) * MASTER_H)
            fw = int(rng.uniform(2, 8))
            fh = int(rng.uniform(2, 7))
            y0, y1 = max(0, fy - fh), min(MASTER_H, fy + fh)
            x0, x1 = max(0, fx - fw), min(MASTER_W, fx + fw)
            br = float(rng.uniform(0.18, 0.46))
            bg[y0:y1, x0:x1] = bg[y0:y1, x0:x1] * (1.0 - br) + gold_c * br

        edge_r = np.hypot((u - 0.5) * 1.12, (v - 0.50) * 1.08)
        vig = 1.0 - 0.16 * np.clip((edge_r - 0.42) / 0.50, 0.0, 1.0) ** 1.6
        bg = np.clip(bg * vig[..., None], 0.0, 1.0)
        return Image.fromarray((bg * 255.0).astype(np.uint8), "RGB")

    if preset == "pastel_bokeh":
        # Airy light pastel gradient + silky dreamy bokeh orbs (ideal for kawaii / sakura / bright art)
        p_top = np.clip(0.68 + 0.28 * aura, 0.0, 1.0)
        p_mid = np.clip(0.76 + 0.22 * accent, 0.0, 1.0)
        p_bot = np.clip(0.72 + 0.26 * sec, 0.0, 1.0)
        t1 = np.clip(v * 1.6, 0.0, 1.0)[..., None]
        t2 = np.clip((v - 0.45) * 1.8, 0.0, 1.0)[..., None]
        bg = (p_top * (1.0 - t1) + p_mid * t1) * (1.0 - t2) + p_bot * t2

        # Soft pearlescent light ribbons
        rib = 0.5 + 0.5 * np.sin(u * 4.8 + v * 3.6 + 0.5) * np.cos(v * 5.2 - u * 2.1)
        bg = np.clip(bg + np.array([1.0, 0.99, 1.0], dtype=np.float32) * (np.power(rib, 2.8)[..., None] * 0.12), 0.0, 1.0)

        # Large dreamy translucent bokeh discs
        for _ in range(42):
            bx = int(rng.uniform(0.04, 0.96) * MASTER_W)
            by = int(rng.uniform(0.04, 0.96) * MASTER_H)
            br_r = int(rng.uniform(22, 82))
            alpha_b = float(rng.uniform(0.08, 0.22))
            col_b = np.array([1.0, 1.0, 1.0], dtype=np.float32) if rng.random() < 0.6 else np.clip(0.65 + 0.35 * accent, 0.0, 1.0)
            y0, y1 = max(0, by - br_r - 6), min(MASTER_H, by + br_r + 7)
            x0, x1 = max(0, bx - br_r - 6), min(MASTER_W, bx + br_r + 7)
            py_b, px_b = np.mgrid[y0:y1, x0:x1].astype(np.float32)
            dist = np.hypot(px_b - bx, py_b - by)
            disc = 1.0 - np.clip((dist - br_r * 0.86) / (br_r * 0.22), 0.0, 1.0)
            ring = np.exp(-((dist - br_r * 0.84) / max(br_r * 0.09, 2.0)) ** 2) * 0.45
            w_b = np.clip(disc * 0.68 + ring, 0.0, 1.0)[..., None] * alpha_b
            bg[y0:y1, x0:x1] = bg[y0:y1, x0:x1] * (1.0 - w_b) + col_b * w_b

        edge_r = np.hypot((u - 0.5) * 1.10, (v - 0.48) * 1.06)
        vig = 1.0 - 0.12 * np.clip((edge_r - 0.44) / 0.50, 0.0, 1.0) ** 1.5
        bg = np.clip(bg * vig[..., None], 0.0, 1.0)
        return Image.fromarray((bg * 255.0).astype(np.uint8), "RGB")

    if preset == "obsidian_velvet":
        # Ultra-clean luxury dark charcoal studio backdrop + subtle overhead cone + fine film grain
        dx_c, dy_c = (u - 0.50) * 1.12, (v - 0.32) * 1.15
        cone = np.exp(-(dx_c ** 2 + dy_c ** 2) / (2.0 * 0.36 ** 2))
        deep_ch = np.array([0.042, 0.045, 0.056], dtype=np.float32) + aura * 0.035
        hi_ch = np.array([0.135, 0.142, 0.168], dtype=np.float32) + aura * 0.095 + accent * 0.035
        bg = deep_ch * (1.0 - cone[..., None]) + hi_ch * cone[..., None]

        # Subtle studio velvet micro-grain
        grain = cv2.resize(rng.normal(0.0, 1.0, (MASTER_H // 2, MASTER_W // 2)).astype(np.float32), (MASTER_W, MASTER_H))
        bg += np.clip(grain, -1.5, 1.5)[..., None] * 0.008
        edge_r = np.hypot((u - 0.5) * 1.16, (v - 0.48) * 1.08)
        vig = 1.0 - 0.56 * np.clip((edge_r - 0.32) / 0.56, 0.0, 1.0) ** 1.65
        bg = np.clip(bg * vig[..., None], 0.0, 1.0)
        return Image.fromarray((bg * 255.0).astype(np.uint8), "RGB")

    # Default: celestial_nebula (deep studio + celestial light portal + nebula ribbons + stardust)
    deep_base = aura * 0.14 + np.array([0.025, 0.032, 0.055], dtype=np.float32)
    top_tint = aura * 0.28 + np.array([0.03, 0.04, 0.07], dtype=np.float32)
    bg = deep_base * (0.45 + 0.55 * v[..., None]) + top_tint * np.power(1.0 - v[..., None], 1.6)

    cx, cy = 0.50, 0.29
    dx = u - cx
    dy = (v - cy) * (MASTER_H / float(MASTER_W))
    rad = np.hypot(dx, dy)
    ang = np.arctan2(dy, dx)

    portal = np.exp(-(rad ** 2) / (2.0 * 0.34 ** 2))
    core_halo = np.exp(-(rad ** 2) / (2.0 * 0.14 ** 2))
    rays = 0.5 + 0.5 * np.cos(ang * 12.0 + 0.4) * np.cos(ang * 5.0 - 0.7)
    rays_env = np.exp(-rad * 2.1) * np.power(rays, 2.2)

    bg += aura * (portal[..., None] * 0.42 + rays_env[..., None] * 0.16)
    bg += accent * (core_halo[..., None] * 0.34 + rays_env[..., None] * 0.10)

    wave1 = np.sin(u * 5.2 + v * 3.1 + 0.6) * np.cos(v * 4.4 - u * 2.3)
    wave2 = np.cos(u * 7.8 - v * 4.9 + 1.4) * np.sin(v * 6.2 + u * 2.7)
    nebula = np.clip(0.5 + 0.5 * (0.6 * wave1 + 0.4 * wave2), 0.0, 1.0)
    nebula = np.power(nebula, 2.6) * np.exp(-((v - 0.48) ** 2) / (2.0 * 0.36 ** 2))
    bg += (0.65 * aura + 0.35 * accent) * nebula[..., None] * 0.20

    for _ in range(95):
        sx = int(rng.uniform(0.06, 0.94) * MASTER_W)
        sy = int(rng.uniform(0.05, 0.92) * MASTER_H)
        sr = int(rng.uniform(2, 16))
        br = float(rng.uniform(0.08, 0.32))
        col = accent if rng.random() < 0.45 else aura
        y0, y1 = max(0, sy - sr * 3), min(MASTER_H, sy + sr * 3 + 1)
        x0, x1 = max(0, sx - sr * 3), min(MASTER_W, sx + sr * 3 + 1)
        py, px = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        d2 = (px - sx) ** 2 + (py - sy) ** 2
        spot = np.exp(-d2 / (2.0 * max(sr * 0.65, 1.2) ** 2))
        bg[y0:y1, x0:x1] += spot[..., None] * (col * 0.75 + 0.25) * br

    edge_r = np.hypot((u - 0.5) * 1.15, (v - 0.48) * 1.08)
    vig = 1.0 - 0.46 * np.clip((edge_r - 0.38) / 0.52, 0.0, 1.0) ** 1.6
    bg = np.clip(bg * vig[..., None], 0.0, 1.0)
    return Image.fromarray((bg * 255.0).astype(np.uint8), "RGB")


def _load_cjk_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Locate a crisp CJK + Latin bold font across Windows, macOS, and Linux."""
    candidates = [
        # Windows
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        # Linux
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def bake_on_card_nameplate(fg_pil: Image.Image, title: str, badge: str, palette: dict) -> Image.Image:
    """Composite a sleek metallic bottom collector nameplate onto master_fg when label_mode == 'on_card'."""
    out = fg_pil.convert("RGBA").copy()
    layer = Image.new("RGBA", (MASTER_W, MASTER_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    edge_spec = [int(np.clip(c * 255, 0, 255)) for c in palette.get("edge_spec", [0.98, 0.90, 0.70])]
    edge_base = [int(np.clip(c * 255, 0, 255)) for c in palette.get("edge_base", [0.55, 0.45, 0.30])]
    metal_hi = tuple(edge_spec) + (245,)
    metal_lo = tuple(edge_base) + (235,)
    plate_fill = (12, 16, 28, 224)

    title_str = (title or "").strip()
    badge_str = (badge or "").strip()
    if not title_str and not badge_str:
        return out

    font_title = _load_cjk_font(34)
    font_badge = _load_cjk_font(22)

    # Measure layout dynamically to fit nicely inside the lower frame margin
    t_bbox = draw.textbbox((0, 0), title_str, font=font_title) if title_str else (0, 0, 0, 0)
    b_bbox = draw.textbbox((0, 0), badge_str, font=font_badge) if badge_str else (0, 0, 0, 0)
    t_w, t_h = t_bbox[2] - t_bbox[0], t_bbox[3] - t_bbox[1]
    b_w, b_h = b_bbox[2] - b_bbox[0], b_bbox[3] - b_bbox[1]

    chip_pad_x = 18
    chip_w = (b_w + chip_pad_x * 2) if badge_str else 0
    gap = 20 if (badge_str and title_str) else 0
    content_w = chip_w + gap + t_w
    plate_w = int(np.clip(content_w + 88, 360, MASTER_W - 220))
    plate_h = 78
    x0 = (MASTER_W - plate_w) // 2
    y0 = int(MASTER_H * 0.872)
    x1, y1 = x0 + plate_w, y0 + plate_h

    # Chamfered octagonal collector nameplate
    ch = 16
    poly = [
        (x0 + ch, y0), (x1 - ch, y0),
        (x1, y0 + ch), (x1, y1 - ch),
        (x1 - ch, y1), (x0 + ch, y1),
        (x0, y1 - ch), (x0, y0 + ch),
    ]
    draw.polygon(poly, fill=plate_fill)
    draw.line(poly + [poly[0]], fill=metal_lo, width=5)
    inner = [
        (x0 + ch + 3, y0 + 3), (x1 - ch - 3, y0 + 3),
        (x1 - 3, y0 + ch + 3), (x1 - 3, y1 - ch - 3),
        (x1 - ch - 3, y1 - 3), (x0 + ch + 3, y1 - 3),
        (x0 + 3, y1 - ch - 3), (x0 + 3, y0 + ch + 3),
    ]
    draw.line(inner + [inner[0]], fill=metal_hi, width=2)

    cx = x0 + (plate_w - content_w) // 2
    cy = (y0 + y1) // 2
    if badge_str:
        chip_h = 38
        cy0 = cy - chip_h // 2
        draw.rounded_rectangle(
            [cx, cy0, cx + chip_w, cy0 + chip_h],
            radius=10,
            fill=tuple(edge_base) + (210,),
            outline=metal_hi,
            width=2,
        )
        bx = cx + chip_pad_x - b_bbox[0]
        by = cy - b_h // 2 - b_bbox[1]
        draw.text((bx, by), badge_str, font=font_badge, fill=(255, 250, 236, 255))
        cx += chip_w + gap

    if title_str:
        tx = cx - t_bbox[0]
        ty = cy - t_h // 2 - t_bbox[1]
        draw.text((tx + 2, ty + 2), title_str, font=font_title, fill=(0, 0, 0, 170))
        draw.text((tx, ty), title_str, font=font_title, fill=tuple(edge_spec) + (255,))

    return Image.alpha_composite(out, layer)


def run_asset_lint(
    mid_rgba: np.ndarray,
    fg_rgba: np.ndarray,
    orig_mid_size: tuple[int, int],
    mid_fit_applied: str,
    matte_meta: dict,
    bg_source: str,
) -> dict:
    """Objective pre-render asset diagnostics (edge clipping, coverage, fringe spill, frame window)."""
    alpha = mid_rgba[..., 3].astype(np.float32) / 255.0
    rgb = mid_rgba[..., :3].astype(np.float32) / 255.0
    opaque = alpha > 0.50

    coverage_pct = round(float(np.mean(opaque)) * 100.0, 2)
    strip = 3
    border_touch = {
        "top_pct": round(float(np.mean(opaque[:strip, :])) * 100.0, 2),
        "left_pct": round(float(np.mean(opaque[:, :strip])) * 100.0, 2),
        "right_pct": round(float(np.mean(opaque[:, -strip:])) * 100.0, 2),
        "bottom_pct": round(float(np.mean(opaque[-strip:, :])) * 100.0, 2),
    }

    # Check semi-transparent fringe for lingering neon green/magenta chroma spill
    fringe = (alpha > 0.08) & (alpha < 0.72)
    fringe_green = 0.0
    fringe_magenta = 0.0
    if int(np.sum(fringe)) > 40:
        fr = rgb[fringe]
        fringe_green = round(float(np.mean(np.maximum(fr[:, 1] - np.maximum(fr[:, 0], fr[:, 2]), 0.0))), 4)
        fringe_magenta = round(float(np.mean(np.maximum(np.minimum(fr[:, 0], fr[:, 2]) - fr[:, 1], 0.0))), 4)

    fg_open_pct = round(float(np.mean(fg_rgba[..., 3] < 40)) * 100.0, 2)
    orig_w, orig_h = orig_mid_size
    orig_ratio = round(orig_w / float(max(1, orig_h)), 4)

    warnings: list[str] = []
    mid_mode = matte_meta.get("mid_mode", "unknown")
    if coverage_pct < 8.0:
        warnings.append(f"LOW_SUBJECT_COVERAGE: mid opaque area is only {coverage_pct}% (cutout may have eroded subject).")
    elif coverage_pct > 90.0 and mid_mode != "none":
        warnings.append(f"HIGH_SUBJECT_COVERAGE: mid opaque area is {coverage_pct}% (background may not have been removed; inspect cutout_check.png).")

    if mid_mode != "none":
        if border_touch["top_pct"] > 1.5:
            warnings.append(
                f"EDGE_CLIPPING_TOP: {border_touch['top_pct']}% of top border is opaque (head/ears/crown/weapon may be clipped; consider mid_fit='contain' or wider headroom)."
            )
        if border_touch["left_pct"] > 2.5 or border_touch["right_pct"] > 2.5:
            warnings.append(
                f"EDGE_CLIPPING_SIDE: opaque subject touches left={border_touch['left_pct']}%, right={border_touch['right_pct']}% (limbs/props may clip during ±24° tilt)."
            )
    if fringe_green > 0.14:
        warnings.append(f"FRINGE_GREEN_SPILL: semi-transparent edge shows green excess={fringe_green} (check cutout_check.png).")
    if fringe_magenta > 0.14:
        warnings.append(f"FRINGE_MAGENTA_SPILL: semi-transparent edge shows magenta excess={fringe_magenta} (check cutout_check.png).")
    if fg_open_pct < 62.0:
        warnings.append(f"CROWDED_FRAME: fg frame interior window is only {fg_open_pct}% open (recommend >= 70%).")
    if mid_mode == "grabcut":
        warnings.append("GRABCUT_USED: local GrabCut was used on a non-uniform backdrop; visually verify hair/accessories in cutout_check.png before full render.")
    if abs(orig_ratio - 0.75) > 0.15:
        warnings.append(
            f"ASPECT_RATIO_MISMATCH: raw mid is {orig_w}x{orig_h} (ratio {orig_ratio} vs target 0.75); applied mid_fit='{mid_fit_applied}'."
        )

    return {
        "orig_mid_size": [orig_w, orig_h],
        "orig_mid_ratio": orig_ratio,
        "mid_fit_applied": mid_fit_applied,
        "mid_matte_mode": mid_mode,
        "bg_source": bg_source,
        "subject_coverage_pct": coverage_pct,
        "border_touch": border_touch,
        "fringe_green_excess": fringe_green,
        "fringe_magenta_excess": fringe_magenta,
        "fg_open_window_pct": fg_open_pct,
        "warnings": warnings,
    }


def bbox_initial_warp(alpha_bin: np.ndarray, depth_bin: np.ndarray) -> np.ndarray:
    ay, ax = np.where(alpha_bin > 0.5)
    dy, dx = np.where(depth_bin > 0.5)
    warp = np.eye(2, 3, dtype=np.float32)
    if len(ax) < 100 or len(dx) < 100:
        return warp
    acx, acy = float(np.mean(ax)), float(np.mean(ay))
    dcx, dcy = float(np.mean(dx)), float(np.mean(dy))
    asx, asy = float(np.std(ax)) + 1e-5, float(np.std(ay)) + 1e-5
    dsx, dsy = float(np.std(dx)) + 1e-5, float(np.std(dy)) + 1e-5
    s = 0.5 * (float(np.clip(dsx / asx, 0.85, 1.18)) + float(np.clip(dsy / asy, 0.85, 1.18)))
    warp[0, 0] = s
    warp[1, 1] = s
    warp[0, 2] = dcx - s * acx
    warp[1, 2] = dcy - s * acy
    return warp


def align_depth_ecc(alpha_f: np.ndarray, depth_gray: np.ndarray):
    alpha_bin = (alpha_f > 0.25).astype(np.float32)
    depth_bin = (depth_gray > 14.0).astype(np.float32)
    alpha_soft = cv2.GaussianBlur(alpha_bin, (15, 15), 4.0)
    depth_soft = cv2.GaussianBlur(depth_bin, (15, 15), 4.0)

    def iou_score(m1, m2):
        inter = np.sum((m1 > 0.5) & (m2 > 0.5))
        union = np.sum((m1 > 0.5) | (m2 > 0.5))
        return float(inter) / float(union + 1e-6)

    iou_raw = iou_score(alpha_bin, depth_bin)
    warp_init = bbox_initial_warp(alpha_bin, depth_bin)
    depth_bbox = cv2.warpAffine(depth_bin, warp_init, (MASTER_W, MASTER_H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
    iou_bbox = iou_score(alpha_bin, depth_bbox)

    best_warp = np.eye(2, 3, dtype=np.float32) if iou_raw >= iou_bbox else warp_init.copy()
    best_iou = max(iou_raw, iou_bbox)

    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 300, 1e-5)
    for motion in (cv2.MOTION_AFFINE, cv2.MOTION_EUCLIDEAN):
        try:
            w_try = best_warp.copy()
            cc, w_out = cv2.findTransformECC(alpha_soft, depth_soft, w_try, motion, criteria)
            d_try = cv2.warpAffine(depth_bin, w_out, (MASTER_W, MASTER_H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
            iou_try = iou_score(alpha_bin, d_try)
            print(f"ECC motion={motion}: cc={cc:.5f}, iou={iou_try:.4f} (raw={iou_raw:.4f}, bbox={iou_bbox:.4f})")
            if iou_try >= best_iou - 0.002:
                best_warp = w_out
                best_iou = iou_try
                break
        except cv2.error as e:
            print(f"ECC motion={motion} fallback due to: {e}")

    warped_depth = cv2.warpAffine(
        depth_gray.astype(np.float32),
        best_warp,
        (MASTER_W, MASTER_H),
        flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0.0,
    )
    return warped_depth, iou_raw, best_iou, best_warp


def synthesize_auto_depth(mid_rgba: np.ndarray) -> np.ndarray:
    """Synthesize plausible smooth bas-relief height map directly from subject silhouette + luminance."""
    rgb = mid_rgba[..., :3].astype(np.float32) / 255.0
    alpha_f = mid_rgba[..., 3].astype(np.float32) / 255.0
    fg_bin = (alpha_f > 0.25).astype(np.uint8)
    inner_dist = cv2.distanceTransform(fg_bin, cv2.DIST_L2, 5)
    p95 = float(np.percentile(inner_dist[fg_bin > 0], 95)) if np.any(fg_bin > 0) else 60.0
    d_norm = np.power(np.clip(inner_dist / max(p95, 1.0), 0.0, 1.0), 0.65)

    yy, xx = np.mgrid[0:MASTER_H, 0:MASTER_W]
    ux = (xx.astype(np.float32) / MASTER_W - 0.5) / 0.28
    uy = (yy.astype(np.float32) / MASTER_H - 0.36) / 0.34
    prior = np.exp(-0.5 * (ux ** 2 + uy ** 2)) * 0.28

    luma = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    luma_blur = cv2.GaussianBlur(luma, (17, 17), 4.5)
    relief = np.clip(0.62 * d_norm + prior + 0.15 * luma_blur, 0.0, 1.0)
    synth = np.where(alpha_f > 0.12, 30.0 + 215.0 * relief, 0.0).astype(np.float32)
    return synth


def build_smooth_height_field(warped_depth: np.ndarray, alpha_f: np.ndarray):
    solid = (alpha_f > 0.82) & (warped_depth > 14.0)
    solid_u8 = solid.astype(np.uint8) * 255
    eroded = cv2.erode(solid_u8, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 127
    seeds = eroded & (warped_depth > 14.0)
    if np.sum(seeds) < 100:
        seeds = (alpha_f > 0.25) & (warped_depth > 14.0)
    if not np.any(seeds):
        zeros = np.zeros_like(alpha_f, dtype=np.float32)
        return zeros, zeros

    src = (~seeds).astype(np.uint8)
    dist_out, labels = cv2.distanceTransformWithLabels(src, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    seed_vals = warped_depth[seeds]
    extrap = seed_vals[labels - 1]
    height_raw = np.where(seeds, warped_depth, extrap)
    height_raw = np.where(dist_out <= 32.0, height_raw, extrap)

    height_bilat = cv2.bilateralFilter(height_raw.astype(np.float32), d=15, sigmaColor=28.0, sigmaSpace=15.0)
    fg_mask = alpha_f > 0.20
    if np.any(fg_mask):
        lo = float(np.percentile(height_bilat[fg_mask], 1.5))
        hi = max(float(np.percentile(height_bilat[fg_mask], 99.5)), lo + 20.0)
    else:
        lo, hi = 15.0, 255.0

    norm_h = 0.15 + 0.85 * np.clip((height_bilat - lo) / (hi - lo), 0.0, 1.0)
    fg_u8 = (alpha_f > 0.35).astype(np.uint8)
    inner_dist = cv2.distanceTransform(fg_u8, cv2.DIST_L2, 5)
    inner_cap = float(np.percentile(inner_dist[fg_u8 > 0], 95)) if np.any(fg_u8 > 0) else 60.0
    inner_pillow = np.sqrt(np.clip(inner_dist / max(inner_cap, 1.0), 0.0, 1.0)) * 0.07

    extrap_h = np.clip(norm_h + inner_pillow, 0.0, 1.0)
    aligned_vis = np.where(alpha_f > 0.05, extrap_h, 0.0)
    return aligned_vis, extrap_h


def _hsv_to_rgb01(h_deg: float, s: float, v: float) -> list[float]:
    h = (h_deg % 360.0) / 60.0
    c = v * s
    x = c * (1.0 - abs(h % 2.0 - 1.0))
    m = v - c
    if h < 1:
        rgb = (c, x, 0.0)
    elif h < 2:
        rgb = (x, c, 0.0)
    elif h < 3:
        rgb = (0.0, c, x)
    elif h < 4:
        rgb = (0.0, x, c)
    elif h < 5:
        rgb = (x, 0.0, c)
    else:
        rgb = (c, 0.0, x)
    return [round(float(np.clip(ch + m, 0.0, 1.0)), 3) for ch in rgb]


def resolve_palette(theme_palette, bg_rgb: np.ndarray, fg_rgba: np.ndarray, palettes_db: dict) -> dict:
    base = dict(palettes_db["celestial-gold"])
    if isinstance(theme_palette, dict):
        merged = dict(base)
        merged.update(theme_palette)
        return merged
    if isinstance(theme_palette, str) and theme_palette != "auto":
        if theme_palette in palettes_db:
            return dict(palettes_db[theme_palette])
        print(f"Warning: unknown theme_palette '{theme_palette}', falling back to 'auto'.")

    # Auto extraction from bg dominant chromatic accent & fg dominant metal hue
    bg_hsv = cv2.cvtColor(bg_rgb, cv2.COLOR_RGB2HSV)
    bh = bg_hsv[..., 0].astype(np.float32) * 2.0
    bs = bg_hsv[..., 1].astype(np.float32) / 255.0
    bv = bg_hsv[..., 2].astype(np.float32) / 255.0
    bg_sel = (bs > 0.25) & (bv > 0.28)
    if np.sum(bg_sel) > 200:
        rad = np.radians(bh[bg_sel])
        bg_hue = float(np.degrees(np.arctan2(np.median(np.sin(rad)), np.median(np.cos(rad)))) % 360.0)
        bg_sat = float(np.clip(np.median(bs[bg_sel]), 0.38, 0.78))
    else:
        bg_hue, bg_sat = 212.0, 0.65

    aura_col = _hsv_to_rgb01(bg_hue, float(np.clip(bg_sat * 0.92, 0.35, 0.80)), 0.92)
    sand2_col = _hsv_to_rgb01(bg_hue - 12.0, float(np.clip(bg_sat * 0.65, 0.28, 0.60)), 0.98)

    fg_rgb = fg_rgba[..., :3]
    fg_a = fg_rgba[..., 3] > 128
    fg_hsv = cv2.cvtColor(fg_rgb, cv2.COLOR_RGB2HSV)
    fh = fg_hsv[..., 0].astype(np.float32) * 2.0
    fs = fg_hsv[..., 1].astype(np.float32) / 255.0
    fv = fg_hsv[..., 2].astype(np.float32) / 255.0
    fg_valid = fg_a & (fv > 0.20)
    if np.sum(fg_valid) > 200:
        med_fs = float(np.median(fs[fg_valid]))
        rad_f = np.radians(fh[fg_valid])
        fg_hue = float(np.degrees(np.arctan2(np.median(np.sin(rad_f)), np.median(np.cos(rad_f)))) % 360.0)
    else:
        med_fs, fg_hue = 0.45, 40.0

    if med_fs < 0.18:
        # Cool platinum / titanium metallic rim
        edge_base = [0.42, 0.46, 0.52]
        edge_spec = [0.92, 0.96, 1.00]
        metal_tint = [0.88, 0.94, 1.00]
        sand1_col = _hsv_to_rgb01(bg_hue + 18.0, 0.22, 0.98)
        ui_accent = "#bce8ff"
    else:
        metal_hue = fg_hue if (18.0 <= fg_hue <= 60.0 or fg_hue >= 315.0) else 40.0
        edge_base = _hsv_to_rgb01(metal_hue, 0.46, 0.52)
        edge_spec = _hsv_to_rgb01(metal_hue, 0.28, 1.00)
        metal_tint = _hsv_to_rgb01(metal_hue, 0.38, 1.00)
        sand1_col = _hsv_to_rgb01(metal_hue, 0.52, 1.00)
        r_hex, g_hex, b_hex = [int(round(c * 255)) for c in _hsv_to_rgb01(metal_hue, 0.50, 1.00)]
        ui_accent = f"#{r_hex:02x}{g_hex:02x}{b_hex:02x}"

    seq3 = _hsv_to_rgb01(bg_hue + 48.0, 0.32, 1.00)
    seq2 = _hsv_to_rgb01(bg_hue, 0.14, 1.00)
    return {
        "edge_base": edge_base,
        "edge_spec": edge_spec,
        "metal_tint": metal_tint,
        "aura": aura_col,
        "sand1": sand1_col,
        "sand2": sand2_col,
        "sequins": [sand1_col, sand2_col, seq2, seq3],
        "part1": sand1_col,
        "part2": sand2_col,
        "ui_accent": ui_accent,
    }


def detect_face_bbox(mid_rgb: np.ndarray, alpha_f: np.ndarray) -> list[float]:
    hsv = cv2.cvtColor(mid_rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0].astype(np.float32) * 2.0, hsv[..., 1] / 255.0, hsv[..., 2] / 255.0
    skin = ((h < 42.0) | (h > 335.0)) & (s > 0.06) & (s < 0.55) & (v > 0.35) & (alpha_f > 0.7)
    yy, xx = np.mgrid[0:MASTER_H, 0:MASTER_W]
    roi = skin & (yy > 0.10 * MASTER_H) & (yy < 0.48 * MASTER_H) & (xx > 0.25 * MASTER_W) & (xx < 0.75 * MASTER_W)
    num, _, stats, _ = cv2.connectedComponentsWithStats(roi.astype(np.uint8))
    best_box = [0.36, 0.16, 0.64, 0.36]
    if num > 1:
        cid = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        if stats[cid, cv2.CC_STAT_AREA] > 400:
            x, y, bw, bh, _ = stats[cid]
            pad_x = int(0.30 * bw) + 30
            pad_y = int(0.35 * bh) + 35
            best_box = [
                round(max(0.0, (x - pad_x) / MASTER_W), 4),
                round(max(0.0, (y - pad_y) / MASTER_H), 4),
                round(min(1.0, (x + bw + pad_x) / MASTER_W), 4),
                round(min(1.0, (y + bh + pad_y) / MASTER_H), 4),
            ]
    return best_box


def build_masks_and_meta(bg_rgb: np.ndarray, mid_rgba: np.ndarray, fg_rgba: np.ndarray, cfg: dict, palettes_db: dict):
    bg_f = bg_rgb.astype(np.float32) / 255.0
    bg_luma = 0.299 * bg_f[..., 0] + 0.587 * bg_f[..., 1] + 0.114 * bg_f[..., 2]
    gx = cv2.Sobel(bg_luma, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(bg_luma, cv2.CV_32F, 0, 1, ksize=3)
    bg_edge = np.hypot(gx, gy)
    bg_edge_norm = np.clip(bg_edge / max(float(np.percentile(bg_edge, 97)), 0.05), 0.0, 1.0)
    r_holo = np.power(np.clip(1.0 - bg_luma, 0.0, 1.0), 1.35) * (1.0 - 0.65 * bg_edge_norm)
    r_holo = np.clip(cv2.GaussianBlur(r_holo, (21, 21), 6.0) * 1.15, 0.12, 1.0)

    mid_rgb = mid_rgba[..., :3]
    mid_alpha = mid_rgba[..., 3].astype(np.float32) / 255.0
    mid_f = mid_rgb.astype(np.float32) / 255.0
    mid_hsv = cv2.cvtColor(mid_rgb, cv2.COLOR_RGB2HSV)
    mh = mid_hsv[..., 0].astype(np.float32) * 2.0
    ms = mid_hsv[..., 1].astype(np.float32) / 255.0
    mv = mid_hsv[..., 2].astype(np.float32) / 255.0
    mid_luma = 0.299 * mid_f[..., 0] + 0.587 * mid_f[..., 1] + 0.114 * mid_f[..., 2]

    face_cfg = cfg.get("face_box", "auto")
    if face_cfg is None:
        face_box = None
    elif isinstance(face_cfg, (list, tuple)) and len(face_cfg) == 4:
        face_box = [round(float(v), 4) for v in face_cfg]
    else:
        face_box = detect_face_bbox(mid_rgb, mid_alpha)

    yy, xx = np.mgrid[0:MASTER_H, 0:MASTER_W]
    xn = xx / float(MASTER_W)
    yn = yy / float(MASTER_H)
    if face_box is not None:
        in_face = (xn >= face_box[0]) & (xn <= face_box[2]) & (yn >= face_box[1]) & (yn <= face_box[3])
    else:
        in_face = np.zeros((MASTER_H, MASTER_W), dtype=bool)

    skin_like = ((mh < 34.0) | (mh > 335.0)) & (ms < 0.42) & (mv > 0.62)
    gold_hue = (mh >= 18.0) & (mh <= 56.0) & (ms >= 0.28) & (mv >= 0.38)
    bright_metal = (mv >= 0.88) & (ms <= 0.22) & (~skin_like)
    g_metal = np.where((gold_hue | bright_metal) & (~(in_face & skin_like)) & (mid_alpha > 0.25), 1.0, 0.0).astype(np.float32)
    g_metal = cv2.GaussianBlur(g_metal, (7, 7), 1.8) * mid_alpha

    mx = cv2.Sobel(mid_luma, cv2.CV_32F, 1, 0, ksize=3)
    my = cv2.Sobel(mid_luma, cv2.CV_32F, 0, 1, ksize=3)
    m_grad = np.hypot(mx, my)
    grad_cap = float(np.percentile(m_grad[mid_alpha > 0.3], 96)) if np.any(mid_alpha > 0.3) else 0.3
    b_sar = np.clip(m_grad / max(grad_cap, 0.05), 0.0, 1.0) * mid_alpha

    fg_alpha = fg_rgba[..., 3].astype(np.float32) / 255.0
    fg_bin = (fg_alpha > 0.35).astype(np.uint8)
    fg_dist = cv2.distanceTransform(fg_bin, cv2.DIST_L2, 5)
    fg_cap = float(np.percentile(fg_dist[fg_bin > 0], 92)) if np.any(fg_bin > 0) else 20.0
    a_emboss = np.clip(fg_dist / max(fg_cap, 2.0), 0.0, 1.0) * fg_alpha

    masks_rgba = np.dstack([
        np.clip(r_holo * 255.0, 0, 255),
        np.clip(g_metal * 255.0, 0, 255),
        np.clip(b_sar * 255.0, 0, 255),
        np.clip(a_emboss * 255.0, 0, 255),
    ]).astype(np.uint8)

    bg_bright = cv2.GaussianBlur(bg_luma, (51, 51), 16.0)
    roi_bg = bg_bright[int(0.15 * MASTER_H):int(0.65 * MASTER_H), int(0.20 * MASTER_W):int(0.80 * MASTER_W)]
    cy_off, cx_off = np.unravel_index(np.argmax(roi_bg), roi_bg.shape)
    astro_cx = round((0.20 * MASTER_W + cx_off) / MASTER_W, 4)
    astro_cy = round((0.15 * MASTER_H + cy_off) / MASTER_H, 4)

    med_bg = np.percentile(bg_f.reshape(-1, 3), 35, axis=0)
    studio_rgb = [int(np.clip(c * 255 * 0.42, 6, 48)) for c in med_bg]

    glints = []

    def is_outside_face(u, v):
        if face_box is None:
            return True
        pad = 0.03
        return not (face_box[0] - pad <= u <= face_box[2] + pad and face_box[1] - pad <= v <= face_box[3] + pad)

    def pick_peaks(score_map, count, min_dist_px, scale_range, kind):
        work = score_map.copy()
        margin_x, margin_y = int(0.035 * MASTER_W), int(0.035 * MASTER_H)
        work[:margin_y, :] = 0.0
        work[-margin_y:, :] = 0.0
        work[:, :margin_x] = 0.0
        work[:, -margin_x:] = 0.0
        picked = 0
        for _ in range(count * 8):
            if picked >= count:
                break
            iy, ix = np.unravel_index(np.argmax(work), work.shape)
            if float(work[iy, ix]) <= 0.15:
                break
            u, v = ix / float(MASTER_W), iy / float(MASTER_H)
            y0, y1 = max(0, iy - min_dist_px), min(MASTER_H, iy + min_dist_px)
            x0, x1 = max(0, ix - min_dist_px), min(MASTER_W, ix + min_dist_px)
            work[y0:y1, x0:x1] = 0.0
            if not is_outside_face(u, v):
                continue
            if any((u - g["x"]) ** 2 + (v - g["y"]) ** 2 < 0.0045 for g in glints):
                continue
            glints.append({
                "x": round(u, 4),
                "y": round(v, 4),
                "size": round(scale_range[0] + (scale_range[1] - scale_range[0]) * ((picked % 3) / 2.0), 4),
                "phase": round((picked * 0.37) % 1.0, 3),
                "kind": kind,
            })
            picked += 1

    fg_f = fg_rgba[..., :3].astype(np.float32) / 255.0
    fg_luma = (0.299 * fg_f[..., 0] + 0.587 * fg_f[..., 1] + 0.114 * fg_f[..., 2]) * fg_alpha
    fg_peak_map = fg_luma * (0.4 + 0.6 * a_emboss)
    if str(cfg.get("label_mode", "page_only")).lower().strip() == "on_card":
        # Keep 4-point frame glints off the bottom nameplate text so title & badge stay crisp
        fg_peak_map[int(0.845 * MASTER_H) : int(0.955 * MASTER_H), int(0.12 * MASTER_W) : int(0.88 * MASTER_W)] = 0.0
    pick_peaks(fg_peak_map, 6, 110, (0.045, 0.072), "frame")
    pick_peaks(g_metal * mid_luma, 5, 110, (0.036, 0.062), "subject_metal")
    pick_peaks(bg_luma * (1.0 - mid_alpha) * (1.0 - fg_alpha), 4, 140, (0.030, 0.050), "bg_star")

    palette = resolve_palette(cfg.get("theme_palette", "auto"), bg_rgb, fg_rgba, palettes_db)

    # v2.1 FX #1: Prop light sweep config
    prop_cfg = cfg.get("prop_fx") or {}
    prop_enabled = bool(prop_cfg.get("enabled", bool(prop_cfg.get("mask_polygons"))))
    raw_tint = prop_cfg.get("tint", "auto")
    if isinstance(raw_tint, (list, tuple)) and len(raw_tint) == 3:
        prop_tint = [round(float(v), 3) for v in raw_tint]
    else:
        prop_tint = [round(float(v), 3) for v in palette.get("edge_spec", [0.95, 0.95, 1.0])]

    raw_gain = prop_cfg.get("gain", 0.90)
    prop_gain = round(0.90 if raw_gain in (None, "auto") else float(raw_gain), 3)
    prop_fx = {
        "enabled": prop_enabled,
        "start_uv": [round(float(v), 4) for v in prop_cfg.get("start_uv", [0.5, 0.7])],
        "tip_uv": [round(float(v), 4) for v in prop_cfg.get("tip_uv", [0.5, 0.3])],
        "tint": prop_tint,
        "gain": prop_gain,
    }

    # v2.1 FX #2: Single bespoke analytical SDF motion motif
    motif_map = {"none": -1, "feathers_bubbles": 0, "cyber_stars": 1, "petals": 2, "embers": 3, "snowflakes": 4}
    raw_motif = cfg.get("motion_motif", "none")
    motif_cfg = {"kind": raw_motif} if isinstance(raw_motif, str) else (raw_motif or {})
    motif_kind_name = str(motif_cfg.get("kind", "none")).lower().strip()
    motif_id = motif_map.get(motif_kind_name, -1)
    c1 = motif_cfg.get("color1", "auto")
    c2 = motif_cfg.get("color2", "auto")
    motif_col1 = [round(float(v), 3) for v in (c1 if isinstance(c1, (list, tuple)) and len(c1) == 3 else palette["part1"])]
    motif_col2 = [round(float(v), 3) for v in (c2 if isinstance(c2, (list, tuple)) and len(c2) == 3 else palette["part2"])]
    motion_motif = {
        "kind": motif_kind_name if motif_id >= 0 else "none",
        "kind_id": motif_id,
        "color1": motif_col1,
        "color2": motif_col2,
    }

    label_mode = str(cfg.get("label_mode", "page_only")).lower().strip()
    if label_mode not in ("page_only", "on_card", "hidden"):
        label_mode = "page_only"

    holo_pattern = str(cfg.get("holo_pattern", "starburst")).lower().strip()
    if holo_pattern not in VALID_HOLO_PATTERNS:
        holo_pattern = "starburst"

    material_preset = str(cfg.get("material_preset", "sar_quicksand")).lower().strip()
    if material_preset not in VALID_MATERIAL_PRESETS:
        material_preset = "sar_quicksand"

    lighting_preset = str(cfg.get("lighting_preset", "gallery_neutral")).lower().strip()
    if lighting_preset not in VALID_LIGHTING_PRESETS:
        lighting_preset = "gallery_neutral"

    bg_preset = str(cfg.get("bg_preset", "celestial_nebula")).lower().strip()
    if bg_preset not in VALID_BG_PRESETS:
        bg_preset = "celestial_nebula"

    ui_lang = str(cfg.get("ui_lang", "auto")).lower().strip()
    if ui_lang not in ("auto", "zh", "en"):
        ui_lang = "auto"

    meta = {
        "title": str(cfg.get("title", "3D 全息流麻收藏卡")),
        "badge": str(cfg.get("badge", "SAR / UR")),
        "subtitle": str(cfg.get("subtitle", "3D 交互全息流麻卡")),
        "label_mode": label_mode,
        "ui_lang": ui_lang,
        "studio_bg_label": str(cfg.get("studio_bg_label", "暗绒展台")),
        "holo_pattern": holo_pattern,
        "material_preset": material_preset,
        "lighting_preset": lighting_preset,
        "bg_preset": bg_preset,
        "frame_tint": cfg.get("frame_tint", "auto"),
        "seed": int(cfg.get("seed", 20261121)),
        "master_size": [MASTER_W, MASTER_H],
        "studio_color_rgb": studio_rgb,
        "astrolabe_center": [astro_cx, astro_cy],
        "face_box": face_box,
        "glints": glints,
        "palette": palette,
        "prop_fx": prop_fx,
        "motion_motif": motion_motif,
    }
    return masks_rgba, meta


def main():
    parser = argparse.ArgumentParser(description="Align depth or synthesize bas-relief depth and generate scene masks.")
    parser.add_argument("--workdir", required=True, type=Path, help="Project workspace directory")
    parser.add_argument("--auto-depth", action="store_true", help="Synthesize smooth relief depth instead of aligning mid_depth")
    args = parser.parse_args()

    workdir = args.workdir.resolve()
    raw_dir = workdir / "01_raw_layers"
    mat_dir = workdir / "02_matted"
    proc_dir = workdir / "03_processed"
    proc_dir.mkdir(parents=True, exist_ok=True)

    cfg = {}
    cfg_path = workdir / "card_config.json"
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    palettes_db = json.loads(PALETTES_PATH.read_text(encoding="utf-8"))

    matte_meta = {}
    matte_meta_path = mat_dir / "matte_meta.json"
    if matte_meta_path.exists():
        try:
            matte_meta = json.loads(matte_meta_path.read_text(encoding="utf-8"))
        except Exception:
            matte_meta = {}

    mid_path = (mat_dir / "mid_rgba.png") if (mat_dir / "mid_rgba.png").exists() else find_layer(raw_dir, ["mid", "mid_2k", "subject", "character"])
    if mid_path is None:
        raise FileNotFoundError(f"Could not find mid_rgba.png in {mat_dir} or mid layer in {raw_dir}")

    fg_path = (mat_dir / "fg_rgba.png") if (mat_dir / "fg_rgba.png").exists() else find_layer(raw_dir, ["fg", "fg_2k", "frame", "border"])
    is_builtin_frame = False
    if fg_path is None:
        fg_path = resolve_fallback_frame(cfg.get("fallback_frame"))
        is_builtin_frame = True
        print(f"Using built-in fallback frame: {fg_path.name}")

    with Image.open(mid_path) as raw_mid_im:
        orig_mid_size = raw_mid_im.size
        mid_pil, mid_fit_applied = resize_mid_smart(raw_mid_im, str(cfg.get("mid_fit", "auto")))
    fg_pil = resize_exact_3_4(Image.open(fg_path).convert("RGBA"), "cover")

    mid_rgba = np.array(mid_pil)
    alpha_f = mid_rgba[..., 3].astype(np.float32) / 255.0

    bg_path = find_layer(raw_dir, ["bg", "bg_2k", "background"])
    bg_preset_name = str(cfg.get("bg_preset", "celestial_nebula")).lower().strip()
    if bg_path is not None:
        bg_pil = resize_exact_3_4(Image.open(bg_path).convert("RGB"), "cover")
        bg_source = "user_supplied"
    else:
        print(f"No bg layer supplied in 01_raw_layers/; synthesizing procedural backdrop (bg_preset={bg_preset_name}).")
        bg_pil = synthesize_procedural_bg(
            mid_rgba,
            cfg.get("theme_palette", "auto"),
            palettes_db,
            seed=int(cfg.get("seed", 20261121)),
            bg_preset=bg_preset_name,
        )
        bg_source = f"procedural:{bg_preset_name}"

    bg_rgb = np.array(bg_pil)

    # Resolve palette early for dynamic built-in frame tinting and/or engraved on-card nameplate
    prelim_pal = resolve_palette(cfg.get("theme_palette", "auto"), bg_rgb, np.array(fg_pil), palettes_db)
    fg_pil = apply_frame_tint(
        fg_pil,
        is_builtin_frame=is_builtin_frame,
        frame_stem=fg_path.stem.lower(),
        frame_tint=cfg.get("frame_tint", "auto"),
        palette=prelim_pal,
    )

    label_mode = str(cfg.get("label_mode", "page_only")).lower().strip()
    if label_mode == "on_card":
        fg_pil = bake_on_card_nameplate(
            fg_pil,
            str(cfg.get("title", "")),
            str(cfg.get("badge", "")),
            prelim_pal,
        )
        print(f"Baked on-card metallic nameplate onto master_fg (badge={cfg.get('badge', '')!r}, title={cfg.get('title', '')!r}).")

    fg_rgba = np.array(fg_pil)

    depth_path = None if args.auto_depth else find_layer(raw_dir, ["mid_depth", "mid_depth_2k", "depth"])
    if depth_path is not None:
        depth_pil = resize_exact_3_4(Image.open(depth_path).convert("L"), "cover")
        depth_gray = np.array(depth_pil)
        warped_depth, iou_raw, iou_aligned, warp_mat = align_depth_ecc(alpha_f, depth_gray)
        depth_source = "ecc_aligned"
    else:
        print("No mid_depth supplied (or --auto-depth enabled); synthesizing distance-transform + luminance relief depth.")
        warped_depth = synthesize_auto_depth(mid_rgba)
        iou_raw, iou_aligned = 1.0, 1.0
        warp_mat = np.eye(2, 3, dtype=np.float32)
        depth_source = "auto_synthesized"

    aligned_vis, extrap_h = build_smooth_height_field(warped_depth, alpha_f)
    Image.fromarray(np.clip(aligned_vis * 255.0, 0, 255).astype(np.uint8), "L").save(proc_dir / "depth_aligned.png")
    Image.fromarray(np.clip(extrap_h * 255.0, 0, 255).astype(np.uint8), "L").save(proc_dir / "depth_extrapolated.png")

    bg_pil.save(proc_dir / "master_bg.png")
    mid_pil.save(proc_dir / "master_mid.png")
    fg_pil.save(proc_dir / "master_fg.png")

    masks_rgba, meta = build_masks_and_meta(bg_rgb, mid_rgba, fg_rgba, cfg, palettes_db)
    meta["bg_source"] = bg_source
    meta["depth_source"] = depth_source
    meta["ecc_iou_raw"] = round(iou_raw, 4)
    meta["ecc_iou_aligned"] = round(iou_aligned, 4)
    meta["warp_matrix"] = [[round(float(v), 6) for v in row] for row in warp_mat]

    lint = run_asset_lint(mid_rgba, fg_rgba, orig_mid_size, mid_fit_applied, matte_meta, bg_source)
    bo_mask, bo_info = build_breakout_mask(cfg, workdir, mid_rgba, fg_rgba)
    meta["breakout"] = bo_info
    bo_path = proc_dir / "breakout_mask.png"
    if bo_mask is not None:
        Image.fromarray(bo_mask, "L").save(bo_path)
        print(f"Break-the-frame enabled (mode={bo_info['mode']}): {bo_info['popped_out_pct']}% of the subject now overlaps the frame from above.")
    else:
        if bo_path.exists():
            bo_path.unlink()
        if bo_info["subject_under_frame_pct"] >= 3.0 and not bo_info["mid_full_bleed"]:
            lint["warnings"].append(
                f"SUBJECT_UNDER_FRAME: {bo_info['subject_under_frame_pct']}% of the subject is hidden behind the frame "
                "(set breakout.enabled=true for a break-the-frame pop-out, or re-generate mid with ~12% headroom / a thinner frame)."
            )
    meta["asset_lint"] = lint
    for w_msg in lint["warnings"]:
        print(f"LINT WARNING: {w_msg}")

    Image.fromarray(masks_rgba, "RGBA").save(proc_dir / "masks_rgba.png")
    if meta["prop_fx"]["enabled"]:
        _, _, prop_pct = build_prop_mask_for_workdir(workdir, cfg)
        meta["prop_fx"]["active_area_pct"] = round(prop_pct, 2)
    (proc_dir / "scene_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    # 4-panel QA inspection grid
    comp = Image.alpha_composite(Image.alpha_composite(bg_pil.convert("RGBA"), mid_pil), fg_pil)
    overlay = np.array(comp.convert("RGB")).copy()
    if meta["face_box"] is not None:
        fx0, fy0, fx1, fy1 = [int(v * s) for v, s in zip(meta["face_box"], [MASTER_W, MASTER_H, MASTER_W, MASTER_H])]
        cv2.rectangle(overlay, (fx0, fy0), (fx1, fy1), (80, 255, 160), 3)
    acx, acy = int(meta["astrolabe_center"][0] * MASTER_W), int(meta["astrolabe_center"][1] * MASTER_H)
    cv2.drawMarker(overlay, (acx, acy), (255, 220, 60), cv2.MARKER_CROSS, 36, 4)
    for g in meta["glints"]:
        gx, gy = int(g["x"] * MASTER_W), int(g["y"] * MASTER_H)
        cv2.circle(overlay, (gx, gy), 14, (255, 90, 220), 3)

    depth_color = cv2.cvtColor(cv2.applyColorMap(np.clip(aligned_vis * 255, 0, 255).astype(np.uint8), cv2.COLORMAP_INFERNO), cv2.COLOR_BGR2RGB)
    alpha_edge = cv2.Canny((alpha_f > 0.35).astype(np.uint8) * 255, 50, 150)
    depth_edge = cv2.Canny((aligned_vis > 0.05).astype(np.uint8) * 255, 50, 150)
    contour_vis = (mid_rgba[..., :3] * alpha_f[..., None]).astype(np.uint8)
    contour_vis[alpha_edge > 0] = [0, 255, 255]
    contour_vis[depth_edge > 0] = [255, 60, 180]
    masks_vis = masks_rgba[..., :3]

    pw, ph = 480, 640
    grid = np.vstack([
        np.hstack([cv2.resize(overlay, (pw, ph)), cv2.resize(depth_color, (pw, ph))]),
        np.hstack([cv2.resize(contour_vis, (pw, ph)), cv2.resize(masks_vis, (pw, ph))]),
    ])
    Image.fromarray(grid, "RGB").save(proc_dir / "align_check.png")
    print(
        f"Stage prepare complete: bg_source={bg_source}, depth_source={depth_source}, "
        f"mid_fit={mid_fit_applied}, ECC IoU {iou_raw:.4f} -> {iou_aligned:.4f}, "
        f"glints={len(meta['glints'])}, lint_warnings={len(lint['warnings'])}"
    )


if __name__ == "__main__":
    main()
