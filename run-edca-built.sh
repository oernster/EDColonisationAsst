#!/usr/bin/env bash
set -euo pipefail

# Build + run helper (Linux) for Elite: Dangerous Colonisation Assistant.
#
# Goal:
#   Avoid Flatpak entirely. Build the frontend to frontend/dist (served by FastAPI at /app),
#   set up a Python venv for the backend, run the backend, then open the browser.
#
# This replaces the five per-distro copies (debian, fedora, arch, rhel, void).
# They differed only in the package-manager line and in which script name their
# own messages quoted, so four of them were free to drift out of step with the
# one that gets run: void had already lost the black step the other four had.
# The package manager is detected at runtime and only ever used to phrase the
# install hint printed when a prerequisite is missing; nothing is installed for
# you and no privileged command is run.
#
# Usage:
#   chmod +x ./run-edca-built.sh
#   ./run-edca-built.sh
#
# Options via env:
#   EDCA_HOST=127.0.0.1                   (bind host for uvicorn)
#   EDCA_PORT=8000                        (bind port for uvicorn)
#   EDCA_PYTHON=python3.12                (python executable used to create the backend venv)
#   EDCA_VENV_DIR=.venv312                (where to create/use the backend venv; default: backend/.venv)
#   EDCA_RECREATE_VENV=1                  (delete and recreate the venv if Python version mismatch)
#   EDCA_SKIP_FRONTEND_BUILD=1            (skip npm ci/build; assumes frontend/dist exists)
#   EDCA_FORCE_FRONTEND_BUILD=1           (rebuild frontend even if frontend/dist exists)
#   EDCA_SKIP_BACKEND_DEPS=1              (skip uv pip install -r backend/requirements.txt)
#
# Notes:
#  - This is NOT a Flatpak build. It runs from source on your machine.
#  - You need Python 3.10+.
#  - Node.js/npm are only required when actually building the frontend.
#  - Tested on Debian family. The other distro paths are UNTESTED helpers.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
cd "${SCRIPT_DIR}"

APP_HOST="${EDCA_HOST:-127.0.0.1}"
APP_PORT="${EDCA_PORT:-8000}"
UI_URL="http://${APP_HOST}:${APP_PORT}/app/"

log() { printf '%s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

# ----------------------------- package manager detection
#
# Used for hint text only. The first match wins, so a system carrying more than
# one manager gets the one that is idiomatic for it rather than an arbitrary
# choice: apt-get is checked before dnf because Debian derivatives sometimes
# ship dnf; a Debian user should be told to use apt.

detect_pkg_manager() {
  local candidate
  for candidate in apt-get dnf pacman zypper xbps-install apk yum; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      printf '%s' "${candidate}"
      return 0
    fi
  done
  printf '%s' "unknown"
}

PKG_MANAGER="$(detect_pkg_manager)"

# Print the install command for the given packages in the detected distro's own
# idiom. Package names differ between families, so each branch names its own.
install_hint() {
  case "${PKG_MANAGER}" in
    apt-get)     printf 'sudo apt-get update && sudo apt-get install -y %s' "$*" ;;
    dnf)         printf 'sudo dnf install -y %s' "$*" ;;
    yum)         printf 'sudo yum install -y %s' "$*" ;;
    pacman)      printf 'sudo pacman -Syu --needed %s' "$*" ;;
    zypper)      printf 'sudo zypper install -y %s' "$*" ;;
    xbps-install) printf 'sudo xbps-install -Sy %s' "$*" ;;
    apk)         printf 'sudo apk add %s' "$*" ;;
    *)           printf 'install %s with your distribution package manager' "$*" ;;
  esac
}

log "Package manager detected: ${PKG_MANAGER}"

# ----------------------------- prerequisites
#
# Default Python selection:
# - If EDCA_PYTHON is set, use it.
# - Otherwise prefer system python3.13 (common on newer Debian), else fall back to python3.

if [ -n "${EDCA_PYTHON:-}" ]; then
  PYTHON="${EDCA_PYTHON}"
else
  if command -v python3.13 >/dev/null 2>&1; then
    PYTHON="python3.13"
  else
    PYTHON="python3"
  fi
fi

if ! command -v "${PYTHON}" >/dev/null 2>&1; then
  if [ -z "${EDCA_PYTHON:-}" ] && command -v python >/dev/null 2>&1; then
    PYTHON="python"
  else
    die "Python is required but was not found on PATH. Install Python 3.10+ ($(install_hint python3)). You can also set EDCA_PYTHON to an interpreter you already have."
  fi
fi

PY_VER="$("${PYTHON}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null || true)"
log "Using Python: ${PYTHON} (${PY_VER})"

if ! command -v uv >/dev/null 2>&1; then
  die "uv is required but was not found on PATH. Install uv (https://docs.astral.sh/uv/) and ensure it is on PATH (often: export PATH=\"\$HOME/.local/bin:\$PATH\")."
fi

# pydantic==2.5.0 pulls pydantic-core which may not have wheels for Python 3.13,
# causing a Rust build requirement (maturin/cargo). If you hit build issues, use uv-managed Python 3.12.
PY_MAJOR_MINOR="$("${PYTHON}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
if [ "${PY_MAJOR_MINOR}" = "3.13" ]; then
  log "NOTE: Python 3.13 detected. If you hit pydantic-core build errors, use Python 3.12 via uv and run with: EDCA_PYTHON=python3.12 EDCA_VENV_DIR=.venv312 ./${SCRIPT_NAME}"
fi

# Node/npm are only required if we are going to build the frontend.
NEED_FRONTEND_BUILD=1
if [ "${EDCA_SKIP_FRONTEND_BUILD:-0}" = "1" ]; then
  NEED_FRONTEND_BUILD=0
elif [ -d "frontend/dist" ]; then
  # If a production build already exists, default to reusing it unless the user explicitly wants rebuilds.
  if [ "${EDCA_FORCE_FRONTEND_BUILD:-0}" != "1" ]; then
    NEED_FRONTEND_BUILD=0
  fi
fi

if [ "${NEED_FRONTEND_BUILD}" = "1" ]; then
  if ! command -v npm >/dev/null 2>&1; then
    die "Node.js/npm are required to build the frontend but were not found on PATH. Install Node.js 20+ ($(install_hint nodejs npm)). You can also set EDCA_SKIP_FRONTEND_BUILD=1 with an existing frontend/dist."
  fi
fi

# ----------------------------- backend venv + deps

VENV_DIR="${EDCA_VENV_DIR:-backend/.venv}"
VENV_PY="${VENV_DIR}/bin/python"
RECREATE_VENV="${EDCA_RECREATE_VENV:-0}"

# If EDCA_PYTHON is explicitly set, enforce that the venv uses that Python major.minor.
# If EDCA_PYTHON is NOT set, prefer "just run" behavior: reuse any existing venv without error,
# even if the caller's shell has a different python on PATH (e.g. an activated uv venv).
if [ -n "${EDCA_PYTHON:-}" ] && [ -x "${VENV_PY}" ]; then
  VENV_MAJOR_MINOR="$("${VENV_PY}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
  if [ -n "${PY_MAJOR_MINOR:-}" ] && [ -n "${VENV_MAJOR_MINOR}" ] && [ "${VENV_MAJOR_MINOR}" != "${PY_MAJOR_MINOR}" ]; then
    if [ "${RECREATE_VENV}" = "1" ]; then
      log "Venv at ${VENV_DIR} uses Python ${VENV_MAJOR_MINOR} but requested ${PY_MAJOR_MINOR}; recreating (EDCA_RECREATE_VENV=1) ..."
      rm -rf "${VENV_DIR}"
    else
      die "Venv at ${VENV_DIR} uses Python ${VENV_MAJOR_MINOR} but requested ${PY_MAJOR_MINOR}. Set EDCA_RECREATE_VENV=1 to recreate it. You can also set EDCA_VENV_DIR to a different venv (e.g. .venv312)."
    fi
  fi
fi

if [ ! -x "${VENV_PY}" ]; then
  log "Creating backend virtualenv at ${VENV_DIR} using ${PYTHON} ..."
  "${PYTHON}" -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

if [ "${EDCA_SKIP_BACKEND_DEPS:-0}" != "1" ]; then
  if [ ! -f "backend/requirements.txt" ]; then
    die "backend/requirements.txt not found."
  fi

  log "Installing backend dependencies (uv pip) ..."
  uv pip install -r backend/requirements.txt

  # Always ensure black is available in the backend venv so we can format the
  # backend codebase before running. This keeps the backend consistent with
  # the Windows build script, which also runs black.
  log "Installing black (code formatter) into backend venv (uv pip) ..."
  uv pip install black

  log "Formatting backend Python code with black ..."
  "${VENV_PY}" -m black backend/src backend/tests
else
  log "Skipping backend dependency install (EDCA_SKIP_BACKEND_DEPS=1)."
fi

# ----------------------------- frontend build

if [ "${NEED_FRONTEND_BUILD}" = "1" ]; then
  if [ ! -f "frontend/package-lock.json" ]; then
    die "frontend/package-lock.json not found (expected for reproducible builds)."
  fi
  log "Installing frontend dependencies (npm ci) ..."
  npm --prefix frontend ci --no-audit --no-fund
  log "Building frontend production bundle (vite build) ..."
  npm --prefix frontend run build --no-audit --no-fund
else
  if [ "${EDCA_SKIP_FRONTEND_BUILD:-0}" = "1" ]; then
    log "Skipping frontend build (EDCA_SKIP_FRONTEND_BUILD=1)."
  else
    log "Skipping frontend build (reusing existing frontend/dist)."
  fi
fi

if [ ! -d "frontend/dist" ]; then
  cat >&2 <<'EOF'
Error: frontend/dist not found.

This script opens the UI at /app/, which is served by the backend only when a production
frontend build exists at frontend/dist.

Fix options:
  1) Build the frontend once (requires Node/npm):
       npm --prefix frontend ci
       npm --prefix frontend run build

  2) Copy a prebuilt frontend/dist from another machine/CI build into ./frontend/dist

If you intentionally skipped the frontend build, unset EDCA_SKIP_FRONTEND_BUILD or provide frontend/dist.
EOF
  exit 1
fi

# ----------------------------- run backend + open browser

log "Starting backend on http://${APP_HOST}:${APP_PORT} (UI: ${UI_URL}) ..."
set +e
"${VENV_PY}" -m uvicorn backend.src.main:app --host "${APP_HOST}" --port "${APP_PORT}" &
BACKEND_PID=$!
set -e

cleanup() {
  log ""
  log "Stopping backend (PID ${BACKEND_PID}) ..."
  kill "${BACKEND_PID}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Wait until backend + UI are ready (best-effort)
log "Waiting for backend to become ready ..."
"${VENV_PY}" - <<PY
import time
import urllib.request

base = "http://${APP_HOST}:${APP_PORT}"
urls = [f"{base}/api/health", f"{base}/app/"]
deadline = time.time() + 60

def ok(u: str) -> bool:
    try:
        with urllib.request.urlopen(u, timeout=2) as r:
            return 200 <= r.getcode() < 500
    except Exception:
        return False

while time.time() < deadline:
    if all(ok(u) for u in urls):
        break
    time.sleep(0.5)
PY

log "Opening browser: ${UI_URL}"
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "${UI_URL}" >/dev/null 2>&1 || true
elif command -v open >/dev/null 2>&1; then
  open "${UI_URL}" >/dev/null 2>&1 || true
else
  "${VENV_PY}" - <<PY
import webbrowser
webbrowser.open("${UI_URL}")
PY
fi

log "Backend is running. Press Ctrl+C to stop."
wait "${BACKEND_PID}"
