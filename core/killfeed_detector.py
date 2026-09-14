"""
ARIA — Kill Feed OCR Detector
==============================
Watches the Apex kill feed in real time.
Detects knocks, kills, downs, deaths involving Hidarikikinoaku.
Fires events to the clip saver when detected.

Zero performance impact — reads screen pixels only,
no memory access, no TOS violations.

Player: Hidarikikinoaku
"""

import time
import threading
import re
import numpy as np
from pathlib import Path
from datetime import datetime
from loguru import logger

try:
    import mss
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

from clips.obs_clip_manager import EventType, GameEvent


# ── Kill Feed Region (auto-calibrated or manual) ─────────────────────────────
# Apex kill feed is top-right corner of screen
# These are percentages of screen dimensions (resolution-independent)
KILLFEED_REGION = {
    "left_pct":   0.72,   # 72% from left edge
    "top_pct":    0.03,   # 3% from top
    "width_pct":  0.27,   # 27% of screen width
    "height_pct": 0.30,   # 30% of screen height
}

# Damage number region (right side, mid-screen)
DAMAGE_REGION = {
    "left_pct":   0.55,
    "top_pct":    0.30,
    "width_pct":  0.40,
    "height_pct": 0.40,
}


class KillFeedDetector:
    """
    Watches the Apex Legends kill feed and fires events when
    Hidarikikinoaku gets a knock, kill, gets knocked, or dies.
    
    Also reads damage numbers from screen.
    Fires events to OBSClipManager to trigger clip saves.
    """

    # Patterns that indicate events in kill feed
    KILL_VERBS      = ["knocked down", "killed", "eliminated", "finished"]
    KNOCK_ICON      = "💀"   # skull icon in feed
    SHIELD_BREAK    = "🛡"

    def __init__(self, config: dict, event_callback=None):
        self.username         = config.get("apex_username", "Hidarikikinoaku")
        self.poll_interval    = float(config.get("poll_interval", 0.5))
        self.ocr_confidence   = float(config.get("ocr_confidence", 0.65))
        self.event_callback   = event_callback  # called when event detected

        self._running         = False
        self._thread          = None
        self._reader          = None
        self._screen          = None
        self._screen_w        = 1920
        self._screen_h        = 1080

        # Deduplication — don't fire same event twice within 3 seconds
        self._last_events: dict[str, float] = {}
        self._dedupe_window = 3.0

        # Session tracking
        self.session_events: list[GameEvent] = []
        self.session_start    = time.time()

        logger.info(f"Kill Feed Detector initialized | Watching for: {self.username}")

    def start(self) -> bool:
        """Start the kill feed detection loop."""
        if not MSS_AVAILABLE:
            logger.error("mss not installed: pip install mss")
            return False
        if not CV2_AVAILABLE:
            logger.error("opencv not installed: pip install opencv-python")
            return False

        # Initialize OCR
        if EASYOCR_AVAILABLE:
            logger.info("Loading EasyOCR model (first run takes ~30 seconds)...")
            self._reader = easyocr.Reader(["en"], gpu=self._has_gpu(), verbose=False)
            logger.info("OCR ready ✅")
        else:
            logger.warning("EasyOCR not installed — using basic template matching only")

        # Get screen dimensions
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            self._screen_w = monitor["width"]
            self._screen_h = monitor["height"]
            logger.info(f"Screen: {self._screen_w}x{self._screen_h}")

        self._running = True
        self._thread = threading.Thread(
            target=self._detection_loop,
            daemon=True,
            name="AriaKillFeedDetector"
        )
        self._thread.start()
        logger.info("Kill feed detection started ✅")
        return True

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("Kill feed detection stopped")

    def _has_gpu(self) -> bool:
        """Check if GPU is available for OCR acceleration."""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def _get_killfeed_region(self) -> dict:
        """Calculate kill feed pixel region based on screen size."""
        return {
            "left":   int(self._screen_w * KILLFEED_REGION["left_pct"]),
            "top":    int(self._screen_h * KILLFEED_REGION["top_pct"]),
            "width":  int(self._screen_w * KILLFEED_REGION["width_pct"]),
            "height": int(self._screen_h * KILLFEED_REGION["height_pct"]),
        }

    def _capture_region(self, region: dict) -> np.ndarray | None:
        """Capture a screen region and return as numpy array."""
        try:
            with mss.mss() as sct:
                monitor = {
                    "left":   region["left"],
                    "top":    region["top"],
                    "width":  region["width"],
                    "height": region["height"],
                }
                screenshot = sct.grab(monitor)
                img = np.array(screenshot)
                return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        except Exception as e:
            logger.debug(f"Screen capture error: {e}")
            return None

    def _preprocess_for_ocr(self, img: np.ndarray) -> np.ndarray:
        """
        Enhance kill feed text for better OCR accuracy.
        Kill feed text in Apex is white on dark background.
        """
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Upscale for better OCR on small text
        scale = 2
        h, w = gray.shape
        gray = cv2.resize(gray, (w * scale, h * scale),
                          interpolation=cv2.INTER_CUBIC)

        # Threshold — keep white text
        _, thresh = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)

        # Slight denoise
        denoised = cv2.fastNlMeansDenoising(thresh, h=10)

        return denoised

    def _read_text(self, img: np.ndarray) -> list[tuple[str, float]]:
        """
        Run OCR on image, return list of (text, confidence) tuples.
        """
        if self._reader is None:
            return []

        processed = self._preprocess_for_ocr(img)
        try:
            results = self._reader.readtext(processed, detail=1)
            text_results = []
            for (bbox, text, confidence) in results:
                if confidence >= self.ocr_confidence:
                    text_results.append((text.lower().strip(), confidence))
            return text_results
        except Exception as e:
            logger.debug(f"OCR error: {e}")
            return []

    def _detection_loop(self):
        """Main detection loop — polls kill feed region."""
        logger.debug("Detection loop started")
        region = self._get_killfeed_region()

        while self._running:
            try:
                img = self._capture_region(region)
                if img is not None:
                    self._analyze_killfeed(img)
            except Exception as e:
                logger.debug(f"Detection loop error: {e}")

            time.sleep(self.poll_interval)

    def _analyze_killfeed(self, img: np.ndarray):
        """Analyze kill feed image for events involving our player."""
        texts = self._read_text(img)
        if not texts:
            return

        full_text = " ".join(t[0] for t in texts)
        username_lower = self.username.lower()

        # Check if our player appears in any kill feed line
        if username_lower not in full_text:
            return

        # Parse the event
        event = self._parse_killfeed_text(full_text, username_lower)
        if event:
            self._fire_event(event)

    def _parse_killfeed_text(self, text: str, username: str) -> GameEvent | None:
        """
        Parse kill feed text to determine event type.
        
        Kill feed patterns in Apex:
        "[player] knocked down [target]"
        "[player] killed [target]"  
        "[player] eliminated [target]"
        
        We need to know if username is the KILLER or the VICTIM.
        """
        # Patterns for outgoing events (you did something)
        knock_out_patterns = [
            rf"{username}.{{0,20}}knocked down",
            rf"{username}.{{0,20}}knocked",
        ]
        kill_out_patterns = [
            rf"{username}.{{0,20}}killed",
            rf"{username}.{{0,20}}eliminated",
            rf"{username}.{{0,20}}finished",
        ]

        # Patterns for incoming events (something happened to you)
        knock_in_patterns = [
            rf"knocked down.{{0,20}}{username}",
            rf"knocked.{{0,20}}{username}",
        ]
        kill_in_patterns = [
            rf"killed.{{0,20}}{username}",
            rf"eliminated.{{0,20}}{username}",
            rf"finished.{{0,20}}{username}",
        ]

        now = time.time()
        event_type = None

        # Check outgoing first
        for pattern in knock_out_patterns:
            if re.search(pattern, text):
                event_type = EventType.KNOCK_BY_YOU
                break

        if not event_type:
            for pattern in kill_out_patterns:
                if re.search(pattern, text):
                    event_type = EventType.KILL_BY_YOU
                    break

        # Check incoming
        if not event_type:
            for pattern in knock_in_patterns:
                if re.search(pattern, text):
                    event_type = EventType.KNOCKED_BY_ENEMY
                    break

        if not event_type:
            for pattern in kill_in_patterns:
                if re.search(pattern, text):
                    event_type = EventType.KILLED_BY_ENEMY
                    break

        if not event_type:
            return None

        # Extract opponent name (the other player in the kill feed line)
        opponent = self._extract_opponent(text, username)

        event = GameEvent(
            event_type  = event_type,
            timestamp   = now,
            player      = username,
            target      = opponent,
            session_id  = datetime.now().strftime("%Y%m%d_%H%M%S"),
        )

        logger.info(f"Kill feed event: {event_type.value} | "
                    f"Opponent: {opponent} | Text: '{text[:60]}'")
        return event

    def _extract_opponent(self, text: str, username: str) -> str:
        """Extract the opponent's name from kill feed text."""
        # Remove our username and common verbs to find opponent
        cleaned = text.replace(username, "").strip()
        for verb in ["knocked down", "knocked", "killed", "eliminated", "finished"]:
            cleaned = cleaned.replace(verb, "").strip()
        # Clean remaining noise
        cleaned = re.sub(r"[^a-zA-Z0-9_\-]", " ", cleaned).strip()
        cleaned = " ".join(cleaned.split())  # normalize spaces
        return cleaned[:32] if cleaned else "unknown"

    def _fire_event(self, event: GameEvent):
        """Fire event, with deduplication to prevent double-firing."""
        event_key = f"{event.event_type.value}_{event.target}"
        now = time.time()

        # Check if we fired this same event recently
        if event_key in self._last_events:
            if now - self._last_events[event_key] < self._dedupe_window:
                return  # duplicate, skip

        self._last_events[event_key] = now
        self.session_events.append(event)

        # Call the callback (which triggers clip saving)
        if self.event_callback:
            threading.Thread(
                target=self.event_callback,
                args=(event,),
                daemon=True,
                name=f"AriaClipSaver_{event.event_type.value}"
            ).start()

    def detect_damage_numbers(self) -> list[int]:
        """
        Detect damage numbers that appear on screen during combat.
        These float up when you hit an enemy.
        Returns list of damage values detected.
        """
        damage_region = {
            "left":   int(self._screen_w * DAMAGE_REGION["left_pct"]),
            "top":    int(self._screen_h * DAMAGE_REGION["top_pct"]),
            "width":  int(self._screen_w * DAMAGE_REGION["width_pct"]),
            "height": int(self._screen_h * DAMAGE_REGION["height_pct"]),
        }

        img = self._capture_region(damage_region)
        if img is None:
            return []

        texts = self._read_text(img)
        damage_values = []

        for text, confidence in texts:
            # Damage numbers are purely numeric, typically 10-300
            text_clean = text.strip().replace(",", "")
            if text_clean.isdigit():
                val = int(text_clean)
                if 5 <= val <= 300:
                    damage_values.append(val)

        return damage_values

    def detect_match_end(self) -> bool:
        """
        Detect when a match ends (lobby screen visible).
        Used to trigger Aria's post-match coaching session.
        Looks for the lobby/character select screen.
        """
        # Capture center of screen
        center_region = {
            "left":   int(self._screen_w * 0.30),
            "top":    int(self._screen_h * 0.40),
            "width":  int(self._screen_w * 0.40),
            "height": int(self._screen_h * 0.20),
        }

        img = self._capture_region(center_region)
        if img is None:
            return False

        texts = self._read_text(img)
        full_text = " ".join(t[0] for t in texts)

        lobby_indicators = [
            "play again", "continue", "lobby",
            "apex legends", "choose legend",
            "ready", "firing range"
        ]

        for indicator in lobby_indicators:
            if indicator in full_text:
                logger.info(f"Match end detected: '{indicator}' found on screen")
                return True

        return False

    def get_session_summary(self) -> dict:
        """Return a summary of all events in this session."""
        knocks = [e for e in self.session_events
                  if e.event_type == EventType.KNOCK_BY_YOU]
        kills  = [e for e in self.session_events
                  if e.event_type == EventType.KILL_BY_YOU]
        downs  = [e for e in self.session_events
                  if e.event_type == EventType.KNOCKED_BY_ENEMY]
        deaths = [e for e in self.session_events
                  if e.event_type == EventType.KILLED_BY_ENEMY]

        return {
            "total_events": len(self.session_events),
            "knocks":       len(knocks),
            "kills":        len(kills),
            "downs":        len(downs),
            "deaths":       len(deaths),
            "kd_ratio":     round((len(kills)) / max(len(deaths), 1), 2),
            "session_duration_min": round(
                (time.time() - self.session_start) / 60, 1),
        }


# ── Quick test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    def on_event(event: GameEvent):
        print(f"\n🎮 EVENT: {event.event_type.value}")
        print(f"   Target: {event.target}")
        print(f"   Time: {datetime.fromtimestamp(event.timestamp)}")

    config = {
        "apex_username":  "Hidarikikinoaku",
        "poll_interval":  "0.5",
        "ocr_confidence": "0.65",
    }

    detector = KillFeedDetector(config, event_callback=on_event)

    print("Kill Feed Detector Test")
    print(f"Watching for: Hidarikikinoaku")
    print("Open Apex Legends and play — events will appear here")
    print("Press Ctrl+C to stop\n")

    if detector.start():
        print("✅ Detector running\n")
        try:
            while True:
                time.sleep(10)
                summary = detector.get_session_summary()
                print(f"Session: {summary['knocks']} knocks | "
                      f"{summary['deaths']} deaths | "
                      f"KD: {summary['kd_ratio']}")
        except KeyboardInterrupt:
            detector.stop()
            print("\nFinal session summary:")
            print(detector.get_session_summary())
    else:
        print("❌ Could not start detector")
