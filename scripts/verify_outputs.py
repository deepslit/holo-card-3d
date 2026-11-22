"""Stage 5: Verify frozen-standard 3-deliverable bundle (HTML, animated RGBA WebP, GIF)."""
import argparse
import json
import sys
from pathlib import Path
from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UNREPLACED_TOKENS = (
    "__TITLE__",
    "__BADGE__",
    "__BADGE_STYLE__",
    "__SUBTITLE__",
    "__STUDIO_BG_LABEL__",
    "__UI_ACCENT__",
    "__META_JSON__",
    "__ASSETS_JSON__",
)


def check_html(html_path: Path) -> dict:
    if not html_path.exists():
        return {"ok": False, "error": f"Missing {html_path}"}
    size = html_path.stat().st_size
    text = html_path.read_text(encoding="utf-8", errors="replace")
    has_webgl2 = "webgl2" in text
    has_debug = "__CARD_DEBUG__" in text
    leftover = [tok for tok in UNREPLACED_TOKENS if tok in text]
    ok = size > 100 * 1024 and has_webgl2 and has_debug and not leftover
    return {
        "ok": ok,
        "bytes": size,
        "mb": round(size / (1024 * 1024), 2),
        "has_webgl2": has_webgl2,
        "has_debug": has_debug,
        "leftover_tokens": leftover,
    }


def check_webp(webp_path: Path, expected_frames: int, expected_dur: int) -> dict:
    if not webp_path.exists():
        return {"ok": False, "error": f"Missing {webp_path}"}
    size = webp_path.stat().st_size
    data = webp_path.read_bytes()
    pos, chunks = 12, []
    while pos + 8 <= len(data):
        cid = data[pos:pos + 4].decode("ascii", "replace")
        csz = int.from_bytes(data[pos + 4:pos + 8], "little")
        if cid == "ANMF" and pos + 24 <= len(data):
            dur = int.from_bytes(data[pos + 20:pos + 23], "little")
            fl = data[pos + 23]
            chunks.append((dur, (fl >> 0) & 1, (fl >> 1) & 1))
        pos += 8 + csz + (csz & 1)

    flags = sorted(set((d, nb) for _, d, nb in chunks))
    durs = sorted(set(c[0] for c in chunks))
    total_ms = sum(c[0] for c in chunks)

    q_frame = min(max(0, expected_frames // 4), max(0, expected_frames - 1))
    with Image.open(webp_path) as wi:
        ww, wh = wi.size
        wi.seek(q_frame)
        fq = wi.convert("RGBA")
        corners = [fq.getpixel((x, y))[3] for x, y in [(0, 0), (ww - 1, 0), (0, wh - 1), (ww - 1, wh - 1)]]

    ok = (
        (ww, wh) == (690, 960)
        and len(chunks) == expected_frames
        and flags == [(1, 1)]
        and durs == [expected_dur]
        and total_ms == expected_frames * expected_dur
        and corners == [0, 0, 0, 0]
    )
    return {
        "ok": ok,
        "bytes": size,
        "mb": round(size / (1024 * 1024), 2),
        "size": [ww, wh],
        "anmf_count": len(chunks),
        "flags_dispose_noblend": [list(f) for f in flags],
        "unique_dur_ms": durs,
        "total_ms": total_ms,
        "q_frame_index": q_frame,
        "q_frame_corner_alphas": corners,
    }


def check_gif(gif_path: Path, expected_frames: int, expected_dur: int) -> dict:
    if not gif_path.exists():
        return {"ok": False, "error": f"Missing {gif_path}"}
    size = gif_path.stat().st_size
    with Image.open(gif_path) as gi:
        gw, gh = gi.size
        n_frames = gi.n_frames
        loop = gi.info.get("loop")
        durs = []
        for i in range(n_frames):
            gi.seek(i)
            durs.append(gi.info.get("duration"))
    u_durs = sorted(set(durs))
    total_ms = sum(d or 0 for d in durs)
    ok = (
        (gw, gh) == (460, 640)
        and n_frames == expected_frames
        and loop == 0
        and u_durs == [expected_dur]
        and total_ms == expected_frames * expected_dur
    )
    return {
        "ok": ok,
        "bytes": size,
        "mb": round(size / (1024 * 1024), 2),
        "size": [gw, gh],
        "n_frames": n_frames,
        "loop": loop,
        "unique_dur_ms": u_durs,
        "total_ms": total_ms,
    }


def main():
    parser = argparse.ArgumentParser(description="Verify holographic_card HTML/WebP/GIF outputs against frozen spec.")
    parser.add_argument("--workdir", required=True, type=Path, help="Project workspace directory")
    parser.add_argument("--expected-frames", type=int, default=84)
    parser.add_argument("--expected-dur", type=int, default=60)
    args = parser.parse_args()

    workdir = args.workdir.resolve()
    out_dir = workdir / "output"
    meta_path = workdir / "03_processed" / "scene_meta.json"
    asset_lint = {}
    label_mode = "page_only"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            asset_lint = meta.get("asset_lint") or {}
            label_mode = str(meta.get("label_mode", "page_only"))
        except Exception:
            pass

    html_res = check_html(out_dir / "holographic_card.html")
    webp_res = check_webp(out_dir / "holographic_card.webp", args.expected_frames, args.expected_dur)
    gif_res = check_gif(out_dir / "holographic_card.gif", args.expected_frames, args.expected_dur)

    anim_fps = round(1000.0 / max(1, args.expected_dur), 2)
    html_res["target_fps"] = 60
    webp_res["effective_fps"] = anim_fps
    gif_res["effective_fps"] = anim_fps

    all_ok = html_res["ok"] and webp_res["ok"] and gif_res["ok"]
    lint_warnings = asset_lint.get("warnings", [])

    visual_qa = [
        "cutout_edges: confirm hair, accessories, and semi-transparent edges look natural with zero halo in 03_processed/cutout_check.png",
        "subject_framing: confirm ears, head, limbs, and props are not clipped at card edges in 03_processed/preview_composite.png & qa_keyframes.png",
        "lighting_and_contrast: confirm rich dark contrast with zero highlight wash-out across tilted angles in 03_processed/qa_keyframes.png",
    ]
    if label_mode == "on_card":
        visual_qa.append("nameplate_legibility: confirm on-card title & rarity badge text is crisp, centered, and unobstructed")

    report = {
        "workdir": str(workdir),
        "status": "PASS" if all_ok else "FAIL",
        "technical_status": "PASS" if all_ok else "FAIL",
        "expected_frames": args.expected_frames,
        "expected_dur_ms": args.expected_dur,
        "output_specs": {
            "html": "interactive WebGL2, 60 fps target, 5.2s auto-orbit",
            "webp": f"690x960 RGBA, {args.expected_frames} frames @ {args.expected_dur}ms (~{anim_fps} fps, {args.expected_frames * args.expected_dur / 1000:.2f}s)",
            "gif": f"460x640 RGB, {args.expected_frames} frames @ {args.expected_dur}ms (~{anim_fps} fps, {args.expected_frames * args.expected_dur / 1000:.2f}s)",
        },
        "html": html_res,
        "webp": webp_res,
        "gif": gif_res,
        "asset_lint_warnings": lint_warnings,
        "visual_qa_required": visual_qa,
        "note": "Technical PASS verifies dimensions, frame count, timing, zero-ghosting WebP flags, corner transparency, and WebGL2 structure; it does NOT automatically certify visual aesthetics, anatomy/ear clipping, or typography.",
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
