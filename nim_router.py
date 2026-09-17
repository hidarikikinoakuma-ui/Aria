"""
nim_router.py — Smart AI endpoint router for Aria
===================================================
Automatically switches AI calls between:
  - Ollama (local, Qwen2.5-VL 7B) — when Apex is NOT running
  - Cloud NIM (NVIDIA API)        — when Apex IS running (protect GPU/fps)

Logic:
  r5apex_dx12.exe running     →  cloud NIM  (don't compete with GPU)
  r5apex_dx12.exe NOT running →  local Ollama (full VRAM, fast, free)

Used by aria_server.py to get the right OpenAI client on each request.
"""

import os
import time
import threading
from loguru import logger

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from openai import OpenAI

# ── Config ────────────────────────────────────────────────────────────────────

APEX_PROCESS    = "r5apex_dx12.exe"
CHECK_INTERVAL  = 15          # seconds between process checks

# Ollama runs on Windows host — Docker reaches it via host.docker.internal
OLLAMA_URL      = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434/v1")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "qwen2.5vl:7b")

CLOUD_NIM_URL   = os.getenv("NIM_BASE_URL_CLOUD", "https://integrate.api.nvidia.com/v1")
CLOUD_NIM_MODEL = os.getenv("AI_MODEL_CLOUD", "qwen/qwen3.5-vl")   # cloud fallback model
NIM_API_KEY     = os.getenv("NIM_API_KEY", "")

# FORCE_LOCAL=true  → always use Ollama, never switch to cloud
# FORCE_CLOUD=true  → always use cloud NIM, never use Ollama
FORCE_LOCAL     = os.getenv("FORCE_LOCAL", "").lower() in ("true", "1", "yes")
FORCE_CLOUD     = os.getenv("FORCE_CLOUD", "").lower() in ("true", "1", "yes")

# Aria's Windows companion agent (ARIA_ALL_IN_ONE.py) can POST to this endpoint
# on the Docker container to report Apex process state — solves the Docker/Windows
# process visibility gap without needing host PID namespace sharing.
# Set APEX_SIGNAL_ENDPOINT="" to disable this and rely only on psutil.
APEX_SIGNAL_ENDPOINT = os.getenv("APEX_SIGNAL_ENDPOINT", "")

# For callers that read AI_MODEL from this module
AI_MODEL        = OLLAMA_MODEL


class NIMRouter:
    """
    Maintains two OpenAI-compatible clients (Ollama local + cloud NIM) and
    returns the right one based on whether Apex is running.

    Three ways it detects Apex:
    1. psutil process scan (works when running natively, not from Docker)
    2. External signal — ARIA_ALL_IN_ONE.py calls set_apex_running(True/False)
       when it detects the process on Windows, then the container reads it.
    3. FORCE_LOCAL / FORCE_CLOUD env vars — manual override for testing.

    Thread-safe.
    """

    def __init__(self):
        self._apex_running = False
        self._apex_signaled = False   # set by external signal from Windows host
        self._lock = threading.Lock()

        if FORCE_LOCAL:
            logger.info("FORCE_LOCAL=true — always using Ollama, ignoring Apex state")
        elif FORCE_CLOUD:
            logger.info("FORCE_CLOUD=true — always using cloud NIM, ignoring Apex state")

        # Ollama — OpenAI-compatible, no key needed
        self._local_client = OpenAI(
            base_url=OLLAMA_URL,
            api_key="ollama",   # Ollama ignores this but the client requires something
        )

        # Cloud NIM — used when Apex is running
        self._cloud_client = OpenAI(
            base_url=CLOUD_NIM_URL,
            api_key=NIM_API_KEY,
        ) if NIM_API_KEY else None

        # Start background checker
        self._checker = threading.Thread(target=self._check_loop, daemon=True)
        self._checker.start()
        logger.info(
            f"NIM router started — "
            f"local: Ollama {OLLAMA_MODEL} @ {OLLAMA_URL} | "
            f"cloud: {CLOUD_NIM_MODEL} @ {CLOUD_NIM_URL}"
        )
        logger.info(f"Watching for {APEX_PROCESS} every {CHECK_INTERVAL}s")

    def set_apex_running(self, running: bool):
        """
        External signal — called by ARIA_ALL_IN_ONE.py on the Windows host
        via a POST to /api/apex-state so the container knows Apex state
        without needing host PID namespace access.
        """
        with self._lock:
            changed = running != self._apex_signaled
            self._apex_signaled = running
            self._apex_running = running
        if changed:
            logger.info(
                f"Apex state updated via external signal: "
                f"{'RUNNING' if running else 'CLOSED'}"
            )

    def _is_apex_running(self) -> bool:
        """Check if r5apex_dx12.exe is in the process list via psutil."""
        if not PSUTIL_AVAILABLE:
            return False
        try:
            for proc in psutil.process_iter(["name"]):
                if proc.info["name"] and \
                   proc.info["name"].lower() == APEX_PROCESS.lower():
                    return True
        except Exception:
            pass
        return False

    def _check_loop(self):
        """Background thread — checks process list every CHECK_INTERVAL seconds."""
        while True:
            try:
                # Only use psutil if no external signal has been received
                with self._lock:
                    has_signal = self._apex_signaled is not False  # once set, trust it
                if not has_signal:
                    running = self._is_apex_running()
                    with self._lock:
                        if running != self._apex_running:
                            self._apex_running = running
                            if running:
                                logger.info(
                                    f"{APEX_PROCESS} detected via psutil — "
                                    "switching to CLOUD NIM"
                                )
                            else:
                                logger.info(
                                    "Apex closed (psutil) — "
                                    f"switching to LOCAL Ollama ({OLLAMA_MODEL})"
                                )
            except Exception as e:
                logger.warning(f"Process check error: {e}")
            time.sleep(CHECK_INTERVAL)

    @property
    def apex_running(self) -> bool:
        if FORCE_LOCAL:
            return False
        if FORCE_CLOUD:
            return True
        with self._lock:
            return self._apex_running

    def get_client(self) -> tuple["OpenAI", str, str]:
        """
        Returns (client, endpoint_label, model_name).
        Call this before every AI request.
        """
        use_cloud = self.apex_running   # property handles FORCE flags

        if use_cloud:
            if self._cloud_client is None:
                logger.warning(
                    "Apex is running but no NIM_API_KEY set — "
                    "falling back to local Ollama (may affect GPU/framerate)"
                )
                return self._local_client, "local-fallback", OLLAMA_MODEL
            return self._cloud_client, "cloud", CLOUD_NIM_MODEL
        else:
            return self._local_client, "local", OLLAMA_MODEL

    def status(self) -> dict:
        """Return current routing status — shown at GET /api/nim-status."""
        client, endpoint, model = self.get_client()
        return {
            "apex_running":      self.apex_running,
            "active_endpoint":   endpoint,
            "active_model":      model,
            "force_local":       FORCE_LOCAL,
            "force_cloud":       FORCE_CLOUD,
            "local_url":         OLLAMA_URL,
            "local_model":       OLLAMA_MODEL,
            "cloud_url":         CLOUD_NIM_URL,
            "cloud_model":       CLOUD_NIM_MODEL,
            "reason": (
                "FORCE_LOCAL override" if FORCE_LOCAL else
                "FORCE_CLOUD override" if FORCE_CLOUD else
                f"{APEX_PROCESS} running — using cloud NIM to protect GPU"
                if self.apex_running
                else f"Apex not running — using local Ollama ({OLLAMA_MODEL})"
            ),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
# Import this and call nim_router.get_client() anywhere in the app.

nim_router = NIMRouter()
