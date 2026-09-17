"""
Aria Voice Server
=================
Wraps Coqui XTTS v2 as a simple HTTP API.
The Aria backend calls this to generate speech.

Endpoints:
  GET  /health          — liveness check
  POST /tts             — generate speech, returns WAV bytes
  POST /tts/stream      — (future) streaming audio
  GET  /speakers        — list available speakers
"""

import io
import os
import time
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from loguru import logger
import uvicorn

# ── Config ────────────────────────────────────────────────────────────────────

MODEL_NAME      = os.getenv("TTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2")
DEFAULT_SPEAKER = os.getenv("TTS_SPEAKER", "Ana Florence")
DEFAULT_LANG    = os.getenv("TTS_LANGUAGE", "en")
VOICE_DIR       = Path(os.getenv("VOICE_DIR", "/tts/voices"))
CUSTOM_VOICE    = VOICE_DIR / "aria_voice_ref.wav"   # drop your WAV here to clone it

app = FastAPI(title="Aria Voice Server", version="1.0.0")

# ── Model load (once at startup) ──────────────────────────────────────────────

tts_model = None

@app.on_event("startup")
async def load_model():
    global tts_model
    logger.info(f"Loading TTS model: {MODEL_NAME}")
    start = time.time()
    try:
        from TTS.api import TTS
        tts_model = TTS(MODEL_NAME)
        logger.info(f"TTS model ready in {time.time()-start:.1f}s")
        if CUSTOM_VOICE.exists():
            logger.info(f"Custom voice file found: {CUSTOM_VOICE} — will use voice cloning")
        else:
            logger.info(f"No custom voice at {CUSTOM_VOICE} — using speaker: {DEFAULT_SPEAKER}")
    except Exception as e:
        logger.error(f"Failed to load TTS model: {e}")
        raise

# ── Request/Response models ───────────────────────────────────────────────────

class TTSRequest(BaseModel):
    text: str
    speaker: str = DEFAULT_SPEAKER
    language: str = DEFAULT_LANG
    speed: float = 1.0

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok" if tts_model is not None else "loading",
        "model": MODEL_NAME,
        "speaker": DEFAULT_SPEAKER,
        "custom_voice": CUSTOM_VOICE.exists(),
    }

@app.get("/speakers")
def list_speakers():
    """List the built-in XTTS v2 speakers."""
    if tts_model is None:
        raise HTTPException(503, "Model not loaded yet")
    try:
        speakers = tts_model.speakers or []
    except Exception:
        speakers = ["Ana Florence"]
    return {"speakers": speakers}

@app.post("/tts")
def synthesize(req: TTSRequest):
    """
    Generate speech from text.
    Returns raw WAV bytes (audio/wav).

    If aria_voice_ref.wav exists in /tts/voices, uses voice cloning instead
    of the named speaker — the cloned voice sounds like the reference recording.
    """
    if tts_model is None:
        raise HTTPException(503, "TTS model not loaded yet — try again in a moment")

    if not req.text.strip():
        raise HTTPException(400, "text cannot be empty")

    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        if CUSTOM_VOICE.exists():
            # Voice cloning — sounds like the recorded reference
            tts_model.tts_to_file(
                text=req.text,
                speaker_wav=str(CUSTOM_VOICE),
                language=req.language,
                file_path=tmp_path,
            )
        else:
            # Use a named XTTS v2 speaker
            tts_model.tts_to_file(
                text=req.text,
                speaker=req.speaker,
                language=req.language,
                file_path=tmp_path,
            )

        with open(tmp_path, "rb") as f:
            wav_bytes = f.read()

        Path(tmp_path).unlink(missing_ok=True)

        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={"X-Speaker": req.speaker, "X-Language": req.language},
        )

    except Exception as e:
        logger.error(f"TTS synthesis failed: {e}")
        raise HTTPException(500, f"TTS failed: {e}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5002, log_level="info")
