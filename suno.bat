@echo off
rem Runs Bokin Suno with its own Python: suno login ten, suno download ten link ...
chcp 65001 >nul
"%~dp0.venv\Scripts\python.exe" "%~dp0suno\bokin_suno.py" %*
exit /b %errorlevel%
