#!/usr/bin/env bash
# ============================================================
#  ARIA — Linux / AWS CloudShell Setup
# ============================================================
#  Sets up the development environment so you can edit and
#  test ARIA from Linux or AWS CloudShell.
#
#  NOTE: Aria is designed to RUN on Windows (for OBS, PyQt5,
#  GameSir controller). This script sets up the dev/test
#  environment on Linux for editing and partial testing.
#
#  Usage:
#    chmod +x scripts/setup.sh
#    ./scripts/setup.sh
#
#  Player: Hidarikikinoaku (LeftHandDevil)
#  Coach:  Aria (@migikonokami / RightHandGod)
# ============================================================

set -e  # exit on error

ARIA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ARIA_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

ok()   { echo -e "  ${GREEN}✅${NC}  $1"; }
warn() { echo -e "  ${YELLOW}⚠️ ${NC}  $1"; }
fail() { echo -e "  ${RED}❌${NC}  $1"; }
info() { echo -e "  ℹ️   $1"; }

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║           ARIA — Linux / CloudShell Setup           ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Python version check ──────────────────────────────────────────────────────
echo "── Checking Python ─────────────────────────────────────"
PYTHON=$(command -v python3 || command -v python || true)
if [ -z "$PYTHON" ]; then
    fail "Python not found. Install Python 3.10+."
    exit 1
fi

PYVER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYMAJ=$("$PYTHON" -c "import sys; print(sys.version_info.major)")
PYMIN=$("$PYTHON" -c "import sys; print(sys.version_info.minor)")

if [ "$PYMAJ" -lt 3 ] || ([ "$PYMAJ" -eq 3 ] && [ "$PYMIN" -lt 10 ]); then
    fail "Python 3.10+ required, found $PYVER"
    info "On Ubuntu/Debian: sudo apt install python3.11"
    info "On Amazon Linux:  sudo dnf install python3.11"
    exit 1
fi
ok "Python $PYVER"

# ── pip ───────────────────────────────────────────────────────────────────────
echo ""
echo "── Checking pip ────────────────────────────────────────"
if ! "$PYTHON" -m pip --version &>/dev/null; then
    warn "pip not found — attempting install..."
    curl -sS https://bootstrap.pypa.io/get-pip.py | "$PYTHON"
fi
PIP_VER=$("$PYTHON" -m pip --version | awk '{print $2}')
ok "pip $PIP_VER"

# ── Create data directories ───────────────────────────────────────────────────
echo ""
echo "── Creating directories ────────────────────────────────"
for DIR in \
    data/clips \
    data/sessions \
    data/reports \
    data/exports \
    data/youtube \
    data/annotated \
    assets/sprites \
    assets/sounds \
    assets/templates \
    logs; do
    mkdir -p "$ARIA_DIR/$DIR"
done
ok "All directories created"

# ── Install Linux-compatible packages (core subset) ──────────────────────────
echo ""
echo "── Installing core Python packages ────────────────────"
info "Installing packages that work on Linux (full list in requirements.txt)"
info "Windows-only packages (PyQt5, inputs, winsound) are skipped here."
echo ""

LINUX_PACKAGES=(
    "loguru==0.7.2"
    "openai==1.30.1"
    "opencv-python==4.9.0.80"
    "Pillow==10.3.0"
    "numpy==1.26.4"
    "psutil==5.9.8"
    "fastapi==0.111.0"
    "uvicorn==0.29.0"
    "websockets==12.0"
    "mss==9.0.1"
    "requests==2.32.2"
    "aiohttp==3.9.5"
    "schedule==1.2.1"
    "rich==13.7.1"
    "pydantic==2.7.1"
    "python-dotenv==1.0.1"
    "tweepy==4.14.0"
    "praw==7.7.1"
    "moviepy==1.0.3"
    "ffmpeg-python==0.2.0"
    "SQLAlchemy==2.0.30"
    "aiosqlite==0.20.0"
)

FAILED_PKGS=()
for PKG in "${LINUX_PACKAGES[@]}"; do
    PKG_NAME="${PKG%%==*}"
    printf "  Installing %-35s" "$PKG ..."
    if "$PYTHON" -m pip install "$PKG" --quiet 2>/dev/null; then
        echo -e "${GREEN}✅${NC}"
    else
        echo -e "${YELLOW}⚠️ ${NC}"
        FAILED_PKGS+=("$PKG")
    fi
done

if [ ${#FAILED_PKGS[@]} -gt 0 ]; then
    echo ""
    warn "Some packages failed to install:"
    for P in "${FAILED_PKGS[@]}"; do
        info "  $P"
    done
    info "These may have system library dependencies. Check README.md for details."
fi

# ── Verify key imports ────────────────────────────────────────────────────────
echo ""
echo "── Verifying imports ───────────────────────────────────"
"$PYTHON" - <<'EOF'
import importlib, sys
OK = []; FAIL = []
for pkg in ["loguru","openai","cv2","numpy","fastapi","uvicorn","websockets","PIL","psutil","rich","requests"]:
    try:
        importlib.import_module(pkg)
        OK.append(pkg)
    except ImportError:
        FAIL.append(pkg)
print(f"  OK: {', '.join(OK)}")
if FAIL:
    print(f"  Missing: {', '.join(FAIL)}")
    sys.exit(1)
EOF
ok "Core imports verified"

# ── Git setup ─────────────────────────────────────────────────────────────────
echo ""
echo "── Git status ──────────────────────────────────────────"
if command -v git &>/dev/null; then
    if [ -d "$ARIA_DIR/.git" ]; then
        BRANCH=$(git -C "$ARIA_DIR" branch --show-current 2>/dev/null || echo "unknown")
        ok "Git repo on branch: $BRANCH"
        REMOTE=$(git -C "$ARIA_DIR" remote get-url origin 2>/dev/null || echo "none")
        if [ "$REMOTE" != "none" ]; then
            info "Remote: $REMOTE"
        else
            warn "No remote configured. See README.md to push to GitHub."
        fi
    else
        warn "Not a git repository. Run: git init && git remote add origin <your-repo>"
    fi
else
    warn "git not found. Install with: sudo apt install git"
fi

# ── Environment variable reminder ────────────────────────────────────────────
echo ""
echo "── Environment ─────────────────────────────────────────"
if [ -z "$OPENAI_API_KEY" ]; then
    warn "OPENAI_API_KEY not set in environment"
    info "Set it with: export OPENAI_API_KEY=sk-..."
    info "Or add it to config/aria.conf under [analysis]"
else
    ok "OPENAI_API_KEY is set"
fi

# ── Run health check ──────────────────────────────────────────────────────────
echo ""
echo "── Running health check ────────────────────────────────"
"$PYTHON" "$ARIA_DIR/scripts/health_check.py" 2>/dev/null || true

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║                  Setup Complete                      ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Dev environment ready. From here you can:"
echo ""
echo "  Edit code:       vim / nano / code (any editor)"
echo "  Syntax check:    python3 -m py_compile core/apex_live_api.py"
echo "  Health check:    python3 scripts/health_check.py"
echo "  Export report:   python3 scripts/export_report.py --list"
echo "  Reset session:   python3 scripts/reset_session.py"
echo ""
echo "  To run Aria (Windows required for OBS + overlay):"
echo "    Double-click ARIA_START.bat"
echo ""
echo "  To push to GitHub:"
echo "    git add . && git commit -m 'update' && git push"
echo ""
