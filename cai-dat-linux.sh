#!/usr/bin/env bash
# Sets up Bokin Up Video on Linux (Ubuntu/Debian): Python packages in .venv, Google Chrome, a virtual screen (xvfb),
# a self-test.
set -euo pipefail
cd "$(dirname "$0")"
SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"
if ! python3 -c 'import sys, ensurepip; assert sys.version_info >= (3, 10)' 2>/dev/null; then
  $SUDO apt-get update
  $SUDO apt-get install -y python3 python3-venv
fi
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install -r requirements.txt
if ! command -v google-chrome >/dev/null 2>&1; then
  echo "Đang cài Google Chrome..."
  $SUDO .venv/bin/python -m patchright install --with-deps chrome
fi
if ! command -v xvfb-run >/dev/null 2>&1; then
  $SUDO apt-get update
  $SUDO apt-get install -y xvfb
fi
chmod +x upvideo.sh
.venv/bin/python upvideo/bokin_upvideo.py selftest
echo
echo "Xong. Bước tiếp theo: vào VPS bằng Remote Desktop rồi chạy ./upvideo.sh login <tên-kênh> (xem README)"
