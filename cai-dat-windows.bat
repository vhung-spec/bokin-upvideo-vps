@echo off
rem Sets up Bokin Up Video on Windows: Python packages in .venv, Google Chrome if missing, a self-test.
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && py -3 -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>nul && set "PY=python"
if not defined PY (
    echo Can Python 3.10 tro len: tai o https://www.python.org/downloads/ , khi cai nho tick "Add python.exe to PATH".
    goto :fail
)
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv || goto :fail
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail
set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=1"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=1"
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=1"
if not defined CHROME (
    echo Dang cai Google Chrome...
    ".venv\Scripts\python.exe" -m patchright install chrome || goto :fail
)
".venv\Scripts\python.exe" upvideo\bokin_upvideo.py selftest || goto :fail
echo.
echo Xong. Buoc tiep theo: upvideo login ten-kenh
if "%~1"=="" pause
exit /b 0
:fail
echo Cai dat KHONG thanh cong. Xem loi o tren.
if "%~1"=="" pause
exit /b 1
