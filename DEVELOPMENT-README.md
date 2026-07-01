# EDCA Development Guide

This guide is for developers building, running and extending the
Elite: Dangerous Colonisation Assistant (EDCA) from a source checkout.
For the end-user quick start, see [README.md](README.md).

Related documents:

- [ARCHITECTURE.md](ARCHITECTURE.md) - high-level system and component design
- [ARCHITECTURE_1_backend.md](ARCHITECTURE_1_backend.md) - backend architecture detail
- [ARCHITECTURE_2_frontend_and_runtime.md](ARCHITECTURE_2_frontend_and_runtime.md) - frontend and packaged-runtime architecture
- [TESTING.md](TESTING.md) - how to run the tests and the coverage gate
- [PROJECT_SETUP.md](PROJECT_SETUP.md) - first-time environment setup notes
- [GameGlass-Integration.md](GameGlass-Integration.md) - GameGlass shard integration

---

## Building the Windows release (two commands)

The whole Windows build pipeline is two scripts at the project root, run in
order:

```powershell
# 1) Build the self-contained runtime EXE
python buildexe.py

# 2) Stage the payload and build the GUI installer EXE
python buildinstaller.py
```

Run both from the project root with a Python environment that has
`backend/requirements-dev.txt` installed (this includes Nuitka and PySide6).

### What buildexe.py does

[buildexe.py](buildexe.py) compiles
[backend/src/runtime_entry.py](backend/src/runtime_entry.py) with Nuitka
(onefile, PySide6 plugin) into a self-contained runtime that embeds Python
and every backend dependency. It also:

- Refreshes `BUILD_ID` (UTC timestamp + short git SHA) so installed builds
  can be identified via `/api/health`.
- Reads the canonical version from the top-level `VERSION` file and stamps
  it into the EXE's PE metadata (product/file version, company, copyright).
- Bundles `VERSION` and `BUILD_ID` inside the EXE.
- Keeps all Nuitka intermediates under `build/` (gitignored).

Output: `dist-runtime/EDColonisationAsst.exe`

Set `EDCA_DEBUG_CONSOLE=1` in the environment before building to produce a
debug build with an attached console.

### What buildinstaller.py does

[buildinstaller.py](buildinstaller.py):

1. Requires `dist-runtime/EDColonisationAsst.exe` (fails fast with a hint to
   run `python buildexe.py` first).
2. Ensures the frontend production bundle exists, running `npm run build`
   when npm is available (an existing `frontend/dist` is accepted when npm
   is absent).
3. Stages a fresh curated payload under `build/payload/`: backend sources
   (shipped as `*.py_` so Nuitka does not strip them; the installer renames
   them back on deploy), the built frontend, icons, `LICENSE`, `VERSION`
   and the runtime EXE.
4. Compiles the PySide6 installer UI at [installer/app.py](installer/app.py)
   with Nuitka (onefile) with the payload embedded, stamping the same PE
   metadata from `VERSION`.

Output: `dist-installer/EDColonisationAsstInstaller.exe`

### Build system layout

```text
buildexe.py           # runtime EXE build (Nuitka onefile)
buildinstaller.py     # payload staging + installer EXE build
installer/
├── app.py            # PySide6 GUI installer (Install / Repair / Uninstall)
└── css.py            # installer QSS themes (dark / light)
build/                # Nuitka intermediates + staged payload (gitignored)
dist-runtime/         # EDColonisationAsst.exe (gitignored)
dist-installer/       # EDColonisationAsstInstaller.exe (gitignored)
VERSION               # single source of truth for the app version
BUILD_ID              # build marker written by buildexe.py
```

The `VERSION` file is the single source of truth for the application
version. The backend reads it at runtime
([backend/src/\_\_init\_\_.py](backend/src/__init__.py)), the build scripts
stamp it into PE metadata and the installer displays it; nothing else
hardcodes a version.

### Prerequisites (developer machine)

- Windows 10/11 x64.
- **Python 3.13+** (3.12 remains a supported fallback).
- **Visual Studio 2022 Build Tools** with the *Desktop development with C++*
  workload (MSVC v143) and a recent Windows 10/11 SDK; see the compiler
  notes below.
- **Node.js 18+** with npm (frontend build only; never needed by end users).
- Backend dev dependencies installed:

  ```powershell
  cd backend
  python -m venv venv        # or: uv venv venv
  venv\Scripts\activate
  pip install -r requirements-dev.txt
  ```

### Windows compiler requirements for Nuitka

Nuitka compiles Python to C and needs a platform C/C++ compiler. This
project is tested with **MSVC**, not Cygwin GCC.

For Python 3.13 (the current default):

- Nuitka requires **MSVC 14.3 (v143 toolset) or later**, provided by
  Visual Studio 2022 Build Tools
  (`https://aka.ms/vs/17/release/vs_BuildTools.exe`).
- Choose the workload **Desktop development with C++** and confirm
  **MSVC v143 - VS 2022 C++ x64/x86 build tools** plus a recent
  **Windows 10/11 SDK** in the Individual components tab.
- MSVC 14.2 (VS 2019, v142) is not sufficient for Python 3.13; Nuitka fails
  with "MSVC 14.3 or later is required".

If you build with Python 3.11/3.12 instead, MSVC 14.2 (v142) still works;
create the backend venv with that interpreter explicitly. MinGW-w64 is
possible in principle but untested for this project; Cygwin GCC is not
supported.

### Smoke-testing the installer

On a Windows test machine:

1. Run `dist-installer/EDColonisationAsstInstaller.exe` and choose
   **Install** (default target: `%LOCALAPPDATA%\EDColonisationAssistant`;
   no elevation required).
2. Confirm the install directory contains `EDColonisationAsst.exe`,
   `backend/` and `frontend/dist/`.
3. Launch via the Start Menu / Desktop shortcut:
   - The startup splash appears (icon, author, version, live status).
   - A tray icon appears (Open Web UI / Help / Exit).
   - The browser opens `http://127.0.0.1:8000/app/` once the backend is
     actually ready.
4. No system Python or Node.js should be required.

---

## Backend development (FastAPI, Python)

Run these from the `backend/` directory unless noted.

### Setup

```bash
cd backend
python -m venv venv          # or: uv venv venv
venv\Scripts\activate        # Windows; source venv/bin/activate on Unix
pip install -r requirements-dev.txt
```

### Running the dev server

```bash
uvicorn src.main:app --reload
```

or from the project root: `uvicorn backend.src.main:app --reload`.

- REST API: `http://localhost:8000`
- Swagger docs: `http://localhost:8000/docs`
- Live updates (AJAX long-poll): `http://localhost:8000/api/changes/longpoll`

### Configuration

Non-sensitive config lives in [backend/config.yaml](backend/config.yaml)
(journal directory, server host/port, CORS, logging). Commander-specific
and Inara secrets live in `backend/commander.yaml`, which is gitignored;
copy [backend/example.commander.yaml](backend/example.commander.yaml) or
let the Settings page in the UI write it for you. Do not commit real API
keys.

### Testing

See [TESTING.md](TESTING.md). Short version, from `backend/`:

```bash
pytest -v --cov
```

The suite enforces 100% coverage of the gated backend surface; the build
fails below it.

### Code quality

From `backend/`:

```bash
black src/ tests/
isort src/ tests/
mypy src/
pylint src/
```

### Git hooks

A shared pre-commit hook lives at [.githooks/pre-commit](.githooks/pre-commit).
Enable it per clone with:

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
```

It formats staged Python files with black and runs the backend test suite
(including the coverage gate) before every commit.

---

## Frontend development (React + TypeScript)

Run these from the `frontend/` directory.

```bash
npm install       # once
npm run dev       # dev server at http://localhost:5173
npm run build     # production bundle in frontend/dist (tsc && vite build)
npm test          # vitest suite
npm run lint      # eslint
```

The production bundle is served by FastAPI at `/app/` (Vite is configured
with `base: '/app/'`). Rebuild the frontend before rebuilding the installer.

---

## Running from source (developer view)

### Windows / general

From the project root, two terminals:

```bash
# Terminal 1: backend
uvicorn backend.src.main:app --reload

# Terminal 2: frontend
npm --prefix frontend run dev
```

Or use the convenience scripts [run-edca.bat](run-edca.bat) /
[run-edca.sh](run-edca.sh), which install dependencies and start both.

### Linux

Use the distro-specific helper from the project root; each creates a venv,
installs backend requirements, ensures `frontend/dist` exists and serves
everything on `http://127.0.0.1:8000/app/`:

- Debian / Ubuntu / Mint: [run-edca-built-debian.sh](run-edca-built-debian.sh) (recommended)
- Fedora: [run-edca-built-fedora.sh](run-edca-built-fedora.sh) (UNTESTED)
- Arch: [run-edca-built-arch.sh](run-edca-built-arch.sh) (UNTESTED)
- RHEL / Rocky / Alma: [run-edca-built-rhel.sh](run-edca-built-rhel.sh) (UNTESTED)
- Void: [run-edca-built-void.sh](run-edca-built-void.sh) (UNTESTED)

Useful environment variables: `EDCA_HOST`, `EDCA_PORT`, `EDCA_PYTHON`,
`EDCA_VENV_DIR`, `EDCA_RECREATE_VENV=1` and `EDCA_SKIP_FRONTEND_BUILD=1`
(use a prebuilt `frontend/dist` without Node installed). Install `uv` once
per machine (`curl -LsSf https://astral.sh/uv/install.sh | sh`) and
`uv python install 3.13` if your distro lacks Python 3.13.

---

## Runtime behaviour of the installed app

The Start Menu / Desktop shortcuts point at `EDColonisationAsst.exe`, which:

- Detects FROZEN mode and starts an in-process `uvicorn.Server` hosting the
  FastAPI app on `http://127.0.0.1:8000`.
- Shows the startup splash immediately (icon, author, version, live status)
  and polls readiness without blocking the UI.
- Serves the bundled frontend at `http://127.0.0.1:8000/app/` and opens the
  browser only once both the health endpoint and the web UI respond.
- Provides a tray icon with Open Web UI, a Help submenu (About plus
  Check for Updates) and Exit.
- Started with `--no-browser` (login autostart), it stays silent: no splash
  and no browser.

See [ARCHITECTURE_2_frontend_and_runtime.md](ARCHITECTURE_2_frontend_and_runtime.md)
for the full runtime architecture.

---

## GameGlass integration

GameGlass shard assets live under `frontend/src/gameglass/`. For endpoints,
layout guidance and the long-poll contract, see
[GameGlass-Integration.md](GameGlass-Integration.md).
