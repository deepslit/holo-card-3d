"""Stage 4: Build frozen-standard 60fps offline single-file WebGL2 interactive 3D card."""
import argparse
import base64
import html
import io
import json
import sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TEX_W, TEX_H = 768, 1024

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
    "ui_accent": "#ffd97d",
}


def premult_blur_u8(rgba_img: Image.Image, sigma: float) -> Image.Image:
    arr = np.array(rgba_img.convert("RGBA"), dtype=np.float32) / 255.0
    rgb = arr[..., :3]
    a = arr[..., 3:4]
    k = int(np.ceil(sigma * 3.0)) * 2 + 1
    pre_b = cv2.GaussianBlur(rgb * a, (k, k), sigma)
    a_b = cv2.GaussianBlur(a, (k, k), sigma)
    if a_b.ndim == 2:
        a_b = a_b[..., None]
    rgb_out = np.where(a_b > 1e-4, pre_b / np.maximum(a_b, 1e-4), 0.0)
    out = np.concatenate([np.clip(rgb_out, 0.0, 1.0), np.clip(a_b, 0.0, 1.0)], axis=-1)
    return Image.fromarray((out * 255.0).astype(np.uint8), "RGBA")


def encode_webp_uri(img: Image.Image, quality: int = 90) -> str:
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=quality, lossless=False, method=4)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def encode_png_uri(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>__TITLE__ · 3D 全息流麻收藏卡 (__BADGE__)</title>
<style>
  :root {
    --accent: __UI_ACCENT__;
    --accent-rgb: __UI_ACCENT_RGB__;
    --accent-deep: __UI_ACCENT_DEEP__;
    --studio-rgb: __STUDIO_RGB__;
    --text-main: rgba(246, 247, 250, 0.94);
    --text-muted: rgba(226, 230, 238, 0.68);
    --text-dim: rgba(220, 225, 234, 0.40);
    --glass-bg: rgba(20, 21, 25, 0.78);
    --glass-border: rgba(255, 255, 255, 0.11);
    --glass-highlight: rgba(255, 255, 255, 0.13);
    --glass-shadow: 0 18px 44px rgba(0, 0, 0, 0.56), 0 2px 10px rgba(0, 0, 0, 0.34);
    --btn-hover: rgba(255, 255, 255, 0.09);
    --sep: rgba(255, 255, 255, 0.12);
    --track-bg: rgba(255, 255, 255, 0.16);
    --slider-col: rgba(242, 244, 248, 0.90);
    --corner-col: rgba(255, 255, 255, 0.14);
    --plaque-shadow: 0 2px 16px rgba(0, 0, 0, 0.65);
    --badge-bg: rgba(255, 255, 255, 0.08);
    --badge-border: rgba(255, 255, 255, 0.16);
    --badge-fg: rgba(246, 247, 250, 0.92);
    --badge-dot: rgba(246, 247, 250, 0.78);
    --active-bg: rgba(244, 245, 248, 0.95);
    --active-border: rgba(255, 255, 255, 0.95);
    --active-fg: #111318;
    --active-dot: #111318;
  }
  body.theme-light {
    --text-main: rgba(16, 22, 36, 0.92);
    --text-muted: rgba(38, 50, 72, 0.72);
    --text-dim: rgba(45, 58, 80, 0.46);
    --glass-bg: rgba(255, 255, 255, 0.78);
    --glass-border: rgba(15, 23, 42, 0.11);
    --glass-highlight: rgba(255, 255, 255, 0.92);
    --glass-shadow: 0 14px 36px rgba(15, 23, 42, 0.10), 0 2px 8px rgba(15, 23, 42, 0.06);
    --btn-hover: rgba(15, 23, 42, 0.06);
    --sep: rgba(15, 23, 42, 0.12);
    --track-bg: rgba(15, 23, 42, 0.15);
    --slider-col: var(--accent-deep);
    --corner-col: rgba(15, 23, 42, 0.18);
    --plaque-shadow: 0 1px 10px rgba(255, 255, 255, 0.65);
    --badge-bg: rgba(16, 22, 36, 0.90);
    --badge-border: rgba(16, 22, 36, 0.92);
    --badge-fg: var(--accent);
    --badge-dot: var(--accent);
    --active-bg: rgba(16, 22, 36, 0.90);
    --active-border: rgba(16, 22, 36, 0.92);
    --active-fg: #ffffff;
    --active-dot: var(--accent);
  }

  * { box-sizing: border-box; user-select: none; -webkit-user-select: none; -webkit-tap-highlight-color: transparent; }
  html, body {
    margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden;
    background: #07080b; color: var(--text-main);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  #glcanvas {
    position: fixed; inset: 0; width: 100%; height: 100%; display: block;
    touch-action: none; cursor: grab;
    opacity: 0; transition: opacity 0.42s cubic-bezier(0.22, 1, 0.36, 1);
  }
  #glcanvas.ready { opacity: 1; }
  #glcanvas:active { cursor: grabbing; }

  /* Subtle museum vitrine corner hairlines (zero-cost static CSS) */
  .vitrine-corners {
    position: fixed; inset: 18px; z-index: 5; pointer-events: none;
    transition: opacity 0.32s ease;
  }
  .vitrine-corners i {
    position: absolute; width: 14px; height: 14px;
    border-color: var(--corner-col); border-style: solid; border-width: 0;
    transition: border-color 0.28s ease;
  }
  .vitrine-corners .c-tl { top: 0; left: 0; border-top-width: 1px; border-left-width: 1px; }
  .vitrine-corners .c-tr { top: 0; right: 0; border-top-width: 1px; border-right-width: 1px; }
  .vitrine-corners .c-bl { bottom: 0; left: 0; border-bottom-width: 1px; border-left-width: 1px; }
  .vitrine-corners .c-br { bottom: 0; right: 0; border-bottom-width: 1px; border-right-width: 1px; }

  /* Top-left editorial gallery plaque */
  .plaque {
    position: fixed; top: 28px; left: 32px; z-index: 10;
    pointer-events: none; max-width: min(440px, calc(100vw - 156px));
    display: flex; flex-direction: column; gap: 6px;
    transition: opacity 0.32s ease, transform 0.32s cubic-bezier(0.22, 1, 0.36, 1);
  }
  .plaque-meta {
    display: flex; align-items: center; gap: 10px;
  }
  .plaque-chip {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 3px 9px 3px 8px; border-radius: 999px;
    background: var(--badge-bg); border: 1px solid var(--badge-border);
    color: var(--badge-fg);
    font-size: 10px; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase;
    line-height: 1.25;
    transition: background 0.25s ease, border-color 0.25s ease;
  }
  .plaque-chip::before {
    content: ""; width: 4.5px; height: 4.5px; border-radius: 1px;
    background: var(--badge-dot); transform: rotate(45deg);
  }
  .plaque-kicker {
    font-size: 10px; font-weight: 500; letter-spacing: 0.18em; text-transform: uppercase;
    color: var(--text-dim); text-shadow: var(--plaque-shadow);
  }
  .plaque-title {
    margin: 0; font-size: clamp(17px, 2vw, 21px); font-weight: 500;
    letter-spacing: 0.06em; line-height: 1.25; color: var(--text-main);
    text-shadow: var(--plaque-shadow);
    transition: color 0.25s ease;
  }
  .plaque-sub {
    margin: 0; font-size: 11.5px; font-weight: 400; letter-spacing: 0.03em; line-height: 1.45;
    color: var(--text-muted); text-shadow: var(--plaque-shadow);
    transition: color 0.25s ease;
  }
  .plaque-sub:empty { display: none; }

  /* Top-right minimal Language & Zen controls */
  .top-actions {
    position: fixed; top: 26px; right: 28px; z-index: 20;
    display: inline-flex; align-items: center; gap: 8px;
  }
  .lang-btn, .zen-btn {
    height: 36px; border-radius: 999px;
    display: inline-flex; align-items: center; justify-content: center;
    background: var(--glass-bg); border: 1px solid var(--glass-border);
    box-shadow: inset 0 1px 0 var(--glass-highlight), 0 8px 22px rgba(0, 0, 0, 0.22);
    backdrop-filter: blur(12px) saturate(140%); -webkit-backdrop-filter: blur(12px) saturate(140%);
    color: var(--text-muted); cursor: pointer;
    transition: opacity 0.28s ease, background 0.18s ease, color 0.18s ease, transform 0.14s ease, border-color 0.2s ease;
  }
  .lang-btn {
    padding: 0 11px; min-width: 42px;
    font-size: 11px; font-weight: 600; letter-spacing: 0.08em;
  }
  .zen-btn { width: 36px; padding: 0; }
  .lang-btn:hover, .zen-btn:hover { color: var(--text-main); border-color: var(--glass-highlight); }
  .lang-btn:active, .zen-btn:active { transform: scale(0.93); }
  .zen-btn svg { width: 15px; height: 15px; stroke: currentColor; fill: none; stroke-width: 1.65; stroke-linecap: round; stroke-linejoin: round; }

  /* Subtle ephemeral gesture hint */
  .hint-pill {
    position: fixed; bottom: 76px; left: 50%; transform: translateX(-50%); z-index: 9;
    pointer-events: none; white-space: nowrap;
    font-size: 11px; letter-spacing: 0.08em; color: var(--text-dim);
    text-shadow: var(--plaque-shadow);
    transition: opacity 0.6s ease, transform 0.6s ease;
  }
  .hint-pill.faded { opacity: 0; transform: translate(-50%, 6px); }

  /* Bottom single-row floating glass dock */
  .controls {
    position: fixed; bottom: 22px; left: 50%; transform: translateX(-50%); z-index: 12;
    display: inline-flex; align-items: center; gap: 3px;
    height: 44px; padding: 4px 10px 4px 5px; border-radius: 999px;
    max-width: calc(100vw - 24px);
    background: var(--glass-bg);
    border: 1px solid var(--glass-border);
    box-shadow: inset 0 1px 0 var(--glass-highlight), var(--glass-shadow);
    backdrop-filter: blur(14px) saturate(150%); -webkit-backdrop-filter: blur(14px) saturate(150%);
    transition: opacity 0.32s ease, transform 0.32s cubic-bezier(0.22, 1, 0.36, 1), background 0.25s ease, border-color 0.25s ease;
  }
  .dock-sep {
    width: 1px; height: 18px; margin: 0 4px; flex-shrink: 0;
    background: var(--sep);
  }
  .btn {
    appearance: none; border: 1px solid transparent; background: transparent;
    color: var(--text-muted); height: 34px; padding: 0 11px; border-radius: 999px;
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    font-size: 12px; font-weight: 500; letter-spacing: 0.02em; white-space: nowrap;
    cursor: pointer; flex-shrink: 0;
    transition: background 0.16s ease, color 0.16s ease, border-color 0.18s ease, transform 0.12s ease;
  }
  .btn.icon-only { width: 34px; padding: 0; }
  .btn svg {
    width: 14px; height: 14px; flex-shrink: 0;
    stroke: currentColor; fill: none; stroke-width: 1.65; stroke-linecap: round; stroke-linejoin: round;
  }
  .btn:hover { background: var(--btn-hover); color: var(--text-main); }
  .btn:active { transform: scale(0.95); }
  .btn.active, .btn.active:hover {
    background: var(--active-bg);
    border-color: var(--active-border);
    color: var(--active-fg);
  }
  .btn .status-dot {
    width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0;
    background: currentColor; opacity: 0.35;
    transition: background 0.2s ease, opacity 0.2s ease, box-shadow 0.2s ease;
  }
  .btn.active .status-dot {
    background: var(--active-dot); opacity: 1;
  }
  .bg-swatch {
    width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
    border: 1px solid rgba(255, 255, 255, 0.38);
    background: rgb(var(--studio-rgb));
    box-shadow: inset 0 1px 2px rgba(255, 255, 255, 0.25);
    transition: background 0.25s ease, border-color 0.25s ease;
  }
  body.theme-light .bg-swatch { border-color: rgba(15, 23, 42, 0.22); }

  /* Custom refined holo intensity slider */
  .holo-ctrl {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 0 4px 0 6px; height: 34px; flex-shrink: 0;
    color: var(--text-muted);
  }
  .holo-ctrl svg {
    width: 14px; height: 14px; flex-shrink: 0;
    stroke: var(--slider-col); fill: none; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round;
    opacity: 0.95;
  }
  .holo-val {
    font-size: 11px; font-weight: 500; font-variant-numeric: tabular-nums;
    color: var(--text-muted); min-width: 32px; text-align: right;
  }
  input[type="range"].holo-range {
    -webkit-appearance: none; appearance: none;
    width: 74px; height: 22px; background: transparent; cursor: pointer; margin: 0;
    --pct: 60.7%;
  }
  input[type="range"].holo-range:focus { outline: none; }
  input[type="range"].holo-range::-webkit-slider-runnable-track {
    height: 3px; border-radius: 999px;
    background: linear-gradient(to right, var(--slider-col) 0%, var(--slider-col) var(--pct), var(--track-bg) var(--pct), var(--track-bg) 100%);
  }
  input[type="range"].holo-range::-webkit-slider-thumb {
    -webkit-appearance: none; appearance: none;
    width: 12px; height: 12px; border-radius: 50%; margin-top: -4.5px;
    background: #ffffff;
    border: 1.5px solid var(--slider-col);
    box-shadow: 0 1px 6px rgba(0, 0, 0, 0.42);
    transition: transform 0.14s ease, box-shadow 0.16s ease;
  }
  input[type="range"].holo-range:hover::-webkit-slider-thumb {
    transform: scale(1.16);
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.48), 0 0 0 3px rgba(255, 255, 255, 0.12);
  }
  input[type="range"].holo-range::-moz-range-track {
    height: 3px; border-radius: 999px; background: var(--track-bg);
  }
  input[type="range"].holo-range::-moz-range-progress {
    height: 3px; border-radius: 999px; background: var(--slider-col);
  }
  input[type="range"].holo-range::-moz-range-thumb {
    width: 12px; height: 12px; border-radius: 50%;
    background: #ffffff; border: 1.5px solid var(--slider-col);
    box-shadow: 0 1px 6px rgba(0, 0, 0, 0.36);
  }

  /* Compact floating craft preset popover (hidden by default for zero clutter) */
  .craft-pop {
    position: fixed; bottom: 76px; left: 50%; z-index: 16;
    transform: translate(-50%, 8px); opacity: 0; pointer-events: none;
    width: max-content; max-width: calc(100vw - 24px);
    padding: 12px 14px; border-radius: 18px;
    background: var(--glass-bg);
    border: 1px solid var(--glass-border);
    box-shadow: inset 0 1px 0 var(--glass-highlight), var(--glass-shadow);
    backdrop-filter: blur(18px) saturate(150%); -webkit-backdrop-filter: blur(18px) saturate(150%);
    display: flex; flex-direction: column; gap: 9px;
    transition: opacity 0.22s ease, transform 0.22s cubic-bezier(0.22, 1, 0.36, 1);
  }
  .craft-pop.open { opacity: 1; pointer-events: auto; transform: translate(-50%, 0); }
  .craft-row { display: flex; align-items: center; gap: 8px; }
  .craft-lbl {
    font-size: 11px; font-weight: 500; letter-spacing: 0.05em; color: var(--text-dim);
    width: 42px; flex-shrink: 0;
  }
  .craft-chips { display: flex; flex-wrap: wrap; gap: 4px; flex: 1; }
  .chip {
    appearance: none; border: 1px solid transparent; background: transparent;
    color: var(--text-muted); height: 26px; padding: 0 9px; border-radius: 999px;
    font-size: 11.5px; font-weight: 500; letter-spacing: 0.01em; cursor: pointer;
    transition: background 0.08s ease, color 0.08s ease, border-color 0.08s ease;
  }
  .chip:hover { background: var(--btn-hover); color: var(--text-main); }
  .chip.active, .chip.active:hover {
    background: var(--active-bg); border-color: var(--active-border); color: var(--active-fg);
  }
  .craft-divider { height: 1px; background: var(--sep); margin: 2px 0; }
  .craft-export { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .exp-btn {
    appearance: none; border: 1px solid var(--glass-border); background: var(--btn-hover);
    color: var(--text-main); height: 28px; padding: 0 11px; border-radius: 999px;
    display: inline-flex; align-items: center; gap: 5px;
    font-size: 11.5px; font-weight: 500; letter-spacing: 0.01em; cursor: pointer;
    transition: background 0.14s ease, border-color 0.14s ease, opacity 0.14s ease, transform 0.1s ease;
  }
  .exp-btn svg {
    width: 12.5px; height: 12.5px; stroke: currentColor; fill: none;
    stroke-width: 1.75; stroke-linecap: round; stroke-linejoin: round;
  }
  .exp-btn:hover:not(:disabled) { border-color: var(--glass-highlight); background: rgba(255,255,255,0.14); }
  body.theme-light .exp-btn:hover:not(:disabled) { background: rgba(15,23,42,0.10); }
  .exp-btn:active:not(:disabled) { transform: scale(0.96); }
  .exp-btn:disabled { opacity: 0.45; cursor: progress; }
  .exp-btn.primary {
    background: var(--active-bg); border-color: var(--active-border); color: var(--active-fg);
  }
  .exp-btn.primary:hover:not(:disabled) { opacity: 0.90; background: var(--active-bg); }
  .exp-status {
    display: none; flex-direction: column; gap: 5px; padding-top: 2px;
  }
  .exp-status.show { display: flex; }
  .exp-status-txt {
    font-size: 11px; color: var(--text-muted); font-variant-numeric: tabular-nums;
    display: flex; justify-content: space-between; align-items: center;
  }
  .exp-bar {
    height: 2.5px; border-radius: 999px; background: var(--track-bg); overflow: hidden;
  }
  .exp-bar-fill {
    height: 100%; width: 0%; border-radius: 999px; background: var(--slider-col);
    transition: width 0.08s linear;
  }

  /* Zen mode (pure showcase, hide all HUD chrome) */
  body.zen-mode .plaque { opacity: 0; transform: translateY(-8px); pointer-events: none; }
  body.zen-mode .controls { opacity: 0; transform: translate(-50%, 14px); pointer-events: none; }
  body.zen-mode .craft-pop { opacity: 0; transform: translate(-50%, 14px); pointer-events: none; }
  body.zen-mode .vitrine-corners, body.zen-mode .hint-pill { opacity: 0; }
  body.zen-mode .lang-btn { opacity: 0; pointer-events: none; }
  body.zen-mode .zen-btn { opacity: 0.24; }
  body.zen-mode .zen-btn:hover { opacity: 0.92; }

  #errBanner {
    display: none; position: fixed; inset: 0; z-index: 40;
    align-items: center; justify-content: center; padding: 28px;
    background: rgba(6, 10, 20, 0.94); color: #ffb4b4;
    font-size: 13px; line-height: 1.6; text-align: center; white-space: pre-wrap;
  }

  @media (max-width: 640px) {
    .vitrine-corners { inset: 12px; }
    .plaque { top: 20px; left: 20px; max-width: calc(100vw - 122px); gap: 4px; }
    .plaque-kicker { display: none; }
    .plaque-sub { font-size: 11px; }
    .top-actions { top: 18px; right: 18px; gap: 6px; }
    .lang-btn { height: 34px; padding: 0 9px; min-width: 38px; font-size: 10.5px; }
    .zen-btn { width: 34px; height: 34px; }
    .controls {
      bottom: 16px; height: 42px; padding: 4px 8px 4px 4px; gap: 2px;
    }
    .btn { height: 32px; padding: 0 8px; font-size: 11.5px; }
    .btn.icon-only { width: 32px; }
    .btn .lbl-hide-sm { display: none; }
    .dock-sep { margin: 0 2px; }
    input[type="range"].holo-range { width: 58px; }
    .holo-val { display: none; }
    .hint-pill { bottom: 68px; font-size: 10.5px; }
  }
</style>
</head>
<body>
<canvas id="glcanvas"></canvas>

<div class="vitrine-corners" aria-hidden="true">
  <i class="c-tl"></i><i class="c-tr"></i><i class="c-bl"></i><i class="c-br"></i>
</div>

<header class="plaque" id="badge"__BADGE_STYLE__>
  <div class="plaque-meta">
    <span class="plaque-chip">__BADGE__</span>
    <span class="plaque-kicker">3D HOLOGRAPHIC</span>
  </div>
  <h1 class="plaque-title">__TITLE__</h1>
  <p class="plaque-sub">__SUBTITLE__</p>
</header>

<div class="top-actions">
  <button class="lang-btn" id="btnLang" title="Switch to English" aria-label="Switch Language">EN</button>
  <button class="zen-btn" id="btnZen" title="纯净模式 (H)" aria-label="切换界面显示">
    <svg id="iconEyeOpen" viewBox="0 0 24 24"><path d="M2.5 12s3.5-6.5 9.5-6.5S21.5 12 21.5 12s-3.5 6.5-9.5 6.5S2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="2.8"/></svg>
    <svg id="iconEyeClosed" viewBox="0 0 24 24" style="display:none"><path d="M3 3l18 18"/><path d="M10.6 10.7a2.8 2.8 0 0 0 3.7 3.7"/><path d="M9.4 5.8A9.8 9.8 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a16.4 16.4 0 0 1-3.1 4"/><path d="M6.2 7.5A16.7 16.7 0 0 0 2.5 12s3.5 6.5 9.5 6.5c1.4 0 2.7-.3 3.9-.8"/></svg>
  </button>
</div>

<div class="hint-pill" id="hintPill">悬停或拖拽赏卡 · 双击归零 · H 隐藏界面</div>

<div class="craft-pop" id="craftPop" role="dialog" aria-label="材质、光影与底纹实时切换">
  <div class="craft-row">
    <span class="craft-lbl" id="lblMat">材质</span>
    <div class="craft-chips" id="matChips">
      <button class="chip" data-mat="0">流麻 SAR</button>
      <button class="chip" data-mat="1">亚克力砖</button>
      <button class="chip" data-mat="2">碎冰闪</button>
      <button class="chip" data-mat="3">浮雕箔</button>
      <button class="chip" data-mat="4">丝绒烫金</button>
      <button class="chip" data-mat="5">纯净闪卡</button>
    </div>
  </div>
  <div class="craft-row">
    <span class="craft-lbl" id="lblLit">光影</span>
    <div class="craft-chips" id="litChips">
      <button class="chip" data-lit="0">展柜均衡</button>
      <button class="chip" data-lit="1">戏剧轮廓</button>
      <button class="chip" data-lit="2">暖阳鎏金</button>
      <button class="chip" data-lit="3">冷月幽光</button>
      <button class="chip" data-lit="4">柔光箱</button>
    </div>
  </div>
  <div class="craft-row">
    <span class="craft-lbl" id="lblHolo">底纹</span>
    <div class="craft-chips" id="holoChips">
      <button class="chip" data-holo="0">星芒</button>
      <button class="chip" data-holo="1">棱镜格</button>
      <button class="chip" data-holo="2">星海波</button>
      <button class="chip" data-holo="3">碎冰晶</button>
      <button class="chip" data-holo="4">斜向拉丝</button>
      <button class="chip" data-holo="5">菱格暗纹</button>
    </div>
  </div>
  <div class="craft-divider"></div>
  <div class="craft-row">
    <span class="craft-lbl" id="lblExp">导出</span>
    <div class="craft-export">
      <button class="exp-btn primary" id="btnExpWebp" title="离线导出 690×960 透明零残影动图 WebP（不覆盖原文件）">
        <svg viewBox="0 0 24 24"><path d="M12 3v12m0 0-4-4m4 4 4-4"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>
        <span id="expWebpLbl">透明 WebP</span>
      </button>
      <button class="exp-btn" id="btnExpGif" title="离线导出 460×640 当前背景动图 GIF（不覆盖原文件）">
        <svg viewBox="0 0 24 24"><path d="M12 3v12m0 0-4-4m4 4 4-4"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>
        <span id="expGifLbl">动图 GIF</span>
      </button>
      <button class="exp-btn" id="btnCopyCfg" title="复制当前工艺配置 JSON 片段">
        <svg viewBox="0 0 24 24"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
        <span id="copyCfgLbl">复制参数</span>
      </button>
    </div>
  </div>
  <div class="exp-status" id="expStatus">
    <div class="exp-status-txt"><span id="expTxt">准备中…</span><span id="expPct">0%</span></div>
    <div class="exp-bar"><div class="exp-bar-fill" id="expFill"></div></div>
  </div>
</div>

<nav class="controls" id="controls" aria-label="3D 卡片控制栏">
  <button class="btn active" id="btnOrbit" title="自动巡航 (Space)">
    <span class="status-dot"></span>
    <svg viewBox="0 0 24 24"><ellipse cx="12" cy="12" rx="9" ry="4.2" transform="rotate(-24 12 12)"/><circle cx="12" cy="12" r="2.2"/></svg>
    <span class="lbl-hide-sm" id="orbitLbl">巡航</span>
  </button>
  <button class="btn icon-only" id="btnReset" title="归零 0° (双击画布)" aria-label="归零角度">
    <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="7.5"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3"/><circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/></svg>
  </button>
  <button class="btn icon-only" id="btnGyro" title="陀螺仪倾摆" aria-label="陀螺仪倾摆">
    <svg viewBox="0 0 24 24"><rect x="7" y="3.5" width="10" height="17" rx="2.2"/><path d="M11 17.5h2"/><path d="M3.2 9.5a11 11 0 0 0 0 5M20.8 9.5a11 11 0 0 1 0 5"/></svg>
  </button>

  <span class="dock-sep" aria-hidden="true"></span>

  <button class="btn" id="btnBg" title="切换展台背景">
    <span class="bg-swatch" id="bgSwatch"></span>
    <span id="bgLabel">__STUDIO_BG_LABEL__</span>
  </button>
  <button class="btn" id="btnQual" title="切换渲染清晰度">
    <svg viewBox="0 0 24 24"><path d="M12 3.2 20 8v8l-8 4.8L4 16V8l8-4.8Z"/><path d="M12 12.2 20 8M12 12.2 4 8M12 12.2v8.6"/></svg>
    <span id="qualLabel">流畅</span>
  </button>
  <button class="btn" id="btnCraft" title="实时切换材质、光影与底纹">
    <svg viewBox="0 0 24 24"><path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="2.2" fill="var(--glass-bg)"/><circle cx="15" cy="17" r="2.2" fill="var(--glass-bg)"/></svg>
    <span class="lbl-hide-sm" id="craftLbl">工艺</span>
  </button>

  <span class="dock-sep" aria-hidden="true"></span>

  <label class="holo-ctrl" id="holoCtrl" title="调整全息闪度">
    <svg viewBox="0 0 24 24"><path d="M12 2.5 14.3 9.7 21.5 12 14.3 14.3 12 21.5 9.7 14.3 2.5 12 9.7 9.7 12 2.5Z"/></svg>
    <input type="range" class="holo-range" id="holoRange" min="0.2" max="1.6" step="0.05" value="1.05" aria-label="全息闪度">
    <span class="holo-val" id="holoVal">105%</span>
  </label>
</nav>

<div id="errBanner"></div>

<script>
const META = __META_JSON__;
const ASSETS = __ASSETS_JSON__;

const VS_SRC = `#version 300 es
in vec2 a_pos;
void main() {
  gl_Position = vec4(a_pos, 0.0, 1.0);
}`;

const FS_SRC = `#version 300 es
precision highp float;

uniform vec2 u_res;
uniform vec2 u_cardSize;
uniform float u_dCam;
uniform float u_time;
uniform float u_yaw;
uniform float u_pitch;
uniform float u_hoverY;
uniform float u_holoGain;
uniform int u_bgMode;
uniform int u_transparent;
uniform int u_holoPattern;
uniform int u_materialPreset;
uniform int u_lightingPreset;
uniform vec3 u_studioCol;
uniform vec2 u_astroCenter;
uniform mat3 u_R;
uniform mat3 u_RT;
uniform vec4 u_glints[16];
uniform int u_glintCount;

uniform vec3 u_edgeBase;
uniform vec3 u_edgeSpec;
uniform vec3 u_metalTint;
uniform vec3 u_auraCol;
uniform vec3 u_sandCol1;
uniform vec3 u_sandCol2;
uniform vec3 u_seqCols[4];
uniform vec3 u_partCol1;
uniform vec3 u_partCol2;

uniform int u_propEnabled;
uniform vec2 u_propStart;
uniform vec2 u_propTip;
uniform vec3 u_propTint;
uniform float u_propGain;
uniform int u_motifKind;
uniform vec4 u_faceLock;

uniform sampler2D u_bg;
uniform sampler2D u_mid;
uniform sampler2D u_fg;
uniform sampler2D u_depthNorm;
uniform sampler2D u_aux;
uniform sampler2D u_fgBevel;
uniform sampler2D u_propMask;

out vec4 fragColor;

const float PI = 3.14159265;

float hash12(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}

vec3 hash32(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
  p3 += dot(p3, p3.yxz + 33.33);
  return fract((p3.xxy + p3.yzz) * p3.zyx);
}

float sdRoundedBox(vec2 p, vec2 b, float r) {
  vec2 q = abs(p) - b + r;
  return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

vec3 spectral(float phase) {
  float p = phase * 2.0 * PI;
  return 0.5 + 0.5 * cos(p + vec3(0.0, 2.0944, 4.1888));
}

vec2 planeUV(float zPlane, vec3 oLoc, vec3 dLoc, float cw, float ch) {
  float tp = (zPlane - oLoc.z) / (abs(dLoc.z) < 1e-4 ? -1e-4 : dLoc.z);
  vec2 p = oLoc.xy + tp * dLoc.xy;
  float comp = u_dCam / (u_dCam - zPlane);
  return vec2(0.5) + (p * comp) / vec2(cw, ch);
}

// Fast cellular Voronoi cracked-ice crystalline prism facets (evaluated only when active)
vec3 evalCrackedIce(vec2 uv, vec3 halfVec, float tiltShift) {
  vec2 g = uv * vec2(10.0, 13.0);
  vec2 cell = floor(g);
  float d1 = 8.0;
  float d2 = 8.0;
  vec2 bestId = cell;
  for (int dy = -1; dy <= 1; dy++) {
    for (int dx = -1; dx <= 1; dx++) {
      vec2 nc = cell + vec2(float(dx), float(dy));
      vec3 r = hash32(nc + 31.7);
      vec2 pt = nc + 0.14 + 0.72 * r.xy;
      float d = length(g - pt);
      if (d < d1) {
        d2 = d1;
        d1 = d;
        bestId = nc;
      } else if (d < d2) {
        d2 = d;
      }
    }
  }
  vec3 rCell = hash32(bestId * 2.13 + 19.4);
  vec2 nXY = (rCell.xy * 2.0 - 1.0) * 0.72;
  vec3 nLoc = normalize(vec3(nXY, sqrt(max(0.12, 1.0 - dot(nXY, nXY)))));
  vec3 nW = normalize(u_R * nLoc);
  float ndh = clamp(abs(dot(nW, halfVec)), 0.0, 1.0);
  float spec = pow(ndh, 7.5);
  float flash = smoothstep(0.32, 0.88, spec);
  float edge = exp(-pow((d2 - d1) / 0.036, 2.0)) * (0.28 + 0.85 * spec);
  vec3 prism = spectral(rCell.z * 2.4 + tiltShift * 1.9 + 0.45 * ndh);
  return prism * (0.08 + 0.92 * flash) + vec3(0.98, 0.99, 1.0) * (edge * 0.58 + pow(ndh, 24.0) * 0.55);
}

// Crisp high-contrast optical diffraction pattern shared by background & top-foil lamination
vec3 evalHoloPattern(vec2 uv, int patId, float tiltShift, vec3 halfVec, float aspect) {
  vec2 dAstro = (uv - u_astroCenter) * vec2(1.0, aspect);
  float angA = atan(dAstro.y, dAstro.x);
  float radA = length(dAstro);
  if (patId == 1) {
    // Crisp 9x12 mosaic prism squares (each tile shifts rainbow phase independently)
    vec2 g = uv * vec2(9.0, 12.0);
    vec2 tid = floor(g);
    vec2 tf = fract(g);
    float tileMask = smoothstep(0.0, 0.08, tf.x) * smoothstep(0.0, 0.08, 1.0 - tf.x)
                   * smoothstep(0.0, 0.08, tf.y) * smoothstep(0.0, 0.08, 1.0 - tf.y);
    float cph = hash12(tid + 7.13);
    float sh = pow(0.5 + 0.5 * cos(cph * 6.283 + u_yaw * 0.20 + u_pitch * 0.15), 2.2);
    vec3 col = spectral(cph * 1.9 + tiltShift * 1.8);
    float gridLine = (1.0 - tileMask) * 0.25;
    return col * (tileMask * (0.12 + 0.95 * sh)) + vec3(0.95, 0.98, 1.0) * gridLine;
  } else if (patId == 2) {
    // Flowing concentric cosmos vortex waves
    float wave = pow(0.5 + 0.5 * sin(radA * 32.0 - angA * 4.0 + u_yaw * 0.18), 2.3);
    vec3 col = spectral(radA * 2.1 - tiltShift * 1.5 + 0.18 * wave);
    return col * (0.10 + 0.95 * wave);
  } else if (patId == 3) {
    return evalCrackedIce(uv, halfVec, tiltShift);
  } else if (patId == 4) {
    // Bold diagonal brushed-foil rainbow ribbons + micro hairlines
    float diag = uv.x - uv.y * 1.35;
    float band = pow(0.5 + 0.5 * cos(diag * 24.0 + u_yaw * 0.22 + u_pitch * 0.12), 2.4);
    float brush = 0.72 + 0.28 * sin((uv.x * 95.0 + uv.y * 125.0) * PI);
    vec3 col = spectral(diag * 1.55 + tiltShift * 1.85);
    return col * (0.10 + 0.95 * band * brush);
  } else if (patId == 5) {
    // Crisp geometric diamond / argyle guilloche lattice
    float d1 = abs(sin((uv.x * 11.0 + uv.y * 14.5) * PI));
    float d2 = abs(sin((uv.x * 11.0 - uv.y * 14.5) * PI));
    float ridge = max(1.0 - smoothstep(0.0, 0.24, d1), 1.0 - smoothstep(0.0, 0.24, d2));
    float sweepMod = 0.35 + 0.65 * pow(0.5 + 0.5 * cos((uv.x * 5.0 - uv.y * 6.5) * PI + u_yaw * 0.18), 1.6);
    vec3 col = spectral(uv.x * 1.35 + uv.y * 1.10 + tiltShift * 1.7);
    return col * (ridge * sweepMod * 1.05);
  }
  // Default 0: Sharp 24-ray celestial starburst beams
  float rays = pow(0.5 + 0.5 * cos(angA * 24.0 + u_yaw * 0.14), 2.4);
  float micro = 0.76 + 0.24 * sin((uv.x * 110.0 + uv.y * 145.0) * PI + u_yaw * 0.14);
  vec3 col = spectral(angA / (2.0 * PI) + radA * 1.35 + tiltShift * 1.6);
  return col * (0.10 + 0.95 * rays * micro);
}

// Fast single-pass multi-depth 2x2 Voronoi 3D micro-sequins
vec3 evalQuicksandSequins(vec2 uv, vec2 grid, vec3 lightDir, vec3 halfVec, float ang) {
  vec2 grav = vec2(0.024 * sin(radians(u_yaw)), 0.019 * sin(radians(u_pitch)));
  vec2 guv = (uv + grav) * grid;
  vec2 baseCell = floor(guv - 0.5);
  vec3 acc = vec3(0.0);

  for (int dy = 0; dy <= 1; dy++) {
    for (int dx = 0; dx <= 1; dx++) {
      vec2 nc = baseCell + vec2(float(dx), float(dy));
      if (nc.x < 0.0 || nc.x >= grid.x || nc.y < 0.0 || nc.y >= grid.y) continue;
      vec3 r3 = hash32(nc + 17.3);
      if (r3.x < 0.08) continue;
      float speed = r3.y > 0.65 ? 2.0 : 1.0;
      float ph = r3.z * 2.0 * PI;
      float zShift = (r3.x - 0.5) * 0.35;
      vec2 center = nc + vec2(0.24 + 0.52 * r3.y, 0.24 + 0.52 * r3.z)
                  + grav * zShift * grid
                  + vec2(0.14 * sin(ang * speed + ph), 0.14 * cos(ang * speed + ph));
      vec2 delta = center - guv;
      float dist2 = dot(delta, delta);
      float rad = 0.09 + 0.07 * hash12(nc + 9.1);
      if (dist2 > rad * rad * 8.0) continue;
      float spot = exp(-dist2 / (2.0 * rad * rad));

      vec3 rn = hash32(nc * 3.17 + 41.0) * 2.0 - 1.0;
      rn.z = abs(rn.z) + 0.35;
      vec3 nWorld = normalize(u_R * normalize(rn));
      float spec = pow(clamp(abs(dot(nWorld, halfVec)), 0.0, 1.0), 34.0);
      float diff = 0.22 + 0.78 * clamp(abs(dot(nWorld, lightDir)), 0.0, 1.0);
      float br = diff * 0.36 + spec * 1.75;

      vec3 col = r3.y < 0.35 ? u_seqCols[0]
               : r3.y < 0.68 ? u_seqCols[1]
               : r3.y < 0.85 ? u_seqCols[2]
                             : u_seqCols[3];
      acc += spot * col * br * 1.15;
    }
  }
  return acc;
}

vec4 evalBespokeMotif(vec2 dp, float sizePx, float rotAngle, float tumblePhase, float seedId, float isSubBubble) {
  float cR = cos(rotAngle);
  float sR = sin(rotAngle);
  vec2 rp = vec2(dp.x * cR + dp.y * sR, -dp.x * sR + dp.y * cR);
  float foreshorten = 0.48 + 0.52 * abs(cos(tumblePhase));
  rp.y /= max(0.35, foreshorten);

  float aa = max(1.0, sizePx * 0.095);
  float fillA = 0.0;
  float rimGlow = 0.0;
  float gradT = 0.5;

  if (u_motifKind == 0) {
    if (isSubBubble > 0.5) {
      float r = length(rp);
      float rad = sizePx * 0.58;
      float ring = exp(-pow((r - rad) / max(1.1, sizePx * 0.14), 2.0));
      float hi = exp(-dot(rp - vec2(-rad * 0.38, -rad * 0.38), rp - vec2(-rad * 0.38, -rad * 0.38)) / max(1.0, pow(rad * 0.28, 2.0)));
      fillA = clamp(ring * 0.72 + hi * 0.85, 0.0, 1.0);
      rimGlow = hi * 0.9;
      gradT = 0.25 + 0.75 * hi;
    } else {
      float x = rp.x / max(sizePx * 1.15, 1.0);
      if (abs(x) <= 1.05) {
        float y = rp.y / max(sizePx * 0.38, 1.0) - 0.34 * (x * x);
        float profile = max(0.0, 1.0 - x * x);
        float d = (abs(y) - profile) * sizePx * 0.38;
        fillA = 1.0 - smoothstep(-aa, aa, d);
        rimGlow = exp(-(y * y) / 0.032) * profile * 0.55;
        gradT = clamp(0.5 + 0.5 * x, 0.0, 1.0);
      }
    }
  } else if (u_motifKind == 1) {
    vec2 q = abs(rp) / max(sizePx * 0.96, 1.0);
    if (q.x < 1.25 && q.y < 1.25) {
      float ast = pow(max(q.x, 1e-4), 0.56) + pow(max(q.y, 1e-4), 0.56);
      float d = (ast - 1.0) * sizePx * 0.75;
      fillA = 1.0 - smoothstep(-aa, aa, d);
      rimGlow = exp(-dot(q, q) * 9.0) * 0.65;
      gradT = clamp(0.5 + 0.5 * (rp.x - rp.y) / max(sizePx, 1.0), 0.0, 1.0);
    }
  } else if (u_motifKind == 2) {
    float x = rp.x / max(sizePx * 1.12, 1.0);
    if (abs(x) <= 1.08) {
      float y = rp.y / max(sizePx * 0.44, 1.0);
      float w = clamp(1.0 - x * x, 0.0, 1.0) * (0.64 + 0.36 * sin((x + 1.0) * 1.35)) * (1.0 - 0.14 * exp(-pow((x - 0.92) / 0.22, 2.0)));
      float d = (abs(y) - w) * sizePx * 0.44;
      fillA = 1.0 - smoothstep(-aa, aa, d);
      rimGlow = exp(-(y * y) / 0.045) * w * 0.35;
      gradT = clamp(0.5 + 0.5 * x, 0.0, 1.0);
    }
  } else if (u_motifKind == 3) {
    // Glowing diamond ember
    vec2 q = vec2(abs(rp.x) / max(sizePx * 1.15, 1.0), abs(rp.y) / max(sizePx * 0.45, 1.0));
    float d = (q.x + q.y - 1.0) * sizePx * 0.45;
    fillA = 1.0 - smoothstep(-aa, aa, d);
    rimGlow = exp(-dot(q, q) * 5.0) * 0.75;
    gradT = clamp(q.x, 0.0, 1.0);
  } else {
    // 6-armed crystal snowflake
    float r = length(rp);
    if (r < sizePx * 1.15) {
      float a6 = mod(atan(rp.y, rp.x) + PI / 6.0, PI / 3.0) - PI / 6.0;
      vec2 p6 = r * vec2(cos(a6), abs(sin(a6)));
      float arm = max(p6.x - sizePx, p6.y - sizePx * 0.11);
      float barb = max(abs(p6.x - 0.55 * sizePx - p6.y * 0.7) - sizePx * 0.08, p6.y - 0.38 * sizePx);
      float d = min(arm, barb);
      fillA = 1.0 - smoothstep(-aa, aa, d);
      rimGlow = exp(-(r * r) / max(1.0, pow(sizePx * 0.25, 2.0))) * 0.6;
      gradT = clamp(r / max(sizePx, 1.0), 0.0, 1.0);
    }
  }

  vec3 baseCol = mix(u_partCol1, u_partCol2, gradT);
  float shimmer = 0.72 + 0.28 * sin(u_time * 2.0 + seedId * 3.1 + tumblePhase);
  vec3 col = clamp(baseCol * (0.85 + 0.35 * shimmer) + vec3(0.98, 0.98, 1.0) * rimGlow * 0.42, 0.0, 1.0);
  return vec4(col, fillA);
}

void main() {
  float cw = u_cardSize.x;
  float ch = u_cardSize.y;
  float cornerR = 0.045 * cw;
  float tNorm = u_time / (2.0 * PI);
  float cyc = fract(tNorm);

  vec2 pxBase = vec2(gl_FragCoord.x - 0.5 * u_res.x, (u_res.y - gl_FragCoord.y) - 0.5 * u_res.y);

  vec2 radNorm = pxBase / (u_res * 0.62);
  float vig = clamp(1.0 - 0.62 * pow(length(radNorm), 1.55), 0.08, 1.0);
  // Curated architectural gallery overhead cone + subtle lower plinth sheen
  vec2 spotUV = vec2(pxBase.x / max(u_res.x * 0.44, 1.0), (pxBase.y + u_res.y * 0.30) / max(u_res.y * 0.72, 1.0));
  float overheadCone = exp(-dot(spotUV, spotUV) * 1.55);
  float floorSheen = smoothstep(0.32 * ch, 0.62 * ch, pxBase.y) * exp(-pow(pxBase.x / max(cw * 1.35, 1.0), 2.0)) * 0.022;

  // Mode 0: True-black charcoal velvet studio with a whisper of theme tint (never muddy mid-tone blue)
  vec3 studioNeutral = mix(vec3(0.026, 0.028, 0.035), vec3(0.068, 0.072, 0.084), clamp(0.42 * vig + 0.58 * overheadCone, 0.0, 1.0));
  vec3 studioWhisper = u_studioCol * (0.14 + 0.24 * overheadCone) + u_auraCol * (0.028 * overheadCone);
  vec3 bgStudio = clamp(studioNeutral + studioWhisper + vec3(floorSheen), 0.0, 1.0);

  // Mode 1: Pure museum pitch obsidian (zero color cast)
  vec3 bgObsidian = clamp(
    mix(vec3(0.008, 0.009, 0.012), vec3(0.024, 0.026, 0.032), clamp(0.40 * vig + 0.60 * overheadCone, 0.0, 1.0)) + vec3(floorSheen * 0.55),
    0.0, 1.0
  );

  // Mode 2: Bright neutral gallery wall
  vec3 bgGallery = mix(vec3(0.872, 0.884, 0.906), vec3(0.960, 0.964, 0.974), clamp(0.45 * vig + 0.55 * overheadCone, 0.0, 1.0));
  vec3 backdrop = u_bgMode == 0 ? bgStudio : (u_bgMode == 1 ? bgObsidian : bgGallery);

  // Dual-lobe grounded contact shadow (tight core + soft penumbra)
  float shCy = 0.5 * ch + 0.095 * cw;
  float hoverScale = 1.0 - 0.14 * (-u_hoverY / max(0.013 * u_res.y, 1.0));
  vec2 shRad = vec2(cw * 0.44 * hoverScale, 0.056 * cw * hoverScale);
  vec2 shDelta = vec2(pxBase.x + u_yaw * (cw / 510.0) * 1.4, pxBase.y - shCy) / shRad;
  float shD2 = dot(shDelta, shDelta);
  float groundSh = (exp(-shD2 * 2.2) * 0.62 + exp(-shD2 * 0.72) * 0.38) * (u_bgMode == 2 ? 0.25 : 0.64);

  // Tight, restrained ambient card bounce directly behind the slab (zero neon fog)
  vec2 auraDelta = vec2(pxBase.x / (cw * 0.60), (pxBase.y - u_hoverY) / (ch * 0.56));
  float auraPulse = 0.82 + 0.18 * sin(2.0 * u_time);
  float aura = exp(-dot(auraDelta, auraDelta) / 0.62) * 0.13 * auraPulse;
  vec3 auraCol = u_auraCol * aura * (u_bgMode == 2 ? 0.0 : (u_bgMode == 1 ? 0.40 : 1.0));

  vec3 canvasCol = backdrop * (1.0 - groundSh) + auraCol;

  float trCardA = 0.0;
  vec3 trCardCol = vec3(0.0);
  vec3 trPropFlare = vec3(0.0);

  bool insideBox = abs(pxBase.x) <= cw * 0.68 && abs(pxBase.y - u_hoverY) <= ch * 0.68;
  if (insideBox) {
    vec3 lightDir = normalize(vec3(
      0.36 * cos(u_time) - 0.25 * sin(u_time) + 0.28 * sin(radians(u_yaw)),
      -0.42 + 0.14 * sin(2.0 * u_time) - 0.20 * sin(radians(u_pitch)),
      0.84
    ));
    vec3 lightLoc = normalize(u_RT * lightDir);
    vec3 halfCam = normalize(lightDir + vec3(0.0, 0.0, 1.0));

    vec3 dCam = normalize(vec3(pxBase.x, pxBase.y, -u_dCam));
    vec3 oLoc = u_RT * vec3(0.0, -u_hoverY, u_dCam);
    vec3 dLoc = u_RT * dCam;
    float invDlz = 1.0 / (abs(dLoc.z) < 1e-4 ? -1e-4 : dLoc.z);

    float t0 = -oLoc.z * invDlz;
    vec2 p0 = oLoc.xy + t0 * dLoc.xy;
    float sd0 = sdRoundedBox(p0, vec2(0.5 * cw, 0.5 * ch), cornerR);
    float aaW = max(1.1, cw / 450.0);
    float frontMask = 1.0 - smoothstep(-aaW, aaW, sd0);

    // Material preset parameters (0:SAR, 1:Acrylic, 2:CrackedIce, 3:EtchedFoil, 4:MatteVelvet, 5:CleanTCG)
    float matThick = u_materialPreset == 1 ? 1.85 : (u_materialPreset == 3 ? 1.14 : 1.0);
    float matHolo = u_materialPreset == 1 ? 0.32 : (u_materialPreset == 2 ? 0.85 : (u_materialPreset == 3 ? 0.65 : (u_materialPreset == 4 ? 0.0 : (u_materialPreset == 5 ? 1.45 : 1.0))));
    float matSand = u_materialPreset == 0 ? 1.0 : (u_materialPreset == 1 ? 0.78 : (u_materialPreset == 2 ? 0.15 : 0.0));
    float matSeq  = u_materialPreset == 0 ? 1.0 : (u_materialPreset == 1 ? 1.85 : (u_materialPreset == 2 ? 0.30 : 0.0));
    float matEmboss = u_materialPreset == 1 ? 0.75 : (u_materialPreset == 2 ? 1.15 : (u_materialPreset == 3 ? 2.60 : (u_materialPreset == 4 ? 0.30 : (u_materialPreset == 5 ? 1.05 : 1.0))));
    float matMetal  = u_materialPreset == 1 ? 0.95 : (u_materialPreset == 2 ? 1.15 : (u_materialPreset == 3 ? 1.75 : (u_materialPreset == 4 ? 2.55 : 1.05)));
    float matPearl  = u_materialPreset == 1 ? 0.65 : (u_materialPreset == 2 ? 0.75 : (u_materialPreset == 3 ? 0.35 : (u_materialPreset == 4 ? 0.0 : (u_materialPreset == 5 ? 0.90 : 1.0))));
    float matGlass  = u_materialPreset == 1 ? 1.60 : (u_materialPreset == 2 ? 0.95 : (u_materialPreset == 3 ? 0.80 : (u_materialPreset == 4 ? 0.08 : (u_materialPreset == 5 ? 1.25 : 1.0))));
    bool useIceOverlay = (u_materialPreset == 2);

    // Lighting preset parameters (0:Gallery, 1:DramaticRim, 2:GoldenHour, 3:Moonlit, 4:SoftPastel)
    vec3 litKeyCol = u_lightingPreset == 1 ? vec3(0.96, 0.99, 1.05)
                   : (u_lightingPreset == 2 ? vec3(1.06, 0.96, 0.82)
                   : (u_lightingPreset == 3 ? vec3(0.86, 0.94, 1.07)
                   : (u_lightingPreset == 4 ? vec3(1.02, 1.00, 1.01) : vec3(1.0))));
    float litDiffBase = u_lightingPreset == 1 ? 0.76 : (u_lightingPreset == 2 ? 0.88 : (u_lightingPreset == 3 ? 0.84 : (u_lightingPreset == 4 ? 0.95 : 0.90)));
    float litDiffAmp  = u_lightingPreset == 1 ? 0.32 : (u_lightingPreset == 2 ? 0.20 : (u_lightingPreset == 3 ? 0.22 : (u_lightingPreset == 4 ? 0.10 : 0.16)));
    float litRimStr   = u_lightingPreset == 1 ? 0.48 : (u_lightingPreset == 2 ? 0.28 : (u_lightingPreset == 3 ? 0.34 : (u_lightingPreset == 4 ? 0.12 : 0.0)));
    vec3 litRimCol = u_lightingPreset == 1 ? mix(u_auraCol, u_sandCol2, 0.45)
                   : (u_lightingPreset == 2 ? vec3(1.00, 0.84, 0.48)
                   : (u_lightingPreset == 3 ? vec3(0.58, 0.82, 1.00)
                   : (u_lightingPreset == 4 ? vec3(1.00, 0.96, 0.99) : u_auraCol)));
    vec3 litSheenTint = u_lightingPreset == 1 ? vec3(0.88, 0.95, 1.05)
                      : (u_lightingPreset == 2 ? vec3(1.00, 0.93, 0.78)
                      : (u_lightingPreset == 3 ? vec3(0.84, 0.94, 1.00)
                      : (u_lightingPreset == 4 ? vec3(1.00, 0.98, 0.99) : vec3(0.92, 0.96, 1.0))));
    float litShadowStr = u_lightingPreset == 1 ? 0.56 : (u_lightingPreset == 2 ? 0.46 : (u_lightingPreset == 3 ? 0.52 : (u_lightingPreset == 4 ? 0.28 : 0.44)));

    float edgeAlpha = 0.0;
    vec3 edgeCol = vec3(0.0);
    if (frontMask < 0.995) {
      float thickness = 0.036 * cw * matThick;
      float tb = (-thickness - oLoc.z) * invDlz;
      float sdb = sdRoundedBox(oLoc.xy + tb * dLoc.xy, vec2(0.5 * cw, 0.5 * ch), cornerR);
      if (sdb <= aaW || sd0 <= aaW + thickness * 0.65) {
        vec2 edgeHitXY = vec2(0.0);
        float edgeHitS = 0.0;
        for (int s = 1; s <= 8; s++) {
          float fs = float(s) / 8.0;
          float sz = -thickness * fs;
          float ts = (sz - oLoc.z) * invDlz;
          vec2 ps = oLoc.xy + ts * dLoc.xy;
          float sds = sdRoundedBox(ps, vec2(0.5 * cw, 0.5 * ch), cornerR);
          float sm = 1.0 - smoothstep(-aaW, aaW, sds);
          float w = clamp(sm * (1.0 - edgeAlpha), 0.0, 1.0);
          edgeHitXY += ps * w;
          edgeHitS += fs * w;
          edgeAlpha = clamp(edgeAlpha + w, 0.0, 1.0);
        }
        if (edgeAlpha > 0.005) {
          vec2 nXY = sign(edgeHitXY) * smoothstep(vec2(cw * 0.42, ch * 0.42), vec2(cw * 0.5, ch * 0.5), abs(edgeHitXY));
          vec3 nEdge = normalize(vec3(nXY, 0.25 + 0.35 * (1.0 - edgeHitS)));
          vec3 hLocEdge = normalize(lightLoc - vec3(0.0, 0.0, -1.0));
          float ndotlE = clamp(dot(nEdge, lightLoc), 0.0, 1.0);
          float ndothE = clamp(dot(nEdge, hLocEdge), 0.0, 1.0);
          float grain = 0.88 + 0.12 * sin((edgeHitXY.x + edgeHitXY.y) * 0.55 + edgeHitS * 14.0);
          if (u_materialPreset == 1) {
            vec3 crystBase = mix(vec3(0.74, 0.82, 0.92), u_edgeSpec, 0.35);
            edgeCol = (crystBase * (0.48 + 0.52 * ndotlE) + vec3(0.96, 0.99, 1.0) * 1.05 * pow(ndothE, 24.0)) * (0.94 + 0.06 * grain) * (1.0 - 0.16 * edgeHitS);
          } else {
            edgeCol = (u_edgeBase * (0.45 + 0.65 * ndotlE) + u_edgeSpec * 0.85 * pow(ndothE, 18.0)) * grain * (1.0 - 0.28 * edgeHitS);
          }
        }
      }
    }

    vec3 cardCol = vec3(0.0);
    if (frontMask > 0.004) {
      vec3 vLoc = -dLoc;
      vec3 hLoc = normalize(vLoc + lightLoc);
      vec2 ug = planeUV(0.0, oLoc, dLoc, cw, ch);

      // FRONT-TO-BACK 1: Foreground Embossed Frame
      vec3 fgAccCol = vec3(0.0);
      float fgAccA = 0.0;
      for (int fi = 0; fi < 2; fi++) {
        float zf = (fi == 0 ? 0.006 : 0.012) * cw;
        vec2 uf = planeUV(zf, oLoc, dLoc, cw, ch);
        float inFg = step(0.0, uf.x) * step(uf.x, 1.0) * step(0.0, uf.y) * step(uf.y, 1.0);
        vec2 ufc = clamp(uf, 0.0, 1.0);
        vec4 fgS = texture(u_fg, ufc);
        float fa = fgS.a * inFg;
        if (fa > 0.005) {
          vec3 fBev = texture(u_fgBevel, ufc).rgb;
          if (fi == 1) fa *= smoothstep(0.18, 0.45, fBev.r);
          vec2 fNxy = fBev.gb * 2.0 - 1.0;
          vec3 fn = normalize(vec3(fNxy, sqrt(max(0.08, 1.0 - dot(fNxy, fNxy)))));
          float fNdotL = clamp(dot(fn, lightLoc), 0.0, 1.0);
          float fNdotH = clamp(dot(fn, hLoc), 0.0, 1.0);
          vec3 iridFg = spectral(uf.x * 0.8 + uf.y * 1.1 + 0.022 * u_yaw + 0.015 * u_pitch);
          vec3 sheenTint = 0.62 * u_metalTint + 0.22 * u_edgeSpec + 0.16 * iridFg;
          vec3 fCol = fgS.rgb * (0.76 + 0.24 * fNdotL) + sheenTint * 0.42 * pow(fNdotH, 16.0);
          fCol = mix(fCol, 0.85 + (fCol - 0.85) / (1.0 + 1.5 * max(fCol - 0.85, 0.0)), step(0.85, fCol));
          if (fi == 0) fCol *= 0.86;
          fgAccCol = mix(fgAccCol, clamp(fCol, 0.0, 1.0), fa);
          fgAccA = clamp(fgAccA + fa * (1.0 - fgAccA), 0.0, 1.0);
        }
      }

      // FRONT-TO-BACK 2: Midground 3D Subject
      vec3 mLit = vec3(0.0);
      float mA = 0.0;
      if (fgAccA < 0.99) {
        vec2 um = ug;
        bool hitFound = false;
        if (abs(u_yaw) + abs(u_pitch) < 0.12) {
          float inMid = step(0.0, um.x) * step(um.x, 1.0) * step(0.0, um.y) * step(um.y, 1.0);
          vec4 dn0 = texture(u_depthNorm, clamp(um, 0.0, 1.0));
          hitFound = (dn0.g * inMid) > 0.01;
        } else {
          float zMidBase = -0.012 * cw;
          float zMidAmp = 0.064 * cw;
          float zStart = zMidBase + zMidAmp;
          float zEnd = zMidBase;
          float dzStep = (zEnd - zStart) / 11.0;
          float zLo = zEnd;
          float zHi = zStart;

          for (int i = 0; i <= 11; i++) {
            float zTest = zStart + float(i) * dzStep;
            vec2 ut = planeUV(zTest, oLoc, dLoc, cw, ch);
            float inUV = step(0.0, ut.x) * step(ut.x, 1.0) * step(0.0, ut.y) * step(ut.y, 1.0);
            vec2 dn = texture(u_depthNorm, clamp(ut, 0.0, 1.0)).rg;
            float zSurf = zMidBase + dn.r * zMidAmp;
            if (!hitFound && zTest <= zSurf && (dn.g * inUV) > 0.14) {
              hitFound = true;
              zLo = zTest;
              zHi = zTest - dzStep;
            }
          }
          if (hitFound) {
            for (int b = 0; b < 3; b++) {
              float zMidB = 0.5 * (zLo + zHi);
              vec2 ut = planeUV(zMidB, oLoc, dLoc, cw, ch);
              float inUV = step(0.0, ut.x) * step(ut.x, 1.0) * step(0.0, ut.y) * step(ut.y, 1.0);
              vec2 dn = texture(u_depthNorm, clamp(ut, 0.0, 1.0)).rg;
              float zSurf = zMidBase + dn.r * zMidAmp;
              if (zMidB <= zSurf && (dn.g * inUV) > 0.14) zLo = zMidB;
              else zHi = zMidB;
            }
            um = planeUV(0.5 * (zLo + zHi), oLoc, dLoc, cw, ch);
          }
        }

        if (hitFound) {
          float inMid = step(0.0, um.x) * step(um.x, 1.0) * step(0.0, um.y) * step(um.y, 1.0);
          vec2 umc = clamp(um, 0.0, 1.0);
          vec4 midTex = texture(u_mid, umc);
          mA = midTex.a * inMid;
          if (mA > 0.004) {
            vec2 mNxy = texture(u_depthNorm, umc).ba * 2.0 - 1.0;
            vec3 mNorm = normalize(vec3(mNxy, sqrt(max(0.05, 1.0 - dot(mNxy, mNxy)))));
            vec2 mAux = texture(u_aux, umc).gb;
            float mMetal = mAux.x;
            float mSarB = mAux.y;

            float halfLambert = clamp(0.5 * dot(mNorm, lightLoc) + 0.5, 0.0, 1.0);
            float diffGain = litDiffBase + litDiffAmp * halfLambert;
            float ndoth = clamp(dot(mNorm, hLoc), 0.0, 1.0);
            float ndotv = clamp(dot(mNorm, vLoc), 0.0, 1.0);

            float metalSpec = pow(ndoth, 28.0) * mMetal * 0.78 * matMetal;
            float metalBrushed = (0.5 + 0.5 * sin((um.x * 95.0 - um.y * 35.0) * PI + u_yaw * 0.1)) * mMetal * 0.14 * matMetal;
            float sarEmboss = clamp(0.42 + 0.58 * dot(mNxy, lightLoc.xy), 0.0, 1.0) * mSarB * 0.26 * matEmboss;
            float fresnel = pow(1.0 - ndotv, 3.2);
            vec3 pearlRim = spectral(um.x + um.y + 0.015 * u_yaw) * (fresnel * 0.22 * matPearl) * 0.55;
            vec3 litRim = litRimCol * (fresnel * litRimStr);

            vec3 propGleam = vec3(0.0);
            if (u_propEnabled == 1) {
              float pMask = texture(u_propMask, umc).r;
              if (pMask > 0.01) {
                vec2 pVec = u_propTip - u_propStart;
                float pLen2 = max(dot(pVec, pVec), 1e-4);
                float sAlong = dot(umc - u_propStart, pVec) / pLen2;
                vec2 pPerp = vec2(-pVec.y, pVec.x) / max(sqrt(pLen2), 1e-4);
                float diagOff = dot(umc - u_propStart, pPerp) * 0.24;

                float swT = clamp((cyc - 0.18) / 0.30, 0.0, 1.0);
                swT = swT * swT * (3.0 - 2.0 * swT);
                float swPos = mix(-0.18, 1.16, swT);
                float swEnv = smoothstep(0.16, 0.22, cyc) * (1.0 - smoothstep(0.45, 0.52, cyc));
                float dS = (sAlong + diagOff) - swPos;

                float bladeCore = exp(-(dS * dS) / 0.0036);
                float bladeHalo = exp(-(dS * dS) / 0.020);
                vec3 propPrism = spectral(sAlong * 1.4 + umc.x * 0.8 + 0.02 * u_yaw);
                float luma = dot(midTex.rgb, vec3(0.299, 0.587, 0.114));
                float inkKeep = smoothstep(0.05, 0.26, luma + 0.12 * mMetal);
                float subtleCatch = pow(ndoth, 22.0) * 0.14;
                propGleam = (
                  (vec3(1.0, 0.99, 0.97) * bladeCore * 0.54 + mix(u_propTint, propPrism, 0.32) * bladeHalo * 0.34) * swEnv
                  + u_propTint * subtleCatch
                ) * pMask * inkKeep * u_propGain * u_holoGain;
              }
            }

            mLit = midTex.rgb * (diffGain * litKeyCol)
                 + u_metalTint * (metalSpec + metalBrushed)
                 + vec3(sarEmboss)
                 + pearlRim
                 + litRim
                 + propGleam;
            mLit = mix(mLit, 0.85 + (mLit - 0.85) / (1.0 + 1.4 * max(mLit - 0.85, 0.0)), step(0.85, mLit));

            vec2 ufSh = planeUV(0.009 * cw, oLoc, dLoc, cw, ch) + lightLoc.xy * 0.018;
            float fgShA = texture(u_fg, clamp(ufSh, 0.0, 1.0)).a * step(0.0, ufSh.x) * step(ufSh.x, 1.0) * step(0.0, ufSh.y) * step(ufSh.y, 1.0);
            mLit *= (1.0 - 0.18 * fgShA);
          }
        }
      }

      // FRONT-TO-BACK 3: Deep Background + Holo + Quicksand
      vec3 bgWithSand = vec3(0.0);
      if (fgAccA < 0.99 && mA < 0.985) {
        vec2 ub = planeUV(-0.082 * cw, oLoc, dLoc, cw, ch);
        vec2 ubOs = clamp(vec2(0.5) + (ub - 0.5) / 1.07, 0.0, 1.0);
        vec3 bgCol = texture(u_bg, ubOs).rgb;
        float rHoloMask = texture(u_aux, ubOs).r;

        float tiltShift = 0.016 * u_yaw + 0.012 * u_pitch;
        vec3 holoPatBg = evalHoloPattern(ubOs, u_holoPattern, tiltShift, halfCam, ch / cw);
        vec3 bgLit = bgCol + holoPatBg * (rHoloMask * 0.52 * u_holoGain * matHolo);
        if (useIceOverlay && u_holoPattern != 3) {
          bgLit += evalCrackedIce(ubOs, halfCam, tiltShift) * (rHoloMask * 0.42 * u_holoGain);
        }

        if (u_motifKind >= 0) {
          vec2 udMotif = planeUV(-0.044 * cw, oLoc, dLoc, cw, ch);
          for (int db = 0; db < 2; db++) {
            float fdb = float(db);
            float dirX = u_motifKind == 2 ? -1.0 : (u_motifKind == 1 ? 1.0 : 0.0);
            float dirY = (u_motifKind == 0 || u_motifKind == 3) ? -1.0 : 1.0;
            vec2 posUv = vec2(
              0.12 + 0.76 * fract(hash12(vec2(fdb, 11.3)) + tNorm * dirX + ((u_motifKind == 0 || u_motifKind == 3) ? 0.03 * sin(u_time + fdb * 2.0) : 0.0)),
              0.12 + 0.76 * fract(hash12(vec2(fdb, 23.7)) + tNorm * dirY)
            );
            vec2 dpUv = (udMotif - posUv) * vec2(cw, ch);
            float sz = (0.014 + 0.005 * hash12(vec2(fdb, 3.1))) * cw;
            if (abs(dpUv.x) < sz * 2.2 && abs(dpUv.y) < sz * 2.2) {
              float rotA = hash12(vec2(fdb, 5.2)) * 6.283 + u_time * (db == 0 ? 1.0 : -1.0);
              vec4 mRes = evalBespokeMotif(dpUv, sz, rotA, u_time + fdb * 1.7, fdb, 0.0);
              bgLit = mix(bgLit, mRes.rgb, mRes.a * 0.72);
            }
          }
        }

        vec2 us1 = planeUV(-0.058 * cw, oLoc, dLoc, cw, ch);
        vec3 sandStreams = vec3(0.0);
        if (matSand > 0.01) {
          vec2 us2 = planeUV(-0.036 * cw, oLoc, dLoc, cw, ch);
          vec2 grav = vec2(0.025 * sin(radians(u_yaw)), 0.020 * sin(radians(u_pitch)));
          float f1 = sin((us1.x + grav.x) * 18.0 + us1.y * 9.0 + u_time) * cos((us1.y + grav.y) * 14.0 - us1.x * 7.0 - u_time);
          float silk1 = pow(clamp(0.5 + 0.5 * f1, 0.0, 1.0), 3.2) * (0.4 + 0.6 * rHoloMask);
          float f2 = sin((us2.x - grav.x * 1.3) * 24.0 - us2.y * 13.0 - 2.0 * u_time) * cos((us2.y + grav.y * 1.2) * 19.0 + us2.x * 11.0 + u_time);
          float silk2 = pow(clamp(0.5 + 0.5 * f2, 0.0, 1.0), 3.6) * (0.35 + 0.65 * rHoloMask);
          sandStreams = (silk1 * u_sandCol1 * 0.24 + silk2 * u_sandCol2 * 0.22) * u_holoGain * matSand;
        }

        vec3 seq = vec3(0.0);
        if (matSeq > 0.01) {
          vec2 seqGrid = u_materialPreset == 1 ? vec2(18.0, 23.0) : vec2(15.0, 19.0);
          seq = evalQuicksandSequins(us1, seqGrid, lightDir, halfCam, u_time) * (0.85 * matSeq * u_holoGain);
        }
        bgWithSand = bgLit + sandStreams + seq;

        vec2 shBase = us1 + lightLoc.xy * 0.042 * vec2(1.0, cw / ch);
        float inSh = step(0.0, shBase.x) * step(shBase.x, 1.0) * step(0.0, shBase.y) * step(shBase.y, 1.0);
        float shBlur = texture(u_aux, clamp(shBase, 0.0, 1.0)).a * inSh;
        bgWithSand *= (1.0 - litShadowStr * shBlur);
      }

      cardCol = mix(bgWithSand, clamp(mLit, 0.0, 1.0), mA);
      cardCol = mix(cardCol, fgAccCol, fgAccA);

      // Post-composite Surface Lamination & Craft Coat (strictly face-protected via u_faceLock!)
      vec2 ugC = clamp(ug, 0.0, 1.0);
      vec2 fCenC = 0.5 * (u_faceLock.xy + u_faceLock.zw);
      vec2 fRadC = max(0.5 * (u_faceLock.zw - u_faceLock.xy), vec2(0.08));
      float faceProtect = smoothstep(0.66, 1.38, length((ugC - fCenC) / fRadC));
      float sweepU = 0.62 + 0.78 * sin(u_time);
      float bandD = (ug.x * 0.72 + ug.y * 0.52) - sweepU;
      float tiltShiftTop = 0.016 * u_yaw + 0.012 * u_pitch;
      float broadSweep = 0.28 + 0.72 * exp(-(bandD * bandD) / 0.14);

      if (u_materialPreset == 4) {
        // Matte Velvet + Spot-UV Hot Foil: deep soft-touch matte paper contrasting with blazing metal foil
        float vGrain = (hash12(gl_FragCoord.xy * 0.73) - 0.5) * 0.026;
        float spotMetal = max(texture(u_aux, ugC).g * mA, fgAccA * 0.85);
        vec3 matteCol = pow(max(cardCol, vec3(0.001)), vec3(1.13)) * 0.90 + vec3(vGrain);
        cardCol = mix(matteCol, cardCol, clamp(spotMetal * 1.15, 0.0, 1.0));
        float spotFoil = exp(-(bandD * bandD) / 0.025) * spotMetal * 0.42 * u_holoGain;
        cardCol += u_metalTint * spotFoil;
      } else {
        // Selected Holo Pattern top-foil sheen across dress, props, frame & bg (face stays 100% pure)
        float topHoloBase = u_materialPreset == 5 ? 0.46 : (u_materialPreset == 1 ? 0.12 : (u_materialPreset == 3 ? 0.16 : 0.28));
        vec3 topHoloRgb = evalHoloPattern(ugC, u_holoPattern, tiltShiftTop, halfCam, ch / cw);
        float topHoloAmt = topHoloBase * faceProtect * broadSweep * u_holoGain;
        cardCol += topHoloRgb * topHoloAmt * (1.0 - 0.52 * cardCol);

        if (u_materialPreset == 1) {
          // Acrylic Quicksand Brick: inner crystal prism rim + front-chamber floating holographic glitter
          float innerGlass = smoothstep(-15.0, -1.2, sd0) * (1.0 - smoothstep(-1.5, 0.5, sd0));
          vec3 prismRim = mix(vec3(0.92, 0.97, 1.0), spectral(ug.x * 2.0 + ug.y * 2.0 + tiltShiftTop * 2.5), 0.38);
          cardCol += prismRim * innerGlass * (0.28 + 0.35 * broadSweep);
          vec2 uFront = planeUV(0.015 * cw, oLoc, dLoc, cw, ch);
          vec3 frontGlitter = evalQuicksandSequins(uFront, vec2(11.0, 15.0), lightDir, halfCam, u_time + 1.4);
          cardCol += frontGlitter * (0.62 * faceProtect * u_holoGain);
        } else if (u_materialPreset == 2) {
          // Cracked Ice Lamination: crisp angular polygonal crystal facets snapping across the whole card
          vec3 iceTop = evalCrackedIce(ugC, halfCam, tiltShiftTop);
          float iceAmt = (0.48 + 0.22 * (1.0 - mA)) * faceProtect * u_holoGain;
          cardCol += iceTop * iceAmt * (1.0 - 0.48 * cardCol);
        } else if (u_materialPreset == 3) {
          // Etched / Guilloche SAR Foil: visible carved concentric metallic contour ridges
          float dTop = texture(u_depthNorm, ugC).r;
          float lumaTop = dot(cardCol, vec3(0.299, 0.587, 0.114));
          float ridgeWave = sin(dTop * 130.0 + (ugC.x * 20.0 - ugC.y * 16.0) + lumaTop * 14.0 + u_yaw * 0.14);
          float etchLine = pow(0.5 + 0.5 * ridgeWave, 5.0);
          vec3 foilCol = mix(u_metalTint, u_edgeSpec, 0.45);
          cardCol += foilCol * (etchLine * faceProtect * (0.22 + 0.44 * broadSweep) * u_holoGain);
        }
      }

      float glassBand = exp(-(bandD * bandD) / 0.0085) * 0.11 + exp(-(bandD * bandD) / 0.0009) * 0.13;
      if (u_materialPreset == 1) {
        float bandD2 = (ug.x * 0.72 + ug.y * 0.52) - (sweepU - 0.24);
        glassBand += exp(-(bandD2 * bandD2) / 0.0022) * 0.14;
      }
      vec2 spotC = vec2(0.5 + 0.28 * sin(u_time), 0.44 + 0.22 * cos(2.0 * u_time));
      vec2 spotD = (ug - spotC) * vec2(1.0, ch / cw);
      float spotlight = exp(-dot(spotD, spotD) / 0.16) * 0.08;
      float bevelRim = smoothstep(-4.5, -0.5, sd0) * (0.09 + 0.20 * max(0.0, sin(u_time) * (ug.x - 0.5) * 2.0 + 0.5));
      vec3 sheenCol = litSheenTint * ((glassBand + spotlight + bevelRim) * matGlass);
      cardCol = clamp(cardCol + sheenCol * (1.0 - 0.72 * cardCol), 0.0, 1.0);
    }

    float totalCardA = clamp(frontMask + edgeAlpha * (1.0 - frontMask), 0.0, 1.0);
    vec3 totalCardCol = mix(edgeCol, cardCol, frontMask);

    if (totalCardA > 0.005) {
      float sweepU = 0.62 + 0.78 * sin(u_time);
      for (int i = 0; i < 16; i++) {
        if (i >= u_glintCount) break;
        vec4 g = u_glints[i];
        float zg = g.w < 0.0 ? -0.082 * cw : (g.w > 0.5 ? 0.012 * cw : 0.016 * cw);
        float compG = (u_dCam - zg) / u_dCam;
        vec3 gLoc = vec3((g.x - 0.5) * cw * compG, (g.y - 0.5) * ch * compG, zg);
        vec3 gCam = u_R * gLoc;
        vec2 gPx = vec2(gCam.x, gCam.y + u_hoverY) * (u_dCam / (u_dCam - gCam.z));
        float arm = g.z * cw;
        vec2 d = pxBase - gPx;
        if (abs(d.x) < arm * 1.4 && abs(d.y) < arm * 1.4) {
          float distBand = abs((g.x * 0.72 + g.y * 0.52) - sweepU);
          float sweepTrig = exp(-(distBand * distBand) / 0.018);
          float twinkle = 0.25 + 0.75 * (0.5 + 0.5 * sin(2.0 * u_time + abs(g.w) * 6.283));
          float glintCap = u_propEnabled == 1 ? 0.92 : 1.35;
          float inten = min(glintCap, (u_propEnabled == 1 ? 0.20 : 0.28) * twinkle + (u_propEnabled == 1 ? 0.68 : 1.05) * sweepTrig) * u_holoGain;
          float curArm = arm * (0.65 + 0.55 * sweepTrig);
          float sig = max(1.1, curArm * 0.045);
          float ah = exp(-(d.y * d.y) / (2.0 * sig * sig)) * exp(-abs(d.x) / (curArm * 0.36));
          float av = exp(-(d.x * d.x) / (2.0 * sig * sig)) * exp(-abs(d.y) / (curArm * 0.36));
          float core = exp(-dot(d, d) / (2.0 * pow(curArm * 0.14, 2.0)));
          vec3 tint = g.w < 0.0 ? vec3(0.82, 0.95, 1.0) : vec3(1.0, 0.96, 0.86);
          totalCardCol += clamp((ah + av + core * 1.1) * inten, 0.0, glintCap) * tint * totalCardA;
        }
      }
      trCardA = totalCardA;
      trCardCol = clamp(totalCardCol, 0.0, 1.0);
      canvasCol = mix(canvasCol, trCardCol, totalCardA);

      // Single Hairline Prop Tip Ring & Delicate Cross Flare (cyc 0.43..0.65)
      if (u_propEnabled == 1) {
        float fLife = (cyc - 0.43) / 0.22;
        if (fLife > 0.0 && fLife < 1.0) {
          float zf = 0.018 * cw;
          float compF = (u_dCam - zf) / u_dCam;
          vec3 fLoc = vec3((u_propTip.x - 0.5) * cw * compF, (u_propTip.y - 0.5) * ch * compF, zf);
          vec3 fCam = u_R * fLoc;
          vec2 fPx = vec2(fCam.x, fCam.y + u_hoverY) * (u_dCam / (u_dCam - fCam.z));
          vec2 df = pxBase - fPx;
          float distF = length(df);
          if (distF < 0.16 * cw) {
            float fadeIn = smoothstep(0.0, 0.10, fLife);
            float fadeOut = pow(1.0 - fLife, 1.75);
            float ringStr = fadeIn * fadeOut * u_propGain * u_holoGain;
            float curR = (0.014 + 0.105 * pow(fLife, 0.58)) * cw;
            float ringW = max(1.1, cw * 0.0018);
            float ang = atan(df.y, df.x);
            float arcMod = 0.70 + 0.30 * sin(ang * 2.0 + 0.65 + u_time);
            float ring = exp(-pow((distF - curR) / ringW, 2.0)) * arcMod * ringStr * 0.62;
            float flareEnv = fadeIn * pow(1.0 - fLife, 2.05) * u_propGain * u_holoGain;
            float cArm = (0.052 + 0.075 * (1.0 - fLife)) * cw;
            float cSig = max(0.85, cArm * 0.022);
            float needleH = exp(-(df.y * df.y) / (2.0 * cSig * cSig)) * exp(-abs(df.x) / (cArm * 0.44));
            float needleV = exp(-(df.x * df.x) / (2.0 * cSig * cSig)) * exp(-abs(df.y) / (cArm * 0.44));
            float pinhole = exp(-dot(df, df) / (2.0 * pow(max(1.2, cArm * 0.042), 2.0)));
            vec3 flareTint = mix(u_propTint, vec3(1.0, 0.99, 0.96), 0.55);
            vec3 propAdd = ring * u_propTint + clamp(needleH + needleV + pinhole * 0.65, 0.0, 0.92) * flareTint * flareEnv * 0.94;
            canvasCol += propAdd;
            trPropFlare = propAdd;
          }
        }
      }
    }
  }

  vec3 trMotifRgb = vec3(0.0);
  float trMotifA = 0.0;
  if (u_motifKind >= 0) {
    for (int fp = 0; fp < 4; fp++) {
      float ffp = float(fp);
      float isBubble = (u_motifKind == 0 && fp >= 2) ? 1.0 : 0.0;
      float dirX = u_motifKind == 2 ? -1.0 : (u_motifKind == 1 ? 1.0 : 0.0);
      float dirY = (u_motifKind == 0 || u_motifKind == 3) ? -1.0 : 1.0;
      vec2 fpUv = vec2(
        0.08 + 0.84 * fract(hash12(vec2(ffp, 4.1)) + tNorm * dirX + ((u_motifKind == 0 || u_motifKind == 3) ? 0.035 * sin(u_time + ffp * 1.9) : 0.0)),
        0.08 + 0.84 * fract(hash12(vec2(ffp, 8.9)) + tNorm * dirY)
      );
      vec2 fCen = 0.5 * (u_faceLock.xy + u_faceLock.zw);
      vec2 fRad = max(0.5 * (u_faceLock.zw - u_faceLock.xy), vec2(0.08));
      float faceSafe = mix(0.14, 1.0, smoothstep(0.85, 1.55, length((fpUv - fCen) / fRad)));
      float zp = 0.022 * cw;
      float compP = (u_dCam - zp) / u_dCam;
      vec3 pLoc = vec3((fpUv.x - 0.5) * cw * compP, (fpUv.y - 0.5) * ch * compP, zp);
      vec3 pCam = u_R * pLoc;
      vec2 pPx = vec2(pCam.x, pCam.y + u_hoverY) * (u_dCam / (u_dCam - pCam.z));
      vec2 dp = pxBase - pPx;
      float pSize = (isBubble > 0.5 ? 0.011 : (0.016 + 0.005 * hash12(vec2(ffp, 2.3)))) * cw;
      if (abs(dp.x) < pSize * 2.0 && abs(dp.y) < pSize * 2.0) {
        float rotA = hash12(vec2(ffp, 7.1)) * 6.283 + u_time * (mod(ffp, 2.0) < 0.5 ? 1.0 : -1.0);
        vec4 mRes = evalBespokeMotif(dp, pSize, rotA, u_time + ffp * 2.1, ffp + 3.0, isBubble);
        float am = mRes.a * faceSafe * 0.90;
        canvasCol = mix(canvasCol, mRes.rgb, am);
        trMotifRgb = trMotifRgb * (1.0 - am) + mRes.rgb * am;
        trMotifA = clamp(trMotifA + am * (1.0 - trMotifA), 0.0, 1.0);
      }
    }
  }

  if (u_transparent == 1) {
    float inSafe = step(14.0, gl_FragCoord.x) * step(gl_FragCoord.x, u_res.x - 14.0)
                 * step(14.0, gl_FragCoord.y) * step(gl_FragCoord.y, u_res.y - 14.0);
    float auraR = length(auraDelta);
    float auraTr = aura * (1.0 - smoothstep(0.72, 1.12, auraR)) * inSafe;
    vec3 auraTrCol = u_auraCol * auraTr * 0.85;
    float shTr = (groundSh > 0.02 ? groundSh : 0.0) * inSafe;
    float shOnly = clamp(shTr * (1.0 - trCardA), 0.0, 0.60);
    float bgTrA = clamp(auraTr * 0.65 + shTr * 0.78, 0.0, 0.88);
    vec3 compRgb = auraTrCol * (1.0 - shOnly) * (1.0 - trCardA) + trCardCol * trCardA;
    float compA = clamp(max(trCardA, max(bgTrA, shOnly)), 0.0, 1.0);
    float mAs = trMotifA * inSafe;
    compRgb = compRgb * (1.0 - mAs) + trMotifRgb * inSafe;
    compA = clamp(mAs + compA * (1.0 - mAs), 0.0, 1.0);
    vec3 pfS = trPropFlare * inSafe;
    float pfM = max(pfS.r, max(pfS.g, pfS.b));
    compA = clamp(max(compA, pfM), 0.0, 1.0);
    compRgb = min(compRgb + pfS, vec3(compA));
    if (compA < 0.015) {
      fragColor = vec4(0.0);
    } else {
      fragColor = vec4(clamp(compRgb / max(compA, 1e-4), 0.0, 1.0), compA);
    }
    return;
  }

  // 1-LSB dither eliminates 8-bit gradient banding on dark studio backdrops
  float dither = (hash12(gl_FragCoord.xy) - 0.5) * (1.2 / 255.0);
  fragColor = vec4(clamp(canvasCol + dither, 0.0, 1.0), 1.0);
}`;

function showError(msg) {
  const b = document.getElementById("errBanner");
  b.style.display = "flex";
  b.textContent = msg;
}

window.__CARD_DEBUG__ = { ready: false, glOk: false, shaderError: null };

async function init() {
  const canvas = document.getElementById("glcanvas");
  const gl = canvas.getContext("webgl2", { antialias: false, alpha: false, powerPreference: "high-performance" });
  if (!gl) {
    window.__CARD_DEBUG__.shaderError = "WebGL2 unavailable";
    showError("当前浏览器不支持 WebGL2，请使用最新版 Chrome / Edge / Safari 打开。");
    return;
  }

  function compile(type, src) {
    const sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      const log = gl.getShaderInfoLog(sh);
      gl.deleteShader(sh);
      throw new Error(log);
    }
    return sh;
  }

  let prog;
  try {
    const vs = compile(gl.VERTEX_SHADER, VS_SRC);
    const fs = compile(gl.FRAGMENT_SHADER, FS_SRC);
    prog = gl.createProgram();
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
    window.__CARD_DEBUG__.glOk = true;
  } catch (err) {
    window.__CARD_DEBUG__.shaderError = String(err);
    showError("WebGL2 着色器编译失败：\n" + err);
    return;
  }

  const quad = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, quad);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
  const aPos = gl.getAttribLocation(prog, "a_pos");
  gl.enableVertexAttribArray(aPos);
  gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

  async function loadTex(uri, unit) {
    const img = new Image();
    img.src = uri;
    await img.decode();
    gl.activeTexture(gl.TEXTURE0 + unit);
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    return tex;
  }

  await Promise.all([
    loadTex(ASSETS.bg, 0),
    loadTex(ASSETS.mid, 1),
    loadTex(ASSETS.fg, 2),
    loadTex(ASSETS.depthNorm, 3),
    loadTex(ASSETS.aux, 4),
    loadTex(ASSETS.fgBevel, 5),
    loadTex(ASSETS.propMask, 6),
  ]);

  gl.useProgram(prog);
  ["u_bg","u_mid","u_fg","u_depthNorm","u_aux","u_fgBevel","u_propMask"].forEach((name, i) => {
    gl.uniform1i(gl.getUniformLocation(prog, name), i);
  });

  const loc = {};
  ["u_res","u_cardSize","u_dCam","u_time","u_yaw","u_pitch","u_hoverY","u_holoGain",
   "u_bgMode","u_transparent","u_holoPattern","u_materialPreset","u_lightingPreset","u_studioCol","u_astroCenter","u_R","u_RT","u_glints","u_glintCount",
   "u_edgeBase","u_edgeSpec","u_metalTint","u_auraCol","u_sandCol1","u_sandCol2","u_seqCols","u_partCol1","u_partCol2",
   "u_propEnabled","u_propStart","u_propTip","u_propTint","u_propGain","u_motifKind","u_faceLock"].forEach((n) => {
    loc[n] = gl.getUniformLocation(prog, n);
  });

  const pal = META.palette || {};
  const HOLO_KEYS = ["starburst", "prism_grid", "cosmos_waves", "cracked_ice", "diagonal_foil", "diamond_lattice"];
  const MAT_KEYS = ["sar_quicksand", "acrylic_brick", "cracked_ice", "etched_foil", "matte_velvet", "clean_tcg"];
  const LIT_KEYS = ["gallery_neutral", "dramatic_rim", "golden_hour", "moonlit_prism", "soft_pastel"];
  const HOLO_MAP = { starburst: 0, prism_grid: 1, cosmos_waves: 2, cracked_ice: 3, diagonal_foil: 4, diamond_lattice: 5 };
  const MAT_MAP = { sar_quicksand: 0, acrylic_brick: 1, cracked_ice: 2, etched_foil: 3, matte_velvet: 4, clean_tcg: 5 };
  const LIT_MAP = { gallery_neutral: 0, dramatic_rim: 1, golden_hour: 2, moonlit_prism: 3, soft_pastel: 4 };
  let holoPatternId = HOLO_MAP[String(META.holo_pattern || "starburst").toLowerCase()] ?? 0;
  let materialPresetId = MAT_MAP[String(META.material_preset || "sar_quicksand").toLowerCase()] ?? 0;
  let lightingPresetId = LIT_MAP[String(META.lighting_preset || "gallery_neutral").toLowerCase()] ?? 0;
  const seqFlat = new Float32Array(12);
  const seqSrc = pal.sequins || [[1,0.86,0.45],[0.62,0.94,1],[0.86,0.92,1],[0.78,0.68,1]];
  for (let i = 0; i < 4; i++) {
    const c = seqSrc[i % seqSrc.length];
    seqFlat[i * 3 + 0] = c[0];
    seqFlat[i * 3 + 1] = c[1];
    seqFlat[i * 3 + 2] = c[2];
  }

  const glintsArr = new Float32Array(16 * 4);
  const gList = META.glints.slice(0, 16);
  gList.forEach((g, idx) => {
    const kindCode = g.kind === "bg_star" ? -(0.1 + g.phase) : (g.kind === "frame" ? (0.6 + g.phase) : (0.1 + g.phase * 0.3));
    glintsArr[idx * 4 + 0] = g.x;
    glintsArr[idx * 4 + 1] = g.y;
    glintsArr[idx * 4 + 2] = g.size;
    glintsArr[idx * 4 + 3] = kindCode;
  });

  let autoOrbit = true;
  let gyroEnabled = false;
  let bgMode = 0;
  let highQual = false;
  let holoGain = 1.05;
  let targetYaw = 0, targetPitch = 0;
  let curYaw = 0, curPitch = 0;
  let manualHold = false;
  let forcedPose = null;
  let timeAcc = 0;
  let lastTs = performance.now();
  let rafId = 0;
  let isPageHidden = document.hidden;
  let hasDrawnFirst = false;

  // Pre-allocated rotation matrices eliminate per-frame GC churn at 60fps
  const matR = new Float32Array(9);
  const matRT = new Float32Array(9);
  function writeRotMats(yawDeg, pitchDeg, rollDeg) {
    const ry = yawDeg * 0.017453292519943295;
    const rx = pitchDeg * 0.017453292519943295;
    const rz = rollDeg * 0.017453292519943295;
    const cy = Math.cos(ry), sy = Math.sin(ry);
    const cx = Math.cos(rx), sx = Math.sin(rx);
    const cz = Math.cos(rz), sz = Math.sin(rz);
    const r00 = cz * cy - sz * sx * sy, r01 = -sz * cx, r02 = cz * sy + sz * sx * cy;
    const r10 = sz * cy + cz * sx * sy, r11 =  cz * cx, r12 = sz * sy - cz * sx * cy;
    const r20 = -cx * sy,               r21 =  sx,      r22 = cx * cy;
    matR[0] = r00; matR[1] = r10; matR[2] = r20;
    matR[3] = r01; matR[4] = r11; matR[5] = r21;
    matR[6] = r02; matR[7] = r12; matR[8] = r22;
    matRT[0] = r00; matRT[1] = r01; matRT[2] = r02;
    matRT[3] = r10; matRT[4] = r11; matRT[5] = r12;
    matRT[6] = r20; matRT[7] = r21; matRT[8] = r22;
  }

  function resize() {
    const dprMax = highQual ? 1.5 : 1.0;
    const maxDim = highQual ? 1440 : 900;
    const dpr = Math.min(window.devicePixelRatio || 1, dprMax);
    const rawW = Math.max(300, Math.floor(window.innerWidth * dpr));
    const rawH = Math.max(300, Math.floor(window.innerHeight * dpr));
    const cap = Math.min(1.0, maxDim / Math.max(rawW, rawH));
    const w = Math.floor(rawW * cap);
    const h = Math.floor(rawH * cap);
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
      gl.viewport(0, 0, w, h);
    }
  }
  window.addEventListener("resize", () => { resize(); if (forcedPose || !rafId) drawNow(); });
  canvas.addEventListener("webglcontextlost", (e) => {
    e.preventDefault();
    if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
    showError("WebGL 上下文已暂停，请刷新页面恢复渲染。");
  });
  resize();

  function setVec3(u, v, fb) {
    const c = v || fb;
    gl.uniform3f(u, c[0], c[1], c[2]);
  }

  // Upload all immutable uniforms once instead of every animation frame
  gl.useProgram(prog);
  gl.uniform1i(loc.u_holoPattern, holoPatternId);
  gl.uniform3f(loc.u_studioCol, META.studio_color_rgb[0] / 255, META.studio_color_rgb[1] / 255, META.studio_color_rgb[2] / 255);
  gl.uniform2f(loc.u_astroCenter, META.astrolabe_center[0], META.astrolabe_center[1]);
  gl.uniform4fv(loc.u_glints, glintsArr);
  gl.uniform1i(loc.u_glintCount, gList.length);
  setVec3(loc.u_edgeBase, pal.edge_base, [0.52, 0.43, 0.28]);
  setVec3(loc.u_edgeSpec, pal.edge_spec, [1.00, 0.92, 0.72]);
  setVec3(loc.u_metalTint, pal.metal_tint, [1.00, 0.89, 0.62]);
  setVec3(loc.u_auraCol, pal.aura, [0.24, 0.55, 0.95]);
  setVec3(loc.u_sandCol1, pal.sand1, [1.00, 0.85, 0.48]);
  setVec3(loc.u_sandCol2, pal.sand2, [0.55, 0.90, 1.00]);
  gl.uniform3fv(loc.u_seqCols, seqFlat);
  const motif = META.motion_motif || {};
  const pfx = META.prop_fx || {};
  const p1c = (motif.kind_id >= 0 && motif.color1) ? motif.color1 : pal.part1;
  const p2c = (motif.kind_id >= 0 && motif.color2) ? motif.color2 : pal.part2;
  setVec3(loc.u_partCol1, p1c, [1.00, 0.88, 0.55]);
  setVec3(loc.u_partCol2, p2c, [0.55, 0.90, 1.00]);
  gl.uniform1i(loc.u_propEnabled, pfx.enabled ? 1 : 0);
  const ps = pfx.start_uv || [0.5, 0.7];
  const pt = pfx.tip_uv || [0.5, 0.3];
  gl.uniform2f(loc.u_propStart, ps[0], ps[1]);
  gl.uniform2f(loc.u_propTip, pt[0], pt[1]);
  setVec3(loc.u_propTint, pfx.tint, [0.92, 0.96, 1.0]);
  gl.uniform1f(loc.u_propGain, pfx.gain ?? 0.95);
  gl.uniform1i(loc.u_motifKind, motif.kind_id ?? -1);
  const fb = META.face_box || [0.40, 0.20, 0.60, 0.35];
  gl.uniform4f(loc.u_faceLock, fb[0], fb[1], fb[2], fb[3]);

  function drawNow() {
    const yawNorm = Math.max(-1.0, Math.min(1.0, curYaw / 24.0));
    const roll = 1.6 * yawNorm;
    const hoverY = -0.013 * canvas.height * yawNorm;
    const cw = Math.min(canvas.width * 0.67, canvas.height * 0.67 * 0.75);
    const ch = cw * (4.0 / 3.0);
    const dCam = 3.8 * cw;
    writeRotMats(curYaw, curPitch, roll);

    gl.uniform2f(loc.u_res, canvas.width, canvas.height);
    gl.uniform2f(loc.u_cardSize, cw, ch);
    gl.uniform1f(loc.u_dCam, dCam);
    gl.uniform1f(loc.u_time, timeAcc);
    gl.uniform1f(loc.u_yaw, curYaw);
    gl.uniform1f(loc.u_pitch, curPitch);
    gl.uniform1f(loc.u_hoverY, hoverY);
    gl.uniform1f(loc.u_holoGain, holoGain);
    gl.uniform1i(loc.u_bgMode, bgMode);
    gl.uniform1i(loc.u_transparent, 0);
    gl.uniform1i(loc.u_holoPattern, holoPatternId);
    gl.uniform1i(loc.u_materialPreset, materialPresetId);
    gl.uniform1i(loc.u_lightingPreset, lightingPresetId);
    gl.uniformMatrix3fv(loc.u_R, false, matR);
    gl.uniformMatrix3fv(loc.u_RT, false, matRT);

    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    if (!hasDrawnFirst) {
      hasDrawnFirst = true;
      canvas.classList.add("ready");
    }
  }

  function ensureLoop() {
    if (!rafId && !isPageHidden) {
      lastTs = performance.now();
      rafId = requestAnimationFrame(renderFrame);
    }
  }

  document.addEventListener("visibilitychange", () => {
    isPageHidden = document.hidden;
    if (isPageHidden) {
      if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
    } else if (!forcedPose) {
      ensureLoop();
    }
  });

  function renderFrame(now) {
    rafId = 0;
    const dt = Math.min((now - lastTs) / 1000, 0.05);
    lastTs = now;
    if (forcedPose) {
      curYaw = forcedPose.yaw;
      curPitch = forcedPose.pitch;
      timeAcc = forcedPose.time ?? (curYaw / 24.0);
      drawNow();
      return;
    }
    timeAcc += dt * (2.0 * Math.PI / 5.2);
    if (autoOrbit && !manualHold && !gyroEnabled) {
      targetYaw = 24.0 * Math.sin(timeAcc);
      targetPitch = 11.5 * Math.sin(2.0 * timeAcc);
    }
    const damp = 1.0 - Math.exp(-9.0 * dt);
    curYaw += (targetYaw - curYaw) * damp;
    curPitch += (targetPitch - curPitch) * damp;
    drawNow();

    const settled = !autoOrbit && !gyroEnabled && !manualHold
      && Math.abs(targetYaw - curYaw) < 0.004 && Math.abs(targetPitch - curPitch) < 0.004;
    if (!settled && !isPageHidden) {
      rafId = requestAnimationFrame(renderFrame);
    }
  }

  const hintPill = document.getElementById("hintPill");
  let hintDismissed = false;
  function dismissHint() {
    if (!hintDismissed && hintPill) {
      hintDismissed = true;
      hintPill.classList.add("faded");
    }
  }
  setTimeout(dismissHint, 5500);

  function updateFromPointer(clientX, clientY) {
    const nx = (clientX / window.innerWidth) * 2.0 - 1.0;
    const ny = (clientY / window.innerHeight) * 2.0 - 1.0;
    targetYaw = Math.max(-30.0, Math.min(30.0, nx * 30.0));
    targetPitch = Math.max(-19.0, Math.min(19.0, -ny * 19.0));
  }
  canvas.addEventListener("pointermove", (e) => {
    if (gyroEnabled) return;
    forcedPose = null;
    manualHold = true;
    dismissHint();
    updateFromPointer(e.clientX, e.clientY);
    ensureLoop();
  });
  canvas.addEventListener("pointerleave", () => { manualHold = false; ensureLoop(); });
  canvas.addEventListener("pointerdown", (e) => {
    forcedPose = null;
    manualHold = true;
    dismissHint();
    updateFromPointer(e.clientX, e.clientY);
    ensureLoop();
  });
  canvas.addEventListener("dblclick", () => {
    resetView();
  });
  window.addEventListener("pointerup", () => {
    if (autoOrbit) manualHold = false;
  });

  const btnOrbit = document.getElementById("btnOrbit");
  const orbitLbl = document.getElementById("orbitLbl");
  const btnGyro = document.getElementById("btnGyro");
  const btnReset = document.getElementById("btnReset");
  const btnBg = document.getElementById("btnBg");
  const bgLabel = document.getElementById("bgLabel");
  const bgSwatch = document.getElementById("bgSwatch");
  const btnQual = document.getElementById("btnQual");
  const qualLabel = document.getElementById("qualLabel");
  const btnCraft = document.getElementById("btnCraft");
  const craftLbl = document.getElementById("craftLbl");
  const craftPop = document.getElementById("craftPop");
  const holoCtrl = document.getElementById("holoCtrl");
  const matChips = document.querySelectorAll("#matChips .chip");
  const litChips = document.querySelectorAll("#litChips .chip");
  const holoChips = document.querySelectorAll("#holoChips .chip");
  const holoRange = document.getElementById("holoRange");
  const holoVal = document.getElementById("holoVal");
  const btnLang = document.getElementById("btnLang");
  const btnZen = document.getElementById("btnZen");
  const iconEyeOpen = document.getElementById("iconEyeOpen");
  const iconEyeClosed = document.getElementById("iconEyeClosed");
  const lblMat = document.getElementById("lblMat");
  const lblLit = document.getElementById("lblLit");
  const lblHolo = document.getElementById("lblHolo");
  const lblExp = document.getElementById("lblExp");
  const expWebpLbl = document.getElementById("expWebpLbl");
  const expGifLbl = document.getElementById("expGifLbl");

  const hasCjk = (s) => /[\u3400-\u9fff]/.test(String(s || ""));
  const customStudioEn = (META.studio_bg_label && !hasCjk(META.studio_bg_label)) ? META.studio_bg_label : "Dark Velvet";
  const I18N = {
    zh: {
      htmlLang: "zh-CN",
      langBtn: "EN",
      langTitle: "Switch to English",
      zenTitle: "纯净模式 (H)",
      zenAria: "切换界面显示",
      hint: "悬停或拖拽赏卡 · 双击归零 · H 隐藏界面",
      craftAria: "材质、光影与底纹实时切换",
      controlsAria: "3D 卡片控制栏",
      orbit: "巡航",
      orbitTitle: "自动巡航 (Space)",
      resetTitle: "归零 0° (双击画布)",
      resetAria: "归零角度",
      gyroTitle: "陀螺仪倾摆",
      gyroAria: "陀螺仪倾摆",
      bgTitle: "切换展台背景",
      bgNames: [META.studio_bg_label || "暗绒展台", "黑曜纯黑", "画廊亮白"],
      qualTitle: "切换渲染清晰度",
      qualSmooth: "流畅",
      qualHi: "高清",
      craft: "工艺",
      craftTitle: "实时切换材质、光影与底纹",
      holoTitle: "调整全息闪度",
      lblMat: "材质",
      lblLit: "光影",
      lblHolo: "底纹",
      lblExp: "导出",
      mats: ["流麻 SAR", "亚克力砖", "碎冰闪", "浮雕箔", "丝绒烫金", "纯净闪卡"],
      lits: ["展柜均衡", "戏剧轮廓", "暖阳鎏金", "冷月幽光", "柔光箱"],
      holos: ["星芒", "棱镜格", "星海波", "碎冰晶", "斜向拉丝", "菱格暗纹"],
      expWebp: "透明 WebP",
      expWebpTitle: "离线导出 690×960 透明零残影动图 WebP（不覆盖原文件）",
      expGif: "动图 GIF",
      expGifTitle: "离线导出 460×640 当前背景动图 GIF（不覆盖原文件）",
      copyCfg: "复制参数",
      copyCfgTitle: "复制当前工艺配置 JSON 片段",
      copied: "已复制",
      expPrep: "准备中…",
      expWebpEnc: (i, n) => `透明 WebP 编码中 ${i} / ${n}`,
      expWebpMux: "封装零残影 WebP 容器…",
      expWebpUnsup: "当前浏览器不支持原生 WebP 编码，请使用 Chrome / Edge / Firefox 或导出 GIF。",
      expGifPal: "分析 256 色最优调色板…",
      expGifEnc: (i, n) => `动图 GIF 编码中 ${i} / ${n}`,
      expDone: (f) => `已导出 ${f}`,
      expFail: (m) => `导出失败：${m}`,
    },
    en: {
      htmlLang: "en",
      langBtn: "中文",
      langTitle: "切换为中文",
      zenTitle: "Zen Mode (H)",
      zenAria: "Toggle HUD visibility",
      hint: "Hover or drag to tilt · Double-click to reset · Press H for Zen",
      craftAria: "Live craft, lighting & holo studio",
      controlsAria: "3D card controls",
      orbit: "Orbit",
      orbitTitle: "Auto-Orbit (Space)",
      resetTitle: "Reset 0° (Double-click)",
      resetAria: "Reset angle",
      gyroTitle: "Gyroscope Tilt",
      gyroAria: "Gyroscope Tilt",
      bgTitle: "Switch showcase backdrop",
      bgNames: [customStudioEn, "Pitch Obsidian", "Gallery White"],
      qualTitle: "Toggle render resolution",
      qualSmooth: "Smooth",
      qualHi: "Hi-Res",
      craft: "Craft",
      craftTitle: "Switch material, lighting & holo live",
      holoTitle: "Holo Intensity",
      lblMat: "Craft",
      lblLit: "Light",
      lblHolo: "Holo",
      lblExp: "Export",
      mats: ["SAR Quicksand", "Acrylic Brick", "Cracked Ice", "Etched Foil", "Matte Foil", "Clean TCG"],
      lits: ["Gallery", "Dramatic Rim", "Golden Hour", "Moonlit Prism", "Soft Pastel"],
      holos: ["Starburst", "Prism Grid", "Cosmos", "Cracked Ice", "Diagonal", "Diamond"],
      expWebp: "Transparent WebP",
      expWebpTitle: "Export 690×960 zero-ghosting transparent WebP offline (non-overwriting)",
      expGif: "Animated GIF",
      expGifTitle: "Export 460×640 animated GIF offline with current backdrop (non-overwriting)",
      copyCfg: "Copy JSON",
      copyCfgTitle: "Copy current craft preset JSON snippet",
      copied: "Copied",
      expPrep: "Preparing…",
      expWebpEnc: (i, n) => `Encoding WebP ${i} / ${n}`,
      expWebpMux: "Muxing zero-ghosting WebP…",
      expWebpUnsup: "Native WebP encoding is unavailable in this browser. Use Chrome / Edge / Firefox or export GIF.",
      expGifPal: "Building 256-color palette…",
      expGifEnc: (i, n) => `Encoding GIF ${i} / ${n}`,
      expDone: (f) => `Exported ${f}`,
      expFail: (m) => `Export failed: ${m}`,
    },
  };

  function resolveInitialLang() {
    try {
      const saved = localStorage.getItem("holo_card_ui_lang");
      if (saved === "zh" || saved === "en") return saved;
    } catch {}
    const cfgLang = String(META.ui_lang || "auto").toLowerCase().trim();
    if (cfgLang === "zh" || cfgLang === "en") return cfgLang;
    const nav = String(navigator.language || "zh").toLowerCase();
    return nav.startsWith("zh") ? "zh" : "en";
  }
  let curLang = resolveInitialLang();
  const T = () => I18N[curLang] || I18N.zh;

  function toggleOrbit() {
    forcedPose = null;
    autoOrbit = !autoOrbit;
    manualHold = false;
    btnOrbit.classList.toggle("active", autoOrbit);
    ensureLoop();
  }
  function resetView() {
    forcedPose = null;
    autoOrbit = false;
    manualHold = false;
    btnOrbit.classList.remove("active");
    targetYaw = 0; targetPitch = 0;
    ensureLoop();
  }
  function toggleZen() {
    const zen = document.body.classList.toggle("zen-mode");
    if (zen) setCraftOpen(false);
    iconEyeOpen.style.display = zen ? "none" : "";
    iconEyeClosed.style.display = zen ? "" : "none";
  }

  btnOrbit.onclick = toggleOrbit;
  btnReset.onclick = resetView;
  btnZen.onclick = toggleZen;

  const studioSw = META.studio_color_rgb || [24, 38, 66];
  const bgSwatches = [
    `rgb(${Math.min(255, Math.round(studioSw[0] * 0.45 + 24))}, ${Math.min(255, Math.round(studioSw[1] * 0.45 + 26))}, ${Math.min(255, Math.round(studioSw[2] * 0.45 + 32))})`,
    "#06070a",
    "#f2f4f8",
  ];
  bgSwatch.style.background = bgSwatches[0];

  function applyBgMode(mode) {
    bgMode = ((mode % 3) + 3) % 3;
    bgLabel.textContent = T().bgNames[bgMode];
    bgSwatch.style.background = bgSwatches[bgMode];
    document.body.classList.toggle("theme-light", bgMode === 2);
    if (forcedPose || !rafId) drawNow();
  }
  btnBg.onclick = () => applyBgMode(bgMode + 1);

  btnQual.onclick = () => {
    highQual = !highQual;
    qualLabel.textContent = highQual ? T().qualHi : T().qualSmooth;
    btnQual.classList.toggle("active", highQual);
    resize();
    if (forcedPose || !rafId) drawNow();
  };

  function syncCraftChips() {
    matChips.forEach((b) => b.classList.toggle("active", Number(b.dataset.mat) === materialPresetId));
    litChips.forEach((b) => b.classList.toggle("active", Number(b.dataset.lit) === lightingPresetId));
    holoChips.forEach((b) => b.classList.toggle("active", Number(b.dataset.holo) === holoPatternId));
  }
  syncCraftChips();

  let isExporting = false;
  const btnExpWebp = document.getElementById("btnExpWebp");
  const btnExpGif = document.getElementById("btnExpGif");
  const btnCopyCfg = document.getElementById("btnCopyCfg");
  const copyCfgLbl = document.getElementById("copyCfgLbl");
  const expStatus = document.getElementById("expStatus");
  const expTxt = document.getElementById("expTxt");
  const expPct = document.getElementById("expPct");
  const expFill = document.getElementById("expFill");

  function applyLang(lang, persist = true) {
    curLang = lang === "en" ? "en" : "zh";
    if (persist) {
      try { localStorage.setItem("holo_card_ui_lang", curLang); } catch {}
    }
    const tr = T();
    document.documentElement.lang = tr.htmlLang;
    btnLang.textContent = tr.langBtn;
    btnLang.title = tr.langTitle;
    btnZen.title = tr.zenTitle;
    btnZen.setAttribute("aria-label", tr.zenAria);
    if (hintPill) hintPill.textContent = tr.hint;
    craftPop.setAttribute("aria-label", tr.craftAria);
    document.getElementById("controls").setAttribute("aria-label", tr.controlsAria);
    orbitLbl.textContent = tr.orbit;
    btnOrbit.title = tr.orbitTitle;
    btnReset.title = tr.resetTitle;
    btnReset.setAttribute("aria-label", tr.resetAria);
    btnGyro.title = tr.gyroTitle;
    btnGyro.setAttribute("aria-label", tr.gyroAria);
    btnBg.title = tr.bgTitle;
    bgLabel.textContent = tr.bgNames[bgMode];
    btnQual.title = tr.qualTitle;
    qualLabel.textContent = highQual ? tr.qualHi : tr.qualSmooth;
    craftLbl.textContent = tr.craft;
    btnCraft.title = tr.craftTitle;
    holoCtrl.title = tr.holoTitle;
    holoRange.setAttribute("aria-label", tr.holoTitle);
    lblMat.textContent = tr.lblMat;
    lblLit.textContent = tr.lblLit;
    lblHolo.textContent = tr.lblHolo;
    lblExp.textContent = tr.lblExp;
    matChips.forEach((b) => { const i = Number(b.dataset.mat); if (tr.mats[i]) b.textContent = tr.mats[i]; });
    litChips.forEach((b) => { const i = Number(b.dataset.lit); if (tr.lits[i]) b.textContent = tr.lits[i]; });
    holoChips.forEach((b) => { const i = Number(b.dataset.holo); if (tr.holos[i]) b.textContent = tr.holos[i]; });
    expWebpLbl.textContent = tr.expWebp;
    btnExpWebp.title = tr.expWebpTitle;
    expGifLbl.textContent = tr.expGif;
    btnExpGif.title = tr.expGifTitle;
    copyCfgLbl.textContent = tr.copyCfg;
    btnCopyCfg.title = tr.copyCfgTitle;
    if (!isExporting && !expStatus.classList.contains("show")) {
      expTxt.textContent = tr.expPrep;
    }
  }
  applyLang(curLang, false);
  btnLang.onclick = (e) => {
    e.stopPropagation();
    applyLang(curLang === "zh" ? "en" : "zh", true);
  };

  function setCraftOpen(open) {
    if (!open && isExporting) return;
    craftPop.classList.toggle("open", open);
    btnCraft.classList.toggle("active", open);
  }
  btnCraft.onclick = (e) => {
    e.stopPropagation();
    dismissHint();
    setCraftOpen(!craftPop.classList.contains("open"));
  };
  craftPop.addEventListener("pointerdown", (e) => e.stopPropagation());
  document.addEventListener("pointerdown", (e) => {
    if (!isExporting && craftPop.classList.contains("open") && !craftPop.contains(e.target) && !btnCraft.contains(e.target) && !btnLang.contains(e.target)) {
      setCraftOpen(false);
    }
  });

  function buildExportFilename(ext) {
    const rawTitle = String(META.title || "holo_card").trim();
    const safeTitle = rawTitle.replace(/[\\/:*?"<>|\s]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 32) || "holo_card";
    return `${safeTitle}_${MAT_KEYS[materialPresetId]}_${LIT_KEYS[lightingPresetId]}_${HOLO_KEYS[holoPatternId]}.${ext}`;
  }

  function triggerDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }

  function setExportProgress(label, pct) {
    expStatus.classList.add("show");
    expTxt.textContent = label;
    const p = Math.max(0, Math.min(100, Math.round(pct)));
    expPct.textContent = p + "%";
    expFill.style.width = p + "%";
  }

  function createExportFbo(w, h) {
    gl.activeTexture(gl.TEXTURE7);
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    const fbo = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    return { fbo, tex };
  }

  function renderExportFrame(w, h, fIdx, numFrames, transparent, rawBuf, flippedBuf) {
    const t = fIdx / numFrames;
    const ang = 2.0 * Math.PI * t;
    const yaw = 24.0 * Math.sin(ang);
    const pitch = 11.5 * Math.sin(2.0 * ang);
    const roll = 1.6 * Math.sin(ang);
    const hoverY = -0.013 * h * Math.sin(ang);
    const cw = 492.0 * (w / 690.0);
    const ch = cw * (4.0 / 3.0);
    const dCam = 3.8 * cw;
    writeRotMats(yaw, pitch, roll);

    gl.useProgram(prog);
    gl.viewport(0, 0, w, h);
    gl.uniform2f(loc.u_res, w, h);
    gl.uniform2f(loc.u_cardSize, cw, ch);
    gl.uniform1f(loc.u_dCam, dCam);
    gl.uniform1f(loc.u_time, ang);
    gl.uniform1f(loc.u_yaw, yaw);
    gl.uniform1f(loc.u_pitch, pitch);
    gl.uniform1f(loc.u_hoverY, hoverY);
    gl.uniform1f(loc.u_holoGain, holoGain);
    gl.uniform1i(loc.u_bgMode, bgMode);
    gl.uniform1i(loc.u_transparent, transparent ? 1 : 0);
    gl.uniform1i(loc.u_holoPattern, holoPatternId);
    gl.uniform1i(loc.u_materialPreset, materialPresetId);
    gl.uniform1i(loc.u_lightingPreset, lightingPresetId);
    gl.uniformMatrix3fv(loc.u_R, false, matR);
    gl.uniformMatrix3fv(loc.u_RT, false, matRT);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, rawBuf);

    const rowBytes = w * 4;
    for (let y = 0; y < h; y++) {
      const srcOff = (h - 1 - y) * rowBytes;
      flippedBuf.set(rawBuf.subarray(srcOff, srcOff + rowBytes), y * rowBytes);
    }
  }

  // Pure offline RIFF Animated RGBA WebP muxer (dispose=1, no_blend=1 zero-ghosting)
  function muxAnimatedWebP(frameWebps, w, h, durMs) {
    const anmfChunks = [];
    let totalAnmf = 0;
    for (let i = 0; i < frameWebps.length; i++) {
      const buf = frameWebps[i];
      if (buf.length < 12 || buf[0] !== 0x52 || buf[1] !== 0x49 || buf[8] !== 0x57 || buf[9] !== 0x45) {
        throw new Error("浏览器未输出标准 WebP 帧，请使用 Chrome / Edge / Firefox 导出 WebP。");
      }
      const subChunks = [];
      let subLen = 0;
      let pos = 12;
      while (pos + 8 <= buf.length) {
        const c0 = buf[pos], c1 = buf[pos + 1], c2 = buf[pos + 2], c3 = buf[pos + 3];
        const csz = (buf[pos + 4]) | (buf[pos + 5] << 8) | (buf[pos + 6] << 16) | (buf[pos + 7] << 24);
        const fullLen = 8 + csz + (csz & 1);
        const isAlph = c0 === 0x41 && c1 === 0x4C && c2 === 0x50 && c3 === 0x48;
        const isVp8  = c0 === 0x56 && c1 === 0x50 && c2 === 0x38 && (c3 === 0x20 || c3 === 0x4C);
        if ((isAlph || isVp8) && pos + fullLen <= buf.length) {
          subChunks.push(buf.subarray(pos, pos + fullLen));
          subLen += fullLen;
        }
        pos += fullLen;
      }
      const payloadLen = 16 + subLen;
      const chunkLen = 8 + payloadLen + (payloadLen & 1);
      const out = new Uint8Array(chunkLen);
      out[0] = 0x41; out[1] = 0x4E; out[2] = 0x4D; out[3] = 0x46; // 'ANMF'
      out[4] = payloadLen & 255; out[5] = (payloadLen >>> 8) & 255; out[6] = (payloadLen >>> 16) & 255; out[7] = (payloadLen >>> 24) & 255;
      // X=0, Y=0 (6 bytes zero), Width-1, Height-1, DurMs, Flags=0x03 (dispose=1, no_blend=1)
      const wm = w - 1, hm = h - 1;
      out[14] = wm & 255; out[15] = (wm >>> 8) & 255; out[16] = (wm >>> 16) & 255;
      out[17] = hm & 255; out[18] = (hm >>> 8) & 255; out[19] = (hm >>> 16) & 255;
      out[20] = durMs & 255; out[21] = (durMs >>> 8) & 255; out[22] = (durMs >>> 16) & 255;
      out[23] = 0x03;
      let wp = 24;
      for (const sc of subChunks) { out.set(sc, wp); wp += sc.length; }
      anmfChunks.push(out);
      totalAnmf += out.length;
    }
    const riffSize = 4 + 18 + 14 + totalAnmf;
    const file = new Uint8Array(8 + riffSize);
    file.set([0x52, 0x49, 0x46, 0x46], 0); // 'RIFF'
    file[4] = riffSize & 255; file[5] = (riffSize >>> 8) & 255; file[6] = (riffSize >>> 16) & 255; file[7] = (riffSize >>> 24) & 255;
    file.set([0x57, 0x45, 0x42, 0x50], 8); // 'WEBP'
    // VP8X (flags = 0x12: Animation + Alpha)
    const wm = w - 1, hm = h - 1;
    file.set([0x56, 0x50, 0x38, 0x58, 10, 0, 0, 0, 0x12, 0, 0, 0, wm & 255, (wm >>> 8) & 255, (wm >>> 16) & 255, hm & 255, (hm >>> 8) & 255, (hm >>> 16) & 255], 12);
    // ANIM (bg = 0,0,0,0, loop = 0)
    file.set([0x41, 0x4E, 0x49, 0x4D, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0], 30);
    let p = 44;
    for (const ac of anmfChunks) { file.set(ac, p); p += ac.length; }
    return new Blob([file], { type: "image/webp" });
  }

  // Pure offline GIF89a encoder (Median-Cut 256-color shared palette + Floyd-Steinberg + fast LZW)
  function buildMedianCutPalette(samples) {
    let boxes = [samples];
    while (boxes.length < 256) {
      let bestIdx = -1, bestSpan = -1, bestCh = 0;
      for (let i = 0; i < boxes.length; i++) {
        const b = boxes[i];
        if (b.length < 6) continue;
        let r0 = 255, r1 = 0, g0 = 255, g1 = 0, b0 = 255, b1 = 0;
        for (let j = 0; j < b.length; j += 3) {
          const r = b[j], g = b[j + 1], bl = b[j + 2];
          if (r < r0) r0 = r; if (r > r1) r1 = r;
          if (g < g0) g0 = g; if (g > g1) g1 = g;
          if (bl < b0) b0 = bl; if (bl > b1) b1 = bl;
        }
        const rs = r1 - r0, gs = g1 - g0, bs = b1 - b0;
        const span = Math.max(rs, gs, bs);
        if (span > bestSpan) {
          bestSpan = span; bestIdx = i;
          bestCh = rs >= gs && rs >= bs ? 0 : (gs >= bs ? 1 : 2);
        }
      }
      if (bestIdx < 0 || bestSpan <= 0) break;
      const box = boxes[bestIdx];
      const n = box.length / 3;
      const order = new Int32Array(n);
      for (let i = 0; i < n; i++) order[i] = i;
      order.sort((a, b) => box[a * 3 + bestCh] - box[b * 3 + bestCh]);
      const mid = n >> 1;
      const left = new Uint8Array(mid * 3);
      const right = new Uint8Array((n - mid) * 3);
      for (let i = 0; i < mid; i++) {
        const s = order[i] * 3;
        left[i * 3] = box[s]; left[i * 3 + 1] = box[s + 1]; left[i * 3 + 2] = box[s + 2];
      }
      for (let i = mid; i < n; i++) {
        const s = order[i] * 3, d = (i - mid) * 3;
        right[d] = box[s]; right[d + 1] = box[s + 1]; right[d + 2] = box[s + 2];
      }
      boxes[bestIdx] = left;
      boxes.push(right);
    }
    const palOut = new Uint8Array(768);
    for (let i = 0; i < boxes.length && i < 256; i++) {
      const b = boxes[i];
      const n = b.length / 3;
      if (n <= 0) continue;
      let sr = 0, sg = 0, sb = 0;
      for (let j = 0; j < b.length; j += 3) { sr += b[j]; sg += b[j + 1]; sb += b[j + 2]; }
      palOut[i * 3] = Math.round(sr / n);
      palOut[i * 3 + 1] = Math.round(sg / n);
      palOut[i * 3 + 2] = Math.round(sb / n);
    }
    return palOut;
  }

  function buildRgb555Lut(palOut) {
    const lut = new Uint8Array(32768);
    for (let r5 = 0; r5 < 32; r5++) {
      const r = (r5 << 3) | 4;
      for (let g5 = 0; g5 < 32; g5++) {
        const g = (g5 << 3) | 4;
        const base = (r5 << 10) | (g5 << 5);
        for (let b5 = 0; b5 < 32; b5++) {
          const b = (b5 << 3) | 4;
          let best = 0, bestD = 1e9;
          for (let i = 0; i < 256; i++) {
            const dr = r - palOut[i * 3], dg = g - palOut[i * 3 + 1], db = b - palOut[i * 3 + 2];
            const d = dr * dr + dg * dg + db * db;
            if (d < bestD) { bestD = d; best = i; }
          }
          lut[base | b5] = best;
        }
      }
    }
    return lut;
  }

  function quantizeFrameFS(rgba, w, h, palOut, lut, outIdx) {
    const stride = (w + 2) * 3;
    let errCur = new Float32Array(stride);
    let errNxt = new Float32Array(stride);
    for (let y = 0; y < h; y++) {
      errNxt.fill(0);
      const rowOff = y * w;
      for (let x = 0; x < w; x++) {
        const p4 = (rowOff + x) * 4;
        const eOff = (x + 1) * 3;
        const r = Math.max(0, Math.min(255, rgba[p4] + errCur[eOff]));
        const g = Math.max(0, Math.min(255, rgba[p4 + 1] + errCur[eOff + 1]));
        const b = Math.max(0, Math.min(255, rgba[p4 + 2] + errCur[eOff + 2]));
        const idx = lut[((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)];
        outIdx[rowOff + x] = idx;
        const dr = r - palOut[idx * 3], dg = g - palOut[idx * 3 + 1], db = b - palOut[idx * 3 + 2];
        const eR = eOff + 3;
        errCur[eR] += dr * 0.4375; errCur[eR + 1] += dg * 0.4375; errCur[eR + 2] += db * 0.4375;
        const eDL = eOff - 3;
        errNxt[eDL] += dr * 0.1875; errNxt[eDL + 1] += dg * 0.1875; errNxt[eDL + 2] += db * 0.1875;
        errNxt[eOff] += dr * 0.3125; errNxt[eOff + 1] += dg * 0.3125; errNxt[eOff + 2] += db * 0.3125;
        errNxt[eR] += dr * 0.0625; errNxt[eR + 1] += dg * 0.0625; errNxt[eR + 2] += db * 0.0625;
      }
      const tmp = errCur; errCur = errNxt; errNxt = tmp;
    }
  }

  function lzwEncodeGif(indices) {
    const clearCode = 256, eoiCode = 257;
    const htKey = new Int32Array(8192).fill(-1);
    const htVal = new Int32Array(8192);
    const out = [];
    const block = new Uint8Array(256);
    let blockLen = 0;
    let bitBuf = 0, bitCnt = 0;

    function flushBlock() {
      if (blockLen > 0) {
        const c = new Uint8Array(blockLen + 1);
        c[0] = blockLen;
        c.set(block.subarray(0, blockLen), 1);
        out.push(c);
        blockLen = 0;
      }
    }
    function emit(code, size) {
      bitBuf |= code << bitCnt;
      bitCnt += size;
      while (bitCnt >= 8) {
        block[blockLen++] = bitBuf & 255;
        bitBuf >>>= 8;
        bitCnt -= 8;
        if (blockLen === 255) flushBlock();
      }
    }

    let codeSize = 9, nextCode = 258;
    emit(clearCode, codeSize);
    let prefix = indices[0];
    for (let i = 1; i < indices.length; i++) {
      const k = indices[i];
      const key = (prefix << 8) | k;
      let slot = ((prefix << 5) ^ ((k * 2654435761) >>> 20)) & 8191;
      let found = -1;
      while (true) {
        const hk = htKey[slot];
        if (hk === key) { found = htVal[slot]; break; }
        if (hk === -1) break;
        slot = (slot + 1) & 8191;
      }
      if (found >= 0) {
        prefix = found;
      } else {
        emit(prefix, codeSize);
        if (nextCode < 4096) {
          if (nextCode === (1 << codeSize) && codeSize < 12) codeSize++;
          htKey[slot] = key;
          htVal[slot] = nextCode++;
        } else {
          emit(clearCode, codeSize);
          htKey.fill(-1);
          codeSize = 9;
          nextCode = 258;
        }
        prefix = k;
      }
    }
    emit(prefix, codeSize);
    emit(eoiCode, codeSize);
    if (bitCnt > 0) {
      block[blockLen++] = bitBuf & 255;
    }
    flushBlock();
    out.push(new Uint8Array([0])); // block terminator
    let total = 1;
    for (const c of out) total += c.length;
    const res = new Uint8Array(total);
    res[0] = 8; // LZW min code size
    let p = 1;
    for (const c of out) { res.set(c, p); p += c.length; }
    return res;
  }

  async function runOfflineExport(kind) {
    if (isExporting) return;
    isExporting = true;
    btnExpWebp.disabled = true;
    btnExpGif.disabled = true;
    if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }

    const NUM_FRAMES = 84;
    const DUR_MS = 60;
    const expW = kind === "webp" ? 690 : 460;
    const expH = kind === "webp" ? 960 : 640;
    const { fbo, tex } = createExportFbo(expW, expH);
    const rawBuf = new Uint8Array(expW * expH * 4);
    const flipBuf = new Uint8Array(expW * expH * 4);

    try {
      if (kind === "webp") {
        const c2d = document.createElement("canvas");
        c2d.width = expW; c2d.height = expH;
        const ctx = c2d.getContext("2d");
        const imgData = ctx.createImageData(expW, expH);
        const frameWebps = [];
        for (let i = 0; i < NUM_FRAMES; i++) {
          renderExportFrame(expW, expH, i, NUM_FRAMES, true, rawBuf, flipBuf);
          imgData.data.set(flipBuf);
          ctx.putImageData(imgData, 0, 0);
          const blob = await new Promise((res) => c2d.toBlob(res, "image/webp", 0.88));
          if (!blob) throw new Error(T().expWebpUnsup);
          frameWebps.push(new Uint8Array(await blob.arrayBuffer()));
          if (i % 3 === 0 || i === NUM_FRAMES - 1) {
            setExportProgress(T().expWebpEnc(i + 1, NUM_FRAMES), ((i + 1) / NUM_FRAMES) * 95);
            await new Promise((r) => setTimeout(r, 0));
          }
        }
        setExportProgress(T().expWebpMux, 98);
        const outBlob = muxAnimatedWebP(frameWebps, expW, expH, DUR_MS);
        const fname = buildExportFilename("webp");
        triggerDownload(outBlob, fname);
        setExportProgress(T().expDone(fname), 100);
      } else {
        // Pass 1: Sample 8 keyframes to build optimal shared 256-color Median-Cut palette
        setExportProgress(T().expGifPal, 5);
        await new Promise((r) => setTimeout(r, 0));
        const sampleFrames = [0, 10, 21, 31, 42, 52, 63, 73];
        const stepPx = 19;
        const sampleList = [];
        for (const sf of sampleFrames) {
          renderExportFrame(expW, expH, sf, NUM_FRAMES, false, rawBuf, flipBuf);
          for (let p = 0; p < expW * expH; p += stepPx) {
            const p4 = p * 4;
            sampleList.push(flipBuf[p4], flipBuf[p4 + 1], flipBuf[p4 + 2]);
          }
        }
        const gifPal = buildMedianCutPalette(new Uint8Array(sampleList));
        const lut = buildRgb555Lut(gifPal);
        const idxBuf = new Uint8Array(expW * expH);

        // GIF89a header + LSD + Global Color Table + Netscape 2.0 loop=0
        const chunks = [];
        const hdr = new Uint8Array(13 + 768 + 19);
        hdr.set([0x47,0x49,0x46,0x38,0x39,0x61], 0); // GIF89a
        hdr[6] = expW & 255; hdr[7] = (expW >>> 8) & 255;
        hdr[8] = expH & 255; hdr[9] = (expH >>> 8) & 255;
        hdr[10] = 0xF7; hdr[11] = 0; hdr[12] = 0; // GCT=1, 8-bit, 256 colors
        hdr.set(gifPal, 13);
        hdr.set([0x21,0xFF,0x0B, 0x4E,0x45,0x54,0x53,0x43,0x41,0x50,0x45,0x32,0x2E,0x30, 0x03,0x01, 0x00,0x00, 0x00], 13 + 768);
        chunks.push(hdr);

        const delayCs = Math.round(DUR_MS / 10); // 6 => 60ms
        const gce = new Uint8Array([0x21, 0xF9, 0x04, 0x04, delayCs & 255, (delayCs >>> 8) & 255, 0x00, 0x00]);
        const imgDesc = new Uint8Array([0x2C, 0, 0, 0, 0, expW & 255, (expW >>> 8) & 255, expH & 255, (expH >>> 8) & 255, 0x00]);

        for (let i = 0; i < NUM_FRAMES; i++) {
          renderExportFrame(expW, expH, i, NUM_FRAMES, false, rawBuf, flipBuf);
          quantizeFrameFS(flipBuf, expW, expH, gifPal, lut, idxBuf);
          chunks.push(gce, imgDesc, lzwEncodeGif(idxBuf));
          if (i % 2 === 0 || i === NUM_FRAMES - 1) {
            setExportProgress(T().expGifEnc(i + 1, NUM_FRAMES), 10 + ((i + 1) / NUM_FRAMES) * 88);
            await new Promise((r) => setTimeout(r, 0));
          }
        }
        chunks.push(new Uint8Array([0x3B])); // GIF trailer
        const outBlob = new Blob(chunks, { type: "image/gif" });
        const fname = buildExportFilename("gif");
        triggerDownload(outBlob, fname);
        setExportProgress(T().expDone(fname), 100);
      }
    } catch (err) {
      setExportProgress(T().expFail(err && err.message ? err.message : String(err)), 0);
    } finally {
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.deleteFramebuffer(fbo);
      gl.deleteTexture(tex);
      gl.viewport(0, 0, canvas.width, canvas.height);
      isExporting = false;
      btnExpWebp.disabled = false;
      btnExpGif.disabled = false;
      drawNow();
      ensureLoop();
    }
  }

  btnExpWebp.onclick = () => runOfflineExport("webp");
  btnExpGif.onclick = () => runOfflineExport("gif");
  btnCopyCfg.onclick = async () => {
    const snippet = JSON.stringify({
      material_preset: MAT_KEYS[materialPresetId],
      lighting_preset: LIT_KEYS[lightingPresetId],
      holo_pattern: HOLO_KEYS[holoPatternId],
      holo_gain: Number(holoGain.toFixed(2)),
    }, null, 2);
    try {
      await navigator.clipboard.writeText(snippet);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = snippet;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    copyCfgLbl.textContent = T().copied;
    setTimeout(() => { copyCfgLbl.textContent = T().copyCfg; }, 1800);
  };
  matChips.forEach((b) => {
    b.onclick = () => {
      materialPresetId = Number(b.dataset.mat);
      syncCraftChips();
      if (forcedPose || !rafId) drawNow();
    };
  });
  litChips.forEach((b) => {
    b.onclick = () => {
      lightingPresetId = Number(b.dataset.lit);
      syncCraftChips();
      if (forcedPose || !rafId) drawNow();
    };
  });
  holoChips.forEach((b) => {
    b.onclick = () => {
      holoPatternId = Number(b.dataset.holo);
      syncCraftChips();
      if (forcedPose || !rafId) drawNow();
    };
  });

  function syncHoloSlider() {
    const min = parseFloat(holoRange.min), max = parseFloat(holoRange.max);
    const pct = ((holoGain - min) / (max - min)) * 100;
    holoRange.style.setProperty("--pct", pct.toFixed(1) + "%");
    holoVal.textContent = Math.round(holoGain * 100) + "%";
  }
  syncHoloSlider();
  holoRange.oninput = (e) => {
    holoGain = parseFloat(e.target.value);
    syncHoloSlider();
    if (forcedPose || !rafId) drawNow();
  };

  window.addEventListener("keydown", (e) => {
    if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) return;
    if (e.code === "KeyH") {
      toggleZen();
    } else if (e.code === "Escape") {
      setCraftOpen(false);
    } else if (e.code === "Space") {
      e.preventDefault();
      toggleOrbit();
    } else if (e.code === "KeyR") {
      resetView();
    }
  });

  function handleOrient(e) {
    if (!gyroEnabled || e.gamma == null || e.beta == null) return;
    targetYaw = Math.max(-30.0, Math.min(30.0, e.gamma * 0.95));
    targetPitch = Math.max(-19.0, Math.min(19.0, (e.beta - 45) * 0.65));
    ensureLoop();
  }
  btnGyro.onclick = async () => {
    if (!gyroEnabled && typeof DeviceOrientationEvent !== "undefined" && typeof DeviceOrientationEvent.requestPermission === "function") {
      try {
        const res = await DeviceOrientationEvent.requestPermission();
        if (res !== "granted") return;
      } catch { return; }
    }
    gyroEnabled = !gyroEnabled;
    btnGyro.classList.toggle("active", gyroEnabled);
    if (gyroEnabled) {
      forcedPose = null;
      autoOrbit = false;
      btnOrbit.classList.remove("active");
      window.addEventListener("deviceorientation", handleOrient);
      ensureLoop();
    } else {
      window.removeEventListener("deviceorientation", handleOrient);
    }
  };

  window.__CARD_DEBUG__ = {
    ready: true,
    glOk: true,
    shaderError: null,
    setBgMode: (m) => applyBgMode(m),
    setLang: (l) => applyLang(l, false),
    setPresets: (opts = {}) => {
      if (opts.material !== undefined) {
        materialPresetId = typeof opts.material === "number" ? opts.material : (MAT_MAP[String(opts.material).toLowerCase()] ?? materialPresetId);
      }
      if (opts.lighting !== undefined) {
        lightingPresetId = typeof opts.lighting === "number" ? opts.lighting : (LIT_MAP[String(opts.lighting).toLowerCase()] ?? lightingPresetId);
      }
      if (opts.holo !== undefined) {
        holoPatternId = typeof opts.holo === "number" ? opts.holo : (HOLO_MAP[String(opts.holo).toLowerCase()] ?? holoPatternId);
      }
      syncCraftChips();
      if (forcedPose || !rafId) drawNow();
    },
    setZenMode: (v) => {
      const zen = !!v;
      document.body.classList.toggle("zen-mode", zen);
      iconEyeOpen.style.display = zen ? "none" : "";
      iconEyeClosed.style.display = zen ? "" : "none";
    },
    setAutoOrbit: (v) => {
      autoOrbit = !!v;
      forcedPose = null;
      manualHold = false;
      btnOrbit.classList.toggle("active", autoOrbit);
      if (autoOrbit) ensureLoop();
    },
    setPose: (yawDeg, pitchDeg, timeVal) => {
      autoOrbit = false;
      manualHold = false;
      btnOrbit.classList.remove("active");
      forcedPose = { yaw: yawDeg, pitch: pitchDeg, time: timeVal ?? (yawDeg / 24.0) };
      curYaw = yawDeg; curPitch = pitchDeg; timeAcc = forcedPose.time;
      targetYaw = yawDeg; targetPitch = pitchDeg;
      if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
      drawNow();
    },
    benchGpu: (frames = 20) => {
      const px = new Uint8Array(4);
      const t0 = performance.now();
      for (let i = 0; i < frames; i++) {
        curYaw = 30.0 * Math.sin(i * 0.25);
        curPitch = 19.0 * Math.sin(i * 0.5);
        timeAcc = i * 0.25;
        drawNow();
      }
      gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
      const elapsed = performance.now() - t0;
      return {
        avgGpuMs: +(elapsed / frames).toFixed(2),
        estMaxFps: +(frames * 1000 / Math.max(elapsed, 0.5)).toFixed(1),
        canvasW: canvas.width,
        canvasH: canvas.height,
      };
    },
    capturePng: (yawDeg, pitchDeg, timeVal) => {
      autoOrbit = false;
      manualHold = false;
      btnOrbit.classList.remove("active");
      forcedPose = { yaw: yawDeg, pitch: pitchDeg, time: timeVal ?? (yawDeg / 24.0) };
      curYaw = yawDeg; curPitch = pitchDeg; timeAcc = forcedPose.time;
      targetYaw = yawDeg; targetPitch = pitchDeg;
      if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
      drawNow();
      return canvas.toDataURL("image/png");
    },
    measureFps: (frames = 25) => new Promise((resolve) => {
      forcedPose = null;
      autoOrbit = true;
      manualHold = false;
      btnOrbit.classList.add("active");
      ensureLoop();
      let count = 0;
      let t0 = 0;
      function step(ts) {
        if (count === 0) t0 = ts;
        count++;
        if (count <= frames) {
          requestAnimationFrame(step);
        } else {
          const elapsed = Math.max(1, ts - t0);
          resolve({
            fps: +(frames * 1000 / elapsed).toFixed(1),
            avgMs: +(elapsed / frames).toFixed(2),
            canvasW: canvas.width,
            canvasH: canvas.height,
          });
        }
      }
      requestAnimationFrame(step);
    }),
  };

  drawNow();
  ensureLoop();
}

init().catch((err) => {
  window.__CARD_DEBUG__.shaderError = String(err);
  showError("初始化失败：" + err);
});
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Build standalone offline WebGL2 interactive 3D HTML card.")
    parser.add_argument("--workdir", required=True, type=Path, help="Project workspace directory")
    args = parser.parse_args()

    workdir = args.workdir.resolve()
    proc_dir = workdir / "03_processed"
    out_dir = workdir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = json.loads((proc_dir / "scene_meta.json").read_text(encoding="utf-8"))
    pal = dict(DEFAULT_PALETTE)
    pal.update(meta.get("palette", {}))
    meta["palette"] = pal

    bg_pil = Image.open(proc_dir / "master_bg.png").convert("RGB").resize((TEX_W, TEX_H), Image.Resampling.LANCZOS)
    bg_dof = Image.fromarray(cv2.GaussianBlur(np.array(bg_pil), (5, 5), 0.85), "RGB")

    mid_pil = Image.open(proc_dir / "master_mid.png").convert("RGBA").resize((TEX_W, TEX_H), Image.Resampling.LANCZOS)
    fg_pil = Image.open(proc_dir / "master_fg.png").convert("RGBA").resize((TEX_W, TEX_H), Image.Resampling.LANCZOS)
    fg_dof = premult_blur_u8(fg_pil, sigma=0.55)

    depth_f = np.array(Image.open(proc_dir / "depth_extrapolated.png").convert("L").resize((TEX_W, TEX_H), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0
    masks_f = np.array(Image.open(proc_dir / "masks_rgba.png").convert("RGBA").resize((TEX_W, TEX_H), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0
    mid_a = np.array(mid_pil)[..., 3].astype(np.float32) / 255.0

    dz_dx = cv2.Sobel(depth_f, cv2.CV_32F, 1, 0, ksize=5) / 8.0
    dz_dy = cv2.Sobel(depth_f, cv2.CV_32F, 0, 1, ksize=5) / 8.0
    nx = np.clip(-dz_dx * 2.1, -0.58, 0.58)
    ny = np.clip(-dz_dy * 2.1, -0.58, 0.58)
    nz = np.ones_like(nx)
    nlen = np.sqrt(nx ** 2 + ny ** 2 + nz ** 2)
    nx /= nlen
    ny /= nlen

    depth_norm_rgba = np.dstack([
        np.clip(depth_f * 255.0, 0, 255),
        np.clip(mid_a * 255.0, 0, 255),
        np.clip((nx * 0.5 + 0.5) * 255.0, 0, 255),
        np.clip((ny * 0.5 + 0.5) * 255.0, 0, 255),
    ]).astype(np.uint8)

    sh_blur = cv2.GaussianBlur(mid_a, (25, 25), 7.5)
    aux_rgba = np.dstack([
        np.clip(masks_f[..., 0] * 255.0, 0, 255),
        np.clip(masks_f[..., 1] * 255.0, 0, 255),
        np.clip(masks_f[..., 2] * 255.0, 0, 255),
        np.clip(sh_blur * 255.0, 0, 255),
    ]).astype(np.uint8)

    fg_emb = masks_f[..., 3]
    fx_n = -cv2.Sobel(fg_emb, cv2.CV_32F, 1, 0, ksize=5) * 0.45
    fy_n = -cv2.Sobel(fg_emb, cv2.CV_32F, 0, 1, ksize=5) * 0.45
    flen = np.sqrt(fx_n ** 2 + fy_n ** 2 + 1.0)
    fx_n /= flen
    fy_n /= flen
    fg_bevel_rgba = np.dstack([
        np.clip(fg_emb * 255.0, 0, 255),
        np.clip((fx_n * 0.5 + 0.5) * 255.0, 0, 255),
        np.clip((fy_n * 0.5 + 0.5) * 255.0, 0, 255),
        np.full_like(fg_emb, 255.0),
    ]).astype(np.uint8)

    prop_mask_path = proc_dir / "prop_mask.png"
    if prop_mask_path.exists() and (meta.get("prop_fx") or {}).get("enabled"):
        pm_pil = Image.open(prop_mask_path).convert("L").resize((TEX_W, TEX_H), Image.Resampling.LANCZOS)
    else:
        pm_pil = Image.new("L", (4, 4), 0)

    assets = {
        "bg": encode_webp_uri(bg_dof, quality=90),
        "mid": encode_webp_uri(mid_pil, quality=92),
        "fg": encode_webp_uri(fg_dof, quality=92),
        "depthNorm": encode_png_uri(Image.fromarray(depth_norm_rgba, "RGBA")),
        "aux": encode_webp_uri(Image.fromarray(aux_rgba, "RGBA"), quality=92),
        "fgBevel": encode_webp_uri(Image.fromarray(fg_bevel_rgba, "RGBA"), quality=90),
        "propMask": encode_png_uri(pm_pil),
    }

    title_esc = html.escape(str(meta.get("title", "3D 全息流麻收藏卡")))
    badge_esc = html.escape(str(meta.get("badge", "SAR / UR")))
    subtitle_esc = html.escape(str(meta.get("subtitle", "3D 交互全息流麻卡")))
    studio_esc = html.escape(str(meta.get("studio_bg_label", "主题棚拍")))
    accent_str = str(pal.get("ui_accent", "#ffd97d")).strip()
    if not (accent_str.startswith("#") and len(accent_str) in (4, 7)):
        accent_str = "#ffd97d"
    hex_raw = accent_str[1:]
    if len(hex_raw) == 3:
        hex_raw = "".join(c * 2 for c in hex_raw)
    try:
        ar, ag, ab = int(hex_raw[0:2], 16), int(hex_raw[2:4], 16), int(hex_raw[4:6], 16)
        acc_rgb = f"{ar}, {ag}, {ab}"
        # Deepened accent for crisp contrast on light gallery frosted dock
        luma = 0.299 * ar + 0.587 * ag + 0.114 * ab
        darken = min(1.0, 128.0 / max(luma, 1.0)) if luma > 128.0 else 1.0
        acc_deep = f"#{int(ar * darken):02x}{int(ag * darken):02x}{int(ab * darken):02x}"
    except ValueError:
        accent_str = "#ffd97d"
        acc_rgb = "255, 217, 125"
        acc_deep = "#9c741a"
    studio_rgb_raw = meta.get("studio_color_rgb", [24, 38, 66])
    studio_rgb = f"{int(studio_rgb_raw[0])}, {int(studio_rgb_raw[1])}, {int(studio_rgb_raw[2])}"

    meta_json = json.dumps(meta, ensure_ascii=False).replace("</", "<\\/")
    assets_json = json.dumps(assets).replace("</", "<\\/")

    label_mode = str(meta.get("label_mode", "page_only")).lower().strip()
    badge_style = ' style="display:none"' if label_mode == "hidden" else ""

    html_out = (
        HTML_TEMPLATE
        .replace("__TITLE__", title_esc)
        .replace("__BADGE__", badge_esc)
        .replace("__BADGE_STYLE__", badge_style)
        .replace("__SUBTITLE__", subtitle_esc)
        .replace("__STUDIO_BG_LABEL__", studio_esc)
        .replace("__UI_ACCENT_RGB__", acc_rgb)
        .replace("__UI_ACCENT_DEEP__", acc_deep)
        .replace("__UI_ACCENT__", accent_str)
        .replace("__STUDIO_RGB__", studio_rgb)
        .replace("__META_JSON__", meta_json)
        .replace("__ASSETS_JSON__", assets_json)
    )
    out_path = out_dir / "holographic_card.html"
    out_path.write_text(html_out, encoding="utf-8")
    print(f"Saved {out_path} ({out_path.stat().st_size / 1024 / 1024:.2f} MB)")


if __name__ == "__main__":
    main()
