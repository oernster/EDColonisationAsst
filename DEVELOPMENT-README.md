# EDCA Development Guide

This guide is for developers building, running and extending the
Elite: Dangerous Colonisation Assistant (EDCA) from a source checkout.
For the end-user quick start, see [README.md](README.md).

Related documents:

- [ARCHITECTURE.md](ARCHITECTURE.md) - high-level system and component design
- [ARCHITECTURE_1_backend.md](ARCHITECTURE_1_backend.md) - backend architecture detail
- [ARCHITECTURE_2_frontend_and_runtime.md](ARCHITECTURE_2_frontend_and_runtime.md) - frontend and packaged-runtime architecture
- [TESTING.md](TESTING.md) - how to run the tests and the coverage gate
- [TECH_DEBT.md](TECH_DEBT.md) - what is still open, what is deliberately left and what only looks like debt
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
4. Compiles the PySide6 installer package with Nuitka (onefile) from the
   root entry point [installer_main.py](installer_main.py), with
   `--include-package=installer` and the payload embedded at
   `installer/payload`, stamping the same PE metadata from `VERSION`.

   The entry point is at the repository root rather than inside the package
   because a script is compiled with its own directory on the module search
   path: compiling `installer/app.py` directly would leave the `installer.*`
   imports unresolvable. Compiling from the root also gives the payload one
   anchor that holds in both source and compiled runs.

Output: `dist-installer/EDColonisationAsstInstaller.exe`

### Build system layout

```text
buildexe.py           # runtime EXE build (Nuitka onefile)
buildinstaller.py     # payload staging + installer EXE build
installer_main.py     # installer entry point (Nuitka compiles this)
installer/
├── app.py            # composition root
├── cli.py            # --uninstall / --quiet / --help
├── constants.py      # every name written to disk or to the registry
├── ops/              # side effects, no Qt (payload, copy, shortcuts, processes)
├── state/            # HKCU record, version comparison, the state model
├── shared/           # resource anchoring and crash logging, no Qt
└── ui/               # the themed window, its dialogs, its themes and the worker thread
tests/installer/      # the setup program's suite (run from the root)
build/                # Nuitka intermediates + staged payload (gitignored)
dist-runtime/         # EDColonisationAsst.exe (gitignored)
dist-installer/       # EDColonisationAsstInstaller.exe (gitignored)
VERSION               # single source of truth for the app version
BUILD_ID              # build marker written by buildexe.py (gitignored)
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
- Dev dependencies installed in a root virtual environment, which is what
  the build scripts, the whole-suite test run and the linters use:

  ```powershell
  python -m venv venv        # or: uv venv venv
  venv\Scripts\activate
  pip install -r backend\requirements-dev.txt
  ```

  That one environment serves everything, including the backend suite run
  from `backend/`; see [PROJECT_SETUP.md](PROJECT_SETUP.md).

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
   `backend/`, `frontend/dist/` and `_uninstall/`.
3. Launch via the Start Menu / Desktop shortcut:
   - The startup splash appears (icon, author, version, live status).
   - A tray icon appears (Open Web UI / Help / Exit).
   - The browser opens `http://127.0.0.1:8000/app/` once the backend is
     actually ready.
4. No system Python or Node.js should be required.
5. Leave **Launch when finished** ticked on a fresh install and confirm the
   app comes up on its own once the installer reports success.
6. Re-run the installer with the app open: it should offer to close the
   running instance before it replaces any files, saying that the running
   session ends; the button should read Upgrade, Reinstall or Downgrade
   rather than Install. Declining the offer should abort rather than
   proceed.
7. Repair an installation that has **start when I sign in** enabled and
   confirm the tick survives, both in the window and in the Run key.
8. Uninstall from **Apps & features**, not from the downloaded installer:
   the registered uninstaller runs from inside the install directory, so
   this is the path that exercises the deferred deletion. The directory
   should be gone within a few seconds of the window closing.

---

## Backend development (FastAPI, Python)

Run these from the `backend/` directory unless noted.

### Setup

Use the root environment created above; there is nothing extra to install
under `backend/`.

```bash
venv\Scripts\activate        # Windows; source venv/bin/activate on Unix
cd backend
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

See [TESTING.md](TESTING.md). Short version, from the **repository root**:

```bash
python -m pytest -q
```

That runs the backend suite and the setup program's suite together under
one gate. Running `pytest` from `backend/` still works and
enforces the same gate on the backend alone. Either way the run fails below
100% on the gated surface; the exit code is what to read: a
coverage-gated run prints the coverage table last, so there is no "N
passed" line at the bottom.

### Code quality

From `backend/`:

```bash
black src/ tests/
isort src/ tests/
mypy src/
pylint src/
```

From the repository root, for the setup program and its suite, which are
clean under all three:

```bash
black --check installer installer_main.py tests
ruff check --isolated installer installer_main.py tests
flake8 installer installer_main.py tests
```

flake8 needs no line-length flag: `.flake8` at the repository root sets 88 to
match black.

`backend/src` is clean under both too and is linted against its own
configuration:

```bash
ruff check --config backend/pyproject.toml backend/src
flake8 backend/src
```

The pre-commit hook runs all of these, so a clean run here means a clean hook.

The front end is linted too, by ESLint:

```bash
cd frontend
npm run lint
```

`frontend/eslint.config.js` is the flat config the ESLint 9 upgrade left the
project without, which is why this script had been failing rather than
passing. It is composed only from the plugins already in devDependencies and
is deliberately not type-aware: `npm run type-check` (`tsc --noEmit`) already
runs strict over the same files and is the better tool for anything needing
types.

### Git hooks

A shared pre-commit hook lives at [.githooks/pre-commit](.githooks/pre-commit).
Enable it per clone with:

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
```

It formats staged Python files with black, lints the Python surface and the
front end, then runs a bare `pytest -q` from the repository root, which is
the full gate: both suites under the 100% coverage requirement. It resolves its interpreter from the root
`venv/`, the environment that actually carries the tooling. If that
environment is missing pytest or black it fails with a named error rather
than falling through to `PATH`.

One limit remains: it runs neither linter. That gap is recorded in
[TECH_DEBT.md](TECH_DEBT.md).

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

Use [run-edca-built.sh](run-edca-built.sh) from the project root. It creates a
venv, installs backend requirements, ensures `frontend/dist` exists and serves
everything on `http://127.0.0.1:8000/app/`.

It replaced five per-distro copies that differed only in their package-manager
hints. Those hints are now printed at runtime and only when a prerequisite is
actually missing, phrased for whichever of apt, dnf, pacman, zypper, xbps, apk
or yum is on the machine. It installs nothing itself. Debian, Ubuntu and Mint
are the tested path; the rest are UNTESTED but take the same route.

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
