"""
╔══════════════════════════════════════════════════════════════╗
║               ARIA — ALL IN ONE                              ║
║                                                              ║
║  One file. Everything. Run it and Aria is alive.             ║
║                                                              ║
║    ✅  Installs all missing Python packages                   ║
║    ✅  Downloads & installs OBS if not found                  ║
║    ✅  Starts OBS with replay buffer ready                    ║
║    ✅  Writes liveapi.json so Apex Live API works             ║
║    ✅  Creates LAUNCH_APEX.bat (one-click Apex launcher)      ║
║    ✅  Connects to Apex Live API (no OCR, no lag)             ║
║    ✅  Logs GameSir G7 Pro inputs + shows live button display ║
║    ✅  Starts mobile companion server                         ║
║    ✅  Runs Aria's coaching overlay after every match         ║
║    ✅  Uploads weekly YouTube video automatically             ║
║    ✅  Posts to Twitter/X and Reddit as Aria                  ║
║                                                              ║
║  HOW TO USE EVERY SESSION:                                   ║
║    python ARIA_ALL_IN_ONE.py                                 ║
║    Then double-click  LAUNCH_APEX.bat  to start Apex         ║
║                                                              ║
║  FIRST RUN:                                                  ║
║    Set NIM_API_KEY below (build.nvidia.com — free credits)   ║
║                                                              ║
║  Player: Hidarikikinoaku (LeftHandDevil)                     ║
║  Coach:  Aria (@migikonokami / RightHandGod)                 ║
╚══════════════════════════════════════════════════════════════╝
"""

# ════════════════════════════════════════════════════════════════
#  SETTINGS  —  fill these in once, never touch again
# ════════════════════════════════════════════════════════════════

NIM_API_KEY     = ""          # Primary. Free credits at build.nvidia.com (sign up → API Key)
OPENAI_API_KEY  = ""          # Fallback. Set AI_BACKEND = "openai" below to use instead
AI_BACKEND      = "nim"       # "nim" (default, free) or "openai"
OBS_PASSWORD    = ""          # Only if you set a password in OBS WebSocket settings
MOBILE_PORT     = 8765        # Port your phone connects to

# Paths — defaults work for most installs
OBS_PATH     = r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"
STEAM_PATH   = r"C:\Program Files (x86)\Steam\steam.exe"
APEX_LIVEAPI = r"C:\Program Files (x86)\Steam\steamapps\common\Apex Legends\LiveAPI\liveapi.json"

# Social (optional — leave blank to skip posting)
TWITTER_API_KEY       = ""
TWITTER_API_SECRET    = ""
TWITTER_ACCESS_TOKEN  = ""
TWITTER_ACCESS_SECRET = ""
REDDIT_CLIENT_ID      = ""
REDDIT_CLIENT_SECRET  = ""

# ════════════════════════════════════════════════════════════════
#  IMPORTS
# ════════════════════════════════════════════════════════════════

import sys
import os
import subprocess
import time
import threading
import socket
import json
import configparser
import asyncio
import urllib.request
import re
import math
import base64
import shutil
import schedule
import random
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

# Third-party — installed at runtime if missing
try:
    from loguru import logger
    _LOGURU_READY = True
except ImportError:
    import logging
    logger = logging.getLogger("aria")
    _LOGURU_READY = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    import mss
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

try:
    import inputs
    INPUTS_AVAILABLE = True
except ImportError:
    INPUTS_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import obsws_python as obs
    OBS_AVAILABLE = True
except ImportError:
    OBS_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# ── AI backend factory ────────────────────────────────────────────────────────
_NIM_BASE_URL        = "https://integrate.api.nvidia.com/v1"
_NIM_VISION_MODEL    = "qwen/qwen3.5-vl"
_NIM_TEXT_MODEL      = "qwen/qwen3.5-vl"
_OPENAI_VISION_MODEL = "gpt-4o"
_OPENAI_TEXT_MODEL   = "gpt-4o"

def _build_ai_client(config: dict):
    """Return (OpenAI-compatible client, vision_model, text_model) or (None, …)."""
    if not OPENAI_AVAILABLE:
        return None, _NIM_VISION_MODEL, _NIM_TEXT_MODEL

    backend = config.get("ai_backend", AI_BACKEND).lower()

    if backend == "openai":
        key = config.get("openai_api_key", OPENAI_API_KEY).strip()
        if not key:
            return None, _OPENAI_VISION_MODEL, _OPENAI_TEXT_MODEL
        return OpenAI(api_key=key), _OPENAI_VISION_MODEL, _OPENAI_TEXT_MODEL
    else:  # nim (default)
        key = config.get("nim_api_key", NIM_API_KEY).strip()
        if not key:
            return None, _NIM_VISION_MODEL, _NIM_TEXT_MODEL
        return OpenAI(base_url=_NIM_BASE_URL, api_key=key), _NIM_VISION_MODEL, _NIM_TEXT_MODEL
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

try:
    from moviepy.editor import (
        VideoFileClip, concatenate_videoclips,
        AudioFileClip, CompositeVideoClip, TextClip,
    )
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False

try:
    from googleapiclient.discovery import build as yt_build
    from googleapiclient.http import MediaFileUpload
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request as GRequest
    from google.oauth2.credentials import Credentials
    YOUTUBE_API_AVAILABLE = True
except ImportError:
    YOUTUBE_API_AVAILABLE = False

try:
    import tweepy
    TWEEPY_AVAILABLE = True
except ImportError:
    TWEEPY_AVAILABLE = False

try:
    import praw
    PRAW_AVAILABLE = True
except ImportError:
    PRAW_AVAILABLE = False

try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QLabel,
        QPushButton, QVBoxLayout, QHBoxLayout, QTextEdit, QFrame,
    )
    from PyQt5.QtCore import (
        Qt, QTimer, QPropertyAnimation, QEasingCurve,
        QThread, pyqtSignal,
    )
    from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QPen, QBrush
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False

try:
    from TTS.api import TTS as CoquiTTS
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

# ════════════════════════════════════════════════════════════════
#  CONSTANTS
# ════════════════════════════════════════════════════════════════

ARIA_DIR     = Path(__file__).parent
PLAYER_NAME  = "Hidarikikinoaku"
PLAYER_HANDLE= "LeftHandDevil"
COACH_HANDLE = "@migikonokami"
LEGEND_MAIN  = "Alter"

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

# Overlay colour palette
C = {
    "red":    "#C0392B",
    "blue":   "#2E86AB",
    "silver": "#BDC3C7",
    "panel":  "#1A1A2E",
    "text":   "#ECEFF1",
    "muted":  "#B0BEC5",
    "gold":   "#F39C12",
    "green":  "#27AE60",
    "danger": "#E74C3C",
}

IDLE = "idle"; TALKING = "talking"; POINTING = "pointing"
PROUD = "proud"; CONCERNED = "concerned"; THINKING = "thinking"

# Kill-feed screen regions (% of screen)
KILLFEED_REGION = {"left_pct": 0.72, "top_pct": 0.03,
                   "width_pct": 0.27, "height_pct": 0.30}
DAMAGE_REGION   = {"left_pct": 0.55, "top_pct": 0.30,
                   "width_pct": 0.40, "height_pct": 0.40}

# Live API event categories
CAT_PLAYER_KILLED      = "playerKilled"
CAT_PLAYER_DOWN        = "playerDown"
CAT_PLAYER_DAMAGED     = "playerDamaged"
CAT_MATCH_START        = "matchStart"
CAT_MATCH_STATE_END    = "matchStateEnd"
CAT_GAME_STATE_CHANGED = "gameStateChanged"
CAT_INIT               = "init"

# ════════════════════════════════════════════════════════════════
#  ENUMS & CORE DATACLASSES
# ════════════════════════════════════════════════════════════════

class EventType(Enum):
    KNOCK_BY_YOU     = "knock_by_you"
    KILL_BY_YOU      = "kill_by_you"
    KNOCKED_BY_ENEMY = "knocked_by_enemy"
    KILLED_BY_ENEMY  = "killed_by_enemy"
    REVIVED          = "revived"
    CHAMPION         = "champion"
    RING_CLOSE       = "ring_close"


@dataclass
class GameEvent:
    event_type: EventType
    timestamp:  float
    player:     str
    target:     str
    weapon:     str = ""
    damage:     int = 0
    clip_path:  str = ""
    session_id: str = ""


@dataclass
class SystemProfile:
    cpu_name:  str   = ""
    cpu_cores: int   = 0
    cpu_threads: int = 0
    ram_gb:    float = 0.0
    gpu_name:  str   = ""
    gpu_vram_gb: float = 0.0
    gpu_vendor: str  = ""
    can_run_stable_diffusion: bool = False
    can_run_whisper_local:    bool = False
    can_run_coqui_tts:        bool = False
    can_run_llm_local:        bool = False
    use_api_vision:           bool = True
    mode: str = "api"


@dataclass
class FightAnalysis:
    clip_path:           str   = ""
    event_type:          str   = ""
    timestamp:           float = 0.0
    analyzed_at:         str   = field(default_factory=lambda: datetime.now().isoformat())
    legend_played:       str   = "Alter"
    overall_verdict:     str   = ""
    fight_quality:       str   = ""
    primary_fix:         str   = ""
    key_moment:          str   = ""
    key_moment_time:     float = 0.0
    positioning_score:   float = 0.0
    movement_score:      float = 0.0
    aim_score:           float = 0.0
    decision_score:      float = 0.0
    overall_score:       float = 0.0
    what_went_wrong:     str   = ""
    what_went_right:     str   = ""
    specific_drill:      str   = ""
    aria_quote:          str   = ""
    controller_context:  str   = ""
    damage_dealt:        int   = 0
    damage_taken:        int   = 0
    attacker_name:       str   = ""
    frames_analyzed:     int   = 0
    model_used:          str   = ""
    api_cost_estimate:   float = 0.0


@dataclass
class ControllerState:
    timestamp:     float = 0.0
    left_x:        float = 0.0
    left_y:        float = 0.0
    right_x:       float = 0.0
    right_y:       float = 0.0
    left_trigger:  float = 0.0
    right_trigger: float = 0.0
    btn_a: bool = False
    btn_b: bool = False
    btn_x: bool = False
    btn_y: bool = False
    lb:    bool = False
    rb:    bool = False
    ls_click: bool = False
    rs_click: bool = False
    dpad_up:    bool = False
    dpad_down:  bool = False
    dpad_left:  bool = False
    dpad_right: bool = False
    start:  bool = False
    select: bool = False
    is_moving:       bool  = False
    is_aiming:       bool  = False
    is_firing:       bool  = False
    movement_speed:  float = 0.0
    aim_speed:       float = 0.0


@dataclass
class InputEvent:
    timestamp:      float
    event_type:     str
    input_name:     str
    value:          float
    state_snapshot: dict = None

# ════════════════════════════════════════════════════════════════
#  STEP 1 — Install missing Python packages
# ════════════════════════════════════════════════════════════════

REQUIRED_PACKAGES = {
    "loguru":     "loguru==0.7.2",
    "openai":     "openai==1.30.1",
    "cv2":        "opencv-python==4.9.0.80",
    "websockets": "websockets==12.0",
    "mss":        "mss==9.0.1",
    "PIL":        "Pillow==10.3.0",
    "fastapi":    "fastapi==0.111.0",
    "uvicorn":    "uvicorn==0.29.0",
    "numpy":      "numpy==1.26.4",
    "inputs":     "inputs==0.5",
    "schedule":   "schedule==1.2.1",
    "pydantic":   "pydantic==2.7.1",
    "rich":       "rich==13.7.1",
    "psutil":     "psutil==5.9.8",
    "tweepy":     "tweepy==4.14.0",
    "praw":       "praw==7.7.1",
    "aiohttp":    "aiohttp==3.9.5",
    "requests":   "requests==2.32.2",
    "moviepy":    "moviepy==1.0.3",
    "obsws":      "obs-websocket-py==1.0.0",
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
    print(f"[ARIA] Installing {len(missing)} missing package(s)...")
    for pkg in missing:
        print(f"  → {pkg} ...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
            capture_output=True
        )
        if result.returncode != 0:
            print(f"    ⚠️  {pkg} failed — {result.stderr.decode()[:80]}")
    print("[ARIA] Packages ready ✅\n")


# ════════════════════════════════════════════════════════════════
#  SYSTEM DETECTOR
# ════════════════════════════════════════════════════════════════

def _detect_gpu_windows(profile: SystemProfile) -> SystemProfile:
    try:
        result = subprocess.run(
            ["wmic", "path", "win32_VideoController",
             "get", "name,AdapterRAM", "/format:csv"],
            capture_output=True, text=True, timeout=10
        )
        for line in [l.strip() for l in result.stdout.splitlines() if l.strip()]:
            parts = line.split(",")
            if len(parts) >= 3:
                name = parts[2].strip()
                if name and name.lower() not in ("name", ""):
                    profile.gpu_name = name
                    try:
                        profile.gpu_vram_gb = round(int(parts[1].strip()) / (1024**3), 1)
                    except (ValueError, TypeError):
                        profile.gpu_vram_gb = 0.0
                    n = name.lower()
                    if any(x in n for x in ("nvidia","geforce","rtx","gtx")):
                        profile.gpu_vendor = "nvidia"
                    elif any(x in n for x in ("amd","radeon","rx ")):
                        profile.gpu_vendor = "amd"
                    elif "intel" in n:
                        profile.gpu_vendor = "intel"
                    break
    except Exception as e:
        logger.warning(f"GPU detection failed: {e}")
    return profile


def _detect_gpu_linux(profile: SystemProfile) -> SystemProfile:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(",")
            if len(parts) >= 2:
                profile.gpu_name = parts[0].strip()
                profile.gpu_vram_gb = round(float(parts[1].strip()) / 1024, 1)
                profile.gpu_vendor = "nvidia"
                return profile
    except FileNotFoundError:
        pass
    try:
        result = subprocess.run(["lspci"], capture_output=True, text=True, timeout=10)
        for line in result.stdout.splitlines():
            if "VGA" in line or "3D" in line:
                profile.gpu_name = line.split(":")[-1].strip()
                if "AMD" in line or "Radeon" in line:
                    profile.gpu_vendor = "amd"
                elif "NVIDIA" in line:
                    profile.gpu_vendor = "nvidia"
                elif "Intel" in line:
                    profile.gpu_vendor = "intel"
                break
    except FileNotFoundError:
        pass
    return profile


def detect_system() -> SystemProfile:
    profile = SystemProfile()
    profile.cpu_name = platform.processor() if "platform" in dir() else ""
    try:
        import platform as _plat
        profile.cpu_name = _plat.processor()
        os_type = _plat.system()
    except Exception:
        os_type = "Unknown"
    if PSUTIL_AVAILABLE:
        try:
            profile.cpu_cores   = psutil.cpu_count(logical=False) or 0
            profile.cpu_threads = psutil.cpu_count(logical=True)  or 0
            profile.ram_gb      = round(psutil.virtual_memory().total / (1024**3), 1)
        except Exception:
            pass
    if os_type == "Windows":
        profile = _detect_gpu_windows(profile)
    elif os_type == "Linux":
        profile = _detect_gpu_linux(profile)
    vram = profile.gpu_vram_gb
    ram  = profile.ram_gb
    v    = profile.gpu_vendor
    if ram >= 8:
        profile.can_run_coqui_tts = True
    if v in ("nvidia","amd") and vram >= 4.0:
        profile.can_run_stable_diffusion = True
        profile.can_run_whisper_local    = True
    elif ram >= 16:
        profile.can_run_whisper_local = True
    if v in ("nvidia","amd") and vram >= 8.0:
        profile.can_run_llm_local = True
    profile.use_api_vision = True
    if profile.can_run_stable_diffusion and profile.can_run_coqui_tts:
        profile.mode = "local" if profile.can_run_llm_local else "hybrid"
    else:
        profile.mode = "api"
    return profile


def load_system_profile() -> SystemProfile:
    path = ARIA_DIR / "config" / "system_profile.json"
    if path.exists():
        try:
            with open(path) as f:
                return SystemProfile(**json.load(f))
        except Exception:
            pass
    profile = detect_system()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(asdict(profile), f, indent=2)
    return profile


def print_system_profile(profile: SystemProfile):
    print("\n" + "="*55)
    print("  ARIA — SYSTEM PROFILE")
    print("="*55)
    print(f"  GPU:  {profile.gpu_name or 'Not detected'} ({profile.gpu_vram_gb}GB VRAM)")
    print(f"  RAM:  {profile.ram_gb}GB    Mode: {profile.mode.upper()}")
    print(f"  TTS:  {'✅' if profile.can_run_coqui_tts else '❌'}   "
          f"Vision API: {'✅' if profile.use_api_vision else '❌'}")
    print("="*55 + "\n")


# ════════════════════════════════════════════════════════════════
#  OBS CLIP MANAGER
# ════════════════════════════════════════════════════════════════

class OBSClipManager:
    def __init__(self, config: dict):
        self.host           = config.get("obs_host", "localhost")
        self.port           = int(config.get("obs_port", 4455))
        self.password       = config.get("obs_password", "")
        self.clips_folder   = Path(config.get("clips_folder", "data/clips"))
        self.clip_before    = int(config.get("clip_before_event", 20))
        self.clip_after     = int(config.get("clip_after_event", 8))
        self.session_id     = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.client         = None
        self.connected      = False
        self.pending_events: list[GameEvent] = []
        self.session_folder = self.clips_folder / self.session_id
        self.session_folder.mkdir(parents=True, exist_ok=True)

    def connect(self) -> bool:
        if not OBS_AVAILABLE:
            logger.warning("obsws_python not installed — OBS disabled")
            return False
        try:
            self.client    = obs.ReqClient(host=self.host, port=self.port,
                                           password=self.password, timeout=3)
            self.connected = True
            self._check_replay_buffer()
            return True
        except Exception as e:
            self.connected = False
            logger.warning(f"OBS connect failed: {e}")
            return False

    def disconnect(self):
        if self.client and self.connected:
            try:
                self.client.disconnect()
            except Exception:
                pass
            self.connected = False

    def _check_replay_buffer(self):
        try:
            status = self.client.get_replay_buffer_status()
            if not status.output_active:
                self.client.start_replay_buffer()
                logger.info("Replay buffer started ✅")
            else:
                logger.info("Replay buffer already active ✅")
        except Exception as e:
            logger.warning(f"Replay buffer check: {e}")

    def save_clip(self, event: GameEvent) -> str | None:
        if not self.connected:
            return None
        try:
            time.sleep(self.clip_after)
            self.client.save_replay_buffer()
            time.sleep(2)
            clip_path = self._find_latest_obs_file()
            if not clip_path:
                return None
            organized = self._organize_clip(clip_path, event)
            event.clip_path = str(organized)
            self.pending_events.append(event)
            logger.info(f"Clip saved: {organized.name}")
            return str(organized)
        except Exception as e:
            logger.error(f"Clip save failed: {e}")
            return None

    def _find_latest_obs_file(self) -> Path | None:
        dirs = [Path.home() / "Videos",
                Path.home() / "Videos" / "Apex Legends"]
        latest_file, latest_time = None, 0
        for folder in dirs:
            if not folder.exists():
                continue
            for ext in ("*.mp4", "*.mkv"):
                for f in folder.glob(ext):
                    if f.stat().st_mtime > latest_time:
                        latest_time = f.stat().st_mtime
                        latest_file = f
        if latest_file and (time.time() - latest_time) < 30:
            return latest_file
        return None

    def _organize_clip(self, raw_path: Path, event: GameEvent) -> Path:
        ext      = raw_path.suffix
        ts       = datetime.now().strftime("%H%M%S")
        count    = len(list(self.session_folder.glob("*.mp4"))) + 1
        filename = f"{event.event_type.value}_{ts}_{count:03d}{ext}"
        dest     = self.session_folder / filename
        shutil.move(str(raw_path), str(dest))
        meta = {
            "event_type": event.event_type.value,
            "timestamp":  event.timestamp,
            "player":     event.player,
            "target":     event.target,
            "session_id": self.session_id,
            "clip_file":  filename,
        }
        with open(dest.with_suffix(".json"), "w") as f:
            json.dump(meta, f, indent=2)
        return dest

    def get_session_clips(self) -> list[dict]:
        clips = []
        for meta_file in self.session_folder.glob("*.json"):
            try:
                with open(meta_file) as f:
                    meta = json.load(f)
                clip_file = self.session_folder / meta["clip_file"]
                if clip_file.exists():
                    meta["clip_path"] = str(clip_file)
                    clips.append(meta)
            except Exception:
                pass
        clips.sort(key=lambda x: x.get("timestamp", 0))
        return clips

    def bucket_clips(self) -> tuple[list, list]:
        clips      = self.get_session_clips()
        highlights = [c for c in clips if c.get("event_type") in
                      (EventType.KNOCK_BY_YOU.value, EventType.KILL_BY_YOU.value)]
        mistakes   = [c for c in clips if c.get("event_type") in
                      (EventType.KNOCKED_BY_ENEMY.value, EventType.KILLED_BY_ENEMY.value)]
        return highlights, mistakes

    def end_session(self) -> dict:
        highlights, mistakes = self.bucket_clips()
        summary = {
            "session_id":     self.session_id,
            "session_folder": str(self.session_folder),
            "total_clips":    len(highlights) + len(mistakes),
            "highlights":     highlights,
            "mistakes":       mistakes,
            "knock_count":    len([h for h in highlights
                                   if h["event_type"] == EventType.KNOCK_BY_YOU.value]),
            "kill_count":     len([h for h in highlights
                                   if h["event_type"] == EventType.KILL_BY_YOU.value]),
            "down_count":     len([m for m in mistakes
                                   if m["event_type"] == EventType.KNOCKED_BY_ENEMY.value]),
            "death_count":    len([m for m in mistakes
                                   if m["event_type"] == EventType.KILLED_BY_ENEMY.value]),
        }
        with open(self.session_folder / "session_summary.json", "w") as f:
            json.dump(summary, f, indent=2)
        logger.info(f"Session ended | Knocks: {summary['knock_count']} | "
                    f"Deaths: {summary['death_count']} | Clips: {summary['total_clips']}")
        return summary

# ════════════════════════════════════════════════════════════════
#  KILL FEED DETECTOR  (OCR fallback)
# ════════════════════════════════════════════════════════════════

class KillFeedDetector:
    def __init__(self, config: dict, event_callback=None):
        self.username       = config.get("apex_username", PLAYER_NAME)
        self.poll_interval  = float(config.get("poll_interval", 0.5))
        self.ocr_confidence = float(config.get("ocr_confidence", 0.65))
        self.event_callback = event_callback
        self._running       = False
        self._thread        = None
        self._reader        = None
        self._screen_w      = 1920
        self._screen_h      = 1080
        self._last_events: dict[str, float] = {}
        self._dedupe_window = 3.0
        self.session_events: list[GameEvent] = []
        self.session_start  = time.time()

    def start(self) -> bool:
        if not MSS_AVAILABLE:
            logger.error("mss not installed"); return False
        if not CV2_AVAILABLE:
            logger.error("opencv not installed"); return False
        if EASYOCR_AVAILABLE:
            logger.info("Loading EasyOCR (first run ~30s)...")
            try:
                self._reader = easyocr.Reader(["en"], gpu=self._has_gpu(), verbose=False)
                logger.info("OCR ready ✅")
            except Exception as e:
                logger.warning(f"EasyOCR init failed: {e}")
        with mss.mss() as sct:
            m = sct.monitors[1]
            self._screen_w = m["width"]; self._screen_h = m["height"]
        self._running = True
        self._thread  = threading.Thread(target=self._detection_loop,
                                         daemon=True, name="AriaOCR")
        self._thread.start()
        logger.info("Kill feed OCR detection started ✅")
        return True

    def stop(self):
        self._running = False
        if self._thread: self._thread.join(timeout=3)

    def _has_gpu(self) -> bool:
        try:
            import torch; return torch.cuda.is_available()
        except ImportError:
            return False

    def _capture_region(self, region: dict):
        try:
            with mss.mss() as sct:
                img = np.array(sct.grab({
                    "left": region["left"], "top": region["top"],
                    "width": region["width"], "height": region["height"],
                }))
                return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        except Exception:
            return None

    def _read_text(self, img) -> list:
        if self._reader is None: return []
        gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w  = gray.shape
        gray  = cv2.resize(gray, (w*2, h*2), interpolation=cv2.INTER_CUBIC)
        _, th = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
        try:
            return [(t.lower().strip(), c)
                    for (_, t, c) in self._reader.readtext(th, detail=1)
                    if c >= self.ocr_confidence]
        except Exception:
            return []

    def _detection_loop(self):
        w, h = self._screen_w, self._screen_h
        region = {
            "left":   int(w * KILLFEED_REGION["left_pct"]),
            "top":    int(h * KILLFEED_REGION["top_pct"]),
            "width":  int(w * KILLFEED_REGION["width_pct"]),
            "height": int(h * KILLFEED_REGION["height_pct"]),
        }
        while self._running:
            try:
                img = self._capture_region(region)
                if img is not None:
                    self._analyze_killfeed(img)
            except Exception as e:
                logger.debug(f"OCR loop: {e}")
            time.sleep(self.poll_interval)

    def _analyze_killfeed(self, img):
        texts = self._read_text(img)
        if not texts: return
        full  = " ".join(t[0] for t in texts)
        uname = self.username.lower()
        if uname not in full: return
        event = self._parse_killfeed_text(full, uname)
        if event: self._fire_event(event)

    def _parse_killfeed_text(self, text: str, username: str):
        now = time.time()
        for pattern in [rf"{username}.{{0,20}}knocked down", rf"{username}.{{0,20}}knocked"]:
            if re.search(pattern, text):
                return self._make_event(EventType.KNOCK_BY_YOU, text, username, now)
        for pattern in [rf"{username}.{{0,20}}killed", rf"{username}.{{0,20}}eliminated"]:
            if re.search(pattern, text):
                return self._make_event(EventType.KILL_BY_YOU, text, username, now)
        for pattern in [rf"knocked down.{{0,20}}{username}", rf"knocked.{{0,20}}{username}"]:
            if re.search(pattern, text):
                return self._make_event(EventType.KNOCKED_BY_ENEMY, text, username, now)
        for pattern in [rf"killed.{{0,20}}{username}", rf"eliminated.{{0,20}}{username}"]:
            if re.search(pattern, text):
                return self._make_event(EventType.KILLED_BY_ENEMY, text, username, now)
        return None

    def _make_event(self, etype, text, username, now):
        cleaned = text.replace(username, "")
        for verb in ["knocked down","knocked","killed","eliminated","finished"]:
            cleaned = cleaned.replace(verb, "")
        cleaned = re.sub(r"[^a-zA-Z0-9_\-]", " ", cleaned).strip()
        opponent = " ".join(cleaned.split())[:32] or "unknown"
        return GameEvent(event_type=etype, timestamp=now, player=username,
                         target=opponent,
                         session_id=datetime.now().strftime("%Y%m%d_%H%M%S"))

    def _fire_event(self, event: GameEvent):
        key = f"{event.event_type.value}_{event.target}"
        now = time.time()
        if self._last_events.get(key, 0) and now - self._last_events[key] < self._dedupe_window:
            return
        self._last_events[key] = now
        self.session_events.append(event)
        if self.event_callback:
            threading.Thread(target=self.event_callback, args=(event,),
                             daemon=True).start()

    def detect_match_end(self) -> bool:
        if not (MSS_AVAILABLE and CV2_AVAILABLE): return False
        w, h = self._screen_w, self._screen_h
        region = {"left": int(w*0.30), "top": int(h*0.40),
                  "width": int(w*0.40), "height": int(h*0.20)}
        img = self._capture_region(region)
        if img is None: return False
        texts = self._read_text(img)
        full  = " ".join(t[0] for t in texts)
        for indicator in ["play again","lobby","apex legends","choose legend","ready"]:
            if indicator in full: return True
        return False

    def get_session_summary(self) -> dict:
        knocks = [e for e in self.session_events if e.event_type == EventType.KNOCK_BY_YOU]
        kills  = [e for e in self.session_events if e.event_type == EventType.KILL_BY_YOU]
        downs  = [e for e in self.session_events if e.event_type == EventType.KNOCKED_BY_ENEMY]
        deaths = [e for e in self.session_events if e.event_type == EventType.KILLED_BY_ENEMY]
        return {
            "total_events": len(self.session_events),
            "knocks": len(knocks), "kills": len(kills),
            "downs": len(downs),   "deaths": len(deaths),
            "kd_ratio": round(len(kills)/max(len(deaths),1), 2),
            "session_duration_min": round((time.time()-self.session_start)/60, 1),
        }


# ════════════════════════════════════════════════════════════════
#  APEX LIVE API
# ════════════════════════════════════════════════════════════════

class ApexLiveAPI:
    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 7777

    def __init__(self, config: dict, event_callback=None):
        self.username       = config.get("apex_username", PLAYER_NAME).lower()
        self.event_callback = event_callback
        self.host           = config.get("liveapi_host", self.DEFAULT_HOST)
        self.port           = int(config.get("liveapi_port", self.DEFAULT_PORT))
        self._running       = False
        self._thread        = None
        self._loop          = None
        self._dedupe_window = 3.0
        self._last_events: dict[str, float] = {}
        self.session_events: list[GameEvent] = []
        self.session_start  = time.time()
        self._in_match      = False
        self._match_ended   = False
        self._damage_buffer: dict[str, dict] = {}
        self._damage_window_secs = 8.0

    def start(self) -> bool:
        if not WEBSOCKETS_AVAILABLE:
            logger.error("websockets not installed"); return False
        self._running = True
        self._thread  = threading.Thread(target=self._run_loop, daemon=True,
                                         name="AriaLiveAPI")
        self._thread.start()
        logger.info(f"Live API listener started — ws://{self.host}:{self.port}")
        return True

    def stop(self):
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread: self._thread.join(timeout=5)

    def detect_match_end(self) -> bool:
        if self._match_ended and not self._in_match:
            self._match_ended = False
            return True
        return False

    def get_session_summary(self) -> dict:
        knocks = [e for e in self.session_events if e.event_type == EventType.KNOCK_BY_YOU]
        kills  = [e for e in self.session_events if e.event_type == EventType.KILL_BY_YOU]
        downs  = [e for e in self.session_events if e.event_type == EventType.KNOCKED_BY_ENEMY]
        deaths = [e for e in self.session_events if e.event_type == EventType.KILLED_BY_ENEMY]
        return {
            "total_events": len(self.session_events),
            "knocks": len(knocks), "kills": len(kills),
            "downs": len(downs),   "deaths": len(deaths),
            "kd_ratio": round(len(kills)/max(len(deaths),1), 2),
            "session_duration_min": round((time.time()-self.session_start)/60, 1),
        }

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect_loop())
        finally:
            self._loop.close()

    async def _connect_loop(self):
        uri = f"ws://{self.host}:{self.port}"
        while self._running:
            try:
                async with websockets.connect(
                    uri, ping_interval=20, ping_timeout=10, max_size=2**20
                ) as ws:
                    logger.info("Apex Live API connected ✅")
                    async for raw in ws:
                        if not self._running: break
                        try:
                            await self._dispatch(raw)
                        except Exception as e:
                            logger.debug(f"Event error: {e}")
            except (ConnectionRefusedError, OSError):
                logger.debug("Apex not running — retrying in 5s")
            except Exception as e:
                logger.warning(f"Live API: {e}")
            if self._running:
                await asyncio.sleep(5)

    async def _dispatch(self, raw: str):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        cat   = msg.get("category", "")
        event = msg.get("event", msg)
        if not cat: return
        if   cat == CAT_INIT:               logger.info(f"Live API version: {event.get('apiVersion','?')}")
        elif cat == CAT_MATCH_START:        self._on_match_start(event)
        elif cat == CAT_MATCH_STATE_END:    self._on_match_end(event)
        elif cat == CAT_GAME_STATE_CHANGED: self._on_state_changed(event)
        elif cat == CAT_PLAYER_DOWN:        self._on_player_down(event)
        elif cat == CAT_PLAYER_KILLED:      self._on_player_killed(event)
        elif cat == CAT_PLAYER_DAMAGED:     self._on_player_damaged(event)

    def _on_match_start(self, e):
        self._in_match = True; self._match_ended = False
        self.session_events.clear(); self._damage_buffer.clear()
        self.session_start = time.time()
        logger.info("Match started — session reset ✅")

    def _on_match_end(self, e):
        if not self._in_match: return
        self._in_match = False; self._match_ended = True
        logger.info("Match ended — coaching pipeline triggered")

    def _on_state_changed(self, e):
        if e.get("state","").lower() in ("pregame","lobby","resolution") and self._in_match:
            self._on_match_end(e)

    def _on_player_down(self, e):
        attacker = self._name(e,"attacker"); victim = self._name(e,"victim"); now = time.time()
        if   attacker == self.username: self._fire(EventType.KNOCK_BY_YOU,     victim,   now)
        elif victim   == self.username: self._fire(EventType.KNOCKED_BY_ENEMY, attacker, now)

    def _on_player_killed(self, e):
        attacker = self._name(e,"attacker"); victim = self._name(e,"victim"); now = time.time()
        if   attacker == self.username: self._fire(EventType.KILL_BY_YOU,     victim,   now)
        elif victim   == self.username: self._fire(EventType.KILLED_BY_ENEMY, attacker, now)

    def _on_player_damaged(self, e):
        attacker = self._name(e,"attacker"); victim = self._name(e,"victim")
        amount   = int(e.get("damageInflicted", 0))
        if not amount: return
        key = str(int(time.time() / self._damage_window_secs))
        if key not in self._damage_buffer:
            self._damage_buffer[key] = {"damage_dealt": 0, "damage_taken": 0}
        if   attacker == self.username: self._damage_buffer[key]["damage_dealt"] += amount
        elif victim   == self.username: self._damage_buffer[key]["damage_taken"] += amount
        bucket = int(time.time() / self._damage_window_secs)
        for k in list(self._damage_buffer):
            if int(k) < bucket - 3:
                del self._damage_buffer[k]

    def _fire(self, event_type: EventType, target: str, now: float):
        key = f"{event_type.value}_{target}"
        if self._last_events.get(key, 0) and now - self._last_events[key] < self._dedupe_window:
            return
        self._last_events[key] = now
        bucket = int(now / self._damage_window_secs)
        dealt  = sum(self._damage_buffer.get(str(bucket+o),{}).get("damage_dealt",0) for o in (0,-1))
        taken  = sum(self._damage_buffer.get(str(bucket+o),{}).get("damage_taken",0) for o in (0,-1))
        ge     = GameEvent(event_type=event_type, timestamp=now, player=self.username,
                           target=target or "unknown",
                           session_id=datetime.now().strftime("%Y%m%d_%H%M%S"))
        ge.live_api_context = {"damage_dealt": dealt, "damage_taken": taken, "attacker_name": target}
        arrow = "→" if "by_you" in event_type.value else "←"
        logger.info(f"{arrow} {event_type.value}: {target} | {dealt} dealt / {taken} taken")
        self.session_events.append(ge)
        if self.event_callback:
            threading.Thread(target=self.event_callback, args=(ge,), daemon=True).start()

    def _name(self, event: dict, role: str) -> str:
        obj = event.get(role, {})
        if not isinstance(obj, dict): return ""
        return (obj.get("name") or obj.get("playerName") or "").lower().strip()


# ════════════════════════════════════════════════════════════════
#  CONTROLLER LOGGER
# ════════════════════════════════════════════════════════════════

class ControllerLogger:
    DEADZONE = 0.10

    def __init__(self, config: dict):
        self.session_id    = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_folder    = Path(config.get("input_log_folder", "data/sessions"))
        self.log_folder.mkdir(parents=True, exist_ok=True)
        self.log_file      = self.log_folder / f"{self.session_id}_inputs.jsonl"
        self.deadzone      = float(config.get("stick_deadzone", 0.10))
        self.trigger_dead  = float(config.get("trigger_deadzone", 0.05))
        self.state         = ControllerState()
        self.events: list  = []
        self.session_start = time.time()
        self._running      = False
        self._thread       = None
        self._lock         = threading.Lock()
        self._log_handle   = None
        self._ads_start_time = None
        self._ads_durations  = []
        self._last_state_time = time.time()
        self.stats = {
            "total_inputs": 0, "time_moving": 0.0,
            "time_aiming": 0.0, "time_firing": 0.0,
            "time_moving_while_aiming": 0.0,
            "time_stationary_while_aiming": 0.0,
            "jump_count": 0, "slide_count": 0,
            "ads_activations": 0, "avg_ads_duration_ms": 0.0,
            "fire_bursts": 0, "ability_1_uses": 0,
            "ability_2_uses": 0, "melee_count": 0,
        }

    def start(self) -> bool:
        if not INPUTS_AVAILABLE:
            logger.error("inputs library not available"); return False
        if not self._controller_connected():
            time.sleep(5)
            if not self._controller_connected():
                logger.error("Controller not found — connect GameSir G7 Pro via USB")
                return False
        self._running    = True
        self._log_handle = open(self.log_file, "w")
        self._thread     = threading.Thread(target=self._log_loop, daemon=True,
                                            name="AriaController")
        self._thread.start()
        logger.info("Controller logging started ✅")
        return True

    def stop(self) -> dict:
        self._running = False
        if self._thread: self._thread.join(timeout=3)
        if self._log_handle: self._log_handle.close()
        self._finalize_stats()
        stats_path = self.log_folder / f"{self.session_id}_controller_stats.json"
        with open(stats_path, "w") as f:
            json.dump(self.stats, f, indent=2)
        return self.stats

    def _controller_connected(self) -> bool:
        try:
            return bool(inputs.devices.gamepads)
        except Exception:
            return False

    def _log_loop(self):
        while self._running:
            try:
                for raw in inputs.get_gamepad():
                    if not self._running: break
                    self._process_event(raw)
            except inputs.UnpluggedError:
                logger.warning("Controller unplugged — waiting...")
                time.sleep(2)
            except Exception as e:
                if self._running:
                    logger.error(f"Controller read: {e}")
                    time.sleep(0.1)

    def _process_event(self, raw):
        now     = time.time()
        elapsed = now - self._last_state_time
        self._update_time_stats(elapsed)
        self._last_state_time = now
        code    = raw.code
        value   = raw.state

        def ns(v): return round(max(-1.0, min(1.0, v/32767.0)), 4)
        def nt(v): return round(max(0.0, min(1.0, v/255.0)), 4)
        def dz(v, d): return 0.0 if abs(v) < d else v

        input_event = None
        with self._lock:
            if code == "ABS_X":
                self.state.left_x = dz(ns(value), self.deadzone)
                input_event = InputEvent(now, "stick_move", "LEFT_X", self.state.left_x)
            elif code == "ABS_Y":
                self.state.left_y = dz(ns(value), self.deadzone)
                input_event = InputEvent(now, "stick_move", "LEFT_Y", self.state.left_y)
            elif code == "ABS_RX":
                self.state.right_x = dz(ns(value), self.deadzone)
                input_event = InputEvent(now, "stick_move", "RIGHT_X", self.state.right_x)
            elif code == "ABS_RY":
                self.state.right_y = dz(ns(value), self.deadzone)
                input_event = InputEvent(now, "stick_move", "RIGHT_Y", self.state.right_y)
            elif code == "ABS_Z":
                was_ads = self.state.is_aiming
                self.state.left_trigger = nt(value)
                self.state.is_aiming    = self.state.left_trigger > self.trigger_dead
                if self.state.is_aiming and not was_ads:
                    self._ads_start_time = now; self.stats["ads_activations"] += 1
                elif not self.state.is_aiming and was_ads and self._ads_start_time:
                    self._ads_durations.append((now - self._ads_start_time) * 1000)
                    self._ads_start_time = None
                input_event = InputEvent(now, "trigger", "LEFT_TRIGGER", self.state.left_trigger)
            elif code == "ABS_RZ":
                was_firing = self.state.is_firing
                self.state.right_trigger = nt(value)
                self.state.is_firing     = self.state.right_trigger > self.trigger_dead
                if self.state.is_firing and not was_firing: self.stats["fire_bursts"] += 1
                input_event = InputEvent(now, "trigger", "RIGHT_TRIGGER", self.state.right_trigger)
            elif code == "BTN_SOUTH":
                self.state.btn_a = bool(value)
                if value: self.stats["jump_count"] += 1
                input_event = InputEvent(now, "button_press" if value else "button_release", "A", float(value))
            elif code == "BTN_EAST":
                self.state.btn_b = bool(value)
                if value: self.stats["slide_count"] += 1
                input_event = InputEvent(now, "button_press" if value else "button_release", "B", float(value))
            elif code == "BTN_WEST":
                self.state.btn_x = bool(value)
                input_event = InputEvent(now, "button_press" if value else "button_release", "X", float(value))
            elif code == "BTN_NORTH":
                self.state.btn_y = bool(value)
                input_event = InputEvent(now, "button_press" if value else "button_release", "Y", float(value))
            elif code == "BTN_TL":
                self.state.lb = bool(value)
                if value: self.stats["ability_1_uses"] += 1
                input_event = InputEvent(now, "button_press" if value else "button_release", "LB", float(value))
            elif code == "BTN_TR":
                self.state.rb = bool(value)
                if value: self.stats["ability_2_uses"] += 1
                input_event = InputEvent(now, "button_press" if value else "button_release", "RB", float(value))
            elif code == "BTN_THUMBL":
                self.state.ls_click = bool(value)
                if value: self.stats["melee_count"] += 1
                input_event = InputEvent(now, "button_press" if value else "button_release", "LS", float(value))
            elif code == "BTN_THUMBR":
                self.state.rs_click = bool(value)
                input_event = InputEvent(now, "button_press" if value else "button_release", "RS", float(value))
            elif code == "ABS_HAT0Y":
                self.state.dpad_up   = value == -1
                self.state.dpad_down = value == 1
                input_event = InputEvent(now, "dpad", "DPAD_Y", float(value))
            elif code == "ABS_HAT0X":
                self.state.dpad_left  = value == -1
                self.state.dpad_right = value == 1
                input_event = InputEvent(now, "dpad", "DPAD_X", float(value))
            self.state.movement_speed = round(math.sqrt(self.state.left_x**2 + self.state.left_y**2), 4)
            self.state.aim_speed      = round(math.sqrt(self.state.right_x**2 + self.state.right_y**2), 4)
            self.state.is_moving      = self.state.movement_speed > self.deadzone

        if input_event:
            self.stats["total_inputs"] += 1
            input_event.state_snapshot = {
                "left_x": self.state.left_x, "left_y": self.state.left_y,
                "right_x": self.state.right_x, "right_y": self.state.right_y,
                "left_trigger": self.state.left_trigger,
                "right_trigger": self.state.right_trigger,
                "is_moving": self.state.is_moving,
                "is_aiming": self.state.is_aiming,
                "is_firing": self.state.is_firing,
                "movement_speed": self.state.movement_speed,
            }
            line = json.dumps({
                "t": round(input_event.timestamp - self.session_start, 4),
                "type": input_event.event_type, "input": input_event.input_name,
                "value": input_event.value, "state": input_event.state_snapshot,
            })
            if self._log_handle:
                self._log_handle.write(line + "\n")
                self._log_handle.flush()

    def _update_time_stats(self, elapsed: float):
        if self.state.is_moving:  self.stats["time_moving"]  += elapsed
        if self.state.is_aiming:  self.stats["time_aiming"]  += elapsed
        if self.state.is_firing:  self.stats["time_firing"]  += elapsed
        if self.state.is_moving and self.state.is_aiming:
            self.stats["time_moving_while_aiming"] += elapsed
        elif self.state.is_aiming:
            self.stats["time_stationary_while_aiming"] += elapsed

    def _finalize_stats(self):
        if self._ads_durations:
            self.stats["avg_ads_duration_ms"] = round(
                sum(self._ads_durations)/len(self._ads_durations), 1)
        if self.stats["time_aiming"] > 0:
            pct = self.stats["time_moving_while_aiming"] / self.stats["time_aiming"]
            self.stats["movement_while_aiming_pct"] = round(pct * 100, 1)
        else:
            self.stats["movement_while_aiming_pct"] = 0.0
        self.stats["session_duration_s"] = round(time.time() - self.session_start, 1)

    def get_inputs_for_clip(self, clip_start: float, clip_end: float) -> list:
        if not self.log_file.exists(): return []
        result = []
        with open(self.log_file) as f:
            for line in f:
                try:
                    ev = json.loads(line.strip())
                    if clip_start <= ev.get("t", 0) <= clip_end:
                        result.append(ev)
                except json.JSONDecodeError:
                    pass
        return result

    def get_coaching_summary(self) -> str:
        s   = self.stats
        pct = s.get("movement_while_aiming_pct", 0)
        min_= round(s.get("session_duration_s", 0)/60, 1)
        return (
            f"Session: {min_} min | Inputs: {s['total_inputs']}\n"
            f"Moving while aiming: {pct}% (target: 70%+)\n"
            f"ADS activations: {s['ads_activations']} | "
            f"Avg hold: {s['avg_ads_duration_ms']}ms\n"
            f"Fire bursts: {s['fire_bursts']} | "
            f"Jumps: {s['jump_count']} | Slides: {s['slide_count']}\n"
            f"Abilities: Q={s['ability_1_uses']} E={s['ability_2_uses']}"
        )

# ════════════════════════════════════════════════════════════════
#  FIGHT ANALYSIS ENGINE
# ════════════════════════════════════════════════════════════════

FIGHT_ANALYSIS_SYSTEM_PROMPT = """You are Aria, an elite Apex Legends AI coach.
Your player is Hidarikikinoaku — handle: LeftHandDevil — Gold 4, targeting Predator.
GameSir G7 Pro 8K controller.
Review this fight clip frame-by-frame. Be specific and honest.
Personality: firm like Erza Scarlet, loyal like Rem. High standards. No sugarcoating.
Respond with valid JSON only — no markdown, no prose outside the JSON.
Schema:
{
  "overall_verdict": "One sharp sentence",
  "fight_quality": "clean|sloppy|unlucky|outplayed|mistake",
  "primary_fix": "Single most important habit to change",
  "key_moment": "What happened at the decisive moment",
  "key_moment_time": <float>,
  "positioning_score": <0-10>, "movement_score": <0-10>,
  "aim_score": <0-10>, "decision_score": <0-10>, "overall_score": <0-10>,
  "what_went_wrong": "Technical breakdown",
  "what_went_right": "Anything executed well",
  "specific_drill": "Concrete practice drill",
  "aria_quote": "Aria's personal comment — 2-3 sentences max"
}"""

SESSION_REPORT_SYSTEM_PROMPT = """You are Aria, Apex Legends AI coach for Hidarikikinoaku (LeftHandDevil).
Write a post-match coaching report. Be specific — reference patterns across clips.
Identify the #1 habit to fix. Include a brief road-to-Predator progress note.
Under 300 words. Direct, caring, high standards. No generic AI language. Plain text only."""


class FightAnalysisEngine:
    def __init__(self, config: dict):
        self.config = config
        self.client, self.vision_model, self.coaching_model = _build_ai_client(config)
        self.max_frames     = int(config.get("max_frames_per_clip", 8))
        self.reports_folder = config.get("reports_folder", "data/reports")
        os.makedirs(self.reports_folder, exist_ok=True)

    def analyze_clip(self, clip_path: str, event_type: str,
                     controller_summary: str = "",
                     session_summary: dict = None,
                     live_api_context: dict = None,
                     legend_played: str = "Alter") -> Optional[FightAnalysis]:
        session_summary  = session_summary  or {}
        live_api_context = live_api_context or {}
        analysis = FightAnalysis(
            clip_path=clip_path, event_type=event_type,
            timestamp=session_summary.get("match_start_time", time.time()),
            controller_context=controller_summary,
            damage_dealt=live_api_context.get("damage_dealt", 0),
            damage_taken=live_api_context.get("damage_taken", 0),
            attacker_name=live_api_context.get("attacker_name", ""),
            legend_played=legend_played,
        )
        if not Path(clip_path).exists():
            return self._fallback_analysis(analysis)
        frames_b64, clip_dur = self._extract_frames(clip_path)
        analysis.frames_analyzed = len(frames_b64)
        if not frames_b64 or not self.client:
            return self._fallback_analysis(analysis)
        try:
            result = self._call_vision_api(frames_b64, event_type,
                                           controller_summary, session_summary,
                                           live_api_context, clip_dur)
            if result:
                self._apply_result(analysis, result)
                analysis.model_used       = self.vision_model
                analysis.api_cost_estimate = len(frames_b64) * 0.00255 + 0.002
                logger.info(f"Analysis: {Path(clip_path).name} — "
                            f"{analysis.overall_verdict} ({analysis.overall_score}/10)")
            else:
                return self._fallback_analysis(analysis)
        except Exception as e:
            logger.error(f"Vision API failed for {Path(clip_path).name}: {e}")
            return self._fallback_analysis(analysis)
        return analysis

    def generate_session_report(self, analyses: list,
                                session_summary: dict,
                                controller_stats: dict) -> str:
        if not analyses or not self.client:
            return self._minimal_report(session_summary, controller_stats)
        try:
            context  = self._build_session_context(analyses, session_summary, controller_stats)
            response = self.client.chat.completions.create(
                model=self.coaching_model,
                messages=[
                    {"role": "system", "content": SESSION_REPORT_SYSTEM_PROMPT},
                    {"role": "user",   "content": context},
                ],
                max_tokens=600, temperature=0.7,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Session report failed: {e}")
            return self._minimal_report(session_summary, controller_stats)

    def save_analysis(self, analysis: FightAnalysis, output_dir: str) -> str:
        os.makedirs(output_dir, exist_ok=True)
        stem     = Path(analysis.clip_path).stem if analysis.clip_path else "unknown"
        out_path = Path(output_dir) / f"analysis_{stem}_{int(time.time())}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(asdict(analysis), f, indent=2, ensure_ascii=False)
        return str(out_path)

    def _extract_frames(self, clip_path: str) -> tuple:
        if not CV2_AVAILABLE: return [], 0.0
        frames_b64 = []; clip_dur = 0.0
        try:
            cap = cv2.VideoCapture(clip_path)
            if not cap.isOpened(): return [], 0.0
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0
            clip_dur = total / fps
            if total == 0: cap.release(); return [], 0.0
            n       = min(self.max_frames, total)
            indices = [int(i*(total-1)/max(n-1,1)) for i in range(n)]
            for idx in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if not ret: continue
                h, w = frame.shape[:2]
                if max(h,w) > 1280:
                    scale = 1280/max(h,w)
                    frame = cv2.resize(frame,(int(w*scale),int(h*scale)),
                                       interpolation=cv2.INTER_AREA)
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                frames_b64.append(base64.b64encode(buf.tobytes()).decode("utf-8"))
            cap.release()
        except Exception as e:
            logger.error(f"Frame extraction: {e}")
        return frames_b64, clip_dur

    def _call_vision_api(self, frames_b64, event_type, ctrl_summary,
                         session_summary, live_api_context, clip_dur):
        ctrl_ctx = f"Controller data:\n{ctrl_summary}\n\n" if ctrl_summary else ""
        live_ctx = ""
        if live_api_context:
            d = live_api_context.get("damage_dealt",0)
            t = live_api_context.get("damage_taken",0)
            a = live_api_context.get("attacker_name","")
            live_ctx = f"Live API: {d} dealt, {t} taken"
            if a: live_ctx += f", killed by: {a}"
            live_ctx += "\n\n"
        k       = session_summary.get("knock_count",0)
        dd      = session_summary.get("death_count",0)
        user_text = (
            f"Event: {event_type}\n"
            f"{len(frames_b64)} frames from {clip_dur:.1f}s clip\n"
            f"Match so far: {k} knocks, {dd} deaths\n\n"
            f"{ctrl_ctx}{live_ctx}"
            "Review these frames and give your JSON analysis."
        )
        content = [{"type":"text","text":user_text}]
        for b64 in frames_b64:
            content.append({"type":"image_url","image_url":{
                "url": f"data:image/jpeg;base64,{b64}","detail":"auto"}})
        response = self.client.chat.completions.create(
            model=self.vision_model,
            messages=[
                {"role":"system","content":FIGHT_ANALYSIS_SYSTEM_PROMPT},
                {"role":"user","content":content},
            ],
            max_tokens=800, temperature=0.3,
            response_format={"type":"json_object"},
        )
        raw = response.choices[0].message.content.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            s = raw.find("{"); e = raw.rfind("}") + 1
            if s != -1 and e > s:
                try: return json.loads(raw[s:e])
                except json.JSONDecodeError: pass
            return None

    def _apply_result(self, analysis: FightAnalysis, r: dict):
        analysis.overall_verdict   = str(r.get("overall_verdict",""))
        analysis.fight_quality     = str(r.get("fight_quality","mistake"))
        analysis.primary_fix       = str(r.get("primary_fix",""))
        analysis.key_moment        = str(r.get("key_moment",""))
        analysis.key_moment_time   = float(r.get("key_moment_time",0.0))
        analysis.positioning_score = float(r.get("positioning_score",5.0))
        analysis.movement_score    = float(r.get("movement_score",5.0))
        analysis.aim_score         = float(r.get("aim_score",5.0))
        analysis.decision_score    = float(r.get("decision_score",5.0))
        analysis.overall_score     = float(r.get("overall_score",5.0))
        analysis.what_went_wrong   = str(r.get("what_went_wrong",""))
        analysis.what_went_right   = str(r.get("what_went_right",""))
        analysis.specific_drill    = str(r.get("specific_drill",""))
        analysis.aria_quote        = str(r.get("aria_quote",""))

    def _fallback_analysis(self, analysis: FightAnalysis) -> FightAnalysis:
        is_m = analysis.event_type in ("knocked_by_enemy","killed_by_enemy")
        if analysis.damage_dealt or analysis.damage_taken:
            verdict = (f"Knocked — {analysis.damage_dealt} dealt, "
                       f"{analysis.damage_taken} taken. Add API key for full breakdown.")
        else:
            verdict = ("Got knocked — review this clip manually." if is_m
                       else "Clip recorded — API key needed for full analysis.")
        analysis.overall_verdict  = verdict
        analysis.fight_quality    = "mistake" if is_m else "clean"
        analysis.primary_fix      = "Add NIM_API_KEY (or OPENAI_API_KEY) to ARIA_ALL_IN_ONE.py for coaching."
        analysis.key_moment       = "Unknown — no API analysis"
        for attr in ("positioning_score","movement_score","aim_score","decision_score","overall_score"):
            setattr(analysis, attr, 5.0)
        analysis.what_went_wrong  = "Full analysis unavailable without an AI API key."
        analysis.specific_drill   = "Watch the clip. Note one thing you'd do differently."
        analysis.aria_quote       = ("I can't coach you without my eyes open. "
                                     "Add your API key — every match you skip is wasted data.")
        analysis.model_used       = "fallback"
        return analysis

    def _build_session_context(self, analyses, session_summary, controller_stats) -> str:
        k  = session_summary.get("knock_count",0)
        d  = session_summary.get("death_count",0)
        mv = controller_stats.get("movement_while_aiming_pct",0)
        lines = [f"Match: {k} knocks, {d} deaths."]
        if mv: lines.append(f"Moving while aiming: {mv}% (target: 65%+)")
        lines.append(f"Clips analyzed: {len(analyses)}")
        mistakes   = [a for a in analyses if a.event_type in ("knocked_by_enemy","killed_by_enemy")]
        highlights = [a for a in analyses if a.event_type not in ("knocked_by_enemy","killed_by_enemy")]
        if mistakes:
            lines.append("\nMistakes:")
            for a in mistakes:
                lines.append(f"  [{a.event_type}] {a.overall_verdict} "
                             f"(decision {a.decision_score}/10)")
                if a.primary_fix: lines.append(f"    Fix: {a.primary_fix}")
        if highlights:
            lines.append("\nHighlights:")
            for a in highlights:
                lines.append(f"  [{a.event_type}] {a.overall_verdict} ({a.overall_score}/10)")
        if analyses:
            avg_d = sum(a.decision_score    for a in analyses)/len(analyses)
            avg_m = sum(a.movement_score    for a in analyses)/len(analyses)
            avg_p = sum(a.positioning_score for a in analyses)/len(analyses)
            lines.append(f"\nAverages — Decision: {avg_d:.1f} Movement: {avg_m:.1f} "
                         f"Positioning: {avg_p:.1f}")
        lines.append("\nWrite Aria's post-match coaching report based on this data.")
        return "\n".join(lines)

    def _minimal_report(self, session_summary, controller_stats) -> str:
        k  = session_summary.get("knock_count",0)
        d  = session_summary.get("death_count",0)
        mv = controller_stats.get("movement_while_aiming_pct",0)
        lines = [f"Match complete. {k} knocks, {d} deaths.\n"]
        if mv:
            lines.append(f"Moving while aiming: {mv}% — "
                         f"{'good' if mv >= 65 else 'needs work'} (target: 65%+)\n")
        lines += ["\nAdd NIM_API_KEY to ARIA_ALL_IN_ONE.py for full coaching.",
                  "Free credits at: https://build.nvidia.com\n", "— Aria"]
        return "\n".join(lines)


# ════════════════════════════════════════════════════════════════
#  VIDEO ANNOTATOR  (stubs — full implementation in video_annotator.py)
# ════════════════════════════════════════════════════════════════

class VideoAnnotator:
    """Burns coaching annotations into fight clips."""

    def annotate_mistake(self, clip_path: str, analysis_data: dict) -> str:
        if not CV2_AVAILABLE or not clip_path or not Path(clip_path).exists():
            return clip_path or ""
        try:
            cap      = cv2.VideoCapture(clip_path)
            fps      = cap.get(cv2.CAP_PROP_FPS) or 30.0
            w        = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h        = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            stem     = Path(clip_path).stem
            out_path = str(Path(clip_path).parent / f"{stem}_mistake_annotated.mp4")
            writer   = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"),
                                       fps, (w, h))
            verdict  = analysis_data.get("overall_verdict", "")
            fix      = analysis_data.get("primary_fix", "")
            key_t    = float(analysis_data.get("key_moment_time", 0))
            frame_no = 0
            while True:
                ret, frame = cap.read()
                if not ret: break
                sec = frame_no / fps
                # Red circle at key moment
                if abs(sec - key_t) < 1.0:
                    cx, cy = w // 2, h // 2
                    cv2.circle(frame, (cx, cy), 80, (0, 50, 220), 3)
                # Verdict text overlay for first 3 seconds
                if sec < 3.0 and verdict:
                    cv2.putText(frame, verdict[:60], (20, 40),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2, cv2.LINE_AA)
                # Primary fix at bottom throughout
                if fix:
                    cv2.putText(frame, f"Fix: {fix[:60]}", (20, h - 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2, cv2.LINE_AA)
                writer.write(frame)
                frame_no += 1
            cap.release(); writer.release()
            logger.info(f"Annotated clip: {out_path}")
            return out_path
        except Exception as e:
            logger.error(f"Annotation failed: {e}")
            return clip_path

    def annotate_highlight(self, clip_path: str, analysis_data: dict) -> str:
        if not CV2_AVAILABLE or not clip_path or not Path(clip_path).exists():
            return clip_path or ""
        try:
            cap      = cv2.VideoCapture(clip_path)
            fps      = cap.get(cv2.CAP_PROP_FPS) or 30.0
            w        = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h        = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            stem     = Path(clip_path).stem
            out_path = str(Path(clip_path).parent / f"{stem}_highlight_annotated.mp4")
            writer   = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"),
                                       fps, (w, h))
            verdict  = analysis_data.get("overall_verdict", "Clean fight!")
            frame_no = 0
            while True:
                ret, frame = cap.read()
                if not ret: break
                sec = frame_no / fps
                if sec < 2.0:
                    cv2.putText(frame, verdict[:60], (20, 40),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 80), 2, cv2.LINE_AA)
                writer.write(frame)
                frame_no += 1
            cap.release(); writer.release()
            return out_path
        except Exception as e:
            logger.error(f"Highlight annotation failed: {e}")
            return clip_path

# ════════════════════════════════════════════════════════════════
#  MOBILE COMPANION API
# ════════════════════════════════════════════════════════════════

class MobileCompanionAPI:
    ARIA_MOBILE_PROMPT = (
        "You are Aria (@migikonokami, 'RightHandGod'), the elite Apex Legends AI coach "
        "for Hidarikikinoaku ('LeftHandDevil'). The player is on their phone. "
        "Keep responses concise. You know all their bad habits. "
        "Be direct but warm — like a coach they can text anytime. "
        "Current rank: {rank}. Target: Predator. Controller: GameSir G7 Pro 8K."
    )

    def __init__(self, config: dict):
        self.config       = config
        self.data_dir     = Path("data")
        self.clips_dir    = self.data_dir / "clips"
        self.static_dir   = Path("mobile/static")
        self.openai, self._chat_model, _ = _build_ai_client(config)
        self.conversations: dict[str, list] = {}

    def build_app(self):
        if not FASTAPI_AVAILABLE:
            raise ImportError("FastAPI not installed")
        app = FastAPI(title="Aria Mobile Companion", version="1.0.0")
        app.add_middleware(CORSMiddleware, allow_origins=["*"],
                           allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
        if self.static_dir.exists():
            app.mount("/static", StaticFiles(directory=str(self.static_dir)), name="static")
        self._register_routes(app)
        return app

    def _register_routes(self, app):
        @app.get("/")
        async def root():
            idx = self.static_dir / "index.html"
            return FileResponse(str(idx)) if idx.exists() \
                else {"status": "Aria online", "player": PLAYER_NAME}

        @app.get("/health")
        async def health():
            return {"status": "online", "aria": "ready",
                    "timestamp": datetime.now().isoformat()}

        @app.get("/api/profile")
        async def get_profile():
            return {
                "username":     PLAYER_NAME,
                "display_name": PLAYER_HANDLE,
                "coach":        f"Aria ({COACH_HANDLE})",
                "current_rank": self.config.get("current_rank", "Gold IV"),
                "current_rp":   self.config.get("current_rp", 143),
                "target_rank":  "Predator",
                "controller":   "GameSir G7 Pro 8K",
            }

        @app.get("/api/sessions")
        async def get_sessions(limit: int = 10):
            sessions = self._load_recent_sessions(limit)
            return {"sessions": sessions, "count": len(sessions)}

        @app.get("/api/clips")
        async def get_clips(session_id: str = None, clip_type: str = None,
                            limit: int = 20):
            clips = self._list_clips(session_id, clip_type, limit)
            return {"clips": clips, "count": len(clips)}

        @app.get("/api/clips/{clip_id}/video")
        async def stream_clip(clip_id: str, quality: str = "medium"):
            clip_path = self._find_clip(clip_id)
            if not clip_path:
                raise HTTPException(404, "Clip not found")
            mobile_path = self._prepare_mobile_clip(clip_path, quality)
            def iter_file():
                with open(mobile_path, "rb") as f:
                    while chunk := f.read(65536): yield chunk
            return StreamingResponse(iter_file(), media_type="video/mp4")

        @app.get("/api/clips/{clip_id}/analysis")
        async def get_clip_analysis(clip_id: str):
            clip_path = self._find_clip(clip_id)
            if not clip_path: raise HTTPException(404, "Clip not found")
            analysis  = self._load_clip_analysis(clip_path)
            if not analysis: raise HTTPException(404, "Analysis not available")
            return analysis

        @app.get("/api/roadmap")
        async def get_roadmap():
            habits   = self._load_habit_tracker()
            sessions = self._load_recent_sessions(20)
            needed   = self._estimate_rp_to_predator()
            weekly   = self._calculate_weekly_rp(sessions)
            eta      = round(needed / max(weekly, 1), 1) if weekly > 0 else None
            return {
                "current_rank":   self.config.get("current_rank", "Gold IV"),
                "current_rp":     self.config.get("current_rp", 143),
                "rp_to_predator": needed,
                "weekly_rp_rate": weekly,
                "eta_weeks":      eta,
                "top_blockers":   habits.get("top_blockers", []),
                "this_week_focus": habits.get("current_focus", "Left stick active while aiming"),
            }

        @app.post("/api/chat")
        async def chat(message: dict):
            user_msg    = message.get("message","").strip()
            session_key = message.get("session_key","default")
            if not user_msg: raise HTTPException(400, "Message cannot be empty")
            reply, clips = await self._chat(user_msg, session_key)
            return {"response": reply, "clip_refs": clips,
                    "timestamp": datetime.now().isoformat()}

    async def _chat(self, message: str, session_key: str) -> tuple:
        if not self.openai:
            return ("Chat requires an API key. "
                    "Add NIM_API_KEY to ARIA_ALL_IN_ONE.py (free at build.nvidia.com).", [])
        if session_key not in self.conversations:
            self.conversations[session_key] = []
        rank    = self.config.get("current_rank", "Gold IV")
        system  = self.ARIA_MOBILE_PROMPT.format(rank=rank)
        habits  = self._load_habit_tracker()
        issues  = habits.get("top_blockers", [])
        if issues: system += f"\nKnown bad habits: {', '.join(issues)}"
        self.conversations[session_key].append({"role":"user","content":message})
        history = self.conversations[session_key][-10:]
        clip_refs = self._find_relevant_clips(message)
        try:
            response = self.openai.chat.completions.create(
                model=self._chat_model,
                messages=[{"role":"system","content":system}, *history],
                max_tokens=300, temperature=0.5,
            )
            reply = response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Chat failed: {e}")
            reply = "Trouble connecting right now. Check your API key."
            clip_refs = []
        self.conversations[session_key].append({"role":"assistant","content":reply})
        return reply, clip_refs

    def _load_recent_sessions(self, limit: int) -> list:
        sessions = []
        if not self.clips_dir.exists(): return sessions
        for f in sorted(self.clips_dir.glob("*/session_summary.json"), reverse=True)[:limit]:
            try:
                with open(f) as fp: sessions.append(json.load(fp))
            except Exception: pass
        return sessions

    def _list_clips(self, session_id, clip_type, limit) -> list:
        clips = []; search = (self.clips_dir/session_id if session_id else self.clips_dir)
        if not search.exists(): return clips
        for meta_file in sorted(search.rglob("*.json"), reverse=True)[:limit*2]:
            if "session_summary" in meta_file.name or "analysis" in meta_file.name: continue
            try:
                with open(meta_file) as f: meta = json.load(f)
                if clip_type and meta.get("event_type") != clip_type: continue
                clip_file = meta_file.parent / meta.get("clip_file","")
                if clip_file.exists():
                    meta["clip_id"]  = meta_file.stem
                    meta["clip_url"] = f"/api/clips/{meta_file.stem}/video"
                    clips.append(meta)
                if len(clips) >= limit: break
            except Exception: pass
        return clips

    def _find_clip(self, clip_id: str):
        for meta_file in self.clips_dir.rglob(f"{clip_id}.json"):
            try:
                with open(meta_file) as f: meta = json.load(f)
                p = meta_file.parent / meta.get("clip_file","")
                if p.exists(): return str(p)
            except Exception: pass
        return None

    def _load_clip_analysis(self, clip_path: str):
        stem = Path(clip_path).stem
        p    = Path(clip_path).parent / f"{stem}_analysis.json"
        if p.exists():
            with open(p) as f: return json.load(f)
        return None

    def _prepare_mobile_clip(self, clip_path: str, quality: str) -> str:
        bitrate = {"low":"400k","medium":"800k","high":"1500k"}.get(quality,"800k")
        stem    = Path(clip_path).stem
        mobile  = Path("data/mobile_cache") / f"{stem}_{quality}.mp4"
        mobile.parent.mkdir(parents=True, exist_ok=True)
        if mobile.exists(): return str(mobile)
        os.system(f'ffmpeg -y -i "{clip_path}" -vcodec libx264 -b:v {bitrate} '
                  f'-acodec aac -b:a 128k -vf scale=1280:-2 "{mobile}" -loglevel error')
        return str(mobile) if mobile.exists() else clip_path

    def _find_relevant_clips(self, message: str) -> list:
        keywords = message.lower().split()
        loc  = {"fragment","storm","olympus","worlds","edge","building","hill","zone","ring"}
        evts = {"knock","die","died","death","down","kill"}
        for w in keywords:
            if w in loc or w in evts:
                return self._list_clips(None, None, 5)[:3]
        return []

    def _load_habit_tracker(self) -> dict:
        p = Path("data/habit_tracker.json")
        if p.exists():
            with open(p) as f: return json.load(f)
        return {"top_blockers": ["Stationary while ADS",
                                 "Doorway discipline",
                                 "Third-party awareness"],
                "current_focus": "Left stick active — move while you aim",
                "trends": {}}

    def _estimate_rp_to_predator(self) -> int:
        rank_rp = {"Gold IV":1200,"Gold III":900,"Gold II":600,"Gold I":300,"Platinum IV":0}
        base    = rank_rp.get(self.config.get("current_rank","Gold IV"), 1200)
        have    = int(self.config.get("current_rp", 143))
        return max(0, 15000 - base - have)

    def _calculate_weekly_rp(self, sessions: list) -> int:
        total_k = sum(s.get("knock_count",0) for s in sessions[-20:])
        count   = max(len(sessions[-20:]), 1)
        return int((total_k * 12 / count) * 10)


def run_mobile_server(config: dict, host: str = "0.0.0.0", port: int = MOBILE_PORT):
    if not FASTAPI_AVAILABLE:
        logger.error("FastAPI not installed — mobile server disabled")
        return
    api = MobileCompanionAPI(config)
    app = api.build_app()
    logger.info(f"Mobile companion on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


# ════════════════════════════════════════════════════════════════
#  ARIA OVERLAY  (PyQt5)
# ════════════════════════════════════════════════════════════════

if PYQT5_AVAILABLE:
    class VoiceThread(QThread):
        done = pyqtSignal()
        def __init__(self, text, engine, speaker_wav=None, language="en"):
            super().__init__()
            self.text        = text
            self.engine      = engine
            self.speaker_wav = speaker_wav
            self.language    = language
        def run(self):
            try:
                if self.engine:
                    path = "data/aria_voice.wav"
                    os.makedirs("data", exist_ok=True)
                    if self.speaker_wav and os.path.exists(self.speaker_wav):
                        # XTTS v2 multi-speaker mode — uses reference wav for voice style
                        self.engine.tts_to_file(
                            text=self.text,
                            file_path=path,
                            speaker_wav=self.speaker_wav,
                            language=self.language,
                        )
                    else:
                        # XTTS v2 with built-in default speaker
                        self.engine.tts_to_file(
                            text=self.text,
                            file_path=path,
                            speaker="Ana Florence",  # warm, clear female voice included with XTTS v2
                            language=self.language,
                        )
                    if sys.platform == "win32":
                        import winsound
                        winsound.PlaySound(path, winsound.SND_FILENAME)
                    else:
                        os.system(f"aplay '{path}' 2>/dev/null")
            except Exception as e:
                logger.debug(f"Voice error: {e}")
            finally:
                self.done.emit()

    class AriaSprite(QWidget):
        def __init__(self, sprites_dir: Path, parent=None):
            super().__init__(parent)
            self.sprites_dir = sprites_dir
            self.state = IDLE; self.frame = 0; self.frames: dict = {}
            self.setFixedSize(260, 360)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self._load()
            self.timer = QTimer(); self.timer.timeout.connect(self._tick)
            self.timer.start(83)

        def _load(self):
            for state in [IDLE,TALKING,POINTING,PROUD,CONCERNED,THINKING]:
                d = self.sprites_dir / state; frames = []
                if d.exists():
                    for f in sorted(d.glob("*.png")):
                        px = QPixmap(str(f))
                        if not px.isNull():
                            frames.append(px.scaled(260,360,Qt.KeepAspectRatio,Qt.SmoothTransformation))
                self.frames[state] = frames or [self._draw(state)]

        def _draw(self, state: str) -> QPixmap:
            px = QPixmap(260, 360); px.fill(Qt.transparent)
            p  = QPainter(px); p.setRenderHint(QPainter.Antialiasing)
            # Armor body
            p.setBrush(QBrush(QColor(C["panel"]))); p.setPen(QPen(QColor(C["blue"]),2))
            p.drawRoundedRect(48,112,164,222,16,16)
            # Red chest
            p.setBrush(QBrush(QColor(C["red"]))); p.setPen(Qt.NoPen)
            p.drawRect(48,148,164,7); p.drawRect(48,200,164,4)
            # Silver shoulders
            p.setBrush(QBrush(QColor(C["silver"])))
            p.drawEllipse(22,116,42,26); p.drawEllipse(196,116,42,26)
            # Blue trim
            p.setBrush(QBrush(QColor(C["blue"])))
            p.drawEllipse(26,118,18,12); p.drawEllipse(216,118,18,12)
            # Head
            p.setBrush(QBrush(QColor("#F2C89B"))); p.setPen(QPen(QColor("#D4A574"),1))
            p.drawEllipse(88,26,84,90)
            # Hair
            p.setBrush(QBrush(QColor("#6B2D0F"))); p.setPen(Qt.NoPen)
            p.drawEllipse(84,14,92,64)
            p.setBrush(QBrush(QColor("#8B4513"))); p.drawEllipse(90,16,80,50)
            p.setBrush(QBrush(QColor("#7B3B10")))
            p.drawRect(84,50,16,96); p.drawRect(160,50,16,96)
            p.setBrush(QBrush(QColor("#9B5523"))); p.drawEllipse(116,8,28,22)
            # Eyes
            p.setBrush(QBrush(QColor(C["blue"]))); p.setPen(Qt.NoPen)
            p.drawEllipse(102,66,20,15); p.drawEllipse(138,66,20,15)
            p.setBrush(QBrush(QColor("#0A1F3A")))
            p.drawEllipse(108,69,9,9); p.drawEllipse(144,69,9,9)
            p.setBrush(QBrush(QColor("white")))
            p.drawEllipse(114,70,4,4); p.drawEllipse(150,70,4,4)
            # Mouth
            p.setPen(QPen(QColor("#B87060"),2)); p.setBrush(Qt.NoBrush)
            if state == PROUD:    p.drawArc(116,92,28,16,0,-180*16)
            elif state == CONCERNED: p.drawArc(116,100,28,12,0,160*16)
            elif state == TALKING:
                p.setBrush(QBrush(QColor("#8B4040"))); p.drawEllipse(122,92,16,10)
            else: p.drawArc(118,94,24,12,0,-120*16)
            if state == POINTING:
                p.setBrush(QBrush(QColor(C["panel"]))); p.setPen(QPen(QColor(C["blue"]),2))
                p.drawRoundedRect(210,138,42,14,6,6)
                p.setBrush(QBrush(QColor("#F2C89B"))); p.setPen(QPen(QColor("#D4A574"),1))
                p.drawEllipse(246,136,14,10)
            p.setPen(QPen(QColor(C["muted"]))); p.setFont(QFont("Arial",8))
            p.drawText(0,344,260,14,Qt.AlignCenter,"Aria  ·  @migikonokami")
            p.end(); return px

        def set_state(self, state: str):
            if state != self.state: self.state = state; self.frame = 0
        def _tick(self):
            frames = self.frames.get(self.state,[])
            if frames: self.frame = (self.frame+1) % len(frames); self.update()
        def paintEvent(self, event):
            frames = self.frames.get(self.state,[])
            if not frames: return
            p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
            p.drawPixmap(0,0,frames[self.frame % len(frames)]); p.end()

    class AriaOverlay(QMainWindow):
        def __init__(self, config: dict = None):
            super().__init__()
            self.config      = config or {}
            self.sprites_dir = Path(self.config.get("sprites_dir","assets/sprites"))
            self.tts         = None
            self._analyses   = []
            self._vthread    = None
            self._fade_ref   = None
            self._tw_timer   = None
            self._init_tts(); self._build_ui(); self._position()

        def _init_tts(self):
            if not TTS_AVAILABLE: return
            try:
                self.tts = CoquiTTS(
                    model_name="tts_models/multilingual/multi-dataset/xtts_v2",
                    progress_bar=False,
                    gpu=self._gpu(),
                )
                # Speaker reference wav — drop assets/aria_voice_ref.wav to customise Aria's voice
                self._speaker_wav = "assets/aria_voice_ref.wav" if os.path.exists("assets/aria_voice_ref.wav") else None
                logger.info("Aria voice ready ✅ (XTTS v2)")
            except Exception as e:
                logger.warning(f"TTS failed: {e}")

        def _gpu(self):
            try:
                import torch; return torch.cuda.is_available()
            except ImportError: return False

        def _build_ui(self):
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
            self.setAttribute(Qt.WA_TranslucentBackground)
            root = QWidget(); root.setStyleSheet("background:transparent;")
            self.setCentralWidget(root)
            row = QHBoxLayout(root); row.setContentsMargins(0,0,0,0); row.setSpacing(0)
            self.sprite = AriaSprite(self.sprites_dir)
            row.addWidget(self.sprite, 0, Qt.AlignBottom); row.addWidget(self._panel())
            self.setFixedSize(660, 400)

        def _panel(self) -> QFrame:
            f = QFrame(); f.setFixedSize(390,390)
            f.setStyleSheet(f"QFrame{{background:rgba(13,13,30,218);border:1px solid {C['blue']};border-radius:10px;}}")
            v = QVBoxLayout(f); v.setContentsMargins(14,10,14,10); v.setSpacing(6)
            h  = QHBoxLayout()
            n  = QLabel("ARIA"); n.setStyleSheet(f"color:{C['red']};font-size:13px;font-weight:bold;letter-spacing:3px;")
            s  = QLabel("@migikonokami"); s.setStyleSheet(f"color:{C['blue']};font-size:9px;")
            self.lrank = QLabel("Gold IV → Predator"); self.lrank.setStyleSheet(f"color:{C['gold']};font-size:9px;")
            h.addWidget(n); h.addWidget(s); h.addStretch(); h.addWidget(self.lrank); v.addLayout(h)
            div = QFrame(); div.setFrameShape(QFrame.HLine); div.setStyleSheet(f"color:{C['blue']};"); v.addWidget(div)
            self.lstats = QLabel("Analyzing your match..."); self.lstats.setStyleSheet(f"color:{C['muted']};font-size:10px;"); v.addWidget(self.lstats)
            self.txt = QTextEdit(); self.txt.setReadOnly(True)
            self.txt.setStyleSheet(f"QTextEdit{{background:transparent;color:{C['text']};font-size:11px;border:none;}}QScrollBar:vertical{{width:3px;background:transparent;}}QScrollBar::handle:vertical{{background:{C['blue']};border-radius:1px;}}")
            v.addWidget(self.txt)
            self.lfix = QLabel(""); self.lfix.setWordWrap(True)
            self.lfix.setStyleSheet(f"color:{C['text']};background:rgba(192,57,43,35);border-left:3px solid {C['red']};padding:5px 8px;font-size:10px;border-radius:3px;")
            self.lfix.hide(); v.addWidget(self.lfix)
            br = QHBoxLayout(); br.setSpacing(5)
            self.bmistake = self._btn("▶ Mistake Film", C["danger"])
            self.bhigh    = self._btn("⭐ Highlights",  C["green"])
            self.byt      = self._btn("📤 Post YouTube", C["blue"])
            self.bclose   = self._btn("✕", C["muted"], small=True)
            self.bmistake.clicked.connect(self._on_mistake)
            self.bhigh.clicked.connect(self._on_highlights)
            self.byt.clicked.connect(self._on_youtube)
            self.bclose.clicked.connect(self.hide_overlay)
            for b in [self.bmistake, self.bhigh, self.byt]: br.addWidget(b)
            br.addStretch(); br.addWidget(self.bclose); v.addLayout(br)
            return f

        def _btn(self, label, color, small=False):
            b = QPushButton(label)
            pad = "3px 6px" if small else "5px 10px"; fsz = "9px" if small else "10px"
            b.setStyleSheet(f"QPushButton{{background:rgba(255,255,255,10);color:{color};border:1px solid {color};border-radius:5px;padding:{pad};font-size:{fsz};}}QPushButton:hover{{background:rgba(255,255,255,22);}}")
            return b

        def _position(self):
            if not PYQT5_AVAILABLE: return
            s = QApplication.primaryScreen().geometry()
            self.move(s.width()-self.width()-20, s.height()-self.height()-55)

        def show_intro(self, player_name=PLAYER_NAME, player_handle=PLAYER_HANDLE):
            intro = (
                f"Hey. I'm Aria.\n\nYour coach. Your analyst. Your second set of eyes.\n\n"
                f"I've reviewed your replays, {player_handle}. You belong higher than Gold Four. "
                f"The gap between you and Predator is decisions — positioning, when to peek, when to hold.\n\n"
                f"Main Alter. Use Void Passage mid-fight to reposition — stop peeking the same angle twice.\n\n"
                f"Launch Apex. I'll be watching every fight.\n\n— Aria  ·  @migikonokami"
            )
            self.lstats.setText(f"{player_name}  ·  Gold 4  ·  Road to Predator  ·  Alter main")
            self.lfix.setText("► Launch Apex via  LAUNCH_APEX.bat"); self.lfix.show()
            self.sprite.set_state(TALKING); self.show(); self._fade_in(); self._typewrite(intro)
            self._speak(intro[:400])

        def show_post_match(self, session_summary: dict, coaching_report: str,
                            primary_fix: str = "", analyses: list = None):
            self._analyses = analyses or []
            k = session_summary.get("knock_count",0)
            d = session_summary.get("death_count",0)
            c = session_summary.get("total_clips",0)
            self.lstats.setText(f"{k} knocks  •  {d} deaths  •  {c} clips saved")
            if primary_fix: self.lfix.setText(f"📌 Focus next session: {primary_fix}"); self.lfix.show()
            else: self.lfix.hide()
            if d == 0 and k >= 3: self.sprite.set_state(PROUD)
            elif d >= 3:          self.sprite.set_state(CONCERNED)
            else:                 self.sprite.set_state(TALKING)
            self.show(); self._fade_in(); self._typewrite(coaching_report)
            self._speak(coaching_report[:380])

        def _typewrite(self, text: str):
            self.txt.clear(); self._tw_text = text; self._tw_pos = 0
            if self._tw_timer: self._tw_timer.stop()
            self._tw_timer = QTimer(); self._tw_timer.timeout.connect(self._tw_tick)
            self._tw_timer.start(16)

        def _tw_tick(self):
            if self._tw_pos < len(self._tw_text):
                self.txt.setPlainText(self.txt.toPlainText() + self._tw_text[self._tw_pos])
                self.txt.verticalScrollBar().setValue(self.txt.verticalScrollBar().maximum())
                self._tw_pos += 1
            else:
                self._tw_timer.stop()

        def _speak(self, text: str):
            if not self.tts: return
            self.sprite.set_state(TALKING)
            self._vthread = VoiceThread(text, self.tts, speaker_wav=getattr(self, "_speaker_wav", None))
            self._vthread.done.connect(lambda: self.sprite.set_state(IDLE))
            self._vthread.start()

        def _fade_in(self):
            self.setWindowOpacity(0.0)
            a = QPropertyAnimation(self, b"windowOpacity")
            a.setDuration(500); a.setStartValue(0.0); a.setEndValue(0.93)
            a.setEasingCurve(QEasingCurve.OutCubic); a.start(); self._fade_ref = a

        def hide_overlay(self):
            a = QPropertyAnimation(self, b"windowOpacity")
            a.setDuration(350); a.setStartValue(self.windowOpacity()); a.setEndValue(0.0)
            a.setEasingCurve(QEasingCurve.InCubic); a.finished.connect(self.hide)
            a.start(); self._fade_ref = a

        def _on_mistake(self):
            self.sprite.set_state(POINTING)
            for a in self._analyses:
                if a.get("event_type") in ("knocked_by_enemy","killed_by_enemy"):
                    p = a.get("clip_path","")
                    if p and os.path.exists(p):
                        os.startfile(p) if sys.platform=="win32" else os.system(f"xdg-open '{p}'")
                        break
            self._speak("Watch this. This is where it went wrong.")

        def _on_highlights(self):
            self.sprite.set_state(PROUD)
            for a in self._analyses:
                if a.get("event_type") in ("knock_by_you","kill_by_you"):
                    p = a.get("clip_path","")
                    if p:
                        folder = str(Path(p).parent)
                        os.startfile(folder) if sys.platform=="win32" else os.system(f"xdg-open '{folder}'")
                        break
            self._speak("These are your best plays. Study what you did right.")

        def _on_youtube(self):
            self._speak("Compiling your highlights. Ready for Sunday upload.")
            logger.info("YouTube post requested via overlay")

        def mousePressEvent(self, e):
            if e.button() == Qt.LeftButton:
                self._drag = e.globalPos() - self.frameGeometry().topLeft()

        def mouseMoveEvent(self, e):
            if e.buttons() == Qt.LeftButton and hasattr(self,"_drag"):
                self.move(e.globalPos() - self._drag)

else:
    # Stub when PyQt5 not installed
    class AriaOverlay:
        def __init__(self, config=None): self.config = config or {}
        def show_intro(self, **kw): pass
        def show_post_match(self, **kw): pass
        def hide_overlay(self): pass

# ════════════════════════════════════════════════════════════════
#  YOUTUBE MANAGER
# ════════════════════════════════════════════════════════════════

APEX_LEGEND_PERSONAS: dict[str, str] = {
    "Alter":      "Alter — mysterious void-walker. Short, cryptic lines. Dark humor. Calls enemies 'echoes.'",
    "Wraith":     "Wraith — cold, intense. 'The voices warned me.' Short sentences.",
    "Bangalore":  "Bangalore — military precision. 'Oscar Mike', 'copy that'. Tactical.",
    "Bloodhound": "Bloodhound — Old Norse warrior. 'Skál', 'the Allfather'. Honor.",
    "Lifeline":   "Lifeline — Jamaican energy. Calls people 'love'. No-nonsense.",
    "Pathfinder": "Pathfinder — cheerful MRVN. Says 'friend!' constantly.",
    "Octane":     "Octane — adrenaline junkie. '¡Rápido!', '¡Vamos!'. Exclamation marks.",
    "Horizon":    "Horizon — Scottish scientist. Physics metaphors. Warm.",
    "Loba":       "Loba — glamorous thief. Aristocratic confidence.",
    "Seer":       "Seer — poet-warrior. Moths, light, destiny. Calm intensity.",
    "Valkyrie":   "Valkyrie — cocky pilot. Flight metaphors.",
    "Ash":        "Ash — cold Simulacrum. 'Acceptable losses.' No warmth.",
    "Mad Maggie": "Mad Maggie — furious Salvo warrior. Loves explosions.",
    "Newcastle":  "Newcastle — hero. Protective. Family. Never leaves anyone behind.",
    "Revenant":   "Revenant — nihilistic simulacrum. Mocks everything.",
    "Fuse":       "Fuse — Australian explosives nut. 'Mate.' Party atmosphere.",
    "Rampart":    "Rampart — South Asian weapons modder. Calls her LMG 'Sheila'.",
    "Crypto":     "Crypto — paranoid hacker. Trusts no one. Tech jargon.",
    "Mirage":     "Mirage — class clown hiding insecurity. Bad jokes constantly.",
}

LEGEND_COSPLAY_LINES: dict[str, str] = {
    "Alter":      "...that play existed between what is and what isn't. 🌀",
    "Wraith":     "The voices said run. He ran the right way. ⚡",
    "Bangalore":  "Oscar Mike. No hesitation. Textbook execution. 🎖️",
    "Bloodhound": "The Allfather guided your hands on that one. 🐦‍⬛",
    "Lifeline":   "Okay love — even I didn't think you had that in you. 💚",
    "Pathfinder": "GREATEST. GRAPPLE. EVER. (said with full sincerity, friend!) 🤖",
    "Octane":     "¡¡RÁPIDO!! That was actually perfect!! VAMOS!! ⚡💉",
    "Horizon":    "The gravitational poetry of that repositioning... chef's kiss. 🪐",
    "Loba":       "Darling. That was *exquisite.* 💎",
    "Seer":       "The moth flies toward the light. You became the light. 🦋",
    "Valkyrie":   "Jets hot, decision perfect. VTOL kings. 🚀",
    "Ash":        "Acceptable. Actually — impressive. Don't tell anyone I said that.",
    "Mad Maggie": "THAT'S what I'm talking about!! BLOW IT ALL UP!! 💥",
    "Newcastle":  "You protected the squad AND cleaned up. That's a hero play. 🛡️",
    "Revenant":   "You died eventually anyway. But not today. That was worthy.",
    "Fuse":       "MATE. That was the best thing I've seen all season. Cheers! 🔥",
    "Rampart":    "Okay okay even Sheila would be proud of that one 😤💪",
    "Crypto":     "Surveillance confirmed: that play was flawless. 💻",
    "Mirage":     "Okay but did you see THAT? Almost as good as me. Almost.",
}


class YouTubeManager:
    def __init__(self, config: dict):
        self.config        = config
        self.upload_day    = config.get("upload_day", "sunday")
        self.upload_time   = config.get("upload_time", "20:00")
        self.visibility    = config.get("default_visibility", "public")
        self.output_dir    = Path("data/youtube"); self.output_dir.mkdir(parents=True, exist_ok=True)
        self.clips_dir     = Path("data/clips")
        self.week_queue: list[dict] = []
        self.youtube       = None
        self.openai_client, _, self._text_model = _build_ai_client(config)

    def authenticate(self, credentials_file="config/youtube_credentials.json",
                     token_file="config/youtube_token.json") -> bool:
        if not YOUTUBE_API_AVAILABLE:
            logger.error("google-api-python-client not installed"); return False
        creds = None
        if os.path.exists(token_file):
            creds = Credentials.from_authorized_user_file(token_file, YOUTUBE_SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(GRequest())
            else:
                if not os.path.exists(credentials_file):
                    logger.error(f"YouTube credentials not found: {credentials_file}"); return False
                flow  = InstalledAppFlow.from_client_secrets_file(credentials_file, YOUTUBE_SCOPES)
                creds = flow.run_local_server(port=0)
            with open(token_file,"w") as f: f.write(creds.to_json())
        self.youtube = yt_build("youtube","v3",credentials=creds)
        logger.info("YouTube API authenticated ✅"); return True

    def add_clip_to_queue(self, clip_meta: dict):
        self.week_queue.append(clip_meta); self._save_queue()

    def _save_queue(self):
        with open(self.output_dir/"week_queue.json","w") as f: json.dump(self.week_queue,f,indent=2)

    def _load_queue(self):
        p = self.output_dir/"week_queue.json"
        if p.exists():
            with open(p) as f: self.week_queue = json.load(f)

    def compile_weekly_video(self, session_reports: list) -> str:
        highlights, mistakes = self._select_best_clips(session_reports)
        if not highlights and not mistakes: return ""
        script = self._generate_video_script(highlights, mistakes, session_reports)
        if MOVIEPY_AVAILABLE and CV2_AVAILABLE:
            return self._compile_with_moviepy(highlights, mistakes, script)
        return self._compile_basic(highlights, mistakes)

    def _select_best_clips(self, session_reports: list) -> tuple:
        all_h, all_m = [], []
        for report in session_reports:
            for clip in report.get("highlights",[]):
                ap = Path(clip.get("clip_path","")).with_suffix("")
                ap = Path(str(ap)+"_analysis.json")
                clip["quality"] = json.load(open(ap)).get("overall_score",5) if ap.exists() else 5
                all_h.append(clip)
            for clip in report.get("mistakes",[]):
                ap = Path(clip.get("clip_path","")).with_suffix("")
                ap = Path(str(ap)+"_analysis.json")
                clip["interest"] = 10 - json.load(open(ap)).get("overall_score",5) if ap.exists() else 5
                all_m.append(clip)
        all_h.sort(key=lambda x: x.get("quality",0), reverse=True)
        all_m.sort(key=lambda x: x.get("interest",0), reverse=True)
        return all_h[:5], all_m[:1]

    def _generate_video_script(self, highlights, mistakes, session_reports) -> dict:
        if not self.openai_client: return self._default_script(session_reports)
        total_k  = sum(r.get("knock_count",0) for r in session_reports)
        total_d  = sum(r.get("death_count",0) for r in session_reports)
        rank     = self.config.get("current_rank","Gold IV")
        rp       = self.config.get("current_rp",0)
        best_score = float(highlights[0].get("quality",0)) if highlights else 0.0
        cosplay_ctx = ""
        if best_score >= 9.0:
            legend = highlights[0].get("legend", self.config.get("legend_main","Alter"))
            persona = APEX_LEGEND_PERSONAS.get(legend, f"{legend} personality.")
            cosplay_ctx = (
                f"\n⚠️ COSPLAY MODE: Best clip scored {best_score}/10. "
                f"For thumbnail_text, cold_open_text, aria_intro_voiceover ONLY — "
                f"write as {legend}: {persona}\nThen return to Aria's normal voice.\n"
            )
            logger.info(f"🎭 Cosplay mode: Aria as {legend}")
        prompt = (
            f"You are Aria (@migikonokami), Apex Legends coach, running @{PLAYER_HANDLE} YouTube.{cosplay_ctx}\n"
            f"Week: {len(session_reports)} sessions, {total_k} knocks, {total_d} deaths. "
            f"Rank: {rank} ({rp} RP).\n"
            "Write a video script JSON with: video_title, video_description, cold_open_text, "
            "aria_intro_voiceover, highlight_callouts (list), mistake_breakdown_intro, "
            "mistake_breakdown_commentary, improvement_summary, outro, tags (list), thumbnail_text."
        )
        try:
            resp   = self.openai_client.chat.completions.create(
                model=self._text_model, messages=[{"role":"user","content":prompt}],
                max_tokens=1200, temperature=0.7)
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            logger.error(f"Script gen failed: {e}"); return self._default_script(session_reports)

    def _default_script(self, session_reports) -> dict:
        k    = sum(r.get("knock_count",0) for r in session_reports)
        week = datetime.now().strftime("%B %d")
        rank = self.config.get("current_rank","Gold IV")
        return {
            "video_title":       f"Aria's Film Room — {week} | {rank} Grind",
            "video_description": f"{PLAYER_HANDLE} weekly Apex breakdown. {k} knocks. "
                                 f"Coached by Aria ({COACH_HANDLE}).\n#ApexLegends #RoadToPredator",
            "cold_open_text":    "BEST PLAY OF THE WEEK",
            "aria_intro_voiceover": f"Another week of film. {k} knocks. Let's get into it.",
            "highlight_callouts": ["CLEAN","NICE READ","GOOD MOVEMENT","SHARP","THAT'S IT"],
            "mistake_breakdown_intro": "Watch this and tell me what you see wrong.",
            "mistake_breakdown_commentary": "Stopped moving. Two seconds stationary. Free kill.",
            "improvement_summary": f"{self.config.get('current_rp',0)} RP in {rank}. Closing the gap.",
            "outro": "Subscribe to watch this climb to Predator. See you next Sunday.",
            "tags": ["apex legends","apex ranked","road to predator","apex coaching",
                     PLAYER_HANDLE, "lefthanddevil"],
            "thumbnail_text": "ARIA REVIEWS YOUR PLAYS",
        }

    def _compile_with_moviepy(self, highlights, mistakes, script) -> str:
        clips = []
        for clip_meta in (highlights[:5] + mistakes[:1]):
            p = clip_meta.get("clip_path","")
            if p and os.path.exists(p):
                try:
                    c = VideoFileClip(p); clips.append(c.subclip(0, min(15, c.duration)))
                except Exception as e: logger.warning(f"Clip load failed: {e}")
        if not clips: return self._compile_basic(highlights, mistakes)
        try:
            final    = concatenate_videoclips(clips, method="compose")
            out_path = str(self.output_dir / f"weekly_{datetime.now().strftime('%Y%m%d')}.mp4")
            final.write_videofile(out_path, codec="libx264", audio_codec="aac",
                                  fps=30, logger=None)
            return out_path
        except Exception as e:
            logger.error(f"MoviePy failed: {e}"); return self._compile_basic(highlights, mistakes)

    def _compile_basic(self, highlights, mistakes) -> str:
        paths = []
        for c in highlights[:5] + mistakes[:1]:
            p = c.get("clip_path","")
            if p and os.path.exists(p):
                ann = p.replace(".mp4","_mistake_annotated.mp4")
                paths.append(ann if os.path.exists(ann) else p)
        if not paths: return ""
        out_path  = str(self.output_dir / f"weekly_{datetime.now().strftime('%Y%m%d')}.mp4")
        list_file = self.output_dir / "concat_list.txt"
        with open(list_file,"w") as f:
            for p in paths: f.write(f"file '{os.path.abspath(p)}'\n")
        ret = os.system(f'ffmpeg -y -f concat -safe 0 -i "{list_file}" '
                        f'-c:v libx264 -c:a aac "{out_path}" -loglevel error')
        return out_path if (ret == 0 and os.path.exists(out_path)) else ""

    def generate_thumbnail(self, video_path: str, script: dict) -> str:
        if not CV2_AVAILABLE or not os.path.exists(video_path): return ""
        try:
            cap  = cv2.VideoCapture(video_path)
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            best_frame, best_score = None, 0
            for pct in [0.1,0.2,0.3,0.4,0.5]:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(total*pct))
                ret, frame = cap.read()
                if ret:
                    score = np.sum(cv2.Canny(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY),50,150))
                    if score > best_score: best_score = score; best_frame = frame.copy()
            cap.release()
            if best_frame is None: return ""
            h, w = best_frame.shape[:2]
            overlay = best_frame.copy()
            cv2.rectangle(overlay,(0,0),(w,120),(0,0,0),-1)
            cv2.rectangle(overlay,(0,h-100),(w,h),(0,0,0),-1)
            cv2.addWeighted(overlay,0.6,best_frame,0.4,0,best_frame)
            txt = script.get("thumbnail_text","APEX FILM ROOM").upper()
            cv2.putText(best_frame,txt,(30,90),cv2.FONT_HERSHEY_DUPLEX,2.2,(50,50,220),6,cv2.LINE_AA)
            cv2.putText(best_frame,txt,(30,90),cv2.FONT_HERSHEY_DUPLEX,2.2,(255,255,255),2,cv2.LINE_AA)
            cv2.putText(best_frame,f"@{PLAYER_HANDLE}  |  coached by Aria",
                        (30,h-25),cv2.FONT_HERSHEY_DUPLEX,0.65,(180,180,220),1,cv2.LINE_AA)
            cv2.rectangle(best_frame,(0,0),(w,8),(50,50,200),-1)
            thumb = str(self.output_dir/f"thumbnail_{datetime.now().strftime('%Y%m%d')}.jpg")
            cv2.imwrite(thumb, best_frame, [cv2.IMWRITE_JPEG_QUALITY,95])
            return thumb
        except Exception as e:
            logger.error(f"Thumbnail failed: {e}"); return ""

    def upload_video(self, video_path: str, script: dict, thumbnail_path: str = "") -> str:
        if not self.youtube or not os.path.exists(video_path): return ""
        title    = script.get("video_title","Apex Legends | Weekly Film Room")
        desc     = script.get("video_description","")
        base_tags= ["apex legends","apex ranked","road to predator","apex coach",
                    PLAYER_NAME, PLAYER_HANDLE, "aria coach", COACH_HANDLE]
        all_tags = list(set(script.get("tags",[]) + base_tags))[:30]
        body     = {
            "snippet": {"title":title[:100],"description":desc[:5000],
                        "tags":all_tags,"categoryId":"20"},
            "status":  {"privacyStatus":self.visibility,"selfDeclaredMadeForKids":False},
        }
        media    = MediaFileUpload(video_path, mimetype="video/mp4",
                                   resumable=True, chunksize=10*1024*1024)
        logger.info(f"Uploading: {title}")
        try:
            request = self.youtube.videos().insert(part="snippet,status", body=body, media_body=media)
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status: logger.info(f"Upload: {int(status.progress()*100)}%")
            video_id = response.get("id","")
            logger.info(f"Upload complete ✅ — https://youtube.com/watch?v={video_id}")
            if thumbnail_path and os.path.exists(thumbnail_path):
                try:
                    self.youtube.thumbnails().set(
                        videoId=video_id,
                        media_body=MediaFileUpload(thumbnail_path,mimetype="image/jpeg")
                    ).execute()
                except Exception as e: logger.warning(f"Thumbnail: {e}")
            return video_id
        except Exception as e:
            logger.error(f"Upload failed: {e}"); return ""

    def start_weekly_scheduler(self, session_provider_fn):
        def job():
            logger.info("Weekly YouTube job triggered")
            try:
                reports   = session_provider_fn()
                if not reports: return
                video_path = self.compile_weekly_video(reports)
                if not video_path: return
                script     = self._generate_video_script([], [], reports)
                thumbnail  = self.generate_thumbnail(video_path, script)
                video_id   = self.upload_video(video_path, script, thumbnail)
                if video_id: self.week_queue = []; self._save_queue()
            except Exception as e: logger.error(f"Weekly YouTube job: {e}")
        getattr(schedule.every(), self.upload_day).at(self.upload_time).do(job)
        def run_sched():
            logger.info(f"YouTube scheduler — every {self.upload_day} at {self.upload_time}")
            while True: schedule.run_pending(); time.sleep(60)
        threading.Thread(target=run_sched, daemon=True, name="AriaYouTubeScheduler").start()
        logger.info("Weekly YouTube scheduler started ✅")

    def run_now(self, session_reports: list) -> str:
        video = self.compile_weekly_video(session_reports)
        if not video: return ""
        script = self._generate_video_script([], [], session_reports)
        thumb  = self.generate_thumbnail(video, script)
        return self.upload_video(video, script, thumb)


# ════════════════════════════════════════════════════════════════
#  SOCIAL MANAGER
# ════════════════════════════════════════════════════════════════

class SocialManager:
    SUBREDDIT = "apexlegends"

    def __init__(self, config: dict):
        self.config     = config
        self._twitter   = None
        self._reddit    = None
        if TWEEPY_AVAILABLE:
            ak = config.get("twitter_api_key",""); aks = config.get("twitter_api_secret","")
            at = config.get("twitter_access_token",""); ats = config.get("twitter_access_secret","")
            if all([ak,aks,at,ats]):
                try:
                    self._twitter = tweepy.Client(consumer_key=ak, consumer_secret=aks,
                                                  access_token=at, access_token_secret=ats)
                    logger.info("Twitter connected ✅")
                except Exception as e: logger.warning(f"Twitter: {e}")
        if PRAW_AVAILABLE:
            ci = config.get("reddit_client_id",""); cs = config.get("reddit_client_secret","")
            if ci and cs:
                try:
                    self._reddit = praw.Reddit(client_id=ci, client_secret=cs,
                                               user_agent=f"Aria coach for {PLAYER_NAME}")
                    logger.info("Reddit connected ✅")
                except Exception as e: logger.warning(f"Reddit: {e}")

    def post_match_highlight(self, clip_path: str, analysis) -> dict:
        score   = getattr(analysis,"overall_score",5.0)
        verdict = getattr(analysis,"overall_verdict","")
        fix     = getattr(analysis,"primary_fix","")
        legend  = getattr(analysis,"legend_played",self.config.get("legend_main","Alter"))
        if score >= 9.0:
            tweet = self._cosplay_tweet(verdict, score, legend)
            logger.info(f"🎭 Cosplay tweet as {legend}")
        else:
            tweet = self._highlight_tweet(verdict, fix, score)
        return {"twitter": self._tweet(tweet)}

    def post_youtube_drop(self, youtube_url: str, title: str, description: str) -> dict:
        tweet = (f"New video just dropped 🎥\n\n{title}\n\n{youtube_url}\n\n"
                 f"Full breakdown. Every mistake, every correct play.\n"
                 f"#{PLAYER_HANDLE} #ApexLegends #RoadToPredator")
        reddit_title = f"[{PLAYER_HANDLE}] {title} — AI coach breaks down every fight"
        reddit_body  = (f"Aria ({COACH_HANDLE}) reviewed every clip.\n\nVideo: {youtube_url}\n\n"
                        f"{description}\n\nCurrently {self.config.get('current_rank','Gold 4')} → Predator.")
        return {"twitter": self._tweet(tweet),
                "reddit":  self._reddit_post(reddit_title, reddit_body, youtube_url)}

    def post_rank_update(self, new_rank: str, rp: int) -> dict:
        tweet = (f"Rank update 📈\n\n{new_rank} — {rp} RP\n\n"
                 f"Aria had notes. I fixed it.\n#ApexLegends #{PLAYER_HANDLE} #RoadToPredator")
        return {"twitter": self._tweet(tweet)}

    def post_session_stats(self, session_summary: dict, coaching_report: str) -> dict:
        k   = session_summary.get("knock_count",0)
        d   = session_summary.get("death_count",0)
        kd  = round(k/max(d,1),2)
        tweet = (f"Session: {k} knocks / {d} deaths (KD {kd})\n\n"
                 f"Aria: {coaching_report[:140] if coaching_report else 'Review pending.'}\n\n"
                 f"#{PLAYER_HANDLE} #ApexLegends")
        return {"twitter": self._tweet(tweet)}

    def _tweet(self, text: str) -> str:
        if not self._twitter: return "skipped (no Twitter credentials)"
        try:
            if len(text) > 280: text = text[:277] + "..."
            resp = self._twitter.create_tweet(text=text)
            tid  = resp.data.get("id","?")
            logger.info(f"Tweet posted: {tid}"); return f"ok:{tid}"
        except Exception as e: logger.warning(f"Tweet failed: {e}"); return f"error:{e}"

    def _reddit_post(self, title: str, body: str, url: str = None) -> str:
        if not self._reddit: return "skipped (no Reddit credentials)"
        try:
            sub  = self._reddit.subreddit(self.SUBREDDIT)
            post = sub.submit(title=title, url=url) if url else sub.submit(title=title, selftext=body)
            logger.info(f"Reddit post: {post.url}"); return f"ok:{post.url}"
        except Exception as e: logger.warning(f"Reddit post: {e}"); return f"error:{e}"

    def _highlight_tweet(self, verdict: str, fix: str, score: float) -> str:
        if score >= 8:   opener = f"Clean fight from {PLAYER_HANDLE} 🔥"
        elif score >= 6: opener = "Decent fight. Room to improve."
        else:            opener = "Mistake caught. Noted. Fixed."
        lines = [opener]
        if verdict: lines.append(f"Aria: {verdict[:100]}")
        if fix and score < 8: lines.append(f"Fix: {fix[:80]}")
        lines.append(f"\n#{PLAYER_HANDLE} #ApexLegends #RoadToPredator")
        return "\n".join(lines)

    def _cosplay_tweet(self, verdict: str, score: float, legend: str) -> str:
        line = LEGEND_COSPLAY_LINES.get(legend, f"Elite play. As {legend} would say — respect.")
        tweet = (f"okay i had to —\n\n{line}\n\n"
                 f"{PLAYER_HANDLE} scored {score:.0f}/10.\n"
                 f"Full breakdown dropping this Sunday.\n\n"
                 f"#{PLAYER_HANDLE} #ApexLegends #{legend.replace(' ','')} #RoadToPredator")
        if len(tweet) > 280: tweet = tweet[:277] + "..."
        return tweet

# ════════════════════════════════════════════════════════════════
#  OBS SETUP HELPERS
# ════════════════════════════════════════════════════════════════

OBS_INSTALLER_URL = "https://github.com/obsproject/obs-studio/releases/download/30.1.2/OBS-Studio-30.1.2-Windows-Installer.exe"
ALT_OBS_PATHS = [
    r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
    r"C:\Program Files (x86)\obs-studio\bin\64bit\obs64.exe",
    str(Path.home() / r"AppData\Local\Programs\obs-studio\bin\64bit\obs64.exe"),
]

BUTTON_MAP = {
    "BTN_SOUTH":"A","BTN_EAST":"B","BTN_WEST":"X","BTN_NORTH":"Y",
    "BTN_TL":"LB","BTN_TR":"RB","BTN_TL2":"LT","BTN_TR2":"RT",
    "BTN_SELECT":"BACK","BTN_START":"START","BTN_THUMBL":"LS",
    "BTN_THUMBR":"RS","ABS_HAT0X":"DPAD◄►","ABS_HAT0Y":"DPAD▲▼",
}


def find_obs() -> Path | None:
    for p in [OBS_PATH] + ALT_OBS_PATHS:
        if Path(p).exists(): return Path(p)
    return None


def install_obs():
    obs_path = find_obs()
    if obs_path:
        print(f"[ARIA] OBS found: {obs_path} ✅"); return obs_path
    print("[ARIA] OBS not found — downloading OBS Studio 30.1.2...")
    installer = ARIA_DIR / "obs_installer.exe"
    try:
        def _progress(block, size, total):
            pct = min(int(block*size/total*100),100) if total > 0 else 0
            print(f"\r  Downloading OBS... {pct}%   ", end="", flush=True)
        urllib.request.urlretrieve(OBS_INSTALLER_URL, installer, _progress)
        print()
        subprocess.run([str(installer),"/S","/D=C:\\Program Files\\obs-studio"], check=True)
        installer.unlink(missing_ok=True)
        obs_path = find_obs()
        if obs_path: print(f"[ARIA] OBS installed ✅  {obs_path}"); return obs_path
        print("[ARIA] OBS install finished but not found — launch OBS manually."); return None
    except Exception as e:
        print(f"[ARIA] OBS install failed: {e}")
        installer.unlink(missing_ok=True); return None


def start_obs(obs_path: Path | None):
    if not obs_path: print("[ARIA] Skipping OBS — not found."); return
    if PSUTIL_AVAILABLE:
        try:
            if any("obs" in p.name().lower() for p in psutil.process_iter(["name"])):
                print("[ARIA] OBS already running ✅"); return
        except Exception: pass
    try:
        subprocess.Popen(
            [str(obs_path), "--minimize-to-tray", "--startreplaybuffer"],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0,
        )
        print("[ARIA] OBS launched with replay buffer ✅")
        time.sleep(3)
    except Exception as e: print(f"[ARIA] OBS launch failed: {e}")


def setup_liveapi():
    config = {
        "cl_liveapi_enabled": True,
        "cl_liveapi_use_websocket": True,
        "cl_liveapi_websocket_keepalive_enabled": True,
        "cl_liveapi_websocket_keepalive_interval": 30,
        "cl_liveapi_ws_datacenter_only": True,
        "cl_liveapi_ws_retry_count": 5,
        "cl_liveapi_ws_retry_time": 10,
        "cl_liveapi_requests": [{"url":"ws://127.0.0.1:7777","useMessagePack":False}],
    }
    json_str = json.dumps(config, indent=2)
    (ARIA_DIR/"liveapi.json").write_text(json_str)
    target = Path(APEX_LIVEAPI)
    if target.parent.exists():
        try:
            target.write_text(json_str)
            print("[ARIA] liveapi.json written to Apex folder ✅")
        except PermissionError:
            print(f"[ARIA] ⚠️  Couldn't write to Apex folder — copy aria/liveapi.json → {target.parent}")
    else:
        print("[ARIA] Apex folder not found — copy liveapi.json manually after first Apex launch")


def create_apex_launcher():
    bat = ARIA_DIR / "LAUNCH_APEX.bat"
    bat.write_text(
        f'@echo off\ntitle Launch Apex Legends — Aria Live API\n'
        f'echo.\necho  Launching Apex with Aria Live API...\necho.\n'
        f'start "" "{STEAM_PATH}" -applaunch 1172470 '
        f'+cl_liveapi_enabled 1 +cl_liveapi_use_websocket 1\n'
        f'timeout /t 3 /nobreak >nul\n'
    )
    print("[ARIA] LAUNCH_APEX.bat created ✅")


def patch_config():
    conf_path = ARIA_DIR / "config" / "aria.conf"
    if not conf_path.exists(): return
    cfg = configparser.ConfigParser(); cfg.read(conf_path); changed = False
    def _set(s, k, v):
        nonlocal changed
        if v and cfg.get(s, k, fallback="") == "":
            if s not in cfg: cfg[s] = {}
            cfg[s][k] = v; changed = True
    _set("analysis",  "openai_api_key", OPENAI_API_KEY)
    _set("recording", "obs_password",   OBS_PASSWORD)
    for section, key in [("player","username"),("detection","apex_username")]:
        if section not in cfg: cfg[section] = {}
        if cfg[section].get(key,"") != PLAYER_NAME:
            cfg[section][key] = PLAYER_NAME; changed = True
    if changed:
        with open(conf_path,"w") as f: cfg.write(f)
        print(f"[ARIA] Config updated ✅  (username: {PLAYER_NAME})")


def start_button_display():
    def _run():
        try:
            import inputs as _inputs
            held = set()
            print("\n[ARIA] 🎮 GameSir G7 Pro — live button display active")
            print("─"*50)
            while True:
                try:
                    for event in _inputs.get_gamepad():
                        label = BUTTON_MAP.get(event.code, event.code)
                        if event.ev_type == "Key":
                            if event.state == 1: held.add(label)
                            elif event.state == 0: held.discard(label)
                        display = "  ".join(sorted(held)) if held else "· · ·"
                        print(f"\r🎮  [ {display} ]          ", end="", flush=True)
                except Exception: time.sleep(2)
        except Exception: pass
    threading.Thread(target=_run, daemon=True, name="AriaButtonDisplay").start()


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close(); return ip
    except Exception: return "localhost"


def load_config(path: str = "config/aria.conf") -> dict:
    cfg = configparser.ConfigParser(); cfg.read(path)
    flat = {}
    for section in cfg.sections():
        for key, value in cfg.items(section): flat[key] = value
    return flat


def print_banner(local_ip: str, config: dict):
    rank    = config.get("current_rank","Gold 4")
    rp      = config.get("current_rp","143")
    api_ok  = bool(OPENAI_API_KEY or config.get("openai_api_key",""))
    api_str = "✅ set" if api_ok else "❌ MISSING — add to SETTINGS above"
    print(f"""
╔══════════════════════════════════════════════════════╗
║                    ARIA SYSTEM                       ║
║              Road to Predator                        ║
╠══════════════════════════════════════════════════════╣
║  Player:   {PLAYER_NAME:<25} ║
║  Handle:   {PLAYER_HANDLE:<25} ║
║  Coach:    Aria ({COACH_HANDLE})                  ║
║  Rank:     {rank:<20} {rp} RP               ║
║  Target:   Predator  |  Legend: {LEGEND_MAIN:<14}       ║
╠══════════════════════════════════════════════════════╣
║  OpenAI:   {api_str:<41}║
║  Kill feed: Apex Live API (no OCR, instant)          ║
║  Recording: OBS Replay Buffer (90s)                  ║
║  Controller: GameSir G7 Pro 8K                       ║
╠══════════════════════════════════════════════════════╣
║  Mobile: http://{local_ip}:{MOBILE_PORT}
║  ► Double-click  LAUNCH_APEX.bat  to start Apex      ║
╚══════════════════════════════════════════════════════╝
""")


def aria_intro():
    speech = (
        f"Hey. I'm Aria. Your coach, your analyst, your second set of eyes. "
        f"I've been watching every match, and I will not let you waste this season. "
        f"You're {PLAYER_HANDLE} — {PLAYER_NAME} in-game — "
        f"Gold Four right now, but that's not where you stay. "
        f"We're going to Predator. Not maybe. Not eventually. We are going. "
        f"Main {LEGEND_MAIN}. Use Void Passage to reposition mid-fight — "
        f"stop peeking the same angle twice. Now launch Apex. I'll be watching."
    )
    print("\n" + "═"*56)
    print("  ARIA — INTRODUCTION")
    print("═"*56)
    words, line = speech.split(), ""
    for word in words:
        if len(line) + len(word) + 1 > 54:
            print(f"  {line}"); line = word
        else:
            line = f"{line} {word}".strip()
    if line: print(f"  {line}")
    print("═"*56 + "\n")
    def _speak():
        try:
            tts = CoquiTTS(model_name="tts_models/en/ljspeech/tacotron2-DDC",
                           progress_bar=False)
            out = str(ARIA_DIR/"logs"/"aria_intro.wav")
            tts.tts_to_file(text=speech, file_path=out)
            if os.name == "nt":
                import winsound; winsound.PlaySound(out, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception: pass
    threading.Thread(target=_speak, daemon=True, name="AriaIntroVoice").start()


# ════════════════════════════════════════════════════════════════
#  ARIA SYSTEM  (orchestrator)
# ════════════════════════════════════════════════════════════════

class AriaSystem:
    def __init__(self, config: dict):
        self.config           = config
        self.running          = False
        self.clip_manager     = None
        self.controller       = None
        self.killfeed         = None
        self.overlay          = None
        self.youtube_manager  = None
        self.social_manager   = None
        self.mobile_thread    = None
        self.in_match         = False

    def start(self):
        self.running = True

        # System detection
        try:
            profile = load_system_profile()
            print_system_profile(profile)
        except Exception as e: logger.warning(f"System detection: {e}")

        # OBS
        try:
            self.clip_manager = OBSClipManager(self.config)
            if self.clip_manager.connect(): logger.info("OBS connected ✅")
            else: logger.warning("OBS not connected — check WebSocket Server is enabled")
        except Exception as e: logger.warning(f"OBS: {e}")

        # Controller
        try:
            self.controller = ControllerLogger(self.config)
            if self.controller.start(): logger.info("Controller logging started ✅")
            else: logger.warning("Controller not found — connect GameSir G7 Pro via USB")
        except Exception as e: logger.warning(f"Controller: {e}")

        # Kill feed — Live API preferred, OCR fallback
        try:
            self.killfeed = ApexLiveAPI(self.config, event_callback=self._on_game_event)
            if self.killfeed.start(): logger.info("Apex Live API active ✅")
            else: raise RuntimeError("Live API start returned False")
        except Exception as e:
            logger.warning(f"Live API failed ({e}) — falling back to OCR")
            try:
                self.killfeed = KillFeedDetector(self.config, event_callback=self._on_game_event)
                if self.killfeed.start(): logger.info("OCR kill feed fallback started ✅")
                else: logger.warning("OCR fallback also failed")
            except Exception as e2: logger.warning(f"OCR fallback: {e2}")

        # Social & YouTube managers
        self.social_manager  = SocialManager(self.config)
        self.youtube_manager = YouTubeManager(self.config)
        self.youtube_manager._load_queue()

        # Mobile API
        self._start_mobile_server()

        # Match watcher
        self._start_match_watcher()

        logger.info("All systems running — launch Apex and play 🎮")

    def _on_game_event(self, event: GameEvent):
        logger.info(f"Game event: {event.event_type.value} — {event.target}")
        if self.clip_manager:
            try:
                clip_path = self.clip_manager.save_clip(event)
                if clip_path: logger.info(f"Clip saved: {Path(clip_path).name}")
            except Exception as e: logger.error(f"Clip save: {e}")

    def _start_match_watcher(self):
        def watch():
            was_in_match = False
            while self.running:
                try:
                    if self.killfeed:
                        in_lobby = self.killfeed.detect_match_end()
                        n_events = len(self.killfeed.session_events)
                        if in_lobby and was_in_match and n_events > 0:
                            logger.info("Match ended — triggering coaching pipeline")
                            self._run_post_match()
                            was_in_match = False
                        elif not in_lobby and n_events > 0:
                            was_in_match = True
                except Exception as e: logger.debug(f"Match watcher: {e}")
                time.sleep(5)
        threading.Thread(target=watch, daemon=True, name="AriaMatchWatcher").start()

    def _run_post_match(self):
        logger.info("Running post-match pipeline...")

        session_summary  = {}
        controller_stats = {}

        if self.clip_manager:  session_summary  = self.clip_manager.end_session()
        if self.controller:
            controller_stats = self.controller.stop()
            self.controller.start()

        # Analyze clips
        analyses = []
        try:
            engine    = FightAnalysisEngine(self.config)
            all_clips = (session_summary.get("mistakes",[]) +
                         session_summary.get("highlights",[]))
            for clip_meta in all_clips[:int(self.config.get("max_clips_per_match",10))]:
                clip_path  = clip_meta.get("clip_path","")
                event_type = clip_meta.get("event_type","")
                if not clip_path or not Path(clip_path).exists(): continue
                ctrl_summary = self.controller.get_coaching_summary() if self.controller else ""
                live_ctx     = {}
                if hasattr(clip_meta, "live_api_context"): live_ctx = clip_meta.live_api_context
                analysis = engine.analyze_clip(clip_path, event_type, ctrl_summary,
                                               session_summary, live_ctx)
                if analysis:
                    analyses.append(analysis)
                    engine.save_analysis(analysis, str(Path(clip_path).parent))
        except Exception as e: logger.error(f"Clip analysis: {e}")

        # Session report
        coaching_report = ""
        primary_fix     = ""
        try:
            engine          = FightAnalysisEngine(self.config)
            coaching_report = engine.generate_session_report(analyses, session_summary, controller_stats)
            mistakes        = [a for a in analyses
                               if a.event_type in ("knocked_by_enemy","killed_by_enemy")]
            if mistakes: primary_fix = mistakes[0].primary_fix
        except Exception as e:
            logger.error(f"Report gen: {e}")
            k  = session_summary.get("knock_count",0)
            d  = session_summary.get("death_count",0)
            coaching_report = f"Match complete.\n{k} knocks, {d} deaths.\nAdd API key for full coaching."

        # Overlay
        self._show_overlay(session_summary, coaching_report, primary_fix, analyses)

        # Annotate mistakes in background
        def annotate():
            annotator = VideoAnnotator()
            for a in analyses:
                if a.event_type in ("knocked_by_enemy","killed_by_enemy"):
                    annotator.annotate_mistake(a.clip_path, asdict(a))
        threading.Thread(target=annotate, daemon=True, name="AriaAnnotator").start()

        # Queue highlights for YouTube
        try:
            for clip in session_summary.get("highlights",[]):
                self.youtube_manager.add_clip_to_queue(clip)
        except Exception as e: logger.debug(f"YouTube queue: {e}")

        # Post session stats to social
        try:
            self.social_manager.post_session_stats(session_summary, coaching_report)
        except Exception as e: logger.debug(f"Social post: {e}")

        logger.info("Post-match pipeline complete")

    def _show_overlay(self, session_summary, coaching_report, primary_fix, analyses):
        try:
            if not PYQT5_AVAILABLE: return
            app = QApplication.instance()
            if not app: return
            if not self.overlay: self.overlay = AriaOverlay(self.config)
            analyses_dicts = [{"event_type": a.event_type, "clip_path": a.clip_path,
                               "verdict": a.overall_verdict, "quality": a.fight_quality}
                              for a in analyses]
            self.overlay.show_post_match(session_summary=session_summary,
                                         coaching_report=coaching_report,
                                         primary_fix=primary_fix,
                                         analyses=analyses_dicts)
        except Exception as e: logger.error(f"Overlay: {e}")

    def _start_mobile_server(self):
        def run():
            try:
                run_mobile_server(self.config,
                                  host=self.config.get("host","0.0.0.0"),
                                  port=int(self.config.get("port", MOBILE_PORT)))
            except Exception as e: logger.error(f"Mobile server: {e}")
        self.mobile_thread = threading.Thread(target=run, daemon=True, name="AriaMobile")
        self.mobile_thread.start()
        logger.info(f"Mobile companion starting on port {self.config.get('port', MOBILE_PORT)} ✅")

    def stop(self):
        self.running = False
        if self.killfeed:     self.killfeed.stop()
        if self.controller:   self.controller.stop()
        if self.clip_manager: self.clip_manager.disconnect()
        logger.info("Aria system stopped")


# ════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════

def main():
    import platform as _plat
    print(__doc__)

    os.chdir(ARIA_DIR)
    for folder in ["data/clips","data/sessions","data/reports","data/youtube",
                   "data/annotated","logs","assets/sprites","assets/templates",
                   "assets/sounds","config"]:
        os.makedirs(folder, exist_ok=True)

    # 1. Install packages
    install_packages()

    # 2. Re-setup loguru now that it's installed
    try:
        from loguru import logger as _logger
        _logger.remove()
        _logger.add(sys.stdout, level="INFO",
                    format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}")
        _logger.add("logs/aria.log", level="DEBUG", rotation="50 MB",
                    format="{time} | {level} | {message}")
    except Exception:
        pass

    # 3. Patch config with settings from top of this file
    patch_config()

    # 4. OBS
    obs_path = install_obs()
    start_obs(obs_path)

    # 5. Apex Live API config
    setup_liveapi()

    # 6. Apex launcher shortcut
    create_apex_launcher()

    # 7. GameSir button display
    start_button_display()

    # 8. Load config
    config = load_config("config/aria.conf")
    if OPENAI_API_KEY: config["openai_api_key"] = OPENAI_API_KEY

    # 9. Print banner
    local_ip = get_local_ip()
    print_banner(local_ip, config)

    # 10. Aria's intro speech
    aria_intro()

    # 11. Launch
    _launch_aria(config)


def _launch_aria(config: dict):
    aria = AriaSystem(config)

    if PYQT5_AVAILABLE:
        try:
            app = QApplication(sys.argv)
            app.setQuitOnLastWindowClosed(False)
            aria.start()

            # Show intro overlay after 2 seconds
            def _show_intro():
                try:
                    overlay = AriaOverlay(config)
                    overlay.show_intro(player_name=PLAYER_NAME, player_handle=PLAYER_HANDLE)
                    app._aria_intro_overlay = overlay
                except Exception as e:
                    logger.warning(f"Intro overlay: {e}")
            QTimer.singleShot(2000, _show_intro)

            logger.info("Aria is active. Waiting for Apex... 🎮")
            try:
                sys.exit(app.exec_())
            except (SystemExit, KeyboardInterrupt):
                aria.stop()
        except Exception as e:
            logger.warning(f"Qt failed: {e} — running without overlay")
            _run_headless(aria)
    else:
        logger.warning("PyQt5 not installed — running without overlay (pip install PyQt5)")
        _run_headless(aria)

    logger.info("Aria stopped. GG.")


def _run_headless(aria: AriaSystem):
    aria.start()
    logger.info("Aria is active. Waiting for Apex... 🎮")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        aria.stop()


if __name__ == "__main__":
    main()
