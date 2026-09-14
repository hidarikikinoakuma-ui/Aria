@echo off
:: ============================================================
:: ARIA — Setup Script for Windows
:: Run this ONCE to install everything
:: Player: Hidarikikinoaku
:: ============================================================

echo.
echo ╔══════════════════════════════════════════════╗
echo ║         ARIA SETUP — INSTALLING              ║
echo ║         Apex Legends AI Coach                ║
echo ╚══════════════════════════════════════════════╝
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found.
    echo Download Python 3.11 from: https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during install
    pause
    exit /b 1
)

echo [OK] Python found
python --version

:: Check pip
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] pip not found. Reinstall Python.
    pause
    exit /b 1
)

:: Create virtual environment
echo.
echo [1/6] Creating virtual environment...
python -m venv venv
call venv\Scripts\activate.bat

:: Upgrade pip
echo.
echo [2/6] Upgrading pip...
python -m pip install --upgrade pip --quiet

:: Install core dependencies
echo.
echo [3/6] Installing core dependencies...
echo (This may take 5-10 minutes on first run)
echo.
pip install numpy opencv-python Pillow mss psutil easyocr requests aiohttp loguru pydantic schedule rich python-dotenv --quiet
echo [OK] Core dependencies installed

:: Install PyQt5 for overlay
echo.
echo [4/6] Installing desktop overlay (PyQt5)...
pip install PyQt5 PyQt5-sip --quiet
echo [OK] Desktop overlay ready

:: Install AI and API dependencies
echo.
echo [5/6] Installing AI dependencies...
pip install openai anthropic fastapi uvicorn websockets SQLAlchemy aiosqlite --quiet
echo [OK] AI dependencies installed

:: Install video processing
echo.
echo [6/6] Installing video processing...
pip install ffmpeg-python moviepy imageio imageio-ffmpeg --quiet
echo [OK] Video processing ready

:: Install controller input
pip install inputs pygame --quiet
echo [OK] Controller input ready

:: Install OBS WebSocket
pip install obsws-python --quiet
echo [OK] OBS WebSocket ready

:: Install YouTube API
pip install google-api-python-client google-auth google-auth-oauthlib --quiet
echo [OK] YouTube API ready

:: Optional - TTS (Aria's voice)
echo.
echo Installing Aria's voice (Coqui TTS)...
echo This is optional but recommended. It takes a few minutes.
pip install TTS --quiet
echo [OK] Voice installed

:: Create required directories
echo.
echo Creating folder structure...
mkdir data\clips 2>nul
mkdir data\sessions 2>nul
mkdir data\reports 2>nul
mkdir data\youtube 2>nul
mkdir data\annotated 2>nul
mkdir data\mobile_cache 2>nul
mkdir assets\sprites\idle 2>nul
mkdir assets\sprites\talking 2>nul
mkdir assets\sprites\pointing 2>nul
mkdir assets\sprites\proud 2>nul
mkdir assets\sprites\concerned 2>nul
mkdir assets\sprites\thinking 2>nul
mkdir logs 2>nul
mkdir config 2>nul

echo [OK] Folders created

:: Check for config
if not exist config\aria.conf (
    echo.
    echo [WARNING] config\aria.conf not found
    echo Copy it from the project files and add your OpenAI API key
)

echo.
echo ╔══════════════════════════════════════════════╗
echo ║              SETUP COMPLETE                  ║
echo ╠══════════════════════════════════════════════╣
echo ║                                              ║
echo ║  BEFORE STARTING:                            ║
echo ║  1. Open config\aria.conf                    ║
echo ║  2. Add your OpenAI API key                  ║
echo ║     (platform.openai.com/api-keys)           ║
echo ║  3. Open OBS and enable WebSocket Server     ║
echo ║     (Tools -> WebSocket Server Settings)     ║
echo ║  4. Connect your GameSir G7 Pro via USB      ║
echo ║                                              ║
echo ║  TO START ARIA:                              ║
echo ║  Double-click start_aria.bat                 ║
echo ║  OR run: python main.py                      ║
echo ║                                              ║
echo ╚══════════════════════════════════════════════╝
echo.
pause
