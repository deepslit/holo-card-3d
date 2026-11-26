"""Generate the 8 crisp, anti-aliased 1200x1600 RGBA built-in collector-card frames into assets/frames/."""
import math
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


def build_full_art_glass(px: np.ndarray, py: np.ndarray) -> np.ndarray:
    """Ultra-minimal crystal acrylic/glass bevel edge with tiny corner micro-pins (>92% open art area)."""
    hw, hh = W * 0.5, H * 0.5
    sd_outer = sd_rounded_box(px, py, hw + 4.0, hh + 4.0, 54.0)
    sd_inner = sd_rounded_box(px, py, hw - 18.0, hh - 18.0, 40.0)
    band_main = np.maximum(sd_outer, -sd_inner)
    alpha_rim = (1.0 - smoothstep(-1.2, 1.2, band_main)) * 0.78

    sd_hair_out = sd_rounded_box(px, py, hw - 26.0, hh - 26.0, 35.0)
    sd_hair_in = sd_rounded_box(px, py, hw - 29.0, hh - 29.0, 33.5)
    alpha_hair = (1.0 - smoothstep(-0.9, 0.9, np.maximum(sd_hair_out, -sd_hair_in))) * 0.52

    sd_pins = np.full((H, W), 999.0, dtype=np.float32)
    sd_pin_rings = np.full((H, W), 999.0, dtype=np.float32)
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            d_c = np.hypot(px - sx * (hw - 42.0), py - sy * (hh - 42.0))
            sd_pins = np.minimum(sd_pins, d_c - 6.0)
            sd_pin_rings = np.minimum(sd_pin_rings, np.abs(d_c - 11.5) - 1.4)

    alpha_pins = 1.0 - smoothstep(-0.9, 0.9, sd_pins)
    alpha_rings = (1.0 - smoothstep(-0.9, 0.9, sd_pin_rings)) * 0.65
    alpha = np.clip(np.maximum(np.maximum(alpha_rim, alpha_hair), np.maximum(alpha_pins, alpha_rings)), 0.0, 1.0)

    profile = 1.0 - np.abs(np.clip(-sd_inner / 18.0, 0.0, 1.0) * 2.0 - 1.0)
    h_rim = (0.45 + 0.48 * smoothstep(0.0, 1.0, profile)) * (alpha_rim > 0.01)
    h_hair = 0.72 * (alpha_hair > 0.01)
    h_pins = (0.94 - 0.18 * np.clip((sd_pins + 6.0) / 6.0, 0.0, 1.0)) * alpha_pins
    height = np.maximum(np.maximum(h_rim, h_hair), h_pins)

    rgba = shade_metallic_relief(
        height,
        alpha,
        base_col=np.array([0.84, 0.89, 0.95], np.float32),
        hi_col=np.array([1.00, 1.00, 1.00], np.float32),
        dark_col=np.array([0.38, 0.44, 0.54], np.float32),
        gloss=0.92,
    )
    return rgba


def build_baroque_arch(px: np.ndarray, py: np.ndarray) -> np.ndarray:
    """Art Nouveau / Mucha elliptical arch collector frame with carved spandrel filigree."""
    hw, hh = W * 0.5, H * 0.5
    sd_outer = sd_rounded_box(px, py, hw + 4.0, hh + 4.0, 54.0)

    # Graceful shallow Roman/elliptical top arch (dips only ~220px at corners so head/hair/wings never clip)
    arch_w = hw - 48.0  # 552px half-width
    arch_h = 225.0      # shallow arch rise
    arch_spring_y = -hh + 56.0 + arch_h
    ex = px / arch_w
    ey = (py - arch_spring_y) / arch_h
    sd_ell = (np.hypot(ex, ey) - 1.0) * min(arch_w, arch_h)
    sd_rect_ap = sd_rounded_box(px, py - 24.0, arch_w, hh - 72.0, 34.0)
    sd_ap = np.where(py < arch_spring_y, np.maximum(sd_ell, np.abs(px) - arch_w), sd_rect_ap)

    band_main = np.maximum(sd_outer, -sd_ap)
    alpha_main = 1.0 - smoothstep(-1.2, 1.2, band_main)

    # Crisp inner filigree double rail tracing the arch contour
    in_card = 1.0 - smoothstep(-1.2, 1.2, sd_outer)
    sd_rail_1 = np.abs(sd_ap + 14.0) - 2.8
    sd_rail_2 = np.abs(sd_ap - 11.0) - 2.0
    alpha_rail1 = (1.0 - smoothstep(-1.0, 1.0, sd_rail_1)) * in_card
    alpha_rail2 = (1.0 - smoothstep(-1.0, 1.0, sd_rail_2)) * in_card

    # Upper spandrel celestial rings, filigree arcs & concave 4-point star medallions
    sd_orn = np.full((H, W), 999.0, dtype=np.float32)
    sd_gems = np.full((H, W), 999.0, dtype=np.float32)
    for sx in (-1.0, 1.0):
        cx_u, cy_u = sx * (hw - 72.0), -hh + 72.0
        d_ru = np.hypot(px - cx_u, py - cy_u)
        sd_orn = np.minimum(sd_orn, np.abs(d_ru - 36.0) - 3.6)
        sd_orn = np.minimum(sd_orn, np.abs(d_ru - 22.0) - 2.2)
        sd_gems = np.minimum(sd_gems, sd_diamond_star(px, py, cx_u, cy_u, 22.0, 22.0, 0.45))
        # Secondary corner filigree curl
        cx_u2, cy_u2 = sx * (hw - 140.0), -hh + 44.0
        sd_gems = np.minimum(sd_gems, sd_diamond_star(px, py, cx_u2, cy_u2, 14.0, 14.0, 0.48))
        # Lower corner rosettes
        cx_b, cy_b = sx * (hw - 54.0), hh - 54.0
        d_rb = np.hypot(px - cx_b, py - cy_b)
        sd_orn = np.minimum(sd_orn, np.abs(d_rb - 22.0) - 3.2)
        sd_gems = np.minimum(sd_gems, sd_diamond_star(px, py, cx_b, cy_b, 18.0, 18.0, 0.48))

    # Top apex crown star & bottom crest diamond
    sd_orn = np.minimum(sd_orn, sd_diamond_star(px, py, 0.0, -hh + 34.0, 48.0, 20.0, 0.65))
    sd_gems = np.minimum(sd_gems, sd_diamond_star(px, py, 0.0, -hh + 34.0, 26.0, 15.0, 0.46))
    sd_orn = np.minimum(sd_orn, sd_diamond_star(px, py, 0.0, hh - 32.0, 52.0, 22.0, 0.66))
    sd_gems = np.minimum(sd_gems, sd_diamond_star(px, py, 0.0, hh - 32.0, 28.0, 12.0, 0.50))

    alpha_orn = (1.0 - smoothstep(-1.1, 1.1, sd_orn)) * in_card
    alpha_gems = (1.0 - smoothstep(-1.0, 1.0, sd_gems)) * in_card
    alpha = np.maximum(np.maximum(alpha_main, np.maximum(alpha_rail1, alpha_rail2)), np.maximum(alpha_orn, alpha_gems))

    # Sculpted convex arch molding + recessed satin spandrels so filigree gleams cleanly
    edge_d = np.clip(-sd_ap / 44.0, 0.0, 1.0)
    h_main = (0.36 + 0.52 * smoothstep(0.0, 1.0, 1.0 - np.abs(edge_d * 2.0 - 1.0))) * alpha_main
    spandrel = (sd_ap > 32.0) & (py < arch_spring_y)
    h_main = np.where(spandrel, 0.24 * alpha_main, h_main)
    h_rails = np.maximum(0.86 * alpha_rail1, 0.72 * alpha_rail2)
    h_orn = 0.88 * alpha_orn
    h_gems = (0.98 - 0.14 * smoothstep(-10.0, 0.0, sd_gems)) * alpha_gems
    height = np.maximum(np.maximum(h_main, h_rails), np.maximum(h_orn, h_gems))

    rgba = shade_metallic_relief(
        height,
        alpha,
        base_col=np.array([0.76, 0.76, 0.79], np.float32),
        hi_col=np.array([1.00, 1.00, 1.00], np.float32),
        dark_col=np.array([0.24, 0.25, 0.30], np.float32),
        gloss=0.86,
    )
    rgb_f = rgba[..., :3].astype(np.float32) / 255.0
    rgb_f *= subtle_brushed_noise(seed=303, scale=0.013)[..., None]
    rgba[..., :3] = np.clip(rgb_f * 255.0, 0, 255).astype(np.uint8)
    return rgba


def build_eastern_ink(px: np.ndarray, py: np.ndarray) -> np.ndarray:
    """Traditional Eastern begonia-corner (海棠角) & key-fret lattice frame in neutral silver relief."""
    hw, hh = W * 0.5, H * 0.5
    sd_outer = sd_rounded_box(px, py, hw + 4.0, hh + 4.0, 50.0)

    # Inner aperture with concave begonia corners (subtract corner circles from inner box)
    iw, ih = hw - 44.0, hh - 44.0
    sd_box = sd_rounded_box(px, py, iw, ih, 10.0)
    corner_cut = np.full((H, W), 999.0, dtype=np.float32)
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            d_c = np.hypot(px - sx * iw, py - sy * ih) - 56.0
            corner_cut = np.minimum(corner_cut, d_c)
    sd_ap = np.maximum(sd_box, -corner_cut)

    band_main = np.maximum(sd_outer, -sd_ap)
    alpha_main = 1.0 - smoothstep(-1.2, 1.2, band_main)

    # Fine double inner fret rail tracing the begonia window
    sd_inner_line = np.abs(sd_ap - 11.0) - 2.3
    sd_outer_line = np.abs(sd_ap + 14.0) - 2.2
    in_card = 1.0 - smoothstep(-1.2, 1.2, sd_outer)
    alpha_l1 = (1.0 - smoothstep(-1.0, 1.0, sd_inner_line)) * in_card
    alpha_l2 = (1.0 - smoothstep(-1.0, 1.0, sd_outer_line)) * in_card

    # Crisp corner fret squares + top/bottom cloud lozenge accents
    sd_orn = np.full((H, W), 999.0, dtype=np.float32)
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            cx_k, cy_k = sx * (hw - 42.0), sy * (hh - 42.0)
            d_sq1 = np.abs(sd_rounded_box(px - cx_k, py - cy_k, 20.0, 20.0, 3.0)) - 2.8
            d_sq2 = sd_rounded_box(px - cx_k, py - cy_k, 8.0, 8.0, 2.0)
            sd_orn = np.minimum(sd_orn, np.minimum(d_sq1, d_sq2))
    for sy in (-1.0, 1.0):
        d_bar = sd_rounded_box(px, py - sy * (hh - 23.0), 115.0, 6.0, 3.0)
        d_loz = sd_diamond_star(px, py, 0.0, sy * (hh - 23.0), 32.0, 13.0, 0.72)
        sd_orn = np.minimum(sd_orn, np.minimum(d_bar, d_loz))

    alpha_orn = (1.0 - smoothstep(-1.0, 1.0, sd_orn)) * in_card
    alpha = np.maximum(np.maximum(alpha_main, alpha_orn), np.maximum(alpha_l1, alpha_l2))

    profile = 1.0 - np.abs(np.clip(-sd_ap / 44.0, 0.0, 1.0) * 2.0 - 1.0)
    h_main = (0.36 + 0.50 * smoothstep(0.0, 1.0, profile)) * alpha_main
    h_lines = np.maximum(0.76 * alpha_l1, 0.84 * alpha_l2)
    h_orn = 0.90 * alpha_orn
    height = np.maximum(np.maximum(h_main, h_lines), h_orn)

    rgba = shade_metallic_relief(
        height,
        alpha,
        base_col=np.array([0.80, 0.80, 0.78], np.float32),
        hi_col=np.array([0.99, 0.99, 0.98], np.float32),
        dark_col=np.array([0.28, 0.28, 0.30], np.float32),
        gloss=0.76,
    )
    rgb_f = rgba[..., :3].astype(np.float32) / 255.0
    rgb_f *= subtle_brushed_noise(seed=404, scale=0.015)[..., None]
    rgba[..., :3] = np.clip(rgb_f * 255.0, 0, 255).astype(np.uint8)
    return rgba


def build_y2k_polaroid(px: np.ndarray, py: np.ndarray) -> np.ndarray:
    """Y2K chrome filmstrip / polaroid collector frame with sprocket notches & star studs."""
    hw, hh = W * 0.5, H * 0.5
    sd_outer = sd_rounded_box(px, py, hw + 4.0, hh + 4.0, 48.0)
    # Asymmetric clean gallery chin at bottom (96px) and crisp 44px top/sides
    sd_inner = sd_rounded_box(px, py + 26.0, hw - 46.0, hh - 70.0, 22.0)

    # Punch crisp filmstrip sprocket windows along left & right vertical rails
    sd_sprockets = np.full((H, W), 999.0, dtype=np.float32)
    for sx in (-1.0, 1.0):
        for sy_pos in np.linspace(-hh + 150.0, hh - 200.0, 11):
            d_sp = sd_rounded_box(px - sx * (hw - 23.0), py - float(sy_pos), 7.5, 16.0, 3.5)
            sd_sprockets = np.minimum(sd_sprockets, d_sp)

    band_main = np.maximum(sd_outer, -sd_inner)
    # Subtract sprocket cutouts slightly (keep subtle translucent recess instead of harsh hole)
    alpha_main = 1.0 - smoothstep(-1.2, 1.2, band_main)
    sprocket_mask = 1.0 - smoothstep(-1.0, 1.0, sd_sprockets)
    alpha_main = alpha_main * (1.0 - 0.72 * sprocket_mask)

    # Inner hairline chrome bezel + Y2K 4-point chrome stars on top-right & bottom-left
    sd_bezel = np.abs(sd_inner + 4.0) - 2.2
    alpha_bezel = 1.0 - smoothstep(-1.0, 1.0, sd_bezel)

    sd_stars = np.full((H, W), 999.0, dtype=np.float32)
    star_specs = [
        (hw - 58.0, -hh + 56.0, 26.0),
        (hw - 102.0, -hh + 44.0, 13.0),
        (-hw + 68.0, hh - 50.0, 28.0),
        (-hw + 114.0, hh - 42.0, 14.0),
        (hw - 68.0, hh - 50.0, 18.0),
    ]
    for cx_s, cy_s, r_s in star_specs:
        sd_stars = np.minimum(sd_stars, sd_diamond_star(px, py, cx_s, cy_s, r_s, r_s, 0.42))
    # Sleek bottom pill groove (minimal Y2K barcode/status bar accent)
    sd_pill = np.abs(sd_rounded_box(px, py - (hh - 48.0), 120.0, 10.0, 10.0)) - 2.2
    in_card = 1.0 - smoothstep(-1.2, 1.2, sd_outer)
    alpha_stars = (1.0 - smoothstep(-1.0, 1.0, np.minimum(sd_stars, sd_pill))) * in_card
    alpha = np.clip(np.maximum(np.maximum(alpha_main, alpha_bezel), alpha_stars), 0.0, 1.0)

    h_main = (0.48 + 0.34 * smoothstep(0.0, 14.0, -band_main)) * (alpha_main > 0.05)
    h_main = np.where(sprocket_mask > 0.3, h_main * 0.35, h_main)
    h_bezel = 0.84 * alpha_bezel
    h_stars = (0.98 - 0.14 * smoothstep(-10.0, 0.0, sd_stars)) * alpha_stars
    height = np.maximum(np.maximum(h_main, h_bezel), h_stars)

    rgba = shade_metallic_relief(
        height,
        alpha,
        base_col=np.array([0.84, 0.86, 0.90], np.float32),
        hi_col=np.array([1.00, 1.00, 1.00], np.float32),
        dark_col=np.array([0.30, 0.34, 0.42], np.float32),
        gloss=0.88,
    )
    rgb_f = rgba[..., :3].astype(np.float32) / 255.0
    rgb_f *= subtle_brushed_noise(seed=505, scale=0.011)[..., None]
    rgba[..., :3] = np.clip(rgb_f * 255.0, 0, 255).astype(np.uint8)
    return rgba


def build_gothic_spire(px: np.ndarray, py: np.ndarray) -> np.ndarray:
    """Dark cathedral pointed gothic arch frame with forged gunmetal-silver bevel & diamond rivets."""
    hw, hh = W * 0.5, H * 0.5
    sd_outer = sd_rounded_box(px, py, hw + 4.0, hh + 4.0, 48.0)

    # Pointed gothic lancet arch with apex cleanly framed at -hh + 62 and springing at -hh + 330
    arch_span = hw - 48.0  # 552px
    spring_y = -hh + 330.0
    c_g = 240.0
    r_g = arch_span + c_g
    y_scale = (spring_y - (-hh + 62.0)) / math.sqrt(r_g * r_g - c_g * c_g)
    py_s = (py - spring_y) / max(y_scale, 0.25)
    d_left = (np.hypot(px + c_g, py_s) - r_g) * y_scale
    d_right = (np.hypot(px - c_g, py_s) - r_g) * y_scale
    sd_lancet = np.maximum(d_left, d_right)
    sd_lower = sd_rounded_box(px, py - 24.0, arch_span, hh - 72.0, 20.0)
    sd_ap = np.where(py < spring_y, np.maximum(sd_lancet, np.abs(px) - arch_span), sd_lower)

    band_main = np.maximum(sd_outer, -sd_ap)
    alpha_main = 1.0 - smoothstep(-1.2, 1.2, band_main)

    # Double cathedral tracery ribs
    in_card = 1.0 - smoothstep(-1.2, 1.2, sd_outer)
    sd_rib1 = np.abs(sd_ap + 14.0) - 2.6
    sd_rib2 = np.abs(sd_ap - 11.0) - 2.0
    alpha_r1 = (1.0 - smoothstep(-1.0, 1.0, sd_rib1)) * in_card
    alpha_r2 = (1.0 - smoothstep(-1.0, 1.0, sd_rib2)) * in_card

    # Corner lancet diamonds & forged rivets along side borders
    sd_orn = np.full((H, W), 999.0, dtype=np.float32)
    sd_studs = np.full((H, W), 999.0, dtype=np.float32)
    for sx in (-1.0, 1.0):
        # Upper cathedral rose spandrel rings + spikes
        cx_u, cy_u = sx * (hw - 90.0), -hh + 96.0
        sd_orn = np.minimum(sd_orn, np.abs(np.hypot(px - cx_u, py - cy_u) - 34.0) - 3.2)
        sd_studs = np.minimum(sd_studs, sd_diamond_star(px, py, cx_u, cy_u, 22.0, 28.0, 0.44))
        # Bottom corner corner-shields
        sd_studs = np.minimum(sd_studs, sd_diamond_star(px, py, sx * (hw - 42.0), hh - 42.0, 20.0, 20.0, 0.50))
        # Forged rivets down the sides
        for ry_pos in (-220.0, 0.0, 220.0, 440.0):
            sd_studs = np.minimum(sd_studs, sd_diamond_star(px, py, sx * (hw - 22.0), ry_pos, 9.0, 16.0, 0.56))
    # Apex spire finial + bottom gothic crest
    sd_studs = np.minimum(sd_studs, sd_diamond_star(px, py, 0.0, -hh + 30.0, 18.0, 26.0, 0.42))
    sd_studs = np.minimum(sd_studs, sd_diamond_star(px, py, 0.0, hh - 30.0, 38.0, 16.0, 0.48))

    alpha_orn = (1.0 - smoothstep(-1.0, 1.0, sd_orn)) * in_card
    alpha_studs = (1.0 - smoothstep(-1.0, 1.0, sd_studs)) * in_card
    alpha = np.maximum(np.maximum(alpha_main, np.maximum(alpha_r1, alpha_r2)), np.maximum(alpha_orn, alpha_studs))

    profile = 1.0 - np.abs(np.clip(-sd_ap / 44.0, 0.0, 1.0) * 2.0 - 1.0)
    h_main = (0.30 + 0.54 * smoothstep(0.0, 1.0, profile)) * alpha_main
    spandrel = (sd_ap > 34.0) & (py < spring_y)
    h_main = np.where(spandrel, 0.28 * alpha_main, h_main)
    h_ribs = np.maximum(0.84 * alpha_r1, 0.68 * alpha_r2)
    h_orn = 0.86 * alpha_orn
    h_studs = (0.98 - 0.16 * smoothstep(-10.0, 0.0, sd_studs)) * alpha_studs
    height = np.maximum(np.maximum(h_main, h_ribs), np.maximum(h_orn, h_studs))

    rgba = shade_metallic_relief(
        height,
        alpha,
        base_col=np.array([0.46, 0.48, 0.54], np.float32),
        hi_col=np.array([0.96, 0.98, 1.00], np.float32),
        dark_col=np.array([0.11, 0.12, 0.16], np.float32),
        gloss=0.88,
    )
    rgb_f = rgba[..., :3].astype(np.float32) / 255.0
    rgb_f *= subtle_brushed_noise(seed=606, scale=0.015)[..., None]
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
        ("full_art_glass.png", build_full_art_glass),
        ("baroque_arch.png", build_baroque_arch),
        ("eastern_ink.png", build_eastern_ink),
        ("y2k_polaroid.png", build_y2k_polaroid),
        ("gothic_spire.png", build_gothic_spire),
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
        comp = Image.alpha_composite(chk_pil, img).convert("RGB").resize((300, 400), Image.Resampling.LANCZOS)
        previews.append(comp)

    cols = 4
    rows = (len(previews) + cols - 1) // cols
    sheet = Image.new("RGB", (300 * cols, 400 * rows), (14, 18, 28))
    for i, p in enumerate(previews):
        sheet.paste(p, ((i % cols) * 300, (i // cols) * 400))
    sheet_path = OUT_DIR / "_frames_preview.png"
    sheet.save(sheet_path)
    print(f"Saved preview sheet: {sheet_path}")


if __name__ == "__main__":
    main()
