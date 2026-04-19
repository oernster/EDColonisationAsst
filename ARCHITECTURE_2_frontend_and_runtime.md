# Elite: Dangerous Colonisation Assistant – Frontend & Runtime Architecture

This document complements [`ARCHITECTURE_1_backend.md`](ARCHITECTURE_1_backend.md:1) by focusing on:

- The **React/TypeScript frontend** that consumes the backend APIs.
- The **runtime/launcher/tray stack** and single‑instance behaviour.
- How everything is packaged and run on users’ machines.

---

## 1. Frontend architecture

### 1.1 Technology stack

- **Framework**: React 18 with TypeScript
- **State management**: Zustand
- **UI components**: Material‑UI (MUI)
- **HTTP client**: Axios
- **Build tool / dev server**: Vite
- **Testing**:
  - Vitest
  - React Testing Library

### 1.2 Project structure (frontend)

```text
frontend/
├── index.html                    # Root HTML template
├── package.json                  # NPM scripts and dependencies
├── tsconfig.json                 # TypeScript config
├── vite.config.ts                # Vite config (incl. dev proxy to backend)
└── src/
    ├── main.tsx                  # React entry point
    ├── App.tsx                   # Top‑level app component
    ├── index.css                 # Global styles
    ├── components/
    │   ├── SystemSelector/
    │   │   └── SystemSelector.tsx
    │   ├── SiteList/
    │   │   └── SiteList.tsx
    │   ├── FleetCarriers/
    │   │   └── FleetCarriersPanel.tsx
    │   └── Settings/
    │       └── SettingsPage.tsx
    ├── services/
    │   └── api.ts                # Axios client and typed API helpers
    ├── stores/
    │   ├── colonisationStore.ts  # Zustand store for colonisation data
    │   └── carrierStore.ts       # Zustand store for Fleet carrier data
    ├── hooks/
    │   └── (no websocket hooks; live updates use AJAX long-poll in App)
    ├── types/
    │   ├── colonisation.ts       # Shared frontend types for colonisation data
    │   ├── fleetCarriers.ts      # Types for Fleet carrier data
    │   └── settings.ts           # Types for settings/Inara config
    ├── gameglass/
    │   ├── app.js
    │   ├── index.html
    │   └── style.css
    └── test/
        └── setup.ts              # Vitest + Testing Library setup
```

### 1.3 Data flow (frontend)

The frontend talks to the backend over HTTP (REST + AJAX long-polling), using helpers in [`api.ts`](frontend/src/services/api.ts:1).

- **Initial data via REST**:
  - `/api/systems` – for the system selector.
  - `/api/system` – `SystemColonisationData` for the selected system.
  - `/api/system/commodities` – aggregated per‑commodity “shopping list”.
  - `/api/journal/status` – journal/latest‑file status.
  - `/api/settings` – app/journal/Inara settings.
  - `/api/carriers/*` – Fleet carrier identity and state.

- **Live updates via AJAX long-polling**:
  - The UI holds a request open to `GET /api/changes/longpoll?since=<seq>`.
  - When the backend ingests journal changes it bumps an in-process sequence and the long-poll returns immediately.
  - The UI then refetches `/api/systems` and `/api/system?name=<current>`.

State is centralised in two Zustand stores:

- [`colonisationStore`](frontend/src/stores/colonisationStore.ts:1)
  - `currentSystem`, `systemData`, `allSystems`, `loading`, `error`, `currentSystemInfo`, `settingsVersion`.
  - Actions to set the current system, update system data, and update the system list.

- [`carrierStore`](frontend/src/stores/carrierStore.ts:1)
  - `currentCarrierInfo`, `currentCarrierState`, `myCarriers`, loading/error flags.
  - Actions that call:
    - `/api/carriers/current`
    - `/api/carriers/current/state`
    - `/api/carriers/mine`

### 1.4 Key components

- **SystemSelector** – [`SystemSelector.tsx`](frontend/src/components/SystemSelector/SystemSelector.tsx:1)

  - Renders an autocomplete/dropdown of known systems.
  - Uses `/api/systems` and `/api/systems/search`.
  - Updates the selected system in `colonisationStore` and triggers fetch/subscription.

- **SiteList & SiteCard** – [`SiteList.tsx`](frontend/src/components/SiteList/SiteList.tsx:1)

  - Shows a **system summary**, **system shopping list** and **per‑station cards**.
  - Reads `systemData` from `colonisationStore`:
    - Uses an internal `aggregateCommodities` helper to re‑aggregate commodities for the **System Shopping List**.
    - Displays per‑commodity and per‑site progress with MUI progress bars and chips.

- **FleetCarriersPanel** – [`FleetCarriersPanel.tsx`](frontend/src/components/FleetCarriers/FleetCarriersPanel.tsx:1)

  - “Fleet Carriers” tab in the UI.
  - Uses `carrierStore` to:
    - Load `currentCarrierInfo` and `currentCarrierState` (only while docked at a Fleet carrier).
    - Load `myCarriers` (inferred from journal `CarrierStats` + `CarrierLocation`).
  - Presents:
    - Current docked carrier identity and services.
    - Derived cargo snapshot and buy/sell orders from `CarrierTradeOrder` events.
    - A list of known owned/squadron carriers.

- **SettingsPage** – [`SettingsPage.tsx`](frontend/src/components/Settings/SettingsPage.tsx:1)

  - Uses `/api/settings` to:
    - Read and update journal directory.
    - Configure Inara/commander settings.
  - Writes back to the backend, which persists to YAML.

- **App / main** – [`App.tsx`](frontend/src/App.tsx:1), [`main.tsx`](frontend/src/main.tsx:1)

  - Compose the overall layout and route tabs/screens.
  - Initialise stores and start the AJAX long-poll live update loop.

---

## 2. Runtime, launcher and tray architecture

Beyond the FastAPI server, the project ships a **runtime stack** that:

- Ensures **single‑instance** behaviour per OS user.
- Starts backend and frontend services in a friendly way for end users.
- Provides a system tray and launcher UI in development and in packaged builds.

The runtime code lives under [`backend/src/runtime`](backend/src/runtime:1) and is exercised by thin entrypoints:

- [`backend/src/launcher.py`](backend/src/launcher.py:1)
- [`backend/src/tray_app.py`](backend/src/tray_app.py:1)
- [`backend/src/runtime_entry.py`](backend/src/runtime_entry.py:1)

### 2.1 ApplicationInstanceLock (single instance)

[`ApplicationInstanceLock`](backend/src/runtime/app_singleton.py:31) provides a **mutex‑like singleton** per user:

- **Windows**:
  - Lock file under `%LOCALAPPDATA%\EDColonisationAsst\<app_id>.lock`.
  - Uses `msvcrt.locking` for non‑blocking exclusive file locking.

- **POSIX**:
  - Lock file under one of:
    - `$XDG_RUNTIME_DIR/edca`
    - `$XDG_CACHE_HOME/EDColonisationAsst`
    - `~/.cache/EDColonisationAsst`
  - Uses `fcntl.flock` for non‑blocking exclusive locks.

API:

- `acquire() -> bool` – returns `True` if this process acquires the lock, `False` if another instance holds it; may raise `ApplicationInstanceLockError` on I/O or directory creation errors.
- `release()` – best‑effort unlock and file close.
- Context manager: usable as `with ApplicationInstanceLock(...):`.

**Behavioural contract across entrypoints**:

- First process per user to acquire the lock becomes the **main instance** (launcher/tray or runtime).
- Any subsequent run:

  - Packaged runtime (`runtime_entry.py`): opens the existing UI (`http://127.0.0.1:8000/app/`) in the browser and exits with code `0`.
  - Dev launcher (`launcher.py`): same redirect behaviour.
  - Tray controller (`tray_app.py`): exits without starting another backend/frontend pair.

This guarantees only one EDCA backend/tray/launcher combination runs at a time per OS user while making repeated launches user‑friendly.

### 2.2 Common runtime helpers

[`runtime/common.py`](backend/src/runtime/common.py:1) centralises:

- Lightweight debug logging via `_debug_log`, writing to `EDColonisationAsst-runtime.log` next to the executable.
- Import of the FastAPI [`app`](backend/src/main.py:1) as `fastapi_app` for in‑process servers.
- Logging configuration (`setup_logging`, `logger`).
- Runtime mode detection (`RuntimeMode`, `get_runtime_mode`) used by the packaged runtime and dev helpers.

[`runtime/environment.py`](backend/src/runtime/environment.py:1) encapsulates:

- Whether we are in DEV or FROZEN (packaged) mode.
- Paths such as:
  - `project_root`
  - `icon_path`
  - Backend port and frontend URL used by the tray and runtime.

### 2.3 Launcher (development workflow)

[`launcher_components.py`](backend/src/runtime/launcher_components.py:1) factors out most of the dev launcher logic:

- `QtLaunchWindow` – PySide6 window with:
  - Icon, title.
  - Status label.
  - Progress bar.
  - “Open Web UI” button.

- `Launcher` – orchestrates:

  - Python availability checks.
  - Backend virtualenv creation (`backend/venv`).
  - Backend dependency installation via `pip`.
  - Starting the tray controller (`backend/src/tray_app.py`) inside the venv.
  - Polling backend `/api/health` and `/app` until ready.

[`launcher.py`](backend/src/launcher.py:1) is a thin entrypoint:

- Acquires the `ApplicationInstanceLock`.
- Sets up `QApplication` and `QtLaunchWindow`.
- Instantiates `Launcher` and starts the Qt event loop.

In DEV mode, this is the simplest way to start both backend and frontend with helpful logging and status.

### 2.4 Tray controller (development workflow)

[`tray_components.py`](backend/src/runtime/tray_components.py:1) implements the dev tray controller:

- `ProcessGroup` – simple wrapper around `subprocess.Popen` with `terminate()` and optional `kill()` handling for process groups.
- `TrayController`:
  - Starts/stops:
    - Backend: `uvicorn backend.src.main:app` (via system Python or `backend/venv`).
    - Frontend: `npm run dev -- --host 127.0.0.1 --port 5173` via `cmd.exe /c` on Windows.
  - Configures system tray icon and an Exit action.
  - Logs to:
    - `<install-root>/run-edca.log`
    - `%LOCALAPPDATA%\EDColonisationAsst\run-edca.log` on Windows.

[`tray_app.py`](backend/src/tray_app.py:1) is the thin entrypoint:

- Enforces the single‑instance guarantee via `ApplicationInstanceLock`.
- Creates a Qt app and instantiates `TrayController`.
- Enters the Qt event loop.

### 2.5 Packaged runtime (frozen EXE)

For Windows installers and similar packaged distributions, the main entrypoint is [`runtime_entry.py`](backend/src/runtime_entry.py:1) and the orchestration is in [`app_runtime.py`](backend/src/runtime/app_runtime.py:1).

Key classes:

- `BackendServerController` – starts/stops an in‑process `uvicorn.Server` hosting `fastapi_app`:

  - Uses a custom `_QuietUvicornConfig` that disables uvicorn’s own logging configuration (to avoid conflicts in certain frozen environments).
  - In FROZEN mode, runs uvicorn in a **background thread** in the same process as the EXE.
  - `wait_until_ready(timeout=...)` polls `/api/health` and `/app/` to ensure the backend and static frontend are reachable.

- `TrayUIController` – simple Qt system tray UI in frozen mode:

  - Sets EDCA icon and tooltip.
  - Offers:
    - “Open Web UI” (launches default browser at `RuntimeEnvironment.frontend_url`, usually `http://127.0.0.1:8000/app/`).
    - “Exit” (with confirmation).
  - Clicking/double‑clicking the tray icon also opens the web UI.

- `RuntimeApplication` – top‑level orchestrator:

  - `run()`:
    - In DEV mode: delegates to the legacy launcher window (`_run_dev()`).
    - In FROZEN mode: runs `_run_frozen()`:
      - Starts the in‑process backend server via `BackendServerController`.
      - Waits for readiness.
      - Creates and shows `TrayUIController`.
      - Automatically opens the web UI in the user’s default browser.
      - Runs the Qt event loop until exit, then stops the backend.

`runtime_entry.py` bootstraps logging and the single‑instance lock, then instantiates `RuntimeApplication` and calls `run()`.

---

## 3. Deployment and running

### 3.1 Local development

For developers working from a clone:

- Backend only:

  ```bash
  cd backend
  python -m venv venv
  venv\Scripts\activate  # Windows
  # source venv/bin/activate  # POSIX
  pip install -r requirements-dev.txt
  uvicorn backend.src.main:app --reload
  ```

- Frontend only:

  ```bash
  cd frontend
  npm install
  npm run dev
  ```

- Full dev experience (Qt launcher + tray):

  ```bash
  # From project root
  python -m backend.src.launcher
  ```

  or run the installed launcher executable if available.

### 3.2 Packaged/built runtime

On Windows, a Nuitka/EXE‑based runtime:

- Uses `runtime_entry.py` as the EXE entrypoint.
- Bundles the backend and uses in‑process uvicorn.
- Serves the built frontend from `frontend/dist` mounted at `/app` (see [`main.py`](backend/src/main.py:144)).
- Presents a system tray icon from which users can open/close EDCA.
- Enforces the single‑instance contract via `ApplicationInstanceLock`:
  - Additional launches open the existing browser UI rather than starting a new backend.

On Linux, helper scripts like:

- [`run-edca-built-debian.sh`](run-edca-built-debian.sh:1)
- [`run-edca-built-fedora.sh`](run-edca-built-fedora.sh:1)
- [`run-edca-built-arch.sh`](run-edca-built-arch.sh:1)
- [`run-edca-built-rhel.sh`](run-edca-built-rhel.sh:1)
- [`run-edca-built-void.sh`](run-edca-built-void.sh:1)

start the backend with production settings and, if desired, serve the built frontend from `frontend/dist`. These scripts remain valid with the new runtime and single‑instance design.

---

## 4. Frontend and runtime testing

- Frontend tests:

  - [`App.test.tsx`](frontend/src/App.test.tsx:1)
  - [`test/setup.ts`](frontend/src/test/setup.ts:1)

  use Vitest + Testing Library to validate UI behaviour and integration with API helpers.

- Runtime tests:

  - [`test_runtime_components.py`](backend/tests/unit/test_runtime_components.py:1)
  - [`test_runtime_entry.py`](backend/tests/unit/test_runtime_entry.py:1)
  - [`test_launcher.py`](backend/tests/unit/test_launcher.py:1)
  - [`test_tray_app.py`](backend/tests/unit/test_tray_app.py:1)

  exercise:

  - Launcher window behaviour.
  - Tray controller starting/stopping backend/frontend processes.
  - Single‑instance enforcement via `ApplicationInstanceLock`.
  - Frozen/runtime entry behaviour under error and success conditions.

Together with [`ARCHITECTURE_1_backend.md`](ARCHITECTURE_1_backend.md:1), this file gives a complete view of how EDCA is built, run, and presented to users: from journals and SQLite persistence through to React UI, Qt runtime, and single‑instance guarantees.
