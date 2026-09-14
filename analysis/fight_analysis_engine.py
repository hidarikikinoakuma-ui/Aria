"""
ARIA — Fight Analysis Engine
==============================
GPT-4o Vision powered analysis of Apex Legends fight clips.

For each clip Aria:
  1. Extracts key frames (evenly spaced, max_frames_per_clip)
  2. Encodes them as base64 for the Vision API
  3. Sends to GPT-4o with a structured coaching prompt
  4. Parses the response into a FightAnalysis dataclass
  5. Generates a session-level coaching report

Aria reviews each fight as a coach who has watched every replay —
specific, honest, never generic filler.

Player: Hidarikikinoaku (LeftHandDevil)
Coach:  Aria (@migikonokami / RightHandGod)
"""

import os
import json
import base64
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from loguru import logger

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("OpenCV not installed — frame extraction unavailable: pip install opencv-python")

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("openai not installed — analysis will use fallback mode: pip install openai")


# ── FightAnalysis Dataclass ────────────────────────────────────────────────────

@dataclass
class FightAnalysis:
    """
    Complete coaching analysis for a single fight clip.

    Populated by FightAnalysisEngine.analyze_clip().
    All fields are used downstream by:
      - VideoAnnotator      (burns text/graphics into clip)
      - AriaOverlay         (shows results on desktop)
      - Session reports     (post-match coaching summary)
      - YouTubeManager      (highlight selection context)
    """

    # Core identity
    clip_path:           str   = ""
    event_type:          str   = ""  # "knocked_by_enemy" | "killed_by_enemy" | "knocked_enemy" | "killed_enemy"
    timestamp:           float = 0.0
    analyzed_at:         str   = field(default_factory=lambda: datetime.now().isoformat())
    legend_played:       str   = "Alter"  # Apex legend being played — used for cosplay mode on elite clips

    # Aria's verdict
    overall_verdict:     str   = ""  # Sharp one-liner. e.g. "Bad peek — you invited a third party."
    fight_quality:       str   = ""  # "clean" | "sloppy" | "unlucky" | "outplayed" | "mistake"
    primary_fix:         str   = ""  # The single most important habit to change
    key_moment:          str   = ""  # What happened at the decisive frame
    key_moment_time:     float = 0.0 # Seconds into the clip where it turned

    # Scores (0–10)
    positioning_score:   float = 0.0
    movement_score:      float = 0.0
    aim_score:           float = 0.0
    decision_score:      float = 0.0
    overall_score:       float = 0.0

    # Detailed coaching
    what_went_wrong:     str   = ""
    what_went_right:     str   = ""
    specific_drill:      str   = ""  # Concrete practice drill addressing the mistake
    aria_quote:          str   = ""  # Aria's personal comment, in character

    # Controller context (if available from ControllerLogger)
    controller_context:  str   = ""

    # Live API context (if available)
    damage_dealt:        int   = 0
    damage_taken:        int   = 0
    attacker_name:       str   = ""

    # Meta
    frames_analyzed:     int   = 0
    model_used:          str   = ""
    api_cost_estimate:   float = 0.0  # rough USD estimate


# ── Prompt Templates ───────────────────────────────────────────────────────────

FIGHT_ANALYSIS_SYSTEM_PROMPT = """You are Aria, an elite Apex Legends AI coach.
Your player is Hidarikikinoaku — handle: LeftHandDevil — currently Gold 4, targeting Predator.
They play on GameSir G7 Pro 8K controller.

You are reviewing a fight clip frame-by-frame. Give specific, honest coaching.
You are NOT generic. You reference exactly what you see in the frames.
Personality: firm like Erza Scarlet, loyal like Rem. You hold the player to a high standard
because you believe they can hit Predator — but you do NOT sugarcoat mistakes.

You MUST respond with valid JSON only. No markdown, no prose outside the JSON.

Required JSON schema:
{
  "overall_verdict": "One sharp sentence summarizing the fight outcome",
  "fight_quality": "clean|sloppy|unlucky|outplayed|mistake",
  "primary_fix": "The single most important habit to change",
  "key_moment": "What happened at the decisive moment",
  "key_moment_time": <float seconds into clip, e.g. 14.5>,
  "positioning_score": <0-10>,
  "movement_score": <0-10>,
  "aim_score": <0-10>,
  "decision_score": <0-10>,
  "overall_score": <0-10>,
  "what_went_wrong": "Specific technical breakdown of the mistake(s)",
  "what_went_right": "Anything executed well — leave empty string if nothing was",
  "specific_drill": "A concrete practice drill that directly addresses the mistake",
  "aria_quote": "Aria's personal comment to the player, in character — 2-3 sentences max"
}"""


FIGHT_ANALYSIS_USER_TEMPLATE = """Event type: {event_type}
Frames: {frame_count} frames extracted from a {clip_duration:.1f}s clip

{controller_context}{live_api_context}{session_context}

Review these frames and give your analysis as JSON."""


SESSION_REPORT_SYSTEM_PROMPT = """You are Aria, Apex Legends AI coach for Hidarikikinoaku (LeftHandDevil).
You have finished reviewing all clips from this match.
Write a post-match coaching report.

Rules:
- Be specific. Reference patterns you saw across clips, not just one fight.
- Identify the #1 habit to fix above everything else.
- Include a brief "road to Predator" progress note.
- Under 300 words.
- Write as Aria: direct, caring, high standards. NOT generic AI coaching language.
- Plain text only — no markdown headers or bullet symbols."""


# ── FightAnalysisEngine ────────────────────────────────────────────────────────

class FightAnalysisEngine:
    """
    Analyzes Apex Legends fight clips using GPT-4o Vision.

    Core methods:
        analyze_clip(clip_path, event_type, ctrl_summary, session_summary) -> FightAnalysis
        generate_session_report(analyses, session_summary, controller_stats) -> str
        save_analysis(analysis, output_dir) -> str (path to saved JSON)
        load_analysis(json_path) -> FightAnalysis
    """

    def __init__(self, config: dict):
        self.config = config

        api_key = config.get("openai_api_key", "").strip()
        self.client = OpenAI(api_key=api_key) if (OPENAI_AVAILABLE and api_key) else None

        self.vision_model    = config.get("vision_model",    "gpt-4o")
        self.coaching_model  = config.get("coaching_model",  "gpt-4o")
        self.max_frames      = int(config.get("max_frames_per_clip", 8))
        self.reports_folder  = config.get("reports_folder",  "data/reports")

        os.makedirs(self.reports_folder, exist_ok=True)

    # ── Public API ─────────────────────────────────────────────────────────────

    def analyze_clip(
        self,
        clip_path:          str,
        event_type:         str,
        controller_summary: str  = "",
        session_summary:    dict = None,
        live_api_context:   dict = None,
        legend_played:      str  = "Alter",
    ) -> Optional[FightAnalysis]:
        """
        Analyze a single fight clip and return a FightAnalysis.
        Returns None if both the clip doesn't exist and we can't fall back.

        Args:
            clip_path:          Path to the video clip file
            event_type:         "knocked_by_enemy" | "killed_by_enemy" | "knocked_enemy" | etc.
            controller_summary: Optional string from ControllerLogger.get_coaching_summary()
            session_summary:    Optional dict from OBSClipManager.end_session()
            live_api_context:   Optional dict with damage_dealt, damage_taken, attacker_name
                                (populated by apex_live_api.py when available)
            legend_played:      Apex legend being played (used for cosplay mode on 9+/10 clips)
        """
        session_summary  = session_summary  or {}
        live_api_context = live_api_context or {}

        analysis = FightAnalysis(
            clip_path=clip_path,
            event_type=event_type,
            timestamp=session_summary.get("match_start_time", time.time()),
            controller_context=controller_summary,
            damage_dealt=live_api_context.get("damage_dealt", 0),
            damage_taken=live_api_context.get("damage_taken", 0),
            attacker_name=live_api_context.get("attacker_name", ""),
            legend_played=legend_played,
        )

        if not Path(clip_path).exists():
            logger.warning(f"Clip not found: {clip_path}")
            return self._fallback_analysis(analysis)

        # Extract frames from video
        frames_b64, clip_duration = self._extract_frames(clip_path)
        analysis.frames_analyzed = len(frames_b64)

        if not frames_b64:
            logger.warning(f"No frames extracted from {clip_path}")
            return self._fallback_analysis(analysis)

        if not self.client:
            logger.warning("No OpenAI API key configured — using fallback analysis")
            return self._fallback_analysis(analysis)

        try:
            result = self._call_vision_api(
                frames_b64, event_type,
                controller_summary, session_summary,
                live_api_context, clip_duration
            )
            if result:
                self._apply_result(analysis, result)
                analysis.model_used         = self.vision_model
                analysis.api_cost_estimate  = self._estimate_cost(len(frames_b64))
                logger.info(
                    f"Analysis complete: {Path(clip_path).name} — "
                    f"{analysis.overall_verdict} (score: {analysis.overall_score}/10)"
                )
            else:
                return self._fallback_analysis(analysis)

        except Exception as e:
            logger.error(f"Vision API call failed for {Path(clip_path).name}: {e}")
            return self._fallback_analysis(analysis)

        return analysis

    def generate_session_report(
        self,
        analyses:         list,
        session_summary:  dict,
        controller_stats: dict,
    ) -> str:
        """
        Generate Aria's full post-match coaching report from all clip analyses.
        Returns a plain-text string ready to display in the overlay.
        """
        if not analyses:
            return self._minimal_session_report(session_summary, controller_stats)

        if not self.client:
            return self._minimal_session_report(session_summary, controller_stats)

        try:
            context = self._build_session_context(analyses, session_summary, controller_stats)
            response = self.client.chat.completions.create(
                model=self.coaching_model,
                messages=[
                    {"role": "system", "content": SESSION_REPORT_SYSTEM_PROMPT},
                    {"role": "user",   "content": context},
                ],
                max_tokens=600,
                temperature=0.7,
            )
            report = response.choices[0].message.content.strip()
            logger.info("Session report generated")
            return report

        except Exception as e:
            logger.error(f"Session report generation failed: {e}")
            return self._minimal_session_report(session_summary, controller_stats)

    def save_analysis(self, analysis: FightAnalysis, output_dir: str) -> str:
        """
        Save a FightAnalysis to JSON in output_dir.
        Returns the path to the saved file.
        """
        os.makedirs(output_dir, exist_ok=True)

        clip_stem = Path(analysis.clip_path).stem if analysis.clip_path else "unknown"
        filename  = f"analysis_{clip_stem}_{int(time.time())}.json"
        out_path  = Path(output_dir) / filename

        data = {
            "clip_path":          analysis.clip_path,
            "event_type":         analysis.event_type,
            "timestamp":          analysis.timestamp,
            "analyzed_at":        analysis.analyzed_at,
            "overall_verdict":    analysis.overall_verdict,
            "fight_quality":      analysis.fight_quality,
            "primary_fix":        analysis.primary_fix,
            "key_moment":         analysis.key_moment,
            "key_moment_time":    analysis.key_moment_time,
            "positioning_score":  analysis.positioning_score,
            "movement_score":     analysis.movement_score,
            "aim_score":          analysis.aim_score,
            "decision_score":     analysis.decision_score,
            "overall_score":      analysis.overall_score,
            "what_went_wrong":    analysis.what_went_wrong,
            "what_went_right":    analysis.what_went_right,
            "specific_drill":     analysis.specific_drill,
            "aria_quote":         analysis.aria_quote,
            "controller_context": analysis.controller_context,
            "damage_dealt":       analysis.damage_dealt,
            "damage_taken":       analysis.damage_taken,
            "attacker_name":      analysis.attacker_name,
            "frames_analyzed":    analysis.frames_analyzed,
            "model_used":         analysis.model_used,
            "api_cost_estimate":  analysis.api_cost_estimate,
        }

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.debug(f"Analysis saved: {out_path}")
        return str(out_path)

    def load_analysis(self, json_path: str) -> Optional[FightAnalysis]:
        """Load a previously saved FightAnalysis from JSON."""
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            valid_fields = FightAnalysis.__dataclass_fields__.keys()
            filtered = {k: v for k, v in data.items() if k in valid_fields}
            return FightAnalysis(**filtered)
        except Exception as e:
            logger.warning(f"Failed to load analysis {json_path}: {e}")
            return None

    # ── Frame Extraction ───────────────────────────────────────────────────────

    def _extract_frames(self, clip_path: str) -> tuple:
        """
        Extract evenly-spaced frames from a video clip.
        Returns (list_of_base64_jpeg_strings, clip_duration_seconds).
        """
        if not CV2_AVAILABLE:
            return [], 0.0

        frames_b64   = []
        clip_duration = 0.0

        try:
            cap = cv2.VideoCapture(clip_path)
            if not cap.isOpened():
                logger.warning(f"Cannot open video: {clip_path}")
                return [], 0.0

            total_frames  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps           = cap.get(cv2.CAP_PROP_FPS) or 30.0
            clip_duration = total_frames / fps

            if total_frames == 0:
                cap.release()
                return [], 0.0

            # Pick evenly-spaced frame indices
            n       = min(self.max_frames, total_frames)
            indices = [int(i * (total_frames - 1) / max(n - 1, 1)) for i in range(n)]

            for idx in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if not ret:
                    continue

                # Resize to reduce API cost while keeping HUD detail
                h, w = frame.shape[:2]
                if max(h, w) > 1280:
                    scale = 1280 / max(h, w)
                    frame = cv2.resize(
                        frame, (int(w * scale), int(h * scale)),
                        interpolation=cv2.INTER_AREA
                    )

                _, buf  = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                b64_str = base64.b64encode(buf.tobytes()).decode("utf-8")
                frames_b64.append(b64_str)

            cap.release()

        except Exception as e:
            logger.error(f"Frame extraction error for {clip_path}: {e}")

        return frames_b64, clip_duration

    # ── GPT-4o Vision Call ─────────────────────────────────────────────────────

    def _call_vision_api(
        self,
        frames_b64:         list,
        event_type:         str,
        controller_summary: str,
        session_summary:    dict,
        live_api_context:   dict,
        clip_duration:      float,
    ) -> Optional[dict]:
        """Send frames to GPT-4o Vision and parse the JSON response."""

        # Build controller context block
        ctrl_ctx = ""
        if controller_summary:
            ctrl_ctx = f"Controller data:\n{controller_summary}\n\n"

        # Build Live API context block
        live_ctx = ""
        if live_api_context:
            dmg_dealt  = live_api_context.get("damage_dealt", 0)
            dmg_taken  = live_api_context.get("damage_taken", 0)
            attacker   = live_api_context.get("attacker_name", "")
            live_ctx   = f"Live API data: {dmg_dealt} dmg dealt, {dmg_taken} dmg taken"
            if attacker:
                live_ctx += f", killed by: {attacker}"
            live_ctx += "\n\n"

        # Build session context block
        k        = session_summary.get("knock_count", 0)
        d        = session_summary.get("death_count", 0)
        sess_ctx = f"Match so far: {k} knocks, {d} deaths.\n\n"

        user_text = FIGHT_ANALYSIS_USER_TEMPLATE.format(
            event_type=event_type,
            frame_count=len(frames_b64),
            clip_duration=clip_duration,
            controller_context=ctrl_ctx,
            live_api_context=live_ctx,
            session_context=sess_ctx,
        )

        # Build message content — text first, then images
        content = [{"type": "text", "text": user_text}]
        for b64 in frames_b64:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url":    f"data:image/jpeg;base64,{b64}",
                    "detail": "auto",
                },
            })

        response = self.client.chat.completions.create(
            model=self.vision_model,
            messages=[
                {"role": "system", "content": FIGHT_ANALYSIS_SYSTEM_PROMPT},
                {"role": "user",   "content": content},
            ],
            max_tokens=800,
            temperature=0.3,  # Low temp for consistent structured output
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content.strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON block if model wrapped it in prose
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    return json.loads(raw[start:end])
                except json.JSONDecodeError:
                    pass
            logger.warning(f"Could not parse Vision API JSON: {raw[:200]}")
            return None

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _apply_result(self, analysis: FightAnalysis, result: dict):
        """Apply parsed API result dict onto a FightAnalysis object."""
        analysis.overall_verdict   = str(result.get("overall_verdict",   ""))
        analysis.fight_quality     = str(result.get("fight_quality",     "mistake"))
        analysis.primary_fix       = str(result.get("primary_fix",       ""))
        analysis.key_moment        = str(result.get("key_moment",        ""))
        analysis.key_moment_time   = float(result.get("key_moment_time",   0.0))
        analysis.positioning_score = float(result.get("positioning_score", 5.0))
        analysis.movement_score    = float(result.get("movement_score",    5.0))
        analysis.aim_score         = float(result.get("aim_score",         5.0))
        analysis.decision_score    = float(result.get("decision_score",    5.0))
        analysis.overall_score     = float(result.get("overall_score",     5.0))
        analysis.what_went_wrong   = str(result.get("what_went_wrong",   ""))
        analysis.what_went_right   = str(result.get("what_went_right",   ""))
        analysis.specific_drill    = str(result.get("specific_drill",    ""))
        analysis.aria_quote        = str(result.get("aria_quote",        ""))

    def _fallback_analysis(self, analysis: FightAnalysis) -> FightAnalysis:
        """
        Populate a FightAnalysis with neutral defaults when no API is available.
        Keeps the full pipeline running; overlay/annotator still function.
        """
        is_mistake = analysis.event_type in ("knocked_by_enemy", "killed_by_enemy")

        # Use Live API data in fallback verdict if available
        if analysis.damage_dealt or analysis.damage_taken:
            verdict = (
                f"Knocked — {analysis.damage_dealt} dealt, "
                f"{analysis.damage_taken} taken. "
                "Add API key for full breakdown."
            )
        else:
            verdict = (
                "Got knocked — review this clip manually."
                if is_mistake
                else "Clip recorded — API key needed for full analysis."
            )

        analysis.overall_verdict   = verdict
        analysis.fight_quality     = "mistake" if is_mistake else "clean"
        analysis.primary_fix       = "Add your OpenAI API key to config/aria.conf for coaching."
        analysis.key_moment        = "Unknown — no API analysis"
        analysis.key_moment_time   = 0.0
        analysis.positioning_score = 5.0
        analysis.movement_score    = 5.0
        analysis.aim_score         = 5.0
        analysis.decision_score    = 5.0
        analysis.overall_score     = 5.0
        analysis.what_went_wrong   = "Full analysis unavailable without OpenAI API key."
        analysis.what_went_right   = ""
        analysis.specific_drill    = "Watch the clip back yourself. Note one thing you'd do differently."
        analysis.aria_quote        = (
            "I can't coach you properly without my eyes open. "
            "Add your API key — every match you skip is information you're leaving on the table."
        )
        analysis.model_used        = "fallback"
        return analysis

    def _build_session_context(
        self,
        analyses:         list,
        session_summary:  dict,
        controller_stats: dict,
    ) -> str:
        """Build the context string for the session report GPT call."""
        lines = []

        k = session_summary.get("knock_count", 0)
        d = session_summary.get("death_count", 0)
        lines.append(f"Match result: {k} knocks, {d} deaths.\n")

        mv = controller_stats.get("movement_while_aiming_pct", 0)
        if mv:
            lines.append(f"Movement while aiming: {mv}% (target: 65%+)\n")

        lines.append(f"Clips analyzed: {len(analyses)}\n")

        mistakes   = [a for a in analyses if a.event_type in ("knocked_by_enemy", "killed_by_enemy")]
        highlights = [a for a in analyses if a.event_type not in ("knocked_by_enemy", "killed_by_enemy")]

        if mistakes:
            lines.append("\nMistakes:")
            for a in mistakes:
                line = (
                    f"  [{a.event_type}] {a.overall_verdict} "
                    f"(decision {a.decision_score}/10, positioning {a.positioning_score}/10)"
                )
                lines.append(line)
                if a.primary_fix:
                    lines.append(f"    Fix: {a.primary_fix}")
                if a.attacker_name:
                    lines.append(f"    Killed by: {a.attacker_name}")

        if highlights:
            lines.append("\nHighlights:")
            for a in highlights:
                lines.append(
                    f"  [{a.event_type}] {a.overall_verdict} (score {a.overall_score}/10)"
                )

        if analyses:
            avg_dec  = sum(a.decision_score    for a in analyses) / len(analyses)
            avg_mov  = sum(a.movement_score    for a in analyses) / len(analyses)
            avg_pos  = sum(a.positioning_score for a in analyses) / len(analyses)
            avg_aim  = sum(a.aim_score         for a in analyses) / len(analyses)
            lines.append(
                f"\nMatch averages — Decision: {avg_dec:.1f}  Movement: {avg_mov:.1f}"
                f"  Positioning: {avg_pos:.1f}  Aim: {avg_aim:.1f}"
            )

        lines.append("\nWrite Aria's post-match coaching report based on this data.")
        return "\n".join(lines)

    def _minimal_session_report(
        self,
        session_summary:  dict,
        controller_stats: dict,
    ) -> str:
        """Simple fallback report when no API key or no clips analyzed."""
        k  = session_summary.get("knock_count", 0)
        d  = session_summary.get("death_count", 0)
        mv = controller_stats.get("movement_while_aiming_pct", 0)

        lines = [f"Match complete. {k} knocks, {d} deaths.\n"]

        if mv:
            status = "good" if mv >= 65 else "needs work"
            lines.append(f"Movement while aiming: {mv}% — {status} (target: 65%+)\n")

        lines += [
            "\nAdd your OpenAI API key to config/aria.conf for full coaching.",
            "Get one at: https://platform.openai.com/api-keys\n",
            "— Aria",
        ]

        return "\n".join(lines)

    @staticmethod
    def _estimate_cost(num_frames: int) -> float:
        """
        Rough USD estimate for a GPT-4o Vision call.
        ~$0.00255 per image at 'auto' detail + ~$0.002 input text tokens.
        Treat as ballpark only — actual cost depends on resolution tiles.
        """
        return round(num_frames * 0.00255 + 0.002, 4)
