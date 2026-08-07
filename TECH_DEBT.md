# Colonisation Assistant: Technical Debt

A standing reference to the project's outstanding technical debt. It records what is still open, weighs whether each item is worth doing and gives the rationale. Every item is a behaviour-preserving internal concern: nothing here proposes reverting a feature or changing any UI or UX behaviour. Scope is the whole repository (the FastAPI backend under `backend/`, the React front end under `frontend/`, the runtime and launcher, the bespoke installer, the delivery scripts and the GitHub Pages site) read against `ARCHITECTURE.md` and its two companion documents.

---

## 1. Eighteen files are over the 400-line module cap

`carrier_service.py` was the first and is done: 960 lines split into six modules along the seams its own section markers already described, none over 263 lines.

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

Eighteen entries remain in `_LEGACY_OVER_LIMIT` in [tests/structural/test_structural.py](tests/structural/test_structural.py), measured 2026-08-07:

| Lines | File |
|---|---|
| 927 | `backend/tests/unit/test_file_watcher.py` |
| 794 | `backend/tests/unit/test_coverage_journal_ingestion.py` |
| 793 | `backend/tests/unit/test_api_carriers.py` |
| 752 | `frontend/src/components/FleetCarriers/FleetCarriersPanel.tsx` |
| 745 | `backend/tests/unit/test_coverage_file_watcher.py` |
| 670 | `backend/tests/unit/test_coverage_carrier_service.py` |
| 651 | `frontend/src/App.tsx` |
| 598 | `frontend/src/components/SiteList/SiteList.tsx` |
| 575 | `backend/src/services/journal_ingestion.py` |
| 542 | `backend/src/runtime/app_runtime.py` |
| 540 | `backend/tests/unit/test_runtime_components.py` |
| 494 | `backend/src/main.py` |
| 488 | `backend/src/services/journal_parser.py` |
| 470 | `backend/src/repositories/colonisation_repository.py` |
| 466 | `backend/tests/unit/test_api_routes.py` |
| 448 | `backend/tests/unit/test_journal_parser.py` |
| 425 | `backend/src/runtime/launcher_components.py` |
| 406 | `frontend/src/hooks/useKeepAwake.ts` |

The cap is asserted, so nothing new joins them; a staleness test fails on any entry whose file is no longer over the limit, which is what removed `carrier_service.py` from the list. The list can only shrink and this item closes when it is empty.

`App.tsx` at 651 is the one to take next: a root component that large is usually holding state that belongs in hooks; `useKeepAwake.ts` shows the project already knows how to write them. The six test files are the cheapest of the rest, since splitting a suite by the surface it exercises carries no behavioural risk at all.

`backend/tests/unit/test_coverage_repository.py` sits at 391, inside the band where the next edit pushes it over. It is within the cap today, so the structural suite passes it; whoever touches it next should take it to 350 or below rather than shave two lines off.

## 2. The US spelling of the colonisation events is documented but not implemented

`journal_parser.py` said it three times over: `RELEVANT_EVENTS` is commented "accept both US and UK spellings", the dispatch reaches for the parsers through set literals shaped to hold more than one name each; `_parse_construction_depot`'s docstring lists "US/UK spellings (handled by RELEVANT_EVENTS / dispatch)" among the formats it handles.

None of it is there. The set held `"ColonisationContribution"` twice, which is how it went unnoticed: a set deduplicates, so the second entry was invisible at runtime and the slot that should have carried the z-spelling was silently consumed. `Coloniz` does not appear anywhere in `backend/src` or `backend/tests`. Any journal line carrying `ColonizationConstructionDepot` or `ColonizationContribution` is dropped by the `event_type not in RELEVANT_EVENTS` guard before any parser sees it.

The duplicate is removed, which is a no-op at runtime and is as far as this should go without a decision. **Needs a ruling**, because both directions change something:

- Implement it: add both z-spellings to `RELEVANT_EVENTS` and to the two dispatch sets. That makes the parser start accepting events it currently drops, which is a behaviour change and wants a test with a real US-spelled journal line.
- Delete the claim: strip the three mentions so nothing promises a capability the parser does not have.

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
