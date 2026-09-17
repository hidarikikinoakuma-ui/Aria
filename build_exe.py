"""
build_exe.py — Build Aria.exe with PyInstaller
================================================
Run this ONCE to produce a standalone Aria.exe that users can
double-click without needing Python installed.

Usage (from Aria folder):
    py build_exe.py

Output:
    dist/Aria.exe   ← distribute this single file

Requirements:
    pip install pyinstaller>=6.0.0

What the EXE does on launch:
  1. Extracts itself into a temp folder
  2. Installs any missing Python packages (pip is bundled)
  3. Starts OBS, writes liveapi.json, creates LAUNCH_APEX.bat
  4. Shows Aria's intro speech (XTTS v2 voice)
  5. Connects to Apex Live API and starts coaching
"""

import subprocess
import sys
import os
from pathlib import Path

ARIA_DIR = Path(__file__).parent

# ── Install PyInstaller if missing ────────────────────────────────────────────
try:
    import PyInstaller
    print(f"PyInstaller {PyInstaller.__version__} found ✅")
except ImportError:
    print("Installing PyInstaller...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0.0"], check=True)
    print("PyInstaller installed ✅")

# ── Assets to bundle ──────────────────────────────────────────────────────────
# Format: ("source_path", "destination_folder_inside_exe")
datas = []

# Config template
conf_template = ARIA_DIR / "config" / "aria.conf.template"
if conf_template.exists():
    datas.append((str(conf_template), "config"))

# Assets folder (avatar, sounds, sprites)
assets_dir = ARIA_DIR / "assets"
if assets_dir.exists():
    datas.append((str(assets_dir), "assets"))

# Mobile static files
mobile_static = ARIA_DIR / "mobile" / "static"
if mobile_static.exists():
    datas.append((str(mobile_static), "mobile/static"))

# ── PyInstaller spec args ─────────────────────────────────────────────────────
data_args = []
for src, dst in datas:
    data_args += ["--add-data", f"{src};{dst}"]  # Windows uses semicolon

icon_path = ARIA_DIR / "assets" / "aria_icon.ico"
icon_args = ["--icon", str(icon_path)] if icon_path.exists() else []

# ── Build command ─────────────────────────────────────────────────────────────
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",                        # single EXE
    "--windowed",                       # no console window (has its own rich console)
    "--console",                        # actually keep console — Aria prints to it
    "--name", "Aria",                   # output: dist/Aria.exe
    "--clean",                          # remove old build artifacts first
    "--noconfirm",                      # overwrite without asking

    # Hidden imports — packages Aria loads dynamically
    "--hidden-import", "loguru",
    "--hidden-import", "openai",
    "--hidden-import", "fastapi",
    "--hidden-import", "uvicorn",
    "--hidden-import", "uvicorn.logging",
    "--hidden-import", "uvicorn.loops",
    "--hidden-import", "uvicorn.loops.auto",
    "--hidden-import", "uvicorn.protocols",
    "--hidden-import", "uvicorn.protocols.http",
    "--hidden-import", "uvicorn.protocols.http.auto",
    "--hidden-import", "uvicorn.protocols.websockets",
    "--hidden-import", "uvicorn.protocols.websockets.auto",
    "--hidden-import", "uvicorn.lifespan",
    "--hidden-import", "uvicorn.lifespan.on",
    "--hidden-import", "websockets",
    "--hidden-import", "cv2",
    "--hidden-import", "PIL",
    "--hidden-import", "PIL.Image",
    "--hidden-import", "mss",
    "--hidden-import", "psutil",
    "--hidden-import", "inputs",
    "--hidden-import", "schedule",
    "--hidden-import", "pydantic",
    "--hidden-import", "rich",
    "--hidden-import", "aiohttp",
    "--hidden-import", "requests",
    "--hidden-import", "tweepy",
    "--hidden-import", "praw",
    "--hidden-import", "sqlalchemy",
    "--hidden-import", "aiosqlite",
    "--hidden-import", "TTS",
    "--hidden-import", "TTS.api",

    # Exclude heavy packages we don't use in the EXE
    # (NIM/Ollama calls go over HTTP — no local model weights needed in the EXE)
    "--exclude-module", "torch",
    "--exclude-module", "torchvision",
    "--exclude-module", "tensorflow",
    "--exclude-module", "keras",

    *data_args,
    *icon_args,

    str(ARIA_DIR / "ARIA_START.py"),    # entry point
]

print("\n" + "═" * 60)
print("  Building Aria.exe — this takes 2-5 minutes...")
print("═" * 60 + "\n")

result = subprocess.run(cmd, cwd=str(ARIA_DIR))

if result.returncode == 0:
    exe_path = ARIA_DIR / "dist" / "Aria.exe"
    size_mb  = round(exe_path.stat().st_size / 1024 / 1024, 1) if exe_path.exists() else "?"
    print("\n" + "═" * 60)
    print(f"  ✅  Aria.exe built successfully!")
    print(f"  📦  Location: dist\\Aria.exe  ({size_mb} MB)")
    print(f"  🚀  Share dist\\Aria.exe — no Python needed to run it")
    print("═" * 60 + "\n")
    print("NOTE: First run takes 5-10 min — installs packages & downloads OBS.")
    print("Users still need to paste their NIM_API_KEY on first launch.")
else:
    print("\n❌ Build failed — see errors above.")
    print("Common fixes:")
    print("  • pip install pyinstaller>=6.0.0")
    print("  • Make sure you're in the Aria folder")
    sys.exit(1)
