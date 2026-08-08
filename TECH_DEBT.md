# Colonisation Assistant: Technical Debt

A standing reference to the project's outstanding technical debt. It records what is still open, weighs whether each item is worth doing and gives the rationale. Every item is a behaviour-preserving internal concern: nothing here proposes reverting a feature or changing any UI or UX behaviour. Scope is the whole repository (the FastAPI backend under `backend/`, the React front end under `frontend/`, the runtime and launcher, the bespoke installer, the delivery scripts and the GitHub Pages site) read against `ARCHITECTURE.md` and its two companion documents.

**Nothing is open.** What follows is the standing decisions that keep it that way: what only looks like debt and what is correct as it stands.

---

## Looks like debt, not worth touching

- The eighteen `test_coverage_*.py` modules being named after the gate rather than after behaviour. Ugly and honest. Enforcing what they achieve matters more than renaming them; redistributing them into behaviour-named modules is a later tidy. Newer suites do not repeat the pattern: the carrier and installer files are named after the behaviour or the module under test.
- The four scripts in `backend/tools/` printing to stdout. Development instruments, correctly separated into `tools/` and outside the coverage gate.
- The three architecture documents (`ARCHITECTURE.md` plus a backend and a frontend companion). A split-stack project legitimately needs more than one; the root file indexes them.
- `PROJECT_SETUP.md` and `GameGlass-Integration.md` alongside `DEVELOPMENT-README.md`. Distinct subjects.

## Not debt (do not "fix" these)

These look like candidates but are correct as they stand; changing them would regress or add cost for nothing.

- **The 100% gate itself.** It is the right target and the suite genuinely reaches it, now across `backend/src` and the Qt-free half of `installer/` together.
- **`IColonisationRepository` as a named interface with one implementation.** It looks like ceremony; it is the seam that lets the services be tested without a database; it is also the boundary the structural suite now asserts.
- **`RELEVANT_EVENTS` accepting the UK spelling of the colonisation events only.** Frontier is a UK studio and writes `ColonisationConstructionDepot` and `ColonisationContribution`, so a z-spelled event is one the game does not emit. Adding the z-spellings would widen the parser for a case that cannot arrive and would need a fabricated journal line to test. `Coloniz` appears nowhere in `backend/src` or `backend/tests`; that is correct rather than an omission. The parser used to claim otherwise in two comments, which is why this is written down.
- **The colonisation database running in WAL with `synchronous=NORMAL`, on one shared connection.** Both look like corners cut and neither is. The database is derived data, not a system of record: every row is rebuilt from the commander's journal files, which is what `initialise` already relies on when it deletes a database whose schema it cannot read. So the fsync per commit that `FULL` performs buys a durability guarantee this data does not need, while costing one fsync per depot event. Transactions remain atomic, consistent and isolated; only durability across an operating system crash is traded, at a price of one automatic rebuild. Sharing the connection is not a widened transaction boundary either: `with conn:` commits or rolls back and never closes, so each repository method still owns exactly one transaction. Measured end to end on a real 72-file, 67 MB journal folder, the first-run backfill went from 137.5 s to 2.2 s and the worst event-loop stall from 137.4 s to 0.5 s, with the resulting database identical field for field. Reverting either change reinstates a two-minute startup during which the backend cannot answer `/api/health`.
- **The journal-file watcher polling rather than using filesystem notifications.** Elite Dangerous appends to journal files in a way that OS notification APIs report inconsistently across platforms. Polling is the reliable choice here.
- **`backend/src/__init__.py` resolving `VERSION` and `BUILD_ID` from two locations** (source tree, then beside the frozen executable). That dual lookup is what makes the same code work from a checkout and from a packaged build; it is also why `BUILD_ID` can be untracked and gitignored while the packaged app still reports one: `buildexe.py` writes it into the payload and the resolver copes with it being absent from a source checkout.
- **The separate `runtime/` package holding `app_runtime.py` and `launcher_components.py`.** A backend that ships as a desktop application needs an explicit runtime layer distinct from the web app; keeping it out of `api` and `services` is correct.
- **`installer/ui` and `installer/app.py` sitting outside the coverage gate.** They are the setup program's Qt widget surface and its process-level composition root, excluded on exactly the grounds the backend's runtime shell is. Everything worth asserting was factored out into `installer/ops` and `installer/state` first; those are gated at 100%.
- **The setup program shelling out to `tasklist`, `taskkill` and PowerShell rather than using COM or a process library.** It keeps the compiled onefile down to PySide6 plus the standard library; every one of those calls goes through a single injectable seam, so the choice costs nothing in testability.
- **LGPL-3.0.** Aligned with the Qt-based installer; deliberate.
