"""
╔══════════════════════════════════════════════════════════════╗
║                   ARIA — ONE BUTTON LAUNCH                   ║
║                                                              ║
║  Run this ONE file. It does everything automatically:        ║
║    ✅  Installs all missing Python packages                   ║
║    ✅  Downloads & installs OBS if not found                  ║
║    ✅  Starts OBS with replay buffer ready                    ║
║    ✅  Writes liveapi.json so Apex Live API works             ║
║    ✅  Creates LAUNCH_APEX.bat (one-click Apex launcher)      ║
║    ✅  Connects to Apex Live API (no OCR, no lag)             ║
║    ✅  Logs GameSir G7 Pro inputs + shows live button display ║
║    ✅  Starts mobile companion server                         ║
║    ✅  Runs Aria's coaching overlay after every match         ║
║                                                              ║
║  HOW TO USE EVERY SESSION:                                   ║
║    Double-click  ARIA_START.bat                              ║
║    Then double-click  LAUNCH_APEX.bat  to start Apex         ║
║                                                              ║
║  FIRST RUN:                                                  ║
║    Set OPENAI_API_KEY below (platform.openai.com/api-keys)   ║
║                                                              ║
║  Player: Hidarikikinoaku (LeftHandDevil)                     ║
║  Coach:  Aria (@migikonokami / RightHandGod)                 ║
╚══════════════════════════════════════════════════════════════╝
"""

# ════════════════════════════════════════════════════════════════
#  SETTINGS  —  fill these in once, never touch again
# ════════════════════════════════════════════════════════════════

OPENAI_API_KEY  = ""     # Required for coaching. Get at: platform.openai.com/api-keys
OBS_PASSWORD    = ""     # Only if you set a password in OBS WebSocket settings
MOBILE_PORT     = 8765   # Port your phone connects to

# Paths — defaults work for most installs, only change if yours is different
OBS_PATH    = r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"
STEAM_PATH  = r"C:\Program Files (x86)\Steam\steam.exe"
APEX_LIVEAPI = r"C:\Program Files (x86)\Steam\steamapps\common\Apex Legends\LiveAPI\liveapi.json"

# ════════════════════════════════════════════════════════════════
#  DO NOT EDIT BELOW THIS LINE
# ════════════════════════════════════════════════════════════════

import sys
import os
import subprocess
import time
import threading
import socket
import json
import configparser
import urllib.request
from pathlib import Path

ARIA_DIR = Path(__file__).parent
os.chdir(ARIA_DIR)
os.makedirs("logs", exist_ok=True)

PLAYER_NAME  = "Hidarikikinoaku"
PLAYER_HANDLE= "LeftHandDevil"
COACH_HANDLE = "@migikonokami"
LEGEND_MAIN  = "Alter"


# ════════════════════════════════════════════════════════════════
#  STEP 1 — Install missing Python packages
# ════════════════════════════════════════════════════════════════

REQUIRED_PACKAGES = {
    "loguru":      "loguru==0.7.2",
    "openai":      "openai==1.30.1",
    "cv2":         "opencv-python==4.9.0.80",
    "websockets":  "websockets==12.0",
    "mss":         "mss==9.0.1",
    "PIL":         "Pillow==10.3.0",
    "fastapi":     "fastapi==0.111.0",
    "uvicorn":     "uvicorn==0.29.0",
    "numpy":       "numpy==1.26.4",
    "inputs":      "inputs==0.5",
    "schedule":    "schedule==1.2.1",
    "pydantic":    "pydantic==2.7.1",
    "rich":        "rich==13.7.1",
    "psutil":      "psutil==5.9.8",
    "tweepy":      "tweepy==4.14.0",
    "praw":        "praw==7.7.1",
    "aiohttp":     "aiohttp==3.9.5",
    "requests":    "requests==2.32.2",
    "moviepy":     "moviepy==1.0.3",
    "obsws":       "obs-websocket-py==1.0.0",
}


def install_packages():
    print("\n[ARIA] Checking Python packages...")
    missing = []
    for import_name, pip_spec in REQUIRED_PACKAGES.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pip_spec)

    if not missing:
        print("[ARIA] All packages already installed ✅")
        return

    print(f"[ARIA] Installing {len(missing)} missing package(s) — this takes a few minutes on first run...")
    for pkg in missing:
        print(f"  → installing {pkg} ...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
            capture_output=True
        )
        if result.returncode != 0:
            print(f"    ⚠️  {pkg} failed — {result.stderr.decode()[:80]}")

    print("[ARIA] Packages ready ✅\n")


# ════════════════════════════════════════════════════════════════
#  STEP 2 — Install OBS if not found
# ════════════════════════════════════════════════════════════════

OBS_INSTALLER_URL = "https://github.com/obsproject/obs-studio/releases/download/30.1.2/OBS-Studio-30.1.2-Windows-Installer.exe"
OBS_INSTALLER_FILENAME = "obs_installer.exe"

ALT_OBS_PATHS = [
    r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
    r"C:\Program Files (x86)\obs-studio\bin\64bit\obs64.exe",
    str(Path.home() / r"AppData\Local\Programs\obs-studio\bin\64bit\obs64.exe"),
]


def find_obs() -> Path | None:
    """Search common install locations for OBS."""
    paths_to_check = [OBS_PATH] + ALT_OBS_PATHS
    for p in paths_to_check:
        if Path(p).exists():
            return Path(p)
    return None


def install_obs():
    """Download and silently install OBS Studio if not found."""
    obs_path = find_obs()
    if obs_path:
        print(f"[ARIA] OBS found: {obs_path} ✅")
        return obs_path

    print("[ARIA] OBS not found — downloading OBS Studio 30.1.2...")
    print(f"       Source: {OBS_INSTALLER_URL}")

    installer_path = ARIA_DIR / OBS_INSTALLER_FILENAME

    try:
        def _progress(block_num, block_size, total_size):
            downloaded = block_num * block_size
            pct        = min(int(downloaded / total_size * 100), 100) if total_size > 0 else 0
            print(f"\r  Downloading OBS... {pct}%   ", end="", flush=True)

        urllib.request.urlretrieve(OBS_INSTALLER_URL, installer_path, _progress)
        print()
        print("[ARIA] Download complete. Installing OBS silently...")

        # /S = silent install, /D = install directory
        subprocess.run(
            [str(installer_path), "/S", f"/D=C:\\Program Files\\obs-studio"],
            check=True
        )

        # Clean up installer
        installer_path.unlink(missing_ok=True)

        obs_path = find_obs()
        if obs_path:
            print(f"[ARIA] OBS installed ✅  {obs_path}")
            return obs_path
        else:
            print("[ARIA] OBS install finished but path not found — please launch OBS manually.")
            return None

    except Exception as e:
        print(f"[ARIA] OBS installation failed: {e}")
        print("       Download OBS manually from: https://obsproject.com/download")
        installer_path.unlink(missing_ok=True)
        return None


# ════════════════════════════════════════════════════════════════
#  STEP 3 — Patch aria.conf with settings from top of this file
# ════════════════════════════════════════════════════════════════

def patch_config():
    conf_path = ARIA_DIR / "config" / "aria.conf"
    if not conf_path.exists():
        return

    cfg = configparser.ConfigParser()
    cfg.read(conf_path)
    changed = False

    def _set(section, key, value):
        nonlocal changed
        if value and cfg.get(section, key, fallback="") == "":
            if section not in cfg:
                cfg[section] = {}
            cfg[section][key] = value
            changed = True

    _set("analysis",  "openai_api_key", OPENAI_API_KEY)
    _set("recording", "obs_password",   OBS_PASSWORD)

    # Always make sure username is correct
    if "player" not in cfg:
        cfg["player"] = {}
    if cfg["player"].get("username", "") != PLAYER_NAME:
        cfg["player"]["username"] = PLAYER_NAME
        changed = True

    if "detection" not in cfg:
        cfg["detection"] = {}
    if cfg["detection"].get("apex_username", "") != PLAYER_NAME:
        cfg["detection"]["apex_username"] = PLAYER_NAME
        changed = True

    if changed:
        with open(conf_path, "w") as f:
            cfg.write(f)
        print(f"[ARIA] Config updated ✅  (username: {PLAYER_NAME})")


# ════════════════════════════════════════════════════════════════
#  STEP 4 — Write liveapi.json into Apex folder
# ════════════════════════════════════════════════════════════════

def setup_liveapi():
    config = {
        "cl_liveapi_enabled": True,
        "cl_liveapi_use_websocket": True,
        "cl_liveapi_websocket_keepalive_enabled": True,
        "cl_liveapi_websocket_keepalive_interval": 30,
        "cl_liveapi_ws_datacenter_only": True,
        "cl_liveapi_ws_retry_count": 5,
        "cl_liveapi_ws_retry_time": 10,
        "cl_liveapi_requests": [
            {"url": "ws://127.0.0.1:7777", "useMessagePack": False}
        ],
    }
    json_str = json.dumps(config, indent=2)

    # Always write a local copy
    local = ARIA_DIR / "liveapi.json"
    local.write_text(json_str)

    # Write to Apex folder if it exists
    target = Path(APEX_LIVEAPI)
    if target.parent.exists():
        try:
            target.write_text(json_str)
            print(f"[ARIA] liveapi.json written to Apex folder ✅")
        except PermissionError:
            print(f"[ARIA] ⚠️  Couldn't write to Apex folder (permission denied).")
            print(f"       Manually copy  aria\\liveapi.json  →  {target.parent}")
    else:
        print(f"[ARIA] Apex LiveAPI folder not found yet.")
        print(f"       Run Apex once, then copy  aria\\liveapi.json  →  {target.parent}")


# ════════════════════════════════════════════════════════════════
#  STEP 5 — Create LAUNCH_APEX.bat (one-click Apex with Live API)
# ════════════════════════════════════════════════════════════════

def create_apex_launcher():
    bat = ARIA_DIR / "LAUNCH_APEX.bat"
    bat.write_text(f"""@echo off
title Launch Apex Legends — Aria Live API
echo.
echo  Launching Apex Legends with Aria Live API enabled...
echo  (make sure ARIA_START.bat is already running)
echo.
start "" "{STEAM_PATH}" -applaunch 1172470 +cl_liveapi_enabled 1 +cl_liveapi_use_websocket 1
timeout /t 3 /nobreak >nul
""")
    print("[ARIA] LAUNCH_APEX.bat created ✅  (use this to start Apex every session)")


# ════════════════════════════════════════════════════════════════
#  STEP 6 — Start OBS
# ════════════════════════════════════════════════════════════════

def start_obs(obs_path: Path | None):
    if not obs_path:
        print("[ARIA] Skipping OBS launch — not found.")
        return

    # Check if OBS is already running
    try:
        import psutil
        if any("obs" in p.name().lower() for p in psutil.process_iter(["name"])):
            print("[ARIA] OBS is already running ✅")
            return
    except Exception:
        pass

    try:
        subprocess.Popen(
            [str(obs_path), "--minimize-to-tray", "--startreplaybuffer"],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        print("[ARIA] OBS launched with replay buffer ✅")
        print("[ARIA] OBS setup (first time only):")
        print("       Tools → WebSocket Server → Enable WebSocket Server → Apply")
        time.sleep(3)
    except Exception as e:
        print(f"[ARIA] OBS launch failed: {e}")


# ════════════════════════════════════════════════════════════════
#  STEP 7 — GameSir G7 Pro live button display
# ════════════════════════════════════════════════════════════════

BUTTON_MAP = {
    "BTN_SOUTH":  "A",
    "BTN_EAST":   "B",
    "BTN_WEST":   "X",
    "BTN_NORTH":  "Y",
    "BTN_TL":     "LB",
    "BTN_TR":     "RB",
    "BTN_TL2":    "LT",
    "BTN_TR2":    "RT",
    "BTN_SELECT": "BACK",
    "BTN_START":  "START",
    "BTN_THUMBL": "LS",
    "BTN_THUMBR": "RS",
    "ABS_HAT0X":  "DPAD◄►",
    "ABS_HAT0Y":  "DPAD▲▼",
}


def start_button_display():
    def _run():
        try:
            import inputs
            held = set()
            print("\n[ARIA] 🎮 GameSir G7 Pro — live button display active")
            print("─" * 50)
            while True:
                try:
                    for event in inputs.get_gamepad():
                        label = BUTTON_MAP.get(event.code, event.code)
                        if event.ev_type == "Key":
                            if event.state == 1:
                                held.add(label)
                            elif event.state == 0:
                                held.discard(label)
                        display = "  ".join(sorted(held)) if held else "· · ·"
                        print(f"\r🎮  [ {display} ]          ", end="", flush=True)
                except inputs.UnpluggedError:
                    print("\r[ARIA] Controller unplugged — reconnect GameSir G7 Pro", end="")
                    time.sleep(2)
        except ImportError:
            print("[ARIA] ⚠️  inputs package missing — run: pip install inputs==0.5")
        except Exception as e:
            print(f"\n[ARIA] Button display stopped: {e}")

    threading.Thread(target=_run, daemon=True, name="AriaButtonDisplay").start()


# ════════════════════════════════════════════════════════════════
#  Aria's intro — she speaks when everything is ready
# ════════════════════════════════════════════════════════════════

def aria_intro():
    """
    Aria introduces herself when all systems are up.
    Tries to use Coqui TTS for voice. Falls back to text-only.
    """
    speech = (
        f"Hey. I'm Aria. Your coach, your analyst, your second set of eyes. "
        f"I've been watching every match, and I will not let you waste this season. "
        f"You're {PLAYER_HANDLE} — {PLAYER_NAME} in-game — "
        f"Gold Four right now, but that's not where you stay. "
        f"We're going to Predator. Not maybe. Not eventually. We are going. "
        f"I'll be here after every match. I'll show you exactly what went wrong, "
        f"exactly what to fix, and exactly what you're doing right. "
        f"Main {LEGEND_MAIN}. Use Void Passage to reposition mid-fight — stop peeking the same angle twice. "
        f"Now launch Apex. I'll be watching."
    )

    # Print the intro regardless of TTS
    print("\n" + "═" * 56)
    print("  ARIA — INTRODUCTION")
    print("═" * 56)
    # Word-wrap at ~54 chars
    words  = speech.split()
    line   = ""
    for word in words:
        if len(line) + len(word) + 1 > 54:
            print(f"  {line}")
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        print(f"  {line}")
    print("═" * 56 + "\n")

    # Try TTS voice
    def _speak():
        try:
            from TTS.api import TTS
            tts = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC", progress_bar=False)
            out = str(ARIA_DIR / "logs" / "aria_intro.wav")
            tts.tts_to_file(text=speech, file_path=out)
            # Play it
            if os.name == "nt":
                import winsound
                winsound.PlaySound(out, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            pass  # TTS is optional — text display is enough

    threading.Thread(target=_speak, daemon=True, name="AriaIntroVoice").start()


# ════════════════════════════════════════════════════════════════
#  Banner
# ════════════════════════════════════════════════════════════════

def print_banner(local_ip: str):
    cfg = configparser.ConfigParser()
    cfg.read(ARIA_DIR / "config" / "aria.conf")
    rank    = cfg.get("player", "current_rank", fallback="Gold 4")
    rp      = cfg.get("player", "current_rp",   fallback="143")
    api_ok  = bool(OPENAI_API_KEY or cfg.get("analysis", "openai_api_key", fallback=""))
    api_str = "✅ set" if api_ok else "❌ MISSING — add to SETTINGS above"

    print(f"""
╔══════════════════════════════════════════════════════╗
║                    ARIA SYSTEM                       ║
║              Road to Predator                        ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  Player:   {PLAYER_NAME:<25} ║
║  Handle:   {PLAYER_HANDLE:<25} ║
║  Coach:    Aria ({COACH_HANDLE})                  ║
║  Rank:     {rank:<20} {rp} RP               ║
║  Target:   Predator                                  ║
║  Legend:   {LEGEND_MAIN} (Skirmisher)                      ║
║                                                      ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  OpenAI:   {api_str:<41}║
║  Kill feed: Apex Live API (no OCR, instant)          ║
║  Recording: OBS Replay Buffer (90s)                  ║
║  Controller: GameSir G7 Pro 8K                       ║
║                                                      ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  Mobile companion: http://{local_ip}:{MOBILE_PORT}
║                                                      ║
║  ► Double-click  LAUNCH_APEX.bat  to start Apex      ║
║  ► Aria appears automatically after every match      ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
""")


# ════════════════════════════════════════════════════════════════
#  Get local IP
# ════════════════════════════════════════════════════════════════

def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


# ════════════════════════════════════════════════════════════════
#  MAIN — runs everything in sequence
# ════════════════════════════════════════════════════════════════

def main():
    print(__doc__)

    # 1. Python packages
    install_packages()

    # Now loguru is available
    from loguru import logger
    logger.remove()
    logger.add(sys.stdout, level="INFO",
               format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}")
    logger.add("logs/aria.log", level="DEBUG", rotation="50 MB",
               format="{time} | {level} | {message}")

    # 2. Create folders
    for folder in ["data/clips","data/sessions","data/reports","data/youtube",
                   "data/annotated","logs","assets/sprites","assets/templates"]:
        os.makedirs(folder, exist_ok=True)

    # 3. Patch config
    patch_config()

    # 4. OBS — install if needed, then launch
    obs_path = install_obs()
    start_obs(obs_path)

    # 5. Apex Live API setup
    setup_liveapi()

    # 6. Apex launcher shortcut
    create_apex_launcher()

    # 7. GameSir button display
    start_button_display()

    # 8. Load flat config
    cfg = configparser.ConfigParser()
    cfg.read(ARIA_DIR / "config" / "aria.conf")
    flat = {}
    for section in cfg.sections():
        for key, val in cfg.items(section):
            flat[key] = val
    if OPENAI_API_KEY:
        flat["openai_api_key"] = OPENAI_API_KEY

    # 9. Banner + local IP
    local_ip = get_local_ip()
    print_banner(local_ip)

    # 10. Aria's intro speech
    aria_intro()

    # 11. Start Aria system
    _launch_aria(flat, logger)


def _launch_aria(config: dict, logger):
    """Start the full Aria system, using Live API if available."""

    use_live_api = Path(ARIA_DIR / "core" / "apex_live_api.py").exists()

    try:
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QTimer
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)

        system = _build_aria(config, use_live_api, logger)
        system.start()
        logger.info("Aria is active. Waiting for Apex...")

        # Show Aria's intro overlay 2 seconds after startup
        def _show_intro():
            try:
                from overlay.aria_overlay import AriaOverlay
                overlay = AriaOverlay(config)
                overlay.show_intro(
                    player_name=PLAYER_NAME,
                    player_handle=PLAYER_HANDLE,
                )
                app._aria_intro_overlay = overlay  # prevent garbage collection
            except Exception as e:
                logger.warning(f"Intro overlay failed: {e}")

        QTimer.singleShot(2000, _show_intro)  # 2 second delay after startup

        try:
            sys.exit(app.exec_())
        except (SystemExit, KeyboardInterrupt):
            system.stop()

    except ImportError:
        logger.warning("PyQt5 not installed — running without overlay (pip install PyQt5)")
        system = _build_aria(config, use_live_api, logger)
        system.start()
        logger.info("Aria is active. Waiting for Apex...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            system.stop()

    logger.info("Aria stopped. GG.")


def _build_aria(config: dict, use_live_api: bool, logger):
    """Build and return an AriaSystem, with Live API patched in if available."""
    import main as aria_main

    if use_live_api:
        try:
            import core.apex_live_api as live_mod

            _orig_start = aria_main.AriaSystem.start

            def _patched_start(self):
                self.running = True

                try:
                    from core.system_detector import load_profile, print_profile
                    print_profile(load_profile())
                except Exception as e:
                    logger.warning(f"System detection: {e}")

                try:
                    from clips.obs_clip_manager import OBSClipManager
                    self.clip_manager = OBSClipManager(self.config)
                    if self.clip_manager.connect():
                        logger.info("OBS connected ✅")
                    else:
                        logger.warning("OBS not connected — check OBS WebSocket Server is enabled")
                except Exception as e:
                    logger.warning(f"OBS: {e}")

                try:
                    from core.controller_logger import ControllerLogger
                    self.controller = ControllerLogger(self.config)
                    if self.controller.start():
                        logger.info("GameSir G7 Pro logging started ✅")
                    else:
                        logger.warning("Controller not found — connect GameSir via USB")
                except Exception as e:
                    logger.warning(f"Controller: {e}")

                # Live API — primary event source
                try:
                    self.killfeed = live_mod.ApexLiveAPI(
                        self.config, event_callback=self._on_game_event
                    )
                    if self.killfeed.start():
                        logger.info("Apex Live API active ✅  (no OCR needed)")
                    else:
                        raise RuntimeError("Live API start returned False")
                except Exception as e:
                    logger.warning(f"Live API failed ({e}) — falling back to OCR")
                    try:
                        from core.killfeed_detector import KillFeedDetector
                        self.killfeed = KillFeedDetector(
                            self.config, event_callback=self._on_game_event
                        )
                        self.killfeed.start()
                        logger.info("OCR kill feed fallback started")
                    except Exception as e2:
                        logger.warning(f"OCR fallback also failed: {e2}")

                self._start_mobile_server()
                self._start_match_watcher()
                logger.info("All systems running — launch Apex and play 🎮")

            aria_main.AriaSystem.start = _patched_start
            logger.info("Live API patched into Aria system ✅")

        except Exception as e:
            logger.warning(f"Live API patch failed: {e} — using original start")

    return aria_main.AriaSystem(config)


if __name__ == "__main__":
    main()
