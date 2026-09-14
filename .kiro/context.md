# ARIA — Project Context for Kiro

This file gives Kiro full context so you never have to repeat yourself.
Load this when starting a new session on any machine.

---

## The Player

- **In-game name:** Hidarikikinoaku
- **Handle:** LeftHandDevil
- **Current rank:** Gold 4
- **Goal:** Predator
- **Legend:** Alter (main)
- **Controller:** GameSir G7 Pro 8K (Hall Effect sticks)
- **Platform:** PC, Steam, Windows

---

## The Coach — Aria

- **Name:** Aria
- **Social handle:** @migikonokami ("RightHandGod")
- **Personality:** Firm like Erza Scarlet, loyal like Rem. High standards, no sugarcoating.
- **Design:** Auburn hair, steel blue eyes, red/silver/blue tactical armor. Asuna elegance + Erza armor + Rem blue accents.
- **Voice:** Coqui TTS (local, private)

---

## What Was Built

Everything lives in one file: `ARIA_ALL_IN_ONE.py`

### What it does:
1. **Auto-installs** all Python packages on first run
2. **Installs OBS** automatically if not found
3. **Launches OBS** with replay buffer (90s) ready
4. **Writes liveapi.json** into Apex folder so Live API works
5. **Creates LAUNCH_APEX.bat** — always use this to start Apex
6. **Apex Live API listener** — WebSocket, no OCR, instant kill/death events
7. **OCR kill feed fallback** — EasyOCR if Live API fails
8. **GameSir G7 Pro logger** — logs every input, live button display in terminal
9. **OBS clip manager** — auto-saves clips on knocks/kills/deaths (20s before + 8s after)
10. **GPT-4o fight analysis** — extracts frames, sends to Vision API, returns coaching JSON
11. **Video annotator** — burns mistake circles, text, arrows onto MP4 clips
12. **Mobile companion API** — FastAPI PWA, chat with Aria, review clips on phone
13. **Desktop overlay** — PyQt5 transparent overlay, Aria's animated sprite, appears after every match
14. **YouTube manager** — weekly auto-compile, generates title/description/thumbnail, uploads Sunday 20:00
15. **Cosplay mode** — when a clip scores 9+/10, Aria channels the legend's persona (Alter, Wraith, etc.)
16. **Social manager** — posts to Twitter/X and Reddit as @migikonokami after matches and uploads

---

## Repo

- **GitHub:** `https://github.com/hidarikikinoakuma-ui/Aria`
- **Branch:** `main`
- **Main file:** `ARIA_ALL_IN_ONE.py` (3029 lines, everything in one file)
- **Original modules:** still in subfolders (`core/`, `analysis/`, `clips/`, etc.)

---

## How to Run

```bash
# Add your OpenAI API key at the top of ARIA_ALL_IN_ONE.py first
python ARIA_ALL_IN_ONE.py
```

Then launch Apex using `LAUNCH_APEX.bat` (Aria creates this on first run).

---

## Settings Location

Open `ARIA_ALL_IN_ONE.py` and find the SETTINGS block near line 25:

```python
OPENAI_API_KEY  = "sk-..."   # required
OBS_PASSWORD    = ""          # only if OBS WebSocket has a password
MOBILE_PORT     = 8765
```

All other settings are in `config/aria.conf` (auto-created on first run).

---

## One-Time Setup Steps (already done in CloudShell, needed on new PC)

1. Install Python 3.11+ — python.org/downloads — check "Add to PATH"
2. Paste OpenAI API key into ARIA_ALL_IN_ONE.py SETTINGS block
3. Run `python ARIA_ALL_IN_ONE.py` once — installs everything automatically
4. In OBS: Tools → WebSocket Server Settings → Enable WebSocket Server → Apply
5. In OBS: Tools → Replay Buffer → set to 90 seconds → Start
6. Always launch Apex via `LAUNCH_APEX.bat`

---

## Key Design Decisions (so Kiro doesn't second-guess them)

- **One file philosophy:** The user wants everything in `ARIA_ALL_IN_ONE.py`. Do not split into modules unless asked.
- **No OCR during gameplay:** Live API is primary. OCR is only a fallback.
- **Zero performance impact during matches:** All processing happens AFTER the match ends.
- **Cosplay mode:** When overall_score >= 9.0, Aria channels the legend's persona in YouTube script + tweets. This is intentional and wanted.
- **Post to social as Aria:** All social posts go out as @migikonokami, not as Hidarikikinoaku.
- **Weekly YouTube:** Auto-compiles and uploads every Sunday at 20:00. Uses MoviePy + ffmpeg.
- **Mobile as PWA:** No app store. Phone opens the FastAPI server URL and installs as PWA.

---

## Things Still To Do (potential future tasks)

- Add Aria's actual sprite art (currently draws a placeholder in code)
- Set up YouTube OAuth credentials (`config/youtube_credentials.json`)
- Set up Twitter/X API keys in SETTINGS
- Set up Reddit API keys in SETTINGS
- Mobile PWA frontend (`mobile/static/index.html`) — basic HTML exists, could be improved
- Cloudflare tunnel setup for remote mobile access (`scripts/cloudflare_tunnel.py`)

---

## Files in This Repo

```
ARIA_ALL_IN_ONE.py     ← THE main file. Run this.
main.py                ← Original system controller (still works)
ARIA_START.py          ← Original one-button launcher (still works)
README.md              ← Full install instructions
requirements.txt       ← Full dependency list
config/aria.conf       ← All runtime settings
core/                  ← Original modules (apex_live_api, killfeed_detector, etc.)
analysis/              ← fight_analysis_engine, video_annotator
clips/                 ← obs_clip_manager
overlay/               ← aria_overlay (PyQt5)
mobile/                ← mobile_api (FastAPI)
youtube/               ← youtube_manager
social/                ← social_manager
scripts/               ← health_check, reset_session, export_report, cloudflare_tunnel
data/                  ← clips, sessions, reports (gitignored, created at runtime)
logs/                  ← aria.log (gitignored, created at runtime)
assets/                ← sprites, sounds, templates
```

---

## How to Continue in Kiro on Your Local PC

1. Clone the repo: `git clone https://github.com/hidarikikinoakuma-ui/Aria.git`
2. Open Kiro CLI inside the folder: `cd Aria && kiro`
3. Kiro will read this file automatically and have full context
4. Just tell it what you want — no need to re-explain the project

---

*Last updated from AWS CloudShell session — September 14, 2026*
