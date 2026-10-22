@echo off
rem Runs Bokin Up Video with its own Python: upvideo login ten-kenh, upvideo run lich.csv ...
chcp 65001 >nul
"%~dp0.venv\Scripts\python.exe" "%~dp0upvideo\bokin_upvideo.py" %*
exit /b %errorlevel%
