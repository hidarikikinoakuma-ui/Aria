"""
ARIA — Analysis Package
========================
AI-powered fight analysis using GPT-4o Vision.

  - fight_analysis_engine  Frame extraction + GPT-4o coaching analysis
  - video_annotator         Burns coaching graphics onto clip MP4s

Player: Hidarikikinoaku (LeftHandDevil)
Coach:  Aria (@migikonokami / RightHandGod)
"""

from .fight_analysis_engine import FightAnalysisEngine, FightAnalysis
from .video_annotator import VideoAnnotator

__all__ = [
    "FightAnalysisEngine",
    "FightAnalysis",
    "VideoAnnotator",
]
