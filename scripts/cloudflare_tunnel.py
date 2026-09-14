#!/usr/bin/env python3
"""
ARIA — Cloudflare Tunnel Helper
==================================
Exposes the mobile companion server to the internet via Cloudflare Tunnel.
This lets you chat with Aria and review clips from anywhere — not just home.

No port forwarding. No router config. Free with a Cloudflare account.

Usage:
    python scripts/cloudflare_tunnel.py              # start tunnel
    python scripts/cloudflare_tunnel.py --install    # install cloudflared CLI
    python scripts/cloudflare_tunnel.py --qr         # print QR code for phone

Requirements:
    cloudflared  (free — https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/)

Player: Hidarikikinoaku (LeftHandDevil)
Coach:  Aria (@migikonokami / RightHandGod)
"""

import sys
import os
import subprocess
import shutil
import argparse
import configparser
import threading
import time
from pathlib import Path

ARIA_DIR = Path(__file__).parent.parent
os.chdir(ARIA_DIR)

parser = argparse.ArgumentParser(description="Cloudflare Tunnel for ARIA mobile companion")
parser.add_argument("--install", action="store_true", help="Install cloudflared CLI")
parser.add_argument("--qr",      action="store_true", help="Print QR code for phone (requires qrcode package)")
parser.add_argument("--port",    type=int, default=None, help="Override mobile port from config")
args = parser.parse_args()

# ── Load port from config ─────────────────────────────────────────────────────
def get_mobile_port() -> int:
    if args.port:
        return args.port
    cfg = configparser.ConfigParser()
    cfg.read(ARIA_DIR / "config" / "aria.conf")
    return int(cfg.get("mobile", "port", fallback="8765"))

# ── Install cloudflared ───────────────────────────────────────────────────────
def install_cloudflared():
    print()
    print("  Installing cloudflared...")
    print()

    if sys.platform == "win32":
        url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
        dest = ARIA_DIR / "cloudflared.exe"
        print(f"  Downloading cloudflared from: {url}")
        try:
            import urllib.request
            urllib.request.urlretrieve(url, dest)
            print(f"  ✅ Saved to {dest}")
            print(f"     Add this folder to PATH, or run from aria/ directory.")
        except Exception as e:
            print(f"  ❌ Download failed: {e}")
            print("     Get it manually: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/")

    elif sys.platform == "darwin":
        print("  On macOS, install via Homebrew:")
        print("    brew install cloudflare/cloudflare/cloudflared")

    else:
        # Linux
        print("  On Linux, install via:")
        print()
        print("    # Debian / Ubuntu:")
        print("    curl -L https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null")
        print("    echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared jammy main' | sudo tee /etc/apt/sources.list.d/cloudflared.list")
        print("    sudo apt-get update && sudo apt-get install cloudflared")
        print()
        print("    # Or direct download:")
        print("    wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64")
        print("    chmod +x cloudflared-linux-amd64")
        print("    sudo mv cloudflared-linux-amd64 /usr/local/bin/cloudflared")

    sys.exit(0)


# ── Print QR code ─────────────────────────────────────────────────────────────
def print_qr(url: str):
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
        print(f"  Scan to open ARIA on your phone: {url}")
    except ImportError:
        print(f"  📱 Open this on your phone: {url}")
        print("     (Install qrcode for a QR code: pip install qrcode)")


# ── Find cloudflared ──────────────────────────────────────────────────────────
def find_cloudflared() -> str | None:
    # Check PATH first
    found = shutil.which("cloudflared")
    if found:
        return found
    # Check local aria/ directory
    for name in ["cloudflared", "cloudflared.exe"]:
        local = ARIA_DIR / name
        if local.exists():
            return str(local)
    return None


# ── Main ──────────────────────────────────────────────────────────────────────
if args.install:
    install_cloudflared()

print()
print("╔══════════════════════════════════════════════════════╗")
print("║          ARIA — Cloudflare Tunnel                   ║")
print("╚══════════════════════════════════════════════════════╝")
print()

cf = find_cloudflared()
if not cf:
    print("  ❌ cloudflared not found.")
    print()
    print("  Install it with:")
    print("    python scripts/cloudflare_tunnel.py --install")
    print()
    print("  Or get it from:")
    print("    https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/")
    sys.exit(1)

port = get_mobile_port()
print(f"  cloudflared: {cf}")
print(f"  Tunneling:   http://localhost:{port} → internet")
print()
print("  Starting tunnel... (Ctrl+C to stop)")
print()

# ── Capture the tunnel URL from cloudflared output ───────────────────────────
tunnel_url = None
url_event  = threading.Event()

def _read_output(proc):
    global tunnel_url
    for line in proc.stderr:
        line = line.strip()
        if "trycloudflare.com" in line or ".cloudflare.com" in line:
            # Extract the URL from the log line
            parts = line.split()
            for part in parts:
                if part.startswith("https://"):
                    tunnel_url = part
                    url_event.set()
                    break
        if line:
            print(f"  [cloudflared] {line}")

try:
    proc = subprocess.Popen(
        [cf, "tunnel", "--url", f"http://localhost:{port}"],
        stderr=subprocess.PIPE,
        text=True,
    )

    # Read output in background thread
    t = threading.Thread(target=_read_output, args=(proc,), daemon=True)
    t.start()

    # Wait up to 15 seconds for URL to appear
    url_event.wait(timeout=15)

    if tunnel_url:
        print()
        print("  ╔═══════════════════════════════════════════════════╗")
        print(f"  ║  🌐  {tunnel_url:<45}║")
        print("  ╚═══════════════════════════════════════════════════╝")
        print()
        print("  Open that URL on your phone to access ARIA.")
        print("  This link works from anywhere — home, ranked queue, anywhere.")
        print()
        if args.qr:
            print_qr(tunnel_url)

        # Save URL to a file so other scripts can pick it up
        url_file = ARIA_DIR / "data" / "tunnel_url.txt"
        url_file.parent.mkdir(parents=True, exist_ok=True)
        url_file.write_text(tunnel_url)

    else:
        print()
        print("  ⚠️  Could not detect tunnel URL automatically.")
        print("     Check the cloudflared output above for your URL.")

    # Keep running until Ctrl+C
    proc.wait()

except KeyboardInterrupt:
    print()
    print("  Tunnel stopped.")
    if tunnel_url:
        # Clear saved URL
        url_file = ARIA_DIR / "data" / "tunnel_url.txt"
        if url_file.exists():
            url_file.unlink()
    sys.exit(0)
except Exception as e:
    print(f"  ❌ Failed to start tunnel: {e}")
    sys.exit(1)
