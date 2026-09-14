"""
ARIA — GameSir G7 Pro 8K Controller Input Logger
=================================================
Reads every input from your GameSir G7 Pro in real time.
Logs stick positions, trigger depths, button presses with timestamps.
Syncs input timeline to gameplay clips so Aria can show
exactly what your hands did during every fight.

Zero performance impact — runs in a background thread.
Logs to session file, read only after match ends.

Player: Hidarikikinoaku
Controller: GameSir G7 Pro 8K (Hall Effect Sticks)
"""

import time
import json
import threading
import os
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from loguru import logger

try:
    import inputs
    INPUTS_AVAILABLE = True
except ImportError:
    INPUTS_AVAILABLE = False
    logger.warning("inputs library not installed — controller logging disabled")

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


# ── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class ControllerState:
    """Snapshot of controller state at a point in time."""
    timestamp: float = 0.0

    # Left stick (movement) — Hall Effect, -1.0 to 1.0
    left_x: float  = 0.0     # -1.0 = full left, 1.0 = full right
    left_y: float  = 0.0     # -1.0 = full up,   1.0 = full down

    # Right stick (aim) — Hall Effect, -1.0 to 1.0
    right_x: float = 0.0
    right_y: float = 0.0

    # Triggers — 0.0 to 1.0
    left_trigger:  float = 0.0   # ADS
    right_trigger: float = 0.0   # Fire

    # Face buttons
    btn_a:     bool = False   # Jump
    btn_b:     bool = False   # Crouch / Slide
    btn_x:     bool = False   # Reload / Interact
    btn_y:     bool = False   # Switch weapon

    # Bumpers
    lb: bool = False          # Ability 1 (Q)
    rb: bool = False          # Ability 2 (E)

    # Stick clicks
    ls_click: bool = False    # Sprint / Melee
    rs_click: bool = False    # Melee / Inspect

    # D-Pad
    dpad_up:    bool = False
    dpad_down:  bool = False
    dpad_left:  bool = False
    dpad_right: bool = False

    # System
    start:  bool = False      # Menu / Map
    select: bool = False      # Inventory

    # Derived metrics (calculated)
    is_moving:       bool  = False   # left stick outside deadzone
    is_aiming:       bool  = False   # left trigger > threshold
    is_firing:       bool  = False   # right trigger > threshold
    movement_speed:  float = 0.0     # 0.0 to 1.0 — how hard you're pushing stick
    aim_speed:       float = 0.0     # right stick magnitude


@dataclass
class InputEvent:
    """A discrete input change event."""
    timestamp: float
    event_type: str    # button_press, button_release, stick_move, trigger
    input_name: str    # A, B, LEFT_X, RIGHT_TRIGGER, etc.
    value: float       # 1.0 for press, 0.0 for release, float for analog
    state_snapshot: dict = None   # full controller state at this moment


# ── Controller Logger ────────────────────────────────────────────────────────

class ControllerLogger:
    """
    Logs all GameSir G7 Pro inputs during a match session.
    
    Runs in background — zero impact on game performance.
    After match ends, the log is synced to clip timestamps
    so Aria can show your exact inputs on screen.
    """

    DEADZONE = 0.10   # matches GameSir default, adjust to taste

    def __init__(self, config: dict):
        self.session_id     = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_folder     = Path(config.get("input_log_folder", "data/sessions"))
        self.log_folder.mkdir(parents=True, exist_ok=True)
        self.log_file       = self.log_folder / f"{self.session_id}_inputs.jsonl"
        self.deadzone       = float(config.get("stick_deadzone", 0.10))
        self.trigger_dead   = float(config.get("trigger_deadzone", 0.05))

        self.state          = ControllerState()
        self.events: list[InputEvent] = []
        self.session_start  = time.time()

        self._running       = False
        self._thread        = None
        self._lock          = threading.Lock()
        self._log_handle    = None

        # Stats tracked for Aria's coaching analysis
        self.stats = {
            "total_inputs":          0,
            "time_moving":           0.0,   # seconds left stick active
            "time_aiming":           0.0,   # seconds ADS held
            "time_firing":           0.0,   # seconds firing
            "time_moving_while_aiming": 0.0,  # the key coaching metric
            "time_stationary_while_aiming": 0.0,
            "jump_count":            0,
            "slide_count":           0,
            "ads_activations":       0,
            "avg_ads_duration_ms":   0.0,
            "fire_bursts":           0,
            "ability_1_uses":        0,
            "ability_2_uses":        0,
            "melee_count":           0,
        }

        self._ads_start_time  = None
        self._ads_durations   = []
        self._last_state_time = time.time()

        logger.info(f"Controller logger initialized | Session: {self.session_id}")

    def start(self) -> bool:
        """Start logging controller inputs in background thread."""
        if not INPUTS_AVAILABLE:
            logger.error("inputs library not available")
            logger.info("Install with: pip install inputs")
            return False

        # Check controller is connected
        if not self._controller_connected():
            logger.warning("GameSir G7 Pro not detected — checking again in 5s")
            time.sleep(5)
            if not self._controller_connected():
                logger.error("Controller not found. Make sure GameSir G7 Pro is connected via USB.")
                return False

        self._running = True
        self._log_handle = open(self.log_file, "w")
        self._thread = threading.Thread(
            target=self._log_loop,
            daemon=True,
            name="AriaControllerLogger"
        )
        self._thread.start()
        logger.info("Controller logging started ✅")
        return True

    def stop(self) -> dict:
        """Stop logging and return session statistics."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._log_handle:
            self._log_handle.close()

        self._finalize_stats()
        self._save_stats()

        logger.info(f"Controller logging stopped | "
                    f"{self.stats['total_inputs']} inputs logged")
        return self.stats

    def _controller_connected(self) -> bool:
        """Check if any gamepad is connected."""
        try:
            gamepads = inputs.devices.gamepads
            if gamepads:
                logger.info(f"Controller found: {gamepads[0]}")
                return True
            return False
        except Exception:
            return False

    def _log_loop(self):
        """Main input reading loop — runs in background thread."""
        logger.debug("Controller log loop started")

        while self._running:
            try:
                events = inputs.get_gamepad()
                for raw_event in events:
                    if not self._running:
                        break
                    self._process_event(raw_event)

            except inputs.UnpluggedError:
                logger.warning("Controller unplugged — waiting for reconnect...")
                time.sleep(2)
            except Exception as e:
                if self._running:
                    logger.error(f"Controller read error: {e}")
                    time.sleep(0.1)

    def _process_event(self, raw):
        """Process a raw input event and update state."""
        now = time.time()
        elapsed = now - self._last_state_time

        # Update time-in-state stats before changing state
        self._update_time_stats(elapsed)
        self._last_state_time = now

        event_type = raw.ev_type
        code       = raw.code
        value      = raw.state

        # Normalize stick values from raw int to -1.0 to 1.0
        # Xbox/XInput: range is -32768 to 32767
        def norm_stick(v): return round(max(-1.0, min(1.0, v / 32767.0)), 4)
        def norm_trigger(v): return round(max(0.0, min(1.0, v / 255.0)), 4)
        def apply_deadzone(v, dz): return 0.0 if abs(v) < dz else v

        input_event = None

        with self._lock:
            prev_state = ControllerState(**asdict(self.state))

            # ── Analog sticks ──────────────────────────────
            if code == "ABS_X":
                raw_val = apply_deadzone(norm_stick(value), self.deadzone)
                self.state.left_x = raw_val
                input_event = InputEvent(now, "stick_move", "LEFT_X", raw_val)

            elif code == "ABS_Y":
                raw_val = apply_deadzone(norm_stick(value), self.deadzone)
                self.state.left_y = raw_val
                input_event = InputEvent(now, "stick_move", "LEFT_Y", raw_val)

            elif code == "ABS_RX":
                raw_val = apply_deadzone(norm_stick(value), self.deadzone)
                self.state.right_x = raw_val
                input_event = InputEvent(now, "stick_move", "RIGHT_X", raw_val)

            elif code == "ABS_RY":
                raw_val = apply_deadzone(norm_stick(value), self.deadzone)
                self.state.right_y = raw_val
                input_event = InputEvent(now, "stick_move", "RIGHT_Y", raw_val)

            # ── Triggers ───────────────────────────────────
            elif code == "ABS_Z":   # Left trigger — ADS
                t_val = norm_trigger(value)
                was_ads = self.state.is_aiming
                self.state.left_trigger = t_val
                self.state.is_aiming = t_val > self.trigger_dead

                if self.state.is_aiming and not was_ads:
                    self._ads_start_time = now
                    self.stats["ads_activations"] += 1
                elif not self.state.is_aiming and was_ads and self._ads_start_time:
                    duration_ms = (now - self._ads_start_time) * 1000
                    self._ads_durations.append(duration_ms)
                    self._ads_start_time = None

                input_event = InputEvent(now, "trigger", "LEFT_TRIGGER", t_val)

            elif code == "ABS_RZ":  # Right trigger — Fire
                t_val = norm_trigger(value)
                was_firing = self.state.is_firing
                self.state.right_trigger = t_val
                self.state.is_firing = t_val > self.trigger_dead

                if self.state.is_firing and not was_firing:
                    self.stats["fire_bursts"] += 1

                input_event = InputEvent(now, "trigger", "RIGHT_TRIGGER", t_val)

            # ── Face Buttons ───────────────────────────────
            elif code == "BTN_SOUTH":   # A — Jump
                self.state.btn_a = bool(value)
                if value:
                    self.stats["jump_count"] += 1
                input_event = InputEvent(now,
                    "button_press" if value else "button_release", "A", float(value))

            elif code == "BTN_EAST":    # B — Crouch/Slide
                self.state.btn_b = bool(value)
                if value:
                    self.stats["slide_count"] += 1
                input_event = InputEvent(now,
                    "button_press" if value else "button_release", "B", float(value))

            elif code == "BTN_WEST":    # X — Reload/Interact
                self.state.btn_x = bool(value)
                input_event = InputEvent(now,
                    "button_press" if value else "button_release", "X", float(value))

            elif code == "BTN_NORTH":   # Y — Switch weapon
                self.state.btn_y = bool(value)
                input_event = InputEvent(now,
                    "button_press" if value else "button_release", "Y", float(value))

            # ── Bumpers ────────────────────────────────────
            elif code == "BTN_TL":      # LB — Ability 1
                self.state.lb = bool(value)
                if value:
                    self.stats["ability_1_uses"] += 1
                input_event = InputEvent(now,
                    "button_press" if value else "button_release", "LB", float(value))

            elif code == "BTN_TR":      # RB — Ability 2
                self.state.rb = bool(value)
                if value:
                    self.stats["ability_2_uses"] += 1
                input_event = InputEvent(now,
                    "button_press" if value else "button_release", "RB", float(value))

            # ── Stick Clicks ───────────────────────────────
            elif code == "BTN_THUMBL":  # LS click — Sprint/Melee
                self.state.ls_click = bool(value)
                if value:
                    self.stats["melee_count"] += 1
                input_event = InputEvent(now,
                    "button_press" if value else "button_release", "LS", float(value))

            elif code == "BTN_THUMBR":  # RS click — Melee
                self.state.rs_click = bool(value)
                input_event = InputEvent(now,
                    "button_press" if value else "button_release", "RS", float(value))

            # ── D-Pad ──────────────────────────────────────
            elif code == "ABS_HAT0Y":
                self.state.dpad_up   = value == -1
                self.state.dpad_down = value == 1
                input_event = InputEvent(now, "dpad", "DPAD_Y", float(value))

            elif code == "ABS_HAT0X":
                self.state.dpad_left  = value == -1
                self.state.dpad_right = value == 1
                input_event = InputEvent(now, "dpad", "DPAD_X", float(value))

            # Update derived metrics
            import math
            self.state.movement_speed = round(
                math.sqrt(self.state.left_x**2 + self.state.left_y**2), 4)
            self.state.aim_speed = round(
                math.sqrt(self.state.right_x**2 + self.state.right_y**2), 4)
            self.state.is_moving = self.state.movement_speed > self.deadzone

        # Write event to log file
        if input_event:
            self.stats["total_inputs"] += 1
            input_event.state_snapshot = {
                "left_x":        self.state.left_x,
                "left_y":        self.state.left_y,
                "right_x":       self.state.right_x,
                "right_y":       self.state.right_y,
                "left_trigger":  self.state.left_trigger,
                "right_trigger": self.state.right_trigger,
                "is_moving":     self.state.is_moving,
                "is_aiming":     self.state.is_aiming,
                "is_firing":     self.state.is_firing,
                "movement_speed": self.state.movement_speed,
            }
            log_line = json.dumps({
                "t":     round(input_event.timestamp - self.session_start, 4),
                "type":  input_event.event_type,
                "input": input_event.input_name,
                "value": input_event.value,
                "state": input_event.state_snapshot,
            })
            if self._log_handle:
                self._log_handle.write(log_line + "\n")
                self._log_handle.flush()

    def _update_time_stats(self, elapsed: float):
        """Update cumulative time stats based on current state."""
        if self.state.is_moving:
            self.stats["time_moving"] += elapsed
        if self.state.is_aiming:
            self.stats["time_aiming"] += elapsed
        if self.state.is_firing:
            self.stats["time_firing"] += elapsed
        if self.state.is_moving and self.state.is_aiming:
            self.stats["time_moving_while_aiming"] += elapsed
        elif self.state.is_aiming and not self.state.is_moving:
            self.stats["time_stationary_while_aiming"] += elapsed

    def _finalize_stats(self):
        """Calculate derived statistics after session ends."""
        if self._ads_durations:
            self.stats["avg_ads_duration_ms"] = round(
                sum(self._ads_durations) / len(self._ads_durations), 1)

        # Movement while aiming percentage — KEY COACHING METRIC
        if self.stats["time_aiming"] > 0:
            pct = self.stats["time_moving_while_aiming"] / self.stats["time_aiming"]
            self.stats["movement_while_aiming_pct"] = round(pct * 100, 1)
        else:
            self.stats["movement_while_aiming_pct"] = 0.0

        # Total session duration
        self.stats["session_duration_s"] = round(
            time.time() - self.session_start, 1)

    def _save_stats(self):
        """Save final stats to session folder."""
        stats_path = self.log_folder / f"{self.session_id}_controller_stats.json"
        with open(stats_path, "w") as f:
            json.dump(self.stats, f, indent=2)
        logger.info(f"Controller stats saved: {stats_path}")

    def get_inputs_for_clip(self, clip_start: float, clip_end: float) -> list[dict]:
        """
        Extract inputs that occurred during a specific clip's time window.
        Used to overlay controller inputs on coaching videos.
        
        clip_start / clip_end are seconds since session start.
        """
        if not self.log_file.exists():
            return []

        clip_inputs = []
        with open(self.log_file) as f:
            for line in f:
                try:
                    event = json.loads(line.strip())
                    t = event.get("t", 0)
                    if clip_start <= t <= clip_end:
                        clip_inputs.append(event)
                except json.JSONDecodeError:
                    continue

        return clip_inputs

    def get_coaching_summary(self) -> str:
        """
        Returns a plain-English coaching summary of controller stats.
        Fed to Aria's AI analysis engine.
        """
        s = self.stats
        pct = s.get("movement_while_aiming_pct", 0)
        session_min = round(s.get("session_duration_s", 0) / 60, 1)

        lines = [
            f"Session duration: {session_min} minutes",
            f"Total inputs: {s['total_inputs']}",
            f"",
            f"MOVEMENT:",
            f"  Moving while aiming: {pct}%",
            f"  (Pro benchmark: 70%+. Below 50% means you're standing still in fights.)",
            f"  Time aiming total: {round(s['time_aiming'], 1)}s",
            f"  Time stationary while aiming: {round(s['time_stationary_while_aiming'], 1)}s",
            f"",
            f"MECHANICS:",
            f"  ADS activations: {s['ads_activations']}",
            f"  Avg ADS hold time: {s['avg_ads_duration_ms']}ms",
            f"  Fire bursts: {s['fire_bursts']}",
            f"  Jumps: {s['jump_count']}",
            f"  Slides: {s['slide_count']}",
            f"  Melees: {s['melee_count']}",
            f"",
            f"ABILITIES:",
            f"  Ability 1 (Q): {s['ability_1_uses']} uses",
            f"  Ability 2 (E): {s['ability_2_uses']} uses",
        ]
        return "\n".join(lines)


# ── Quick test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("GameSir G7 Pro Input Logger Test")
    print("Press Ctrl+C to stop\n")

    config = {
        "input_log_folder": "data/sessions",
        "stick_deadzone":   "0.10",
        "trigger_deadzone": "0.05",
    }

    logger_instance = ControllerLogger(config)

    if logger_instance.start():
        print("✅ Controller connected — logging inputs")
        print("   Move sticks, press buttons — you'll see events in the log")
        try:
            while True:
                time.sleep(5)
                print(f"   Inputs logged so far: {logger_instance.stats['total_inputs']}")
        except KeyboardInterrupt:
            stats = logger_instance.stop()
            print("\n" + logger_instance.get_coaching_summary())
    else:
        print("❌ Controller not found")
        print("   Connect your GameSir G7 Pro via USB and try again")
