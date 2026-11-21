"""Stage 2B: Multi-mode chroma-key / native-alpha matting & fringe despill for collector card layers."""
import argparse
import json
import sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SKILL_ROOT = Path(__file__).resolve().parent.parent
BUILTIN_FRAMES_DIR = SKILL_ROOT / "assets" / "frames"
IMG_EXTS = (".png", ".webp", ".jpg", ".jpeg")


def find_layer(raw_dir: Path, stems: list[str]) -> Path | None:
    """Find first existing image matching stems (case-insensitive) in raw_dir."""
    if not raw_dir.exists():
        return None
    files = {p.name.lower(): p for p in raw_dir.iterdir() if p.is_file()}
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


def detect_key_mode(img_path: Path) -> str:
    """Auto-detect native transparent RGBA vs solid chroma backdrop (green / magenta / blue)."""
    with Image.open(img_path) as im:
        if im.mode in ("RGBA", "LA", "PA"):
            alpha = np.array(im.convert("RGBA"))[..., 3]
            if float(np.mean(alpha < 12)) > 0.04:
                return "rgba"
        rgb = np.array(im.convert("RGB"), dtype=np.float32) / 255.0

    h, w = rgb.shape[:2]
    bw = max(4, min(16, w // 40))
    bh = max(4, min(16, h // 40))
    border_pixels = np.concatenate([
        rgb[:bh, :, :].reshape(-1, 3),
        rgb[-bh:, :, :].reshape(-1, 3),
        rgb[:, :bw, :].reshape(-1, 3),
        rgb[:, -bw:, :].reshape(-1, 3),
    ], axis=0)
    med = np.median(border_pixels, axis=0)
    r, g, b = float(med[0]), float(med[1]), float(med[2])

    if g - max(r, b) > 0.22:
        return "green"
    if min(r, b) - g > 0.22:
        return "magenta"
    if b - max(r, g) > 0.22:
        return "blue"
    print(f"Warning: border median RGB=({r:.2f}, {g:.2f}, {b:.2f}) did not clearly match green/magenta/blue; defaulting to 'green'.")
    return "green"


def remove_small_speckles(alpha: np.ndarray, min_area: int) -> np.ndarray:
    fg_bin = (alpha > 0.12).astype(np.uint8)
    num_cc, labels, stats, _ = cv2.connectedComponentsWithStats(fg_bin, connectivity=8)
    out = alpha.copy()
    for cid in range(1, num_cc):
        if stats[cid, cv2.CC_STAT_AREA] < min_area:
            out[labels == cid] = 0.0
    return out


def extrapolate_fringe_rgb(rgb_work: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Dilate solid interior edge colors outward into semi-transparent fringe to avoid dark halos."""
    solid = alpha > 0.85
    if not np.any(solid):
        return rgb_work
    fringe = (alpha > 0.0) & (alpha <= 0.55)
    rgb_clean = rgb_work.copy()
    valid = alpha > 0.70
    for _ in range(4):
        num = cv2.boxFilter((rgb_clean * valid[..., None]).astype(np.float32), -1, (3, 3), normalize=False)
        den = cv2.boxFilter(valid.astype(np.float32), -1, (3, 3), normalize=False)
        fill_ok = (~valid) & (den > 0.5)
        rgb_clean[fill_ok] = num[fill_ok] / den[fill_ok][..., None]
        valid = valid | fill_ok
    blend = np.clip((0.55 - alpha) / 0.55, 0.0, 1.0)[..., None]
    return np.where(fringe[..., None], rgb_work * (1.0 - blend) + rgb_clean * blend, rgb_work)


def extract_native_rgba(img_path: Path, is_frame: bool = False) -> np.ndarray:
    """Load an existing RGBA/PNG cutout, remove tiny specks, and dehalo semi-transparent fringes."""
    with Image.open(img_path) as im:
        rgba_u8 = np.array(im.convert("RGBA"))
    rgb = rgba_u8[..., :3].astype(np.float32) / 255.0
    alpha = rgba_u8[..., 3].astype(np.float32) / 255.0
    alpha = np.where(alpha < 0.02, 0.0, alpha)
    alpha = remove_small_speckles(alpha, min_area=24 if is_frame else 40)
    rgb_final = extrapolate_fringe_rgb(rgb, alpha)
    return np.dstack([
        np.clip(rgb_final * 255.0, 0, 255),
        np.clip(alpha[..., None] * 255.0, 0, 255),
    ]).astype(np.uint8)


def _chroma_metrics(rgb: np.ndarray, h_deg: float, key_color: str):
    """Compute circular hue distance and chroma excess for green, magenta, or blue screens."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    if key_color == "green":
        excess = g - np.maximum(r, b)
        target_hue = 120.0
    elif key_color == "magenta":
        excess = np.minimum(r, b) - g
        target_hue = 300.0
    elif key_color == "blue":
        excess = b - np.maximum(r, g)
        target_hue = 240.0
    else:
        raise ValueError(f"Unsupported key_color: {key_color}")
    raw_d = np.abs(h_deg - target_hue)
    hue_dist = np.minimum(raw_d, 360.0 - raw_d)
    return excess, hue_dist


def _despill_chroma(rgb: np.ndarray, excess: np.ndarray, near_edge_mask: np.ndarray, key_color: str) -> np.ndarray:
    """Remove key-color spill near matte edges while restoring perceived luminance."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    if key_color == "green":
        g_target = 0.50 * r + 0.50 * b
        spill_raw = np.maximum(g - np.maximum(r, b) * 0.96, 0.0)
        strength = np.where(near_edge_mask, np.clip(spill_raw * 6.5, 0.0, 1.0), np.clip((excess - 0.005) * 8.0, 0.0, 1.0))
        g_new = g * (1.0 - strength) + np.minimum(g, g_target) * strength
        removed = np.maximum(g - g_new, 0.0)
        lum_boost = removed * 0.35
        r_new = np.clip(r + lum_boost * np.where(r >= b, 0.65, 0.35), 0.0, 1.0)
        b_new = np.clip(b + lum_boost * np.where(b >= r, 0.65, 0.35), 0.0, 1.0)
        return np.dstack([r_new, np.clip(g_new, 0.0, 1.0), b_new])

    if key_color == "blue":
        b_target = 0.50 * r + 0.50 * g
        spill_raw = np.maximum(b - np.maximum(r, g) * 0.96, 0.0)
        strength = np.where(near_edge_mask, np.clip(spill_raw * 6.5, 0.0, 1.0), np.clip((excess - 0.005) * 8.0, 0.0, 1.0))
        b_new = b * (1.0 - strength) + np.minimum(b, b_target) * strength
        removed = np.maximum(b - b_new, 0.0)
        lum_boost = removed * 0.35
        r_new = np.clip(r + lum_boost * np.where(r >= g, 0.65, 0.35), 0.0, 1.0)
        g_new = np.clip(g + lum_boost * np.where(g >= r, 0.65, 0.35), 0.0, 1.0)
        return np.dstack([r_new, g_new, np.clip(b_new, 0.0, 1.0)])

    # Magenta despill: clamp R and B excess above G proportionally, restoring perceived luma into G
    spill_raw = np.maximum(np.minimum(r, b) - g * 0.96, 0.0)
    strength = np.where(near_edge_mask, np.clip(spill_raw * 6.5, 0.0, 1.0), np.clip((excess - 0.005) * 8.0, 0.0, 1.0))
    r_new = r * (1.0 - strength) + np.minimum(r, g) * strength
    b_new = b * (1.0 - strength) + np.minimum(b, g) * strength
    removed = 0.5 * (np.maximum(r - r_new, 0.0) + np.maximum(b - b_new, 0.0))
    g_new = np.clip(g + removed * 0.35, 0.0, 1.0)
    return np.dstack([np.clip(r_new, 0.0, 1.0), g_new, np.clip(b_new, 0.0, 1.0)])


def chroma_matte(img_path: Path, key_color: str = "green", is_frame: bool = False) -> np.ndarray:
    """Extract clean RGBA uint8 image from a green, magenta, or blue chroma-keyed JPG/PNG."""
    bgr = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(f"Could not read {img_path}")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h_deg = hsv[..., 0].astype(np.float32) * 2.0
    s_norm = hsv[..., 1].astype(np.float32) / 255.0
    v_norm = hsv[..., 2].astype(np.float32) / 255.0

    excess, hue_dist = _chroma_metrics(rgb, h_deg, key_color)
    in_key_hue = (hue_dist < 44.0) & (s_norm > 0.25) & (v_norm > 0.20)
    in_pure_key_hue = (hue_dist < 28.0) & (s_norm > 0.62) & (v_norm > 0.32)

    cand_bg = ((excess > 0.11) & in_key_hue) | (excess > 0.22)
    h, w = cand_bg.shape
    flood = cand_bg.astype(np.uint8) * 255
    mask = np.zeros((h + 2, w + 2), np.uint8)
    for x in range(w):
        if flood[0, x] == 255:
            cv2.floodFill(flood, mask, (x, 0), 128)
        if flood[h - 1, x] == 255:
            cv2.floodFill(flood, mask, (x, h - 1), 128)
    for y in range(h):
        if flood[y, 0] == 255:
            cv2.floodFill(flood, mask, (0, y), 128)
        if flood[y, w - 1] == 255:
            cv2.floodFill(flood, mask, (w - 1, y), 128)

    border_bg = flood == 128
    enclosed_thresh = 0.20 if is_frame else 0.32
    enclosed_bg = (excess > enclosed_thresh) & in_pure_key_hue
    definite_bg = border_bg | enclosed_bg

    bg_u8 = definite_bg.astype(np.uint8) * 255
    kernel_dil = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    kernel_ero = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    outer_bg = cv2.erode(bg_u8, kernel_ero) > 127
    near_edge_fg = (cv2.dilate(bg_u8, kernel_dil) > 127) & (~definite_bg)
    transition_band = (definite_bg & (~outer_bg)) | near_edge_fg

    low_t, high_t = 0.015, 0.16
    hue_w = np.clip(1.0 - hue_dist / 48.0, 0.0, 1.0) * np.clip((s_norm - 0.18) / 0.30, 0.0, 1.0)
    chroma_score = np.clip((excess - low_t) / (high_t - low_t), 0.0, 1.0) * (0.4 + 0.6 * hue_w)
    soft_alpha = 1.0 - chroma_score

    alpha = np.ones((h, w), dtype=np.float32)
    alpha[outer_bg] = 0.0
    alpha[transition_band] = soft_alpha[transition_band]
    alpha = np.clip(alpha, 0.0, 1.0)
    alpha = remove_small_speckles(alpha, min_area=24 if is_frame else 40)

    if not is_frame:
        sheer_bleed = (~definite_bg) & (excess > 0.03) & (hue_dist < 40.0)
        alpha = np.where(sheer_bleed, alpha * np.clip(1.0 - 0.72 * excess, 0.25, 1.0), alpha)

    alpha = cv2.GaussianBlur(alpha, (3, 3), 0.45)
    alpha[outer_bg] = 0.0

    near_edge_mask = cv2.dilate(bg_u8, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))) > 127
    rgb_despilled = _despill_chroma(rgb, excess, near_edge_mask, key_color)
    rgb_final = extrapolate_fringe_rgb(rgb_despilled, alpha)

    return np.dstack([
        np.clip(rgb_final * 255.0, 0, 255),
        np.clip(alpha[..., None] * 255.0, 0, 255),
    ]).astype(np.uint8)


def matte_single_layer(img_path: Path, key_mode_cfg: str, is_frame: bool) -> tuple[np.ndarray, str]:
    mode = detect_key_mode(img_path) if key_mode_cfg == "auto" else key_mode_cfg
    if mode == "rgba":
        return extract_native_rgba(img_path, is_frame=is_frame), mode
    return chroma_matte(img_path, key_color=mode, is_frame=is_frame), mode


def make_checker_preview(mid_rgba: np.ndarray, fg_rgba: np.ndarray) -> Image.Image:
    """Render split dark-navy / light-gray checkerboard inspection sheet."""
    mid_pil = Image.fromarray(mid_rgba, "RGBA").resize((576, 768), Image.Resampling.LANCZOS)
    fg_pil = Image.fromarray(fg_rgba, "RGBA").resize((576, 768), Image.Resampling.LANCZOS)
    pw, ph = 576, 768
    sq = 24
    yy, xx = np.mgrid[0:ph, 0:pw]
    pat = ((xx // sq) + (yy // sq)) % 2
    dark_bg = np.where(pat[..., None] == 0, np.array([16, 22, 38], np.uint8), np.array([28, 36, 58], np.uint8))
    light_bg = np.where(pat[..., None] == 0, np.array([210, 214, 222], np.uint8), np.array([235, 238, 244], np.uint8))
    split_bg = np.where((xx < pw // 2)[..., None], dark_bg, light_bg)
    bg_pil = Image.fromarray(split_bg, "RGB").convert("RGBA")

    sheet = Image.new("RGB", (pw * 2, ph), (15, 18, 28))
    sheet.paste(Image.alpha_composite(bg_pil, mid_pil).convert("RGB"), (0, 0))
    sheet.paste(Image.alpha_composite(bg_pil, fg_pil).convert("RGB"), (pw, 0))
    return sheet


def main():
    parser = argparse.ArgumentParser(description="Matte mid & fg card layers cleanly to RGBA.")
    parser.add_argument("--workdir", required=True, type=Path, help="Project workspace containing 01_raw_layers/")
    parser.add_argument("--key-color", default="auto", choices=["auto", "rgba", "green", "magenta", "blue"])
    args = parser.parse_args()

    workdir = args.workdir.resolve()
    raw_dir = workdir / "01_raw_layers"
    mat_dir = workdir / "02_matted"
    proc_dir = workdir / "03_processed"
    mat_dir.mkdir(parents=True, exist_ok=True)
    proc_dir.mkdir(parents=True, exist_ok=True)

    cfg = {}
    cfg_path = workdir / "card_config.json"
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    key_cfg = args.key_color if args.key_color != "auto" else str(cfg.get("key_color", "auto")).lower()

    mid_path = find_layer(raw_dir, ["mid", "mid_2k", "subject", "character"])
    if mid_path is None:
        raise FileNotFoundError(f"Could not find mid layer in {raw_dir} (expected mid.png/.jpg/.webp)")

    fg_path = find_layer(raw_dir, ["fg", "fg_2k", "frame", "border"])
    if fg_path is None:
        fg_path = resolve_fallback_frame(cfg.get("fallback_frame"))
        print(f"No custom fg layer found in {raw_dir}; using built-in fallback frame: {fg_path.name}")

    mid_rgba, mid_mode = matte_single_layer(mid_path, key_cfg, is_frame=False)
    fg_rgba, fg_mode = matte_single_layer(fg_path, key_cfg, is_frame=True)

    mid_pil = Image.fromarray(mid_rgba, "RGBA")
    fg_pil = Image.fromarray(fg_rgba, "RGBA")
    mid_pil.save(mat_dir / "mid_rgba.png")
    fg_pil.save(mat_dir / "fg_rgba.png")

    black_bg = Image.new("RGBA", mid_pil.size, (0, 0, 0, 255))
    mid_on_black = Image.alpha_composite(black_bg, mid_pil).convert("RGB")
    mid_on_black.save(mat_dir / "mid_on_black.png")

    preview = make_checker_preview(mid_rgba, fg_rgba)
    preview.save(proc_dir / "cutout_check.png")
    print(f"Matte complete: mid={mid_path.name}[{mid_mode}] {mid_pil.size}, fg={fg_path.name}[{fg_mode}] {fg_pil.size}")


if __name__ == "__main__":
    main()
