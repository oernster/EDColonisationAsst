# Testing EDCA

How to run the test suites and what the coverage gate means.

Related documents: [README.md](README.md),
[DEVELOPMENT-README.md](DEVELOPMENT-README.md),
[ARCHITECTURE_1_backend.md](ARCHITECTURE_1_backend.md).

---

## Backend (pytest)

Run from the `backend/` directory with the dev environment installed
(`pip install -r requirements-dev.txt`):

```bash
pytest -v --cov
```

This runs the full unit suite with branch coverage and enforces the
coverage gate: the run **fails if coverage of the gated surface is below
100%**. The gate is configured in [backend/pytest.ini](backend/pytest.ini)
(`--cov-fail-under=100`) with the coverage scope defined in
[backend/pyproject.toml](backend/pyproject.toml) under `[tool.coverage.run]`.

Useful variants:

```bash
pytest -v --cov --cov-report=html   # HTML report in backend/htmlcov/
pytest tests/unit/test_models.py -v # a single file
pytest -q --no-cov                  # quick run without the gate
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

## Frontend (vitest)

Run from the `frontend/` directory:

```bash
npm test                 # vitest suite
npm run test:coverage    # with coverage
npm run type-check       # tsc
npm run lint             # eslint
```

## Pre-commit hook

With the shared hook enabled (`git config core.hooksPath .githooks`), every
commit formats staged Python files with black and runs the backend suite
including the coverage gate, so a commit cannot land below 100% on the
gated surface.
