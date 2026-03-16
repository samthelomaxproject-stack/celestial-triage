#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ "$(uname)" != "Darwin" ]]; then
  echo "This packaging script is for macOS only."
  exit 1
fi

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  if [[ -d ".venv312" ]]; then
    # shellcheck source=/dev/null
    source .venv312/bin/activate
  elif [[ -d ".venv" ]]; then
    # shellcheck source=/dev/null
    source .venv/bin/activate
  fi
fi

if ! python3 -c "import tkinter" >/dev/null 2>&1; then
  echo "tkinter/_tkinter is missing in current Python runtime."
  echo "Use a Tk-capable runtime first, e.g.:"
  echo "  brew install python@3.12 python-tk@3.12"
  echo "  python3.12 -m venv .venv312 && source .venv312/bin/activate"
  echo "  pip install -r requirements.txt"
  exit 1
fi

if ! python3 -c "import PyInstaller" >/dev/null 2>&1; then
  pip install pyinstaller
fi

APP_NAME="CelestialTriage"

pyinstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "$APP_NAME" \
  --paths src \
  src/celestial_triage/macapp/app_main.py

APP_PATH="dist/${APP_NAME}.app"
if [[ -d "$APP_PATH" ]]; then
  echo "Built app bundle: $APP_PATH"
else
  echo "Build did not produce expected app bundle: $APP_PATH"
  exit 1
fi
