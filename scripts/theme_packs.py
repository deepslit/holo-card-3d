"""Theme packs: ready-made matching backdrop + frame pairs for cards made without an image generator.

    python scripts/theme_packs.py --list
    python scripts/theme_packs.py --apply gothic_moon --workdir <workdir>
    python scripts/theme_packs.py --fetch            # download the packs when assets/themes/ has no images

`--apply` copies the pack's bg / fg into <workdir>/01_raw_layers/ (never overwriting layers that are already
there) and writes the pack's recommended presets into <workdir>/card_config.json. Nothing else in the pipeline
changes: the copied files are ordinary `bg` and `fg` layers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SKILL_ROOT = Path(__file__).resolve().parent.parent
THEMES_DIR = SKILL_ROOT / "assets" / "themes"
INDEX_PATH = THEMES_DIR / "themes.json"
MIRRORS = [
    "https://raw.githubusercontent.com/deepslit/holo-card-3d/main/assets/themes/",
    "https://gitee.com/deepslit/holo-card-3d/raw/main/assets/themes/",
]
LAYER_FILES = {"bg": "bg.jpg", "fg": "fg.webp"}
PRESET_KEYS = ("lighting_preset", "holo_pattern", "material_preset")


def load_index() -> dict:
    if not INDEX_PATH.exists():
        raise SystemExit(f"Theme index not found: {INDEX_PATH}")
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pack_files(name: str) -> dict[str, Path]:
    return {layer: THEMES_DIR / name / fname for layer, fname in LAYER_FILES.items()}


def missing_files(index: dict) -> list[tuple[str, str]]:
    return [(name, fname) for name in index["themes"] for fname in LAYER_FILES.values() if not (THEMES_DIR / name / fname).exists()]


def cmd_list(index: dict) -> None:
    missing = {name for name, _ in missing_files(index)}
    for name, t in index["themes"].items():
        state = "not downloaded - run --fetch" if name in missing else "ready"
        print(f"{name:16s} [{t['category']:7s}] {t['title_zh']} / {t['title_en']} - {t['description']} ({state})")


def cmd_fetch(index: dict) -> None:
    todo = missing_files(index)
    if not todo:
        print("All theme packs are already present.")
        return
    for name, fname in todo:
        expected = index["themes"][name]["sha256"][fname]
        dest = THEMES_DIR / name / fname
        dest.parent.mkdir(parents=True, exist_ok=True)
        last_err = None
        for base in MIRRORS:
            url = f"{base}{name}/{fname}"
            try:
                with urllib.request.urlopen(url, timeout=30) as resp:
                    data = resp.read()
                if hashlib.sha256(data).hexdigest() != expected:
                    last_err = f"checksum mismatch from {url}"
                    continue
                dest.write_bytes(data)
                print(f"Downloaded {name}/{fname} ({len(data) // 1024} KB)")
                last_err = None
                break
            except Exception as exc:  # network errors differ per platform; try the next mirror
                last_err = f"{url}: {exc}"
        if last_err:
            raise SystemExit(f"Could not download {name}/{fname}: {last_err}\nThe card still works without theme packs (procedural backdrop + built-in frames).")


def cmd_apply(index: dict, name: str, workdir: Path) -> None:
    if name not in index["themes"]:
        raise SystemExit(f"Unknown theme pack '{name}'. Available: {', '.join(index['themes'])}")
    theme = index["themes"][name]
    files = pack_files(name)
    absent = [p.name for p in files.values() if not p.exists()]
    if absent:
        raise SystemExit(f"Theme pack '{name}' has no image files here ({', '.join(absent)}). Run: python scripts/theme_packs.py --fetch")
    raw_dir = workdir / "01_raw_layers"
    raw_dir.mkdir(parents=True, exist_ok=True)
    existing = {p.stem.lower() for p in raw_dir.iterdir() if p.is_file()}
    for layer, src in files.items():
        if layer in existing:
            print(f"Kept the existing {layer} layer in {raw_dir} (theme pack file not copied).")
            continue
        shutil.copyfile(src, raw_dir / f"{layer}{src.suffix}")
        print(f"Copied {name}/{src.name} -> {raw_dir / (layer + src.suffix)}")

    cfg_path = workdir / "card_config.json"
    example = SKILL_ROOT / "assets" / "card_config.example.json"
    cfg = json.loads((cfg_path if cfg_path.exists() else example).read_text(encoding="utf-8"))
    cfg["theme_pack"] = name
    for key in PRESET_KEYS:
        cfg[key] = theme[key]
    cfg["motion_motif"] = {"kind": theme["motion_motif"], "color1": "auto", "color2": "auto"}
    cfg["fallback_frame"] = None
    breakout = cfg.get("breakout") if isinstance(cfg.get("breakout"), dict) else {}
    cfg["breakout"] = {"mode": "top", "until_v": 0.62, "feather": 0.05, **breakout, "enabled": True}
    cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote presets for '{name}' into {cfg_path}: " + ", ".join(f"{k}={theme[k]}" for k in PRESET_KEYS) + f", motion_motif={theme['motion_motif']}, breakout on")


def main() -> None:
    parser = argparse.ArgumentParser(description="List, download, or apply holo-card theme packs.")
    parser.add_argument("--list", action="store_true", help="List theme packs")
    parser.add_argument("--fetch", action="store_true", help="Download pack images that are not present (about 3.5 MB in total)")
    parser.add_argument("--apply", metavar="NAME", help="Copy a pack's bg/fg into the workdir and write its presets")
    parser.add_argument("--workdir", type=Path, help="Card project directory (required with --apply)")
    args = parser.parse_args()
    index = load_index()
    if args.fetch:
        cmd_fetch(index)
    if args.apply:
        if not args.workdir:
            raise SystemExit("--apply needs --workdir <card project directory>")
        cmd_apply(index, args.apply, args.workdir.resolve())
    if args.list or not (args.fetch or args.apply):
        cmd_list(index)


if __name__ == "__main__":
    main()
