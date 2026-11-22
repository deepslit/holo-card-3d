"""Cross-platform environment, Python interpreter, and dependency preflight check (pure stdlib)."""
import argparse
import ctypes
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SKILL_ROOT = Path(__file__).resolve().parent.parent
REQ_FILE = SKILL_ROOT / "requirements.txt"

REQUIRED_MODULES = [
    ("numpy", "numpy"),
    ("PIL", "Pillow"),
    ("cv2", "opencv-python"),
]


def get_total_ram_gb() -> float | None:
    system = platform.system()
    try:
        if system == "Windows":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return round(stat.ullTotalPhys / (1024 ** 3), 2)
        elif system == "Linux":
            meminfo = Path("/proc/meminfo")
            if meminfo.exists():
                for line in meminfo.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return round(kb / (1024 ** 2), 2)
        elif system == "Darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=3).strip()
            return round(int(out) / (1024 ** 3), 2)
    except Exception:
        return None
    return None


def find_candidate_pythons() -> list[str]:
    """Locate non-Store Python binaries on the machine for helpful diagnostics."""
    found: list[str] = []
    seen: set[str] = set()

    def _add(p: Path):
        try:
            rp = str(p.resolve())
        except Exception:
            rp = str(p)
        low = rp.lower()
        if "windowsapps" in low or low in seen or not p.is_file():
            return
        seen.add(low)
        found.append(rp)

    for cmd in ("python3", "python", "py"):
        hit = shutil.which(cmd)
        if hit:
            _add(Path(hit))

    if platform.system() == "Windows":
        local_app = os.environ.get("LOCALAPPDATA", "")
        roots = [
            Path(local_app) / "Programs" / "Python" if local_app else None,
            Path("C:/Python312"),
            Path("C:/Python311"),
            Path("C:/Python310"),
        ]
        for root in roots:
            if not root or not root.exists():
                continue
            if (root / "python.exe").is_file():
                _add(root / "python.exe")
            for sub in sorted(root.glob("Python3*"), reverse=True):
                if (sub / "python.exe").is_file():
                    _add(sub / "python.exe")
    else:
        for cand in ("/usr/bin/python3", "/usr/local/bin/python3", "/opt/homebrew/bin/python3"):
            _add(Path(cand))

    return found[:6]


def _probe_pillow_webp_anim() -> bool:
    """Verify Pillow supports RGBA animated WebP encoding cleanly across Pillow 10/11/12+."""
    import io
    from PIL import Image, features
    if not features.check("webp"):
        return False
    try:
        buf = io.BytesIO()
        f1 = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
        f2 = Image.new("RGBA", (4, 4), (0, 255, 0, 0))
        f1.save(buf, format="WEBP", save_all=True, append_images=[f2], duration=[60, 60], loop=0)
        return b"ANMF" in buf.getvalue()
    except Exception:
        return False


def check_packages() -> tuple[dict, list[str]]:
    pkg_info = {}
    missing = []
    for mod_name, pip_name in REQUIRED_MODULES:
        spec = importlib.util.find_spec(mod_name)
        if spec is None:
            pkg_info[pip_name] = {"installed": False, "version": None}
            missing.append(pip_name)
            continue
        try:
            mod = __import__(mod_name)
            ver = getattr(mod, "__version__", "unknown")
            entry = {"installed": True, "version": str(ver)}
            if mod_name == "PIL":
                entry["webp_anim_support"] = _probe_pillow_webp_anim()
            pkg_info[pip_name] = entry
        except Exception as exc:
            pkg_info[pip_name] = {"installed": False, "error": str(exc)}
            missing.append(pip_name)
    return pkg_info, missing


def main():
    parser = argparse.ArgumentParser(description="Check Python, dependencies, disk, and RAM for holo-card-3d.")
    parser.add_argument("--workdir", type=Path, default=Path.cwd(), help="Target workspace path for disk check")
    args = parser.parse_args()

    system = platform.system()
    py_exe = str(Path(sys.executable).resolve())
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 10)
    is_win_store_stub = system == "Windows" and "windowsapps" in py_exe.lower()

    pkgs, missing = check_packages()
    webp_anim_ok = bool(pkgs.get("Pillow", {}).get("webp_anim_support", False)) if pkgs.get("Pillow", {}).get("installed") else False

    check_path = args.workdir.resolve()
    while not check_path.exists() and check_path.parent != check_path:
        check_path = check_path.parent
    disk = shutil.disk_usage(check_path)
    free_gb = round(disk.free / (1024 ** 3), 2)
    ram_gb = get_total_ram_gb()

    warnings: list[str] = []
    errors: list[str] = []

    if is_win_store_stub:
        errors.append("Current interpreter appears to be a Windows Store alias; use a real Python 3.10+ interpreter.")
    if not py_ok:
        errors.append(f"Python {py_ver} detected; Python >= 3.10 is recommended.")
    if missing:
        errors.append(f"Missing required packages: {', '.join(missing)}")
    elif not webp_anim_ok:
        errors.append("Pillow is installed but animated WebP support ('webp_anim') is unavailable.")

    if free_gb < 0.5:
        warnings.append(f"Low free disk space ({free_gb} GB) at {check_path}; recommend >= 0.5 GB.")
    if ram_gb is not None and ram_gb < 2.0:
        warnings.append(f"Low system RAM ({ram_gb} GB); pass --workers 1..2 during render.")

    if system == "Windows":
        setup_hint = f'"{py_exe}" -m venv .venv; .\\.venv\\Scripts\\python.exe -m pip install -r "{REQ_FILE}"'
        pip_hint = f'"{py_exe}" -m pip install -r "{REQ_FILE}"'
    else:
        setup_hint = f'"{py_exe}" -m venv .venv && ./.venv/bin/python -m pip install -r "{REQ_FILE}"'
        pip_hint = f'"{py_exe}" -m pip install -r "{REQ_FILE}"'

    ok = len(errors) == 0
    report = {
        "status": "OK" if ok else "ACTION_REQUIRED",
        "os": f"{system} {platform.release()}",
        "python": {
            "executable": py_exe,
            "version": py_ver,
            "ok": py_ok and not is_win_store_stub,
            "is_windows_store_stub": is_win_store_stub,
        },
        "packages": pkgs,
        "resources": {
            "cpu_count": os.cpu_count() or 1,
            "disk_free_gb": free_gb,
            "ram_total_gb": ram_gb,
        },
        "warnings": warnings,
        "errors": errors,
    }
    if not ok:
        report["recommended_commands"] = {
            "install_into_current_python": pip_hint,
            "create_isolated_venv": setup_hint,
        }
        report["detected_pythons"] = find_candidate_pythons()

    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
