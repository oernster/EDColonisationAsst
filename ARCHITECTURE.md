# Elite: Dangerous Colonisation Assistant, Architecture Overview

This document is the **front door** to the EDCA architecture. It gives you the big picture and points you to the detailed backend and frontend/runtime documents that now serve as the source of truth.

---

## 1. High-level system overview

```text
┌─────────────────────────────────────────────────────────────────────┐
│                          React Frontend (Vite)                     │
│  - System selector, site list, Fleet Carriers, settings UI         │
│  - Talks to backend via:                                           │
│      • REST  → http://localhost:47021/api/*                         │
│      • Live updates (AJAX long-poll) → http://localhost:47021/api/changes/longpoll │
└─────────────────────────────────────────────────────────────────────┘
                            ▲                  ▲
                            │                  │
                   JSON over HTTP        JSON over WS
                            │                  │
                            ▼                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Python Backend (FastAPI)                         │
│                                                                     │
│  - Journal ingestion pipeline                                       │
│      • Watches Elite journals via watchdog                          │
│      • Parses relevant events                                       │
│      • Updates SQLite-backed repository                             │
│  - Aggregation services                                             │
│      • Aggregates data per system/site                              │
│      • Optionally enriches with Inara data                          │
│  - APIs                                                             │
│      • REST routes under /api/*                                     │
│      • Live updates via AJAX long-poll (/api/changes/longpoll)       │
│      • Fleet carrier endpoints under /api/carriers/*                │
└─────────────────────────────────────────────────────────────────────┘
                            ▲
                            │  filesystem (journal directory)
                            │
┌─────────────────────────────────────────────────────────────────────┐
│                 Elite: Dangerous Journal Files                      │
│  - Journal.*.log  (line-delimited JSON events)                      │
│  - Location/FSDJump/Docked/Commander events track context           │
│  - Colonisation* events expose construction depot state             │
│  - Carrier* events expose Fleet carrier state                       │
└─────────────────────────────────────────────────────────────────────┘
```

At a glance:

- The **backend** watches and parses Elite: Dangerous journal files, persists colonisation state in SQLite, reconstructs Fleet carrier state in memory and exposes REST APIs plus an AJAX long-poll live update endpoint.
- The **frontend** is a React/TypeScript app (MUI, Zustand, Vite) that consumes those APIs to show system progress, shopping lists, carrier state and settings.

Note: EDCA previously used WebSockets for live updates; this has been replaced by AJAX long-polling via `/api/changes/longpoll`.
- A **runtime layer** (Qt launcher, tray, packaged EXE) wraps the backend and serves the built frontend to end users, enforcing a single-instance guarantee per OS user.

---

## 2. Detailed architecture documents

For implementation-level detail, use the split architecture docs at the project root:

### 2.1 Backend architecture

See [`ARCHITECTURE_1_backend.md`](ARCHITECTURE_1_backend.md:1).

That document focuses on:

- FastAPI app structure and lifespan.
- Journal ingestion:
  - Parser, file watcher, system tracker.
  - First-run import vs incremental updates.
- Colonisation data model and SQLite repository:
  - `ConstructionSite`, `Commodity`, `SystemColonisationData`, `CommodityAggregate`.
  - DB schema, versioning and automatic reset for incompatible schema changes.
- Fleet carrier state reconstruction from carrier journal events:
  - `CarrierLocation`, `CarrierStats`, `CarrierTradeOrder`.
  - `Market.json` snapshot merge to avoid missing orders when only deltas are emitted.
  - Normalisation of commodity identifiers and display names.
- Data aggregation and optional Inara integration.
- Backend REST APIs and AJAX long-poll live updates.
- Backend testing and quality tooling.

### 2.2 Frontend & runtime architecture

See [`ARCHITECTURE_2_frontend_and_runtime.md`](ARCHITECTURE_2_frontend_and_runtime.md:1).

That document focuses on:

- React/TypeScript frontend:
  - Component structure (SystemSelector, SiteList, FleetCarriersPanel, SettingsPage).
  - Stores (`colonisationStore`, `carrierStore`).
  - How the UI uses `/api/*` and AJAX long-polling at `/api/changes/longpoll`.
- Fleet Carriers UI:
  - Current docked carrier header and services.
  - Cargo and buy/sell order presentation.
  - Known own/squadron carriers list.
- Settings UI:
  - Journal directory configuration.
  - Commander/Inara settings (with Inara integration currently dormant).
- Runtime / launcher / tray stack:
  - `ApplicationInstanceLock` and single-instance behaviour.
  - Dev launcher window and tray controller.
  - Packaged/frozen runtime (in-process uvicorn + Qt tray).
- Deployment and helper scripts for running EDCA on different platforms.
- Frontend and runtime tests.

These two files are the authoritative, up-to-date references for how EDCA works internally.

### 2.3 What enforces the shape

The layering those documents describe is asserted by
[tests/structural/test_structural.py](tests/structural/test_structural.py),
which reads source files and walks their syntax trees rather than importing
anything. Before it existed the shape held by habit rather than by rule.

- **`models` is the innermost layer.** It imports nothing else from the
  backend. `test_models_import_nothing_else_from_the_backend`.
- **Nothing imports outwards.** `repositories` stays free of `api`, `services`
  and `runtime`; `services` stays free of `api` and `runtime`; `api` stays free
  of `runtime`. `IColonisationRepository` designs that seam and this guards it.
  An import deferred inside a function counts exactly as one at module level.
  `test_backend_layers_import_only_inwards`.
- **The setup program is a separate program.** It imports nothing from
  `backend/`, which is what keeps the compiled onefile down to PySide6 plus the
  standard library. `test_the_setup_program_imports_nothing_from_the_application`.
- **No file exceeds 400 lines.** The rule arrived with an allowlist of the
  nineteen that were already over it, which could only shrink and which a
  staleness test emptied one entry at a time. It is empty, so the allowlist and
  that test are gone and the cap now applies to every scanned file without
  exception. `test_modules_within_line_limit`.

The size scan reads TypeScript as well as Python, because four of the nineteen
were front-end components. `buildexe.py` and `buildinstaller.py` are outside
every scan: they are linear recipes read top to bottom.

---

## 3. The setup program

The `installer/` package is a second, self-contained program that ships the
first one. It imports nothing from `backend/` and is deliberately
dependency-light: process detection is `tasklist`, version comparison is a
tuple compare and shortcuts are written through the Windows scripting host, so
the compiled onefile pulls in nothing beyond PySide6 and the standard library.

It follows the same shape as the application, for the same reason.

```text
installer_main.py     entry point (compiled by buildinstaller.py)
installer/
├── app.py            composition root: crash logging, command line, window
├── cli.py            --uninstall / --quiet / --help
├── constants.py      every name written to disk or to the registry
├── ops/              side effects, no Qt
│   ├── commands.py       the one seam through which the installer shells out
│   ├── copy_tree.py      the payload copy and delete, with per-file progress
│   ├── errors.py         the typed exception hierarchy
│   ├── install_ops.py    install, upgrade, reinstall, downgrade, repair
│   ├── paths.py          the per-user locations, from environment variables
│   ├── payload.py        finding the payload and what travels with it
│   ├── progress.py       the phases and their percentage spans
│   ├── running_app.py    detecting, closing and launching the application
│   ├── shortcuts.py      the Desktop and Start Menu shortcuts
│   └── uninstall_ops.py  removal, including the deferred delete
├── state/            installed state, no Qt
│   ├── model.py          the snapshot the window reads
│   ├── registry.py       the HKCU Uninstall and Run records
│   └── versioning.py     version comparison
├── shared/           resource anchoring and crash logging, no Qt
└── ui/               the only Qt client: window, dialogs, theme, worker thread
```

`ops` and `state` hold every side effect and import no Qt, which is what
allows them to sit inside the 100% coverage gate alongside the backend.

### The three seams

Three seams keep the privileged work testable:

- every external command goes through an injectable `CommandRunner`, so no
  test spawns a process it did not intend to;
- the HKCU locations are a `RegistryKeys` value rather than constants baked
  into each function, so a test writes to a scratch key instead of the user's
  own registration;
- the per-user directories come from environment variables, so the suite
  redirects the profile into a temporary tree; the payload is anchored on
  the `installer` package directory, so the suite redirects that too and
  stages a tiny tree in place of the real payload.

### Where the payload lives

The payload is a plain directory tree rather than an archive, staged by
`buildinstaller.py` under `build/payload/` and embedded by Nuitka at
`installer/payload`. It is resolved relative to the installer package, which
holds in both a source run and a compiled run, with the directory beside the
launcher kept as a further candidate so an installer built before this change
still resolves. A payload that cannot be found is a hard failure: the previous
last-resort fallback to the project root would, after the move into a
subpackage, have installed the installer's own sources.

Nuitka strips loose executables out of an included data directory, so the
runtime executable is embedded a second time under `installer/runtime` and
recovered from there when the copied payload turns out not to carry it.

### Invariants and what enforces them

Each of these is a rule the setup program must not break, followed by the
test in [tests/installer/](tests/installer) that fails if it does.

- **The primary action is one pass.** Install, upgrade, reinstall and
  downgrade are the same sequence and the button says which one it is about
  to do. An older installation is removed and replaced without a second run.
  `test_install_is_one_pass_over_an_older_installation`,
  `test_classify_reports_upgrade_reinstall_and_downgrade`.
- **No action touches files the running application holds.** Install, repair
  and uninstall all detect a running application and offer to close it,
  stating that the running session ends; declining stops the action. The
  close is a forced termination followed by a bounded poll for the file lock
  to release, because the app minimises to the tray rather than exiting when
  its window closes.
  `test_install_refuses_while_the_app_is_running`,
  `test_repair_refuses_while_the_app_is_running`,
  `test_uninstall_closes_a_running_application_first`,
  `test_close_running_app_ends_the_process_and_waits_for_the_lock`,
  `test_close_running_app_reports_a_process_that_will_not_end`.
- **The uninstaller never deletes its own running image.** What is registered
  is a copy of the setup program under `_uninstall/` inside the install
  directory. Whatever is left after the in-place delete is handed to a
  detached PowerShell helper that polls until the lock releases, rather than
  sleeping once and hoping.
  `test_copy_uninstaller_places_a_copy_under_the_install`,
  `test_remove_install_dir_defers_when_it_holds_the_running_executable`,
  `test_the_deferred_script_polls_rather_than_waiting_once`.
- **A repair preserves the sign-in setting.** It is read back from the Run
  key rather than assumed off, so a repair reflects what is registered
  instead of writing an unticked box over the user's choice.
  `test_repair_leaves_the_sign_in_setting_exactly_as_it_was`,
  `test_autostart_can_be_enabled_then_disabled`.
- **The copy cannot write outside the install directory.** Every destination
  is resolved and checked to be inside the target; links are skipped
  rather than followed.
  `test_safe_destination_refuses_a_path_that_leaves_the_target`,
  `test_copy_tree_skips_a_linked_file`,
  `test_copy_tree_does_not_descend_into_a_linked_directory`.
- **A missing payload is a hard failure, never a fallback.** There is no
  last-resort guess at what to install.
  `test_payload_root_fails_loudly_when_there_is_nothing_to_install`,
  `test_install_fails_loudly_with_no_payload_to_install`.
- **Launching the app is detached and rooted in the install directory**, so
  the "launch when finished" option does not tie the new process to the
  installer's lifetime.
  `test_launch_starts_the_app_detached_in_its_own_directory`.

One behaviour is deliberately outside that list: every long operation runs
on a worker thread and reports back through signals, so the window stays
responsive without re-entering the event loop from inside the copy. The
worker is Qt, so it sits in `installer/ui` outside the coverage gate. The one
property that matters is asserted anyway in
`tests/installer/test_worker_threading.py`: **the outcome is delivered on the
interface thread.** A Qt signal connected to a bare callable has no receiver
whose thread affinity Qt can consult, so it degrades to a direct connection
and runs in the sender's thread. That put widget calls and modal dialogs on
the worker thread; it also made the cleanup join the very thread it ran on. Every
worker signal is now connected to a bound method of `OperationRunner`, which
lives on the interface thread. The thread is joined before the callback
runs so a callback may safely close the window. What the worker drives (the
phase spans and the per-file progress) is gated:
`test_copy_tree_reports_progress_across_the_phase`,
`test_scaled_maps_progress_into_the_phase_span`.

---

## 4. Other useful documentation

- **Development workflows and tooling**  
  [`DEVELOPMENT-README.md`](DEVELOPMENT-README.md)  
  - How to run backend and frontend in development.
  - The Windows build pipeline: `python buildexe.py` (runtime EXE) then
    `python buildinstaller.py` (GUI installer), with the installer UI
    sources under `installer/`.
  - Lint/type-checking commands.

- **Testing**  
  [`TESTING.md`](TESTING.md)  
  - How to run the suites (`python -m pytest -q` from the repository root,
    which runs the backend and the setup program under one gate) and what
    the 100% coverage gate covers.

- **Technical debt**  
  [`TECH_DEBT.md`](TECH_DEBT.md)  
  - What is still open, what only looks like debt and what is deliberate
    and should not be "fixed".

- **GameGlass integration**  
  [`GameGlass-Integration.md`](GameGlass-Integration.md:1)
  - How to use EDCA’s APIs and live update long-poll endpoint from GameGlass shards.
  - Which endpoints to call for system lists, site data and aggregated commodities.

- **Project setup**  
  [`PROJECT_SETUP.md`](PROJECT_SETUP.md:1)  
  - Environment prerequisites.
  - Initial setup steps for contributors.

- **Top-level README**  
  [`README.md`](README.md:1)  
  - What EDCA is, how to install and run it as an end user.
  - Links to the architecture docs and development notes.

---

## 5. Suggested reading order

For a new contributor (or a future you coming back to the project):

1. Start here, in this overview, to understand the major moving parts.
2. Read:
   - [`ARCHITECTURE_1_backend.md`](ARCHITECTURE_1_backend.md:1) if you are working on parsing, ingestion, APIs or persistence.
   - [`ARCHITECTURE_2_frontend_and_runtime.md`](ARCHITECTURE_2_frontend_and_runtime.md:1) if you are working on the React UI, Fleet Carriers panel or the Qt/runtime stack.
   - Section 3 above if you are working on the setup program.
3. Use the inline file/line links in those docs to jump directly to concrete implementations and tests.

This keeps `ARCHITECTURE.md` small and navigational, while the split backend/frontend documents carry the full architectural detail.
