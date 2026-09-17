"""
aria_server.py — Docker entry point for the Aria backend container.

Reads config from environment variables (set in docker-compose.yml / .env),
wires up the NIM router (auto-switches cloud/local based on Apex process),
then starts the FastAPI mobile companion server.

Auto-switch logic:
  r5apex_dx12.exe running  →  cloud NIM  (protect GPU / framerate)
  r5apex_dx12.exe NOT running  →  local NIM container (full GPU speed)
"""

import os
import uvicorn
from loguru import logger
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from mobile.mobile_api import MobileCompanionAPI
from nim_router import nim_router

# ── Read config from environment ──────────────────────────────────────────────

AI_MODEL       = os.getenv("AI_MODEL", "nvidia/nemotron-nano-vl-8b-v1")
TTS_SERVER_URL = os.getenv("TTS_SERVER_URL", "http://tts:5002")
MOBILE_PORT    = int(os.getenv("MOBILE_PORT", "8765"))

config = {
    "ai_backend":        "nim_router",   # signals to use nim_router, not a static client
    "ai_model":          AI_MODEL,
    "tts_server_url":    TTS_SERVER_URL,
    "current_rank":      os.getenv("CURRENT_RANK", "Gold IV"),
    "current_rp":        int(os.getenv("CURRENT_RP", "143")),
    # Social
    "twitter_api_key":    os.getenv("TWITTER_API_KEY", ""),
    "twitter_api_secret": os.getenv("TWITTER_API_SECRET", ""),
    "twitter_access_token":  os.getenv("TWITTER_ACCESS_TOKEN", ""),
    "twitter_access_secret": os.getenv("TWITTER_ACCESS_SECRET", ""),
    "reddit_client_id":     os.getenv("REDDIT_CLIENT_ID", ""),
    "reddit_client_secret": os.getenv("REDDIT_CLIENT_SECRET", ""),
}

logger.info(f"AI model: {AI_MODEL}")
logger.info(f"TTS server: {TTS_SERVER_URL}")
logger.info("NIM router active — watching for r5apex_dx12.exe")

# ── Build the FastAPI app ─────────────────────────────────────────────────────

api = MobileCompanionAPI(config)
app = api.build_app()

# ── Extra routes ─────────────────────────────────────────────────────────────

@app.get("/api/nim-status")
def nim_status():
    """Shows which AI endpoint is active and why."""
    return JSONResponse(nim_router.status())

@app.post("/api/apex-state")
def apex_state(body: dict):
    """
    Called by ARIA_ALL_IN_ONE.py on the Windows host to signal Apex process state.
    Solves the Docker/Windows process-visibility gap without host PID namespace.

    POST /api/apex-state
    {"running": true}   ← Apex just launched
    {"running": false}  ← Apex just closed
    """
    running = bool(body.get("running", False))
    nim_router.set_apex_running(running)
    return {"ok": True, "apex_running": running, "routing": nim_router.status()}

@app.get("/health/full")
def health_full():
    return {
        "status": "online",
        "aria": "ready",
        "nim": nim_router.status(),
        "tts_url": TTS_SERVER_URL,
    }

# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "aria_server:app",
        host="0.0.0.0",
        port=MOBILE_PORT,
        log_level="info",
        reload=False,
    )
