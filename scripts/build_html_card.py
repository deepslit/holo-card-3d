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
    --border: rgba(185, 218, 255, 0.24);
    --text: #eef5ff;
    --accent: __UI_ACCENT__;
  }
  * { box-sizing: border-box; user-select: none; -webkit-user-select: none; }
  html, body {
    margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden;
    background: #070d1c; color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  }
  #glcanvas {
    position: fixed; inset: 0; width: 100%; height: 100%; display: block;
    touch-action: none; cursor: grab;
  }
  #glcanvas:active { cursor: grabbing; }
  .badge {
    position: fixed; top: 16px; left: 18px; z-index: 10;
    padding: 8px 14px; border-radius: 999px;
    background: rgba(10, 17, 36, 0.82); border: 1px solid var(--border);
    font-size: 12px; letter-spacing: 0.04em; color: #dbe9ff;
    pointer-events: none; display: flex; align-items: center; gap: 8px;
  }
  .badge strong { color: var(--accent); font-weight: 600; }
  .controls {
    position: fixed; bottom: 18px; left: 50%; transform: translateX(-50%); z-index: 10;
    display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 8px;
    padding: 9px 14px; border-radius: 16px; max-width: calc(100vw - 24px);
    background: rgba(10, 17, 36, 0.84); border: 1px solid var(--border);
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.38);
  }
  .btn {
    appearance: none; border: 1px solid rgba(255,255,255,0.16);
    background: rgba(255,255,255,0.08); color: var(--text);
    padding: 6px 11px; border-radius: 10px; font-size: 12px; font-weight: 500;
    cursor: pointer; transition: all 0.16s ease; white-space: nowrap;
  }
  .btn:hover { background: rgba(255,255,255,0.16); border-color: rgba(255,217,125,0.45); }
  .btn.active {
    background: linear-gradient(135deg, rgba(255,215,120,0.28), rgba(100,190,255,0.26));
    border-color: var(--accent); color: #fff6d8;
  }
  .slider-wrap {
    display: flex; align-items: center; gap: 7px; padding: 0 6px;
    font-size: 12px; color: #cfe0ff;
  }
  input[type="range"] { width: 82px; accent-color: var(--accent); cursor: pointer; }
  #errBanner {
    display: none; position: fixed; inset: 0; z-index: 30;
    align-items: center; justify-content: center; padding: 24px;
    background: rgba(7, 11, 22, 0.92); color: #ffb4b4; text-align: center;
  }
</style>
</head>
<body>
<canvas id="glcanvas"></canvas>
<div class="badge" id="badge">
  <strong>__BADGE__</strong>
  <span>__TITLE__ · __SUBTITLE__</span>
</div>
<div class="controls" id="controls">
  <button class="btn active" id="btnOrbit">自动巡航</button>
  <button class="btn" id="btnGyro">陀螺仪</button>
  <button class="btn" id="btnReset">归零 0°</button>
  <button class="btn" id="btnBg">背景: __STUDIO_BG_LABEL__</button>
  <button class="btn" id="btnQual">画质: 流畅</button>
  <label class="slider-wrap">
    <span>闪度</span>
    <input type="range" id="holoRange" min="0.2" max="1.6" step="0.05" value="1.05">
  </label>
</div>
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
uniform int u_holoPattern;
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

  vec2 radNorm = pxBase / (u_res * 0.55);
  float vig = clamp(1.0 - 0.52 * pow(length(radNorm), 1.45), 0.15, 1.0);
  vec3 bgStudio = clamp(u_studioCol * (0.65 + 0.85 * vig) + (u_auraCol * 0.06) * vig, 0.0, 1.0);
  vec3 backdrop = u_bgMode == 0 ? bgStudio : (u_bgMode == 1 ? vec3(0.02, 0.025, 0.04) : vec3(0.91, 0.93, 0.96));

  float shCy = 0.5 * ch + 0.095 * cw;
  float hoverScale = 1.0 - 0.14 * (-u_hoverY / max(0.013 * u_res.y, 1.0));
  vec2 shRad = vec2(cw * 0.44 * hoverScale, 0.056 * cw * hoverScale);
  vec2 shDelta = vec2(pxBase.x + u_yaw * (cw / 510.0) * 1.4, pxBase.y - shCy) / shRad;
  float groundSh = exp(-dot(shDelta, shDelta) * 1.4) * (u_bgMode == 2 ? 0.30 : 0.48);

  vec2 auraDelta = vec2(pxBase.x / (cw * 0.68), (pxBase.y - u_hoverY) / (ch * 0.64));
  float auraPulse = 0.65 + 0.35 * sin(2.0 * u_time);
  float aura = exp(-dot(auraDelta, auraDelta) / 0.85) * 0.38 * auraPulse;
  vec3 auraCol = u_auraCol * aura * (u_bgMode == 2 ? 0.35 : 1.0);

  vec3 canvasCol = backdrop * (1.0 - groundSh) + auraCol;

  for (int bi = 0; bi < 10; bi++) {
    float fi = float(bi);
    vec2 bp = vec2(hash12(vec2(fi, 1.1)), hash12(vec2(fi, 2.3))) * 0.86 + 0.07;
    bp.x += 0.014 * sin(u_time + fi * 1.7) - u_yaw * 0.0020;
    bp.y += 0.018 * cos(u_time + fi * 2.1) - u_pitch * 0.0016;
    vec2 bPos = (bp - 0.5) * u_res;
    float br = (1.8 + 2.2 * hash12(vec2(fi, 3.7))) * (cw / 510.0);
    vec2 d = pxBase - bPos;
    if (abs(d.x) < br * 3.0 && abs(d.y) < br * 3.0) {
      float g = exp(-dot(d, d) / (2.0 * br * br)) * 0.54;
      vec3 bCol = hash12(vec2(fi, 4.9)) > 0.45 ? u_partCol1 : u_partCol2;
      canvasCol += g * bCol * (u_bgMode == 2 ? 0.25 : 1.0);
    }
  }

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

    float edgeAlpha = 0.0;
    vec3 edgeCol = vec3(0.0);
    if (frontMask < 0.995) {
      float thickness = 0.036 * cw;
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
          edgeCol = (u_edgeBase * (0.45 + 0.65 * ndotlE) + u_edgeSpec * 0.85 * pow(ndothE, 18.0)) * grain * (1.0 - 0.28 * edgeHitS);
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
            float diffGain = 0.90 + 0.16 * halfLambert;
            float ndoth = clamp(dot(mNorm, hLoc), 0.0, 1.0);
            float ndotv = clamp(dot(mNorm, vLoc), 0.0, 1.0);

            float metalSpec = pow(ndoth, 28.0) * mMetal * 0.78;
            float metalBrushed = (0.5 + 0.5 * sin((um.x * 95.0 - um.y * 35.0) * PI + u_yaw * 0.1)) * mMetal * 0.14;
            float sarEmboss = clamp(0.42 + 0.58 * dot(mNxy, lightLoc.xy), 0.0, 1.0) * mSarB * 0.26;
            float fresnel = pow(1.0 - ndotv, 3.2) * 0.22;
            vec3 pearlRim = spectral(um.x + um.y + 0.015 * u_yaw) * fresnel * 0.55;

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

            mLit = midTex.rgb * diffGain
                 + u_metalTint * (metalSpec + metalBrushed)
                 + vec3(sarEmboss)
                 + pearlRim
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

        vec2 dAstro = (ubOs - u_astroCenter) * vec2(1.0, ch / cw);
        float angA = atan(dAstro.y, dAstro.x);
        float radA = length(dAstro);
        float carrier;
        if (u_holoPattern == 1) {
          carrier = 0.5 + 0.5 * cos((ubOs.x * 36.0 + ubOs.y * 48.0) * PI + u_yaw * 0.09) * cos((ubOs.x * 36.0 - ubOs.y * 48.0) * PI - u_pitch * 0.08);
        } else if (u_holoPattern == 2) {
          carrier = 0.5 + 0.5 * sin(radA * 20.0 - angA * 6.0 + u_yaw * 0.10);
        } else {
          carrier = 0.5 + 0.5 * cos(angA * 24.0 + u_yaw * 0.08);
        }
        float microGrating = 0.5 + 0.5 * sin((ubOs.x * 110.0 + ubOs.y * 145.0) * PI + u_yaw * 0.14);
        float tiltShift = 0.016 * u_yaw + 0.012 * u_pitch;
        vec3 spec1 = spectral(ubOs.x * 1.45 + ubOs.y * 0.95 + tiltShift * 1.4 + 0.08 * carrier);
        vec3 spec2 = spectral(radA * 2.1 - tiltShift * 1.1 + 0.12 * microGrating);
        vec3 holoComb = 0.58 * spec1 + 0.42 * spec2;
        float holoStr = rHoloMask * (0.20 + 0.24 * carrier * (0.5 + 0.5 * microGrating)) * u_holoGain;
        vec3 bgLit = bgCol + holoComb * holoStr * 0.55;

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
        vec2 us2 = planeUV(-0.036 * cw, oLoc, dLoc, cw, ch);
        vec2 grav = vec2(0.025 * sin(radians(u_yaw)), 0.020 * sin(radians(u_pitch)));
        float f1 = sin((us1.x + grav.x) * 18.0 + us1.y * 9.0 + u_time) * cos((us1.y + grav.y) * 14.0 - us1.x * 7.0 - u_time);
        float silk1 = pow(clamp(0.5 + 0.5 * f1, 0.0, 1.0), 3.2) * (0.4 + 0.6 * rHoloMask);
        float f2 = sin((us2.x - grav.x * 1.3) * 24.0 - us2.y * 13.0 - 2.0 * u_time) * cos((us2.y + grav.y * 1.2) * 19.0 + us2.x * 11.0 + u_time);
        float silk2 = pow(clamp(0.5 + 0.5 * f2, 0.0, 1.0), 3.6) * (0.35 + 0.65 * rHoloMask);
        vec3 sandStreams = (silk1 * u_sandCol1 * 0.24 + silk2 * u_sandCol2 * 0.22) * u_holoGain;

        vec3 seq = evalQuicksandSequins(us1, vec2(15.0, 19.0), lightDir, halfCam, u_time);
        bgWithSand = bgLit + sandStreams + seq * 0.85 * u_holoGain;

        vec2 shBase = us1 + lightLoc.xy * 0.042 * vec2(1.0, cw / ch);
        float inSh = step(0.0, shBase.x) * step(shBase.x, 1.0) * step(0.0, shBase.y) * step(shBase.y, 1.0);
        float shBlur = texture(u_aux, clamp(shBase, 0.0, 1.0)).a * inSh;
        bgWithSand *= (1.0 - 0.44 * shBlur);
      }

      cardCol = mix(bgWithSand, clamp(mLit, 0.0, 1.0), mA);
      cardCol = mix(cardCol, fgAccCol, fgAccA);

      float sweepU = 0.62 + 0.78 * sin(u_time);
      float bandD = (ug.x * 0.72 + ug.y * 0.52) - sweepU;
      float glassBand = exp(-(bandD * bandD) / 0.0085) * 0.11 + exp(-(bandD * bandD) / 0.0009) * 0.13;
      vec2 spotC = vec2(0.5 + 0.28 * sin(u_time), 0.44 + 0.22 * cos(2.0 * u_time));
      vec2 spotD = (ug - spotC) * vec2(1.0, ch / cw);
      float spotlight = exp(-dot(spotD, spotD) / 0.16) * 0.08;
      float bevelRim = smoothstep(-4.5, -0.5, sd0) * (0.09 + 0.20 * max(0.0, sin(u_time) * (ug.x - 0.5) * 2.0 + 0.5));
      vec3 sheenCol = vec3(0.92, 0.96, 1.0) * (glassBand + spotlight + bevelRim);
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
      canvasCol = mix(canvasCol, clamp(totalCardCol, 0.0, 1.0), totalCardA);

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
            canvasCol += ring * u_propTint + clamp(needleH + needleV + pinhole * 0.65, 0.0, 0.92) * flareTint * flareEnv * 0.94;
          }
        }
      }
    }
  }

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
        canvasCol = mix(canvasCol, mRes.rgb, mRes.a * faceSafe * 0.90);
      }
    }
  } else {
    for (int fi_i = 0; fi_i < 8; fi_i++) {
      float fi = float(fi_i);
      vec2 fp = vec2(hash12(vec2(fi, 8.1)), hash12(vec2(fi, 9.3))) * 0.88 + 0.06;
      fp.x += 0.018 * sin(u_time + fi * 2.3) + u_yaw * 0.0055;
      fp.y += 0.022 * cos(u_time + fi * 1.9) + u_pitch * 0.0045;
      vec2 fPos = (fp - 0.5) * u_res;
      float fr = (3.0 + 3.2 * hash12(vec2(fi, 7.7))) * (cw / 510.0);
      vec2 d = pxBase - fPos;
      if (abs(d.x) < fr * 3.0 && abs(d.y) < fr * 3.0) {
        float g = exp(-dot(d, d) / (2.0 * fr * fr)) * 0.42;
        vec3 fCol = hash12(vec2(fi, 5.5)) > 0.45 ? u_partCol1 : u_partCol2;
        canvasCol += g * fCol * (u_bgMode == 2 ? 0.28 : 1.0);
      }
    }
  }

  fragColor = vec4(clamp(canvasCol, 0.0, 1.0), 1.0);
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
   "u_bgMode","u_holoPattern","u_studioCol","u_astroCenter","u_R","u_RT","u_glints","u_glintCount",
   "u_edgeBase","u_edgeSpec","u_metalTint","u_auraCol","u_sandCol1","u_sandCol2","u_seqCols","u_partCol1","u_partCol2",
   "u_propEnabled","u_propStart","u_propTip","u_propTint","u_propGain","u_motifKind","u_faceLock"].forEach((n) => {
    loc[n] = gl.getUniformLocation(prog, n);
  });

  const pal = META.palette || {};
  const holoPatternId = META.holo_pattern === "prism_grid" ? 1 : (META.holo_pattern === "cosmos_waves" ? 2 : 0);
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

  function rotMats(yawDeg, pitchDeg, rollDeg) {
    const ry = yawDeg * Math.PI / 180, rx = pitchDeg * Math.PI / 180, rz = rollDeg * Math.PI / 180;
    const cy = Math.cos(ry), sy = Math.sin(ry);
    const cx = Math.cos(rx), sx = Math.sin(rx);
    const cz = Math.cos(rz), sz = Math.sin(rz);
    const r00 = cz*cy - sz*sx*sy, r01 = -sz*cx, r02 = cz*sy + sz*sx*cy;
    const r10 = sz*cy + cz*sx*sy, r11 =  cz*cx, r12 = sz*sy - cz*sx*cy;
    const r20 = -cx*sy,           r21 =  sx,    r22 = cx*cy;
    return {
      R:  new Float32Array([r00,r10,r20, r01,r11,r21, r02,r12,r22]),
      RT: new Float32Array([r00,r01,r02, r10,r11,r12, r20,r21,r22]),
    };
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
  resize();

  function setVec3(u, v, fb) {
    const c = v || fb;
    gl.uniform3f(u, c[0], c[1], c[2]);
  }

  function drawNow() {
    const yawNorm = Math.max(-1.0, Math.min(1.0, curYaw / 24.0));
    const roll = 1.6 * yawNorm;
    const hoverY = -0.013 * canvas.height * yawNorm;
    const cw = Math.min(canvas.width * 0.67, canvas.height * 0.67 * 0.75);
    const ch = cw * (4.0 / 3.0);
    const dCam = 3.8 * cw;
    const { R, RT } = rotMats(curYaw, curPitch, roll);

    gl.useProgram(prog);
    gl.uniform2f(loc.u_res, canvas.width, canvas.height);
    gl.uniform2f(loc.u_cardSize, cw, ch);
    gl.uniform1f(loc.u_dCam, dCam);
    gl.uniform1f(loc.u_time, timeAcc);
    gl.uniform1f(loc.u_yaw, curYaw);
    gl.uniform1f(loc.u_pitch, curPitch);
    gl.uniform1f(loc.u_hoverY, hoverY);
    gl.uniform1f(loc.u_holoGain, holoGain);
    gl.uniform1i(loc.u_bgMode, bgMode);
    gl.uniform1i(loc.u_holoPattern, holoPatternId);
    gl.uniform3f(loc.u_studioCol, META.studio_color_rgb[0]/255, META.studio_color_rgb[1]/255, META.studio_color_rgb[2]/255);
    gl.uniform2f(loc.u_astroCenter, META.astrolabe_center[0], META.astrolabe_center[1]);
    gl.uniformMatrix3fv(loc.u_R, false, R);
    gl.uniformMatrix3fv(loc.u_RT, false, RT);
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

    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  function ensureLoop() {
    if (!rafId) {
      lastTs = performance.now();
      rafId = requestAnimationFrame(renderFrame);
    }
  }

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
    if (!settled) {
      rafId = requestAnimationFrame(renderFrame);
    }
  }

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
    updateFromPointer(e.clientX, e.clientY);
    ensureLoop();
  });
  canvas.addEventListener("pointerleave", () => { manualHold = false; ensureLoop(); });
  canvas.addEventListener("pointerdown", (e) => {
    forcedPose = null;
    manualHold = true;
    updateFromPointer(e.clientX, e.clientY);
    ensureLoop();
  });
  window.addEventListener("pointerup", () => {
    if (autoOrbit) manualHold = false;
  });

  const btnOrbit = document.getElementById("btnOrbit");
  const btnGyro = document.getElementById("btnGyro");
  const btnReset = document.getElementById("btnReset");
  const btnBg = document.getElementById("btnBg");
  const btnQual = document.getElementById("btnQual");
  const holoRange = document.getElementById("holoRange");

  btnOrbit.onclick = () => {
    forcedPose = null;
    autoOrbit = !autoOrbit;
    manualHold = false;
    btnOrbit.classList.toggle("active", autoOrbit);
    ensureLoop();
  };
  btnReset.onclick = () => {
    forcedPose = null;
    autoOrbit = false;
    manualHold = false;
    btnOrbit.classList.remove("active");
    targetYaw = 0; targetPitch = 0;
    ensureLoop();
  };
  const bgNames = [META.studio_bg_label || "主题棚拍", "暗夜纯黑", "画廊亮白"];
  btnBg.onclick = () => {
    bgMode = (bgMode + 1) % 3;
    btnBg.textContent = "背景: " + bgNames[bgMode];
    if (forcedPose || !rafId) drawNow();
  };
  btnQual.onclick = () => {
    highQual = !highQual;
    btnQual.textContent = highQual ? "画质: 高清" : "画质: 流畅";
    btnQual.classList.toggle("active", highQual);
    resize();
    if (forcedPose || !rafId) drawNow();
  };
  holoRange.oninput = (e) => {
    holoGain = parseFloat(e.target.value);
    if (forcedPose || !rafId) drawNow();
  };

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
      curYaw = yawDeg; curPitch = pitchDeg;
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
      curYaw = yawDeg; curPitch = pitchDeg;
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
    subtitle_esc = html.escape(str(meta.get("subtitle", "3D 交互全息流麻卡（悬停/拖拽/陀螺仪倾摆）")))
    studio_esc = html.escape(str(meta.get("studio_bg_label", "主题棚拍")))
    accent_str = str(pal.get("ui_accent", "#ffd97d"))
    if not (accent_str.startswith("#") and len(accent_str) in (4, 7)):
        accent_str = "#ffd97d"

    meta_json = json.dumps(meta, ensure_ascii=False).replace("</", "<\\/")
    assets_json = json.dumps(assets).replace("</", "<\\/")

    html_out = (
        HTML_TEMPLATE
        .replace("__TITLE__", title_esc)
        .replace("__BADGE__", badge_esc)
        .replace("__SUBTITLE__", subtitle_esc)
        .replace("__STUDIO_BG_LABEL__", studio_esc)
        .replace("__UI_ACCENT__", accent_str)
        .replace("__META_JSON__", meta_json)
        .replace("__ASSETS_JSON__", assets_json)
    )
    out_path = out_dir / "holographic_card.html"
    out_path.write_text(html_out, encoding="utf-8")
    print(f"Saved {out_path} ({out_path.stat().st_size / 1024 / 1024:.2f} MB)")


if __name__ == "__main__":
    main()
