"""
ARIA — Core Package
====================
Core components:
  - apex_live_api      WebSocket listener for Apex Live API events
  - killfeed_detector  OCR-based kill feed fallback
  - controller_logger  GameSir G7 Pro input logging
  - system_detector    Hardware detection and capability profiling

Player: Hidarikikinoaku (LeftHandDevil)
Coach:  Aria (@migikonokami / RightHandGod)
"""

from .apex_live_api import ApexLiveAPI
from .killfeed_detector import KillFeedDetector
from .controller_logger import ControllerLogger
from .system_detector import SystemProfile, load_profile, print_profile

__all__ = [
    "ApexLiveAPI",
    "KillFeedDetector",
    "ControllerLogger",
    "SystemProfile",
    "load_profile",
    "print_profile",
]
