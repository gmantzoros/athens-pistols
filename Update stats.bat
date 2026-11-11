@echo off
rem Double-click to pull the latest games from basketaki.com and refresh the website data.
cd /d "%~dp0"
echo Updating Athens Pistols stats from basketaki.com ...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scrape_basketaki.ps1"
echo.
echo Finished. Open site\index.html (or refresh it) to see the new games.
pause
