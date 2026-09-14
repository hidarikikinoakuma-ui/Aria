@echo off
:: ============================================================
:: ARIA — Start Script
:: Run this every time you want to use Aria
:: ============================================================

cd /d "%~dp0"
call venv\Scripts\activate.bat
python main.py
pause
