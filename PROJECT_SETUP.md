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
├── GameGlass-Integration.md  # GameGlass shard integration
├── VERSION                   # Single source of truth for the version
├── buildexe.py               # Windows runtime EXE build (Nuitka)
├── buildinstaller.py         # Windows GUI installer build (Nuitka)
├── installer/                # PySide6 installer UI (app.py, css.py)
├── backend/                  # Python FastAPI backend
│   ├── src/                  # models, services, repositories, api, utils, runtime
│   ├── tests/unit/           # pytest suite (100% gate; see TESTING.md)
│   ├── config.yaml           # non-sensitive backend config
│   ├── requirements.txt      # runtime dependencies
│   ├── requirements-dev.txt  # dev/build dependencies (incl. Nuitka)
│   ├── pytest.ini            # pytest + coverage gate configuration
│   └── pyproject.toml        # black/isort/coverage configuration
├── frontend/                 # React + TypeScript (Vite, MUI, Zustand)
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── docs/                     # GitHub Pages site
└── run-edca*.sh / .bat       # convenience run scripts
```

## Setup steps

### 1. Backend

```bash
cd backend
python -m venv venv            # or: uv venv venv
venv\Scripts\activate          # Windows; source venv/bin/activate on Unix
pip install -r requirements-dev.txt
```

Copy `backend/example.commander.yaml` to `backend/commander.yaml` if you
want Inara integration (the file is gitignored; never commit real keys).

### 2. Frontend

```bash
cd frontend
npm install
```

### 3. Verify

```bash
# Backend suite with the coverage gate (from backend/)
pytest -v --cov

# Frontend suite (from frontend/)
npm test
```

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
backend suite including the coverage gate.

## Useful commands

```bash
# Backend (from backend/)
pytest -k "test_parse" -v            # tests matching a pattern
pytest --cov --cov-report=html       # HTML coverage report in htmlcov/
black src/ tests/ && isort src/ tests/
mypy src/ && pylint src/

# Frontend (from frontend/)
npm run test:ui                      # vitest UI
npm run type-check && npm run lint
```

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
