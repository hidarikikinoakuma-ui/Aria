#!/usr/bin/env python3
"""
ARIA — Reset Session
======================
Clears the current in-progress session data so the next match starts fresh.
Does NOT delete clips or reports — only clears the active session state.

Use this if Aria got confused about match state, or after a crash.

Usage:
    python scripts/reset_session.py           # interactive prompt
    python scripts/reset_session.py --force   # skip confirmation

Player: Hidarikikinoaku (LeftHandDevil)
Coach:  Aria (@migikonokami / RightHandGod)
"""

import sys
import os
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime

ARIA_DIR = Path(__file__).parent.parent
os.chdir(ARIA_DIR)

# ── CLI args ──────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Reset ARIA session state")
parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")
parser.add_argument("--full",  action="store_true", help="Also clear logs (keeps clips and reports)")
args = parser.parse_args()

# ── What gets cleared ─────────────────────────────────────────────────────────
SESSION_STATE_FILES = [
    "data/current_session.json",
    "data/session_state.json",
    "data/aria_voice.wav",
]

SESSION_STATE_DIRS = [
    # Only the currently-active OBS session folder (identified by a .active marker)
]

LOG_FILES = [
    "logs/aria.log",
]

print()
print("╔══════════════════════════════════════════════════════╗")
print("║               ARIA — Reset Session                  ║")
print("╚══════════════════════════════════════════════════════╝")
print()
print("  This will clear:")
print("  ✦ Active session state (data/current_session.json)")
print("  ✦ Any .active session markers")
if args.full:
    print("  ✦ Log files (logs/aria.log)")
print()
print("  This will NOT delete:")
print("  ✦ Saved clips (data/clips/)")
print("  ✦ Analysis reports (data/reports/)")
print("  ✦ Session archives (data/sessions/)")
print("  ✦ Your config (config/aria.conf)")
print()

if not args.force:
    answer = input("  Proceed? [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        print("  Cancelled.")
        sys.exit(0)

cleared: list[str] = []
skipped: list[str] = []

# ── Clear session state files ──────────────────────────────────────────────────
for file_path in SESSION_STATE_FILES:
    p = ARIA_DIR / file_path
    if p.exists():
        try:
            p.unlink()
            cleared.append(str(p.relative_to(ARIA_DIR)))
        except Exception as e:
            print(f"  ⚠️  Could not delete {p.name}: {e}")
    else:
        skipped.append(str(p.relative_to(ARIA_DIR)))

# ── Clear .active markers left by sessions ────────────────────────────────────
sessions_dir = ARIA_DIR / "data" / "sessions"
if sessions_dir.exists():
    for marker in sessions_dir.glob("**/*.active"):
        try:
            marker.unlink()
            cleared.append(str(marker.relative_to(ARIA_DIR)))
        except Exception as e:
            print(f"  ⚠️  Could not delete {marker.name}: {e}")

# ── Optionally clear logs ─────────────────────────────────────────────────────
if args.full:
    for file_path in LOG_FILES:
        p = ARIA_DIR / file_path
        if p.exists():
            try:
                # Rotate rather than delete — keeps last 100 lines as archive
                lines = p.read_text(errors="replace").splitlines()
                archive = ARIA_DIR / "logs" / f"aria_pre_reset_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                archive.write_text("\n".join(lines[-100:]) + "\n")
                p.write_text("")
                cleared.append(str(p.relative_to(ARIA_DIR)))
                print(f"  📦 Archived last 100 lines → {archive.name}")
            except Exception as e:
                print(f"  ⚠️  Could not clear {p.name}: {e}")

# ── Write a fresh empty session state ─────────────────────────────────────────
fresh_state = {
    "session_id": None,
    "started_at": None,
    "events": [],
    "clips": [],
    "status": "idle",
    "reset_at": datetime.now().isoformat(),
    "reset_by": "scripts/reset_session.py",
}
state_path = ARIA_DIR / "data" / "current_session.json"
state_path.parent.mkdir(parents=True, exist_ok=True)
state_path.write_text(json.dumps(fresh_state, indent=2))
cleared.append("data/current_session.json (reset to idle)")

# ── Summary ───────────────────────────────────────────────────────────────────
print()
if cleared:
    print("  Cleared:")
    for item in cleared:
        print(f"    ✅  {item}")
if skipped:
    print()
    print("  Already clean (nothing to clear):")
    for item in skipped[:5]:
        print(f"    ⬛  {item}")
    if len(skipped) > 5:
        print(f"    ⬛  ... and {len(skipped) - 5} more")

print()
print("  ✅ Session reset complete.")
print("     Aria is ready for a fresh session.")
print("     Launch ARIA_START.py to begin.")
print()
