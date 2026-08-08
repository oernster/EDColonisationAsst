# Colonisation Assistant: Technical Debt

A standing reference to the project's outstanding technical debt. It records what is still open, weighs whether each item is worth doing and gives the rationale. Every item is a behaviour-preserving internal concern: nothing here proposes reverting a feature or changing any UI or UX behaviour. Scope is the whole repository (the FastAPI backend under `backend/`, the React front end under `frontend/`, the runtime and launcher, the bespoke installer, the delivery scripts and the GitHub Pages site) read against `ARCHITECTURE.md` and its two companion documents.

---

## 1. One front-end file is over the 400-line module cap

Eighteen are done. `carrier_service.py` went from 960 lines to seven modules, none over 263, along the seams its own section markers already described. `App.tsx` went from 651 to 249 by moving its state into hooks, which is what the item said it was holding. `journal_ingestion.py` went from 575 to 256, `app_runtime.py` from 542 to 267, `main.py` from 494 to 306, `journal_parser.py` from 488 to 180, `colonisation_repository.py` from 470 to 288 and `launcher_components.py` from 425 to 321. All eight oversized test modules were then split by the surface each set of tests exercises.

The test split follows one shape throughout. Shared scaffolding (imports, fakes, fixtures, module constants) moves to a private `_<stem>_support.py`, which pytest never collects because it does not match `test_*.py`; the tests are dealt out to sibling modules in declaration order, each importing only the support names it actually uses. `test_journal_parser.py` needed no support module at all, so it has none. The invariant that made this safe to do mechanically is the test count: 507 before and 507 after, at 100% coverage throughout.

| Module | Lines | What it holds |
|---|---|---|
| `carrier_service.py` | 255 | The two response builders, plus the re-export surface |
| `carrier_orders.py` | 263 | Cargo, buy and sell orders from CarrierTradeOrder events |
| `carrier_market.py` | 254 | Market.json reconciliation and the SpaceUsage arithmetic |
| `carrier_identity.py` | 135 | Reconciling Docked, CarrierStats and CarrierLocation into one identity |
| `carrier_naming.py` | 109 | Commodity name normalisation, both directions |
| `carrier_events.py` | 96 | Latest-event lookups over a journal stream |
| `carrier_fleet.py` | 93 | The commander's own and squadron carriers |

`carrier_service.py` stays the public surface: `api/carriers.py` and the tests import from it unchanged, with `__all__` marking the re-exports so an auto-fixer cannot delete them. Nothing imports rightwards, so there is no cycle.

One entry remains in `_LEGACY_OVER_LIMIT` in [tests/structural/test_structural.py](tests/structural/test_structural.py), measured 2026-08-08:

| Lines | File |
|---|---|
| 406 | `frontend/src/hooks/useKeepAwake.ts` |

The cap is asserted, so nothing new joins them; a staleness test fails on any entry whose file is no longer over the limit, which is what removed `carrier_service.py` from the list. The list can only shrink and this item closes when it is empty.

What came out of `App.tsx`, with why each piece is one: `theme.ts` (62) because two MUI themes are configuration rather than component logic; `useThemeMode` (44), `useKeepAwakePreference` (61), `useLiveUpdates` (102) and `useBackendMeta` (52) because each owns one piece of state and the effects that maintain it; `KeepAwakeChip` (96), `AboutPanel` (105) and `LicensePanel` (32) because a status indicator and two pages of static copy are components, not root-component body.

`useLiveUpdates` is the one worth reading before changing. The long-poll loop subscribes once and never again, so it reads the selected system through a ref rather than closing over a value that would go stale immediately. Its two safety nets are load-bearing: a short sleep when the backend returns `changed=false` straight away, which a misconfigured proxy or a test double will do and which would otherwise spin the CPU; and exponential backoff when the request itself fails.

`journal_ingestion.py` came apart along the two concerns its one long method was carrying. `journal_tail_reader.py` (174) owns the byte offset and partial-line buffer that make an append-only file safe to re-read; `colonisation_projection.py` (291) owns the repository merge rules that stop a stale depot snapshot regressing progress. What is left in `journal_ingestion.py` (256) is the watchdog boundary and event routing, plus one `_record_diagnostics` guard in place of the six copies of the same try/except the file used to hold. The tests that reached for the moved methods now call them on the collaborator that owns them.

`app_runtime.py` split along the three responsibilities its own docstring already listed: `backend_server.py` (262) holds the in-process uvicorn control and the readiness probes; `tray_ui.py` (149) holds the frozen runtime's tray; what is left in `app_runtime.py` (267) is `RuntimeApplication`. It stays the public surface the way `carrier_service.py` does, re-exporting both controllers under `__all__`, so `runtime_entry` imports nothing new. The readiness tests moved to `test_backend_server_readiness.py` alongside the code they exercise. This package is outside the coverage gate (`**/src/runtime/*`), so the split was verified by the suite passing and by the re-exports resolving, not by a coverage delta.

`main.py` gave up the two startup journal functions to `services/startup_ingestion.py` (233): the first-run backfill and the bounded repeat-run tail sync. That move is the one in this list with a coverage consequence. `main.py` is omitted from the gate (`**/src/main.py`) and both functions were only ever monkeypatched, so neither body had ever been executed by a test; the extracted module is gated like any other service, so it arrives with 13 tests covering every degradation path (unreadable stats, unparseable config, missing directory, no journals, one bad file mid-history, a failing refresh hint). The suite went 507 to 520 and stayed at 100%.

The three identical `change_bus.bump()` guards became one `notify_clients_best_effort`, which is why `main.py` no longer imports `change_bus` at all.

`journal_parser.py` split on an observation its own code made: not one of the nine `_parse_*` methods touched `self`. They are now module-level functions in three modules grouped by how much work each does: `colonisation_event_parser.py` (206) holds the two events whose journal format has changed in service and therefore all the normalisation, `carrier_event_parser.py` (140) the three fleet carrier events and `commander_event_parser.py` (92) the four plain field maps. What is left in `journal_parser.py` (180) is relevance, the file walk and the dispatch.

The if/elif dispatch chain became a `_EVENT_PARSERS` table, which is what removes the second restatement of every event name. `RELEVANT_EVENTS` is deliberately NOT derived from that table: a test subclass widens it and an eventual ruling on item 2 might too, so it stays a separate extension point with `parse_line` handling a name the table does not know. Nothing about the split touches that ruling, which is still open. No test changed: every one of them goes through `parse_line` or `parse_file`, so coverage stayed at 100% untouched.

`colonisation_repository.py` was the one to be careful with, because it is the only file in this list holding a lock and a transaction boundary. The cut was chosen so that neither moved: `colonisation_db.py` (225) takes the file location, the schema version and the connection, all of which run once in the constructor before any lock exists; `colonisation_mapping.py` (76) takes the row-to-model rebuild and the commodity-key normalisation, both pure. What is left in `colonisation_repository.py` (288) is the queries and the locking, untouched.

The lock rule is now stated at the top of the module rather than only on the one method that had to explain itself: the lock is not reentrant, every method that opens a connection takes it and the two composed of those (`get_stats`, `update_commodity`) must not. `update_commodity` remains a read and a write in two transactions rather than one, which is the price of that rule and is recorded where it happens.

`launcher_components.py` split along an interface it already had. `LaunchView` declares four methods and names no Qt type, which is why `Launcher` can be driven end to end by a recording stand-in with no QApplication in the test. `launcher_view.py` (194) now holds that interface and its one real implementation, `QtLaunchWindow`; `launcher_components.py` (321) keeps the steps, the subprocess plumbing and the log. It imports the view module and re-exports it under `__all__`, so `launcher.py` and the tests still reach the whole stack through one name and nothing outside the package changed.

**Every Python file in the repository is now inside the cap.** The front end is linted too: `frontend/eslint.config.js` arrived with the flat config the ESLint 9 upgrade had left the project without; the pre-commit hook runs it.

`FleetCarriersPanel.tsx` held five components and a formatting module in one file, so it split by component: `CarrierCargoSection.tsx` (201), `CurrentCarrierHeader.tsx` (128), `CarrierMarketSection.tsx` (114), `CarrierIdentityList.tsx` (113) and `carrierServices.ts` (97), leaving the panel itself at 214 to own the store wiring, the three effects and the layout. The service filter-and-sort had a copy in the header and another in the list rows and is now one `visibleServicesSorted`; the `space_usage` shape was declared inline twice and is now a named `CarrierSpaceUsage`.

This is the first split in the sweep with no existing tests behind it, since the five Vitest tests render `<App />` and never reach this panel. It arrives with eight characterisation tests covering the not-docked copy, the docked header and its chips, the service filtering and ordering, both market columns, the cargo totals and the free-space arithmetic. Those were checked against three mutations (drop the sort, drop the service filter, drop the buy-order reservation), each of which failed exactly one test.

`SiteList.tsx` came apart the same way, into `SiteCard.tsx` (194), `SystemShoppingList.tsx` (136), `SystemSummary.tsx` (80) and `siteAggregation.ts` (193), leaving `SiteList.tsx` at 118 to own the filtering, the empty states and which site the tabs select. The three derivations that were tangled into the components are now pure functions in `siteAggregation.ts`: the shopping-list aggregation, the completed-station rule and the per-site delivery progress. `isStationCompleted` moving to module scope also settles a question its old position raised, since it was declared in the component body and used inside a `useMemo` that did not list it.

It arrives with 14 tests, six of them driving the arithmetic directly rather than through a render, which is the point of having pulled it out. Four mutations were used to check they were not vacuous (drop the outstanding-sites guard, reverse the sort order, drop a clause from the completed rule, drop the progress clamp) and each failed exactly the test that claims that behaviour. The one pre-existing SiteList test in `App.test.tsx` is left where it is and still passes, which is what shows the extracted progress calculation is unchanged.

What is left is `useKeepAwake.ts` at 406. It is a hook rather than a component, so it will not come apart the way the two panels did: its length is the sequence of wake-lock strategies it falls through, not layout. Every other file that left this list took a characterisation suite with it. That one has none either.

## 2. The US spelling of the colonisation events is documented but not implemented

The parser says it twice over: `RELEVANT_EVENTS` in `journal_parser.py` is commented "accept both US and UK spellings"; `parse_construction_depot` in `colonisation_event_parser.py` lists "US/UK spellings (handled by RELEVANT_EVENTS / dispatch)" among the formats its docstring claims to handle. It said it a third time through a dispatch chain whose set literals were shaped to hold more than one name each; that chain is now a lookup table, so the claim no longer has a place to hide.

None of it is there. The set held `"ColonisationContribution"` twice, which is how it went unnoticed: a set deduplicates, so the second entry was invisible at runtime and the slot that should have carried the z-spelling was silently consumed. `Coloniz` does not appear anywhere in `backend/src` or `backend/tests`. Any journal line carrying `ColonizationConstructionDepot` or `ColonizationContribution` is dropped by the `event_type not in RELEVANT_EVENTS` guard before any parser sees it.

The duplicate is removed, which is a no-op at runtime and is as far as this should go without a decision. **Needs a ruling**, because both directions change something:

- Implement it: add both z-spellings to `RELEVANT_EVENTS` and to `_EVENT_PARSERS`, pointing at the same two functions. That makes the parser start accepting events it currently drops, which is a behaviour change and wants a test with a real US-spelled journal line.
- Delete the claim: strip both mentions so nothing promises a capability the parser does not have.

I would implement it, because the game writes what it writes and dropping an event silently is the worse failure. It needs your call on whether Frontier ever emits the z-spelling; if they never have, deleting the claim is the honest and cheaper answer.

---

## Looks like debt, not worth touching

- The fourteen `test_coverage_*.py` modules being named after the gate rather than after behaviour. Ugly and honest. Enforcing what they achieve matters more than renaming them; redistributing them into behaviour-named modules is a later tidy. The installer suite does not repeat the pattern: its files are named after the module under test.
- `backend/tools/check_live_carrier_api.py` and `debug_carrier_orders.py` printing to stdout. Development instruments, correctly separated into `tools/`.
- The three architecture documents (`ARCHITECTURE.md` plus a backend and a frontend companion). A split-stack project legitimately needs more than one; the root file indexes them.
- `PROJECT_SETUP.md` and `GameGlass-Integration.md` alongside `DEVELOPMENT-README.md`. Distinct subjects.
- `buildinstaller.py` at 396 lines. Delivery script, deliberately outside the structural suite's scan.

## Not debt (do not "fix" these)

These look like candidates but are correct as they stand; changing them would regress or add cost for nothing.

- **The 100% gate itself.** It is the right target and the suite genuinely reaches it, now across `backend/src` and the Qt-free half of `installer/` together.
- **`IColonisationRepository` as a named interface with one implementation.** It looks like ceremony; it is the seam that lets the services be tested without a database; it is also the boundary the structural suite now asserts.
- **The journal-file watcher polling rather than using filesystem notifications.** Elite Dangerous appends to journal files in a way that OS notification APIs report inconsistently across platforms. Polling is the reliable choice here.
- **`backend/src/__init__.py` resolving `VERSION` and `BUILD_ID` from two locations** (source tree, then beside the frozen executable). That dual lookup is what makes the same code work from a checkout and from a packaged build; it is also why `BUILD_ID` can be untracked and gitignored while the packaged app still reports one: `buildexe.py` writes it into the payload and the resolver copes with it being absent from a source checkout.
- **The separate `runtime/` package holding `app_runtime.py` and `launcher_components.py`.** A backend that ships as a desktop application needs an explicit runtime layer distinct from the web app; keeping it out of `api` and `services` is correct.
- **`installer/ui` and `installer/app.py` sitting outside the coverage gate.** They are the setup program's Qt widget surface and its process-level composition root, excluded on exactly the grounds the backend's runtime shell is. Everything worth asserting was factored out into `installer/ops` and `installer/state` first; those are gated at 100%.
- **The setup program shelling out to `tasklist`, `taskkill` and PowerShell rather than using COM or a process library.** It keeps the compiled onefile down to PySide6 plus the standard library; every one of those calls goes through a single injectable seam, so the choice costs nothing in testability.
- **LGPL-3.0.** Aligned with the Qt-based installer; deliberate.
