@echo off
title ARIA — Apex Legends AI Coach
color 0A

echo.
echo  ╔══════════════════════════════════════╗
echo  ║         ARIA — STARTING UP           ║
echo  ║     Hidarikikinoaku / LeftHandDevil  ║
echo  ╚══════════════════════════════════════╝
echo.

:: Move to the aria folder (same folder as this .bat file)
cd /d "%~dp0"

:: Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found.
    echo Download Python 3.11 from: https://www.python.org/downloads/
    echo Check "Add Python to PATH" during install.
    pause
    exit /b 1
)

:: Run the one-button launcher
python ARIA_START.py

pause
