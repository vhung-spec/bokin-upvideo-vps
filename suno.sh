#!/usr/bin/env bash
# Runs Bokin Suno with its own Python. Without a screen (an SSH session) Chrome gets a virtual one (xvfb-run);
# 'login' needs a real screen (Remote Desktop) because a person signs in.
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$DIR/.venv/bin/python"
LOGIN=""
for a in "$@"; do [ "$a" = "login" ] && LOGIN=1; done
if [ -z "${DISPLAY:-}" ] && [ -z "$LOGIN" ] && command -v xvfb-run >/dev/null 2>&1; then
  exec xvfb-run -a -s "-screen 0 1366x900x24" "$PY" "$DIR/suno/bokin_suno.py" "$@"
fi
exec "$PY" "$DIR/suno/bokin_suno.py" "$@"
