# Colonisation Assistant: Technical Debt

A standing reference to the project's outstanding technical debt. It records what is still open, weighs whether each item is worth doing and gives the rationale. Every item is a behaviour-preserving internal concern: nothing here proposes reverting a feature or changing any UI or UX behaviour. Scope is the whole repository (the FastAPI backend under `backend/`, the React front end under `frontend/`, the runtime and launcher, the bespoke installer, the delivery scripts and the GitHub Pages site) read against `ARCHITECTURE.md` and its two companion documents.

---

## 1. The US spelling of the colonisation events is documented but not implemented

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
