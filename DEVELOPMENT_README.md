## Production release: building the Windows installer

This section summarises the end-to-end steps to produce a **production-ready**
Windows installer (`EDColonisationAsstInstaller.exe`) that:

- Installs EDCA under a user-writable directory (no admin required by default).
- Ships a self-contained runtime executable (`EDColonisationAsst.exe`) with an
  embedded Python interpreter and backend dependencies.
- Serves the pre-built frontend from FastAPI at `http://127.0.0.1:8000/app/`.
- Does **not** require end users to install Python or Node.js.

These steps are intended for **developers** preparing a release.

### Quick Windows build via batch script (recommended)

On a Windows **developer** machine, the simplest way to produce a fresh runtime
and GUI installer is to run the root-level batch script
[`build-windows-installer.bat()`](build-windows-installer.bat:1) from **PowerShell**:

```powershell
# From the project root
cd C:\Users\Oliver\Development\EDColonisationAsst
.\build-windows-installer.bat
```

Requirements (Windows developer machine):

- Windows 10/11 x64.
- Windows PowerShell 5+ or PowerShell 7+ (recommended).
- **Python 3.13+** installed and available on `PATH` (3.12 remains supported where needed).
- **Visual Studio 2022 Build Tools** with the *Desktop development with C++*
  workload (MSVC v143 toolset) and a recent Windows 10/11 SDK installed
  (see [Windows compiler requirements for Nuitka](#windows-compiler-requirements-for-nuitka)).
- **Node.js 18+** with `npm` available on `PATH` (the script checks for it and
  will fail fast if missing).
- `uv` is **not** required up front; if `uv` is not found on `PATH`, the script
  will attempt to auto-install it using the official PowerShell installer
  (`irm https://astral.sh/uv/install.ps1 | iex`). If that auto-install fails,
  the script prints a clear error and exits.

What the script does:

1. **Kill running EDCA-related processes**

   Best-effort `taskkill` calls ensure no leftover processes are holding files
   open inside the repo:

   - `EDColonisationAsst.exe`
   - `EDColonisationAsstInstaller.exe`
   - `node.exe`
   - `python.exe`

2. **Global cleanup**

   - Removes `backend\.venv` and backend `__pycache__` directories.
   - Deletes Nuitka build artefacts:
     - `build`, `build_payload`, `guiinstaller.*`, `runtime_entry.*`, etc.
   - Removes old EXEs:
     - `EDColonisationAsst.exe`
     - `EDColonisationAsstInstaller.exe`
   - Deletes logs such as:
     - `guiinstaller.log`
     - `run-edca.log`
     - `frontend-dev.log`
     - `tray.pid`
   - Cleans frontend artefacts under `frontend/`:
     - `node_modules`, `dist`, `.vite`, `.turbo`, `.cache`.

3. **Backend environment via `uv`**

   In `backend/`:

   - `uv venv .venv`
   - `uv pip install -r requirements-dev.txt`

   This prepares a dedicated backend venv containing Nuitka, PySide6,
   FastAPI, and all other build/runtime dependencies needed for packaging.

4. **Frontend build**

   In `frontend/`:

   - `npm install`
   - `npm i --package-lock-only`
   - `npm audit fix --force`
   - `npm run build` → produces `frontend/dist`.

5. **Build runtime EXE**

   Uses the backend venv Python to run
   [`buildruntime.py`](buildruntime.py:49), which invokes Nuitka to create:

   - `EDColonisationAsst.exe` – the self-contained runtime executable.

6. **Build GUI installer EXE**

   Uses the same venv Python to run
   [`buildguiinstaller.py`](buildguiinstaller.py:40), which:

   - Rebuilds the curated `build_payload/` tree (backend, frontend, runtime EXE, etc.).
   - Invokes Nuitka on [`guiinstaller.py`](guiinstaller.py:1) to produce:

     - `EDColonisationAsstInstaller.exe` – the PySide6 GUI installer.

After the script completes successfully, both EXEs are written to the project
root and are ready for smoke testing and release.

The remaining sections describe the same process in more granular, manual
steps. You can use them if you need to debug or customise specific stages.

### 1. Prerequisites (developer machine)

On the machine where you build the installer:

- Python 3.13+ installed and on `PATH` (3.12 remains supported).
- [`uv`](https://docs.astral.sh/uv/getting-started/) installed.
- Node.js + npm installed (for building the frontend only).
- A working **C/C++ toolchain** suitable for Nuitka (details in
  [Windows compiler requirements](#windows-compiler-requirements-for-nuitka) below).

### 2. Backend dependencies (dev environment)

From the **`backend/`** directory:

```bash
cd backend
uv venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
# source .venv/bin/activate

uv pip install -r requirements-dev.txt
```

This installs all backend + installer build dependencies into a local venv.

### 3. Build the frontend bundle (Vite/React)

From the **`frontend/`** directory:

```bash
cd frontend
npm install
npm run build
cd ..
```

Notes:

- `npm run build` produces `frontend/dist`, which is served by FastAPI at
  `/app`. Vite is configured with `base: '/app/'` so assets resolve under
  `/app/assets/...`.

### 4. Build the runtime EXE (embedded Python backend)

From the **project root** (`c:/Users/Oliver/Development/EDColonisationAsst`):

```bash
uv run python buildruntime.py
```

This runs [`buildruntime.py`](buildruntime.py:1), which:

- Uses Nuitka to compile [`backend/src/runtime_entry.py`](backend/src/runtime_entry.py:1)
  into a single-file EXE:
  - `EDColonisationAsst.exe` (in the project root).
- The EXE embeds:
  - Python runtime.
  - Backend code and dependencies.
- At runtime, it:
  - Starts the FastAPI app in-process on `http://127.0.0.1:8000`.
  - Serves `frontend/dist` at `http://127.0.0.1:8000/app/`.
  - Shows a tray icon with “Open Web UI” and “Exit”.

End users do **not** need Python installed when launched via this EXE.

### 5. Build the GUI installer EXE

Still from the **project root**:

```bash
uv run python buildguiinstaller.py
```

This runs [`buildguiinstaller.py`](buildguiinstaller.py:40), which:

- Ensures `frontend/dist` exists (and runs `npm run build` if not).
- Rebuilds the curated payload tree under `build_payload/`:
  - Includes:
    - `backend/` (with `.py` renamed to `.py_`).
    - `frontend/` (including `dist/`).
    - `run-edca.bat`, `EDColonisationAsst.ico`, `LICENSE`.
    - `EDColonisationAsst.exe` (runtime EXE created in step 4).
- Builds the PySide6 GUI installer via Nuitka from [`guiinstaller.py`](guiinstaller.py:1):
  - Output: `EDColonisationAsstInstaller.exe` in the project root.

### 6. Verify the installer (smoke test)

On a Windows test machine:

1. Copy `EDColonisationAsstInstaller.exe` to the machine.
2. Run it and choose **Install**:
   - Default install directory should be:
     - `%LOCALAPPDATA%\EDColonisationAssistant`
3. After install, check that the install directory contains:
   - `EDColonisationAsst.exe`
   - `backend/`, `frontend/` (with `frontend/dist`).
4. Launch EDCA via the Start Menu / Desktop shortcut:
   - The shortcut should point to `EDColonisationAsst.exe`.
   - A tray icon should appear.
   - The browser should open `http://127.0.0.1:8000/app/` and load the UI.
   - No system Python or Node.js should be required.

If all of the above succeeds, `EDColonisationAsstInstaller.exe` is ready to be
shipped as a production installer.

---

## Project layout

- Root project docs:
  - [`ARCHITECTURE.md`](ARCHITECTURE.md:1) – high-level system and component design; canonical architecture reference located alongside this file in the repository (and on GitHub).
  - [`PROJECT_SETUP.md`](PROJECT_SETUP.md:1) – additional notes and setup details
- Backend (FastAPI, Python): see **Backend development** below
- Frontend (React + TypeScript): see **Frontend development** below

---

## Backend development (FastAPI, Python)

Python FastAPI backend for the Elite: Dangerous Colonisation Assistant.

### Setup

Run these commands from the **`backend/` directory** unless otherwise noted.

1. **Install `uv` (once per machine):**

   Follow the official instructions at https://docs.astral.sh/uv/getting-started/
   (for example, via `pipx install uv` on Windows, or your preferred package manager).

2. **Create a virtual environment with `uv`:**

   ```bash
   uv venv .venv
   ```

3. **Activate the virtual environment:**

   ```bash
   # Windows (PowerShell or cmd)
   .venv\Scripts\activate

   # Linux/Mac
   source .venv/bin/activate
   ```

4. **Install dependencies with `uv`:**

   ```bash
   uv pip install -r requirements-dev.txt
   ```

4. **Configure base settings:**

   - Edit `config.yaml` to match your Elite: Dangerous installation.
   - Default journal path is typically:

     ```text
     C:\Users\%USERNAME%\Saved Games\Frontier Developments\Elite Dangerous
     ```

   - See **Configuration** below for full details.

### Commander / Inara configuration

Commander-specific and Inara secrets live in [`backend/commander.yaml`](backend/commander.yaml:1). Example:

```yaml
inara:
  app_name: "ED Colonisation Assistant"
  api_key: "INARA-API-KEY-GOES-HERE"
  commander_name: "CMDR Example"
```

Notes:

- Do **not** commit your real API key or commander name; `backend/commander.yaml` is ignored via [`.gitignore`](.gitignore:1).
- You can populate this file in two ways:
  - Via the **Settings** page in the UI (Inara API Key + Commander Name fields), which will write/update `backend/commander.yaml` for you.
  - By creating/editing `backend/commander.yaml` manually using the structure above.
- An example template is provided at [`backend/example.commander.yaml`](backend/example.commander.yaml:1).

### Running the backend

From the **`backend/` directory**:

#### Development server

```bash
uvicorn src.main:app --reload
```

or, from the **project root**:

```bash
uvicorn backend.src.main:app --reload
```

The API will be available at:

- REST API: `http://localhost:8000`
- API docs (Swagger): `http://localhost:8000/docs`
- Live updates (AJAX long-poll): `http://localhost:8000/api/changes/longpoll`

#### Production server

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

(or the equivalent `backend.src.main:app` invocation from the project root).

### Testing (backend)

From the **`backend/` directory**, with your virtual environment activated:

- To run the full backend test suite:

  ```bash
  pytest
  ```

- To run with coverage and see missing lines in the terminal:

  ```bash
  pytest --cov=src --cov-report=term-missing
  ```

- To generate an HTML coverage report (open `backend/htmlcov/index.html` in a browser):

  ```bash
  pytest --cov=src --cov-report=html
  ```

- To run a specific test file (for example, the models tests):

  ```bash
  pytest tests/unit/test_models.py -v
  ```

### Code quality (backend)

From the **`backend/` directory**:

#### Format code

```bash
black src/ tests/
isort src/ tests/
```

#### Type checking

```bash
mypy src/
```

#### Linting

```bash
pylint src/
```

### Git hooks (backend)

This repository includes a shared git pre-commit hook under
[`.githooks/pre-commit`](.githooks/pre-commit:1). When enabled, it will:

- Format any **staged** Python files with `black` and re-stage them.
- Run the backend pytest suite and block the commit if tests fail.

The hook prefers the backend virtual environment, falling back to a global
`black`/`pytest` if necessary:

- `backend/.venv/bin/python -m black` / `-m pytest` (Linux/macOS)
- `backend/.venv/Scripts/python.exe -m black` / `-m pytest` (Windows, Git Bash)
- Plain `black` / `pytest` if no backend venv Python is found.

To enable the shared hooks for **this clone only**, run once from the project root:

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
```

After that, every `git commit` will:

1. Run `black` on staged `*.py` files and re-add them to the index.
2. Run `pytest -q -c backend/pytest.ini backend/tests`.
3. Abort the commit if either step fails.

If you explicitly do **not** want the hook to enforce tests/formatting for a
specific local clone (for example, on a CI machine that already runs its own
checks), simply do not set `core.hooksPath` in that clone, or point it elsewhere.

### Backend project structure

```text
backend/
├── src/
│   ├── models/          # Data models (Pydantic)
│   ├── services/        # Business logic
│   ├── repositories/    # Data access
│   ├── api/             # API endpoints
│   ├── utils/           # Utilities
│   ├── config.py        # Configuration
│   └── main.py          # Application entry point
├── tests/
│   ├── unit/            # Unit tests
│   └── conftest.py      # Test fixtures
├── requirements.txt      # Production dependencies
└── requirements-dev.txt  # Development dependencies
```

### Backend API overview

The backend exposes REST endpoints plus a **live update** endpoint implemented as **AJAX long-polling**. Key routes (actual implementation in [`backend/src/api/routes.py`](backend/src/api/routes.py:1) and [`backend/src/api/changes.py`](backend/src/api/changes.py:1)):

#### REST

- `GET /api/health` – health check.
- `GET /api/systems` – list all systems with construction sites known locally.
- `GET /api/systems/current` – get current player system and (if docked) station.
- `GET /api/system?name={system_name}` – get colonisation data for a specific system.
- `GET /api/system/commodities?name={system_name}` – get aggregated commodities (system shopping list).
- `GET /api/sites` – get all construction sites, categorized by status.
- `GET /api/sites/{market_id}` – get a specific construction site.
- `GET /api/stats` – overall statistics.
- `POST /api/debug/reload-journals` – debug endpoint to re-parse journals from disk.
- Settings & journal:
  - `GET /api/settings`, `POST /api/settings` – get/update app settings (including journal directory and Inara config).
  - `GET /api/journal/status` – minimal view of the current system from journal files.

#### Live updates (AJAX long-poll)

`GET /api/changes/longpoll?since=<seq>&timeout_s=<seconds>` – blocks until the backend detects new journal ingestion, or until the timeout elapses.

Response:

```json
{
  "seq": 42,
  "changed": true
}
```

Client contract:

- Keep `seq` and call long-poll in a loop.
- When `changed: true`, refetch the relevant REST endpoints (usually `/api/systems` and `/api/system?name=...`).
- When `changed: false`, wait briefly and long-poll again.

### Backend architecture

The backend follows SOLID principles and a clean layered approach:

- **Models** – Pydantic models for data validation and serialization.
- **Services** – business logic:
  - Journal parser
  - File watcher
  - System tracker
  - Data aggregator
  - Inara service wrapper
- **Repositories** – data access layer (SQLite persistence via [`ColonisationRepository`](backend/src/repositories/colonisation_repository.py:65)).
- **API** – REST endpoints + live update long-poll endpoint.

Key components:

1. **Journal Parser** – parses Elite: Dangerous journal files and emits typed events.
2. **File Watcher** – monitors the journal directory and re-parses on change.
3. **System Tracker** – tracks the commander’s current system and station.
4. **Data Aggregator** – merges local journal data (and, in future, Inara data) into system/site summaries.
5. **Repository** – thread-safe, lock-protected access to persisted colonisation data in SQLite.
6. **ChangeBus** – in-process change sequence used by `/api/changes/longpoll`.

### Backend configuration

Main non-sensitive config is in [`backend/config.yaml`](backend/config.yaml:1):

```yaml
journal:
  directory: "C:\\Users\\%USERNAME%\\Saved Games\\Frontier Developments\\Elite Dangerous"
  watch_interval: 1.0

server:
  host: "0.0.0.0"
  port: 8000
  cors_origins:
    - "http://localhost:5173"

  # Note: websocket config is legacy and currently unused (live updates use AJAX long-polling).

logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

Commander/Inara settings are stored separately in [`backend/commander.yaml`](backend/commander.yaml:1); see **Commander / Inara configuration** above.

### Backend troubleshooting

- **Journal files not found**
  - Verify the path in `backend/config.yaml`.
  - Ensure Elite: Dangerous has been run at least once.
  - Check that the directory exists and is accessible.

- **Import errors**
  - Ensure the virtual environment is activated.
  - Run `uv pip install -r requirements-dev.txt` from the `backend/` directory.

- **Tests failing**
  - Check Python version (3.12+ recommended; 3.13 is the primary target).
  - Ensure all dependencies are installed.
  - Run `pytest -v` for detailed output.

---

## Frontend development (React + TypeScript)

React + TypeScript frontend for the Elite: Dangerous Colonisation Assistant.

### Setup

Run these commands from the **`frontend/` directory**.

1. **Install dependencies:**

   ```bash
   npm install
   ```

2. **Backend proxy / configuration:**

   - The frontend is configured to proxy API requests to `http://localhost:8000`.
   - Ensure the backend is running before starting the frontend (see backend section above).

### Running the frontend

From the **`frontend/` directory**:

#### Development server

```bash
npm run dev
```

The application will be available at:

- `http://localhost:5173`

#### Production build

```bash
npm run build
npm run preview
```

### Testing (frontend)

From the **`frontend/` directory**:

#### Run tests

```bash
npm test
```

#### Run tests with UI

```bash
npm run test:ui
```

#### Run tests with coverage

```bash
npm run test:coverage
```

### Frontend code quality

From the **`frontend/` directory**:

#### Type checking

```bash
npm run type-check
```

#### Linting

```bash
npm run lint
```

### Frontend project structure

```text
frontend/
├── src/
│   ├── components/      # React components
│   │   ├── SystemSelector/
│   │   └── SiteList/
│   ├── stores/          # Zustand state management
│   ├── services/        # API services
│   ├── types/           # TypeScript types
│   ├── App.tsx          # Main application
│   ├── main.tsx         # Entry point
│   └── index.css        # Global styles
├── public/              # Static assets
├── index.html           # HTML template
├── package.json         # Dependencies
├── tsconfig.json        # TypeScript config
└── vite.config.ts       # Vite config
```

### Frontend features

- **System Selector** – dropdown of all known colonisation systems (from journal data) with client-side autocomplete.
- **System View**:
  - System-level shopping list of commodities (aggregated across all sites in the selected system).
  - Per-station view: tabs for each construction site with detailed commodity progress.
- **Settings** – configure journal directory and Inara details, persisted to backend config files.
- **Color-coded status** – green for completed, orange for in-progress, etc.
- **Responsive design** – layout tuned for desktop; works on smaller screens.

### Frontend technologies

- **React 18** – UI framework.
- **TypeScript** – static typing.
- **Material-UI (MUI)** – component library.
- **Zustand** – state management.
- **Axios** – HTTP client.
- **Vite** – dev server and build tool.

### Frontend troubleshooting

- **Blank page**
  - Ensure backend is running on port `8000`.
  - Check the browser console for errors.
  - Verify `npm install` completed successfully.

- **API connection errors**
  - Verify backend is accessible at `http://localhost:8000`.
  - Check CORS settings in backend.
  - Ensure proxy configuration in `vite.config.ts` is correct.

- **Build errors**
  - Clear node_modules and lockfile:
    ```bash
    rm -rf node_modules package-lock.json
    npm install
    ```
  - Check Node.js version (18+ recommended).

---

## Running the application (developer view)

This section is aimed at **developers**. For a simplified, non‑technical quick start, see [`README.md`](README.md).

### Linux (Debian/Ubuntu/Mint): simple build + run (no Flatpak)

If you want to avoid the Flatpak build pipeline entirely, use the root-level script
[`run-edca-built-debian.sh`](run-edca-built-debian.sh:1). It will:

- Create/use a backend virtual environment (venv).
- Install backend runtime dependencies from [`backend/requirements.txt`](backend/requirements.txt:1) using `uv pip`.
- Build the production frontend into `frontend/dist` (only if Node is available and a build is needed).
- Start the backend on `http://127.0.0.1:8000`.
- Open your browser at `http://127.0.0.1:8000/app/`.

#### Prerequisites (Linux)

1) **Install uv (once per machine)**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv --version
```

2) **Install Python 3.13 locally via uv (recommended)**

Some newer distros may not yet provide `python3.13` via the default package repos.
Using `uv` avoids system package constraints and prevents Rust build issues with
older pinned dependencies (for example `pydantic-core` wheels). If your distro
cannot provide 3.13 via uv for some reason, 3.12 remains a supported fallback.

```bash
uv python install 3.13
```

3) **(Optional) Install Node.js/npm**

Node is only required if you want the script to build `frontend/dist` on this machine.
If you already have `frontend/dist` (from CI or another machine), you can skip Node
and run with `EDCA_SKIP_FRONTEND_BUILD=1`.

#### Run (one command)

Recommended first run (Debian default: use system Python 3.13 if available):

```bash
./run-edca-built-debian.sh
```

If you want to force a specific Python, use uv-managed Python 3.13:

```bash
EDCA_PYTHON=python3.13 EDCA_VENV_DIR=.venv313 ./run-edca-built-debian.sh
```

If you do not have Node installed and also do not have `frontend/dist` yet, the script
will error with a clear message. In that case either:

- Install Node and build once:
  ```bash
  npm --prefix frontend ci
  npm --prefix frontend run build
  ```
  then rerun `./run-edca-built-debian.sh`, or

- Copy a prebuilt `frontend/dist` into `./frontend/dist` and run:
  ```bash
  EDCA_PYTHON=python3.12 EDCA_VENV_DIR=.venv312 EDCA_SKIP_FRONTEND_BUILD=1 ./run-edca-built-debian.sh
  ```

#### Useful environment variables

- Change host/port:
  ```bash
  EDCA_HOST=127.0.0.1 EDCA_PORT=8000 ./run-edca-built-debian.sh
  ```
- Recreate the venv if it was created with the wrong Python version:
  ```bash
  EDCA_PYTHON=python3.13 EDCA_VENV_DIR=.venv313 EDCA_RECREATE_VENV=1 ./run-edca-built-debian.sh
  ```

This workflow intentionally prioritizes simplicity and avoiding heavyweight packaging steps.
It is suitable for local development, smoke testing, and demos on Linux.

### Linux (other distros): helper scripts (UNTESTED)

The following scripts are provided as convenience entry points for other distributions, but are **UNTESTED**:

- Fedora: [`run-edca-built-fedora.sh`](run-edca-built-fedora.sh:1) (UNTESTED)
- Arch: [`run-edca-built-arch.sh`](run-edca-built-arch.sh:1) (UNTESTED)
- RHEL/Rocky/Alma: [`run-edca-built-rhel.sh`](run-edca-built-rhel.sh:1) (UNTESTED)
- Void: [`run-edca-built-void.sh`](run-edca-built-void.sh:1) (UNTESTED)

They follow the same overall approach as [`run-edca-built-debian.sh`](run-edca-built-debian.sh:1) (uv + Python 3.13 via uv by default, with 3.12 as a supported fallback, optional Node for building `frontend/dist`) but include distro-specific prerequisite hints.

### Root‑level launch scripts

From the **project root**, you can use the same scripts that non‑developers use:

- Windows: [`run-edca.bat`](run-edca.bat)
- Linux / macOS: [`run-edca.sh`](run-edca.sh)

These scripts will:

- Ensure Python backend dependencies from [`backend/requirements.txt`](backend/requirements.txt:1) are installed.
- Ensure frontend dependencies in [`frontend/package.json`](frontend/package.json:1) are installed.
- Start the backend API (FastAPI + Uvicorn) on `http://localhost:8000`.
- Start the frontend (Vite + React) on `http://localhost:5173`.

They are convenient for quick local runs, smoke tests and demos.

### Manual launch from project root

If you prefer explicit commands but don’t want to `cd` into subfolders, you can start both services from the **project root**:

```bash
# Terminal 1 – backend (FastAPI, reload for development)
uvicorn backend.src.main:app --reload
```

Backend will be available at:

- API:  http://localhost:8000
- Docs: http://localhost:8000/docs
- Live updates: http://localhost:8000/api/changes/longpoll

```bash
# Terminal 2 – frontend (Vite + React)
npm --prefix frontend run dev
```

Frontend will be available at:

- http://localhost:5173

These commands are essentially what the launch scripts wrap, but without dependency checks.

### Manual launch from subdirectories

For more traditional workflows:

- Backend: see **Backend development** above (run from [`backend/`](backend:1), usually with a virtualenv).
- Frontend: see **Frontend development** above (run from [`frontend/`](frontend:1)).

Those sections show `uvicorn src.main:app --reload` and `npm run dev` from within each subproject.

## Windows GUI installer build (current pipeline)

This section documents the concrete Windows build pipeline that produces the
self-contained GUI installer executable (`EDColonisationAsstInstaller.exe`)
using Nuitka and the PySide6-based installer UI in
[`guiinstaller.py`](guiinstaller.py:1).

The resulting installer:

- Installs EDCA into a **user-writable directory** under
  `%LOCALAPPDATA%\EDColonisationAssistant` by default (no elevation required).
- Ships:
  - `EDColonisationAsst.exe` – the self-contained runtime executable built
    from [`backend/src/runtime_entry.py`](backend/src/runtime_entry.py:1) via
    [`buildruntime.py`](buildruntime.py:49). This embeds the Python runtime and
    backend dependencies and is the primary entrypoint for end users.
  - Pre-built frontend assets (`frontend/dist`) served by FastAPI at `/app`.
  - Backend configuration and support files (for example
    [`backend/config.yaml`](backend/config.yaml:1) and
    [`backend/example.commander.yaml`](backend/example.commander.yaml:1)).
  - Developer-oriented scripts such as [`run-edca.bat`](run-edca.bat:1),
    [`backend/src/launcher.py`](backend/src/launcher.py:1) and
    [`backend/src/tray_app.py`](backend/src/tray_app.py:1) for advanced and
    legacy workflows; these are **not** used by the Start Menu / Desktop
    shortcuts created by the installer.
- Does **not** require Python or Node.js/npm on the end-user machine at runtime.

### Prerequisites (developer machine)

On the **developer** machine (where you build the installer):

- Python 3.12+ installed and on `PATH`.
- [`uv`](https://docs.astral.sh/uv/getting-started/) installed.
- Node.js + npm installed (for building the frontend only).
- A supported C/C++ toolchain for Nuitka (see
  [Windows compiler requirements for Nuitka](#windows-compiler-requirements-for-nuitka)).
- Python dependencies installed (from the project root or `backend/`):

  ```bash
  # From backend/ (recommended)
  cd backend
  uv venv .venv
  .venv\Scripts\activate   # or source .venv/bin/activate on Unix
  uv pip install -r requirements-dev.txt
  ```

  The `backend/requirements-dev.txt` file includes all backend and installer
  build dependencies, including **Nuitka**. Nuitka is required for:

  - [`buildruntime.py`](buildruntime.py:49) → builds `EDColonisationAsst.exe`
  - [`buildguiinstaller.py`](buildguiinstaller.py:40) → builds `EDColonisationAsstInstaller.exe`

  The dev requirements include FastAPI, PySide6, and other libraries used by
  the backend and installer.

### Windows compiler requirements for Nuitka

Nuitka compiles Python code to C/C++ and then uses a platform C/C++ compiler.
On Windows, this project is tested and supported with **MSVC**, not Cygwin GCC.

**For Python 3.13 (current default backend version):**

- Nuitka requires **MSVC 14.3 (v143 toolset) or later**.
- This is provided by **Visual Studio 2022 Build Tools**:

  1. Download the Build Tools installer from Microsoft:

     - Direct link: `https://aka.ms/vs/17/release/vs_BuildTools.exe`

  2. Run the installer and for **Visual Studio Build Tools 2022** choose:

     - Workload: **Desktop development with C++**
     - Verify in the *Individual components* tab that these are installed:
       - **MSVC v143 - VS 2022 C++ x64/x86 build tools**
       - A recent **Windows 10 SDK** or **Windows 11 SDK**

- MSVC 14.2 (Visual Studio 2019, v142 toolset) is **not sufficient** for
  Python 3.13; Nuitka will fail with an error similar to:

  > `Nuitka-Scons: For Python version 3.13 MSVC 14.3 or later is required, not 14.2 which is too old.`

**If you choose to build with Python 3.11 or 3.12 instead of 3.13:**

- Nuitka can still use **MSVC 14.2 (v142)**.
- You must ensure the backend venv is explicitly created with a Python 3.11
  interpreter, for example:

  ```powershell
  cd backend
  uv venv .venv --python=python3.11
  .venv\Scripts\activate
  uv pip install -r requirements-dev.txt
  ```

- The rest of the build pipeline (`buildruntime.py`, `buildguiinstaller.py`,
  `build-windows-installer.bat`) stays the same; only the Python version used
  by Nuitka changes.

**GCC / MinGW-w64 notes (advanced):**

- Nuitka can also target **MinGW-w64** (GCC) on Windows, but this project is
  currently configured and tested with MSVC only.
- Cygwin GCC is **not** supported for this build; installing Cygwin does not
  satisfy Nuitka’s MSVC requirement for Python 3.12.
- If you decide to experiment with MinGW-w64, follow Nuitka’s official
  documentation and update the build scripts accordingly; this is out of scope
  for the default EDCA build pipeline.

### 1. Build the frontend (Vite/React)

From the **`frontend/`** directory:

```bash
cd frontend
npm install
npm run build
```

- `npm install` – installs frontend dependencies as declared in
  [`frontend/package.json`](frontend/package.json:1).
- `npm run build` – runs `tsc && vite build`, producing a static bundle in
  `frontend/dist/`.

Notes:

- Tests under `src/**/*.test.tsx` are **excluded** from the production
  TypeScript build via [`tsconfig.json`](frontend/tsconfig.json:1), so you
  don’t need Jest typings just to build.
- Re-run `npm run build` whenever you change frontend code and before
  rebuilding the installer.

### 2. Build the GUI installer executable

From the **project root** (`c:/Users/Oliver/Development/EDColonisationAsst`):

```bash
uv run python buildguiinstaller.py
```

This runs [`build_installer()`](buildguiinstaller.py:40), which:

1. Rebuilds a curated payload tree under `build_payload/` via
   [`_ensure_payload_dir`](buildguiinstaller.py:141):

   - Copies `backend/` and `frontend/`, including `frontend/dist/`.
   - Excludes dev artefacts such as `.git`, `.venv`, `node_modules`,
     `__pycache__`, tests, coverage output, etc.
   - Renames backend `*.py` files in `build_payload/backend/src` to `*.py_`
     so Nuitka doesn’t treat them as importable modules rather than data.

2. Writes a `VERSION` file from [`backend/src/__init__.py`](backend/src/__init__.py:1)
   so the installer can display the correct version in its UI.

3. Invokes Nuitka with the PySide6 plugin to compile
   [`guiinstaller.py`](guiinstaller.py:1) into a single-file executable:

   - Includes the `build_payload` directory as bundled data:
     `--include-data-dir=build_payload=payload`.
   - Bundles `LICENSE` and `VERSION` alongside the executable.

On success, it produces:

- `EDColonisationAsstInstaller.exe` in the **project root**.

### 3. Install / repair using the GUI installer

Run `EDColonisationAsstInstaller.exe` on Windows:

- The default install directory (shown in the installer window) is:

  ```text
  %LOCALAPPDATA%\EDColonisationAssistant
  ```

  This is computed by [`get_default_install_dir()`](guiinstaller.py:154) and
  avoids `C:\Program Files\...` so that standard (non-admin) accounts can
  install and run EDCA without elevation.

- Actions:

  - **Install** – copies the curated payload from `payload/` into the install
    directory, restoring backend `*.py_` back to `*.py` via
    [`InstallerWindow._copy_tree`](guiinstaller.py:781), and (on Windows)
    creates Start Menu / Desktop shortcuts and an Add/Remove Programs entry.
  - **Repair** – overwrites files from the bundled payload into the existing
    install directory and recreates shortcuts if needed.
  - **Uninstall** – stops the tray (via `tray.pid` and `taskkill`), removes
    the install directory, removes shortcuts, and unregisters the app.

### 4. Runtime behaviour of the installed app

After installation:

- The Start Menu / Desktop shortcuts created by the installer point directly
  to `EDColonisationAsst.exe` in the install directory.

- `EDColonisationAsst.exe` is a Nuitka-built wrapper around
  [`RuntimeApplication`](backend/src/runtime_entry.py:280):

  - It detects that it is running in **FROZEN** mode via
    [`get_runtime_mode()`](backend/src/utils/runtime.py:36).
  - It starts an in-process `uvicorn.Server` hosting the FastAPI app from
    [`backend/src/main.py`](backend/src/main.py:1) on
    `http://127.0.0.1:8000` using
    [`BackendServerController`](backend/src/runtime_entry.py:87).
  - It waits for the backend and static frontend to become available at:

    - `http://127.0.0.1:8000/api/health`
    - `http://127.0.0.1:8000/app/`

    via [`wait_until_ready()`](backend/src/runtime_entry.py:128).

  - It shows a system tray icon managed by
    [`TrayUIController`](backend/src/runtime_entry.py:205) with **Open Web UI**
    and **Exit** actions.
  - On first launch it automatically opens the default browser to:

    ```text
    http://127.0.0.1:8000/app/
    ```

- [`main.py`](backend/src/main.py:1) mounts the pre-built frontend as static
  files:

  ```python
  from fastapi.staticfiles import StaticFiles

  PROJECT_ROOT = Path(__file__).resolve().parents[2]
  frontend_dist = PROJECT_ROOT / "frontend" / "dist"

  if frontend_dist.exists():
      app.mount(
          "/app",
          StaticFiles(directory=frontend_dist, html=True),
          name="frontend",
      )
  ```

  This means:

  - The frontend is served directly by FastAPI from the bundled `dist/`
    assets.
  - No Vite dev server (`npm run dev`) is started at runtime.
  - End users do **not** need Node.js or npm installed at all.

### 5. Summary of the full Windows build → install → run flow

Developer steps:

1. Backend dev dependencies:

   ```bash
   cd backend
   uv venv .venv
   .venv\Scripts\activate      # or Unix equivalent
   uv pip install -r requirements-dev.txt
   ```

2. Frontend build:

   ```bash
   cd ../frontend
   npm install
   npm run build
   ```

3. Build installer:

   ```bash
   cd ..
   uv run python buildguiinstaller.py
   ```

4. Ship/execute `EDColonisationAsstInstaller.exe`.

User steps:

1. Run `EDColonisationAsstInstaller.exe` and click **Install**.
2. Use the Start Menu / Desktop shortcut “Elite: Dangerous Colonisation
   Assistant”.
3. Wait for the launcher to report “Ready” and click “Open Web UI”.

No additional tools (Python, Node, npm, Vite) are required on the user’s
machine; they are either embedded (Python via venv + bundled deps) or the
artifacts are pre-built (frontend `dist`).

---

## Bundling / distribution (high level)

It *is* possible to bundle the entire application as a local launchable program on Windows, Linux and macOS, but this requires OS‑specific build pipelines. At a high level:

### 1. Build the frontend

Produce a static bundle:

```bash
cd frontend
npm run build
```

This outputs static assets in `frontend/dist/` which can be:

- Served by FastAPI using `StaticFiles`, or
- Served by an external web server (NGINX, Apache, Caddy, etc).

A typical FastAPI mounting (example only) would live in [`backend/src/main.py`](backend/src/main.py:81):

```python
from fastapi.staticfiles import StaticFiles

app.mount(
    "/app",
    StaticFiles(directory="frontend/dist", html=True),
    name="frontend",
)
```

You can choose whether to expose the UI at `/` or under a path like `/app`.

### 2. Package backend + static frontend per OS

Regardless of OS, the bundle needs:

- Python runtime (if you don’t embed it).
- Backend code: [`backend/src/`](backend/src:1) and configs such as [`backend/config.yaml`](backend/config.yaml:1).
- Persistence: SQLite database created/used by [`ColonisationRepository`](backend/src/repositories/colonisation_repository.py:64).
- Static frontend: `frontend/dist/`.

**Windows options (Python‑centric):**

- Use a “freezer” tool (one of):
  - PyInstaller
  - cx_Freeze
  - PyOxidizer
- Package the FastAPI app (plus `frontend/dist`) into:
  - A self‑contained executable, or
  - An installable directory with a launcher EXE.
- Entry point:
  - Run Uvicorn against `backend.src.main:app` (see [`backend/src/main.py`](backend/src/main.py:119)).
- Optional:
  - MSI / Inno Setup installer.
  - Start‑menu / desktop shortcuts that open the default browser at `http://localhost:8000` or the mounted frontend URL.

**Linux options:**

- Similar to Windows but per‑distro / per‑arch builds:
  - PyInstaller binary.
  - Native packages (`.deb`, `.rpm`) that:
    - Install Python runtime + dependencies.
    - Install `frontend/dist`.
    - Configure a systemd service that runs `uvicorn backend.src.main:app`.
- Optional:
  - A `.desktop` file to open the default browser pointing at the local URL.

**macOS options:**

- Use a bundler that can produce a `.app` bundle (e.g. Briefcase or PyInstaller with macOS support).
- Inside the `.app`:
  - Embed Python, backend code, config and `frontend/dist`.
  - Start the FastAPI/Uvicorn process on app launch.
  - Use `open http://localhost:8000` (or the chosen URL) to open the browser automatically.

### 3. All‑in‑one desktop app wrappers

If you prefer a single desktop window rather than “browser + local server”, you can wrap the existing HTTP API (REST + long-poll) with:

- Electron
- Tauri
- Neutralino

In this model:

- The React UI runs inside the desktop shell.
- It communicates with the Python backend over:
  - `http://localhost:8000` (REST) and `http://localhost:8000/api/changes/longpoll` (AJAX live updates), or
  - Embedded Python bindings (more complex).

Pros:

- Single icon and window, feels more “native”.

Cons:

- Extra tooling complexity (build pipelines per platform).
- Larger runtime (especially with Electron).
- You still maintain the Python backend.

### Recommended path for this project

For this repository, a pragmatic evolution is:

1. **Short term** – keep using:
   - [`run-edca.bat`](run-edca.bat) on Windows.
   - [`run-edca.sh`](run-edca.sh) on Linux/macOS.
2. **Medium term** – serve `frontend/dist` from FastAPI and ship:
   - Per‑OS “frozen” backend binaries that embed the static frontend.
3. **Long term** – if desired, wrap the existing API in an Electron/Tauri shell for a single‑window experience.

---

## GameGlass integration

This project includes assets intended for GameGlass shard integration under:

- [`frontend/src/gameglass/`](frontend/src/gameglass:1)

For detailed API usage, endpoints, and layout guidance for shards, see:

- [`GameGlass-Integration.md`](GameGlass-Integration.md:1)

That document describes:

- How to call the backend APIs from a GameGlass-embedded web app.
- Which endpoints to use for system/site lists and aggregated commodity “shopping lists”.
- How to consume the `/api/changes/longpoll` endpoint for live updates.
