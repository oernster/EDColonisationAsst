# Elite: Dangerous Colonisation Assistant – Backend Architecture

This document focuses on the **Python backend** of the Elite: Dangerous Colonisation Assistant: how it ingests Elite journals, stores colonisation data, and exposes APIs. It is a backend‑only slice of the full architecture described in [`ARCHITECTURE.md`](ARCHITECTURE.md:1).

---

## 1. Backend technology stack

- **Framework**: FastAPI + Uvicorn (usually run as `uvicorn backend.src.main:app`)
- **Language/runtime**: Python 3.10+
- **Config & settings**:
  - Pydantic v2 + `pydantic-settings` in [`backend/src/config.py`](backend/src/config.py:1)
  - YAML configuration in [`backend/config.yaml`](backend/config.yaml:1)
  - Commander/Inara secrets in `backend/commander.yaml` (user-created from the example)
- **Persistence**: SQLite via `sqlite3` in [`ColonisationRepository`](backend/src/repositories/colonisation_repository.py:130)
- **File watching**: `watchdog` in [`FileWatcher`](backend/src/services/file_watcher.py:1)
- **HTTP client**: `httpx` (for Inara) in [`backend/src/services/inara_service.py`](backend/src/services/inara_service.py:1)
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
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py                  # Core REST API under /api
│   │   ├── changes.py                 # /api/changes/longpoll endpoint (AJAX live updates)
│   │   ├── settings.py                # /api/settings endpoints
│   │   ├── carriers.py                # /api/carriers endpoints (Fleet carriers)
│   │   └── journal.py                 # /api/journal/status, etc.
│   ├── models/
│   │   ├── __init__.py
│   │   ├── api_models.py              # Response models for REST
│   │   ├── colonisation.py            # Core colonisation domain models
│   │   ├── carriers.py                # Fleet carrier domain models
│   │   └── journal_events.py          # Typed journal event models
│   ├── repositories/
│   │   ├── __init__.py
│   │   └── colonisation_repository.py # SQLite-backed repository
│   ├── runtime/
│   │   ├── __init__.py
│   │   ├── app_runtime.py             # Packaged runtime orchestration
│   │   ├── app_singleton.py           # ApplicationInstanceLock
│   │   ├── common.py                  # Shared runtime helpers
│   │   ├── environment.py             # Runtime environment detection
│   │   ├── launcher_components.py     # Dev launcher window/tray helpers
│   │   └── tray_components.py         # Dev tray helpers
│   ├── services/
│   │   ├── __init__.py
│   │   ├── journal_parser.py          # Parses Journal.*.log events
│   │   ├── journal_ingestion.py       # Ingestion pipeline using JournalParser
│   │   ├── file_watcher.py            # Watchdog integration and event pipeline
│   │   ├── data_aggregator.py         # Aggregates per-system data, Inara merge
│   │   ├── system_tracker.py          # Tracks current system/station
│   │   └── inara_service.py           # Thin wrapper around Inara API
│   └── utils/
│       ├── __init__.py
│       ├── journal.py                 # Journal-specific helpers
│       ├── logger.py                  # Logging configuration and helpers
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

   - [`ColonisationRepository`](backend/src/repositories/colonisation_repository.py:130)
   - [`DataAggregator`](backend/src/services/data_aggregator.py:37)
   - [`SystemTracker`](backend/src/services/system_tracker.py:1)
   - [`JournalParser`](backend/src/services/journal_parser.py:39)
   - [`FileWatcher`](backend/src/services/file_watcher.py:39)

3. Stores them on `app.state` and wires dependencies:

   - [`set_dependencies`](backend/src/api/routes.py:35) for REST routes.

4. Performs a **one‑time initial import** of existing journals when the DB is empty, using `_prime_colonisation_database_if_empty`:

   - Calls [`repository.get_stats()`](backend/src/repositories/colonisation_repository.py:256).
   - If `total_sites == 0`, it:
     - Locates the journal directory from `config.journal.directory`.
     - Walks all `Journal.*.log` files.
     - Uses [`JournalFileHandler._process_file`](backend/src/services/journal_ingestion.py:109) with a real `JournalParser` and `SystemTracker` to ingest events.
   - On subsequent runs (non‑empty DB), this step is skipped.

5. Configures the `FileWatcher`:

   - Calls `file_watcher.set_update_callback(...)` so that changes bump the in-process change sequence used by AJAX long-polling (`/api/changes/longpoll`).
   - Starts watching the journal directory with `file_watcher.start_watching(journal_dir)`, handling errors non‑fatally so the API can still start even if watching fails.

On shutdown, the lifespan handler stops the `FileWatcher` and its watchdog observer via `file_watcher.stop_watching()`.

### 3.2 Automatic DB reset for new installs

The colonisation SQLite DB is located via [`_get_db_file()`](backend/src/repositories/colonisation_repository.py:18), which chooses:

- **Dev mode** (non‑frozen): `backend/colonisation.db`
- **Frozen/packaged runtime**: `%LOCALAPPDATA%\EDColonisationAsst\colonisation.db` on Windows, or `~/.edcolonisationasst/colonisation.db` on POSIX.

To ensure **new installs** and incompatible schema changes start from a clean slate, [`ColonisationRepository`](backend/src/repositories/colonisation_repository.py:130) now:

- Defines a schema version constant:

  ```python
  CURRENT_DB_SCHEMA_VERSION = 1
  ```

- Creates two tables in [`_create_tables`](backend/src/repositories/colonisation_repository.py:151):

  ```sql
  CREATE TABLE IF NOT EXISTS construction_sites (...);
  CREATE TABLE IF NOT EXISTS metadata (
      key   TEXT PRIMARY KEY,
      value TEXT NOT NULL
  );
  ```

- On repository initialisation, calls `_initialise_database()`:

  1. If the DB file **does not exist**:
     - Creates tables and stamps the current schema version in `metadata` via `_set_schema_version(CURRENT_DB_SCHEMA_VERSION)`.
  2. If the DB file **exists**:
     - Reads `db_schema_version` from `metadata` using `_get_schema_version()`.
     - If the stored version equals `CURRENT_DB_SCHEMA_VERSION`, it is left as‑is.
     - If the version is missing or different (e.g. from an older install or a manually copied DB), it:
       - Deletes the DB file once.
       - Recreates tables.
       - Stamps the new version.

With this design:

- A **fresh install** (or a code upgrade that introduces version metadata) will automatically discard any old DB state and rebuild from journals using the first‑run import described above.
- Subsequent runs leave the DB intact and rely purely on the `FileWatcher` for incremental updates.

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
- `CommanderEvent`
- Fleet carrier events:
  - `CarrierLocationEvent`
  - `CarrierStatsEvent`
  - `CarrierTradeOrderEvent`

Fleet carrier domain models are in [`backend/src/models/carriers.py`](backend/src/models/carriers.py:1). Recent additions:

- `CarrierState.space_usage` (type: `CarrierSpaceUsage`) exposes the raw `CarrierStats.SpaceUsage` breakdown when available:
  - `total_capacity`, `crew`, `module_packs`, `cargo`, `cargo_space_reserved`, `free_space`

---

## 5. Repository and persistence

[`ColonisationRepository`](backend/src/repositories/colonisation_repository.py:130) abstracts the SQLite DB for colonisation data:

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
  - Normalises `commodity_name` and each `commodity.name` via `_normalise_commodity_key(...)`.
  - Updates `commodity.provided_amount` using `max(old, new)`.

- `clear_all() -> None`
  - Deletes all rows from `construction_sites` (used by tests and `/api/debug/reload-journals`).

Concurrency:

- Uses an `asyncio.Lock` (`self._lock`) to guard compound operations.
- Methods that call other lock‑taking methods are carefully written to avoid deadlock (e.g. `update_commodity` does not take the lock directly but relies on `get_site_by_market_id` / `add_construction_site` doing so).

---

## 6. Journal ingestion pipeline

### 6.1 Parser

[`JournalParser`](backend/src/services/journal_parser.py:39) is responsible for parsing individual journal lines and files.

- `parse_file(path) -> list[JournalEvent]`:
  - Iterates lines in `Journal.*.log` and calls `parse_line()`.

- `parse_line(line: str) -> Optional[JournalEvent]`:
  - Parses JSON.
  - Filters to **relevant events**:

    ```python
    RELEVANT_EVENTS = {
        "ColonisationConstructionDepot",
        "ColonisationConstructionDepot",
        "ColonisationContribution",
        "ColonisationContribution",
        "Location",
        "FSDJump",
        "Docked",
        "Commander",
        "CarrierLocation",
        "CarrierStats",
        "CarrierTradeOrder",
    }
    ```

  - Dispatches to internal handlers:
    - `_parse_construction_depot(...)`
    - `_parse_contribution(...)`
    - `_parse_location(...)`
    - `_parse_fsd_jump(...)`
    - `_parse_docked(...)`
    - `_parse_commander(...)`
    - `_parse_carrier_location(...)`
    - `_parse_carrier_stats(...)`
    - `_parse_carrier_trade_order(...)`

- `_parse_construction_depot` normalises:

  - Old `Commodities` arrays with `Total`/`Delivered`.
  - New `ResourcesRequired` arrays with `RequiredAmount`/`ProvidedAmount`.

- `_parse_contribution` supports both:

  - Legacy flat schema (`Commodity`, `TotalQuantity`).
  - New `ColonisationContribution` with `Contributions: [{Name, Name_Localised, Amount}]`.

### 6.2 Ingestion and system tracking

[`JournalFileHandler`](backend/src/services/journal_ingestion.py:39) orchestrates ingestion:

- Hooks into `watchdog` events:

  - `on_created`, `on_modified` schedule `_process_file(path)` on the event loop for any `Journal.*.log`.

- `_process_file(file_path: Path) -> None`:

  1. Calls `parser.parse_file(file_path)` to get `JournalEvent` instances.
  2. Updates [`SystemTracker`](backend/src/services/system_tracker.py:1) for:
     - `LocationEvent`
     - `FSDJumpEvent`
     - `DockedEvent`
  3. For `DockedEvent` at colonisation sites:
     - Invokes `_process_docked_at_construction_site` to create or enrich a `ConstructionSite`.
  4. For `ColonisationConstructionDepotEvent`:
     - Invokes `_process_construction_depot` to:
       - Convert raw commodity payloads into `Commodity` models.
       - Merge new snapshot state with any existing site, ensuring we never regress progress values.
  5. For `ColonisationContributionEvent`:
     - Invokes `_process_contribution` to call `repository.update_commodity`.
  6. Tracks which systems were updated and invokes the optional `update_callback(system_name)`; in production this bumps the in-process change sequence used by AJAX long-polling.

### 6.3 First‑run vs incremental ingestion

- **First run / empty DB:**
  - `_prime_colonisation_database_if_empty(...)` runs once on startup (see section 3.1).
  - It uses `JournalFileHandler._process_file` to ingest all historical `Journal.*.log` files.

- **Normal operation:**
  - `FileWatcher` watches the journal directory and calls the same `_process_file` for changed/created files.
  - Only new activity is ingested; the DB persists across restarts unless a schema reset is triggered by `ColonisationRepository`.

---

## 7. Aggregation and Inara integration

[`DataAggregator`](backend/src/services/data_aggregator.py:37) provides high-level views over `ConstructionSite` data:

- `aggregate_by_system(system_name) -> SystemColonisationData`:

  - Fetches local sites via `repository.get_sites_by_system(system_name)`.
  - Optionally queries Inara via [`InaraService`](backend/src/services/inara_service.py:1) and merges:

    - Upgrades local sites to completed when Inara marks them as complete.
    - Adds Inara‑only completed sites.
    - Never introduces “phantom” in‑progress sites from Inara.

  - Supports a preference `config.inara.prefer_local_for_commander_systems` to prefer journal data in systems the commander has visited.

- `aggregate_commodities(sites) -> list[CommodityAggregate]`:

  - Re-aggregates all `Commodity` instances across sites into per‑commodity totals and averages.

- `get_system_summary(system_name) -> dict[str, Any]`:

  - Convenience helper returning counts, completion percentage, and the most‑needed commodity.

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

- `GET /api/carriers/current` – current docking context (docked carrier identity when docked at a Fleet carrier).
- `GET /api/carriers/current/state` – reconstructed snapshot including:
  - Identity + services
  - Buy and sell orders from `CarrierTradeOrder` events
  - Capacity metrics from `CarrierStats.SpaceUsage`
  - `space_usage` breakdown (when present)
  - Market.json merge to avoid “missing order” artefacts when the journal only emits deltas
- `GET /api/carriers/mine` – known own/squadron carriers derived from recent `CarrierStats`/`CarrierLocation`.

Key colonisation endpoints:

- `GET /api/health` – health check + journal directory info.
- `GET /api/systems` – systems with construction sites.
- `GET /api/systems/search?q=...` – fuzzy search over known systems.
- `GET /api/systems/current` – current system/station from `SystemTracker`.
- `GET /api/system?name=...` – `SystemColonisationData` for one system.
- `GET /api/system/commodities?name=...` – aggregated `CommodityAggregate` list.
- `GET /api/sites` – global list of in‑progress and completed sites.
- `GET /api/sites/{market_id}` – detail view of a single site.
- `GET /api/stats` – high-level stats from the repository.
- `POST /api/debug/reload-journals` – explicit full re‑import using the same pipeline as the first‑run preload.

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
- Live update long-poll is exercised indirectly via API wiring tests and frontend integration.
- Runtime/launcher/tray stack: [`test_runtime_components.py`](backend/tests/unit/test_runtime_components.py:1), [`test_runtime_entry.py`](backend/tests/unit/test_runtime_entry.py:1), [`test_launcher.py`](backend/tests/unit/test_launcher.py:1), [`test_tray_app.py`](backend/tests/unit/test_tray_app.py:1)

The first‑run preload logic and DB versioning are exercised indirectly via:

- Repository tests (schema creation and data round‑trip).
- API reload tests (`test_reload_journals_processes_journal_files`).
- File watcher integration tests for depot + contribution flows, including the new `ColonisationContribution` array schema.

This document should give you a concise, backend‑only view of how EDCA ingests journals, stores colonisation state, and surfaces it via APIs, including the new **automatic DB reset + first‑run journal import** behaviour for new installs.
