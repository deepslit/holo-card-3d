"""Unified runner for the 3D holographic quicksand collector-card pipeline."""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPTS_DIR = Path(__file__).resolve().parent


def run_step(label: str, script_name: str, extra_args: list[str]) -> None:
    t0 = time.time()
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name), *extra_args]
    print(f"\n=== [{label}] Running {script_name} ===")
    subprocess.run(cmd, check=True)
    print(f"=== [{label}] Done in {time.time() - t0:.1f}s ===")


def main():
    parser = argparse.ArgumentParser(description="Run 3D holographic collector-card pipeline end-to-end or by stage.")
    parser.add_argument("--workdir", required=True, type=Path, help="Project workspace directory")
    parser.add_argument(
        "--stage",
        default="all",
        choices=["all", "env", "matte", "prop-grid", "prop-mask", "prepare", "preview", "html", "render", "verify"],
    )
    parser.add_argument(
        "--key-color",
        default="auto",
        choices=["auto", "rgba", "green", "magenta", "blue", "solid", "grabcut", "none"],
    )
    parser.add_argument("--auto-depth", action="store_true", help="Synthesize relief depth without mid_depth")
    parser.add_argument("--crop", nargs=4, type=float, metavar=("U0", "V0", "U1", "V1"), help="Optional UV crop for prop-grid")
    parser.add_argument("--frames", type=int, default=84)
    parser.add_argument("--duration-ms", type=int, default=60)
    parser.add_argument("--webp-quality", type=int, default=88)
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 4))
    args = parser.parse_args()

    workdir = str(args.workdir.resolve())
    t_total = time.time()
    stages = ["matte", "prepare", "preview", "html", "render", "verify"] if args.stage == "all" else [args.stage]

    for st in stages:
        if st == "env":
            run_step("Preflight env", "check_env.py", ["--workdir", workdir])
        elif st == "matte":
            run_step("Stage 1/5 matte", "matte_layers.py", ["--workdir", workdir, "--key-color", args.key_color])
        elif st == "prop-grid":
            grid_args = ["--workdir", workdir, "--grid"]
            if args.crop:
                grid_args.extend(["--crop", *[str(v) for v in args.crop]])
            run_step("Stage prop-grid", "build_prop_mask.py", grid_args)
        elif st == "prop-mask":
            run_step("Stage prop-mask", "build_prop_mask.py", ["--workdir", workdir])
        elif st == "prepare":
            prep_args = ["--workdir", workdir]
            if args.auto_depth:
                prep_args.append("--auto-depth")
            run_step("Stage 2/5 prepare", "prepare_assets.py", prep_args)
        elif st == "preview":
            run_step(
                "Stage preview",
                "render_card.py",
                ["--workdir", workdir, "--frames", str(args.frames), "--preview-only"],
            )
        elif st == "html":
            run_step("Stage 3/5 html", "build_html_card.py", ["--workdir", workdir])
        elif st == "render":
            run_step(
                "Stage 4/5 render",
                "render_card.py",
                [
                    "--workdir", workdir,
                    "--frames", str(args.frames),
                    "--duration-ms", str(args.duration_ms),
                    "--webp-quality", str(args.webp_quality),
                    "--workers", str(args.workers),
                ],
            )
        elif st == "verify":
            run_step(
                "Stage 5/5 verify",
                "verify_outputs.py",
                [
                    "--workdir", workdir,
                    "--expected-frames", str(args.frames),
                    "--expected-dur", str(args.duration_ms),
                ],
            )

    print(f"\nPipeline stage '{args.stage}' completed cleanly in {time.time() - t_total:.1f}s.")


if __name__ == "__main__":
    main()
