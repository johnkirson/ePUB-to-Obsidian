@echo off
REM Build a standalone Windows .exe of the app into dist\ePUB-to-Obsidian.exe
REM Requires: pip install pyinstaller
cd /d "%~dp0"
python -m PyInstaller --noconfirm ePUB-to-Obsidian.spec
echo.
echo Done. The app is at dist\ePUB-to-Obsidian.exe
pause
