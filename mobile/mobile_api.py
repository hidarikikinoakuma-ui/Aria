"""
ARIA — Mobile Companion API
=============================
FastAPI backend that powers Aria on your phone.
Chat with Aria anywhere. She sends you annotated clips.
She narrates over the clip while showing you exactly what went wrong.

Works on any phone — iPhone or Android — via PWA (no app store needed).
Access from home network or via Cloudflare Tunnel from anywhere.

Player: Hidarikikinoaku
"""

import os
import json
import time
import asyncio
from pathlib import Path
from datetime import datetime
from loguru import logger

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    logger.error("FastAPI not installed: pip install fastapi uvicorn")

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


# ── Mobile API ────────────────────────────────────────────────────────────────

class MobileCompanionAPI:
    """
    The backend that powers Aria on your phone.

    Features:
    - Chat with Aria about any match or clip
    - Aria sends annotated clips to your phone
    - She narrates over clips in real time via WebSocket
    - Session history and habit tracking accessible anywhere
    - Predator roadmap always available
    """

    def __init__(self, config: dict):
        self.config       = config
        self.api_key      = config.get("openai_api_key", "")
        self.data_dir     = Path("data")
        self.clips_dir    = self.data_dir / "clips"
        self.sessions_dir = self.data_dir / "sessions"
        self.static_dir   = Path("mobile/static")

        self.openai = None
        if OPENAI_AVAILABLE and self.api_key:
            self.openai = OpenAI(api_key=self.api_key)

        # Conversation history per session (in memory)
        self.conversations: dict[str, list] = {}

        # Aria's mobile system prompt
        self.ARIA_MOBILE_PROMPT = """You are Aria (@migikonokami, "RightHandGod"), 
the elite Apex Legends AI coach for Hidarikikinoaku ("LeftHandDevil").

The player is currently talking to you on their phone, away from their PC.
They might be on a break, commuting, or just thinking about their game.

MOBILE CONTEXT:
- Keep responses concise for mobile reading — shorter than desktop coaching
- You can reference specific clips they've saved — say "that fight at Fragment" 
  or "the clip from your last session"
- You remember ALL their bad habits from sessions
- You are direct but warm — like a coach they can text anytime
- When they ask about a specific fight, guide them to watch the clip
- You can send them clips and annotate them in real time

PLAYER PROFILE:
- Username: Hidarikikinoaku (LeftHandDevil)
- Current rank: {rank}
- Current RP: {rp}
- Target: Predator
- Controller: GameSir G7 Pro 8K
- Known issues: [loaded from session history]

Respond naturally. You know this player well."""

    def build_app(self) -> "FastAPI":
        """Build and configure the FastAPI application."""
        if not FASTAPI_AVAILABLE:
            raise ImportError("FastAPI not installed")

        app = FastAPI(
            title="Aria Mobile Companion",
            description="Your Apex AI coach — available anywhere",
            version="1.0.0"
        )

        # CORS — allow mobile browser access
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Serve the mobile web app
        if self.static_dir.exists():
            app.mount("/static", StaticFiles(directory=str(self.static_dir)),
                      name="static")

        # Register routes
        self._register_routes(app)
        return app

    def _register_routes(self, app):

        # ── Health check ──────────────────────────────────────────────────────
        @app.get("/")
        async def root():
            return FileResponse(str(self.static_dir / "index.html")) \
                if (self.static_dir / "index.html").exists() \
                else {"status": "Aria online", "player": "Hidarikikinoaku"}

        @app.get("/health")
        async def health():
            return {"status": "online", "aria": "ready",
                    "timestamp": datetime.now().isoformat()}

        # ── Player Profile ────────────────────────────────────────────────────
        @app.get("/api/profile")
        async def get_profile():
            return {
                "username":     "Hidarikikinoaku",
                "display_name": "LeftHandDevil",
                "coach":        "Aria (@migikonokami)",
                "current_rank": self.config.get("current_rank", "Gold IV"),
                "current_rp":   self.config.get("current_rp", 143),
                "rp_to_next":   self.config.get("rp_to_next", 750),
                "target_rank":  "Predator",
                "controller":   "GameSir G7 Pro 8K",
            }

        # ── Sessions ──────────────────────────────────────────────────────────
        @app.get("/api/sessions")
        async def get_sessions(limit: int = 10):
            """Get recent match sessions."""
            sessions = self._load_recent_sessions(limit)
            return {"sessions": sessions, "count": len(sessions)}

        @app.get("/api/sessions/{session_id}")
        async def get_session(session_id: str):
            """Get details of a specific session."""
            session = self._load_session(session_id)
            if not session:
                raise HTTPException(404, "Session not found")
            return session

        # ── Clips ─────────────────────────────────────────────────────────────
        @app.get("/api/clips")
        async def get_clips(session_id: str = None, clip_type: str = None,
                            limit: int = 20):
            """List available clips with metadata."""
            clips = self._list_clips(session_id, clip_type, limit)
            return {"clips": clips, "count": len(clips)}

        @app.get("/api/clips/{clip_id}/video")
        async def stream_clip(clip_id: str, quality: str = "medium"):
            """Stream a clip video to the mobile device."""
            clip_path = self._find_clip(clip_id)
            if not clip_path:
                raise HTTPException(404, "Clip not found")

            # Transcode for mobile if needed
            mobile_path = self._prepare_mobile_clip(clip_path, quality)

            def iter_file():
                with open(mobile_path, "rb") as f:
                    while chunk := f.read(1024 * 64):  # 64KB chunks
                        yield chunk

            return StreamingResponse(
                iter_file(),
                media_type="video/mp4",
                headers={
                    "Content-Disposition": f"inline; filename={clip_id}.mp4",
                    "Accept-Ranges": "bytes",
                }
            )

        @app.get("/api/clips/{clip_id}/analysis")
        async def get_clip_analysis(clip_id: str):
            """Get Aria's analysis of a specific clip."""
            clip_path = self._find_clip(clip_id)
            if not clip_path:
                raise HTTPException(404, "Clip not found")

            analysis = self._load_clip_analysis(clip_path)
            if not analysis:
                raise HTTPException(404, "Analysis not yet available for this clip")
            return analysis

        @app.get("/api/clips/{clip_id}/annotated")
        async def get_annotated_clip(clip_id: str):
            """Get the annotated version of a clip (with arrows, circles, etc.)."""
            clip_path = self._find_clip(clip_id)
            if not clip_path:
                raise HTTPException(404, "Clip not found")

            # Look for annotated version
            stem = Path(clip_path).stem
            for suffix in ["_mistake_annotated.mp4", "_highlight_annotated.mp4"]:
                ann_path = Path(clip_path).parent / f"{stem}{suffix}"
                if ann_path.exists():
                    def iter_file():
                        with open(str(ann_path), "rb") as f:
                            while chunk := f.read(1024 * 64):
                                yield chunk
                    return StreamingResponse(iter_file(), media_type="video/mp4")

            # Fall back to original
            raise HTTPException(404, "Annotated clip not found — run analysis first")

        # ── Predator Roadmap ──────────────────────────────────────────────────
        @app.get("/api/roadmap")
        async def get_roadmap():
            """Get Aria's current Predator roadmap for the player."""
            habits = self._load_habit_tracker()
            sessions = self._load_recent_sessions(20)

            total_rp_needed = self._estimate_rp_to_predator()
            weekly_rp = self._calculate_weekly_rp_rate(sessions)
            eta_weeks  = round(total_rp_needed / max(weekly_rp, 1), 1) \
                         if weekly_rp > 0 else None

            top_blockers = habits.get("top_blockers", [
                "Stationary while ADS",
                "Doorway discipline",
                "Third-party awareness",
            ])

            return {
                "current_rank": self.config.get("current_rank", "Gold IV"),
                "current_rp":   self.config.get("current_rp", 143),
                "rp_to_predator": total_rp_needed,
                "weekly_rp_rate": weekly_rp,
                "eta_weeks": eta_weeks,
                "top_blockers": top_blockers,
                "this_week_focus": habits.get("current_focus",
                                              "Left stick active while aiming"),
                "improvement_trends": habits.get("trends", {}),
            }

        # ── Chat with Aria ────────────────────────────────────────────────────
        @app.post("/api/chat")
        async def chat(message: dict):
            """
            Send a message to Aria and get her response.
            She remembers the conversation history.
            """
            user_message = message.get("message", "").strip()
            session_key  = message.get("session_key", "default")

            if not user_message:
                raise HTTPException(400, "Message cannot be empty")

            response_text, clip_refs = await self._chat_with_aria(
                user_message, session_key
            )

            return {
                "response":  response_text,
                "clip_refs": clip_refs,   # clips Aria wants to show
                "timestamp": datetime.now().isoformat(),
            }

        # ── WebSocket for real-time clip narration ────────────────────────────
        @app.websocket("/ws/narrate/{clip_id}")
        async def narrate_clip(websocket: WebSocket, clip_id: str):
            """
            WebSocket for real-time clip narration.
            While the clip plays on your phone, Aria sends commentary
            in real time — telling you what to watch for at each moment.
            """
            await websocket.accept()
            logger.info(f"Narration session started: clip {clip_id}")

            clip_path = self._find_clip(clip_id)
            if not clip_path:
                await websocket.send_json({"error": "Clip not found"})
                await websocket.close()
                return

            analysis = self._load_clip_analysis(clip_path)
            if not analysis:
                await websocket.send_json({
                    "type": "narration",
                    "time": 0,
                    "text": "Playing your clip. No analysis available yet.",
                })
                await websocket.close()
                return

            try:
                # Send narration events timed to clip moments
                await self._send_timed_narration(websocket, analysis, clip_path)
            except WebSocketDisconnect:
                logger.info(f"Narration session ended: clip {clip_id}")
            except Exception as e:
                logger.error(f"Narration error: {e}")
                await websocket.close()

    async def _chat_with_aria(
        self, message: str, session_key: str
    ) -> tuple[str, list]:
        """
        Process a chat message and get Aria's response.
        Searches clip library for relevant clips to reference.
        """
        if not self.openai:
            return (
                "Chat requires an OpenAI API key. "
                "Add it to config/aria.conf under [analysis] openai_api_key.",
                []
            )

        # Initialize conversation history
        if session_key not in self.conversations:
            self.conversations[session_key] = []

        # Build context-aware system prompt
        rank = self.config.get("current_rank", "Gold IV")
        rp   = self.config.get("current_rp", 143)
        habits = self._load_habit_tracker()
        recent_issues = habits.get("top_blockers", [])

        system = self.ARIA_MOBILE_PROMPT.format(rank=rank, rp=rp)
        if recent_issues:
            system += f"\n\nCurrent known bad habits: {', '.join(recent_issues)}"

        # Add user message to history
        self.conversations[session_key].append({
            "role": "user", "content": message
        })

        # Keep last 10 messages for context
        history = self.conversations[session_key][-10:]

        # Check if user is asking about a specific clip
        clip_refs = self._find_relevant_clips(message)

        # Add clip context if found
        if clip_refs:
            clip_context = f"\n\nRelevant clips found: {len(clip_refs)}. "
            clip_context += "You can reference these specific moments."
            history[-1]["content"] += clip_context

        try:
            response = self.openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system},
                    *history
                ],
                max_tokens=300,
                temperature=0.5,
            )
            reply = response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Chat API call failed: {e}")
            reply = "I'm having trouble connecting right now. Check your API key."
            clip_refs = []

        # Add response to history
        self.conversations[session_key].append({
            "role": "assistant", "content": reply
        })

        return reply, clip_refs

    async def _send_timed_narration(
        self, websocket, analysis: dict, clip_path: str
    ):
        """
        Send timed narration events that sync with the clip playback.
        The phone plays the clip — Aria's text arrives at the right moments.
        """
        duration = self._get_clip_duration(clip_path)
        key_time = float(analysis.get("key_moment_time", duration * 0.5))

        # Narration timeline
        events = [
            {
                "time": 0.0,
                "type": "narration",
                "text": analysis.get("what_happened", "Watch this clip carefully."),
                "annotation": None,
            },
            {
                "time": max(0, key_time - 1.0),
                "type": "alert",
                "text": "⚠️ Key moment coming up...",
                "annotation": None,
            },
            {
                "time": key_time,
                "type": "narration",
                "text": analysis.get("key_moment", "This is where it happened."),
                "annotation": {
                    "type": "highlight",
                    "message": analysis.get("decision_making", "")
                },
            },
            {
                "time": key_time + 1.5,
                "type": "coaching",
                "text": analysis.get("primary_fix", ""),
                "annotation": None,
            },
            {
                "time": duration - 2.0,
                "type": "summary",
                "text": (f"Verdict: {analysis.get('overall_verdict', '')}  |  "
                         f"Quality: {analysis.get('fight_quality', 5)}/10"),
                "annotation": None,
            },
        ]

        # Send start signal
        await websocket.send_json({"type": "ready", "duration": duration})

        # Stream narration events with timing
        start_time = time.time()
        event_idx = 0

        while event_idx < len(events):
            elapsed = time.time() - start_time
            event = events[event_idx]

            if elapsed >= event["time"]:
                await websocket.send_json({
                    "type":       event["type"],
                    "time":       event["time"],
                    "text":       event["text"],
                    "annotation": event["annotation"],
                })
                event_idx += 1
            else:
                await asyncio.sleep(0.1)

        await websocket.send_json({"type": "done"})

    # ── Data Helpers ──────────────────────────────────────────────────────────

    def _load_recent_sessions(self, limit: int) -> list[dict]:
        sessions = []
        if not self.sessions_dir.exists():
            return sessions
        for f in sorted(self.clips_dir.glob("*/session_summary.json"),
                        reverse=True)[:limit]:
            try:
                with open(f) as fp:
                    sessions.append(json.load(fp))
            except Exception:
                pass
        return sessions

    def _load_session(self, session_id: str) -> dict | None:
        path = self.clips_dir / session_id / "session_summary.json"
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return None

    def _list_clips(self, session_id: str, clip_type: str,
                    limit: int) -> list[dict]:
        clips = []
        search_dir = (self.clips_dir / session_id
                      if session_id else self.clips_dir)
        if not search_dir.exists():
            return clips

        for meta_file in sorted(search_dir.rglob("*.json"),
                                reverse=True)[:limit * 2]:
            if "session_summary" in meta_file.name:
                continue
            if "analysis" in meta_file.name:
                continue
            try:
                with open(meta_file) as f:
                    meta = json.load(f)
                if clip_type and meta.get("event_type") != clip_type:
                    continue
                clip_file = meta_file.parent / meta.get("clip_file", "")
                if clip_file.exists():
                    meta["clip_id"] = meta_file.stem
                    meta["clip_url"] = f"/api/clips/{meta_file.stem}/video"
                    meta["annotated_url"] = \
                        f"/api/clips/{meta_file.stem}/annotated"
                    clips.append(meta)
                if len(clips) >= limit:
                    break
            except Exception:
                pass
        return clips

    def _find_clip(self, clip_id: str) -> str | None:
        """Find a clip file by its ID (stem of the metadata file)."""
        for meta_file in self.clips_dir.rglob(f"{clip_id}.json"):
            try:
                with open(meta_file) as f:
                    meta = json.load(f)
                clip_file = meta_file.parent / meta.get("clip_file", "")
                if clip_file.exists():
                    return str(clip_file)
            except Exception:
                pass
        return None

    def _load_clip_analysis(self, clip_path: str) -> dict | None:
        stem = Path(clip_path).stem
        for suffix in ["_analysis.json"]:
            p = Path(clip_path).parent / f"{stem}{suffix}"
            if p.exists():
                with open(p) as f:
                    return json.load(f)
        return None

    def _prepare_mobile_clip(self, clip_path: str, quality: str) -> str:
        """Transcode clip for mobile if needed (smaller file size)."""
        quality_map = {"low": "400k", "medium": "800k", "high": "1500k"}
        bitrate = quality_map.get(quality, "800k")

        stem = Path(clip_path).stem
        mobile_path = Path("data/mobile_cache") / f"{stem}_{quality}.mp4"
        mobile_path.parent.mkdir(parents=True, exist_ok=True)

        if mobile_path.exists():
            return str(mobile_path)

        cmd = (
            f'ffmpeg -y -i "{clip_path}" '
            f'-vcodec libx264 -b:v {bitrate} '
            f'-acodec aac -b:a 128k '
            f'-vf scale=1280:-2 '
            f'"{mobile_path}" -loglevel error'
        )
        os.system(cmd)

        return str(mobile_path) if mobile_path.exists() else clip_path

    def _find_relevant_clips(self, message: str) -> list[dict]:
        """Find clips relevant to what the user is asking about."""
        keywords = message.lower().split()
        location_words = ["fragment", "storm", "olympus", "worlds", "edge",
                          "building", "hill", "zone", "ring"]
        event_words = ["knock", "die", "died", "death", "down", "kill"]

        relevant = []
        for word in keywords:
            if word in location_words or word in event_words:
                clips = self._list_clips(None, None, 5)
                relevant.extend(clips[:2])
                break

        return relevant[:3]

    def _load_habit_tracker(self) -> dict:
        habit_file = Path("data/habit_tracker.json")
        if habit_file.exists():
            with open(habit_file) as f:
                return json.load(f)
        return {
            "top_blockers": [
                "Stationary while ADS — left stick goes dead in fights",
                "Doorway discipline — not clearing corners before pushing",
                "Third-party awareness — getting caught rotating",
            ],
            "current_focus": "Left stick active — move while you aim",
            "trends": {},
        }

    def _estimate_rp_to_predator(self) -> int:
        """Rough estimate of RP needed to reach Predator from current rank."""
        rank_rp = {
            "Bronze IV": 3600, "Bronze III": 3300, "Bronze II": 3000,
            "Bronze I": 2700, "Silver IV": 2400, "Silver III": 2100,
            "Silver II": 1800, "Silver I": 1500, "Gold IV": 1200,
            "Gold III": 900, "Gold II": 600, "Gold I": 300,
            "Platinum IV": 0,
        }
        current_rank = self.config.get("current_rank", "Gold IV")
        current_rp   = int(self.config.get("current_rp", 143))
        predator_rp  = 15000  # approx total RP to Predator from zero

        base = rank_rp.get(current_rank, 1200)
        already_have = predator_rp - base - current_rp
        return max(0, already_have)

    def _calculate_weekly_rp_rate(self, sessions: list) -> int:
        """Estimate weekly RP gain from recent sessions."""
        # Rough estimate: each knock = ~12 RP, each win assist = ~30 RP
        total_knocks = sum(s.get("knock_count", 0) for s in sessions[-20:])
        sessions_count = max(len(sessions[-20:]), 1)
        rp_per_session = (total_knocks * 12) / sessions_count
        sessions_per_week = 10  # assumed
        return int(rp_per_session * sessions_per_week)

    def _get_clip_duration(self, clip_path: str) -> float:
        if not CV2_AVAILABLE:
            return 30.0
        cap = cv2.VideoCapture(clip_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        cap.release()
        return frames / fps


def run_mobile_server(config: dict, host: str = "0.0.0.0", port: int = 8765):
    """Start the mobile companion API server."""
    if not FASTAPI_AVAILABLE:
        logger.error("FastAPI not installed: pip install fastapi uvicorn")
        return

    api = MobileCompanionAPI(config)
    app = api.build_app()

    logger.info(f"Starting Aria Mobile Companion on {host}:{port}")
    logger.info(f"Access on your phone: http://[your-PC-IP]:{port}")
    logger.info("Find your PC IP: ipconfig (Windows) or ip addr (Linux)")

    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    config = {
        "openai_api_key": "",   # add your key
        "current_rank":   "Gold IV",
        "current_rp":     "143",
        "rp_to_next":     "750",
        "apex_username":  "Hidarikikinoaku",
    }
    run_mobile_server(config)
