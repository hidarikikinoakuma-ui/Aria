# ARIA — Apex Legends AI Coach

> **Player:** Hidarikikinoaku (LeftHandDevil)  
> **Coach:** Aria (@migikonokami / RightHandGod)  
> **Goal:** Gold 4 → Predator

Aria is a personal AI coaching system for Apex Legends. She watches every match through Apex's native Live API, saves clips of key moments via OBS, analyzes each fight using GPT-4o Vision, and delivers a full coaching breakdown after every match — on your desktop and on your phone.

---

## What Aria Does

| Feature | How it works |
|---|---|
| **Live event detection** | Connects to Apex's native WebSocket API — no OCR, no screen capture during gameplay |
| **Auto clip saving** | Triggers OBS replay buffer on kills, deaths, knocks — 20s before + 8s after each event |
| **GPT-4o fight analysis** | Extracts key frames from each clip, sends to GPT-4o Vision for coaching feedback |
| **Annotated clips** | Burns mistake circles, arrows, and text directly onto MP4s |
| **Desktop overlay** | Animated sprite overlay appears after every match with Aria's coaching |
| **Voice feedback** | Coqui TTS reads Aria's coaching out loud (local, private) |
| **Mobile companion** | FastAPI PWA — chat with Aria and review clips from your phone |
| **Controller logging** | Logs every GameSir G7 Pro input, overlays them on clips |
| **YouTube channel** | Auto-compiles weekly highlights, generates titles/descriptions, uploads every Sunday |
| **Social media** | Posts as @migikonokami on Twitter/X, TikTok, Instagram, Reddit |

---

## Quick Start (Windows)

### 1. Prerequisites

- Windows 10/11 (64-bit)
- Python 3.11+ — [python.org/downloads](https://python.org/downloads)
- OBS Studio — Aria installs it automatically if not found
- Apex Legends installed via Steam

### 2. Get your OpenAI API key

Go to [platform.openai.com/api-keys](https://platform.openai.com/api-keys) and create a key.

### 3. Configure Aria

Open `ARIA_START.py` in any text editor. Fill in the settings at the top:

```python
OPENAI_API_KEY = "sk-..."    # Required — paste your key here
OBS_PASSWORD   = ""          # Only if you set a password in OBS WebSocket
MOBILE_PORT    = 8765        # Port your phone connects to
```

Everything else is auto-detected.

### 4. Launch

Double-click **`ARIA_START.bat`** — that's it.

Aria will:
1. Install all missing Python packages automatically
2. Install OBS if not found
3. Launch OBS with the replay buffer active
4. Write `liveapi.json` into your Apex folder
5. Create `LAUNCH_APEX.bat` for you

Then double-click **`LAUNCH_APEX.bat`** to start Apex with Live API enabled.

Aria appears automatically after your first match.

---

## First Session Checklist

- [ ] Set `OPENAI_API_KEY` in `ARIA_START.py`
- [ ] Run `ARIA_START.bat` once
- [ ] In OBS: `Tools → WebSocket Server Settings → Enable WebSocket Server → Apply`
- [ ] Use `LAUNCH_APEX.bat` every time to start Apex (enables Live API)
- [ ] After a match, Aria's overlay appears automatically

---

## Mobile Companion

Your phone shows Aria's coaching, annotated clips, and lets you chat with her between matches.

**On your home network:**
1. Start Aria (ARIA_START.bat)
2. Note the URL in the startup banner: `http://192.168.x.x:8765`
3. Open that URL on your phone's browser
4. Tap "Add to Home Screen" to install it as a PWA

**From anywhere (Cloudflare Tunnel):**
```bash
python scripts/cloudflare_tunnel.py --install  # install cloudflared once
python scripts/cloudflare_tunnel.py            # start tunnel, get public URL
python scripts/cloudflare_tunnel.py --qr       # show QR code for phone
```

---

## Project Structure

```
aria/
├── ARIA_START.py          # One-button launcher — run this
├── ARIA_START.bat         # Windows shortcut to launch
├── main.py                # Core system controller (AriaSystem)
├── requirements.txt       # Full dependency list
├── config/
│   └── aria.conf          # All settings (rank, API keys, ports, etc.)
├── core/
│   ├── apex_live_api.py   # WebSocket listener for Apex Live API
│   ├── killfeed_detector.py  # OCR fallback kill feed detection
│   ├── controller_logger.py  # GameSir G7 Pro input logging
│   └── system_detector.py    # Hardware detection
├── analysis/
│   ├── fight_analysis_engine.py  # GPT-4o Vision fight analysis
│   └── video_annotator.py        # Burns annotations onto clips
├── clips/
│   └── obs_clip_manager.py  # OBS WebSocket clip management
├── overlay/
│   └── aria_overlay.py      # PyQt5 transparent desktop overlay
├── mobile/
│   ├── mobile_api.py        # FastAPI mobile backend
│   └── static/
│       ├── index.html       # PWA frontend
│       └── manifest.json    # PWA install manifest
├── social/
│   └── social_manager.py    # Twitter/X, Reddit, TikTok, Instagram
├── youtube/
│   └── youtube_manager.py   # Weekly highlight compilation + upload
├── scripts/
│   ├── health_check.py      # Verify all components are working
│   ├── reset_session.py     # Clear session state after crash
│   ├── export_report.py     # Export coaching reports to txt/md/json
│   ├── cloudflare_tunnel.py # Remote mobile access via Cloudflare
│   └── setup.sh             # Linux / CloudShell dev environment setup
├── data/
│   ├── clips/               # Raw OBS clips (organized by session)
│   ├── sessions/            # Session archives
│   ├── reports/             # Coaching reports (JSON)
│   └── exports/             # Exported reports (txt, md)
├── assets/
│   ├── sprites/             # Aria's animated sprite frames
│   ├── sounds/              # Voice lines cache
│   └── templates/           # YouTube thumbnail templates
└── logs/
    └── aria.log             # System log
```

---

## Utility Scripts

Run these from the `aria/` directory:

```bash
# Check everything is working before a session
python scripts/health_check.py

# Reset session state after a crash or weird state
python scripts/reset_session.py
python scripts/reset_session.py --force   # skip confirmation
python scripts/reset_session.py --full    # also rotate logs

# Export coaching reports
python scripts/export_report.py           # latest session as .txt
python scripts/export_report.py --list    # list all sessions
python scripts/export_report.py --all --format md  # all sessions as Markdown
python scripts/export_report.py --session 20240901_142233  # specific session

# Cloudflare tunnel for remote mobile access
python scripts/cloudflare_tunnel.py --install  # install cloudflared (once)
python scripts/cloudflare_tunnel.py            # start tunnel
python scripts/cloudflare_tunnel.py --qr       # show QR code for phone

# Linux / CloudShell dev environment setup
bash scripts/setup.sh
```

---

## Configuration Reference

All settings live in `config/aria.conf`. Key sections:

### `[player]`
| Key | Description |
|---|---|
| `username` | Your in-game EA username (exact spelling) |
| `current_rank` | e.g. `Gold 4` |
| `current_rp` | Current RP number |

### `[analysis]`
| Key | Description |
|---|---|
| `openai_api_key` | GPT-4o key (or set via `OPENAI_API_KEY` env var) |
| `vision_model` | Default: `gpt-4o` |
| `max_clips_per_match` | How many clips to analyze per match (default: 10) |

### `[recording]`
| Key | Description |
|---|---|
| `obs_host` | OBS host (default: `localhost`) |
| `obs_port` | OBS WebSocket port (default: `4455`) |
| `replay_buffer_seconds` | Replay buffer length (default: 90) |
| `clip_before_event` | Seconds before event in clip (default: 20) |
| `clip_after_event` | Seconds after event in clip (default: 8) |

### `[mobile]`
| Key | Description |
|---|---|
| `port` | Mobile companion port (default: `8765`) |

### `[social]`
Fill in API keys for the platforms you want to use. All are optional.

---

## YouTube Setup

1. Create a Google Cloud project at [console.cloud.google.com](https://console.cloud.google.com)
2. Enable the YouTube Data API v3
3. Create OAuth 2.0 credentials, download `client_secrets.json`
4. Place `client_secrets.json` in the `aria/` root directory
5. On first run, Aria will open a browser for you to authorize the channel

Aria uploads every Sunday at 20:00 automatically.

---

## Social Media Setup

Fill in credentials in `config/aria.conf` under `[social]`:

- **Twitter/X:** Create an app at [developer.x.com](https://developer.x.com)
- **Reddit:** Create an app at [reddit.com/prefs/apps](https://reddit.com/prefs/apps)
- **TikTok:** Use `tiktok_session_id` (from browser cookies — see TikTokUploader docs)
- **Instagram:** Username + password (uses instagrapi)

All social posting is optional. Aria posts as @migikonokami.

---

## Troubleshooting

**Aria can't find kills / events**
- Make sure you launched Apex using `LAUNCH_APEX.bat` (enables Live API)
- Check `logs/aria.log` for WebSocket connection errors
- Verify `liveapi.json` exists in your Apex folder

**OBS not connecting**
- Open OBS → `Tools → WebSocket Server Settings → Enable WebSocket Server`
- Default port: 4455, no password needed unless you set one
- Enable the Replay Buffer: `Tools → Replay Buffer`

**No clips being saved**
- OBS Replay Buffer must be active (green light in OBS)
- Check `data/clips/` — clips are organized by session date

**Mobile app not loading**
- Make sure ARIA_START.py is running (mobile server starts automatically)
- Use the IP shown in Aria's startup banner
- For remote access, run `scripts/cloudflare_tunnel.py`

**Overlay not appearing**
- PyQt5 required: `pip install PyQt5`
- On Linux, Aria runs without overlay (headless mode)

**Run health check for full diagnosis:**
```bash
python scripts/health_check.py
```

---

## Development (Linux / CloudShell)

The full system runs on Windows, but you can edit and test from Linux:

```bash
bash scripts/setup.sh       # install deps, verify imports
python scripts/health_check.py  # check what works on Linux
```

Modules with Windows-only dependencies (PyQt5 overlay, `inputs` controller, winsound) gracefully degrade — they detect the platform and skip themselves rather than crashing.

---

## Privacy

Everything runs locally:
- OBS clips stay on your PC
- GPT-4o Vision sends clip frames to OpenAI's API only for analysis
- No telemetry, no cloud sync, no data leaves your machine except OpenAI API calls and social posts you explicitly configure

---

## Legend Notes — Alter

Aria's coaching is tuned for **Alter (Skirmisher)**:
- Use **Void Passage** to reposition mid-fight, not just to escape
- Stop peeking the same angle twice in a row
- Void Passage cooldown tracking is built into the analysis prompt

---

*ARIA — Road to Predator. Not maybe. Not eventually.*
