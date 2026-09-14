"""
ARIA — Desktop Overlay App
===========================
Transparent desktop overlay showing Aria's animated sprite.
Appears after each match. Zero resource usage during gameplay.

Design: Asuna elegance + Erza strength + Rem loyalty
Colors: Auburn hair, steel blue eyes, red/silver/blue armor
Player: Hidarikikinoaku (LeftHandDevil)
Coach:  Aria (@migikonokami / RightHandGod)
"""

import sys
import os
import threading
from pathlib import Path
from loguru import logger

try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QLabel,
        QPushButton, QVBoxLayout, QHBoxLayout, QTextEdit, QFrame
    )
    from PyQt5.QtCore import (
        Qt, QTimer, QPropertyAnimation, QEasingCurve,
        QThread, pyqtSignal
    )
    from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QPen, QBrush
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False

try:
    from TTS.api import TTS
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

# ── Color palette ─────────────────────────────────────────────────────────────
C = {
    "red":    "#C0392B",   # Erza crimson
    "blue":   "#2E86AB",   # Rem blue
    "silver": "#BDC3C7",
    "panel":  "#1A1A2E",
    "text":   "#ECEFF1",
    "muted":  "#B0BEC5",
    "gold":   "#F39C12",
    "green":  "#27AE60",
    "danger": "#E74C3C",
}

IDLE = "idle"; TALKING = "talking"; POINTING = "pointing"
PROUD = "proud"; CONCERNED = "concerned"; THINKING = "thinking"


class VoiceThread(QThread):
    done = pyqtSignal()

    def __init__(self, text, engine):
        super().__init__()
        self.text = text
        self.engine = engine

    def run(self):
        try:
            if self.engine:
                path = "data/aria_voice.wav"
                os.makedirs("data", exist_ok=True)
                self.engine.tts_to_file(text=self.text, file_path=path)
                if sys.platform == "win32":
                    import winsound
                    winsound.PlaySound(path, winsound.SND_FILENAME)
                else:
                    os.system(f"aplay '{path}' 2>/dev/null")
        except Exception as e:
            logger.debug(f"Voice error: {e}")
        finally:
            self.done.emit()


class AriaSprite(QWidget):
    """
    Aria's animated sprite.
    Loads PNG frames from assets/sprites/{state}/*.png
    Draws a detailed placeholder until real art is generated.
    """

    def __init__(self, sprites_dir: Path, parent=None):
        super().__init__(parent)
        self.sprites_dir = sprites_dir
        self.state = IDLE
        self.frame = 0
        self.frames: dict = {}
        self.setFixedSize(260, 360)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._load()
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(83)  # 12 fps

    def _load(self):
        for state in [IDLE, TALKING, POINTING, PROUD, CONCERNED, THINKING]:
            d = self.sprites_dir / state
            frames = []
            if d.exists():
                for f in sorted(d.glob("*.png")):
                    px = QPixmap(str(f))
                    if not px.isNull():
                        frames.append(px.scaled(
                            260, 360, Qt.KeepAspectRatio,
                            Qt.SmoothTransformation
                        ))
            self.frames[state] = frames or [self._draw(state)]

    def _draw(self, state: str) -> QPixmap:
        """
        Drawn placeholder — Aria's actual design:
        Auburn hair, steel blue eyes, red/silver tactical armor.
        Asuna's elegance + Erza's armor + Rem's blue accents.
        """
        px = QPixmap(260, 360)
        px.fill(Qt.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing)

        # Armor body
        p.setBrush(QBrush(QColor(C["panel"])))
        p.setPen(QPen(QColor(C["blue"]), 2))
        p.drawRoundedRect(48, 112, 164, 222, 16, 16)

        # Red chest line (Erza)
        p.setBrush(QBrush(QColor(C["red"])))
        p.setPen(Qt.NoPen)
        p.drawRect(48, 148, 164, 7)
        p.drawRect(48, 200, 164, 4)

        # Silver shoulders
        p.setBrush(QBrush(QColor(C["silver"])))
        p.drawEllipse(22, 116, 42, 26)
        p.drawEllipse(196, 116, 42, 26)

        # Blue shoulder trim (Rem)
        p.setBrush(QBrush(QColor(C["blue"])))
        p.drawEllipse(26, 118, 18, 12)
        p.drawEllipse(216, 118, 18, 12)

        # Head — warm skin
        p.setBrush(QBrush(QColor("#F2C89B")))
        p.setPen(QPen(QColor("#D4A574"), 1))
        p.drawEllipse(88, 26, 84, 90)

        # Dark auburn hair base
        p.setBrush(QBrush(QColor("#6B2D0F")))
        p.setPen(Qt.NoPen)
        p.drawEllipse(84, 14, 92, 64)

        # Lighter auburn highlight
        p.setBrush(QBrush(QColor("#8B4513")))
        p.drawEllipse(90, 16, 80, 50)

        # Long flowing side strands (Asuna)
        p.setBrush(QBrush(QColor("#7B3B10")))
        p.drawRect(84, 50, 16, 96)
        p.drawRect(160, 50, 16, 96)
        p.drawRect(92, 90, 8, 56)

        # Top bun (Asuna signature)
        p.setBrush(QBrush(QColor("#9B5523")))
        p.drawEllipse(116, 8, 28, 22)

        # Steel blue eyes — key feature
        p.setBrush(QBrush(QColor(C["blue"])))
        p.setPen(Qt.NoPen)
        p.drawEllipse(102, 66, 20, 15)
        p.drawEllipse(138, 66, 20, 15)

        # Pupils
        p.setBrush(QBrush(QColor("#0A1F3A")))
        p.drawEllipse(108, 69, 9, 9)
        p.drawEllipse(144, 69, 9, 9)

        # Eye shine
        p.setBrush(QBrush(QColor("white")))
        p.drawEllipse(114, 70, 4, 4)
        p.drawEllipse(150, 70, 4, 4)

        # Eyelashes
        p.setPen(QPen(QColor("#2C1810"), 2))
        p.drawLine(102, 66, 98, 62)
        p.drawLine(122, 66, 126, 62)
        p.drawLine(138, 66, 134, 62)
        p.drawLine(158, 66, 162, 62)

        # Mouth varies by state
        p.setPen(QPen(QColor("#B87060"), 2))
        p.setBrush(Qt.NoBrush)
        if state == PROUD:
            p.drawArc(116, 92, 28, 16, 0, -180 * 16)
        elif state == CONCERNED:
            p.drawArc(116, 100, 28, 12, 0, 160 * 16)
        elif state == TALKING:
            p.setBrush(QBrush(QColor("#8B4040")))
            p.drawEllipse(122, 92, 16, 10)
        else:
            p.drawArc(118, 94, 24, 12, 0, -120 * 16)

        # Pointing arm
        if state == POINTING:
            p.setBrush(QBrush(QColor(C["panel"])))
            p.setPen(QPen(QColor(C["blue"]), 2))
            p.drawRoundedRect(210, 138, 42, 14, 6, 6)
            p.setBrush(QBrush(QColor("#F2C89B")))
            p.setPen(QPen(QColor("#D4A574"), 1))
            p.drawEllipse(246, 136, 14, 10)

        # Thinking hand
        if state == THINKING:
            p.setBrush(QBrush(QColor("#F2C89B")))
            p.setPen(QPen(QColor("#D4A574"), 1))
            p.drawEllipse(68, 96, 30, 22)

        # Name tag
        p.setPen(QPen(QColor(C["muted"])))
        p.setFont(QFont("Arial", 8))
        p.drawText(0, 344, 260, 14, Qt.AlignCenter, "Aria  ·  @migikonokami")

        p.end()
        return px

    def set_state(self, state: str):
        if state != self.state:
            self.state = state
            self.frame = 0

    def _tick(self):
        frames = self.frames.get(self.state, [])
        if frames:
            self.frame = (self.frame + 1) % len(frames)
            self.update()

    def paintEvent(self, event):
        frames = self.frames.get(self.state, [])
        if not frames:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.drawPixmap(0, 0, frames[self.frame % len(frames)])
        p.end()


class AriaOverlay(QMainWindow):
    """
    Main Aria overlay. Transparent, always on top, bottom-right.
    Silent during gameplay. Activates only after each match ends.
    """

    def __init__(self, config: dict = None):
        super().__init__()
        self.config = config or {}
        self.sprites_dir = Path(self.config.get("sprites_dir", "assets/sprites"))
        self.tts = None
        self._analyses = []
        self._vthread = None
        self._fade_ref = None
        self._tw_timer = None

        self._init_tts()
        self._build_ui()
        self._position()

    def _init_tts(self):
        if not TTS_AVAILABLE:
            return
        try:
            logger.info("Loading Aria voice...")
            self.tts = TTS(
                model_name="tts_models/en/ljspeech/tacotron2-DDC",
                progress_bar=False,
                gpu=self._gpu()
            )
            logger.info("Aria voice ready ✅")
        except Exception as e:
            logger.warning(f"TTS failed: {e}")

    def _gpu(self) -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def _build_ui(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        root = QWidget()
        root.setStyleSheet("background:transparent;")
        self.setCentralWidget(root)
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.sprite = AriaSprite(self.sprites_dir)
        row.addWidget(self.sprite, 0, Qt.AlignBottom)
        row.addWidget(self._panel())
        self.setFixedSize(660, 400)

    def _panel(self) -> QFrame:
        f = QFrame()
        f.setFixedSize(390, 390)
        f.setStyleSheet(f"""
            QFrame {{
                background:rgba(13,13,30,218);
                border:1px solid {C['blue']};
                border-radius:10px;
            }}
        """)
        v = QVBoxLayout(f)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(6)

        # Header
        h = QHBoxLayout()
        n = QLabel("ARIA")
        n.setStyleSheet(f"color:{C['red']};font-size:13px;font-weight:bold;"
                        f"font-family:'Segoe UI';letter-spacing:3px;")
        s = QLabel("@migikonokami")
        s.setStyleSheet(f"color:{C['blue']};font-size:9px;")
        self.lrank = QLabel("Gold IV → Predator")
        self.lrank.setStyleSheet(f"color:{C['gold']};font-size:9px;")
        h.addWidget(n); h.addWidget(s); h.addStretch(); h.addWidget(self.lrank)
        v.addLayout(h)

        div = QFrame(); div.setFrameShape(QFrame.HLine)
        div.setStyleSheet(f"color:{C['blue']};"); v.addWidget(div)

        self.lstats = QLabel("Analyzing your match...")
        self.lstats.setStyleSheet(f"color:{C['muted']};font-size:10px;")
        v.addWidget(self.lstats)

        self.txt = QTextEdit()
        self.txt.setReadOnly(True)
        self.txt.setStyleSheet(f"""
            QTextEdit {{
                background:transparent; color:{C['text']};
                font-size:11px; font-family:'Segoe UI',Arial; border:none;
            }}
            QScrollBar:vertical {{ width:3px; background:transparent; }}
            QScrollBar::handle:vertical {{ background:{C['blue']}; border-radius:1px; }}
        """)
        v.addWidget(self.txt)

        self.lfix = QLabel("")
        self.lfix.setWordWrap(True)
        self.lfix.setStyleSheet(f"""
            color:{C['text']}; background:rgba(192,57,43,35);
            border-left:3px solid {C['red']}; padding:5px 8px;
            font-size:10px; border-radius:3px;
        """)
        self.lfix.hide()
        v.addWidget(self.lfix)

        br = QHBoxLayout(); br.setSpacing(5)
        self.bmistake = self._btn("▶ Mistake Film", C["danger"])
        self.bhigh    = self._btn("⭐ Highlights",  C["green"])
        self.byt      = self._btn("📤 Post YouTube", C["blue"])
        self.bclose   = self._btn("✕", C["muted"], small=True)
        self.bmistake.clicked.connect(self._on_mistake)
        self.bhigh.clicked.connect(self._on_highlights)
        self.byt.clicked.connect(self._on_youtube)
        self.bclose.clicked.connect(self.hide_overlay)
        for b in [self.bmistake, self.bhigh, self.byt]:
            br.addWidget(b)
        br.addStretch(); br.addWidget(self.bclose)
        v.addLayout(br)
        return f

    def _btn(self, label, color, small=False):
        b = QPushButton(label)
        pad = "3px 6px" if small else "5px 10px"
        fsz = "9px"     if small else "10px"
        b.setStyleSheet(f"""
            QPushButton {{ background:rgba(255,255,255,10); color:{color};
                border:1px solid {color}; border-radius:5px;
                padding:{pad}; font-size:{fsz}; }}
            QPushButton:hover  {{ background:rgba(255,255,255,22); }}
            QPushButton:pressed {{ background:rgba(255,255,255,6); }}
        """)
        return b

    def _position(self):
        if not PYQT5_AVAILABLE:
            return
        s = QApplication.primaryScreen().geometry()
        self.move(s.width() - self.width() - 20,
                  s.height() - self.height() - 55)

    # ── Public API ────────────────────────────────────────────────────────────

    def show_intro(self, player_name: str = "Hidarikikinoaku",
                   player_handle: str = "LeftHandDevil"):
        """
        Show Aria's startup introduction.
        Called once when ARIA_START launches — she appears and introduces herself.
        """
        intro = (
            f"Hey. I'm Aria.\n\n"
            f"Your coach. Your analyst. Your second set of eyes.\n\n"
            f"I've reviewed your replays, {player_handle}. "
            f"You belong higher than Gold Four. "
            f"The gap between you and Predator is decisions — "
            f"positioning, when to peek, when to hold. That is what I fix.\n\n"
            f"Main Alter. Use Void Passage mid-fight to reposition — "
            f"stop peeking the same angle twice.\n\n"
            f"Launch Apex. I'll be watching every fight.\n\n"
            f"— Aria  ·  @migikonokami"
        )

        self.lstats.setText(
            f"{player_name}  ·  Gold 4  ·  Road to Predator  ·  Alter main"
        )
        self.lfix.setText("► Launch Apex via  LAUNCH_APEX.bat")
        self.lfix.show()
        self.sprite.set_state(TALKING)
        self.show()
        self._fade_in()
        self._typewrite(intro)
        self._speak(intro[:400])

    def show_post_match(self, session_summary: dict, coaching_report: str,
                        primary_fix: str = "", analyses: list = None):
        """Called every time a match ends. Shows Aria with full breakdown."""
        self._analyses = analyses or []
        k = session_summary.get("knock_count", 0)
        d = session_summary.get("death_count", 0)
        c = session_summary.get("total_clips",  0)
        self.lstats.setText(f"{k} knocks  •  {d} deaths  •  {c} clips saved")

        if primary_fix:
            self.lfix.setText(f"📌 Focus next session: {primary_fix}")
            self.lfix.show()
        else:
            self.lfix.hide()

        if d == 0 and k >= 3:
            self.sprite.set_state(PROUD)
        elif d >= 3:
            self.sprite.set_state(CONCERNED)
        else:
            self.sprite.set_state(TALKING)

        self.show()
        self._fade_in()
        self._typewrite(coaching_report)
        self._speak(coaching_report[:380])

    def _typewrite(self, text: str):
        self.txt.clear()
        self._tw_text = text
        self._tw_pos  = 0
        if self._tw_timer:
            self._tw_timer.stop()
        self._tw_timer = QTimer()
        self._tw_timer.timeout.connect(self._tw_tick)
        self._tw_timer.start(16)

    def _tw_tick(self):
        if self._tw_pos < len(self._tw_text):
            self.txt.setPlainText(
                self.txt.toPlainText() + self._tw_text[self._tw_pos]
            )
            self.txt.verticalScrollBar().setValue(
                self.txt.verticalScrollBar().maximum()
            )
            self._tw_pos += 1
        else:
            self._tw_timer.stop()

    def _speak(self, text: str):
        if not self.tts:
            return
        self.sprite.set_state(TALKING)
        self._vthread = VoiceThread(text, self.tts)
        self._vthread.done.connect(lambda: self.sprite.set_state(IDLE))
        self._vthread.start()

    def _fade_in(self):
        self.setWindowOpacity(0.0)
        a = QPropertyAnimation(self, b"windowOpacity")
        a.setDuration(500); a.setStartValue(0.0); a.setEndValue(0.93)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.start(); self._fade_ref = a

    def hide_overlay(self):
        a = QPropertyAnimation(self, b"windowOpacity")
        a.setDuration(350)
        a.setStartValue(self.windowOpacity()); a.setEndValue(0.0)
        a.setEasingCurve(QEasingCurve.InCubic)
        a.finished.connect(self.hide); a.start()
        self._fade_ref = a

    def _on_mistake(self):
        self.sprite.set_state(POINTING)
        for a in self._analyses:
            if a.get("event_type") in ("knocked_by_enemy", "killed_by_enemy"):
                path = a.get("clip_path", "")
                if path and os.path.exists(path):
                    os.startfile(path) if sys.platform == "win32" \
                        else os.system(f"xdg-open '{path}'")
                    break
        self._speak("Watch this. This is where it went wrong.")

    def _on_highlights(self):
        self.sprite.set_state(PROUD)
        for a in self._analyses:
            if a.get("event_type") in ("knock_by_you", "kill_by_you"):
                path = a.get("clip_path", "")
                if path:
                    folder = str(Path(path).parent)
                    os.startfile(folder) if sys.platform == "win32" \
                        else os.system(f"xdg-open '{folder}'")
                    break
        self._speak("These are your best plays. Study what you did right.")

    def _on_youtube(self):
        self._speak("Compiling your highlights. Ready for Sunday upload.")
        logger.info("YouTube post requested via overlay")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and hasattr(self, "_drag"):
            self.move(e.globalPos() - self._drag)


if __name__ == "__main__":
    if not PYQT5_AVAILABLE:
        print("pip install PyQt5")
        sys.exit(1)
    app = QApplication(sys.argv)
    overlay = AriaOverlay()
    overlay.show_post_match(
        session_summary={"knock_count": 3, "death_count": 2, "total_clips": 5},
        coaching_report=(
            "Alright. Film room.\n\n"
            "Three knocks tonight — that third one on Fragment was clean. "
            "You held the angle, pre-aimed the doorway, and punished him "
            "the second he pushed. That is what I have been asking for.\n\n"
            "Fight 2 — you stopped moving. Left stick dead for two seconds "
            "while ADS. Stationary target at Diamond is a dead target. "
            "Not an aim problem. A discipline problem.\n\n"
            "One focus next session: left stick stays active every fight. "
            "Move while you aim.\n\n"
            "607 RP from Gold 3. The gap is closing."
        ),
        primary_fix="Left stick active — move while you aim",
    )
    sys.exit(app.exec_())
