# Colonisation Assistant: Technical Debt

A standing reference to the project's outstanding technical debt. It records what is still open, weighs whether each item is worth doing and gives the rationale. Every item is a behaviour-preserving internal concern: nothing here proposes reverting a feature or changing any UI or UX behaviour. Scope is the whole repository (the FastAPI backend under `backend/`, the React front end under `frontend/`, the runtime and launcher, the bespoke installer, the delivery scripts and the GitHub Pages site) read against `ARCHITECTURE.md` and its two companion documents.

---

## 1. There is no structural test of any kind

The backend has a clean shape (`api`, `services`, `repositories`, `models`, `runtime`, `config`) and `ARCHITECTURE_1_backend.md` describes it. Nothing enforces it.

The direction most worth protecting is `repositories` and `models` staying free of `api` and `services`; `services` staying free of `api`. `IColonisationRepository` already exists as an interface, so the seam is designed; it is just unguarded. A single AST import scan asserting those two rules is the cheapest structural work available in this repository.

A module-size assertion belongs in the same file. Nineteen source and test files still exceed 400 lines (the largest is `carrier_service.py` at 965), so it will need an explicit allowlist to be adoptable at all: Calendifier's `_LEGACY_OVER_LIMIT` plus a staleness test is the pattern that works on a codebase which predates the rule. Building that allowlist and keeping it honest is a job in its own right, which is why this item is still open even though the setup program was split.

The `installer/` package and its suite are already clear of the limit (the largest are `installer/ui/main_window.py` at 332 and `tests/installer/test_install_ops.py` at 326) and would go into the test with no allowance.

## 2. `carrier_service.py` is 965 lines and the front end has three files over 500

| File | Lines |
|---|---|
| `backend/src/services/carrier_service.py` | 965 |
| `frontend/src/components/FleetCarriers/FleetCarriersPanel.tsx` | 752 |
| `frontend/src/App.tsx` | 651 |
| `frontend/src/components/SiteList/SiteList.tsx` | 598 |
| `backend/src/services/journal_ingestion.py` | 526 |
| `backend/src/runtime/app_runtime.py` | 523 |

`carrier_service.py` is the one to take first. It is the largest non-installer source file, it has its own 785-line API test and its own 670-line coverage test; fleet-carrier state reconstruction from journal events is the most intricate logic in the project. Splitting it along the seams the tests already imply (order reconstruction, docking context, cargo and market state) would make each part reviewable.

`App.tsx` at 651 lines is the second: a root component that large is usually holding state that belongs in hooks; `useKeepAwake.ts` at 406 shows the project already knows how to write them.

## 3. Around thirty broad exception handlers, concentrated on the startup path

`backend/src/main.py` has fourteen, `config.py` five, `backend/src/__init__.py` four and `launcher.py` three. About half carry `# noqa: BLE001` with no reason text; the rest carry nothing.

`main.py` and `launcher.py` are where the FastAPI server, the file watcher and the WebView runtime are brought up. A swallowed exception there is the difference between an application that fails visibly and one that opens to an empty panel. `config.py`'s five are on settings loading, where the fallback is a default the user did not choose and was not told about.

Give each a written reason and narrow where the specific exception is known. The two in `api/carriers.py` and `api/journal.py` are at an HTTP boundary and are fine as broad handlers; they just need the reason.

## 4. Five near-identical distro launcher scripts

`run-edca-built-arch.sh`, `run-edca-built-debian.sh`, `run-edca-built-fedora.sh`, `run-edca-built-rhel.sh` and `run-edca-built-void.sh`, plus `run-edca.sh` and `run-edca.bat`.

Five scripts that differ only in package-manager invocation means five places to update when the launch sequence changes; four of them will be stale before anyone notices because most users are on one distro. Collapse them into one script that detects the package manager (`pacman`, `apt`, `dnf`, `xbps-install`) and branches, which is a dozen lines and one file to maintain.

## 5. The pre-commit hook runs a fraction of the gate, from a virtual environment that does not exist

`.githooks/pre-commit` formats staged Python files with black and then runs `pytest -q -c backend/pytest.ini backend/tests`. That is the backend half of the gate only. The installer suite lives at `tests/` and needs the repository root configuration, so a commit that breaks it (or drops the setup program's Qt-free packages below 100%) still passes the hook.

The interpreter selection is worse. The hook prefers `backend/.venv/bin/python`, then `backend/.venv/Scripts/python.exe`; only then does it fall back to whatever `black` and `pytest` are on `PATH`. There is no `backend/.venv` anywhere in this repository. The environment that actually has the tooling is `venv/` at the root; a `backend/venv/` directory exists but has no pytest in it. So the hook always takes the `PATH` branch; which interpreter that is depends on which shell the commit was made from.

The fix is small and entirely within the hook: point it at the root configuration (`pytest -q` from the repository root, which is what `pytest.ini` is now set up to do) and at `venv/`. It is left alone here deliberately, because changing a hook and the code it guards in the same piece of work means neither gets a clean before-and-after.

## 6. flake8 and ruff are installed but nothing runs them; flake8 also has no configuration

Both are now in `backend/requirements-dev.txt` and `backend/requirements-dev-linux.txt`; both are installed in `venv/` and `backend/venv/`. The `installer/` package, `installer_main.py` and `tests/` are clean under `black --check`, `ruff check --isolated` and `flake8 --max-line-length=88`. Nothing enforces any of it: the hook runs black and the backend suite only (item 5); there is no lint step in CI.

The `--max-line-length=88` is load-bearing and is its own small gap. There is no `.flake8`, `setup.cfg` or `tox.ini` anywhere in the repository, so flake8 defaults to 79 characters while black is configured for 88 in `backend/pyproject.toml`. Run bare, flake8 reports fifteen E501s against lines black itself produced. Give flake8 a configuration file that sets 88 and the two tools stop disagreeing.

The rest of the repository is not clean, so turning either linter on repo-wide is a separate job rather than a flag flip. The proportionate next step is to add `ruff check --isolated installer installer_main.py tests` and the matching flake8 run to the hook, which locks in the surface that is already clean without demanding the sweep first.

The written `[tool.ruff]` section in `backend/pyproject.toml` has never been run and is stale against current ruff: it emits `The top-level linter settings are deprecated in favour of their counterparts in the lint section` and wants `extend-select` moved to `lint.extend-select` and `isort` to `lint.isort`. Fix that at the same time or the first real run starts with a warning.

---

## Looks like debt, not worth touching

- The fourteen `test_coverage_*.py` modules being named after the gate rather than after behaviour. Ugly and honest. Enforcing what they achieve matters more than renaming them; redistributing them into behaviour-named modules is a later tidy. The installer suite does not repeat the pattern: its files are named after the module under test.
- `backend/tools/check_live_carrier_api.py` and `debug_carrier_orders.py` printing to stdout. Development instruments, correctly separated into `tools/`.
- The three architecture documents (`ARCHITECTURE.md` plus a backend and a frontend companion). A split-stack project legitimately needs more than one; the root file indexes them.
- `PROJECT_SETUP.md` and `GameGlass-Integration.md` alongside `DEVELOPMENT-README.md`. Distinct subjects.
- `buildinstaller.py` at 396 lines. Delivery script, exempt from the cap by design.

## Not debt (do not "fix" these)

These look like candidates but are correct as they stand; changing them would regress or add cost for nothing.

- **The 100% gate itself.** It is the right target and the suite genuinely reaches it, now across `backend/src` and the Qt-free half of `installer/` together.
- **`IColonisationRepository` as a named interface with one implementation.** It looks like ceremony; it is the seam that lets the services be tested without a database; it is also the boundary item 1 wants asserted.
- **The journal-file watcher polling rather than using filesystem notifications.** Elite Dangerous appends to journal files in a way that OS notification APIs report inconsistently across platforms. Polling is the reliable choice here.
- **`backend/src/__init__.py` resolving `VERSION` and `BUILD_ID` from two locations** (source tree, then beside the frozen executable). That dual lookup is what makes the same code work from a checkout and from a packaged build; it is also why `BUILD_ID` can be untracked and gitignored while the packaged app still reports one: `buildexe.py` writes it into the payload and the resolver copes with it being absent from a source checkout.
- **The separate `runtime/` package holding `app_runtime.py` and `launcher_components.py`.** A backend that ships as a desktop application needs an explicit runtime layer distinct from the web app; keeping it out of `api` and `services` is correct.
- **`installer/ui` and `installer/app.py` sitting outside the coverage gate.** They are the setup program's Qt widget surface and its process-level composition root, excluded on exactly the grounds the backend's runtime shell is. Everything worth asserting was factored out into `installer/ops` and `installer/state` first; those are gated at 100%.
- **The setup program shelling out to `tasklist`, `taskkill` and PowerShell rather than using COM or a process library.** It keeps the compiled onefile down to PySide6 plus the standard library; every one of those calls goes through a single injectable seam, so the choice costs nothing in testability.
- **LGPL-3.0.** Aligned with the Qt-based installer; deliberate.
