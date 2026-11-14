#!/usr/bin/env python3
"""Build a standalone single-file executable for the current platform.

Usage:
    python scripts/build_binary.py            # build into dist/
    python scripts/build_binary.py --clean    # wipe build/ and dist/ first

The version comes from CHANGELOG.md (the single source of truth), and the
artifact is named:

    lspy-<version>-windows-x64.exe          (Windows)
    lspy-<version>-linux-x86_64             (Linux)
    lspy-<version>-macos-arm64              (macOS)

Requires PyInstaller (`pip install pyinstaller`). lspy itself has no third-party
runtime dependencies, so the bundle stays small.
"""

import re
import shutil
import subprocess
import sys
import platform
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
DIST = ROOT / "dist"


def changelog_version():
    text = CHANGELOG.read_text(encoding="utf-8")
    m = re.search(r"^##\s*\[(\d+\.\d+\.\d+)\]", text, re.MULTILINE)
    if not m:
        raise SystemExit("error: no '## [x.y.z]' heading found in CHANGELOG.md")
    return m.group(1)


def platform_tag():
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        return "windows-x64"
    if system == "darwin":
        return "macos-" + ("arm64" if machine in ("arm64", "aarch64") else "x64")
    if machine in ("x86_64", "amd64"):
        return "linux-x86_64"
    if machine in ("aarch64", "arm64"):
        return "linux-arm64"
    return f"linux-{machine}"


def artifact_name(version, tag):
    suffix = ".exe" if platform.system().lower() == "windows" else ""
    return f"lspy-{version}-{tag}{suffix}"


def main(argv):
    do_clean = "--clean" in argv
    version = changelog_version()
    tag = platform_tag()

    if importlib.util.find_spec("PyInstaller") is None:
        raise SystemExit("error: PyInstaller is missing — run: pip install pyinstaller")

    if do_clean:
        for p in (ROOT / "build", DIST):
            if p.exists():
                shutil.rmtree(p)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",
        "--clean",
        "--noconfirm",
        "--name", "lspy",
        str(ROOT / "lspy.py"),
    ]
    # tkinter is imported lazily inside pick_files(), so name it explicitly when present.
    if importlib.util.find_spec("tkinter") is not None:
        cmd += ["--hidden-import", "tkinter", "--hidden-import", "tkinter.filedialog"]

    print("building:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        raise SystemExit(f"error: PyInstaller failed with exit code {result.returncode}")

    built = DIST / ("lspy.exe" if platform.system().lower() == "windows" else "lspy")
    if not built.exists():
        raise SystemExit(f"error: expected binary not found: {built}")

    target = DIST / artifact_name(version, tag)
    if target.exists():
        target.unlink()
    built.rename(target)
    print(f"artifact: {target} ({target.stat().st_size / 1024 / 1024:.1f} MiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
