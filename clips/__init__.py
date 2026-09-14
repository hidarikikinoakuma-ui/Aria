"""
ARIA — Clips Package
=====================
OBS integration for replay buffer clip management.

  - obs_clip_manager  Connects to OBS WebSocket, triggers clip saves,
                      organizes clips by session and event type.

Player: Hidarikikinoaku (LeftHandDevil)
Coach:  Aria (@migikonokami / RightHandGod)
"""

from .obs_clip_manager import OBSClipManager, GameEvent, EventType

__all__ = [
    "OBSClipManager",
    "GameEvent",
    "EventType",
]
