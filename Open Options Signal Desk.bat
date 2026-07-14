@echo off
cd /d "%~dp0"
start "Options Signal Keep Alive" powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0keep_app_alive.ps1"
timeout /t 3 > nul
start "" "http://localhost:8502/"
