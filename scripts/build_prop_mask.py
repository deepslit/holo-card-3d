"""UV grid helper and pixel-exact 1200x1600 prop_mask.png generator for v2.1 holo-card-3d."""
import argparse
import json
import sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MASTER_W, MASTER_H = 1200, 1600


def _rasterize_polys(polys_uv: list[list[list[float]]], w: int = MASTER_W, h: int = MASTER_H) -> np.ndarray:
    im = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(im)
    for poly in polys_uv:
        if len(poly) >= 3:
            pts = [(round(float(u) * w), round(float(v) * h)) for u, v in poly]
            d.polygon(pts, fill=255)
    return np.array(im, dtype=np.float32) / 255.0


def _dilate_bool(mask_bool: np.ndarray, radius: int = 2) -> np.ndarray:
    if radius <= 0 or not np.any(mask_bool):
        return mask_bool
    k = radius * 2 + 1
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    return cv2.dilate(mask_bool.astype(np.uint8), ker) > 0


def export_uv_grid(mid_path: Path, out_path: Path, crop_uv: list[float] | None = None) -> Path:
    rgba = np.array(Image.open(mid_path).convert("RGBA").resize((MASTER_W, MASTER_H), Image.Resampling.LANCZOS))
    a = rgba[..., 3:4].astype(np.float32) / 255.0
    bg = np.full((MASTER_H, MASTER_W, 3), np.array([15.0, 19.0, 29.0], dtype=np.float32))
    rgb = (rgba[..., :3].astype(np.float32) * a + bg * (1.0 - a)).astype(np.uint8)
    im = Image.fromarray(rgb, "RGB")
    d = ImageDraw.Draw(im)

    font = ImageFont.load_default()
    step = 0.05
    for idx in range(1, 20):
        uv = idx * step
        is_major = (idx % 2 == 0)
        x = round(uv * MASTER_W)
        y = round(uv * MASTER_H)
        col_line = (60, 225, 255) if is_major else (42, 130, 165)
        w_line = 2 if is_major else 1
        d.line([(x, 0), (x, MASTER_H)], fill=col_line, width=w_line)
        d.line([(0, y), (MASTER_W, y)], fill=col_line, width=w_line)
        if is_major or crop_uv is not None:
            d.rectangle([x + 3, 4, x + 42, 20], fill=(12, 16, 26))
            d.text((x + 5, 5), f"{uv:.2f}", fill=(255, 230, 110), font=font)
            d.rectangle([4, y + 3, 44, y + 19], fill=(12, 16, 26))
            d.text((6, y + 4), f"{uv:.2f}", fill=(255, 230, 110), font=font)

    if crop_uv is not None:
        x0, y0, x1, y1 = [float(v) for v in crop_uv]
        px0, py0 = max(0, int(round(x0 * MASTER_W))), max(0, int(round(y0 * MASTER_H)))
        px1, py1 = min(MASTER_W, int(round(x1 * MASTER_W))), min(MASTER_H, int(round(y1 * MASTER_H)))
        if px1 > px0 + 8 and py1 > py0 + 8:
            im = im.crop((px0, py0, px1, py1))
            scale = max(1, min(1400 // im.width, 1600 // im.height))
            if scale > 1:
                im = im.resize((im.width * scale, im.height * scale), Image.Resampling.NEAREST)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    im.save(out_path, format="PNG", optimize=True)
    print(f"[prop-grid] Wrote {out_path} ({im.width}x{im.height})")
    return out_path


def build_prop_mask_for_workdir(workdir: Path, cfg: dict | None = None) -> tuple[Path, Path, float]:
    proc_dir = workdir / "03_processed"
    raw_dir = workdir / "01_raw_layers"
    if cfg is None:
        cfg_path = workdir / "card_config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}

    mid_path = proc_dir / "master_mid.png"
    if not mid_path.exists():
        raise FileNotFoundError(f"Missing {mid_path}; run --stage prepare first.")

    mid_pil = Image.open(mid_path).convert("RGBA").resize((MASTER_W, MASTER_H), Image.Resampling.LANCZOS)
    rgba = np.array(mid_pil)
    prop_cfg = cfg.get("prop_fx") or {}

    mask_out = proc_dir / "prop_mask.png"
    qa_out = proc_dir / "prop_mask_qa.png"

    # Honor explicit user-supplied grayscale mask in 01_raw_layers/prop_mask.png if present & no polygons given
    raw_mask_cand = None
    for ext in (".png", ".webp", ".jpg"):
        p = raw_dir / f"prop_mask{ext}"
        if p.exists():
            raw_mask_cand = p
            break

    polys = prop_cfg.get("mask_polygons") or []
    if not polys and raw_mask_cand is not None:
        m_u8 = np.array(Image.open(raw_mask_cand).convert("L").resize((MASTER_W, MASTER_H), Image.Resampling.LANCZOS))
        Image.fromarray(m_u8, "L").save(mask_out, format="PNG", optimize=True)
    elif polys:
        pm = _rasterize_polys(polys)
        excl_polys = prop_cfg.get("exclude_polygons") or []
        excl_factor = np.ones((MASTER_H, MASTER_W), dtype=np.float32)
        if excl_polys:
            hz = _rasterize_polys(excl_polys) > 0.5
            skin_only = bool(prop_cfg.get("exclude_skin_in_exclude_zones", True))
            if skin_only:
                r, g, b = [rgba[..., i].astype(np.float32) for i in range(3)]
                skin = (r > 165) & (g > 110) & (r > g + 6) & (r > b + 8)
                excl = _dilate_bool(skin & hz, radius=2)
            else:
                excl = hz
            excl_factor = 1.0 - excl.astype(np.float32)

        alpha_m = np.clip((rgba[..., 3].astype(np.float32) - 20.0) / 100.0, 0.0, 1.0)
        sigma = float(prop_cfg.get("feather_sigma", 1.6))
        raw = pm * excl_factor * alpha_m
        im_m = Image.fromarray(np.clip(raw * 255.0, 0, 255).astype(np.uint8), "L")
        if sigma > 0.1:
            im_m = im_m.filter(ImageFilter.GaussianBlur(radius=sigma))
        m_u8 = np.array(im_m, dtype=np.uint8)
        Image.fromarray(m_u8, "L").save(mask_out, format="PNG", optimize=True)
    else:
        m_u8 = np.zeros((MASTER_H, MASTER_W), dtype=np.uint8)
        Image.fromarray(m_u8, "L").save(mask_out, format="PNG", optimize=True)

    pct = float((m_u8 > 20).mean() * 100.0)

    # Render side-by-side QA image: full card mask overlay + auto-zoomed prop bounding crop
    a_f = rgba[..., 3:4].astype(np.float32) / 255.0
    bg_dark = np.full((MASTER_H, MASTER_W, 3), np.array([14.0, 18.0, 28.0], dtype=np.float32))
    rgb = rgba[..., :3].astype(np.float32) * a_f + bg_dark * (1.0 - a_f)
    m_f = m_u8.astype(np.float32) / 255.0
    vis = rgb * (1.0 - 0.50 * m_f[..., None]) + np.array([45.0, 240.0, 255.0]) * (0.50 * m_f[..., None])
    edge = np.clip(np.abs(np.gradient(m_f, axis=0)) + np.abs(np.gradient(m_f, axis=1)), 0.0, 1.0)
    edge_b = np.clip(edge * 4.2, 0.0, 1.0)
    vis = vis * (1.0 - 0.78 * edge_b[..., None]) + np.array([255.0, 48.0, 96.0]) * (0.78 * edge_b[..., None])

    full_im = Image.fromarray(np.clip(vis, 0, 255).astype(np.uint8), "RGB")
    start_uv = prop_cfg.get("start_uv")
    tip_uv = prop_cfg.get("tip_uv")
    d_full = ImageDraw.Draw(full_im)
    if start_uv and tip_uv:
        sx, sy = round(float(start_uv[0]) * MASTER_W), round(float(start_uv[1]) * MASTER_H)
        tx, ty = round(float(tip_uv[0]) * MASTER_W), round(float(tip_uv[1]) * MASTER_H)
        d_full.line([(sx, sy), (tx, ty)], fill=(255, 224, 90), width=4)
        d_full.ellipse([sx - 10, sy - 10, sx + 10, sy + 10], fill=(80, 255, 140), outline=(10, 14, 24), width=2)
        d_full.ellipse([tx - 12, ty - 12, tx + 12, ty + 12], fill=(255, 215, 70), outline=(255, 70, 90), width=3)

    ys, xs = np.where(m_u8 > 20)
    if len(xs) > 0:
        x0 = max(0, int(xs.min()) - 90)
        y0 = max(0, int(ys.min()) - 90)
        x1 = min(MASTER_W, int(xs.max()) + 90)
        y1 = min(MASTER_H, int(ys.max()) + 90)
        crop = full_im.crop((x0, y0, x1, y1))
    else:
        crop = full_im.copy()

    pw, ph = 600, 800
    left_panel = full_im.resize((pw, ph), Image.Resampling.LANCZOS)
    right_panel = Image.new("RGB", (pw, ph), (12, 16, 24))
    sc = min(pw / max(1, crop.width), ph / max(1, crop.height))
    rw, rh = max(1, round(crop.width * sc)), max(1, round(crop.height * sc))
    right_panel.paste(crop.resize((rw, rh), Image.Resampling.LANCZOS), ((pw - rw) // 2, (ph - rh) // 2))

    sheet = Image.new("RGB", (pw * 2, ph), (10, 14, 22))
    sheet.paste(left_panel, (0, 0))
    sheet.paste(right_panel, (pw, 0))
    sheet.save(qa_out, format="PNG", optimize=True)
    print(f"[prop-mask] Wrote {mask_out} ({pct:.2f}% active) + QA sheet {qa_out}")
    return mask_out, qa_out, pct


def main():
    parser = argparse.ArgumentParser(description="Export UV coordinate grid or build 1200x1600 prop_mask.png.")
    parser.add_argument("--workdir", required=True, type=Path, help="Project workspace directory")
    parser.add_argument("--grid", action="store_true", help="Render 03_processed/uv_grid_mid.png with 0.05 UV rulers")
    parser.add_argument("--crop", nargs=4, type=float, metavar=("U0", "V0", "U1", "V1"), help="Optional zoomed UV region")
    args = parser.parse_args()

    workdir = args.workdir.resolve()
    proc_dir = workdir / "03_processed"
    raw_dir = workdir / "01_raw_layers"
    mat_dir = workdir / "02_matted"

    if args.grid:
        mid_src = proc_dir / "master_mid.png"
        if not mid_src.exists():
            mid_src = mat_dir / "mid_rgba.png"
        if not mid_src.exists():
            for ext in (".png", ".webp", ".jpg"):
                c = raw_dir / f"mid{ext}"
                if c.exists():
                    mid_src = c
                    break
        if not mid_src.exists():
            raise FileNotFoundError(f"No mid layer found under {workdir}")
        out_name = "uv_grid_crop.png" if args.crop else "uv_grid_mid.png"
        export_uv_grid(mid_src, proc_dir / out_name, crop_uv=args.crop)
    else:
        build_prop_mask_for_workdir(workdir)


if __name__ == "__main__":
    main()
