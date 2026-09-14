"""
ARIA — Main Launcher
======================
Starts the entire Aria coaching system.

What runs at startup:
1. System detector — figures out your hardware
2. Controller logger — starts logging GameSir G7 Pro inputs
3. Kill feed detector — watches for knocks/deaths in Apex
4. OBS clip manager — ready to save clips on events
5. Mobile API — starts the phone companion server
6. Match-end watcher — triggers Aria's post-match coaching

The overlay and analysis only run AFTER each match.
Zero performance impact during gameplay.

Player: Hidarikikinoaku (LeftHandDevil)
Coach:  Aria (@migikonokami / RightHandGod)
"""

import sys
import os
import time
import threading
import configparser
import socket
from pathlib import Path
from loguru import logger

# ── Logging setup ─────────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logger.remove()
logger.add(sys.stdout, level="INFO",
           format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}")
logger.add("logs/aria.log", level="DEBUG", rotation="50 MB",
           format="{time} | {level} | {message}")


def load_config(path: str = "config/aria.conf") -> dict:
    """Load configuration from aria.conf into a flat dict."""
    cfg = configparser.ConfigParser()
    cfg.read(path)
    flat = {}
    for section in cfg.sections():
        for key, value in cfg.items(section):
            flat[key] = value
    return flat


def get_local_ip() -> str:
    """Get this machine's local IP for mobile connection instructions."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def print_startup_banner(config: dict, local_ip: str):
    """Print Aria's startup banner."""
    rank = config.get("current_rank", "Gold IV")
    rp   = config.get("current_rp", "143")
    port = config.get("port", "8765")

    banner = f"""
╔══════════════════════════════════════════════════════╗
║                    ARIA SYSTEM                       ║
║              Road to Predator                        ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  Player:   Hidarikikinoaku (LeftHandDevil)           ║
║  Coach:    Aria (@migikonokami)                      ║
║  Rank:     {rank:<20} {rp} RP               ║
║  Target:   Predator                                  ║
║                                                      ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  Controller:  GameSir G7 Pro 8K (auto-detecting)     ║
║  Recording:   OBS Replay Buffer (90s)                ║
║  Analysis:    GPT-4o Vision                          ║
║  Voice:       Coqui TTS (local)                      ║
║                                                      ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  Mobile companion:                                   ║
║  Open on your phone: http://{local_ip:<20}  ║
║  Port: {port}                                         ║
║                                                      ║
║  ARIA IS READY. LAUNCH APEX AND START PLAYING.       ║
║  She will appear after your first match.             ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
"""
    print(banner)


class AriaSystem:
    """
    The main Aria system controller.
    Coordinates all components and manages match lifecycle.
    """

    def __init__(self, config: dict):
        self.config        = config
        self.running       = False

        # Components — imported here to avoid circular imports
        self.clip_manager  = None
        self.controller    = None
        self.killfeed      = None
        self.overlay       = None
        self.mobile_thread = None

        # Match state
        self.in_match      = False
        self.current_session = None

    def start(self):
        """Start all Aria components."""
        self.running = True

        # ── System detection ────────────────────────────────────────────────
        logger.info("Running system detection...")
        try:
            from core.system_detector import load_profile, print_profile
            profile = load_profile()
            print_profile(profile)
        except Exception as e:
            logger.warning(f"System detection failed: {e}")

        # ── OBS Clip Manager ─────────────────────────────────────────────────
        logger.info("Connecting to OBS...")
        try:
            from clips.obs_clip_manager import OBSClipManager
            self.clip_manager = OBSClipManager(self.config)
            if self.clip_manager.connect():
                logger.info("OBS connected ✅")
            else:
                logger.warning("OBS not connected — clips will not be saved")
                logger.warning("Start OBS and enable WebSocket Server (Tools menu)")
        except Exception as e:
            logger.warning(f"OBS setup failed: {e}")

        # ── Controller Logger ─────────────────────────────────────────────────
        logger.info("Starting controller input logger...")
        try:
            from core.controller_logger import ControllerLogger
            self.controller = ControllerLogger(self.config)
            if self.controller.start():
                logger.info("GameSir G7 Pro logging started ✅")
            else:
                logger.warning("Controller not detected — connect GameSir G7 Pro via USB")
        except Exception as e:
            logger.warning(f"Controller logger failed: {e}")

        # ── Kill Feed Detector ────────────────────────────────────────────────
        logger.info("Starting kill feed detector...")
        try:
            from core.killfeed_detector import KillFeedDetector
            self.killfeed = KillFeedDetector(
                self.config,
                event_callback=self._on_game_event
            )
            if self.killfeed.start():
                logger.info("Kill feed detection started ✅")
            else:
                logger.warning("Kill feed detection failed to start")
        except Exception as e:
            logger.warning(f"Kill feed detector failed: {e}")

        # ── Mobile API ────────────────────────────────────────────────────────
        logger.info("Starting mobile companion API...")
        self._start_mobile_server()

        # ── Match-end watcher ─────────────────────────────────────────────────
        logger.info("Starting match-end watcher...")
        self._start_match_watcher()

        logger.info("All systems running. Waiting for Apex Legends...")
        logger.info("Aria will appear after your first match ends.")

    def _on_game_event(self, event):
        """Called when kill feed detector fires an event."""
        logger.info(f"Game event: {event.event_type.value} — {event.target}")

        # Save a clip for this event
        if self.clip_manager:
            try:
                clip_path = self.clip_manager.save_clip(event)
                if clip_path:
                    logger.info(f"Clip saved: {Path(clip_path).name}")
            except Exception as e:
                logger.error(f"Clip save failed: {e}")

    def _start_match_watcher(self):
        """
        Watches for match-end screen.
        When detected, triggers Aria's post-match coaching session.
        Runs in background thread — very low overhead.
        """
        def watch():
            was_in_match = False
            check_interval = 5.0   # check every 5 seconds

            while self.running:
                try:
                    if self.killfeed:
                        in_lobby = self.killfeed.detect_match_end()
                        session_events = len(
                            self.killfeed.session_events
                        ) if self.killfeed else 0

                        # Detect match-end transition
                        if in_lobby and was_in_match and session_events > 0:
                            logger.info("Match ended — triggering Aria coaching session")
                            self._run_post_match()
                            was_in_match = False
                        elif not in_lobby and session_events > 0:
                            was_in_match = True

                except Exception as e:
                    logger.debug(f"Match watcher error: {e}")

                time.sleep(check_interval)

        t = threading.Thread(target=watch, daemon=True, name="AriaMatchWatcher")
        t.start()

    def _run_post_match(self):
        """
        Full post-match pipeline:
        1. End the session, collect all clips
        2. Run fight analysis on each clip
        3. Generate coaching report
        4. Show Aria overlay with results
        5. Queue highlights for YouTube
        """
        logger.info("Running post-match analysis pipeline...")

        # ── End session ──────────────────────────────────────────────────────
        session_summary = {}
        controller_stats = {}

        if self.clip_manager:
            session_summary = self.clip_manager.end_session()
        if self.controller:
            controller_stats = self.controller.stop()
            # Restart controller logging for next match
            self.controller.start()

        # ── Analyze clips ─────────────────────────────────────────────────────
        analyses = []
        try:
            from analysis.fight_analysis_engine import FightAnalysisEngine
            engine = FightAnalysisEngine(self.config)

            all_clips = (
                session_summary.get("mistakes", []) +
                session_summary.get("highlights", [])
            )

            max_clips = int(self.config.get("max_clips_per_match", 10))
            for clip_meta in all_clips[:max_clips]:
                clip_path   = clip_meta.get("clip_path", "")
                event_type  = clip_meta.get("event_type", "")
                if not clip_path or not Path(clip_path).exists():
                    continue

                ctrl_summary = ""
                if self.controller:
                    start_t = clip_meta.get("timestamp", 0)
                    inputs  = self.controller.get_inputs_for_clip(
                        start_t - 20, start_t + 8
                    )
                    from core.controller_logger import ControllerLogger
                    temp = ControllerLogger.__new__(ControllerLogger)
                    temp.stats = controller_stats
                    ctrl_summary = temp.get_coaching_summary() if inputs else ""

                analysis = engine.analyze_clip(
                    clip_path, event_type,
                    ctrl_summary, session_summary
                )
                if analysis:
                    analyses.append(analysis)
                    engine.save_analysis(
                        analysis,
                        str(Path(clip_path).parent)
                    )

        except Exception as e:
            logger.error(f"Clip analysis failed: {e}")

        # ── Generate coaching report ──────────────────────────────────────────
        coaching_report = ""
        primary_fix     = ""
        try:
            from analysis.fight_analysis_engine import FightAnalysisEngine
            engine = FightAnalysisEngine(self.config)
            coaching_report = engine.generate_session_report(
                analyses, session_summary, controller_stats
            )
            # Extract primary fix from worst mistake
            mistakes = [a for a in analyses
                        if a.event_type in
                        ("knocked_by_enemy", "killed_by_enemy")]
            if mistakes:
                primary_fix = mistakes[0].primary_fix
        except Exception as e:
            logger.error(f"Coaching report generation failed: {e}")
            coaching_report = self._fallback_report(session_summary, controller_stats)

        # ── Show overlay ──────────────────────────────────────────────────────
        self._show_overlay(session_summary, coaching_report,
                           primary_fix, analyses)

        # ── Annotate mistake clips ─────────────────────────────────────────────
        self._annotate_clips(analyses)

        # ── Queue highlights for YouTube ──────────────────────────────────────
        self._queue_highlights(session_summary, analyses)

        logger.info("Post-match pipeline complete")

    def _show_overlay(self, session_summary: dict, coaching_report: str,
                      primary_fix: str, analyses: list):
        """Show Aria's desktop overlay with coaching results."""
        try:
            from PyQt5.QtWidgets import QApplication
            from overlay.aria_overlay import AriaOverlay

            app = QApplication.instance()
            if not app:
                logger.warning("No QApplication — overlay cannot show")
                return

            if not self.overlay:
                self.overlay = AriaOverlay(self.config)

            # Convert FightAnalysis objects to dicts for overlay
            analyses_dicts = []
            for a in analyses:
                analyses_dicts.append({
                    "event_type": a.event_type,
                    "clip_path":  a.clip_path,
                    "verdict":    a.overall_verdict,
                    "quality":    a.fight_quality,
                })

            self.overlay.show_post_match(
                session_summary=session_summary,
                coaching_report=coaching_report,
                primary_fix=primary_fix,
                analyses=analyses_dicts,
            )
        except Exception as e:
            logger.error(f"Overlay failed: {e}")

    def _annotate_clips(self, analyses: list):
        """Burn coaching annotations into mistake clips in background."""
        def annotate():
            try:
                from analysis.video_annotator import VideoAnnotator
                annotator = VideoAnnotator()
                for a in analyses:
                    if a.event_type in ("knocked_by_enemy", "killed_by_enemy"):
                        annotator.annotate_mistake(
                            a.clip_path,
                            {
                                "overall_verdict":  a.overall_verdict,
                                "key_moment":       a.key_moment,
                                "key_moment_time":  a.key_moment_time,
                                "primary_fix":      a.primary_fix,
                                "positioning_score": a.positioning_score,
                                "movement_score":   a.movement_score,
                                "aim_score":        a.aim_score,
                                "decision_score":   a.decision_score,
                            }
                        )
            except Exception as e:
                logger.debug(f"Annotation failed: {e}")

        threading.Thread(target=annotate, daemon=True,
                         name="AriaAnnotator").start()

    def _queue_highlights(self, session_summary: dict, analyses: list):
        """Add highlights to YouTube weekly queue."""
        try:
            from youtube.youtube_manager import YouTubeManager
            yt = YouTubeManager(self.config)
            yt._load_queue()
            for clip in session_summary.get("highlights", []):
                yt.add_clip_to_queue(clip)
        except Exception as e:
            logger.debug(f"YouTube queue update failed: {e}")

    def _fallback_report(self, session_summary: dict,
                         controller_stats: dict) -> str:
        """Simple fallback report if API unavailable."""
        k  = session_summary.get("knock_count", 0)
        d  = session_summary.get("death_count", 0)
        mv = controller_stats.get("movement_while_aiming_pct", 0)
        return (
            f"Match complete.\n\n"
            f"{k} knocks, {d} deaths.\n\n"
            f"Movement while aiming: {mv}%\n"
            f"(Target: 65%+ to compete at higher ranks)\n\n"
            f"Review your clips and add your OpenAI API key "
            f"to config/aria.conf for full coaching analysis."
        )

    def _start_mobile_server(self):
        """Start mobile companion API in background thread."""
        def run():
            try:
                from mobile.mobile_api import run_mobile_server
                run_mobile_server(
                    self.config,
                    host=self.config.get("host", "0.0.0.0"),
                    port=int(self.config.get("port", 8765))
                )
            except Exception as e:
                logger.error(f"Mobile server failed: {e}")

        self.mobile_thread = threading.Thread(
            target=run, daemon=True, name="AriaMobileAPI"
        )
        self.mobile_thread.start()
        logger.info(f"Mobile server starting on port {self.config.get('port', 8765)} ✅")

    def stop(self):
        """Gracefully stop all components."""
        self.running = False
        if self.killfeed:
            self.killfeed.stop()
        if self.controller:
            self.controller.stop()
        if self.clip_manager:
            self.clip_manager.disconnect()
        logger.info("Aria system stopped")


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    # Change to aria directory
    aria_dir = Path(__file__).parent
    os.chdir(aria_dir)

    # Load config
    config = load_config("config/aria.conf")

    # Print banner
    local_ip = get_local_ip()
    print_startup_banner(config, local_ip)

    # Validate API key
    if not config.get("openai_api_key"):
        logger.warning("No OpenAI API key set!")
        logger.warning("Edit config/aria.conf and add your key under [analysis]")
        logger.warning("Get a key at: https://platform.openai.com/api-keys")
        logger.warning("Aria will run in limited mode without it.\n")

    # Start Qt app for overlay (must be on main thread)
    try:
        from PyQt5.QtWidgets import QApplication
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)

        # Start Aria system
        aria = AriaSystem(config)
        aria.start()

        logger.info("Qt event loop starting — Aria is active")

        # Run Qt event loop
        try:
            sys.exit(app.exec_())
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            aria.stop()

    except ImportError:
        # No PyQt5 — run without overlay
        logger.warning("PyQt5 not installed — running without desktop overlay")
        logger.warning("Install with: pip install PyQt5")

        aria = AriaSystem(config)
        aria.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            aria.stop()


if __name__ == "__main__":
    main()
