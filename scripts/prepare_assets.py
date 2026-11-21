"""Stage 3A: Align or synthesize relief depth, resolve theme palette, masks, and scene_meta.json."""
import argparse
import json
import math
import sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

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
    if not cand.exists():
        cand = BUILTIN_FRAMES_DIR / "classic_sar_gold.png"
    return cand


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
    pick_peaks(fg_luma * (0.4 + 0.6 * a_emboss), 6, 110, (0.045, 0.072), "frame")
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

    meta = {
        "title": str(cfg.get("title", "3D 全息流麻收藏卡")),
        "badge": str(cfg.get("badge", "SAR / UR")),
        "subtitle": str(cfg.get("subtitle", "3D 交互全息流麻卡（悬停/拖拽/陀螺仪倾摆）")),
        "studio_bg_label": str(cfg.get("studio_bg_label", "主题棚拍")),
        "holo_pattern": str(cfg.get("holo_pattern", "starburst")),
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

    bg_path = find_layer(raw_dir, ["bg", "bg_2k", "background"])
    if bg_path is None:
        raise FileNotFoundError(f"Could not find background layer in {raw_dir} (expected bg.png/.jpg/.webp)")

    mid_path = (mat_dir / "mid_rgba.png") if (mat_dir / "mid_rgba.png").exists() else find_layer(raw_dir, ["mid", "mid_2k", "subject", "character"])
    if mid_path is None:
        raise FileNotFoundError(f"Could not find mid_rgba.png in {mat_dir} or mid layer in {raw_dir}")

    fg_path = (mat_dir / "fg_rgba.png") if (mat_dir / "fg_rgba.png").exists() else find_layer(raw_dir, ["fg", "fg_2k", "frame", "border"])
    if fg_path is None:
        fg_path = resolve_fallback_frame(cfg.get("fallback_frame"))
        print(f"Using built-in fallback frame: {fg_path.name}")

    depth_path = None if args.auto_depth else find_layer(raw_dir, ["mid_depth", "mid_depth_2k", "depth"])

    bg_pil = resize_exact_3_4(Image.open(bg_path).convert("RGB"), "cover")
    mid_pil = resize_exact_3_4(Image.open(mid_path).convert("RGBA"), "cover")
    fg_pil = resize_exact_3_4(Image.open(fg_path).convert("RGBA"), "cover")

    bg_rgb = np.array(bg_pil)
    mid_rgba = np.array(mid_pil)
    fg_rgba = np.array(fg_pil)
    alpha_f = mid_rgba[..., 3].astype(np.float32) / 255.0

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
    meta["depth_source"] = depth_source
    meta["ecc_iou_raw"] = round(iou_raw, 4)
    meta["ecc_iou_aligned"] = round(iou_aligned, 4)
    meta["warp_matrix"] = [[round(float(v), 6) for v in row] for row in warp_mat]

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
    print(f"Stage prepare complete: depth_source={depth_source}, ECC IoU {iou_raw:.4f} -> {iou_aligned:.4f}, glints={len(meta['glints'])}")


if __name__ == "__main__":
    main()
