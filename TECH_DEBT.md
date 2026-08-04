# Colonisation Assistant: Technical Debt

A standing reference to the project's outstanding technical debt. It records what is still open, weighs whether each item is worth doing and gives the rationale. Every item is a behaviour-preserving internal concern: nothing here proposes reverting a feature or changing any UI or UX behaviour. Scope is the whole repository (the FastAPI backend under `backend/`, the React front end under `frontend/`, the runtime and launcher, the bespoke installer, the delivery scripts and the GitHub Pages site) read against `ARCHITECTURE.md` and its two companion documents.

---

## 1. There are two `pytest.ini` files, and the root one silently drops the coverage gate

`backend/pytest.ini` carries the gate:

```
addopts =
    -v
    --cov=src
    --cov-report=html
    --cov-report=term-missing
    --cov-fail-under=100
```

The root `pytest.ini` has `testpaths = backend/tests` and **no `addopts` at all**. Its own comment explains why it exists: "This exists so running `pytest` from the project root (common in VS Code / CI) uses a writable cache directory and the backend test suite by default."

So the invocation the file itself describes as the common one is the invocation with no gate. `pytest` at the root collects and runs every backend test, reports them all passing and measures nothing. `pytest` inside `backend/` enforces 100%. Same tests, same code, two different verdicts depending on the working directory, and the more likely directory is the weaker one.

This is first because it silently invalidates the project's strongest quality claim, and because the fix is to copy four lines from one file to the other (adjusting `--cov=src` to `--cov=backend/src`). Better still, delete the root file and keep one configuration, moving the cache-directory setting into the backend one.

The evidence that the gate matters here is in the test names: eight modules are called `test_coverage_*.py` (`test_coverage_journal_ingestion`, `test_coverage_file_watcher`, `test_coverage_carrier_service`, `test_coverage_repository`, `test_coverage_api_misc`, `test_coverage_version_utils` and others), totalling roughly 3,000 lines written specifically to reach 100%. That work is real and it is currently unenforced from the directory most people run tests in.

## 2. `installer/app.py` is 1687 lines and outside every gate

The largest file in the repository, by more than a factor of one and a half. `--cov=src` means it contributes nothing to coverage, and there is no structural test in the project, so nothing measures its size either.

It is a PySide6 application in its own right doing payload extraction, registry writes, shortcut creation and per-user deployment, and a defect in it lands on a user's machine before the application ever starts.

The proportionate fix is the split Meridian uses: `installer/ops` for the Qt-free logic (paths, registry, extraction, shortcuts) brought into the coverage source, and `installer/ui` left as the untested widget surface.

## 3. There is no structural test of any kind

The backend has a clean shape (`api`, `services`, `repositories`, `models`, `runtime`, `config`) and `ARCHITECTURE_1_backend.md` describes it. Nothing enforces it.

The direction most worth protecting is `repositories` and `models` staying free of `api` and `services`, and `services` staying free of `api`. `IColonisationRepository` already exists as an interface, so the seam is designed; it is just unguarded. A single AST import scan asserting those two rules is the cheapest structural work available in this repository.

A module-size assertion belongs in the same file. Twenty-four files currently exceed 400 lines, so it will need an explicit allowlist to be adoptable at all: Calendifier's `_LEGACY_OVER_LIMIT` plus a staleness test is the pattern that works on a codebase which predates the rule.

## 4. `carrier_service.py` is 965 lines and the front end has three files over 500

| File | Lines |
|---|---|
| `backend/src/services/carrier_service.py` | 965 |
| `frontend/src/components/FleetCarriers/FleetCarriersPanel.tsx` | 752 |
| `frontend/src/App.tsx` | 651 |
| `frontend/src/components/SiteList/SiteList.tsx` | 598 |
| `backend/src/services/journal_ingestion.py` | 526 |
| `backend/src/runtime/app_runtime.py` | 523 |

`carrier_service.py` is the one to take first. It is the largest non-installer source file, it has its own 785-line API test and its own 670-line coverage test, and fleet-carrier state reconstruction from journal events is the most intricate logic in the project. Splitting it along the seams the tests already imply (order reconstruction, docking context, cargo and market state) would make each part reviewable.

`App.tsx` at 651 lines is the second: a root component that large is usually holding state that belongs in hooks, and `useKeepAwake.ts` at 406 shows the project already knows how to write them.

## 5. `BUILD_ID` is build output that is tracked

`buildexe.py` writes `BUILD_ID` on every build ("a build identifier (UTC timestamp + short git SHA)"), and the file is tracked, currently reading `20260701T225500Z-df283ad`.

So every build dirties the working tree with a change nobody intends to commit, and the committed value is whatever the last build happened to produce rather than anything meaningful about the current source. `backend/src/__init__.py` reads it from the source tree or from beside the frozen executable, so the runtime needs the file to exist at package time, not in git.

Untrack it, add it to `.gitignore`, and have `buildexe.py` continue writing it into the payload. `backend/src/__init__.py` already has a fallback path for when it is absent, so a source checkout keeps working.

`VERSION` at `2.9.0` stays tracked and is correct.

## 6. Around thirty broad exception handlers, concentrated on the startup path

`backend/src/main.py` has fourteen, `config.py` five, `backend/src/__init__.py` four and `launcher.py` three. About half carry `# noqa: BLE001` with no reason text; the rest carry nothing.

`main.py` and `launcher.py` are where the FastAPI server, the file watcher and the WebView runtime are brought up. A swallowed exception there is the difference between an application that fails visibly and one that opens to an empty panel. `config.py`'s five are on settings loading, where the fallback is a default the user did not choose and was not told about.

Give each a written reason and narrow where the specific exception is known. The two in `api/carriers.py` and `api/journal.py` are at an HTTP boundary and are fine as broad handlers; they just need the reason.

## 7. Five near-identical distro launcher scripts

`run-edca-built-arch.sh`, `run-edca-built-debian.sh`, `run-edca-built-fedora.sh`, `run-edca-built-rhel.sh` and `run-edca-built-void.sh`, plus `run-edca.sh` and `run-edca.bat`.

Five scripts that differ only in package-manager invocation means five places to update when the launch sequence changes, and four of them will be stale before anyone notices because most users are on one distro. Collapse them into one script that detects the package manager (`pacman`, `apt`, `dnf`, `xbps-install`) and branches, which is a dozen lines and one file to maintain.

---

## Looks like debt, not worth touching

- The eight `test_coverage_*.py` modules being named after the gate rather than after behaviour. Ugly and honest. Item 1 is about enforcing what they achieve, not renaming them; redistributing them into behaviour-named modules is a later tidy.
- `backend/tools/check_live_carrier_api.py` and `debug_carrier_orders.py` printing to stdout. Development instruments, correctly separated into `tools/`.
- The three architecture documents (`ARCHITECTURE.md` plus a backend and a frontend companion). A split-stack project legitimately needs more than one, and the root file indexes them.
- `PROJECT_SETUP.md` and `GameGlass-Integration.md` alongside `DEVELOPMENT-README.md`. Distinct subjects.
- `buildinstaller.py` at 379 lines. Delivery script, exempt from the cap by design.

## Not debt (do not "fix" these)

These look like candidates but are correct as they stand; changing them would regress or add cost for nothing.

- **The 100% gate in `backend/pytest.ini` itself.** It is the right target and the suite genuinely reaches it. Item 1 is about the root file undermining it, not about the gate being too strict.
- **`IColonisationRepository` as a named interface with one implementation.** It looks like ceremony; it is the seam that lets the services be tested without a database, and it is the boundary item 3 wants asserted.
- **The journal-file watcher polling rather than using filesystem notifications.** Elite Dangerous appends to journal files in a way that OS notification APIs report inconsistently across platforms. Polling is the reliable choice here.
- **`backend/src/__init__.py` resolving `VERSION` and `BUILD_ID` from two locations** (source tree, then beside the frozen executable). That dual lookup is what makes the same code work from a checkout and from a packaged build. Item 5 removes `BUILD_ID` from git, not from this resolver.
- **The separate `runtime/` package holding `app_runtime.py` and `launcher_components.py`.** A backend that ships as a desktop application needs an explicit runtime layer distinct from the web app; keeping it out of `api` and `services` is correct.
- **LGPL-3.0.** Aligned with the Qt-based installer, and deliberate.
