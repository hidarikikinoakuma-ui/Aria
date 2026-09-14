#!/usr/bin/env python3
"""
ARIA — Health Check
=====================
Quickly verify that every Aria component is importable and configured.
Run this before a session to catch missing packages or misconfigured keys.

Usage:
    python scripts/health_check.py

Player: Hidarikikinoaku (LeftHandDevil)
Coach:  Aria (@migikonokami / RightHandGod)
"""

import sys
import os
import json
import configparser
import socket
from pathlib import Path

# ── Make sure we run from the aria/ root ──────────────────────────────────────
ARIA_DIR = Path(__file__).parent.parent
os.chdir(ARIA_DIR)
sys.path.insert(0, str(ARIA_DIR))

# ─────────────────────────────────────────────────────────────────────────────
PASS  = "✅"
FAIL  = "❌"
WARN  = "⚠️ "
SKIP  = "⬛"

results: list[tuple[str, str, str]] = []   # (status, label, detail)


def check(label: str, fn, warn_only: bool = False):
    """Run fn(), record PASS/FAIL/WARN."""
    try:
        detail = fn()
        results.append((PASS, label, detail or ""))
    except Exception as e:
        status = WARN if warn_only else FAIL
        results.append((status, label, str(e)))


# ─────────────────────────────────────────────────────────────────────────────
#  1. Python version
# ─────────────────────────────────────────────────────────────────────────────
check("Python version", lambda: (
    f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10)
    else (_ for _ in ()).throw(RuntimeError(
        f"Python 3.10+ required, found {sys.version_info.major}.{sys.version_info.minor}"
    ))
))

# ─────────────────────────────────────────────────────────────────────────────
#  2. Required Python packages
# ─────────────────────────────────────────────────────────────────────────────
PACKAGES = {
    "loguru":      ("loguru",     False),
    "openai":      ("openai",     False),
    "cv2":         ("cv2",        False),
    "numpy":       ("numpy",      False),
    "fastapi":     ("fastapi",    False),
    "uvicorn":     ("uvicorn",    False),
    "websockets":  ("websockets", False),
    "PIL":         ("PIL",        False),
    "mss":         ("mss",        False),
    "psutil":      ("psutil",     False),
    "rich":        ("rich",       False),
    "requests":    ("requests",   False),
    "schedule":    ("schedule",   False),
    "pydantic":    ("pydantic",   False),
    "tweepy":      ("tweepy",     True),   # social — optional
    "praw":        ("praw",       True),   # social — optional
    "PyQt5":       ("PyQt5",      True),   # overlay — optional on Linux
    "moviepy":     ("moviepy",    True),   # video — optional
    "inputs":      ("inputs",     True),   # controller — Windows only
}

for display, (import_name, warn_only) in PACKAGES.items():
    def _imp(n=import_name, d=display):
        import importlib
        m = importlib.import_module(n)
        ver = getattr(m, "__version__", "?")
        return f"v{ver}"
    check(f"Package: {display}", _imp, warn_only=warn_only)

# ─────────────────────────────────────────────────────────────────────────────
#  3. Config file
# ─────────────────────────────────────────────────────────────────────────────
def _check_config():
    conf_path = ARIA_DIR / "config" / "aria.conf"
    if not conf_path.exists():
        raise FileNotFoundError(f"config/aria.conf not found at {conf_path}")
    cfg = configparser.ConfigParser()
    cfg.read(conf_path)
    required_sections = ["player", "aria", "recording", "liveapi", "analysis"]
    missing = [s for s in required_sections if s not in cfg]
    if missing:
        raise RuntimeError(f"Missing config sections: {missing}")
    username = cfg.get("player", "username", fallback="")
    if not username:
        raise RuntimeError("player.username is not set in aria.conf")
    return f"username={username}"

check("Config: aria.conf", _check_config)

# ─────────────────────────────────────────────────────────────────────────────
#  4. OpenAI API key
# ─────────────────────────────────────────────────────────────────────────────
def _check_openai_key():
    cfg = configparser.ConfigParser()
    cfg.read(ARIA_DIR / "config" / "aria.conf")
    key = cfg.get("analysis", "openai_api_key", fallback="") or os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("openai_api_key not set — add it to aria.conf or OPENAI_API_KEY env var")
    return f"sk-...{key[-4:]}"

check("OpenAI API key", _check_openai_key, warn_only=True)

# ─────────────────────────────────────────────────────────────────────────────
#  5. Directory structure
# ─────────────────────────────────────────────────────────────────────────────
EXPECTED_DIRS = [
    "config", "core", "analysis", "clips", "overlay",
    "mobile", "social", "youtube", "scripts",
    "data/clips", "data/sessions", "data/reports",
    "assets/sprites", "assets/sounds", "assets/templates",
    "logs",
]

def _check_dirs():
    missing = [d for d in EXPECTED_DIRS if not (ARIA_DIR / d).exists()]
    if missing:
        raise RuntimeError(f"Missing directories: {missing}")
    return f"{len(EXPECTED_DIRS)} dirs present"

check("Directory structure", _check_dirs)

# ─────────────────────────────────────────────────────────────────────────────
#  6. Module imports
# ─────────────────────────────────────────────────────────────────────────────
MODULES = [
    ("core.system_detector",          "SystemProfile"),
    ("core.apex_live_api",            "ApexLiveAPI"),
    ("core.killfeed_detector",        "KillFeedDetector"),
    ("core.controller_logger",        "ControllerLogger"),
    ("analysis.fight_analysis_engine","FightAnalysisEngine"),
    ("analysis.video_annotator",      "VideoAnnotator"),
    ("clips.obs_clip_manager",        "OBSClipManager"),
    ("overlay.aria_overlay",          "AriaOverlay"),
    ("mobile.mobile_api",             "MobileCompanionAPI"),
    ("social.social_manager",         "SocialManager"),
    ("youtube.youtube_manager",       "YouTubeManager"),
]

for module_path, cls_name in MODULES:
    def _imp_mod(mp=module_path, cn=cls_name):
        import importlib
        mod = importlib.import_module(mp)
        if not hasattr(mod, cn):
            raise AttributeError(f"{cn} not found in {mp}")
        return f"{mp}.{cn}"
    check(f"Module: {module_path}", _imp_mod)

# ─────────────────────────────────────────────────────────────────────────────
#  7. OBS WebSocket (optional — OBS must be running)
# ─────────────────────────────────────────────────────────────────────────────
def _check_obs():
    cfg = configparser.ConfigParser()
    cfg.read(ARIA_DIR / "config" / "aria.conf")
    host = cfg.get("recording", "obs_host", fallback="localhost")
    port = int(cfg.get("recording", "obs_port", fallback="4455"))
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    result = s.connect_ex((host, port))
    s.close()
    if result != 0:
        raise RuntimeError(f"OBS not reachable at {host}:{port} — is OBS running?")
    return f"{host}:{port} reachable"

check("OBS WebSocket", _check_obs, warn_only=True)

# ─────────────────────────────────────────────────────────────────────────────
#  8. Local network IP (mobile companion)
# ─────────────────────────────────────────────────────────────────────────────
def _check_network():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    s.close()
    cfg = configparser.ConfigParser()
    cfg.read(ARIA_DIR / "config" / "aria.conf")
    port = cfg.get("mobile", "port", fallback="8765")
    return f"http://{ip}:{port}"

check("Network (mobile URL)", _check_network, warn_only=True)

# ─────────────────────────────────────────────────────────────────────────────
#  9. Data folders writable
# ─────────────────────────────────────────────────────────────────────────────
def _check_writable():
    for d in ["data/clips", "data/sessions", "data/reports", "logs"]:
        p = ARIA_DIR / d
        p.mkdir(parents=True, exist_ok=True)
        test_file = p / ".write_test"
        test_file.touch()
        test_file.unlink()
    return "data/ and logs/ writable"

check("Write permissions", _check_writable)

# ─────────────────────────────────────────────────────────────────────────────
#  Report
# ─────────────────────────────────────────────────────────────────────────────
print()
print("╔══════════════════════════════════════════════════════╗")
print("║               ARIA — Health Check                   ║")
print("╚══════════════════════════════════════════════════════╝")
print()

passed = sum(1 for s, _, _ in results if s == PASS)
warned = sum(1 for s, _, _ in results if s == WARN)
failed = sum(1 for s, _, _ in results if s == FAIL)

for status, label, detail in results:
    detail_str = f"  ({detail})" if detail else ""
    print(f"  {status}  {label}{detail_str}")

print()
print(f"  Results: {passed} passed, {warned} warnings, {failed} failed")
print()

if failed > 0:
    print("  ❌ Aria is NOT ready. Fix the failures above before launching.")
    sys.exit(1)
elif warned > 0:
    print("  ⚠️  Aria can start, but some optional features are unavailable.")
    print("     See warnings above for details.")
    sys.exit(0)
else:
    print("  ✅ All checks passed. Aria is fully operational.")
    print("     Run ARIA_START.py (or ARIA_START.bat on Windows) to launch.")
    sys.exit(0)
