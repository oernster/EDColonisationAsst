# Colonisation Assistant: Technical Debt

A standing reference to the project's outstanding technical debt. It records what is still open, weighs whether each item is worth doing and gives the rationale. Nothing here proposes reverting a feature or changing any UI or UX behaviour, though the open item below is user-visible in its effect: it is a measured startup stall rather than an internal tidy. Scope is the whole repository (the FastAPI backend under `backend/`, the React front end under `frontend/`, the runtime and launcher, the bespoke installer, the delivery scripts and the GitHub Pages site) read against `ARCHITECTURE.md` and its two companion documents.

**One item is open.** It is recorded first, followed by the standing decisions: what only looks like debt and what is correct as it stands.

---

## Open

1. **The first-run journal backfill holds the event loop for the whole of its run.** `prime_colonisation_database_if_empty` in `backend/src/services/startup_ingestion.py` is scheduled with `asyncio.create_task`, so it does not block the ASGI lifespan; the comment in `main.py` reads as though that settles it. It does not. A detached task still owns the single event loop while it runs; this one never yields it. Measured against a real 72-file, 67 MB journal folder, the backfill takes 137.5 s and blocks the loop for 137.4 s in one unbroken stall, so neither `/api/health` nor `/app/` can be answered for the duration. That is what the startup splash reports as "Starting the local backend..." on a first launch. It also sits only 43 s inside the 180 s readiness budget in `runtime/splash.py`, so a slower machine or a larger journal folder turns the stall into a readiness timeout.

   The cost is not parsing. Profiled over the six largest files (29.3 MB, 39.3 s total), `sqlite3.Connection.commit` accounts for 30.3 s of it, 77%, across 4,068 calls at roughly 7.4 ms each: one commit per depot event, each preceded by a fresh `sqlite3.connect` and an `nt.mkdir`. JSON decoding totals 0.27 s across the same run.

   The repair is a transaction and connection strategy for the backfill (either one transaction across the import or a connection held open for its duration), not a faster parser and not a worker thread: the work is fsync-bound, so moving it off the loop without changing the commit pattern would preserve the cost and add a threading problem to it. Because it changes persistence semantics on the path every other write shares, it wants its own unit of work with its own tests rather than being folded into an unrelated change.

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
- **`RELEVANT_EVENTS` accepting the UK spelling of the colonisation events only.** Frontier is a UK studio and writes `ColonisationConstructionDepot` and `ColonisationContribution`, so a z-spelled event is one the game does not emit. Adding the z-spellings would widen the parser for a case that cannot arrive and would need a fabricated journal line to test. `Coloniz` appears nowhere in `backend/src` or `backend/tests`; that is correct rather than an omission. The parser used to claim otherwise in two comments, which is why this is written down.
- **The journal-file watcher polling rather than using filesystem notifications.** Elite Dangerous appends to journal files in a way that OS notification APIs report inconsistently across platforms. Polling is the reliable choice here.
- **`backend/src/__init__.py` resolving `VERSION` and `BUILD_ID` from two locations** (source tree, then beside the frozen executable). That dual lookup is what makes the same code work from a checkout and from a packaged build; it is also why `BUILD_ID` can be untracked and gitignored while the packaged app still reports one: `buildexe.py` writes it into the payload and the resolver copes with it being absent from a source checkout.
- **The separate `runtime/` package holding `app_runtime.py` and `launcher_components.py`.** A backend that ships as a desktop application needs an explicit runtime layer distinct from the web app; keeping it out of `api` and `services` is correct.
- **`installer/ui` and `installer/app.py` sitting outside the coverage gate.** They are the setup program's Qt widget surface and its process-level composition root, excluded on exactly the grounds the backend's runtime shell is. Everything worth asserting was factored out into `installer/ops` and `installer/state` first; those are gated at 100%.
- **The setup program shelling out to `tasklist`, `taskkill` and PowerShell rather than using COM or a process library.** It keeps the compiled onefile down to PySide6 plus the standard library; every one of those calls goes through a single injectable seam, so the choice costs nothing in testability.
- **LGPL-3.0.** Aligned with the Qt-based installer; deliberate.
