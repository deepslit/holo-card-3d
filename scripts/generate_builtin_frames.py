"""Generate 3 crisp, anti-aliased 1200x1600 RGBA fallback collector-card frames into resources/frames/."""
import sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

W, H = 1200, 1600
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "frames"


def smoothstep(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def sd_rounded_box(px: np.ndarray, py: np.ndarray, hw: float, hh: float, r: float) -> np.ndarray:
    qx = np.abs(px) - (hw - r)
    qy = np.abs(py) - (hh - r)
    return np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0)) + np.minimum(np.maximum(qx, qy), 0.0) - r


def sd_diamond_star(px: np.ndarray, py: np.ndarray, cx: float, cy: float, rx: float, ry: float, pinch: float = 0.45) -> np.ndarray:
    dx = np.abs(px - cx) / max(rx, 1e-4)
    dy = np.abs(py - cy) / max(ry, 1e-4)
    d_norm = np.power(dx + 1e-6, pinch) + np.power(dy + 1e-6, pinch) - 1.0
    return d_norm * min(rx, ry) * 0.42


def subtle_brushed_noise(seed: int = 42, scale: float = 0.016) -> np.ndarray:
    """Directional micro-brushed metal grain without visible striped moire."""
    rng = np.random.default_rng(seed)
    n = rng.normal(0.0, 1.0, (H // 2, W // 2)).astype(np.float32)
    n_up = cv2.resize(n, (W, H), interpolation=cv2.INTER_LINEAR)
    # Directional blur along diagonal/horizontal brush angle
    k = np.zeros((7, 7), dtype=np.float32)
    for i in range(7):
        k[i, i] = 1.0 / 7.0
    brushed = cv2.filter2D(n_up, -1, k)
    return 1.0 + np.clip(brushed, -1.5, 1.5) * scale


def shade_metallic_relief(height: np.ndarray, alpha: np.ndarray, base_col: np.ndarray, hi_col: np.ndarray, dark_col: np.ndarray, gloss: float = 0.72) -> np.ndarray:
    gx = cv2.Sobel(height.astype(np.float32), cv2.CV_32F, 1, 0, ksize=5) / 8.0
    gy = cv2.Sobel(height.astype(np.float32), cv2.CV_32F, 0, 1, ksize=5) / 8.0
    nx = -gx * 2.5
    ny = -gy * 2.5
    nz = np.ones_like(nx)
    nlen = np.sqrt(nx * nx + ny * ny + nz * nz) + 1e-5
    nx /= nlen
    ny /= nlen
    nz /= nlen

    light = np.array([-0.42, -0.58, 0.70], dtype=np.float32)
    light /= np.linalg.norm(light)
    half_v = light + np.array([0.0, 0.0, 1.0], dtype=np.float32)
    half_v /= np.linalg.norm(half_v)

    ndotl = np.clip(nx * light[0] + ny * light[1] + nz * light[2], 0.0, 1.0)
    ndoth = np.clip(nx * half_v[0] + ny * half_v[1] + nz * half_v[2], 0.0, 1.0)

    rgb = (
        dark_col[None, None, :] * (1.0 - height[..., None]) * 0.52
        + base_col[None, None, :] * (0.50 + 0.56 * ndotl[..., None])
        + hi_col[None, None, :] * (gloss * np.power(ndoth, 20.0)[..., None])
    )
    rgb = np.clip(rgb, 0.0, 1.0)
    rgba = np.dstack([rgb, np.clip(alpha, 0.0, 1.0)]) * 255.0
    return rgba.astype(np.uint8)


def build_classic_sar_gold(px: np.ndarray, py: np.ndarray) -> np.ndarray:
    hw, hh = W * 0.5, H * 0.5
    sd_outer = sd_rounded_box(px, py, hw + 4.0, hh + 4.0, 56.0)
    sd_inner_main = sd_rounded_box(px, py, hw - 44.0, hh - 44.0, 38.0)

    # Smooth convex bevel perimeter border + inner crisp filigree trim line
    band_main = np.maximum(sd_outer, -sd_inner_main)
    alpha_main = 1.0 - smoothstep(-1.2, 1.2, band_main)

    sd_hair_out = sd_rounded_box(px, py, hw - 56.0, hh - 56.0, 33.0)
    sd_hair_in = sd_rounded_box(px, py, hw - 62.0, hh - 62.0, 30.0)
    alpha_hair = 1.0 - smoothstep(-1.0, 1.0, np.maximum(sd_hair_out, -sd_hair_in))

    # Crisp corner L-plates + circular filigree rings + concave 4-point star medallions
    cx_off, cy_off = hw - 54.0, hh - 54.0
    sd_corner = np.full((H, W), 999.0, dtype=np.float32)
    sd_stars = np.full((H, W), 999.0, dtype=np.float32)
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            d_ring = np.abs(np.hypot(px - sx * cx_off, py - sy * cy_off) - 24.0) - 4.0
            d_shield = np.hypot(px - sx * (hw - 36.0), py - sy * (hh - 36.0)) - 34.0
            sd_corner = np.minimum(sd_corner, np.minimum(d_shield, d_ring))
            d_star = sd_diamond_star(px, py, sx * cx_off, sy * cy_off, 25.0, 25.0, 0.48)
            sd_stars = np.minimum(sd_stars, d_star)

    # Delicate side midpoint diamond studs + top/bottom crest diamonds
    for sy in (-1.0, 1.0):
        d_crest_base = sd_diamond_star(px, py, 0.0, sy * (hh - 34.0), 44.0, 22.0, 0.68)
        sd_corner = np.minimum(sd_corner, d_crest_base)
        d_crest_gem = sd_diamond_star(px, py, 0.0, sy * (hh - 34.0), 26.0, 13.0, 0.52)
        sd_stars = np.minimum(sd_stars, d_crest_gem)
    for sx in (-1.0, 1.0):
        d_side_stud = sd_diamond_star(px, py, sx * (hw - 22.0), 0.0, 12.0, 24.0, 0.56)
        sd_stars = np.minimum(sd_stars, d_side_stud)

    alpha_corner = (1.0 - smoothstep(-1.2, 1.2, sd_corner)) * (1.0 - smoothstep(-1.2, 1.2, sd_outer))
    alpha_stars = (1.0 - smoothstep(-1.1, 1.1, sd_stars)) * (1.0 - smoothstep(-1.2, 1.2, sd_outer))
    alpha = np.maximum(np.maximum(alpha_main, alpha_hair), np.maximum(alpha_corner, alpha_stars))

    # Smooth convex pillow profile across border width (no diagonal stripe noise!)
    profile = 1.0 - np.abs(np.clip(-sd_inner_main / 44.0, 0.0, 1.0) * 2.0 - 1.0)
    h_main = (0.36 + 0.56 * smoothstep(0.0, 1.0, profile)) * alpha_main
    h_hair = 0.68 * alpha_hair
    h_corner = (0.62 + 0.30 * smoothstep(-14.0, 0.0, -sd_corner)) * alpha_corner
    h_stars = (0.96 - 0.16 * smoothstep(-10.0, 0.0, sd_stars)) * alpha_stars
    height = np.maximum(np.maximum(h_main, h_hair), np.maximum(h_corner, h_stars))

    rgba = shade_metallic_relief(
        height,
        alpha,
        base_col=np.array([0.85, 0.68, 0.34], np.float32),
        hi_col=np.array([1.00, 0.96, 0.78], np.float32),
        dark_col=np.array([0.36, 0.25, 0.10], np.float32),
        gloss=0.80,
    )
    rgb_f = rgba[..., :3].astype(np.float32) / 255.0
    pearl = np.array([0.98, 0.98, 1.00], np.float32)
    gem_mix = (alpha_stars * 0.45)[..., None]
    rgb_f = np.clip(rgb_f * (1.0 - gem_mix) + pearl[None, None, :] * gem_mix, 0.0, 1.0)
    rgb_f *= subtle_brushed_noise(seed=101, scale=0.014)[..., None]
    rgba[..., :3] = np.clip(rgb_f * 255.0, 0, 255).astype(np.uint8)
    return rgba


def build_minimal_platinum(px: np.ndarray, py: np.ndarray) -> np.ndarray:
    hw, hh = W * 0.5, H * 0.5
    sd_outer = sd_rounded_box(px, py, hw + 4.0, hh + 4.0, 54.0)
    sd_inner = sd_rounded_box(px, py, hw - 36.0, hh - 36.0, 38.0)
    band_main = np.maximum(sd_outer, -sd_inner)
    alpha_main = 1.0 - smoothstep(-1.2, 1.2, band_main)

    sd_line_out = sd_rounded_box(px, py, hw - 48.0, hh - 48.0, 33.0)
    sd_line_in = sd_rounded_box(px, py, hw - 53.0, hh - 53.0, 31.0)
    alpha_line = 1.0 - smoothstep(-1.0, 1.0, np.maximum(sd_line_out, -sd_line_in))

    sd_studs = np.full((H, W), 999.0, dtype=np.float32)
    sd_tabs = np.full((H, W), 999.0, dtype=np.float32)
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            d_box = sd_rounded_box(px - sx * (hw - 32.0), py - sy * (hh - 32.0), 42.0, 42.0, 14.0)
            d_cut = sd_rounded_box(px - sx * (hw - 62.0), py - sy * (hh - 62.0), 30.0, 30.0, 9.0)
            sd_tabs = np.minimum(sd_tabs, np.maximum(d_box, -d_cut))
            d_stud = np.hypot(px - sx * (hw - 26.0), py - sy * (hh - 26.0)) - 6.5
            sd_studs = np.minimum(sd_studs, d_stud)

    alpha_tabs = (1.0 - smoothstep(-1.2, 1.2, sd_tabs)) * (1.0 - smoothstep(-1.2, 1.2, sd_outer))
    alpha_studs = (1.0 - smoothstep(-1.0, 1.0, sd_studs)) * (1.0 - smoothstep(-1.2, 1.2, sd_outer))
    alpha = np.maximum(np.maximum(alpha_main, alpha_line), np.maximum(alpha_tabs, alpha_studs))

    profile = 1.0 - np.abs(np.clip(-sd_inner / 36.0, 0.0, 1.0) * 2.0 - 1.0)
    h_main = (0.38 + 0.54 * smoothstep(0.0, 1.0, profile)) * alpha_main
    h_line = 0.72 * alpha_line
    h_tabs = (0.76 + 0.18 * smoothstep(-14.0, 0.0, -sd_tabs)) * alpha_tabs
    h_studs = (0.96 - 0.14 * np.clip((sd_studs + 6.5) / 6.5, 0.0, 1.0)) * alpha_studs
    height = np.maximum(np.maximum(h_main, h_line), np.maximum(h_tabs, h_studs))

    rgba = shade_metallic_relief(
        height,
        alpha,
        base_col=np.array([0.76, 0.82, 0.90], np.float32),
        hi_col=np.array([0.97, 0.99, 1.00], np.float32),
        dark_col=np.array([0.28, 0.34, 0.44], np.float32),
        gloss=0.84,
    )
    rgb_f = rgba[..., :3].astype(np.float32) / 255.0
    rgb_f *= subtle_brushed_noise(seed=202, scale=0.012)[..., None]
    rgba[..., :3] = np.clip(rgb_f * 255.0, 0, 255).astype(np.uint8)
    return rgba


def build_cyber_hud_frame(px: np.ndarray, py: np.ndarray) -> np.ndarray:
    hw, hh = W * 0.5, H * 0.5
    sd_outer = sd_rounded_box(px, py, hw + 4.0, hh + 4.0, 48.0)
    sd_inner = sd_rounded_box(px, py, hw - 44.0, hh - 44.0, 28.0)
    band_main = np.maximum(sd_outer, -sd_inner)
    alpha_main = 1.0 - smoothstep(-1.2, 1.2, band_main)

    ax = np.abs(px)
    ay = np.abs(py)
    diag = (ax - (hw - 120.0)) + (ay - (hh - 120.0))
    d_armor = np.maximum(sd_rounded_box(px, py, hw - 2.0, hh - 2.0, 44.0), -sd_rounded_box(px, py, hw - 66.0, hh - 66.0, 22.0))
    sd_armor = np.maximum(d_armor, -(-diag + 118.0))
    alpha_armor = 1.0 - smoothstep(-1.2, 1.2, sd_armor)

    d_top_bar = sd_rounded_box(px, py - (hh - 24.0), 170.0, 11.0, 5.0)
    d_bot_bar = sd_rounded_box(px, py + (hh - 24.0), 170.0, 11.0, 5.0)
    alpha_bars = 1.0 - smoothstep(-1.0, 1.0, np.minimum(d_top_bar, d_bot_bar))

    d_neon_strip = np.abs(sd_inner + 6.0) - 2.5
    # Keep precision scale ticks strictly outside corner brackets and center HUD bars
    tick_h = (np.sin(px * 0.19) > 0.88) & (ay > hh - 36.0) & (ay < hh - 10.0) & (ax > 205.0) & (ax < hw - 150.0)
    tick_v = (np.sin(py * 0.19) > 0.88) & (ax > hw - 36.0) & (ax < hw - 10.0) & (ay < hh - 150.0)
    tick_rep = tick_h | tick_v
    alpha_neon = (1.0 - smoothstep(-0.9, 0.9, d_neon_strip)) * (0.65 + 0.35 * (alpha_armor > 0.2))
    alpha_ticks = np.where(tick_rep, 0.85, 0.0).astype(np.float32) * alpha_main

    alpha = np.maximum(np.maximum(alpha_main, alpha_armor), np.maximum(alpha_bars, alpha_neon))

    h_main = smoothstep(0.0, 18.0, -band_main) * 0.58 * alpha_main
    h_armor = (0.72 + 0.24 * smoothstep(-16.0, 0.0, -sd_armor)) * alpha_armor
    h_bars = 0.82 * alpha_bars
    height = np.maximum(np.maximum(h_main, h_armor), h_bars)

    rgba = shade_metallic_relief(
        height,
        alpha,
        base_col=np.array([0.24, 0.30, 0.40], np.float32),
        hi_col=np.array([0.74, 0.92, 1.00], np.float32),
        dark_col=np.array([0.09, 0.12, 0.18], np.float32),
        gloss=0.72,
    )
    rgb_f = rgba[..., :3].astype(np.float32) / 255.0
    cyan = np.array([0.32, 0.95, 1.00], np.float32)
    glow = np.clip(alpha_neon * 0.92 + alpha_ticks * 0.72 + alpha_bars * 0.52 * (np.abs(px) < 115.0), 0.0, 1.0)[..., None]
    rgb_f = np.clip(rgb_f * (1.0 - 0.65 * glow) + cyan[None, None, :] * glow, 0.0, 1.0)
    rgba[..., :3] = np.clip(rgb_f * 255.0, 0, 255).astype(np.uint8)
    return rgba


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    yy, xx = np.mgrid[0:H, 0:W]
    px = xx.astype(np.float32) - W * 0.5
    py = yy.astype(np.float32) - H * 0.5

    specs = [
        ("classic_sar_gold.png", build_classic_sar_gold),
        ("minimal_platinum.png", build_minimal_platinum),
        ("cyber_hud_frame.png", build_cyber_hud_frame),
    ]

    previews = []
    sq = 24
    pat = ((xx // sq) + (yy // sq)) % 2
    chk = np.where(pat[..., None] == 0, np.array([22, 28, 44], np.uint8), np.array([34, 42, 64], np.uint8))
    chk_pil = Image.fromarray(chk, "RGB").convert("RGBA")

    for fname, builder in specs:
        rgba = builder(px, py)
        center_clear = float(np.mean(rgba[200:1400, 150:1050, 3] == 0))
        img = Image.fromarray(rgba, "RGBA")
        out_path = OUT_DIR / fname
        img.save(out_path, optimize=True)
        print(f"Generated {out_path} ({out_path.stat().st_size / 1024:.1f} KB, center_transparent={center_clear:.3f})")
        comp = Image.alpha_composite(chk_pil, img).convert("RGB").resize((360, 480), Image.Resampling.LANCZOS)
        previews.append(comp)

    sheet = Image.new("RGB", (360 * len(previews), 480), (14, 18, 28))
    for i, p in enumerate(previews):
        sheet.paste(p, (i * 360, 0))
    sheet_path = OUT_DIR / "_frames_preview.png"
    sheet.save(sheet_path)
    print(f"Saved preview sheet: {sheet_path}")


if __name__ == "__main__":
    main()
