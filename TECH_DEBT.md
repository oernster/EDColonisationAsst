# Colonisation Assistant: Technical Debt

A standing reference to the project's outstanding technical debt. It records what is still open, weighs whether each item is worth doing and gives the rationale. Every item is a behaviour-preserving internal concern: nothing here proposes reverting a feature or changing any UI or UX behaviour. Scope is the whole repository (the FastAPI backend under `backend/`, the React front end under `frontend/`, the runtime and launcher, the bespoke installer, the delivery scripts and the GitHub Pages site) read against `ARCHITECTURE.md` and its two companion documents.

---

## 1. `carrier_service.py` is 965 lines and the front end has three files over 500

| File | Lines |
|---|---|
| `backend/src/services/carrier_service.py` | 965 |
| `frontend/src/components/FleetCarriers/FleetCarriersPanel.tsx` | 752 |
| `frontend/src/App.tsx` | 651 |
| `frontend/src/components/SiteList/SiteList.tsx` | 598 |
| `backend/src/services/journal_ingestion.py` | 526 |
| `backend/src/runtime/app_runtime.py` | 523 |

`carrier_service.py` is the one to take first. It is the largest non-installer source file, it has its own 793-line API test and its own 670-line coverage test; fleet-carrier state reconstruction from journal events is the most intricate logic in the project. Splitting it along the seams the tests already imply (order reconstruction, docking context, cargo and market state) would make each part reviewable.

`App.tsx` at 651 lines is the second: a root component that large is usually holding state that belongs in hooks; `useKeepAwake.ts` at 406 shows the project already knows how to write them.

These nineteen files (seven backend source, eight backend test, four front end) are the whole of `_LEGACY_OVER_LIMIT` in [tests/structural/test_structural.py](tests/structural/test_structural.py). The cap is asserted, so nothing new joins them; a staleness test fails on any entry whose file is no longer over the limit. The list can only shrink and this item closes when it is empty. The `installer/` package and its suite are already clear of the limit and carry no allowance.

`backend/tests/unit/test_coverage_repository.py` sits at 391, inside the band where the next edit pushes it over. It is within the cap today, so the structural suite passes it; whoever touches it next should take it to 350 or below rather than shave two lines off.

## 2. Around thirty broad exception handlers, concentrated on the startup path

`backend/src/main.py` has fourteen, `config.py` five, `backend/src/__init__.py` four and `launcher.py` three. About half carry `# noqa: BLE001` with no reason text; the rest carry nothing.

`main.py` and `launcher.py` are where the FastAPI server, the file watcher and the WebView runtime are brought up. A swallowed exception there is the difference between an application that fails visibly and one that opens to an empty panel. `config.py`'s five are on settings loading, where the fallback is a default the user did not choose and was not told about.

Give each a written reason and narrow where the specific exception is known. The two in `api/carriers.py` and `api/journal.py` are at an HTTP boundary and are fine as broad handlers; they just need the reason.

## 3. `backend/` is outside the lint step and a long way from passing

The configuration gap is closed. `.flake8` sets 88 at the repository root so flake8 and black no longer disagree, the stale top-level `[tool.ruff]` keys have moved under `[tool.ruff.lint]`; the pre-commit hook now runs `ruff check --isolated` and `flake8` over `installer`, `installer_main.py` and `tests` before the suite. That surface passes both linters and the hook fails on a planted violation, so it will stay passing.

What is left is the reason the step is scoped that narrowly. `backend/src` is not close to clean and widening the list is a sweep, not a flag flip. Measured 2026-08-07 with ruff 0.16.1:

| Rule | Count | What it is |
|---|---|---|
| UP045, UP006, UP035, UP037, UP017 | 226 | `Optional[X]`, `typing.List` and friends against a `py311` target |
| BLE001 | 70 | Broad `except Exception`, the same population as item 2 |
| E402 | 56 | Imports after code, mostly the runtime path juggling `sys.path` |
| I001 | 45 | Import blocks out of order |
| S110, S112 | 34 | `try`/`except`/`pass` and `try`/`except`/`continue` |
| E501 | 26 | Over 88 characters |
| F401 | 24 | Unused imports |
| everything else | 77 | RUF, PIE, ASYNC, B, TRY, FURB, SIM, PERF, PYI |

558 in total, 322 of them auto-fixable. `flake8` at 88 over the same tree reports 59.

Three things make this one job rather than eight. The 226 typing findings are mechanical and safe under `--fix`. The 70 BLE001 findings are item 2 seen from the other end, so doing item 2 first shrinks this by an eighth and doing this first would pre-empt the judgement item 2 asks for. The E402 and F401 counts include the deliberate re-exports in `launcher.py`, which want `__all__` or a targeted `# noqa` with a reason rather than deletion, so the auto-fixer cannot be trusted to run unattended over the whole tree.

`frontend/` has no linter wired at all and is not counted above.

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
