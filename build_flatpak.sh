#!/usr/bin/env bash
# build_flatpak.sh - Build the Elite: Dangerous Colonisation Assistant as a Flatpak
#
# Uses org.freedesktop.Platform//25.08 (Python 3.13). The wheels are
# pre-downloaded on the host, then installed inside the sandbox from those local
# wheels with --no-index, so the build itself is offline.
#
# What gets packaged is the source tree, not a compiled binary: the sandbox
# already ships its own Python and every dependency, which is the same condition
# the frozen Windows build satisfies by other means. Inside the sandbox the app
# therefore runs uvicorn in-process behind a Qt tray icon, exactly as the
# packaged Windows runtime does, rather than building a virtual environment and
# spawning processes as a source checkout does.
#
# Usage:
#   ./build_flatpak.sh             - build, install locally, AND produce the bundle
#   ./build_flatpak.sh --no-bundle - build + install only (skip the bundle)
#
# Options via env:
#   EDCA_VENV_DIR=backend/.venv        (venv used to run pip download and Pillow)
#   EDCA_FORCE_FRONTEND_BUILD=1        (rebuild frontend/dist even if it exists)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

APP_ID="uk.co.oernster.EDColonisationAsst"
APP_VERSION=$(tr -d '[:space:]' < VERSION)
BUNDLE="edcolonisationasst.flatpak"
BUILD_DIR=".flatpak-build"
REPO_DIR=".flatpak-repo"
MANIFEST="${APP_ID}.yml"

# The command name, the staged directory name and the launcher all share this.
# Lower case with no punctuation because it becomes an executable on PATH.
APP_COMMAND="edcolonisationasst"
STAGED_DIR="/app/share/${APP_COMMAND}"

RUNTIME="org.freedesktop.Platform"
SDK="org.freedesktop.Sdk"
RUNTIME_VERSION="25.08"

# Python version shipped by the runtime above. Used to build the site-packages
# path the launcher exports; keep it in sync with RUNTIME_VERSION.
PYTHON_MM="3.13"

REQUIREMENTS="backend/requirements-flatpak.txt"

# The venv used only by this script, for pip download and for Pillow. The same
# default as run-edca-built.sh, so a machine that has already run that script
# has this already.
VENV_DIR="${EDCA_VENV_DIR:-backend/.venv}"

# Wheels are tagged for the runtime's Python and glibc. pip does NOT widen a
# --platform tag to the older manylinux tags, so every tag we accept has to be
# listed. PySide6 ships manylinux_2_28, watchdog publishes only the older
# manylinux2014 spelling and the pure-Python distributions are any-tagged. The
# runtime's glibc is newer than all of them.
WHEEL_PYTHON="3.13"
WHEEL_PLATFORMS=(
    manylinux_2_34_x86_64
    manylinux_2_28_x86_64
    manylinux_2_17_x86_64
    manylinux2014_x86_64
)

# The master artwork. Every icon size is a DOWNSCALE of this file: nothing is
# ever resampled upwards, which would soften artwork to fill a size it never
# had. The master is 343px, so the hicolor set stops at 256 rather than running
# to the 512 a larger master would allow.
MASTER_ICON="EDColonisationAsst.png"

# The distributable bundle is the point of the script, so it is built by
# default. Pass --no-bundle to skip it and only build plus install locally.
MAKE_BUNDLE=1
for arg in "$@"; do
    if [[ "$arg" == "--no-bundle" ]]; then MAKE_BUNDLE=0; fi
done

# ── Colour helpers ────────────────────────────────────────────────────────────
bold=$(tput bold 2>/dev/null || true)
reset=$(tput sgr0 2>/dev/null || true)
section() { echo; echo "${bold}=== $* ===${reset}"; }

run_with_spinner() {
    local label="$1" watch=""
    shift
    if [[ "${1:-}" == "--watch" ]]; then watch="$2"; shift 2; fi
    if [[ "${1:-}" == "--" ]]; then shift; fi
    "$@" &
    local pid=$! i=0 spin='⣾⣽⣻⢿⡿⣟⣯⣷'
    # The spinner rewrites one line with a carriage return, which only reads as
    # a spinner on a terminal. Redirected to a file or a pipe there is nothing
    # to rewrite, so every frame lands as its own line and buries the log; in
    # that case announce the step once and wait quietly.
    # 'wait' is read inside an if so that set -e does not abort the script
    # before the outcome line is printed; the non-zero code is returned instead.
    local rc=0
    if [[ ! -t 1 ]]; then
        echo "  ... ${label}"
        if wait "$pid"; then rc=0; else rc=$?; fi
        [[ $rc -eq 0 ]] && echo "  OK   ${label}" || echo "  FAIL ${label}"
        return $rc
    fi
    while kill -0 "$pid" 2>/dev/null; do
        local extra=""
        if [[ -n "$watch" && -f "$watch" ]]; then
            extra="  ($(du -sh "$watch" 2>/dev/null | cut -f1) written)"
        fi
        printf "\r  %s  %s%s" "${spin:$((i % ${#spin})):1}" "$label" "$extra"
        i=$((i + 1)); sleep 0.3
    done
    if wait "$pid"; then rc=0; else rc=$?; fi
    [[ $rc -eq 0 ]] && printf "\r  ✓  %-72s\n" "$label" \
                     || printf "\r  ✗  %-72s\n" "$label"
    return $rc
}

# ── Tool checks ───────────────────────────────────────────────────────────────
section "Checking dependencies"
install_if_missing() {
    local pkg="$1"
    if ! command -v "$pkg" &>/dev/null; then
        echo "  $pkg not found - installing..."
        if   command -v apt-get &>/dev/null; then sudo apt-get update -qq && sudo apt-get install -y "$pkg"
        elif command -v dnf    &>/dev/null; then sudo dnf install -y "$pkg"
        elif command -v pacman &>/dev/null; then sudo pacman -Sy --noconfirm "$pkg"
        elif command -v zypper &>/dev/null; then sudo zypper install -y "$pkg"
        else echo "ERROR: unsupported package manager" >&2; exit 1; fi
    else echo "  $pkg: OK"; fi
}
install_if_missing flatpak
install_if_missing flatpak-builder

if [[ ! -f "${REQUIREMENTS}" ]]; then
    echo "ERROR: ${REQUIREMENTS} not found." >&2
    exit 1
fi

if [[ ! -f "${MASTER_ICON}" ]]; then
    echo "ERROR: master icon ${MASTER_ICON} not found." >&2
    echo "       Every packaged icon is derived from it, so it cannot be skipped." >&2
    exit 1
fi

# The venv exists to run pip download against the runtime's Python tags and to
# give Pillow somewhere to live. Nothing from it is packaged.
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    echo "  Creating build virtualenv at ${VENV_DIR} ..."
    python3 -m venv "${VENV_DIR}"
else
    echo "  Build virtualenv: OK (${VENV_DIR})"
fi
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

# Pillow is a BUILD dependency only: it derives the hicolor icon set from the
# master PNG. The application itself never imports it, so it is not in any
# requirements file and a venv made from those alone will not have it.
if python3 -c "import PIL" &>/dev/null; then
    echo "  Pillow: OK"
else
    echo "  Pillow not found in the venv - installing..."
    pip install -q Pillow
fi

# ── Frontend bundle ───────────────────────────────────────────────────────────
# The backend serves the built frontend at /app/ and mounts it only when
# frontend/dist exists. A flatpak built without it would install cleanly, start
# cleanly and then serve nothing, which is the worst of the three outcomes, so
# it is a hard requirement here rather than a warning.
section "Checking the frontend bundle"
if [[ -d frontend/dist && "${EDCA_FORCE_FRONTEND_BUILD:-0}" != "1" ]]; then
    echo "  frontend/dist: OK (reusing; set EDCA_FORCE_FRONTEND_BUILD=1 to rebuild)"
else
    if ! command -v npm &>/dev/null; then
        echo "ERROR: frontend/dist is missing and npm was not found on PATH." >&2
        echo "       Install Node.js 20+ or copy a prebuilt frontend/dist into place." >&2
        exit 1
    fi
    if [[ ! -f frontend/package-lock.json ]]; then
        echo "ERROR: frontend/package-lock.json not found (expected for a reproducible build)." >&2
        exit 1
    fi
    run_with_spinner "Installing frontend dependencies (npm ci)" -- \
        npm --prefix frontend ci --no-audit --no-fund
    run_with_spinner "Building frontend production bundle (vite build)" -- \
        npm --prefix frontend run build --no-audit --no-fund
fi

# ── Flatpak remote + runtime ──────────────────────────────────────────────────
section "Configuring Flathub remote"
flatpak remote-add --if-not-exists --user flathub \
    https://dl.flathub.org/repo/flathub.flatpakrepo

section "Installing runtime and SDK (${RUNTIME_VERSION})"
flatpak install --user --noninteractive flathub \
    "${RUNTIME}//${RUNTIME_VERSION}" \
    "${SDK}//${RUNTIME_VERSION}" \
    || true

# ── Pre-download wheels (Python 3.13 / manylinux x86_64) ──────────────────────
section "Pre-downloading wheels (Python ${WHEEL_PYTHON} / ${WHEEL_PLATFORMS[0]})"
rm -rf .flatpak-wheels
mkdir -p .flatpak-wheels

platform_args=()
for tag in "${WHEEL_PLATFORMS[@]}"; do platform_args+=(--platform "$tag"); done

run_with_spinner "Downloading wheels for $(grep -cE '^[^#[:space:]]' "${REQUIREMENTS}") requirements" -- \
    pip download --only-binary :all: \
        --python-version "${WHEEL_PYTHON}" --implementation cp \
        "${platform_args[@]}" \
        -q -d .flatpak-wheels -r "${REQUIREMENTS}"

echo "  $(ls .flatpak-wheels/ | wc -l) distributions ready"

# ── Icons ─────────────────────────────────────────────────────────────────────
# The repo carries one master PNG and a Windows .ico and no hicolor size set,
# which is what a desktop needs to draw the app anywhere other than the window
# itself. The set is derived here rather than committed, so the artwork has one
# source of truth.
section "Generating hicolor icons from the master"
rm -rf packaging/icons
mkdir -p packaging/icons
python3 - "${MASTER_ICON}" <<'PYICONS'
from pathlib import Path
import sys

from PIL import Image

MASTER = Path(sys.argv[1])
OUT = Path("packaging/icons")
SIZES = (16, 32, 48, 64, 128, 256)

master = Image.open(MASTER).convert("RGBA")
for size in SIZES:
    if size > master.width:
        raise SystemExit(
            f"master {MASTER} is {master.width}px, too small for a {size}px icon"
        )
    master.resize((size, size), Image.LANCZOS).save(OUT / f"edca_{size}.png")
print(f"  {len(SIZES)} icon sizes written from {MASTER} ({master.width}px master)")
PYICONS

# ── Packaging helpers ─────────────────────────────────────────────────────────
section "Writing packaging helpers"
mkdir -p packaging

# EDCA_PROJECT_ROOT is what the tray side needs. Inside the sandbox sys.argv[0]
# is this launcher's own path, which is not where the frontend bundle and the
# icon live, so the staged root is stated rather than guessed. The backend
# resolves its own root from the module layout and needs no help.
cat > "packaging/${APP_COMMAND}-launcher.sh" <<LAUNCHER
#!/bin/sh
export LD_LIBRARY_PATH="/app/lib\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
export PYTHONPATH="${STAGED_DIR}:/app/lib/python${PYTHON_MM}/site-packages\${PYTHONPATH:+:\$PYTHONPATH}"
export QT_PLUGIN_PATH="/app/lib/python${PYTHON_MM}/site-packages/PySide6/Qt/plugins"
export QT_QPA_PLATFORM_PLUGIN_PATH="/app/lib/python${PYTHON_MM}/site-packages/PySide6/Qt/plugins/platforms"
export EDCA_PROJECT_ROOT="${STAGED_DIR}"
if [ -n "\${WAYLAND_DISPLAY:-}" ] && [ -z "\${FORCE_X11:-}" ]; then
    export QT_QPA_PLATFORM=wayland
elif [ -n "\${DISPLAY:-}" ]; then
    export QT_QPA_PLATFORM=xcb
else
    export QT_QPA_PLATFORM=xcb
fi
exec python3 -m backend.src.runtime_entry "\$@"
LAUNCHER
chmod +x "packaging/${APP_COMMAND}-launcher.sh"

cat > "packaging/${APP_ID}.desktop" <<DESKTOP
[Desktop Entry]
Name=Colonisation Assistant
Comment=Track Elite Dangerous colonisation projects, hauling and carrier logistics
Exec=${APP_COMMAND}
Icon=${APP_ID}
Terminal=false
Type=Application
Categories=Game;Utility;
# StartupWMClass is deliberately absent for now. It ties the window back to this
# entry so it lights up the launcher it was started from rather than appearing
# as a second, generic one, but the value has to MATCH what the toolkit actually
# publishes and this application has not been observed on a Linux desktop yet.
# Qt takes WM_CLASS from the application name, which here is a string with
# spaces and a colon in it, and Wayland does not use WM_CLASS at all: it matches
# on the id from setDesktopFileName, which the application does not yet call.
# Guessing produces a line that silently matches nothing. Read the real value
# with 'xprop WM_CLASS' once it runs, add setDesktopFileName for Wayland, then
# set this.
DESKTOP

cat > "packaging/${APP_ID}.metainfo.xml" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>${APP_ID}</id>
  <name>Colonisation Assistant</name>
  <summary>Colonisation support for Elite Dangerous</summary>
  <metadata_license>MIT</metadata_license>
  <project_license>LGPL-3.0-or-later</project_license>
  <description>
    <p>The Elite: Dangerous Colonisation Assistant reads the Player Journal and
    tracks construction sites, per-system shopping lists, carrier finances and
    crew. The interface is served locally in a browser, so it can be opened on a
    tablet over the local network alongside the game.</p>
  </description>
  <releases>
    <release version="${APP_VERSION}"/>
  </releases>
  <url type="homepage">https://ernster.dev/EDColonisationAsst/</url>
</component>
XML

echo "  Packaging helpers ready."

# ── Manifest ──────────────────────────────────────────────────────────────────
section "Writing manifest ${MANIFEST}"

cat > "${MANIFEST}" <<YAML
app-id: ${APP_ID}
runtime: ${RUNTIME}
runtime-version: "${RUNTIME_VERSION}"
sdk: ${SDK}

command: ${APP_COMMAND}

build-options:
  strip: true
  no-debuginfo: true

finish-args:
  - --share=ipc
  - --socket=fallback-x11
  - --socket=wayland
  - --device=dri
  # The interface is an HTTP server the user opens in a browser, including from
  # a tablet on the same network, so this is what the application IS rather than
  # an optional extra. It also carries the update check.
  - --share=network
  # The journal lives inside the game's Wine or Proton prefix under the user's
  # home. Read and write because the settings page lets the user point the app
  # at a different journal directory.
  - --filesystem=home
  # Steam installed AS A FLATPAK keeps its Proton prefixes under ~/.var/app,
  # which flatpak deliberately excludes from --filesystem=home. Without this
  # line the app finds no journal at all on that very common setup and reports
  # no journal directory on a machine that plainly has one. Read-only: the app
  # never writes to the journal.
  - --filesystem=~/.var/app/com.valvesoftware.Steam:ro
  # The tray icon. On Linux a Qt tray icon is not drawn into a panel at all: it
  # is published over D-Bus as a StatusNotifierItem and the desktop's watcher
  # draws it. Inside the sandbox that watcher is unreachable unless it is named
  # here. Talking to the watcher is the entire grant; publishing an item also
  # means owning a bus name of the form org.kde.StatusNotifierItem-PID-N, which
  # cannot be expressed here and is not needed, because Qt hands the watcher its
  # unique connection name instead.
  - --talk-name=org.kde.StatusNotifierWatcher

modules:

  # ── Python dependencies (local wheels only, fully offline) ────────────────
  - name: python-deps
    buildsystem: simple
    build-commands:
      - python3 -m ensurepip --upgrade --default-pip
      - pip3 install --no-cache-dir --no-index --find-links wheels --prefix=/app
          -r requirements-flatpak.txt
    sources:
      - type: dir
        path: .flatpak-wheels
        dest: wheels
      - type: file
        path: ${REQUIREMENTS}

  # ── Application source and assets ─────────────────────────────────────────
  # Staged in the source layout, backend/src beside frontend/dist under one
  # root, because that is the layout the backend resolves its own project root
  # from. Anything else would leave it unable to find the frontend bundle.
  - name: ${APP_COMMAND}
    buildsystem: simple
    build-commands:
      - mkdir -p ${STAGED_DIR}/backend ${STAGED_DIR}/frontend
      - cp -r backend/src ${STAGED_DIR}/backend/src
      - cp -r frontend/dist ${STAGED_DIR}/frontend/dist
      - cp VERSION BUILD_ID LICENSE ${STAGED_DIR}/
      # The tray resolves its icon from the project root by this exact name.
      - cp EDColonisationAsst.ico EDColonisationAsst.png ${STAGED_DIR}/
      - install -Dm644 packaging/icons/edca_16.png  /app/share/icons/hicolor/16x16/apps/${APP_ID}.png
      - install -Dm644 packaging/icons/edca_32.png  /app/share/icons/hicolor/32x32/apps/${APP_ID}.png
      - install -Dm644 packaging/icons/edca_48.png  /app/share/icons/hicolor/48x48/apps/${APP_ID}.png
      - install -Dm644 packaging/icons/edca_64.png  /app/share/icons/hicolor/64x64/apps/${APP_ID}.png
      - install -Dm644 packaging/icons/edca_128.png /app/share/icons/hicolor/128x128/apps/${APP_ID}.png
      - install -Dm644 packaging/icons/edca_256.png /app/share/icons/hicolor/256x256/apps/${APP_ID}.png
      - install -Dm755 packaging/${APP_COMMAND}-launcher.sh /app/bin/${APP_COMMAND}
      - install -Dm644 packaging/${APP_ID}.desktop /app/share/applications/${APP_ID}.desktop
      - install -Dm644 packaging/${APP_ID}.metainfo.xml /app/share/metainfo/${APP_ID}.metainfo.xml
      - install -Dm644 LICENSE /app/share/licenses/${APP_ID}/LICENSE
    sources:
      - type: file
        path: VERSION
      - type: file
        path: BUILD_ID
      - type: file
        path: LICENSE
      - type: file
        path: EDColonisationAsst.ico
      - type: file
        path: EDColonisationAsst.png
      - type: dir
        path: backend/src
        dest: backend/src
      - type: dir
        path: frontend/dist
        dest: frontend/dist
      - type: dir
        path: packaging
        dest: packaging
YAML

echo "  Manifest written."

# ── Build ─────────────────────────────────────────────────────────────────────
section "Building Flatpak"
rm -rf "${BUILD_DIR}" "${REPO_DIR}"

flatpak-builder \
    --user \
    --install-deps-from=flathub \
    --install \
    --force-clean \
    --repo="${REPO_DIR}" \
    "${BUILD_DIR}" \
    "${MANIFEST}"

# ── Bundle (on by default; skip with --no-bundle) ─────────────────────────────
if [[ $MAKE_BUNDLE -eq 1 ]]; then
    section "Bundling to ${BUNDLE}"
    echo "  The spinner shows how much of ${BUNDLE} has been written."
    echo
    rm -f "${BUNDLE}"
    run_with_spinner "Writing ${BUNDLE}" --watch "${BUNDLE}" -- \
        flatpak build-bundle "${REPO_DIR}" "${BUNDLE}" "${APP_ID}"
    echo
    echo "${bold}Bundle: ${BUNDLE}  ($(du -sh "${BUNDLE}" | cut -f1))${reset}"
    echo
    echo "Install on another machine:"
    echo "  1. Copy ${BUNDLE} to the target machine"
    echo "  2. flatpak install --user ${BUNDLE}"
    echo "  3. flatpak run ${APP_ID}"
fi

echo
echo "${bold}Build complete.${reset}"
echo
echo "The app is already installed locally. To manage it:"
echo
echo "  Run:        flatpak run ${APP_ID}"
echo "  Uninstall:  flatpak uninstall --user ${APP_ID}"
echo
echo "It starts as a tray icon and serves the interface locally; open it from"
echo "the tray menu. Its database, configuration and logs are written under"
echo "~/.var/app/${APP_ID}, not into the installed application."
echo
if [[ $MAKE_BUNDLE -ne 1 ]]; then
    echo "Bundle skipped (--no-bundle). Run without it to produce ${BUNDLE}."
    echo
fi
