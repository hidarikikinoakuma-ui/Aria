"""
ARIA — Mobile Package
======================
FastAPI backend + PWA frontend for the mobile companion app.

  - mobile_api  REST + WebSocket API that powers Aria on your phone.
                Chat with Aria. View annotated clips. Track session history.
                Accessible on local network or via Cloudflare Tunnel.

Static files (PWA frontend) are in mobile/static/:
  - index.html      Full React-style PWA — no app store needed
  - manifest.json   PWA install manifest for Add-to-Home-Screen

Player: Hidarikikinoaku (LeftHandDevil)
Coach:  Aria (@migikonokami / RightHandGod)
"""

from .mobile_api import MobileCompanionAPI

__all__ = [
    "MobileCompanionAPI",
]
