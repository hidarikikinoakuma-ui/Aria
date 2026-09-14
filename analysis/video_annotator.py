"""
ARIA — Video Annotator
========================
Takes a fight clip and burns coaching annotations directly into it:
- Red circles around mistakes
- Arrows pointing to what you should have done
- Controller input display showing exactly what your hands did
- Text callouts at key moments
- Aria's verdict text overlay

Output is a clean annotated MP4 ready for review or posting.

Player: Hidarikikinoaku
"""

import os
import json
import math
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.error("OpenCV not installed: pip install opencv-python")

try:
    import ffmpeg
    FFMPEG_AVAILABLE = True
except ImportError:
    FFMPEG_AVAILABLE = False


# ── Annotation Data Structures ────────────────────────────────────────────────

@dataclass
class Annotation:
    """A single annotation that appears at a specific time in the clip."""
    start_sec: float         # when it appears
    end_sec: float           # when it disappears
    annotation_type: str     # circle / arrow / text / controller / highlight_box


@dataclass
class CircleAnnotation(Annotation):
    """Red circle highlighting a mistake area."""
    x: int = 0              # center x
    y: int = 0              # center y
    radius: int = 60
    color: tuple = (0, 50, 192)   # BGR — red
    thickness: int = 3
    label: str = ""
    annotation_type: str = "circle"


@dataclass
class ArrowAnnotation(Annotation):
    """Arrow pointing to what should have happened."""
    x1: int = 0; y1: int = 0    # tail
    x2: int = 0; y2: int = 0    # head (where arrow points)
    color: tuple = (50, 192, 50) # BGR — green
    thickness: int = 3
    label: str = ""
    annotation_type: str = "arrow"


@dataclass
class TextAnnotation(Annotation):
    """Coaching text box that appears at a key moment."""
    x: int = 0
    y: int = 0
    text: str = ""
    color: tuple = (255, 255, 255)
    bg_color: tuple = (13, 13, 46)
    font_scale: float = 0.6
    annotation_type: str = "text"


@dataclass
class ControllerOverlay(Annotation):
    """
    Shows controller input state in the corner.
    Displays live stick positions, triggers, buttons.
    """
    input_timeline: list = field(default_factory=list)  # from controller logger
    position: str = "bottom_left"   # corner position
    annotation_type: str = "controller"


@dataclass
class HighlightBox(Annotation):
    """Pulsing border around the entire frame for key moments."""
    color: tuple = (0, 50, 192)    # BGR — red for mistakes, green for highlights
    thickness: int = 8
    annotation_type: str = "highlight_box"


# ── Annotator ────────────────────────────────────────────────────────────────

class VideoAnnotator:
    """
    Burns coaching annotations into fight clips.

    Two modes:
    - mistake_mode: red circles, mistake callouts, what went wrong
    - highlight_mode: green highlights, clean annotations, ready for YouTube
    """

    # Colors (BGR for OpenCV)
    RED    = (50,  50,  220)
    GREEN  = (50,  200,  50)
    BLUE   = (200, 130,  50)
    WHITE  = (240, 240, 240)
    YELLOW = (50,  200, 200)
    DARK   = (30,   26,  13)

    # Aria's font
    FONT       = cv2.FONT_HERSHEY_DUPLEX
    FONT_SMALL = cv2.FONT_HERSHEY_SIMPLEX

    def __init__(self, output_dir: str = "data/annotated"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def annotate_mistake(
        self,
        clip_path: str,
        analysis: dict,
        controller_inputs: list = None,
    ) -> str:
        """
        Annotate a mistake clip with Aria's coaching callouts.
        Returns path to annotated video.
        """
        annotations = self._build_mistake_annotations(
            clip_path, analysis, controller_inputs or []
        )
        return self._render(clip_path, annotations, mode="mistake")

    def annotate_highlight(
        self,
        clip_path: str,
        analysis: dict,
        title: str = "",
    ) -> str:
        """
        Annotate a highlight clip — clean, minimal, YouTube-ready.
        Returns path to annotated video.
        """
        annotations = self._build_highlight_annotations(
            clip_path, analysis, title
        )
        return self._render(clip_path, annotations, mode="highlight")

    def _build_mistake_annotations(
        self, clip_path: str, analysis: dict, inputs: list
    ) -> list:
        """Build annotation list for a mistake clip."""
        annotations = []
        cap = cv2.VideoCapture(clip_path)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 30)
        cap.release()

        key_time = float(analysis.get("key_moment_time", duration * 0.5))

        # ── Red pulsing border at the key mistake moment ──────────────────
        annotations.append(HighlightBox(
            start_sec=max(0, key_time - 1.5),
            end_sec=min(duration, key_time + 2.0),
            color=self.RED,
            thickness=8,
        ))

        # ── "MISTAKE" label at top ────────────────────────────────────────
        annotations.append(TextAnnotation(
            start_sec=0,
            end_sec=duration,
            x=10, y=40,
            text=f"MISTAKE FILM  •  {analysis.get('overall_verdict', '')}",
            color=self.WHITE,
            bg_color=(20, 20, 80),
            font_scale=0.55,
        ))

        # ── Score bar (top right) ─────────────────────────────────────────
        annotations.append(TextAnnotation(
            start_sec=0,
            end_sec=duration,
            x=w - 320, y=40,
            text=(f"POS:{analysis.get('positioning_score',5)}/10  "
                  f"MOV:{analysis.get('movement_score',5)}/10  "
                  f"AIM:{analysis.get('aim_score',5)}/10"),
            color=self.YELLOW,
            bg_color=(20, 20, 80),
            font_scale=0.45,
        ))

        # ── Key moment callout text ────────────────────────────────────────
        key_moment_text = analysis.get("key_moment", "")
        if key_moment_text:
            # Wrap text to fit screen
            wrapped = self._wrap_text(key_moment_text, 55)
            y_pos = h - (len(wrapped) * 28) - 80
            for i, line in enumerate(wrapped):
                annotations.append(TextAnnotation(
                    start_sec=max(0, key_time - 0.5),
                    end_sec=min(duration, key_time + 4.0),
                    x=10,
                    y=y_pos + (i * 28),
                    text=line,
                    color=self.WHITE,
                    bg_color=(50, 10, 10),
                    font_scale=0.55,
                ))

        # ── Primary fix at the end of clip ────────────────────────────────
        fix_text = analysis.get("primary_fix", "")
        if fix_text:
            wrapped = self._wrap_text(f"FIX: {fix_text}", 50)
            for i, line in enumerate(wrapped):
                annotations.append(TextAnnotation(
                    start_sec=max(0, duration - 3.0),
                    end_sec=duration,
                    x=10,
                    y=h - 120 + (i * 28),
                    text=line,
                    color=self.YELLOW,
                    bg_color=(10, 10, 50),
                    font_scale=0.55,
                ))

        # ── Controller input overlay ──────────────────────────────────────
        if inputs:
            annotations.append(ControllerOverlay(
                start_sec=0,
                end_sec=duration,
                input_timeline=inputs,
                position="bottom_right",
            ))

        # ── Aria watermark ────────────────────────────────────────────────
        annotations.append(TextAnnotation(
            start_sec=0,
            end_sec=duration,
            x=w - 200, y=h - 20,
            text="coached by Aria @migikonokami",
            color=(150, 150, 150),
            bg_color=(0, 0, 0),
            font_scale=0.38,
        ))

        return annotations

    def _build_highlight_annotations(
        self, clip_path: str, analysis: dict, title: str
    ) -> list:
        """Build annotation list for a highlight clip — clean, minimal."""
        annotations = []
        cap = cv2.VideoCapture(clip_path)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 30)
        cap.release()

        # Green border flash at best moment
        key_time = float(analysis.get("key_moment_time", duration * 0.6))
        annotations.append(HighlightBox(
            start_sec=max(0, key_time - 0.3),
            end_sec=min(duration, key_time + 0.8),
            color=self.GREEN,
            thickness=6,
        ))

        # Clip title (first 2 seconds)
        if title:
            annotations.append(TextAnnotation(
                start_sec=0, end_sec=2.5,
                x=w // 2 - 200, y=60,
                text=title[:50],
                color=self.WHITE,
                bg_color=(13, 13, 46),
                font_scale=0.7,
            ))

        # Damage / quality info at key moment
        verdict = analysis.get("overall_verdict", "")
        if verdict in ("Clean", "Great Play", "Good Play"):
            annotations.append(TextAnnotation(
                start_sec=max(0, key_time - 0.2),
                end_sec=min(duration, key_time + 1.5),
                x=10, y=h - 50,
                text=verdict.upper(),
                color=self.GREEN,
                bg_color=(10, 40, 10),
                font_scale=0.65,
            ))

        # Watermark
        annotations.append(TextAnnotation(
            start_sec=0, end_sec=duration,
            x=w - 200, y=h - 20,
            text="@Hidarikikinoaku | coached by Aria",
            color=(180, 180, 180),
            bg_color=(0, 0, 0),
            font_scale=0.36,
        ))

        return annotations

    def _render(self, clip_path: str, annotations: list, mode: str) -> str:
        """
        Render all annotations onto the video.
        Returns path to the output file.
        """
        if not CV2_AVAILABLE:
            logger.error("OpenCV required for video annotation")
            return clip_path

        cap = cv2.VideoCapture(clip_path)
        if not cap.isOpened():
            logger.error(f"Cannot open: {clip_path}")
            return clip_path

        fps    = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        stem   = Path(clip_path).stem
        out_path = self.output_dir / f"{stem}_{mode}_annotated.mp4"

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(out_path), fourcc, fps, (width, height))

        frame_num = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            current_sec = frame_num / fps

            # Apply all active annotations for this timestamp
            for ann in annotations:
                if ann.start_sec <= current_sec <= ann.end_sec:
                    frame = self._draw_annotation(
                        frame, ann, current_sec, fps, width, height
                    )

            writer.write(frame)
            frame_num += 1

            if frame_num % 300 == 0:
                pct = round(frame_num / total * 100)
                logger.debug(f"Annotating: {pct}%")

        cap.release()
        writer.release()
        logger.info(f"Annotated clip saved: {out_path}")
        return str(out_path)

    def _draw_annotation(
        self, frame, ann, current_sec: float,
        fps: float, w: int, h: int
    ):
        """Draw a single annotation onto a frame."""

        if ann.annotation_type == "circle":
            # Pulsing circle effect
            pulse = 0.85 + 0.15 * math.sin(current_sec * 6)
            r = int(ann.radius * pulse)
            cv2.circle(frame, (ann.x, ann.y), r, ann.color, ann.thickness)
            cv2.circle(frame, (ann.x, ann.y), r - 10,
                       (*ann.color[:2], min(255, ann.color[2] + 60)), 1)
            if ann.label:
                cv2.putText(frame, ann.label,
                            (ann.x - 40, ann.y - r - 10),
                            self.FONT, 0.5, ann.color, 2)

        elif ann.annotation_type == "arrow":
            cv2.arrowedLine(frame,
                            (ann.x1, ann.y1), (ann.x2, ann.y2),
                            ann.color, ann.thickness,
                            tipLength=0.25)
            if ann.label:
                mid_x = (ann.x1 + ann.x2) // 2
                mid_y = (ann.y1 + ann.y2) // 2
                cv2.putText(frame, ann.label, (mid_x, mid_y - 8),
                            self.FONT, 0.45, ann.color, 1)

        elif ann.annotation_type == "text":
            self._draw_text_box(frame, ann.text, ann.x, ann.y,
                                ann.color, ann.bg_color, ann.font_scale)

        elif ann.annotation_type == "highlight_box":
            # Pulsing border around entire frame
            alpha = 0.5 + 0.5 * abs(math.sin(current_sec * 4))
            thickness = max(4, int(ann.thickness * alpha))
            cv2.rectangle(frame, (0, 0), (w - 1, h - 1),
                          ann.color, thickness)

        elif ann.annotation_type == "controller":
            frame = self._draw_controller_state(
                frame, ann, current_sec, w, h
            )

        return frame

    def _draw_text_box(
        self, frame, text: str, x: int, y: int,
        color: tuple, bg_color: tuple, scale: float
    ):
        """Draw text with a semi-transparent background box."""
        (tw, th), baseline = cv2.getTextSize(text, self.FONT, scale, 1)
        pad = 6

        # Background box
        overlay = frame.copy()
        cv2.rectangle(overlay,
                      (x - pad, y - th - pad),
                      (x + tw + pad, y + baseline + pad),
                      bg_color, -1)
        cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

        # Text
        cv2.putText(frame, text, (x, y), self.FONT, scale, color, 1,
                    cv2.LINE_AA)

    def _draw_controller_state(
        self, frame, ann: ControllerOverlay,
        current_sec: float, w: int, h: int
    ):
        """
        Draw a controller diagram showing current input state.
        Shows exactly what Hidarikikinoaku's hands were doing.
        """
        # Find the input state closest to current_sec
        state = self._get_input_at_time(ann.input_timeline, current_sec)
        if not state:
            return frame

        # Controller panel position — bottom right
        panel_w, panel_h = 180, 110
        px = w - panel_w - 10
        py = h - panel_h - 10

        # Draw semi-transparent background
        overlay = frame.copy()
        cv2.rectangle(overlay, (px, py), (px + panel_w, py + panel_h),
                      (20, 20, 50), -1)
        cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)
        cv2.rectangle(frame, (px, py), (px + panel_w, py + panel_h),
                      (100, 100, 180), 1)

        # Title
        cv2.putText(frame, "INPUTS", (px + 5, py + 14),
                    self.FONT_SMALL, 0.38, (180, 180, 220), 1)

        # Left stick (movement)
        lx = px + 30; ly = py + 50
        cv2.circle(frame, (lx, ly), 22, (80, 80, 100), 1)   # dead zone ring
        cv2.circle(frame, (lx, ly), 24, (60, 60, 80), 1)    # outer ring
        stick_x = lx + int(state.get("left_x", 0) * 20)
        stick_y = ly + int(state.get("left_y", 0) * 20)
        moving = state.get("is_moving", False)
        stick_color = self.GREEN if moving else (100, 100, 100)
        cv2.circle(frame, (stick_x, stick_y), 6, stick_color, -1)
        cv2.putText(frame, "L", (lx - 4, ly + 35),
                    self.FONT_SMALL, 0.32, (150, 150, 180), 1)

        # Right stick (aim)
        rx = px + 100; ry = py + 50
        cv2.circle(frame, (rx, ry), 22, (80, 80, 100), 1)
        cv2.circle(frame, (rx, ry), 24, (60, 60, 80), 1)
        rstick_x = rx + int(state.get("right_x", 0) * 20)
        rstick_y = ry + int(state.get("right_y", 0) * 20)
        cv2.circle(frame, (rstick_x, rstick_y), 6, self.BLUE, -1)
        cv2.putText(frame, "R", (rx - 4, ry + 35),
                    self.FONT_SMALL, 0.32, (150, 150, 180), 1)

        # Left trigger (ADS)
        lt_val = state.get("left_trigger", 0)
        lt_h = int(lt_val * 20)
        lt_color = self.YELLOW if lt_val > 0.1 else (60, 60, 80)
        cv2.rectangle(frame, (px + 5, py + 30), (px + 13, py + 50),
                      (60, 60, 80), -1)
        if lt_h > 0:
            cv2.rectangle(frame, (px + 5, py + 50 - lt_h),
                          (px + 13, py + 50), lt_color, -1)
        cv2.putText(frame, "ADS", (px + 2, py + 60),
                    self.FONT_SMALL, 0.28, (150, 150, 180), 1)

        # Right trigger (fire)
        rt_val = state.get("right_trigger", 0)
        rt_h = int(rt_val * 20)
        rt_color = self.RED if rt_val > 0.1 else (60, 60, 80)
        cv2.rectangle(frame, (px + panel_w - 13, py + 30),
                      (px + panel_w - 5, py + 50), (60, 60, 80), -1)
        if rt_h > 0:
            cv2.rectangle(frame, (px + panel_w - 13, py + 50 - rt_h),
                          (px + panel_w - 5, py + 50), rt_color, -1)
        cv2.putText(frame, "FIRE", (px + panel_w - 18, py + 60),
                    self.FONT_SMALL, 0.28, (150, 150, 180), 1)

        # Movement warning — if stationary while aiming, flash red label
        if state.get("is_aiming", False) and not state.get("is_moving", False):
            cv2.putText(frame, "STATIONARY!", (px + 5, py + 90),
                        self.FONT_SMALL, 0.42, self.RED, 1)

        return frame

    def _get_input_at_time(self, timeline: list, sec: float) -> dict:
        """Find the input state closest to the given timestamp."""
        if not timeline:
            return {}
        best = None
        best_diff = float("inf")
        for entry in timeline:
            t = entry.get("t", 0)
            diff = abs(t - sec)
            if diff < best_diff:
                best_diff = diff
                best = entry.get("state", {})
        return best or {}

    @staticmethod
    def _wrap_text(text: str, width: int) -> list[str]:
        """Wrap text to fit within a character width."""
        words = text.split()
        lines = []
        current = ""
        for word in words:
            if len(current) + len(word) + 1 <= width:
                current += (" " if current else "") + word
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def create_comparison_clip(
        self,
        mistake_clip: str,
        good_example_text: str,
        output_path: str = None
    ) -> str:
        """
        Create a side-by-side or split comparison showing
        what went wrong vs what should have happened.
        Used for Aria's coaching breakdowns.
        """
        if not CV2_AVAILABLE:
            return mistake_clip

        cap = cv2.VideoCapture(mistake_clip)
        fps    = cap.get(cv2.CAP_PROP_FPS) or 30
        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if output_path is None:
            stem = Path(mistake_clip).stem
            output_path = str(self.output_dir / f"{stem}_breakdown.mp4")

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        frame_num = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            sec = frame_num / fps

            # In the last 4 seconds, fade in the "what to do instead" panel
            if sec > (total / fps) - 4.0:
                overlay = frame.copy()
                cv2.rectangle(overlay, (0, height - 120),
                              (width, height), (10, 10, 40), -1)
                cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)

                lines = VideoAnnotator._wrap_text(
                    f"INSTEAD: {good_example_text}", 60
                )
                for i, line in enumerate(lines[:3]):
                    cv2.putText(frame, line,
                                (10, height - 90 + i * 26),
                                cv2.FONT_HERSHEY_DUPLEX, 0.5,
                                (80, 220, 80), 1, cv2.LINE_AA)

            writer.write(frame)
            frame_num += 1

        cap.release()
        writer.release()
        return output_path


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not CV2_AVAILABLE:
        print("pip install opencv-python")
        exit(1)

    # Test with a sample analysis
    test_analysis = {
        "event_type":         "knocked_by_enemy",
        "overall_verdict":    "Positional Error",
        "fight_quality":      4,
        "key_moment":         "You stopped moving while ADS at 0:06. "
                              "Left stick went dead for 2 seconds. "
                              "You were a stationary target.",
        "key_moment_time":    6.0,
        "positioning_score":  4,
        "movement_score":     3,
        "aim_score":          6,
        "primary_fix":        "Keep left stick active while aiming",
    }

    # Fake input timeline for testing
    test_inputs = [
        {"t": i * 0.1, "state": {
            "left_x": 0.0 if 5.5 < i * 0.1 < 7.5 else 0.4,
            "left_y": 0.0,
            "right_x": 0.3,
            "right_y": 0.1,
            "left_trigger": 0.9 if i * 0.1 > 5.0 else 0.0,
            "right_trigger": 0.8 if i * 0.1 > 5.5 else 0.0,
            "is_moving": not (5.5 < i * 0.1 < 7.5),
            "is_aiming": i * 0.1 > 5.0,
            "is_firing": i * 0.1 > 5.5,
        }}
        for i in range(200)
    ]

    annotator = VideoAnnotator()
    print("VideoAnnotator ready.")
    print("Pass a clip path to annotate_mistake() or annotate_highlight()")
    print("Example:")
    print("  out = annotator.annotate_mistake('path/to/clip.mp4', analysis, inputs)")
