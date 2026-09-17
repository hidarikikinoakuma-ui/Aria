# Aria Docker Stack

Two containers + Ollama on your Windows host.

```
aria-backend   → Coaching API + mobile companion   (port 8765)
aria-tts       → Coqui XTTS v2 voice server        (port 5002)
Ollama         → Qwen2.5-VL 7B  (runs on Windows, NOT in Docker)
```

## How the AI switching works

Aria watches for `r5apex_dx12.exe` every 15 seconds:

| State | AI used | Why |
|---|---|---|
| Apex running | Cloud NIM API | GPU stays free → no frame drops |
| Apex closed | Local Ollama (Qwen2.5-VL 7B) | Full 16 GB VRAM, fast, free |

Check which is active at any time: `http://localhost:8765/api/nim-status`

## Setup

### Step 1 — Install Ollama (one time)

```powershell
winget install Ollama.Ollama
```

Then pull the model (downloads ~4.5 GB):

```powershell
ollama pull qwen2.5vl:7b
```

Verify it works:

```powershell
ollama run qwen2.5vl:7b "hello"
```

### Step 2 — Install NVIDIA Container Toolkit (one time, for GPU in Docker)

Only needed so the `tts` container can use your GPU for faster voice synthesis.
Without it, TTS still works — just slower (~3s per response instead of <1s).

[Install guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)

### Step 3 — Configure and start

```powershell
# From the Aria folder
copy .env.example .env
notepad .env    # paste your NIM_API_KEY (from build.nvidia.com)

docker compose up -d --build
```

First build takes 5-10 min (downloads XTTS v2 model into the image).

### Step 4 — Check everything is up

```powershell
docker compose ps          # both should say "healthy"

# Test voice server
curl http://localhost:5002/health

# Test backend + see which AI is active
curl http://localhost:8765/api/nim-status
```

## Accessing Aria on your phone

1. Find your PC's local IP: open PowerShell → `ipconfig` → look for IPv4 under your network adapter
2. On your phone, open: `http://<your-PC-IP>:8765`

## Custom voice for Aria

Drop a 6-30 second WAV recording into `./assets/aria_voice_ref.wav` before starting.
XTTS clones it automatically — Aria sounds like whoever you recorded.

## Updating Aria code

```powershell
git pull
docker compose up -d --build aria   # rebuild just the backend
```

## Updating the Ollama model

```powershell
ollama pull qwen2.5vl:7b    # re-pulls if a newer version is available
```

## What still runs on Windows (outside Docker)

These need your gaming PC directly:

- **OBS** — replay buffer control
- **Game overlay** — Aria's avatar window (PyQt5)
- **Controller input** — GameSir G7 Pro HID reading
- **Screen capture** — `mss` during game

Run `py ARIA_ALL_IN_ONE.py` on Windows as normal for those.
The Docker stack handles AI, voice, and mobile app.

## Troubleshooting

**Ollama not reachable from Docker:**
Make sure Ollama is running (`ollama serve` or it auto-starts as a service after install).
Docker reaches it at `host.docker.internal:11434` — this works automatically on Docker Desktop for Windows.

**TTS container slow:**
GPU not being used. Check NVIDIA Container Toolkit is installed and Docker Desktop has GPU support enabled (Settings → Resources → GPU).

**Cloud NIM being used even when Apex is closed:**
`psutil` inside the container can't see Windows host processes unless you share the host PID namespace.
This is a known limitation — add `pid: host` to the `aria` service in `docker-compose.yml` to fix it (Linux only).
On Windows Docker Desktop, the router defaults to cloud when it can't read the process list — set `FORCE_LOCAL=true` in `.env` to always use Ollama.
