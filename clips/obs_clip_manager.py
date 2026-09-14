"""
ARIA — OBS Replay Buffer Controller
=====================================
Connects to OBS via WebSocket.
Saves clips when kill feed events are detected.
Zero performance impact during match — only triggers on events.

Player: Hidarikikinoaku
"""

import asyncio
import os
import json
import time
import shutil
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from loguru import logger

try:
    import obsws_python as obs
    OBS_AVAILABLE = True
except ImportError:
    OBS_AVAILABLE = False
    logger.warning("obsws_python not installed — OBS integration disabled")


class EventType(Enum):
    KNOCK_BY_YOU     = "knock_by_you"       # you knocked someone
    KILL_BY_YOU      = "kill_by_you"        # you finished/killed someone
    KNOCKED_BY_ENEMY = "knocked_by_enemy"   # you got knocked
    KILLED_BY_ENEMY  = "killed_by_enemy"    # you died
    REVIVED          = "revived"            # you were revived
    CHAMPION         = "champion"           # squad won
    RING_CLOSE       = "ring_close"         # ring is closing (context)


@dataclass
class GameEvent:
    event_type: EventType
    timestamp: float
    player: str         # who did it
    target: str         # who it happened to
    weapon: str = ""
    damage: int = 0
    clip_path: str = ""
    session_id: str = ""


class OBSClipManager:
    """
    Manages OBS replay buffer and auto-clips on game events.
    
    How it works:
    1. OBS runs with replay buffer enabled (90 seconds in RAM)
    2. When kill feed detector fires an event, we call save_replay()
    3. OBS saves the last N seconds as a video file
    4. We rename and organize it into the clips folder
    5. Clip is tagged with event type for analysis routing
    """

    def __init__(self, config: dict):
        self.host     = config.get("obs_host", "localhost")
        self.port     = int(config.get("obs_port", 4455))
        self.password = config.get("obs_password", "")
        self.clips_folder = Path(config.get("clips_folder", "data/clips"))
        self.clip_before  = int(config.get("clip_before_event", 20))
        self.clip_after   = int(config.get("clip_after_event", 8))
        self.session_id   = datetime.now().strftime("%Y%m%d_%H%M%S")

        self.client       = None
        self.connected    = False
        self.pending_events: list[GameEvent] = []

        # Create session folder
        self.session_folder = self.clips_folder / self.session_id
        self.session_folder.mkdir(parents=True, exist_ok=True)
        logger.info(f"OBS Clip Manager initialized | Session: {self.session_id}")

    def connect(self) -> bool:
        """Connect to OBS WebSocket server."""
        if not OBS_AVAILABLE:
            logger.error("obsws_python not installed. Run: pip install obsws-python")
            return False

        try:
            self.client = obs.ReqClient(
                host=self.host,
                port=self.port,
                password=self.password,
                timeout=3
            )
            self.connected = True
            logger.info(f"Connected to OBS at {self.host}:{self.port}")

            # Verify replay buffer is available
            self._check_replay_buffer()
            return True

        except Exception as e:
            self.connected = False
            logger.error(f"Failed to connect to OBS: {e}")
            logger.info("Make sure OBS is open and WebSocket server is enabled:")
            logger.info("  OBS → Tools → WebSocket Server Settings → Enable")
            return False

    def disconnect(self):
        if self.client and self.connected:
            self.client.disconnect()
            self.connected = False
            logger.info("Disconnected from OBS")

    def _check_replay_buffer(self):
        """Verify replay buffer is running, start it if not."""
        try:
            status = self.client.get_replay_buffer_status()
            if not status.output_active:
                logger.info("Replay buffer not active — starting it...")
                self.client.start_replay_buffer()
                time.sleep(1)
                logger.info("Replay buffer started")
            else:
                logger.info("Replay buffer already active ✅")
        except Exception as e:
            logger.warning(f"Could not check replay buffer status: {e}")

    def save_clip(self, event: GameEvent) -> str | None:
        """
        Trigger OBS to save the replay buffer as a clip.
        Returns the path to the saved clip, or None on failure.
        """
        if not self.connected:
            logger.warning("OBS not connected — cannot save clip")
            return None

        try:
            # Wait for clip_after seconds so we capture the aftermath
            logger.info(f"Event detected: {event.event_type.value} — "
                        f"waiting {self.clip_after}s for aftermath...")
            time.sleep(self.clip_after)

            # Save the replay buffer
            self.client.save_replay_buffer()
            logger.info("Replay buffer save triggered")

            # Give OBS a moment to write the file
            time.sleep(2)

            # Find the most recently saved file in OBS output folder
            clip_path = self._find_latest_obs_file()
            if not clip_path:
                logger.error("Could not find saved clip from OBS")
                return None

            # Move and rename it to our organized folder
            organized_path = self._organize_clip(clip_path, event)
            event.clip_path = str(organized_path)
            self.pending_events.append(event)

            logger.info(f"Clip saved: {organized_path.name}")
            return str(organized_path)

        except Exception as e:
            logger.error(f"Failed to save clip: {e}")
            return None

    def _find_latest_obs_file(self) -> Path | None:
        """Find the most recently created file in OBS output directory."""
        # Common OBS output locations on Windows
        obs_output_dirs = [
            Path.home() / "Videos",
            Path.home() / "Videos" / "Apex Legends",
            Path("C:/Users") / os.getenv("USERNAME", "") / "Videos",
        ]

        latest_file = None
        latest_time = 0

        for folder in obs_output_dirs:
            if not folder.exists():
                continue
            for f in folder.glob("*.mp4"):
                if f.stat().st_mtime > latest_time:
                    latest_time = f.stat().st_mtime
                    latest_file = f
            for f in folder.glob("*.mkv"):
                if f.stat().st_mtime > latest_time:
                    latest_time = f.stat().st_mtime
                    latest_file = f

        # Only accept files created in the last 30 seconds
        if latest_file and (time.time() - latest_time) < 30:
            return latest_file

        return None

    def _organize_clip(self, raw_path: Path, event: GameEvent) -> Path:
        """
        Move clip to organized folder with descriptive name.
        
        Naming: {session_id}_{event_type}_{timestamp}.mp4
        Example: 20240818_143022_knock_by_you_001.mp4
        """
        ext       = raw_path.suffix
        timestamp = datetime.now().strftime("%H%M%S")
        count     = len(list(self.session_folder.glob("*.mp4"))) + 1
        filename  = f"{event.event_type.value}_{timestamp}_{count:03d}{ext}"
        dest      = self.session_folder / filename

        shutil.move(str(raw_path), str(dest))

        # Save event metadata alongside clip
        meta_path = dest.with_suffix(".json")
        meta = {
            "event_type":  event.event_type.value,
            "timestamp":   event.timestamp,
            "player":      event.player,
            "target":      event.target,
            "weapon":      event.weapon,
            "damage":      event.damage,
            "session_id":  self.session_id,
            "clip_file":   filename,
            "clip_before_seconds": self.clip_before,
            "clip_after_seconds":  self.clip_after,
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        return dest

    def get_session_clips(self) -> list[dict]:
        """Return all clips from this session with their metadata."""
        clips = []
        for meta_file in self.session_folder.glob("*.json"):
            try:
                with open(meta_file) as f:
                    meta = json.load(f)
                clip_file = self.session_folder / meta["clip_file"]
                if clip_file.exists():
                    meta["clip_path"] = str(clip_file)
                    clips.append(meta)
            except Exception as e:
                logger.warning(f"Could not read clip metadata {meta_file}: {e}")

        # Sort by timestamp
        clips.sort(key=lambda x: x.get("timestamp", 0))
        return clips

    def bucket_clips(self) -> tuple[list[dict], list[dict]]:
        """
        Split session clips into:
        - highlights (your knocks/kills) → YouTube pipeline
        - mistakes (your downs/deaths) → coaching pipeline
        """
        clips      = self.get_session_clips()
        highlights = []
        mistakes   = []

        for clip in clips:
            et = clip.get("event_type", "")
            if et in (EventType.KNOCK_BY_YOU.value, EventType.KILL_BY_YOU.value):
                highlights.append(clip)
            elif et in (EventType.KNOCKED_BY_ENEMY.value, EventType.KILLED_BY_ENEMY.value):
                mistakes.append(clip)

        logger.info(f"Session clips bucketed: "
                    f"{len(highlights)} highlights, {len(mistakes)} mistakes")
        return highlights, mistakes

    def end_session(self) -> dict:
        """
        Called when match ends.
        Returns session summary for Aria to coach from.
        """
        highlights, mistakes = self.bucket_clips()
        summary = {
            "session_id":      self.session_id,
            "session_folder":  str(self.session_folder),
            "total_clips":     len(highlights) + len(mistakes),
            "highlights":      highlights,
            "mistakes":        mistakes,
            "knock_count":     len([h for h in highlights
                                    if h["event_type"] == EventType.KNOCK_BY_YOU.value]),
            "kill_count":      len([h for h in highlights
                                    if h["event_type"] == EventType.KILL_BY_YOU.value]),
            "down_count":      len([m for m in mistakes
                                    if m["event_type"] == EventType.KNOCKED_BY_ENEMY.value]),
            "death_count":     len([m for m in mistakes
                                    if m["event_type"] == EventType.KILLED_BY_ENEMY.value]),
        }

        # Save session summary
        summary_path = self.session_folder / "session_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)

        logger.info(f"Session ended | "
                    f"Knocks: {summary['knock_count']} | "
                    f"Deaths: {summary['death_count']} | "
                    f"Clips: {summary['total_clips']}")
        return summary


# ── Quick test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from core.system_detector import load_profile

    config = {
        "obs_host": "localhost",
        "obs_port": "4455",
        "obs_password": "",
        "clips_folder": "data/clips",
        "clip_before_event": "20",
        "clip_after_event":  "8",
    }

    manager = OBSClipManager(config)

    if manager.connect():
        print("✅ OBS connected — replay buffer active")
        print("   Aria is ready to save clips")
    else:
        print("❌ OBS not connected")
        print("   Make sure OBS is open with WebSocket server enabled")
        print("   OBS → Tools → WebSocket Server Settings → Enable WebSocket Server")
