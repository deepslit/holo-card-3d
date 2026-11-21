"""Stage 3B: Render frozen-standard 84-frame seamless 3D holographic + flowing quicksand GIF & RGBA WebP."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import math
import os
import sys
import time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Standard frozen canvas dimensions
W, H = 690, 960
GIF_W, GIF_H = 460, 640
CW, CH = 492.0, 656.0
CORNER_R = 0.045 * CW
D_CAM = 3.8 * CW

DEFAULT_PALETTE = {
    "edge_base": [0.52, 0.43, 0.28],
    "edge_spec": [1.00, 0.92, 0.72],
    "metal_tint": [1.00, 0.89, 0.62],
    "aura": [0.24, 0.55, 0.95],
    "sand1": [1.00, 0.85, 0.48],
    "sand2": [0.55, 0.90, 1.00],
    "sequins": [
        [1.00, 0.86, 0.45],
        [0.62, 0.94, 1.00],
        [0.86, 0.92, 1.00],
        [0.78, 0.68, 1.00],
    ],
    "part1": [1.00, 0.88, 0.55],
    "part2": [0.55, 0.90, 1.00],
}


def premult_blur(rgba: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0.05:
        return rgba
    rgb = rgba[..., :3]
    a = rgba[..., 3:4]
    k = int(math.ceil(sigma * 3.0)) * 2 + 1
    premult_b = cv2.GaussianBlur(rgb * a, (k, k), sigma)
    a_b = cv2.GaussianBlur(a, (k, k), sigma)
    if a_b.ndim == 2:
        a_b = a_b[..., None]
    rgb_out = np.where(a_b > 1e-4, premult_b / np.maximum(a_b, 1e-4), 0.0)
    return np.concatenate([np.clip(rgb_out, 0.0, 1.0), np.clip(a_b, 0.0, 1.0)], axis=-1)


def rot_matrix(yaw_deg: float, pitch_deg: float, roll_deg: float) -> np.ndarray:
    ry, rx, rz = np.radians([yaw_deg, pitch_deg, roll_deg])
    cy, sy = math.cos(ry), math.sin(ry)
    cx, sx = math.cos(rx), math.sin(rx)
    cz, sz = math.cos(rz), math.sin(rz)
    Ry = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]], dtype=np.float32)
    Rx = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]], dtype=np.float32)
    Rz = np.array([[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
    return (Rz @ Rx @ Ry).astype(np.float32)


def sd_rounded_box(px: np.ndarray, py: np.ndarray, hw: float, hh: float, r: float) -> np.ndarray:
    qx = np.abs(px) - (hw - r)
    qy = np.abs(py) - (hh - r)
    outside = np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0))
    inside = np.minimum(np.maximum(qx, qy), 0.0)
    return outside + inside - r


def smoothstep(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def sample_bilinear(img: np.ndarray, u: np.ndarray, v: np.ndarray, border_mode=cv2.BORDER_CONSTANT) -> np.ndarray:
    ih, iw = img.shape[:2]
    map_x = (u * (iw - 1)).astype(np.float32)
    map_y = (v * (ih - 1)).astype(np.float32)
    return cv2.remap(img, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=border_mode)


def spectral_rainbow(phase: np.ndarray) -> np.ndarray:
    p = phase * (2.0 * math.pi)
    r = 0.5 + 0.5 * np.cos(p + 0.0)
    g = 0.5 + 0.5 * np.cos(p + 2.0944)
    b = 0.5 + 0.5 * np.cos(p + 4.1888)
    return np.stack([r, g, b], axis=-1).astype(np.float32)


def build_sequins(seed: int, palette_seqs: list, count: int = 300):
    rng = np.random.default_rng(seed)
    u = rng.uniform(0.04, 0.96, count).astype(np.float32)
    v = rng.uniform(0.04, 0.96, count).astype(np.float32)
    z = rng.uniform(-0.074, -0.032, count).astype(np.float32)
    rad = rng.uniform(1.6, 3.6, count).astype(np.float32)
    phase = rng.uniform(0.0, 2.0 * math.pi, count).astype(np.float32)
    speed = rng.choice([1.0, 2.0], size=count, p=[0.65, 0.35]).astype(np.float32)
    n = rng.normal(0.0, 1.0, (count, 3)).astype(np.float32)
    n[:, 2] = np.abs(n[:, 2]) + 0.25
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    palette = np.array(palette_seqs, dtype=np.float32)
    col = palette[rng.integers(0, len(palette), count)]
    return dict(u=u, v=v, z=z, rad=rad, phase=phase, speed=speed, n=n, col=col)


def build_space_particles(seed: int, p1_col: list, p2_col: list, n_back: int = 34, n_front: int = 22):
    rng = np.random.default_rng(seed + 79601)
    c1 = np.array(p1_col, dtype=np.float32)
    c2 = np.array(p2_col, dtype=np.float32)

    def make_set(n, is_front):
        x = rng.uniform(0.06, 0.94, n).astype(np.float32)
        y = rng.uniform(0.06, 0.94, n).astype(np.float32)
        rad = rng.uniform(2.2 if is_front else 1.5, 5.2 if is_front else 3.2, n).astype(np.float32)
        amp_x = rng.uniform(0.008, 0.025, n).astype(np.float32)
        amp_y = rng.uniform(0.010, 0.032, n).astype(np.float32)
        ph = rng.uniform(0.0, 2.0 * math.pi, n).astype(np.float32)
        freq = rng.choice([1.0, 2.0], size=n).astype(np.float32)
        col = np.where(rng.uniform(0, 1, n)[:, None] > 0.45, c1, c2)
        return dict(x=x, y=y, rad=rad, amp_x=amp_x, amp_y=amp_y, ph=ph, freq=freq, col=col)

    return make_set(n_back, False), make_set(n_front, True)


def draw_star_glints(canvas_rgb: np.ndarray, glints_screen: list, sweep_u: float, t_norm: float):
    out = canvas_rgb
    prop_on = bool(_CTX["meta"].get("prop_fx", {}).get("enabled"))
    for g in glints_screen:
        gx, gy = g["px"], g["py"]
        if gx < -30 or gx >= W + 30 or gy < -30 or gy >= H + 30:
            continue
        dist_band = abs((g["u"] * 0.72 + g["v"] * 0.52) - sweep_u)
        sweep_trig = math.exp(-(dist_band ** 2) / 0.018)
        twinkle = 0.25 + 0.75 * (0.5 + 0.5 * math.sin(2.0 * math.pi * (t_norm * 2.0 + g["phase"])))
        cap_i = 0.92 if prop_on else 1.35
        base_i = ((0.20 if prop_on else 0.28) * twinkle + (0.68 if prop_on else 1.05) * sweep_trig) * g["vis"]
        intensity = min(cap_i, base_i)
        if intensity < 0.08:
            continue

        arm = max(10, int(g["size"] * CW * (0.65 + 0.55 * sweep_trig)))
        x0, x1 = max(0, int(gx) - arm), min(W, int(gx) + arm + 1)
        y0, y1 = max(0, int(gy) - arm), min(H, int(gy) + arm + 1)
        if x1 <= x0 or y1 <= y0:
            continue

        yy, xx = np.mgrid[y0:y1, x0:x1]
        dx = xx.astype(np.float32) - gx
        dy = yy.astype(np.float32) - gy
        r = np.hypot(dx, dy)
        sigma_arm = max(1.1, arm * 0.045)
        arm_h = np.exp(-(dy ** 2) / (2.0 * sigma_arm ** 2)) * np.exp(-np.abs(dx) / (arm * 0.36))
        arm_v = np.exp(-(dx ** 2) / (2.0 * sigma_arm ** 2)) * np.exp(-np.abs(dy) / (arm * 0.36))
        core = np.exp(-(r ** 2) / (2.0 * (arm * 0.14) ** 2))
        d1 = (dx + dy) * 0.7071
        d2 = (dx - dy) * 0.7071
        diag = 0.22 * (
            np.exp(-(d1 ** 2) / (2.0 * sigma_arm ** 2)) * np.exp(-np.abs(d2) / (arm * 0.20))
            + np.exp(-(d2 ** 2) / (2.0 * sigma_arm ** 2)) * np.exp(-np.abs(d1) / (arm * 0.20))
        )
        spark = np.clip((arm_h + arm_v + core * (0.85 if prop_on else 1.1) + diag) * intensity, 0.0, 1.4)[..., None]
        tint = np.array([1.0, 0.96, 0.86], dtype=np.float32) if g["kind"] != "bg_star" else np.array([0.82, 0.95, 1.0], dtype=np.float32)
        out[y0:y1, x0:x1] = out[y0:y1, x0:x1] + spark * tint


def _hash12(a: float, b: float) -> float:
    p3x = math.fmod(abs(a * 0.1031), 1.0)
    p3y = math.fmod(abs(b * 0.1031), 1.0)
    p3z = p3x
    d = p3x * (p3y + 33.33) + p3y * (p3z + 33.33) + p3z * (p3x + 33.33)
    return math.fmod(((p3x + d) + (p3y + d)) * (p3z + d), 1.0)


def eval_sdf_motif_patch(dx: np.ndarray, dy: np.ndarray, size_px: float, rot_rad: float, tumble: float,
                         seed_id: float, motif_id: int, is_bubble: bool,
                         c1: np.ndarray, c2: np.ndarray, ang: float):
    """Evaluate crisp analytical SDF motif colors (rgb HxWx3) & alpha (HxW) for local crop."""
    cr, sr = math.cos(rot_rad), math.sin(rot_rad)
    rpx = dx * cr + dy * sr
    rpy = (-dx * sr + dy * cr) / max(0.35, 0.48 + 0.52 * abs(math.cos(tumble)))
    aa = max(1.0, size_px * 0.095)
    fill_a = np.zeros_like(dx, dtype=np.float32)
    rim_glow = np.zeros_like(dx, dtype=np.float32)
    grad_t = np.full_like(dx, 0.5, dtype=np.float32)

    if motif_id == 0:
        if is_bubble:
            r = np.hypot(rpx, rpy)
            rad = size_px * 0.58
            ring = np.exp(-np.power((r - rad) / max(1.1, size_px * 0.14), 2.0))
            d_hi = (rpx + rad * 0.38) ** 2 + (rpy + rad * 0.38) ** 2
            hi = np.exp(-d_hi / max(1.0, (rad * 0.28) ** 2))
            fill_a = np.clip(ring * 0.72 + hi * 0.85, 0.0, 1.0)
            rim_glow = hi * 0.90
            grad_t = 0.25 + 0.75 * hi
        else:
            x = rpx / max(size_px * 1.15, 1.0)
            mask = np.abs(x) <= 1.05
            y = rpy / max(size_px * 0.38, 1.0) - 0.34 * (x ** 2)
            prof = np.maximum(0.0, 1.0 - x ** 2)
            d = (np.abs(y) - prof) * size_px * 0.38
            fa = np.where(mask, 1.0 - smoothstep(-aa, aa, d), 0.0)
            fill_a = fa
            rim_glow = np.where(mask, np.exp(-(y ** 2) / 0.032) * prof * 0.55, 0.0)
            grad_t = np.clip(0.5 + 0.5 * x, 0.0, 1.0)
    elif motif_id == 1:
        qx = np.abs(rpx) / max(size_px * 0.96, 1.0)
        qy = np.abs(rpy) / max(size_px * 0.96, 1.0)
        mask = (qx < 1.25) & (qy < 1.25)
        ast = np.power(np.maximum(qx, 1e-4), 0.56) + np.power(np.maximum(qy, 1e-4), 0.56)
        d = (ast - 1.0) * size_px * 0.75
        fill_a = np.where(mask, 1.0 - smoothstep(-aa, aa, d), 0.0)
        rim_glow = np.where(mask, np.exp(-(qx ** 2 + qy ** 2) * 9.0) * 0.65, 0.0)
        grad_t = np.clip(0.5 + 0.5 * (rpx - rpy) / max(size_px, 1.0), 0.0, 1.0)
    elif motif_id == 2:
        x = rpx / max(size_px * 1.12, 1.0)
        mask = np.abs(x) <= 1.08
        y = rpy / max(size_px * 0.44, 1.0)
        w = np.clip(1.0 - x ** 2, 0.0, 1.0) * (0.64 + 0.36 * np.sin((x + 1.0) * 1.35)) * (1.0 - 0.14 * np.exp(-((x - 0.92) / 0.22) ** 2))
        d = (np.abs(y) - w) * size_px * 0.44
        fill_a = np.where(mask, 1.0 - smoothstep(-aa, aa, d), 0.0)
        rim_glow = np.where(mask, np.exp(-(y ** 2) / 0.045) * w * 0.35, 0.0)
        grad_t = np.clip(0.5 + 0.5 * x, 0.0, 1.0)
    elif motif_id == 3:
        qx = np.abs(rpx) / max(size_px * 1.15, 1.0)
        qy = np.abs(rpy) / max(size_px * 0.45, 1.0)
        d = (qx + qy - 1.0) * size_px * 0.45
        fill_a = 1.0 - smoothstep(-aa, aa, d)
        rim_glow = np.exp(-(qx ** 2 + qy ** 2) * 5.0) * 0.75
        grad_t = np.clip(qx, 0.0, 1.0)
    else:
        r = np.hypot(rpx, rpy)
        mask = r < size_px * 1.15
        a6 = np.mod(np.arctan2(rpy, rpx) + math.pi / 6.0, math.pi / 3.0) - math.pi / 6.0
        p6x = r * np.cos(a6)
        p6y = r * np.abs(np.sin(a6))
        d = np.minimum(np.maximum(p6x - size_px, p6y - size_px * 0.11),
                       np.maximum(np.abs(p6x - 0.55 * size_px - p6y * 0.7) - size_px * 0.08, p6y - 0.38 * size_px))
        fill_a = np.where(mask, 1.0 - smoothstep(-aa, aa, d), 0.0)
        rim_glow = np.where(mask, np.exp(-(r ** 2) / max(1.0, (size_px * 0.25) ** 2)) * 0.6, 0.0)
        grad_t = np.clip(r / max(size_px, 1.0), 0.0, 1.0)

    shimmer = 0.72 + 0.28 * math.sin(ang * 2.0 + seed_id * 3.1 + tumble)
    base_col = c1[None, None, :] * (1.0 - grad_t[..., None]) + c2[None, None, :] * grad_t[..., None]
    col = np.clip(base_col * (0.85 + 0.35 * shimmer) + np.array([0.98, 0.98, 1.0], dtype=np.float32)[None, None, :] * (rim_glow[..., None] * 0.42), 0.0, 1.0)
    return col, np.clip(fill_a, 0.0, 1.0)


_CTX = {}


def _init_worker(proc_dir_str: str, num_frames: int):
    """Load preprocessed assets once per worker process (Windows spawn safe)."""
    cv2.setNumThreads(1)
    proc_dir = Path(proc_dir_str)
    meta = json.loads((proc_dir / "scene_meta.json").read_text(encoding="utf-8"))

    pal = dict(DEFAULT_PALETTE)
    pal.update(meta.get("palette", {}))
    seed = int(meta.get("seed", 20261121))

    AW, AH = 660, 880
    bg_raw = np.array(Image.open(proc_dir / "master_bg.png").convert("RGB").resize((AW, AH), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0
    mid_raw = np.array(Image.open(proc_dir / "master_mid.png").convert("RGBA").resize((AW, AH), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0
    fg_raw = np.array(Image.open(proc_dir / "master_fg.png").convert("RGBA").resize((AW, AH), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0
    depth_raw = np.array(Image.open(proc_dir / "depth_extrapolated.png").convert("L").resize((AW, AH), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0
    masks_raw = np.array(Image.open(proc_dir / "masks_rgba.png").convert("RGBA").resize((AW, AH), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0

    bg_dof = cv2.GaussianBlur(bg_raw, (5, 5), 0.85)
    fg_dof = premult_blur(fg_raw, sigma=0.55)
    depth_alpha_pack = np.dstack([depth_raw, mid_raw[..., 3]]).astype(np.float32)

    dz_dx = cv2.Sobel(depth_raw, cv2.CV_32F, 1, 0, ksize=5) / 8.0
    dz_dy = cv2.Sobel(depth_raw, cv2.CV_32F, 0, 1, ksize=5) / 8.0
    slope_scale = 2.1
    gx_n = np.clip(-dz_dx * slope_scale, -0.58, 0.58)
    gy_n = np.clip(-dz_dy * slope_scale, -0.58, 0.58)
    gz_n = np.ones_like(gx_n)
    norm_len = np.sqrt(gx_n ** 2 + gy_n ** 2 + gz_n ** 2)
    mid_normals = np.stack([gx_n / norm_len, gy_n / norm_len, gz_n / norm_len], axis=-1).astype(np.float32)

    mid_luma = 0.299 * mid_raw[..., 0] + 0.587 * mid_raw[..., 1] + 0.114 * mid_raw[..., 2]
    sx = cv2.Sobel(mid_luma, cv2.CV_32F, 1, 0, ksize=3)
    sy = cv2.Sobel(mid_luma, cv2.CV_32F, 0, 1, ksize=3)
    sar_vec = np.stack([sx, sy], axis=-1).astype(np.float32)

    fg_emb = masks_raw[..., 3]
    fx_n = -cv2.Sobel(fg_emb, cv2.CV_32F, 1, 0, ksize=5) * 0.45
    fy_n = -cv2.Sobel(fg_emb, cv2.CV_32F, 0, 1, ksize=5) * 0.45
    fg_normals = np.stack([fx_n, fy_n, np.ones_like(fx_n)], axis=-1)
    fg_normals /= np.linalg.norm(fg_normals, axis=-1, keepdims=True)

    yy_a, xx_a = np.mgrid[0:H, 0:W]
    px_base = xx_a.astype(np.float32) - W * 0.5
    py_base = yy_a.astype(np.float32) - H * 0.5

    s_col = np.array(meta["studio_color_rgb"], dtype=np.float32) / 255.0
    aura_c = np.array(pal["aura"], dtype=np.float32)
    rad_bg = np.hypot(px_base / (W * 0.55), py_base / (H * 0.55))
    vig = np.clip(1.0 - 0.52 * (rad_bg ** 1.45), 0.15, 1.0)[..., None]
    studio_bg = np.clip(s_col[None, None, :] * (0.65 + 0.85 * vig) + (aura_c * 0.06)[None, None, :] * vig, 0.0, 1.0)

    prop_mask_img = np.zeros((AH, AW), dtype=np.float32)
    pm_path = proc_dir / "prop_mask.png"
    if pm_path.exists() and (meta.get("prop_fx") or {}).get("enabled"):
        prop_mask_img = np.array(Image.open(pm_path).convert("L").resize((AW, AH), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0

    _CTX.update({
        "meta": meta,
        "pal": pal,
        "num_frames": num_frames,
        "mid_raw": mid_raw,
        "masks_raw": masks_raw,
        "prop_mask": prop_mask_img,
        "bg_dof": bg_dof,
        "fg_dof": fg_dof,
        "depth_alpha_pack": depth_alpha_pack,
        "mid_normals": mid_normals,
        "sar_vec": sar_vec,
        "fg_normals": fg_normals,
        "yy_a": yy_a,
        "px_base": px_base,
        "py_base": py_base,
        "studio_bg": studio_bg,
        "sequins": build_sequins(seed, pal["sequins"], count=300),
        "parts": build_space_particles(seed, pal["part1"], pal["part2"], n_back=34, n_front=22),
    })


def render_single_frame(f_idx: int):
    meta = _CTX["meta"]
    pal = _CTX["pal"]
    num_frames = _CTX["num_frames"]
    mid_raw = _CTX["mid_raw"]
    masks_raw = _CTX["masks_raw"]
    bg_dof = _CTX["bg_dof"]
    fg_dof = _CTX["fg_dof"]
    depth_alpha_pack = _CTX["depth_alpha_pack"]
    mid_normals = _CTX["mid_normals"]
    sar_vec = _CTX["sar_vec"]
    fg_normals = _CTX["fg_normals"]
    yy_a = _CTX["yy_a"]
    px_base = _CTX["px_base"]
    py_base = _CTX["py_base"]
    studio_bg = _CTX["studio_bg"]
    sequins = _CTX["sequins"]
    back_parts, front_parts = _CTX["parts"]

    edge_base_c = np.array(pal["edge_base"], dtype=np.float32)
    edge_spec_c = np.array(pal["edge_spec"], dtype=np.float32)
    metal_tint_c = np.array(pal["metal_tint"], dtype=np.float32)
    aura_c = np.array(pal["aura"], dtype=np.float32)
    sand1_c = np.array(pal["sand1"], dtype=np.float32)
    sand2_c = np.array(pal["sand2"], dtype=np.float32)
    holo_pattern = meta.get("holo_pattern", "starburst")

    astro_cx, astro_cy = meta["astrolabe_center"]
    z_back = -0.082 * CW
    z_sand1 = -0.058 * CW
    z_sand2 = -0.036 * CW
    z_mid_base = -0.012 * CW
    z_mid_amp = 0.064 * CW
    z_fg_base = 0.008 * CW
    thickness = 0.036 * CW
    slice_zs = [-thickness * (s / 10.0) for s in range(1, 11)]

    t = f_idx / float(num_frames)
    ang = 2.0 * math.pi * t
    yaw = 24.0 * math.sin(ang)
    pitch = 11.5 * math.sin(2.0 * ang)
    roll = 1.6 * math.sin(ang)
    hover_y = -0.013 * H * math.sin(ang)

    R = rot_matrix(yaw, pitch, roll)
    RT = R.T

    light_dir = np.array([
        0.36 * math.cos(ang) - 0.25 * math.sin(ang),
        -0.42 + 0.14 * math.sin(2.0 * ang),
        0.84,
    ], dtype=np.float32)
    light_dir /= np.linalg.norm(light_dir)
    light_loc = RT @ light_dir

    d_len = np.sqrt(px_base ** 2 + py_base ** 2 + D_CAM ** 2)
    dx_c = px_base / d_len
    dy_c = py_base / d_len
    dz_c = -D_CAM / d_len

    o_loc = RT @ np.array([0.0, -hover_y, D_CAM], dtype=np.float32)
    dlx = RT[0, 0] * dx_c + RT[0, 1] * dy_c + RT[0, 2] * dz_c
    dly = RT[1, 0] * dx_c + RT[1, 1] * dy_c + RT[1, 2] * dz_c
    dlz = RT[2, 0] * dx_c + RT[2, 1] * dy_c + RT[2, 2] * dz_c
    inv_dlz = 1.0 / np.where(np.abs(dlz) < 1e-4, -1e-4, dlz)

    t0 = -o_loc[2] * inv_dlz
    p0x = o_loc[0] + t0 * dlx
    p0y = o_loc[1] + t0 * dly
    sd0 = sd_rounded_box(p0x, p0y, CW * 0.5, CH * 0.5, CORNER_R)
    front_mask = 1.0 - smoothstep(-1.1, 1.1, sd0)

    edge_alpha = np.zeros((H, W), dtype=np.float32)
    edge_rgb = np.zeros((H, W, 3), dtype=np.float32)
    edge_hit_x = np.zeros((H, W), dtype=np.float32)
    edge_hit_y = np.zeros((H, W), dtype=np.float32)
    edge_hit_s = np.zeros((H, W), dtype=np.float32)
    for si, sz in enumerate(slice_zs, start=1):
        ts = (sz - o_loc[2]) * inv_dlz
        psx = o_loc[0] + ts * dlx
        psy = o_loc[1] + ts * dly
        sds = sd_rounded_box(psx, psy, CW * 0.5, CH * 0.5, CORNER_R)
        sm = (1.0 - smoothstep(-1.1, 1.1, sds)) * (edge_alpha < 0.99)
        fill_w = np.clip(sm * (1.0 - edge_alpha), 0.0, 1.0)
        edge_hit_x += psx * fill_w
        edge_hit_y += psy * fill_w
        edge_hit_s += (si / 10.0) * fill_w
        edge_alpha = np.clip(edge_alpha + fill_w, 0.0, 1.0)

    if np.any(edge_alpha > 0.01):
        nx_e = np.sign(edge_hit_x) * smoothstep(CW * 0.42, CW * 0.5, np.abs(edge_hit_x))
        ny_e = np.sign(edge_hit_y) * smoothstep(CH * 0.42, CH * 0.5, np.abs(edge_hit_y))
        nz_e = 0.25 + 0.35 * (1.0 - edge_hit_s)
        ne_len = np.sqrt(nx_e ** 2 + ny_e ** 2 + nz_e ** 2) + 1e-5
        nx_e /= ne_len
        ny_e /= ne_len
        nz_e /= ne_len
        h_loc = light_loc - np.array([0.0, 0.0, -1.0], dtype=np.float32)
        h_loc /= np.linalg.norm(h_loc)
        ndotl_e = np.clip(nx_e * light_loc[0] + ny_e * light_loc[1] + nz_e * light_loc[2], 0.0, 1.0)
        ndoth_e = np.clip(nx_e * h_loc[0] + ny_e * h_loc[1] + nz_e * h_loc[2], 0.0, 1.0)
        grain = 0.88 + 0.12 * np.sin((edge_hit_x + edge_hit_y) * 0.55 + edge_hit_s * 14.0)
        edge_rgb = (edge_base_c * (0.45 + 0.65 * ndotl_e[..., None]) + edge_spec_c * (0.85 * (ndoth_e ** 18)[..., None])) * grain[..., None]
        edge_rgb *= 1.0 - 0.28 * edge_hit_s[..., None]

    ys_c, xs_c = np.where(front_mask > 0.004)
    y0_c, y1_c = int(ys_c.min()), int(ys_c.max()) + 1
    x0_c, x1_c = int(xs_c.min()), int(xs_c.max()) + 1

    olx, oly, olz = o_loc[0], o_loc[1], o_loc[2]
    dlx_c = dlx[y0_c:y1_c, x0_c:x1_c]
    dly_c = dly[y0_c:y1_c, x0_c:x1_c]
    dlz_c = dlz[y0_c:y1_c, x0_c:x1_c]
    inv_c = inv_dlz[y0_c:y1_c, x0_c:x1_c]
    sd0_c = sd0[y0_c:y1_c, x0_c:x1_c]
    hc_w, hc_h = x1_c - x0_c, y1_c - y0_c

    def plane_uv(z_p: float):
        tp = (z_p - olz) * inv_c
        px_p = olx + tp * dlx_c
        py_p = oly + tp * dly_c
        comp = D_CAM / (D_CAM - z_p)
        return 0.5 + (px_p * comp) / CW, 0.5 + (py_p * comp) / CH

    # 1. Deep Background Layer (1.07x overscan) + SAR/UR Holo Shader
    prop_fx = meta.get("prop_fx") or {}
    prop_enabled = bool(prop_fx.get("enabled"))
    motif = meta.get("motion_motif") or {}
    motif_id = int(motif.get("kind_id", -1))

    ub, vb = plane_uv(z_back)
    ub_os = np.clip(0.5 + (ub - 0.5) / 1.07, 0.0, 1.0)
    vb_os = np.clip(0.5 + (vb - 0.5) / 1.07, 0.0, 1.0)
    bg_col = sample_bilinear(bg_dof, ub_os, vb_os, border_mode=cv2.BORDER_REPLICATE)
    r_holo_mask = sample_bilinear(masks_raw[..., 0], ub_os, vb_os, border_mode=cv2.BORDER_REPLICATE)

    du_a = ub_os - astro_cx
    dv_a = (vb_os - astro_cy) * (CH / CW)
    ang_a = np.arctan2(dv_a, du_a)
    rad_a = np.hypot(du_a, dv_a)
    if holo_pattern == "prism_grid":
        carrier = 0.5 + 0.5 * np.cos((ub_os * 36.0 + vb_os * 48.0) * math.pi + yaw * 0.09) * np.cos((ub_os * 36.0 - vb_os * 48.0) * math.pi - pitch * 0.08)
    elif holo_pattern == "cosmos_waves":
        carrier = 0.5 + 0.5 * np.sin(rad_a * 20.0 - ang_a * 6.0 + yaw * 0.10)
    else:
        carrier = 0.5 + 0.5 * np.cos(ang_a * 24.0 + yaw * 0.08)
    micro_grating = 0.5 + 0.5 * np.sin((ub_os * 110.0 + vb_os * 145.0) * math.pi + yaw * 0.14)
    tilt_shift = 0.016 * yaw + 0.012 * pitch
    spec1 = spectral_rainbow(ub_os * 1.45 + vb_os * 0.95 + tilt_shift * 1.4 + 0.08 * carrier)
    spec2 = spectral_rainbow(rad_a * 2.1 - tilt_shift * 1.1 + 0.12 * micro_grating)
    holo_comb = 0.58 * spec1 + 0.42 * spec2
    holo_strength = r_holo_mask * (0.20 + 0.24 * carrier * (0.5 + 0.5 * micro_grating))
    bg_lit = bg_col + holo_comb * holo_strength[..., None] * 0.55

    # Deep plane bespoke SDF motifs inside card
    if motif_id >= 0:
        mc1 = np.array(motif.get("color1", pal["part1"]), dtype=np.float32)
        mc2 = np.array(motif.get("color2", pal["part2"]), dtype=np.float32)
        for db in range(2):
            dir_x = -1.0 if motif_id == 2 else (1.0 if motif_id == 1 else 0.0)
            dir_y = -1.0 if motif_id in (0, 3) else 1.0
            pu = 0.12 + 0.76 * math.fmod(_hash12(float(db), 11.3) + t * dir_x + ((0.03 * math.sin(ang + db * 2.0)) if motif_id in (0, 3) else 0.0) + 10.0, 1.0)
            pv = 0.12 + 0.76 * math.fmod(_hash12(float(db), 23.7) + t * dir_y + 10.0, 1.0)
            comp_m = (D_CAM - (-0.044 * CW)) / D_CAM
            mloc = np.array([(pu - 0.5) * CW * comp_m, (pv - 0.5) * CH * comp_m, -0.044 * CW], dtype=np.float32)
            mcam = R @ mloc
            mpx = mcam[0] * D_CAM / (D_CAM - mcam[2]) + W * 0.5 - x0_c
            mpy = (mcam[1] + hover_y) * D_CAM / (D_CAM - mcam[2]) + H * 0.5 - y0_c
            msz = (0.014 + 0.005 * _hash12(float(db), 3.1)) * CW
            ix0, ix1 = max(0, int(mpx - msz * 2.2)), min(hc_w, int(mpx + msz * 2.2) + 1)
            iy0, iy1 = max(0, int(mpy - msz * 2.2)), min(hc_h, int(mpy + msz * 2.2) + 1)
            if ix1 > ix0 and iy1 > iy0:
                yym, xxm = np.mgrid[iy0:iy1, ix0:ix1]
                rot_a = _hash12(float(db), 5.2) * 6.283 + ang * (1.0 if db == 0 else -1.0)
                mcol, ma = eval_sdf_motif_patch(xxm - mpx, yym - mpy, msz, rot_a, ang + db * 1.7, float(db), motif_id, False, mc1, mc2, ang)
                bg_lit[iy0:iy1, ix0:ix1] = bg_lit[iy0:iy1, ix0:ix1] * (1.0 - ma[..., None] * 0.72) + mcol * (ma[..., None] * 0.72)

    # 2. Flowing Quicksand Interlayer + 300 3D sequins
    us1, vs1 = plane_uv(z_sand1)
    us2, vs2 = plane_uv(z_sand2)
    grav_x = 0.025 * math.sin(math.radians(yaw))
    grav_y = 0.020 * math.sin(math.radians(pitch))
    flow1 = np.sin((us1 + grav_x) * 18.0 + vs1 * 9.0 + ang) * np.cos((vs1 + grav_y) * 14.0 - us1 * 7.0 - ang)
    silk1 = np.power(np.clip(0.5 + 0.5 * flow1, 0.0, 1.0), 3.2) * (0.4 + 0.6 * r_holo_mask)
    flow2 = np.sin((us2 - grav_x * 1.3) * 24.0 - vs2 * 13.0 - 2.0 * ang) * np.cos((vs2 + grav_y * 1.2) * 19.0 + us2 * 11.0 + ang)
    silk2 = np.power(np.clip(0.5 + 0.5 * flow2, 0.0, 1.0), 3.6) * (0.35 + 0.65 * r_holo_mask)
    sand_glow = silk1[..., None] * sand1_c * 0.24 + silk2[..., None] * sand2_c * 0.22
    bg_with_sand = bg_lit + sand_glow

    h_vec = light_dir + np.array([0.0, 0.0, 1.0], dtype=np.float32)
    h_vec /= np.linalg.norm(h_vec)
    sq_n_world = (R @ sequins["n"].T).T
    sq_spec = np.power(np.clip(np.abs(sq_n_world @ h_vec), 0.0, 1.0), 36.0)
    sq_diff = 0.22 + 0.78 * np.clip(np.abs(sq_n_world @ light_dir), 0.0, 1.0)
    sq_br = sq_diff * 0.35 + sq_spec * 1.45

    su = sequins["u"] + 0.012 * np.sin(ang * sequins["speed"] + sequins["phase"]) + 0.022 * math.sin(math.radians(yaw))
    sv = sequins["v"] + 0.014 * np.cos(ang * sequins["speed"] + sequins["phase"]) + 0.018 * math.sin(math.radians(pitch))
    comp_sq = (D_CAM - sequins["z"] * CW) / D_CAM
    sq_loc = np.stack([(su - 0.5) * CW * comp_sq, (sv - 0.5) * CH * comp_sq, sequins["z"] * CW], axis=1)
    sq_cam = (R @ sq_loc.T).T
    sq_px = sq_cam[:, 0] * D_CAM / (D_CAM - sq_cam[:, 2]) + W * 0.5 - x0_c
    sq_py = (sq_cam[:, 1] + hover_y) * D_CAM / (D_CAM - sq_cam[:, 2]) + H * 0.5 - y0_c

    for qi in range(len(su)):
        qx, qy = float(sq_px[qi]), float(sq_py[qi])
        qr = float(sequins["rad"][qi])
        if qx < -qr * 2 or qx >= hc_w + qr * 2 or qy < -qr * 2 or qy >= hc_h + qr * 2:
            continue
        bx0, bx1 = max(0, int(qx - qr * 2.2)), min(hc_w, int(qx + qr * 2.2) + 1)
        by0, by1 = max(0, int(qy - qr * 2.2)), min(hc_h, int(qy + qr * 2.2) + 1)
        if bx1 <= bx0 or by1 <= by0:
            continue
        yy_s, xx_s = np.mgrid[by0:by1, bx0:bx1]
        r2 = (xx_s - qx) ** 2 + (yy_s - qy) ** 2
        spot = np.exp(-r2 / (2.0 * (qr * 0.55) ** 2))
        bg_with_sand[by0:by1, bx0:bx1] += spot[..., None] * sequins["col"][qi] * float(sq_br[qi]) * 0.85

    sh_ox = -light_loc[0] * 0.042
    sh_oy = -light_loc[1] * 0.042 * (CW / CH)
    sh_alpha = cv2.GaussianBlur(sample_bilinear(mid_raw[..., 3], us1 - sh_ox, vs1 - sh_oy), (25, 25), 7.5)
    bg_with_sand *= 1.0 - 0.44 * sh_alpha[..., None]

    # 3. Midground 3D Subject (18 + 4 binary Relief Mapping)
    z_start = z_mid_base + z_mid_amp
    z_end = z_mid_base
    dz_step = (z_end - z_start) / 18.0
    hit_found = np.zeros((hc_h, hc_w), dtype=bool)
    z_lo = np.full((hc_h, hc_w), z_end, dtype=np.float32)
    z_hi = np.full((hc_h, hc_w), z_start, dtype=np.float32)

    for step_i in range(19):
        z_test = z_start + step_i * dz_step
        ut, vt = plane_uv(z_test)
        da = sample_bilinear(depth_alpha_pack, ut, vt, border_mode=cv2.BORDER_CONSTANT)
        z_surf = z_mid_base + da[..., 0] * z_mid_amp
        below = (z_test <= z_surf) & (da[..., 1] > 0.14) & (~hit_found)
        if np.any(below):
            hit_found[below] = True
            z_lo[below] = z_test
            z_hi[below] = z_test - dz_step

    for _ in range(4):
        z_mid_b = 0.5 * (z_lo + z_hi)
        ut, vt = plane_uv(z_mid_b)
        da = sample_bilinear(depth_alpha_pack, ut, vt, border_mode=cv2.BORDER_CONSTANT)
        z_surf = z_mid_base + da[..., 0] * z_mid_amp
        is_below = (z_mid_b <= z_surf) & (da[..., 1] > 0.14)
        z_lo = np.where(is_below, z_mid_b, z_lo)
        z_hi = np.where(is_below, z_hi, z_mid_b)

    um, vm = plane_uv(0.5 * (z_lo + z_hi))
    mid_rgba_hit = sample_bilinear(mid_raw, um, vm, border_mode=cv2.BORDER_CONSTANT)
    m_rgb = mid_rgba_hit[..., :3]
    m_a = np.where(hit_found, mid_rgba_hit[..., 3], 0.0)

    m_norm = sample_bilinear(mid_normals, um, vm, border_mode=cv2.BORDER_REPLICATE)
    m_norm /= np.linalg.norm(m_norm, axis=-1, keepdims=True) + 1e-5
    m_metal = sample_bilinear(masks_raw[..., 1], um, vm, border_mode=cv2.BORDER_REPLICATE)
    m_sar_b = sample_bilinear(masks_raw[..., 2], um, vm, border_mode=cv2.BORDER_REPLICATE)
    m_sar_v = sample_bilinear(sar_vec, um, vm, border_mode=cv2.BORDER_REPLICATE)

    ndotl = m_norm[..., 0] * light_loc[0] + m_norm[..., 1] * light_loc[1] + m_norm[..., 2] * light_loc[2]
    diffuse_gain = 0.90 + 0.16 * np.clip(0.5 * ndotl + 0.5, 0.0, 1.0)

    vx, vy, vz = -dlx_c, -dly_c, -dlz_c
    hx, hy, hz = vx + light_loc[0], vy + light_loc[1], vz + light_loc[2]
    hl = np.sqrt(hx ** 2 + hy ** 2 + hz ** 2) + 1e-5
    hx, hy, hz = hx / hl, hy / hl, hz / hl
    ndoth = np.clip(m_norm[..., 0] * hx + m_norm[..., 1] * hy + m_norm[..., 2] * hz, 0.0, 1.0)
    ndotv = np.clip(m_norm[..., 0] * vx + m_norm[..., 1] * vy + m_norm[..., 2] * vz, 0.0, 1.0)

    metal_spec = np.power(ndoth, 28.0) * m_metal * 0.78
    metal_brushed = (0.5 + 0.5 * np.sin((um * 95.0 - vm * 35.0) * math.pi + yaw * 0.1)) * m_metal * 0.14
    sar_dot = np.clip(m_sar_v[..., 0] * light_loc[0] + m_sar_v[..., 1] * light_loc[1], 0.0, 1.0)
    sar_emboss = sar_dot * m_sar_b * 0.28
    pearl_rim = spectral_rainbow(um + vm + 0.015 * yaw) * (np.power(1.0 - ndotv, 3.2) * 0.22)[..., None] * 0.55

    prop_gleam = np.zeros_like(m_rgb)
    if prop_enabled:
        pm_val = sample_bilinear(_CTX["prop_mask"], um, vm, border_mode=cv2.BORDER_CONSTANT)
        if np.any(pm_val > 0.01):
            p_s = np.array(prop_fx.get("start_uv", [0.5, 0.7]), dtype=np.float32)
            p_t = np.array(prop_fx.get("tip_uv", [0.5, 0.3]), dtype=np.float32)
            p_vec = p_t - p_s
            p_len2 = max(float(np.dot(p_vec, p_vec)), 1e-4)
            p_len = math.sqrt(p_len2)
            s_along = ((um - p_s[0]) * p_vec[0] + (vm - p_s[1]) * p_vec[1]) / p_len2
            diag_off = ((um - p_s[0]) * (-p_vec[1]) + (vm - p_s[1]) * p_vec[0]) * (0.24 / max(p_len, 1e-4))
            cyc = t % 1.0
            sw_t = max(0.0, min(1.0, (cyc - 0.18) / 0.30))
            sw_t = sw_t * sw_t * (3.0 - 2.0 * sw_t)
            sw_pos = -0.18 + (1.16 - (-0.18)) * sw_t
            sw_env = float(smoothstep(0.16, 0.22, np.array(cyc)) * (1.0 - smoothstep(0.45, 0.52, np.array(cyc))))
            d_s = (s_along + diag_off) - sw_pos
            b_core = np.exp(-(d_s ** 2) / 0.0036)
            b_halo = np.exp(-(d_s ** 2) / 0.020)
            p_prism = spectral_rainbow(s_along * 1.4 + um * 0.8 + 0.02 * yaw)
            luma_m = 0.299 * m_rgb[..., 0] + 0.587 * m_rgb[..., 1] + 0.114 * m_rgb[..., 2]
            ink_keep = smoothstep(0.05, 0.26, luma_m + 0.12 * m_metal)
            p_tint = np.array(prop_fx.get("tint", [0.92, 0.96, 1.0]), dtype=np.float32)
            p_gain = float(prop_fx.get("gain", 0.90))
            subtle_catch = np.power(ndoth, 22.0) * 0.14
            mixed_tint = p_tint[None, None, :] * 0.68 + p_prism * 0.32
            prop_gleam = (
                (np.array([1.0, 0.99, 0.97], dtype=np.float32)[None, None, :] * (b_core[..., None] * 0.54) + mixed_tint * (b_halo[..., None] * 0.34)) * sw_env
                + p_tint[None, None, :] * subtle_catch[..., None]
            ) * (pm_val * ink_keep * p_gain)[..., None]

    m_lit = m_rgb * diffuse_gain[..., None] + metal_tint_c[None, None, :] * (metal_spec + metal_brushed)[..., None] + sar_emboss[..., None] + pearl_rim + prop_gleam
    m_ex = np.maximum(m_lit - 0.85, 0.0)
    m_lit = np.where(m_lit > 0.85, 0.85 + m_ex / (1.0 + 1.4 * m_ex), m_lit)
    card_rgb = bg_with_sand * (1.0 - m_a[..., None]) + np.clip(m_lit, 0.0, 1.0) * m_a[..., None]

    # 4. Foreground Embossed Baroque Frame (flush 3 slices: 0.005..0.012*CW)
    uf_sh, vf_sh = plane_uv(z_fg_base)
    fg_shadow_a = cv2.GaussianBlur(sample_bilinear(fg_dof[..., 3], uf_sh + light_loc[0] * 0.018, vf_sh + light_loc[1] * 0.018), (11, 11), 3.0)
    card_rgb *= 1.0 - 0.18 * (fg_shadow_a * m_a)[..., None]

    fg_acc_rgb = np.zeros((hc_h, hc_w, 3), dtype=np.float32)
    fg_acc_a = np.zeros((hc_h, hc_w), dtype=np.float32)
    for fi, zf in enumerate([0.005 * CW, 0.0085 * CW, 0.012 * CW]):
        uf, vf = plane_uv(zf)
        fg_s = sample_bilinear(fg_dof, uf, vf, border_mode=cv2.BORDER_CONSTANT)
        fa = fg_s[..., 3]
        if fi == 2:
            emb_h = sample_bilinear(masks_raw[..., 3], uf, vf)
            fa = fa * smoothstep(0.18, 0.45, emb_h)
        fn = sample_bilinear(fg_normals, uf, vf, border_mode=cv2.BORDER_REPLICATE)
        f_ndotl = np.clip(fn[..., 0] * light_loc[0] + fn[..., 1] * light_loc[1] + fn[..., 2] * light_loc[2], 0.0, 1.0)
        f_ndoth = np.clip(fn[..., 0] * hx + fn[..., 1] * hy + fn[..., 2] * hz, 0.0, 1.0)
        irid_fg = spectral_rainbow(uf * 0.8 + vf * 1.1 + 0.022 * yaw + 0.015 * pitch)
        sheen_tint = 0.62 * metal_tint_c + 0.22 * edge_spec_c + 0.16 * irid_fg
        f_col = fg_s[..., :3] * (0.76 + 0.24 * f_ndotl[..., None]) + sheen_tint * (0.42 * (f_ndoth ** 16))[..., None]
        f_ex = np.maximum(f_col - 0.85, 0.0)
        f_col = np.where(f_col > 0.85, 0.85 + f_ex / (1.0 + 1.5 * f_ex), f_col)
        if fi < 2:
            f_col *= 0.82 + 0.09 * fi
        fg_acc_rgb = fg_acc_rgb * (1.0 - fa[..., None]) + np.clip(f_col, 0.0, 1.0) * fa[..., None]
        fg_acc_a = np.clip(fg_acc_a + fa * (1.0 - fg_acc_a), 0.0, 1.0)

    card_rgb = card_rgb * (1.0 - fg_acc_a[..., None]) + fg_acc_rgb * fg_acc_a[..., None]

    # 5. Diagonal Glass Sweep + Spotlight + Bevel Sheen
    ug, vg = plane_uv(0.0)
    sweep_u = 0.62 + 0.78 * math.sin(ang)
    band_dist = (ug * 0.72 + vg * 0.52) - sweep_u
    glass_band = np.exp(-(band_dist ** 2) / 0.0085) * 0.11 + np.exp(-(band_dist ** 2) / 0.0009) * 0.13
    spot_x = 0.5 + 0.28 * math.sin(ang)
    spot_y = 0.44 + 0.22 * math.cos(2.0 * ang)
    spotlight = np.exp(-((ug - spot_x) ** 2 + ((vg - spot_y) * CH / CW) ** 2) / 0.16) * 0.08
    bevel_rim = smoothstep(-4.5, -0.5, sd0_c) * (0.09 + 0.20 * np.maximum(0.0, math.sin(ang) * (ug - 0.5) * 2.0 + 0.5))
    sheen_col = np.array([0.92, 0.96, 1.0], np.float32) * (glass_band + spotlight + bevel_rim)[..., None]
    card_rgb = np.clip(card_rgb + sheen_col * (1.0 - 0.72 * card_rgb), 0.0, 1.0)

    card_canvas_rgb = np.zeros((H, W, 3), dtype=np.float32)
    card_canvas_rgb[y0_c:y1_c, x0_c:x1_c] = card_rgb
    total_card_a = np.clip(front_mask + edge_alpha * (1.0 - front_mask), 0.0, 1.0)
    total_card_rgb = edge_rgb * (1.0 - front_mask[..., None]) + card_canvas_rgb * front_mask[..., None]

    glints_screen = []
    for g in meta["glints"]:
        zg = 0.012 * CW if g["kind"] == "frame" else (0.016 * CW if g["kind"] == "subject_metal" else z_back)
        comp_g = (D_CAM - zg) / D_CAM
        gl = np.array([(g["x"] - 0.5) * CW * comp_g, (g["y"] - 0.5) * CH * comp_g, zg], dtype=np.float32)
        gc = R @ gl
        gpx = gc[0] * D_CAM / (D_CAM - gc[2]) + W * 0.5
        gpy = (gc[1] + hover_y) * D_CAM / (D_CAM - gc[2]) + H * 0.5
        glints_screen.append({"px": float(gpx), "py": float(gpy), "u": g["x"], "v": g["y"], "size": g["size"], "phase": g["phase"], "kind": g["kind"], "vis": 1.0})

    draw_star_glints(total_card_rgb, glints_screen, sweep_u, t)
    total_card_rgb = np.clip(total_card_rgb * total_card_a[..., None], 0.0, 1.0)

    # Single Hairline Prop Tip Ring & Delicate Cross Flare (cyc 0.43..0.65)
    prop_flare_rgb = np.zeros((H, W, 3), dtype=np.float32)
    if prop_enabled:
        cyc = t % 1.0
        f_life = (cyc - 0.43) / 0.22
        if 0.0 < f_life < 1.0:
            p_tip = prop_fx.get("tip_uv", [0.5, 0.3])
            zf = 0.018 * CW
            comp_f = (D_CAM - zf) / D_CAM
            fl = np.array([(p_tip[0] - 0.5) * CW * comp_f, (p_tip[1] - 0.5) * CH * comp_f, zf], dtype=np.float32)
            fc = R @ fl
            fx_px = fc[0] * D_CAM / (D_CAM - fc[2]) + W * 0.5
            fy_py = (fc[1] + hover_y) * D_CAM / (D_CAM - fc[2]) + H * 0.5
            rad_lim = int(0.16 * CW)
            x0, x1 = max(14, int(fx_px - rad_lim)), min(W - 14, int(fx_px + rad_lim) + 1)
            y0, y1 = max(14, int(fy_py - rad_lim)), min(H - 14, int(fy_py + rad_lim) + 1)
            if x1 > x0 and y1 > y0:
                yyf, xxf = np.mgrid[y0:y1, x0:x1]
                dfx = xxf.astype(np.float32) - fx_px
                dfy = yyf.astype(np.float32) - fy_py
                dist_f = np.hypot(dfx, dfy)
                fade_in = float(smoothstep(0.0, 0.10, np.array(f_life)))
                p_gain = float(prop_fx.get("gain", 0.90))
                p_tint = np.array(prop_fx.get("tint", [0.92, 0.96, 1.0]), dtype=np.float32)
                ring_str = fade_in * ((1.0 - f_life) ** 1.75) * p_gain
                cur_r = (0.014 + 0.105 * (f_life ** 0.58)) * CW
                ring_w = max(1.1, CW * 0.0018)
                arc_mod = 0.70 + 0.30 * np.sin(np.arctan2(dfy, dfx) * 2.0 + 0.65 + ang)
                ring = np.exp(-((dist_f - cur_r) / ring_w) ** 2) * arc_mod * ring_str * 0.62
                fl_env = fade_in * ((1.0 - f_life) ** 2.05) * p_gain
                c_arm = (0.052 + 0.075 * (1.0 - f_life)) * CW
                c_sig = max(0.85, c_arm * 0.022)
                nh = np.exp(-(dfy ** 2) / (2.0 * c_sig ** 2)) * np.exp(-np.abs(dfx) / (c_arm * 0.44))
                nv = np.exp(-(dfx ** 2) / (2.0 * c_sig ** 2)) * np.exp(-np.abs(dfy) / (c_arm * 0.44))
                pin = np.exp(-(dfx ** 2 + dfy ** 2) / (2.0 * max(1.2, c_arm * 0.042) ** 2))
                f_tint = p_tint * 0.45 + np.array([1.0, 0.99, 0.96], dtype=np.float32) * 0.55
                add_p = ring[..., None] * p_tint + np.clip(nh + nv + pin * 0.65, 0.0, 0.92)[..., None] * f_tint * fl_env * 0.94
                in_disk = (dist_f < 0.16 * CW)[..., None]
                prop_flare_rgb[y0:y1, x0:x1] = np.where(in_disk, add_p, 0.0)

    aura_r = np.hypot(px_base / (CW * 0.68), (py_base - hover_y) / (CH * 0.64))
    aura_pulse = 0.65 + 0.35 * math.sin(2.0 * ang)
    aura = np.exp(-(aura_r ** 2) / 0.85) * 0.38 * aura_pulse
    aura_col = aura_c * aura[..., None]

    sh_cy = H * 0.5 + CH * 0.5 + 64.0
    hover_scale = 1.0 - 0.14 * (-hover_y / (0.013 * H))
    sh_rx = CW * 0.44 * hover_scale
    sh_ry = 30.0 * hover_scale
    ground_sh = np.exp(-(((px_base + yaw * 1.05) / sh_rx) ** 2 + ((yy_a - sh_cy) / sh_ry) ** 2) * 1.4) * 0.46

    if motif_id >= 0:
        back_layer_rgb = np.zeros((H, W, 3), dtype=np.float32)
        back_layer_a = np.zeros((H, W), dtype=np.float32)
        front_layer_rgb = np.zeros((H, W, 3), dtype=np.float32)
        front_layer_a = np.zeros((H, W), dtype=np.float32)
        mc1 = np.array(motif.get("color1", pal["part1"]), dtype=np.float32)
        mc2 = np.array(motif.get("color2", pal["part2"]), dtype=np.float32)
        fb = meta.get("face_box") or [0.40, 0.20, 0.60, 0.35]
        fcx, fcy = 0.5 * (fb[0] + fb[2]), 0.5 * (fb[1] + fb[3])
        frx, fry = max(0.5 * (fb[2] - fb[0]), 0.08), max(0.5 * (fb[3] - fb[1]), 0.08)
        for fp in range(4):
            is_bub = (motif_id == 0 and fp >= 2)
            dir_x = -1.0 if motif_id == 2 else (1.0 if motif_id == 1 else 0.0)
            dir_y = -1.0 if motif_id in (0, 3) else 1.0
            pu = 0.08 + 0.84 * math.fmod(_hash12(float(fp), 4.1) + t * dir_x + ((0.035 * math.sin(ang + fp * 1.9)) if motif_id in (0, 3) else 0.0) + 10.0, 1.0)
            pv = 0.08 + 0.84 * math.fmod(_hash12(float(fp), 8.9) + t * dir_y + 10.0, 1.0)
            fdist = math.hypot((pu - fcx) / frx, (pv - fcy) / fry)
            face_safe = 0.14 + 0.86 * float(smoothstep(0.85, 1.55, np.array(fdist)))
            comp_p = (D_CAM - 0.022 * CW) / D_CAM
            ploc = np.array([(pu - 0.5) * CW * comp_p, (pv - 0.5) * CH * comp_p, 0.022 * CW], dtype=np.float32)
            pcam = R @ ploc
            ppx = pcam[0] * D_CAM / (D_CAM - pcam[2]) + W * 0.5
            ppy = (pcam[1] + hover_y) * D_CAM / (D_CAM - pcam[2]) + H * 0.5
            psz = (0.011 if is_bub else (0.016 + 0.005 * _hash12(float(fp), 2.3))) * CW
            ix0, ix1 = max(14, int(ppx - psz * 2.0)), min(W - 14, int(ppx + psz * 2.0) + 1)
            iy0, iy1 = max(14, int(ppy - psz * 2.0)), min(H - 14, int(ppy + psz * 2.0) + 1)
            if ix1 > ix0 and iy1 > iy0:
                yym, xxm = np.mgrid[iy0:iy1, ix0:ix1]
                rot_a = _hash12(float(fp), 7.1) * 6.283 + ang * (1.0 if fp % 2 == 0 else -1.0)
                mcol, ma = eval_sdf_motif_patch(xxm - ppx, yym - ppy, psz, rot_a, ang + fp * 2.1, float(fp) + 3.0, motif_id, is_bub, mc1, mc2, ang)
                am = ma * face_safe * 0.90
                front_layer_rgb[iy0:iy1, ix0:ix1] = front_layer_rgb[iy0:iy1, ix0:ix1] * (1.0 - am[..., None]) + mcol * am[..., None]
                front_layer_a[iy0:iy1, ix0:ix1] = np.clip(front_layer_a[iy0:iy1, ix0:ix1] + am * (1.0 - front_layer_a[iy0:iy1, ix0:ix1]), 0.0, 1.0)

        # Output A: Studio Backdrop Frame (for GIF & QA)
        gif_comp = studio_bg * (1.0 - ground_sh[..., None]) + aura_col
        gif_comp = gif_comp * (1.0 - total_card_a[..., None]) + total_card_rgb
        gif_comp = gif_comp * (1.0 - front_layer_a[..., None]) + front_layer_rgb
        gif_comp = np.clip(gif_comp + prop_flare_rgb, 0.0, 1.0)
        gif_small = cv2.resize((gif_comp * 255.0).astype(np.uint8), (GIF_W, GIF_H), interpolation=cv2.INTER_AREA)

        # Output B: Transparent RGBA Frame (for animated WebP, hard zero alpha cutoff + premultiplied alpha-over SDF motifs)
        aura_tr = aura * (1.0 - smoothstep(0.75, 1.15, aura_r))
        aura_tr_col = aura_c * aura_tr[..., None]
        ground_sh_tr = np.where(ground_sh > 0.02, ground_sh, 0.0)
        sh_only = np.clip(ground_sh_tr * (1.0 - total_card_a), 0.0, 0.65)
        bg_tr_a = np.clip(aura_tr * 0.65 + ground_sh_tr * 0.80, 0.0, 0.88)
        comp_tr_rgb = (aura_tr_col * 0.85) * (1.0 - sh_only[..., None]) * (1.0 - total_card_a[..., None]) + total_card_rgb
        comp_tr_a = np.clip(np.maximum(total_card_a, np.maximum(bg_tr_a, sh_only)), 0.0, 1.0)
        comp_tr_rgb = comp_tr_rgb * (1.0 - front_layer_a[..., None]) + front_layer_rgb
        comp_tr_a = np.clip(front_layer_a + comp_tr_a * (1.0 - front_layer_a), 0.0, 1.0)
        flare_max = np.max(prop_flare_rgb, axis=-1)
        comp_tr_a = np.clip(np.maximum(comp_tr_a, flare_max), 0.0, 1.0)
        comp_tr_rgb = np.minimum(comp_tr_rgb + prop_flare_rgb, comp_tr_a[..., None])
        comp_tr_a = np.where(comp_tr_a < 0.015, 0.0, comp_tr_a)
        straight_rgb = np.where(comp_tr_a[..., None] > 0.0, comp_tr_rgb / np.maximum(comp_tr_a[..., None], 1e-4), 0.0)
        webp_rgba = np.dstack([
            np.clip(straight_rgb * 255.0, 0, 255),
            np.clip(comp_tr_a[..., None] * 255.0, 0, 255),
        ]).astype(np.uint8)
        return f_idx, gif_small, webp_rgba

    back_layer_rgb = np.zeros((H, W, 3), dtype=np.float32)
    back_layer_a = np.zeros((H, W), dtype=np.float32)
    for pi in range(len(back_parts["x"])):
        bx = (back_parts["x"][pi] + back_parts["amp_x"][pi] * math.sin(ang * back_parts["freq"][pi] + back_parts["ph"][pi]) - yaw * 0.0022) * W
        by = (back_parts["y"][pi] + back_parts["amp_y"][pi] * math.cos(ang * back_parts["freq"][pi] + back_parts["ph"][pi]) - pitch * 0.0018) * H
        pr = float(back_parts["rad"][pi])
        ix0, ix1 = max(0, int(bx - pr * 3)), min(W, int(bx + pr * 3) + 1)
        iy0, iy1 = max(0, int(by - pr * 3)), min(H, int(by + pr * 3) + 1)
        if ix1 <= ix0 or iy1 <= iy0:
            continue
        yy_p, xx_p = np.mgrid[iy0:iy1, ix0:ix1]
        g_p = np.exp(-((xx_p - bx) ** 2 + (yy_p - by) ** 2) / (2.0 * (pr * 0.9) ** 2)) * 0.55
        back_layer_rgb[iy0:iy1, ix0:ix1] += g_p[..., None] * back_parts["col"][pi]
        back_layer_a[iy0:iy1, ix0:ix1] = np.maximum(back_layer_a[iy0:iy1, ix0:ix1], g_p)

    front_layer_rgb = np.zeros((H, W, 3), dtype=np.float32)
    front_layer_a = np.zeros((H, W), dtype=np.float32)
    for pi in range(len(front_parts["x"])):
        fx = (front_parts["x"][pi] + front_parts["amp_x"][pi] * math.sin(ang * front_parts["freq"][pi] + front_parts["ph"][pi]) + yaw * 0.0055) * W
        fy = (front_parts["y"][pi] + front_parts["amp_y"][pi] * math.cos(ang * front_parts["freq"][pi] + front_parts["ph"][pi]) + pitch * 0.0045) * H
        pr = float(front_parts["rad"][pi])
        ix0, ix1 = max(0, int(fx - pr * 3.5)), min(W, int(fx + pr * 3.5) + 1)
        iy0, iy1 = max(0, int(fy - pr * 3.5)), min(H, int(fy + pr * 3.5) + 1)
        if ix1 <= ix0 or iy1 <= iy0:
            continue
        yy_p, xx_p = np.mgrid[iy0:iy1, ix0:ix1]
        g_p = np.exp(-((xx_p - fx) ** 2 + (yy_p - fy) ** 2) / (2.0 * (pr * 1.25) ** 2)) * 0.42
        front_layer_rgb[iy0:iy1, ix0:ix1] += g_p[..., None] * front_parts["col"][pi]
        front_layer_a[iy0:iy1, ix0:ix1] = np.maximum(front_layer_a[iy0:iy1, ix0:ix1], g_p)

    # Output A: Studio Backdrop Frame (for GIF & QA)
    gif_comp = studio_bg * (1.0 - ground_sh[..., None]) + aura_col + back_layer_rgb
    gif_comp = gif_comp * (1.0 - total_card_a[..., None]) + total_card_rgb
    gif_comp = np.clip(gif_comp + front_layer_rgb + prop_flare_rgb, 0.0, 1.0)
    gif_small = cv2.resize((gif_comp * 255.0).astype(np.uint8), (GIF_W, GIF_H), interpolation=cv2.INTER_AREA)

    # Output B: Transparent RGBA Frame (for animated WebP, hard zero alpha cutoff)
    aura_tr = aura * (1.0 - smoothstep(0.75, 1.15, aura_r))
    aura_tr_col = aura_c * aura_tr[..., None]
    ground_sh_tr = np.where(ground_sh > 0.02, ground_sh, 0.0)
    back_a_tr = np.where(back_layer_a > 0.02, back_layer_a, 0.0)
    front_a_tr = np.where(front_layer_a > 0.02, front_layer_a, 0.0)
    back_rgb_tr = np.where(back_a_tr[..., None] > 0.0, back_layer_rgb, 0.0)
    front_rgb_tr = np.where(front_a_tr[..., None] > 0.0, front_layer_rgb, 0.0)

    bg_tr_rgb = aura_tr_col * 0.85 + back_rgb_tr
    bg_tr_a = np.clip(aura_tr * 0.65 + back_a_tr * 0.75 + ground_sh_tr * 0.80, 0.0, 0.88)
    sh_only = np.clip(ground_sh_tr * (1.0 - total_card_a), 0.0, 0.65)
    comp_tr_rgb = bg_tr_rgb * (1.0 - sh_only[..., None]) * (1.0 - total_card_a[..., None]) + total_card_rgb + front_rgb_tr + prop_flare_rgb
    comp_tr_a = np.clip(np.maximum(total_card_a, np.maximum(bg_tr_a, sh_only)) + front_a_tr * 0.5, 0.0, 1.0)
    comp_tr_a = np.clip(np.maximum(comp_tr_a, np.max(prop_flare_rgb, axis=-1)), 0.0, 1.0)
    comp_tr_a = np.where(comp_tr_a < 0.015, 0.0, comp_tr_a)
    straight_rgb = np.where(comp_tr_a[..., None] > 0.0, np.minimum(comp_tr_rgb, comp_tr_a[..., None]) / np.maximum(comp_tr_a[..., None], 1e-4), 0.0)
    webp_rgba = np.dstack([
        np.clip(straight_rgb * 255.0, 0, 255),
        np.clip(comp_tr_a[..., None] * 255.0, 0, 255),
    ]).astype(np.uint8)
    return f_idx, gif_small, webp_rgba


def set_webp_dispose_background(path: Path) -> int:
    """Set dispose=1 (clear to transparent bg before next frame) & no_blend=1 on all ANMF chunks."""
    data = bytearray(path.read_bytes())
    pos = 12
    count = 0
    while pos + 8 <= len(data):
        cid = bytes(data[pos:pos + 4])
        csz = int.from_bytes(data[pos + 4:pos + 8], "little")
        if cid == b"ANMF" and pos + 24 <= len(data):
            data[pos + 23] = (data[pos + 23] & ~0x03) | 0x03
            count += 1
        pos += 8 + csz + (csz & 1)
    path.write_bytes(bytes(data))
    return count


def main():
    parser = argparse.ArgumentParser(description="Render 84-frame animated WebP & GIF collector cards.")
    parser.add_argument("--workdir", required=True, type=Path, help="Project workspace directory")
    parser.add_argument("--frames", type=int, default=84)
    parser.add_argument("--duration-ms", type=int, default=60)
    parser.add_argument("--webp-quality", type=int, default=88)
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 4))
    parser.add_argument("--webp-only", action="store_true")
    args = parser.parse_args()

    workdir = args.workdir.resolve()
    proc_dir = workdir / "03_processed"
    out_dir = workdir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    t_start = time.time()
    n_frames = args.frames
    workers = max(1, args.workers)
    print(f"Rendering {n_frames} frames across {workers} worker processes (dur={args.duration_ms}ms, webp_only={args.webp_only})...")

    results = [None] * n_frames
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker, initargs=(str(proc_dir), n_frames)) as pool:
        for done_count, (f_idx, gif_small, webp_rgba) in enumerate(pool.map(render_single_frame, range(n_frames)), start=1):
            results[f_idx] = (Image.fromarray(gif_small, "RGB"), Image.fromarray(webp_rgba, "RGBA"))
            if done_count % max(1, n_frames // 4) == 0 or done_count == n_frames:
                print(f"Rendered {done_count}/{n_frames} frames ({time.time() - t_start:.1f}s)")

    gif_rgb_frames = [r[0] for r in results]
    webp_frames = [r[1] for r in results]
    durations = [args.duration_ms] * n_frames

    # 1. Animated RGBA WebP with independent keyframes & dispose=1 + no_blend=1
    webp_path = out_dir / "holographic_card.webp"
    webp_frames[0].save(
        webp_path,
        save_all=True,
        append_images=webp_frames[1:],
        duration=durations,
        loop=0,
        background=(0, 0, 0, 0),
        minimize_size=False,
        kmin=1,
        kmax=1,
        lossless=False,
        quality=args.webp_quality,
        method=4,
    )
    n_anmf = set_webp_dispose_background(webp_path)
    print(f"Saved {webp_path} ({webp_path.stat().st_size / 1024:.1f} KB, ANMF dispose=1 count={n_anmf})")

    if args.webp_only:
        return

    # 2. Shared 256-color Median Cut palette from 8 evenly spaced frames + Floyd-Steinberg dithering
    rep_indices = [int((i * n_frames) // 8) for i in range(8)]
    mosaic = Image.new("RGB", (GIF_W * 4, GIF_H * 2))
    for idx_i, f_i in enumerate(rep_indices):
        mosaic.paste(gif_rgb_frames[min(f_i, n_frames - 1)], ((idx_i % 4) * GIF_W, (idx_i // 4) * GIF_H))
    shared_palette = mosaic.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)

    gif_q_frames = [fr.quantize(palette=shared_palette, dither=Image.Dither.FLOYDSTEINBERG) for fr in gif_rgb_frames]
    gif_path = out_dir / "holographic_card.gif"
    gif_q_frames[0].save(
        gif_path,
        save_all=True,
        append_images=gif_q_frames[1:],
        duration=durations,
        loop=0,
        optimize=False,
    )
    print(f"Saved {gif_path} ({gif_path.stat().st_size / 1024:.1f} KB)")

    # 3. Export QA contact sheet: [0, mid_prop_gleam(0.37), peak_tip_flare(0.49), q3, last, webp[peak]_over_checker]
    f_gleam = min(n_frames - 1, max(0, int(round(0.37 * n_frames))))
    f_flare = min(n_frames - 1, max(0, int(round(0.49 * n_frames))))
    f_q1 = min(n_frames - 1, max(0, n_frames // 4))
    f_q3 = min(n_frames - 1, max(0, (3 * n_frames) // 4))
    f_last = n_frames - 1

    sq = 24
    yy_c, xx_c = np.mgrid[0:GIF_H, 0:GIF_W]
    chk = np.where((((xx_c // sq) + (yy_c // sq)) % 2)[..., None] == 0, np.array([210, 215, 224], np.uint8), np.array([238, 241, 247], np.uint8))
    webp_chk_small = webp_frames[f_flare].resize((GIF_W, GIF_H), Image.Resampling.LANCZOS)
    webp_chk = Image.alpha_composite(Image.fromarray(chk, "RGB").convert("RGBA"), webp_chk_small).convert("RGB")

    panels = [gif_rgb_frames[0], gif_rgb_frames[f_gleam], gif_rgb_frames[f_flare], gif_rgb_frames[f_q3], gif_rgb_frames[f_last], webp_chk]
    qa_sheet = Image.new("RGB", (GIF_W * 3, GIF_H * 2), (10, 12, 18))
    for i, pan in enumerate(panels):
        qa_sheet.paste(pan, ((i % 3) * GIF_W, (i // 3) * GIF_H))
    qa_sheet.save(proc_dir / "qa_keyframes.png")
    print(f"Saved QA contact sheet: {proc_dir / 'qa_keyframes.png'}")


if __name__ == "__main__":
    main()
