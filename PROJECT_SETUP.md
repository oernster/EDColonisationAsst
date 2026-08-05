# EDCA Project Setup Guide

First-time environment setup for working on the Elite: Dangerous
Colonisation Assistant from a source checkout.

Related documents: [README.md](README.md) (end-user overview),
[DEVELOPMENT-README.md](DEVELOPMENT-README.md) (build pipeline and dev
workflows), [TESTING.md](TESTING.md) (test suites and the coverage gate),
[ARCHITECTURE.md](ARCHITECTURE.md) (system design front door).

## Prerequisites

### Backend

- Python 3.13+ (3.12 remains a supported fallback)
- Virtual environment support (`python -m venv` or `uv venv`)

### Frontend

- Node.js 18+ with npm
- A modern web browser

### Windows release builds only

- Visual Studio 2022 Build Tools with the *Desktop development with C++*
  workload (MSVC v143) and a recent Windows 10/11 SDK. See the compiler
  notes in [DEVELOPMENT-README.md](DEVELOPMENT-README.md).

### Elite: Dangerous journals

EDCA reads journal files from your local save folder, typically:

```text
C:\Users\%USERNAME%\Saved Games\Frontier Developments\Elite Dangerous
```

The path is configurable via the Settings page in the web UI or
`backend/config.yaml`.

## Project structure

```text
EDColonisationAsst/
├── README.md                 # End-user overview and doc index
├── DEVELOPMENT-README.md     # Build pipeline and dev workflows
├── TESTING.md                # Test suites and the coverage gate
├── ARCHITECTURE.md           # Architecture front door
├── ARCHITECTURE_1_backend.md # Backend architecture detail
├── ARCHITECTURE_2_frontend_and_runtime.md # Frontend + runtime detail
├── TECH_DEBT.md              # Standing record of open internal debt
├── GameGlass-Integration.md  # GameGlass shard integration
├── VERSION                   # Single source of truth for the version
├── pytest.ini                # Root pytest + coverage gate (backend + installer)
├── buildexe.py               # Windows runtime EXE build (Nuitka)
├── buildinstaller.py         # Windows GUI installer build (Nuitka)
├── installer_main.py         # Setup program entry point (Nuitka compiles this)
├── installer/                # The setup program, a separate PySide6 application
│   ├── ops/                  # side effects, no Qt (payload, copy, shortcuts, processes)
│   ├── state/                # HKCU record, version comparison, the state model
│   ├── shared/               # resource anchoring and crash logging, no Qt
│   └── ui/                   # the themed window, its dialogs and the worker thread
├── tests/installer/          # Setup program suite (inside the same 100% gate)
├── backend/                  # Python FastAPI backend
│   ├── src/                  # models, services, repositories, api, utils, runtime
│   ├── tests/unit/           # pytest suite (100% gate; see TESTING.md)
│   ├── config.yaml           # non-sensitive backend config
│   ├── requirements.txt      # runtime dependencies
│   ├── requirements-dev.txt  # dev/build dependencies (incl. Nuitka)
│   ├── pytest.ini            # backend-only pytest + coverage gate configuration
│   └── pyproject.toml        # black/isort/coverage configuration
├── frontend/                 # React + TypeScript (Vite, MUI, Zustand)
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── docs/                     # GitHub Pages site
└── run-edca*.sh / .bat       # convenience run scripts
```

`BUILD_ID` also appears at the root after a build. It is written by
`buildexe.py` and gitignored, so it is build output rather than source.

## Setup steps

### 1. Python

One environment at the repository root serves everything: the whole gated
suite, the backend suite run from `backend/`, the linters and the build
scripts.

```bash
python -m venv venv            # or: uv venv venv
venv\Scripts\activate          # Windows; source venv/bin/activate on Unix
pip install -r backend/requirements-dev.txt
```

On Linux, install `backend/requirements-dev-linux.txt` instead.

Keep it activated when you change into `backend/`; there is nothing extra
to install there.

Copy `backend/example.commander.yaml` to `backend/commander.yaml` if you
want Inara integration (the file is gitignored; never commit real keys).

### 2. Frontend

```bash
cd frontend
npm install
```

### 3. Verify

```bash
# The whole gated suite: backend plus the setup program (from the root)
python -m pytest -q

# Frontend suite (from frontend/)
npm test
```

Trust the exit code rather than the console text: a coverage-gated run
prints the coverage table last, so there is no "N passed" line to read at
the bottom.

### 4. Run in development

```bash
# Terminal 1 (project root)
uvicorn backend.src.main:app --reload

# Terminal 2 (project root)
npm --prefix frontend run dev
```

Backend: `http://localhost:8000` (Swagger at `/docs`). Frontend dev
server: `http://localhost:5173`.

### 5. Optional: enable the pre-commit hook

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
```

Every commit then formats staged Python files with black and runs the
backend suite including its coverage gate. It does not run the setup
program's suite or either linter; see [TECH_DEBT.md](TECH_DEBT.md) for what
that leaves unguarded and why the hook has been left alone for now.

## Useful commands

```bash
# Whole suite (from the root)
python -m pytest -q                  # backend + setup program, gated
python -m pytest tests/installer -q --no-cov   # setup program only, ungated

# Backend (from backend/)
pytest                               # the gated backend suite
pytest -k "test_parse" -q --no-cov   # tests matching a pattern
black src/ tests/ && isort src/ tests/
mypy src/ && pylint src/

# Linters, on the surface that is clean (from the root)
ruff check --isolated installer installer_main.py tests
flake8 --max-line-length=88 installer installer_main.py tests

# Frontend (from frontend/)
npm run test:ui                      # vitest UI
npm run type-check && npm run lint
```

The `--max-line-length=88` is needed because there is no flake8
configuration file in the repository, so flake8 would otherwise default to
79 while black is set to 88.

## Resources

- [FastAPI documentation](https://fastapi.tiangolo.com/)
- [React documentation](https://react.dev/)
- [Pydantic documentation](https://docs.pydantic.dev/)
- [Material-UI documentation](https://mui.com/)
- [Elite: Dangerous journal documentation](https://elite-journal.readthedocs.io/)

## Next steps

- Building the Windows release: [DEVELOPMENT-README.md](DEVELOPMENT-README.md)
- Understanding the internals: [ARCHITECTURE.md](ARCHITECTURE.md)
- Adding code and tests: [TESTING.md](TESTING.md)
