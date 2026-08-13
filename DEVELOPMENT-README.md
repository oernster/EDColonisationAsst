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
- **Python 3.13** for a release build. The application itself runs on
  3.11 or newer (`requires-python` in `backend/pyproject.toml`); the
  shipped Windows binary is compiled on 3.13.
- **Visual Studio 2022 Build Tools** with the *Desktop development with C++*
  workload (MSVC v143) and a recent Windows 10/11 SDK; see the compiler
  notes below.
- **Node.js 20.19+** with npm (frontend build only; never needed by end
  users). That is the floor Vite declares in its own `engines`; 22.12+
  also qualifies.
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
   - The browser opens `http://127.0.0.1:47021/app/` once the backend is
     actually ready.
4. No system Python or Node.js should be required.
5. Leave **Launch when finished** ticked on a fresh install and confirm the
   app comes up on its own once the installer reports success. The window
   closes itself only on a launch that actually happened: if the start fails,
   it stays open and reports the path to start from instead.
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

## Building the Linux release (one command)

```bash
./build_flatpak.sh             # build, install locally and write the bundle
./build_flatpak.sh --no-bundle # build and install only
```

Run it from the project root on a Linux machine. It installs `flatpak` and
`flatpak-builder` through whichever of apt, dnf, pacman or zypper is present.
Node is needed only if `frontend/dist` has to be built.

### What build_flatpak.sh does

It targets `org.freedesktop.Platform//25.08`, which ships Python 3.13. Nothing
is compiled: the sandbox already provides its own interpreter and every
dependency, which is the condition the frozen Windows build satisfies by other
means, so what is packaged is the source tree. Inside the sandbox EDCA
therefore takes the same path as the packaged Windows runtime, uvicorn
in-process behind a Qt tray icon, rather than the source-checkout path of
building a virtual environment and spawning processes.

In order, the script:

1. Checks its tools, then creates or reuses a build virtualenv at
   `backend/.venv` (the same default `run-edca-built.sh` uses) and puts Pillow
   in it. Pillow is a build dependency only; the application never imports it.
2. Builds `frontend/dist` if it is missing. This is a hard failure rather than a
   warning when Node is absent, because a Flatpak built without it installs
   cleanly, starts cleanly and then serves nothing.
3. Downloads the wheels named in
   [backend/requirements-flatpak.txt](backend/requirements-flatpak.txt) on the
   host, tagged for Python 3.13 and manylinux, then installs them inside the
   sandbox with `--no-index`. The build never reaches the network.
4. Derives the hicolor icon set from `EDColonisationAsst.png`. Every size is a
   downscale of that master and nothing is ever resampled upwards, so the set
   stops at 256: the master is 343px.
5. Writes the manifest, the launcher, the `.desktop` entry and the
   `.metainfo.xml` from heredocs. None of them is committed; only the script is.
6. Builds, installs for the current user and writes
   `edcolonisationasst.flatpak`.

`./cleanup_flatpak.sh` undoes all of it and uninstalls the app. It touches
nothing belonging to the Windows or the run-from-source paths, so the delivery
routes stay independent. `--keep-installed` clears the artefacts and leaves the
app; `--purge-data` additionally deletes `~/.var/app/<app-id>`, which is opt-in
because that is where the commander's database lives.

### Why the requirements file is its own

[backend/requirements-flatpak.txt](backend/requirements-flatpak.txt) mirrors
`backend/requirements.txt` with two differences, both forced rather than chosen:

- Nuitka and shiboken6 are absent. Nuitka builds the Windows executable and is
  never imported at runtime; shiboken6 arrives with PySide6.
- PyYAML is 6.0.3 rather than 6.0.1. The runtime ships Python 3.13 and 6.0.1
  published no wheel for it, not even a pure-Python one, so the offline download
  fails outright rather than falling back.

### What the sandbox is granted

Every permission in `finish-args` is there for a named reason:

| Grant | Why |
|---|---|
| `--share=ipc`, `--socket=fallback-x11`, `--socket=wayland`, `--device=dri` | Qt needs a display for the tray and the splash |
| `--share=network` | the interface is an HTTP server the user opens in a browser, including from a tablet on the same network |
| `--filesystem=home` | the journal lives in the game's Wine or Proton prefix; the settings page can repoint it |
| `--filesystem=~/.var/app/com.valvesoftware.Steam:ro` | a Flatpak Steam keeps its Proton prefixes there; `--filesystem=home` deliberately excludes it |
| `--talk-name=org.kde.StatusNotifierWatcher` | a Linux tray icon is published over D-Bus and drawn by the desktop's watcher, which is unreachable from the sandbox without this |

### What runs where inside the sandbox

The application is staged in its source layout under
`/app/share/edcolonisationasst`, `backend/src` beside `frontend/dist`, because
that is the layout the backend resolves its own project root from. The launcher
at `/app/bin/edcolonisationasst` sets `PYTHONPATH`, the Qt plugin paths and:

- `EDCA_PROJECT_ROOT`, because inside the sandbox `sys.argv[0]` is the launcher
  rather than the staged directory, so the tray cannot find the icon by
  guessing.
- `RESOURCE_NAME`, which is the instance half of `WM_CLASS` on X11. Qt derives
  it from the executable when it is unset. In here the executable is
  `python3`.

`/app` is read-only, so everything EDCA writes goes to the per-user data
directory instead: see
[`user_data.py`](backend/src/utils/user_data.py) and section 2.5 of
[ARCHITECTURE_2_frontend_and_runtime.md](ARCHITECTURE_2_frontend_and_runtime.md).

### Testing it

Nothing about the Flatpak can be verified from Windows beyond shell syntax and
the generated files, so the first build on a Linux machine is where surprises
belong. Worth checking beyond "it starts":

1. The tray icon appears. If it does not, the control window should have
   appeared in its place, which is the tray-availability fallback working.
2. The dock shows one entry rather than two, which is the desktop identity
   matching.
3. Saving a journal directory on the Settings page succeeds, which is the
   writable-path work.

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
uvicorn src.main:app --reload --port 47021
```

or from the project root: `uvicorn backend.src.main:app --reload --port 47021`.

The `--port` flag matters: the uvicorn CLI defaults to 8000 and does not read
the configured port (only the `python -m src.main` path does), so without it
the frontend dev proxy cannot reach the backend.

- REST API: `http://localhost:47021`
- Swagger docs: `http://localhost:47021/docs`
- Live updates (AJAX long-poll): `http://localhost:47021/api/changes/longpoll`

### Configuration

Non-sensitive config lives in [backend/config.yaml](backend/config.yaml)
(server host/port, CORS, logging). It names **no journal directory**, on
purpose: the file is tracked, so a path written into it is one machine's path
shipped to everybody; the one that used to be there pointed at a Linux
Steam Proton prefix. The directory is detected instead; set the key only to
override that. The dormant Inara configuration lives in
`backend/commander.yaml`, which is gitignored and hand-created from
[backend/example.commander.yaml](backend/example.commander.yaml); no shipped
feature reads it, so the Settings UI does not expose it. Do not commit real
API keys. The commander's name is not stored anywhere: it is read from the
journal files (`/api/journal/status`).

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
uvicorn backend.src.main:app --reload --port 47021

# Terminal 2: frontend
npm --prefix frontend run dev
```

Or use the convenience scripts [run-edca.bat](run-edca.bat) /
[run-edca.sh](run-edca.sh), which install dependencies and start both.

### Linux

Use [run-edca-built.sh](run-edca-built.sh) from the project root. It creates a
venv, installs backend requirements, ensures `frontend/dist` exists and serves
everything on `http://127.0.0.1:47021/app/`.

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

#### Distributions and desktops the script has not seen

The script's package hints cover the common package managers, which is a
different thing from covering the common systems. What follows names what EDCA
actually needs rather than which package provides it, because that answer
differs on every distribution and on some of them the usual answer is wrong.

What it needs is short:

- **Python 3.11 or newer.** That is the floor `backend/pyproject.toml` declares.
  The convenience scripts still say 3.10 in their prompts, which is older than
  the package metadata allows.
- **Node 20.19 or newer, only to build the front end.** Set
  `EDCA_SKIP_FRONTEND_BUILD=1` against a prebuilt `frontend/dist` and Node is
  not needed at all.
- **A browser**, because the UI is a web page rather than a window.
- **Qt, only for the tray icon and the splash.** See below: it is optional in a
  way that is worth knowing.

#### Desktop environments other than GNOME

A system tray is not something a Linux desktop owes anyone. The icon is not
drawn by EDCA at all: it is published over D-Bus as a StatusNotifierItem and
the desktop's own watcher draws it. A GNOME session provides no watcher without
an extension, Ubuntu ships that extension enabled, KDE, XFCE, MATE, Cinnamon and
LXQt each provide one by their own route; any of them can have it turned
off.

**EDCA does not depend on it.** This is the useful difference between EDCA and a
tray-only application: the entire interface is a web page, so where no icon
appears the app is still running and still completely usable. Open
`http://127.0.0.1:47021/app/` and bookmark it. Nothing is lost but the
convenience of the menu.

The packaged runtime asks rather than assuming. `TrayUIController` calls
`QSystemTrayIcon.isSystemTrayAvailable()` when it is built. Where the answer
is no it shows a small control window instead, carrying the same Open Web UI,
the same Help menu and the same Exit, plus a line saying why it is there.
Closing that window is the same request as pressing Exit. Running from source
through `run-edca-built.sh` takes the no-Qt path below and has no tray at all,
by design.

If the splash or the tray behave oddly under Wayland, forcing the X11 path
through XWayland is the first thing to try:

```bash
QT_QPA_PLATFORM=xcb ./run-edca-built.sh
```

#### Running with no Qt at all

On a distribution where PySide6 is difficult, skip it. The backend is a plain
FastAPI application that imports no Qt whatsoever, so it can be run directly and
used entirely through the browser:

```bash
python -m uvicorn backend.src.main:app --host 127.0.0.1 --port 47021
```

Then open `http://127.0.0.1:47021/app/`, which needs `frontend/dist` to have
been built at least once. What you give up is the tray icon and the splash. What
you keep is every feature, because all of them live in the web UI.

That matters most where the PySide6 wheel is the problem rather than the
project. `pip install PySide6` fetches a wheel built for a conventional
filesystem layout, one with an interpreter and loader at fixed paths and shared
libraries on a global search path. A distribution not built that way, NixOS
being the clear case, installs the wheel perfectly happily and then fails to
import it, which reads as a broken package rather than as a mismatched
assumption. The answer there is either to take Qt for Python from the
distribution instead of from pip or to run inside an environment providing the
conventional layout. That is a question about your distribution rather than
about EDCA. Or, given the above, to not install it at all.

Two commands tell the possible causes apart:

```bash
python -c "import PySide6.QtWidgets; print('Qt imports')"
```

```bash
QT_DEBUG_PLUGINS=1 python -m backend.src.tray_app
```

The first separates a Python-level import failure from a Qt-level one. The
second makes Qt name every platform plugin it tried and why it rejected each,
which is what to read when the import succeeds and nothing appears on screen.

---

## Runtime behaviour of the installed app

The Start Menu / Desktop shortcuts point at `EDColonisationAsst.exe`, which:

- Detects FROZEN mode and starts an in-process `uvicorn.Server` hosting the
  FastAPI app on `http://127.0.0.1:47021`. That port is a preference, not a
  promise: the port a previous run recorded is tried first, then the configured
  one, then the remaining candidates, then whatever the operating system will
  give, because
  Windows reserves whole ranges and can make a port unbindable while it looks
  unused. Whatever is chosen is recorded, so the address stays put across runs.
- Shows the startup splash immediately (icon, author, version, live status and
  a progress bar) and polls readiness without blocking the UI. On a first run
  the splash reports the journal import stage by stage, measured in bytes read.
- Serves the bundled frontend at `http://127.0.0.1:47021/app/` and opens the
  browser only once both the health endpoint and the web UI respond.
- Provides a tray icon with Open Web UI, a Help submenu (About plus
  Check for Updates) and Exit. Where the desktop reports no system tray,
  a small control window carrying the same actions appears instead.
- Started with `--no-browser` (login autostart), it stays silent: no splash
  and no browser.

See [ARCHITECTURE_2_frontend_and_runtime.md](ARCHITECTURE_2_frontend_and_runtime.md)
for the full runtime architecture.

---

## GameGlass integration

GameGlass shard assets live under `frontend/src/gameglass/`. For endpoints,
layout guidance and the long-poll contract, see
[GameGlass-Integration.md](GameGlass-Integration.md).
