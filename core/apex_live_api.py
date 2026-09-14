"""
ARIA — Apex Legends Live API Listener
=======================================
Replaces OCR kill feed with Apex's native WebSocket event API.

Zero screen capture. Zero OCR errors. Zero performance impact.
Apex pushes exact player names and damage numbers directly.

Player: Hidarikikinoaku (LeftHandDevil)
Coach:  Aria (@migikonokami / RightHandGod)
"""

import asyncio
import json
import time
import threading
from datetime import datetime
from pathlib import Path
from loguru import logger

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

from clips.obs_clip_manager import EventType, GameEvent

CAT_PLAYER_KILLED      = "playerKilled"
CAT_PLAYER_DOWN        = "playerDown"
CAT_PLAYER_DAMAGED     = "playerDamaged"
CAT_MATCH_START        = "matchStart"
CAT_MATCH_STATE_END    = "matchStateEnd"
CAT_GAME_STATE_CHANGED = "gameStateChanged"
CAT_INIT               = "init"


class ApexLiveAPI:
    """
    WebSocket listener for Apex Legends Live API.
    Drop-in replacement for KillFeedDetector — same public interface.
    """

    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 7777

    def __init__(self, config: dict, event_callback=None):
        self.username       = config.get("apex_username", "Hidarikikinoaku").lower()
        self.event_callback = event_callback
        self.host           = config.get("liveapi_host", self.DEFAULT_HOST)
        self.port           = int(config.get("liveapi_port", self.DEFAULT_PORT))

        self._running  = False
        self._thread   = None
        self._loop     = None

        self._dedupe_window              = 3.0
        self._last_events: dict[str, float] = {}

        self.session_events: list[GameEvent] = []
        self.session_start   = time.time()
        self._in_match       = False
        self._match_ended    = False

        self._damage_buffer: dict[str, dict] = {}
        self._damage_window_secs = 8.0

        logger.info(f"Apex Live API | ws://{self.host}:{self.port} | watching: {self.username}")

    # ── Public interface ───────────────────────────────────────

    def start(self) -> bool:
        if not WEBSOCKETS_AVAILABLE:
            logger.error("websockets not installed — run: pip install websockets==12.0")
            return False
        self._running = True
        self._thread  = threading.Thread(target=self._run_loop, daemon=True, name="AriaLiveAPI")
        self._thread.start()
        logger.info("Live API listener started — will auto-connect when Apex launches")
        return True

    def stop(self):
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)

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
            "total_events":         len(self.session_events),
            "knocks":               len(knocks),
            "kills":                len(kills),
            "downs":                len(downs),
            "deaths":               len(deaths),
            "kd_ratio":             round(len(kills) / max(len(deaths), 1), 2),
            "session_duration_min": round((time.time() - self.session_start) / 60, 1),
        }

    # ── Async loop ─────────────────────────────────────────────

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
                async with websockets.connect(uri, ping_interval=20, ping_timeout=10, max_size=2**20) as ws:
                    logger.info("Apex Live API connected ✅")
                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            await self._dispatch(raw)
                        except Exception as e:
                            logger.debug(f"Event error: {e}")
            except (ConnectionRefusedError, OSError):
                logger.debug("Apex not running — retrying in 5s")
            except websockets.exceptions.ConnectionClosed:
                logger.info("Live API disconnected — reconnecting...")
            except Exception as e:
                logger.warning(f"Live API: {e}")
            if self._running:
                await asyncio.sleep(5)

    # ── Dispatch ───────────────────────────────────────────────

    async def _dispatch(self, raw: str):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        category = msg.get("category", "")
        event    = msg.get("event", msg)
        if not category:
            return
        if   category == CAT_INIT:               self._on_init(event)
        elif category == CAT_MATCH_START:        self._on_match_start(event)
        elif category == CAT_MATCH_STATE_END:    self._on_match_end(event)
        elif category == CAT_GAME_STATE_CHANGED: self._on_state_changed(event)
        elif category == CAT_PLAYER_DOWN:        self._on_player_down(event)
        elif category == CAT_PLAYER_KILLED:      self._on_player_killed(event)
        elif category == CAT_PLAYER_DAMAGED:     self._on_player_damaged(event)

    # ── Handlers ───────────────────────────────────────────────

    def _on_init(self, e: dict):
        logger.info(f"Apex Live API version: {e.get('apiVersion','?')}")

    def _on_match_start(self, e: dict):
        self._in_match    = True
        self._match_ended = False
        self.session_events.clear()
        self._damage_buffer.clear()
        self.session_start = time.time()
        logger.info("Match started — session reset ✅")

    def _on_match_end(self, e: dict):
        if not self._in_match:
            return
        self._in_match    = False
        self._match_ended = True
        logger.info("Match ended — Aria coaching pipeline triggered")

    def _on_state_changed(self, e: dict):
        if e.get("state", "").lower() in ("pregame", "lobby", "resolution") and self._in_match:
            self._on_match_end(e)

    def _on_player_down(self, e: dict):
        attacker, victim, now = self._name(e,"attacker"), self._name(e,"victim"), time.time()
        if   attacker == self.username: self._fire(EventType.KNOCK_BY_YOU,     victim,   now)
        elif victim   == self.username: self._fire(EventType.KNOCKED_BY_ENEMY, attacker, now)

    def _on_player_killed(self, e: dict):
        attacker, victim, now = self._name(e,"attacker"), self._name(e,"victim"), time.time()
        if   attacker == self.username: self._fire(EventType.KILL_BY_YOU,      victim,   now)
        elif victim   == self.username: self._fire(EventType.KILLED_BY_ENEMY,  attacker, now)

    def _on_player_damaged(self, e: dict):
        attacker = self._name(e, "attacker")
        victim   = self._name(e, "victim")
        amount   = int(e.get("damageInflicted", 0))
        if not amount:
            return
        key = str(int(time.time() / self._damage_window_secs))
        if key not in self._damage_buffer:
            self._damage_buffer[key] = {"damage_dealt": 0, "damage_taken": 0}
        if   attacker == self.username: self._damage_buffer[key]["damage_dealt"] += amount
        elif victim   == self.username: self._damage_buffer[key]["damage_taken"] += amount
        bucket = int(time.time() / self._damage_window_secs)
        for k in list(self._damage_buffer):
            if int(k) < bucket - 3:
                del self._damage_buffer[k]

    # ── Fire event ─────────────────────────────────────────────

    def _fire(self, event_type: EventType, target: str, now: float):
        key = f"{event_type.value}_{target}"
        if self._last_events.get(key, 0) and now - self._last_events[key] < self._dedupe_window:
            return
        self._last_events[key] = now

        bucket = int(now / self._damage_window_secs)
        dealt  = sum(self._damage_buffer.get(str(bucket + o), {}).get("damage_dealt", 0) for o in (0, -1))
        taken  = sum(self._damage_buffer.get(str(bucket + o), {}).get("damage_taken", 0) for o in (0, -1))

        ge                      = GameEvent(
            event_type = event_type,
            timestamp  = now,
            player     = self.username,
            target     = target or "unknown",
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S"),
        )
        ge.live_api_context = {"damage_dealt": dealt, "damage_taken": taken, "attacker_name": target}

        arrow = "→" if "by_you" in event_type.value else "←"
        logger.info(f"{arrow} {event_type.value}: {target} | {dealt} dealt / {taken} taken")

        self.session_events.append(ge)
        if self.event_callback:
            threading.Thread(target=self.event_callback, args=(ge,), daemon=True).start()

    # ── Helper ─────────────────────────────────────────────────

    def _name(self, event: dict, role: str) -> str:
        obj = event.get(role, {})
        if not isinstance(obj, dict):
            return ""
        return (obj.get("name") or obj.get("playerName") or "").lower().strip()


if __name__ == "__main__":
    import sys
    if "--gen-config" in sys.argv:
        config = {
            "cl_liveapi_enabled": True,
            "cl_liveapi_use_websocket": True,
            "cl_liveapi_websocket_keepalive_enabled": True,
            "cl_liveapi_websocket_keepalive_interval": 30,
            "cl_liveapi_ws_datacenter_only": True,
            "cl_liveapi_ws_retry_count": 5,
            "cl_liveapi_ws_retry_time": 10,
            "cl_liveapi_requests": [{"url": "ws://127.0.0.1:7777", "useMessagePack": False}],
        }
        path = r"C:\Program Files (x86)\Steam\steamapps\common\Apex Legends\LiveAPI\liveapi.json"
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(config, indent=2))
        print(f"Written: {path}")
        print("Steam launch options: +cl_liveapi_enabled 1 +cl_liveapi_use_websocket 1")
        sys.exit(0)

    def cb(e: GameEvent):
        ctx = getattr(e, "live_api_context", {})
        print(f"EVENT {e.event_type.value} | {e.target} | dealt={ctx.get('damage_dealt')} taken={ctx.get('damage_taken')}")

    api = ApexLiveAPI({"apex_username": "Hidarikikinoaku"}, event_callback=cb)
    api.start()
    print("Listening for Apex events. Launch Apex. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        api.stop()
