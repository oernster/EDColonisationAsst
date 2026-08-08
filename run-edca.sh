#!/usr/bin/env bash
set -e

echo "Elite: Dangerous Colonisation Assistant"
echo "---------------------------------------"
echo "Developer helper script (Linux/macOS): runs backend + Vite dev server from source."
echo
echo "For packaged installs, prefer the Windows installer on Windows or the Flatpak build script on Linux."
echo

# Change to project root (directory of this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR"

# Find Python (prefer backend virtualenv if it exists)
PYTHON="python3"
if [ -x "backend/.venv/bin/python" ]; then
  PYTHON="backend/.venv/bin/python"
else
  if ! command -v python3 >/dev/null 2>&1; then
    if command -v python >/dev/null 2>&1; then
      PYTHON="python"
    else
      echo "Python 3 is required but was not found on PATH."
      echo "Please install Python 3.10+ and try again."
      exit 1
    fi
  fi
fi

# Ensure Node.js / npm are available
if ! command -v npm >/dev/null 2>&1; then
  echo "Node.js and npm are required but were not found on PATH."
  echo "Please install Node.js 18+ (https://nodejs.org/) and try again."
  exit 1
fi

echo
echo "Checking Python dependencies..."
"$PYTHON" -m pip install -r backend/requirements.txt >/dev/null
if [ $? -ne 0 ]; then
  echo
  echo "Failed to install Python dependencies."
  echo "Make sure pip is available for your Python installation."
  exit 1
fi

if [ ! -d "frontend/node_modules" ]; then
  echo
  echo "Installing frontend dependencies (this may take a few minutes)..."
  npm --prefix frontend install
fi

echo
echo "Starting backend (API server) on http://localhost:47021 ..."
# Run backend in the background
"$PYTHON" -m uvicorn backend.src.main:app --host 0.0.0.0 --port 47021 &
BACKEND_PID=$!

echo
echo "Starting frontend (web UI) on http://localhost:5173 ..."
echo "When you are finished, press Ctrl+C to stop the frontend."
echo "The backend will be stopped automatically."
echo

cd frontend
npm run dev

# When frontend dev server exits, stop backend
if kill "$BACKEND_PID" 2>/dev/null; then
  echo
  echo "Stopped backend (PID $BACKEND_PID)."
fi