# Elite: Dangerous Colonisation Assistant, Backend Architecture

This document focuses on the **Python backend** of the Elite: Dangerous Colonisation Assistant: how it ingests Elite journals, stores colonisation data and exposes APIs. It is a backend‑only slice of the full architecture described in [`ARCHITECTURE.md`](ARCHITECTURE.md:1).

---

## 1. Backend technology stack

- **Framework**: FastAPI + Uvicorn (usually run as `uvicorn backend.src.main:app`)
- **Language/runtime**: Python 3.11+ (`requires-python` in
  [`backend/pyproject.toml`](backend/pyproject.toml:1); the Windows release is
  built on 3.13)
- **Config & settings**:
  - Pydantic v2 + `pydantic-settings` in [`backend/src/config.py`](backend/src/config.py:1)
  - YAML configuration in [`backend/config.yaml`](backend/config.yaml:1)
  - Inara credentials and preferences in `backend/commander.yaml` (user-created from the example)
- **Persistence**: SQLite via `sqlite3` in [`ColonisationRepository`](backend/src/repositories/colonisation_repository.py:80)
- **File watching**: `watchdog` in [`FileWatcher`](backend/src/services/file_watcher.py:1)
- **HTTP client**: none in service. Nothing under `backend/src` performs an outbound HTTP request; the Inara path (section 7) is dormant. `httpx` remains a dev dependency for the ASGI test client.
- **Live updates**: AJAX long-polling via [`backend/src/api/changes.py`](backend/src/api/changes.py:1) backed by [`ChangeBus`](backend/src/services/change_bus.py:1)
- **Logging**: Standard library logging configured in [`backend/src/utils/logger.py`](backend/src/utils/logger.py:1)
- **Tests**: `pytest` + plugins under [`backend/tests/unit`](backend/tests/unit:1)

---

## 2. Backend project structure

```text
backend/
├── config.yaml                        # Main runtime configuration
├── example.commander.yaml             # Example per‑commander/Inara config
├── requirements.txt                   # Runtime dependencies
├── requirements-dev.txt               # Dev/test tooling
├── pyproject.toml                     # Black/isort and tooling configuration
├── src/
│   ├── __init__.py                    # Package root, defines __version__
│   ├── main.py                        # FastAPI app, lifespan, entrypoint
│   ├── config.py                      # Pydantic settings and config loader
│   ├── constants.py                   # Defaults shared across the backend
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py                  # Core REST API under /api
│   │   ├── health.py                  # /api/health, including startup progress
│   │   ├── changes.py                 # /api/changes/longpoll endpoint (AJAX live updates)
│   │   ├── settings.py                # /api/settings endpoints
│   │   ├── carriers.py                # /api/carriers endpoints (Fleet carriers)
│   │   └── journal.py                 # /api/journal/status, etc.
│   ├── models/
│   │   ├── __init__.py
│   │   ├── api_models.py              # Response models for REST
│   │   ├── colonisation.py            # Core colonisation domain models
│   │   ├── carriers.py                # Fleet carrier domain models
│   │   ├── carrier_status.py          # Fuel, finance, crew and balance history
│   │   └── journal_events.py          # Typed journal event models
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── colonisation_repository.py # SQLite-backed repository
│   │   ├── colonisation_db.py        # DB location, schema version, connections
│   │   └── colonisation_mapping.py   # Row to model, commodity key normalisation
│   ├── runtime/
│   │   ├── __init__.py
│   │   ├── app_runtime.py             # Packaged runtime orchestration
│   │   ├── backend_server.py          # In-process uvicorn control and readiness
│   │   ├── tray_ui.py                 # Frozen-runtime system tray UI
│   │   ├── app_singleton.py           # ApplicationInstanceLock
│   │   ├── common.py                  # Shared runtime helpers
│   │   ├── environment.py             # Runtime environment detection
│   │   ├── launcher_components.py     # Dev launcher orchestration and steps
│   │   ├── launcher_view.py           # LaunchView interface and Qt window
│   │   ├── dialogs.py                 # Showing a dialog with no window to show it over
│   │   ├── splash.py                  # Frozen-runtime startup splash window
│   │   ├── startup_monitor.py         # Readiness polling and its status line
│   │   ├── startup_report.py          # Startup progress read back off /api/health
│   │   ├── help_menu.py               # About and Check for Updates, shared
│   │   └── tray_components.py         # Dev tray helpers
│   ├── services/
│   │   ├── __init__.py
│   │   ├── journal_parser.py          # Relevance, file walk and line dispatch
│   │   ├── colonisation_event_parser.py # The two events whose format changed
│   │   ├── carrier_event_parser.py    # The five fleet carrier events
│   │   ├── commander_event_parser.py  # Location, FSDJump, Docked, Undocked, Commander
│   │   ├── market_event_parser.py     # MarketBuy and MarketSell, one parser
│   │   ├── startup_ingestion.py       # First-run backfill and repeat-run tail sync
│   │   ├── startup_progress.py        # How far that backfill has got, for the splash
│   │   ├── change_bus.py              # In-process change sequence behind the long-poll
│   │   ├── journal_ingestion.py       # Watchdog boundary; routes parsed events
│   │   ├── journal_tail_reader.py     # Incremental byte-offset reads of a journal
│   │   ├── colonisation_projection.py # Colonisation events into the repository
│   │   ├── carrier_service.py         # Carrier response builders (public surface)
│   │   ├── carrier_events.py          # Latest-event lookups over a journal stream
│   │   ├── carrier_fleet.py           # Own and squadron carriers
│   │   ├── carrier_hold.py            # Per-commodity hold from the export plus trades
│   │   ├── carrier_identity.py        # Docked + CarrierStats + CarrierLocation -> identity
│   │   ├── carrier_market.py          # Market.json merge and SpaceUsage arithmetic
│   │   ├── carrier_naming.py          # Commodity name normalisation
│   │   ├── carrier_orders.py          # Cargo, buy and sell orders
│   │   ├── carrier_status.py          # Fuel, jump range, finances and crew
│   │   ├── carrier_balance.py         # Balance movements over the observed window
│   │   ├── carrier_transit.py         # Booked jump, arrival and cancellation
│   │   ├── market_export_service.py   # Reading the carrier's Market.json export
│   │   ├── file_watcher.py            # Watchdog integration and event pipeline
│   │   ├── file_watcher_polling.py    # Polling fallback, mixed into FileWatcher
│   │   ├── data_aggregator.py         # Aggregates per-system data, Inara merge
│   │   ├── system_tracker.py          # Tracks current system/station
│   │   └── inara_service.py           # Thin wrapper around Inara API
│   └── utils/
│       ├── __init__.py
│       ├── journal.py                 # Journal directory detection and file helpers
│       ├── logger.py                  # Logging configuration and helpers
│       ├── ports.py                   # Probing and choosing a bindable port
│       ├── windows.py                 # Windows-only helpers
│       └── runtime.py                 # Frozen/runtime detection helpers
└── tests/
    ├── unit/                          # Unit and integration-style tests
    └── conftest.py                    # Shared pytest fixtures
```

---

## 3. Application lifecycle and first‑run behaviour

The main FastAPI application lives in [`backend/src/main.py`](backend/src/main.py:1).

### 3.1 Startup sequence

On startup, the lifespan context manager `lifespan(app)`:

1. Loads configuration via [`get_config()`](backend/src/config.py:1).
2. Constructs core components:

   - [`ColonisationRepository`](backend/src/repositories/colonisation_repository.py:80)
   - [`DataAggregator`](backend/src/services/data_aggregator.py:37)
   - [`SystemTracker`](backend/src/services/system_tracker.py:1)
   - [`JournalParser`](backend/src/services/journal_parser.py:71)
   - [`FileWatcher`](backend/src/services/file_watcher.py:39)

3. Stores them on `app.state` and wires dependencies:

   - [`set_dependencies`](backend/src/api/routes.py:35) for REST routes.

4. Decides whether this is a first run by reading [`repository.get_stats()`](backend/src/repositories/colonisation_repository.py:182) once (`total_sites == 0`), then **schedules the initial journal ingestion as a background task** (`_startup_ingestion` via `asyncio.create_task`) rather than awaiting it inline.

   This is a deliberate readiness guarantee. ASGI lifespan startup runs **before** uvicorn begins serving requests, so any blocking work here delays `/api/health` and freezes the packaged runtime's startup splash. Walking the full journal history can take minutes on a large journal folder, so it must never sit on the readiness path. The background task:

   - **First run (empty DB):** [`prime_colonisation_database_if_empty`](backend/src/services/startup_ingestion.py:1) walks all `Journal.*.log` files via [`JournalFileHandler._process_file`](backend/src/services/journal_ingestion.py:153) to backfill history once. It runs while the UI is already available; the change‑bus bump on completion drives the long‑poll UI to refetch and populate progressively.
   - **Repeat run (persisted DB under `%LOCALAPPDATA%`):** only a bounded tail sync ([`sync_latest_journals_best_effort`](backend/src/services/startup_ingestion.py:1), newest few files). The full history is already persisted; live changes are handled by watchdog and polling, so re‑scanning everything on every launch is unnecessary.

5. Configures the `FileWatcher`:

   - Calls `file_watcher.set_update_callback(...)` so that changes bump the in-process change sequence used by AJAX long-polling (`/api/changes/longpoll`).
   - Starts watching with `file_watcher.start_watching(journal_dir, process_existing=False)`. The `process_existing=False` flag skips the watcher's own blocking full‑history scan (that initial catch‑up is owned by the background task above); watchdog plus the polling fallback still deliver live updates. Errors are handled non‑fatally so the API starts even if watching fails.

On shutdown, the lifespan handler stops the `FileWatcher` and its watchdog observer via `file_watcher.stop_watching()`.

Because the heavy ingestion is off the readiness path, `test_lifespan_readiness.py` guards that entering the lifespan returns promptly while the import completes in the background.

### 3.2 Automatic DB reset for new installs

Everything in this section lives in [`colonisation_db.py`](backend/src/repositories/colonisation_db.py:1). It runs once, at repository construction, before any query and outside the repository lock, which is what lets it sit in a module of its own.

The colonisation SQLite DB is located via [`resolve_db_file()`](backend/src/repositories/colonisation_db.py:42), which chooses:

- **Dev mode** (non‑frozen): `backend/src/colonisation.db`, derived from that module's own location
- **Frozen/packaged runtime**: `%LOCALAPPDATA%\EDColonisationAsst\colonisation.db` on Windows or `~/.edcolonisationasst/colonisation.db` on POSIX.

To ensure **new installs** and incompatible schema changes start from a clean slate, [`ColonisationDatabase`](backend/src/repositories/colonisation_db.py:75):

- Defines a schema version constant:

  ```python
  CURRENT_DB_SCHEMA_VERSION = 1
  ```

- Creates two tables in `_create_tables`:

  ```sql
  CREATE TABLE IF NOT EXISTS construction_sites (...);
  CREATE TABLE IF NOT EXISTS metadata (
      key   TEXT PRIMARY KEY,
      value TEXT NOT NULL
  );
  ```

- Is asked by the repository's constructor for `initialise()`:

  1. If the DB file **does not exist**:
     - Creates tables and stamps the current schema version in `metadata`.
  2. If the DB file **exists**:
     - Reads `db_schema_version` from `metadata` using `read_schema_version()`.
     - If the stored version equals `CURRENT_DB_SCHEMA_VERSION`, it is left as‑is.
     - If the version is missing or different (e.g. from an older install or a manually copied DB), it:
       - Deletes the DB file once.
       - Recreates tables.
       - Stamps the new version.

With this design:

- A **fresh install** (or a code upgrade that introduces version metadata) will automatically discard any old DB state and rebuild from journals using the first‑run import described above.
- Subsequent runs leave the DB intact and rely purely on the `FileWatcher` for incremental updates.

### 3.3 Finding the journal directory

The tracked [`backend/config.yaml`](backend/config.yaml:1) names no journal
directory; that absence is the design rather than an omission. The file is
tracked, so a path written into it is one machine's path shipped to everyone;
the one that used to be there pointed at a Linux Steam Proton prefix.

[`_default_journal_directory()`](backend/src/config.py:18) calls
[`find_journal_directory()`](backend/src/utils/journal.py:119), which probes the
usual Saved Games locations and the Steam/Proton prefixes. Setting the key in
the YAML or the journal directory in the Settings page overrides the probe.

The import is deliberately **late**, inside the function rather than at module
level: `utils/__init__` imports the logger, the logger imports config, so a
top-level import here is circular.

### 3.4 Saying how far startup has got

[`startup_progress.py`](backend/src/services/startup_progress.py:1) records the
stage of the first-run backfill and how much of it is done;
[`api/health.py`](backend/src/api/health.py:1) publishes it on the health
response. The packaged runtime's splash polls health anyway, so this rides along
on a request it was already making rather than adding an endpoint of its own.

---

## 4. Data model overview

Core colonisation models live in [`backend/src/models/colonisation.py`](backend/src/models/colonisation.py:1):

- **`Commodity`**
  - `name`, `name_localised`
  - `required_amount`, `provided_amount`, `payment`
  - Derived fields:
    - `remaining_amount`
    - `progress_percentage`
    - `status` (`NOT_STARTED`, `IN_PROGRESS`, `COMPLETED`)

- **`ConstructionSite`**
  - `market_id`
  - `station_name`, `station_type`
  - `system_name`, `system_address`
  - `construction_progress`
  - `construction_complete`, `construction_failed`
  - `commodities: list[Commodity]`
  - `last_updated`, `last_source`

  Notes:
  - `construction_progress` reflects the journal field `ConstructionProgress` when present.
  - The **frontend UI does not rely on `construction_progress` for the per-site progress bar**; instead it computes a live per-site delivery percentage from commodity totals (sum provided / sum required) to avoid a “stuck” indicator when deliveries are happening.

- **`SystemColonisationData`**
  - `system_name`
  - `construction_sites: list[ConstructionSite]`
  - Computed:
    - `total_sites`, `completed_sites`, `in_progress_sites`
    - `completion_percentage`

- **`CommodityAggregate`**
  - `commodity_name`, `commodity_name_localised`
  - `total_required`, `total_provided`, `total_remaining`
  - `sites_requiring`
  - `average_payment`
  - `progress_percentage`

Journal event models are in [`backend/src/models/journal_events.py`](backend/src/models/journal_events.py:1), including:

- `ColonisationConstructionDepotEvent`
- `ColonisationContributionEvent`
- `LocationEvent`
- `FSDJumpEvent`
- `DockedEvent`
- `UndockedEvent`
- `CommanderEvent`
- `MarketTransactionEvent` (both `MarketBuy` and `MarketSell`, direction carried as a flag)
- Fleet carrier events:
  - `CarrierLocationEvent`
  - `CarrierStatsEvent`
  - `CarrierTradeOrderEvent`
  - `CarrierJumpRequestEvent`
  - `CarrierJumpCancelledEvent`

Fleet carrier domain models are in [`backend/src/models/carriers.py`](backend/src/models/carriers.py:1):

- `CarrierState` is the whole snapshot: identity, hold, orders, capacity, status,
  balance history and `snapshot_time`.
- `CarrierState.space_usage` (type: `CarrierSpaceUsage`) exposes the raw `CarrierStats.SpaceUsage` breakdown when available:
  - `total_capacity`, `crew`, `module_packs`, `cargo`, `cargo_space_reserved`, `free_space`
- `CarrierState.commander_aboard` says whether the commander is on the carrier.
  It is a fact about the commander, deliberately separate from every field that
  describes the carrier, because where they are standing does not change what
  the carrier holds.
- `CarrierIdentity.transit` (type: `CarrierTransit`) carries the movement state.
  `CarrierTransitState` has two members and not three: a carrier is `PARKED` or
  `IN_TRANSIT`; a cancelled jump simply returns it to `PARKED`.

The status side lives in [`backend/src/models/carrier_status.py`](backend/src/models/carrier_status.py:1):

- **`CarrierStatus`**: `fuel_level`, `jump_range_current`, `jump_range_max`,
  `pending_decommission`, a `CarrierFinance` and a list of `CarrierCrewMember`.
- **`CarrierFinance`**: `carrier_balance`, `reserve_balance`, `available_balance`,
  `reserve_percent` and the three service tax rates.
- **`CarrierCrewMember`**: the service `role`, whether it is `activated` and
  whether it is `enabled`, plus the crew member's `name` when the journal names one.
- **`CarrierBalanceHistory`**: the `entries`, the `observed_from`/`observed_to`
  window they were seen over, the `net_change` and the number of `movements`.
  Every field is optional or empty rather than zero-filled, because a reading
  the journal did not carry is omitted rather than invented.

---

## 5. Repository and persistence

[`ColonisationRepository`](backend/src/repositories/colonisation_repository.py:80) abstracts the SQLite DB for colonisation data. It owns the queries and the locking; the file location and schema live in [`colonisation_db.py`](backend/src/repositories/colonisation_db.py:1) and the row-to-model translation in [`colonisation_mapping.py`](backend/src/repositories/colonisation_mapping.py:1).

- Table `construction_sites` holds a row per depot, with `commodities` stored as JSON.
- Table `metadata` stores `db_schema_version` and future metadata keys.

Key methods:

- `add_construction_site(site: ConstructionSite) -> None`
  - Performs `INSERT OR REPLACE` by `market_id`.
  - Serialises each `Commodity` via `model_dump()`.

- `get_site_by_market_id(market_id: int) -> Optional[ConstructionSite]`

- `get_sites_by_system(system_name: str) -> list[ConstructionSite]`

- `get_all_systems() -> list[str]`
  - Distinct `system_name` values.

- `get_all_sites() -> list[ConstructionSite]`

- `get_stats() -> dict[str, int]`
  - Computes `total_systems`, `total_sites`, `in_progress_sites`, `completed_sites` in memory.

- `update_commodity(market_id: int, commodity_name: str, provided_amount: int) -> None`
  - Loads the site.
  - Normalises `commodity_name` and each `commodity.name` via `normalise_commodity_key(...)`.
  - Updates `commodity.provided_amount` using `max(old, new)`.

- `clear_all() -> None`
  - Deletes all rows from `construction_sites` (used by tests and `/api/debug/reload-journals`).

Concurrency, which the split deliberately left where it was:

- A non‑reentrant `asyncio.Lock` (`self._lock`) guards every method that opens a connection.
- A method that calls one of those must therefore NOT take the lock as well. `get_stats` and `update_commodity` are the two composed of the others, so neither takes it.
- Each connection is opened inside its own `with` block, so one transaction never spans two methods. `update_commodity` is a read and a write in two separate transactions rather than one; that is the price of the deadlock rule above and is recorded on the method.

---

## 6. Journal ingestion pipeline

### 6.1 Parser

[`JournalParser`](backend/src/services/journal_parser.py:71) owns which events matter, how a file is walked and how a line is dispatched. The per-event parsing lives in three modules beside it, grouped by how much work each group does.

- `parse_file(path) -> list[JournalEvent]`:
  - Iterates lines in `Journal.*.log` and calls `parse_line()`.
  - One unreadable line is logged and skipped; one unreadable file yields an empty list. Neither abandons the rest.

- `parse_line(line: str) -> Optional[JournalEvent]`:
  - Parses JSON and reads the timestamp.
  - Filters to `RELEVANT_EVENTS`, then looks the event up in `_EVENT_PARSERS` and calls it. The table replaced an if/elif chain that restated every event name a second time.
  - `RELEVANT_EVENTS` stays a separate `ClassVar` because it is a subclass extension point; a subclass that widens it past what the table knows gets `None` rather than an exception.

The fifteen events, by module:

| Module | Events | Why they are together |
|---|---|---|
| [`colonisation_event_parser.py`](backend/src/services/colonisation_event_parser.py:1) | `ColonisationConstructionDepot`, `ColonisationContribution` | The only two whose journal format has changed in service, so the only two carrying real normalisation |
| [`carrier_event_parser.py`](backend/src/services/carrier_event_parser.py:1) | `CarrierLocation`, `CarrierStats`, `CarrierTradeOrder`, `CarrierJumpRequest`, `CarrierJumpCancelled` | The fleet carrier feature area, reconciled downstream by `carrier_identity`, `carrier_orders`, `carrier_status` and `carrier_transit` |
| [`commander_event_parser.py`](backend/src/services/commander_event_parser.py:1) | `Location`, `FSDJump`, `Docked`, `Undocked`, `Commander`, `LoadGame` | Where the commander is, who they are and what they are worth as the session opens; all six are plain field maps. `Undocked` matters as much as `Docked`: without it, a docking stays true forever |
| [`market_event_parser.py`](backend/src/services/market_event_parser.py:1) | `MarketBuy`, `MarketSell` | One parser for both, because they are the same shape. Direction is carried as a flag so the hold derivation never has to know journal spellings |

`parse_construction_depot` normalises:

  - Old `Commodities` arrays with `Total`/`Delivered`.
  - New `ResourcesRequired` arrays with `RequiredAmount`/`ProvidedAmount`.
  - Missing station and system fields, which fall back to placeholders rather than raising.

`parse_contribution` supports both:

  - Legacy flat schema (`Commodity`, `TotalQuantity`).
  - New `ColonisationContribution` with `Contributions: [{Name, Name_Localised, Amount}]`.
  - Anything else raises `ValueError`, which `parse_line` turns into a warning and a `None`.

### 6.2 Ingestion and system tracking

Ingestion is three collaborators, split so that the watchdog boundary, the reading of a file being written and the repository merge rules are each testable on their own.

[`JournalFileHandler`](backend/src/services/journal_ingestion.py:62) is the watchdog boundary and the router:

- Hooks into `watchdog` events:

  - `on_created`, `on_modified` schedule `_process_file(path)` on the event loop for any `Journal.*.log`.
  - `on_modified` also fires the `__exports__` refresh for the companion exports (`Market.json`, `Cargo.json`, `Status.json`), which are never parsed here.

- `_process_file(file_path: Path) -> None`:

  1. Asks [`JournalTailReader`](backend/src/services/journal_tail_reader.py:34) for the events appended since the last pass.
  2. Routes each one through `_route_event`, updating [`SystemTracker`](backend/src/services/system_tracker.py:1) for:
     - `LocationEvent`
     - `FSDJumpEvent`
     - `DockedEvent`
  3. Hands every colonisation event to [`ColonisationProjector`](backend/src/services/colonisation_projection.py:40).
  4. Tracks which systems were updated and invokes the optional `update_callback(system_name)`; in production this bumps the in-process change sequence used by AJAX long-polling.
  5. Records best-effort diagnostics through `_record_diagnostics`, the single guarded write behind `/api/watcher/status`. A failure there never interrupts ingestion.

[`JournalTailReader`](backend/src/services/journal_tail_reader.py:34) keeps a byte offset and a partial-line buffer per file, so the first sight of a file is a whole-file parse and every pass after it reads only what the game has appended. A partial final line (the game mid-write) is retained and retried rather than parsed as truncated JSON; a file that has shrunk has been rotated, so its state is discarded and the file re-read.

[`ColonisationProjector`](backend/src/services/colonisation_projection.py:40) owns the repository writes:

- `project_docked` creates a placeholder `ConstructionSite` or upgrades an existing one's metadata, which is what reflects a renamed site.
- `project_depot` converts raw commodity payloads into `Commodity` models and merges the snapshot with any existing site, ensuring progress values never regress. It returns the resolved system name, since depot events frequently omit `StarSystem`.
- `project_contribution` calls `repository.update_commodity`.

### 6.3 First‑run vs incremental ingestion

- **First run / empty DB:**
  - `prime_colonisation_database_if_empty(...)` runs once, in a background task scheduled during startup (see section 3.1), so it never blocks server readiness.
  - It uses `JournalFileHandler._process_file` to ingest all historical `Journal.*.log` files, bumping the change bus so the UI populates progressively.

- **Repeat launch / non‑empty DB:**
  - Only a bounded tail sync (`sync_latest_journals_best_effort`) runs in the background; the persisted DB already holds prior history.
  - The watcher is started with `process_existing=False`, so no full re‑scan happens on the readiness path.

- **Normal operation:**
  - `FileWatcher` watches the journal directory and calls the same `_process_file` for changed/created files.
  - Only new activity is ingested; the DB persists across restarts unless a schema reset is triggered by `ColonisationRepository`.

---

## 7. Aggregation and Inara integration

> **The Inara branch is inert in the shipped build.**
> [`get_system_colonisation_data`](backend/src/services/inara_service.py:36) performs no HTTP request and returns an empty list unconditionally, so `aggregate_by_system` always takes its "no Inara data" path and returns local journal data alone. The reason is upstream: no confirmed INAPI v1 event exposes the construction and colonisation data this feature needs. An earlier attempt was built on community-goal events, which are unrelated and produced misleading errors and logs.
>
> The merge rules below therefore describe code that only test doubles reach today. They are documented because they are the contract any future Inara integration must satisfy, not because they currently run. `INARA_API_URL` and the module-level rate-limit and cache state beside it (`_MIN_CALL_INTERVAL_SECONDS`, `_CACHE_TTL`, `_last_call_at`, `_ban_until`, `_rate_limit_lock`, `_system_cache`) are likewise unreferenced, held for that same future call.
>
> EDCA makes no outbound request for colonisation data. The backend's only network calls are loopback probes against itself; the Help menu's "Check for Updates" hands a GitHub URL to the user's browser rather than fetching it. The web UI's update check is browser-side on the same principle: the page fetches the latest release from the public GitHub releases API (one anonymous GET, nothing of the user's sent) and when it is newer shows a prompt offering to download the Windows installer asset (falling back to the releases page), skip that version or decide later. A skipped version is remembered in the browser's localStorage and the check repeats every 24 hours while the HUD stays open; the backend itself still makes no outbound call.

[`DataAggregator`](backend/src/services/data_aggregator.py:37) provides high-level views over `ConstructionSite` data:

- `aggregate_by_system(system_name) -> SystemColonisationData`:

  - Fetches local sites via `repository.get_sites_by_system(system_name)`.
  - Merges those local sites with whatever [`InaraService`](backend/src/services/inara_service.py:1) returns, which in the shipped build is always nothing (see the note above):

    - Upgrades local sites to completed when Inara marks them as complete.
    - Adds Inara‑only completed sites.
    - Never introduces “phantom” in‑progress sites from Inara.

  - Supports a preference `config.inara.prefer_local_for_commander_systems` to prefer journal data in systems the commander has visited. Like the rest of the Inara configuration it is yaml/env-only: the Settings UI and `/api/settings` do not expose it.

- `aggregate_commodities(sites) -> list[CommodityAggregate]`:

  - Re-aggregates all `Commodity` instances across sites into per‑commodity totals and averages.

- `get_system_summary(system_name) -> dict[str, Any]`:

  - Convenience helper returning counts, completion percentage and the most‑needed commodity.

These methods power:

- `GET /api/system`
- `GET /api/system/commodities`
- `GET /api/sites`
- AJAX long-poll notifications via `/api/changes/longpoll`.

---

## 8. REST and live update APIs (backend facets)

The backend’s colonisation APIs are defined in:

- [`backend/src/api/routes.py`](backend/src/api/routes.py:1)
- [`backend/src/api/journal.py`](backend/src/api/journal.py:1)
- [`backend/src/api/settings.py`](backend/src/api/settings.py:1)
- [`backend/src/api/changes.py`](backend/src/api/changes.py:1)

Fleet carrier endpoints are defined in [`backend/src/api/carriers.py`](backend/src/api/carriers.py:1) and are powered by [`backend/src/services/carrier_service.py`](backend/src/services/carrier_service.py:1).

Key carrier endpoints:

- `GET /api/carriers/current`: current docking context. Whether the commander is
  on a Fleet carrier **right now**, resolved from the newest event that settles
  it rather than from the last docking on record (see below).
- `GET /api/carriers/current/state`: reconstructed snapshot including:
  - Identity + services, plus the transit state when a jump is booked
  - Buy and sell orders from `CarrierTradeOrder` events
  - The per-commodity hold, with the age of the export it is anchored on and any tonnage it cannot account for (see below)
  - Capacity metrics from `CarrierStats.SpaceUsage`
  - `space_usage` breakdown (when present)
  - Fuel, jump range, finances, tax rates and crew
  - The balance history over the window the journal covers
  - `commander_aboard`, saying whether the commander is on it
  - Market.json merge to avoid “missing order” artefacts when the journal only emits deltas
- `GET /api/carriers/mine`: known own/squadron carriers derived from recent `CarrierStats`/`CarrierLocation`.

### 8.1 Where the commander is and where the carrier is

Two separate questions that the API used to answer as one.

**Is the commander aboard?** `find_current_carrier_docking` in
[`carrier_events.py`](backend/src/services/carrier_events.py:1) takes the newest
event that settles it (out of `Docked`, `Undocked`, `FSDJump` and `Location`)
and stops there. Its predecessor asked only when the commander was last at a
carrier, which is a question whose answer stays true forever; `Undocked` was not
parsed at all, so nothing could ever make it false again.

**Where is the carrier?** `derive_carrier_transit` in
[`carrier_transit.py`](backend/src/services/carrier_transit.py:1) reads
`CarrierJumpRequest` for a booked jump and clears it on the arriving
`CarrierLocation`. The arrival must match the destination `SystemAddress`: a
login writes a `CarrierLocation` for the carrier's *current* system, which
appears in real journals and would otherwise clear a live transit.
`CarrierJump` is not used, because it carries no `CarrierID` and is only written
when the commander is aboard, which makes it the wrong anchor.

The state endpoint answers for the carrier whether or not the commander is on
it, rebuilding from the last time they were, returning 404 only when no
carrier can be resolved from the journal window at all.

### 8.2 The carrier hold

Elite Dangerous emits no carrier inventory event, so [`carrier_hold.py`](backend/src/services/carrier_hold.py:1) derives one. Three sources, two of which produce it and one of which checks it:

- **`Market.json` `Stock` is the anchor.** It is absolute; it is also the carrier's real hold rather than only what is listed for sale. The game rewrites it when the commander docks and opens the carrier's commodity market, so it is a snapshot rather than a live reading.
- **`MarketBuy` and `MarketSell` against the carrier's own market move it afterwards.** Buying takes tonnage out; selling puts tonnage in. These are why those two events are parsed at all.
- **`CarrierStats.SpaceUsage.Cargo` is an independent total**, so the difference against the summed hold is surfaced rather than hidden. Zero means the snapshot still agrees with the carrier.

**The snapshot is the anchor, never a starting guess.** Reconstructing a hold from transactions alone was measured against 629 `CarrierStats` samples from a real carrier and matched none of them, drifting by up to 4,880 tonnes and producing impossible negatives, because cargo also moves by routes the commander's own journal never records. Every derived tonnage is therefore clamped at zero.

What the carrier **holds** and what it is **offering** are separate questions. A sell order's `Stock` is the tonnage attached to that order and stays journal-derived; the hold covers every commodity aboard whether or not it carries an order. Reading one as the other is what previously hid cargo with no sell order against it.

### 8.3 The balance history

[`carrier_balance.py`](backend/src/services/carrier_balance.py:1) reports every
movement in the carrier's balance across the journal window and attaches **no
cause to any of them**. That is deliberate and is not a gap to be filled later:
the game emits no upkeep event; nothing in the journal separates upkeep from
a tritium purchase or from trade income. Reconstructing upkeep was measured
against 635 readings and does not work, so the history reports what moved and
when, saying nothing about why.

Key colonisation endpoints:

- `GET /api/health`: version, build marker, journal directory and accessibility,
  plus a `startup` block ([`StartupProgressResponse`](backend/src/models/api_models.py:61))
  carrying the stage, the files and bytes done against their totals, a percentage
  by bytes and a message. It rides on health rather than on an endpoint of its
  own because the splash already polls health to decide when to open the browser.
  Progress is measured in bytes rather than files: journal files vary hugely in
  size; counting files makes the bar lurch.
- `GET /api/journal/status`: the commander's current status, read on demand
  from the newest journal file: the current system, the commander's name
  (`Commander` event), the credit balance the session loaded with (`LoadGame`;
  the journal records no running balance, so this is the freshest reading that
  exists) and the docked context (station name and type plus `is_docked`,
  settled by the newest of `Docked`/`Undocked`/`FSDJump`/`Location`). Every
  game session opens its journal with `Commander` and `LoadGame` events, which
  is why none of this is a stored setting.
- `GET /api/systems`: systems with construction sites.
- `GET /api/systems/search?q=...`: fuzzy search over known systems.
- `GET /api/systems/current`: current system/station from `SystemTracker`.
- `GET /api/system?name=...`: `SystemColonisationData` for one system.
- `GET /api/system/commodities?name=...`: aggregated `CommodityAggregate` list.
- `GET /api/sites`: global list of in‑progress and completed sites.
- `GET /api/sites/{market_id}`: detail view of a single site.
- `GET /api/stats`: high-level stats from the repository.
- `POST /api/debug/reload-journals`: explicit full re‑import using the same pipeline as the first‑run preload.

Live updates:

- `GET /api/changes/longpoll?since=<seq>&timeout_s=<seconds>`
- The response is `{ "seq": <int>, "changed": <bool> }`.
- Clients long-poll in a loop; when `changed` is true they refetch the relevant REST endpoints.

---

## 9. Backend testing

Backend tests under [`backend/tests/unit`](backend/tests/unit:1) cover:

- Journal parsing: [`test_journal_parser.py`](backend/tests/unit/test_journal_parser.py:1)
- File watcher and ingestion: [`test_file_watcher.py`](backend/tests/unit/test_file_watcher.py:1)
- Aggregation and Inara integration: [`test_data_aggregator.py`](backend/tests/unit/test_data_aggregator.py:1)
- Repository behaviour and commodity updates: [`test_repository.py`](backend/tests/unit/test_repository.py:1)
- System tracker and journal utilities: [`test_system_tracker_and_utils.py`](backend/tests/unit/test_system_tracker_and_utils.py:1)
- API routes: [`test_api_routes.py`](backend/tests/unit/test_api_routes.py:1), [`test_api_journal_and_settings.py`](backend/tests/unit/test_api_journal_and_settings.py:1)
- Fleet carrier behaviour, one suite per question rather than one per module:
  [`test_carrier_docking.py`](backend/tests/unit/test_carrier_docking.py:1) (is the
  commander aboard), [`test_carrier_transit.py`](backend/tests/unit/test_carrier_transit.py:1)
  (booked, arrived, cancelled), [`test_carrier_hold.py`](backend/tests/unit/test_carrier_hold.py:1),
  [`test_carrier_status.py`](backend/tests/unit/test_carrier_status.py:1) and
  [`test_carrier_balance.py`](backend/tests/unit/test_carrier_balance.py:1)
- Startup: [`test_startup_ingestion.py`](backend/tests/unit/test_startup_ingestion.py:1),
  [`test_startup_progress.py`](backend/tests/unit/test_startup_progress.py:1),
  [`test_lifespan_readiness.py`](backend/tests/unit/test_lifespan_readiness.py:1)
- Port selection: [`test_ports.py`](backend/tests/unit/test_ports.py:1)
- Live update long-poll is exercised indirectly via API wiring tests and frontend integration.
- Runtime/launcher/tray stack: [`test_runtime_components.py`](backend/tests/unit/test_runtime_components.py:1), [`test_runtime_entry.py`](backend/tests/unit/test_runtime_entry.py:1), [`test_launcher.py`](backend/tests/unit/test_launcher.py:1), [`test_tray_app.py`](backend/tests/unit/test_tray_app.py:1)

The first‑run preload logic and DB versioning are exercised indirectly via:

- Repository tests (schema creation and data round‑trip).
- API reload tests (`test_reload_journals_processes_journal_files`).
- File watcher integration tests for depot + contribution flows, including the new `ColonisationContribution` array schema.

The suite runs with branch coverage and a hard 100% gate on the testable
backend surface. `python -m pytest -q` from the repository root is the
invocation to use: it runs this suite together with the setup program's under
one gate. `pytest` from `backend/` enforces the same gate on the
backend alone. See [`TESTING.md`](TESTING.md) for the gate scope, the omit
rationale for the Qt runtime shell and the no-mock-libraries testing
conventions.

This document should give you a concise, backend‑only view of how EDCA ingests journals, stores colonisation state and surfaces it via APIs, including the **automatic DB reset and first‑run journal import** that a new install goes through.
