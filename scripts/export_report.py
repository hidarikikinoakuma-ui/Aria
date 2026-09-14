#!/usr/bin/env python3
"""
ARIA — Export Report
======================
Exports coaching reports from any session to a readable format.
Supports JSON (raw), plain text, and Markdown.

Usage:
    python scripts/export_report.py                     # export latest session
    python scripts/export_report.py --session 20240901_142233
    python scripts/export_report.py --all               # export all sessions
    python scripts/export_report.py --format md         # Markdown output
    python scripts/export_report.py --format txt        # plain text
    python scripts/export_report.py --format json       # raw JSON (default)
    python scripts/export_report.py --out ~/Desktop/    # output directory

Player: Hidarikikinoaku (LeftHandDevil)
Coach:  Aria (@migikonokami / RightHandGod)
"""

import sys
import os
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

ARIA_DIR = Path(__file__).parent.parent
os.chdir(ARIA_DIR)

# ── CLI args ──────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Export ARIA coaching reports")
parser.add_argument("--session", help="Session ID to export (e.g. 20240901_142233)")
parser.add_argument("--all",     action="store_true", help="Export all sessions")
parser.add_argument("--format",  choices=["json", "txt", "md"], default="txt",
                    help="Output format (default: txt)")
parser.add_argument("--out",     default=None, help="Output directory (default: data/exports/)")
parser.add_argument("--list",    action="store_true", help="List available sessions and exit")
args = parser.parse_args()

REPORTS_DIR = ARIA_DIR / "data" / "reports"
SESSIONS_DIR = ARIA_DIR / "data" / "sessions"
EXPORT_DIR  = Path(args.out) if args.out else ARIA_DIR / "data" / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
def find_sessions() -> list[Path]:
    """Find all session report files."""
    reports: list[Path] = []
    for d in [REPORTS_DIR, SESSIONS_DIR]:
        if d.exists():
            reports.extend(d.glob("**/*.json"))
    # Sort by modification time, newest first
    reports.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return reports


def load_report(path: Path) -> dict:
    """Load a JSON report file."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e), "path": str(path)}


# ─────────────────────────────────────────────────────────────────────────────
#  Formatters
# ─────────────────────────────────────────────────────────────────────────────
def format_json(data: dict) -> str:
    return json.dumps(data, indent=2, default=str)


def format_txt(data: dict, session_id: str = "") -> str:
    lines = []
    lines.append("=" * 60)
    lines.append(f"  ARIA COACHING REPORT")
    lines.append(f"  Session: {session_id or data.get('session_id', 'unknown')}")
    ts = data.get("ended_at") or data.get("started_at") or ""
    if ts:
        lines.append(f"  Date:    {ts[:19].replace('T', ' ')}")
    lines.append("=" * 60)

    # Player summary
    player = data.get("player", {}) or {}
    if player:
        lines.append("")
        lines.append(f"  Player:  {player.get('username', 'Hidarikikinoaku')}")
        lines.append(f"  Rank:    {player.get('rank', '?')}  ({player.get('rp', '?')} RP)")

    # Match summary
    summary = data.get("summary", {}) or {}
    if summary:
        lines.append("")
        lines.append("  ── Match Summary ──────────────────────────────────────")
        kills  = summary.get("kills", "?")
        deaths = summary.get("deaths", "?")
        damage = summary.get("damage_dealt", "?")
        result = summary.get("match_result", "?")
        lines.append(f"  Result:  {result}")
        lines.append(f"  K/D:     {kills} kills / {deaths} deaths")
        lines.append(f"  Damage:  {damage}")

    # Coaching feedback
    analyses = data.get("analyses", []) or []
    if analyses:
        lines.append("")
        lines.append(f"  ── Fight Analysis ({len(analyses)} clips) ─────────────────────")
        for i, analysis in enumerate(analyses, 1):
            lines.append("")
            lines.append(f"  [{i}] {analysis.get('event_type', 'fight').upper()}")
            verdict = analysis.get("verdict", "")
            if verdict:
                lines.append(f"  Verdict: {verdict}")
            mistakes = analysis.get("mistakes", [])
            for m in mistakes:
                lines.append(f"  ✗  {m}")
            positives = analysis.get("positives", [])
            for p in positives:
                lines.append(f"  ✓  {p}")
            advice = analysis.get("advice", "")
            if advice:
                lines.append(f"  → {advice}")

    # Habit tracking
    habits = data.get("habit_report", {}) or {}
    if habits:
        lines.append("")
        lines.append("  ── Habit Tracking ─────────────────────────────────────")
        for habit, value in habits.items():
            lines.append(f"  {habit}: {value}")

    # Aria's overall message
    message = data.get("aria_message", "") or data.get("coaching_message", "")
    if message:
        lines.append("")
        lines.append("  ── Aria's Message ─────────────────────────────────────")
        # Word-wrap at 56 chars
        words = message.split()
        line = ""
        for word in words:
            if len(line) + len(word) + 1 > 56:
                lines.append(f"  {line}")
                line = word
            else:
                line = f"{line} {word}".strip()
        if line:
            lines.append(f"  {line}")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


def format_md(data: dict, session_id: str = "") -> str:
    ts = data.get("ended_at") or data.get("started_at") or ""
    date_str = ts[:19].replace("T", " ") if ts else "Unknown date"

    lines = []
    lines.append(f"# ARIA Coaching Report")
    lines.append(f"**Session:** {session_id or data.get('session_id', 'unknown')}  ")
    lines.append(f"**Date:** {date_str}")
    lines.append("")

    player = data.get("player", {}) or {}
    if player:
        lines.append("## Player")
        lines.append(f"- **Username:** {player.get('username', 'Hidarikikinoaku')}")
        lines.append(f"- **Rank:** {player.get('rank', '?')} ({player.get('rp', '?')} RP)")
        lines.append("")

    summary = data.get("summary", {}) or {}
    if summary:
        lines.append("## Match Summary")
        lines.append(f"- **Result:** {summary.get('match_result', '?')}")
        lines.append(f"- **Kills:** {summary.get('kills', '?')}")
        lines.append(f"- **Deaths:** {summary.get('deaths', '?')}")
        lines.append(f"- **Damage:** {summary.get('damage_dealt', '?')}")
        lines.append("")

    analyses = data.get("analyses", []) or []
    if analyses:
        lines.append(f"## Fight Analysis ({len(analyses)} clips)")
        for i, analysis in enumerate(analyses, 1):
            event = analysis.get("event_type", "fight").title()
            lines.append(f"\n### {i}. {event}")
            verdict = analysis.get("verdict", "")
            if verdict:
                lines.append(f"> {verdict}")
                lines.append("")
            mistakes = analysis.get("mistakes", [])
            if mistakes:
                lines.append("**Mistakes:**")
                for m in mistakes:
                    lines.append(f"- {m}")
            positives = analysis.get("positives", [])
            if positives:
                lines.append("")
                lines.append("**Positives:**")
                for p in positives:
                    lines.append(f"- {p}")
            advice = analysis.get("advice", "")
            if advice:
                lines.append("")
                lines.append(f"**Fix:** {advice}")
        lines.append("")

    message = data.get("aria_message", "") or data.get("coaching_message", "")
    if message:
        lines.append("## Aria's Message")
        lines.append(f"> {message}")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by ARIA — Apex Legends AI Coach*  ")
    lines.append("*Player: Hidarikikinoaku | Coach: Aria (@migikonokami)*")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────
all_sessions = find_sessions()

if args.list:
    print()
    print("  Available sessions:")
    print()
    if not all_sessions:
        print("  (none — play a match first)")
    for p in all_sessions:
        print(f"  {p.stem:<30}  {p.parent.name}")
    print()
    sys.exit(0)

# Select which sessions to export
if args.all:
    to_export = all_sessions
elif args.session:
    to_export = [p for p in all_sessions if args.session in p.stem]
    if not to_export:
        print(f"  ❌ No session found matching: {args.session}")
        print(f"     Run with --list to see available sessions.")
        sys.exit(1)
else:
    # Latest session
    if not all_sessions:
        print("  ❌ No session reports found.")
        print("     Play a match first, then run this script.")
        sys.exit(1)
    to_export = [all_sessions[0]]

# Export
exported: list[Path] = []
for report_path in to_export:
    data      = load_report(report_path)
    session_id = report_path.stem
    ext        = {"json": ".json", "txt": ".txt", "md": ".md"}[args.format]
    out_name   = f"aria_report_{session_id}{ext}"
    out_path   = EXPORT_DIR / out_name

    if args.format == "json":
        content = format_json(data)
    elif args.format == "md":
        content = format_md(data, session_id)
    else:
        content = format_txt(data, session_id)

    out_path.write_text(content, encoding="utf-8")
    exported.append(out_path)

print()
print("╔══════════════════════════════════════════════════════╗")
print("║              ARIA — Export Report                   ║")
print("╚══════════════════════════════════════════════════════╝")
print()
print(f"  Exported {len(exported)} report(s) → {EXPORT_DIR}/")
print()
for p in exported:
    print(f"  ✅  {p.name}")
print()
