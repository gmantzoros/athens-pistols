@echo off
rem Double-click to pull the latest games from basketaki.com and refresh the website data.
cd /d "%~dp0"
echo Updating Athens Pistols stats from basketaki.com ...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scrape_basketaki.ps1"
echo.
echo Checking upcoming games and scouting ...
where python >nul 2>nul && python "%~dp0scrape_upcoming.py" || echo Python not found: upcoming games were not updated.
echo.
echo Checking game photos, reports and videos ...
where python >nul 2>nul && python "%~dp0scrape_media.py" || echo Photos were not updated (see the message above).
echo.
echo Finished. Open site\index.html (or refresh it) to see the new games.
pause
