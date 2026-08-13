# Elite: Dangerous Colonisation Assistant, Frontend & Runtime Architecture

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
    ├── theme.ts                  # The two MUI themes the toggle switches between
    ├── index.css                 # Global styles
    ├── components/
    │   ├── SystemSelector/
    │   │   └── SystemSelector.tsx
    │   ├── SiteList/
    │   │   ├── SiteList.tsx           # The tab: selection, loading, error
    │   │   ├── SystemSummary.tsx      # Counts and overall progress
    │   │   ├── SystemShoppingList.tsx # The aggregated per-commodity list
    │   │   ├── SiteCard.tsx           # One construction site
    │   │   └── siteAggregation.ts     # The arithmetic, lifted out of the components
    │   ├── FleetCarriers/
    │   │   ├── FleetCarriersPanel.tsx           # The tab and its three sub-tabs
    │   │   ├── CurrentCarrierHeader.tsx         # Identity, services, aboard or not
    │   │   ├── CarrierTransitChip.tsx           # Destination and countdown
    │   │   ├── CarrierCargoSection.tsx          # The hold
    │   │   ├── CarrierMarketSection.tsx         # Buy and sell orders
    │   │   ├── CarrierStatusSection.tsx         # Fuel, range, finance, crew
    │   │   ├── CarrierBalanceHistorySection.tsx # Balance movements over time
    │   │   ├── CarrierIdentityList.tsx          # Own and squadron carriers
    │   │   ├── carrierServices.ts               # Service names for display
    │   │   └── carrierTransit.ts                # Countdown arithmetic
    │   ├── About/
    │   │   ├── AboutPanel.tsx    # Version, author and credits
    │   │   └── LicensePanel.tsx  # The licence text
    │   ├── KeepAwake/
    │   │   └── KeepAwakeChip.tsx # Keep-awake state, in the header
    │   └── Settings/
    │       └── SettingsPage.tsx
    ├── services/
    │   └── api.ts                # Axios client and typed API helpers
    ├── utils/
    │   ├── apiError.ts           # One place that turns a failure into a message
    │   ├── commanderStatus.ts    # Journal status into header copy (credits, location)
    │   └── device.ts             # Handheld detection
    ├── stores/
    │   ├── colonisationStore.ts  # Zustand store for colonisation data
    │   └── carrierStore.ts       # Zustand store for Fleet carrier data
    ├── hooks/
    │   ├── useLiveUpdates.ts         # AJAX long-poll loop and its backoff
    │   ├── useBackendMeta.ts         # Version, health and the commander status
    │   ├── useThemeMode.ts           # Theme choice, persisted
    │   ├── useKeepAwakePreference.ts # Whether the user wants keep-awake
    │   ├── useKeepAwake.ts           # Which keep-awake strategy is in force
    │   ├── keepAwakeCapabilities.ts  # Wake Lock, secure context, handheld probes
    │   ├── keepAwakeVideo.ts         # The hidden fallback video, start to finish
    │   └── useRepaintHeartbeat.ts    # Compositor nudge alongside a held lock
    ├── types/
    │   ├── colonisation.ts       # Shared frontend types for colonisation data
    │   ├── fleetCarriers.ts      # Types for Fleet carrier data
    │   └── settings.ts           # Types for settings
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
  - `/api/systems`: for the system selector.
  - `/api/system`: `SystemColonisationData` for the selected system.
  - `/api/system/commodities`: aggregated per‑commodity “shopping list”.
  - `/api/journal/status`: the commander's status (current system, name,
    session credit balance, docked context), read on demand from the newest
    journal file. The header shows it and `useBackendMeta` re-reads it on a
    gentle timer, since it changes as the commander plays.
  - `/api/settings`: the journal directory, the one user-editable setting.
  - `/api/carriers/*`: Fleet carrier identity and state.

- **Live updates via AJAX long-polling**:
  - The UI holds a request open to `GET /api/changes/longpoll?since=<seq>`.
  - When the backend ingests journal changes it bumps an in-process sequence and the long-poll returns immediately.
  - The UI then refetches `/api/systems` and `/api/system?name=<current>`.

State is centralised in two Zustand stores:

- [`colonisationStore`](frontend/src/stores/colonisationStore.ts:1)
  - `currentSystem`, `systemData`, `allSystems`, `loading`, `error`, `currentSystemInfo`, `settingsVersion`.
  - Actions to set the current system, update system data and update the system list.

- [`carrierStore`](frontend/src/stores/carrierStore.ts:1)
  - `currentCarrierInfo`, `currentCarrierState`, `myCarriers`, loading/error flags.
  - Actions that call:
    - `/api/carriers/current`
    - `/api/carriers/current/state`
    - `/api/carriers/mine`

### 1.4 Key components

- **SystemSelector**: [`SystemSelector.tsx`](frontend/src/components/SystemSelector/SystemSelector.tsx:1)

  - Renders an autocomplete/dropdown of known systems.
  - Uses `/api/systems` and `/api/systems/search`.
  - Updates the selected system in `colonisationStore` and triggers fetch/subscription.

- **SiteList & SiteCard**: [`SiteList.tsx`](frontend/src/components/SiteList/SiteList.tsx:1)

  - Shows a **system summary** (`SystemSummary`), a **system shopping list**
    (`SystemShoppingList`) and **per‑station cards** (`SiteCard`). `SiteList`
    itself is now only the tab: selection, loading and error states.
  - Reads `systemData` from `colonisationStore`:
    - Uses `siteAggregation.ts` to re‑aggregate commodities for the **System
      Shopping List**. The arithmetic lives there rather than inside the
      components, which is what let each of them come back under the size limit.
    - Displays per‑commodity progress and **per‑site overall delivery progress** with MUI progress bars and chips.
    - Per‑site progress bar semantics:
      - Labelled **Commodities Delivered** in the UI.
      - Computed as `sum(provided_amount) / sum(required_amount) * 100` across all commodities for the site.
      - If the site has no commodity requirements yet, the UI shows an indeterminate progress bar with the text “Awaiting requirements”.
      - Note: this intentionally does **not** use the journal field `ConstructionProgress`, which can remain static while commodity deliveries are happening.

- **FleetCarriersPanel**: [`FleetCarriersPanel.tsx`](frontend/src/components/FleetCarriers/FleetCarriersPanel.tsx:1)

  - “Fleet Carriers” tab in the UI.
  - Uses `carrierStore` to:
    - Load `currentCarrierInfo` and `currentCarrierState`. The state is loaded
      whether or not the commander is aboard, because where they are standing
      does not change what the carrier holds. `commander_aboard` is what the
      header labels, the only thing that changes when they leave.
    - Load `myCarriers` (inferred from journal `CarrierStats` + `CarrierLocation`).
  - Presents:
    - Carrier identity and services, via `CurrentCarrierHeader`.
    - A `CarrierTransitChip` when a jump is booked, naming the destination and
      counting down to departure. Arrival clears it; cancelling returns the
      carrier to holding station.
    - A single “Free after all buy orders” metric derived from carrier capacity usage:
      - Uses `CarrierStats.SpaceUsage` breakdown (TotalCapacity, Crew/ModulePacks, Cargo) and
      - Uses the live summed BUY order outstanding tonnage for reservation (so UI reacts immediately to buy-order tweaks).
    - A list of known owned/squadron carriers, via `CarrierIdentityList`.

  Fleet carrier detail sub-tabs, one component each:

  - **Market** (`CarrierMarketSection`): buy and sell orders from
    `CarrierTradeOrder` events, with the `Market.json` merge handled by the
    backend. A cancelled order stops being advertised.
  - **Cargo** (`CarrierCargoSection`): the per-commodity hold, with how old the
    export it is anchored on is and any tonnage it cannot account for.
  - **Status** (`CarrierStatusSection` plus `CarrierBalanceHistorySection`):
    fuel and jump range, finances and tax rates, crew and every movement in the
    balance over the observed window. A reading the journal did not carry is
    omitted rather than drawn as a zero.
  - The selected sub-tab is `carrierViewTab` in `carrierStore` and defaults to
    **Market**.

- **SettingsPage**: [`SettingsPage.tsx`](frontend/src/components/Settings/SettingsPage.tsx:1)

  - Uses `/api/settings` to override the journal directory, the one
    user-editable setting. The backend detects it, so this is an override for
    an unusual installation rather than a setup step. Writes back to the
    backend, which persists to YAML.
  - Also owns the browser-side keep-awake preference, which lives in
    `localStorage` rather than in backend settings.
  - The commander's name is not on this page: it is detected from the journals
    and shown in the header. The dormant Inara configuration is not on it
    either: no shipped feature reads it, so it stays yaml/env-only.

- **App / main**: [`App.tsx`](frontend/src/App.tsx:1), [`main.tsx`](frontend/src/main.tsx:1)

  - Compose the overall layout and route tabs/screens.
  - Initialise stores and start the AJAX long-poll live update loop.
  - App holds no state of its own beyond composition: it moved into the hooks
    (`useThemeMode`, `useKeepAwakePreference`, `useBackendMeta`,
    `useLiveUpdates`) and its copy into the components it renders.
  - The header reports the commander from the journal status: name, session
    credit balance and where they are (`describeLocation` phrases the docked
    context: station, planetary base or carrier, plus the system).
  - **The HUD carries no update check at all.** The whole of it, the hook, the
    release parsing, the prompt and the About tab's button, was removed. It
    had no timer and asked only when the user asked it to, which was thought
    to be enough. The timer was never the problem: this HUD is served over
    the local network and cannot tell whether the device reading it is the
    machine EDCA is installed on, so a tablet beside the cockpit was offered a
    Windows installer it had no way to run. Update checking belongs to the
    tray (section 2.5), which runs on the machine that can act on the answer.
    One owner also ends the case where a single release could raise two
    prompts, each carrying a skip the other could not see. `AboutPanel` has a
    test asserting the absence, so the surface cannot return without the
    tablet problem returning with it.
  - Theme is one control rather than two: a single toggle that switches between
    the two themes in `theme.ts`, persisted by `useThemeMode`.

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

- `acquire() -> bool`: returns `True` if this process acquires the lock, `False` if another instance holds it; may raise `ApplicationInstanceLockError` on I/O or directory creation errors.
- `release()`: best‑effort unlock and file close.
- Context manager: usable as `with ApplicationInstanceLock(...):`.

**Behavioural contract across entrypoints**:

- First process per user to acquire the lock becomes the **main instance** (launcher/tray or runtime).
- Any subsequent run:

  - Packaged runtime (`runtime_entry.py`): opens the existing UI (`http://127.0.0.1:47021/app/`) in the browser and exits with code `0`.
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

The dev launcher is two modules split along an interface it already had. `LaunchView` declares four methods and no Qt types, so `Launcher` never sees a widget; a full launch sequence is therefore testable against a recording stand-in with no QApplication involved. The dependency runs one way: `launcher_components` imports `launcher_view` and re-exports it, so `launcher.py` still reaches the whole stack through one import.

[`launcher_view.py`](backend/src/runtime/launcher_view.py:1) holds the display:

- `LaunchView`: the Qt-free interface (`set_status`, `show_error`, `allow_open_frontend`, `process_events`).
- `QtLaunchWindow`: the one implementation, a PySide6 window with:
  - Icon, title.
  - Status label.
  - Progress bar.
  - “Open Web UI” button.

[`launcher_components.py`](backend/src/runtime/launcher_components.py:1) holds the orchestration:

- `Launcher`, which drives:

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

- `ProcessGroup`: simple wrapper around `subprocess.Popen` with `terminate()` and optional `kill()` handling for process groups.
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

For Windows installers and similar packaged distributions, the main entrypoint is [`runtime_entry.py`](backend/src/runtime_entry.py:1) and the orchestration is in [`app_runtime.py`](backend/src/runtime/app_runtime.py:1). The two controllers it drives live in modules of their own and are re-exported from `app_runtime`, which stays the runtime stack's public surface.

Key classes:

- `BackendServerController` ([`backend_server.py`](backend/src/runtime/backend_server.py:1)): starts/stops an in‑process `uvicorn.Server` hosting `fastapi_app`:

  - Uses a custom `_QuietUvicornConfig` that disables uvicorn’s own logging configuration (to avoid conflicts in certain frozen environments).
  - In FROZEN mode, runs uvicorn in a **background thread** in the same process as the EXE.
  - `probe_ready()` runs a single non‑blocking readiness probe of `/api/health` and `/app/`; `wait_until_ready(timeout=...)` is the blocking wrapper around it for callers that need a synchronous wait.
  - The port is chosen rather than assumed. [`ports.py`](backend/src/utils/ports.py:1)
    probes against the same host the server will bind, because a port free on the
    loopback can still be taken on the wildcard address. The order is: the port a
    previous run recorded, then the configured one, then the remaining known
    candidates, then whatever the operating system will give. A known address is
    worth more than a random one, since it keeps the web UI somewhere a bookmark
    can still find; the chosen port is recorded so the next run and any second
    instance land on the same place. Windows reserves whole ranges, so a port can
    be unbindable while appearing unused, which is what this exists for.

- `StartupSplashWindow` ([`splash.py`](backend/src/runtime/splash.py:1)),
  `StartupMonitor` ([`startup_monitor.py`](backend/src/runtime/startup_monitor.py:1))
  and `StartupReport` ([`startup_report.py`](backend/src/runtime/startup_report.py:1)):
  first‑run feedback in frozen mode:

  - The splash shows the app icon, “by Oliver Ernster”, the version (from the top‑level `VERSION` file via `src.__version__`), a live status line and a progress bar.
  - `StartupMonitor` polls `BackendServerController.probe_ready()` on a Qt timer, so the UI thread never blocks; status progresses from “Starting the local backend...” to “Preparing the web interface...” to “Ready”.
  - `StartupReport` reads the `startup` block back off the health response the
    monitor is already fetching, so the splash can say **what** the first run is
    doing and how far through it is rather than sitting on one message for
    minutes. It names the stage and draws the bar by bytes read, not files, since
    journal files vary hugely in size and a file count makes the bar lurch.
  - The browser is opened only when both endpoints actually respond; on timeout the splash reports the problem and closes while the tray stays available.
  - Silent starts (`--no-browser`, used for login autostart) show no splash and open no browser.

- `TrayUIController` ([`tray_ui.py`](backend/src/runtime/tray_ui.py:1)): simple Qt system tray UI in frozen mode, distinct from the dev tray in `tray_components.py`:

  - Sets EDCA icon and tooltip.
  - Offers:
    - “Open Web UI” (launches default browser at `RuntimeEnvironment.frontend_url`, usually `http://127.0.0.1:47021/app/`).
    - “Help” submenu ([`help_menu.py`](backend/src/runtime/help_menu.py:1), shared with the dev tray): “About” (icon, author, copyright, open source credits) and “Check for Updates”, which runs a real check and reports all three outcomes. It used to open the GitHub releases page and nothing else, so a menu item named after a question never asked it and left the user comparing version numbers by eye. `help_menu` still knows nothing about releases: the check arrives as a callable from [`update_check.py`](backend/src/runtime/update_check.py:1), which both trays build at composition time.
    - “Exit” (with confirmation).
  - Clicking/double‑clicking the tray icon also opens the web UI.
  - **There may be no tray and that is not an error.** `QSystemTrayIcon.isSystemTrayAvailable()` is asked once, in the constructor, because the answer decides which surface exists for the life of the process. On Windows it is always true. On Linux the icon is not drawn by the application at all: it is published over D-Bus as a StatusNotifierItem and drawn by the desktop's own watcher. Plenty of desktops ship no watcher; inside a flatpak the watcher is unreachable unless the sandbox is granted `org.kde.StatusNotifierWatcher`, so a missing permission is indistinguishable from a missing tray from in here. When the answer is no, [`TrayFallbackWindow`](backend/src/runtime/tray_fallback.py:1) takes the tray's place: the same two actions, the same Help menu and a line saying why it is there. Without it the failure is silent and total, since a packaged install has no window of its own: the application starts, serves the interface, shows nothing and cannot be quit except by killing the process.
  - The check is deliberately not retried. A false negative costs the user a small window instead of a tray icon, which is a worse fit but still every action they need; believing a false positive costs them the application.
  - Closing the fallback window is routed to the same Exit, because `quitOnLastWindowClosed` is False: a window that merely hid itself would restore exactly the state the module exists to prevent. `_on_exit` therefore returns whether the application is actually going away; a cancelled confirmation leaves the window on screen.
  - Tested in [`test_tray_ui.py`](backend/tests/unit/test_tray_ui.py:1) with fakes rather than Qt widgets, matching the rest of the runtime suite. The tests were verified by removing the detection and watching three of them fail.

- **Desktop identity**: what ties a running window back to the launcher it was started from. Get it wrong and the application still works; it simply appears in the dock as a second, generic entry beside its own icon, which is the kind of fault nobody reports.

  The two display servers answer it differently and EDCA runs under either, so both are set and neither is guessed:

  - **Wayland** ignores WM_CLASS. It matches on the desktop entry the application names through `QGuiApplication.setDesktopFileName`, which `_build_application` sets from [`desktop_file_name()`](backend/src/utils/runtime.py:1). Inside a flatpak that value is read back from `FLATPAK_ID`, which is the same string flatpak used to install the entry, so the two cannot disagree the way a second copy of the constant could. Outside a sandbox it falls back to `APPLICATION_ID`.
  - **X11** matches WM_CLASS, which has two halves that Qt fills from different places. The **class** half comes from the Qt application name, so the desktop entry's `StartupWMClass` carries that exact string, colon and spaces included. The **instance** half comes from `RESOURCE_NAME`, which the flatpak launcher exports; without it Qt derives the instance name from the executable. Inside the sandbox the executable is `python3`, so every window would announce itself as python3 and match nothing.

  The string therefore lives in two languages, Python and the packaging script, which is the real risk here: a one-character difference matches nothing and fails silently. [`test_desktop_identity.py`](backend/tests/unit/test_desktop_identity.py:1) asserts the packaging script's `APP_ID` and `QT_APPLICATION_NAME` against the real Python constants, plus the launcher still exporting `RESOURCE_NAME`. It was verified by drifting the name by one character and watching the suite fail.

  Every dialog this menu opens goes through
  [`dialogs.present`](backend/src/runtime/dialogs.py:1) rather than a bare
  `exec()`. A packaged EDCA has no main window, so a dialog raised from the
  tray has no parent and the application has no active window for it to sit
  over; Windows then leaves it wherever the z-order puts it, which with a
  full-screen game in front is somewhere the user never sees. The Exit
  confirmation opened there, so pressing Exit looked like nothing happening and
  read as a refusal to quit. `present` sets `WindowStaysOnTopHint` **before**
  the window exists (changing it afterwards recreates the window and drops it
  back down), then shows, raises, activates and only then runs the modal loop.
  Activation can still be refused, since Windows will not let a process that
  does not own the foreground steal it, which is exactly why the flag rather
  than the activation is what carries the fix.

- `UpdateCheckController` ([`update_check.py`](backend/src/runtime/update_check.py:1)):
  the tray's update check, shared by the frozen and dev trays.

  - Trigger: one check 3 seconds after construction, so it never contends
    with starting the backend. There is no repeating timer. **This is the only
    update check in the product.** It honours a skipped version and says
    nothing at all unless there is something new to say. The Help menu's
    manual check ignores the skip and reports every outcome, because a user
    who asked deserves an answer even when the answer is that nothing has
    changed.
  - Why the tray owns it and the browser has none: the web UI is served over
    the local network and is meant to be read from a tablet beside the
    cockpit, so it cannot know whether the device reading it is the machine
    EDCA is installed on. Every offer it made was an offer to download a
    package the device might have no way to install. The tray runs on the
    machine that can act on the answer. Two surfaces also meant one release
    could raise two prompts, each with a skip the other could not see.
  - Threading: the request runs on a `threading.Thread` so an unreachable
    GitHub cannot freeze the tray; the worker emits an internal signal
    connected to a **bound method of the controller**. The controller is
    created on the interface thread, so Qt has a receiver whose affinity it
    can consult and delivers through a queued connection: every widget is
    then built on the interface thread. A signal connected to a bare callable
    would leave Qt nothing to consult, degrade to a direct connection and
    build the prompt on the worker thread. Proved offscreen rather than
    assumed.
  - The rules live below it, inside the coverage gate: `update_service`
    decides, `version_compare` compares, `github_release_source` fetches and
    `update_state` remembers a skip. What is left here is Qt wiring and the
    words on three dialogs, which is why it sits in the omitted runtime shell.

- `RuntimeApplication`: top‑level orchestrator:

  - `run()`:
    - In DEV mode: delegates to the legacy launcher window (`_run_dev()`).
    - In FROZEN mode: runs `_run_frozen()`:
      - Shows the startup splash immediately (unless `--no-browser`).
      - Starts the in‑process backend server via `BackendServerController`.
      - Creates and shows `TrayUIController` straight away so Exit is always available.
      - Polls readiness via `StartupMonitor` without blocking the Qt event loop.
      - Opens the web UI in the user’s default browser only once ready.
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
  uvicorn backend.src.main:app --reload --port 47021
  ```

  The `--port` flag matters: the uvicorn CLI defaults to 8000 and does not
  read the configured port, so without it the frontend dev proxy (which
  targets 47021) cannot reach the backend.

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

On Linux, the helper script [`run-edca-built.sh`](run-edca-built.sh:1) starts the backend with production settings and (if desired) serves the built frontend from `frontend/dist`. It remains valid with the runtime and single‑instance design above.

It is one script rather than one per distribution. The package manager is detected at runtime and used only to phrase install hints, so the executable path is identical everywhere and cannot drift between distributions the way five hand-maintained copies did.

---

## 4. Frontend and runtime testing

- Frontend tests, Vitest plus Testing Library, with
  [`test/setup.ts`](frontend/src/test/setup.ts:1) as the shared setup:

  - [`App.test.tsx`](frontend/src/App.test.tsx:1): layout, tabs and API wiring.
  - [`SiteList.test.tsx`](frontend/src/components/SiteList/SiteList.test.tsx:1)
  - [`FleetCarriersPanel.test.tsx`](frontend/src/components/FleetCarriers/FleetCarriersPanel.test.tsx:1)
    and [`CarrierStatusSection.test.tsx`](frontend/src/components/FleetCarriers/CarrierStatusSection.test.tsx:1)
  - [`carrierTransit.test.ts`](frontend/src/components/FleetCarriers/carrierTransit.test.ts:1):
    the countdown arithmetic, tested as a function rather than through a component.
  - [`useKeepAwake.test.ts`](frontend/src/hooks/useKeepAwake.test.ts:1) and
    [`keepAwakeStrategies.test.ts`](frontend/src/hooks/keepAwakeStrategies.test.ts:1):
    the hook arrived with these when it was split by wake-lock strategy, having
    had none before.

- Runtime tests:

  - [`test_runtime_components.py`](backend/tests/unit/test_runtime_components.py:1)
    and [`test_runtime_components_launcher.py`](backend/tests/unit/test_runtime_components_launcher.py:1)
  - [`test_backend_server_readiness.py`](backend/tests/unit/test_backend_server_readiness.py:1)
  - [`test_splash.py`](backend/tests/unit/test_splash.py:1)
  - [`test_runtime_entry.py`](backend/tests/unit/test_runtime_entry.py:1)
  - [`test_launcher.py`](backend/tests/unit/test_launcher.py:1)
  - [`test_app_singleton.py`](backend/tests/unit/test_app_singleton.py:1)
  - [`test_tray_app.py`](backend/tests/unit/test_tray_app.py:1)
  - [`test_help_menu.py`](backend/tests/unit/test_help_menu.py:1)

  exercise:

  - Launcher orchestration against a recording `LaunchView`, with no QApplication.
  - Tray controller starting/stopping backend/frontend processes.
  - Readiness probing and the status line it produces.
  - Single‑instance enforcement via `ApplicationInstanceLock`.
  - Frozen/runtime entry behaviour under error and success conditions.

Together with [`ARCHITECTURE_1_backend.md`](ARCHITECTURE_1_backend.md:1), this file gives a complete view of how EDCA is built, run and presented to users: from journals and SQLite persistence through to React UI, Qt runtime and single‑instance guarantees.
