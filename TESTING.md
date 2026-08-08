# Testing EDCA

How to run the test suites and what the coverage gate means.

Related documents: [README.md](README.md),
[DEVELOPMENT-README.md](DEVELOPMENT-README.md),
[ARCHITECTURE_1_backend.md](ARCHITECTURE_1_backend.md).

---

## Python (pytest)

Run from the **repository root** with the dev environment installed
(`pip install -r backend/requirements-dev.txt` into the root `venv/`):

```bash
python -m pytest -q
```

That is the invocation to use: it runs the backend suite and the installer
suite together under one gate. The root configuration
([pytest.ini](pytest.ini)) puts the repository root on the module search path
so the installer suite can import `installer.*`; it also points coverage at both
`backend/src` and `installer`.

Running from `backend/` still works and enforces the same gate on the backend
alone:

```bash
cd backend
pytest
```

Do not add `--cov` to either command. Both configurations already pass a
scoped `--cov`; a second bare `--cov` on the command line widens the
measurement to everything imported, including the test modules themselves.
The gate then fails at around 99% with every source file at 100%, which reads
as a coverage regression and is not one.

The two configurations must stay in step. They did not always: the root one
carried no coverage gate and no `asyncio_mode`, so a root-level run silently
skipped every asynchronous test and reported a smaller pass count than the
same suite run from `backend/`, with no gate at all. The weaker of the two was
the one the likelier invocation picked up. If you change one file, change the
other.

Either invocation runs the full unit suite with branch coverage and enforces
the coverage gate: the run **fails if coverage of the gated surface is below
100%**. The gate is configured in [backend/pytest.ini](backend/pytest.ini) and
[pytest.ini](pytest.ini) (`--cov-fail-under=100`), with the coverage scope
defined in [backend/pyproject.toml](backend/pyproject.toml) under
`[tool.coverage.run]`. An HTML report is written on every run: `backend/htmlcov/`
from `backend/`, `htmlcov/` from the root.

Useful variants, all of which need `--no-cov` because a partial selection
cannot meet a 100% gate:

```bash
pytest tests/unit/test_models.py -q --no-cov   # a single file (from backend/)
pytest -k "test_parse" -q --no-cov             # tests matching a pattern
python -m pytest tests/installer -q --no-cov   # the installer suite alone (from the root)
```

Trust the exit code, not the console text: coverage-gated runs print the
coverage table last, so `0` means all tests passed AND the gate was met;
anything non-zero means a failure that needs reading.

### What the gate covers

The gate is scoped to the testable backend surface: models, services,
repositories, API routes, configuration and utilities. Excluded via the
`omit` list in `pyproject.toml` are:

- `src/runtime/*`, `src/runtime_entry.py`, `src/tray_app.py`,
  `src/launcher.py` - the Qt runtime shell (tray, splash, launcher,
  single-instance lock, in-process uvicorn orchestration). Its pure logic
  (startup readiness monitor, menu wiring, process management, status
  messages) is deliberately extracted into testable units and covered; the
  Qt widget and OS-process surfaces themselves are exercised manually and
  via the packaged-build smoke test instead of fragile UI tests.
- `src/main.py` - the FastAPI composition root (app assembly, static
  mounts, startup wiring).
- `installer/ui/*` and `installer/app.py` - the setup program's Qt client
  and its composition root, excluded on the same grounds as the runtime
  shell above.

`installer/ops`, `installer/state`, `installer/shared`, `installer/cli.py`
and `installer/constants.py` are **inside** the gate. The setup program does
the most privileged work in the product (registry writes, shortcut creation,
per-user deployment, uninstall) and a defect in it lands on a machine before
the application ever starts, so its Qt-free half is measured rather than left
unmeasured.

Everything inside the gate must stay at 100% statement AND branch
coverage. If you add code there, add tests with it; the build fails
otherwise.

### Testing conventions

- **No mock libraries.** `unittest.mock` and `pytest-mock` are not used.
  Tests use real implementations, pytest's `monkeypatch` and hand-written
  fakes (see the Dummy* classes in
  [backend/tests/unit/test_runtime_components.py](backend/tests/unit/test_runtime_components.py)).
- Repository tests use **real SQLite databases** in pytest `tmp_path`
  directories, never mocked connections.
- FastAPI endpoints are tested through the ASGI test client, not by
  calling handlers directly.
- Qt widget behaviour is not unit-tested (see the omit rationale above);
  anything worth asserting is factored out of the widgets into plain
  Python first.

### The installer suite

[tests/installer/](tests/installer) covers the setup program. No test may
touch a real EDCA installation; three fixtures in
[tests/installer/conftest.py](tests/installer/conftest.py) are what guarantee
that:

- `scratch_keys` yields a unique `RegistryKeys` under a test-only HKCU root
  and deletes the whole subtree afterwards, so no test reads or writes the
  real Uninstall or Run registration;
- `staged_payload` redirects the payload anchors at a temporary directory and
  the tests stage a tiny tree there, so the real staged payload is never read
  and never copied;
- `isolated_profile` redirects `USERPROFILE`, `LOCALAPPDATA` and `APPDATA`
  into a temporary tree, so shortcuts and install directories land there.

Every external command goes through the hand-written `FakeRunner` in
[tests/installer/fakes.py](tests/installer/fakes.py), so no test spawns a
process, ends a real one or writes a real shortcut. The one place a genuinely
unreachable branch remains is marked `# pragma: no cover` with a one-line
reason.

`tests/` is deliberately **not** a Python package: `backend/tests` already
claims the top-level name `tests`, so a second package of that name would
shadow it. The suite imports its helpers as plain top-level modules
(`from fakes import ...`).

### The structural suite

[tests/structural/test_structural.py](tests/structural/test_structural.py)
asserts the shape the architecture documents describe. It imports nothing from
the application: it reads source files and walks their syntax trees, so it adds
no coverage and costs a fraction of a second.

Four rules:

- `models` is the innermost layer and imports nothing else from the backend.
- `repositories` stays free of `api`, `services` and `runtime`; `services`
  stays free of `api` and `runtime`; `api` stays free of `runtime`. The walk is
  over the whole syntax tree, so an import deferred inside a function counts
  exactly as one at module level.
- The setup program imports nothing from `backend/`, which is what keeps the
  compiled onefile down to PySide6 plus the standard library.
- No file exceeds 400 lines. The rule arrived with an allowlist of the nineteen
  files that were already over it, which could only shrink and which a staleness
  test emptied one entry at a time. It is empty, so the allowlist and that test
  are gone and every scanned file is now held to the limit.

The size scan reads TypeScript as well as Python. Four of the nineteen were
front-end components, so a scan that walked `*.py` only would have reported a
clean repository while `FleetCarriersPanel.tsx` sat at 752 lines. TypeScript is
measured but not parsed: the import rules are Python only.

`buildexe.py` and `buildinstaller.py` are outside every scan. They are linear
recipes read top to bottom, where splitting a sequence of flags and steps
across modules costs more than it buys.

## Frontend (vitest)

Run from the `frontend/` directory:

```bash
npm test                 # vitest suite
npm run test:coverage    # with coverage
npm run type-check       # tsc
npm run lint             # eslint
```

## Linters

The setup program, its entry point and its suite are clean under three tools,
run from the repository root:

```bash
black --check installer installer_main.py tests
ruff check --isolated installer installer_main.py tests
flake8 installer installer_main.py tests
```

flake8 needs no line-length flag any more. `.flake8` at the repository root
sets 88 to match black in `backend/pyproject.toml`, so the two tools no longer
disagree about the lines black itself produced.

`backend/src` is clean under both as well and is linted against its own
configuration:

```bash
ruff check --config backend/pyproject.toml backend/src
flake8 backend/src
```

The pre-commit hook runs every one of these before the suite, so a clean run
here means a clean hook.

The front end is linted too, by ESLint:

```bash
cd frontend
npm run lint
```

`frontend/eslint.config.js` is the flat config the ESLint 9 upgrade left the
project without, which is why this script had been failing rather than
passing. It is composed only from the plugins already in devDependencies and
is deliberately not type-aware: `npm run type-check` (`tsc --noEmit`) already
runs strict over the same files and is the better tool for anything needing
types.

## Pre-commit hook

With the shared hook enabled (`git config core.hooksPath .githooks`), every
commit formats staged Python files with black, lints the Python surface and
the front end, then runs a bare `pytest -q` from the repository root. That is the same command documented
above and the same gate: both suites, 100% coverage, exit code or nothing.

The interpreter is resolved once, from the root `venv/`, which is where the
tooling lives. If that environment is absent or lacks pytest and black the
hook stops with a named error rather than falling through to whatever is on
`PATH`, so the check that runs is never silently a different check.

One limit remains: the hook runs neither linter, because the repository is
not yet clean under either. That gap is recorded in
[TECH_DEBT.md](TECH_DEBT.md).
